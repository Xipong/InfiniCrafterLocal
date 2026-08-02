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

        int laneCount = craftPlayer.MultiDevWindowCount;
        const int width = 430;
        const int headerHeight = 44;
        const int laneHeight = 112;
        const int footerHeight = 30;
        int height = headerHeight + laneCount * laneHeight + footerHeight;
        int x = Math.Clamp(Main.screenWidth - width - 28, 24, Math.Max(24, Main.screenWidth - width - 24));
        int y = Math.Clamp(150, 80, Math.Max(80, Main.screenHeight - height - 24));
        var panel = new Rectangle(x, y, width, height);
        var clearButton = new Rectangle(panel.Right - 116, panel.Y + 8, 98, 28);

        var slotA = new Rectangle[laneCount];
        var slotB = new Rectangle[laneCount];
        var craftButtons = new Rectangle[laneCount];
        for (int lane = 0; lane < laneCount; lane++)
        {
            int rowY = panel.Y + headerHeight + lane * laneHeight;
            slotA[lane] = new Rectangle(panel.X + 16, rowY + 24, SlotSize, SlotSize);
            slotB[lane] = new Rectangle(panel.X + 78, rowY + 24, SlotSize, SlotSize);
            craftButtons[lane] = new Rectangle(panel.X + 144, rowY + 31, 78, 36);
        }

        HandleMouse(craftPlayer, slotA, slotB, craftButtons, clearButton);
        DrawPanel(spriteBatch, panel);
        Utils.DrawBorderString(spriteBatch, "InfiniCraft station", new Vector2(panel.X + 14, panel.Y + 9), Color.Cyan, 0.92f);
        Utils.DrawBorderString(
            spriteBatch,
            laneCount > 1 ? $"MULTI-DEV ×{laneCount}" : "use /multidevcraft 2 or 3",
            new Vector2(panel.X + 170, panel.Y + 13),
            laneCount > 1 ? Color.LightGreen : Color.Gray,
            0.62f);
        DrawButton(spriteBatch, clearButton, !craftPlayer.HasAnyCraftLanePending && craftPlayer.HasAnyInput, "Clear all");

        for (int lane = 0; lane < laneCount; lane++)
        {
            int rowY = panel.Y + headerHeight + lane * laneHeight;
            if (lane > 0)
                DrawRect(spriteBatch, new Rectangle(panel.X + 12, rowY, panel.Width - 24, 1), new Color(75, 105, 135, 150));
            Color laneColor = lane switch { 0 => Color.LightSkyBlue, 1 => Color.LightGreen, _ => Color.Violet };
            Utils.DrawBorderString(spriteBatch, $"Window {lane + 1} · LLM {lane + 1}", new Vector2(panel.X + 14, rowY + 3), laneColor, 0.66f);

            ref Item first = ref craftPlayer.StationInput(lane * 2);
            ref Item second = ref craftPlayer.StationInput(lane * 2 + 1);
            DrawInputSlot(spriteBatch, slotA[lane], ref first, "A");
            DrawInputSlot(spriteBatch, slotB[lane], ref second, "B");
            DrawInputName(spriteBatch, slotA[lane], first, Color.LightSkyBlue);
            DrawInputName(spriteBatch, slotB[lane], second, Color.LightPink);

            bool pending = craftPlayer.IsCraftLanePending(lane);
            DrawButton(spriteBatch, craftButtons[lane], craftPlayer.CanStartStationCraftLane(lane), pending ? "Busy" : "Craft");
            string label = pending ? Truncate(craftPlayer.CraftLaneLabel(lane), 31) : "Independent A+B pair";
            Utils.DrawBorderString(spriteBatch, label, new Vector2(panel.X + 235, rowY + 29), Color.Silver, 0.60f);
            Utils.DrawBorderString(spriteBatch, craftPlayer.CraftLaneStatus(lane), new Vector2(panel.X + 235, rowY + 50), pending ? Color.Orange : Color.LightGray, 0.59f);

            var bar = new Rectangle(panel.X + 144, rowY + 78, panel.Width - 160, 12);
            DrawRect(spriteBatch, bar, new Color(18, 20, 28, 230));
            int fill = (int)Math.Round(bar.Width * MathHelper.Clamp(craftPlayer.CraftLaneProgress(lane), 0f, 1f));
            if (fill > 0)
                DrawGradient(spriteBatch, new Rectangle(bar.X, bar.Y, fill, bar.Height), new Color(40, 190, 220, 235), laneColor * 0.9f);
        }

        string footer = laneCount > 1
            ? "Each window spends its own ingredients · exact llm_1/2/3 · RMB clears slot"
            : "Admin unlock: /multidevcraft 2 or /multidevcraft 3";
        Utils.DrawBorderString(spriteBatch, footer, new Vector2(panel.X + 14, panel.Bottom - 23), Color.Gray, 0.56f);
        if (panel.Contains(new Point(Main.mouseX, Main.mouseY)))
            Main.LocalPlayer.mouseInterface = true;
    }

    private static void HandleMouse(
        InfiniCraftPlayer craftPlayer,
        Rectangle[] slotA,
        Rectangle[] slotB,
        Rectangle[] craftButtons,
        Rectangle clearButton)
    {
        var mouse = new Point(Main.mouseX, Main.mouseY);
        if (Main.mouseRight && Main.mouseRightRelease)
        {
            for (int lane = 0; lane < slotA.Length; lane++)
            {
                if (slotA[lane].Contains(mouse) && craftPlayer.TryClearInputToInventory(lane * 2))
                {
                    Main.mouseRightRelease = false;
                    return;
                }
                if (slotB[lane].Contains(mouse) && craftPlayer.TryClearInputToInventory(lane * 2 + 1))
                {
                    Main.mouseRightRelease = false;
                    return;
                }
            }
        }
        if (!Main.mouseLeft || !Main.mouseLeftRelease)
            return;

        for (int lane = 0; lane < slotA.Length; lane++)
        {
            if (slotA[lane].Contains(mouse))
            {
                if (!craftPlayer.TryTakeInputToMouse(lane * 2)) craftPlayer.TryPutMouseItemIntoInput(lane * 2);
                Main.mouseLeftRelease = false;
                return;
            }
            if (slotB[lane].Contains(mouse))
            {
                if (!craftPlayer.TryTakeInputToMouse(lane * 2 + 1)) craftPlayer.TryPutMouseItemIntoInput(lane * 2 + 1);
                Main.mouseLeftRelease = false;
                return;
            }
            if (craftButtons[lane].Contains(mouse))
            {
                if (!craftPlayer.TryStartCraftFromStation(lane))
                    CombatText.NewText(Main.LocalPlayer.Hitbox, Color.OrangeRed, craftPlayer.IsCraftLanePending(lane) ? "This craft window is busy" : "Need two input items");
                Main.mouseLeftRelease = false;
                return;
            }
        }
        if (clearButton.Contains(mouse))
        {
            craftPlayer.TryClearAllInputsToInventory();
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
