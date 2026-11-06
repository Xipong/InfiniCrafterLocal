using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;

internal static partial class EngineRuntimeChecks
{
    // Observe production Draw/DrawDetail rectangles at their paint boundaries;
    // no graphics device, art, native content loading or alternate layout math.
    private sealed class AtlasLayoutPaint : IDisposable
    {
        internal const BindingFlags Flags = BindingFlags.Static | BindingFlags.NonPublic;
        internal static readonly Type Ui = typeof(RecipeJournalUISystem);
        internal readonly List<Rectangle> Wells = new();
        internal readonly Dictionary<string, (Rectangle Bounds, bool Centered)> Labels = new();
        private readonly List<Hook> hooks = new();
        internal AtlasLayoutPaint()
        {
            Add("DrawBook", (Action<SpriteBatch, Rectangle>)((_, _) => {}));
            Add("DrawPaperSlip", (Action<SpriteBatch, Rectangle, bool>)((_, _, _) => {}));
            Add("Button", (Func<SpriteBatch, Rectangle, string, bool, Vector2, bool, bool, bool>)((_, _, _, _, _, _, _) => false));
            Add("LineageButton", (Func<SpriteBatch, Rectangle, string, bool, Vector2, bool>)((_, _, _, _, _) => false));
            Add("HeaderLabel", (Action<SpriteBatch, string, Rectangle, Color, float>)((_, _, _, _, _) => {}));
            Add("Label", (Action<SpriteBatch, string, Vector2, Color, float, int>)((_, text, at, _, _, width) => Labels[text] = (new Rectangle((int)at.X, (int)at.Y, width, 20), false)));
            Add("CenterLabel", (Action<SpriteBatch, string, Rectangle, Color, float>)((_, text, rect, _, _) => Labels[text] = (rect, true)));
            Add("Text", (Func<string, object[], string>)((key, _) => key));
            Add("Fill", (Action<SpriteBatch, Rectangle, Color>)((_, _, _) => {}));
            Add("Trace", (Action<SpriteBatch, Vector2, Vector2, Color>)((_, _, _, _) => {}));
            Add("ItemSlotBackground", (Action<SpriteBatch, Rectangle, bool, bool>)((_, rect, _, _) => Wells.Add(rect)));
            Add("Sprite", (Action<SpriteBatch, GeneratedItemData, Rectangle>)((_, _, _) => {}));
            Add("Paragraph", (Action<SpriteBatch, string, Rectangle, Color, float, bool>)((_, _, _, _, _, _) => {}));
        }
        internal void Add(string name, Delegate callback) => hooks.Add(new Hook(Ui.GetMethod(name, Flags)!, callback));
        internal static void Set(string name, object value) => Ui.GetField(name, Flags)!.SetValue(null, value);
        public void Dispose() { for (int i = hooks.Count - 1; i >= 0; i--) hooks[i].Dispose(); }
    }

    private static void AtlasLayoutNativeGrid()
    {
        WithPlayer((player, _) => {
            using var actors = new NativeActorState();
            using var paint = new AtlasLayoutPaint();
            paint.Add("DrawDetail", (Action<SpriteBatch, GeneratedItemData, Rectangle, InfiniCraftPlayer, bool, Vector2>)((_, _, _, _, _, _) => {}));
            // Coverage is checked separately by the existing focus/overlay tests.
            paint.Add("IsCovered", (Func<bool>)(() => false));
            int oldWidth = Terraria.Main.screenWidth, oldHeight = Terraria.Main.screenHeight;
            int oldX = Terraria.Main.mouseX, oldY = Terraria.Main.mouseY;
            bool oldInventory = Terraria.Main.playerInventory, oldMenu = Terraria.Main.gameMenu;
            bool oldLeft = Terraria.Main.mouseLeft, oldRight = Terraria.Main.mouseRight;
            var oldKeys = Terraria.Main.keyState;
            try
            {
                Terraria.Main.myPlayer = 0; Terraria.Main.player[0] = player;
                Terraria.Main.gameMenu = false; Terraria.Main.mouseLeft = Terraria.Main.mouseRight = false;
                Terraria.Main.mouseX = Terraria.Main.mouseY = -100;
                Terraria.Main.keyState = default;
                var records = Enumerable.Range(0, 256).Select(i => {
                    var data = GeneratedItemData.Placeholder(); data.Id = "layout-" + i; data.Name = data.Id;
                    data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString(); return data;
                }).ToArray();
                foreach (var viewport in new[] { new Point(1280, 800), new Point(820, 600), new Point(680, 560), new Point(520, 480), new Point(521, 481) })
                {
                    new RecipeJournalUISystem().OnWorldUnload(); RecipeJournalUISystem.Open();
                    AtlasLayoutPaint.Set("_known", records); AtlasLayoutPaint.Set("_snapshotTick", Terraria.Main.GameUpdateCount);
                    Terraria.Main.screenWidth = viewport.X; Terraria.Main.screenHeight = viewport.Y;
                    paint.Wells.Clear();
                    AtlasLayoutPaint.Ui.GetMethod("Draw", AtlasLayoutPaint.Flags)!.Invoke(null, null);
                    var layout = RecipeJournalView.Bounds(viewport.X, viewport.Y);
                    Equal(layout.Rows * layout.Columns, paint.Wells.Count, "actual Draw emits every full-page slot");
                    foreach (var well in paint.Wells) Equal(true, layout.List.Contains(well), "actual slot remains within list/hit viewport");
                    int left = paint.Wells.Min(r => r.Left) - layout.List.Left;
                    int right = layout.List.Right - paint.Wells.Max(r => r.Right);
                    Equal(true, Math.Abs(left - right) <= 1, $"actual grid symmetric margins at {viewport}: {left}/{right}");
                    for (int i = 1; i < layout.Columns; i++) Equal(52, paint.Wells[i].X - paint.Wells[i-1].X, "native slot pitch unchanged");
                    if (layout.Detail.X > layout.List.Right)
                        Equal((layout.Book.Width - 64) * 42 / 100, layout.List.Width, "wide page retains unsnapped share, not whole-cell rounding");
                }
            }
            finally
            {
                new RecipeJournalUISystem().OnWorldUnload();
                Terraria.Main.screenWidth = oldWidth; Terraria.Main.screenHeight = oldHeight;
                Terraria.Main.mouseX = oldX; Terraria.Main.mouseY = oldY;
                Terraria.Main.playerInventory = oldInventory; Terraria.Main.gameMenu = oldMenu;
                Terraria.Main.mouseLeft = oldLeft; Terraria.Main.mouseRight = oldRight; Terraria.Main.keyState = oldKeys;
            }
        });
    }

    private static void AtlasLayoutNativeCaptions()
    {
        using var paint = new AtlasLayoutPaint();
        var data = GeneratedItemData.Placeholder(); data.Id = "layout-caption";
        data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString();
        try
        {
            foreach (var area in new[] { new Rectangle(100, 40, 500, 600), new Rectangle(100, 40, 300, 400) })
            {
                new RecipeJournalUISystem().OnWorldUnload();
                AtlasLayoutPaint.Set("_known", new[] { data }); AtlasLayoutPaint.Set("_selected", data.Id);
                paint.Wells.Clear(); paint.Labels.Clear();
                AtlasLayoutPaint.Ui.GetMethod("DrawDetail", AtlasLayoutPaint.Flags)!.Invoke(null,
                    new object?[] { null, data, area, new InfiniCraftPlayer(), false, new Vector2(-100) });
                Equal(3, paint.Wells.Count, "real detail emits two ingredient wells and result");
                var inputs = Rectangle.Union(paint.Wells[0], paint.Wells[1]); var result = paint.Wells[2];
                var ingredients = paint.Labels["Ingredients"]; var output = paint.Labels["Result"];
                Equal(result.Center.X, output.Bounds.Center.X, "actual result caption shares seal center, not eight pixels left");
                Equal(inputs.Center.X, ingredients.Bounds.Center.X, "actual caption centers on tall column or compact input pair");
                Equal(true, ingredients.Centered && output.Centered, "both captions use the centered text owner");
                Equal(ingredients.Bounds.Y, output.Bounds.Y, "caption baseline row is shared");
                Equal(false, ingredients.Bounds.Intersects(output.Bounds), "caption groups do not overlap");
            }
        }
        finally { new RecipeJournalUISystem().OnWorldUnload(); }
    }
}
