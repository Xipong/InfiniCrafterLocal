using InfiniCrafterLocal.Common.Services;
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

/// <summary>
/// One strict definition reader for current generated items, including local
/// storage and network delivery. Full JSON preserves authoring diagnostics;
/// network JSON carries typed runtime/final assets, and player saves carry a
/// compact world-scoped reference. Unsupported input is never rewritten.
/// </summary>
public sealed partial class GeneratedItemData
{
    public const int CurrentSchemaVersion = 5;
    public int SchemaVersion { get; set; } = CurrentSchemaVersion;

    // Full definitions already travel via the registry's bounded chunk protocol,
    // not a single ModPacket string. Share that existing 256 KiB ceiling.
    internal const int MaxDefinitionJsonBytes = 256 * 1024;
    private const int MaxPlayerSaveTagStringPayloadBytes = 4 * 1024;
    private const string PlayerSaveReferenceKind = "generatedItemRefV5";

    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = false,
        PropertyNameCaseInsensitive = false,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    };

    public string ToJson()
    {
        return JsonSerializer.Serialize(CloneNormalized(), Options);
    }

    public string ToNetworkJson()
    {
        GeneratedItemData clone = CloneNormalized();
        StripAuthoringBulkForTransport(clone);
        string json = JsonSerializer.Serialize(clone, Options);
        if (Utf8ByteCount(json) > MaxDefinitionJsonBytes)
            throw new InvalidDataException($"Generated item '{Id}' network payload exceeds {MaxDefinitionJsonBytes} bytes");
        return json;
    }

    // Same stripped definition as network projection, but cloning is local:
    // it must not lose identity merely because a network byte budget refuses it.
    internal GeneratedItemData CloneForItemInstance()
    {
        GeneratedItemData clone = CloneNormalized();
        StripAuthoringBulkForTransport(clone);
        return clone;
    }

    public string ToPlayerSaveJson()
    {
        var payload = new PlayerSaveReferencePayload
        {
            Id = SafeText(Id, 64),
            RecipeKey = SafeText(RecipeKey, 120),
            RuntimeApiVersion = RuntimeProgramSpec.CurrentApiVersion,
            WorldScoped = RecipeMeta?.WorldScoped ?? true,
            WorldId = SafeText(RecipeMeta?.WorldId ?? "", 32),
            Name = SafeName(Name),
            Category = SafeText(Category, 32),
            ParentA = SafeName(ParentA),
            ParentB = SafeName(ParentB),
        };
        string json = JsonSerializer.Serialize(payload, Options);
        if (Utf8ByteCount(json) <= MaxPlayerSaveTagStringPayloadBytes)
            return json;
        payload.RecipeKey = "";
        payload.ParentA = "";
        payload.ParentB = "";
        json = JsonSerializer.Serialize(payload, Options);
        if (Utf8ByteCount(json) > MaxPlayerSaveTagStringPayloadBytes)
            throw new InvalidDataException("Generated item save reference exceeds TagIO safety limit");
        return json;
    }

    public static GeneratedItemData? FromPlayerSaveJson(string? json)
    {
        const string boundary = "GeneratedItemData.FromPlayerSaveJson";
        ContractJsonDiagnostics.Clear(boundary);
        if (string.IsNullOrWhiteSpace(json))
            return null;
        try
        {
            PlayerSaveReferencePayload? payload = ReadStrictJson<PlayerSaveReferencePayload>(json);
            if (payload is null || !string.Equals(payload.InfiniSaveKind, PlayerSaveReferenceKind, StringComparison.Ordinal))
                throw new InvalidDataException("Only v5 generatedItemRef saves are accepted; full/legacy item JSON is not migrated");
            if (payload.Version != CurrentSchemaVersion)
                throw new InvalidDataException($"Unsupported saved reference version '{payload.Version}'");
            if (!string.Equals(payload.RuntimeApiVersion, RuntimeProgramSpec.CurrentApiVersion, StringComparison.Ordinal))
                throw new InvalidDataException($"Unsupported saved runtime API '{payload.RuntimeApiVersion}'");
            return ReferenceOnly(payload);
        }
        catch (Exception ex)
        {
            ContractJsonDiagnostics.Record(boundary, ex);
            return null;
        }
    }

    public static bool IsPlayerSaveReferenceOnly(GeneratedItemData? data)
        => data is not null && string.Equals(data.SourceMode, "player_save_ref", StringComparison.Ordinal);

    public static GeneratedItemData? FromJson(string? json)
    {
        const string boundary = "GeneratedItemData.FromJson";
        ContractJsonDiagnostics.Clear(boundary);
        if (string.IsNullOrWhiteSpace(json))
            return null;
        try
        {
            GeneratedItemData? parsed = ReadStrictJson<GeneratedItemData>(json);
            if (parsed is null)
                return null;
            parsed.Normalize();
            return parsed;
        }
        catch (Exception ex)
        {
            ContractJsonDiagnostics.Record(boundary, ex);
            return null;
        }
    }

    private static T? ReadStrictJson<T>(string json)
    {
        using var document = JsonDocument.Parse(json);
        RequireUniqueJsonMembers(document.RootElement, "$");
        return document.RootElement.Deserialize<T>(Options);
    }

    private static void RequireUniqueJsonMembers(JsonElement value, string path)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty member in value.EnumerateObject())
            {
                string child = path + "." + member.Name;
                if (!names.Add(member.Name))
                    throw new JsonException("Duplicate JSON member", child, null, null);
                RequireUniqueJsonMembers(member.Value, child);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            int index = 0;
            foreach (JsonElement child in value.EnumerateArray())
                RequireUniqueJsonMembers(child, path + "[" + index++ + "]");
        }
    }

    public static GeneratedItemData Placeholder()
        => InertUnavailable("placeholder", "corrupt_reference");

    private static GeneratedItemData ReferenceOnly(PlayerSaveReferencePayload payload)
    {
        GeneratedItemData data = InertUnavailable(
            string.IsNullOrWhiteSpace(payload.Id) ? "missing_reference" : SafeText(payload.Id, 64),
            "player_save_ref");
        data.RecipeKey = SafeText(payload.RecipeKey, 120);
        data.Name = string.IsNullOrWhiteSpace(payload.Name) ? "Generated Item" : SafeName(payload.Name);
        data.ParentA = SafeName(payload.ParentA);
        data.ParentB = SafeName(payload.ParentB);
        data.Category = SafeText(payload.Category, 32).ToLowerInvariant();
        data.RecipeMeta.WorldScoped = payload.WorldScoped;
        data.RecipeMeta.WorldId = SafeText(payload.WorldId, 32);
        data.Normalize();
        return data;
    }

    private static GeneratedItemData InertUnavailable(string id, string sourceMode)
    {
        const string itemEntityId = "unavailable_item";
        return new GeneratedItemData
        {
            SchemaVersion = CurrentSchemaVersion,
            RuntimeApiVersion = RuntimeProgramSpec.CurrentApiVersion,
            Id = id,
            Name = "Unavailable Generated Item",
            ParentA = "Unknown",
            ParentB = "Unknown",
            Category = "generic",
            SourceMode = sourceMode,
            Tags = new[] { "generated", "unavailable" },
            Gameplay = new GameplaySpec
            {
                Kind = "generic", DamageClass = "generic", Damage = 0,
                UseTime = 24, UseAnimation = 24, UseStyleName = "shoot",
                Rarity = ItemRarityID.White, Value = 0, MaxStack = 1,
                Width = 24, Height = 24,
            },
            RuntimeProgram = new RuntimeProgramSpec
            {
                ItemEntityId = itemEntityId,
                PrimaryEntityId = itemEntityId,
                PrimaryOwner = RuntimeProgramSpec.ItemBodyOwner,
                Entities = new[]
                {
                    new RuntimeEntitySpec
                    {
                        Id = itemEntityId,
                        Kind = RuntimeEntityKind.ItemBody,
                        VisualRole = "inventory_item",
                        Visual = new RuntimeEntityVisualSpec { Role = "inventory_item", AssetMode = "no_asset" },
                    },
                },
                Bindings = Array.Empty<RuntimeBindingSpec>(),
                ItemUse = new RuntimeItemUseSpec { UseStyle = "shoot", DisableMeleeHitbox = true },
            },
            Accessory = new AccessorySpec { Enabled = false },
            Armor = new ArmorSpec { Enabled = false },
            Visual = new VisualSpec
            {
                SpriteStatus = "unavailable",
                PreferredCanvasSize = 32,
                InventoryScale = 1f,
                WorldScale = 1f,
            },
            VfxManifest = VfxManifestSpec.Empty(),
        };
    }

    // Readers, registry admission and ApplyToItem own normalization of live data.
    // Mutable callers also exist: serialize a private graph and validate that graph
    // before projection, never partially normalize the source on success or failure.
    private GeneratedItemData CloneNormalized()
    {
        var clone = CloneUnchecked(this);
        clone.Normalize();
        return clone;
    }

    private static GeneratedItemData CloneUnchecked(GeneratedItemData source)
    {
        string json = JsonSerializer.Serialize(source, Options);
        return JsonSerializer.Deserialize<GeneratedItemData>(json, Options)
            ?? throw new InvalidDataException("Failed to clone generated item");
    }

    private static void StripAuthoringBulkForTransport(GeneratedItemData clone)
    {
        clone.Debug = new Dictionary<string, JsonElement>();
        clone.Concept = null;
        clone.Realization = null;
        clone.LlmStageAccounting = null;
        clone.ContractVersions = null;
        clone.RecipeHealth = null;

        clone.Tags = SafeTextArray(clone.Tags, 12, 32);
        clone.Visual.ImagePrompt = "";
        clone.Visual.NegativePrompt = "";
        clone.Visual.EquipOverlayPrompt = "";
        clone.Visual.SpriteRawPath = "";
        clone.Visual.SpritePath = GeneratedAssetSyncService.FileNameFromPath(clone.Visual.SpritePath);
        clone.Visual.EquipOverlayPath = GeneratedAssetSyncService.FileNameFromPath(clone.Visual.EquipOverlayPath);
        foreach (RuntimeEntitySpec entity in clone.RuntimeProgram.Entities)
        {
            entity.Visual.Prompt = "";
            entity.Visual.Silhouette = "";
            entity.Visual.VisualIdentity = "";
            entity.Visual.SpritePath = GeneratedAssetSyncService.FileNameFromPath(entity.Visual.SpritePath);
        }
        foreach (VfxAssetSpec asset in clone.VfxManifest.Assets ?? Array.Empty<VfxAssetSpec>()) {
            asset.Prompt = "";
            asset.NegativePrompt = "";
            asset.SpritePath = GeneratedAssetSyncService.FileNameFromPath(asset.SpritePath);
        }
        if (clone.RecipeMeta is not null)
        {
            // Exact recipe lineage is runtime presentation data, not authoring bulk.
            // Clones, registry sync and embedded placement definitions all need it.
            clone.RecipeMeta.AssetBaseUrl = SafeText(clone.RecipeMeta.AssetBaseUrl, 200);
            clone.RecipeMeta.AssetFiles = (clone.RecipeMeta.AssetFiles ?? Array.Empty<string>())
                .Select(GeneratedAssetSyncService.FileNameFromPath)
                .Where(x => x.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Take(64)
                .ToArray();
        }
    }

    private static int Utf8ByteCount(string value) => Encoding.UTF8.GetByteCount(value ?? "");

    private sealed class PlayerSaveReferencePayload
    {
        [JsonRequired, JsonPropertyName("infiniSaveKind")] public string InfiniSaveKind { get; set; } = PlayerSaveReferenceKind;
        [JsonRequired, JsonPropertyName("version")] public int Version { get; set; } = CurrentSchemaVersion;
        [JsonPropertyName("id")] public string Id { get; set; } = "";
        [JsonPropertyName("recipeKey")] public string RecipeKey { get; set; } = "";
        [JsonRequired, JsonPropertyName("runtimeApiVersion")] public string RuntimeApiVersion { get; set; } = RuntimeProgramSpec.CurrentApiVersion;
        [JsonPropertyName("worldScoped")] public bool WorldScoped { get; set; } = true;
        [JsonPropertyName("worldId")] public string WorldId { get; set; } = "";
        [JsonPropertyName("name")] public string Name { get; set; } = "Generated Item";
        [JsonPropertyName("category")] public string Category { get; set; } = "generic";
        [JsonPropertyName("parentA")] public string ParentA { get; set; } = "";
        [JsonPropertyName("parentB")] public string ParentB { get; set; } = "";
    }
}
