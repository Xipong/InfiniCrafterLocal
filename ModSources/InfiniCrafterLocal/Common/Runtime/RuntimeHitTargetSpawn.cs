#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Utilities;

namespace InfiniCrafterLocal.Common.Runtime;

// The source hit chooses the exact NPC. This value freezes its geometry
// before delayed dispatch. A positive exclusion also retains the
// exact incarnation; zero explicitly carries no incarnation cancellation guard.
internal readonly record struct RuntimeHitTargetSpawnSnapshot(
    Vector2 Center, float MaxSidePx, Vector2 Direction,
    RuntimeInitialNpcExclusion Exclusion, int Seed)
{
    internal bool IsValid => new RuntimeSpawnTransform(Center, Direction).IsValid
        && float.IsFinite(MaxSidePx) && MaxSidePx > 0f && Exclusion.IsValid;

    internal static bool TryCapture(RuntimeHitTargetSpawnSpec spec, NPC? target, Vector2 direction,
        out RuntimeHitTargetSpawnSnapshot snapshot)
    {
        snapshot = default;
        if (!spec.IsValid || target is null || target.whoAmI < 0 || target.whoAmI >= Main.maxNPCs
            || !ReferenceEquals(Main.npc[target.whoAmI], target) || target.width <= 0 || target.height <= 0
            || !new RuntimeSpawnTransform(target.Center, direction).IsValid
            || !RuntimeInitialNpcExclusion.TryCapture(target, spec.InitialIgnoreCountdownUpdates!.Value, out var exclusion))
            return false;
        snapshot = new(target.Center, Math.Max(target.width, target.height),
            direction.SafeNormalize(Vector2.Zero), exclusion, 0);
        return snapshot.IsValid;
    }
}

internal static class RuntimeHitTargetSpawn
{
    internal static bool TryPlan(RuntimeHitTargetSpawnSpec spec, RuntimeHitTargetSpawnSnapshot snapshot, int count,
        out RuntimeSpawnTransform[] transforms, out int[] velocitySeeds)
    {
        transforms = Array.Empty<RuntimeSpawnTransform>();
        velocitySeeds = Array.Empty<int>();
        if (!spec.IsValid || !snapshot.IsValid || !snapshot.Exclusion.CanApply || count < 1 || count > 12)
            return false;
        var random = new UnifiedRandom(snapshot.Seed);
        var planned = new RuntimeSpawnTransform[count];
        var seeds = new int[count];
        float radius = snapshot.MaxSidePx * spec.HitboxMaxSideFactor!.Value + spec.ClearancePx!.Value;
        for (int i = 0; i < count; i++)
        {
            Vector2 position, direction;
            // NextDouble is [0,1): explicit 0 and 1 are exact branch endpoints.
            bool before = random.NextDouble() < spec.BeforeProbability!.Value;
            if (before)
            {
                float jitterRadius = spec.BeforePositionJitterRadiusPx!.Value * MathF.Sqrt((float)random.NextDouble());
                double jitterAngle = random.NextDouble() * Math.Tau;
                Vector2 jitter = new((float)Math.Cos(jitterAngle) * jitterRadius, (float)Math.Sin(jitterAngle) * jitterRadius);
                position = snapshot.Center - snapshot.Direction * radius + jitter;
                direction = snapshot.Direction.RotatedBy((random.NextDouble() * 2d - 1d) * spec.BeforeDirectionJitterRadians!.Value);
            }
            else
            {
                double angle = count == 1 ? 0d : (i / (double)(count - 1) - 0.5d) * spec.AfterFanSpreadRadians!.Value;
                direction = snapshot.Direction.RotatedBy(angle);
                position = snapshot.Center + direction * radius;
            }
            planned[i] = new(position, direction);
            if (!planned[i].IsValid) return false;
            // A separate child stream means its selected velocity distribution
            // cannot change a sibling's geometry. Delays retain these seeds.
            seeds[i] = random.Next();
        }
        transforms = planned;
        velocitySeeds = seeds;
        return true;
    }
}
