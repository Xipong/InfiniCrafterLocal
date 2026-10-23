#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.Players;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using Terraria;
using Terraria.GameInput;
namespace InfiniCrafterLocal.Common.UI;
public sealed partial class InfiniCraftStationUISystem
{
    private static bool _historyOpen, _historyAllWorlds;
    private static int _historyPage;
    private static void DrawCraftHistory(SpriteBatch sb, InfiniCraftPlayer owner)
    {
        int width = Math.Min(660, Main.screenWidth - 24), height = Math.Min(480, Main.screenHeight - 24);
        var panel = new Rectangle((Main.screenWidth - width) / 2, (Main.screenHeight - height) / 2, width, height);
        DrawPanel(sb, panel); Main.LocalPlayer.mouseInterface = true;
        PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Craft History");
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        var close = new Rectangle(panel.Right - 40, panel.Y + 8, 28, 26);
        DrawButton(sb, close, true, "×");
        var world = new Rectangle(panel.X + 12, panel.Y + 8, 170, 26);
        DrawButton(sb, world, true, ForgeText(_historyAllWorlds ? "HistoryAllWorlds" : "HistoryCurrentWorld"));
        if (click && world.Contains(Main.mouseX, Main.mouseY)) { _historyAllWorlds = !_historyAllWorlds; _historyPage = 0; }
        if (click && close.Contains(Main.mouseX, Main.mouseY) || Main.keyState.IsKeyDown(Keys.Escape)) { _historyOpen = false; Main.mouseLeftRelease = false; return; }
        var entries = owner.CraftHistory.Where(e => _historyAllWorlds || e.World == Main.worldID.ToString()).ToArray();
        int visible = Math.Max(1, (height - 88) / 86), pages = Math.Max(1, (entries.Length + visible - 1) / visible);
        if (PlayerInput.ScrollWheelDeltaForUI != 0) _historyPage += PlayerInput.ScrollWheelDeltaForUI < 0 ? 1 : -1;
        _historyPage = Math.Clamp(_historyPage, 0, pages - 1);
        for (int i = 0; i < visible && _historyPage * visible + i < entries.Length; i++)
        {
            var row = entries[_historyPage * visible + i]; int y = panel.Y + 44 + i * 86;
            string heading = new DateTime(row.UtcTicks, DateTimeKind.Utc).ToLocalTime().ToString("g") + " · " + ForgeText("Lane", row.Lane + 1) + " · " + ForgeText("Outcome" + row.Outcome.Kind);
            DrawFittedText(sb, heading, new(panel.X + 14, y), Color.LightSkyBlue, width - 28, .62f);
            DrawFittedText(sb, row.Recipe, new(panel.X + 14, y + 21), Color.White, width - 28, .62f);
            DrawFittedText(sb, row.Outcome.Message, new(panel.X + 14, y + 42), Color.Silver, width - 28, .6f);
            string disposition = ForgeText("HistoryMaterials" + row.Outcome.Materials);
            DrawFittedText(sb, disposition, new(panel.X + 14, y + 62), Color.Gray, width - 28, .55f);
            if (new Rectangle(panel.X + 10, y, width - 20, 83).Contains(Main.mouseX, Main.mouseY))
                Main.instance.MouseText(heading, row.Recipe + "\n" + row.Outcome.Message + "\n" + disposition);
        }
        var prev = new Rectangle(panel.X + 12, panel.Bottom - 34, 34, 24);
        var next = new Rectangle(panel.Right - 46, panel.Bottom - 34, 34, 24);
        DrawButton(sb, prev, _historyPage > 0, "‹"); DrawButton(sb, next, _historyPage + 1 < pages, "›");
        if (click && prev.Contains(Main.mouseX, Main.mouseY)) _historyPage = Math.Max(0, _historyPage - 1);
        if (click && next.Contains(Main.mouseX, Main.mouseY)) _historyPage = Math.Min(pages - 1, _historyPage + 1);
        DrawFittedText(sb, ForgeText("HistoryNotice", entries.Length, _historyPage + 1, pages), new(panel.X + 54, panel.Bottom - 29), Color.Silver, width - 108, .55f);
        if (click) Main.mouseLeftRelease = false;
        Main.HoverItem = new Item(); Main.hoverItemName = "";
    }
}
