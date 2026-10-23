#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void InventoryDeposit()
 {
        WithPlayer((player, owner) => {
            var old = Terraria.Main.mouseItem; int net = Terraria.Main.netMode;
            try { Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer; Terraria.Main.mouseItem = new Terraria.Item();
                player.inventory[4] = new Terraria.Item(Terraria.ID.ItemID.Wood, 8) { favorited = true };
                Equal(false, owner.TryDepositInventoryItem(4, 0), "favorites cannot be moved");
                player.inventory[4].favorited = false;
                Equal(true, owner.TryDepositInventoryItem(4, 0), "explicit slot deposited");
                Equal(7, player.inventory[4].stack, "one unit consumed from source");
                Equal(1, owner.StationInput(0).stack, "one unit in existing escrow");
                Equal(true, Terraria.Main.mouseItem.IsAir, "cursor restored empty");
                Equal(false, owner.TryDepositInventoryItem(4, 0), "occupied target refuses");
                Equal(7, player.inventory[4].stack, "refusal preserves source");
            } finally { Terraria.Main.mouseItem = old; Terraria.Main.netMode = net; }
        });
 }
}
