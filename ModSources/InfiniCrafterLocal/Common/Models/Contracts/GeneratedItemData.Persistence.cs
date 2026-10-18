#nullable enable
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;

public sealed partial class GeneratedItemData
{
    // Persisted v5 is a durable read boundary, not the fresh Author/network grammar.
    // Keep historical positives when changing DTO metadata in a minor release.
    // Only enumerated inert fields can be omitted; executing fields must either
    // lower losslessly from their declared saved owner or fail with an exact path.
    // This projection never writes a cache/save, infers mechanics or dispatches a
    // historical engine. The result still passes the CURRENT strict DTO/Normalize.
    private const string PersistedVfx15 = "infini.vfx.runtime-events.v15";
    private const string PersistedBoundary = "GeneratedItemData.FromLocalCacheJson";
    private static readonly HashSet<string> PersistedOpaqueOwners = new(StringComparer.OrdinalIgnoreCase) {
        "$.debug", "$.concept", "$.realization", "$.llmStageAccounting", "$.contractVersions", "$.recipeHealth",
        "$.canonical", "$.sourceRepresentation", "$.inheritance", "$.lossBudget", "$.itemKnowledge",
        "$.vfxManifest.motif", "$.vfxManifest.debug"
    };

    [JsonIgnore]
    public string[] LocalCacheReadReceipt { get; private set; } = Array.Empty<string>();

    public static GeneratedItemData? FromLocalCacheJson(string? json)
    {
        ContractJsonDiagnostics.Clear(PersistedBoundary);
        if (string.IsNullOrWhiteSpace(json)) return null;
        try
        {
            // The wire reader is case-insensitive. Reject ambiguous duplicates
            // before editing, including differently cased aliases of removed keys.
            using var document = JsonDocument.Parse(json);
            RejectPersistedDuplicates(document.RootElement, "$");
            var root = JsonNode.Parse(json, new JsonNodeOptions { PropertyNameCaseInsensitive = true }) as JsonObject
                ?? throw PersistedFailure("$", "persisted definition must be an object");
            if (root["schemaVersion"]?.GetValue<int>() != CurrentSchemaVersion)
                throw PersistedFailure("$.schemaVersion", "only persisted generated item v5 is supported");
            if (PersistedString(root, "runtimeApiVersion", "$") != RuntimeProgramSpec.CurrentApiVersion)
                throw PersistedFailure("$.runtimeApiVersion", "unsupported persisted runtime API");
            var receipt = new List<string>();
            DropPersisted(root, "$", receipt, "canonical", "sourceRepresentation", "inheritance", "lossBudget", "itemKnowledge");
            DropPersistedOwner(root, "generatedParentSummary", receipt, "notableEffects", "runtimePrimaryEntityId", "runtimeEntityIds");
            DropPersistedOwner(root, "gameplay", receipt, "stage", "powerBudget");
            DropPersistedOwner(root, "accessory", receipt, "archetype");
            DropPersistedOwner(root, "armor", receipt, "archetype");
            DropPersistedOwner(root, "visual", receipt, "objectType", "style", "requiredAnchors", "preservationScore", "semanticReviewStatus",
                "visualSoulSignature", "visualSoulArchetype", "dominantColorHex", "accentColorHex", "visualSoulGlow", "visualSoulPulse", "visualSoulCoverage", "visualSoulEdgeDensity", "effectColor");
            if (root["vfxManifest"] is JsonObject manifest)
                DropRetiredPersistedVfxMetadata(manifest, receipt);
            GeneratedItemData? parsed = JsonSerializer.Deserialize<GeneratedItemData>(receipt.Count == 0 ? json : root.ToJsonString(), Options);
            if (parsed is null) return null;
            parsed.Normalize();
            parsed.LocalCacheReadReceipt = receipt.ToArray();
            return parsed;
        }
        catch (Exception exception)
        {
            ContractJsonDiagnostics.Record(PersistedBoundary, exception);
            return null;
        }
    }

    private static JsonException PersistedFailure(string path, string reason)
        => new($"Persisted definition {path}: {reason}", path, null, null);

    private static void RejectPersistedDuplicates(JsonElement node, string path)
    {
        // Diagnostic blobs and explicitly inert removed owners are opaque JSON,
        // not case-insensitive DTOs. Preserve their legitimate dictionary keys.
        if (PersistedOpaqueOwners.Contains(path)) return;
        if (node.ValueKind == JsonValueKind.Object) {
            var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (JsonProperty property in node.EnumerateObject()) {
                if (!keys.Add(property.Name)) throw PersistedFailure(path + "." + property.Name, "duplicate JSON member");
                RejectPersistedDuplicates(property.Value, path + "." + property.Name);
            }
        } else if (node.ValueKind == JsonValueKind.Array) {
            int index = 0;
            foreach (JsonElement element in node.EnumerateArray()) RejectPersistedDuplicates(element, path + "[" + index++ + "]");
        }
    }

    private static void DropPersistedOwner(JsonObject root, string owner, List<string> receipt, params string[] fields)
    {
        if (root[owner] is JsonObject row) DropPersisted(row, "$." + owner, receipt, fields);
    }

    private static void DropPersisted(JsonObject row, string path, List<string> receipt, params string[] fields)
    {
        foreach (string field in fields)
            if (row.Remove(field)) receipt.Add("persisted:v5:inert " + path + "." + field);
    }

    private static string PersistedString(JsonObject row, string field, string path)
    {
        if (row[field] is JsonValue value && value.TryGetValue<string>(out string? text) && text is not null) return text;
        throw PersistedFailure(path + "." + field, "expected explicit string");
    }

    private static void DropRetiredPersistedVfxMetadata(JsonObject manifest, List<string> receipt)
    {
        // Saved definitions already own their executable VFX. Discard only
        // advisory envelope fields; never inspect motif, recover named colors,
        // translate old renderers or invent Dust selectors.
        if (manifest["schema"] is not JsonValue token
            || !token.TryGetValue<string>(out string? version)
            || (version != PersistedVfx15 && version != VfxManifestSpec.CurrentSchema))
            return; // The current strict DTO diagnoses unsupported versions.

        if (version == PersistedVfx15)
        {
            // Empty v15 has no executing effects, so only its inert envelope
            // differs. Active v15 slots relied on retired rendering semantics.
            // Refuse the item without modifying any saved file.
            if (manifest["slots"] is not JsonArray slots || slots.Count != 0)
                throw PersistedFailure("$.vfxManifest.slots",
                    "nonempty VFX v15 needs retired execution semantics; cannot run on current renderer without reauthoring");
        }

        // Do not even inspect the contents of retired metadata.
        DropPersisted(manifest, "$.vfxManifest", receipt, "effectName", "inspirationNames",
            "playbackMode", "seed", "confidence", "effectMagnitude", "visualBudgetClass",
            "motif", "overlayPolicy", "debug", "hasSlots");
        if (manifest["budget"] is JsonObject budget)
            DropPersisted(budget, "$.vfxManifest.budget", receipt,
                "effectMagnitude", "visualBudgetClass", "emergencyCap",
                "spawnRateMultiplier", "enableSoftGlow", "enablePointSparks",
                "enablePersistentSmoke");

        if (version == PersistedVfx15)
        {
            manifest["schema"] = VfxManifestSpec.CurrentSchema;
            receipt.Add("persisted:v15:empty-presentation-only $.vfxManifest.schema");
        }
    }
}
