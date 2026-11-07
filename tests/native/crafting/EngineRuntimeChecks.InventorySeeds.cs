using System;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData InventorySeedData()
    {
        var data = GeneratedItemData.Placeholder();
        data.Id = "current_inventory_seeds"; data.SourceMode = "test_fixture";
        data.Gameplay.CollectSeedsFromGrass = true;
        return GeneratedItemData.FromJson(data.ToNetworkJson())
            ?? throw new Exception("current seed DTO refused: " + ContractJsonDiagnostics.LastError?.Message);
    }

    private static PropertyInfo SeedFlag() => typeof(GameplaySpec).GetProperty("CollectSeedsFromGrass")
        ?? throw new Exception("missing per-definition inventory seed flag");

    private static ModSystem SeedSystem()
    {
        Type type = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedInventorySeedSystem")
            ?? throw new Exception("missing narrow native inventory seed hook");
        return (ModSystem)Activator.CreateInstance(type)!;
    }

    private static Item SeedHost(GeneratedItemData data)
    {
        var item = new Item(ItemID.WoodenSword);
        AttachItem(new GeneratedItem(), item, data);
        return item;
    }

    private static void InventorySeedDtoKeepsLiteralAndAbsence()
    {
        GeneratedItemData data = InventorySeedData();
        Equal(true, (bool)SeedFlag().GetValue(data.Gameplay)!, "delivered opt-in survives FromJson/Normalize");
        data.Normalize();
        Equal(true, (bool)SeedFlag().GetValue(data.Gameplay)!, "normalization never clears explicit opt-in");
        SeedFlag().SetValue(data.Gameplay, false);
        Equal(false, (bool)SeedFlag().GetValue(GeneratedItemData.FromJson(data.ToNetworkJson())!.Gameplay)!, "explicit false remains declared inactive, not coerced to true");
        Equal<object?>(null, SeedFlag().GetValue(GeneratedItemData.Placeholder().Gameplay), "absent storage stays null, semantically inactive");
        var node = System.Text.Json.Nodes.JsonNode.Parse(InventorySeedData().ToNetworkJson())!;
        node["gameplay"]!.AsObject().Remove("collectSeedsFromGrass");
        var absent = GeneratedItemData.FromJson(node.ToJsonString())!;
        Equal<object?>(null, SeedFlag().GetValue(absent.Gameplay), "current optional absence is not materialized");
        string network = absent.ToNetworkJson(), local = absent.ToJson();
        Equal(false, network.Contains("collectSeedsFromGrass", StringComparison.Ordinal), "absent flag omitted from network JSON");
        Equal(false, local.Contains("collectSeedsFromGrass", StringComparison.Ordinal), "absent flag omitted from local JSON");
        var roundtrip = GeneratedItemData.FromJson(network)!;
        Equal(network, roundtrip.ToNetworkJson(), "current absent flag survives exact network roundtrip");
        Equal(GeneratedItemRegistryService.DefinitionIdentity(absent), GeneratedItemRegistryService.DefinitionIdentity(roundtrip),
            "optional absence preserves current definition identity");
        foreach (string bad in new[] { "1", "\"true\"", "null", "{}", "[]" })
        {
            node["gameplay"]!["collectSeedsFromGrass"] = System.Text.Json.Nodes.JsonNode.Parse(bad);
            bool refused;
            try { refused = GeneratedItemData.FromJson(node.ToJsonString()) is null; }
            catch (Exception e) when (e is System.Text.Json.JsonException or InvalidDataException) { refused = true; }
            Equal(true, refused, "native strict boolean refusal " + bad);
        }
        WithForgePresentationLanguages(locale => {
            var visible = InventorySeedData();
            var host = AttachItem(new GeneratedItem(), new Item(ItemID.WoodenSword), visible);
            typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
            var rows = new System.Collections.Generic.List<TooltipLine>();
            host.ModifyRuntimeTooltips(rows, expanded: true);
            const string key = "Mods.InfiniCrafterLocal.RuntimeTooltip.InventorySeedCollection";
            string expected = Terraria.Localization.Language.GetTextValue(key);
            Equal(true, !string.IsNullOrWhiteSpace(expected) && expected != key, "inventory seed localization resolves");
            Equal(expected, rows.Single(row => row.Name == "InfiniInventorySeedCollection").Text,
                "inventory passive is disclosed as its actual native condition, not an active-use promise");
            SeedFlag().SetValue(visible.Gameplay, false);
            rows.Clear(); host.ModifyRuntimeTooltips(rows, expanded: true);
            Equal(false, rows.Any(row => row.Name == "InfiniInventorySeedCollection"), "inactive flag makes no seed promise");
        });
    }

    private static void InventorySeedNativeHasItemIsInstanceLocal()
    {
        using var state = new NativeActorState();
        var system = SeedSystem();
        bool[] flags = (bool[])ItemID.Sets.DropSeedsIfInInventory.Clone();
        var player = new Player { active = true };
        var other = new Player { active = true };
        GeneratedItemData data = InventorySeedData();
        GeneratedItemRegistryService.StampCurrentWorld(data);
        Item generated = SeedHost(data);
        system.Load();
        try
        {
            foreach (int slot in new[] { 0, 49, 50, 53, 54, 57 })
            {
                player.inventory[slot] = generated;
                Equal(true, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "native inventory domain slot " + slot);
                Equal(false, player.HasItem(flags), "reference-distinct identical set is untouched");
                Equal(false, player.HasItem(ItemID.Blowpipe), "integer HasItem overload untouched");
                Equal(false, other.HasItem(ItemID.Sets.DropSeedsIfInInventory), "other player's inventory isolated");
                player.inventory[slot] = new Item();
            }
            for (int slot = 58; slot < player.inventory.Length; slot++)
            {
                player.inventory[slot] = generated;
                Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "native excluded slot " + slot);
                player.inventory[slot] = new Item();
            }
            player.bank.item[0] = generated;
            player.bank4.item[0] = generated;
            player.armor[0] = generated;
            Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "container/equipment is not inventory");
            var unflaggedData = InventorySeedData();
            GeneratedItemRegistryService.StampCurrentWorld(unflaggedData);
            SeedFlag().SetValue(unflaggedData.Gameplay, false);
            Item unflagged = SeedHost(unflaggedData);
            Equal(generated.type, unflagged.type, "separate definitions share exactly one proxy type");
            player.inventory[0] = unflagged;
            other.inventory[0] = generated;
            Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "another definition/owner cannot grant the flag");
            Equal(true, other.HasItem(ItemID.Sets.DropSeedsIfInInventory), "explicit definition remains independently enabled");
            other.inventory[0] = new Item();
            var unrelated = new bool[ItemID.Sets.DropSeedsIfInInventory.Length];
            unrelated[unflagged.type] = true;
            Equal(true, player.HasItem(unrelated), "unrelated native-positive array remains original-owned");
            player.inventory[0] = generated;
            generated.stack = 0;
            Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "zero stack is inactive");
            generated.stack = 1;
            int type = generated.type;
            generated.type = 0;
            Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "air is inactive");
            generated.type = type;
            SeedFlag().SetValue(data.Gameplay, false);
            Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "unflagged instance of same proxy type inactive");
            SeedFlag().SetValue(data.Gameplay, true);
            data.SourceMode = "player_save_ref";
            Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "unhydrated reference cannot grant flag");
            data.SourceMode = "test_fixture";
            string world = data.RecipeMeta.WorldId;
            data.RecipeMeta.WorldId = world + "_other";
            Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "foreign-world data inactive");
            data.RecipeMeta.WorldId = world;
            player.dead = true; player.active = false;
            Equal(true, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "HasItem itself has no dead/active gate, matching native");
            player.inventory[0] = new Item();
            foreach (int vanilla in new[] { ItemID.Blowpipe, ItemID.Blowgun })
            {
                player.inventory[0] = new Item(vanilla);
                Equal(true, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "native vanilla positive remains " + vanilla);
            }
            Equal(true, flags.SequenceEqual(ItemID.Sets.DropSeedsIfInInventory), "global proxy/native flags never mutated");
        }
        finally { system.Unload(); }
        player.inventory[0] = generated;
        player.dead = false; player.active = true;
        Equal(false, player.HasItem(ItemID.Sets.DropSeedsIfInInventory), "Unload removes only generated extension");
    }

    private static void InventorySeedWorldGenPreservesRandomAndOwner()
    {
        using var state = new NativeActorState();
        var system = SeedSystem();
        var data = InventorySeedData();
        GeneratedItemRegistryService.StampCurrentWorld(data);
        var owner = new Player { active = true, whoAmI = 0, position = new Vector2(160, 160) };
        var other = new Player { active = true, whoAmI = 1, position = new Vector2(1600, 1600) };
        Terraria.Main.player = Enumerable.Range(0, Terraria.Main.player.Length).Select(_ => new Player { active = false }).ToArray();
        Terraria.Main.player[0] = owner; Terraria.Main.player[1] = other;
        var nearest = typeof(WorldGen).GetMethod("GetPlayerForTile", BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)!;
        bool Drop() => WorldGen.KillTile_ShouldDropSeeds(10, 10);
        int successes = 0;
        system.Load();
        try
        {
            Equal(owner, (Player)nearest.Invoke(null, new object[] { 10, 10 })!, "native tile owner not replaced");
            foreach (int mode in new[] { NetmodeID.SinglePlayer, NetmodeID.MultiplayerClient, NetmodeID.Server })
            {
                Terraria.Main.netMode = mode;
                for (int seed = 0; seed < 32; seed++)
                {
                    var expected = new Terraria.Utilities.UnifiedRandom(seed);
                    bool selected = expected.Next(2) == 0;
                    int next = expected.Next();
                    foreach (Item witness in new[] { new Item(ItemID.Blowpipe), new Item(ItemID.Blowgun), SeedHost(data) })
                    {
                        owner.inventory[0] = witness;
                        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(seed);
                        Equal(selected, Drop(), "actual WorldGen native RNG gate " + mode + "/" + seed);
                        Equal(next, Terraria.Main.rand.Next(), "exactly native RNG consumption");
                    }
                    if (selected) successes++;
                    owner.inventory[0] = new Item(); other.inventory[0] = SeedHost(data);
                    Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(seed);
                    Equal(false, Drop(), "far player's explicit passive cannot affect tile owner");
                }
            }
            Equal(true, successes > 0, "positive RNG cohort exercised");
        }
        finally { system.Unload(); }
    }
}
