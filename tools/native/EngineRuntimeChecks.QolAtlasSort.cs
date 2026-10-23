using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolAtlasSort()
    {
        GeneratedItemData Entry(string id, int depth) { var d = GeneratedItemData.Placeholder(); d.Id = id; d.Name = id; d.RecipeMeta.GenerationDepth = depth; return d; }
        var records = new[] { Entry("a", 3), Entry("b", 1), Entry("c", 2) };
        Equal("a,c,b", string.Join(",", RecipeJournalView.Sort(records, RecipeJournalView.SortOrder.DeepFirst, _ => false).Select(d => d.Id)), "deepest recipes first");
        Equal("c,b,a", string.Join(",", RecipeJournalView.Sort(records, RecipeJournalView.SortOrder.ShallowFirst, id => id == "c").Select(d => d.Id)), "favorites retain priority over depth");
        Equal("a,b,c", string.Join(",", RecipeJournalView.Sort(records, RecipeJournalView.SortOrder.Name, _ => false).Select(d => d.Id)), "name sort remains available");
    }
}
