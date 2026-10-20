#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using ReLogic.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.GameInput;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

[Autoload(Side = ModSide.Client)]
public sealed class RecipeJournalUISystem : ModSystem
{
    public static bool IsOpen { get; private set; }
    private static string _query = "", _selected = "";
    private static bool _searchFocus, _favoritesOnly;
    private static int _page, _detailScroll;
    private static GeneratedItemData[] _known = Array.Empty<GeneratedItemData>();
    private static uint _snapshotTick;
    private static readonly Stack<string> History = new();
    private static readonly Color Ink = new(45, 53, 59), Muted = new(104, 108, 105), Gold = new(180, 137, 65);
    internal static string Text(string key, params object[] args)
        => Language.GetTextValue("Mods.InfiniCrafterLocal.RecipeJournal." + key, args);

    public static void Open()
    {
        IsOpen = true; _searchFocus = false; _snapshotTick = uint.MaxValue;
        Main.playerInventory = true;
        if (Main.netMode == Terraria.ID.NetmodeID.MultiplayerClient)
            InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer();
    }
    private static void Close() { IsOpen = false; Main.blockInput = false; _searchFocus = false; }
    public override void OnWorldUnload()
    {
        Close(); _query = _selected = ""; _page = 0; _favoritesOnly = false;
        _known = Array.Empty<GeneratedItemData>(); History.Clear();
    }
    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        int index = layers.FindIndex(layer => layer.Name == "Vanilla: Inventory");
        if (index >= 0) layers.Insert(Math.Min(index + 2, layers.Count), new LegacyGameInterfaceLayer("InfiniCrafterLocal: Recipe Journal", Draw, InterfaceScaleType.UI));
    }
    private static void Select(string id, bool remember = true)
    {
        if (remember && _selected.Length != 0 && _selected != id)
        {
            if (History.Count >= 32) History.Clear();
            History.Push(_selected);
        }
        _selected = id; _detailScroll = 0;
    }
    private static bool Draw()
    {
        if (!IsOpen) return true;
        if (Main.gameMenu || !Main.playerInventory || Main.LocalPlayer.dead) { Close(); return true; }
        if (Main.keyState.IsKeyDown(Keys.Escape) && Main.oldKeyState.IsKeyUp(Keys.Escape)) { Close(); return true; }
        if (Main.hideUI) return true;
        var player = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
        Main.LocalPlayer.mouseInterface = true;
        // Snapshot is refreshed outside per-entry drawing, never through generator HTTP.
        if (_snapshotTick == uint.MaxValue || unchecked(Main.GameUpdateCount - _snapshotTick) >= 60)
        {
            _known = InfiniCrafterLocalMod.GeneratedItems?.Snapshot() ?? Array.Empty<GeneratedItemData>();
            _snapshotTick = Main.GameUpdateCount;
        }
        Main.blockInput = _searchFocus;
        if (_searchFocus)
        {
            PlayerInput.WritingText = true; Main.instance.HandleIME();
            string query = Main.GetInputText(_query);
            query = query[..Math.Min(query.Length, 80)];
            if (query != _query) { _query = query; _page = 0; }
        }
        var entries = RecipeJournalView.Entries(_known, Main.worldID.ToString(), _query, player.IsJournalFavorite, _favoritesOnly);
        if (_selected.Length == 0 && entries.Length > 0) Select(entries[0].Id, false);
        // InterfaceScaleType.UI already applies PlayerInput.SetZoom_UI to screen and mouse.
        int width = Main.screenWidth, height = Main.screenHeight;
        var layout = RecipeJournalView.Bounds(width, height);
        Rectangle book = layout.Book;
        Vector2 cursor = new Vector2(Main.mouseX, Main.mouseY);
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        if (click && !book.Contains(cursor.ToPoint())) { _searchFocus = false; Main.mouseLeftRelease = false; }
        var sb = Main.spriteBatch;
        Fill(sb, new Rectangle(0, 0, width, height), new Color(9, 17, 25, 190));
        Fill(sb, new Rectangle(book.X + 7, book.Y + 9, book.Width, book.Height), new Color(0, 0, 0, 100));
        Fill(sb, book, new Color(234, 227, 209));
        Fill(sb, new Rectangle(book.X, book.Y, book.Width, 78), new Color(25, 48, 56));
        Fill(sb, new Rectangle(book.X, book.Y + 77, book.Width, 2), Gold);
        Label(sb, Text("Eyebrow"), new Vector2(book.X + 24, book.Y + 12), new Color(202, 176, 123), 0.52f, book.Width - 100);
        Label(sb, Text("Title"), new Vector2(book.X + 22, book.Y + 29), new Color(247, 239, 217), 1.05f, book.Width - 100);
        if (Button(sb, new Rectangle(book.Right - 48, book.Y + 20, 28, 30), "×", click, cursor, dark: true)) Close();
        Rectangle search = new(book.X + 20, book.Y + 82, Math.Max(105, layout.List.Width - 92), 24);
        Fill(sb, search, _searchFocus ? new Color(255, 252, 239) : new Color(218, 210, 190));
        Label(sb, _query.Length == 0 ? Text("Search") : _query + (_searchFocus && Main.GameUpdateCount % 60 < 30 ? "|" : ""), search.TopLeft() + new Vector2(7, 2), _query.Length == 0 ? Muted : Ink, 0.56f, search.Width - 12);
        if (click && search.Contains(cursor.ToPoint())) { _searchFocus = true; Main.mouseLeftRelease = false; }
        Rectangle favorites = new(search.Right + 6, search.Y, 86, 24);
        if (Button(sb, favorites, _favoritesOnly ? Text("All") : Text("Favorites"), click, cursor)) { _favoritesOnly = !_favoritesOnly; _page = 0; _searchFocus = false; }
        // Search occupies the first row above the list contents.
        Rectangle list = layout.List; list.Y += 16; list.Height -= 16;
        int rows = Math.Max(1, list.Height / 58), pages = Math.Max(1, (entries.Length + rows - 1) / rows);
        _page = Math.Clamp(_page, 0, pages - 1);
        for (int i = 0; i < rows && _page * rows + i < entries.Length; i++)
        {
            GeneratedItemData entry = entries[_page * rows + i];
            var row = new Rectangle(list.X, list.Y + i * 58, list.Width, 52);
            bool active = entry.Id == _selected;
            Fill(sb, row, active ? new Color(38, 69, 75) : new Color(224, 215, 195));
            if (active) Fill(sb, new Rectangle(row.X, row.Y, 3, row.Height), Gold);
            Sprite(sb, entry, new Rectangle(row.X + 9, row.Y + 8, 36, 36));
            Label(sb, (player.IsJournalFavorite(entry.Id) ? "★ " : "") + entry.Name, new Vector2(row.X + 54, row.Y + 7), active ? new Color(250, 243, 222) : Ink, 0.66f, row.Width - 64);
            Label(sb, entry.ParentA + " + " + entry.ParentB, new Vector2(row.X + 54, row.Y + 29), active ? new Color(180, 200, 195) : Muted, 0.48f, row.Width - 64);
            if (click && row.Contains(cursor.ToPoint())) { Select(entry.Id); _searchFocus = false; Main.mouseLeftRelease = false; }
        }
        int wheel = PlayerInput.ScrollWheelDeltaForUI;
        if (wheel != 0 && list.Contains(cursor.ToPoint())) _page = Math.Clamp(_page + (wheel < 0 ? 1 : -1), 0, pages - 1);
        if (wheel != 0 && layout.Detail.Contains(cursor.ToPoint())) _detailScroll = Math.Max(0, _detailScroll + (wheel < 0 ? 2 : -2));
        if (entries.Length == 0) Paragraph(sb, Text(_favoritesOnly ? "NoFavorites" : _query.Length == 0 ? "Empty" : "NoMatches"), list, Muted, 0.62f);
        GeneratedItemData? selected = _known.FirstOrDefault(d => d.Id == _selected);
        if (selected is not null) DrawDetail(sb, selected, layout.Detail, player, click, cursor);
        else Paragraph(sb, Text("Welcome"), layout.Detail, Muted, 0.7f);
        int bottom = book.Bottom - 35;
        if (Button(sb, new Rectangle(book.X + 20, bottom, 32, 24), "‹", click, cursor) && _page > 0) _page--;
        Label(sb, Text("Page", _page + 1, pages), new Vector2(book.X + 64, bottom + 3), Muted, 0.55f, 140);
        if (Button(sb, new Rectangle(book.X + 200, bottom, 32, 24), "›", click, cursor) && _page + 1 < pages) _page++;
        if (book.Width > 700) Label(sb, Text("Count", _known.Length), new Vector2(book.Right - 250, bottom + 3), Muted, 0.55f, 226);
        if (click && book.Contains(cursor.ToPoint())) Main.mouseLeftRelease = false;
        return true;
    }
    private static void DrawDetail(SpriteBatch sb, GeneratedItemData data, Rectangle area, InfiniCraftPlayer player, bool click, Vector2 cursor)
    {
        Fill(sb, area, new Color(248, 241, 222));
        Fill(sb, new Rectangle(area.X, area.Y, 1, area.Height), new Color(205, 189, 154));
        int x = area.X + 18, y = area.Y + 14, w = area.Width - 36;
        if (area.Height < 180)
        {
            Label(sb, data.Name, new Vector2(x, y), Ink, 0.8f, w);
            Paragraph(sb, data.ParentA + " + " + data.ParentB, new Rectangle(x, y + 32, w, area.Height - 50), Muted, 0.6f);
            return;
        }
        if (History.Count > 0 && Button(sb, new Rectangle(x, y, 80, 23), Text("Back"), click, cursor)) Select(History.Pop(), false);
        Rectangle star = new(area.Right - 130, y, 112, 23);
        if (Button(sb, star, player.IsJournalFavorite(data.Id) ? Text("Saved") : Text("Save"), click, cursor)) player.ToggleJournalFavorite(data.Id);
        y += 36;
        // A quiet geometric seal frames the actual generated sprite.
        Rectangle seal = new(x + (w - 94) / 2, y, 94, 94);
        Fill(sb, seal, new Color(233, 221, 191));
        Fill(sb, new Rectangle(seal.X + 3, seal.Y + 3, 88, 88), new Color(242, 233, 211));
        Sprite(sb, data, new Rectangle(seal.X + 12, seal.Y + 12, 70, 70));
        y += 106;
        Label(sb, data.Name, new Vector2(x, y), Ink, 0.9f, w); y += 31;
        Label(sb, Text("Generation", data.RecipeMeta.GenerationDepth), new Vector2(x, y), Gold, 0.56f, w); y += 29;
        Label(sb, Text("Ingredients"), new Vector2(x, y), Muted, 0.53f, w); y += 22;
        int cardWidth = (w - 24) / 2;
        for (int p = 0; p < 2; p++)
        {
            var card = new Rectangle(x + p * (cardWidth + 24), y, cardWidth, 48);
            GeneratedItemData? parent = RecipeJournalView.Parent(data, p, _known);
            Fill(sb, card, new Color(231, 222, 200));
            Label(sb, p == 0 ? data.ParentA : data.ParentB, card.TopLeft() + new Vector2(8, 7), Ink, 0.62f, card.Width - 16);
            Label(sb, Text(parent is null ? "Ingredient" : "OpenParent"), card.TopLeft() + new Vector2(8, 28), parent is null ? Muted : Gold, 0.46f, card.Width - 16);
            if (parent is not null && click && card.Contains(cursor.ToPoint())) Select(parent.Id);
        }
        Label(sb, "+", new Vector2(x + cardWidth + 7, y + 13), Gold, 0.7f, 18); y += 62;
        Fill(sb, new Rectangle(x, y, w, 1), new Color(210, 194, 160)); y += 13;
        string description = data.GeneratedParentSummary.PlayerExperience;
        if (string.IsNullOrWhiteSpace(description)) description = data.GeneratedParentSummary.Description;
        Paragraph(sb, description, new Rectangle(x, y, w, Math.Max(0, area.Bottom - y - 16)), Ink, 0.63f, true);
    }
    private static void Sprite(SpriteBatch sb, GeneratedItemData data, Rectangle bounds)
    {
        Texture2D? texture = InfiniCrafterLocalMod.Sprites?.TryGet(data.Visual.SpritePath);
        if (texture is null) return; // Assets hydrate through the existing registry, never a fake item.
        float scale = Math.Min(bounds.Width / (float)texture.Width, bounds.Height / (float)texture.Height);
        sb.Draw(texture, bounds.Center.ToVector2(), null, Color.White, 0f, texture.Size() * 0.5f, scale, SpriteEffects.None, 0f);
    }
    private static void Fill(SpriteBatch sb, Rectangle rect, Color color)
    { if (rect.Width > 0 && rect.Height > 0) sb.Draw(TextureAssets.MagicPixel.Value, rect, color); }
    private static void Label(SpriteBatch sb, string text, Vector2 at, Color color, float scale, int width)
    {
        text = (text ?? "").Replace('\n', ' ').Replace('\r', ' ');
        var font = FontAssets.MouseText.Value;
        if (width <= 0) return;
        while (text.Length > 1 && font.MeasureString(text).X * scale > width) text = text[..^1];
        sb.DrawString(font, text, at, color, 0f, Vector2.Zero, scale, SpriteEffects.None, 0f);
    }
    private static void Paragraph(SpriteBatch sb, string text, Rectangle rect, Color color, float scale, bool scroll = false)
    {
        if (rect.Height < 20 || rect.Width <= 0) return;
        var rows = GeneratedItem.WrapRuntimeTooltipLines(text ?? "", rect.Width / scale, value => FontAssets.MouseText.Value.MeasureString(value).X);
        int start = scroll ? Math.Clamp(_detailScroll, 0, Math.Max(0, rows.Count - Math.Max(1, rect.Height / 23))) : 0;
        if (scroll) _detailScroll = start;
        int line = 0;
        foreach (string row in rows.Skip(start))
        {
            if ((line + 1) * 23 > rect.Height) break;
            Label(sb, row, rect.TopLeft() + new Vector2(0, line++ * 23), color, scale, rect.Width);
        }
    }
    private static bool Button(SpriteBatch sb, Rectangle rect, string text, bool click, Vector2 cursor, bool dark = false)
    {
        bool hover = rect.Contains(cursor.ToPoint());
        Fill(sb, rect, dark ? new Color(42, 67, 73) : hover ? new Color(212, 193, 153) : new Color(222, 211, 186));
        Label(sb, text, rect.TopLeft() + new Vector2(6, 2), dark ? new Color(247, 238, 215) : Ink, 0.59f, rect.Width - 12);
        return click && hover;
    }
}
