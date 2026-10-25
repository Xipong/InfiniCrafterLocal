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
public sealed partial class RecipeJournalUISystem : ModSystem
{
    public static bool IsOpen { get; private set; }
    public static ModKeybind ToggleJournalKey { get; private set; } = null!;

    public override void Load()
    {
        ToggleJournalKey = KeybindLoader.RegisterKeybind(Mod, "ToggleRecipeJournal", Keys.K);
        LoadBookSkin();
        LineageClip = new RasterizerState { ScissorTestEnable = true, CullMode = CullMode.None };
    }

    public override void Unload() { ResetSession(); UnloadBookSkin(); LineageClip?.Dispose(); LineageClip = null; ToggleJournalKey = null!; }

    internal static bool CanToggleFromKey(bool focused, bool menu, bool dead, bool writing,
        bool chat, bool blocked, bool rebinding)
        => focused && !menu && !dead && !writing && !chat && !blocked && !rebinding;

    public override void PostUpdateInput()
    {
        // Hidden interface layers may not draw, but must still relinquish text focus.
        if (IsOpen && (Main.gameMenu || !Main.playerInventory || Main.LocalPlayer.dead)) Close();
        if (IsOpen) CanResumeInput(IsCovered(), Main.mouseLeft, Main.mouseRight);
        UpdateLineageInput();
        if (ToggleJournalKey?.JustPressed != true || Main.LocalPlayer is not { active: true } player
            || !CanToggleFromKey(Main.hasFocus, Main.gameMenu, player.dead, PlayerInput.WritingText,
                Main.drawingPlayerChat, Main.blockInput, PlayerInput.CurrentlyRebinding)) return;
        if (IsOpen) Close(); else Open();
    }
    private static string _query = "", _selected = "";
    private static bool _searchFocus, _favoritesOnly, _awaitingMouseRelease;
    private static Player? _sessionOwner;
    private static int _sessionWorld;
    private static RecipeJournalView.EffectFilter _effectFilter;
    private static string _ingredientFilter = "";
    private static int _page, _detailScroll;
    private static GeneratedItemData[] _known = Array.Empty<GeneratedItemData>();
    private static uint _snapshotTick;
    private readonly record struct JournalLocation(string Id, bool Lineage);
    private static readonly Stack<JournalLocation> History = new();
    // Dark ink on a continuous parchment sheet; brass belongs to the leather header.
    private static readonly Color Ink = new(79, 57, 34), Muted = new(113, 88, 55), Gold = new(216, 185, 115);
    private static readonly Color Rule = new(135, 107, 65, 115), Link = new(133, 67, 35);
    private static string _hoverText = "";
    private static readonly string?[] DetailParentIdentities = new string?[2];
    private static readonly Item?[] DetailNativeParents = new Item?[2];
    internal static string Text(string key, params object[] args)
        => Language.GetTextValue("Mods.InfiniCrafterLocal.RecipeJournal." + key, args);

    public static void Open()
    {
        if (!ReferenceEquals(_sessionOwner, Main.LocalPlayer) || _sessionWorld != Main.worldID) ResetSession();
        _sessionOwner = Main.LocalPlayer; _sessionWorld = Main.worldID;
        IsOpen = true; SetSearchFocus(false); _snapshotTick = uint.MaxValue;
        Main.playerInventory = true;
        if (Main.netMode == Terraria.ID.NetmodeID.MultiplayerClient)
            InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer();
    }
    internal static void SetSearchFocus(bool focused)
    {
        if (focused == _searchFocus) return;
        // Do not acquire or clear another interface's text-input reservation.
        if (focused && (Main.blockInput || PlayerInput.WritingText
            || Main.drawingPlayerChat || PlayerInput.CurrentlyRebinding)) return;
        _searchFocus = focused;
        Main.blockInput = focused;
        PlayerInput.WritingText = focused;
    }
    private static void Close() { IsOpen = false; SetSearchFocus(false); ClearLineageHover(); _lineageDragging = _lineageBrowserPending = false; }
    private static bool IsCovered()
        => !Main.hasFocus || Main.hideUI || Main.mapFullscreen || Main.ingameOptionsWindow
            || Main.inFancyUI || Main.drawingPlayerChat || PlayerInput.CurrentlyRebinding
            || (!_searchFocus && (Main.blockInput || PlayerInput.WritingText));
    internal static bool CanResumeInput(bool covered, bool leftDown, bool rightDown)
    {
        if (covered)
        {
            SetSearchFocus(false); ClearLineageHover(); _lineageDragging = false;
            _awaitingMouseRelease = true;
            return false;
        }
        if (_awaitingMouseRelease && (leftDown || rightDown)) return false;
        _awaitingMouseRelease = false;
        return true;
    }
    private static void ResetSession()
    {
        Close(); _query = _selected = ""; _page = _detailScroll = 0; _favoritesOnly = false;
        _known = Array.Empty<GeneratedItemData>(); History.Clear();
        Array.Clear(DetailParentIdentities); Array.Clear(DetailNativeParents);
        _effectFilter = RecipeJournalView.EffectFilter.All; _ingredientFilter = "";
        _snapshotTick = uint.MaxValue; _hoverText = ""; ResetLineage();
        _sessionOwner = null; _sessionWorld = 0; _awaitingMouseRelease = false;
    }
    public override void OnWorldUnload() => ResetSession();
    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        int index = layers.FindIndex(layer => layer.Name == "Vanilla: Inventory");
        if (index >= 0) layers.Insert(Math.Min(index + 2, layers.Count), new LegacyGameInterfaceLayer("InfiniCrafterLocal: Recipe Journal", Draw, InterfaceScaleType.UI));
    }
    private static void Select(string id, bool remember = true)
    {
        if (remember && _selected.Length != 0 && (_selected != id || _lineageOpen))
        {
            if (History.Count >= 32) History.Clear();
            History.Push(new(_selected, _lineageOpen));
        }
        _selected = id; _lineageOpen = _lineageBrowserPending = false; _detailScroll = 0; SetSearchFocus(false);
    }
    private static bool Draw()
    {
        if (!IsOpen) return true;
        if (!ReferenceEquals(_sessionOwner, Main.LocalPlayer) || _sessionWorld != Main.worldID) { ResetSession(); return true; }
        if (Main.gameMenu || !Main.playerInventory || Main.LocalPlayer.dead) { Close(); return true; }
        if (!CanResumeInput(IsCovered(), Main.mouseLeft, Main.mouseRight)) return true;
        if (Main.keyState.IsKeyDown(Keys.Escape) && Main.oldKeyState.IsKeyUp(Keys.Escape)) { Close(); return true; }
        _hoverText = "";
        var player = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();

        // Snapshot is refreshed outside per-entry drawing, never through generator HTTP.
        if (_snapshotTick == uint.MaxValue || unchecked(Main.GameUpdateCount - _snapshotTick) >= 60)
        {
            _known = InfiniCrafterLocalMod.GeneratedItems?.Snapshot() ?? Array.Empty<GeneratedItemData>();
            _snapshotTick = Main.GameUpdateCount;
        }
        if (_searchFocus)
        {
            Main.blockInput = true; PlayerInput.WritingText = true; Main.instance.HandleIME();
            string query = Main.GetInputText(_query);
            query = query[..Math.Min(query.Length, 80)];
            if (query != _query) { _query = query; _page = 0; }
        }
        if (_lineageOpen) return DrawLineage(Main.spriteBatch);
        ClearLineageHover();
        var discoveries = RecipeJournalView.Entries(_known, Main.worldID.ToString(), "", player.IsJournalFavorite, false);
        var entries = RecipeJournalView.Entries(discoveries, Main.worldID.ToString(), _query, player.IsJournalFavorite, _favoritesOnly)
            .Where(d => RecipeJournalView.MatchesEffect(d, _effectFilter)
                && (_ingredientFilter.Length == 0 || d.RecipeMeta.ParentIdentities?.Contains("generated:" + _ingredientFilter, StringComparer.Ordinal) == true)).ToArray();
        if (_selected.Length == 0 && entries.Length > 0)
        {
            // Hydration may finish while the player is typing; auto-selection must not steal focus.
            _selected = entries[0].Id; _detailScroll = 0;
        }
        // InterfaceScaleType.UI already applies PlayerInput.SetZoom_UI to screen and mouse.
        int width = Main.screenWidth, height = Main.screenHeight;
        var layout = RecipeJournalView.Bounds(width, height);
        Rectangle book = layout.Book;
        var controls = RecipeJournalView.BookControls(layout);
        Vector2 cursor = new Vector2(Main.mouseX, Main.mouseY);
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        if (book.Contains(cursor.ToPoint()))
        { Main.LocalPlayer.mouseInterface = true; PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Recipe Journal"); }
        if (click && !book.Contains(cursor.ToPoint())) SetSearchFocus(false);
        var sb = Main.spriteBatch;
        Fill(sb, new Rectangle(0, 0, width, height), new Color(0, 0, 0, 75));
        if (book.Width < 40 || book.Height < 80) { SetSearchFocus(false); return true; }
        DrawBook(sb, book);
        if (book.Width < 260 || book.Height < 240 || layout.Rows == 0 || layout.Columns == 0)
        {
            SetSearchFocus(false);
            Label(sb, Text("Title"), book.TopLeft() + new Vector2(24, 18), Gold, 0.75f, book.Width - 48);
            if (Button(sb, new Rectangle(book.X + 12, book.Y + Math.Min(62, book.Height - 34), Math.Max(0, book.Width - 24), 24), Text("Close"), click, cursor)) Close();
            if (book.Height >= 140) Paragraph(sb, Text("SpaceHint"), new Rectangle(book.X + 24, book.Y + 102, book.Width - 48, book.Height - 126), Muted, 0.65f);
            if (click && book.Contains(cursor.ToPoint())) Main.mouseLeftRelease = false;
            return true;
        }
        Label(sb, Text("Title"), new Vector2(book.X + 36, book.Y + 17), Gold, 0.85f, book.Width - 110);
        if (LineageButton(sb, controls.Close, "×", click, cursor)) { Close(); return true; }
        Rectangle search = controls.Search;
        DrawPaperSlip(sb, search, _searchFocus);
        Label(sb, _query.Length == 0 ? Text("Search") : _query + (_searchFocus && Main.GameUpdateCount % 60 < 30 ? "|" : ""), search.TopLeft() + new Vector2(8, 5), _query.Length == 0 ? Muted : Ink, 0.65f, search.Width - 16);
        if (click && search.Contains(cursor.ToPoint())) { SetSearchFocus(true); Main.mouseLeftRelease = false; }
        else if (click) SetSearchFocus(false);
        if (_searchFocus && Main.keyState.IsKeyDown(Keys.Enter)) SetSearchFocus(false);
        Rectangle favorites = controls.Favorites;
        if (Button(sb, favorites, _favoritesOnly ? Text("All") : Text("Favorites"), click, cursor, selected: _favoritesOnly)) { _favoritesOnly = !_favoritesOnly; _page = 0; }
        if (layout.Detail.X > layout.List.Right)
            Label(sb, Text("Count", discoveries.Length), new Vector2(layout.Detail.X + 12, search.Y + 5), Muted, 0.65f, layout.Detail.Width - 24);
        var effectButton = controls.Filter;
        if (Button(sb, effectButton, Text("Filter" + _effectFilter), click, cursor))
        { _effectFilter = (RecipeJournalView.EffectFilter)(((int)_effectFilter + 1) % 5); _page = 0; }
        if (_ingredientFilter.Length > 0)
        {
            var clear = controls.ClearIngredient;
            var ingredient = discoveries.FirstOrDefault(d => d.Id == _ingredientFilter);
            if (Button(sb, clear, Text("UsingIngredient", ingredient?.Name ?? _ingredientFilter), click, cursor, selected: true))
            { _ingredientFilter = ""; _page = 0; }
        }
        Rectangle list = layout.List;
        int capacity = Math.Max(1, layout.Rows * layout.Columns);
        int pages = Math.Max(1, (entries.Length + capacity - 1) / capacity);
        _page = Math.Clamp(_page, 0, pages - 1);
        for (int i = 0; i < layout.Rows * layout.Columns; i++)
        {
            var slot = new Rectangle(list.X + i % layout.Columns * 52, list.Y + i / layout.Columns * 52, 48, 48);
            int entryIndex = _page * capacity + i;
            GeneratedItemData? entry = entryIndex < entries.Length ? entries[entryIndex] : null;
            if (entry is null) continue;
            bool active = entry.Id == _selected;
            bool hover = slot.Contains(cursor.ToPoint());
            ItemSlotBackground(sb, slot, active, hover);
            Sprite(sb, entry, new Rectangle(slot.X + 6, slot.Y + 6, 36, 36));
            if (player.IsJournalFavorite(entry.Id)) Label(sb, "★", new Vector2(slot.Right - 14, slot.Y + 1), Gold, 0.5f, 14);
            if (hover) _hoverText = entry.Name + "\n" + entry.ParentA + " + " + entry.ParentB;
            if (click && hover) { Select(entry.Id); Main.mouseLeftRelease = false; }
        }
        int wheel = PlayerInput.ScrollWheelDeltaForUI;
        if (wheel != 0 && list.Contains(cursor.ToPoint())) _page = Math.Clamp(_page + (wheel < 0 ? 1 : -1), 0, pages - 1);
        if (wheel != 0 && layout.Detail.Contains(cursor.ToPoint())) _detailScroll = Math.Max(0, _detailScroll + (wheel < 0 ? 2 : -2));
        if (entries.Length == 0)
        {
            DrawPaperSlip(sb, list);
            Paragraph(sb, Text(_ingredientFilter.Length > 0 || _effectFilter != RecipeJournalView.EffectFilter.All ? "NoMatches" : _favoritesOnly ? "NoFavorites" : _query.Length == 0 ? "Empty" : "NoMatches"), new Rectangle(list.X + 10, list.Y + 10, list.Width - 20, list.Height - 20), Muted, 0.65f);
        }
        GeneratedItemData? selected = discoveries.FirstOrDefault(d => d.Id == _selected);
        if (selected is not null) DrawDetail(sb, selected, layout.Detail, player, click, cursor);
        else
        {
            DrawPaperSlip(sb, layout.Detail);
            Paragraph(sb, Text("Welcome"), new Rectangle(layout.Detail.X + 16, layout.Detail.Y + 16, layout.Detail.Width - 32, layout.Detail.Height - 32), Muted, 0.7f);
        }
        int bottom = book.Bottom - 70;
        if (Button(sb, controls.Previous, "‹", click, cursor, enabled: _page > 0)) _page--;
        CenterLabel(sb, Text("Page", _page + 1, pages), controls.Page, Ink, 0.6f);
        if (Button(sb, controls.Next, "›", click, cursor, enabled: _page + 1 < pages)) _page++;
        if (layout.Detail.X > layout.List.Right) Label(sb, Text("ReadOnly"), new Vector2(layout.Detail.X + 12, bottom + 3), Muted, 0.55f, layout.Detail.Width - 24);
        // In stacked layouts the pager owns the bottom-right corner.
        if (layout.Detail.X > layout.List.Right) DrawBookFold(sb, book);
        if (click && book.Contains(cursor.ToPoint())) Main.mouseLeftRelease = false;
        if (_hoverText.Length > 0) Main.instance.MouseText(_hoverText);
        return true;
    }
    private static void DrawDetail(SpriteBatch sb, GeneratedItemData data, Rectangle area, InfiniCraftPlayer player, bool click, Vector2 cursor)
    {
        if (area.Width < 60 || area.Height < 40) return;
        for (int i = 0; i < DetailNativeParents.Length; i++)
        {
            string identity = data.RecipeMeta.ParentIdentities is { } identities && i < identities.Length ? identities[i] : "";
            if (string.Equals(DetailParentIdentities[i], identity, StringComparison.Ordinal)) continue;
            DetailParentIdentities[i] = identity;
            DetailNativeParents[i] = RecipeNativeItemResolver.ResolveParent(data, i);
        }
        DrawPaperSlip(sb, area);
        int x = area.X + 12, y = area.Y + 10, w = area.Width - 24;
        // Keep navigation and save reachable even in the short stacked layout.
        var controls = RecipeJournalView.DetailControls(area);
        if (History.Count > 0 && Button(sb, controls.Back, Text("Back"), click, cursor)) { GoBack(); return; }
        if (Button(sb, controls.Save, player.IsJournalFavorite(data.Id) ? Text("Saved") : Text("Save"), click, cursor, selected: player.IsJournalFavorite(data.Id))) player.ToggleJournalFavorite(data.Id);
        y = controls.Save.Bottom + 6;
        var children = RecipeJournalView.Children(data, _known);
        if (area.Bottom - y >= 26 && Button(sb, new Rectangle(x, y, w, 24), Text("Children", children.Length), click, cursor,
                enabled: children.Length > 0))
        { _ingredientFilter = data.Id; _effectFilter = RecipeJournalView.EffectFilter.All; _favoritesOnly = false; _query = ""; _page = 0; SetSearchFocus(false); }
        y += 30;
        if (area.Bottom - y >= 26 && Button(sb, new Rectangle(x, y, w, 24), Text("Lineage"), click, cursor))
        { OpenLineage(data); return; }
        y += 30;
        if (area.Height < 230)
        {
            if (area.Bottom - y >= 20) Label(sb, data.Name, new Vector2(x, y), Ink, 0.7f, w);
            if (area.Bottom - y >= 45)
                Paragraph(sb, data.ParentA + " + " + data.ParentB, new Rectangle(x, y + 25, w, Math.Max(0, area.Bottom - y - 30)), Muted, 0.6f);
            return;
        }
        Label(sb, data.Name, new Vector2(x, y), Ink, 0.85f, w);
        if (new Rectangle(x, y, w, 25).Contains(cursor.ToPoint())) _hoverText = data.Name;
        y += 26;
        // Reserve generation, diagram captions, and bottom padding before choosing the tall diagram.
        bool compact = area.Width < 360 || area.Bottom - y < 28 + 148 + 26;
        if (!compact)
        {
            Label(sb, Text("Generation", data.RecipeMeta.GenerationDepth), new Vector2(x, y), Muted, 0.58f, w);
            y += 28;
        }
        int inputSize = compact ? 36 : 44, outputSize = compact ? 48 : 72;
        int diagramHeight = compact ? 66 : 148;
        int inputX = x + 10, outputX = x + w - outputSize - 20;
        var result = new Rectangle(outputX, compact ? y + 3 : y + (diagramHeight - outputSize) / 2, outputSize, outputSize);
        Rectangle inputA = new(inputX, compact ? y + 9 : y + 10, inputSize, inputSize);
        Rectangle inputB = compact
            ? new Rectangle(inputX + inputSize + 18, inputA.Y, inputSize, inputSize)
            : new Rectangle(inputX, y + diagramHeight - inputSize - 14, inputSize, inputSize);
        // Two ingredients converge on the selected recipe seal.
        int joinX = result.X - (compact ? 22 : 34);
        if (compact)
        {
            int railY = y + 3;
            Trace(sb, new Vector2(inputA.Center.X, inputA.Y), new Vector2(inputA.Center.X, railY), Link);
            Trace(sb, new Vector2(inputA.Center.X, railY), new Vector2(joinX, railY), Link);
            Trace(sb, new Vector2(joinX, railY), new Vector2(joinX, result.Center.Y), Link);
            Trace(sb, new Vector2(inputB.Right, inputB.Center.Y), new Vector2(joinX, result.Center.Y), Link);
        }
        else
        {
            int routeX = Math.Max(inputA.Right + 12, joinX - 22);
            Trace(sb, new Vector2(inputA.Right, inputA.Center.Y), new Vector2(routeX, inputA.Center.Y), Rule);
            Trace(sb, new Vector2(inputB.Right, inputB.Center.Y), new Vector2(routeX, inputB.Center.Y), Rule);
            Trace(sb, new Vector2(routeX, inputA.Center.Y), new Vector2(joinX, result.Center.Y), Link);
            Trace(sb, new Vector2(routeX, inputB.Center.Y), new Vector2(joinX, result.Center.Y), Link);
        }
        Trace(sb, new Vector2(joinX, result.Center.Y), new Vector2(result.X, result.Center.Y), Link);
        for (int p = 0; p < 2; p++)
        {
            Rectangle slot = p == 0 ? inputA : inputB;
            GeneratedItemData? parent = RecipeJournalView.Parent(data, p, _known);
            bool hover = slot.Contains(cursor.ToPoint());
            ItemSlotBackground(sb, slot, false, hover && parent is not null);
            if (parent is not null) Sprite(sb, parent, new Rectangle(slot.X + 5, slot.Y + 5, slot.Width - 10, slot.Height - 10));
            else if (DetailNativeParents[p] is { } native)
                DrawNativeLineageSprite(sb, native, new Rectangle(slot.X + 5, slot.Y + 5, slot.Width - 10, slot.Height - 10));
            else CenterLabel(sb, "?", slot, Muted, 0.7f);
            if (!compact)
            {
                string name = p == 0 ? data.ParentA : data.ParentB;
                int nameWidth = Math.Max(0, joinX - slot.Right - 28);
                Label(sb, name, new Vector2(slot.Right + 10, slot.Y + 2), parent is null ? Muted : Link, 0.6f, nameWidth);
            }
            if (hover) _hoverText = (p == 0 ? data.ParentA : data.ParentB) + (parent is null ? "" : "\n" + Text("OpenParent"));
            if (parent is not null && click && hover) { Select(parent.Id); return; }
        }
        ItemSlotBackground(sb, result, true, result.Contains(cursor.ToPoint()));
        Sprite(sb, data, new Rectangle(result.X + 7, result.Y + 7, result.Width - 14, result.Height - 14));
        if (result.Contains(cursor.ToPoint())) _hoverText = data.Name;
        Label(sb, Text("Ingredients"), new Vector2(inputX, y + diagramHeight - 7), Muted, 0.55f, result.X - inputX - 12);
        CenterLabel(sb, Text("Result"), new Rectangle(result.X - 28, y + diagramHeight - 7, result.Width + 40, 20), Ink, 0.55f);
        y += diagramHeight + 18;
        // Names remain readable outside the tiny wells; only exact generated parents are clickable.
        string parents = data.ParentA + " + " + data.ParentB;
        if (compact && y + 22 <= area.Bottom - 10)
        {
            Label(sb, parents, new Vector2(x, y), Link, 0.62f, w);
            if (new Rectangle(x, y, w, 23).Contains(cursor.ToPoint())) _hoverText = parents;
            y += 30;
        }
        if (y + 58 > area.Bottom - 10) return;
        Fill(sb, new Rectangle(x, y, w, 1), Rule); y += 12;
        Label(sb, Text("Notes"), new Vector2(x, y), Ink, 0.62f, w); y += 23;
        string description = data.GeneratedParentSummary.PlayerExperience;
        if (string.IsNullOrWhiteSpace(description)) description = data.GeneratedParentSummary.Description;
        Paragraph(sb, description, new Rectangle(x, y, w, Math.Max(0, area.Bottom - y - 12)), Muted, 0.65f, true);
    }
    private static void Sprite(SpriteBatch sb, GeneratedItemData data, Rectangle bounds)
    {
        Texture2D? texture = InfiniCrafterLocalMod.Sprites?.TryGet(data.Visual.SpritePath);
        if (texture is null)
        {
            // A visible pending asset marker, never a substitute item or synchronous load.
            CenterLabel(sb, "…", new Rectangle(bounds.X, bounds.Center.Y - 9, bounds.Width, 20), Ink, .65f);
            return;
        }
        float scale = Math.Min(1f, Math.Min(bounds.Width / (float)texture.Width, bounds.Height / (float)texture.Height));
        sb.Draw(texture, bounds.Center.ToVector2(), null, Color.White, 0f, texture.Size() * 0.5f, scale, SpriteEffects.None, 0f);
    }
    private static void Fill(SpriteBatch sb, Rectangle rect, Color color)
    { if (rect.Width > 0 && rect.Height > 0) sb.Draw(TextureAssets.MagicPixel.Value, rect, SolidPixelSource, PremultipliedUiColor(color)); }
    private static void Label(SpriteBatch sb, string text, Vector2 at, Color color, float scale, int width)
    {
        if (width <= 0) return;
        var font = FontAssets.MouseText.Value;
        text = ClipLineageLabel(text ?? "", width / scale);
        sb.DrawString(font, text, at, color, 0, Vector2.Zero, scale, SpriteEffects.None, 0);
    }
    private static void Paragraph(SpriteBatch sb, string text, Rectangle rect, Color color, float scale, bool scroll = false)
    {
        if (rect.Height < 20 || rect.Width <= 0) return;
        if (scroll) rect.Width -= 9; // Reserve the track before wrapping, never truncate wrapped words.
        if (rect.Width <= 0) return;
        var rows = GeneratedItem.WrapRuntimeTooltipLines(text ?? "", rect.Width / scale, value => FontAssets.MouseText.Value.MeasureString(value).X);
        int start = scroll ? Math.Clamp(_detailScroll, 0, Math.Max(0, rows.Count - Math.Max(1, rect.Height / 23))) : 0;
        if (scroll) _detailScroll = start;
        if (scroll && rows.Count > Math.Max(1, rect.Height / 23))
        {
            int visible = Math.Max(1, rect.Height / 23);
            int track = rect.Height;
            Fill(sb, new Rectangle(rect.Right + 7, rect.Y, 2, track), Rule);
            int thumb = Math.Max(8, track * visible / rows.Count);
            Fill(sb, new Rectangle(rect.Right + 7, rect.Y + (track - thumb) * start / Math.Max(1, rows.Count - visible), 2, thumb), Muted);
        }
        int line = 0;
        foreach (string row in rows.Skip(start))
        {
            if ((line + 1) * 23 > rect.Height) break;
            Label(sb, row, rect.TopLeft() + new Vector2(0, line++ * 23), color, scale, rect.Width);
        }
    }
    private static void ItemSlotBackground(SpriteBatch sb, Rectangle rect, bool selected, bool hover)
        => DrawBookWell(sb, rect, selected, hover);
    internal static readonly Rectangle SolidPixelSource = new(0, 0, 1, 1);
    internal static Color PremultipliedUiColor(Color color)
        => Color.FromNonPremultiplied(color.R, color.G, color.B, color.A);
    internal static Vector2 CenteredTextPosition(Rectangle bounds, Vector2 size)
        => bounds.Center.ToVector2() - size * .5f;
    private static void Trace(SpriteBatch sb, Vector2 from, Vector2 to, Color color)
    {
        Vector2 delta = to - from;
        if (delta.LengthSquared() <= 0f) return;
        // MagicPixel is 1x1000 in Terraria, not a 1x1 texture. Sampling the
        // whole asset makes each connector a thousand-pixel-wide strip.
        sb.Draw(TextureAssets.MagicPixel.Value, from, SolidPixelSource, PremultipliedUiColor(color), MathF.Atan2(delta.Y, delta.X), new Vector2(0, .5f), new Vector2(delta.Length(), 1), SpriteEffects.None, 0f);
    }
    private static void CenterLabel(SpriteBatch sb, string text, Rectangle rect, Color color, float scale)
    {
        if (rect.Width <= 0 || rect.Height <= 0) return;
        text = ClipLineageLabel(text, rect.Width / scale);
        var font = FontAssets.MouseText.Value;
        Vector2 size = font.MeasureString(text) * scale;
        sb.DrawString(font, text, CenteredTextPosition(rect, size), color, 0, Vector2.Zero, scale, SpriteEffects.None, 0);
    }
    private static bool Button(SpriteBatch sb, Rectangle rect, string text, bool click, Vector2 cursor, bool enabled = true, bool selected = false)
    {
        bool hover = enabled && rect.Contains(cursor.ToPoint());
        if (rect.Width <= 0 || rect.Height <= 0) return false;
        Fill(sb, rect, selected ? new Color(139, 54, 39) : hover ? new Color(202, 169, 103, 190) : new Color(177, 144, 86, enabled ? 100 : 40));
        Fill(sb, new Rectangle(rect.X, rect.Y, rect.Width, 1), new Color(239, 216, 159, 160));
        Fill(sb, new Rectangle(rect.X, rect.Bottom - 1, rect.Width, 1), Rule);
        CenterLabel(sb, text, new Rectangle(rect.X + 5, rect.Y + 4, rect.Width - 10, rect.Height - 8), selected ? new Color(255, 230, 184) : enabled ? Ink : Muted, 0.6f);
        if (hover) _hoverText = text;
        return click && hover;
    }
}
