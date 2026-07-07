#nullable enable
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.GameContent;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

/// <summary>
/// Client-side inventory station for InfiniCraft. This is intentionally small and vanilla-like:
/// two explicit input slots, a start button, and a 30-second stabilization bar. No hidden
/// "first two inventory items" behavior.
/// </summary>
[Autoload(Side = ModSide.Client)]
public sealed class InfiniCraftStationUISystem : ModSystem
{
    private const int SlotSize = 52;

    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        int inventoryIndex = layers.FindIndex(layer => layer.Name.Equals("Vanilla: Inventory"));
        if (inventoryIndex == -1)
            inventoryIndex = layers.FindIndex(layer => layer.Name.Equals("Vanilla: Mouse Text"));

        if (inventoryIndex == -1)
            return;

        layers.Insert(inventoryIndex + 1, new LegacyGameInterfaceLayer(
            "InfiniCrafterLocal: Inventory Craft Station",
            delegate
            {
                DrawInventoryStation(Main.spriteBatch);
                return true;
            },
            InterfaceScaleType.UI)
        );
    }

    private static void DrawInventoryStation(SpriteBatch spriteBatch)
    {
        if (!Main.playerInventory || Main.LocalPlayer is null || !Main.LocalPlayer.active)
            return;

        var craftPlayer = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
        bool hasCore = PlayerHasCore(Main.LocalPlayer);
        if (!hasCore && !craftPlayer.HasStationState)
            return;

        const int width = 392;
        const int height = 190;

        int x = Math.Clamp(Main.screenWidth - width - 28, 24, Math.Max(24, Main.screenWidth - width - 24));
        int y = Math.Clamp(216, 110, Math.Max(110, Main.screenHeight - height - 24));

        var panel = new Rectangle(x, y, width, height);
        var slotA = new Rectangle(panel.X + 18, panel.Y + 48, SlotSize, SlotSize);
        var slotB = new Rectangle(panel.X + 82, panel.Y + 48, SlotSize, SlotSize);
        var button = new Rectangle(panel.X + 150, panel.Y + 53, 86, 38);
        var clearButton = new Rectangle(panel.X + 252, panel.Y + 53, 116, 38);
        var barBack = new Rectangle(panel.X + 16, panel.Y + 152, panel.Width - 32, 16);

        HandleMouse(craftPlayer, slotA, slotB, button, clearButton);

        DrawPanel(spriteBatch, panel);
        Utils.DrawBorderString(spriteBatch, "InfiniCraft station", new Vector2(panel.X + 14, panel.Y + 10), Color.Cyan, 0.92f);
        string subtitle = craftPlayer.HasPendingCraft ? Truncate(craftPlayer.CraftLabel, 42) : "Place two items, then stabilize";
        Utils.DrawBorderString(spriteBatch, subtitle, new Vector2(panel.X + 14, panel.Y + 30), Color.Silver, 0.70f);

        DrawInputSlot(spriteBatch, slotA, ref craftPlayer.InputA, "A");
        DrawInputSlot(spriteBatch, slotB, ref craftPlayer.InputB, "B");
        DrawInputName(spriteBatch, slotA, craftPlayer.InputA, Color.LightSkyBlue);
        DrawInputName(spriteBatch, slotB, craftPlayer.InputB, Color.LightPink);

        DrawButton(spriteBatch, button, craftPlayer.CanStartStationCraft && !craftPlayer.HasPendingCraft, craftPlayer.HasPendingCraft ? "Busy" : "Craft");
        DrawButton(spriteBatch, clearButton, !craftPlayer.HasPendingCraft && craftPlayer.HasAnyInput, "Clear inputs");

        string modeHint;
        if (!craftPlayer.HasPendingCraft && craftPlayer.HasAnyInput)
            modeHint = "RMB slot clears · Clear returns inputs";
        else if (!craftPlayer.HasPendingCraft)
            modeHint = Main.netMode == Terraria.ID.NetmodeID.MultiplayerClient
                ? "MP: host generates, assets auto-download"
                : "Place two items manually";
        else
            modeHint = "Generated assets are prefetched while inventory is open";
        Utils.DrawBorderString(spriteBatch, modeHint, new Vector2(panel.X + 150, panel.Y + 102), Color.Gray, 0.60f);
        string inputStatus = craftPlayer.CanStartStationCraft ? "A+B valid · manual craft only" : craftPlayer.HasAnyInput ? "Need second input" : "Manual A/B inputs";
        Utils.DrawBorderString(spriteBatch, inputStatus, new Vector2(panel.X + 150, panel.Y + 119), craftPlayer.CanStartStationCraft ? Color.LightGreen : Color.Silver, 0.58f);

        DrawRect(spriteBatch, new Rectangle(barBack.X - 1, barBack.Y - 1, barBack.Width + 2, barBack.Height + 2), new Color(90, 105, 135, 180));
        DrawRect(spriteBatch, barBack, new Color(18, 20, 28, 230));

        float progress = MathHelper.Clamp(craftPlayer.CraftProgress, 0f, 1f);
        int fillWidth = (int)Math.Round(barBack.Width * progress);
        if (fillWidth > 0)
            DrawGradient(spriteBatch, new Rectangle(barBack.X, barBack.Y, fillWidth, barBack.Height), new Color(40, 190, 220, 235), new Color(160, 90, 255, 235));

        string status = craftPlayer.HasPendingCraft
            ? craftPlayer.IsWaitingForRetry
                ? $"Генератор занят/дописывает — проверка #{craftPlayer.GenerationAttempt + 1} через {craftPlayer.RetrySecondsLeft}с"
                : craftPlayer.IsWaitingForModel ? "Стабилизация завершена — ждём модель" : $"Стабилизация: {Math.Ceiling(craftPlayer.TicksLeft / 60f)}с"
            : craftPlayer.CanStartStationCraft ? "Готово к стабилизации" : "Ожидаются два входных предмета";
        Utils.DrawBorderString(spriteBatch, status, new Vector2(panel.X + 14, panel.Y + 170), craftPlayer.IsWaitingForRetry || craftPlayer.IsWaitingForModel ? Color.Orange : Color.LightSkyBlue, 0.66f);

        var mouse = new Point(Main.mouseX, Main.mouseY);
        if (panel.Contains(mouse))
            Main.LocalPlayer.mouseInterface = true;
    }

    private static void HandleMouse(InfiniCraftPlayer craftPlayer, Rectangle slotA, Rectangle slotB, Rectangle button, Rectangle clearButton)
    {
        var mouse = new Point(Main.mouseX, Main.mouseY);

        if (Main.mouseRight && Main.mouseRightRelease)
        {
            if (slotA.Contains(mouse))
            {
                craftPlayer.TryClearInputToInventory(0);
                Main.mouseRightRelease = false;
                return;
            }
            if (slotB.Contains(mouse))
            {
                craftPlayer.TryClearInputToInventory(1);
                Main.mouseRightRelease = false;
                return;
            }
        }

        if (!Main.mouseLeft || !Main.mouseLeftRelease)
            return;

        if (slotA.Contains(mouse))
        {
            if (!craftPlayer.TryTakeInputToMouse(0)) craftPlayer.TryPutMouseItemIntoInput(0);
            Main.mouseLeftRelease = false;
            return;
        }
        if (slotB.Contains(mouse))
        {
            if (!craftPlayer.TryTakeInputToMouse(1)) craftPlayer.TryPutMouseItemIntoInput(1);
            Main.mouseLeftRelease = false;
            return;
        }
        if (clearButton.Contains(mouse))
        {
            craftPlayer.TryClearAllInputsToInventory();
            Main.mouseLeftRelease = false;
            return;
        }
        if (button.Contains(mouse))
        {
            if (!craftPlayer.TryStartCraftFromStation())
                CombatText.NewText(Main.LocalPlayer.Hitbox, Color.OrangeRed, craftPlayer.HasPendingCraft ? "InfiniCraft already running" : "Need two input items");
            Main.mouseLeftRelease = false;
        }
    }


    private static void DrawInputSlot(SpriteBatch spriteBatch, Rectangle rect, ref Item item, string label)
    {
        float oldScale = Main.inventoryScale;
        Main.inventoryScale = 1f;
        Vector2 pos = rect.TopLeft();
        ItemSlot.Draw(spriteBatch, ref item, ItemSlot.Context.BankItem, pos);
        Main.inventoryScale = oldScale;
        if (item is null || item.IsAir)
            Utils.DrawBorderString(spriteBatch, label, new Vector2(rect.X + 20, rect.Y + 16), Color.DimGray, 0.8f);
    }


    private static void DrawInputName(SpriteBatch spriteBatch, Rectangle rect, Item item, Color color)
    {
        if (item is null || item.IsAir)
            return;
        string name = Truncate(DisplayItemName(item), 15);
        Utils.DrawBorderString(spriteBatch, name, new Vector2(rect.X - 1, rect.Bottom + 2), color, 0.54f);
    }

    private static string DisplayItemName(Item item)
    {
        try
        {
            if (!string.IsNullOrWhiteSpace(item.Name))
                return item.Name;
            if (!string.IsNullOrWhiteSpace(item.ModItem?.Name))
                return item.ModItem.Name;
        }
        catch { }
        return "Item";
    }

    private static void DrawButton(SpriteBatch spriteBatch, Rectangle rect, bool enabled, string text)
    {
        Color back = enabled ? new Color(38, 82, 94, 230) : new Color(45, 45, 52, 210);
        Color border = enabled ? new Color(100, 230, 240, 210) : new Color(90, 90, 100, 160);
        DrawRect(spriteBatch, rect, back);
        DrawRect(spriteBatch, new Rectangle(rect.X, rect.Y, rect.Width, 2), border);
        DrawRect(spriteBatch, new Rectangle(rect.X, rect.Bottom - 2, rect.Width, 2), new Color(20, 30, 40, 220));
        Vector2 size = FontAssets.MouseText.Value.MeasureString(text) * 0.75f;
        Utils.DrawBorderString(spriteBatch, text, new Vector2(rect.Center.X - size.X / 2f, rect.Center.Y - size.Y / 2f - 2), enabled ? Color.White : Color.Gray, 0.75f);
    }

    private static bool PlayerHasCore(Player player)
    {
        int coreType = ModContent.ItemType<InfiniCore>();
        for (int i = 0; i < 58; i++)
            if (!player.inventory[i].IsAir && player.inventory[i].type == coreType)
                return true;
        return false;
    }

    private static void DrawPanel(SpriteBatch spriteBatch, Rectangle panel)
    {
        DrawRect(spriteBatch, panel, new Color(28, 33, 48, 225));
        DrawRect(spriteBatch, new Rectangle(panel.X, panel.Y, panel.Width, 2), new Color(105, 210, 235, 190));
        DrawRect(spriteBatch, new Rectangle(panel.X, panel.Bottom - 2, panel.Width, 2), new Color(35, 55, 86, 220));
        DrawRect(spriteBatch, new Rectangle(panel.X, panel.Y, 2, panel.Height), new Color(70, 150, 190, 170));
        DrawRect(spriteBatch, new Rectangle(panel.Right - 2, panel.Y, 2, panel.Height), new Color(20, 35, 60, 220));
    }

    private static void DrawGradient(SpriteBatch spriteBatch, Rectangle rect, Color leftColor, Color rightColor)
    {
        if (rect.Width <= 0 || rect.Height <= 0)
            return;

        for (int i = 0; i < rect.Width; i++)
        {
            float t = rect.Width <= 1 ? 1f : i / (float)(rect.Width - 1);
            DrawRect(spriteBatch, new Rectangle(rect.X + i, rect.Y, 1, rect.Height), Color.Lerp(leftColor, rightColor, t));
        }
    }

    private static void DrawRect(SpriteBatch spriteBatch, Rectangle rect, Color color)
    {
        spriteBatch.Draw(TextureAssets.MagicPixel.Value, rect, color);
    }

    private static string Truncate(string value, int maxChars)
    {
        if (string.IsNullOrWhiteSpace(value))
            return "InfiniCraft";
        value = value.Trim();
        return value.Length <= maxChars ? value : value[..Math.Max(0, maxChars - 1)] + "…";
    }
}
