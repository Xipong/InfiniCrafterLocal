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
// Python and C# admit the same explicit current item envelope; stage-only
// runtimeContract/visualKit are removed by Python's delivery projection.
// C# executes only the supported sub-specs below.
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
    public RecipeMetaSpec RecipeMeta { get; set; } = new();

    public GeneratedParentSummarySpec GeneratedParentSummary { get; set; } = new();

    public GameplaySpec Gameplay { get; set; } = new();
    public AccessorySpec Accessory { get; set; } = new();
    public ArmorSpec Armor { get; set; } = new();
    public RuntimeProgramSpec RuntimeProgram { get; set; } = new();
    public VisualSpec Visual { get; set; } = new();
    public VfxManifestSpec VfxManifest { get; set; } = new();

    public Dictionary<string, JsonElement> Debug { get; set; } = new();

    // Exact current Python sidecars. They are advisory/diagnostic, never gameplay
    // authority; the root remains closed to unknown or retired contract fields.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? Concept { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? Realization { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? LlmStageAccounting { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? ContractVersions { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? RecipeHealth { get; set; }

}

// =============================================================================
// NAV: GENERATED_ITEM_SUBSPECS
// =============================================================================
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

public sealed class GeneratedParentSummarySpec
{
    public const string CurrentSchema = "infini.generated-parent-summary.v2";

    public string Schema { get; set; } = CurrentSchema;
    public string Name { get; set; } = "";
    public string Identity { get; set; } = "";
    public string Description { get; set; } = "";
    public string PlayerExperience { get; set; } = "";

    private static string Bounded(string? value, int maxLength)
    {
        string text = (value ?? "").Trim();
        return text.Length <= maxLength ? text : text[..maxLength];
    }

    private static string BoundedReport(string? value, int maxScalars)
    {
        // Match the Author schema's Unicode-character allowance, not UTF-16
        // storage units. Keep full admitted reports without cutting a surrogate.
        string text = (value ?? "").Trim();
        int scalars = 0, end = 0;
        foreach (Rune rune in text.EnumerateRunes())
        {
            if (scalars == maxScalars) break;
            end += rune.Utf16SequenceLength;
            scalars++;
        }
        return end == text.Length ? text : text[..end];
    }

    public void Normalize()
    {
        Schema = Bounded(Schema, 64);
        if (!string.Equals(Schema, CurrentSchema, StringComparison.Ordinal))
            throw new InvalidDataException($"Unsupported generated parent summary schema '{Schema}'");
        Name = BoundedReport(Name, 80);
        Identity = Bounded(Identity, 180);
        Description = BoundedReport(Description, 4000);
        PlayerExperience = BoundedReport(PlayerExperience, 3000);

    }
}

public sealed class GeneratedBuffSpec
{
    private PlayerEffectSpec? _playerEffect;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public PlayerEffectSpec? PlayerEffect
    {
        get => _playerEffect;
        set { if (value is null) throw new InvalidDataException("present playerEffect cannot be null"); value.Validate(); _playerEffect = value; }
    }

    public const int PermanentDurationTicks = 0;
    public const int MaxFiniteDurationTicks = int.MaxValue - 1;
    public const int PersistentAfterDeathMaxTicks = 20 * 60 * 60;

    private GeneratedCombatBuffSpec? _combat;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public GeneratedCombatBuffSpec? Combat
    {
        get => _combat;
        set
        {
            if (value is null) throw new InvalidDataException("present combat buff cannot be null");
            value.Validate(); _combat = value;
        }
    }
    private int? _durationTicks;
    internal bool HasExplicitDuration => _durationTicks.HasValue;
    public int DurationTicks
    {
        get => _durationTicks ?? 0;
        set => _durationTicks = value is >= 0 and <= MaxFiniteDurationTicks ? value
            : throw new InvalidDataException("generated buff durationTicks must be 0 (permanent) or a positive Int32 duration below Int32.MaxValue");
    }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(GeneratedBuffExhaustionTicksConverter))]
    public int? ExhaustionTicks
    {
        get => _exhaustionTicks;
        set => _exhaustionTicks = value is null or (>= 0 and <= 21600) ? value
            : throw new InvalidDataException("generated buff exhaustionTicks must be 0..21600");
    }
    private int? _exhaustionTicks;
    public float MiningSpeedMultiplier { get; set; } = 1f;
    public float EmitLightStrength { get; set; } = 0f;
    public string LightColorName { get; set; } = "";
    // Existing wire count is boolean-backed: every positive value enables
    // native Spelunker treasure highlighting; it is not a radius-limited scan.
    public int OreSenseRadiusTiles { get; set; } = 0;
    public bool OreSenseEnabled => OreSenseRadiusTiles > 0;
    public float MovementSpeed { get; set; } = 0f;
    public float JumpBoost { get; set; } = 0f;
    public int ManaRegen { get; set; } = 0;
    public int LifeRegen { get; set; } = 0;
    private string? _lifeRegenCondition;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? LifeRegenCondition
    {
        get => _lifeRegenCondition;
        set => _lifeRegenCondition = PlayerEffectSpec.ValidateCondition(value);
    }
    private string? _treasureSenseCondition;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TreasureSenseCondition
    {
        get => _treasureSenseCondition;
        set => _treasureSenseCondition = PlayerEffectSpec.ValidateCondition(value);
    }


    private bool HasEffectStats =>
        MiningSpeedMultiplier != 1f || EmitLightStrength > 0f || OreSenseEnabled ||
        MovementSpeed != 0f || JumpBoost != 0f || ManaRegen != 0 || LifeRegen != 0 || Combat?.HasEffect == true || PlayerEffect?.HasEffect == true;

    public bool HasAnyEffect => _durationTicks.HasValue && HasEffectStats;

    public void Normalize()
    {
        if (!_durationTicks.HasValue && HasEffectStats)
            throw new InvalidDataException("nonempty generated buff requires explicit durationTicks; 0 means permanent");
        MiningSpeedMultiplier = MathF.Min(4f, MathF.Max(0.25f, MiningSpeedMultiplier <= 0f ? 1f : MiningSpeedMultiplier));
        EmitLightStrength = MathF.Min(1.5f, MathF.Max(0f, EmitLightStrength));
        LightColorName = RuntimeColorPolicy.NormalizeRequired(LightColorName, allowEmpty: EmitLightStrength <= 0f);
        OreSenseRadiusTiles = Math.Min(60, Math.Max(0, OreSenseRadiusTiles));
        MovementSpeed = MathF.Min(2f, MathF.Max(-0.8f, MovementSpeed));
        JumpBoost = MathF.Min(8f, MathF.Max(-8f, JumpBoost));
        ManaRegen = Math.Min(120, Math.Max(-100, ManaRegen));
        LifeRegen = Math.Min(120, Math.Max(-100, LifeRegen));
    }
}

// Property-bound raw admission covers default and named generatedBuff readers.
// Omission does not invoke the converter; present null is not omission.
public sealed class GeneratedBuffExhaustionTicksConverter : JsonConverter<int?>
{
    public override bool HandleNull => true;
    public override int? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.Number || !reader.TryGetInt32(out int ticks)
            || ticks is < 0 or > 21600)
            throw new JsonException("present exhaustionTicks must be an integer 0..21600");
        return ticks;
    }
    public override void Write(Utf8JsonWriter writer, int? value, JsonSerializerOptions options)
    {
        if (value is null || value is < 0 or > 21600)
            throw new JsonException("present exhaustionTicks must be an integer 0..21600");
        writer.WriteNumberValue(value.Value);
    }
}

public sealed class GameplaySpec : IItemEffectsSpec
{
    public string Kind { get; set; } = "generic"; // weapon, potion, accessory, furniture, material, generic
    public string DamageClass { get; set; } = "generic";
    public int Damage { get; set; } = 0;
    public float Knockback { get; set; } = 2f;
    public int UseTime { get; set; } = 24;
    public int UseAnimation { get; set; } = 24;
    public string UseStyleName { get; set; } = "swing";
    public int UseStyle { get; set; } = ItemUseStyleID.Swing;
    public bool AutoReuse { get; set; } = true;
    // Absence is inactive and must stay absent in old definition/network hashes.
    // Explicit false is inert; only an authored fn emits true. Present null is invalid.
    private bool? _collectSeedsFromGrass;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? CollectSeedsFromGrass
    {
        get => _collectSeedsFromGrass;
        set => _collectSeedsFromGrass = value ?? throw new InvalidDataException("collectSeedsFromGrass must be a boolean when present");
    }
    public int HoldoutOffsetX { get; set; } = 0;
    public int HoldoutOffsetY { get; set; } = 0;
    public string HandPose { get; set; } = "";
    public string ReleaseTiming { get; set; } = "";
    public int ManaCost { get; set; } = 0;
    private string? _manaCostInput;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ManaCostInput
    {
        get => _manaCostInput;
        set => _manaCostInput = RuntimeUseInputScope.Require(value);
    }
    public int ManaCostForInput(string input)
        => RuntimeUseInputScope.Matches(ManaCostInput, input) ? Math.Max(0, ManaCost) : 0;
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
    private RuntimeUseConditionSpec[]? _useConditions;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeUseConditionSpec[]? UseConditions
    {
        get => _useConditions;
        set => _useConditions = value ?? throw new InvalidDataException("useConditions cannot be null");
    }
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
    private PlayerEffectSpec? _playerEffect;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public PlayerEffectSpec? PlayerEffect
    {
        get => _playerEffect;
        set { if (value is null) throw new InvalidDataException("present playerEffect cannot be null"); value.Validate(); _playerEffect = value; }
    }

    private bool? _treasureSense;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? TreasureSense
    {
        get => _treasureSense;
        set => _treasureSense = value is bool enabled ? enabled
            : throw new InvalidDataException("present treasureSense must be a boolean");
    }
    public bool Enabled { get; set; } = false;
    public bool WireVision { get; set; } = false;
    public bool IceSkate { get; set; } = false;
    public bool NoKnockback { get; set; } = false;
    public bool FireWalk { get; set; } = false;
    public sealed class AccRunSpeedJsonConverter : RawJsonFloatDomainConverter
    {
        public AccRunSpeedJsonConverter() : base("0", "20", "0") { }
    }
    private float _accRunSpeed;
    [System.Text.Json.Serialization.JsonConverter(typeof(AccRunSpeedJsonConverter))]
    public float AccRunSpeed
    {
        get => _accRunSpeed;
        set => _accRunSpeed = float.IsFinite(value) && value is >= 0f and <= 20f ? value
            : throw new System.IO.InvalidDataException("accRunSpeed requires finite 0..20 pixels/tick");
    }
    private int _rocketBoots;
    public int RocketBoots
    {
        get => _rocketBoots;
        set => _rocketBoots = value is >= 0 and <= 5 ? value
            : throw new System.IO.InvalidDataException("rocketBoots requires native mode 0..5");
    }
    public int Defense { get; set; } = 0;
    public int MaxLife { get; set; } = 0;
    public int MaxMana { get; set; } = 0;
    public int LifeRegen { get; set; } = 0;
    private string? _lifeRegenCondition;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? LifeRegenCondition
    {
        get => _lifeRegenCondition;
        set => _lifeRegenCondition = PlayerEffectSpec.ValidateCondition(value);
    }
    private string? _treasureSenseCondition;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TreasureSenseCondition
    {
        get => _treasureSenseCondition;
        set => _treasureSenseCondition = PlayerEffectSpec.ValidateCondition(value);
    }

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
    public bool HasAnyEffect => TreasureSense == true || PlayerEffect?.HasEffect == true || WireVision || IceSkate || NoKnockback || FireWalk || RocketBoots != 0 || AccRunSpeed != 0f || Defense != 0 || MaxLife != 0 || MaxMana != 0 || LifeRegen != 0 || ManaRegen != 0
        || MovementSpeed != 0f || MaxRunSpeed != 0f || JumpSpeed != 0f
        || GenericDamage != 0f || MeleeDamage != 0f || RangedDamage != 0f || MagicDamage != 0f || SummonDamage != 0f
        || GenericCrit != 0f || AttackSpeed != 0f || Knockback != 0f
        || FallDamageImmune || LavaImmune || WaterWalk || MinionSlots != 0 || SentrySlots != 0
        || ManaCostReduction != 0f || AmmoSaveChance != 0f || Aggro != 0 || Endurance != 0f || ArmorPenetration != 0f
        || WhipRange != 0f || SummonTagDamage != 0f || LightStrength != 0f;
}

public sealed class ArmorSpec
{
    private PlayerEffectSpec? _playerEffect;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public PlayerEffectSpec? PlayerEffect
    {
        get => _playerEffect;
        set { if (value is null) throw new InvalidDataException("present playerEffect cannot be null"); value.Validate(); _playerEffect = value; }
    }

    private bool? _treasureSense;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? TreasureSense
    {
        get => _treasureSense;
        set => _treasureSense = value is bool enabled ? enabled
            : throw new InvalidDataException("present treasureSense must be a boolean");
    }
    public bool Enabled { get; set; } = false;
    public string Slot { get; set; } = ""; // head, body, legs; required when enabled
    public string SetKey { get; set; } = "";
    public int Defense { get; set; } = 0;
    public int MaxLife { get; set; } = 0;
    public int MaxMana { get; set; } = 0;
    public int LifeRegen { get; set; } = 0;
    private string? _lifeRegenCondition;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? LifeRegenCondition
    {
        get => _lifeRegenCondition;
        set => _lifeRegenCondition = PlayerEffectSpec.ValidateCondition(value);
    }
    private string? _treasureSenseCondition;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TreasureSenseCondition
    {
        get => _treasureSenseCondition;
        set => _treasureSenseCondition = PlayerEffectSpec.ValidateCondition(value);
    }

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

    public bool HasAnyEffect => TreasureSense == true || PlayerEffect?.HasEffect == true || Defense != 0 || MaxLife != 0 || MaxMana != 0 || LifeRegen != 0 || ManaRegen != 0
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
public sealed class ItemGripSpec
{
    [JsonRequired]
    public double NormalizedX { get; set; }
    [JsonRequired]
    public double NormalizedY { get; set; }

    public void Validate()
    {
        if (!double.IsFinite(NormalizedX) || !double.IsFinite(NormalizedY)
            || NormalizedX < 0 || NormalizedX > 1 || NormalizedY < 0 || NormalizedY > 1)
            throw new System.IO.InvalidDataException("visual.grip requires finite normalizedX and normalizedY in [0,1]");
    }
}

public sealed class VisualSpec
{
    private int? renderSizePx;
    private float? forwardAngleDegrees;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? RenderSizePx
    {
        get => renderSizePx;
        set => renderSizePx = SpritePresentation.RequireRenderSize(value);
    }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(SpritePresentation.ForwardAngleJsonConverter))]
    public float? ForwardAngleDegrees
    {
        get => forwardAngleDegrees;
        set => forwardAngleDegrees = SpritePresentation.RequireForwardAngle(value);
    }

    private ItemGripSpec? grip;
    private string? accessoryMount;
    // Omission keeps historical presentation; explicit null is not an authored choice.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ItemGripSpec? Grip
    {
        get => grip;
        set => grip = value ?? throw new System.IO.InvalidDataException("visual.grip must be an object when present");
    }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? AccessoryMount
    {
        get => accessoryMount;
        set => accessoryMount = value is "chest" or "back" or "waist" or "shoulder" or "orbit"
            ? value : throw new System.IO.InvalidDataException("visual.accessoryMount must be chest/back/waist/shoulder/orbit when present");
    }
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
    public float SpriteTechnicalScore { get; set; } = 0f;
    public int PreferredCanvasSize { get; set; } = 32;
    public float InventoryScale { get; set; } = 1f;
    public float WorldScale { get; set; } = 1f;
    public int DrawOffsetX { get; set; } = 0;
    public int DrawOffsetY { get; set; } = 0;
}

// Explicit input-local gates. Existing item-wide fields remain readable on saved v5 definitions.
public sealed class RuntimeUseConditionSpec
{
    public string Input { get; set; } = "";
    public string UseConditionMode { get; set; } = "";
    public int UseConditionMinLife { get; set; }
    public int UseConditionMinMana { get; set; }
    public void Validate()
    {
        if (Input is not ("primary_use" or "alternate_use")
            || UseConditionMode is not ("grounded" or "not_wet" or "life_above" or "mana_above")
            || UseConditionMinLife is < 0 or > 1000 || UseConditionMinMana is < 0 or > 1000
            || (UseConditionMode != "life_above" && UseConditionMinLife != 0)
            || (UseConditionMode != "mana_above" && UseConditionMinMana != 0))
            throw new InvalidDataException("Invalid input-local use condition");
    }
}
