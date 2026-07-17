#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Audio;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Projectiles;

// AGENT MAP: native gameplay sync contract for generated projectiles.
// Hydration sync sends sanitized generated definitions/plans once into the registry
// and exposes baked assets through /get_asset. Full background hydration is allowed
// per generatedItemId/specHash-equivalent key when deduped/cached/coalesced; after
// hydration, item use/projectile spawning should behave like normal tModLoader
// gameplay: Terraria/tML syncs world state, while generated packets carry only compact ids/scalar state needed to
// resolve local cached specs. Do not put full GeneratedItemData, full AttackSpec,
// VfxManifestJson, visual kits, prompts, debug data, or PNG bytes in combat packets.
public sealed partial class GeneratedProjectile
{
    private static bool IsMultiplayerProjectileSyncEnabled()
        => Main.netMode != NetmodeID.SinglePlayer;

    private static bool HasGeneratedVisualIdentity(string? generatedItemId)
        => !string.IsNullOrWhiteSpace(generatedItemId);

    private static bool IsValidVisualSyncOwner(int owner)
        => owner >= 0 && owner < Main.maxPlayers;

    private static bool IsMatchingVisualSyncTarget(Projectile projectile, ProjectileVisualSyncPayload payload, int generatedProjectileType)
        => projectile.active
            && projectile.type == generatedProjectileType
            && projectile.owner == payload.Owner
            && projectile.identity == payload.Identity;

    private static int PendingVfxEventExpiryTick()
        => (int)Main.GameUpdateCount + 5 * 60;

    private static bool ShouldSkipRemoteVfxEventBecauseOwnerAlreadyRenderedIt(ProjectileVfxEventSyncPayload payload)
        => payload.Owner == Main.myPlayer;

    private sealed class ProjectileVisualSyncPayload
    {
        public int Owner;
        public int Identity;
        public string GeneratedItemId = "";
        public int ExpireTick;
    }

    private sealed class ProjectileVfxEventSyncPayload
    {
        public int Owner;
        public int Identity;
        public string GeneratedItemId = "";
        public string EventKind = "hit";
        public Vector2 Center;
        public Vector2 Velocity;
        public int Lifetime;
        public int ExpireTick;
    }

    private static readonly Dictionary<string, ProjectileVisualSyncPayload> PendingProjectileVisualSync = new(StringComparer.Ordinal);
    private static readonly List<ProjectileVfxEventSyncPayload> PendingProjectileVfxEvents = new();
    private static readonly Dictionary<string, int> LastVisualSyncRelayTickByProjectile = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, int> LastVfxEventRelayTickByProjectile = new(StringComparer.Ordinal);
    // v0.4.199: per-id/per-asset retry gates. A single missing generated item or
    // slow PNG must not suppress catch-up requests for every other projectile on
    // the peer for several minutes.
    private static readonly Dictionary<string, int> MissingGeneratedItemRequestTicks = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, int> MissingProjectileAssetRequestTicks = new(StringComparer.OrdinalIgnoreCase);
    private const int MissingGeneratedItemRetryTicks = 90;
    private const int MissingFullRegistryRetryTicks = 5 * 60;
    private const int MissingProjectileAssetRetryTicks = 120;
    private int _pendingNetworkSpecTicks;
    private int _visualSyncRebroadcastsSent;
    // v0.4.30: vanilla-style combat sync with explicit runtime family.
    // GeneratedItemData/VFX manifest is synchronized once into GeneratedItemRegistryService.
    // Projectile packets must stay lean: id + compact AI fields, never per-shot PNG/prompts/VFX JSON.
    private const int MaxSupportedMovementCode = InfiniRuntimeLimits.MaxSupportedMovementCode;
    private const int MaxSupportedEffectCode = InfiniRuntimeLimits.MaxSupportedEffectCode;
    private const int MaxSupportedOnHitCode = InfiniRuntimeLimits.MaxSupportedOnHitCode;
    private const int PendingProjectileVisualSyncMaxEntries = 256;
    private const int PendingProjectileVfxEventMaxEntries = 96;
    private const int PendingVisualSyncExpiryTicks = 60 * 5;
    private const int PendingVfxEventExpiryTicks = 5 * 60;
    private const int ProjectileSyncRelayMinTicks = 2;
    private const int VfxEventSyncRelayMinTicks = 1;
    private const int MaxProjectileRelayEntries = 512;
    private const int ProjectileRelayStateAgeTicks = 10 * 60;
    private const int MaxMissingRequestStateEntries = 512;
    private const int MissingRequestStateAgeTicks = 10 * 60;
    public const byte PacketSyncGeneratedProjectileVisual = InfiniNetPacketIds.SyncGeneratedProjectileVisual;
    public const byte PacketSyncGeneratedProjectileVfxEvent = InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent;
    private const int ProjectileSyncVersion = 20;
    private const int ProjectileVisualSyncVersion = 3;


    public void BroadcastVisualSync()
    {
        if (!IsMultiplayerProjectileSyncEnabled())
            return;
        if (!HasGeneratedVisualIdentity(_generatedItemId))
            return;
        // In multiplayer, vanilla projectile sync can arrive on remote peers without the
        // generated item presentation context. Send one tiny id-only context packet
        // keyed by owner+identity; registry/asset hydration supplies sprite/style data.
        var payload = BuildVisualSyncPayload();
        SendProjectileVisualSyncPayload(payload, toClient: -1, ignoreClient: -1);
    }

    private ProjectileVisualSyncPayload BuildVisualSyncPayload()
    {
        return new ProjectileVisualSyncPayload
        {
            Owner = Projectile.owner,
            Identity = Projectile.identity,
            GeneratedItemId = ShortNet(_generatedItemId, 96),
        };
    }

    private static string ShortNet(string? value, int max)
    {
        if (string.IsNullOrEmpty(value) || max <= 0) return "";
        return value.Length <= max ? value : value[..max];
    }

    private static string VisualSyncKey(int owner, int identity) => owner.ToString() + ":" + identity.ToString();

    private static bool TryResolveServerOwnedGeneratedProjectile(int whoAmI, int identity, out GeneratedProjectile generated)
    {
        generated = null!;
        if (!IsValidVisualSyncOwner(whoAmI) || identity < 0)
            return false;
        int generatedType = ModContent.ProjectileType<GeneratedProjectile>();
        for (int i = 0; i < Main.maxProjectiles; i++)
        {
            Projectile projectile = Main.projectile[i];
            if (!projectile.active || projectile.owner != whoAmI || projectile.identity != identity || projectile.type != generatedType)
                continue;
            if (projectile.ModProjectile is GeneratedProjectile candidate)
            {
                generated = candidate;
                return true;
            }
        }
        return false;
    }

    private static bool TryAcceptProjectileRelay(Dictionary<string, int> relayTicks, int owner, int identity, int minimumTicks)
    {
        string key = VisualSyncKey(owner, identity);
        int now = (int)Main.GameUpdateCount;
        lock (relayTicks)
        {
            foreach (string stale in relayTicks.Where(x => now - x.Value >= ProjectileRelayStateAgeTicks).Select(x => x.Key).ToList())
                relayTicks.Remove(stale);
            if (relayTicks.TryGetValue(key, out int last) && now - last < minimumTicks)
                return false;
            if (!relayTicks.ContainsKey(key) && relayTicks.Count >= MaxProjectileRelayEntries)
            {
                string oldest = relayTicks.OrderBy(x => x.Value).First().Key;
                relayTicks.Remove(oldest);
            }
            relayTicks[key] = now;
            return true;
        }
    }

    private static void WriteProjectileVisualSyncPayload(BinaryWriter writer, ProjectileVisualSyncPayload payload)
    {
        writer.Write(ProjectileVisualSyncVersion);
        writer.Write(payload.Owner);
        writer.Write(payload.Identity);
        writer.Write(ShortNet(payload.GeneratedItemId, 96));
    }

    private static ProjectileVisualSyncPayload ReadProjectileVisualSyncPayload(BinaryReader reader)
    {
        int version = reader.ReadInt32();
        if (version != ProjectileVisualSyncVersion)
            throw new InvalidDataException($"Unsupported projectile visual sync version {version}; expected {ProjectileVisualSyncVersion}.");
        return new ProjectileVisualSyncPayload
        {
            Owner = reader.ReadInt32(),
            Identity = reader.ReadInt32(),
            GeneratedItemId = reader.ReadString(),
        };
    }

    private static void SendProjectileVisualSyncPayload(ProjectileVisualSyncPayload payload, int toClient, int ignoreClient)
    {
        if (InfiniCrafterLocalMod.Instance is null)
            return;
        var packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketSyncGeneratedProjectileVisual);
        WriteProjectileVisualSyncPayload(packet, payload);
        if (Main.netMode == NetmodeID.Server)
            packet.Send(toClient, ignoreClient);
        else
            packet.Send();
    }

    public static void HandleProjectileVisualSyncPacket(BinaryReader reader, int whoAmI)
    {
        ProjectileVisualSyncPayload payload;
        try { payload = ReadProjectileVisualSyncPayload(reader); }
        catch (Exception ex)
        {
            LogProjectileWarning("Generated projectile visual sync packet could not be read.", ex);
            return;
        }
        if (payload.Identity < 0 || !IsValidVisualSyncOwner(payload.Owner))
            return;

        if (Main.netMode == NetmodeID.Server)
        {
            if (!TryResolveServerOwnedGeneratedProjectile(whoAmI, payload.Identity, out GeneratedProjectile generated))
                return;
            if (!HasGeneratedVisualIdentity(generated._generatedItemId))
                return;
            if (!TryAcceptProjectileRelay(LastVisualSyncRelayTickByProjectile, whoAmI, payload.Identity, ProjectileSyncRelayMinTicks))
                return;
            payload.Owner = whoAmI;
            payload.GeneratedItemId = ShortNet(generated._generatedItemId, 96);
            SendProjectileVisualSyncPayload(payload, toClient: -1, ignoreClient: whoAmI);
            return;
        }

        if (!TryApplyProjectileVisualSyncPayload(payload))
        {
            StorePendingProjectileVisualSync(payload);
            if (!string.IsNullOrWhiteSpace(payload.GeneratedItemId))
                RequestOneGeneratedItemForMissingProjectile(payload.GeneratedItemId);
        }
    }

    private const int ProjectileVfxEventSyncVersion = 2;

    private ProjectileVfxEventSyncPayload BuildVfxEventSyncPayload(string eventKind, Vector2 center, int lifetime, Vector2 inheritedVelocity)
    {
        return new ProjectileVfxEventSyncPayload
        {
            Owner = Projectile.owner,
            Identity = Projectile.identity,
            GeneratedItemId = ShortNet(_generatedItemId, 96),
            EventKind = ShortNet(string.IsNullOrWhiteSpace(eventKind) ? "hit" : eventKind.ToLowerInvariant(), 24),
            Center = center,
            Velocity = inheritedVelocity,
            Lifetime = Math.Clamp(lifetime, 6, 180),
        };
    }

    private static void WriteProjectileVfxEventPayload(BinaryWriter writer, ProjectileVfxEventSyncPayload payload)
    {
        writer.Write(ProjectileVfxEventSyncVersion);
        writer.Write(payload.Owner);
        writer.Write(payload.Identity);
        writer.Write(ShortNet(payload.GeneratedItemId, 96));
        writer.Write(ShortNet(payload.EventKind, 24));
        writer.Write(payload.Center.X);
        writer.Write(payload.Center.Y);
        writer.Write(payload.Velocity.X);
        writer.Write(payload.Velocity.Y);
        writer.Write(Math.Clamp(payload.Lifetime, 6, 180));
    }

    private static ProjectileVfxEventSyncPayload ReadProjectileVfxEventPayload(BinaryReader reader)
    {
        int version = reader.ReadInt32();
        if (version != ProjectileVfxEventSyncVersion)
            throw new InvalidDataException($"Unsupported projectile VFX event sync version {version}; expected {ProjectileVfxEventSyncVersion}.");
        return new ProjectileVfxEventSyncPayload
        {
            Owner = reader.ReadInt32(),
            Identity = reader.ReadInt32(),
            GeneratedItemId = reader.ReadString(),
            EventKind = reader.ReadString(),
            Center = new Vector2(reader.ReadSingle(), reader.ReadSingle()),
            Velocity = new Vector2(reader.ReadSingle(), reader.ReadSingle()),
            Lifetime = reader.ReadInt32(),
        };
    }

    private static void SendProjectileVfxEventPayload(ProjectileVfxEventSyncPayload payload, int toClient, int ignoreClient)
    {
        if (InfiniCrafterLocalMod.Instance is null || Main.netMode == NetmodeID.SinglePlayer)
            return;
        var packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketSyncGeneratedProjectileVfxEvent);
        WriteProjectileVfxEventPayload(packet, payload);
        if (Main.netMode == NetmodeID.Server)
            packet.Send(toClient, ignoreClient);
        else
            packet.Send();
    }

    public static void HandleProjectileVfxEventSyncPacket(BinaryReader reader, int whoAmI)
    {
        ProjectileVfxEventSyncPayload payload;
        try { payload = ReadProjectileVfxEventPayload(reader); }
        catch (Exception ex)
        {
            LogProjectileWarning("Generated projectile VFX event sync packet could not be read.", ex);
            return;
        }

        if (!IsValidVisualSyncOwner(payload.Owner))
            return;

        if (Main.netMode == NetmodeID.Server)
        {
            if (!TryResolveServerOwnedGeneratedProjectile(whoAmI, payload.Identity, out GeneratedProjectile generated))
                return;
            if (!HasGeneratedVisualIdentity(generated._generatedItemId))
                return;
            if (!string.Equals(payload.EventKind, "hit", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(payload.EventKind, "kill", StringComparison.OrdinalIgnoreCase))
                return;
            if (!TryAcceptProjectileRelay(LastVfxEventRelayTickByProjectile, whoAmI, payload.Identity, VfxEventSyncRelayMinTicks))
                return;
            payload.Owner = whoAmI;
            payload.GeneratedItemId = ShortNet(generated._generatedItemId, 96);
            payload.EventKind = payload.EventKind.ToLowerInvariant();
            payload.Center = generated.Projectile.Center;
            payload.Velocity = generated.Projectile.velocity;
            payload.Lifetime = Math.Clamp(payload.Lifetime, 6, 180);
            SendProjectileVfxEventPayload(payload, toClient: -1, ignoreClient: whoAmI);
            return;
        }

        if (!TrySpawnSyncedVfxEvent(payload))
            StorePendingVfxEvent(payload);
    }

    public static void ClearPresentationSyncCaches()
    {
        lock (PendingProjectileVisualSync) PendingProjectileVisualSync.Clear();
        lock (PendingProjectileVfxEvents) PendingProjectileVfxEvents.Clear();
        lock (LastVisualSyncRelayTickByProjectile) LastVisualSyncRelayTickByProjectile.Clear();
        lock (LastVfxEventRelayTickByProjectile) LastVfxEventRelayTickByProjectile.Clear();
        lock (MissingGeneratedItemRequestTicks) MissingGeneratedItemRequestTicks.Clear();
        lock (MissingProjectileAssetRequestTicks) MissingProjectileAssetRequestTicks.Clear();
    }

    private static void PrunePendingProjectileVisualSyncLocked(int now)
    {
        foreach (string stale in PendingProjectileVisualSync
            .Where(x => x.Value.ExpireTick > 0 && x.Value.ExpireTick <= now)
            .Select(x => x.Key)
            .ToList())
            PendingProjectileVisualSync.Remove(stale);
    }

    private static void StorePendingProjectileVisualSync(ProjectileVisualSyncPayload payload)
    {
        int now = (int)Main.GameUpdateCount;
        payload.ExpireTick = now + PendingVisualSyncExpiryTicks;
        lock (PendingProjectileVisualSync)
        {
            PrunePendingProjectileVisualSyncLocked(now);
            string key = VisualSyncKey(payload.Owner, payload.Identity);
            if (!PendingProjectileVisualSync.ContainsKey(key) && PendingProjectileVisualSync.Count >= PendingProjectileVisualSyncMaxEntries)
            {
                string oldest = PendingProjectileVisualSync.OrderBy(x => x.Value.ExpireTick).First().Key;
                PendingProjectileVisualSync.Remove(oldest);
            }
            PendingProjectileVisualSync[key] = payload;
        }
    }

    private static void PruneTickMapLocked(Dictionary<string, int> map, int now, int maxEntries, int maxAgeTicks, string incomingKey)
    {
        foreach (string stale in map.Where(x => now - x.Value >= maxAgeTicks).Select(x => x.Key).ToList())
            map.Remove(stale);
        if (!map.ContainsKey(incomingKey))
        {
            while (map.Count >= maxEntries)
            {
                string oldest = map.OrderBy(x => x.Value).First().Key;
                map.Remove(oldest);
            }
        }
    }

    public static void FlushPendingProjectileVisualSyncForGeneratedItem(string? generatedItemId)
    {
        string id = (generatedItemId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id) || Main.dedServ)
            return;
        List<ProjectileVisualSyncPayload> ready = new();
        lock (PendingProjectileVisualSync)
        {
            PrunePendingProjectileVisualSyncLocked((int)Main.GameUpdateCount);
            foreach (var kv in PendingProjectileVisualSync.ToArray())
            {
                var payload = kv.Value;
                if (string.Equals(payload.GeneratedItemId, id, StringComparison.Ordinal))
                {
                    ready.Add(payload);
                    PendingProjectileVisualSync.Remove(kv.Key);
                }
            }
        }
        foreach (var payload in ready)
        {
            if (!TryApplyProjectileVisualSyncPayload(payload))
                StorePendingProjectileVisualSync(payload);
        }
    }

    public static void FlushPendingVfxEventsForGeneratedItem(string? generatedItemId)
    {
        string id = (generatedItemId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id) || Main.dedServ)
            return;
        List<ProjectileVfxEventSyncPayload> ready = new();
        int now = (int)Main.GameUpdateCount;
        lock (PendingProjectileVfxEvents)
        {
            for (int i = PendingProjectileVfxEvents.Count - 1; i >= 0; i--)
            {
                var payload = PendingProjectileVfxEvents[i];
                if (payload.ExpireTick > 0 && payload.ExpireTick < now)
                {
                    PendingProjectileVfxEvents.RemoveAt(i);
                    continue;
                }
                if (string.Equals(payload.GeneratedItemId, id, StringComparison.Ordinal))
                {
                    ready.Add(payload);
                    PendingProjectileVfxEvents.RemoveAt(i);
                }
            }
        }
        foreach (var payload in ready)
            TrySpawnSyncedVfxEvent(payload);
    }

    private static void StorePendingVfxEvent(ProjectileVfxEventSyncPayload payload)
    {
        if (!HasGeneratedVisualIdentity(payload.GeneratedItemId))
            return;
        payload.ExpireTick = PendingVfxEventExpiryTick();
        lock (PendingProjectileVfxEvents)
        {
            if (PendingProjectileVfxEvents.Count >= PendingProjectileVfxEventMaxEntries)
                PendingProjectileVfxEvents.RemoveAt(0);
            PendingProjectileVfxEvents.Add(payload);
        }
        RequestOneGeneratedItemForMissingProjectile(payload.GeneratedItemId);
    }

    private static bool TrySpawnSyncedVfxEvent(ProjectileVfxEventSyncPayload payload)
    {
        if (Main.dedServ || !HasGeneratedVisualIdentity(payload.GeneratedItemId))
            return false;
        if (ShouldSkipRemoteVfxEventBecauseOwnerAlreadyRenderedIt(payload))
            return true; // the owner already spawned the local overlay before sending this packet.

        AttackSpec? spec = InfiniCrafterLocalMod.GeneratedItems?.TryGetAttack(payload.GeneratedItemId);
        VfxManifestSpec manifest = InfiniCrafterLocalMod.GeneratedItems?.TryGetVfxManifest(payload.GeneratedItemId) ?? VfxManifestSpec.Empty();
        if (spec is null || manifest is null || !manifest.HasSlots)
        {
            RequestOneGeneratedItemForMissingProjectile(payload.GeneratedItemId);
            return false;
        }
        return GeneratedVfxOverlayProjectile.Spawn(
            new EntitySource_Misc("InfiniCraftRemoteVfx"),
            payload.Center,
            payload.Velocity,
            Math.Clamp(payload.Owner, 0, Main.maxPlayers - 1),
            spec,
            manifest,
            payload.EventKind,
            payload.Lifetime);
    }

    private void BroadcastVfxEventSync(string eventKind, Vector2 center, int lifetime, Vector2 inheritedVelocity)
    {
        if (!IsMultiplayerProjectileSyncEnabled() || Projectile.owner != Main.myPlayer)
            return;
        if (!HasGeneratedVisualIdentity(_generatedItemId) || _vfxManifest is null || !_vfxManifest.HasSlots)
            return;
        SendProjectileVfxEventPayload(BuildVfxEventSyncPayload(eventKind, center, lifetime, inheritedVelocity), toClient: -1, ignoreClient: -1);
    }

    private static bool TryApplyProjectileVisualSyncPayload(ProjectileVisualSyncPayload payload)
    {
        int type = ModContent.ProjectileType<GeneratedProjectile>();
        for (int i = 0; i < Main.maxProjectiles; i++)
        {
            Projectile projectile = Main.projectile[i];
            if (!IsMatchingVisualSyncTarget(projectile, payload, type))
                continue;
            if (projectile.ModProjectile is GeneratedProjectile generated)
            {
                generated.ApplyProjectileVisualSyncPayload(payload);
                return true;
            }
        }
        return false;
    }

    private void ApplyPendingProjectileVisualSyncIfAny()
    {
        string key = VisualSyncKey(Projectile.owner, Projectile.identity);
        ProjectileVisualSyncPayload? payload = null;
        lock (PendingProjectileVisualSync)
        {
            PrunePendingProjectileVisualSyncLocked((int)Main.GameUpdateCount);
            if (PendingProjectileVisualSync.TryGetValue(key, out payload))
                PendingProjectileVisualSync.Remove(key);
        }
        if (payload is not null)
            ApplyProjectileVisualSyncPayload(payload);
    }

    private void ApplyProjectileVisualSyncPayload(ProjectileVisualSyncPayload payload)
    {
        if (!string.IsNullOrWhiteSpace(payload.GeneratedItemId))
            _generatedItemId = payload.GeneratedItemId.Trim();

        bool restoredFromRegistry = false;
        if (!string.IsNullOrWhiteSpace(_generatedItemId) && InfiniCrafterLocalMod.GeneratedItems is not null)
        {
            AttackSpec? parent = InfiniCrafterLocalMod.GeneratedItems.TryGetAttack(_generatedItemId);
            if (parent is not null)
            {
                // This relay carries presentation identity only and can race ahead
                // of ExtraAI. Never treat its arrival as proof that this instance is
                // the Root variant; gameplay hydration is owned by the compact
                // identity+variant packet and the pending-AI retry path below.
                if (_configured && RuntimeCodesSupported())
                {
                    CopyMissingPresentationPaths(parent);
                    if (string.IsNullOrWhiteSpace(_spec.VisualMode)) _spec.VisualMode = parent.VisualMode ?? "";
                    if (string.IsNullOrWhiteSpace(_spec.TrailStyle)) _spec.TrailStyle = parent.TrailStyle ?? "";
                    if (string.IsNullOrWhiteSpace(_spec.ImpactStyle)) _spec.ImpactStyle = parent.ImpactStyle ?? "";
                    if (string.IsNullOrWhiteSpace(_spec.PrimaryColorName)) _spec.PrimaryColorName = parent.PrimaryColorName ?? "";
                }
                restoredFromRegistry = true;
            }
        }

        if (!restoredFromRegistry && !string.IsNullOrWhiteSpace(_generatedItemId))
            RequestOneGeneratedItemForMissingProjectile(payload.GeneratedItemId);
        RequestProjectileAssetCatchupIfMissing(_spec.ProjectileSpritePath, _generatedItemId);
    }


    public override void SendExtraAI(BinaryWriter writer)
    {
        // The world-scoped registry owns the immutable authored AttackSpec. Normal
        // combat packets identify that spec and carry only per-instance state that
        // Terraria cannot reconstruct from the registry or vanilla projectile fields.
        writer.Write(ProjectileSyncVersion);
        writer.Write(_configured);
        writer.Write(ShortNet(_generatedItemId, 96));
        writer.Write((byte)_runtimeVariant);
        writer.Write(_chargeTicksAccumulated);
        writer.Write(_sentryFireTimer);
        writer.Write(_beamLengthPx);
        writer.Write(Projectile.localAI[1]);
        writer.Write(Projectile.localAI[2]);
        writer.Write(_spawnIgnoreNpc);
        writer.Write(_spawnIgnoreTicks);
        writer.Write(_stuckToTile);
        writer.Write(_returningPhase);
    }

    public override void ReceiveExtraAI(BinaryReader reader)
    {
        try
        {
            int syncVersion = reader.ReadInt32();
            if (syncVersion != ProjectileSyncVersion)
            {
                DisableAfterNetworkReadFailure($"Unsupported GeneratedProjectile sync version {syncVersion}; expected {ProjectileSyncVersion}.");
                return;
            }
            bool packetConfigured = reader.ReadBoolean();
            _generatedItemId = reader.ReadString();
            _runtimeVariant = (GeneratedProjectileRuntimeVariant)reader.ReadByte();
            _chargeTicksAccumulated = reader.ReadInt32();
            _sentryFireTimer = reader.ReadInt32();
            _beamLengthPx = reader.ReadSingle();
            Projectile.localAI[1] = reader.ReadSingle();
            Projectile.localAI[2] = reader.ReadSingle();
            _spawnIgnoreNpc = reader.ReadInt32();
            _spawnIgnoreTicks = reader.ReadInt32();
            _stuckToTile = reader.ReadBoolean();
            _returningPhase = reader.ReadBoolean();

            if (_generatedItemId.Length > 96
                || (packetConfigured && _generatedItemId.Length <= 0)
                || !GeneratedChildSpecPolicy.IsKnownVariant(_runtimeVariant)
                || _spawnIgnoreNpc < -1 || _spawnIgnoreNpc >= Main.maxNPCs
                || _spawnIgnoreTicks < 0 || _spawnIgnoreTicks > 10)
            {
                DisableAfterNetworkReadFailure("Generated projectile packet contains an invalid registry identity or runtime variant.");
                return;
            }
            _configured = false;
            _statsApplied = false;
            if (!packetConfigured)
            {
                if (Projectile.active)
                    DeferUnconfiguredNetworkProjectile();
                return;
            }
            if (!TryHydrateRuntimeVariantFromRegistry())
            {
                if (Projectile.active)
                    DeferUnconfiguredNetworkProjectile();
                return;
            }
        }
        catch (Exception ex)
        {
            DisableAfterNetworkReadFailure("Projectile network payload could not be read.", ex);
            return;
        }
    }

    private bool TryHydrateRuntimeVariantFromRegistry()
    {
        if (string.IsNullOrWhiteSpace(_generatedItemId)
            || global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is null)
        {
            RequestOneGeneratedItemForMissingProjectile(_generatedItemId);
            return false;
        }

        AttackSpec? parent = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGetAttack(_generatedItemId);
        if (parent is null)
        {
            RequestOneGeneratedItemForMissingProjectile(_generatedItemId);
            return false;
        }
        if (!GeneratedChildSpecPolicy.TryCreateRuntimeVariant(parent, _runtimeVariant, out AttackSpec resolved))
        {
            DisableUnsupportedProjectile($"Generated projectile variant {_runtimeVariant} is not allowed by registry item {_generatedItemId}.");
            return false;
        }

        if (GeneratedChildSpecPolicy.UsesGenericChildPresentation(_runtimeVariant))
            ApplyAuthoredChildPresentation(resolved, parent);
        VfxManifestSpec manifest = GeneratedChildSpecPolicy.UsesRootVfxManifest(_runtimeVariant)
            ? global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGetVfxManifest(_generatedItemId)
            : new VfxManifestSpec();
        ApplyResolvedRuntimeVariant(resolved, manifest);
        return _configured && Projectile.active;
    }

    private void ApplyResolvedRuntimeVariant(AttackSpec resolved, VfxManifestSpec manifest)
    {
        int chargeTicks = _chargeTicksAccumulated;
        int sentryTimer = _sentryFireTimer;
        float beamLength = _beamLengthPx;
        float childDepth = Projectile.localAI[1];
        float rootIdentity = Projectile.localAI[2];
        bool stuckToTile = _stuckToTile;
        bool returningPhase = _returningPhase;

        ApplyHydratedGeneratedSpec(resolved, manifest, _generatedItemId, _runtimeVariant);
        if (!_configured || !Projectile.active)
            return;

        _chargeTicksAccumulated = Math.Clamp(chargeTicks, 0, Math.Clamp(resolved.ChargeTicks, 1, 300));
        _sentryFireTimer = Math.Clamp(sentryTimer, 0, Math.Clamp(resolved.SentryAttackIntervalTicks, 12, 180));
        _beamLengthPx = float.IsFinite(beamLength)
            ? Math.Clamp(beamLength, 0f, ConfiguredRangePixels(560f))
            : 0f;
        Projectile.localAI[1] = float.IsFinite(childDepth) ? Math.Clamp(childDepth, 0f, 3f) : 0f;
        Projectile.localAI[2] = float.IsFinite(rootIdentity) ? Math.Clamp(rootIdentity, 0f, 1_000_000f) : 0f;
        _stuckToTile = stuckToTile;
        _returningPhase = returningPhase;
        if (_stuckToTile || _returningPhase)
            Projectile.tileCollide = false;
    }

    private void DeferUnconfiguredNetworkProjectile()
    {
        // In multiplayer tML can send the initial projectile entity before the mod
        // projectile has received ApplyGeneratedSpec() and before the registry packet
        // reaches the peer.  Do not treat that first empty packet as legacy data: keep
        // the projectile harmless for a short grace window and let the next configured
        // net update hydrate it.  This avoids random projectile/child/VFX loss without
        // sending bulky item JSON in every projectile packet.
        ClearResolvedRuntimeSpec(Math.Max(_pendingNetworkSpecTicks, 45));
        Projectile.damage = 0;
        Projectile.knockBack = 0f;
        Projectile.friendly = false;
        Projectile.hostile = false;
        Projectile.timeLeft = Math.Max(Projectile.timeLeft, 45);
        Projectile.netUpdate = false;
    }

    private void ClearResolvedRuntimeSpec(int pendingSpecTicks)
    {
        // Clear only the hydrated immutable view. Runtime identity and mutable
        // instance state survive a registry race so the exact variant can resume.
        _configured = false;
        _statsApplied = false;
        _pendingNetworkSpecTicks = pendingSpecTicks;
        _spec = new AttackSpec { Enabled = false, DustSpawnDenom = 0, BurstDustCap = 0, RuntimePlanAuthored = true };
        _vfxManifest = new VfxManifestSpec();
        _vfxState = new InfiniVfxState();
    }

    private void ResetRuntimeSpecState(int pendingSpecTicks = 0, bool clearGeneratedId = false, bool deactivateProjectile = false)
    {
        ClearResolvedRuntimeSpec(pendingSpecTicks);
        _runtimeSpecEverApplied = false;
        _runtimeVariant = GeneratedProjectileRuntimeVariant.Root;
        _returningPhase = false;
        _orbitInitialized = false;
        _whipInitialized = false;
        _whipBaseDirection = Vector2.Zero;
        _whipControlPoints.Clear();
        if (clearGeneratedId)
        {
            _generatedItemId = "";
        }
        if (deactivateProjectile)
        {
            Projectile.active = false;
            Projectile.netUpdate = false;
        }
    }

    private void DisableAfterNetworkReadFailure(string reason = "network read failure", Exception? ex = null)
    {
        LogProjectileWarning(reason, ex);
        ResetRuntimeSpecState(clearGeneratedId: true, deactivateProjectile: true);
    }


    private static void RequestRegistryCatchupForMissingProjectile()
        => RequestOneGeneratedItemForMissingProjectile("");

    private static void RequestOneGeneratedItemForMissingProjectile(string? generatedItemId)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        string id = (generatedItemId ?? "").Trim();
        string key = string.IsNullOrWhiteSpace(id) ? "__full__" : id;
        int retryTicks = string.IsNullOrWhiteSpace(id) ? MissingFullRegistryRetryTicks : MissingGeneratedItemRetryTicks;
        int now = (int)Main.GameUpdateCount;
        lock (MissingGeneratedItemRequestTicks)
        {
            if (MissingGeneratedItemRequestTicks.TryGetValue(key, out int last) && now - last < retryTicks)
                return;
            PruneTickMapLocked(MissingGeneratedItemRequestTicks, now, MaxMissingRequestStateEntries, MissingRequestStateAgeTicks, key);
            MissingGeneratedItemRequestTicks[key] = now;
        }
        if (!string.IsNullOrWhiteSpace(id))
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: true);
        else
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer(forceAssetRetry: true);
    }

    private void MaybeRebroadcastVisualSyncForEarlyRemoteCatchup()
    {
        if (!IsMultiplayerProjectileSyncEnabled() || Projectile.owner != Main.myPlayer)
            return;
        if (!HasGeneratedVisualIdentity(_generatedItemId))
            return;
        int tick = (int)Projectile.localAI[0];
        if ((_visualSyncRebroadcastsSent == 0 && tick >= 2) || (_visualSyncRebroadcastsSent == 1 && tick >= 18))
        {
            _visualSyncRebroadcastsSent++;
            BroadcastVisualSync();
        }
    }

}
