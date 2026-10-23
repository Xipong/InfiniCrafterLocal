#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void InventoryAvailability()
 {
        var player = new Terraria.Player();
        player.inventory[0] = new Terraria.Item(Terraria.ID.ItemID.Wood, 7) { favorited = true };
        player.inventory[1] = new Terraria.Item(Terraria.ID.ItemID.Wood, 3);
        player.inventory[58] = new Terraria.Item(Terraria.ID.ItemID.Wood, 80);
        player.bank.item[0] = new Terraria.Item(Terraria.ID.ItemID.Wood, 12);
        var stock = RecipeInventoryView.Capture(player, "world");
        var row = RecipeInventoryView.Find(stock, "item:Terraria/Wood:9");
        Equal(10L, row.Carried, "cursor excluded from inventory"); Equal(12L, row.Stored, "bank separately counted");
        Equal(7L, row.Protected, "favorite amount remains visible");
        Equal(row, RecipeInventoryView.Find(stock, "item:Terraria:Wood:9"), "exact old identity spelling");
        Equal(7, player.inventory[0].stack, "read-only count");
 }
}
