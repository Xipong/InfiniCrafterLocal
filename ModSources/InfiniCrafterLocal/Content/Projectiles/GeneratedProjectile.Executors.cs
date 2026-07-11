#nullable enable
using Microsoft.Xna.Framework;
using System;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private readonly struct ProjectileRuntimeContext
    {
        public readonly int MovementCode;
        public readonly bool IsStuckToTile;
        public ProjectileRuntimeContext(int movementCode, bool isStuckToTile)
        {
            MovementCode = movementCode;
            IsStuckToTile = isStuckToTile;
        }
    }

    private interface IGeneratedProjectileRuntimeExecutor
    {
        bool CanRun(ProjectileRuntimeContext context);
        bool OwnsRotation(ProjectileRuntimeContext context);
        void Tick(GeneratedProjectile projectile, ProjectileRuntimeContext context);
    }

    private sealed class StraightShotExecutor : IGeneratedProjectileRuntimeExecutor
    {
        public bool CanRun(ProjectileRuntimeContext context) => context.MovementCode == 0;
        public bool OwnsRotation(ProjectileRuntimeContext context) => false;
        public void Tick(GeneratedProjectile projectile, ProjectileRuntimeContext context) { }
    }

    private sealed class BasicMovementExecutor : IGeneratedProjectileRuntimeExecutor
    {
        public bool CanRun(ProjectileRuntimeContext context) => context.MovementCode is >= 1 and <= 15;
        public bool OwnsRotation(ProjectileRuntimeContext context) => context.MovementCode is 5 or 14;
        public void Tick(GeneratedProjectile p, ProjectileRuntimeContext context)
        {
            switch (context.MovementCode)
            {
                case 1: p.SlowHoming(p.ConfiguredHomingStrength(0.035f), p.ConfiguredRangePixels(420f)); break;
                case 2: p.Projectile.velocity.Y += 0.12f; break;
                case 3: p.Projectile.velocity *= 0.985f; break;
                case 4: p.Orbitish(); break;
                case 5: p.Projectile.rotation += 0.26f * Math.Sign(p.Projectile.direction == 0 ? 1 : p.Projectile.direction); p.BoomerangReturn(); break;
                case 6: p.Projectile.velocity.Y += 0.07f; break;
                case 7: p.SineHoming(); break;
                case 8: p.PhaseDrift(); break;
                case 9: p.Accelerate(); break;
                case 10: p.SpiralOut(); break;
                case 11: p.VortexOrb(); break;
                case 12: p.BlackholePull(); break;
                case 13: p.ProximityMissile(); break;
                case 14: p.ReturningGlaive(); break;
                case 15: p.ExpandingWave(); break;
            }
        }
    }

    private sealed class FlailExecutor : IGeneratedProjectileRuntimeExecutor
    {
        public bool CanRun(ProjectileRuntimeContext context) => context.MovementCode == 16;
        public bool OwnsRotation(ProjectileRuntimeContext context) => true;
        public void Tick(GeneratedProjectile projectile, ProjectileRuntimeContext context) => projectile.ApplyFlailTetherAI();
    }

    private sealed class YoyoExecutor : IGeneratedProjectileRuntimeExecutor
    {
        public bool CanRun(ProjectileRuntimeContext context) => context.MovementCode == 17;
        public bool OwnsRotation(ProjectileRuntimeContext context) => true;
        public void Tick(GeneratedProjectile projectile, ProjectileRuntimeContext context) => projectile.ApplyYoyoHoverAI();
    }

    private sealed class WhipExecutor : IGeneratedProjectileRuntimeExecutor
    {
        public bool CanRun(ProjectileRuntimeContext context) => context.MovementCode == 18;
        public bool OwnsRotation(ProjectileRuntimeContext context) => true;
        public void Tick(GeneratedProjectile projectile, ProjectileRuntimeContext context) => projectile.ApplyWhipLashAI();
    }
    private static readonly IGeneratedProjectileRuntimeExecutor[] MovementExecutors =
    {
        new StraightShotExecutor(),
        new BasicMovementExecutor(),
        new FlailExecutor(),
        new YoyoExecutor(),
        new WhipExecutor(),
    };

    private bool RunMovementExecutor(int movementCode)
    {
        var context = new ProjectileRuntimeContext(movementCode, _stuckToTile);
        for (int i = 0; i < MovementExecutors.Length; i++)
        {
            if (!MovementExecutors[i].CanRun(context))
                continue;
            MovementExecutors[i].Tick(this, context);
            return MovementExecutors[i].OwnsRotation(context);
        }
        return false;
    }
}
