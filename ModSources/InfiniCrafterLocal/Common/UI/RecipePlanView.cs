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
    internal readonly record struct Allocation(string Identity, string Name, long Used, long Surplus);
    internal sealed record Plan(IReadOnlyList<Missing> Missing, IReadOnlyList<Step> Steps, bool Truncated,
        IReadOnlyList<Allocation> Allocations, long OwnedTarget, int Quantity)
    {
        internal bool Completed => !Truncated && OwnedTarget >= Quantity;
        internal long TotalCrafts => Steps.Sum(s => s.Crafts);
    }
    internal static Plan Build(GeneratedItemData target, int quantity, IEnumerable<GeneratedItemData> known,
        IReadOnlyDictionary<string, RecipeInventoryView.Stock> inventory, bool includeStorage)
    {
        var recipes = RecipeJournalView.Entries(known, target.RecipeMeta.WorldId, "", _ => false, false)
            .ToDictionary(d => d.Id, StringComparer.Ordinal);
        var available = new Dictionary<string, long>(StringComparer.Ordinal);
        var allocations = new Dictionary<string, Allocation>(StringComparer.Ordinal);
        var missing = new Dictionary<string, Missing>(StringComparer.Ordinal);
        var steps = new List<Step>(); var path = new HashSet<string>(StringComparer.Ordinal);
        int visits = 0; bool truncated = false;
        quantity = Math.Clamp(quantity, 1, 999);
        var targetStock = RecipeInventoryView.Find(inventory, "generated:" + target.Id);
        // Owning the target fulfills the objective even when it is favorited; protected stock
        // is still excluded from ingredients consumed by recursive crafting.
        long ownedTarget = Math.Max(0, targetStock.Carried) + (includeStorage ? Math.Max(0, targetStock.Stored) : 0);
        if (ownedTarget >= quantity) return new(Array.Empty<Missing>(), Array.Empty<Step>(), false, Array.Empty<Allocation>(), ownedTarget, quantity);
        available["generated:" + target.Id] = 0;
        Require("generated:" + target.Id, target.Name, quantity - ownedTarget, 0);
        return new(missing.Values.OrderBy(r => r.Name, StringComparer.CurrentCultureIgnoreCase).ToArray(), steps, truncated,
            allocations.Values.OrderBy(r => r.Name, StringComparer.CurrentCultureIgnoreCase).ToArray(), ownedTarget, quantity);

        void Require(string identity, string name, long count, int depth)
        {
            if (count <= 0 || truncated) return;
            identity = RecipeInventoryView.CanonicalIdentity(identity);
            if (++visits > 512 || depth > 32 || count > 1_000_000_000) { truncated = true; return; }
            if (!available.TryGetValue(identity, out long stock))
            {
                var owned = RecipeInventoryView.Find(inventory, identity);
                stock = Math.Max(0, owned.Carried - owned.Protected) + (includeStorage ? Math.Max(0, owned.Stored - owned.StoredProtected) : 0);
            }
            long taken = Math.Min(stock, count); count -= taken; available[identity] = stock - taken;
            allocations.TryGetValue(identity, out var allocation);
            allocations[identity] = new(identity, name, allocation.Used + taken, allocation.Surplus);
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
            var used = allocations[identity];
            allocations[identity] = used with { Surplus = used.Surplus + produced - count };
            steps.Add(new(recipe.Id, recipe.Name, crafts, produced));
        }
    }
}
