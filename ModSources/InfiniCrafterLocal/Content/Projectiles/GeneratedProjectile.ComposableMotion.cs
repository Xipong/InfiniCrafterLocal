#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private int _releaseAge = -1;
    private int _returnAge = -1;
    private Vector2 _motionAxis = Vector2.UnitX;
    // Received terminal claims and locally executed events are different facts.
    // A server may validate a claim once; repeating it cannot retry rejected work.
    private bool _motionExpiryObserved;
    private (int Age, bool Released, bool Returning, int ReleaseAge, int ReturnAge, Vector2 Position)? _pendingMotionExpiry;

    // Read-only native resolution: old saved opcodes remain stored exactly as authored.
    // They select compatibility stage parameters, NOT another serialized program/engine.
    private readonly struct NativeMotionResolution
    {
        internal readonly RuntimeEntitySpec Entity;
        internal NativeMotionResolution(RuntimeEntitySpec entity) { Entity = entity; }
        internal int Code => Entity.Movement.IsConfigured ? Entity.Movement.Code : -1;
        internal RuntimeParamsSpec Params => Entity.Movement.Params;
        internal bool Beam => Entity.BeamGeometry is not null || Entity.Controller.Code == RuntimeControllerCode.ChannelBeam;
        internal bool Lash => Entity.LashGeometry is not null || Code == 18;
    }
    private NativeMotionResolution ResolvedMotion => new(_entity!);
    private bool HasBeamGeometry => _entity is not null && ResolvedMotion.Beam;
    private bool HasLashGeometry => _entity is not null && ResolvedMotion.Lash;
    private bool HasComposableMotion => _entity is { } e && (e.HasMotionComponents
        || e.TurnModifier?.Window is not null || e.SpeedModifier?.Window is not null
        || e.HomingModifier?.Window is not null || e.NpcAttraction?.Window is not null
        || e.VisualScaleCurve?.Window is not null);

    private bool MotionWindowActive(RuntimeMotionWindowSpec? window)
        => MotionWindowActive(window, _age, _released, _returning, _releaseAge, _returnAge);

    private bool MotionWindowActive(RuntimeMotionWindowSpec? window, int activeAge,
        bool released, bool returning, int releaseAge, int returnAge)
    {
        if (window is null) return true;
        bool charging = (_entity?.Charge is not null || _entity?.Controller.Code == RuntimeControllerCode.ChargeThenRelease) && !released;
        if (window.Phase switch {
            "charging" => !charging, "released" => !released,
            "outbound" => charging || returning, "returning" => !returning, _ => false }) return false;
        if (!window.HasTimingWindow) return true;
        int origin = window.Clock switch { "since_release" => releaseAge, "since_return" => returnAge, _ => 0 };
        if (origin < 0 || origin > activeAge) return false;
        // Relative clock starts on the transition update; every window samples
        // the same start-of-update convention as PR148's Active clock.
        int age = window.Clock == "active" ? activeAge : activeAge - origin + 1;
        return RuntimeModifierClock.Active(age, Projectile.extraUpdates + 1, window.StartDelayTicks!.Value, window.DurationTicks!.Value);
    }

    private void LatchReturn(bool disableTileCollision, bool startsNextUpdate = false)
    {
        // Tile collision runs after AI; its first motion step is the next AI,
        // unlike a timer/distance trigger sampled before this update's stages.
        if (!_returning) { _returning = true; _returnAge = _age + (startsNextUpdate ? 1 : 0); Projectile.netUpdate = true; }
        if (disableTileCollision) Projectile.tileCollide = false;
    }
    private Vector2 MotionAxis(Player owner, bool publish = true)
    {
        if (_entity?.Aim is not { } aim) return _initialDirection;
        Vector2 axis = aim.Source switch {
            "cursor" => publish ? FrontHandCursorDirection(owner) : new Vector2(Projectile.ai[0], Projectile.ai[1]).SafeNormalize(_initialDirection),
            "facing" => new Vector2(owner.direction, 0f),
            "velocity" => Projectile.velocity.SafeNormalize(_motionAxis.SafeNormalize(_initialDirection)),
            _ => _initialDirection,
        };
        axis = axis.SafeNormalize(_initialDirection);
        if (publish && aim.TurnOwner) owner.ChangeDir(axis.X >= 0f ? 1 : -1);
        return axis;
    }
    private Vector2 MotionAnchor(Player owner, string anchor)
        => anchor switch {
            "owner_center" => owner.Center,
            "front_hand" => owner.RotatedRelativePoint(owner.GetFrontHandPosition(owner.compositeFrontArm.stretch,
                owner.compositeFrontArm.rotation), addGfxOffY: false),
            _ => owner.MountedCenter,
        };

    // All old and new steering, sine, drag, spin, reach and curve users share
    // these laws. Compatibility operands (including old zero/absence) are resolved
    // by the caller; the kernel itself never chooses gameplay policy.
    private void SeekVelocity(Vector2 target, float speed, float lerp, bool limitDistance, float minimumSpeed = 0f)
    {
        float distance = Projectile.Distance(target);
        speed = Math.Max(minimumSpeed, speed);
        if (limitDistance) speed = Math.Min(speed, distance);
        // DirectionTo normalizes a zero vector at exact arrival. NaN velocity
        // makes an otherwise live projectile disappear and hold its concurrency
        // slot until expiry. Zero displacement has no steering direction; keep
        // the authored interpolation and leave retirement to its arrival policy.
        Vector2 direction = Projectile.Center == target ? Vector2.Zero : Projectile.DirectionTo(target);
        Projectile.velocity = Vector2.Lerp(Projectile.velocity, direction * speed, lerp);
    }
    private void RetainVelocity(float multiplier) => Projectile.velocity *= multiplier;
    private void AccelerateVertical(float amount) => Projectile.velocity.Y += amount;
    private void RotateVelocity(float radians) => Projectile.velocity = Projectile.velocity.RotatedBy(radians);
    private void SpinBody(float radians) => Projectile.rotation += radians;
    private void AngularSine(float frequency, float phase, float amplitude, float scale = 1f)
        => RotateVelocity(MathF.Sin(_age * frequency + phase) * amplitude * scale);
    private void LateralSine(float frequency, float phase, float amplitude, float minimumSpeed, float scale = 1f, int substeps = 1)
    {
        float speed = Math.Max(minimumSpeed, Projectile.velocity.Length());
        Vector2 forward = Projectile.velocity.SafeNormalize(_initialDirection);
        if (substeps > 1) {
            // Amplitude and velocity share the same world-to-update projection,
            // so their ratio already cancels extraUpdates. Divide the resulting
            // nonlinear turn, not amplitude, to integrate the u=1 law per tick.
            float lateralSpeed = MathF.Sin(_age * frequency + phase) * amplitude * scale;
            float turn = MathF.Atan2(lateralSpeed, speed) / substeps;
            Projectile.velocity = forward.RotatedBy(turn) * speed;
            return;
        }
        // Preserve the exact u=1 operation order and retained SineHome operands.
        Vector2 lateral = forward.RotatedBy(MathHelper.PiOver2) * MathF.Sin(_age * frequency + phase) * amplitude * scale;
        Projectile.velocity = (forward * speed + lateral).SafeNormalize(forward) * speed;
    }
    private void AddVisualScale(float delta, float maximum, bool nonnegative = false)
        => Projectile.scale = nonnegative ? Math.Clamp(Projectile.scale + delta, 0.01f, maximum) : Math.Min(maximum, Projectile.scale + delta);
    private static double MotionCurve(double progress, double start, double peak, double end, double peakProgress)
        => progress <= peakProgress ? start + (peak - start) * progress / peakProgress
            : peak + (end - peak) * (progress - peakProgress) / (1d - peakProgress);
    private void OrbitTrajectory(Vector2 anchor, float radius, float radiansPerUpdate, float phase, float identityPhase)
    {
        Vector2 target = anchor + (_age * radiansPerUpdate + phase + Projectile.identity * identityPhase).ToRotationVector2() * radius;
        Projectile.velocity = target - Projectile.Center; // native integration once, not a second center write
    }
    private NPC? ResolveMotionNpc(float rangePx, bool lineOfSight, bool legacyDistance = false)
    {
        NPC? best = null; float distance = legacyDistance ? rangePx : rangePx * rangePx;
        for (int i = 0; i < Main.maxNPCs; i++) {
            NPC? npc = Main.npc[i];
            if (npc is null || !npc.active || !npc.CanBeChasedBy(Projectile)) continue;
            float d = legacyDistance ? Vector2.Distance(Projectile.Center, npc.Center) : Vector2.DistanceSquared(Projectile.Center, npc.Center);
            if (!float.IsFinite(d) || (legacyDistance ? d >= distance : d > distance || d == distance && best is not null)) continue;
            if (lineOfSight && !Collision.CanHitLine(Projectile.position, Projectile.width, Projectile.height,
                npc.position, npc.width, npc.height)) continue;
            distance = d; best = npc;
        }
        return best;
    }
    private bool AbsoluteMotionActive()
        => _entity is { } e && (e.Attachment is { } a && MotionWindowActive(a.Window) || e.LashGeometry is not null);

    private void RunResolvedMotion()
    {
        var motion = ResolvedMotion;
        RuntimeParamsSpec p = motion.Params;
        // Retained opcodes resolve exact historical stage operands. They use the
        // same native laws below as independently selected nullable components.
        switch (motion.Code) {
            case -1: if (_entity!.IsStationary && !HasComposableMotion) Projectile.velocity = Vector2.Zero; break;
            case 0: break;
            case 1: Home(p.RangeTiles, p.HomingStrength); break;
            case 2: AccelerateVertical(p.GravityPerTick); break;
            case 3: RetainVelocity(p.VelocityRetention == 0f ? 1f : p.VelocityRetention); break;
            case 4: OrbitOwner(p.RangeTiles); break;
            case 5: ReturnAfter(p.ReturnAfterTicks, p.ReturnSpeed); break;
            case 7: SineHome(p); break;
            case 8: PhaseDrift(p.PhaseStrength); break;
            case 9: Accelerate(p.Acceleration, p.MaxSpeed); break;
            case 10: RotateVelocity(p.TurnRadiansPerTick); break;
            case 11: Vortex(p); break;
            case 12: Blackhole(p); break;
            case 13: ProximityMissile(p); break;
            case 14: SpinBody(.35f); ReturnAfter(p.ReturnAfterTicks, p.ReturnSpeed); break;
            case 15: Expand(p); break;
            case 16: Flail(p); break;
            case 17: Yoyo(p); break;
            case 18: Whip(p); break;
            case 19: ForwardRetract(p); break;
            case 20: MoveFrontHand(); break;
            default: Projectile.friendly = false; Projectile.Kill(); return;
        }
        if (!Projectile.active || !HasComposableMotion) return;
        Player owner = Owner();
        // A free force/presentation primitive does not acquire held-item
        // cancellation. Only owner control owns input/death cancellation.
        if (owner is null || !owner.active) { Projectile.friendly = false; Projectile.Kill(); return; }
        _motionAxis = MotionAxis(owner);
        if (!ApplyMotionOwnerControl(owner)) return;
        ApplyMotionCharge(owner);
        if (!Projectile.active) return;
        ApplyMotionReturnTrigger(owner);
        if (_entity!.ArmPose is { } pose && MotionWindowActive(pose.Window) && IsPrimaryRuntimeEntity && OwnerCanControl(owner)
            && ReferenceEquals(FindMotionPoseWriter(owner), this)) {
            CalculateMotionFrontHand(owner, _motionAxis, pose.DurationTicks, pose.StartStretch, pose.PeakStretch,
                pose.EndStretch, pose.PeakProgress, out var stretch, out float rotation, out _);
            ProjectFrontHand(owner, _motionAxis, stretch, rotation, _entity.Aim?.TurnOwner == true);
        }
        if (_entity.Attachment is { } attachment && MotionWindowActive(attachment.Window)) {
            float reach = 0f;
            if (_entity.Reach is { } r && MotionWindowActive(r.Window)) {
                double progress = Math.Clamp(_age / (double)Math.Max(1, AuthoredTicksToProjectileUpdates(r.DurationTicks)), 0d, 1d);
                reach = (float)MotionCurve(progress, r.StartOffsetPx, r.PeakOffsetPx, r.EndOffsetPx, r.PeakProgress);
            }
            Projectile.Center = MotionAnchor(owner, attachment.Anchor) + _motionAxis * (attachment.AxisOffsetPx + reach)
                + _motionAxis.RotatedBy(MathHelper.PiOver2) * attachment.NormalOffsetPx;
            Projectile.velocity = Vector2.Zero;
            if (attachment.Anchor == "front_hand") Projectile.spriteDirection = owner.direction;
        }
        if (_entity.Orbit is { } orbit && MotionWindowActive(orbit.Window))
            OrbitTrajectory(MotionAnchor(owner, orbit.Anchor), orbit.RadiusPx, orbit.RadiansPerUpdate, orbit.PhaseRadians, orbit.IdentityPhaseRadians);
        if (_entity.LashGeometry is { } lash) {
            float progress = lash.Clock == "owner_animation" ? 1f - Math.Clamp(owner.itemAnimation / (float)Math.Max(1, owner.itemAnimationMax), 0f, 1f)
                : Math.Clamp(_age / (float)Math.Max(1, AuthoredTicksToProjectileUpdates(lash.DurationTicks!.Value)), 0f, 1f);
            BuildLashPoints(MotionAnchor(owner, lash.Anchor), _motionAxis, progress, lash.ReachPx,
                lash.Segments, lash.SweepStartRadians, lash.SweepEndRadians, lash.BendRatio,
                lash.UseOwnerGravity ? owner.gravDir : 1f, owner.direction,
                lash.UseOwnerWhipRangeMultiplier ? owner.whipRangeMultiplier : 1f);
            Projectile.Center = _whipPoints[^1]; Projectile.velocity = Vector2.Zero;
        }
        if (_entity.Seek is { } seeks) foreach (var seek in seeks) if (MotionWindowActive(seek.Window)) {
            Vector2? target = seek.Target switch {
                "owner_center" => owner.Center, "owner_mounted" => owner.MountedCenter,
                "cursor" => MotionCursorTarget(owner, seek.CursorLeashPx),
                "nearest_npc" => InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)
                    ? ResolveMotionNpc(seek.SearchRangeTiles!.Value * 16f, seek.RequireLineOfSight == true)?.Center : null,
                _ => null,
            };
            if (target.HasValue) SeekVelocity(target.Value, seek.MaxSpeed, seek.VelocityLerpPerUpdate,
                seek.LimitSpeedToDistance, seek.MinimumSpeed ?? 0f);
        }
        // Fixed new stage order: seek -> signed gravity -> retention -> sine ->
        // PR148 turn/speed/angular homing (caller) -> rotation/presentation.
        if (_entity.VerticalAcceleration is { } gravity && MotionWindowActive(gravity.Window)) AccelerateVertical(gravity.AccelerationYPerUpdate);
        if (_entity.VelocityRetention is { } retention && MotionWindowActive(retention.Window)) RetainVelocity(retention.MultiplierPerUpdate);
        if (_entity.Oscillation is { } sine && MotionWindowActive(sine.Window)) {
            if (sine.Law == "angular_sine") AngularSine(sine.FrequencyRadiansPerUpdate, sine.PhaseRadians, sine.Amplitude);
            else LateralSine(sine.FrequencyRadiansPerUpdate, sine.PhaseRadians, sine.Amplitude, 0f, substeps: Projectile.extraUpdates + 1);
        }
        if (_entity.Opacity is { } opacity && MotionWindowActive(opacity.Window)) Projectile.alpha = opacity.Alpha;
        if (_entity.VisualScaleRate is { } scale && MotionWindowActive(scale.Window)) AddVisualScale(scale.DeltaPerUpdate, scale.MaxScale, nonnegative: true);
        if (_entity.Arrival is { } arrival && MotionWindowActive(arrival.Window)
            && InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)
            && Projectile.Distance(MotionAnchor(owner, arrival.Target)) < arrival.RadiusPx) { Projectile.Kill(); return; }
        if (_entity.Proximity is { } proximity && MotionWindowActive(proximity.Window)
            && InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)) {
            NPC? target = ResolveMotionNpc(proximity.SearchRangeTiles * 16f, proximity.RequireLineOfSight);
            if (target is not null && Projectile.Distance(target.Center) <= proximity.TriggerRadiusPx) {
                if (proximity.Action == "expire_then_kill") ExpireMotion(target);
                Projectile.Kill(); return;
            }
        }
        if (_entity.ManaSustain is not null && !PaySustainedMana(owner)) { Projectile.friendly = false; Projectile.Kill(); }
    }
    private Vector2 MotionCursorTarget(Player owner, float? leash)
    {
        Vector2 offset = Main.myPlayer == owner.whoAmI ? Main.MouseWorld - owner.MountedCenter : new Vector2(Projectile.localAI[0], Projectile.localAI[1]);
        // Cursor seek and cursor aim can coexist: ai is the published axis; cursor
        // position is separately transported in ExtraAI v6, never alias those units.
        if (leash.HasValue && offset.Length() > leash.Value) offset = offset.SafeNormalize(Vector2.UnitX * owner.direction) * leash.Value;
        if (Main.myPlayer == owner.whoAmI) PublishMotionCursor(offset);
        return owner.MountedCenter + offset;
    }
    private Vector2? _publishedMotionCursor;
    private int _motionCursorSyncAge = -1000;
    private void PublishMotionCursor(Vector2 offset)
    {
        Projectile.localAI[0] = offset.X; Projectile.localAI[1] = offset.Y;
        if (_publishedMotionCursor is not null && (_age - _motionCursorSyncAge < Math.Max(1, AuthoredTicksToProjectileUpdates(6))
            || Vector2.DistanceSquared(_publishedMotionCursor.Value, offset) <= 4f)) return;
        _publishedMotionCursor = offset; _motionCursorSyncAge = _age; Projectile.netUpdate = true;
    }
    private void ApplyMotionReturnTrigger(Player owner)
    {
        if (_entity?.ReturnTrigger is not { } trigger) return;
        if (!InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)) {
            if (_returning && trigger.DisableTileCollisionOnReturn) Projectile.tileCollide = false;
            return;
        }
        if (trigger.AfterTicks is int ticks && _age >= AuthoredTicksToProjectileUpdates(ticks)
            || trigger.OwnerDistancePx is float distance && Projectile.Distance(owner.Center) >= distance
            || trigger.OnOwnerRelease && !owner.channel)
            LatchReturn(trigger.DisableTileCollisionOnReturn);
        else if (_returning && trigger.DisableTileCollisionOnReturn) Projectile.tileCollide = false;
    }
    private void ExpireMotion(NPC? target)
    {
        if (_expireEventRan) return;
        _expireEventRan = true;
        RunRuntimeEvent(RuntimeEventKind.OnExpire, target, Projectile.damage);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnExpire, Projectile.Center);
        // Native Kill sends its packet before mod OnKill. Publish the existing
        // ExtraAI terminal observation first so the server sees the actual cause,
        // rather than guessing expiry from an unrelated tile/contact kill.
        if (Main.netMode == Terraria.ID.NetmodeID.MultiplayerClient && Projectile.owner == Main.myPlayer)
            NetMessage.SendData(Terraria.ID.MessageID.SyncProjectile, -1, -1, null, Projectile.whoAmI);
    }
    private void DispatchReceivedMotionExpiry()
    {
        if (_pendingMotionExpiry is not { } observation || !_configured) return;
        _pendingMotionExpiry = null;
        if (!InfiniRuntimeAuthority.IsServer || _expireEventRan || !Projectile.active
            || !float.IsFinite(observation.Position.X) || !float.IsFinite(observation.Position.Y)
            || Projectile.position != observation.Position || observation.Age <= 0 || _activationDelayTicks > 0
            || _data is null || !GeneratedItemRegistryService.IsCurrentWorldData(_data)
            || _entity?.Proximity is not { Action: "expire_then_kill" } proximity
            || !MotionWindowActive(proximity.Window, observation.Age, observation.Released, observation.Returning,
                observation.ReleaseAge, observation.ReturnAge)) return;
        NPC? target = ResolveMotionNpc(proximity.SearchRangeTiles * 16f, proximity.RequireLineOfSight);
        if (target is null || Projectile.Distance(target.Center) > proximity.TriggerRadiusPx) return;
        // The authenticated native source snapshot is only a claim. Actual
        // admitted geometry/window/NPC checks above still own server execution.
        // Missing metadata never authorizes replay at a later source position
        // or after retirement; no live actor is rewound to reconstruct the event.
        EmitSpawnEvent();
        ExpireMotion(target);
    }
    private void ApplyMotionRotation()
    {
        if (_entity?.Rotation is not { } rotation || !MotionWindowActive(rotation.Window)) return;
        switch (rotation.Mode) {
            case "axis": Projectile.rotation = _motionAxis.ToRotation() + rotation.OffsetRadians; break;
            case "velocity": Projectile.rotation = Projectile.velocity.SafeNormalize(_motionAxis).ToRotation() + rotation.OffsetRadians; break;
            case "spin":
                var window = rotation.Window;
                int origin = window?.HasTimingWindow == true
                    ? window.Clock switch { "since_release" => _releaseAge, "since_return" => _returnAge, _ => 0 }
                    : window?.Phase switch { "released" => _releaseAge, "returning" => _returnAge,
                        "outbound" when _released => _releaseAge, _ => 0 };
                int steps = Math.Max(1, _age - origin - AuthoredTicksToProjectileUpdates(window?.StartDelayTicks ?? 0)
                    + (window?.Clock is "since_release" or "since_return"
                        || window?.HasTimingWindow != true && (window?.Phase is "released" or "returning"
                            || window?.Phase == "outbound" && _released) ? 1 : 0));
                Projectile.rotation = rotation.OffsetRadians + (steps - 1) * rotation.RadiansPerUpdate!.Value;
                SpinBody(rotation.RadiansPerUpdate.Value);
                break;
        }
    }
}
