#nullable enable
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using System;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

/// <summary>
/// Exact mechanics owner for projectiles delivered from above a target area.
/// It configures descent geometry only. Projectile theme (arrow, shard, meteor,
/// star, spear, etc.), effect, sprite and VFX remain authored in AttackSpec.
/// </summary>
internal static class GeneratedOverheadBarragePolicy
{
    public static void ConfigureChild(AttackSpec child, AttackSpec parent)
    {
        child.Movement = "gravity_arc";
        child.MovementCode = 2;
        child.OnHit = "none";
        child.OnHitCode = 0;
        child.TileCollide = parent.TileCollide;
        child.Speed = Math.Clamp(parent.Speed > 0f ? parent.Speed : 11f, 4f, 20f);
        child.Lifetime = parent.SecondaryLifetimeTicks > 0
            ? parent.SecondaryLifetimeTicks
            : Math.Min(120, Math.Max(45, parent.Lifetime / 2));

        child.ProjectileFamily = string.IsNullOrWhiteSpace(parent.ProjectileFamily)
            ? "projectile"
            : parent.ProjectileFamily.Trim();
        child.ProjectileShape = !string.IsNullOrWhiteSpace(parent.SecondaryProjectileShape)
            ? parent.SecondaryProjectileShape.Trim()
            : string.IsNullOrWhiteSpace(parent.ProjectileShape) ? "projectile" : parent.ProjectileShape.Trim();
        child.ProjectileMotion = string.IsNullOrWhiteSpace(parent.ProjectileMotion)
            || string.Equals(parent.ProjectileMotion.Trim(), "phase", StringComparison.OrdinalIgnoreCase)
                ? "overhead descent"
                : parent.ProjectileMotion.Trim();
        child.MaxChildProjectiles = 0;
        child.MaxChildDepth = 0;
    }

    public static (Vector2 Origin, Vector2 Velocity) Sample(
        Vector2 targetCenter,
        int index,
        int count,
        float authoredSpreadRadians,
        float speed)
    {
        int safeCount = Math.Max(1, count);
        float t = safeCount <= 1 ? 0f : index / (float)(safeCount - 1) - 0.5f;
        float spread = safeCount <= 1
            ? 0f
            : MathHelper.Clamp(authoredSpreadRadians <= 0f ? 0.44f : authoredSpreadRadians, 0.12f, 1.2f);
        Vector2 origin = targetCenter + new Vector2(
            t * spread * 96f + Main.rand.NextFloat(-18f, 18f),
            -220f - Main.rand.NextFloat(0f, 90f));
        Vector2 aim = targetCenter + Main.rand.NextVector2Circular(36f, 18f);
        Vector2 velocity = (aim - origin).SafeNormalize(Vector2.UnitY) * Math.Clamp(speed, 4f, 20f);
        return (origin, velocity);
    }
}
