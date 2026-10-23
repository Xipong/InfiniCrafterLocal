#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Input;
using Terraria;
using Terraria.GameContent;
using Terraria.GameInput;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class GeneratedUtilityBuffUISystem
{
    private static bool _timelineArmed;
    private static int _timelineScroll;
    private static Point _timelineAnchor;
    private static bool TimelineKey => Main.keyState.IsKeyDown(Keys.LeftShift) || Main.keyState.IsKeyDown(Keys.RightShift);
    private static void DrawTimeline(IReadOnlyList<GeneratedStatusTimelineView.Row> rows)
    {
        if (!TimelineKey) { _timelineArmed = false; _timelineScroll = 0; return; }
        if (!_timelineArmed || rows.Count == 0 || FontAssets.MouseText?.IsLoaded != true) return;
        int visible = Math.Min(rows.Count, Math.Max(1, Math.Min(8, (Main.screenHeight - 80) / 34)));
        int width = Math.Min(440, Math.Max(100, Main.screenWidth - 24));
        var panel = new Rectangle(Math.Clamp(_timelineAnchor.X + 20, 0, Math.Max(0, Main.screenWidth - width)),
            Math.Clamp(_timelineAnchor.Y + 20, 0, Math.Max(0, Main.screenHeight - visible * 34 - 38)), width, visible * 34 + 38);
        if (PlayerInput.ScrollWheelDeltaForUI != 0) _timelineScroll -= Math.Sign(PlayerInput.ScrollWheelDeltaForUI);
        _timelineScroll = Math.Clamp(_timelineScroll, 0, Math.Max(0, rows.Count - visible));
        Main.LocalPlayer.mouseInterface = true;
        var sb = Main.spriteBatch;
        sb.Draw(TextureAssets.MagicPixel.Value, panel, new Color(18, 24, 38, 245));
        bool ru = Language.ActiveCulture.CultureInfo.TwoLetterISOLanguageName == "ru";
        Utils.DrawBorderString(sb, (ru ? "Ближайшие окончания" : "Next expirations") + $"  {_timelineScroll + 1}–{_timelineScroll + visible}/{rows.Count}", panel.TopLeft() + new Vector2(8, 5), Color.Gold, .65f);
        int horizon = Math.Max(1, rows[rows.Count - 1].RemainingTicks);
        for (int i = 0; i < visible; i++)
        {
            var row = rows[_timelineScroll + i];
            Vector2 at = panel.TopLeft() + new Vector2(8, 28 + i * 34);
            string label = row.Label;
            while (label.Length > 1 && FontAssets.MouseText.Value.MeasureString(label).X * .55f > width - 90) label = label[..^1];
            if (label.Length < row.Label.Length) label += "…";
            Utils.DrawBorderString(sb, label, at, Color.White, .55f);
            Utils.DrawBorderString(sb, GeneratedStatusTooltipView.CountdownSeconds(row.RemainingTicks, Language.ActiveCulture.CultureInfo) + (ru ? " с" : " s"), new Vector2(panel.Right - 70, at.Y), Color.LightSkyBlue, .6f);
            if (new Rectangle((int)at.X, (int)at.Y, width - 16, 30).Contains(Main.mouseX, Main.mouseY))
                Main.instance.MouseText(GeneratedStatusTooltipView.Wrap(row.Label, row.Detail, Main.screenWidth, Main.screenHeight,
                    text => FontAssets.MouseText.Value.MeasureString(text)), "");
            var track = new Rectangle((int)at.X, (int)at.Y + 21, width - 16, 3);
            sb.Draw(TextureAssets.MagicPixel.Value, track, Color.DimGray);
            track.Width = Math.Max(1, (int)(track.Width * row.RemainingTicks / (double)horizon));
            sb.Draw(TextureAssets.MagicPixel.Value, track, Color.LightSkyBlue);
        }
    }
}
