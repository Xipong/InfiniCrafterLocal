#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Content.Projectiles;
public sealed partial class GeneratedProjectile
{
    private void MoveTravelingWave(RuntimeParamsSpec p)
    {
        double end = p.WaveStartPhase!.Value + (double)_age * p.WavePhaseRate!.Value;
        double start = end - p.WavePhaseRate.Value;
        float lateralStep = (float)((Math.Sin(end) - Math.Sin(start)) * p.WaveDisplacementAmplitude!.Value * 16f);
        Vector2 axis = _initialDirection;
        Projectile.velocity = axis * p.WaveForwardSpeed!.Value + new Vector2(-axis.Y, axis.X) * lateralStep;
    }
}
