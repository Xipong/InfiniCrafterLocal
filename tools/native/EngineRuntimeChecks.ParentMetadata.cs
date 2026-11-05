using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void StampParentMetadata(GeneratedItemData data)
    {
        data.ParentA = "Literal generated parent";
        data.ParentB = "Literal native parent";
        data.RecipeMeta.ParentIdentities = new[] { "generated:exact-parent-id", "item:Terraria/Wood:9" };
        data.RecipeMeta.ParentCategories = new[] { "weapon", "material" };
        data.RecipeMeta.ParentGeneratedDepths = new[] { 2, 0 };
        data.RecipeMeta.GenerationDepth = 3;
    }

    private static void EqualParentMetadata(GeneratedItemData expected, GeneratedItemData actual, string boundary)
    {
        Equal(expected.ParentA, actual.ParentA, boundary + " first caption");
        Equal(expected.ParentB, actual.ParentB, boundary + " second caption");
        Equal(JsonSerializer.Serialize(expected.RecipeMeta.ParentIdentities), JsonSerializer.Serialize(actual.RecipeMeta.ParentIdentities), boundary + " exact parent identities");
        Equal(JsonSerializer.Serialize(expected.RecipeMeta.ParentCategories), JsonSerializer.Serialize(actual.RecipeMeta.ParentCategories), boundary + " parent categories");
        Equal(JsonSerializer.Serialize(expected.RecipeMeta.ParentGeneratedDepths), JsonSerializer.Serialize(actual.RecipeMeta.ParentGeneratedDepths), boundary + " parent depths");
        Equal(expected.RecipeMeta.GenerationDepth, actual.RecipeMeta.GenerationDepth, boundary + " generation depth");
    }

    private static void ParentMetadataSurvivesNativeClone()
    {
        WithGeneratedPrefixScope(() =>
        {
            var data = GeneratedPrefixFixture(); StampParentMetadata(data);
            var original = GeneratedPrefixHost(data);
            string before = data.ToLocalCacheJson();
            var clone = (GeneratedItem)original.Item.Clone().ModItem;
            EqualParentMetadata(data, clone.Data, "native Item.Clone");
            Equal(false, ReferenceEquals(data.RecipeMeta.ParentIdentities, clone.Data.RecipeMeta.ParentIdentities), "clone metadata is independent");
            clone.Data.RecipeMeta.ParentIdentities[0] = "generated:only-the-clone";
            Equal(before, data.ToLocalCacheJson(), "clone cannot mutate canonical lineage");
        });
    }

    private static void ParentMetadataSurvivesDefinitionTransport()
    {
        var data = GeneratedPrefixFixture(); StampParentMetadata(data);
        data.Debug["testDiagnostic"] = JsonSerializer.SerializeToElement("bulk stays local");
        data.Visual.ImagePrompt = "bulk image prompt stays local";
        string before = data.ToLocalCacheJson();
        EqualParentMetadata(data, GeneratedItemData.FromLocalCacheJson(before)!, "full cache reader");
        var network = GeneratedItemData.FromJson(data.ToNetworkJson())!;
        Equal(true, network is not null, "current strict definition admission");
        EqualParentMetadata(data, network!, "network definition");
        Equal(0, network!.Debug.Count, "diagnostic bulk remains stripped");
        Equal("", network.Visual.ImagePrompt, "image prompt remains stripped");
        Equal(before, data.ToLocalCacheJson(), "network projection leaves source unchanged");
        // Positional metadata must not be deduplicated or guessed from captions.
        foreach (string[] identities in new[] { Array.Empty<string>(), new[] { "", "generated:known-second" }, new[] { "generated:same", "generated:same" } })
        {
            data.RecipeMeta.ParentIdentities = identities;
            EqualParentMetadata(data, data.CloneForItemInstance(), "sparse/duplicate local clone");
            EqualParentMetadata(data, GeneratedItemData.FromJson(data.ToNetworkJson())!, "sparse/duplicate wire");
        }
        var reference = GeneratedItemData.FromPlayerSaveJson(data.ToPlayerSaveJson())!;
        Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(reference), "player save remains compact reference, not second definition store");
        Equal(0, reference.RecipeMeta.ParentIdentities.Length, "unhydrated reference does not guess lineage from names");
        Equal(data.Id, reference.Id, "compact reference retains exact lookup identity");
        data.RecipeMeta.ParentIdentities = new[] { "generated:" + new string('x', GeneratedItemData.MaxDefinitionJsonBytes), "item:Terraria/Wood:9" };
        bool rejected = false;
        try { _ = data.ToNetworkJson(); } catch (InvalidDataException) { rejected = true; }
        Equal(true, rejected, "oversized lineage refuses transport instead of silently dropping parent identities");
        EqualParentMetadata(data, data.CloneForItemInstance(), "local clone does not inherit network byte budget");
    }

    private static void ParentMetadataSurvivesRegistryAndReferenceHydration()
    {
        WithGeneratedPrefixScope(() =>
        {
            using var serializer = WithPersistenceBoolSerializer();
            int world = Terraria.Main.worldID;
            var property = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
            try
            {
                Terraria.Main.worldID = 713251;
                using var registry = new GeneratedItemRegistryService();
                property.SetValue(null, registry);
                var data = GeneratedPrefixFixture(); StampParentMetadata(data);
                data.Id = "parent-metadata-native-regression";
                GeneratedItemRegistryService.StampCurrentWorld(data);
                var host = GeneratedPrefixHost(data);
                var clone = (GeneratedItem)host.Item.Clone().ModItem;
                registry.RegisterLocal(clone.Data, ensureAssets: false);
                registry.ReloadLocalCacheForCurrentWorld();
                Equal(true, registry.TryGet(data.Id, out var canonical), "persisted clone reloads through canonical registry");
                EqualParentMetadata(data, canonical, "registry persisted clone");
                var files = Directory.GetFiles(registry.StoreRoot, "*.json", SearchOption.AllDirectories);
                var saved = new TagCompound(); host.SaveData(saved);
                // Saving the full host may enrich a previously stripped clone's
                // persisted authoring data. The following reference must not replace it.
                var before = files.ToDictionary(file => file, File.ReadAllText);
                var reference = GeneratedPrefixHost(GeneratedItemData.Placeholder());
                reference.LoadData(PersistenceNbtRoundtrip(saved));
                Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(reference.Data), "SaveData/LoadData remains reference-only until hydration");
                registry.RegisterLocal(reference.Data, ensureAssets: false);
                var received = GeneratedPrefixHost(GeneratedItemData.Placeholder());
                GeneratedPrefixNetRoundtrip(reference, received);
                Equal(false, GeneratedItemData.IsPlayerSaveReferenceOnly(received.Data), "NetReceive hydrates exact identity from current-world registry");
                EqualParentMetadata(data, received.Data, "save/load/network registry hydration");
                foreach (var file in before) Equal(file.Value, File.ReadAllText(file.Key), "reference cannot overwrite canonical saved definition");
            }
            finally { property.SetValue(null, null); Terraria.Main.worldID = world; }
        });
    }

    private static void ParentMetadataSurvivesPlacedWorldSave()
    {
        using var serializer = WithPersistenceBoolSerializer();
        WithPersistenceTilemap((player, ledger) =>
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            int x = Player.tileTargetX, y = Player.tileTargetY;
            try
            {
                Player.tileTargetX = Player.tileTargetY = 40;
                var data = PersistencePlacementData(); StampParentMetadata(data);
                var item = new Item(ItemID.WoodenSword, 1);
                var generated = AttachItem(new GeneratedItem(), item, data);
                player.inventory[0] = item; player.selectedItem = 0;
                Terraria.Main.tile[40, 40].WallType = 0;
                Equal(true, generated.CanUseItem(player), "real placement captures definition before mutation");
                Terraria.Main.tile[40, 40].WallType = 1;
                Equal(true, ItemLoader.ConsumeItem(item, player), "real acceptance stores exact placement");
                var saved = new TagCompound(); ledger.SaveWorldData(saved);
                var rows = saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2");
                Equal(1, rows.Count, "one embedded definition");
                EqualParentMetadata(data, GeneratedItemData.FromJson(rows[0].GetString("definitionJson"))!, "placed definition capture");
                ledger.LoadWorldData(PersistenceNbtRoundtrip(saved));
                var reloaded = new TagCompound(); ledger.SaveWorldData(reloaded);
                EqualParentMetadata(data, GeneratedItemData.FromJson(reloaded.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0].GetString("definitionJson"))!, "world save/load");
            }
            finally { Player.tileTargetX = x; Player.tileTargetY = y; }
        });
    }
}
