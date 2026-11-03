#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratedItemRegistryService
{
    // A detached snapshot is essential: inventory/world containers can hold and
    // mutate the same definition object that the registry previously admitted.
    private readonly Dictionary<string, ParentMetadata> _parentMetadata = new(StringComparer.Ordinal);
    private readonly List<string> _lineageRecoveryReceipts = new();

    public string[] GetLineageRecoveryReceipts()
    {
        lock (_lock) return _lineageRecoveryReceipts.ToArray();
    }

    private IEnumerable<(string Path, bool Bundled)> LocalDefinitionFiles()
    {
        // BundledStudio starts the generator with this exact durable --data-dir.
        // world_storage.world_recipe_dir uses safe_file_part; world IDs here are
        // decimal engine IDs, so only its leading/trailing '-' trimming applies.
        string world = CurrentWorldIdString();
        string bundledRecipes = Path.Combine(Path.GetDirectoryName(StoreRoot)!, "Studio", "data", "cache",
            "world_recipes", "world_" + world.Trim('-'), "recipes");
        foreach (string directory in new[] { WorldStoreRoot(world), StoreRoot, bundledRecipes })
        {
            string[] files;
            try { files = Directory.Exists(directory) ? Directory.GetFiles(directory, "*.json") : Array.Empty<string>(); }
            catch (IOException) { continue; }
            catch (UnauthorizedAccessException) { continue; }
            // Stable order makes equal-priority records reproducible. Metadata
            // conflicts still remain unresolved rather than using filename order.
            Array.Sort(files, StringComparer.Ordinal);
            foreach (string file in files) yield return (file, directory == bundledRecipes);
        }
    }

    private IReadOnlyList<ParentMetadata> LegacyLineageMetadata()
    {
        // Historical /recipe_lineage responses were persisted separately from
        // full item definitions. They contain exact ordered parent identities,
        // not enough information to create an item or recover authored prose.
        string world = CurrentWorldIdString();
        string path = Path.Combine(Path.GetDirectoryName(StoreRoot)!, "atlas_lineage",
            "world_" + StorageIdentity(world) + ".json");
        var sources = new List<ParentMetadata>();
        try
        {
            if (!File.Exists(path)) return sources;
            using var document = JsonDocument.Parse(File.ReadAllText(path));
            JsonElement root = document.RootElement;
            if (!UniqueObject(root) || !root.TryGetProperty("worldId", out var savedWorld)
                || savedWorld.ValueKind != JsonValueKind.String || savedWorld.GetString() != world
                || !root.TryGetProperty("items", out var items) || !UniqueObject(items)) return sources;
            foreach (JsonProperty item in items.EnumerateObject())
            {
                JsonElement row = item.Value;
                if (string.IsNullOrWhiteSpace(item.Name) || !UniqueObject(row)
                    || !row.TryGetProperty("recipeKey", out var recipe) || recipe.ValueKind != JsonValueKind.String
                    || string.IsNullOrWhiteSpace(recipe.GetString())
                    || !row.TryGetProperty("parentIdentities", out var parents) || parents.ValueKind != JsonValueKind.Array
                    || parents.GetArrayLength() != 2
                    || parents.EnumerateArray().Any(parent => parent.ValueKind != JsonValueKind.String
                        || string.IsNullOrWhiteSpace(parent.GetString()))) continue;
                sources.Add(new ParentMetadata(item.Name, world, recipe.GetString()!, "", "",
                    parents.EnumerateArray().Select(parent => parent.GetString()!).ToArray(), HasCaptions: false));
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        catch (JsonException) { }
        return sources;
    }

    private static bool UniqueObject(JsonElement value) => value.ValueKind == JsonValueKind.Object
        && value.EnumerateObject().Select(property => property.Name).Distinct(StringComparer.Ordinal).Count()
            == value.EnumerateObject().Count();

    private static ParentMetadata? HistoricalKnowledgeMetadata(string json, GeneratedItemData data)
    {
        // This retired advisory owner is not executed or reintroduced into the
        // DTO. Read only explicit self-bound identities, guarded by slot captions.
        if (string.IsNullOrWhiteSpace(data.RecipeKey)) return null;
        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("itemKnowledge", out var knowledge) || !UniqueObject(knowledge)
            || !knowledge.TryGetProperty("enabled", out var enabled) || enabled.ValueKind != JsonValueKind.True
            || !knowledge.TryGetProperty("resultCard", out var result) || !UniqueObject(result)
            || !result.TryGetProperty("identity", out var resultId) || resultId.ValueKind != JsonValueKind.String
            || resultId.GetString() != "generated:" + data.Id
            || !knowledge.TryGetProperty("parents", out var parents) || parents.ValueKind != JsonValueKind.Array
            || parents.GetArrayLength() != 2) return null;
        string[] identities = new string[2], captions = { data.ParentA, data.ParentB };
        for (int slot = 0; slot < 2; slot++)
        {
            JsonElement parent = parents[slot];
            if (!UniqueObject(parent) || string.IsNullOrWhiteSpace(captions[slot])
                || !parent.TryGetProperty("name", out var name) || name.ValueKind != JsonValueKind.String
                || name.GetString() != captions[slot]
                || !parent.TryGetProperty("identity", out var identity) || identity.ValueKind != JsonValueKind.String
                || string.IsNullOrWhiteSpace(identity.GetString())) return null;
            identities[slot] = identity.GetString()!;
        }
        return new ParentMetadata(data.Id, data.RecipeMeta.WorldId, data.RecipeKey, data.ParentA, data.ParentB, identities);
    }

    private sealed record ParentMetadata(string Id, string World, string RecipeKey,
        string ParentA, string ParentB, string[] Identities, bool HasCaptions = true)
    {
        internal static ParentMetadata Capture(GeneratedItemData data) => new(data.Id,
            data.RecipeMeta.WorldId, data.RecipeKey, data.ParentA, data.ParentB,
            data.RecipeMeta.ParentIdentities?.ToArray() ?? Array.Empty<string>());

        internal bool Matches(GeneratedItemData data) => data.RecipeMeta.WorldScoped
            && Id == data.Id && World == data.RecipeMeta.WorldId && RecipeKey == data.RecipeKey
            // Captions only guard slot order on the same exact recipe/result;
            // they never resolve a parent or join different result identities.
            && (!HasCaptions || ParentA == data.ParentA && ParentB == data.ParentB);
    }

    private void RestoreMissingParentMetadata(GeneratedItemData data, IEnumerable<ParentMetadata> sources)
    {
        string[] current = data.RecipeMeta.ParentIdentities ?? Array.Empty<string>();
        if (current.Length > 2) return; // Do not reinterpret malformed positional metadata.
        string[] restored = new[] { current.ElementAtOrDefault(0) ?? "", current.ElementAtOrDefault(1) ?? "" };
        var candidates = sources.Where(source => source.Matches(data) && source.Identities.Length <= 2
            && Enumerable.Range(0, 2).All(slot => string.IsNullOrWhiteSpace(restored[slot])
                || string.IsNullOrWhiteSpace(source.Identities.ElementAtOrDefault(slot))
                || restored[slot] == source.Identities[slot])).ToArray();
        bool changed = false;
        for (int slot = 0; slot < 2; slot++)
        {
            if (!string.IsNullOrWhiteSpace(restored[slot])) continue;
            string[] exact = candidates.Select(source => source.Identities.ElementAtOrDefault(slot) ?? "")
                .Where(identity => !string.IsNullOrWhiteSpace(identity)).Distinct(StringComparer.Ordinal).Take(2).ToArray();
            if (exact.Length != 1) continue; // Missing or contradictory evidence stays unknown.
            restored[slot] = exact[0]; changed = true;
            if (_lineageRecoveryReceipts.Count < 512)
                _lineageRecoveryReceipts.Add($"fix:restore_exact_recipe_parent_identity:{data.Id}:{slot}");
        }
        if (changed) data.RecipeMeta.ParentIdentities = restored;
    }
}
