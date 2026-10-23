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
}
