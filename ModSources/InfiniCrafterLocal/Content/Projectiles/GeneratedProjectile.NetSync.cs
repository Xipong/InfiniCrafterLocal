#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
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
    private const byte RuntimeNetVersion = 4;
    private const byte VfxEventNetVersion = 5;
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
        Vector2 Velocity,
        InfiniVfxProjectileSnapshot Snapshot)
    {
        public ulong Occurrence { get; init; }
        public byte Origin { get; init; } // 0 server producer, 1 owner-hit producer
    }
    private static readonly VfxOrderedPeerStream VfxEventStream = new();

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
        writer.Write(VfxSourceToken());
        _initialNpcExclusion.Write(writer);
        writer.Write(_sampledInitialVelocity.HasValue);
        if (_sampledInitialVelocity is { } sampled)
        {
            writer.Write(sampled.X);
            writer.Write(sampled.Y);
        }
    }

    public override void ReceiveExtraAI(BinaryReader reader)
    {
        try
        {
            byte runtimeVersion = reader.ReadByte();
            if (runtimeVersion is not (2 or 3) && runtimeVersion != RuntimeNetVersion)
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
            long sourceToken=reader.ReadInt64();
            if(sourceToken==0)throw new InvalidDataException("missing VFX source generation");
            RuntimeInitialNpcExclusion receivedExclusion = runtimeVersion == 2
                ? RuntimeInitialNpcExclusion.None : RuntimeInitialNpcExclusion.Read(reader);
            byte receivedVelocityPresence = runtimeVersion >= 4 ? reader.ReadByte() : (byte)0;
            if (receivedVelocityPresence > 1)
                throw new InvalidDataException("invalid sampled launch presence");
            Vector2? receivedVelocity = receivedVelocityPresence == 1
                ? new Vector2(reader.ReadSingle(), reader.ReadSingle()) : null;
            if (receivedVelocity is { } sampled && (!float.IsFinite(sampled.X) || !float.IsFinite(sampled.Y)))
                throw new InvalidDataException("non-finite sampled launch velocity");
            // An owner already executing this exact physical source retains its
            // local counter. Relayed observations cannot extend or clear immunity.
            bool retainOwnerExclusion = _activationSpawnBudget is not null
                && _vfxSourceToken == sourceToken
                && Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers
                && Main.player[Projectile.owner] is { active: true } owner
                && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner);
            if (!retainOwnerExclusion) _initialNpcExclusion = receivedExclusion;
            if (!retainOwnerExclusion) _sampledInitialVelocity = receivedVelocity;
            if(_vfxSourceToken!=sourceToken){
                _presentationGeneration=new object();_presentationRetired=false;
                _vfxState=new InfiniVfxState {SourceKey=$"net:{Projectile.owner}:{sourceToken}:{_generatedItemId}:{_entityId}"};
            }
            _vfxSourceToken=sourceToken;
            _runtimePayloadRejected = false;
            _preserveSyncedStateOnHydrate = true;
            _configured = false;
            TryHydrate();
        }
        catch
        {
            _runtimePayloadRejected = true;
            _data = null;
            _entity = null;
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
        var payload=CaptureVfxPayload(eventName,center,0);
        if(!payload.Snapshot.IsValid||!float.IsFinite(center.X)||!float.IsFinite(center.Y)||!float.IsFinite(payload.Velocity.X)||!float.IsFinite(payload.Velocity.Y))return;
        var packet=InfiniCrafterLocalMod.Instance.GetPacket();packet.Write(InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent);
        WriteVfxEventPayload(packet,payload);packet.Send(-1, Projectile.owner);
    }

    private VfxEventPayload CaptureVfxPayload(string eventName,Vector2 point,byte origin)
        =>new(Projectile.owner,Projectile.identity,VfxSourceToken(),_data!.Id,_entity!.Id,eventName,point,Projectile.velocity,
            InfiniVfxProjectileSnapshot.Capture(Projectile,_data,_entity.Id)){Occurrence=origin==0?VfxEventStream.NewRelayOccurrence():VfxEventStream.NewOwnerOccurrence(),Origin=origin};
    private static void SendVfxPayload(VfxEventPayload payload,int to,int ignore)
    {
        if(InfiniCrafterLocalMod.Instance is null||!payload.Snapshot.IsValid||!float.IsFinite(payload.Center.X)||!float.IsFinite(payload.Center.Y)||!float.IsFinite(payload.Velocity.X)||!float.IsFinite(payload.Velocity.Y))return;
        var packet=InfiniCrafterLocalMod.Instance.GetPacket();packet.Write(InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent);
        WriteVfxEventPayload(packet,payload);packet.Send(to,ignore);
    }
    private void SendOwnerHitVfxEvent(string eventName,Vector2 point)
    {
        if(Main.netMode!=NetmodeID.MultiplayerClient||Projectile.owner!=Main.myPlayer||_data is null||_entity is null
            ||eventName is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)||!HasExactVfxSlot(_data,_entity.Id,eventName))return;
        SendVfxPayload(CaptureVfxPayload(eventName,point,1),-1,-1);
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
        InfiniVfxProjectileSnapshot snapshot = payload.Snapshot;
        writer.Write(snapshot.Center.X); writer.Write(snapshot.Center.Y);
        writer.Write(snapshot.Tip.X); writer.Write(snapshot.Tip.Y);
        writer.Write(snapshot.Forward.X); writer.Write(snapshot.Forward.Y);
        writer.Write((byte)(snapshot.OwnerCenter.HasValue ? 1 : 0));
        if (snapshot.OwnerCenter is { } owner) { writer.Write(owner.X); writer.Write(owner.Y); }
        writer.Write(snapshot.Pose.Rotation); writer.Write(snapshot.Pose.Scale);
        writer.Write((byte)(snapshot.Pose.Effects == Microsoft.Xna.Framework.Graphics.SpriteEffects.FlipHorizontally ? 1 : 0));
        writer.Write(snapshot.Pose.GfxOffY);
        writer.Write((byte)(snapshot.MaterialTip.HasValue?1:0));
        if(snapshot.MaterialTip is {} tip){writer.Write(tip.X);writer.Write(tip.Y);}
        writer.Write(snapshot.MaterialVelocity.X);writer.Write(snapshot.MaterialVelocity.Y);
        writer.Write(payload.Occurrence==0?1UL:payload.Occurrence);writer.Write(payload.Origin);
    }

    private static InfiniVfxProjectileSnapshot ReadVfxPresentationSnapshot(BinaryReader reader)
    {
        Vector2 center = new(reader.ReadSingle(), reader.ReadSingle());
        Vector2 tip = new(reader.ReadSingle(), reader.ReadSingle());
        Vector2 forward = new(reader.ReadSingle(), reader.ReadSingle());
        byte hasOwner = reader.ReadByte();
        if (hasOwner > 1) throw new InvalidDataException("invalid VFX owner presence");
        Vector2? owner = hasOwner == 1 ? new Vector2(reader.ReadSingle(), reader.ReadSingle()) : null;
        float rotation = reader.ReadSingle(), scale = reader.ReadSingle();
        byte flip = reader.ReadByte();
        if (flip > 1) throw new InvalidDataException("invalid VFX sprite flip");
        float gfxOffY = reader.ReadSingle();
        byte hasMaterialTip=reader.ReadByte();if(hasMaterialTip>1)throw new InvalidDataException("invalid material tip presence");
        Vector2? materialTip=hasMaterialTip==1?new Vector2(reader.ReadSingle(),reader.ReadSingle()):null;
        Vector2 materialVelocity=new(reader.ReadSingle(),reader.ReadSingle());
        return new InfiniVfxProjectileSnapshot(center, tip, forward, owner, new(rotation, scale,
            flip == 1 ? Microsoft.Xna.Framework.Graphics.SpriteEffects.FlipHorizontally : Microsoft.Xna.Framework.Graphics.SpriteEffects.None, gfxOffY)){MaterialTip=materialTip,MaterialVelocity=materialVelocity};
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
            new Vector2(reader.ReadSingle(), reader.ReadSingle()),
            ReadVfxPresentationSnapshot(reader)){Occurrence=reader.ReadUInt64(),Origin=reader.ReadByte()};
        if (payload.Owner < 0
            || payload.Owner >= Main.maxPlayers
            || payload.SourceToken == 0 || payload.Occurrence==0 || payload.Origin>1
            || payload.ItemId.Length > 96
            || payload.EntityId.Length > 48
            || payload.EventName.Length > 24
            || !RuntimeEventKind.IsKnown(payload.EventName)
            || !float.IsFinite(payload.Center.X)
            || !float.IsFinite(payload.Center.Y)
            || !float.IsFinite(payload.Velocity.X)
            || !float.IsFinite(payload.Velocity.Y)
            || !payload.Snapshot.IsValid
            || !float.IsFinite(payload.Snapshot.MaterialVelocity.X) || !float.IsFinite(payload.Snapshot.MaterialVelocity.Y))
            throw new InvalidDataException("invalid generated projectile VFX event payload");
        return payload;
    }

    private static bool AcceptVfxOccurrence(VfxEventPayload payload)
        => Main.netMode==NetmodeID.Server
            ? VfxEventStream.AcceptOwner(payload.Owner,payload.Occurrence)
            : VfxEventStream.AcceptRelay(payload.Occurrence);
    private static GeneratedProjectile? FindVfxPeerSource(VfxEventPayload payload,bool activeOnly)
    {
        foreach(var projectile in Main.projectile)if(projectile is not null&&(!activeOnly||projectile.active)&&projectile.owner==payload.Owner&&projectile.identity==payload.Identity
            &&projectile.ModProjectile is GeneratedProjectile generated&&generated._vfxSourceToken==payload.SourceToken&&generated.Matches(payload.ItemId,payload.EntityId))return generated;
        return null;
    }
    public static void HandleVfxEventSyncPacket(BinaryReader reader, int whoAmI)
    {
        if (reader is null || (Main.netMode != NetmodeID.MultiplayerClient && Main.netMode != NetmodeID.Server))
            return;
        VfxEventPayload payload;
        try { payload = ReadVfxEventPayload(reader); }
        catch { return; }
        if(Main.netMode==NetmodeID.Server) {
            if(payload.Origin!=1||whoAmI!=payload.Owner||payload.EventName is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                ||Main.player[payload.Owner] is not {active:true})return;
            var source=FindVfxPeerSource(payload,true);
            if(source is null||source._data is null||source._entity is null||!GeneratedItemRegistryService.IsCurrentWorldData(source._data)
                ||!HasExactVfxSlot(source._data,payload.EntityId,payload.EventName))return;
            try{RuntimeEventKind.ValidateProducer(source._entity,payload.EventName,false,false);}catch{return;}
            if(!AcceptVfxOccurrence(payload))return;
            // Same vanilla-equivalent owner hit trust as the actual hook. This
            // admits presentation facts only; no collision/damage/gameplay replay.
            SendVfxPayload(payload with { Occurrence=VfxEventStream.NewRelayOccurrence() },-1,payload.Owner);return;
        }
        if (payload.Owner == Main.myPlayer) return;

        GeneratedItemRegistryService? registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (registry is null
            || !registry.TryGet(payload.ItemId, out GeneratedItemData data)
            || !GeneratedItemRegistryService.IsCurrentWorldData(data))
            return;
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(payload.EntityId);
        if (entity is null || !HasExactVfxSlot(data, entity.Id, payload.EventName))
            return;
        if(!AcceptVfxOccurrence(payload))return;
        var live=FindVfxPeerSource(payload,true);
        string sourceKey = live?._vfxState.SourceKey is {Length:>0} key ? key : $"net:{payload.Owner}:{payload.SourceToken}:{payload.ItemId}:{payload.EntityId}";
        InfiniVfxRuntime.OnDetachedEvent(
            data,
            entity.Id,
            payload.EventName,
            data.VfxManifest,
            payload.Center,
            payload.Velocity,
            sourceKey,
            payload.Snapshot,live is null?null:VfxSourceBinding.Capture(live.Projectile),payload.Occurrence);
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
        VfxEventStream.Clear();
        _nextVfxSourceToken = 0;
    }
}
