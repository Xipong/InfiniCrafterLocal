#nullable enable
using InfiniCrafterLocal.Common;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Models;

// AGENT MAP: JSON profile boundary for generated item data.
// Full/local-cache/network/player-save profiles intentionally differ: local cache
// can keep debug/future info, while network/player-save payloads strip bulk/prose
// so C# never treats hidden extension data as executable state.
public sealed partial class GeneratedItemData
{

// =============================================================================
// NAV TOC: GeneratedItemData.cs
// =============================================================================
// NAV: GENERATED_ITEM_CONTRACT        top-level serialized generated item schema
// NAV: GENERATED_ITEM_JSON_NORMALIZE  JSON load/save, placeholder, Normalize()
// NAV: GENERATED_ITEM_APPLY_TO_ITEM   ApplyToItem() and Terraria Item materialization
// NAV: GENERATED_ITEM_SUBSPECS        canonical/source/inheritance/gameplay/accessory specs
// NAV: ATTACK_SPEC_CONTRACT           attack/projectile/runtime fields sent to GeneratedProjectile
// NAV: VISUAL_AND_PRESENTATION_CONTRACT visual prompts, presentation genome, sound profile
// =============================================================================

// =============================================================================
// NAV: GENERATED_ITEM_CONTRACT
// =============================================================================
    public int SchemaVersion { get; set; } = 1;


// =============================================================================
// NAV: GENERATED_ITEM_JSON_NORMALIZE
// =============================================================================
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = false,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow
    };

    public string ToJson() => JsonSerializer.Serialize(this, Options);

    public string ToLocalCacheJson()
    {
        // Local registry cache is the canonical authoring/debug history for this world.
        // It is not a multiplayer transport payload and must keep prompts, item knowledge,
        // source representation, raw sprite paths and debug metadata for tooltips/QA dumps
        // after a restart. Use ToNetworkJson()/ToPlayerSaveJson() only for their narrower
        // sync/save contracts.
        return ToJson();
    }



    private const int MaxNetworkStringPayloadBytes = 100000; // Network generated-item packets allow up to 100 KB; only pathological payloads should be rejected.
    private const int MaxPlayerSaveTagStringPayloadBytes = 4 * 1024; // TagIO stores strings through signed Int16 lengths; stay far below the ~32 KB profile-bricking edge.

    public string ToNetworkJson()
    {
        // Multiplayer item sync should not carry prompt/debug/local-path bulk.
        // Never fall back to `this` for the sanitized network clone: if cloning ever fails,
        // mutating `this` here would erase prompts/debug/paths from the canonical runtime item.
        string originalJson = ToJson();
        var clone = FromJson(originalJson);
        if (clone is null)
            return Utf8ByteCount(originalJson) <= MaxNetworkStringPayloadBytes
                ? originalJson
                : JsonSerializer.Serialize(Placeholder(), Options);

        StripBulkForTransport(clone, keepVfxManifest: true);
        // The typed top-level manifest is the one canonical gameplay copy on the wire.
        // Attack.VfxManifestJson remains a legacy/local fallback only; sending both costs
        // 10-13 KiB per generated item and gives peers two authorities for one VFX plan.
        if (clone.VfxManifest is not null && clone.VfxManifest.HasSlots)
            clone.Attack.VfxManifestJson = "";

        string json = JsonSerializer.Serialize(clone, Options);
        if (Utf8ByteCount(json) <= MaxNetworkStringPayloadBytes)
            return json;

        // If a generated definition is still absurdly large after normal network stripping,
        // drop expensive visual/VFX bulk before giving up. Gameplay fields and asset ids remain.
        VfxManifestSpec itemEventManifest = MinimalItemEventManifest(clone.VfxManifest);
        StripBulkForTransport(clone, keepVfxManifest: false);
        clone.VfxManifest = itemEventManifest;
        json = JsonSerializer.Serialize(clone, Options);
        if (Utf8ByteCount(json) <= MaxNetworkStringPayloadBytes)
            return json;

        var minimal = MinimalNetworkClone(clone);
        json = JsonSerializer.Serialize(minimal, Options);
        return Utf8ByteCount(json) <= MaxNetworkStringPayloadBytes
            ? json
            : JsonSerializer.Serialize(Placeholder(), Options);
    }

    private const string PlayerSaveReferenceKind = "generatedItemRef";

    private sealed class PlayerSaveReferencePayload
    {
        [JsonPropertyName("infiniSaveKind")] public string InfiniSaveKind { get; set; } = PlayerSaveReferenceKind;
        [JsonPropertyName("version")] public int Version { get; set; } = 1;
        [JsonPropertyName("id")] public string Id { get; set; } = "";
        [JsonPropertyName("recipeKey")] public string RecipeKey { get; set; } = "";
        [JsonPropertyName("runtimeApiVersion")] public string RuntimeApiVersion { get; set; } = RuntimeApiCurrent;
        [JsonPropertyName("worldScoped")] public bool WorldScoped { get; set; } = true;
        [JsonPropertyName("worldId")] public string WorldId { get; set; } = "";
        [JsonPropertyName("name")] public string Name { get; set; } = "Generated Item";
        [JsonPropertyName("tooltip")] public string Tooltip { get; set; } = "";
        [JsonPropertyName("category")] public string Category { get; set; } = "generic";
        [JsonPropertyName("sourceMode")] public string SourceMode { get; set; } = "generated";
        [JsonPropertyName("parentA")] public string ParentA { get; set; } = "Unknown";
        [JsonPropertyName("parentB")] public string ParentB { get; set; } = "Unknown";
    }

    public string ToPlayerSaveJson()
    {
        // .tplr/TagIO can brick the whole player profile near the signed Int16 string
        // edge. PlayerSave is therefore only a compact pointer + fallback label; the
        // actual runtime definition is restored from the per-client local registry cache
        // after world load, or from server hydration when multiplayer is available.
        // The serialized kind is generatedItemRef, not a runtime definition.
        var payload = new PlayerSaveReferencePayload
        {
            Id = SafeText(Id, 64),
            RecipeKey = SafeText(RecipeKey, 120),
            RuntimeApiVersion = NormalizeRuntimeApiVersion(RuntimeApiVersion),
            WorldScoped = RecipeMeta?.WorldScoped ?? true,
            WorldId = SafeText(RecipeMeta?.WorldId ?? "", 32),
            Name = SafeText(Name, 80),
            Tooltip = SafeText(Tooltip, 180),
            Category = SafeText(Category, 32),
            SourceMode = SafeText(SourceMode, 32),
            ParentA = SafeText(ParentA, 80),
            ParentB = SafeText(ParentB, 80),
        };
        string json = JsonSerializer.Serialize(payload, Options);
        if (Utf8ByteCount(json) <= MaxPlayerSaveTagStringPayloadBytes)
            return json;

        payload.Tooltip = "";
        payload.RecipeKey = "";
        payload.ParentA = "";
        payload.ParentB = "";
        json = JsonSerializer.Serialize(payload, Options);
        return Utf8ByteCount(json) <= MaxPlayerSaveTagStringPayloadBytes
            ? json
            : JsonSerializer.Serialize(new PlayerSaveReferencePayload { Id = SafeText(Id, 64) }, Options);
    }

    public static GeneratedItemData? FromPlayerSaveJson(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
            return null;

        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.ValueKind == JsonValueKind.Object
                && doc.RootElement.TryGetProperty("infiniSaveKind", out var kind)
                && string.Equals(kind.GetString(), PlayerSaveReferenceKind, StringComparison.Ordinal))
            {
                var root = doc.RootElement;
                string ReadString(string key, int maxLen, string fallback = "")
                {
                    try
                    {
                        if (!root.TryGetProperty(key, out var value) || value.ValueKind != JsonValueKind.String)
                            return fallback;
                        string text = SafeText(value.GetString(), maxLen);
                        return string.IsNullOrWhiteSpace(text) ? fallback : text;
                    }
                    catch { return fallback; }
                }

                bool ReadBool(string key, bool fallback)
                {
                    try
                    {
                        if (!root.TryGetProperty(key, out var value))
                            return fallback;
                        return value.ValueKind == JsonValueKind.True || (value.ValueKind != JsonValueKind.False && fallback);
                    }
                    catch { return fallback; }
                }

                var data = Placeholder();
                data.Id = ReadString("id", 64, data.Id);
                data.RecipeKey = ReadString("recipeKey", 120);
                data.RuntimeApiVersion = NormalizeRuntimeApiVersion(ReadString("runtimeApiVersion", 32, ""));
                data.Name = ReadString("name", 80, data.Name);
                data.Tooltip = ReadString("tooltip", 180, data.Tooltip);
                data.Category = ReadString("category", 32, data.Category);
                data.SourceMode = "player_save_ref";
                data.ParentA = ReadString("parentA", 80, data.ParentA);
                data.ParentB = ReadString("parentB", 80, data.ParentB);
                data.RecipeMeta = new RecipeMetaSpec
                {
                    WorldScoped = ReadBool("worldScoped", true),
                    WorldId = ReadString("worldId", 32),
                };
                data.Debug = new Dictionary<string, JsonElement>();
                data.ExtensionData = new Dictionary<string, JsonElement>();
                data.Normalize();
                return data;
            }
        }
        catch
        {
            // Fall through to legacy full-json player saves below.
        }

        return FromJson(json);
    }

    public static bool IsPlayerSaveReferenceOnly(GeneratedItemData? data)
        => data is not null && string.Equals(data.SourceMode, "player_save_ref", StringComparison.OrdinalIgnoreCase);

    private static int Utf8ByteCount(string value) => Encoding.UTF8.GetByteCount(value ?? "");

    private static void StripBulkForTransport(GeneratedItemData clone, bool keepVfxManifest)
    {
        // Multiplayer/Radmin handoff is ready-runtime state only.  Do not ship LLM
        // prompts, raw source readings, debug blobs, model metadata, or local authoring
        // traces to peers.  Peers only need the finished generated item contract plus
        // final asset filenames/base URL for HTTP cache hydration.
        clone.Debug = new Dictionary<string, JsonElement>();
        clone.ExtensionData.Clear();
        clone.Tags = SafeTextArray(clone.Tags, 12, 32);
        clone.SourceRepresentation = Array.Empty<SourceRepresentationSpec>();
        clone.Inheritance = Array.Empty<InheritanceSpec>();
        clone.ItemKnowledge = new ItemKnowledgeSpec();
        clone.PresentationGenome = new PresentationGenomeSpec();
        if (clone.RecipeMeta is not null)
        {
            clone.RecipeMeta.ParentIdentities = Array.Empty<string>();
            clone.RecipeMeta.ParentCategories = Array.Empty<string>();
            clone.RecipeMeta.WorldId = SafeText(clone.RecipeMeta.WorldId, 32);
            clone.RecipeMeta.AssetTransport = string.Equals(clone.RecipeMeta.AssetTransport, "http", StringComparison.OrdinalIgnoreCase) ? "http" : "native";
            clone.RecipeMeta.AssetBaseUrl = SafeText(clone.RecipeMeta.AssetBaseUrl, 200);
            clone.RecipeMeta.AssetFiles = SafeTextArray(clone.RecipeMeta.AssetFiles, 16, 160)
                .Where(file => file.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                .ToArray();
        }
        clone.Visual.ImagePrompt = "";
        clone.Visual.ProjectileImagePrompt = "";
        clone.Visual.ImpactImagePrompt = "";
        clone.Visual.ChildImagePrompt = "";
        clone.Visual.FieldImagePrompt = "";
        clone.Visual.EquipOverlayPrompt = "";
        clone.Visual.NegativePrompt = "";
        clone.Visual.AssetManifestPath = "";
        clone.Visual.SpriteRawPath = "";
        clone.Attack.ProjectileSpritePrompt = "";
        clone.Attack.ImpactSpritePrompt = "";
        clone.Attack.ChildSpritePrompt = "";
        clone.Attack.FieldSpritePrompt = "";
        if (!keepVfxManifest)
        {
            clone.VfxManifest = new VfxManifestSpec();
            clone.Attack.VfxManifestJson = "";
            clone.Attack.VisualAnimationPlan = "";
        }
    }

    private static void StripKnowledgeForPlayerSave(GeneratedItemData clone)
    {
        clone.Tags = SafeTextArray(clone.Tags, 12, 32);
        clone.SourceRepresentation = Array.Empty<SourceRepresentationSpec>();
        clone.Inheritance = Array.Empty<InheritanceSpec>();
        clone.ItemKnowledge = new ItemKnowledgeSpec();
        clone.PresentationGenome = new PresentationGenomeSpec();
        clone.RecipeMeta.ParentIdentities = Array.Empty<string>();
        clone.RecipeMeta.ParentCategories = Array.Empty<string>();
        clone.RecipeMeta.AssetFiles = Array.Empty<string>();
        clone.RecipeMeta.WorldScoped = clone.RecipeMeta.WorldScoped;
        clone.RecipeMeta.WorldId = SafeText(clone.RecipeMeta.WorldId, 32);
        clone.RecipeMeta.AssetBaseUrl = "";
    }

    private static GeneratedItemData MinimalPlayerSaveClone(GeneratedItemData source)
    {
        return new GeneratedItemData
        {
            SchemaVersion = source.SchemaVersion,
            RuntimeApiVersion = RuntimeApiCurrent,
            Id = source.Id,
            RecipeKey = source.RecipeKey,
            Name = source.Name,
            ParentA = source.ParentA,
            ParentB = source.ParentB,
            Tooltip = source.Tooltip,
            MergeMode = source.MergeMode,
            Category = source.Category,
            SourceMode = source.SourceMode,
            Tags = SafeTextArray(source.Tags, 8, 32),
            Canonical = source.Canonical ?? new CanonicalSpec(),
            LossBudget = source.LossBudget ?? new LossBudgetSpec(),
            RecipeMeta = new RecipeMetaSpec
            {
                UniversalRecipe = source.RecipeMeta?.UniversalRecipe ?? true,
                GenerationDepth = source.RecipeMeta?.GenerationDepth ?? 1,
                RecipeCoherence = source.RecipeMeta?.RecipeCoherence ?? "",
                ChaosBudget = source.RecipeMeta?.ChaosBudget ?? 0f,
                NoveltyBudget = source.RecipeMeta?.NoveltyBudget ?? 0f,
                SampledLane = source.RecipeMeta?.SampledLane ?? "",
                SampledCategory = source.RecipeMeta?.SampledCategory ?? "",
                WorldScoped = source.RecipeMeta?.WorldScoped ?? true,
                WorldId = SafeText(source.RecipeMeta?.WorldId ?? "", 32)
            },
            Gameplay = source.Gameplay ?? new GameplaySpec(),
            Accessory = source.Accessory ?? new AccessorySpec(),
            Armor = source.Armor ?? new ArmorSpec(),
            Attack = source.Attack ?? new AttackSpec(),
            Visual = source.Visual ?? new VisualSpec(),
            Debug = new Dictionary<string, JsonElement>(),
            ExtensionData = new Dictionary<string, JsonElement>()
        };
    }

    private static GeneratedItemData MinimalNetworkClone(GeneratedItemData source)
    {
        GeneratedItemData clone = MinimalPlayerSaveClone(source);
        clone.RecipeMeta.AssetTransport = string.Equals(source.RecipeMeta?.AssetTransport, "http", StringComparison.OrdinalIgnoreCase) ? "http" : "native";
        clone.RecipeMeta.AssetBaseUrl = SafeText(source.RecipeMeta?.AssetBaseUrl ?? "", 200);
        clone.RecipeMeta.AssetFiles = SafeTextArray(source.RecipeMeta?.AssetFiles, 16, 160)
            .Where(file => file.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        clone.VfxManifest = MinimalItemEventManifest(source.VfxManifest);
        return clone;
    }

    private static VfxManifestSpec MinimalItemEventManifest(VfxManifestSpec? source)
    {
        if (source is null || !source.HasSlots)
            return VfxManifestSpec.Empty();

        VfxManifestSpec clone = VfxManifestSpec.FromJson(source.ToJson());
        clone.EffectName = "";
        clone.InspirationNames = Array.Empty<string>();
        clone.Motif = new VfxMotifSpec();
        clone.Debug = new VfxDebugSpec();
        clone.Slots = (clone.Slots ?? Array.Empty<VfxSlotSpec>())
            .Where(IsExecutableItemVfxSlot)
            .OrderBy(slot => slot.Event is "on_use" or "on_alt_use" ? 0 : 1)
            .Take(8)
            .ToArray();
        foreach (VfxSlotSpec slot in clone.Slots)
        {
            slot.EffectName = "";
            slot.BakedClipId = "";
            slot.BakedClipHash = "";
            slot.BakedCommandCount = 0;
            slot.BakedCommands = Array.Empty<VfxBakedCommandSpec>();
        }
        return clone;
    }

    private static bool IsExecutableItemVfxSlot(VfxSlotSpec? slot)
    {
        if (slot is null)
            return false;
        return slot.Event switch
        {
            "while_held" or "while_equipped" => slot.RendererKind is "orbitingMotes" or "childMotes" or "lightCue",
            "on_use" or "on_alt_use" => slot.RendererKind is "impactRing" or "childMotes" or "lightCue" or "soundCue",
            _ => false,
        };
    }

    public static GeneratedItemData? FromJson(string? json)
    {
        const string boundary = "GeneratedItemData.FromJson";
        ContractJsonDiagnostics.Clear(boundary);
        if (string.IsNullOrWhiteSpace(json))
            return null;

        try
        {
            var parsed = JsonSerializer.Deserialize<GeneratedItemData>(json, Options);
            if (parsed is null) return null;
            parsed.Normalize();
            if (!RuntimeApiSupported(parsed.RuntimeApiVersion))
            {
                parsed.SourceMode = "failed";
                parsed.Tooltip = $"Unsupported generated runtime API {parsed.RuntimeApiVersion}; update the mod/generator pair.";
                return parsed;
            }
            if (!RuntimeAttackContractSupported(parsed.Attack, parsed.RuntimeApiVersion))
                return MarkUnsupportedRuntimeAttack(parsed);
            return parsed;
        }
        catch
        {
            // Transport safety: older Python/cache payloads may contain nested debug
            // objects. Debug is not gameplay state and must never block item delivery.
            try
            {
                string safeJson = NormalizeTopLevelDebugForJson(json);
                var parsed = JsonSerializer.Deserialize<GeneratedItemData>(safeJson, Options);
                if (parsed is null) return null;
                parsed.Normalize();
                if (!RuntimeApiSupported(parsed.RuntimeApiVersion))
                {
                    parsed.SourceMode = "failed";
                    parsed.Tooltip = $"Unsupported generated runtime API {parsed.RuntimeApiVersion}; update the mod/generator pair.";
                    return parsed;
                }
                if (!RuntimeAttackContractSupported(parsed.Attack))
                    return MarkUnsupportedRuntimeAttack(parsed);
                return parsed;
            }
            catch (Exception finalException)
            {
                ContractJsonDiagnostics.Record(boundary, finalException);
                return null;
            }
        }
    }

    private static string NormalizeTopLevelDebugForJson(string json)
    {
        using var doc = JsonDocument.Parse(json);
        if (doc.RootElement.ValueKind != JsonValueKind.Object)
            return json;

        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            foreach (var prop in doc.RootElement.EnumerateObject())
            {
                if (!prop.NameEquals("debug"))
                {
                    prop.WriteTo(writer);
                    continue;
                }

                writer.WritePropertyName("debug");
                writer.WriteStartObject();
                if (prop.Value.ValueKind == JsonValueKind.Object)
                {
                    foreach (var debugProp in prop.Value.EnumerateObject())
                    {
                        writer.WriteString(debugProp.Name, debugProp.Value.ValueKind switch
                        {
                            JsonValueKind.String => debugProp.Value.GetString() ?? "",
                            JsonValueKind.Number or JsonValueKind.True or JsonValueKind.False or JsonValueKind.Object or JsonValueKind.Array => debugProp.Value.GetRawText(),
                            JsonValueKind.Null or JsonValueKind.Undefined => "",
                            _ => debugProp.Value.GetRawText()
                        });
                    }
                }
                writer.WriteEndObject();
            }
            writer.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    public static GeneratedItemData Placeholder() => new()
    {
        Id = "placeholder",
        Name = "Unstable Generated Item",
        ParentA = "Unknown",
        ParentB = "Unknown",
        Tooltip = "The recipe data was missing or corrupted.",
        Category = "generic",
        SourceMode = "fallback",
        Tags = new[] { "generated", "unstable" },
        Canonical = new CanonicalSpec { HeadNoun = "item", Class = "generic" },
        Gameplay = new GameplaySpec { Kind = "generic", Rarity = ItemRarityID.White, Value = 100 },
        Accessory = new AccessorySpec { Enabled = false },
        Visual = new VisualSpec
        {
            ImagePrompt = "small pixel art item icon, unknown object, solid magenta key background",
            SpriteStatus = "placeholder",
            PreferredCanvasSize = 32,
            InventoryScale = 1f,
            WorldScale = 1f
        }
    };


}


