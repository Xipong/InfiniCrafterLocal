#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks { private static void StationTargetPriority() {
        TargetingDtoContract("{\"targetPriority\":\"lowest_health\",\"targetPolicy\":\"player_assigned_only\"}", new[] { "{\"targetPriority\":null}", "{\"targetPriority\":\"guess\"}", "{\"targetPolicy\":\"assigned\"}" }, "targetPriority", "targetPolicy");
using var state = new SentryTargetScope();
        var projectile = new Projectile { owner = 0, active = true, Center = new Vector2(1600, 1600) };
        var generated = Attach(projectile); var near = state.Target(0, 30); var hurt = state.Target(1, 90); hurt.life = 20;
        var spec = new RuntimeTargetingSpec { HardRange = true, TargetPriority = "lowest_health" };
        var find = typeof(GeneratedProjectile).GetMethod("FindFiringTarget", SentryPrivate)!;
        NPC? Pick() => (NPC?)find.Invoke(generated, new object[] { 160f, spec });
        Equal(true, ReferenceEquals(hurt, Pick()), "execute priority defeats nearest");
        spec.TargetPriority = "highest_health";
        Equal(true, ReferenceEquals(near, Pick()), "healthiest priority");
        spec.TargetPolicy = "player_assigned_only";
        Equal(true, Pick() is null, "no assigned target means hold fire");
        state.Owner.MinionAttackTargetNPC = hurt.whoAmI;
        Equal(true, ReferenceEquals(hurt, Pick()), "exact assignment wins priority");
        spec.MinimumHealthRatio = .5;
        Equal(true, Pick() is null, "assigned-only never bypasses predicate or retargets implicitly");
        spec.TargetPolicy = "distance_score"; spec.TargetPriority = "closest_to_owner"; spec.MinimumHealthRatio = 0;
        state.Owner.Center = hurt.Center;
        Equal(true, ReferenceEquals(hurt, Pick()), "defensive nearest-owner priority");
} }
