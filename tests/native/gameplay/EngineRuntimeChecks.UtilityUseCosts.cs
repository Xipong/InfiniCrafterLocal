using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData UtilityCostFixture(bool named, int stackCost)
    {
        var data = MobilityConsumptionFixture("", stackCost);
        data.Id = "utility-cost-check"; data.Name = "Utility cost check"; data.SourceMode = "test_fixture";
        data.Gameplay.ManaCost = 10;
        data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 60, ExhaustionTicks = 120, MovementSpeed = .25f };
        if (named)
        {
            data.RuntimeProgram.EffectGroups = new[] { new RuntimeItemEffectGroupSpec {
                Id = "selected", GeneratedBuff = data.Gameplay.GeneratedBuff } };
            data.RuntimeProgram.Bindings[0].Input = RuntimeInputKind.AlternateUse;
            data.RuntimeProgram.Bindings[0].UsePolicy.Action.EffectGroupId = "selected";
            data.Gameplay.GeneratedBuff = new GeneratedBuffSpec();
        }
        GeneratedItemRegistryService.StampCurrentWorld(data);
        return data;
    }

    private static bool UtilityNativeAdmission(Player player, Item item)
        => (bool)typeof(Player).GetMethod("ItemCheck_CheckCanUse", MobilityConsumptionFlags)!.Invoke(player, new object[] { item })!;

    private static void UtilityExhaustionRefusesNativeCosts()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (bool named in new[] { false, true })
        foreach (int stackCost in new[] { 0, 1 })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(100);
            player.statMana = 100; player.manaCost = 1f;
            var host = MobilityConsumptionHost(UtilityCostFixture(named, stackCost));
            player.inventory[0] = host.Item; host.Item.stack = 3;
            player.altFunctionUse = named ? 2 : 0;
            Equal(true, UtilityNativeAdmission(player, host.Item), "first native admission");
            Equal(90, player.statMana, "first real native mana payment");
            scope.RunNativeSuffix(player);
            Equal(3 - stackCost, host.Item.stack, "first native stack payment");
            Equal(60, ExhaustionBuffTicks(generated), "first utility activation");
            MaterialClock(110); ExhaustionBuffTick(generated);
            Equal(false, UtilityNativeAdmission(player, host.Item), "exhausted utility refuses native admission before mana");
            Equal(90, player.statMana, "refused use cannot debit native mana");
            Equal(3 - stackCost, host.Item.stack, "refused use cannot spend another item");
            Equal(59, ExhaustionBuffTicks(generated), "refused use does not refresh buff");
            MaterialClock(220);
            Equal(true, UtilityNativeAdmission(player, host.Item), "exact exhaustion expiry admits");
            Equal(80, player.statMana, "expiry pays once");
        });
    }

    private static void UtilityRefusalPreservesMixedActions()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (string companion in new[] { "heal", "extra-buff", "mobility" })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(100);
            player.statMana = 100; player.manaCost = 1f;
            var data = UtilityCostFixture(false, 1);
            if (companion == "heal") data.Gameplay.HealLife = 7;
            if (companion == "extra-buff") data.Gameplay.ExtraBuffs = new[] { new BuffEntrySpec { BuffCode = BuffID.Swiftness, BuffTime = 60 } };
            if (companion == "mobility") { data.Gameplay.MobilityMode = "recall_home"; data.Gameplay.MobilityCooldownTicks = 60; }
            var host = MobilityConsumptionHost(data); player.inventory[0] = host.Item;
            Equal(true, ExhaustionApply(generated, data.Gameplay.GeneratedBuff, data), "seed exhaustion");
            Equal(true, UtilityNativeAdmission(player, host.Item), companion + " mixed use keeps other effects");
            Equal(90, player.statMana, companion + " native authored cost retained");
            scope.RunNativeSuffix(player);
            Equal(0, host.Item.stack, companion + " successful companion retains stack cost");
            if (companion == "heal") Equal(64, player.statLife, "real native healing");
            if (companion == "extra-buff") Equal(true, player.HasBuff(BuffID.Swiftness), "extra buff applied");
            if (companion == "mobility") Equal(1f, player.teleportTime, "native teleport retained");
        });
    }

    private static void UtilityExhaustionRespectsEventInputScope()
    {
        foreach (string input in new[] { RuntimeInputKind.PrimaryUse, RuntimeInputKind.AlternateUse })
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(100);
            var data = UtilityCostFixture(false, 0);
            data.RuntimeProgram.Bindings = new[] { data.RuntimeProgram.Bindings[0], new RuntimeBindingSpec {
                Id = "alternate", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec { Action = new RuntimeBindingActionSpec {
                    Kind = RuntimeBindingAction.ApplyItemEffects, TargetId = data.RuntimeProgram.ItemEntityId } } } };
            data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!.Events = new[] {
                new RuntimeEventActionSpec { Id = "companion", Event = RuntimeEventKind.OnUse,
                    Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                    Mode = "target_to_owner", Strength = 2f, RadiusTiles = 10f, UseInput = input } };
            var host = MobilityConsumptionHost(data); player.inventory[0] = host.Item;
            Equal(true, ExhaustionApply(generated, data.Gameplay.GeneratedBuff, data), "seed exhaustion");
            Equal(input == RuntimeInputKind.PrimaryUse, host.CanUseItem(player),
                "only the accepted input's companion prevents pure utility rejection");
        });
    }

    private static void UtilityUseStackFollowsActualOutcome()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, generated) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(100);
            var data = UtilityCostFixture(false, 1);
            var host = MobilityConsumptionHost(data); player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "admission before intervening activation");
            Equal(true, ExhaustionApply(generated, data.Gameplay.GeneratedBuff, data), "intervening activation starts fatigue");
            scope.RunNativeSuffix(player);
            Equal(1, host.Item.stack, "post-admission refused pure buff must not consume item");
            Equal(1, host.UseCalls, "refusal still completes native timing");
            Equal(false, ItemLoader.ConsumeItem(host.Item, player), "failed outcome cannot be replayed");
        });
    }
}
