#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using Terraria;
using Terraria.GameContent;
using Terraria.GameInput;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class InfiniCraftStationUISystem
{
    private static Item? _inspectedItem;
    private static int _inspectionScroll;
    internal static IReadOnlyList<string> StationInspectionRows(Item item)
    {
        var rows = new List<string> { item.Name, ForgeText("InspectionNative") };
        if (item.damage > 0) rows.Add(ForgeText("InspectionDamage", item.damage, item.knockBack));
        if (item.useTime > 0) rows.Add(ForgeText("InspectionUse", item.useTime, item.useAnimation, item.mana));
        if (item.defense != 0) rows.Add(ForgeText("InspectionDefense", item.defense));
        if (item.pick > 0 || item.axe > 0 || item.hammer > 0)
            rows.Add(ForgeText("InspectionTools", item.pick, item.axe * 5, item.hammer));
        rows.Add(ForgeText("InspectionStack", item.stack, item.maxStack));
        if (item.ModItem is GeneratedItem generated)
        {
            rows.Add(ForgeText("InspectionGuide"));
            rows.AddRange(GeneratedItem.RuntimeGuide(generated.Data));
        }
        return rows;
    }
    private static void DrawInputInspection(SpriteBatch sb, Rectangle station)
    {
        if (_inspectedItem is null) return;
        int width = Math.Min(560, Math.Max(0, Main.screenWidth - 24));
        int height = Math.Min(460, Math.Max(0, Main.screenHeight - 24));
        var panel = new Rectangle((Main.screenWidth - width) / 2, (Main.screenHeight - height) / 2, width, height);
        if (width < 120 || height < 100) { _inspectedItem = null; return; }
        DrawPanel(sb, panel); Main.LocalPlayer.mouseInterface = true;
        PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Input Inspection");
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        var close = new Rectangle(panel.Right - 42, panel.Y + 8, 28, 26);
        DrawButton(sb, close, true, "×");
        DrawFittedText(sb, ForgeText("InspectionTitle"), panel.TopLeft() + new Vector2(12, 12), Color.LightSkyBlue, panel.Width - 70, .75f);
        if (click && close.Contains(Main.mouseX, Main.mouseY) || Main.keyState.IsKeyDown(Keys.Escape))
        { _inspectedItem = null; Main.mouseLeftRelease = false; return; }
        var rows = StationInspectionRows(_inspectedItem).SelectMany(text => GeneratedItem.WrapRuntimeTooltipLines(text,
            (width - 32) / .67f, s => FontAssets.MouseText.Value.MeasureString(s).X)).ToArray();
        int visible = Math.Max(1, (height - 60) / 24);
        if (PlayerInput.ScrollWheelDeltaForUI != 0) _inspectionScroll += PlayerInput.ScrollWheelDeltaForUI < 0 ? 2 : -2;
        _inspectionScroll = Math.Clamp(_inspectionScroll, 0, Math.Max(0, rows.Length - visible));
        for (int i = _inspectionScroll; i < Math.Min(rows.Length, _inspectionScroll + visible); i++)
            Utils.DrawBorderString(sb, rows[i], new Vector2(panel.X + 14, panel.Y + 46 + (i - _inspectionScroll) * 24), Color.White, .67f);
        if (click) Main.mouseLeftRelease = false;
        Main.HoverItem = new Item(); Main.hoverItemName = "";
    }
}
