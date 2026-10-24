#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private void ApplyVectorAcceleration()
    {
        if (_entity?.VectorAcceleration is not { } spec || !ModifierPhaseActive(spec.StartDelayTicks, spec.DurationTicks)) return;
        Projectile.velocity += new Vector2(spec.AccelerationX, spec.AccelerationY);
    }

    private void ApplySpeedRamp()
    {
        if (_entity?.SpeedRamp is not { } spec || !ModifierPhaseActive(spec.StartDelayTicks, spec.DurationTicks)) return;
        float speed = Projectile.velocity.Length();
        if (speed <= 0f) return;
        double tick = _age / (double)(Projectile.extraUpdates + 1);
        float t = (float)Math.Clamp((tick - spec.StartDelayTicks) / spec.DurationTicks, 0d, 1d);
        Projectile.velocity *= (spec.StartSpeed + (spec.EndSpeed - spec.StartSpeed) * t) / speed;
    }

    private void MoveSpringTether(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        Vector2 delta = owner.MountedCenter - Projectile.Center;
        float distance = delta.Length();
        float stretch = Math.Max(0f, distance - p.SpringRestRadius!.Value * 16f);
        if (distance > 0f) Projectile.velocity += delta * (stretch / distance * p.SpringStiffness!.Value);
        Projectile.velocity *= MathF.Exp(-p.SpringDamping!.Value);
        float speed = Projectile.velocity.Length();
        if (speed > p.SpringMaxSpeed!.Value) Projectile.velocity *= p.SpringMaxSpeed.Value / speed;
    }

    private void MoveEllipticOrbit(RuntimeParamsSpec p)
    {
        Player owner = Owner();
        if (!OwnerCanControl(owner)) { Projectile.Kill(); return; }
        double phase = p.EllipsePhase!.Value + (double)_age * p.EllipseAngularRate!.Value;
        Vector2 axis = _initialDirection;
        Vector2 perpendicular = new(-axis.Y, axis.X);
        Vector2 target = owner.MountedCenter + axis * (float)(Math.Cos(phase) * p.EllipseRadiusAlong!.Value * 16f)
            + perpendicular * (float)(Math.Sin(phase) * p.EllipseRadiusAcross!.Value * 16f);
        Projectile.velocity = target - Projectile.Center;
        Projectile.tileCollide = false;
    }

    private void MoveTravelingWave(RuntimeParamsSpec p)
    {
        double end = p.WaveStartPhase!.Value + (double)_age * p.WavePhaseRate!.Value;
        double start = end - p.WavePhaseRate.Value;
        float lateralStep = (float)((Math.Sin(end) - Math.Sin(start)) * p.WaveDisplacementAmplitude!.Value * 16f);
        Vector2 axis = _initialDirection;
        Projectile.velocity = axis * p.WaveForwardSpeed!.Value + new Vector2(-axis.Y, axis.X) * lateralStep;
    }
}
