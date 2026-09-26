#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using System;
using System.IO;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private const byte RuntimeNetVersion = 1;
    private const byte VfxEventNetVersion = 2;
    private static long _nextVfxSourceToken;
    private long _vfxSourceToken;

    private readonly record struct VfxEventPayload(
        int Owner,
        int Identity,
        long SourceToken,
        string ItemId,
        string EntityId,
        string EventName,
        Vector2 Center,
        Vector2 Velocity);

    public override void SendExtraAI(BinaryWriter writer)
    {
        writer.Write(RuntimeNetVersion);
        writer.Write(_generatedItemId ?? "");
        writer.Write(_entityId ?? "");
        writer.Write((byte)Math.Clamp(_childDepth, 0, 255));
        writer.Write((byte)Math.Clamp(_activationSpawnBudget?.Remaining ?? _remainingSpawnBudget, 0, 255));
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

    private long VfxSourceToken()
    {
        if (_vfxSourceToken != 0)
            return _vfxSourceToken;
        _nextVfxSourceToken++;
        if (_nextVfxSourceToken == 0)
            _nextVfxSourceToken++;
        _vfxSourceToken = _nextVfxSourceToken;
        return _vfxSourceToken;
    }

    private void BroadcastAuthoritativeVfxEvent(string eventName, Vector2 center)
    {
        if (Main.netMode != NetmodeID.Server
            || _data is null
            || _entity is null
            || !HasExactVfxSlot(_data, _entity.Id, eventName)
            || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null)
            return;
        var packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent);
        WriteVfxEventPayload(packet, new VfxEventPayload(
            Projectile.owner,
            Projectile.identity,
            VfxSourceToken(),
            _data.Id,
            _entity.Id,
            eventName,
            center,
            Projectile.velocity));
        packet.Send(-1, Projectile.owner);
    }

    private static void WriteVfxEventPayload(BinaryWriter writer, VfxEventPayload payload)
    {
        writer.Write(VfxEventNetVersion);
        writer.Write(payload.Owner);
        writer.Write(payload.Identity);
        writer.Write(payload.SourceToken);
        writer.Write(payload.ItemId ?? "");
        writer.Write(payload.EntityId ?? "");
        writer.Write(payload.EventName ?? "");
        writer.Write(payload.Center.X);
        writer.Write(payload.Center.Y);
        writer.Write(payload.Velocity.X);
        writer.Write(payload.Velocity.Y);
    }

    private static VfxEventPayload ReadVfxEventPayload(BinaryReader reader)
    {
        if (reader.ReadByte() != VfxEventNetVersion)
            throw new InvalidDataException("unsupported generated projectile VFX event payload");
        var payload = new VfxEventPayload(
            reader.ReadInt32(),
            reader.ReadInt32(),
            reader.ReadInt64(),
            (reader.ReadString() ?? "").Trim(),
            (reader.ReadString() ?? "").Trim(),
            (reader.ReadString() ?? "").Trim().ToLowerInvariant(),
            new Vector2(reader.ReadSingle(), reader.ReadSingle()),
            new Vector2(reader.ReadSingle(), reader.ReadSingle()));
        if (payload.Owner < 0
            || payload.Owner >= Main.maxPlayers
            || payload.SourceToken == 0
            || payload.ItemId.Length > 96
            || payload.EntityId.Length > 48
            || payload.EventName.Length > 24
            || !RuntimeEventKind.IsKnown(payload.EventName)
            || !float.IsFinite(payload.Center.X)
            || !float.IsFinite(payload.Center.Y)
            || !float.IsFinite(payload.Velocity.X)
            || !float.IsFinite(payload.Velocity.Y))
            throw new InvalidDataException("invalid generated projectile VFX event payload");
        return payload;
    }

    public static void HandleVfxEventSyncPacket(BinaryReader reader, int whoAmI)
    {
        if (reader is null || Main.netMode != NetmodeID.MultiplayerClient)
            return;
        VfxEventPayload payload;
        try { payload = ReadVfxEventPayload(reader); }
        catch { return; }
        if (payload.Owner == Main.myPlayer)
            return;

        GeneratedItemRegistryService? registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (registry is null
            || !registry.TryGet(payload.ItemId, out GeneratedItemData data)
            || !GeneratedItemRegistryService.IsCurrentWorldData(data))
            return;
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(payload.EntityId);
        if (entity is null || !HasExactVfxSlot(data, entity.Id, payload.EventName))
            return;
        string sourceKey = $"net:{payload.Owner}:{payload.SourceToken}:{payload.ItemId}:{payload.EntityId}";
        InfiniVfxRuntime.OnDetachedEvent(
            data,
            entity.Id,
            payload.EventName,
            data.VfxManifest,
            payload.Center,
            payload.Velocity,
            sourceKey);
    }

    private static bool HasExactVfxSlot(GeneratedItemData data, string entityId, string eventName)
    {
        foreach (VfxSlotSpec slot in data.VfxManifest.Slots)
            if (string.Equals(slot.EntityId, entityId, StringComparison.Ordinal)
                && string.Equals(slot.Event, eventName, StringComparison.Ordinal))
                return true;
        return false;
    }

    public static void ClearVfxEventSyncCaches()
    {
        _nextVfxSourceToken = 0;
    }
}
