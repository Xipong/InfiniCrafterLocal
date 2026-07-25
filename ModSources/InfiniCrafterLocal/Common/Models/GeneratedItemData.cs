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
/// Serialization profiles for generated-item v5. Full/cache JSON preserves
/// authoring diagnostics; multiplayer transports only the accepted typed runtime
/// and final asset identities; player saves contain a compact world-scoped id.
/// No old schema or runtime contract is imported.
/// </summary>
public sealed partial class GeneratedItemData
{
    public const int CurrentSchemaVersion = 5;
    public int SchemaVersion { get; set; } = CurrentSchemaVersion;

    private const int MaxNetworkStringPayloadBytes = 100_000;
    private const int MaxPlayerSaveTagStringPayloadBytes = 4 * 1024;
    private const string PlayerSaveReferenceKind = "generatedItemRefV5";

    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = false,
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    };

    public string ToJson()
    {
        Normalize();
        return JsonSerializer.Serialize(this, Options);
    }

    public string ToLocalCacheJson() => ToJson();

    public string ToNetworkJson()
    {
        Normalize();
        GeneratedItemData clone = CloneUnchecked(this);
        StripAuthoringBulkForTransport(clone);
        string json = JsonSerializer.Serialize(clone, Options);
        if (Utf8ByteCount(json) > MaxNetworkStringPayloadBytes)
            throw new InvalidDataException($"Generated item '{Id}' network payload exceeds {MaxNetworkStringPayloadBytes} bytes");
        return json;
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
            Name = SafeText(Name, 80),
            Tooltip = SafeText(Tooltip, 180),
            Category = SafeText(Category, 32),
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
            PlayerSaveReferencePayload? payload = JsonSerializer.Deserialize<PlayerSaveReferencePayload>(json, Options);
            if (payload is null || !string.Equals(payload.InfiniSaveKind, PlayerSaveReferenceKind, StringComparison.Ordinal))
                throw new InvalidDataException("Only v5 generatedItemRef saves are accepted; full/legacy item JSON is not migrated");
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
            GeneratedItemData? parsed = JsonSerializer.Deserialize<GeneratedItemData>(json, Options);
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

    public static GeneratedItemData Placeholder()
        => InertUnavailable("placeholder", "Generated item data is unavailable or invalid.", "corrupt_reference");

    private static GeneratedItemData ReferenceOnly(PlayerSaveReferencePayload payload)
    {
        GeneratedItemData data = InertUnavailable(
            string.IsNullOrWhiteSpace(payload.Id) ? "missing_reference" : SafeText(payload.Id, 64),
            string.IsNullOrWhiteSpace(payload.Tooltip) ? "Waiting for generated-item hydration." : payload.Tooltip,
            "player_save_ref");
        data.RecipeKey = SafeText(payload.RecipeKey, 120);
        data.Name = string.IsNullOrWhiteSpace(payload.Name) ? "Generated Item" : SafeText(payload.Name, 80);
        data.ParentA = SafeText(payload.ParentA, 80);
        data.ParentB = SafeText(payload.ParentB, 80);
        data.Category = SafeText(payload.Category, 32).ToLowerInvariant();
        data.RecipeMeta.WorldScoped = payload.WorldScoped;
        data.RecipeMeta.WorldId = SafeText(payload.WorldId, 32);
        data.Normalize();
        return data;
    }

    private static GeneratedItemData InertUnavailable(string id, string tooltip, string sourceMode)
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
            Tooltip = tooltip,
            Category = "generic",
            SourceMode = sourceMode,
            Tags = new[] { "generated", "unavailable" },
            Canonical = new CanonicalSpec { HeadNoun = "item", Class = "generic" },
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
                ObjectType = "unavailable_item",
                SpriteStatus = "unavailable",
                PreferredCanvasSize = 32,
                InventoryScale = 1f,
                WorldScale = 1f,
            },
            VfxManifest = VfxManifestSpec.Empty(),
        };
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
        clone.ExtensionData = new Dictionary<string, JsonElement>();
        clone.SourceRepresentation = Array.Empty<SourceRepresentationSpec>();
        clone.Inheritance = Array.Empty<InheritanceSpec>();
        clone.ItemKnowledge = new ItemKnowledgeSpec();
        clone.Tags = SafeTextArray(clone.Tags, 12, 32);
        clone.Visual.ImagePrompt = "";
        clone.Visual.NegativePrompt = "";
        clone.Visual.EquipOverlayPrompt = "";
        clone.Visual.SpriteRawPath = "";
        clone.Visual.SpritePath = FileNameOnly(clone.Visual.SpritePath);
        clone.Visual.EquipOverlayPath = FileNameOnly(clone.Visual.EquipOverlayPath);
        foreach (RuntimeEntitySpec entity in clone.RuntimeProgram.Entities)
        {
            entity.Visual.Prompt = "";
            entity.Visual.Silhouette = "";
            entity.Visual.VisualIdentity = "";
            entity.Visual.SpritePath = FileNameOnly(entity.Visual.SpritePath);
        }
        clone.VfxManifest.Debug = new VfxDebugSpec();
        clone.VfxManifest.InspirationNames = Array.Empty<string>();
        foreach (VfxSlotSpec slot in clone.VfxManifest.Slots)
        {
            slot.EffectName = "";
            slot.BakedClipId = "";
            slot.BakedClipHash = "";
            slot.BakedCommandCount = 0;
            slot.BakedCommands = Array.Empty<VfxBakedCommandSpec>();
        }
        if (clone.RecipeMeta is not null)
        {
            clone.RecipeMeta.ParentIdentities = Array.Empty<string>();
            clone.RecipeMeta.ParentCategories = Array.Empty<string>();
            clone.RecipeMeta.AssetBaseUrl = SafeText(clone.RecipeMeta.AssetBaseUrl, 200);
            clone.RecipeMeta.AssetFiles = (clone.RecipeMeta.AssetFiles ?? Array.Empty<string>())
                .Select(FileNameOnly)
                .Where(x => x.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Take(64)
                .ToArray();
        }
    }

    private static string FileNameOnly(string? path)
    {
        string text = (path ?? "").Trim();
        if (string.IsNullOrWhiteSpace(text)) return "";
        try { return Path.GetFileName(text.Replace('\\', '/')); }
        catch { return ""; }
    }

    private static int Utf8ByteCount(string value) => Encoding.UTF8.GetByteCount(value ?? "");

    private sealed class PlayerSaveReferencePayload
    {
        [JsonPropertyName("infiniSaveKind")] public string InfiniSaveKind { get; set; } = PlayerSaveReferenceKind;
        [JsonPropertyName("version")] public int Version { get; set; } = 5;
        [JsonPropertyName("id")] public string Id { get; set; } = "";
        [JsonPropertyName("recipeKey")] public string RecipeKey { get; set; } = "";
        [JsonPropertyName("runtimeApiVersion")] public string RuntimeApiVersion { get; set; } = RuntimeProgramSpec.CurrentApiVersion;
        [JsonPropertyName("worldScoped")] public bool WorldScoped { get; set; } = true;
        [JsonPropertyName("worldId")] public string WorldId { get; set; } = "";
        [JsonPropertyName("name")] public string Name { get; set; } = "Generated Item";
        [JsonPropertyName("tooltip")] public string Tooltip { get; set; } = "";
        [JsonPropertyName("category")] public string Category { get; set; } = "generic";
        [JsonPropertyName("parentA")] public string ParentA { get; set; } = "";
        [JsonPropertyName("parentB")] public string ParentB { get; set; } = "";
    }
}
