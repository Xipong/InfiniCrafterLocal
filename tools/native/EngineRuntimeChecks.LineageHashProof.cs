using System;
using System.IO;
using System.Linq;
using System.Diagnostics;
using System.Collections.Generic;
using System.Text.Json;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData HashProofItem(string id = "proof")
    {
        var data = GeneratedItemData.Placeholder();
        data.Id = id; data.ParentA = "Гелевое копье статуи"; data.ParentB = "Эбонит";
        data.RecipeKey = "r_018b30bc4f5a6d192ba1d3d8";
        data.RecipeMeta.WorldId = "853355558"; data.RecipeMeta.WorldScoped = true;
        data.RecipeMeta.ParentIdentities = Array.Empty<string>();
        return data;
    }

    private static void LineageHashProofBoundaries()
    {
        const string a = "generated:g_4a1c8253fd834bff", b = "item:Terraria/EbonstoneBlock:61", wrong = "item:Terraria/EbonsandBlock:370";
        var data = HashProofItem();
        var candidates = new RecipeParentIdentityProof.Candidates(new[] { data });
        candidates.Add(data.ParentA, a); candidates.Add(data.ParentB, b); candidates.Add(data.ParentB, wrong);
        string? Resolve(GeneratedItemData value, string world = "853355558") { int budget = 64; return RecipeParentIdentityProof.Resolve(value, world, candidates, ref budget) is { } ids ? string.Join("|", ids) : null; }
        Equal(data.RecipeKey, RecipeParentIdentityProof.Key(a, b, "853355558"), "C# hash equals recorded Python recipe key");
        Equal<string?>(null, Resolve(data), "a commutative hash does not certify original order");
        int setBudget = 64;
        Equal(a + "|" + b, string.Join("|", RecipeParentIdentityProof.ResolveSet(data, "853355558", candidates, ref setBudget)!), "same-caption native alternatives are distinguished as an unordered pair");
        Equal<string?>(null, Resolve(data, "853355559"), "foreign world cannot restore identities");
        data.RecipeMeta.WorldScoped = false; Equal<string?>(null, Resolve(data), "unscoped record cannot restore"); data.RecipeMeta.WorldScoped = true;
        data.RecipeMeta.ParentIdentities = new[] { wrong, "" }; Equal<string?>(null, Resolve(data), "current conflicting identity is never replaced");
        data.RecipeMeta.ParentIdentities = new[] { a, "" }; Equal(a + "|" + b, Resolve(data), "matching partial identity can be completed");
        data.RecipeMeta.ParentIdentities = new[] { a, "", "" }; Equal<string?>(null, Resolve(data), "malformed slot count stays unknown");
        data.RecipeMeta.ParentIdentities = Array.Empty<string>();
        int shortBudget = 1; Equal(true, RecipeParentIdentityProof.Resolve(data, "853355558", candidates, ref shortBudget) is null, "partial candidate scan cannot prove uniqueness");
        Equal(1, shortBudget, "insufficient budget does not begin hashing");
        data.RecipeKey = "r_000000000000000000000000"; Equal<string?>(null, Resolve(data), "names alone are never evidence");
        data = HashProofItem(); data.ParentA = data.ParentB = "same";
        candidates = new RecipeParentIdentityProof.Candidates(new[] { data }); candidates.Add("same", a); candidates.Add("same", b);
        Equal<string?>(null, Resolve(data), "same captions cannot invent order for distinct identities");
        data.RecipeKey = RecipeParentIdentityProof.Key(a, a, "853355558")!;
        Equal(a + "|" + a, Resolve(data), "identical ingredient pair has one ordered identity");
        for (int i = 0; i < 17; i++) candidates.Add("same", "generated:overflow_" + i);
        Equal<string?>(null, Resolve(data), "candidate overflow cannot select an arbitrary subset");
        Equal<string?>(null, RecipeParentIdentityProof.Key("item:Мод/Имя:61", b, "853355558"), "unsupported legacy JSON encoding is not guessed");
    }

    private static void LineageHashProofLargeWorldBudget()
    {
        var records = Enumerable.Range(0, 20000).Select(index => HashProofItem("large_" + index)).ToArray();
        var clock = Stopwatch.StartNew();
        var targets = records.OrderBy(data => data.Id, StringComparer.Ordinal).Take(RecipeParentIdentityProof.MaxTargets).ToArray();
        var candidates = new RecipeParentIdentityProof.Candidates(targets);
        foreach (var record in records) candidates.Add("irrelevant_" + record.Id, "generated:" + record.Id);
        candidates.Add(targets[0].ParentA, "generated:g_4a1c8253fd834bff");
        candidates.Add(targets[0].ParentB, "item:Terraria/EbonstoneBlock:61");
        candidates.Add(targets[0].ParentB, "item:Terraria/EbonsandBlock:370");
        int budget = RecipeParentIdentityProof.MaxHashChecks, recovered = 0;
        foreach (var target in targets) if (RecipeParentIdentityProof.ResolveSet(target, "853355558", candidates, ref budget) is not null) recovered++;
        clock.Stop();
        Equal(2048, recovered, "large world recovers only bounded target roster");
        Equal(0, budget, "large world uses exactly the strict 4096-pair cap");
        Console.WriteLine($"HASH PROOF PERFORMANCE: records=20000, targets={targets.Length}, checks=4096, elapsedMs={clock.Elapsed.TotalMilliseconds:F2}");
    }

    private static void LineageHashProofRegistryConflictAndForeign()
    {
        int world = Terraria.Main.worldID;
        var samples = ContentSamples.ItemsByType.ToArray();
        try
        {
            Terraria.Main.worldID = 713291;
            var native = new Item { type = ItemID.EbonstoneBlock, stack = 1 }; native.SetNameOverride("same native caption");
            var alternative = new Item { type = ItemID.EbonsandBlock, stack = 1 }; alternative.SetNameOverride("same native caption");
            ContentSamples.ItemsByType[ItemID.EbonstoneBlock] = native; ContentSamples.ItemsByType[ItemID.EbonsandBlock] = alternative;
            using var registry = new GeneratedItemRegistryService();
            var parent = AtlasRecoveryItem("hash-proof-parent", "item:Terraria/Gel:23", "item:Terraria/Spear:280"); parent.Name = "generated parent";
            var child = AtlasRecoveryItem("hash-proof-child"); child.ParentA = parent.Name; child.ParentB = native.Name;
            string[] proven = { "generated:" + parent.Id, "item:Terraria/EbonstoneBlock:61" };
            child.RecipeKey = RecipeParentIdentityProof.Key(proven[0], proven[1], "713291")!;
            child.Gameplay.Damage = 91;
            registry.RegisterLocal(parent, ensureAssets: false); registry.RegisterLocal(child, ensureAssets: false);
            string before = child.CloneForItemInstance().ToLocalCacheJson();
            for (int repeat = 0; repeat < 2; repeat++)
            {
                registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(child.Id, out var recovered);
                Equal(string.Join("|", proven), string.Join("|", recovered.AtlasParentIdentities), "registry automatically displays hash-proven pair after repeated load");
                Equal(0, recovered.RecipeMeta.ParentIdentities.Length, "historical slot identities remain absent");
                Equal(true, recovered.HasRecoveredAtlasParents, "presentation uses the proven parent set without inventing order");
                Equal(child.ParentA, recovered.ParentA, "historical first caption is unchanged");
                Equal(child.ParentB, recovered.ParentB, "historical second caption is unchanged");
                Equal(child.ToNetworkJson(), recovered.ToNetworkJson(), "presentation proof does not leak positional assumptions into multiplayer wire");
                var wire = GeneratedItemData.FromJson(recovered.ToNetworkJson())!;
                Equal(false, wire.HasRecoveredAtlasParents, "wire carries only original authoritative metadata");
                registry.RegisterLocal(wire, persist: false, ensureAssets: false);
                Equal(true, wire.HasRecoveredAtlasParents, "existing registry metadata retains its proof through same-recipe re-registration");
                Equal<int?>(2, RecipeLineageGraph.Build(recovered, registry.Snapshot()).GenerationDepth, "automatic registry lineage computes generation");
                var clone = recovered.CloneForItemInstance(); clone.RecipeMeta.ParentIdentities = Array.Empty<string>();
                Equal(before, clone.ToLocalCacheJson(), "automatic registry repair changes metadata only");
            }
            var conflict = child.CloneForItemInstance(); conflict.RecipeMeta.ParentIdentities = new[] { "generated:conflicting-parent", proven[1] };
            File.WriteAllText(Path.Combine(registry.StoreRoot, "hash-conflicting-definition.json"), conflict.ToLocalCacheJson());
            File.WriteAllText(AtlasLegacySidecarPath(registry), AtlasLegacySidecar((child.Id, child.RecipeKey, proven)).ToJsonString());
            registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(child.Id, out var unresolved);
            Equal("", unresolved.RecipeMeta.ParentIdentities[0], "hash proof never overrides contradictory recorded evidence");
            Equal(proven[1], unresolved.RecipeMeta.ParentIdentities[1], "independently agreeing exact evidence remains");
            Equal(false, registry.GetLineageRecoveryReceipts().Any(value => value.StartsWith("fix:restore_recipe_hash_proven_parent_identity:" + child.Id)), "conflicting record has no hash proof receipt");
            var foreign = AtlasRecoveryItem("hash-proof-foreign"); foreign.Name = "foreign parent"; foreign.RecipeMeta.WorldId = "713292";
            File.WriteAllText(Path.Combine(registry.StoreRoot, "hash-foreign-parent.json"), foreign.ToLocalCacheJson());
            var orphan = AtlasRecoveryItem("hash-proof-orphan"); orphan.ParentA = foreign.Name; orphan.ParentB = native.Name;
            orphan.RecipeKey = RecipeParentIdentityProof.Key("generated:" + foreign.Id, proven[1], "713291")!;
            registry.RegisterLocal(orphan, ensureAssets: false); registry.ReloadLocalCacheForCurrentWorld(); registry.TryGet(orphan.Id, out var noForeign);
            Equal(0, noForeign.RecipeMeta.ParentIdentities.Length, "foreign-world full definition is not a candidate even with matching caption and recipe hash");
        }
        finally { ContentSamples.ItemsByType.Clear(); foreach (var row in samples) ContentSamples.ItemsByType.Add(row.Key, row.Value); Terraria.Main.worldID = world; }
    }

    private static void LineageHashProofMutableCaptionsStayUnordered()
    {
        const string a = "item:Terraria/Gel:23", b = "item:Terraria/Spear:280";
        var data = HashProofItem(); data.ParentA = "old gel caption"; data.ParentB = "old spear caption";
        data.RecipeKey = RecipeParentIdentityProof.Key(a, b, "853355558")!;
        var candidates = new RecipeParentIdentityProof.Candidates(new[] { data });
        candidates.Add(data.ParentA, b); candidates.Add(data.ParentB, a);
        int budget = 64;
        Equal(true, RecipeParentIdentityProof.Resolve(data, "853355558", candidates, ref budget) is null,
            "swapped current captions cannot prove historical ordered slots");
        budget = 64; var pair = RecipeParentIdentityProof.ResolveSet(data, "853355558", candidates, ref budget)!;
        Equal(a + "|" + b, string.Join("|", pair), "same data still certifies the unordered ancestry pair");
        string before = data.ToLocalCacheJson();
        data.RecoveredAtlasParents = new AtlasParentSet(data.Id, data.RecipeMeta.WorldId, data.RecipeKey,
            pair, pair.Select(candidates.Name).ToArray());
        Equal("old spear caption", data.AtlasParentName(0), "canonical Gel icon receives its current caption, not historical slot-A text");
        Equal("old gel caption", data.AtlasParentName(1), "canonical Spear icon receives its current caption, not historical slot-B text");
        Equal(true, data.HasRecoveredAtlasParents, "Atlas uses the proven set");
        Equal(before, data.ToLocalCacheJson(), "presentation view is absent from saved item JSON");
        var samples = ContentSamples.ItemsByType.ToArray();
        try
        {
            var gel = new Item { type = ItemID.Gel, stack = 1 }; gel.SetNameOverride("old spear caption");
            var spear = new Item { type = ItemID.Spear, stack = 1 }; spear.SetNameOverride("old gel caption");
            ContentSamples.ItemsByType[ItemID.Gel] = gel; ContentSamples.ItemsByType[ItemID.Spear] = spear;
            for (int slot = 0; slot < 2; slot++)
                Equal(data.AtlasParentName(slot), RecipeNativeItemResolver.ResolveParent(data, slot)!.Name,
                    "actual native icon/hover item and caption agree after swapped captions");
        }
        finally { ContentSamples.ItemsByType.Clear(); foreach (var row in samples) ContentSamples.ItemsByType.Add(row.Key, row.Value); }
    }

    private static void LineageHashProofGraphRetainsCycleBoundaries()
    {
        int world = Terraria.Main.worldID;
        try
        {
            Terraria.Main.worldID = 713293;
            var root = AtlasRecoveryItem("hash-graph-cycle");
            root.RecoveredAtlasParents = new AtlasParentSet(root.Id, root.RecipeMeta.WorldId, root.RecipeKey,
                new[] { "generated:" + root.Id, "item:Terraria/EbonstoneBlock:61" }, new[] { root.Name, "stone" });
            var graph = RecipeLineageGraph.Build(root, new[] { root });
            Equal(true, graph.Nodes.Any(node => node.Kind == RecipeLineageGraph.NodeKind.Cycle), "presentation-only parent set retains cycle markers");
            Equal<int?>(null, graph.GenerationDepth, "cyclic proven ancestry cannot fabricate generation");
            root.RecoveredAtlasParents = new AtlasParentSet(root.Id, root.RecipeMeta.WorldId, root.RecipeKey,
                new[] { "item:Terraria/EbonstoneBlock:61", "item:Terraria/EbonstoneBlock:61" }, new[] { "stone", "stone" });
            graph = RecipeLineageGraph.Build(root, new[] { root });
            Equal(2, graph.Edges.Single().Multiplicity, "identical unordered parents retain ingredient multiplicity");
            Equal<int?>(1, graph.GenerationDepth, "native-only parent set computes first generation");
            root.RecipeMeta.WorldId = "713294";
            Equal(false, root.HasRecoveredAtlasParents, "world change invalidates transient proof");
            Equal(0, root.AtlasParentIdentities.Length, "expired proof reveals no foreign-world ancestors");
        }
        finally { Terraria.Main.worldID = world; }
    }

    private static void LineageHashProofReceiptsBoundEveryMutation()
    {
        int world = Terraria.Main.worldID;
        var samples = ContentSamples.ItemsByType.ToArray();
        try
        {
            Terraria.Main.worldID = 713291;
            var native = new Item { type = ItemID.EbonstoneBlock, stack = 1 }; native.SetNameOverride("audit native");
            ContentSamples.ItemsByType[ItemID.EbonstoneBlock] = native;
            using var registry = new GeneratedItemRegistryService();
            var children = new List<GeneratedItemData>();
            for (int i = 0; i < 300; i++)
            {
                var parent = AtlasRecoveryItem("audit-parent-" + i, "item:Terraria/Gel:23", "item:Terraria/Spear:280"); parent.Name = "parent " + i;
                var child = AtlasRecoveryItem("audit-child-" + i); child.ParentA = parent.Name; child.ParentB = native.Name;
                child.RecipeKey = RecipeParentIdentityProof.Key("generated:" + parent.Id, "item:Terraria/EbonstoneBlock:61", "713291")!;
                registry.RegisterLocal(parent, persist: false, ensureAssets: false); registry.RegisterLocal(child, persist: false, ensureAssets: false); children.Add(child);
            }
            var parentMetadata = typeof(GeneratedItemRegistryService).GetNestedType("ParentMetadata", BindingFlags.NonPublic)!;
            var dictType = typeof(Dictionary<,>).MakeGenericType(typeof(string), typeof(List<>).MakeGenericType(parentMetadata));
            var sources = Activator.CreateInstance(dictType)!;
            void Recover() => typeof(GeneratedItemRegistryService).GetMethod("RestoreHashProvenParentMetadata", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(registry, new[] { sources });
            Recover();
            Equal(0, children.Sum(c => c.RecipeMeta.ParentIdentities.Length), "300 unordered pairs create no historical slot claims");
            Equal(300, children.Count(c => c.HasRecoveredAtlasParents), "all 300 bounded unordered views are available");
            Equal(300, registry.GetLineageRecoveryReceipts().Length, "every unordered view has one set receipt");
            Recover(); Equal(300, registry.GetLineageRecoveryReceipts().Length, "existing views are not re-recovered or double-receipted");
            var identical = new List<GeneratedItemData>();
            for (int i = 0; i < 300; i++)
            {
                var child = AtlasRecoveryItem("identical-" + i); child.ParentA = child.ParentB = native.Name;
                child.RecipeKey = RecipeParentIdentityProof.Key("item:Terraria/EbonstoneBlock:61", "item:Terraria/EbonstoneBlock:61", "713291")!;
                registry.RegisterLocal(child, persist: false, ensureAssets: false); identical.Add(child);
            }
            Recover();
            int restoredSlots = identical.Sum(c => c.RecipeMeta.ParentIdentities.Count(s => !string.IsNullOrWhiteSpace(s)));
            Equal(212, restoredSlots, "only whole pairs with available audit capacity are mutated");
            Equal(restoredSlots + 300, registry.GetLineageRecoveryReceipts().Length, "no unaudited slot or unordered-view mutation");
            Equal(true, identical.All(c => c.RecipeMeta.ParentIdentities.Length is 0 or 2), "receipt exhaustion cannot leave a partially modified identical pair");
            registry.TryGet("audit-parent-0", out var admitted);
            string knownParents = string.Join("|", admitted.RecipeMeta.ParentIdentities);
            for (int repeat = 0; repeat < 3; repeat++)
            {
                var incoming = admitted.CloneForItemInstance();
                incoming.RecipeMeta.ParentIdentities = repeat == 1
                    ? new[] { admitted.RecipeMeta.ParentIdentities[0], "" } : Array.Empty<string>();
                registry.RegisterLocal(incoming, persist: false, ensureAssets: false);
                registry.TryGet(admitted.Id, out var retained);
                Equal(knownParents, string.Join("|", retained.RecipeMeta.ParentIdentities), "exhausted recovery audit cannot downgrade admitted metadata on repeated hydration");
                Equal(512, registry.GetLineageRecoveryReceipts().Length, "reattaching admitted evidence does not repeat or expand recovery receipts");
            }
            var changedRecipe = admitted.CloneForItemInstance();
            changedRecipe.RecipeKey += "-different"; changedRecipe.RecipeMeta.ParentIdentities = Array.Empty<string>();
            registry.RegisterLocal(changedRecipe, persist: false, ensureAssets: false);
            Equal(0, changedRecipe.RecipeMeta.ParentIdentities.Length, "budget-independent hydration still requires the exact admitted recipe");
        }
        finally { ContentSamples.ItemsByType.Clear(); foreach (var row in samples) ContentSamples.ItemsByType.Add(row.Key, row.Value); Terraria.Main.worldID = world; }
    }

}
