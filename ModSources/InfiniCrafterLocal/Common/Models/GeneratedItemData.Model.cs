#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.VFX;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Models;

// AGENT MAP: game-facing wire/cache/runtime DTO.
// Python may preserve extra/future data, but C# executes only explicit supported
// sub-specs below (Gameplay, Accessory, Armor, RuntimeProgram, Visual, VfxManifest).
// Adding a property here is not enough: wire it through Normalize,
// Apply, runtime executors, tests, and docs before treating it as gameplay.
public sealed partial class GeneratedItemData
{
    public string RuntimeApiVersion { get; set; } = RuntimeApiCurrent;
    private const string RuntimeApiCurrent = InfiniRuntimeLimits.RuntimeApiCurrent;
    public string Id { get; set; } = Guid.NewGuid().ToString("N")[..12];
    public string RecipeKey { get; set; } = "";
    public string Name { get; set; } = "Generated Item";
    public string ParentA { get; set; } = "Unknown";
    public string ParentB { get; set; } = "Unknown";
    public string MergeMode { get; set; } = "literal"; // literal, lexicalized_literal, functional, abstract
    public string Category { get; set; } = "generic";
    public string SourceMode { get; set; } = "generated"; // generated, vanilla_match, fallback

    public string[] Tags { get; set; } = Array.Empty<string>();
    public CanonicalSpec Canonical { get; set; } = new();
    public SourceRepresentationSpec[] SourceRepresentation { get; set; } = Array.Empty<SourceRepresentationSpec>();
    public InheritanceSpec[] Inheritance { get; set; } = Array.Empty<InheritanceSpec>();
    public LossBudgetSpec LossBudget { get; set; } = new();
    public RecipeMetaSpec RecipeMeta { get; set; } = new();
    public ItemKnowledgeSpec ItemKnowledge { get; set; } = new();
    public GeneratedParentSummarySpec GeneratedParentSummary { get; set; } = new();

    public GameplaySpec Gameplay { get; set; } = new();
    public AccessorySpec Accessory { get; set; } = new();
    public ArmorSpec Armor { get; set; } = new();
    public RuntimeProgramSpec RuntimeProgram { get; set; } = new();
    public VisualSpec Visual { get; set; } = new();
    public VfxManifestSpec VfxManifest { get; set; } = new();


    public Dictionary<string, JsonElement> Debug { get; set; } = new();

    // Preserve non-executable diagnostics such as recipeHealth and contractVersions.
    // Retired executable shapes are explicitly rejected during Normalize.
    [JsonExtensionData]
    public Dictionary<string, JsonElement> ExtensionData { get; set; } = new();

}

// =============================================================================
// NAV: GENERATED_ITEM_SUBSPECS
// =============================================================================
public sealed class CanonicalSpec
{
    public string HeadNoun { get; set; } = "item";
    public string[] Modifiers { get; set; } = Array.Empty<string>();
    public string Material { get; set; } = "";
    public string Class { get; set; } = "generic";
    public string[] ShapeAnchors { get; set; } = Array.Empty<string>();
    public string[] VisualAnchors { get; set; } = Array.Empty<string>();
    public string[] HardTags { get; set; } = Array.Empty<string>();
    public string[] SoftTags { get; set; } = Array.Empty<string>();
}

public sealed class SourceRepresentationSpec
{
    public string Parent { get; set; } = "Unknown";
    public string Mode { get; set; } = "visual"; // visual, gameplay, semantic, discarded
    public string Importance { get; set; } = "secondary";
    public string VisualAnchor { get; set; } = "";
    public string Placement { get; set; } = "";
    public string Rationale { get; set; } = "";
}

public sealed class InheritanceSpec
{
    public string Parent { get; set; } = "Unknown";
    public string Role { get; set; } = "influence"; // base_shape, material, attachment, effect, semantic, function
    public string[] PreservedFeatures { get; set; } = Array.Empty<string>();
    public string[] VisualAnchors { get; set; } = Array.Empty<string>();
    public string[] GameplayAnchors { get; set; } = Array.Empty<string>();
    public string LossPolicy { get; set; } = "preserve_hard_tags";
}

public sealed class LossBudgetSpec
{
    public int RequiredParentPresence { get; set; } = 2;
    public int MaxDroppedHardTags { get; set; } = 0;
    public bool MustPreserveHeadNounFromAtLeastOneParent { get; set; } = true;
    public bool MustPreserveMaterialIfPresent { get; set; } = true;
    public float MinPreservationScore { get; set; } = 0.65f;
}

public sealed class RecipeMetaSpec
{
    public bool UniversalRecipe { get; set; } = true;
    public int GenerationDepth { get; set; } = 0;
    public int[] ParentGeneratedDepths { get; set; } = Array.Empty<int>();
    public string RecipeCoherence { get; set; } = "weak";
    public float ChaosBudget { get; set; } = 0f;
    public float NoveltyBudget { get; set; } = 0f;
    public string[] ParentIdentities { get; set; } = Array.Empty<string>();
    public string[] ParentCategories { get; set; } = Array.Empty<string>();
    public string SampledLane { get; set; } = "";
    public string SampledCategory { get; set; } = "";
    public bool WorldScoped { get; set; } = true;
    public string WorldId { get; set; } = "";
    public string AssetTransport { get; set; } = "native";
    public string AssetBaseUrl { get; set; } = "";
    public string[] AssetFiles { get; set; } = Array.Empty<string>();
}


public sealed class ItemKnowledgeSpec
{
    public bool Enabled { get; set; } = true;
    public ParentItemCardSpec[] Parents { get; set; } = Array.Empty<ParentItemCardSpec>();
    public ParentItemCardSpec ResultCard { get; set; } = new();
    public string StrongestTier { get; set; } = "unknown";
    public float StrongestPowerScore { get; set; } = 0f;
    public string StrongestSourceHint { get; set; } = "";
    public string StrongestMaterialTier { get; set; } = "";
    public float StrongestMaterialPowerScore { get; set; } = 0f;
    public string[] TagsFromKnowledge { get; set; } = Array.Empty<string>();
}

public sealed class ParentItemCardSpec
{
    public string Name { get; set; } = "Unknown";
    public string Identity { get; set; } = "";
    public string Category { get; set; } = "generic";
    public string Tier { get; set; } = "unknown";
    public float PowerScore { get; set; } = 0f;
    public float Confidence { get; set; } = 0f;
    public string SourceHint { get; set; } = "";
    public string[] Tags { get; set; } = Array.Empty<string>();
    public int GeneratedDepth { get; set; } = 0;
}

public sealed class GeneratedParentSummarySpec
{
    public const string CurrentSchema = "infini.generated-parent-summary.v2";

    public string Schema { get; set; } = CurrentSchema;
    public string Name { get; set; } = "";
    public string Identity { get; set; } = "";
    public string Description { get; set; } = "";
    public string PlayerExperience { get; set; } = "";
    public string[] NotableEffects { get; set; } = Array.Empty<string>();
    public string RuntimePrimaryEntityId { get; set; } = "";
    public string[] RuntimeEntityIds { get; set; } = Array.Empty<string>();

    private static string Bounded(string? value, int maxLength)
    {
        string text = (value ?? "").Trim();
        return text.Length <= maxLength ? text : text[..maxLength];
    }

    private static string[] BoundedArray(string[]? values, int maxItems, int maxLength)
        => (values ?? Array.Empty<string>())
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .Select(x => Bounded(x, maxLength))
            .Take(maxItems)
            .ToArray();

    public void Normalize()
    {
        Schema = Bounded(Schema, 64);
        if (!string.Equals(Schema, CurrentSchema, StringComparison.Ordinal))
            throw new InvalidDataException($"Unsupported generated parent summary schema '{Schema}'");
        Name = Bounded(Name, 80);
        Identity = Bounded(Identity, 180);
        Description = Bounded(Description, 700);
        PlayerExperience = Bounded(PlayerExperience, 500);
        NotableEffects = BoundedArray(NotableEffects, 12, 280);
        RuntimePrimaryEntityId = Bounded(RuntimePrimaryEntityId, 48);
        RuntimeEntityIds = BoundedArray(RuntimeEntityIds, 24, 48);
    }
}


public sealed class GeneratedBuffSpec
{
    public int DurationTicks { get; set; } = 0;
    public float MiningSpeedMultiplier { get; set; } = 1f;
    public float EmitLightStrength { get; set; } = 0f;
    public string LightColorName { get; set; } = "";
    // Current tMod runtime is bool-backed via Player.findTreasure.  The radius is
    // preserved for authoring/debug/future implementation, but gameplay treats any
    // value > 0 as spelunker-like ore sense.
    public int OreSenseRadiusTiles { get; set; } = 0;
    public bool OreSenseEnabled => OreSenseRadiusTiles > 0;
    public float MovementSpeed { get; set; } = 0f;
    public float JumpBoost { get; set; } = 0f;
    public int ManaRegen { get; set; } = 0;
    public int LifeRegen { get; set; } = 0;

    public bool HasAnyEffect => DurationTicks > 0 && (
        Math.Abs(MiningSpeedMultiplier - 1f) > 0.001f || EmitLightStrength > 0f || OreSenseEnabled ||
        Math.Abs(MovementSpeed) > 0.001f || Math.Abs(JumpBoost) > 0.001f || ManaRegen != 0 || LifeRegen != 0);

    public void Normalize()
    {
        DurationTicks = Math.Min(21600, Math.Max(0, DurationTicks));
        MiningSpeedMultiplier = MathF.Min(4f, MathF.Max(0.25f, MiningSpeedMultiplier <= 0f ? 1f : MiningSpeedMultiplier));
        EmitLightStrength = MathF.Min(1.5f, MathF.Max(0f, EmitLightStrength));
        LightColorName = RuntimeColorPolicy.NormalizeRequired(LightColorName, allowEmpty: EmitLightStrength <= 0f);
        OreSenseRadiusTiles = Math.Min(60, Math.Max(0, OreSenseRadiusTiles));
        MovementSpeed = MathF.Min(2f, MathF.Max(-0.5f, MovementSpeed));
        JumpBoost = MathF.Min(8f, MathF.Max(0f, JumpBoost));
        ManaRegen = Math.Min(120, Math.Max(0, ManaRegen));
        LifeRegen = Math.Min(120, Math.Max(0, LifeRegen));
    }
}

public sealed class GameplaySpec
{
    public string Kind { get; set; } = "generic"; // weapon, potion, accessory, furniture, material, generic
    public string Stage { get; set; } = "early";
    public float PowerBudget { get; set; } = 1f;
    public string DamageClass { get; set; } = "generic";
    public int Damage { get; set; } = 0;
    public float Knockback { get; set; } = 2f;
    public int UseTime { get; set; } = 24;
    public int UseAnimation { get; set; } = 24;
    public string UseStyleName { get; set; } = "swing";
    public int UseStyle { get; set; } = ItemUseStyleID.Swing;
    public bool AutoReuse { get; set; } = true;
    public int HoldoutOffsetX { get; set; } = 0;
    public int HoldoutOffsetY { get; set; } = 0;
    public string HandPose { get; set; } = "";
    public string ReleaseTiming { get; set; } = "";
    public int ManaCost { get; set; } = 0;
    public int Rarity { get; set; } = ItemRarityID.White;
    public int Value { get; set; } = 100;
    public int MaxStack { get; set; } = 1;
    // v0.4.4: stack granted by one generated craft. Needed for LLM-authored ammo/material batches.
    public int CraftYield { get; set; } = 1;
    // Exact per-instance Terraria ammo fields. This marks the generated item as
    // ammunition; it does not configure another item to consume that ammo.
    public string AmmoCategory { get; set; } = "";
    public int AmmoProjectileId { get; set; } = ProjectileID.None;
    public float AmmoShootSpeedPxPerTick { get; set; } = 0f;
    public bool NotAmmo { get; set; } = false;

    public int Width { get; set; } = 24;
    public int Height { get; set; } = 24;
    public float ItemScale { get; set; } = 1f;
    public bool UseTurn { get; set; } = false;
    public int HealLife { get; set; } = 0;
    public int HealMana { get; set; } = 0;
    public bool Potion { get; set; } = false;
    public int BuffCode { get; set; } = InfiniTerrariaSentinels.NoBuffType;
    public int BuffTime { get; set; } = 0;
    public BuffEntrySpec[] ExtraBuffs { get; set; } = Array.Empty<BuffEntrySpec>();
    public GeneratedBuffSpec GeneratedBuff { get; set; } = new();
    public int PickPower { get; set; } = 0;
    public int AxePower { get; set; } = 0;
    public int HammerPower { get; set; } = 0;

    public string MobilityMode { get; set; } = "";
    public int MobilityRangeTiles { get; set; } = 0;
    public int MobilityCooldownTicks { get; set; } = 0;
    public bool MobilitySafeTileOnly { get; set; } = true;
    public float MiningSpeedScale { get; set; } = 1f;

    public float HoldLightStrength { get; set; } = 0f;
    public string HoldLightColorName { get; set; } = "";
    public string UseConditionMode { get; set; } = ""; // none|grounded|not_wet|life_above|mana_above
    public int UseConditionMinLife { get; set; } = 0;
    public int UseConditionMinMana { get; set; } = 0;
}

public sealed class BuffEntrySpec
{
    public int BuffCode { get; set; } = InfiniTerrariaSentinels.NoBuffType;
    public int BuffTime { get; set; } = 0;
}

public sealed class AccessorySpec
{
    public bool Enabled { get; set; } = false;
    public string Archetype { get; set; } = "generic"; // mobility, defense, damage, utility, hybrid
    public int Defense { get; set; } = 0;
    public int MaxLife { get; set; } = 0;
    public int MaxMana { get; set; } = 0;
    public int LifeRegen { get; set; } = 0;
    public int ManaRegen { get; set; } = 0;
    public float MovementSpeed { get; set; } = 0f;
    public float MaxRunSpeed { get; set; } = 0f;
    public float JumpSpeed { get; set; } = 0f;
    public float GenericDamage { get; set; } = 0f;
    public float MeleeDamage { get; set; } = 0f;
    public float RangedDamage { get; set; } = 0f;
    public float MagicDamage { get; set; } = 0f;
    public float SummonDamage { get; set; } = 0f;
    public float GenericCrit { get; set; } = 0f;
    public float AttackSpeed { get; set; } = 0f;
    public float Knockback { get; set; } = 0f;
    public bool FallDamageImmune { get; set; } = false;
    public bool LavaImmune { get; set; } = false;
    public bool WaterWalk { get; set; } = false;
    public int MinionSlots { get; set; } = 0;
    public int SentrySlots { get; set; } = 0;
    public float ManaCostReduction { get; set; } = 0f;
    public float AmmoSaveChance { get; set; } = 0f;
    public int Aggro { get; set; } = 0;
    public float Endurance { get; set; } = 0f;
    public float ArmorPenetration { get; set; } = 0f;
    public float WhipRange { get; set; } = 0f;
    public float SummonTagDamage { get; set; } = 0f;
    public float LightStrength { get; set; } = 0f;
    public string LightColorName { get; set; } = "";
    public bool HasAnyEffect => Defense != 0 || MaxLife != 0 || MaxMana != 0 || LifeRegen != 0 || ManaRegen != 0
        || MovementSpeed != 0f || MaxRunSpeed != 0f || JumpSpeed != 0f
        || GenericDamage != 0f || MeleeDamage != 0f || RangedDamage != 0f || MagicDamage != 0f || SummonDamage != 0f
        || GenericCrit != 0f || AttackSpeed != 0f || Knockback != 0f
        || FallDamageImmune || LavaImmune || WaterWalk || MinionSlots != 0 || SentrySlots != 0
        || ManaCostReduction != 0f || AmmoSaveChance != 0f || Aggro != 0 || Endurance != 0f || ArmorPenetration != 0f
        || WhipRange != 0f || SummonTagDamage != 0f || LightStrength != 0f;
}

public sealed class ArmorSpec
{
    public bool Enabled { get; set; } = false;
    public string Slot { get; set; } = ""; // head, body, legs; required when enabled
    public string SetKey { get; set; } = "";
    public string Archetype { get; set; } = "hybrid";
    public int Defense { get; set; } = 0;
    public int MaxLife { get; set; } = 0;
    public int MaxMana { get; set; } = 0;
    public int LifeRegen { get; set; } = 0;
    public int ManaRegen { get; set; } = 0;
    public float MovementSpeed { get; set; } = 0f;
    public float MaxRunSpeed { get; set; } = 0f;
    public float JumpSpeed { get; set; } = 0f;
    public float GenericDamage { get; set; } = 0f;
    public float MeleeDamage { get; set; } = 0f;
    public float RangedDamage { get; set; } = 0f;
    public float MagicDamage { get; set; } = 0f;
    public float SummonDamage { get; set; } = 0f;
    public float GenericCrit { get; set; } = 0f;
    public float AttackSpeed { get; set; } = 0f;
    public float Knockback { get; set; } = 0f;
    public bool FallDamageImmune { get; set; } = false;
    public bool LavaImmune { get; set; } = false;
    public bool WaterWalk { get; set; } = false;
    public int MinionSlots { get; set; } = 0;
    public int SentrySlots { get; set; } = 0;
    public float ManaCostReduction { get; set; } = 0f;
    public float AmmoSaveChance { get; set; } = 0f;
    public int Aggro { get; set; } = 0;
    public float Endurance { get; set; } = 0f;
    public float ArmorPenetration { get; set; } = 0f;
    public float WhipRange { get; set; } = 0f;
    public float SummonTagDamage { get; set; } = 0f;
    public float LightStrength { get; set; } = 0f;
    public string LightColorName { get; set; } = "";

    public float SetBonusGenericDamage { get; set; } = 0f;
    public float SetBonusMeleeDamage { get; set; } = 0f;
    public float SetBonusRangedDamage { get; set; } = 0f;
    public float SetBonusMagicDamage { get; set; } = 0f;
    public float SetBonusSummonDamage { get; set; } = 0f;
    public float SetBonusGenericCrit { get; set; } = 0f;
    public float SetBonusMovementSpeed { get; set; } = 0f;
    public int SetBonusLifeRegen { get; set; } = 0;
    public int SetBonusManaRegen { get; set; } = 0;
    public int SetBonusMinionSlots { get; set; } = 0;
    public int SetBonusSentrySlots { get; set; } = 0;
    public float SetBonusManaCostReduction { get; set; } = 0f;
    public float SetBonusAmmoSaveChance { get; set; } = 0f;
    public int SetBonusAggro { get; set; } = 0;
    public float SetBonusEndurance { get; set; } = 0f;
    public float SetBonusArmorPenetration { get; set; } = 0f;

    public bool HasAnyEffect => Defense != 0 || MaxLife != 0 || MaxMana != 0 || LifeRegen != 0 || ManaRegen != 0
        || MovementSpeed != 0f || MaxRunSpeed != 0f || JumpSpeed != 0f
        || GenericDamage != 0f || MeleeDamage != 0f || RangedDamage != 0f || MagicDamage != 0f || SummonDamage != 0f
        || GenericCrit != 0f || AttackSpeed != 0f || Knockback != 0f
        || FallDamageImmune || LavaImmune || WaterWalk || MinionSlots != 0 || SentrySlots != 0
        || ManaCostReduction != 0f || AmmoSaveChance != 0f || Aggro != 0 || Endurance != 0f || ArmorPenetration != 0f
        || WhipRange != 0f || SummonTagDamage != 0f || LightStrength != 0f;
}


// =============================================================================
// NAV: ATTACK_SPEC_CONTRACT
// =============================================================================
public sealed class VisualSpec
{
    public string ObjectType { get; set; } = "generic_item";
    public string Style { get; set; } = "terraria_item_sprite";
    public string[] RequiredAnchors { get; set; } = Array.Empty<string>();
    public string[] Palette { get; set; } = Array.Empty<string>();
    public string ImagePrompt { get; set; } = "small pixel art item icon, solid magenta key background";
    public string EquipOverlayPrompt { get; set; } = "";
    public string NegativePrompt { get; set; } = "scene, background, character, realistic render, blurry, text, watermark";
    public string AssetManifestPath { get; set; } = "";
    public string SpriteStatus { get; set; } = "placeholder"; // placeholder, prompt_only, generated, fallback, failed
    public string SpritePath { get; set; } = "";
    public string SpriteRawPath { get; set; } = "";
    public string SpriteUrl { get; set; } = "";
    public string EquipOverlayStatus { get; set; } = "";
    public string EquipOverlayPath { get; set; } = "";
    public string EquipOverlayUrl { get; set; } = "";
    public float EquipOverlayScore { get; set; } = 0f;
    public float PreservationScore { get; set; } = 0f;
    public float SpriteTechnicalScore { get; set; } = 0f;
    public string SemanticReviewStatus { get; set; } = "not_performed";
    public int PreferredCanvasSize { get; set; } = 32;
    public float InventoryScale { get; set; } = 1f;
    public float WorldScale { get; set; } = 1f;
    public int DrawOffsetX { get; set; } = 0;
    public int DrawOffsetY { get; set; } = 0;
    public string VisualSoulSignature { get; set; } = "";
    public string VisualSoulArchetype { get; set; } = "quiet";
    public string DominantColorHex { get; set; } = "#ffffff";
    public string AccentColorHex { get; set; } = "#ffffff";
    public float VisualSoulGlow { get; set; } = 0f;
    public float VisualSoulPulse { get; set; } = 0f;
    public float VisualSoulCoverage { get; set; } = 0f;
    public float VisualSoulEdgeDensity { get; set; } = 0f;
}
