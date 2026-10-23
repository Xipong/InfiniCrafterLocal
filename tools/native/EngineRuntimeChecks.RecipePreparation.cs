#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void RecipePreparation()
 {
        WithPlayer((player, owner) => {
            var old = Terraria.Main.mouseItem; bool inventory = Terraria.Main.playerInventory; int net = Terraria.Main.netMode;
            try { Terraria.Main.mouseItem = new Terraria.Item(); Terraria.Main.playerInventory = true; Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
                var data = GeneratedItemData.Placeholder(); data.Id = "recipe"; data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString();
                data.RecipeMeta.ParentIdentities = new[] { "item:Terraria/Wood:9", "item:Terraria/Wood:9" };
                player.inventory[3] = new Terraria.Item(Terraria.ID.ItemID.Wood, 1);
                Equal(-1, InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.RecipeIngredientSlots(player, data.RecipeMeta.WorldId, data.RecipeMeta.ParentIdentities)[1], "duplicate parents need two units");
                player.inventory[3].stack = 3;
                Equal(true, owner.PrepareKnownRecipe(data, 0), "known recipe admitted");
                owner.TickRecipePreparation(); owner.TickRecipePreparation(); owner.TickRecipePreparation();
                Equal(1, player.inventory[3].stack, "two units transferred exactly");
                Equal(1, owner.StationInput(0).stack, "A ready"); Equal(1, owner.StationInput(1).stack, "B ready");
                Equal(false, owner.HasAnyCraftLanePending, "preparation never starts generation");
            } finally { Terraria.Main.mouseItem=old; Terraria.Main.playerInventory=inventory; Terraria.Main.netMode=net; }
        });
 }
}
