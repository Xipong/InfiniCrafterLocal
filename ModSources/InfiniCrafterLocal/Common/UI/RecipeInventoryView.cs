#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.UI;

internal static class RecipeInventoryView
{
    internal readonly record struct Stock(string Identity, long Carried, long Stored, long Protected);
    internal static string Identity(Item? item, string world)
    {
        if (item is null || item.IsAir) return "";
        if (item.ModItem is GeneratedItem generated)
            return generated.Data.RecipeMeta.WorldScoped && generated.Data.RecipeMeta.WorldId == world
                && !GeneratedItemData.IsPlayerSaveReferenceOnly(generated.Data) ? "generated:" + generated.Data.Id : "";
        string name = item.ModItem is { } mod ? mod.Mod.Name + "/" + mod.Name : "Terraria/" + ItemID.Search.GetName(item.type);
        return "item:" + name + ":" + item.type;
    }
    internal static IReadOnlyDictionary<string, Stock> Capture(Player player, string world)
    {
        var totals = new Dictionary<string, Stock>(StringComparer.Ordinal);
        Add(player.inventory.Take(58), false);
        Add(player.bank.item, true); Add(player.bank2.item, true); Add(player.bank3.item, true); Add(player.bank4.item, true);
        return totals;
        void Add(IEnumerable<Item> items, bool stored)
        {
            foreach (var item in items)
            {
                string id = Identity(item, world); if (id.Length == 0) continue;
                totals.TryGetValue(id, out var old);
                totals[id] = new(id, old.Carried + (!stored ? Math.Max(0, item.stack) : 0),
                    old.Stored + (stored ? Math.Max(0, item.stack) : 0), old.Protected + (!stored && item.favorited ? Math.Max(0, item.stack) : 0));
            }
        }
    }
    internal static Stock Find(IReadOnlyDictionary<string, Stock> stock, string identity)
    {
        if (stock.TryGetValue(identity, out var value)) return value;
        // Historical vanilla identity spelling is exact and lossless.
        if (identity.StartsWith("item:Terraria:", StringComparison.Ordinal))
            stock.TryGetValue("item:Terraria/" + identity[14..], out value);
        return value;
    }
}
