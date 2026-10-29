using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static void AtlasDrawingUsesBoundedPixelsAndCenteredText()
    {
        // Terraria's MagicPixel asset is 1x1000. A full-texture source would
        // produce a 1000-pixel strip even with a Y scale of one.
        var textureBounds = new Rectangle(0, 0, 1, 1000);
        var source = RecipeJournalUISystem.SolidPixelSource;
        Equal(true, textureBounds.Contains(source), "line samples inside the native texture");
        Equal(1, source.Width * source.Height, "UI lines sample one texel independent of asset height");
        foreach (byte alpha in new byte[] { 0, 40, 85, 115, 255 })
        {
            var converted = RecipeJournalUISystem.PremultipliedUiColor(new Color(255, 245, 214, alpha));
            Equal(alpha, converted.A, "paper opacity is preserved");
            Equal(true, converted.R <= alpha && converted.G <= alpha && converted.B <= alpha,
                "AlphaBlend never receives additive straight-alpha paper colors");
        }
        foreach (var bounds in new[] { new Rectangle(10, 20, 118, 26), new Rectangle(30, 40, 80, 28), new Rectangle(0, 0, 44, 44) })
        foreach (var size in new[] { new Vector2(20, 12), new Vector2(60, 18), new Vector2(38, 24) })
        {
            var at = RecipeJournalUISystem.CenteredTextPosition(bounds, size);
            Equal((float)bounds.Center.X, at.X + size.X / 2, "caption horizontal center");
            Equal((float)bounds.Center.Y, at.Y + size.Y / 2, "caption vertical center");
        }
    }

    private static void AtlasBookControlsStayReachableAcrossUiScales()
    {
        foreach (int screenWidth in new[] { 320, 640, 800, 1280, 1920 })
        foreach (int screenHeight in new[] { 240, 360, 600, 720, 1080 })
        foreach (float uiScale in new[] { .75f, 1f, 1.5f, 2f })
        {
            int width = (int)(screenWidth / uiScale), height = (int)(screenHeight / uiScale);
            var layout = RecipeJournalView.Bounds(width, height);
            Equal(true, new Rectangle(0, 0, width, height).Contains(layout.Book), "book respects scaled input/draw viewport");
            if (layout.Book.Width < 260 || layout.Book.Height < 240 || layout.Rows == 0 || layout.Columns == 0) continue;
            var controls = RecipeJournalView.BookControls(layout);
            var rectangles = new[] { controls.Search, controls.Favorites, controls.Filter, controls.ClearIngredient,
                controls.Previous, controls.Page, controls.Next, controls.Close };
            foreach (var control in rectangles)
            {
                Equal(true, control.Width > 0 && control.Height > 0, "every full-mode control has a reachable hit area");
                Equal(true, layout.Book.Contains(control), "toolbar and pagination stay on the book");
                Equal(false, control.Intersects(layout.List) || control.Intersects(layout.Detail), "controls never cover selectable discovery or recipe content");
            }
            for (int i = 0; i < rectangles.Length; i++)
            for (int j = i + 1; j < rectangles.Length; j++)
                Equal(false, rectangles[i].Intersects(rectangles[j]), "independent toolbar controls never share hit targets");
            for (int row = 0; row < layout.Rows; row++)
            for (int col = 0; col < layout.Columns; col++)
            {
                // Native inventory-cell pitch is unchanged by this skin; test every rendered slot.
                var slot = new Rectangle(layout.List.X + col * 52, layout.List.Y + row * 52, 48, 48);
                Equal(true, layout.List.Contains(slot), "no partial discovery slot leaks into detail or pagination");
            }
            if (layout.Detail.Width >= 60 && layout.Detail.Height >= 40)
            {
                var detail = RecipeJournalView.DetailControls(layout.Detail);
                Equal(true, layout.Detail.Contains(detail.Back) && layout.Detail.Contains(detail.Save), "history and favorite controls fit responsive detail");
                Equal(false, detail.Back.Intersects(detail.Save), "history and favorite remain separate click targets");
            }
        }
    }

    private static void AtlasDiscoverySelectionKeepsSearchFavoritesAndAncestry()
    {
        GeneratedItemData Entry(string id, string name, string world = "17")
        {
            var d = GeneratedItemData.Placeholder(); d.Id = id; d.Name = name;
            d.RecipeMeta.WorldScoped = true; d.RecipeMeta.WorldId = world;
            return d;
        }
        var parent = Entry("parent", "Wood compass");
        var child = Entry("child", "Copper branch"); child.ParentA = "Wood compass";
        child.RecipeMeta.ParentIdentities = new[] { "generated:parent", "item:Terraria:Wood:9" };
        child.Gameplay.PickPower = 10;
        var duplicateName = Entry("other", "Wood compass");
        var foreign = Entry("foreign", "Wood compass", "18");
        var rows = new[] { foreign, duplicateName, child, parent, child };
        var found = RecipeJournalView.Entries(rows, "17", "  WOOD  ", id => id == "child", false);
        Equal(3, found.Length, "search includes ingredient names, deduplicates identities and fences foreign worlds");
        Equal("child", found[0].Id, "favorite stays first under ingredient search");
        Equal("child", RecipeJournalView.Entries(rows, "17", "wood", id => id == "child", true).Single().Id,
            "favorites and query compose without leaking nonfavorites");
        Equal("child", found.Where(d => RecipeJournalView.MatchesEffect(d, RecipeJournalView.EffectFilter.Mining)).Single().Id,
            "effect filter composes with search using actual mechanic not caption");
        Equal("child", RecipeJournalView.Children(parent, rows).Single().Id, "detail ingredient history remains exact");
        Equal(0, RecipeJournalView.Children(duplicateName, rows).Length, "same-name discovery never aliases ancestry");
        Equal(0, RecipeJournalView.Entries(rows, "17", "missing-query", _ => true, false).Length, "empty search remains honest");
    }

    private static void AtlasDetailLineageNavigationPreservesReturnLocation()
    {
        const BindingFlags flags = BindingFlags.NonPublic | BindingFlags.Static;
        Type ui = typeof(RecipeJournalUISystem);
        object? Get(string field) => ui.GetField(field, flags)!.GetValue(null);
        void Set(string field, object value) => ui.GetField(field, flags)!.SetValue(null, value);
        void Select(string id) => ui.GetMethod("Select", flags)!.Invoke(null, new object[] { id, true });
        void Back() => ui.GetMethod("GoBack", flags)!.Invoke(null, null);
        var root = GeneratedItemData.Placeholder(); root.Id = "root";
        bool oldBlock = Terraria.Main.blockInput, oldWriting = Terraria.GameInput.PlayerInput.WritingText;
        try
        {
            new RecipeJournalUISystem().OnWorldUnload();
            Terraria.Main.blockInput = Terraria.GameInput.PlayerInput.WritingText = false;
            Set("_query", "compass"); Set("_favoritesOnly", true); Set("_page", 2);
            Select("root");
            ui.GetMethod("OpenLineage", flags)!.Invoke(null, new object[] { root });
            Equal(true, (bool)Get("_lineageOpen")!, "detail opens lineage without losing root");
            Select("parent");
            Equal(false, (bool)Get("_lineageOpen")!, "generated lineage click opens actual parent detail");
            Back();
            Equal("root", (string)Get("_selected")!, "back returns to selected lineage root");
            Equal(true, (bool)Get("_lineageOpen")!, "back restores lineage view rather than an unrelated detail");
            Back();
            Equal("root", (string)Get("_selected")!, "second back returns to original detail");
            Equal(false, (bool)Get("_lineageOpen")!, "original detail view restored");
            Equal("compass", (string)Get("_query")!, "navigation preserves discovery search");
            Equal(true, (bool)Get("_favoritesOnly")!, "navigation preserves favorite filter");
            Equal(2, (int)Get("_page")!, "navigation preserves discovery page");
            Back();
            Equal(false, (bool)Get("_lineageOpen")!, "back on empty history remains safe");
            new RecipeJournalUISystem().OnWorldUnload();
            Equal("", (string)Get("_selected")!, "world exit cannot reuse previous discovery selection");
            Equal("", (string)Get("_query")!, "world exit releases search session");
        }
        finally
        {
            new RecipeJournalUISystem().OnWorldUnload();
            Terraria.Main.blockInput = oldBlock; Terraria.GameInput.PlayerInput.WritingText = oldWriting;
        }
    }
}
