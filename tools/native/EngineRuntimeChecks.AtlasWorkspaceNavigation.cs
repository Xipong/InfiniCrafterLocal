#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void AtlasWorkspaceNavigation()
 {
        foreach (int width in new[] { 80, 240, 370, 500 })
        foreach (int height in new[] { 20, 80, 200, 400 })
        {
            var area = new Microsoft.Xna.Framework.Rectangle(17, 23, width, height);
            var slots = RecipeJournalUISystem.WorkspaceButtons(area, 12);
            Equal(true, slots.All(s => area.Contains(s)), "workspace buttons stay inside viewport");
            for (int i=0;i<slots.Length;i++) for(int j=i+1;j<slots.Length;j++)
                Equal(false, slots[i].Intersects(slots[j]), "workspace choices never overlap");
        }
        WithForgePresentationLanguages(locale => {
            foreach (string key in new[] { "ViewHelp", "WorkspaceHelp", "HelpBrowse", "HelpSearch", "HelpPlan", "HelpOwnership" })
                Equal(false, RecipeJournalUISystem.Text(key).StartsWith("Mods."), "localized atlas help " + locale + "/" + key);
        });
 }
}
