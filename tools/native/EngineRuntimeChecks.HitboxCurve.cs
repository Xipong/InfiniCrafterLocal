using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static RuntimeHitboxCurveSpec HitboxCurve(string curve = "exponential", bool mirror = false)
        => new() { StartScale = 1f, EndScale = 4f, StartDelayTicks = 5,
                   DurationTicks = 60, Curve = curve, MirrorToSprite = mirror };

    private static void HitboxCurveActualDamageRectAndWorldTickClock()
    {
        foreach (int updates in new[] { 1, 3, 6 })
        {
            var entity = Entity(); entity.Kind = "free_projectile";
            entity.Hitbox.WidthPx = 16; entity.Hitbox.HeightPx = 12;
            entity.Hitbox.HitboxScale = 1.5f; entity.Collision.ExtraUpdates = updates - 1;
            entity.HitboxCurve = HitboxCurve();
            var projectile = new Projectile { damage = 100, Center = new Vector2(500f, 600f) };
            var generated = Attach(projectile);
            generated.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX);
            var age = typeof(GeneratedProjectile).GetField("_age", BindingFlags.Instance | BindingFlags.NonPublic)!;
            foreach ((int tick, int expectedWidth, int expectedHeight) in new[] { (0, 24, 18), (5, 24, 18), (35, 48, 36), (65, 96, 72), (100, 96, 72) })
            {
                age.SetValue(generated, tick * updates);
                projectile.scale = 100f; // No visual value is a gameplay source.
                Rectangle hitbox = projectile.Hitbox;
                Point center = hitbox.Center;
                generated.ModifyDamageHitbox(ref hitbox);
                Equal(expectedWidth, hitbox.Width, "curve damage rectangle width");
                Equal(expectedHeight, hitbox.Height, "curve damage rectangle height");
                Equal(center, hitbox.Center, "curve retains native rectangle center");
            }
            entity.HitboxCurve.Curve = "linear";
            age.SetValue(generated, 35 * updates);
            Rectangle linear = projectile.Hitbox;
            generated.ModifyDamageHitbox(ref linear);
            Equal(60, linear.Width, "linear midpoint differs from exponential midpoint");
            entity.HitboxCurve.StartScale = 4f; entity.HitboxCurve.EndScale = 1f;
            Equal(1f, entity.HitboxCurve.ScaleAt(65 * updates, updates), "bounded shrinking curve endpoint");
        }
    }

    private static void HitboxCurveExplicitVisualMirrorAndLateHydration()
    {
        var entity = Entity(); entity.Kind = "free_projectile";
        entity.Collision.ExtraUpdates = 2; entity.Hitbox.DrawScale = 2f; entity.Visual.Scale = 3f;
        entity.HitboxCurve = HitboxCurve(mirror: true);
        var projectile = new Projectile { damage = 100 };
        var generated = Attach(projectile);
        var data = new GeneratedItemData();
        generated.Configure(data, entity, 0, 8, Vector2.UnitX);
        Equal(6f, projectile.scale, "explicit mirror initial scale");
        typeof(GeneratedProjectile).GetField("_age", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(generated, 35 * 3);
        generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
        Equal(12f, projectile.scale, "late hydration uses synced active age and authored extraUpdates");
        var apply = typeof(GeneratedProjectile).GetMethod("ApplyHitboxCurveVisual", BindingFlags.Instance | BindingFlags.NonPublic)!;
        entity.HitboxCurve.MirrorToSprite = false; projectile.scale = 7f;
        apply.Invoke(generated, null);
        Equal(7f, projectile.scale, "no mirror leaves independent visual growth unchanged");
    }

}
