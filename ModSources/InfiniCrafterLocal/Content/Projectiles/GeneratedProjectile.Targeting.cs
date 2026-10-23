#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Content.Projectiles;
public sealed partial class GeneratedProjectile
{
    internal bool AdmitsTargetFilter(NPC npc, RuntimeTargetingSpec targeting, Player owner)
    {
        if (targeting.BossFilter == "boss_only" && !npc.boss || targeting.BossFilter == "non_boss_only" && npc.boss) return false;
        double minimum = targeting.MinimumHealthRatio ?? 0d, maximum = targeting.MaximumHealthRatio ?? 1d;
        if (minimum > 0d || maximum < 1d)
        {
            if (npc.lifeMax <= 0) return false;
            double health = (double)npc.life / npc.lifeMax;
            if (health < minimum || health > maximum) return false;
        }
        Vector2 offset = npc.Center - Projectile.Center;
        if (offset.LengthSquared() < Math.Pow((targeting.MinimumRangeTiles ?? 0d) * 16d, 2d)) return false;
        double cone = targeting.ConeRadians ?? Math.PI * 2d;
        if (cone >= Math.PI * 2d || offset.LengthSquared() == 0f) return true;
        Vector2 axis = targeting.ConeDirection == "projectile_velocity" ? Projectile.velocity : new Vector2(owner.direction, 0f);
        if (axis.LengthSquared() == 0f) return false;
        return Vector2.Dot(Vector2.Normalize(axis), Vector2.Normalize(offset)) >= Math.Cos(cone * .5d) - 1e-7d;
    }
}
