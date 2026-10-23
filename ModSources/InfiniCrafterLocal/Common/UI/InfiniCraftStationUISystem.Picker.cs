#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using Terraria;
using Terraria.GameInput;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class InfiniCraftStationUISystem
{
    private static int _pickerSlot = -1, _pickerPage;
    private static string _pickerQuery = "";
    private static bool _pickerSearchFocus, _pickerSortByStack;
    internal static int[] IngredientPickerSlots(Item[] inventory, string query, bool byStack)
    {
        var eligible = Enumerable.Range(0, Math.Min(58, inventory.Length))
            .Where(i => InfiniCore.IsValidIngredient(inventory[i])
                && inventory[i].Name.Contains(query.Trim(), StringComparison.CurrentCultureIgnoreCase));
        return (byStack ? eligible.OrderByDescending(i => inventory[i].stack).ThenBy(i => i)
            : eligible.OrderBy(i => inventory[i].Name, StringComparer.CurrentCultureIgnoreCase).ThenBy(i => i)).ToArray();
    }
    private static void SetPickerSearchFocus(bool focused)
    {
        if (_pickerSearchFocus && !focused) { Main.blockInput = false; PlayerInput.WritingText = false; }
        _pickerSearchFocus = focused;
        if (focused) { Main.blockInput = true; PlayerInput.WritingText = true; }
    }
    private static void ClosePicker() { _pickerSlot = -1; SetPickerSearchFocus(false); }
    private static void OpenPicker(int slot)
    { _pickerSlot = slot; _pickerPage = 0; _pickerQuery = ""; SetPickerSearchFocus(false); }
    public override void OnWorldUnload() => CloseStationModals();
    private static bool _modalInputReserved, _modalLeft, _modalLeftRelease, _modalRight, _modalRightRelease;
    internal static void ReserveStationModalMouse(bool stationPanelHit = false)
    {
        if ((!StationModalVisible && !stationPanelHit) || _modalInputReserved) return;
        _modalInputReserved = true;
        (_modalLeft, _modalLeftRelease, _modalRight, _modalRightRelease) = (Main.mouseLeft, Main.mouseLeftRelease, Main.mouseRight, Main.mouseRightRelease);
        Main.mouseLeft = Main.mouseLeftRelease = Main.mouseRight = Main.mouseRightRelease = false;
        PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Station Modal");
    }
    internal static bool RestoreStationModalMouse()
    {
        if (!_modalInputReserved) return false;
        _modalInputReserved = false;
        (Main.mouseLeft, Main.mouseLeftRelease, Main.mouseRight, Main.mouseRightRelease) = (_modalLeft, _modalLeftRelease, _modalRight, _modalRightRelease);
        return true;
    }
    internal static bool StationModalVisible => _pickerSlot >= 0 || _inspectedItem is not null || _historyOpen;
    internal static bool StationInteractionAvailable(Player? player)
        => player is { active: true, dead: false } && Main.playerInventory && Main.hasFocus
            && !Main.gameMenu && !Main.hideUI && !Main.mapFullscreen && !Main.ingameOptionsWindow
            && !Main.inFancyUI && !Main.drawingPlayerChat && !PlayerInput.CurrentlyRebinding
            && player.chest == -1 && Main.npcShop == 0 && !RecipeJournalUISystem.IsOpen;
    internal static void CloseStationModals()
    { ClosePicker(); _pickerPage = 0; _pickerQuery = ""; _inspectedItem = null; _inspectionScroll = 0; _historyOpen = false; _historyPage = 0; }
    public override void PostUpdateInput()
    {
        if (!StationInteractionAvailable(Main.LocalPlayer)) { CloseStationModals(); return; }
        if (StationModalVisible && Main.keyState.IsKeyDown(Keys.Escape)
            && !Main.oldKeyState.IsKeyDown(Keys.Escape)) CloseStationModals();
    }
    private static void DrawInventoryPicker(SpriteBatch sb, Rectangle station, InfiniCraftPlayer owner)
    {
        if (_pickerSlot >= owner.MultiDevWindowCount * 2 || owner.IsCraftLanePending(_pickerSlot / 2)
            || !owner.StationInput(_pickerSlot).IsAir || !Main.mouseItem.IsAir)
        { ClosePicker(); return; }
        int height = Math.Min(390, Main.screenHeight - 24);
        if (height < 180 || station.Width < 280) { ClosePicker(); return; }
        var panel = new Rectangle(station.X, Math.Clamp(station.Y, 12, Math.Max(12, Main.screenHeight - height - 12)), station.Width, height);
        DrawPanel(sb, panel); Main.LocalPlayer.mouseInterface = true;
        PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Ingredient Picker");
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        var close = new Rectangle(panel.Right - 42, panel.Y + 8, 28, 26);
        DrawButton(sb, close, true, "×");
        if (click && close.Contains(Main.mouseX, Main.mouseY) || Main.keyState.IsKeyDown(Keys.Escape))
        { ClosePicker(); Main.mouseLeftRelease = false; return; }
        DrawFittedText(sb, ForgeText("PickIngredient", _pickerSlot % 2 == 0 ? "A" : "B"), panel.TopLeft() + new Vector2(12, 12), Color.LightSkyBlue, panel.Width - 70, .7f);
        var search = new Rectangle(panel.X + 12, panel.Y + 42, panel.Width - 138, 28);
        var sort = new Rectangle(search.Right + 6, search.Y, 108, 28);
        DrawButton(sb, search, true, _pickerQuery.Length == 0 ? ForgeText("PickerSearch") : _pickerQuery + (_pickerSearchFocus ? " |" : ""));
        DrawButton(sb, sort, true, ForgeText(_pickerSortByStack ? "PickerSortStack" : "PickerSortName"));
        if (click) SetPickerSearchFocus(search.Contains(Main.mouseX, Main.mouseY));
        if (click && sort.Contains(Main.mouseX, Main.mouseY)) { _pickerSortByStack = !_pickerSortByStack; _pickerPage = 0; }
        if (_pickerSearchFocus)
        {
            Main.blockInput = true; PlayerInput.WritingText = true; Main.instance.HandleIME();
            string query = Main.GetInputText(_pickerQuery);
            if (query.Length > 80) query = query[..80];
            if (query != _pickerQuery) { _pickerQuery = query; _pickerPage = 0; }
            if (Main.keyState.IsKeyDown(Keys.Enter)) SetPickerSearchFocus(false);
        }
        var slots = IngredientPickerSlots(Main.LocalPlayer.inventory, _pickerQuery, _pickerSortByStack);
        int rows = Math.Max(1, (panel.Height - 117) / 42), pages = Math.Max(1, (slots.Length + rows - 1) / rows);
        _pickerPage = Math.Clamp(_pickerPage, 0, pages - 1);
        if (PlayerInput.ScrollWheelDeltaForUI != 0 && panel.Contains(Main.mouseX, Main.mouseY))
            _pickerPage = Math.Clamp(_pickerPage + (PlayerInput.ScrollWheelDeltaForUI < 0 ? 1 : -1), 0, pages - 1);
        for (int i = 0; i < rows && _pickerPage * rows + i < slots.Length; i++)
        {
            int slot = slots[_pickerPage * rows + i]; Item item = Main.LocalPlayer.inventory[slot];
            var rect = new Rectangle(panel.X + 12, panel.Y + 76 + i * 42, panel.Width - 24, 36);
            DrawButton(sb, rect, !owner.HasPendingStationEscrowOperation, item.Name + " × " + item.stack);
            if (rect.Contains(Main.mouseX, Main.mouseY))
            {
                Main.HoverItem = item.Clone(); Main.hoverItemName = item.Name;
                if (click && owner.TryDepositInventoryItem(slot, _pickerSlot)) { ClosePicker(); Main.mouseLeftRelease = false; return; }
            }
        }
        var prev = new Rectangle(panel.X + 12, panel.Bottom - 33, 36, 24);
        var next = new Rectangle(panel.Right - 48, panel.Bottom - 33, 36, 24);
        DrawButton(sb, prev, _pickerPage > 0, "‹"); DrawButton(sb, next, _pickerPage + 1 < pages, "›");
        if (click && prev.Contains(Main.mouseX, Main.mouseY)) _pickerPage = Math.Max(0, _pickerPage - 1);
        if (click && next.Contains(Main.mouseX, Main.mouseY)) _pickerPage = Math.Min(pages - 1, _pickerPage + 1);
        DrawFittedText(sb, slots.Length == 0 ? ForgeText("PickerEmpty") : ForgeText("PickerResults", slots.Length, _pickerPage + 1, pages), new Vector2(prev.Right + 8, prev.Y + 3), Color.Silver, next.X - prev.Right - 16, .55f);
        if (click) Main.mouseLeftRelease = false;
    }
}
