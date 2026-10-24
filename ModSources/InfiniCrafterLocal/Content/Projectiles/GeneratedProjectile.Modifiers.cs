#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private bool ModifierPhaseActive(int delayTicks, int durationTicks)
        => RuntimeModifierClock.Active(_age, Projectile.extraUpdates + 1, delayTicks, durationTicks);

    private void ApplyActiveModifiers()
    {
        if (!Projectile.active || _entity is null) return;
        if (_entity.TurnModifier is { } turn && ModifierPhaseActive(turn.StartDelayTicks, turn.DurationTicks) && MotionWindowActive(turn.Window))
            RotateVelocity(turn.TurnRadiansPerUpdate);
        if (_entity.SpeedModifier is { } speed && ModifierPhaseActive(speed.StartDelayTicks, speed.DurationTicks) && MotionWindowActive(speed.Window))
        {
            MultiplyVelocityCapped(speed.SpeedMultiplierPerUpdate, speed.MaxSpeed, onlyBelowCap: false, legacyNormalize: false);
        }
        ApplyHomingModifier();
    }

    private void ApplyHomingModifier()
    {
        if (_entity?.HomingModifier is not { } homing
            || !ModifierPhaseActive(homing.StartDelayTicks, homing.DurationTicks) || !MotionWindowActive(homing.Window)
            || !InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)) return;
        float speed = Projectile.velocity.Length();
        if (speed <= 0f || !float.IsFinite(speed)) return;
        NPC? target = ResolveMotionNpc(homing.RangeTiles * 16f, homing.RequireLineOfSight);
        float bestDistanceSquared = target is null ? 0f : Vector2.DistanceSquared(Projectile.Center, target.Center);
        if (target is null || bestDistanceSquared <= 0f) return;
        float angle = MathHelper.WrapAngle((target.Center - Projectile.Center).ToRotation() - Projectile.velocity.ToRotation());
        float turn = Math.Clamp(angle, -homing.MaxTurnRadiansPerUpdate, homing.MaxTurnRadiansPerUpdate);
        RotateVelocity(turn);
        if (turn != 0f) Projectile.netUpdate = true;
    }

    private void ApplyNpcAttraction()
    {
        if (!Projectile.active || _entity?.NpcAttraction is not { } pull
            || !ModifierPhaseActive(pull.StartDelayTicks, pull.DurationTicks) || !MotionWindowActive(pull.Window)
            || !InfiniRuntimeAuthority.ShouldRunNpcGameplay()) return;
        ApplyNpcImpulseKernel(Projectile.Center, pull.RangeTiles * 16f, pull.StrengthPerUpdate, pull.Falloff,
            pull.MaxTargets, synchronize: true, legacyDirection: false, chaseSource: Projectile);
    }

    private void ApplyVisualScaleCurve()
    {
        if (_entity?.VisualScaleCurve is { } curve && MotionWindowActive(curve.Window))
            Projectile.scale = _entity.Hitbox.DrawScale * _entity.Visual.Scale * curve.ScaleAt(_age, Projectile.extraUpdates + 1);
    }
}
