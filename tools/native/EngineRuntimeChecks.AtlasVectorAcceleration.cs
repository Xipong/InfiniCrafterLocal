#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
internal static partial class EngineRuntimeChecks
{
 private static void AtlasVectorAcceleration()
 {
        foreach (int updates in new[] {1, 3, 6}) {
            var spec = Entity(); spec.Kind = "free_projectile"; spec.Collision.ExtraUpdates = updates - 1;
            spec.VectorAcceleration = new() { AccelerationX = .3f / updates / updates, AccelerationY = -.1f / updates / updates, StartDelayTicks = 2, DurationTicks = 4 };
            var projectile = new Projectile { active = true, owner = 0, velocity = Vector2.Zero };
            var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
            for (int age = 1; age <= 8 * updates; age++) { ModifierAge(generated, age); InvokeModifier(generated, "ApplyActiveModifiers"); }
            ModifierNear(1.2f, projectile.velocity.X * updates, "world-time X impulse");
            ModifierNear(-.4f, projectile.velocity.Y * updates, "world-time Y impulse");
            ModifierAge(generated, 7 * updates); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Vector2 before = projectile.velocity; InvokeModifier(generated, "ApplyActiveModifiers");
            Equal(before, projectile.velocity, "hydration cannot restart elapsed acceleration");
        }
 }
}
