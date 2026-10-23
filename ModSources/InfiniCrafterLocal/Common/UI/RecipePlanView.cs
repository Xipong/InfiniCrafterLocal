#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.UI;

internal static class RecipePlanView
{
    internal readonly record struct Missing(string Identity, string Name, long Count);
    internal readonly record struct Step(string Id, string Name, long Crafts, long Produced);
    internal sealed record Plan(IReadOnlyList<Missing> Missing, IReadOnlyList<Step> Steps, bool Truncated);
    internal static Plan Build(GeneratedItemData target, int quantity, IEnumerable<GeneratedItemData> known,
        IReadOnlyDictionary<string, RecipeInventoryView.Stock> inventory, bool includeStorage)
    {
        var recipes = RecipeJournalView.Entries(known, target.RecipeMeta.WorldId, "", _ => false, false)
            .ToDictionary(d => d.Id, StringComparer.Ordinal);
        var available = new Dictionary<string, long>(StringComparer.Ordinal);
        var missing = new Dictionary<string, Missing>(StringComparer.Ordinal);
        var steps = new List<Step>(); var path = new HashSet<string>(StringComparer.Ordinal);
        int visits = 0; bool truncated = false;
        Require("generated:" + target.Id, target.Name, Math.Clamp(quantity, 1, 999), 0);
        return new(missing.Values.OrderBy(r => r.Name, StringComparer.CurrentCultureIgnoreCase).ToArray(), steps, truncated);

        void Require(string identity, string name, long count, int depth)
        {
            if (count <= 0 || truncated) return;
            if (++visits > 512 || depth > 32 || count > 1_000_000_000) { truncated = true; return; }
            if (!available.TryGetValue(identity, out long stock))
            {
                var owned = RecipeInventoryView.Find(inventory, identity);
                stock = Math.Max(0, owned.Carried - owned.Protected) + (includeStorage ? owned.Stored : 0);
            }
            long taken = Math.Min(stock, count); count -= taken; available[identity] = stock - taken;
            if (count == 0) return;
            if (!identity.StartsWith("generated:", StringComparison.Ordinal) || !recipes.TryGetValue(identity[10..], out var recipe)
                || recipe.RecipeMeta.ParentIdentities.Length != 2)
            {
                missing.TryGetValue(identity, out var old);
                missing[identity] = new(identity, name, old.Count + count); return;
            }
            if (!path.Add(identity) || recipe.Gameplay.CraftYield <= 0) { truncated = true; return; }
            long crafts = (count + recipe.Gameplay.CraftYield - 1) / recipe.Gameplay.CraftYield;
            Require(recipe.RecipeMeta.ParentIdentities[0], recipe.ParentA, crafts, depth + 1);
            Require(recipe.RecipeMeta.ParentIdentities[1], recipe.ParentB, crafts, depth + 1);
            path.Remove(identity);
            if (truncated) return;
            long produced = crafts * recipe.Gameplay.CraftYield;
            available[identity] += produced - count;
            steps.Add(new(recipe.Id, recipe.Name, crafts, produced));
        }
    }
}
