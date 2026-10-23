using System;
using System.Reflection;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static FieldInfo JournalField(string name) => typeof(RecipeJournalUISystem).GetField(name, BindingFlags.NonPublic | BindingFlags.Static)!;
    private static GeneratedItemData JournalEntry(string id)
    {
        var data = GeneratedItemData.Placeholder(); data.Id = id; data.Name = id;
        data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString(); return data;
    }
    private static void JournalNavigationWorkflow()
    {
        WithPlayer((player, _) => {
            var ui = new RecipeJournalUISystem(); ui.OnWorldUnload();
            try {
                JournalField("_known").SetValue(null, new[] { JournalEntry("a"), JournalEntry("b") });
                JournalField("_selected").SetValue(null, "a");
                JournalField("_query").SetValue(null, "name:a");
                JournalField("_favoritesOnly").SetValue(null, true);
                JournalField("_page").SetValue(null, 3);
                JournalField("_detailScroll").SetValue(null, 7);
                typeof(RecipeJournalUISystem).GetMethod("Select", BindingFlags.NonPublic | BindingFlags.Static)!.Invoke(null, new object[] { "b", true, true });
                Equal("", (string)JournalField("_query").GetValue(null)!, "relation target visible outside previous query");
                Equal("b", (string)JournalField("_selected").GetValue(null)!, "relation target selected");
                Equal(true, RecipeJournalUISystem.NavigateBack(), "history restores prior context");
                Equal("a", (string)JournalField("_selected").GetValue(null)!, "prior selection restored");
                Equal("name:a", (string)JournalField("_query").GetValue(null)!, "query restored");
                Equal(true, (bool)JournalField("_favoritesOnly").GetValue(null)!, "favorite filter restored");
                Equal(3, (int)JournalField("_page").GetValue(null)!, "page restored");
                Equal(7, (int)JournalField("_detailScroll").GetValue(null)!, "reading position restored");
                Equal(false, RecipeJournalUISystem.NavigateBack(), "history consumed once");
            } finally { ui.OnWorldUnload(); }
        });
    }
}
