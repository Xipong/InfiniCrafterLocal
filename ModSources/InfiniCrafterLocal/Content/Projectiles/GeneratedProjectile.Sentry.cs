#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using System;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

// Exact sentry vertical slice. The root is stationary and bounded; every shot is
// converted to an ordinary GeneratedProjectile and cannot inherit sentry lifecycle.
public sealed partial class GeneratedProjectile
{
    private bool ApplySentryAI()
    {
        Projectile.friendly = false;
        Projectile.velocity = Vector2.Zero;
        Projectile.tileCollide = false;
        if (Projectile.owner < 0 || Projectile.owner >= Main.maxPlayers)
        {
            Projectile.Kill();
            return false;
        }
        Player owner = Main.player[Projectile.owner];
        if (!owner.active)
        {
            Projectile.Kill();
            return false;
        }

        _sentryFireTimer++;
        int interval = Math.Clamp(_spec.SentryAttackIntervalTicks, 12, 180);
        if (_sentryFireTimer < interval)
            return true;
        NPC? target = FindSentryTarget(owner, Math.Clamp(_spec.SentryTargetRangeTiles, 8f, 60f) * 16f);
        if (target is null)
            return true;
        _sentryFireTimer = 0;
        if (!InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile))
            return true;

        int count = RuntimeChildCount(Math.Clamp(_spec.ShotCount, 1, 4));
        if (count <= 0)
        {
            Projectile.Kill();
            return false;
        }
        float spread = Math.Clamp(_spec.SpreadRadians, 0f, 0.75f);
        Vector2 baseDirection = (target.Center - Projectile.Center).SafeNormalize(Vector2.UnitX);
        AttackSpec shot = SentryShotSpec();
        for (int i = 0; i < count; i++)
        {
            float offset = count == 1 ? 0f : MathHelper.Lerp(-spread * 0.5f, spread * 0.5f, i / (float)(count - 1));
            Vector2 velocity = baseDirection.RotatedBy(offset) * Math.Max(3f, _spec.Speed);
            SpawnChild(Projectile.Center + velocity.SafeNormalize(Vector2.UnitX) * 14f, velocity, Math.Max(1, Projectile.damage), shot, 1f);
        }
        return true;
    }

    private NPC? FindSentryTarget(Player owner, float range)
    {
        NPC? assigned = Projectile.OwnerMinionAttackTargetNPC;
        if (assigned is not null && assigned.CanBeChasedBy(Projectile)
            && Vector2.Distance(Projectile.Center, assigned.Center) <= range
            && Collision.CanHit(Projectile.position, Projectile.width, Projectile.height, assigned.position, assigned.width, assigned.height))
            return assigned;
        NPC? best = null;
        float bestDistance = range;
        foreach (NPC npc in Main.ActiveNPCs)
        {
            if (!npc.CanBeChasedBy(Projectile)) continue;
            float distance = Vector2.Distance(Projectile.Center, npc.Center);
            if (distance >= bestDistance) continue;
            if (!Collision.CanHit(Projectile.position, Projectile.width, Projectile.height, npc.position, npc.width, npc.height)) continue;
            best = npc;
            bestDistance = distance;
        }
        return best;
    }

    private AttackSpec SentryShotSpec()
    {
        AttackSpec shot = _spec.CloneForRuntimeSpawn();
        GeneratedChildSpecPolicy.ConfigureSentryShot(shot, _spec);
        return shot;
    }
}
