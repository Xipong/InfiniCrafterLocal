#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void AtlasGridKeyboard()
 {
        Equal(-1, RecipeJournalUISystem.NavigateGrid(0, 1, 0, 4, 0), "empty grid");
        Equal(0, RecipeJournalUISystem.NavigateGrid(0, -1, 0, 4, 11), "left edge");
        Equal(10, RecipeJournalUISystem.NavigateGrid(7, 0, 1, 4, 11), "ragged last row");
        Equal(6, RecipeJournalUISystem.NavigateGrid(10, 0, -1, 4, 11), "up from last row");
        Equal(8, RecipeJournalUISystem.NavigateGrid(4, 4, 0, 4, 11), "page retains relative offset");
        Equal(10, RecipeJournalUISystem.NavigateGrid(10, 1, 0, 4, 11), "last edge");
 }
}
