using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData UseInputScopeFixture(string? scope, int delay = 0)
    {
        var data = RootSpawnFixture(4, 1);
        data.RuntimeProgram.Bindings[1].Input = RuntimeInputKind.AlternateUse;
        var action = new RuntimeEventActionSpec {
            Id = "scoped_pull", Event = RuntimeEventKind.OnUse, Action = "pull_on_event",
            ActionCode = RuntimeEventActionCode.Pull, Mode = "target_to_owner",
            Strength = 2f, RadiusTiles = 10f, DelayTicks = delay,
        };
        if (scope is not null) action.UseInput = scope;
        data.RuntimeProgram.Entities[0].Events = new[] { action };
        return data;
    }

    private static void UseInputScopeDtoRoundtripAndStrictAdmission()
    {
        foreach (string? scope in new string?[] { null, "primary_use", "alternate_use", "both" })
        {
            var source = UseInputScopeFixture(scope);
            source.Gameplay.ManaCost = 12;
            if (scope is not null) source.Gameplay.ManaCostInput = scope;
            var wire = JsonNode.Parse(source.ToNetworkJson())!;
            Equal(scope is not null, wire["gameplay"]!.AsObject().ContainsKey("manaCostInput"), "legacy mana scope stays absent");
            Equal(scope is not null, wire["runtimeProgram"]!["entities"]![0]!["events"]![0]!.AsObject().ContainsKey("useInput"), "legacy event scope stays absent");
            var copy = GeneratedItemData.FromJson(wire.ToJsonString()) ?? throw new InvalidOperationException("scoped input wire rejected");
            Equal(scope, copy.Gameplay.ManaCostInput, "mana scope roundtrip");
            Equal(scope, copy.RuntimeProgram.Entities[0].Events[0].UseInput, "event scope roundtrip");
            foreach (string field in new[] { "manaCostInput", "useInput" })
            foreach (JsonNode? invalid in new JsonNode?[] { null, JsonValue.Create("hold"), JsonValue.Create("PrimaryUse"), JsonValue.Create(1) })
            {
                var bad = wire.DeepClone();
                JsonNode owner = field == "manaCostInput" ? bad["gameplay"]! : bad["runtimeProgram"]!["entities"]![0]!["events"]![0]!;
                owner[field] = invalid?.DeepClone();
                Equal(true, GeneratedItemData.FromJson(bad.ToJsonString()) is null, "invalid present scope rejected");
            }
        }
        var absentProducer = JsonNode.Parse(UseInputScopeFixture("alternate_use").ToNetworkJson())!;
        absentProducer["runtimeProgram"]!["bindings"]!.AsArray().RemoveAt(1);
        Equal(true, GeneratedItemData.FromJson(absentProducer.ToJsonString()) is null, "explicit alternate scope requires its producer");
        absentProducer["runtimeProgram"]!["entities"]![0]!["events"]![0]!["useInput"] = "both";
        Equal(true, GeneratedItemData.FromJson(absentProducer.ToJsonString()) is not null, "both matches the remaining primary producer without inventing alternate");
        var wrongEvent = JsonNode.Parse(UseInputScopeFixture("both").ToNetworkJson())!;
        wrongEvent["runtimeProgram"]!["entities"]![0]!["events"]![0]!["event"] = "periodic";
        wrongEvent["runtimeProgram"]!["entities"]![0]!["events"]![0]!["periodTicks"] = 6;
        Equal(true, GeneratedItemData.FromJson(wrongEvent.ToJsonString()) is null, "scope cannot silently apply to a non-use event");
        var wrongEntity = JsonNode.Parse(UseInputScopeFixture("both").ToNetworkJson())!;
        var moved = wrongEntity["runtimeProgram"]!["entities"]![0]!["events"]![0]!.DeepClone();
        moved["event"] = "on_spawn";
        wrongEntity["runtimeProgram"]!["entities"]![0]!["events"] = new JsonArray();
        wrongEntity["runtimeProgram"]!["entities"]![1]!["events"] = new JsonArray(moved);
        Equal(true, GeneratedItemData.FromJson(wrongEntity.ToJsonString()) is null, "projectile cannot consume use input scope");
    }

    private static void UseInputScopeBudgetKeepsDisjointUsesIndependent()
    {
        var data = UseInputScopeFixture("both");
        data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation = 32;
        data.RuntimeProgram.Entities[0].Events = Enumerable.Range(0, 4).Select(i => new RuntimeEventActionSpec {
            Id = "spawn_" + i, Event = RuntimeEventKind.OnUse, Action = "spawn_entity_on_event",
            ActionCode = RuntimeEventActionCode.SpawnEntity, EntityId = "root", Count = 10,
            DamageBasis = RuntimeChildCombatBasis.AuthoredChild, KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild,
            UseInput = i < 2 ? RuntimeInputKind.PrimaryUse : RuntimeInputKind.AlternateUse,
        }).ToArray();
        Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is not null, "20 on each separate use fits budget32");
        foreach (var action in data.RuntimeProgram.Entities[0].Events) action.UseInput = RuntimeInputKind.PrimaryUse;
        Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is null, "40 on one input exceeds unchanged budget32");
        data.RuntimeProgram.Entities[0].Events[2].UseInput = RuntimeInputKind.AlternateUse;
        data.RuntimeProgram.Entities[0].Events[3].UseInput = "both";
        Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is not null, "shared10 plus primary20 fits32");
        data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation = 29;
        Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is null, "both10 remains common rather than disappearing from budget");
    }

    private static void UseInputScopeRoutesOnceAndRetainsDelayedAdmission()
    {
        foreach (string? scope in new string?[] { null, "primary_use", "alternate_use", "both" })
        foreach (int input in new[] { 0, 2 })
        foreach (int delay in new[] { 0, 2 })
        foreach (int mode in new[] { NetmodeID.SinglePlayer, NetmodeID.MultiplayerClient, NetmodeID.Server })
        {
            using var actors = new SwarmRuntimeScope(mode);
            using var clock = new RuntimeWorldClockScope();
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.netMode = mode; Terraria.Main.myPlayer = 0;
            var player = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, direction = 1, altFunctionUse = input };
            player.Center = new Vector2(0, 100);
            var npc = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, width = 20, height = 20,
                life = 100, lifeMax = 100, damage = 1, knockBackResist = 1f };
            npc.Center = new Vector2(100, 100);
            var host = new GeneratedItem();
            var item = new Item { type = ItemID.CopperShortsword, stack = 1 };
            AttachItem(host, item, UseInputScopeFixture(scope, delay));
            player.inventory[0] = item;
            bool selected = scope is null or "both" || scope == (input == 2 ? "alternate_use" : "primary_use");
            bool executes = selected && mode != NetmodeID.MultiplayerClient;
            Equal(true, host.UseItem(player) == true, "accepted input completes");
            if (delay > 0)
            {
                Equal(executes ? 1 : 0, PendingActions(), "only matching authoritative event queues once");
                Equal(Vector2.Zero, npc.velocity, "delayed event has no early effect");
                player.altFunctionUse = input == 2 ? 0 : 2;
                AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
                Equal(0, PendingActions(), "delayed event retires once");
            }
            Equal(executes ? new Vector2(-2, 0) : Vector2.Zero, npc.velocity, "original input selects one effect and preserves network authority");
            RuntimeDelayedActionScheduler.Clear();
        }
    }

    private static void TargetAndFireRejectsSuppressedMovement()
    {
        var source = ChildCombatFixture(targeting: true);
        Equal(true, GeneratedItemData.FromJson(source.ToNetworkJson()) is not null, "stationary target controller retains empty movement placeholder");
        foreach (var movement in new[] { new RuntimeMovementSpec { Name = "move_straight", Code = 0 },
            new RuntimeMovementSpec { Name = "move_orbit", Code = 4 } })
        {
            source.RuntimeProgram.TryGetEntity("root")!.Movement = movement;
            Equal(true, GeneratedItemData.FromJson(source.ToNetworkJson()) is null, "suppressed authored movement is not accepted as executable");
        }
    }

    private static void ManaInputScopeKeepsPrefixAndQuickUseIdentity()
    {
        using var actors = new MobilityConsumptionNativeScope();
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            var data = GeneratedPrefixFixture("magic");
            data.Gameplay.ManaCostInput = "alternate_use";
            data.RuntimeProgram.Bindings[1].Input = RuntimeInputKind.AlternateUse;
            var host = GeneratedPrefixHost(data, ItemID.AmethystStaff);
            player.inventory[0] = host.Item;
            Equal(true, host.Item.Prefix(PrefixID.Mythical), "native magic prefix accepts authored identity");
            int prefixedCost = host.Item.mana;
            Equal(true, prefixedCost < data.Gameplay.ManaCost, "native magic prefix reduces mana cost");
            foreach (int input in new[] { 0, 2, 0, 2 })
            {
                player.altFunctionUse = input;
                Equal(true, host.CanUseItem(player), "prefixed scoped binding admits");
                Equal((int)PrefixID.Mythical, (int)host.Item.prefix, "free input cannot erase accepted magic prefix");
                Equal(input == 2 ? prefixedCost : 0, host.Item.mana, "prefix cost restored without compounding across inputs");
            }
        });
        var quick = new GeneratedQuickUseSystem();
        try
        {
            quick.Load();
            WithPlayer((player, _) => {
                PrepareMobilityConsumptionPlayer(player);
                var data = NamedItemEffectsFixture();
                data.Gameplay.ManaCost = 12; data.Gameplay.ManaCostInput = "alternate_use";
                var host = MobilityConsumptionHost(data); player.inventory[0] = host.Item;
                player.altFunctionUse = 2;
                Equal(true, host.CanUseItem(player), "manual alternate before quick use");
                Equal(12, host.Item.mana, "alternate starts paid");
                Equal(true, ReferenceEquals(host.Item, player.QuickHeal_GetItemToUse()), "quick use still selects primary healing");
                Equal(0, host.Item.mana, "quick-use native admission projects free primary despite stale alternate selector");
                Equal(2, player.altFunctionUse, "quick-use does not mutate user's alternate selector");
            });
        }
        finally { quick.Unload(); }
    }

    private static void ManaInputScopeUsesNativePaymentOnly()
    {
        using var actors = new MobilityConsumptionNativeScope();
        foreach (string? scope in new string?[] { null, "primary_use", "alternate_use", "both" })
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            var data = NamedItemEffectsFixture(); data.Gameplay.ManaCost = 12;
            if (scope is not null) data.Gameplay.ManaCostInput = scope;
            var host = MobilityConsumptionHost(data);
            player.inventory[0] = host.Item;
            player.manaCost = 0.5f; player.manaFlower = false;
            foreach (int input in new[] { 0, 2, 0 })
            {
                player.altFunctionUse = input; player.statMana = 20;
                bool selected = scope is null or "both" || scope == (input == 2 ? "alternate_use" : "primary_use");
                Equal(true, host.CanUseItem(player), "selected binding admits");
                Equal(selected ? 12 : 0, host.Item.mana, "projection restores exact selected native base cost");
                Equal(20, player.statMana, "admission never pays manually");
                Equal(true, player.CheckMana(host.Item, -1, true, true), "native payment accepts available mana");
                Equal(selected ? 14 : 20, player.statMana, "native reduction and one debit preserved");
                player.statMana = 0;
                Equal(!selected, player.CheckMana(host.Item, -1, false, true), "unrelated button works without mana; selected one requires mana");
            }
        });
    }
}
