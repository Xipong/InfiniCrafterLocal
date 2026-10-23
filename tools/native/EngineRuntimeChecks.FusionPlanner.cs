#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void FusionPlanner()
 {
        GeneratedItemData Recipe(string id, int yield, params string[] parents) { var d = GeneratedItemData.Placeholder(); d.Id=id; d.Name=id; d.ParentA="Wood"; d.ParentB="Wood"; d.RecipeMeta.WorldId="w"; d.Gameplay.CraftYield=yield; d.RecipeMeta.ParentIdentities=parents; return d; }
        var child = Recipe("child", 3, "wood", "wood"); var root = Recipe("root", 1, "generated:child", "generated:child");
        var stock = new System.Collections.Generic.Dictionary<string, RecipeInventoryView.Stock>();
        var plan = RecipePlanView.Build(root, 2, new[] { root,child }, stock, false);
        Equal(false, plan.Truncated, "ordinary plan completes");
        Equal(4L, plan.Missing.Single().Count, "two child crafts pay duplicated ingredients; surplus reused");
        Equal(2L, plan.Steps.Where(s => s.Id == "child").Sum(s => s.Crafts), "yield rounding across branches");
        stock["wood"] = new("wood", 3, 1, 1);
        Equal(2L, RecipePlanView.Build(root, 2, new[] { root,child }, stock, false).Missing.Single().Count, "protected stock excluded");
        Equal(1L, RecipePlanView.Build(root, 2, new[] { root,child }, stock, true).Missing.Single().Count, "storage opt in");
        child.RecipeMeta.ParentIdentities = new[] { "generated:root", "wood" };
        Equal(true, RecipePlanView.Build(root, 2, new[] { root,child }, stock, false).Truncated, "cycles refuse a complete plan");
 }
}
