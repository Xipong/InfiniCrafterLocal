#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratedItemRegistryService
{
    private void RestoreHashProvenParentMetadata(IReadOnlyDictionary<string, List<ParentMetadata>> sources)
    {
        string world = CurrentWorldIdString();
        var targets = _byId.Values.Where(data => IsCurrentWorldData(data) && data.RecipeMeta.WorldId == world
                && !data.HasRecoveredAtlasParents && RecipeParentIdentityProof.Missing(data))
            .OrderBy(data => data.Id, StringComparer.Ordinal).Take(RecipeParentIdentityProof.MaxTargets).ToArray();
        if (targets.Length == 0) return;
        var candidates = new RecipeParentIdentityProof.Candidates(targets);
        foreach (var data in _byId.Values)
            if (IsCurrentWorldData(data) && data.RecipeMeta.WorldId == world && !GeneratedItemData.IsPlayerSaveReferenceOnly(data))
                candidates.Add(data.Name, "generated:" + data.Id);
        // Samples exist after native content setup. No runtime dump, file scan,
        // language substitution, persisted numeric-ID fallback, or frame work.
        foreach (var row in ContentSamples.ItemsByType)
        {
            Item item = row.Value;
            if (item.IsAir || item.type != row.Key || item.ModItem is GeneratedItem) continue;
            string fullName;
            if (item.ModItem is { } modItem) fullName = modItem.FullName;
            else
            {
                if (item.type <= 0 || item.type >= ItemID.Count) continue;
                fullName = "Terraria/" + ItemID.Search.GetName(item.type);
            }
            candidates.Add(item.Name, "item:" + fullName + ":" + item.type.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }
        int budget = RecipeParentIdentityProof.MaxHashChecks;
        foreach (var data in targets)
        {
            if (_lineageRecoveryReceipts.Count >= 512) break;
            string[]? proof = RecipeParentIdentityProof.ResolveSet(data, world, candidates, ref budget);
            if (proof is null) continue;
            // A hash proof does not silently override contradictory recorded evidence.
            if (sources.TryGetValue(data.Id, out var recorded) && recorded.Any(source => source.Matches(data)
                && (source.Identities.Length > 2 || source.Identities.Any(value => !string.IsNullOrWhiteSpace(value) && !proof.Contains(value, StringComparer.Ordinal))))) continue;
            string[] previous = data.RecipeMeta.ParentIdentities ?? Array.Empty<string>();
            string[]? ordered = RecipeParentIdentityProof.Ordered(data, proof);
            if (ordered is null)
            {
                // A compact Atlas-only view. Original positional metadata and
                // historical captions remain byte-for-byte unchanged on disk/wire.
                data.RecoveredAtlasParents = new AtlasParentSet(data.Id, world, data.RecipeKey,
                    proof, proof.Select(candidates.Name).ToArray());
                _lineageRecoveryReceipts.Add($"fix:restore_recipe_hash_proven_parent_set:{data.Id}");
                continue;
            }
            int missingSlots = Enumerable.Range(0, 2).Count(slot => previous.Length <= slot || string.IsNullOrWhiteSpace(previous[slot]));
            if (_lineageRecoveryReceipts.Count + missingSlots > 512) continue; // Reserve every receipt before changing either slot.
            // Exact saved positional evidence, when present, remains authoritative.
            if (sources.TryGetValue(data.Id, out recorded) && recorded.Any(source => source.Matches(data)
                && source.Identities.Where((value, slot) => !string.IsNullOrWhiteSpace(value) && value != ordered[slot]).Any())) continue;
            data.RecipeMeta.ParentIdentities = ordered;
            for (int slot = 0; slot < 2; slot++)
                if (previous.Length <= slot || string.IsNullOrWhiteSpace(previous[slot]))
                    _lineageRecoveryReceipts.Add($"fix:restore_recipe_hash_proven_parent_identity:{data.Id}:{slot}");
        }
    }
}
