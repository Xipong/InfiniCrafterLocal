using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolNativeParentIcons()
    {
        var data = GeneratedItemData.Placeholder();
        data.RecipeMeta.ParentIdentities = new[] { "item:Terraria/Wood:9", "item:OtherMod/Wood:9" };
        Equal(Terraria.ID.ItemID.Wood, RecipeJournalView.NativeParentType(data, 0), "exact native identity resolves artwork");
        Equal(0, RecipeJournalView.NativeParentType(data, 1), "modded identity is not reinterpreted as vanilla");
        data.RecipeMeta.ParentIdentities[0] = "item:Terraria:Wood:8";
        Equal(0, RecipeJournalView.NativeParentType(data, 0), "mismatched name and ID remain unknown");
    }
}
