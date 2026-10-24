#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks { private static void StationTargetPrediction() {
        TargetingDtoContract("{\"aimMode\":\"velocity_lead\",\"leadSeconds\":0.5,\"maximumLeadTiles\":4}", new[] { "{\"aimMode\":null}", "{\"aimMode\":\"guess\"}", "{\"leadSeconds\":2.1}", "{\"maximumLeadTiles\":-1}" }, "aimMode", "leadSeconds", "maximumLeadTiles");
using var state = new SentryTargetScope();
        var projectile = new Projectile { owner = 0, active = true, Center = new Vector2(1600, 1600) };
        var generated = Attach(projectile); var target = state.Target(0, 60); target.velocity = new Vector2(0, 2);
        var spec = new RuntimeTargetingSpec { AimMode = "velocity_lead", LeadSeconds = .5, MaximumLeadTiles = 10 };
        var direction = generated.FiringDirection(target, spec);
        Equal(true, Math.Abs(direction.X - direction.Y) < .0001f, "half-second world prediction aims at actual future centre");
        spec.MaximumLeadTiles = 1;
        direction = generated.FiringDirection(target, spec);
        Equal(true, Math.Abs(direction.Y / direction.X - 16f / 60f) < .0001f, "bounded lead preserves predicted direction");
        projectile.extraUpdates = 5;
        Equal(direction, generated.FiringDirection(target, spec), "prediction horizon is world time not update count");
        spec.AimMode = "direct";
        Equal(Vector2.UnitX, generated.FiringDirection(target, spec), "explicit direct mode ignores lead parameters");
        Equal(new Vector2(0, 2), target.velocity, "prediction never mutates target velocity");
} }
