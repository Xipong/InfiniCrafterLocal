#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.IO;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private const byte RuntimeNetVersion = 1;
    private const byte VfxEventNetVersion = 1;
    private const int MaxVfxEventRelayEntries = 512;
    private static readonly Dictionary<(int Owner, int Identity, string EventName), ulong> LastVfxEventRelayTick = new();

    private readonly record struct VfxEventPayload(
        int Owner,
        int Identity,
        string ItemId,
        string EntityId,
        string EventName,
        Vector2 Center);

    public override void SendExtraAI(BinaryWriter writer)
    {
        writer.Write(RuntimeNetVersion);
        writer.Write(_generatedItemId ?? "");
        writer.Write(_entityId ?? "");
        writer.Write((byte)Math.Clamp(_childDepth, 0, 255));
        writer.Write((byte)Math.Clamp(_remainingSpawnBudget, 0, 255));
        writer.Write(_initialDirection.X);
        writer.Write(_initialDirection.Y);
        writer.Write(_age);
        writer.Write(_remainingBounces);
        writer.Write(_activationDelayTicks);
        writer.Write(_returning);
        writer.Write(_released);
        writer.Write(_chargeTicks);
        writer.Write(_controllerTimer);
        writer.Write(_lastTarget);
    }

    public override void ReceiveExtraAI(BinaryReader reader)
    {
        try
        {
            if (reader.ReadByte() != RuntimeNetVersion)
                throw new InvalidDataException("unsupported generated runtime projectile payload");
            _generatedItemId = (reader.ReadString() ?? "").Trim();
            _entityId = (reader.ReadString() ?? "").Trim();
            if (_generatedItemId.Length > 96 || _entityId.Length > 48)
                throw new InvalidDataException("generated runtime projectile identity too long");
            _childDepth = reader.ReadByte();
            _remainingSpawnBudget = reader.ReadByte();
            _initialDirection = new Vector2(reader.ReadSingle(), reader.ReadSingle()).SafeNormalize(Vector2.UnitX);
            _age = Math.Max(0, reader.ReadInt32());
            _remainingBounces = Math.Max(0, reader.ReadInt32());
            _activationDelayTicks = Math.Max(0, reader.ReadInt32());
            _returning = reader.ReadBoolean();
            _released = reader.ReadBoolean();
            _chargeTicks = Math.Max(0, reader.ReadInt32());
            _controllerTimer = Math.Max(0, reader.ReadInt32());
            _lastTarget = reader.ReadInt32();
            _preserveSyncedStateOnHydrate = true;
            _configured = false;
            TryHydrate();
        }
        catch
        {
            _configured = false;
            _preserveSyncedStateOnHydrate = false;
            Projectile.friendly = false;
            Projectile.velocity = Vector2.Zero;
            Projectile.timeLeft = Math.Min(Projectile.timeLeft, 30);
        }
    }

    private void BroadcastVfxEventSync(string eventName, Vector2 center)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient
            || Projectile.owner != Main.myPlayer
            || _data is null
            || _entity is null
            || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent);
        WriteVfxEventPayload(packet, new VfxEventPayload(
            Projectile.owner,
            Projectile.identity,
            _data.Id,
            _entity.Id,
            eventName,
            center));
        packet.Send();
    }

    private static void WriteVfxEventPayload(BinaryWriter writer, VfxEventPayload payload)
    {
        writer.Write(VfxEventNetVersion);
        writer.Write(payload.Owner);
        writer.Write(payload.Identity);
        writer.Write(payload.ItemId ?? "");
        writer.Write(payload.EntityId ?? "");
        writer.Write(payload.EventName ?? "");
        writer.Write(payload.Center.X);
        writer.Write(payload.Center.Y);
    }

    private static VfxEventPayload ReadVfxEventPayload(BinaryReader reader)
    {
        if (reader.ReadByte() != VfxEventNetVersion)
            throw new InvalidDataException("unsupported generated projectile VFX event payload");
        var payload = new VfxEventPayload(
            reader.ReadInt32(),
            reader.ReadInt32(),
            (reader.ReadString() ?? "").Trim(),
            (reader.ReadString() ?? "").Trim(),
            (reader.ReadString() ?? "").Trim().ToLowerInvariant(),
            new Vector2(reader.ReadSingle(), reader.ReadSingle()));
        if (payload.ItemId.Length > 96
            || payload.EntityId.Length > 48
            || payload.EventName.Length > 24
            || !RuntimeEventKind.IsKnown(payload.EventName)
            || !float.IsFinite(payload.Center.X)
            || !float.IsFinite(payload.Center.Y))
            throw new InvalidDataException("invalid generated projectile VFX event payload");
        return payload;
    }

    public static void HandleVfxEventSyncPacket(BinaryReader reader, int whoAmI)
    {
        if (reader is null || Main.netMode == NetmodeID.SinglePlayer) return;
        VfxEventPayload payload;
        try { payload = ReadVfxEventPayload(reader); }
        catch { return; }

        if (Main.netMode == NetmodeID.Server)
        {
            if (whoAmI < 0 || whoAmI >= Main.maxPlayers || payload.Owner != whoAmI)
                return;
            GeneratedProjectile? generated = FindGeneratedProjectile(whoAmI, payload.Identity);
            if (generated?._data is null || generated._entity is null)
                return;
            if (!HasExactVfxSlot(generated._data, generated._entity.Id, payload.EventName))
                return;
            float maxDistance = InfiniRuntimeLimits.MaxRuntimeRangeTiles * 16f;
            if (Vector2.DistanceSquared(generated.Projectile.Center, payload.Center) > maxDistance * maxDistance)
                return;
            var key = (whoAmI, payload.Identity, payload.EventName);
            ulong now = Main.GameUpdateCount;
            if (LastVfxEventRelayTick.TryGetValue(key, out ulong last) && last == now)
                return;
            PruneVfxEventRelayTicks(now);
            LastVfxEventRelayTick[key] = now;

            var relay = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
            if (relay is null) return;
            relay.Write(InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent);
            WriteVfxEventPayload(relay, new VfxEventPayload(
                whoAmI,
                generated.Projectile.identity,
                generated._data.Id,
                generated._entity.Id,
                payload.EventName,
                payload.Center));
            relay.Send(-1, whoAmI);
            return;
        }

        if (payload.Owner == Main.myPlayer) return;
        GeneratedProjectile? remote = FindGeneratedProjectile(payload.Owner, payload.Identity);
        if (remote?._data is null
            || remote._entity is null
            || !string.Equals(remote._data.Id, payload.ItemId, StringComparison.Ordinal)
            || !string.Equals(remote._entity.Id, payload.EntityId, StringComparison.Ordinal)
            || !HasExactVfxSlot(remote._data, payload.EntityId, payload.EventName))
            return;
        InfiniVfxRuntime.OnEvent(
            remote.Projectile,
            payload.EntityId,
            payload.EventName,
            remote._data.VfxManifest,
            ref remote._vfxState,
            payload.Center);
    }

    private static GeneratedProjectile? FindGeneratedProjectile(int owner, int identity)
    {
        if (owner < 0 || owner >= Main.maxPlayers) return null;
        foreach (Projectile projectile in Main.ActiveProjectiles)
            if (projectile.owner == owner
                && projectile.identity == identity
                && projectile.ModProjectile is GeneratedProjectile generated)
                return generated;
        return null;
    }

    private static bool HasExactVfxSlot(GeneratedItemData data, string entityId, string eventName)
    {
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
            if (string.Equals(slot.EntityId, entityId, StringComparison.Ordinal)
                && string.Equals(slot.Event, eventName, StringComparison.Ordinal))
                return true;
        return false;
    }

    private static void PruneVfxEventRelayTicks(ulong now)
    {
        if (LastVfxEventRelayTick.Count < MaxVfxEventRelayEntries) return;
        var stale = new List<(int Owner, int Identity, string EventName)>();
        foreach (var pair in LastVfxEventRelayTick)
            if (now - pair.Value > 600UL)
                stale.Add(pair.Key);
        foreach (var key in stale)
            LastVfxEventRelayTick.Remove(key);
        if (LastVfxEventRelayTick.Count >= MaxVfxEventRelayEntries)
            LastVfxEventRelayTick.Clear();
    }

    public static void ClearVfxEventSyncCaches() => LastVfxEventRelayTick.Clear();
}
