#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    public override bool ShouldUpdatePosition()
        // Pending definitions suspend native position integration without destroying
        // the latest SyncProjectile velocity that hydration will resume.
        => _configured && !(_entity?.IsOwnerAttached == true && _entity.Movement.Code is 18 or 19 or 20)
            && _entity?.Controller.Code != RuntimeControllerCode.ChannelBeam
            && !AbsoluteMotionActive();

    public override void AI()
    {
        if (!TryHydrate() || _data is null || _entity is null)
            return;

        _initialNpcExclusion = _initialNpcExclusion.AfterUpdate();

        if (_activationDelayTicks > 0)
        {
            _activationDelayTicks--;
            Projectile.friendly = false;
            Projectile.alpha = 220;
            Projectile.velocity = Vector2.Zero;
            // Native collision follows this AI call. The final waiting update
            // must remain harmless until on_spawn and the controller run below.
            return;
        }

        // Arming follows the active-age clock, not the one-shot event flag:
        // a peer can receive a waiting snapshot after observing on_spawn.
        if (_age == 0 && _entity.Spawn.OverTarget.DelayTicks > 0)
        {
            Projectile.alpha = 0;
            Projectile.friendly = _entity.Damage.Enabled && Projectile.damage > 0;
            Projectile.netUpdate = true;
        }

        if (!_spawnEventRan)
        {
            // Waiting suppresses movement, not the authored launch. Replay its
            // exact sampled/native-shot vector (or authored constant) only at first activation;
            // later hydration must not reset an already moving projectile.
            if (_age == 0 && _entity.Spawn.OverTarget.DelayTicks > 0
                && _entity.UsesInitialVelocity)
                Projectile.velocity = _sampledInitialVelocity ?? _nativeShotInitialVelocity
                    ?? (_entity.Spawn.Aim != "none" ? _initialDirection * _entity.Spawn.SpeedPxPerTick : Vector2.Zero);
            EmitSpawnEvent();
        }

        _age++;
        RunPeriodicActions();

        if (_entity.Controller.Code == RuntimeControllerCode.TargetAndFire)
        {
            // Firing is independent of authored motion. Omitted movement keeps
            // the legacy stationary helper; native position integration still
            // occurs after AI, so shots use the current (not predicted) center.
            RunResolvedMotion();
            ApplyActiveModifiers();
            if (Projectile.active) ApplyTargetAndFire();
        }
        else if (!RunController())
        {
            RunResolvedMotion();
            ApplyActiveModifiers();
        }
        ApplyNpcAttraction();
        ApplyHitboxCurveVisual();
        ApplyVisualScaleCurve();

        if (_entity.Light.Strength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(_entity.Light.Color, Color.White);
            float s = _entity.Light.Strength;
            Lighting.AddLight(Projectile.Center, c.R / 255f * s, c.G / 255f * s, c.B / 255f * s);
        }
        InfiniVfxRuntime.OnTick(Projectile, _data, _entity.Id, _data.VfxManifest, ref _vfxState);

        if (_entity.Rotation is null && _entity.Movement.Code is not (14 or 16 or 17 or 18) && Projectile.velocity.LengthSquared() > 0.01f)
            Projectile.rotation = SpritePresentation.ProjectileNativeRotation(_entity!, Projectile.velocity.ToRotation());

        ApplyMotionRotation();

        // Terraria decrements timeLeft after AI; 2 is still a live update and
        // is also the keep-alive value used by held/channelled controllers.
        if (Projectile.timeLeft <= 1 && !_expireEventRan)
        {
            _expireEventRan = true;
            RunRuntimeEvent(RuntimeEventKind.OnExpire, null, 0);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnExpire, Projectile.Center);
        }
    }

    private void EmitSpawnEvent()
    {
        if (_spawnEventRan) return;
        _spawnEventRan = true;
        RunRuntimeEvent(RuntimeEventKind.OnSpawn, null, 0);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnSpawn, Projectile.Center);
    }

    private float HitboxCurveScale()
        => _entity?.HitboxCurve?.ScaleAt(_age, Projectile.extraUpdates + 1) ?? 1f;

    private void ApplyHitboxCurveVisual()
    {
        if (_entity?.HitboxCurve?.MirrorToSprite == true)
            Projectile.scale = _entity.Hitbox.DrawScale * _entity.Visual.Scale * HitboxCurveScale();
    }

    private bool RunController()
    {
        return _entity!.Controller.Code switch
        {
            RuntimeControllerCode.None => false,
            RuntimeControllerCode.ChannelBeam => ApplyChannelBeam(),
            RuntimeControllerCode.ChargeThenRelease => ApplyChargeThenRelease(),
            RuntimeControllerCode.TargetAndFire => ApplyTargetAndFire(),
            _ => RejectUnknownController(),
        };
    }

    private bool RejectUnknownController()
    {
        Projectile.friendly = false;
        Projectile.Kill();
        return true;
    }

    private bool ApplyChannelBeam()
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner) || !owner.channel || !HoldingGeneratedItem(owner))
        {
            Projectile.Kill();
            return true;
        }
        if (!TryPayChannelBeamMana(owner))
        {
            Projectile.friendly = false;
            Projectile.Kill();
            return true;
        }
        Vector2 direction = AimDirection(owner);
        Projectile.Center = owner.MountedCenter + direction * 18f;
        Projectile.velocity = direction;
        Projectile.rotation = SpritePresentation.ProjectileNativeRotation(_entity!, direction.ToRotation());
        Projectile.timeLeft = 2;
        Projectile.tileCollide = _entity!.Collision.TileCollide;
        ApplyOwnerLiveness(owner, true, "keep_alive", false);
        Projectile.friendly = ChannelBeamWarmupProgress() >= (_entity.Controller.Params.DamageStartProgress ?? 1d);
        return true;
    }

    private bool TryPayChannelBeamMana(Player owner)
    {
        return _entity!.Controller.Params.ManaPayment != "each_use_time" || PaySustainedMana(owner);
    }

    private double ChannelBeamWarmupProgress() => BeamWarmupProgress();

    private bool ApplyChargeThenRelease()
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return true; }
        RuntimeParamsSpec p = _entity!.Controller.Params;
        if (!_released)
        {
            int chargeDuration = AdvanceCharge(p.ChargeTicks);
            Vector2 direction = AimDirection(owner);
            if (_entity.IsOwnerAttached)
            {
                Projectile.Center = owner.MountedCenter + direction * 18f;
                Projectile.velocity = direction;
                ApplyOwnerLiveness(owner, true, "keep_alive", false);
            }
            else
                Projectile.velocity = Vector2.Zero;
            bool release = !owner.channel || !HoldingGeneratedItem(owner) || _chargeTicks >= chargeDuration && _entity.Controller.Params.DurationTicks > 0 && _age >= AuthoredTicksToProjectileUpdates(_entity.Controller.Params.DurationTicks);
            if (!release)
            {
                // Native Update decrements timeLeft after every AI subupdate.
                // Charging suspends flight: compensate that decrement instead
                // of exhausting the authored lifetime down to the keep-alive 1.
                // Release and owner cancellation do not take this branch.
                Projectile.timeLeft++;
                Projectile.tileCollide = false;
                Projectile.friendly = false;
                return true;
            }
            ReleaseCharge(direction, chargeDuration,
                p.ChargeDamageMultiplier ?? Math.Max(1f, p.PowerMultiplier),
                p.KnockbackMultiplier ?? Math.Max(1f, p.PowerMultiplier),
                p.SpeedMultiplier ?? Math.Max(1f, p.PowerMultiplier), _entity.Spawn.SpeedPxPerTick, restoreLegacyContact: true);
            Projectile.friendly = _entity.Damage.Enabled && Projectile.damage > 0;
            Projectile.tileCollide = _entity.Collision.TileCollide;
        }
        return !_released;
    }

    private bool ApplyTargetAndFire()
    {
        if (!_entity!.Movement.IsConfigured && !HasComposableMotion) Projectile.velocity = Vector2.Zero;
        if (_entity.Targeting.IntervalTicks <= 0) return true;
        _controllerTimer++;
        int interval = AuthoredTicksToProjectileUpdates(Math.Max(6, _entity.Targeting.IntervalTicks));
        if (_controllerTimer < interval || !InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile))
            return true;
        _controllerTimer = 0;
        float range = Math.Max(16f, (_entity.Targeting.RangeTiles > 0 ? _entity.Targeting.RangeTiles : _entity.Controller.Params.RangeTiles) * 16f);
        NPC? target = FindFiringTarget(range, _entity.Targeting);
        if (target is null) return true;
        _lastTarget = target.whoAmI;
        string shotId = _entity.Targeting.ShotEntityId;
        Vector2 direction = Projectile.DirectionTo(target.Center);
        RuntimeSpawnBudget budget = _activationSpawnBudget ?? new RuntimeSpawnBudget(0);
        if (_entity.Targeting.DamageMultiplier is not float damageMultiplier)
            return true;
        if (!RuntimeChildCombat.TryResolve(_entity.Targeting.DamageBasis, _entity.Targeting.KnockbackBasis,
            damageMultiplier, RuntimeParentCombat.Capture(Projectile.GetSource_FromThis(), Owner()),
            out int? damageOverride, out float? knockbackOverride))
            return true;
        int requested = _entity.Targeting.Count ?? 1;
        int granted = budget.Reserve(requested);
        int spawned = granted == requested ? SpawnRuntimeEntity(_data!, shotId, Owner(), Projectile.GetSource_FromThis(),
            Projectile.Center, direction, _childDepth + 1, granted, requestedCount: requested,
            spreadOverride: (float)(_entity.Targeting.SpreadRadians ?? 0d),
            damageMultiplier: damageMultiplier, activationBudget: budget,
            rootDamageOverride: damageOverride, rootKnockbackOverride: knockbackOverride) : 0;
        budget.Return(granted - spawned);
        Projectile.netUpdate = true;
        return true;
    }

    private NPC? FindFiringTarget(float range, RuntimeTargetingSpec targeting)
    {
        bool Admitted(NPC npc, out float score)
        {
            score = float.PositiveInfinity;
            if (!npc.CanBeChasedBy(Projectile)) return false;
            float distance = Vector2.Distance(Projectile.Center, npc.Center);
            // Geometric admission precedes the preference discount. A previous
            // or assigned target cannot turn a hard radius into a score radius.
            if (targeting.HardRange == true && distance > range) return false;
            score = npc.whoAmI == _lastTarget
                ? distance * (1f - Math.Clamp(targeting.SameTargetBias, 0f, 0.9f))
                : distance;
            if (targeting.HardRange != true && score >= range) return false;
            return targeting.RequireLineOfSight != true || Collision.CanHit(
                Projectile.position, Projectile.width, Projectile.height, npc.position, npc.width, npc.height);
        }

        if (targeting.TargetPolicy == "player_assigned_first")
        {
            NPC? assigned = Projectile.OwnerMinionAttackTargetNPC;
            if (assigned is not null && Admitted(assigned, out _)) return assigned;
        }
        NPC? selected = null;
        float best = float.PositiveInfinity;
        foreach (NPC npc in Main.ActiveNPCs)
            if (Admitted(npc, out float score) && score < best)
            {
                selected = npc;
                best = score;
            }
        return selected;
    }

    private Player Owner()
        => Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers ? Main.player[Projectile.owner] : Main.player[0];

    private static bool OwnerCanControl(Player owner)
        => owner is not null && owner.active && !owner.dead && !owner.noItems && !owner.CCed;

    private bool HoldingGeneratedItem(Player owner)
        => owner.HeldItem?.ModItem is GeneratedItem item && string.Equals(item.Data.Id, _generatedItemId, StringComparison.Ordinal);

    private Vector2 AimDirection(Player owner)
    {
        Vector2 direction = Projectile.velocity.SafeNormalize(_initialDirection);
        if (Projectile.owner == Main.myPlayer)
        {
            direction = (Main.MouseWorld - owner.MountedCenter).SafeNormalize(new Vector2(owner.direction, 0f));
            SetOwnerSyncedVector(direction, changeThresholdSquared: 0.0004f, minSyncIntervalTicks: 6);
        }
        else if (new Vector2(Projectile.ai[0], Projectile.ai[1]).LengthSquared() > 0.1f)
            direction = new Vector2(Projectile.ai[0], Projectile.ai[1]).SafeNormalize(direction);
        owner.ChangeDir(direction.X >= 0f ? 1 : -1);
        return direction;
    }


    private void SetOwnerSyncedVector(Vector2 value, float changeThresholdSquared, int minSyncIntervalTicks)
    {
        if (Projectile.owner != Main.myPlayer)
            return;
        Projectile.ai[0] = value.X;
        Projectile.ai[1] = value.Y;
        // Local input keeps moving during the throttle. Compare against the last
        // publication so its final value still reaches peers after input stops.
        if (_age - _lastOwnerVectorSyncAge < Math.Max(1, AuthoredTicksToProjectileUpdates(minSyncIntervalTicks))
            || _lastPublishedOwnerVector is { } previous
                && Vector2.DistanceSquared(previous, value) <= Math.Max(0f, changeThresholdSquared))
            return;
        _lastPublishedOwnerVector = value;
        _lastOwnerVectorSyncAge = _age;
        Projectile.netUpdate = true;
    }

    private NPC? FindNearestNpc(Vector2 center, float range)
        => ResolveMotionNpc(range, false, legacyDistance: true);

    private void Home(float rangeTiles, float strength)
    {
        NPC? target = FindNearestNpc(Projectile.Center, Math.Max(16f, rangeTiles * 16f));
        if (target is null) return;
        float speed = Math.Max(1f, Projectile.velocity.Length());
        SeekVelocity(target.Center, speed, Math.Clamp(strength, 0.001f, 1f), false);
    }

    private void SineHome(RuntimeParamsSpec p)
    {
        Home(p.RangeTiles, p.HomingStrength);
        LateralSine(0.18f, 0f, p.WaveAmplitude, 1f, 0.03f);
    }

    private void OrbitOwner(float rangeTiles)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        float radius = Math.Max(16f, rangeTiles * 16f);
        OrbitTrajectory(owner.MountedCenter, radius, _entity!.Movement.Params.OrbitRadiansPerUpdate ?? 0.055f, 0f, 0.31f);
        Projectile.tileCollide = false;
    }

    private void ReturnAfter(int returnAfterTicks, float returnSpeed)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        if (!_returning && _age >= Math.Max(1, AuthoredTicksToProjectileUpdates(returnAfterTicks))) LatchReturn(true);
        if (!_returning) return;
        Projectile.tileCollide = false;
        float speed = Math.Max(1f, returnSpeed);
        SeekVelocity(owner.Center, speed, 0.2f, false);
        if (Projectile.Distance(owner.Center) < 24f) Projectile.Kill();
    }

    private void PhaseDrift(float strength)
    {
        float s = Math.Clamp(strength, 0f, 2f);
        AngularSine(0.1f, 0f, s, 0.01f);
        Projectile.alpha = (int)(80f * Math.Clamp(s, 0f, 1f));
    }

    private void Accelerate(float acceleration, float maxSpeed)
    {
        float a = acceleration <= 0f ? 1f : acceleration;
        float cap = Math.Max(1f, maxSpeed);
        MultiplyVelocityCapped(a, cap, onlyBelowCap: true, legacyNormalize: true);
    }

    private void Vortex(RuntimeParamsSpec p)
    {
        RetainVelocity(0.99f);
        PullNpcs(Projectile.Center, p.RangeTiles * 16f, p.PullStrength);
    }

    private void Blackhole(RuntimeParamsSpec p)
    {
        RetainVelocity(0.985f);
        PullNpcs(Projectile.Center, p.RangeTiles * 16f, p.PullStrength);
    }

    private static void PullNpcs(Vector2 center, float radius, float strength)
    {
        ApplyNpcImpulseKernel(center, radius, strength, "none", 16, synchronize: false, legacyDirection: true, chaseSource: null);
    }

    private void ProximityMissile(RuntimeParamsSpec p)
    {
        NPC? target = FindNearestNpc(Projectile.Center, Math.Max(16f, p.RangeTiles * 16f));
        if (target is null) return;
        Home(p.RangeTiles, p.HomingStrength);
        if (Projectile.Distance(target.Center) <= Math.Max(4f, p.ProximityRadiusPx))
        {
            RunRuntimeEvent(RuntimeEventKind.OnExpire, target, Projectile.damage);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnExpire, Projectile.Center);
            _expireEventRan = true;
            Projectile.Kill();
        }
    }

    private void Expand(RuntimeParamsSpec p)
    {
        float max = p.MaxScale <= 0f ? Projectile.scale : p.MaxScale;
        AddVisualScale(p.ScalePerTick, max);
    }

    private void Flail(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        float maxRange = Math.Max(32f, p.RangeTiles * 16f);
        if (!_returning && (Projectile.Distance(owner.MountedCenter) >= maxRange || !owner.channel)) LatchReturn(true);
        if (_returning)
        {
            Projectile.tileCollide = false;
            SeekVelocity(owner.MountedCenter, Math.Max(1f, p.ReturnSpeed), 0.25f, false);
            if (Projectile.Distance(owner.MountedCenter) < 20f) Projectile.Kill();
        }
        ClaimHeldProjectile(owner);
        SpinBody(0.4f);
    }

    private void Yoyo(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        float leash = Math.Max(32f, p.RangeTiles * 16f);
        if (!owner.channel) LatchReturn(false);
        Vector2 target;
        if (_returning) target = owner.MountedCenter;
        else
        {
            Vector2 offset = Main.myPlayer == owner.whoAmI ? Main.MouseWorld - owner.MountedCenter : new Vector2(Projectile.ai[0], Projectile.ai[1]);
            if (offset.Length() > leash) offset = offset.SafeNormalize(Vector2.UnitX * owner.direction) * leash;
            if (Main.myPlayer == owner.whoAmI)
                SetOwnerSyncedVector(offset, changeThresholdSquared: 4f, minSyncIntervalTicks: 6);
            target = owner.MountedCenter + offset;
        }
        SeekVelocity(target, Math.Max(1f, p.ReturnSpeed), 0.28f, true);
        Projectile.tileCollide = !_returning && _entity!.Collision.TileCollide;
        ClaimHeldProjectile(owner);
        SpinBody(0.35f);
        if (_returning && Projectile.Distance(owner.MountedCenter) < 20f) Projectile.Kill();
    }

    private void Whip(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner) || owner.itemAnimation <= 0) { Projectile.Kill(); return; }
        BuildWhipPoints(owner, p);
        if (_whipPoints.Count > 0) Projectile.Center = _whipPoints[^1];
        Vector2 direction = Projectile.Center - owner.MountedCenter;
        Projectile.velocity = direction.SafeNormalize(_initialDirection);
        Projectile.rotation = SpritePresentation.ProjectileNativeRotation(_entity!, Projectile.velocity.ToRotation());
        Projectile.timeLeft = 2;
        Projectile.tileCollide = _entity!.Collision.TileCollide;
        ApplyOwnerLiveness(owner, true, "match_lifetime", false);
    }

    private void BuildWhipPoints(Player owner, RuntimeParamsSpec p)
    {
        int segments = Math.Clamp(p.Segments, 3, 64);
        float animationMax = Math.Max(1f, owner.itemAnimationMax);
        float progress = 1f - Math.Clamp(owner.itemAnimation / animationMax, 0f, 1f);
        BuildLashPoints(owner.MountedCenter, _initialDirection, progress, Math.Max(32f, p.RangeTiles * 16f),
            segments, -0.75f, 0.75f, 0.12f, _entity!.WhipUsesOwnerGravity == true ? owner.gravDir : 1f,
            owner.direction, owner.whipRangeMultiplier);
    }

    private void ForwardRetract(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        int duration = Math.Max(2, AuthoredTicksToProjectileUpdates(p.DurationTicks));
        float progress = Math.Clamp(_age / (float)duration, 0f, 1f);
        float reachProgress = TriangleReach(progress);
        Vector2 direction = AimDirection(owner);
        Projectile.Center = owner.MountedCenter + direction * (18f + reachProgress * p.RangeTiles * 16f);
        Projectile.velocity = direction;
        Projectile.rotation = SpritePresentation.ProjectileNativeRotation(_entity!, direction.ToRotation());
        Projectile.timeLeft = Math.Max(2, duration - _age + 1);
        Projectile.tileCollide = false;
        ClaimHeldProjectile(owner);
        if (_age >= duration) Projectile.Kill();
    }
}
