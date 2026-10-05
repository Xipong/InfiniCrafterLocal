using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    // Installed tML 2026.6.3.6, tag commit 29bf9785f5f4de8cd305be002c4cc48aa1177b20:
    // patches/tModLoader/Terraria/UI/ItemSlot.cs.patch (DrawItemIcon),
    // patches/tModLoader/Terraria/Main.cs.patch (DrawItem).
    // CPU-only real FNA Begin/Draw/End + DrawData controls. No GPU, pixel upload,
    // content registration, full ItemSlot UI, world loop or framebuffer assertion.
    public static void GeneratedItemDrawPreservesEngineGeometryAndTint()
    {
        const BindingFlags hidden = BindingFlags.Instance | BindingFlags.NonPublic;
        var batch = (SpriteBatch)RuntimeHelpers.GetUninitializedObject(typeof(SpriteBatch));
        var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
        GC.SuppressFinalize(batch);
        GC.SuppressFinalize(texture);
        foreach (string name in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" })
        {
            var field = typeof(SpriteBatch).GetField(name, hidden)!;
            field.SetValue(batch, Array.CreateInstance(field.FieldType.GetElementType()!, 16));
        }
        var count = typeof(SpriteBatch).GetField("numSprites", hidden)!;
        var vertices = (Array)typeof(SpriteBatch).GetField("vertexInfo", hidden)!.GetValue(batch)!;
        var cache = new RuntimeSpriteCache();
        var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", hidden)!.GetValue(cache)!;
        var record = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
        var cacheProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
        object? oldCache = cacheProperty.GetValue(null);
        bool oldServer = Terraria.Main.dedServ;
        Vector2 oldScreen = Terraria.Main.screenPosition;
        string path = System.IO.Path.Combine(Terraria.Program.SavePath, "item_draw_cpu.png");
        var generated = new GeneratedItem();
        var item = new Item { type = 1, stack = 1, width = 24, height = 30, position = new Vector2(250, 180), scale = 3f };
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
        // Placeholder identity prevents hydration/network work; only presentation fields vary.
        generated.Data.Visual.SpritePath = path;
        generated.Data.Visual.DrawOffsetX = 3;
        generated.Data.Visual.DrawOffsetY = -5;
        var failures = new List<string>();
        Action<SpriteBatch> flush = self => count.SetValue(self, 0);
        using var hook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", hidden)!, flush);
        void Check(bool valid, string message) { if (!valid) failures.Add(message); }
        void Compare(int actualCount, int expectedCount, string label)
        {
            Check(actualCount == expectedCount, $"{label}: queued {actualCount}, expected {expectedCount}");
            for (int i = 0; i < Math.Min(actualCount, expectedCount); i++)
            {
                object actual = vertices.GetValue(i)!;
                object expected = vertices.GetValue(actualCount + i)!;
                foreach (var field in actual.GetType().GetFields())
                {
                    object a = field.GetValue(actual)!, e = field.GetValue(expected)!;
                    // Independent anchor arithmetic can differ by a float32 ULP.
                    bool same = a is Vector3 av && e is Vector3 ev
                        ? Vector3.DistanceSquared(av, ev) < 0.000001f : Equals(a, e);
                    Check(same, $"{label}: sprite {i} {field.Name}");
                }
            }
            count.SetValue(batch, 0);
        }
        try
        {
            Terraria.Main.dedServ = false;
            Terraria.Main.screenPosition = new Vector2(40, 60);
            cacheProperty.SetValue(null, cache);
            textures.Add(path, Activator.CreateInstance(record, texture, 0f, 0L)!);
            batch.Begin();
            // Non-square, odd and small canvases: full UV/canvas retention is intentional.
            // An asymmetric alpha silhouette must not be recentered/cropped by this hook.
            foreach (var size in new[] { new Point(64, 32), new Point(17, 31), new Point(16, 8) })
            foreach (float uiScale in new[] { 0.65f, 1f, 1.4f })
            foreach (float visualScale in new[] { 0.5f, 1f, 1.75f })
            foreach (bool tinted in new[] { false, true })
            foreach (int? renderSize in new int?[] { null, 1, 40, 512 })
            {
                typeof(Texture2D).GetProperty("Width")!.SetValue(texture, size.X);
                typeof(Texture2D).GetProperty("Height")!.SetValue(texture, size.Y);
                item.color = tinted ? new Color(90, 170, 220, 140) : Color.Transparent;
                item.alpha = 97;
                var environment = new Color(150, 120, 90, 190);
                var frame = new Rectangle(0, 32, 32, 32); // origin is frame-local, not atlas coordinates
                // Exercise the real installed caller's scale/lighting helper; do not apply item.scale again.
                ItemSlot.DrawItem_GetColorAndScale(item, uiScale, ref environment, 24f, ref frame, out Color light, out float scale);
                Color drawColor = item.GetAlpha(light), itemColor = item.GetColor(environment);
                var center = new Vector2(110, 90);
                var offset = new Vector2(3, -5);
                generated.Data.Visual = new InfiniCrafterLocal.Common.Models.VisualSpec { SpritePath = path, DrawOffsetX = 3, DrawOffsetY = -5 };
                if (renderSize.HasValue) generated.Data.Visual.RenderSizePx = renderSize.Value;
                generated.Data.Visual.InventoryScale = visualScale;
                bool vanilla = generated.PreDrawInInventory(batch, center, frame, drawColor, itemColor, frame.Size() / 2f, scale);
                Check(!vanilla, "cached inventory replaces vanilla");
                int actualCount = (int)count.GetValue(batch)!;
                float fitScale = scale * Math.Min(1f, 32f / Math.Max(size.X, size.Y)) * visualScale;
                new DrawData(texture, center + offset, texture.Bounds, drawColor, 0f, texture.Bounds.Size() / 2f, fitScale, SpriteEffects.None, 0f).Draw(batch);
                if (tinted)
                    new DrawData(texture, center + offset, texture.Bounds, itemColor, 0f, texture.Bounds.Size() / 2f, fitScale, SpriteEffects.None, 0f).Draw(batch);
                Compare(actualCount, tinted ? 2 : 1, $"inventory {size} ui={uiScale} visual={visualScale} tint={tinted}");

                generated.Data.Visual.WorldScale = visualScale;
                float expectedRotation = tinted ? 0.37f : 0f;
                float worldScale = uiScale, rotation = expectedRotation;
                Color alphaColor = new Color(20, 35, 50, 65); // caller may already apply shimmer/alpha
                vanilla = generated.PreDrawInWorld(batch, environment, alphaColor, ref rotation, ref worldScale, 0);
                Check(!vanilla && worldScale == uiScale && rotation == expectedRotation, "world preserves caller refs");
                if (rotation == 0f)
                {
                    object quad = vertices.GetValue(0)!;
                    float bottom = float.MinValue;
                    for (int corner = 0; corner < 4; corner++)
                        bottom = Math.Max(bottom, ((Vector3)quad.GetType().GetField($"Position{corner}")!.GetValue(quad)!).Y);
                    Check(Math.Abs(bottom - (item.Bottom.Y - Terraria.Main.screenPosition.Y + offset.Y)) < 0.001f,
                        "unrotated world canvas bottom stays on the hitbox bottom plus authored offset");
                }
                actualCount = (int)count.GetValue(batch)!;
                float finalScale = uiScale * visualScale * (renderSize.HasValue ? renderSize.Value / (float)Math.Max(size.X, size.Y) : 1f);
                Vector2 origin = texture.Bounds.Size() / 2f;
                Vector2 position = item.Bottom - Terraria.Main.screenPosition + offset - new Vector2(0, size.Y * finalScale / 2f);
                new DrawData(texture, position, texture.Bounds, alphaColor, rotation, origin, finalScale, SpriteEffects.None, 0f).Draw(batch);
                if (tinted)
                    new DrawData(texture, position, texture.Bounds, item.GetColor(environment), rotation, origin, finalScale, SpriteEffects.None, 0f).Draw(batch);
                Compare(actualCount, tinted ? 2 : 1, $"world {size} scale={uiScale} visual={visualScale} tint={tinted}");
            }
            generated.Data.Visual.SpritePath = "";
            float missingScale = 0.8f, missingRotation = 0.25f;
            Check(generated.PreDrawInInventory(batch, Vector2.Zero, new Rectangle(0, 0, 32, 32), Color.White, Color.White, Vector2.Zero, 1f), "missing inventory delegates to vanilla");
            Check(generated.PreDrawInWorld(batch, Color.White, Color.White, ref missingRotation, ref missingScale, 0), "missing world delegates to vanilla");
            Check((int)count.GetValue(batch)! == 0 && missingScale == 0.8f && missingRotation == 0.25f, "missing texture emits nothing and preserves refs");
            batch.End();
        }
        finally
        {
            cacheProperty.SetValue(null, oldCache);
            Terraria.Main.dedServ = oldServer;
            Terraria.Main.screenPosition = oldScreen;
            textures.Clear(); // CPU shell must not be disposed as a GPU texture.
            cache.Dispose();
        }
        if (failures.Count != 0) throw new InvalidOperationException(string.Join("\n", failures));
    }
}
