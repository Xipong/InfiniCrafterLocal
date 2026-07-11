#nullable enable
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using System;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    /// <summary>
    /// Finite overhead-barrage executor: one target marker, one telegraph timer and
    /// one bounded spawn from above. Theme is owned by the authored child spec.
    /// Do not turn this into a generic trigger/state engine.
    /// </summary>
    private bool ApplyOverheadBarrageAI()
    {
        Projectile.velocity = Vector2.Zero;
        Projectile.tileCollide = false;
        Projectile.friendly = false;
        Projectile.rotation += 0.025f;

        int delayTicks = Math.Clamp(_spec.DelayTicks, 0, 300);
        if (Projectile.localAI[0] <= delayTicks)
        {
            Projectile.timeLeft = Math.Max(2, delayTicks - (int)Projectile.localAI[0] + 20);
            return true;
        }

        if (InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile))
        {
            int count = Math.Clamp(_spec.ShotCount, 1, Math.Max(1, _spec.MaxChildProjectiles));
            SpawnOverheadBarrage(
                Projectile.Center,
                count,
                _spec.SecondaryDamageMultiplier <= 0f ? 0.55f : _spec.SecondaryDamageMultiplier);
        }
        Projectile.Kill();
        return false;
    }
}
