#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Content.Projectiles;
public sealed partial class GeneratedProjectile
{
    private Player? _targetingOwnerPlayer;
    private int _targetingOwnerIndex = -1;
    private void CaptureTargetingOwner(bool preserveSyncedState)
    {
        if (preserveSyncedState && _targetingOwnerPlayer is not null) return;
        _targetingOwnerIndex = Projectile.owner;
        _targetingOwnerPlayer = _targetingOwnerIndex >= 0 && _targetingOwnerIndex < Main.maxPlayers ? Main.player[_targetingOwnerIndex] : null;
    }
    internal bool TryGetFiringOwner(out Player owner)
    {
        owner = _targetingOwnerPlayer!;
        return _targetingOwnerIndex >= 0 && _targetingOwnerIndex < Main.maxPlayers
            && Projectile.owner == _targetingOwnerIndex && ReferenceEquals(owner, Main.player[_targetingOwnerIndex])
            && owner is { active: true, dead: false } && owner.whoAmI == _targetingOwnerIndex
            && InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile) && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner);
    }
    internal static bool AdvanceFiringSchedule(ref int timer, RuntimeTargetingSpec targeting, int updatesPerTick)
    {
        int scale = Math.Clamp(updatesPerTick, 1, 6);
        int warmup = (targeting.WarmupTicks ?? 0) * scale;
        int first = warmup + Math.Max(6, targeting.IntervalTicks) * scale;
        int spacing = (targeting.BurstSpacingTicks ?? 6) * scale;
        int count = targeting.BurstCount ?? 1;
        int last = first + (count - 1) * spacing;
        // Bounded phase state uses the already synchronized controller timer.
        // Reset to warmup after the last volley: warmup is paid once, not per burst.
        timer = (int)Math.Min(Math.Max(0, timer) + 1L, last);
        bool due = timer >= first && (timer - first) % spacing == 0;
        if (timer >= last) timer = warmup;
        return due;
    }
    internal Vector2 FiringDirection(NPC target, RuntimeTargetingSpec targeting)
    {
        Vector2 aim = target.Center;
        if (targeting.AimMode == "velocity_lead")
        {
            Vector2 lead = target.velocity * (float)((targeting.LeadSeconds ?? 0d) * 60d);
            float maximum = (float)((targeting.MaximumLeadTiles ?? 120d) * 16d);
            if (lead.LengthSquared() > maximum * maximum) lead = Vector2.Normalize(lead) * maximum;
            aim += lead;
        }
        return Projectile.DirectionTo(aim);
    }
    internal double TargetPriorityScore(NPC npc, RuntimeTargetingSpec targeting, Player owner, float distanceScore)
    {
        if (targeting.TargetPriority is "lowest_health" or "highest_health")
            return npc.lifeMax <= 0 ? double.PositiveInfinity : (double)npc.life / npc.lifeMax * (targeting.TargetPriority == "highest_health" ? -1d : 1d);
        if (targeting.TargetPriority == "closest_to_owner") return Vector2.DistanceSquared(owner.Center, npc.Center);
        if (targeting.TargetPriority == "facing_alignment")
        {
            Vector2 offset = npc.Center - Projectile.Center;
            return offset.LengthSquared() == 0f ? -1d : -Vector2.Dot(Vector2.Normalize(offset), new Vector2(owner.direction, 0));
        }
        return distanceScore;
    }
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
