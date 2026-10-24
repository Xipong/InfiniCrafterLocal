#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private bool ApplyMotionOwnerControl(Player owner)
    {
        if (_entity?.OwnerControl is not { } control) return true;
        if (InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)
            && (!OwnerCanControl(owner) || control.RequireHeldItem && !HoldingGeneratedItem(owner)
            || control.RequireChannel && !owner.channel
            || control.RequireItemAnimation && owner.itemAnimation <= 0)) {
            Projectile.friendly = false; Projectile.Kill(); return false;
        }
        ApplyOwnerLiveness(owner, control.ClaimHeldProjectile, control.Animation, control.Lifetime == "keep_alive");
        return true;
    }
    private void ApplyOwnerLiveness(Player owner, bool claimHeld, string animation, bool keepLifetime)
    {
        if (claimHeld) ClaimHeldProjectile(owner);
        if (IsPrimaryRuntimeEntity) {
            if (animation == "keep_alive") {
                owner.itemTime = Math.Max(owner.itemTime, 2);
                owner.itemAnimation = Math.Max(owner.itemAnimation, 2);
            }
            if (animation == "match_lifetime") owner.MatchItemTimeToItemAnimation();
        }
        if (keepLifetime) Projectile.timeLeft = 2;
    }
    private bool PaySustainedMana(Player owner)
    {
        if (!InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)) return true;
        uint now = Main.GameUpdateCount;
        if (!_beamManaClockStarted) {
            _beamManaClockStarted = true; _beamLastManaTick = now;
            return true; // initial payment belongs to native item use
        }
        if (unchecked(now - _beamLastManaTick) < (uint)Math.Max(1, owner.HeldItem.useTime)) return true;
        _beamLastManaTick = now;
        return owner.CheckMana(owner.HeldItem, amount: -1, pay: true, blockQuickMana: false);
    }
    private int AdvanceCharge(int durationTicks)
    {
        int duration = Math.Max(1, AuthoredTicksToProjectileUpdates(durationTicks));
        _chargeTicks = Math.Min(duration, _chargeTicks + 1);
        return duration;
    }
    private void ReleaseCharge(Vector2 direction, int duration, float damageMultiplier, float knockbackMultiplier,
        float speedMultiplier, float launchSpeed, bool restoreLegacyContact = false)
    {
        if (_released) return;
        _released = true; _releaseAge = _age;
        float ratio = Math.Clamp(_chargeTicks / (float)duration, 0f, 1f);
        Projectile.damage = Math.Max(0, (int)MathF.Round(Projectile.damage * MathHelper.Lerp(1f, damageMultiplier, ratio)));
        Projectile.knockBack *= MathHelper.Lerp(1f, knockbackMultiplier, ratio);
        Projectile.velocity = direction * launchSpeed * MathHelper.Lerp(1f, speedMultiplier, ratio);
        if (restoreLegacyContact) {
            Projectile.friendly = _entity!.Damage.Enabled && Projectile.damage > 0;
            Projectile.tileCollide = _entity.Collision.TileCollide;
        }
        RunRuntimeEvent(RuntimeEventKind.OnRelease, null, 0);
        EmitAndSyncVfxEvent(RuntimeEventKind.OnRelease, Projectile.Center);
        if (_chargeTicks >= duration) {
            RunRuntimeEvent(RuntimeEventKind.ChannelComplete, null, 0);
            EmitAndSyncVfxEvent(RuntimeEventKind.ChannelComplete, Projectile.Center);
        }
        Projectile.netUpdate = true;
    }
    private void ApplyMotionCharge(Player owner)
    {
        if (_entity?.Charge is not { } charge || _released) return;
        int duration = AdvanceCharge(charge.DurationTicks);
        bool release = !owner.channel || charge.AutoReleaseAfterActiveTicks is int auto
            && _age >= AuthoredTicksToProjectileUpdates(auto);
        if (!release) {
            if (_entity.ChargeRelease?.PauseLifetimeWhileCharging == true) Projectile.timeLeft++;
            return;
        }
        if (!InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)) return;
        if (_entity.ChargeRelease is { } effect)
            ReleaseCharge(_motionAxis, duration, (float)effect.DamageMultiplier, (float)effect.KnockbackMultiplier,
                (float)effect.SpeedMultiplier, effect.LaunchSpeed);
        else {
            // Accumulation without an effect still exposes the one release event,
            // but must not implicitly zero velocity or reapply combat statistics.
            _released = true; _releaseAge = _age;
            RunRuntimeEvent(RuntimeEventKind.OnRelease, null, 0);
            EmitAndSyncVfxEvent(RuntimeEventKind.OnRelease, Projectile.Center);
            if (_chargeTicks >= duration) {
                RunRuntimeEvent(RuntimeEventKind.ChannelComplete, null, 0);
                EmitAndSyncVfxEvent(RuntimeEventKind.ChannelComplete, Projectile.Center);
            }
            Projectile.netUpdate = true;
        }
    }
    private double BeamWarmupProgress()
    {
        int ticks = _entity?.BeamRamp?.WarmupTicks ?? _entity!.Controller.Params.WarmupTicks;
        int duration = AuthoredTicksToProjectileUpdates(ticks);
        return duration <= 0 ? 1d : Math.Clamp((double)_age / duration, 0d, 1d);
    }
    private double BeamDamageStart => _entity?.BeamRamp?.DamageStartProgress
        ?? (_entity?.BeamGeometry is not null ? 0d : _entity!.Controller.Params.DamageStartProgress ?? 1d);
    private double BeamInitialDamage => _entity?.BeamRamp?.InitialDamageMultiplier
        ?? (_entity?.BeamGeometry is not null ? 1d : _entity!.Controller.Params.InitialDamageMultiplier ?? 1d);
    private void ResetComposableState()
    {
        _releaseAge = -1; _returnAge = -1; _motionAxis = _initialDirection;
        _motionExpiryObserved = false; _pendingMotionExpiry = null;
        _publishedMotionCursor = null; _motionCursorSyncAge = -1000;
        if (HasComposableMotion) {
            _age = 0; _chargeTicks = 0; _controllerTimer = 0;
            _released = false; _returning = false;
            _spawnEventRan = false; _expireEventRan = false; _lastTarget = -1;
            _whipPoints.Clear();
        }
    }
}
