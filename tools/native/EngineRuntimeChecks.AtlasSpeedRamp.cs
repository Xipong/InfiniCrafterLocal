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
 private static void AtlasSpeedRamp()
 {
        foreach (int updates in new[] {1, 3, 6}) {
            var spec = Entity(); spec.Kind = "free_projectile"; spec.Collision.ExtraUpdates = updates - 1;
            spec.SpeedRamp = new() { StartSpeed = 12f / updates, EndSpeed = 3f / updates, StartDelayTicks = 2, DurationTicks = 4 };
            var projectile = new Projectile { active = true, owner = 0, velocity = new Vector2(3, 4) };
            var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
            ModifierAge(generated, 4 * updates); InvokeModifier(generated, "ApplyActiveModifiers");
            ModifierNear(7.5f, projectile.velocity.Length() * updates, "absolute halfway speed");
            ModifierNear(.75f, projectile.velocity.X / projectile.velocity.Y, "heading retained");
            projectile.velocity *= 20; InvokeModifier(generated, "ApplyActiveModifiers");
            ModifierNear(7.5f, projectile.velocity.Length() * updates, "history-independent speed envelope");
            ModifierAge(generated, 6 * updates); InvokeModifier(generated, "ApplyActiveModifiers");
            ModifierNear(3f, projectile.velocity.Length() * updates, "exact phase endpoint");
            projectile.velocity = Vector2.Zero; InvokeModifier(generated, "ApplyActiveModifiers");
            Equal(Vector2.Zero, projectile.velocity, "stalled projectile remains stalled");
        }
 }
}
