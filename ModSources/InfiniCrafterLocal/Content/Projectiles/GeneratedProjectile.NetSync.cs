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
    private const byte NativeShotRuntimeNetVersion = 5;
    private const byte ComposableMotionRuntimeNetVersion = 6;
    private const byte VisualScaleRuntimeNetVersion = 7;
    private float? _receivedVisualScale;
    private bool HasStatefulVisualScale => _entity?.VisualScaleRate is not null || _entity?.VisualScaleCurve?.Window is not null;
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
        public byte Origin { get; init; } // 0 server producer, 1 owner producer
    }
    private static readonly VfxOrderedPeerStream VfxEventStream = new();

    public override void SendExtraAI(BinaryWriter writer)
    {
        // Native SyncProjectile does not serialize scale. Rate accumulation and
        // the last value of a closed curve window cannot be derived from age.
        // A pending definition must relay the received value, not proxy defaults.
        bool statefulScale = _configured && HasStatefulVisualScale || _receivedVisualScale.HasValue;
        bool composable = HasComposableMotion || statefulScale;
        writer.Write(statefulScale ? VisualScaleRuntimeNetVersion : composable ? ComposableMotionRuntimeNetVersion : _nativeShotInitialVelocity.HasValue ? NativeShotRuntimeNetVersion : RuntimeNetVersion);
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
        // Keep v4 sampled/constant payloads byte-identical. Only an explicit
        // native-shot launch snapshot needs this additional transport variant.
        if (composable) writer.Write(_nativeShotInitialVelocity.HasValue);
        if (_nativeShotInitialVelocity is { } nativeLaunch)
        {
            writer.Write(nativeLaunch.X);
            writer.Write(nativeLaunch.Y);
        }
        if (composable)
        {
            writer.Write(_releaseAge); writer.Write(_returnAge);
            writer.Write(_spawnEventRan); writer.Write(_expireEventRan);
            writer.Write(Projectile.localAI[0]); writer.Write(Projectile.localAI[1]);
            writer.Write(_motionAxis.X); writer.Write(_motionAxis.Y);
            writer.Write(_beamManaClockStarted); writer.Write(_beamLastManaTick);
        }
        if (statefulScale) writer.Write(_receivedVisualScale ?? Projectile.scale);
    }

    public override void ReceiveExtraAI(BinaryReader reader)
    {
        try
        {
            int priorAge = _age, priorCharge = _chargeTicks, priorTimer = _controllerTimer;
            int priorBounces = _remainingBounces, priorDelay = _activationDelayTicks, priorTarget = _lastTarget;
            bool priorReleased = _released, priorReturning = _returning;
            string priorItemId = _generatedItemId, priorEntityId = _entityId;
            byte runtimeVersion = reader.ReadByte();
            bool statefulScale = runtimeVersion == VisualScaleRuntimeNetVersion;
            bool composable = runtimeVersion == ComposableMotionRuntimeNetVersion || statefulScale;
            if (runtimeVersion != RuntimeNetVersion && runtimeVersion != NativeShotRuntimeNetVersion && !composable)
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
            RuntimeInitialNpcExclusion receivedExclusion = RuntimeInitialNpcExclusion.Read(reader);
            byte receivedVelocityPresence = reader.ReadByte();
            if (receivedVelocityPresence > 1)
                throw new InvalidDataException("invalid sampled launch presence");
            Vector2? receivedVelocity = receivedVelocityPresence == 1
                ? new Vector2(reader.ReadSingle(), reader.ReadSingle()) : null;
            if (receivedVelocity is { } sampled && (!float.IsFinite(sampled.X) || !float.IsFinite(sampled.Y)))
                throw new InvalidDataException("non-finite sampled launch velocity");
            byte nativePresence = composable ? reader.ReadByte() : (byte)(runtimeVersion == NativeShotRuntimeNetVersion ? 1 : 0);
            if (nativePresence > 1) throw new InvalidDataException("invalid native launch presence");
            Vector2? receivedNativeLaunch = nativePresence == 1
                ? new Vector2(reader.ReadSingle(), reader.ReadSingle()) : null;
            int releaseAge = -1, returnAge = -1;
            bool spawned = false, expired = false, manaStarted = false;
            uint manaTick = 0;
            Vector2 cursor = Vector2.Zero, axis = Vector2.UnitX;
            if (composable) {
                releaseAge = reader.ReadInt32(); returnAge = reader.ReadInt32();
                spawned = reader.ReadBoolean(); expired = reader.ReadBoolean();
                cursor = new Vector2(reader.ReadSingle(), reader.ReadSingle());
                axis = new Vector2(reader.ReadSingle(), reader.ReadSingle());
                manaStarted = reader.ReadBoolean(); manaTick = reader.ReadUInt32();
                // A tile callback after AI latches the following update as the
                // return clock's origin; no other future phase age is admitted.
                if (releaseAge < -1 || releaseAge > _age || returnAge < -1 || (long)returnAge > (long)_age + 1
                    || (_released != (releaseAge >= 0)) || (_returning != (returnAge >= 0))
                    || !float.IsFinite(cursor.X) || !float.IsFinite(cursor.Y)
                    || !float.IsFinite(axis.X) || !float.IsFinite(axis.Y) || Math.Abs(axis.LengthSquared() - 1f) > .001f)
                    throw new InvalidDataException("invalid composable motion phase snapshot");
            }
            if (receivedNativeLaunch is { } nativeLaunch
                && (!float.IsFinite(nativeLaunch.X) || !float.IsFinite(nativeLaunch.Y)))
                throw new InvalidDataException("non-finite native shot launch velocity");
            float? receivedScale = statefulScale ? reader.ReadSingle() : null;
            if (receivedScale is { } scale && (!float.IsFinite(scale) || scale is < .01f or > 128f))
                throw new InvalidDataException("invalid stateful visual scale snapshot");
            // An owner already executing this exact physical source retains its
            // local counter. Relayed observations cannot extend or clear immunity.
            bool retainOwnerExclusion = _activationSpawnBudget is not null
                && _vfxSourceToken == sourceToken
                && Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers
                && Main.player[Projectile.owner] is { active: true } owner
                && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner);
            bool sameGeneration = _vfxSourceToken == sourceToken && _data?.Id == _generatedItemId && _entity?.Id == _entityId;
            bool sameSnapshotIdentity = _vfxSourceToken == sourceToken && priorItemId == _generatedItemId && priorEntityId == _entityId;
            bool sameScaleSource = statefulScale && sameSnapshotIdentity;
            bool retainNewerScale = sameScaleSource && (_age < priorAge || _age == priorAge
                && (priorReleased && !_released || priorReturning && !_returning));
            if (sameScaleSource && (retainOwnerExclusion || retainNewerScale))
                receivedScale = _receivedVisualScale ?? Projectile.scale;
            var expiryObservation = (_age, _released, _returning, releaseAge, returnAge, Projectile.position);
            if (!composable || !sameSnapshotIdentity) { _motionExpiryObserved = false; _pendingMotionExpiry = null; }
            if (composable && retainOwnerExclusion) {
                // Relayed owner observations cannot rewind a local lifecycle or
                // repeat its release/terminal events, even during metadata hydration.
                _age = priorAge; _chargeTicks = priorCharge; _controllerTimer = priorTimer;
                _released = priorReleased; _returning = priorReturning;
                _remainingBounces = priorBounces; _activationDelayTicks = priorDelay; _lastTarget = priorTarget;
            }
            else if (composable) {
                // Tile return can latch after AI at the same age. Pending v7
                // metadata must preserve that phase as well as the sampled scale.
                if (sameGeneration || sameScaleSource) {
                    bool stale = _age < priorAge;
                    _age = Math.Max(_age, priorAge); _chargeTicks = Math.Max(_chargeTicks, priorCharge);
                    _released |= priorReleased; _returning |= priorReturning;
                    if (priorReleased && _releaseAge >= 0) releaseAge = _releaseAge;
                    if (priorReturning && _returnAge >= 0) returnAge = _returnAge;
                    if (stale) _controllerTimer = priorTimer;
                }
                _releaseAge = releaseAge; _returnAge = returnAge;
                if (InfiniRuntimeAuthority.IsServer) {
                    // An owner's execution flag must not suppress the server's
                    // own NPC-action/VFX lane, including first hydration.
                    _spawnEventRan = sameSnapshotIdentity && _spawnEventRan;
                    _expireEventRan = sameSnapshotIdentity && _expireEventRan;
                    if (expired && !_motionExpiryObserved) {
                        _motionExpiryObserved = true; _pendingMotionExpiry = expiryObservation;
                    }
                }
                else {
                    _spawnEventRan = spawned || sameGeneration && _spawnEventRan;
                    _expireEventRan = expired || sameGeneration && _expireEventRan;
                }
                Projectile.localAI[0] = cursor.X; Projectile.localAI[1] = cursor.Y;
                _motionAxis = axis;
                _beamManaClockStarted = manaStarted; _beamLastManaTick = manaTick;
            }
            else { _releaseAge = -1; _returnAge = -1; }
            if (!retainOwnerExclusion) _initialNpcExclusion = receivedExclusion;
            if (!retainOwnerExclusion) _sampledInitialVelocity = receivedVelocity;
            if (!retainOwnerExclusion) _nativeShotInitialVelocity = receivedNativeLaunch;
            if (_vfxSourceToken != sourceToken || _data?.Id != _generatedItemId || _entity?.Id != _entityId)
                _penetrationInitialized = false;
            if(_vfxSourceToken!=sourceToken){
                _presentationGeneration=new object();_presentationRetired=false;
                _vfxState=new InfiniVfxState {SourceKey=$"net:{Projectile.owner}:{sourceToken}:{_generatedItemId}:{_entityId}"};
            }
            _vfxSourceToken=sourceToken;
            _receivedVisualScale = receivedScale;
            _runtimePayloadRejected = false;
            _preserveSyncedStateOnHydrate = true;
            _configured = false;
            TryHydrate();
        }
        catch
        {
            RejectRuntimePayload();
        }
    }

    private void RejectRuntimePayload()
    {
        _runtimePayloadRejected = true;
        _data = null;
        _entity = null;
        _configured = false;
        _preserveSyncedStateOnHydrate = false;
        _receivedVisualScale = null;
        _pendingMotionExpiry = null;
        Projectile.friendly = false;
        Projectile.velocity = Vector2.Zero;
        Projectile.timeLeft = Math.Min(Projectile.timeLeft, 30);
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
    // Shared sender/relay producer policy. New charge releases are owner-only
    // gameplay facts; the retained charge controller already emits on the server.
    // Never derive channel completion from a peer's observed charge counter.
    private static bool IsOwnerProducedVfxEvent(RuntimeEntitySpec entity, string eventName)
        => eventName is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit
            || entity.Charge is not null && entity.Controller.Code != RuntimeControllerCode.ChargeThenRelease
                && eventName is RuntimeEventKind.OnRelease or RuntimeEventKind.ChannelComplete;

    private void SendOwnerProducedVfxEvent(string eventName,Vector2 point)
    {
        if(Main.netMode!=NetmodeID.MultiplayerClient||Projectile.owner!=Main.myPlayer||_data is null||_entity is null
            ||!IsOwnerProducedVfxEvent(_entity,eventName)||!HasExactVfxSlot(_data,_entity.Id,eventName))return;
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
            if(payload.Origin!=1||whoAmI!=payload.Owner
                ||Main.player[payload.Owner] is not {active:true})return;
            var source=FindVfxPeerSource(payload,true);
            if(source is null||source._data is null||source._entity is null||!GeneratedItemRegistryService.IsCurrentWorldData(source._data)
                ||!IsOwnerProducedVfxEvent(source._entity,payload.EventName)
                ||!HasExactVfxSlot(source._data,payload.EntityId,payload.EventName)
                ||!payload.Snapshot.IsValidFor(source._entity))return;
            try{RuntimeEventKind.ValidateProducer(source._entity,payload.EventName,false,false);}catch{return;}
            if(!AcceptVfxOccurrence(payload))return;
            // Trust only the authenticated owner's actual hit/release event claim.
            // Presentation relay never executes collision/damage/gameplay or
            // reconstructs completion from ExtraAI or local charge counters.
            SendVfxPayload(payload with { Occurrence=VfxEventStream.NewRelayOccurrence() },-1,payload.Owner);return;
        }
        if (payload.Owner == Main.myPlayer) return;

        GeneratedItemRegistryService? registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (registry is null
            || !registry.TryGet(payload.ItemId, out GeneratedItemData data)
            || !GeneratedItemRegistryService.IsCurrentWorldData(data))
            return;
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(payload.EntityId);
        if (entity is null || !HasExactVfxSlot(data, entity.Id, payload.EventName)
            || !payload.Snapshot.IsValidFor(entity))
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
