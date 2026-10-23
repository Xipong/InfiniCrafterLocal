#nullable enable
using System;
using System.Linq;
using Terraria;
using Terraria.ID;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void ExplorationPickup()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            var ordinary = new Item(ItemID.Wood); var heart = new Item(ItemID.Heart); var mana = new Item(ItemID.Star); var coin = new Item(ItemID.CopperCoin);
            int woodBefore = player.GetItemGrabRange(ordinary), heartBefore = player.GetItemGrabRange(heart), manaBefore = player.GetItemGrabRange(mana), coinBefore = player.GetItemGrabRange(coin);
            var generated = NativeUtilityItem("\"lifePickup\":true,\"manaPickup\":true,\"coinPickup\":true,\"treasurePickup\":true");
            ExplorationPresentation(generated, "lifePickup", "manaPickup", "coinPickup", "treasurePickup");
            generated.UpdateAccessory(player, true);
            Equal(true, player.lifeMagnet && player.manaMagnet && player.goldRing && player.treasureMagnet, "independent native grants");
            Equal(woodBefore + Item.treasureGrabRange, player.GetItemGrabRange(ordinary), "general native range");
            Equal(heartBefore + Item.treasureGrabRange + Item.lifeGrabRange, player.GetItemGrabRange(heart), "heart native range");
            Equal(manaBefore + Item.treasureGrabRange + Item.manaGrabRange, player.GetItemGrabRange(mana), "mana native range");
            Equal(coinBefore + Item.treasureGrabRange + Item.coinGrabRange, player.GetItemGrabRange(coin), "coin native range");
            player.ResetEffects();
            Equal(false, player.lifeMagnet || player.manaMagnet || player.goldRing || player.treasureMagnet, "native reset removes unequipped grants");
            var absent = NativeUtilityItem("\"defense\":1").Data.ToNetworkJson();
            Equal(false, absent.Contains("lifePickup", StringComparison.Ordinal), "old wire preserves omission lifePickup");
            Equal(false, absent.Contains("manaPickup", StringComparison.Ordinal), "old wire preserves omission manaPickup");
            Equal(false, absent.Contains("coinPickup", StringComparison.Ordinal), "old wire preserves omission coinPickup");
            Equal(false, absent.Contains("treasurePickup", StringComparison.Ordinal), "old wire preserves omission treasurePickup");
        });
    }
}
