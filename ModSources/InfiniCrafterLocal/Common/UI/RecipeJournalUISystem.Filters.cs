#nullable enable
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class RecipeJournalUISystem
{
    private static JournalFilterPreset? _beforeFilterReset;
    private static JournalFilterPreset CaptureFilters() => new(_query, _favoritesOnly, _unreadOnly, _effectFilter, _ingredientFilter, _sortOrder, _stockFilter);
    private static void ApplyFilters(JournalFilterPreset preset)
    {
        if (!preset.Valid) return;
        _query = preset.Query; _favoritesOnly = preset.Favorites; _unreadOnly = preset.Unread;
        _effectFilter = preset.Effect; _ingredientFilter = preset.Ingredient; _sortOrder = preset.Sort; _stockFilter = preset.Stock;
        _page = 0; _revealSelection = false; SetSearchFocus(false); SetNoteFocus(false);
    }
    internal static void ResetFilters()
    {
        _beforeFilterReset = CaptureFilters();
        ApplyFilters(new("", false, false, RecipeJournalView.EffectFilter.All, "", RecipeJournalView.SortOrder.Name));
    }
    internal static bool UndoFilterReset()
    {
        if (_beforeFilterReset is null) return false;
        ApplyFilters(_beforeFilterReset); _beforeFilterReset = null; return true;
    }
    private static void DrawFilterPresets(SpriteBatch sb, Rectangle area, bool click, Vector2 cursor)
    {
        var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
        if (Button(sb, new(area.X, area.Y, area.Width, 26), Text("Stock" + _stockFilter), click, cursor))
        { _stockFilter = (RecipeStockFilter.Mode)(((int)_stockFilter + 1) % System.Enum.GetValues<RecipeStockFilter.Mode>().Length); _page = 0; }
        if (new Rectangle(area.X, area.Y, area.Width, 26).Contains(cursor.ToPoint())) _hoverText = Text("StockHint");
        area.Y += 34; area.Height = System.Math.Max(0, area.Height - 34);
        int half = System.Math.Max(0, (area.Width - 6) / 2);
        if (Button(sb, new(area.X, area.Y, half, 25), Text("ResetFilters"), click, cursor)) ResetFilters();
        if (Button(sb, new(area.X + half + 6, area.Y, half, 25), Text("UndoFilterReset"), click, cursor, enabled: _beforeFilterReset is not null)) UndoFilterReset();
        Label(sb, Text("PresetHint"), new(area.X, area.Y + 30), Muted, .55f, area.Width);
        int visible = System.Math.Max(0, (area.Height - 60) / 34);
        _detailScroll = System.Math.Clamp(_detailScroll, 0, System.Math.Max(0, 6 - visible));
        for (int i = _detailScroll; i < System.Math.Min(6, _detailScroll + visible); i++)
        {
            var preset = owner.JournalPreset(i);
            int y = area.Y + 58 + (i - _detailScroll) * 34;
            int tools = System.Math.Min(100, area.Width / 2);
            var load = new Rectangle(area.X, y, area.Width - tools - 6, 26);
            if (Button(sb, load, Text(preset is null ? "PresetEmpty" : "PresetLoad", i + 1), click, cursor, enabled: preset is not null)) ApplyFilters(preset!);
            if (preset is not null && load.Contains(cursor.ToPoint()))
                _hoverText = preset.Query + "\n" + Text("Stock" + preset.Stock) + " · " + Text("Filter" + preset.Effect) + " · " + Text("Sort" + preset.Sort)
                    + (preset.Favorites ? " · " + Text("Favorites") : "") + (preset.Unread ? " · " + Text("OnlyUnvisited") : "");
            if (Button(sb, new(load.Right + 6, y, tools / 2, 26), Text("PresetSave"), click, cursor)) owner.SaveJournalPreset(i, CaptureFilters());
            if (Button(sb, new(load.Right + 8 + tools / 2, y, System.Math.Max(0, tools / 2 - 2), 26), "×", click, cursor, enabled: preset is not null)) owner.SaveJournalPreset(i, null);
        }
    }
}
