using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData AtlasRecoveryItem(string id, params string[] parents)
    {
        var data = GeneratedPrefixFixture();
        data.Id = id; data.Name = id; data.RecipeKey = "recipe-" + id;
        data.ParentA = "First ingredient"; data.ParentB = "Second ingredient";
        GeneratedItemRegistryService.StampCurrentWorld(data);
        data.RecipeMeta.ParentIdentities = parents;
        return data;
    }

    private static void AtlasRecoveryReadsExactHistoricalMetadata()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713261;
            using var registry = new GeneratedItemRegistryService();
            var first = AtlasRecoveryItem("atlas-recovery-first", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            registry.RegisterLocal(first, ensureAssets: false);
            var previous = AtlasRecoveryItem("atlas-recovery-second", "generated:" + first.Id, "item:Terraria/Wood:9");
            var current = previous.CloneForItemInstance(); current.RecipeMeta.ParentIdentities = Array.Empty<string>();
            current.Gameplay.Damage = 91; current.Visual.SpritePath = "current-authoritative.png";
            current.RecipeMeta.GenerationDepth = 0;
            registry.RegisterLocal(current, ensureAssets: false);
            File.WriteAllText(Path.Combine(registry.StoreRoot, "atlas-recovery-historical.json"), previous.ToLocalCacheJson());
            var before = Directory.GetFiles(registry.StoreRoot, "*.json", SearchOption.AllDirectories)
                .ToDictionary(file => file, File.ReadAllBytes);
            for (int repeat = 0; repeat < 2; repeat++)
            {
                registry.ReloadLocalCacheForCurrentWorld();
                Equal(true, registry.TryGet(current.Id, out var restored), "scoped current definition remains registered");
                Equal(string.Join("|", previous.RecipeMeta.ParentIdentities), string.Join("|", restored.RecipeMeta.ParentIdentities), "historical exact identities fill missing parents");
                Equal(91, restored.Gameplay.Damage, "historical mechanics never replace current mechanics");
                Equal("current-authoritative.png", restored.Visual.SpritePath, "historical asset paths never replace current assets");
                Equal(0, restored.RecipeMeta.GenerationDepth, "stored depth never fabricated");
                Equal(true, registry.GetLineageRecoveryReceipts().Any(receipt => receipt == "fix:restore_exact_recipe_parent_identity:" + current.Id + ":0"), "exact recovery carries a fix receipt");
                Equal<int?>(2, RecipeLineageGraph.Build(restored, registry.Snapshot()).GenerationDepth, "restored graph derives old craft generation");
                foreach (var file in before) Equal(true, file.Value.SequenceEqual(File.ReadAllBytes(file.Key)), "cache recovery is read only");
            }
        }
        finally { Terraria.Main.worldID = world; }
    }

    private static void AtlasRecoveryRefusesAmbiguousOrForeignEvidence()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713262;
            using var registry = new GeneratedItemRegistryService();
            var target = AtlasRecoveryItem("atlas-recovery-conflict");
            registry.RegisterLocal(target, ensureAssets: false);
            var first = target.CloneForItemInstance(); first.RecipeMeta.ParentIdentities = new[] { "generated:first", "item:Terraria/Wood:9" };
            var second = first.CloneForItemInstance(); second.RecipeMeta.ParentIdentities[0] = "generated:second";
            File.WriteAllText(Path.Combine(registry.StoreRoot, "atlas-evidence-a.json"), first.ToLocalCacheJson());
            File.WriteAllText(Path.Combine(registry.StoreRoot, "atlas-evidence-b.json"), second.ToLocalCacheJson());
            registry.ReloadLocalCacheForCurrentWorld();
            registry.TryGet(target.Id, out var restored);
            Equal("", restored.RecipeMeta.ParentIdentities[0], "conflicting historical identity stays unknown");
            Equal("item:Terraria/Wood:9", restored.RecipeMeta.ParentIdentities[1], "unambiguous independent slot remains recoverable");
            Equal<int?>(null, RecipeLineageGraph.Build(restored, registry.Snapshot()).GenerationDepth, "incomplete ancestry does not invent generation");

            foreach (string mismatch in new[] { "world", "recipe", "result", "slot-order" })
            {
                var missing = AtlasRecoveryItem("atlas-recovery-negative-" + mismatch);
                registry.RegisterLocal(missing, ensureAssets: false);
                var source = missing.CloneForItemInstance(); source.RecipeMeta.ParentIdentities = first.RecipeMeta.ParentIdentities.ToArray();
                if (mismatch == "world") source.RecipeMeta.WorldId = "foreign";
                if (mismatch == "recipe") source.RecipeKey += "different";
                if (mismatch == "result") source.Id += "different";
                if (mismatch == "slot-order") (source.ParentA, source.ParentB) = (source.ParentB, source.ParentA);
                File.WriteAllText(Path.Combine(registry.StoreRoot, "atlas-evidence-" + mismatch + ".json"), source.ToLocalCacheJson());
                registry.ReloadLocalCacheForCurrentWorld();
                registry.TryGet(missing.Id, out var unchanged);
                Equal(0, unchanged.RecipeMeta.ParentIdentities.Length, "no recovery across " + mismatch);
            }
        }
        finally { Terraria.Main.worldID = world; }
    }

    private static void AtlasRecoveryPreventsLaterMetadataDowngrade()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713263;
            using var registry = new GeneratedItemRegistryService();
            var data = AtlasRecoveryItem("atlas-recovery-downgrade", "generated:known-parent", "item:Terraria/Wood:9");
            registry.RegisterLocal(data, ensureAssets: false);
            var stripped = data.CloneForItemInstance(); stripped.RecipeMeta.ParentIdentities = Array.Empty<string>();
            registry.RegisterLocal(stripped, ensureAssets: false);
            Equal("generated:known-parent", stripped.RecipeMeta.ParentIdentities[0], "stripped old container cannot erase known ancestry");
            stripped.RecipeMeta.ParentIdentities = Array.Empty<string>(); // same mutable object as registry
            registry.RegisterLocal(stripped, ensureAssets: false);
            Equal("generated:known-parent", stripped.RecipeMeta.ParentIdentities[0], "detached evidence survives in-place metadata loss");
            registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(data.Id, out var reloaded);
            Equal("generated:known-parent", reloaded.RecipeMeta.ParentIdentities[0], "normal persist keeps recovered metadata across restart");
            var conflicting = data.CloneForItemInstance(); conflicting.RecipeMeta.ParentIdentities = new[] { "generated:explicit-new-parent", "" };
            registry.RegisterLocal(conflicting, persist: false, ensureAssets: false);
            Equal("generated:explicit-new-parent", conflicting.RecipeMeta.ParentIdentities[0], "existing nonempty identity is never overwritten");
            Equal("", conflicting.RecipeMeta.ParentIdentities[1], "conflicting recipe evidence cannot fill another slot");
            Terraria.Main.worldID++; registry.ReloadLocalCacheForCurrentWorld();
            var otherWorld = AtlasRecoveryItem(data.Id); registry.RegisterLocal(otherWorld, persist: false, ensureAssets: false);
            Equal(0, otherWorld.RecipeMeta.ParentIdentities.Length, "world switch clears detached evidence");
        }
        finally { Terraria.Main.worldID = world; }
    }

    private static void AtlasRecoveryReadsCommittedBundledRecipes()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713264;
            using var registry = new GeneratedItemRegistryService();
            var parent = AtlasRecoveryItem("atlas-bundled-parent", "item:Terraria/Wood:9", "item:Terraria/StoneBlock:3");
            var child = AtlasRecoveryItem("atlas-bundled-child", "generated:" + parent.Id, "item:Terraria/Wood:9");
            string recipes = Path.Combine(Path.GetDirectoryName(registry.StoreRoot)!, "Studio", "data", "cache", "world_recipes", "world_713264", "recipes");
            Directory.CreateDirectory(recipes);
            File.WriteAllText(Path.Combine(recipes, "parent.json"), parent.ToLocalCacheJson());
            File.WriteAllText(Path.Combine(recipes, "child.json"), child.ToLocalCacheJson());
            var foreign = child.CloneForItemInstance(); foreign.Id = "atlas-bundled-foreign"; foreign.RecipeMeta.WorldId = "713265";
            File.WriteAllText(Path.Combine(recipes, "foreign.json"), foreign.ToLocalCacheJson());
            File.WriteAllText(Path.Combine(recipes, "invalid.json"), child.ToLocalCacheJson().Replace("\"schemaVersion\":5", "\"schemaVersion\":4"));
            var placeholder = child.CloneForItemInstance(); placeholder.Id = "placeholder";
            File.WriteAllText(Path.Combine(recipes, "placeholder.json"), placeholder.ToLocalCacheJson());
            var conflict = child.CloneForItemInstance(); conflict.Id = "atlas-bundled-ambiguous";
            File.WriteAllText(Path.Combine(recipes, "conflict-a.json"), conflict.ToLocalCacheJson());
            conflict.Gameplay.Damage++;
            File.WriteAllText(Path.Combine(recipes, "conflict-b.json"), conflict.ToLocalCacheJson());
            var paths = child.CloneForItemInstance(); paths.Id = "atlas-bundled-path-conflict";
            paths.Visual.SpritePath = "old/icon.png";
            File.WriteAllText(Path.Combine(recipes, "paths-a.json"), paths.ToLocalCacheJson());
            paths.Visual.SpritePath = "new/icon.png";
            File.WriteAllText(Path.Combine(recipes, "paths-b.json"), paths.ToLocalCacheJson());
            var large = child.CloneForItemInstance(); large.Id = "atlas-bundled-local-large";
            large.RecipeMeta.ParentIdentities = new[] { "generated:" + new string('x', GeneratedItemData.MaxDefinitionJsonBytes), "item:Terraria/Wood:9" };
            File.WriteAllText(Path.Combine(recipes, "large.json"), large.ToLocalCacheJson());
            var priority = AtlasRecoveryItem("atlas-bundled-priority");
            priority.Gameplay.Damage = 71; priority.Visual.SpritePath = "current/priority.png";
            registry.RegisterLocal(priority, ensureAssets: false);
            var older = priority.CloneForItemInstance(); older.Gameplay.Damage = 3; older.Visual.SpritePath = "old/priority.png";
            older.RecipeMeta.ParentIdentities = new[] { "generated:" + parent.Id, "item:Terraria/Wood:9" };
            File.WriteAllText(Path.Combine(recipes, "priority.json"), older.ToLocalCacheJson());
            var registryBefore = Directory.GetFiles(registry.StoreRoot, "*.json", SearchOption.AllDirectories).ToDictionary(file => file, File.ReadAllBytes);
            var before = Directory.GetFiles(recipes).ToDictionary(file => file, File.ReadAllBytes);
            registry.ReloadLocalCacheForCurrentWorld();
            Equal(true, registry.TryGet(child.Id, out var recovered), "committed generator recipe recovers missing registry definition");
            Equal<int?>(2, RecipeLineageGraph.Build(recovered, registry.Snapshot()).GenerationDepth, "bundled history restores exact ancestry");
            Equal(false, registry.TryGet(foreign.Id, out _), "bundled directory is not proof of world ownership");
            Equal(false, registry.TryGet(conflict.Id, out _), "conflicting bundled definitions cannot choose mechanics by filename");
            Equal(false, registry.TryGet(paths.Id, out _), "same asset basename cannot hide conflicting full local paths");
            Equal(true, registry.TryGet(large.Id, out _), "local recovery does not inherit network projection size limit");
            registry.TryGet(priority.Id, out var retained);
            Equal(71, retained.Gameplay.Damage, "bundled evidence cannot overwrite canonical mechanics");
            Equal("current/priority.png", retained.Visual.SpritePath, "bundled evidence cannot overwrite canonical asset paths");
            Equal("generated:" + parent.Id, retained.RecipeMeta.ParentIdentities[0], "bundled evidence still restores exact canonical parent metadata");
            Equal(4, registry.Snapshot().Length, "only unambiguous valid exact current-world recipes admitted");
            Equal(registryBefore.Count, Directory.GetFiles(registry.StoreRoot, "*.json", SearchOption.AllDirectories).Length, "recovery creates no replacement registry files");
            foreach (var file in registryBefore) Equal(true, file.Value.SequenceEqual(File.ReadAllBytes(file.Key)), "canonical source remains byte exact");
            foreach (var file in before) Equal(true, file.Value.SequenceEqual(File.ReadAllBytes(file.Key)), "generator sources remain byte exact");
        }
        finally { Terraria.Main.worldID = world; }
    }
}
