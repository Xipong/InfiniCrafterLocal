using System;
using System.IO;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ModLoader;
using Terraria.Utilities;

internal static partial class EngineRuntimeChecks
{
    private static void NativeOwnStackChanceUsesOneCompletedActivation()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (int chance in new[] { 0, 1, 35, 99, 100 })
        {
            WithPlayer((player, generated) =>
            {
                PrepareMobilityConsumptionPlayer(player);
                var data = MobilityConsumptionFixture("", 1);
                data.RuntimeProgram.Bindings[0].UsePolicy.Action.Kind = RuntimeBindingAction.UseItemBody;
                data.RuntimeProgram.Bindings[0].UsePolicy.StackConsumeChancePercent = chance;
                data.RuntimeProgram.NormalizeAndValidate();
                var host = MobilityConsumptionHost(data);
                player.inventory[0] = host.Item;
                Equal(true, host.CanUseItem(player), "explicit chance admitted");
                Equal(false, ItemLoader.ConsumeItem(host.Item, player), "no completed activation cannot roll");
                player.ApplyItemTime(host.Item);
                var expectedRandom = new UnifiedRandom(4179);
                Terraria.Main.rand = new UnifiedRandom(4179);
                bool expected = chance == 100 || (chance > 0 && expectedRandom.Next(100) < chance);
                Equal(expected, ItemLoader.ConsumeItem(host.Item, player), "literal own-stack probability");
                Equal(false, ItemLoader.ConsumeItem(host.Item, player), "a repeated hook cannot roll again");
                Equal(expectedRandom.Next(), Terraria.Main.rand.Next(), "exactly one interior roll and no endpoint/replay rolls");
            });
        }
        WithPlayer((player, generated) =>
        {
            PrepareMobilityConsumptionPlayer(player);
            var data = MobilityConsumptionFixture("recall_home", 1);
            data.RuntimeProgram.Bindings[0].UsePolicy.StackConsumeChancePercent = 100;
            var host = MobilityConsumptionHost(data);
            player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "mobility chance admitted");
            Equal(true, generated.TryReserveGeneratedMobilityCooldown(30), "another effect reserves shared cooldown");
            scope.RunNativeSuffix(player);
            Equal(1, host.Item.stack, "failed mobility cannot spend even at 100 percent");
        });
    }

}
