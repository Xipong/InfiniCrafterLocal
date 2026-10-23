#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Content.Projectiles;
public sealed partial class GeneratedProjectile
{
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
}
