#nullable enable
using InfiniCrafterLocal.Common.Models;
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
        => !_configured || !(_entity?.IsOwnerAttached == true && _entity.Movement.Code is 18 or 19)
            && _entity?.Controller.Code != RuntimeControllerCode.ChannelBeam;

    public override void AI()
    {
        if (!TryHydrate() || _data is null || _entity is null)
            return;

        if (_activationDelayTicks > 0)
        {
            _activationDelayTicks--;
            Projectile.friendly = false;
            Projectile.alpha = 220;
            Projectile.velocity = Vector2.Zero;
            if (_activationDelayTicks == 0)
            {
                Projectile.alpha = 0;
                Projectile.friendly = _entity.Damage.Enabled && _entity.Damage.Damage > 0;
                Projectile.netUpdate = true;
            }
            return;
        }

        if (!_spawnEventRan)
        {
            _spawnEventRan = true;
            RunRuntimeEvent(RuntimeEventKind.OnSpawn, null, 0);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnSpawn, Projectile.Center);
        }

        _age++;
        RunPeriodicActions();

        bool controllerOwnsMotion = RunController();
        if (!controllerOwnsMotion)
            RunMovement();

        if (_entity.Light.Strength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(_entity.Light.Color, Color.White);
            float s = _entity.Light.Strength;
            Lighting.AddLight(Projectile.Center, c.R / 255f * s, c.G / 255f * s, c.B / 255f * s);
        }
        InfiniVfxRuntime.OnTick(Projectile, _entity.Id, _data.VfxManifest, ref _vfxState);

        if (_entity.Movement.Code is not (14 or 16 or 17 or 18) && Projectile.velocity.LengthSquared() > 0.01f)
            Projectile.rotation = Projectile.velocity.ToRotation() + MathHelper.PiOver2;

        if (Projectile.timeLeft <= 2 && !_expireEventRan)
        {
            _expireEventRan = true;
            RunRuntimeEvent(RuntimeEventKind.OnExpire, null, 0);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnExpire, Projectile.Center);
        }
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
        Vector2 direction = AimDirection(owner);
        Projectile.Center = owner.MountedCenter + direction * 18f;
        Projectile.velocity = direction;
        Projectile.rotation = direction.ToRotation();
        Projectile.timeLeft = 2;
        Projectile.tileCollide = false;
        ClaimHeldProjectile(owner, keepAnimation: true);
        int warmup = AuthoredTicksToProjectileUpdates(_entity!.Controller.Params.WarmupTicks);
        Projectile.friendly = warmup <= 0 || _age >= warmup;
        return true;
    }

    private bool ApplyChargeThenRelease()
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return true; }
        RuntimeParamsSpec p = _entity!.Controller.Params;
        if (!_released)
        {
            int chargeDuration = Math.Max(1, AuthoredTicksToProjectileUpdates(p.ChargeTicks));
            _chargeTicks = Math.Min(chargeDuration, _chargeTicks + 1);
            Vector2 direction = AimDirection(owner);
            if (_entity.IsOwnerAttached)
            {
                Projectile.Center = owner.MountedCenter + direction * 18f;
                Projectile.velocity = direction;
                ClaimHeldProjectile(owner, keepAnimation: true);
            }
            else
                Projectile.velocity = Vector2.Zero;
            bool release = !owner.channel || !HoldingGeneratedItem(owner) || _chargeTicks >= chargeDuration && _entity.Controller.Params.DurationTicks > 0 && _age >= AuthoredTicksToProjectileUpdates(_entity.Controller.Params.DurationTicks);
            if (!release)
            {
                Projectile.timeLeft = Math.Max(Projectile.timeLeft, 2);
                Projectile.friendly = false;
                return true;
            }
            _released = true;
            float ratio = Math.Clamp(_chargeTicks / (float)chargeDuration, 0f, 1f);
            float multiplier = MathHelper.Lerp(1f, Math.Max(1f, p.PowerMultiplier), ratio);
            Projectile.damage = Math.Max(0, (int)MathF.Round(_entity.Damage.Damage * multiplier));
            Projectile.knockBack = _entity.Damage.Knockback * multiplier;
            Projectile.friendly = _entity.Damage.Enabled && Projectile.damage > 0;
            Projectile.velocity = direction * Math.Max(1f, _entity.Spawn.SpeedPxPerTick) * multiplier;
            Projectile.tileCollide = _entity.Collision.TileCollide;
            RunRuntimeEvent(RuntimeEventKind.OnRelease, null, 0);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnRelease, Projectile.Center);
            if (ratio >= 0.999f)
            {
                RunRuntimeEvent(RuntimeEventKind.ChannelComplete, null, 0);
                EmitAndSyncVfxEvent(RuntimeEventKind.ChannelComplete, Projectile.Center);
            }
            Projectile.netUpdate = true;
        }
        return !_released;
    }

    private bool ApplyTargetAndFire()
    {
        Projectile.velocity = Vector2.Zero;
        _controllerTimer++;
        int interval = AuthoredTicksToProjectileUpdates(Math.Max(6, _entity!.Targeting.IntervalTicks > 0 ? _entity.Targeting.IntervalTicks : _entity.Controller.Params.IntervalTicks));
        if (_controllerTimer < interval || !InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile))
            return true;
        _controllerTimer = 0;
        float range = Math.Max(16f, (_entity.Targeting.RangeTiles > 0 ? _entity.Targeting.RangeTiles : _entity.Controller.Params.RangeTiles) * 16f);
        NPC? target = FindNearestNpc(Projectile.Center, range, _lastTarget, _entity.Targeting.SameTargetBias);
        if (target is null) return true;
        _lastTarget = target.whoAmI;
        string shotId = _entity.Targeting.ShotEntityId;
        Vector2 direction = Projectile.DirectionTo(target.Center);
        int spawned = SpawnRuntimeEntity(_data!, shotId, Owner(), Projectile.GetSource_FromThis(), Projectile.Center, direction, _childDepth + 1, _remainingSpawnBudget, requestedCount: 1);
        _remainingSpawnBudget = Math.Max(0, _remainingSpawnBudget - spawned);
        Projectile.netUpdate = true;
        return true;
    }

    private void RunMovement()
    {
        RuntimeMovementSpec movement = _entity!.Movement;
        if (!movement.IsConfigured)
        {
            if (_entity.IsStationary) Projectile.velocity = Vector2.Zero;
            return;
        }
        RuntimeParamsSpec p = movement.Params;
        switch (movement.Code)
        {
            case 0: break;
            case 1: Home(p.RangeTiles, p.HomingStrength); break;
            case 2: Projectile.velocity.Y += p.GravityPerTick; break;
            case 3: Projectile.velocity *= p.VelocityRetention == 0f ? 1f : p.VelocityRetention; break;
            case 4: OrbitOwner(p.RangeTiles); break;
            case 5: ReturnAfter(p.ReturnAfterTicks, p.ReturnSpeed); break;
            case 6: Projectile.velocity.Y += p.GravityPerTick; break;
            case 7: SineHome(p); break;
            case 8: PhaseDrift(p.PhaseStrength); break;
            case 9: Accelerate(p.Acceleration, p.MaxSpeed); break;
            case 10: Projectile.velocity = Projectile.velocity.RotatedBy(p.TurnRadiansPerTick); break;
            case 11: Vortex(p); break;
            case 12: Blackhole(p); break;
            case 13: ProximityMissile(p); break;
            case 14: Projectile.rotation += 0.35f; ReturnAfter(p.ReturnAfterTicks, p.ReturnSpeed); break;
            case 15: Expand(p); break;
            case 16: Flail(p); break;
            case 17: Yoyo(p); break;
            case 18: Whip(p); break;
            case 19: ForwardRetract(p); break;
            default:
                Projectile.friendly = false;
                Projectile.Kill();
                break;
        }
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
        Vector2 previous = new(Projectile.ai[0], Projectile.ai[1]);
        Projectile.ai[0] = value.X;
        Projectile.ai[1] = value.Y;
        if (_age - _lastOwnerVectorSyncAge < Math.Max(1, AuthoredTicksToProjectileUpdates(minSyncIntervalTicks))
            || Vector2.DistanceSquared(previous, value) <= Math.Max(0f, changeThresholdSquared))
            return;
        _lastOwnerVectorSyncAge = _age;
        Projectile.netUpdate = true;
    }

    private NPC? FindNearestNpc(Vector2 center, float range, int previous = -1, float sameTargetBias = 0f)
    {
        NPC? selected = null;
        float best = range;
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (!npc.CanBeChasedBy(Projectile)) continue;
            float distance = Vector2.Distance(center, npc.Center);
            if (npc.whoAmI == previous) distance *= 1f - Math.Clamp(sameTargetBias, 0f, 0.9f);
            if (distance < best) { best = distance; selected = npc; }
        }
        return selected;
    }

    private void Home(float rangeTiles, float strength)
    {
        NPC? target = FindNearestNpc(Projectile.Center, Math.Max(16f, rangeTiles * 16f));
        if (target is null) return;
        float speed = Math.Max(1f, Projectile.velocity.Length());
        Vector2 desired = Projectile.DirectionTo(target.Center) * speed;
        Projectile.velocity = Vector2.Lerp(Projectile.velocity, desired, Math.Clamp(strength, 0.001f, 1f));
    }

    private void SineHome(RuntimeParamsSpec p)
    {
        Home(p.RangeTiles, p.HomingStrength);
        float speed = Math.Max(1f, Projectile.velocity.Length());
        Vector2 forward = Projectile.velocity.SafeNormalize(_initialDirection);
        Vector2 lateral = forward.RotatedBy(MathHelper.PiOver2) * MathF.Sin(_age * 0.18f) * p.WaveAmplitude * 0.03f;
        Projectile.velocity = (forward * speed + lateral).SafeNormalize(forward) * speed;
    }

    private void OrbitOwner(float rangeTiles)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        float radius = Math.Max(16f, rangeTiles * 16f);
        float angle = _age * 0.055f + Projectile.identity * 0.31f;
        Vector2 target = owner.MountedCenter + angle.ToRotationVector2() * radius;
        Projectile.velocity = target - Projectile.Center;
        Projectile.tileCollide = false;
    }

    private void ReturnAfter(int returnAfterTicks, float returnSpeed)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        if (!_returning && _age >= Math.Max(1, AuthoredTicksToProjectileUpdates(returnAfterTicks))) _returning = true;
        if (!_returning) return;
        Projectile.tileCollide = false;
        float speed = Math.Max(1f, returnSpeed);
        Projectile.velocity = Vector2.Lerp(Projectile.velocity, Projectile.DirectionTo(owner.Center) * speed, 0.2f);
        if (Projectile.Distance(owner.Center) < 24f) Projectile.Kill();
    }

    private void PhaseDrift(float strength)
    {
        float s = Math.Clamp(strength, 0f, 2f);
        Projectile.velocity = Projectile.velocity.RotatedBy(MathF.Sin(_age * 0.1f) * s * 0.01f);
        Projectile.alpha = (int)(80f * Math.Clamp(s, 0f, 1f));
    }

    private void Accelerate(float acceleration, float maxSpeed)
    {
        float a = acceleration <= 0f ? 1f : acceleration;
        float cap = Math.Max(1f, maxSpeed);
        if (Projectile.velocity.Length() < cap) Projectile.velocity *= a;
        if (Projectile.velocity.Length() > cap) Projectile.velocity = Projectile.velocity.SafeNormalize(_initialDirection) * cap;
    }

    private void Vortex(RuntimeParamsSpec p)
    {
        Projectile.velocity *= 0.99f;
        PullNpcs(Projectile.Center, p.RangeTiles * 16f, p.PullStrength);
    }

    private void Blackhole(RuntimeParamsSpec p)
    {
        Projectile.velocity *= 0.985f;
        PullNpcs(Projectile.Center, p.RangeTiles * 16f, p.PullStrength);
    }

    private static void PullNpcs(Vector2 center, float radius, float strength)
    {
        if (!InfiniRuntimeAuthority.ShouldRunNpcGameplay() || radius <= 0f || strength <= 0f) return;
        int pulled = 0;
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (!npc.CanBeChasedBy() || npc.knockBackResist <= 0f || Vector2.DistanceSquared(npc.Center, center) > radius * radius)
                continue;
            npc.velocity += npc.DirectionTo(center) * strength * Math.Clamp(npc.knockBackResist, 0.1f, 1f);
            if (++pulled >= 16)
                break;
        }
    }

    private void ProximityMissile(RuntimeParamsSpec p)
    {
        NPC? target = FindNearestNpc(Projectile.Center, Math.Max(16f, p.RangeTiles * 16f));
        if (target is null) return;
        Home(p.RangeTiles, p.HomingStrength);
        if (Projectile.Distance(target.Center) <= Math.Max(4f, p.ProximityRadiusPx))
        {
            RunRuntimeEvent(RuntimeEventKind.OnExpire, target, Projectile.damage);
            _expireEventRan = true;
            Projectile.Kill();
        }
    }

    private void Expand(RuntimeParamsSpec p)
    {
        float max = p.MaxScale <= 0f ? Projectile.scale : p.MaxScale;
        Projectile.scale = Math.Min(max, Projectile.scale + p.ScalePerTick);
    }

    private void Flail(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        float maxRange = Math.Max(32f, p.RangeTiles * 16f);
        if (!_returning && (Projectile.Distance(owner.MountedCenter) >= maxRange || !owner.channel)) _returning = true;
        if (_returning)
        {
            Projectile.tileCollide = false;
            Projectile.velocity = Vector2.Lerp(Projectile.velocity, Projectile.DirectionTo(owner.MountedCenter) * Math.Max(1f, p.ReturnSpeed), 0.25f);
            if (Projectile.Distance(owner.MountedCenter) < 20f) Projectile.Kill();
        }
        ClaimHeldProjectile(owner);
        Projectile.rotation += 0.4f;
    }

    private void Yoyo(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        float leash = Math.Max(32f, p.RangeTiles * 16f);
        if (!owner.channel) _returning = true;
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
        Projectile.velocity = Vector2.Lerp(Projectile.velocity, Projectile.DirectionTo(target) * Math.Min(Math.Max(1f, p.ReturnSpeed), Projectile.Distance(target)), 0.28f);
        Projectile.tileCollide = false;
        ClaimHeldProjectile(owner);
        Projectile.rotation += 0.35f;
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
        Projectile.rotation = Projectile.velocity.ToRotation() + MathHelper.PiOver2;
        Projectile.timeLeft = 2;
        Projectile.tileCollide = false;
        ClaimHeldProjectile(owner, matchAnimation: true);
    }

    private void BuildWhipPoints(Player owner, RuntimeParamsSpec p)
    {
        _whipPoints.Clear();
        int segments = Math.Clamp(p.Segments, 3, 64);
        float animationMax = Math.Max(1f, owner.itemAnimationMax);
        float progress = 1f - Math.Clamp(owner.itemAnimation / animationMax, 0f, 1f);
        float extension = MathF.Sin(progress * MathHelper.Pi);
        Vector2 direction = _initialDirection.RotatedBy(MathHelper.Lerp(-0.75f, 0.75f, progress) * owner.direction);
        Vector2 normal = direction.RotatedBy(MathHelper.PiOver2);
        float reach = Math.Max(32f, p.RangeTiles * 16f) * extension;
        for (int i = 0; i <= segments; i++)
        {
            float t = i / (float)segments;
            float bend = MathF.Sin(t * MathHelper.Pi) * MathF.Sin(progress * MathHelper.TwoPi) * reach * 0.12f;
            _whipPoints.Add(owner.MountedCenter + direction * reach * t + normal * bend);
        }
    }

    private void ForwardRetract(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        int duration = Math.Max(2, AuthoredTicksToProjectileUpdates(p.DurationTicks));
        float progress = Math.Clamp(_age / (float)duration, 0f, 1f);
        float reachProgress = 1f - Math.Abs(progress * 2f - 1f);
        Vector2 direction = AimDirection(owner);
        Projectile.Center = owner.MountedCenter + direction * (18f + reachProgress * p.RangeTiles * 16f);
        Projectile.velocity = direction;
        Projectile.rotation = direction.ToRotation() + MathHelper.PiOver2;
        Projectile.timeLeft = Math.Max(2, duration - _age + 1);
        Projectile.tileCollide = false;
        ClaimHeldProjectile(owner);
        if (_age >= duration) Projectile.Kill();
    }
}
