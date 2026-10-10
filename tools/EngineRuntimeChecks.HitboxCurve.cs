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

    private static void HitboxCurveExplicitMirrorReachesSpriteVertices()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, _) =>
        {
            const BindingFlags hidden = BindingFlags.Instance | BindingFlags.NonPublic;
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 64);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 16);
            var cacheProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? oldCache = cacheProperty.GetValue(null);
            var cache = new RuntimeSpriteCache();
            var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", hidden)!.GetValue(cache)!;
            var record = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = System.IO.Path.Combine(Terraria.Program.SavePath, "hitbox_curve_body_cpu.png");
            textures.Add(path, Activator.CreateInstance(record, texture, 0f, 0L)!);
            try
            {
                cacheProperty.SetValue(null, cache);
                foreach (string mode in new[] { "baked_sprite", "reuse_item_icon" })
                foreach (bool declaredFrame in new[] { false, true })
                foreach (string policy in new[] { "absent", "independent", "mirror" })
                foreach ((float drawScale, float visualScale, float curveScale, float product) in new[] {
                    (.25f, .25f, .25f, .015625f), (2f, 3f, 2f, 12f), (4f, 4f, 8f, 128f),
                })
                {
                    var data = new GeneratedItemData(); data.Visual.SpritePath = path;
                    var entity = Entity(); entity.Kind = RuntimeEntityKind.FreeProjectile;
                    entity.Visual.AssetMode = mode; entity.Visual.SpritePath = path;
                    entity.Hitbox.DrawScale = drawScale; entity.Visual.Scale = visualScale;
                    if (declaredFrame) { data.Visual.RenderSizePx = 32; entity.Visual.RenderSizePx = 32; }
                    if (policy != "absent") entity.HitboxCurve = new() {
                        StartScale = curveScale, EndScale = curveScale, StartDelayTicks = 0,
                        DurationTicks = 60, Curve = "linear", MirrorToSprite = policy == "mirror",
                    };
                    var projectile = new Projectile { active = true, damage = 100, Center = new Vector2(100, 120), rotation = .35f };
                    var generated = Attach(projectile); generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                    if (policy == "mirror") Equal(product, projectile.scale, "real mirror computes the authored product before drawing");
                    else projectile.scale = product; // Independent legacy live visual state retains its own clamp.
                    string frozen = System.Text.Json.JsonSerializer.Serialize(entity);
                    Rectangle collision = projectile.Hitbox;
                    int index = count(); DrawBodyGeometry(generated);
                    Equal(index + 1, count(), "actual PNG consumer queues one body");
                    Vector3[] points = positions(index);
                    Vector2 edge = new(points[1].X - points[0].X, points[1].Y - points[0].Y);
                    float expectedScale = policy == "mirror" ? product : Math.Clamp(product, .1f, 8f);
                    float expectedWidth = (declaredFrame ? 32f : 64f) * expectedScale;
                    Equal(true, float.IsFinite(edge.Length()) && Math.Abs(edge.Length() - expectedWidth) < .001f + expectedWidth * .000001f,
                        "PNG vertices preserve exact mirror product and frame units: " + mode + "/" + policy);
                    Equal(collision, projectile.Hitbox, "draw never changes native collision rectangle");
                    Equal(frozen, System.Text.Json.JsonSerializer.Serialize(entity), "draw never rewrites authored curve");
                    entity.Visual.AssetMode = "no_asset"; DrawBodyGeometry(generated);
                    Equal(index + 1, count(), "mirror does not invent a visual for explicit no_asset");
                }
            }
            finally { cacheProperty.SetValue(null, oldCache); }
        });
    }

    private static void HitboxCurveExplicitMirrorReachesPrimitiveVertices()
    {
        WithBodyGeometryQueue((count, positions) =>
        {
            foreach (Vector2 aim in new[] { Vector2.UnitX, Vector2.UnitY, new Vector2(-.6f, .8f) })
            foreach (string policy in new[] { "absent", "independent", "mirror" })
            foreach ((float drawScale, float visualScale, float curveScale, float product) in new[] {
                (.25f, .25f, .25f, .015625f), (2f, 3f, 2f, 12f), (4f, 4f, 8f, 128f),
            })
            {
                var entity = Entity(); entity.Kind = RuntimeEntityKind.FreeProjectile;
                entity.Visual.AssetMode = "runtime_geometry"; entity.Hitbox.WidthPx = 4; entity.Hitbox.HeightPx = 4;
                entity.Hitbox.DrawScale = drawScale; entity.Visual.Scale = visualScale;
                if (policy != "absent") entity.HitboxCurve = new() {
                    StartScale = curveScale, EndScale = curveScale, StartDelayTicks = 0,
                    DurationTicks = 60, Curve = "linear", MirrorToSprite = policy == "mirror",
                };
                var projectile = new Projectile { active = true, damage = 100, Center = new Vector2(100, 120), velocity = aim };
                var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), entity, 0, 8, aim);
                if (policy != "mirror") projectile.scale = product;
                float length = policy == "mirror" ? 4f * product : Math.Max(8f, 4f * product);
                float width = policy == "mirror" ? 1.4f * product : Math.Max(2f, 1.4f * product);
                int index = count(); DrawBodyGeometry(generated);
                Equal(index + 1, count(), "even the .0625px authored segment reaches native vertices");
                AssertBodySegment(positions(index), projectile.Center - aim * length * .5f, projectile.Center + aim * length * .5f, width);
            }
            var pixel = Terraria.GameContent.TextureAssets.MagicPixel.Value;
            int before = count();
            foreach (float invalid in new[] { 0f, -1f, float.NaN, float.PositiveInfinity })
                InfiniVfxRuntime.DrawLine(pixel, Vector2.Zero, Vector2.One, Color.White, invalid, preserveWidth: true);
            InfiniVfxRuntime.DrawLine(pixel, Vector2.One, Vector2.One, Color.White, .1f, preserveWidth: true);
            InfiniVfxRuntime.DrawLine(pixel, Vector2.Zero, new Vector2(float.NaN, 1f), Color.White, .1f, preserveWidth: true);
            Equal(before, count(), "exact line path refuses degenerate or nonfinite input");
        });
    }

    private static void HitboxCurveDtoPresenceAndDriverBoundaries()
    {
        var source = RootSpawnFixture(8, 1);
        var raw = JsonNode.Parse(source.ToJson())!.AsObject();
        JsonObject curve = JsonNode.Parse("{\"startScale\":1,\"endScale\":4,\"startDelayTicks\":5,\"durationTicks\":60,\"curve\":\"exponential\",\"mirrorToSprite\":false}")!.AsObject();
        raw["runtimeProgram"]!["entities"]![1]!["hitboxCurve"] = curve;
        var parsed = GeneratedItemData.FromJson(raw.ToJsonString()) ?? throw new InvalidOperationException("valid hitbox curve rejected");
        Equal(4f, parsed.RuntimeProgram.Entities[1].HitboxCurve!.EndScale, "DTO preserves explicit scale");
        Equal(true, GeneratedItemData.FromJson(parsed.ToNetworkJson()) is not null, "network DTO roundtrip");
        foreach (string name in curve.Select(pair => pair.Key).ToArray())
        {
            JsonNode? saved = curve[name]?.DeepClone();
            curve.Remove(name);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "present curve requires " + name);
            curve[name] = saved;
        }
        foreach (string invalid in new[] { "null", "true", "\"1\"", "0", "9" })
        {
            curve["startScale"] = JsonNode.Parse(invalid);
            Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "invalid curve scalar " + invalid);
        }
        curve["startScale"] = 1;
        curve["unknown"] = 1;
        Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "unknown curve field rejected");
        curve.Remove("unknown");
        raw["runtimeProgram"]!["entities"]![1]!["hitboxCurve"] = null;
        Equal(true, GeneratedItemData.FromJson(raw.ToJsonString()) is null, "present null curve rejected");
        raw["runtimeProgram"]!["entities"]![1]!.AsObject().Remove("hitboxCurve");
        var legacy = GeneratedItemData.FromJson(raw.ToJsonString()) ?? throw new InvalidOperationException("legacy curve absence rejected");
        Equal(false, legacy.ToJson().Contains("hitboxCurve", StringComparison.Ordinal), "saved absence does not materialize curve");
    }
}
