#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.UI;

internal static class RecipeStockFilter
{
    internal enum Mode { All, Owned, Missing, ReadyCarried, ReadyWithBanks }
    internal static bool Matches(GeneratedItemData data, Mode mode, IReadOnlyDictionary<string, RecipeInventoryView.Stock> stock)
    {
        if (mode == Mode.All) return true;
        var output = RecipeInventoryView.Find(stock, "generated:" + data.Id);
        if (mode == Mode.Owned) return output.Carried + output.Stored > 0;
        if (mode == Mode.Missing) return output.Carried + output.Stored == 0;
        var parents = data.RecipeMeta.ParentIdentities;
        if (parents is null || parents.Length != 2 || parents.Any(string.IsNullOrWhiteSpace)) return false;
        foreach (var required in parents.GroupBy(id => id, StringComparer.Ordinal))
        {
            var value = RecipeInventoryView.Find(stock, required.Key);
            long available = Math.Max(0, value.Carried - value.Protected) + (mode == Mode.ReadyWithBanks ? value.Stored : 0);
            if (available < required.LongCount()) return false;
        }
        return true;
    }
}
