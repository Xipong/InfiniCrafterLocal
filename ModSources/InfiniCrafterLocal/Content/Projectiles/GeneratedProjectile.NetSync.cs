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
    private const int NetProseMaxChars = InfiniRuntimeLimits.NetProseMaxChars;    // descriptive/script-like strings are not executable network state.
    private const int MaxSupportedMovementCode = InfiniRuntimeLimits.MaxSupportedMovementCode;
    private const int MaxSupportedEffectCode = InfiniRuntimeLimits.MaxSupportedEffectCode;
    private const int MaxSupportedOnHitCode = InfiniRuntimeLimits.MaxSupportedOnHitCode;
    public const byte PacketSyncGeneratedProjectileVisual = InfiniNetPacketIds.SyncGeneratedProjectileVisual;
    public const byte PacketSyncGeneratedProjectileVfxEvent = InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent;
    private const int ProjectileSyncVersion = 6;
    private const int ProjectileVisualSyncVersion = 3;
    private const ushort SyncFlagMobility = 1 << 0;
    private const ushort SyncFlagRuntimeLight = 1 << 1;
    private const ushort SyncFlagSplitRadii = 1 << 2;


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
            // Client-owned projectile visuals are not guaranteed to survive the vanilla
            // client->server->clients projectile relay.  Rebroadcast this compact visual
            // context to every other peer; stamp the owner from the sender instead of
            // trusting client-supplied identity text.
            payload.Owner = Math.Clamp(whoAmI, 0, Main.maxPlayers - 1);
            SendProjectileVisualSyncPayload(payload, toClient: -1, ignoreClient: whoAmI);
            return;
        }

        if (!TryApplyProjectileVisualSyncPayload(payload))
        {
            lock (PendingProjectileVisualSync)
                PendingProjectileVisualSync[VisualSyncKey(payload.Owner, payload.Identity)] = payload;
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
            // Owner/local client sends one compact hit/kill visual event. Relay it to the
            // other clients; stamp the owner from the sender so visual overlays cannot be
            // spoofed onto another player's projectile stream.
            payload.Owner = Math.Clamp(whoAmI, 0, Main.maxPlayers - 1);
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
        lock (MissingGeneratedItemRequestTicks) MissingGeneratedItemRequestTicks.Clear();
        lock (MissingProjectileAssetRequestTicks) MissingProjectileAssetRequestTicks.Clear();
    }

    public static void FlushPendingProjectileVisualSyncForGeneratedItem(string? generatedItemId)
    {
        string id = (generatedItemId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id) || Main.dedServ)
            return;
        List<ProjectileVisualSyncPayload> ready = new();
        lock (PendingProjectileVisualSync)
        {
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
            {
                lock (PendingProjectileVisualSync)
                    PendingProjectileVisualSync[VisualSyncKey(payload.Owner, payload.Identity)] = payload;
            }
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
            if (PendingProjectileVfxEvents.Count > 96)
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
                if (!_configured || !RuntimeCodesSupported())
                    ApplyGeneratedSpec(parent, InfiniCrafterLocalMod.GeneratedItems.TryGetVfxManifest(_generatedItemId), _generatedItemId);
                else
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
        // Native gameplay sync contract: projectile packets carry compact ids/scalar
        // state only. Full GeneratedItemData, AttackSpec, VfxManifestJson, visualKit,
        // prompts, debug data and PNG/JSON bytes are hydrated through registry + /get_asset.
        string SpritePathForNet(string? path) => "";
        bool childShard = Projectile.localAI[1] > 0.001f;
        ushort syncFlags = 0;
        if (!string.IsNullOrWhiteSpace(_spec.MobilityMode)) syncFlags |= SyncFlagMobility;
        if (_spec.RuntimeLightStrength > 0f) syncFlags |= SyncFlagRuntimeLight;
        if (_spec.ImpactVfxRadiusPx > 0 || _spec.AoeDamageRadiusPx > 0 || _spec.ContactForgivenessPx > 0) syncFlags |= SyncFlagSplitRadii;

        writer.Write(ProjectileSyncVersion);
        writer.Write(syncFlags);
        writer.Write(_configured);
        writer.Write(ShortNet(_generatedItemId, 96));
        writer.Write(childShard);
        writer.Write(_spec.MovementCode);
        writer.Write(_spec.EffectCode);
        writer.Write(_spec.OnHitCode);
        writer.Write(_spec.ProjectileWidth);
        writer.Write(_spec.ProjectileHeight);
        writer.Write(_spec.ProjectileScale);
        writer.Write(_spec.HitboxScale);
        writer.Write(_spec.ExplosionRadius);
        writer.Write(_spec.ImpactVfxRadiusPx);
        writer.Write(_spec.AoeDamageRadiusPx);
        writer.Write(_spec.ContactForgivenessPx);
        writer.Write(_spec.Lifetime);
        writer.Write(_spec.Pierce);
        writer.Write(_spec.ExtraUpdates);
        writer.Write(_spec.TileCollide);
        writer.Write(_spec.BounceCount);
        writer.Write(_spec.SplitCount);
        writer.Write(_spec.ChainCount);
        writer.Write(_spec.ImmunityCooldown);
        writer.Write(_spec.ProcMode);
        writer.Write(ShortNet(_spec.Pattern, 80));
        writer.Write(_spec.MaxChildProjectiles);
        writer.Write(_spec.MaxChildDepth);
        writer.Write(_spec.DustSpawnDenom);
        writer.Write(_spec.BurstDustCap);
        writer.Write(ShortNet(_spec.VisualMode, 60));
        writer.Write(ShortNet(_spec.TrailStyle, 80));
        writer.Write(ShortNet(_spec.ImpactStyle, 80));
        writer.Write(ShortNet(_spec.PrimaryColorName, 48));
        writer.Write(_spec.RuntimeLightStrength);
        writer.Write(ShortNet(_spec.MobilityMode, 32));
        writer.Write(_spec.MobilityRangeTiles);
        writer.Write(_spec.MobilityCooldownTicks);
        writer.Write(_spec.MobilitySafeTileOnly);
        writer.Write(ShortNet(_spec.ImpactSoundProfile, 48));
        writer.Write(_spec.SoundPitch);
        writer.Write(_spec.SoundVolume);
        // v0.4.97: this packet slot used to carry prose/script compatibility strings.
        // Runtime now carries explicit family state instead; prose never participates in projectile AI.
        writer.Write(ShortNet(_spec.RuntimeFamily, 32));
        writer.Write(ShortNet(_spec.Delivery, 40));
        writer.Write(ShortNet(_spec.WeaponFamily, 48));
        writer.Write(ShortNet(_spec.ProjectileFamily, 48));
        writer.Write(ShortNet(_spec.AmmoKind, 32));
        writer.Write(_spec.UseStyleCode);
        writer.Write(_spec.HideUseGraphic);
        writer.Write(_spec.DisableItemMeleeHitbox);
        writer.Write(_spec.OwnerHitCheck);
        writer.Write(_spec.ChannelUse);
        writer.Write((byte)0); // reserved bitset for future projectile sync flags
        writer.Write(ShortNet(_spec.ProjectileShape, 160));
        writer.Write(ShortNet(_spec.ProjectileMotion, 120));
        writer.Write(ShortNet(_spec.ProjectileRotation, 64));
        writer.Write(ShortNet(_spec.ProjectileTrail, 120));
        writer.Write(ShortNet(_spec.ProjectileImpact, 120));
        writer.Write(ShortNet(_spec.SoundUse, 80));
        writer.Write(ShortNet(_spec.SoundImpact, 80));
        writer.Write(SpritePathForNet(_spec.ProjectileSpritePath));
        writer.Write(ShortNet(_spec.ProjectileSpriteStatus, 40));
        writer.Write("");
        writer.Write(SpritePathForNet(_spec.ImpactSpritePath));
        writer.Write(ShortNet(_spec.ImpactSpriteStatus, 40));
        writer.Write("");
        writer.Write(SpritePathForNet(_spec.ChildSpritePath));
        writer.Write(ShortNet(_spec.ChildSpriteStatus, 40));
        writer.Write("");
        writer.Write(SpritePathForNet(_spec.FieldSpritePath));
        writer.Write(ShortNet(_spec.FieldSpriteStatus, 40));
        writer.Write("");
        writer.Write(""); // item-level visual plan is restored from GeneratedItemRegistryService
        writer.Write(_spec.RuntimePlanAuthored);
        writer.Write(_spec.SecondarySpreadRadians);
        writer.Write(_spec.SecondaryDamageMultiplier);
        writer.Write(_spec.SecondaryLifetimeTicks);
        writer.Write(_spec.SameTargetBias);
        writer.Write(ShortNet(_spec.DebuffHint, 80));
        writer.Write(_spec.DebuffTime);
        writer.Write(ShortNet(_spec.SecondaryMaterial, 80));
        writer.Write(ShortNet(_spec.SecondaryProjectileShape, 120));
        writer.Write(Projectile.localAI[1]);
        writer.Write(Projectile.localAI[2]);
        writer.Write(_stuckToTile);
    }

    public override void ReceiveExtraAI(BinaryReader reader)
    {
        bool childShard = false;
        try
        {
            int syncVersion = reader.ReadInt32();
            ushort syncFlags = reader.ReadUInt16();
            if (syncVersion != ProjectileSyncVersion)
            {
                DisableAfterNetworkReadFailure($"Unsupported GeneratedProjectile sync version {syncVersion}; expected {ProjectileSyncVersion}.");
                return;
            }
            bool packetConfigured = reader.ReadBoolean();
            _configured = packetConfigured;
            _generatedItemId = reader.ReadString();
            childShard = reader.ReadBoolean();
            _statsApplied = false;
            _spec = (!childShard && global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is not null)
                ? (global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGetAttack(_generatedItemId) ?? new AttackSpec())
                : new AttackSpec();
            _spec.MovementCode = reader.ReadInt32();
            _spec.EffectCode = reader.ReadInt32();
            _spec.OnHitCode = reader.ReadInt32();
            _spec.ProjectileWidth = reader.ReadInt32();
            _spec.ProjectileHeight = reader.ReadInt32();
            _spec.ProjectileScale = reader.ReadSingle();
            _spec.HitboxScale = reader.ReadSingle();
            _spec.ExplosionRadius = reader.ReadInt32();
            _spec.ImpactVfxRadiusPx = reader.ReadInt32();
            _spec.AoeDamageRadiusPx = reader.ReadInt32();
            _spec.ContactForgivenessPx = reader.ReadInt32();
            _spec.Lifetime = reader.ReadInt32();
            _spec.Pierce = reader.ReadInt32();
            _spec.ExtraUpdates = reader.ReadInt32();
            _spec.TileCollide = reader.ReadBoolean();
            _spec.BounceCount = reader.ReadInt32();
            _spec.SplitCount = reader.ReadInt32();
            _spec.ChainCount = reader.ReadInt32();
            _spec.ImmunityCooldown = reader.ReadInt32();
            _spec.ProcMode = reader.ReadInt32();
            _spec.Pattern = reader.ReadString();
            _spec.MaxChildProjectiles = reader.ReadInt32();
            _spec.MaxChildDepth = reader.ReadInt32();
            _spec.DustSpawnDenom = reader.ReadInt32();
            _spec.BurstDustCap = reader.ReadInt32();
            _spec.VisualMode = reader.ReadString();
            _spec.TrailStyle = reader.ReadString();
            _spec.ImpactStyle = reader.ReadString();
            _spec.PrimaryColorName = reader.ReadString();
            _spec.RuntimeLightStrength = reader.ReadSingle();
            _spec.MobilityMode = reader.ReadString();
            _spec.MobilityRangeTiles = reader.ReadInt32();
            _spec.MobilityCooldownTicks = reader.ReadInt32();
            _spec.MobilitySafeTileOnly = reader.ReadBoolean();
            _spec.ImpactSoundProfile = reader.ReadString();
            _spec.SoundPitch = reader.ReadSingle();
            _spec.SoundVolume = reader.ReadSingle();
            _spec.RuntimeFamily = ReadStringKeepBase(reader, _spec.RuntimeFamily, childShard);
            _spec.Delivery = ReadStringKeepBase(reader, _spec.Delivery, childShard);
            _spec.WeaponFamily = ReadStringKeepBase(reader, _spec.WeaponFamily, childShard);
            _spec.ProjectileFamily = ReadStringKeepBase(reader, _spec.ProjectileFamily, childShard);
            _spec.AmmoKind = ReadStringKeepBase(reader, _spec.AmmoKind, childShard);
            _spec.UseStyleCode = reader.ReadInt32();
            _spec.HideUseGraphic = reader.ReadBoolean();
            _spec.DisableItemMeleeHitbox = reader.ReadBoolean();
            _spec.OwnerHitCheck = reader.ReadBoolean();
            _spec.ChannelUse = reader.ReadBoolean();
            _ = reader.ReadByte(); // reserved bitset for future projectile sync flags
            _spec.ProjectileShape = ReadStringKeepBase(reader, _spec.ProjectileShape, childShard);
            _spec.ProjectileMotion = ReadStringKeepBase(reader, _spec.ProjectileMotion, childShard);
            _spec.ProjectileRotation = ReadStringKeepBase(reader, _spec.ProjectileRotation, childShard);
            _spec.ProjectileTrail = ReadStringKeepBase(reader, _spec.ProjectileTrail, childShard);
            _spec.ProjectileImpact = ReadStringKeepBase(reader, _spec.ProjectileImpact, childShard);
            _spec.SoundUse = ReadStringKeepBase(reader, _spec.SoundUse, childShard);
            _spec.SoundImpact = ReadStringKeepBase(reader, _spec.SoundImpact, childShard);
            _spec.ProjectileSpritePath = ReadStringKeepBase(reader, _spec.ProjectileSpritePath, childShard);
            _spec.ProjectileSpriteStatus = ReadStringKeepBase(reader, _spec.ProjectileSpriteStatus, childShard);
            _spec.ProjectileSpritePrompt = ReadStringKeepBase(reader, _spec.ProjectileSpritePrompt, childShard);
            _spec.ImpactSpritePath = ReadStringKeepBase(reader, _spec.ImpactSpritePath, childShard);
            _spec.ImpactSpriteStatus = ReadStringKeepBase(reader, _spec.ImpactSpriteStatus, childShard);
            _spec.ImpactSpritePrompt = ReadStringKeepBase(reader, _spec.ImpactSpritePrompt, childShard);
            _spec.ChildSpritePath = ReadStringKeepBase(reader, _spec.ChildSpritePath, childShard);
            _spec.ChildSpriteStatus = ReadStringKeepBase(reader, _spec.ChildSpriteStatus, childShard);
            _spec.ChildSpritePrompt = ReadStringKeepBase(reader, _spec.ChildSpritePrompt, childShard);
            _spec.FieldSpritePath = ReadStringKeepBase(reader, _spec.FieldSpritePath, childShard);
            _spec.FieldSpriteStatus = ReadStringKeepBase(reader, _spec.FieldSpriteStatus, childShard);
            _spec.FieldSpritePrompt = ReadStringKeepBase(reader, _spec.FieldSpritePrompt, childShard);
            _spec.VisualAnimationPlan = ReadStringKeepBase(reader, _spec.VisualAnimationPlan, childShard);
            if (!childShard && global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems is not null)
                _vfxManifest = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems.TryGetVfxManifest(_generatedItemId);
            else
                _vfxManifest = VfxManifestSpec.FromJson(_spec.VfxManifestJson);
            HydratePresentationFromRegistryIfPossible();
            _lastReceivedVfxManifestJson = _spec.VfxManifestJson ?? "";
            _vfxState = new InfiniVfxState { LocalSeed = _vfxManifest.Seed };
            try
            {
                _spec.RuntimePlanAuthored = reader.ReadBoolean();
                _spec.SecondarySpreadRadians = reader.ReadSingle();
                _spec.SecondaryDamageMultiplier = reader.ReadSingle();
                _spec.SecondaryLifetimeTicks = reader.ReadInt32();
                _spec.SameTargetBias = reader.ReadSingle();
                _spec.DebuffHint = reader.ReadString();
                _spec.DebuffTime = reader.ReadInt32();
                _spec.SecondaryMaterial = reader.ReadString();
                _spec.SecondaryProjectileShape = reader.ReadString();
                Projectile.localAI[1] = reader.ReadSingle();
                Projectile.localAI[2] = reader.ReadSingle();
                _stuckToTile = reader.ReadBoolean();
            }
            catch (Exception ex)
            {
                DisableAfterNetworkReadFailure("Runtime-authored projectile packet is missing or corrupt. Legacy lean projectile packets are no longer supported.", ex);
                return;
            }
        }
        catch (Exception ex)
        {
            DisableAfterNetworkReadFailure("Projectile network payload could not be read.", ex);
            return;
        }
        if (!_configured)
        {
            DeferUnconfiguredNetworkProjectile();
            return;
        }
        if (!_spec.RuntimePlanAuthored)
        {
            DisableUnsupportedProjectile("Legacy non-runtime-authored generated projectile packet received. This archive is authored-runtime only.");
            return;
        }
        if (!RuntimeCodesSupported())
        {
            DisableUnsupportedProjectile($"Unsupported generated runtime opcode/family after network read: movement={_spec.MovementCode}, effect={_spec.EffectCode}, onHit={_spec.OnHitCode}.");
            return;
        }
        if (childShard)
            RestoreAuthoredChildPresentationFromRegistry();
        _remainingBounces = InitialBounceBudget(_spec);
        ApplyConfiguredStats();
    }

    private void DeferUnconfiguredNetworkProjectile()
    {
        // In multiplayer tML can send the initial projectile entity before the mod
        // projectile has received ApplyGeneratedSpec() and before the registry packet
        // reaches the peer.  Do not treat that first empty packet as legacy data: keep
        // the projectile harmless for a short grace window and let the next configured
        // net update hydrate it.  This avoids random projectile/child/VFX loss without
        // sending bulky item JSON in every projectile packet.
        ResetRuntimeSpecState(pendingSpecTicks: Math.Max(_pendingNetworkSpecTicks, 45));
        Projectile.damage = 0;
        Projectile.knockBack = 0f;
        Projectile.friendly = false;
        Projectile.hostile = false;
        Projectile.timeLeft = Math.Max(Projectile.timeLeft, 45);
        Projectile.netUpdate = false;
    }

    private void ResetRuntimeSpecState(int pendingSpecTicks = 0, bool clearGeneratedId = false, bool deactivateProjectile = false)
    {
        _configured = false;
        _statsApplied = false;
        _pendingNetworkSpecTicks = pendingSpecTicks;
        _spec = new AttackSpec { Enabled = false, DustSpawnDenom = 0, BurstDustCap = 0, RuntimePlanAuthored = true };
        _vfxManifest = new VfxManifestSpec();
        _vfxState = new InfiniVfxState();
        if (clearGeneratedId)
        {
            _generatedItemId = "";
            _lastReceivedVfxManifestJson = "";
        }
        if (deactivateProjectile)
        {
            Projectile.active = false;
            Projectile.netUpdate = false;
        }
    }

    private static string ReadStringKeepBase(BinaryReader reader, string current, bool allowEmptyOverride)
    {
        string value = reader.ReadString();
        return (allowEmptyOverride || !string.IsNullOrWhiteSpace(value)) ? value : (current ?? "");
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
