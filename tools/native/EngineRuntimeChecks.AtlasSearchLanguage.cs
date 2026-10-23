#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void AtlasSearchLanguage()
 {
        var data = GeneratedItemData.Placeholder(); data.Name = "Fire \"Quoted\" Blade"; data.ParentA = "Wood";
        Equal(true, RecipeJournalView.MatchesQuery(data, "name:\"Fire \\\"Quoted\\\"\""), "escaped quotation stays literal");
        Equal(false, RecipeJournalView.MatchesQuery(data, "unknown:wood"), "unknown qualifiers are literal terms, never match everything");
        Equal("SearchUnclosedQuote", RecipeJournalView.QueryIssue("name:\"Fire"), "unfinished phrase receives feedback");
        Equal("SearchDepthInvalid", RecipeJournalView.QueryIssue("depth:<>3"), "malformed operator feedback");
        Equal("", RecipeJournalView.QueryIssue("depth:>=3 -parent:stone"), "valid structured query");
        Equal(240, RecipeJournalView.ParseQuery(new string('a', 300)).Terms.Single().Length, "bounded parser");
        Equal(true, RecipeJournalView.ParseQuery(new string('a', 300)).Truncated, "truncation visible");
 }
}
