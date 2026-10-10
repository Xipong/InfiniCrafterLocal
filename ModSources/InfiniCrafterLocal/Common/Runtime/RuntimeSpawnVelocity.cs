#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria.Utilities;

namespace InfiniCrafterLocal.Common.Runtime;

// A bounded per-batch sampler owned by the firing peer. Its output becomes
// native position/velocity state; Configure/hydration never samples it again.
internal static class RuntimeSpawnVelocity
{
    internal static bool TrySample(RuntimeSpawnSpec spawn, Vector2 axis, UnifiedRandom? random, out Vector2 velocity)
    {
        velocity = Vector2.Zero;
        if (spawn.VelocityDistribution is not { } distribution)
        {
            velocity = axis * spawn.SpeedPxPerTick;
            return float.IsFinite(velocity.X) && float.IsFinite(velocity.Y);
        }
        if (!distribution.IsValid || random is null || spawn.SpeedPxPerTick != 0f)
            return false;
        float maximum = distribution.MaxSpeedPxPerUpdate!.Value;
        if (distribution.Kind is "radial" or "disk")
        {
            if (spawn.SpreadRadians != 0f) return false;
            double angle = random.NextDouble() * Math.Tau;
            float magnitude = distribution.Kind == "disk"
                ? maximum * MathF.Sqrt((float)random.NextDouble())
                : MathHelper.Lerp(distribution.MinSpeedPxPerUpdate!.Value, maximum, (float)random.NextDouble());
            velocity = new Vector2((float)Math.Cos(angle), (float)Math.Sin(angle)) * magnitude;
        }
        else
        {
            if (!float.IsFinite(axis.X) || !float.IsFinite(axis.Y) || axis.LengthSquared() <= 0f)
                return false;
            float magnitude = MathHelper.Lerp(distribution.MinSpeedPxPerUpdate!.Value, maximum, (float)random.NextDouble());
            if (distribution.Kind == "cone")
            {
                double angle = (random.NextDouble() * 2d - 1d) * distribution.HalfAngleRadians!.Value;
                float cosine = (float)Math.Cos(angle), sine = (float)Math.Sin(angle);
                axis = new Vector2(axis.X * cosine - axis.Y * sine, axis.X * sine + axis.Y * cosine);
            }
            velocity = axis * magnitude;
        }
        return float.IsFinite(velocity.X) && float.IsFinite(velocity.Y);
    }
}
