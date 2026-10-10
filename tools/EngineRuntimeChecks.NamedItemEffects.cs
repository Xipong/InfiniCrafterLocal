using System;
using System.Collections;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData NamedItemEffectsFixture()
    {
        var data = MobilityConsumptionFixture("", 1);
        data.Gameplay.HealLife = 80; data.Gameplay.HealMana = 70;
        data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 60, JumpBoost = 7f };
        data.RuntimeProgram.EffectGroups = new[] {
            new RuntimeItemEffectGroupSpec { Id = "primary_effects", HealLife = 20, Potion = true,
                GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 60, JumpBoost = 1f } },
            new RuntimeItemEffectGroupSpec { Id = "alternate_effects", HealMana = 35,
                GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 60, JumpBoost = 2f } },
        };
        data.RuntimeProgram.Bindings = new[] {
            new RuntimeBindingSpec { Id = "primary", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
                UsePolicy = new() { StackCost = 1, Action = new() { Kind = RuntimeBindingAction.ApplyItemEffects,
                    TargetId = data.RuntimeProgram.ItemEntityId, EffectGroupId = "primary_effects" } } },
            new RuntimeBindingSpec { Id = "alternate", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Primary,
                UsePolicy = new() { StackCost = 1, Action = new() { Kind = RuntimeBindingAction.ApplyItemEffects,
                    TargetId = data.RuntimeProgram.ItemEntityId, EffectGroupId = "alternate_effects" } } },
        };
        return data;
    }

    private static void NamedItemEffectsSelectNativeUseAndQuickUse()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (int input in new[] { 0, 2 })
        {
            WithPlayer((player, generated) =>
            {
                PrepareMobilityConsumptionPlayer(player);
                var host = MobilityConsumptionHost(NamedItemEffectsFixture());
                player.inventory[0] = host.Item; player.altFunctionUse = input;
                Equal(true, host.CanUseItem(player), "named use admission");
                Equal(input == 0 ? 20 : 0, host.Item.healLife, "native selected healLife");
                Equal(input == 2 ? 35 : 0, host.Item.healMana, "native selected healMana");
                scope.RunNativeSuffix(player);
                Equal(input == 0 ? 77 : 57, player.statLife, "actual native selected healing once");
                Equal(input == 2 ? 55 : 20, player.statMana, "actual native selected mana once");
                generated.PostUpdateEquips();
                Equal(input == 0 ? 1f : 2f, player.jumpSpeedBoost, "selected utility without default or other-group leak");
                Equal(0, host.Item.stack, "completed native use debits its own binding cost once");
                Equal(1, host.UseCalls, "single native use dispatch");
            });
        }
        var quickUse = new GeneratedQuickUseSystem();
        try
        {
            quickUse.Load();
            WithPlayer((player, _) =>
            {
                PrepareMobilityConsumptionPlayer(player);
                var host = MobilityConsumptionHost(NamedItemEffectsFixture());
                player.inventory[0] = host.Item; host.Item.stack = 3; player.altFunctionUse = 2;
                Equal(true, host.CanUseItem(player), "manual alternate projection before native shortcut scan");
                Equal(0, host.Item.healLife, "alternate initially hides primary native healing");
                Equal(true, ReferenceEquals(host.Item, player.QuickHeal_GetItemToUse()), "native shortcut sees primary group after alternate use");
                Equal(true, player.QuickMana_GetItemToUse() is null, "shortcut cannot borrow alternate mana");
                Equal(2, player.altFunctionUse, "shortcut preserves actual input selector");
                Equal(true, GeneratedQuickUtilityActivation.IsEligible(host.Data), "server quick-utility admission resolves primary group");
                host.Data.RuntimeProgram.EffectGroups![0].GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 60 };
                Equal(false, GeneratedQuickUtilityActivation.IsEligible(host.Data), "default utility and alternate utility cannot make primary eligible");
            });
        }
        finally { quickUse.Unload(); }
    }

    private static void NamedMobilityGroupsShareCooldownAndConsumptionOutcome()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, generated) =>
        {
            PrepareMobilityConsumptionPlayer(player);
            var data = NamedItemEffectsFixture();
            data.RuntimeProgram.EffectGroups = new[] {
                new RuntimeItemEffectGroupSpec { Id = "primary_effects", MobilityMode = "recall_home", MobilityCooldownTicks = 60 },
                new RuntimeItemEffectGroupSpec { Id = "alternate_effects", MobilityMode = "blink_to_cursor", MobilityRangeTiles = 12, MobilityCooldownTicks = 90 },
            };
            data.RuntimeProgram.Bindings[0].UsePolicy.StackCost = 0;
            var host = MobilityConsumptionHost(data);
            player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "named recall admission");
            scope.RunNativeSuffix(player);
            Equal(60, generated.GeneratedMobilityCooldownTicks, "primary sets existing player cooldown");
            Equal(1, host.Item.stack, "reusable primary retains item");
            Vector2 afterRecall = player.position;
            player.altFunctionUse = 2; player.itemTime = 0; player.itemAnimation = 20;
            Equal(true, host.CanUseItem(player), "alternate attempt admission");
            scope.RunNativeSuffix(player);
            Equal(afterRecall, player.position, "alternate cannot bypass shared cooldown");
            Equal(60, generated.GeneratedMobilityCooldownTicks, "refusal cannot replace shared cooldown with alternate value");
            Equal(1, host.Item.stack, "pure alternate mobility refusal retains authored consumable stack");
            Equal(false, ItemLoader.ConsumeItem(host.Item, player), "primary success cannot be replayed for alternate consumption");
        });
    }

    private static void NamedHeldEffectsRefreshExactOwnerItemAndBoundSnapshots()
    {
        using var scope = new MobilityConsumptionNativeScope();
        MethodInfo tick = typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityBuff", MobilityConsumptionFlags)!;
        FieldInfo ticks = typeof(InfiniCraftPlayer).GetField("_generatedBuffTicks", MobilityConsumptionFlags)!;
        FieldInfo entries = typeof(InfiniCraftPlayer).GetField("_activeGeneratedUtilityBuffs", MobilityConsumptionFlags)!;
        int snapshots = 0;
        // Count requests at the actual production sender boundary; no socket claim.
        using var sender = new Hook(typeof(InfiniCraftPlayer).GetMethod("SendGeneratedBuffState", MobilityConsumptionFlags)!,
            (Action<InfiniCraftPlayer, int, int>)((_, _, _) => snapshots++));
        WithPlayer((player, generated) =>
        {
            PrepareMobilityConsumptionPlayer(player);
            var data = MobilityConsumptionFixture("", 0);
            data.RuntimeProgram.Bindings[0].UsePolicy.Action.Kind = RuntimeBindingAction.UseItemBody;
            data.RuntimeProgram.EffectGroups = new[] { new RuntimeItemEffectGroupSpec { Id = "held_utility",
                GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 60, JumpBoost = .5f } } };
            data.RuntimeProgram.HeldEffectGroupId = "held_utility";
            var host = MobilityConsumptionHost(data);
            player.inventory[0] = host.Item;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            host.HoldItem(player);
            Equal(0, (int)ticks.GetValue(generated)!, "remote client cannot apply held player effects");
            Terraria.Main.myPlayer = player.whoAmI;
            host.HoldItem(player);
            Equal(60, (int)ticks.GetValue(generated)!, "owner applies held utility immediately");
            Equal(0, snapshots, "owner held refresh never emits server snapshots");
            tick.Invoke(generated, null);
            host.HoldItem(player);
            Equal(59, (int)ticks.GetValue(generated)!, "duplicate same-tick HoldItem does not refresh again");
            Terraria.Main.netMode = NetmodeID.Server;
            // A separate peer has its own host instance and refresh identity.
            var serverHost = MobilityConsumptionHost(data); player.inventory[0] = serverHost.Item;
            for (uint worldTick = 2100; worldTick <= 2160; worldTick++)
            {
                MaterialClock(worldTick); tick.Invoke(generated, null);
                serverHost.HoldItem(player); serverHost.HoldItem(player);
            }
            Equal(3, snapshots, "server snapshots only first refresh and each 30 world ticks");
            Equal(1, ((ICollection)entries.GetValue(generated)!).Count, "identical held refresh never accumulates per-tick entries");
            Equal(60, (int)ticks.GetValue(generated)!, "held duration refreshes exactly");
            player.inventory[0] = new Item(); MaterialClock(2161);
            serverHost.HoldItem(player);
            Equal(3, snapshots, "old host cannot refresh after held item changes");
            for (int i = 0; i < 60; i++) tick.Invoke(generated, null);
            Equal(0, (int)ticks.GetValue(generated)!, "effect expires by authored duration after release");
        });
    }

    private static void NamedItemEffectsDtoRoundTripAndInvalidPresence()
    {
        string json = NamedItemEffectsFixture().ToJson();
        var copy = GeneratedItemData.FromJson(json);
        Equal(true, copy is not null, "named groups survive exact native JSON normalization");
        Equal("alternate_effects", copy!.RuntimeProgram.Bindings[1].UsePolicy.Action.EffectGroupId!, "binding identity survives roundtrip");
        Equal(35, copy.RuntimeProgram.EffectGroups![1].HealMana, "named payload survives roundtrip");
        foreach (string mutation in new[] { "null_groups", "empty_groups", "null_selector", "missing_selector", "orphan", "foreign_stats", "null_generated_buff" })
        {
            JsonObject root = JsonNode.Parse(json)!.AsObject();
            JsonObject runtime = root["runtimeProgram"]!.AsObject();
            JsonObject group = runtime["effectGroups"]![0]!.AsObject();
            JsonObject action = runtime["bindings"]![0]!["usePolicy"]!["action"]!.AsObject();
            if (mutation == "null_groups") runtime["effectGroups"] = null;
            else if (mutation == "empty_groups") runtime["effectGroups"] = new JsonArray();
            else if (mutation == "null_selector") action["effectGroupId"] = null;
            else if (mutation == "missing_selector") action["effectGroupId"] = "missing";
            else if (mutation == "orphan") action.Remove("effectGroupId");
            else if (mutation == "foreign_stats") group["damage"] = 999;
            else group["generatedBuff"] = null;
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "strict native named-group rejection: " + mutation);
        }
    }
}
