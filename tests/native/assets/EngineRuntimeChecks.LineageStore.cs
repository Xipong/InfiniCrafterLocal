using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData CurrentLineageItem(string id, params string[] parents)
    {
        var data = GeneratedPrefixFixture();
        data.Id = id; data.Name = id; data.RecipeKey = "recipe-" + id;
        data.ParentA = "First ingredient"; data.ParentB = "Second ingredient";
        GeneratedItemRegistryService.StampCurrentWorld(data);
        data.RecipeMeta.ParentIdentities = parents;
        return data;
    }

    private static void LineageLoadsOnlyCurrentStoreWithoutInference()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713261;
            using var registry = new GeneratedItemRegistryService();
            var parent = CurrentLineageItem("current-lineage-parent", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            var current = CurrentLineageItem("current-lineage-child", "generated:" + parent.Id, "item:Terraria/Wood:9");
            registry.RegisterLocal(parent, ensureAssets: false);
            registry.RegisterLocal(current, ensureAssets: false);
            var missing = CurrentLineageItem("current-lineage-missing");
            missing.ParentA = parent.Name;
            missing.Gameplay.Damage = 91;
            registry.RegisterLocal(missing, ensureAssets: false);
            var old = missing.CloneForItemInstance();
            old.RecipeMeta.ParentIdentities = current.RecipeMeta.ParentIdentities.ToArray();
            File.WriteAllText(Path.Combine(registry.StoreRoot, "old-record.json"), old.ToJson());
            var orphan = CurrentLineageItem("retired-flat-only", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            File.WriteAllText(Path.Combine(registry.StoreRoot, "flat-only.json"), orphan.ToJson());
            string root = Path.GetDirectoryName(registry.StoreRoot)!;
            string recipes = Path.Combine(root, "Studio", "data", "cache", "world_recipes", "world_713261", "recipes");
            Directory.CreateDirectory(recipes);
            orphan.Id = "retired-bundled-only";
            File.WriteAllText(Path.Combine(recipes, "old.json"), orphan.ToJson());
            File.WriteAllText(Path.Combine(recipes, "same-result.json"), old.ToJson());
            string sidecars = Path.Combine(root, "atlas_lineage"); Directory.CreateDirectory(sidecars);
            File.WriteAllText(Path.Combine(sidecars, "world_713261.json"), JsonSerializer.Serialize(new {
                worldId = "713261", items = new System.Collections.Generic.Dictionary<string, object> {
                    [missing.Id] = new { recipeKey = missing.RecipeKey, parentIdentities = old.RecipeMeta.ParentIdentities }
                }
            }));
            var before = Directory.GetFiles(root, "*.json", SearchOption.AllDirectories).ToDictionary(path => path, File.ReadAllBytes);
            for (int repeat = 0; repeat < 2; repeat++)
            {
                registry.ReloadLocalCacheForCurrentWorld();
                Equal(true, registry.TryGet(current.Id, out var loaded), "current world/id store roundtrip");
                Equal(string.Join("|", current.RecipeMeta.ParentIdentities), string.Join("|", loaded.RecipeMeta.ParentIdentities), "current explicit identities survive unchanged");
                Equal<int?>(2, RecipeLineageGraph.Build(loaded, registry.Snapshot()).GenerationDepth, "current lineage remains usable");
                Equal(true, registry.TryGet(missing.Id, out var unknown), "incomplete lineage does not discard current executable item");
                Equal(0, unknown.RecipeMeta.ParentIdentities.Length, "old records and captions never fill missing lineage");
                Equal(91, unknown.Gameplay.Damage, "no historical mechanics substitution");
                Equal<int?>(null, RecipeLineageGraph.Build(unknown, registry.Snapshot()).GenerationDepth, "unknown ancestry remains unknown");
                Equal(false, registry.TryGet("retired-flat-only", out _), "flat historical definitions are not imported");
                Equal(false, registry.TryGet("retired-bundled-only", out _), "bundled recipe history is not imported");
                foreach (var file in before) Equal(true, file.Value.SequenceEqual(File.ReadAllBytes(file.Key)), "all source data is preserved byte-for-byte");
            }
        }
        finally { Terraria.Main.worldID = world; }
    }

    private static void LineageRegistrationDoesNotRecoverPriorMetadata()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713262;
            using var registry = new GeneratedItemRegistryService();
            var data = CurrentLineageItem("current-lineage-replace", "generated:parent", "item:Terraria/Wood:9");
            registry.RegisterLocal(data, ensureAssets: false);
            var replacement = data.CloneForItemInstance(); replacement.RecipeMeta.ParentIdentities = Array.Empty<string>();
            registry.RegisterLocal(replacement, ensureAssets: false);
            Equal(0, replacement.RecipeMeta.ParentIdentities.Length, "registration does not reattach old lineage evidence");
            registry.ReloadLocalCacheForCurrentWorld();
            Equal(true, registry.TryGet(data.Id, out var reloaded), "replacement persists normally");
            Equal(0, reloaded.RecipeMeta.ParentIdentities.Length, "reload does not infer missing parents");
            Terraria.Main.worldID++;
            registry.ReloadLocalCacheForCurrentWorld();
            Equal(false, registry.TryGet(data.Id, out _), "world isolation remains exact");
        }
        finally { Terraria.Main.worldID = world; }
    }
}
