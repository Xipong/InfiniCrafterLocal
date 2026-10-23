#nullable enable
using System;
using Microsoft.Xna.Framework.Input;
using Terraria;
using Terraria.GameInput;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
namespace InfiniCrafterLocal.Common.UI;
public sealed partial class RecipeJournalUISystem
{
    internal static int NavigateGrid(int index, int dx, int dy, int columns, int count)
    {
        if (count <= 0 || columns <= 0) return -1;
        index = Math.Clamp(index, 0, count - 1);
        return Math.Clamp(index + dx + dy * columns, 0, count - 1);
    }
    private static bool KeyPressed(Keys key) => Main.keyState.IsKeyDown(key) && Main.oldKeyState.IsKeyUp(key);
    private static bool ControlDown => Main.keyState.IsKeyDown(Keys.LeftControl) || Main.keyState.IsKeyDown(Keys.RightControl);
    private static bool KeyboardAvailable => !_searchFocus && !_noteFocus && Main.hasFocus && !Main.drawingPlayerChat
        && !Main.blockInput && !PlayerInput.WritingText && !PlayerInput.CurrentlyRebinding;
    private static void BrowseWithKeyboard(GeneratedItemData[] entries, int columns, int capacity, InfiniCraftPlayer player)
    {
        if (!KeyboardAvailable) return;
        if (KeyPressed(Keys.Tab)) { _workspaceMenu = !_workspaceMenu; _workspaceScroll = 0; return; }
        if (_workspaceMenu) return;
        int index = Array.FindIndex(entries, d => d.Id == _selected);
        int next = index;
        if (KeyPressed(Keys.Left)) next = NavigateGrid(index, -1, 0, columns, entries.Length);
        if (KeyPressed(Keys.Right)) next = NavigateGrid(index, 1, 0, columns, entries.Length);
        if (KeyPressed(Keys.Up)) next = NavigateGrid(index, 0, -1, columns, entries.Length);
        if (KeyPressed(Keys.Down)) next = NavigateGrid(index, 0, 1, columns, entries.Length);
        if (KeyPressed(Keys.PageDown)) next = NavigateGrid(index, capacity, 0, columns, entries.Length);
        if (KeyPressed(Keys.PageUp)) next = NavigateGrid(index, -capacity, 0, columns, entries.Length);
        if (KeyPressed(Keys.Home)) next = entries.Length > 0 ? 0 : -1;
        if (KeyPressed(Keys.End)) next = entries.Length - 1;
        if (next >= 0 && next != index) { Select(entries[next].Id); _page = next / capacity; _revealSelection = false; }
        if (KeyPressed(Keys.Space) && next >= 0)
        {
            string id = entries[next].Id;
            if (ControlDown) { if (!BatchSelection.Add(id)) BatchSelection.Remove(id); }
            else player.ToggleJournalFavorite(id);
        }
        if (KeyPressed(Keys.Back) && History.Count > 0) Select(History.Pop(), false);
    }
}
