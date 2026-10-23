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
            var ui = (Terraria.Main.hasFocus, Terraria.Main.gameMenu, Terraria.Main.hideUI, Terraria.Main.mapFullscreen,
                Terraria.Main.ingameOptionsWindow, Terraria.Main.inFancyUI, Terraria.Main.drawingPlayerChat);
            try {
                player.active = true; player.chest = -1;
                Terraria.Main.hasFocus = true; Terraria.Main.gameMenu = Terraria.Main.hideUI = Terraria.Main.mapFullscreen = false;
                Terraria.Main.ingameOptionsWindow = Terraria.Main.inFancyUI = Terraria.Main.drawingPlayerChat = false;
                Terraria.Main.mouseItem = new Terraria.Item(); Terraria.Main.playerInventory = true; Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
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
                owner.TryClearAllInputsToInventory();
                Equal(true, owner.TrySetMultiDevWindowCount(3, syncServer: false), "enable preparation lane");
                player.inventory[3] = new Terraria.Item(Terraria.ID.ItemID.Wood, 2);
                Equal(true, owner.PrepareKnownRecipe(data, 2), "queue preparation before first deposit");
                Equal(false, owner.TrySetMultiDevWindowCount(1, syncServer: false), "queued preparation protects its visible lane");
                typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetField("_multiDevWindowCount", TestInstance)!.SetValue(owner, 1);
                owner.TickRecipePreparation();
                Equal(false, owner.HasRecipePreparation, "external lane shrink retires preparation");
                Equal(2, player.inventory[3].stack, "hidden lane receives no ingredient");
                Equal(true, owner.StationInput(4).IsAir && owner.StationInput(5).IsAir, "hidden inputs remain empty");
            } finally {
                (Terraria.Main.hasFocus, Terraria.Main.gameMenu, Terraria.Main.hideUI, Terraria.Main.mapFullscreen,
                    Terraria.Main.ingameOptionsWindow, Terraria.Main.inFancyUI, Terraria.Main.drawingPlayerChat) = ui;
                Terraria.Main.mouseItem=old; Terraria.Main.playerInventory=inventory; Terraria.Main.netMode=net; }
        });
 }
}
