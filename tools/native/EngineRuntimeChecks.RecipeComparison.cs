#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void RecipeComparison()
 {
        var a = GeneratedItemData.Placeholder(); var b = GeneratedItemData.Placeholder();
        a.Gameplay.Damage = 30; b.Gameplay.Damage = 20; a.Gameplay.AxePower = 7;
        a.Accessory.Enabled = true; a.Accessory.Defense = 5; b.Armor.Defense = 8;
        var rows = RecipeComparisonView.Compare(a, b);
        Equal(10d, rows.Single(r => r.Key == "BaseDamage").Delta, "signed difference");
        Equal(35d, rows.Single(r => r.Key == "Axe").Value, "native axe units become percent");
        Equal(-3d, rows.Single(r => r.Key == "Defense").Delta, "equipment kind selects actual defense");
        Equal(20, b.Gameplay.Damage, "comparison never mutates the reference");
 }
}
