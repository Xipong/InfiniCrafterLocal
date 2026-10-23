using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolWordSearch()
    {
        var data = GeneratedItemData.Placeholder(); data.Name = "Медный клинок"; data.ParentA = "Дерево";
        Equal(true, RecipeJournalView.MatchesQuery(data, "  КЛИНОК\tдерево "), "words may match different recipe fields");
        Equal(false, RecipeJournalView.MatchesQuery(data, "клинок камень"), "every word is required");
        Equal(true, RecipeJournalView.MatchesQuery(data, " "), "empty query retains discoveries");
    }
}
