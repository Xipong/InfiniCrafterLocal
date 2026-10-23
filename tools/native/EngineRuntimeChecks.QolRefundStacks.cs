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
    }
}
