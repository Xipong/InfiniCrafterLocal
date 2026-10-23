#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Content.Projectiles;
public sealed partial class GeneratedProjectile
{
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
}
