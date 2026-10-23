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
    public override void OnWorldUnload() { _pickerSlot = -1; _pickerPage = 0; }
    private static void DrawInventoryPicker(SpriteBatch sb, Rectangle station, InfiniCraftPlayer owner)
    {
        if (_pickerSlot >= owner.MultiDevWindowCount * 2 || owner.IsCraftLanePending(_pickerSlot / 2)
            || !owner.StationInput(_pickerSlot).IsAir || !Main.mouseItem.IsAir)
        { _pickerSlot = -1; return; }
        int height = Math.Min(390, Main.screenHeight - 24);
        var panel = new Rectangle(station.X, Math.Clamp(station.Y, 12, Math.Max(12, Main.screenHeight - height - 12)), station.Width, height);
        DrawPanel(sb, panel); Main.LocalPlayer.mouseInterface = true;
        PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Ingredient Picker");
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        var close = new Rectangle(panel.Right - 42, panel.Y + 8, 28, 26);
        DrawButton(sb, close, true, "×");
        if (click && close.Contains(Main.mouseX, Main.mouseY) || Main.keyState.IsKeyDown(Keys.Escape))
        { _pickerSlot = -1; Main.mouseLeftRelease = false; return; }
        DrawFittedText(sb, ForgeText("PickIngredient", _pickerSlot % 2 == 0 ? "A" : "B"), panel.TopLeft() + new Vector2(12, 12), Color.LightSkyBlue, panel.Width - 70, .7f);
        var slots = Enumerable.Range(0, Math.Min(58, Main.LocalPlayer.inventory.Length))
            .Where(i => InfiniCore.IsValidIngredient(Main.LocalPlayer.inventory[i])).ToArray();
        int rows = Math.Max(1, (panel.Height - 85) / 42), pages = Math.Max(1, (slots.Length + rows - 1) / rows);
        _pickerPage = Math.Clamp(_pickerPage, 0, pages - 1);
        if (PlayerInput.ScrollWheelDeltaForUI != 0 && panel.Contains(Main.mouseX, Main.mouseY))
            _pickerPage = Math.Clamp(_pickerPage + (PlayerInput.ScrollWheelDeltaForUI < 0 ? 1 : -1), 0, pages - 1);
        for (int i = 0; i < rows && _pickerPage * rows + i < slots.Length; i++)
        {
            int slot = slots[_pickerPage * rows + i]; Item item = Main.LocalPlayer.inventory[slot];
            var rect = new Rectangle(panel.X + 12, panel.Y + 44 + i * 42, panel.Width - 24, 36);
            DrawButton(sb, rect, !owner.HasPendingStationEscrowOperation, item.Name + " × " + item.stack);
            if (rect.Contains(Main.mouseX, Main.mouseY))
            {
                Main.HoverItem = item.Clone(); Main.hoverItemName = item.Name;
                if (click && owner.TryDepositInventoryItem(slot, _pickerSlot)) _pickerSlot = -1;
            }
        }
        var prev = new Rectangle(panel.X + 12, panel.Bottom - 33, 36, 24);
        var next = new Rectangle(panel.Right - 48, panel.Bottom - 33, 36, 24);
        DrawButton(sb, prev, _pickerPage > 0, "‹"); DrawButton(sb, next, _pickerPage + 1 < pages, "›");
        if (click && prev.Contains(Main.mouseX, Main.mouseY)) _pickerPage = Math.Max(0, _pickerPage - 1);
        if (click && next.Contains(Main.mouseX, Main.mouseY)) _pickerPage = Math.Min(pages - 1, _pickerPage + 1);
        DrawFittedText(sb, ForgeText(slots.Length == 0 ? "PickerEmpty" : "PickerHint"), new Vector2(prev.Right + 8, prev.Y + 3), Color.Silver, next.X - prev.Right - 16, .55f);
        if (click) Main.mouseLeftRelease = false;
    }
}
