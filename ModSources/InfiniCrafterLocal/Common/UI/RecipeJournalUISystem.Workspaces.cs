#nullable enable
using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameInput;
using Microsoft.Xna.Framework.Input;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class RecipeJournalUISystem
{
    internal static Rectangle[] WorkspaceButtons(Rectangle area, int count)
    {
        int columns = area.Width >= 360 ? 2 : 1;
        int rows = Math.Max(0, (area.Height - 24) / 32);
        int width = Math.Max(0, (area.Width - (columns - 1) * 6) / columns);
        var result = new Rectangle[Math.Min(Math.Max(0, count), columns * rows)];
        for (int i = 0; i < result.Length; i++)
            result[i] = new Rectangle(area.X + i % columns * (width + 6), area.Y + 24 + i / columns * 32, width, 28);
        return result;
    }

    private static bool DrawWorkspacePicker(SpriteBatch sb, Rectangle area, bool click, Vector2 cursor)
    {
        if (!_workspaceMenu) return false;
        var pages = Enum.GetValues<DetailPage>();
        var slots = WorkspaceButtons(area, pages.Length);
        if (slots.Length == 0) return true;
        if (KeyboardAvailable)
        {
            int selected = (int)_detailPage;
            int dx = KeyPressed(Keys.Left) ? -1 : KeyPressed(Keys.Right) ? 1 : 0;
            int dy = KeyPressed(Keys.Up) ? -1 : KeyPressed(Keys.Down) ? 1 : 0;
            if (dx != 0 || dy != 0)
            {
                _detailPage = pages[NavigateGrid(selected, dx, dy, area.Width >= 360 ? 2 : 1, pages.Length)];
                _detailScroll = 0;
                if ((int)_detailPage < _workspaceScroll) _workspaceScroll = (int)_detailPage;
                if ((int)_detailPage >= _workspaceScroll + slots.Length) _workspaceScroll = (int)_detailPage - slots.Length + 1;
            }
            if (KeyPressed(Keys.Enter)) { _workspaceMenu = false; return true; }
        }
        if (PlayerInput.ScrollWheelDeltaForUI != 0 && area.Contains(cursor.ToPoint()))
            _workspaceScroll += PlayerInput.ScrollWheelDeltaForUI < 0 ? slots.Length : -slots.Length;
        _workspaceScroll = Math.Clamp(_workspaceScroll, 0, Math.Max(0, pages.Length - slots.Length));
        Label(sb, Text("WorkspaceHelp"), area.TopLeft(), Muted, .55f, area.Width);
        for (int i = 0; i < slots.Length && i + _workspaceScroll < pages.Length; i++)
        {
            var page = pages[i + _workspaceScroll];
            if (Button(sb, slots[i], Text("View" + page), click, cursor, selected: page == _detailPage))
            { _detailPage = page; _detailScroll = 0; _workspaceMenu = false; return true; }
        }
        return true;
    }
}
