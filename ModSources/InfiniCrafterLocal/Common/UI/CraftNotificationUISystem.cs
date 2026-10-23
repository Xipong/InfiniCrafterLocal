#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.GameContent;
using Terraria.GameInput;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

[Autoload(Side = ModSide.Client)]
public sealed class CraftNotificationUISystem : ModSystem
{
    private static bool _mouseReserved, _left, _leftRelease, _right, _rightRelease;

    public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
    {
        int text = layers.FindIndex(layer => layer.Name == "Vanilla: Mouse Text");
        if (text < 0) return;
        layers.Insert(text, new LegacyGameInterfaceLayer("InfiniCrafterLocal: Craft Notifications", DrawReserved, InterfaceScaleType.UI));
        int inventory = layers.FindIndex(layer => layer.Name == "Vanilla: Inventory");
        // Notification draws above the station, so reserve first and restore last.
        // This also composes when the station adds its guard after this callback.
        int station = layers.FindIndex(layer => layer.Name == "InfiniCrafterLocal: Station Modal Input");
        int reserve = station >= 0 && station < inventory ? station : inventory;
        if (reserve >= 0) layers.Insert(reserve, new LegacyGameInterfaceLayer("InfiniCrafterLocal: Notification Input", () => {
            if (Visible() && Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>().UnreadCraftNotificationCount > 0)
                ReserveNotificationMouse(NotificationBounds(Main.screenWidth, Main.screenHeight, Main.playerInventory), PlayerInput.IgnoreMouseInterface);
            return true;
        }, InterfaceScaleType.UI));
    }

    private static bool Visible()
        => !Main.gameMenu && Main.hasFocus && !Main.hideUI && !Main.mapFullscreen && !Main.ingameOptionsWindow
            && !Main.inFancyUI && Main.screenWidth >= 480 && Main.screenHeight >= 100
            && Main.LocalPlayer is { active: true } && !InfiniCraftStationUISystem.StationModalVisible
            && !RecipeJournalUISystem.IsOpen;

    internal static Rectangle NotificationBounds(int width, int height, bool inventory)
    {
        int panelWidth = Math.Min(420, Math.Max(0, width - 32));
        return new((width - panelWidth) / 2, Math.Clamp(inventory ? height - 86 : 78, 0, Math.Max(0, height - 66)), panelWidth, 66);
    }

    internal static bool ReserveNotificationMouse(Rectangle bounds, bool ignoreMouseInterface)
    {
        if (_mouseReserved || ignoreMouseInterface || !bounds.Contains(Main.mouseX, Main.mouseY)) return false;
        _mouseReserved = true;
        (_left, _leftRelease, _right, _rightRelease) = (Main.mouseLeft, Main.mouseLeftRelease, Main.mouseRight, Main.mouseRightRelease);
        Main.mouseLeft = Main.mouseLeftRelease = Main.mouseRight = Main.mouseRightRelease = false;
        return true;
    }

    internal static bool RestoreNotificationMouse()
    {
        if (!_mouseReserved) return false;
        _mouseReserved = false;
        (Main.mouseLeft, Main.mouseLeftRelease, Main.mouseRight, Main.mouseRightRelease) = (_left, _leftRelease, _right, _rightRelease);
        return true;
    }

    public override void OnWorldUnload() => RestoreNotificationMouse();
    public override void Unload() => RestoreNotificationMouse();

    private static bool DrawReserved()
    {
        // Native inventory already saw suppressed buttons; only this handler receives
        // the original edge. Consume releases afterwards even if drawing aborts.
        bool reserved = RestoreNotificationMouse();
        try { return Draw(); }
        finally { if (reserved) { Main.mouseLeftRelease = false; Main.mouseRightRelease = false; } }
    }

    internal static string Text(string key, params object[] args)
        => Language.GetTextValue("Mods.InfiniCrafterLocal.CraftNotifications." + key, args);
    internal static string OutcomeLabel(InfiniCraftPlayer.CraftLaneOutcomeKind kind)
        => Text(kind switch {
            InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded => "OutcomeSucceeded",
            InfiniCraftPlayer.CraftLaneOutcomeKind.Failed => "OutcomeFailed",
            InfiniCraftPlayer.CraftLaneOutcomeKind.Cancelled => "OutcomeCancelled",
            InfiniCraftPlayer.CraftLaneOutcomeKind.TimedOut => "OutcomeTimedOut",
            _ => "OutcomeNone",
        });
    private static bool Draw()
    {
        if (!Visible()) return true;
        var owner = Main.LocalPlayer.GetModPlayer<InfiniCraftPlayer>();
        var rows = owner.CaptureCraftNotifications();
        if (rows.Count == 0) return true;
        var row = rows[0];
        var box = NotificationBounds(Main.screenWidth, Main.screenHeight, Main.playerInventory);
        int width = box.Width;
        bool hovered = !PlayerInput.IgnoreMouseInterface && box.Contains(Main.mouseX, Main.mouseY);
        Main.spriteBatch.Draw(TextureAssets.MagicPixel.Value, box, new Color(12, 18, 27, hovered ? 240 : 195));
        string title = Text("Title", row.Lane + 1, OutcomeLabel(row.Outcome.Kind), rows.Count);
        string detail = row.Outcome.Message;
        while (detail.Length > 0 && FontAssets.MouseText.Value.MeasureString(detail).X * .65f > width - 16) detail = detail[..^1];
        Utils.DrawBorderString(Main.spriteBatch, title, new Vector2(box.X + 8, box.Y + 5),
            row.Outcome.Kind == InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded ? Color.LightGreen : Color.LightGoldenrodYellow, .7f);
        Utils.DrawBorderString(Main.spriteBatch, detail, new Vector2(box.X + 8, box.Y + 27), Color.White, .65f);
        Utils.DrawBorderString(Main.spriteBatch, Text("Dismiss"), new Vector2(box.X + 8, box.Y + 46), Color.Silver, .55f);
        if (hovered)
        {
            Main.LocalPlayer.mouseInterface = true;
            Main.instance.MouseText(row.Outcome.Message + "\n" + Text("Overflow", owner.OverflowCraftNotificationCount));
            if (Main.mouseLeft && Main.mouseLeftRelease)
            {
                owner.AcknowledgeCraftNotification(row.Sequence);
                Main.mouseLeftRelease = false;
            }
        }
        return true;
    }
}
