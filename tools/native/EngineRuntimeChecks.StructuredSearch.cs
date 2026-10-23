#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void StructuredSearch()
 {
        var d = GeneratedItemData.Placeholder(); d.Name = "Frost Fire Blade"; d.ParentA = "Ice Block"; d.Tags = new[] { "cold" }; d.RecipeMeta.GenerationDepth = 3;
        Equal(true, RecipeJournalView.MatchesQuery(d, "name:\"Frost Fire\" parent:ice -parent:wood depth:>=3 tag:cold"), "mixed field predicates");
        Equal(false, RecipeJournalView.MatchesQuery(d, "\"Fire Frost\""), "phrase order retained");
        Equal(false, RecipeJournalView.MatchesQuery(d, "depth:>3"), "numeric boundary");
        Equal(false, RecipeJournalView.MatchesQuery(d, "depth:NaN"), "malformed numeric filter refuses");
        Equal(true, RecipeJournalView.MatchesQuery(d, "note:boss collection:combat", "good for bosses", 1), "personal metadata is searchable");
        Equal(false, RecipeJournalView.MatchesQuery(d, "-name:blade"), "negation");
 }
}
