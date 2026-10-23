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
        => ToggleJournalKey = KeybindLoader.RegisterKeybind(Mod, "ToggleRecipeJournal", Keys.K);

    public override void Unload() => ToggleJournalKey = null!;

    internal static bool CanToggleFromKey(bool focused, bool menu, bool dead, bool writing,
        bool chat, bool blocked, bool rebinding)
        => focused && !menu && !dead && !writing && !chat && !blocked && !rebinding;

    public override void PostUpdateInput()
    {
        if (ToggleJournalKey?.JustPressed != true || Main.LocalPlayer is not { active: true } player
            || !CanToggleFromKey(Main.hasFocus, Main.gameMenu, player.dead, PlayerInput.WritingText,
                Main.drawingPlayerChat, Main.blockInput, PlayerInput.CurrentlyRebinding)) return;
        if (IsOpen) Close();
        else
        {
            Open();
            if ((Main.keyState.IsKeyDown(Keys.LeftShift) || Main.keyState.IsKeyDown(Keys.RightShift))
                && player.HeldItem?.ModItem is GeneratedItem held
                && InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.IsCurrentWorldData(held.Data)
                && !GeneratedItemData.IsPlayerSaveReferenceOnly(held.Data))
            {
                _query = ""; _favoritesOnly = false; _ingredientFilter = "";
                _effectFilter = RecipeJournalView.EffectFilter.All; _page = 0;
                Select(held.Data.Id);
            }
        }
    }
    private static string _query = "", _selected = "";
    private static string _comparisonId = "";
    private enum DetailPage { Recipe, Comparison, Ancestors, Descendants, Inventory, Plan, Notebook, Discovery, Guide, Help }
    private static DetailPage _detailPage;
    private static bool _workspaceMenu;
    private static int _workspaceScroll;
    private static bool _searchFocus, _favoritesOnly, _noteFocus;
    private static RecipeJournalView.EffectFilter _effectFilter;
    private static string _ingredientFilter = "";
    private static int _page, _detailScroll;
    private static bool _revealSelection, _unreadOnly;
    private static RecipeJournalView.SortOrder _sortOrder;
    private static GeneratedItemData[] _known = Array.Empty<GeneratedItemData>();
    private static uint _snapshotTick;
    private static readonly Stack<string> History = new();
    // InfiniCore identity: cold forged metal, a warm fusion heart, quiet navigable blue.
    private static readonly Color Ink = new(243, 231, 209), Muted = new(161, 174, 193), Gold = new(241, 170, 77);
    private static readonly Color Panel = new(20, 24, 34), Inset = new(11, 16, 25);
    private static readonly Color Metal = new(65, 72, 84), Bronze = new(128, 98, 62), Link = new(139, 204, 212);
    private static string _hoverText = "";
    internal static string Text(string key, params object[] args)
        => Language.GetTextValue("Mods.InfiniCrafterLocal.RecipeJournal." + key, args);

    public static void Open()
    {
        IsOpen = true; SetSearchFocus(false); _snapshotTick = uint.MaxValue;
        Main.playerInventory = true;
        if (Main.netMode == Terraria.ID.NetmodeID.MultiplayerClient)
            InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer();
    }
    private static void SetSearchFocus(bool focused)
    {
        if (_searchFocus && !focused && !_noteFocus) PlayerInput.WritingText = false;
        if (focused) _noteFocus = false;
        _searchFocus = focused;
        Main.blockInput = focused;
    }
    internal static void Close() { IsOpen = false; SetNoteFocus(false); SetSearchFocus(false); }
    private static void SetNoteFocus(bool focused)
    {
        if (_noteFocus && !focused) PlayerInput.WritingText = false;
        _noteFocus = focused; Main.blockInput = _searchFocus || focused;
    }
    public override void OnWorldUnload()
    {
        Close(); _query = _selected = _comparisonId = ""; _detailPage = DetailPage.Recipe; _page = 0; _favoritesOnly = false; _revealSelection = false; _sortOrder = RecipeJournalView.SortOrder.Name;
        _known = Array.Empty<GeneratedItemData>(); History.Clear(); _unreadOnly = false; _workspaceMenu = false; _workspaceScroll = 0;
        _effectFilter = RecipeJournalView.EffectFilter.All; _ingredientFilter = "";
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
        if (Main.LocalPlayer is { active: true } local && _known.Any(d => d.Id == id && d.RecipeMeta.WorldId == Main.worldID.ToString()))
            local.GetModPlayer<InfiniCraftPlayer>().VisitJournalRecipe(id);
        _selected = id; SetNoteFocus(false); _detailScroll = 0; _revealSelection = true; SetSearchFocus(false); Main.blockInput = false;
    }
    private static bool Draw()
    {
        if (!IsOpen) return true;
        if (Main.gameMenu || !Main.playerInventory || Main.LocalPlayer.dead) { Close(); return true; }
        if (Main.hideUI || Main.mapFullscreen || Main.ingameOptionsWindow || Main.inFancyUI || !Main.hasFocus)
        { SetNoteFocus(false); SetSearchFocus(false); return true; }
        if (Main.hasFocus && Main.keyState.IsKeyDown(Keys.Escape) && Main.oldKeyState.IsKeyUp(Keys.Escape))
        {
            if (_workspaceMenu) { _workspaceMenu = false; return true; }
            if (_noteFocus) { SetNoteFocus(false); return true; }
            if (_searchFocus) { SetSearchFocus(false); return true; }
            Close(); return true;
        }
        if (Main.hasFocus && !Main.drawingPlayerChat && !PlayerInput.CurrentlyRebinding
            && (!PlayerInput.WritingText || _searchFocus)
            && (Main.keyState.IsKeyDown(Keys.LeftControl) || Main.keyState.IsKeyDown(Keys.RightControl))
            && Main.keyState.IsKeyDown(Keys.F) && Main.oldKeyState.IsKeyUp(Keys.F)) SetSearchFocus(true);
        _hoverText = "";
        var player = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
        Main.LocalPlayer.mouseInterface = true;
        PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Recipe Journal");
        // Snapshot is refreshed outside per-entry drawing, never through generator HTTP.
        if (_snapshotTick == uint.MaxValue || unchecked(Main.GameUpdateCount - _snapshotTick) >= 60)
        {
            _known = InfiniCrafterLocalMod.GeneratedItems?.Snapshot() ?? Array.Empty<GeneratedItemData>();
            _snapshotTick = Main.GameUpdateCount;
        }
        Main.blockInput = _searchFocus || _noteFocus;
        if (_searchFocus)
        {
            PlayerInput.WritingText = true; Main.instance.HandleIME();
            string query = Main.GetInputText(_query);
            query = query[..Math.Min(query.Length, 80)];
            if (query != _query) { _query = query; _page = 0; }
        }
        var discoveries = RecipeJournalView.Entries(_known, Main.worldID.ToString(), "", player.IsJournalFavorite, false);
        var entries = RecipeJournalView.Entries(discoveries, Main.worldID.ToString(), _query, player.IsJournalFavorite, _favoritesOnly, player.JournalNote, player.JournalCollection)
            .Where(d => (!_unreadOnly || player.JournalLastVisited(d.Id) == 0) && RecipeJournalView.MatchesEffect(d, _effectFilter)
                && (_ingredientFilter.Length == 0 || d.RecipeMeta.ParentIdentities?.Contains("generated:" + _ingredientFilter, StringComparer.Ordinal) == true)).ToArray();
        entries = RecipeJournalView.Sort(entries, _sortOrder, player.IsJournalFavorite, player.JournalLastVisited);
        if (_selected.Length == 0 && entries.Length > 0)
        {
            // Hydration may finish while the player is typing; auto-selection must not steal focus.
            _selected = entries[0].Id; _detailScroll = 0;
        }
        // InterfaceScaleType.UI already applies PlayerInput.SetZoom_UI to screen and mouse.
        int width = Main.screenWidth, height = Main.screenHeight;
        var layout = RecipeJournalView.Bounds(width, height);
        Rectangle book = layout.Book;
        Vector2 cursor = new Vector2(Main.mouseX, Main.mouseY);
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        if (click && !book.Contains(cursor.ToPoint())) { SetSearchFocus(false); Main.mouseLeftRelease = false; }
        var sb = Main.spriteBatch;
        Fill(sb, new Rectangle(0, 0, width, height), new Color(0, 0, 0, 75));
        if (book.Width < 40 || book.Height < 80) { SetSearchFocus(false); if (click) Main.mouseLeftRelease = false; return true; }
        Chassis(sb, book, Panel);
        CornerClamps(sb, new Rectangle(book.X + 3, book.Y + 3, book.Width - 6, book.Height - 6), Bronze);
        if (book.Width < 260 || book.Height < 240 || layout.Rows == 0 || layout.Columns == 0)
        {
            SetSearchFocus(false);
            Label(sb, Text("Title"), book.TopLeft() + new Vector2(12, 12), Ink, 0.75f, book.Width - 24);
            if (Button(sb, new Rectangle(book.X + 12, book.Y + 42, Math.Max(0, book.Width - 24), 28), Text("Close"), click, cursor)) Close();
            if (book.Height >= 140) Paragraph(sb, Text("SpaceHint"), new Rectangle(book.X + 12, book.Y + 82, book.Width - 24, book.Height - 96), Muted, 0.65f);
            if (click) Main.mouseLeftRelease = false;
            return true;
        }
        DrawCoreBadge(sb, new Rectangle(book.X + 13, book.Y + 5, 30, 30));
        Label(sb, Text("Title"), new Vector2(book.X + 50, book.Y + 9), Ink, 0.85f, book.Width - 102);
        Fill(sb, new Rectangle(book.X + 14, book.Y + 36, book.Width - 28, 1), Metal);
        if (Button(sb, new Rectangle(book.Right - 38, book.Y + 8, 26, 26), "×", click, cursor)) { Close(); return true; }
        Rectangle search = new(book.X + 12, book.Y + 44, Math.Max(60, layout.List.Width - 110), 30);
        Chassis(sb, search, _searchFocus ? new Color(32, 45, 53) : Inset);
        Label(sb, _query.Length == 0 ? Text("Search") : _query + (_searchFocus && Main.GameUpdateCount % 60 < 30 ? "|" : ""), search.TopLeft() + new Vector2(8, 5), _query.Length == 0 ? Muted : Ink, 0.65f, search.Width - 16);
        if (search.Contains(cursor.ToPoint())) _hoverText = Text("SearchKeys") + "\n" + Text("StructuredSearch");
        if (click && search.Contains(cursor.ToPoint())) { SetSearchFocus(true); Main.mouseLeftRelease = false; }
        else if (click) SetSearchFocus(false);
        if (_searchFocus && Main.keyState.IsKeyDown(Keys.Enter)) SetSearchFocus(false);
        Rectangle favorites = new(search.Right + 6, search.Y, 104, 30);
        if (Button(sb, favorites, _favoritesOnly ? Text("All") : Text("Favorites"), click, cursor, selected: _favoritesOnly)) { _favoritesOnly = !_favoritesOnly; _page = 0; }
        if (layout.Detail.X > layout.List.Right)
            Label(sb, Text("Count", discoveries.Length), new Vector2(layout.Detail.X + 12, search.Y + 5), Muted, 0.65f, layout.Detail.Width - 24);
        var effectButton = new Rectangle(book.X + 12, book.Y + 80, Math.Min(182, book.Width - 24), 26);
        if (Button(sb, effectButton, Text("Filter" + _effectFilter), click, cursor))
        { _effectFilter = (RecipeJournalView.EffectFilter)(((int)_effectFilter + 1) % Enum.GetValues<RecipeJournalView.EffectFilter>().Length); _page = 0; }
        if (_ingredientFilter.Length > 0)
        {
            var clear = new Rectangle(effectButton.Right + 6, effectButton.Y, Math.Max(0, book.Right - effectButton.Right - 18), 26);
            var ingredient = discoveries.FirstOrDefault(d => d.Id == _ingredientFilter);
            if (Button(sb, clear, Text("UsingIngredient", ingredient?.Name ?? _ingredientFilter), click, cursor, selected: true))
            { _ingredientFilter = ""; _page = 0; }
        }
        if (_ingredientFilter.Length == 0 && (_query.Length > 0 || _favoritesOnly || _unreadOnly || _effectFilter != RecipeJournalView.EffectFilter.All))
        {
            var reset = new Rectangle(effectButton.Right + 6, effectButton.Y, Math.Max(0, book.Right - effectButton.Right - 18), 26);
            if (Button(sb, reset, Text("ResetFilters"), click, cursor))
            { _query = ""; _favoritesOnly = false; _unreadOnly = false; _effectFilter = RecipeJournalView.EffectFilter.All; _page = 0; SetSearchFocus(false); }
        }
        Rectangle list = layout.List;
        int capacity = Math.Max(1, layout.Rows * layout.Columns);
        int pages = Math.Max(1, (entries.Length + capacity - 1) / capacity);
        if (_revealSelection)
        {
            int selectedIndex = Array.FindIndex(entries, d => d.Id == _selected);
            if (selectedIndex >= 0) _page = selectedIndex / capacity;
            _revealSelection = false;
        }
        _page = Math.Clamp(_page, 0, pages - 1);
        if (!_searchFocus && Main.hasFocus && !Main.drawingPlayerChat && !Main.blockInput
            && !PlayerInput.WritingText && !PlayerInput.CurrentlyRebinding)
        {
            bool Pressed(Keys key) => Main.keyState.IsKeyDown(key) && Main.oldKeyState.IsKeyUp(key);
            if (Pressed(Keys.PageDown)) _page = Math.Min(pages - 1, _page + 1);
            if (Pressed(Keys.PageUp)) _page = Math.Max(0, _page - 1);
            if (Pressed(Keys.Home)) _page = 0;
            if (Pressed(Keys.End)) _page = pages - 1;
        }
        for (int i = 0; i < layout.Rows * layout.Columns; i++)
        {
            var slot = new Rectangle(list.X + i % layout.Columns * 52, list.Y + i / layout.Columns * 52, 48, 48);
            int entryIndex = _page * capacity + i;
            GeneratedItemData? entry = entryIndex < entries.Length ? entries[entryIndex] : null;
            bool active = entry is not null && entry.Id == _selected;
            bool hover = entry is not null && slot.Contains(cursor.ToPoint());
            ItemSlotBackground(sb, slot, active, hover);
            if (entry is null) continue;
            Sprite(sb, entry, new Rectangle(slot.X + 6, slot.Y + 6, 36, 36));
            if (player.IsJournalFavorite(entry.Id)) Label(sb, "★", new Vector2(slot.Right - 14, slot.Y + 1), Gold, 0.5f, 14);
            if (player.JournalLastVisited(entry.Id) == 0) Label(sb, "•", slot.TopLeft() + new Vector2(3, 1), Link, .7f, 12);
            if (hover) _hoverText = entry.Name + "\n" + entry.ParentA + " + " + entry.ParentB + "\n" + Text("FavoriteHint");
            if (hover && Main.mouseRight && Main.mouseRightRelease && !PlayerInput.IgnoreMouseInterface)
            {
                player.ToggleJournalFavorite(entry.Id);
                Main.mouseRightRelease = false;
            }
            if (click && hover) { Select(entry.Id); Main.mouseLeftRelease = false; }
        }
        int wheel = PlayerInput.ScrollWheelDeltaForUI;
        if (wheel != 0 && list.Contains(cursor.ToPoint())) _page = Math.Clamp(_page + (wheel < 0 ? 1 : -1), 0, pages - 1);
        if (wheel != 0 && layout.Detail.Contains(cursor.ToPoint())) _detailScroll = Math.Max(0, _detailScroll + (wheel < 0 ? 2 : -2));
        if (entries.Length == 0)
        {
            Chassis(sb, list, Inset);
            Paragraph(sb, Text(_ingredientFilter.Length > 0 || _effectFilter != RecipeJournalView.EffectFilter.All ? "NoMatches" : _favoritesOnly ? "NoFavorites" : _query.Length == 0 ? "Empty" : "NoMatches"), new Rectangle(list.X + 10, list.Y + 10, list.Width - 20, list.Height - 20), Muted, 0.65f);
        }
        GeneratedItemData? selected = discoveries.FirstOrDefault(d => d.Id == _selected);
        if (selected is not null) DrawDetail(sb, selected, layout.Detail, player, click, cursor);
        else
        {
            Chassis(sb, layout.Detail, Inset);
            Paragraph(sb, Text("Welcome"), new Rectangle(layout.Detail.X + 16, layout.Detail.Y + 16, layout.Detail.Width - 32, layout.Detail.Height - 32), Muted, 0.7f);
        }
        int bottom = book.Bottom - 29;
        if (new Rectangle(list.X, bottom, list.Width, 24).Contains(cursor.ToPoint())) _hoverText = Text("PageKeys");
        if (Button(sb, new Rectangle(list.X, bottom, 30, 24), "‹", click, cursor, enabled: _page > 0)) _page--;
        if (Button(sb, new Rectangle(list.X + 34, bottom, list.Width - 68, 24),
            Text("Sort" + _sortOrder) + " · " + Text("Page", _page + 1, pages), click, cursor))
        { _sortOrder = (RecipeJournalView.SortOrder)(((int)_sortOrder + 1) % Enum.GetValues<RecipeJournalView.SortOrder>().Length); _page = 0; }
        if (new Rectangle(list.X + 34, bottom, list.Width - 68, 24).Contains(cursor.ToPoint())) _hoverText = Text("SortHint");
        if (Button(sb, new Rectangle(list.Right - 30, bottom, 30, 24), "›", click, cursor, enabled: _page + 1 < pages)) _page++;
        if (layout.Detail.X > layout.List.Right) Label(sb, Text("ReadOnly"), new Vector2(layout.Detail.X + 12, bottom + 3), Muted, 0.55f, layout.Detail.Width - 24);
        if (click && book.Contains(cursor.ToPoint())) Main.mouseLeftRelease = false;
        if (_hoverText.Length > 0) Main.instance.MouseText(_hoverText);
        return true;
    }
    private static void DrawDetail(SpriteBatch sb, GeneratedItemData data, Rectangle area, InfiniCraftPlayer player, bool click, Vector2 cursor)
    {
        if (area.Width < 60 || area.Height < 40) return;
        Chassis(sb, area, Inset);
        int x = area.X + 12, y = area.Y + 10, w = area.Width - 24;
        // Keep navigation and save reachable even in the short stacked layout.
        var controls = RecipeJournalView.DetailControls(area);
        if (History.Count > 0 && Button(sb, controls.Back, Text("Back"), click, cursor)) { Select(History.Pop(), false); return; }
        if (Button(sb, controls.Save, player.IsJournalFavorite(data.Id) ? Text("Saved") : Text("Save"), click, cursor, selected: player.IsJournalFavorite(data.Id))) player.ToggleJournalFavorite(data.Id);
        y = controls.Save.Bottom + 6;
        var children = RecipeJournalView.Children(data, _known);
        if (area.Bottom - y >= 26 && Button(sb, new Rectangle(x, y, w, 24), Text("Children", children.Length), click, cursor,
                enabled: children.Length > 0))
        { _ingredientFilter = data.Id; _effectFilter = RecipeJournalView.EffectFilter.All; _favoritesOnly = false; _query = ""; _page = 0; SetSearchFocus(false); }
        y += 30;
        if (area.Bottom - y >= 60)
        {
            int half = (w - 12) / 3;
            if (Button(sb, new Rectangle(x, y, half, 24), Text("View" + _detailPage), click, cursor))
            { SetNoteFocus(false); _workspaceMenu = !_workspaceMenu; _workspaceScroll = 0; }
            if (Button(sb, new Rectangle(x + half + 6, y, half, 24), Text(_comparisonId == data.Id ? "ReferenceSet" : "SetReference"), click, cursor))
            { _comparisonId = data.Id; _detailPage = DetailPage.Comparison; _detailScroll = 0; }
            if (Button(sb, new Rectangle(x + (half + 6) * 2, y, w - (half + 6) * 2, 24), Text(player.IsJournalPinned(data.Id) ? "UnpinGoal" : "PinGoal"), click, cursor))
            {
                if (!player.ToggleJournalPin(data.Id)) _hoverText = Text("PinLimit");
            }
            y += 30;
            if (DrawWorkspacePicker(sb, new Rectangle(x, y, w, area.Bottom - y - 10), click, cursor)) return;
            if (DrawAnalysisPage(sb, data, new Rectangle(x, y, w, area.Bottom - y - 10), click, cursor)) return;
        }
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
        bool compact = area.Height < 300 || area.Width < 360;
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
        // Two inputs converge into the core cradle: this is a read-only provenance diagram.
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
            Trace(sb, new Vector2(inputA.Right, inputA.Center.Y), new Vector2(routeX, inputA.Center.Y), Metal);
            Trace(sb, new Vector2(inputB.Right, inputB.Center.Y), new Vector2(routeX, inputB.Center.Y), Metal);
            Trace(sb, new Vector2(routeX, inputA.Center.Y), new Vector2(joinX, result.Center.Y), Link);
            Trace(sb, new Vector2(routeX, inputB.Center.Y), new Vector2(joinX, result.Center.Y), Link);
        }
        Trace(sb, new Vector2(joinX, result.Center.Y), new Vector2(result.X, result.Center.Y), Gold);
        // One slow travelling point; no particles, additive bloom, or shader state changes.
        float phase = (Main.GlobalTimeWrappedHourly % 3f) / 3f;
        int sparkX = joinX + (int)((result.X - joinX) * phase);
        Fill(sb, new Rectangle(sparkX, result.Center.Y - 1, 3, 3), new Color(255, 227, 160));
        for (int p = 0; p < 2; p++)
        {
            Rectangle slot = p == 0 ? inputA : inputB;
            GeneratedItemData? parent = RecipeJournalView.Parent(data, p, _known);
            bool hover = slot.Contains(cursor.ToPoint());
            ItemSlotBackground(sb, slot, false, hover && parent is not null);
            if (parent is not null) Sprite(sb, parent, new Rectangle(slot.X + 5, slot.Y + 5, slot.Width - 10, slot.Height - 10));
            else if (RecipeJournalView.NativeParentType(data, p) is > 0 and var nativeType)
            {
                Main.instance.LoadItem(nativeType);
                Texture2D texture = TextureAssets.Item[nativeType].Value;
                Rectangle frame = Main.itemAnimations[nativeType]?.GetFrame(texture) ?? texture.Bounds;
                float scale = Math.Min((slot.Width - 10f) / frame.Width, (slot.Height - 10f) / frame.Height);
                sb.Draw(texture, slot.Center.ToVector2(), frame, Color.White, 0f, frame.Size() * .5f, scale, SpriteEffects.None, 0f);
            }
            else CenterLabel(sb, (p + 1).ToString(), new Rectangle(slot.X + 4, slot.Y + 8, slot.Width - 8, 20), Muted, 0.7f);
            if (!compact)
            {
                string name = p == 0 ? data.ParentA : data.ParentB;
                int nameWidth = Math.Max(0, joinX - slot.Right - 28);
                Label(sb, name, new Vector2(slot.Right + 10, slot.Y + 2), parent is null ? Muted : Link, 0.6f, nameWidth);
            }
            if (hover) _hoverText = (p == 0 ? data.ParentA : data.ParentB) + (parent is null ? "" : "\n" + Text("OpenParent"));
            if (parent is not null && click && hover) { Select(parent.Id); return; }
        }
        // Bracketed result cradle echoes the horns and ember heart of the real InfiniCore.
        Rectangle cradle = new(result.X - 6, result.Y - 6, result.Width + 12, result.Height + 12);
        CornerClamps(sb, cradle, Bronze);
        if (!compact)
        {
            // Original forked metal silhouette, echoing the mod's InfiniCore horns.
            for (int side = -1; side <= 1; side += 2)
            {
                float edge = side < 0 ? result.Left - 8 : result.Right + 8;
                Trace(sb, new Vector2(edge, result.Center.Y - 6), new Vector2(edge + side * 7, result.Y - 8), Bronze);
                Trace(sb, new Vector2(edge + side * 7, result.Y - 8), new Vector2(edge - side * 7, result.Y - 20), Bronze);
                Trace(sb, new Vector2(edge, result.Center.Y + 6), new Vector2(edge + side * 7, result.Bottom + 8), Bronze);
                Trace(sb, new Vector2(edge + side * 7, result.Bottom + 8), new Vector2(edge - side * 7, result.Bottom + 16), Bronze);
            }
        }
        ItemSlotBackground(sb, result, true, result.Contains(cursor.ToPoint()));
        Sprite(sb, data, new Rectangle(result.X + 7, result.Y + 7, result.Width - 14, result.Height - 14));
        if (result.Contains(cursor.ToPoint())) _hoverText = data.Name;
        Label(sb, Text("Ingredients"), new Vector2(inputX, y + diagramHeight - 7), Muted, 0.55f, result.X - inputX - 12);
        CenterLabel(sb, Text("Result"), new Rectangle(result.X - 28, y + diagramHeight - 7, result.Width + 40, 20), Gold, 0.55f);
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
        Fill(sb, new Rectangle(x, y, w, 1), Metal); y += 12;
        Label(sb, Text("Notes"), new Vector2(x, y), Ink, 0.62f, w); y += 23;
        string description = data.GeneratedParentSummary.PlayerExperience;
        if (string.IsNullOrWhiteSpace(description)) description = data.GeneratedParentSummary.Description;
        Paragraph(sb, description, new Rectangle(x, y, w, Math.Max(0, area.Bottom - y - 12)), Muted, 0.65f, true);
    }
    private static void Sprite(SpriteBatch sb, GeneratedItemData data, Rectangle bounds)
    {
        Texture2D? texture = InfiniCrafterLocalMod.Sprites?.TryGet(data.Visual.SpritePath);
        if (texture is null) return; // Assets hydrate through the existing registry, never a fake item.
        float scale = Math.Min(1f, Math.Min(bounds.Width / (float)texture.Width, bounds.Height / (float)texture.Height));
        sb.Draw(texture, bounds.Center.ToVector2(), null, Color.White, 0f, texture.Size() * 0.5f, scale, SpriteEffects.None, 0f);
    }
    private static void Fill(SpriteBatch sb, Rectangle rect, Color color)
    { if (rect.Width > 0 && rect.Height > 0) sb.Draw(TextureAssets.MagicPixel.Value, rect, color); }
    private static void Label(SpriteBatch sb, string text, Vector2 at, Color color, float scale, int width)
    {
        text = (text ?? "").Replace('\n', ' ').Replace('\r', ' ');
        var font = FontAssets.MouseText.Value;
        if (width <= 0) return;
        if (font.MeasureString(text).X * scale > width)
        {
            while (text.Length > 0 && font.MeasureString(text + "…").X * scale > width) text = text[..^1];
            text = text.Length == 0 ? "" : text + "…";
        }
        Utils.DrawBorderStringFourWay(sb, font, text, at.X, at.Y, color, Color.Black, Vector2.Zero, scale);
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
            Fill(sb, new Rectangle(rect.Right + 7, rect.Y, 2, track), new Color(38, 47, 61));
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
    private static void CutFill(SpriteBatch sb, Rectangle rect, int cut, Color color)
    {
        cut = Math.Min(cut, Math.Min(rect.Width, rect.Height) / 2);
        if (rect.Width <= 0 || rect.Height <= 0) return;
        Fill(sb, new Rectangle(rect.X, rect.Y + cut, rect.Width, rect.Height - cut * 2), color);
        for (int i = 0; i < cut; i++)
        {
            int inset = cut - i;
            Fill(sb, new Rectangle(rect.X + inset, rect.Y + i, rect.Width - inset * 2, 1), color);
            Fill(sb, new Rectangle(rect.X + inset, rect.Bottom - i - 1, rect.Width - inset * 2, 1), color);
        }
    }
    private static void Chassis(SpriteBatch sb, Rectangle rect, Color color)
    {
        if (rect.Width <= 0 || rect.Height <= 0) return;
        int cut = rect.Height > 50 ? 7 : 4;
        CutFill(sb, rect, cut, new Color(3, 6, 11));
        CutFill(sb, new Rectangle(rect.X + 1, rect.Y + 1, rect.Width - 2, rect.Height - 2), cut, Metal);
        CutFill(sb, new Rectangle(rect.X + 3, rect.Y + 3, rect.Width - 6, rect.Height - 6), Math.Max(1, cut - 1), color);
        Fill(sb, new Rectangle(rect.X + cut + 2, rect.Y + 3, Math.Max(0, rect.Width - cut * 2 - 4), 1), new Color(48, 56, 68));
    }
    private static void CornerClamps(SpriteBatch sb, Rectangle rect, Color color)
    {
        if (rect.Width < 24 || rect.Height < 24) return;
        const int arm = 10;
        for (int side = 0; side < 2; side++)
        for (int end = 0; end < 2; end++)
        {
            int x = side == 0 ? rect.X : rect.Right - 2;
            int y = end == 0 ? rect.Y + 5 : rect.Bottom - arm - 5;
            Fill(sb, new Rectangle(x, y, 2, arm), color);
            int hx = side == 0 ? rect.X + 5 : rect.Right - arm - 5;
            int hy = end == 0 ? rect.Y : rect.Bottom - 2;
            Fill(sb, new Rectangle(hx, hy, arm, 2), color);
        }
    }
    private static void ItemSlotBackground(SpriteBatch sb, Rectangle rect, bool selected, bool hover)
    {
        Chassis(sb, rect, selected ? new Color(39, 31, 27) : Inset);
        Fill(sb, new Rectangle(rect.X + 8, rect.Bottom - 6, Math.Max(0, rect.Width - 16), 1), selected ? Bronze : Metal);
        if (selected || hover) CornerClamps(sb, rect, selected ? Gold : Link);
    }
    private static void Trace(SpriteBatch sb, Vector2 from, Vector2 to, Color color)
    {
        Vector2 delta = to - from;
        sb.Draw(TextureAssets.MagicPixel.Value, from, null, color, MathF.Atan2(delta.Y, delta.X), Vector2.Zero, new Vector2(delta.Length(), 1), SpriteEffects.None, 0f);
    }
    private static void DrawCoreBadge(SpriteBatch sb, Rectangle rect)
    {
        int type = ModContent.ItemType<InfiniCore>();
        Main.instance.LoadItem(type);
        Texture2D texture = TextureAssets.Item[type].Value;
        Rectangle frame = Main.itemAnimations[type]?.GetFrame(texture) ?? texture.Bounds;
        float scale = Math.Min(rect.Width / (float)frame.Width, rect.Height / (float)frame.Height);
        sb.Draw(texture, rect.Center.ToVector2(), frame, Color.White, 0f, frame.Size() * 0.5f, scale, SpriteEffects.None, 0f);
    }
    private static void CenterLabel(SpriteBatch sb, string text, Rectangle rect, Color color, float scale)
    {
        float textWidth = FontAssets.MouseText.Value.MeasureString(text).X * scale;
        Label(sb, text, new Vector2(rect.X + Math.Max(0, (rect.Width - textWidth) / 2), rect.Y), color, scale, rect.Width);
    }
    private static bool Button(SpriteBatch sb, Rectangle rect, string text, bool click, Vector2 cursor, bool enabled = true, bool selected = false)
    {
        bool hover = enabled && rect.Contains(cursor.ToPoint());
        Chassis(sb, rect, hover ? new Color(43, 51, 61) : selected ? new Color(49, 38, 28) : new Color(26, 32, 43));
        CenterLabel(sb, text, new Rectangle(rect.X + 5, rect.Y + 4, rect.Width - 10, rect.Height - 8), enabled ? selected ? Gold : Ink : new Color(105, 113, 128), 0.6f);
        if (hover) _hoverText = text;
        return click && hover;
    }
}
