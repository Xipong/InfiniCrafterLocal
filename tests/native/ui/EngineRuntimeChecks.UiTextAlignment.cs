using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using ReLogic.Content;
using ReLogic.Graphics;
using Terraria;
using Terraria.GameContent;

internal static partial class EngineRuntimeChecks
{
    private static void AtlasLayoutNativeText(bool forge)
    {
        var assembly = typeof(EngineRuntimeChecks).Assembly;
        using var stream = assembly.GetManifestResourceStream(assembly.GetManifestResourceNames().Single(n => n.EndsWith("AtlasMouseTextMetrics.json", StringComparison.Ordinal)))!;
        using var fixture = JsonDocument.Parse(stream);
        var root = fixture.RootElement;
        var font = new DynamicSpriteFont(root.GetProperty("spacing").GetSingle(), root.GetProperty("lineSpacing").GetInt32(), '*');
        var alpha = new Dictionary<(Texture2D, Rectangle), Rectangle?>();
        Rectangle Rect(JsonElement row) { int[] n = row.EnumerateArray().Select(v => v.GetInt32()).ToArray(); return new(n[0], n[1], n[2], n[3]); }
        var pageType = typeof(DynamicSpriteFont).Assembly.GetType("ReLogic.Graphics.FontPage")!;
        var pages = new List<object>();
        foreach (var group in root.GetProperty("characters").EnumerateObject().GroupBy(p => p.Value.GetProperty("page").GetInt32()))
        {
            var texture = CpuTexture(256, 256);
            var glyphs = new List<Rectangle>(); var padding = new List<Rectangle>();
            var chars = new List<char>(); var kerns = new List<Vector3>();
            foreach (var property in group)
            {
                var row = property.Value; var glyph = Rect(row.GetProperty("glyph"));
                glyphs.Add(glyph); padding.Add(Rect(row.GetProperty("padding"))); chars.Add(property.Name[0]);
                float[] k = row.GetProperty("kerning").EnumerateArray().Select(v => v.GetSingle()).ToArray(); kerns.Add(new(k[0], k[1], k[2]));
                var ink = row.GetProperty("alphaBounds");
                if (ink.ValueKind == JsonValueKind.Null) alpha[(texture, glyph)] = null;
                else { var bounds = Rect(ink); bounds.Width -= bounds.X; bounds.Height -= bounds.Y; alpha[(texture, glyph)] = bounds; }
            }
            var page = RuntimeHelpers.GetUninitializedObject(pageType);
            foreach (var pair in new (string Name, object Value)[] { ("Texture", texture), ("Glyphs", glyphs), ("Padding", padding), ("Characters", chars), ("Kerning", kerns) })
                pageType.GetField(pair.Name, TestInstance)!.SetValue(page, pair.Value);
            pages.Add(page);
        }
        var nativePages = Array.CreateInstance(pageType, pages.Count);
        for (int i = 0; i < pages.Count; i++) nativePages.SetValue(pages[i], i);
        // The real reader's default-character binding, not a synthetic fallback.
        typeof(DynamicSpriteFont).GetMethod("SetPages", TestInstance)!.Invoke(font, new object[] { nativePages });
        var previous = FontAssets.MouseText;
        var asset = (Asset<DynamicSpriteFont>)RuntimeHelpers.GetUninitializedObject(typeof(Asset<DynamicSpriteFont>));
        foreach (var field in asset.GetType().GetFields(TestInstance)) if (field.FieldType == typeof(DynamicSpriteFont)) field.SetValue(asset, font);
        asset.GetType().GetProperty("State")!.SetValue(asset, AssetState.Loaded);
        const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
        var glyphCalls = new List<(Vector2 Min, Vector2 Max)>();
        // Leave DynamicSpriteFont.InternalDraw and Utils/ChatManager intact.
        // Observe final native glyph callbacks before SpriteBatch touches a GPU.
        var draw = typeof(SpriteBatch).GetMethod("Draw", new[] { typeof(Texture2D), typeof(Vector2), typeof(Rectangle?), typeof(Color), typeof(float), typeof(Vector2), typeof(Vector2), typeof(SpriteEffects), typeof(float) })!;
        using var glyphBoundary = new Hook(draw, (Action<SpriteBatch, Texture2D, Vector2, Rectangle?, Color, float, Vector2, Vector2, SpriteEffects, float>)
            ((_, texture, at, source, _, rotation, origin, scale, effects, _) => {
                Equal(0f, rotation, "labels remain unrotated"); Equal(Vector2.Zero, origin, "native glyph origin"); Equal(SpriteEffects.None, effects, "labels remain unflipped");
                if (alpha[(texture, source!.Value)] is not { } ink) return;
                glyphCalls.Add((at + ink.TopLeft() * scale, at + ink.BottomRight() * scale));
            }));
        using var buttonPaint = new Hook(typeof(InfiniCraftStationUISystem).GetMethod("DrawRect", flags)!, (Action<SpriteBatch, Rectangle, Color>)((_, _, _) => {}));
        var batch = CpuSpriteBatch(1);
        try
        {
            FontAssets.MouseText = asset;
            var labels = root.GetProperty("labels").EnumerateArray().Select(row => row.GetProperty("text").GetString()!)
                .Concat(new[] { "   Book   ", "\uffff", "", "   " }).ToArray();
            foreach (var bounds in new[] { new Rectangle(10, 20, 117, 39), new Rectangle(10, 20, 62, 26) })
            foreach (string text in labels)
            {
                glyphCalls.Clear();
                if (forge) typeof(InfiniCraftStationUISystem).GetMethod("DrawButton", flags)!.Invoke(null, new object[] { batch, bounds, true, text });
                else typeof(RecipeJournalUISystem).GetMethod("CenterLabel", flags)!.Invoke(null, new object[] { batch, text, bounds, Color.White, .6f });
                if (string.IsNullOrWhiteSpace(text)) { Equal(0, glyphCalls.Count, "empty/whitespace emits no ink"); continue; }
                Equal(true, glyphCalls.Count > 0, "native font emitted glyphs, including default or clipped ellipsis");
                float x = (glyphCalls.Min(g => g.Min.X) + glyphCalls.Max(g => g.Max.X)) * .5f;
                float y = (glyphCalls.Min(g => g.Min.Y) + glyphCalls.Max(g => g.Max.Y)) * .5f;
                // XNB glyph rectangles include at most one transparent edge texel;
                // compare the independently decoded alpha ink to within that raster edge.
                Equal(true, Math.Abs(x - (bounds.X + bounds.Width * .5f)) <= .55f, $"native {(forge ? "forge" : "atlas")} ink X for '{text}': {x}");
                Equal(true, Math.Abs(y - (bounds.Y + bounds.Height * .5f)) <= .55f, $"native {(forge ? "forge" : "atlas")} ink Y for '{text}': {y}");
            }
            if (!forge)
            {
                // Centering math also follows native line reset/CR handling;
                // UI CenterLabel itself deliberately clips labels to one line.
                var target = new Rectangle(13, 27, 301, 121);
                foreach (string text in new[] { "Book\r\nTake", "  ?\n\nКнига  ", "\uffff\nForge" })
                foreach (float scale in new[] { .55f, .85f, 1.5f })
                {
                    glyphCalls.Clear();
                    batch.DrawString(font, text, UiTextAlignment.CenteredPosition(font, text, target, scale), Color.White,
                        0, Vector2.Zero, scale, SpriteEffects.None, 0);
                    float x = (glyphCalls.Min(g => g.Min.X) + glyphCalls.Max(g => g.Max.X)) * .5f;
                    float y = (glyphCalls.Min(g => g.Min.Y) + glyphCalls.Max(g => g.Max.Y)) * .5f;
                    Equal(true, Math.Abs(x - (target.X + target.Width * .5f)) <= scale * .5f + .01f, "multiline native horizontal bearing center");
                    Equal(true, Math.Abs(y - (target.Y + target.Height * .5f)) <= scale * .5f + .01f, "multiline native visible vertical center");
                }
                foreach (string text in new[] { "", " ", "\r\n" })
                    Equal(font.MeasureString(text) * .5f, UiTextAlignment.VisibleCenter(font, text), "no-ink metrics retain safe logical fallback");
            }
        }
        finally { FontAssets.MouseText = previous; }
    }
}
