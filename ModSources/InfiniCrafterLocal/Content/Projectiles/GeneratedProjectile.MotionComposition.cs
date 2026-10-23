#nullable enable
using System;
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
}
