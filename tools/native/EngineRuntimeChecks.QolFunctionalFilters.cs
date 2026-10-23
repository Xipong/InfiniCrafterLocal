using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolFunctionalFilters()
    {
        var data = GeneratedItemData.Placeholder(); data.Name = "Mana armor";
        Equal(false, RecipeJournalView.MatchesEffect(data, RecipeJournalView.EffectFilter.Equipment), "name cannot classify equipment");
        data.Accessory.Enabled = true;
        Equal(true, RecipeJournalView.MatchesEffect(data, RecipeJournalView.EffectFilter.Equipment), "accepted equipment flag is searchable");
        Equal(false, RecipeJournalView.MatchesEffect(data, RecipeJournalView.EffectFilter.Mana), "name cannot invent a mana action");
    }
}
