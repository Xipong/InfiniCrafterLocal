using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolRefundStacks()
    {
        WithPlayer((player, owner) => {
            owner.Initialize();
            var data = VideoUiFixture("g_89cda498eb1f9925"); data.Id = "refund-stack"; data.RecipeKey = "refund-stack";
            var stack = AttachItem(new InfiniCrafterLocal.Content.Items.GeneratedItem(), new Terraria.Item(Terraria.ID.ItemID.Wood, 2) { maxStack = 99 }, data);
            var refund = AttachItem(new InfiniCrafterLocal.Content.Items.GeneratedItem(), new Terraria.Item(Terraria.ID.ItemID.Wood, 1) { maxStack = 99 }, GeneratedItemData.FromJson(data.ToNetworkJson())!);
            player.inventory[0] = stack.Item; owner.InputA = refund.Item;
            Equal(true, owner.TryClearInputToInventory(0), "explicit return succeeds");
            Equal(3, player.inventory[0].stack, "exact generated stack absorbs returned unit");
            Equal(true, player.inventory[1].IsAir, "no extra inventory slot consumed");
        });
        WithPlayer((player, owner) => {
            owner.Initialize(); player.whoAmI = Terraria.Main.myPlayer;
            Equal(true, owner.SetCraftRefundDeliveryPaused(true), "owner pauses delivery");
            for (int i = 0; i < 58; i++) player.inventory[i] = new Terraria.Item(Terraria.ID.ItemID.Wood, 99) { maxStack = 99 };
            player.inventory[0].stack = 98;
            owner.InputA = new Terraria.Item(Terraria.ID.ItemID.Wood, 15) { maxStack = 99 };
            Equal(true, owner.TryClearInputToInventory(0), "paused return retires station input");
            var before = owner.CaptureCraftRefunds();
            Equal(15, before[0].Stack, "paused return retains exact units");
            Equal(1, owner.ClaimCraftRefunds(), "claim merges only fitting unit");
            Equal(14, owner.CaptureCraftRefunds()[0].Stack, "partial claim keeps remainder");
            Equal(15, before[0].Stack, "previous snapshot is immutable");
            Equal(0, owner.ClaimCraftRefunds(), "full inventory neither duplicates nor drops");
            player.inventory[1].TurnToAir();
            Equal(14, owner.ClaimCraftRefunds(0), "exact row claims retained remainder");
            Equal(0, owner.CaptureCraftRefunds().Count, "complete claim retires owner row");
            Equal(14, player.inventory[1].stack, "inventory has original remainder");
            var saved = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(saved);
            owner.SetCraftRefundDeliveryPaused(false); owner.LoadData(saved);
            Equal(true, owner.PauseCraftRefundDelivery, "pause survives native character save/load");
            saved["infiniDeferredCraftRefundsV1"] = new System.Collections.Generic.List<Terraria.ModLoader.IO.TagCompound> {
                Terraria.ModLoader.IO.ItemIO.Save(new Terraria.Item(Terraria.ID.ItemID.Wood, 2)),
                new() { ["mod"] = "Terraria", ["id"] = "broken" },
                Terraria.ModLoader.IO.ItemIO.Save(new Terraria.Item(Terraria.ID.ItemID.StoneBlock, 3)),
            };
            owner.LoadData(saved);
            Equal(2, owner.CaptureCraftRefunds().Count, "bad saved row does not erase valid neighboring claims");
            Equal(5, owner.CaptureCraftRefunds().Sum(row => row.Stack), "all valid saved material units survive");
        });
    }
}
