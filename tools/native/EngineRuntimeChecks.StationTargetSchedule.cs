#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks { private static void StationTargetSchedule() {
        TargetingDtoContract("{\"warmupTicks\":30,\"burstCount\":3,\"burstSpacingTicks\":6}", new[] { "{\"warmupTicks\":null}", "{\"warmupTicks\":1801}", "{\"burstCount\":9}", "{\"burstSpacingTicks\":0}" }, "warmupTicks", "burstCount", "burstSpacingTicks");
var spec = new RuntimeTargetingSpec { IntervalTicks = 10, WarmupTicks = 5, BurstCount = 3, BurstSpacingTicks = 2 };
        foreach (int updates in new[] { 1, 3, 6 }) {
            int timer = 0; var observed = new System.Collections.Generic.List<int>();
            for (int step = 1; step <= 33 * updates; step++)
                if (GeneratedProjectile.AdvanceFiringSchedule(ref timer, spec, updates)) observed.Add(step);
            Equal(true, observed.SequenceEqual(new[] { 15, 17, 19, 29, 31, 33 }.Select(t => t * updates)), "world-time warmup burst and cooldown at update rate " + updates);
        }
        int oldTimer = 0; var neutral = new RuntimeTargetingSpec { IntervalTicks = 6 };
        for (int tick = 1; tick <= 18; tick++) Equal(tick % 6 == 0, GeneratedProjectile.AdvanceFiringSchedule(ref oldTimer, neutral, 1), "omitted schedule keeps old cadence");
        int original = 16, hydrated = original;
        Equal(GeneratedProjectile.AdvanceFiringSchedule(ref original, spec, 1), GeneratedProjectile.AdvanceFiringSchedule(ref hydrated, spec, 1), "serialized timer resumes same burst phase");
} }
