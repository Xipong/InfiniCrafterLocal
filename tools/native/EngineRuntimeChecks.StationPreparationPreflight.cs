#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks { private static void StationPreparationPreflight() {
WithPlayer((player, owner) => {
            var mouse = Terraria.Main.mouseItem;
            try {
                Terraria.Main.mouseItem = new Terraria.Item();
                var data = GeneratedItemData.Placeholder(); data.RecipeMeta.WorldId = Terraria.Main.worldID.ToString();
                data.RecipeMeta.ParentIdentities = new[] { "item:Terraria/Wood:9", "item:Terraria/Wood:9" };
                player.inventory[3] = new Terraria.Item(Terraria.ID.ItemID.Wood, 1);
                Equal(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.RecipePreparationReadiness.MissingStock, owner.GetRecipePreparationReadiness(data, 0), "duplicate parent shortage");
                player.inventory[3].stack = 2; player.inventory[3].favorited = true;
                Equal(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.RecipePreparationReadiness.ProtectedStock, owner.GetRecipePreparationReadiness(data, 0), "protected sufficient stock");
                player.inventory[3].favorited = false;
                Equal(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer.RecipePreparationReadiness.Ready, owner.GetRecipePreparationReadiness(data, 0), "exact two-unit stock admitted");
                Equal(2, player.inventory[3].stack, "preflight is observational");
            } finally { Terraria.Main.mouseItem = mouse; }
        });
} }
