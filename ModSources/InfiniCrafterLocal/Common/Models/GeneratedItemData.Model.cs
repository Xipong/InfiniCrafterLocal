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
// sub-specs below (Gameplay, Accessory, Armor, Attack, Visual, VfxManifest).
// Adding a property here is not enough: wire it through Normalize,
// Apply, runtime executors, tests, and docs before treating it as gameplay.
public sealed partial class GeneratedItemData
{
    public string RuntimeApiVersion { get; set; } = RuntimeApiCurrent;
    private const string RuntimeApiCurrent = InfiniRuntimeLimits.RuntimeApiCurrent;
    private const int MaxSupportedMovementCode = InfiniRuntimeLimits.MaxSupportedMovementCode;
    private const int MaxSupportedEffectCode = InfiniRuntimeLimits.MaxSupportedEffectCode;
    private const int MaxSupportedOnHitCode = InfiniRuntimeLimits.MaxSupportedOnHitCode;
    private static readonly HashSet<string> SupportedRuntimeApiVersions = new(StringComparer.OrdinalIgnoreCase)
    {
        RuntimeApiCurrent
    };
    public string Id { get; set; } = Guid.NewGuid().ToString("N")[..12];
    public string RecipeKey { get; set; } = "";
    public string Name { get; set; } = "Generated Item";
    public string ParentA { get; set; } = "Unknown";
    public string ParentB { get; set; } = "Unknown";
    public string Tooltip { get; set; } = "A locally generated item.";
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
    public AttackSpec Attack { get; set; } = new();
    public VisualSpec Visual { get; set; } = new();
    public PresentationGenomeSpec PresentationGenome { get; set; } = new();
    public VfxManifestSpec VfxManifest { get; set; } = new();
    public RuntimeArchetypeSpec RuntimeArchetype { get; set; } = new();
    public RuntimeContractSpec RuntimeContract { get; set; } = new();
    public Dictionary<string, JsonElement> Debug { get; set; } = new();

    // Preserve Python-authored top-level fields that the C# runtime does not execute yet
    // (runtimePlan, recipeHealth, contractVersions, runtimeAffordance, future diagnostics).
    // Local cache/debug round-trips should not lie by silently erasing them, while
    // network/player-save payloads still strip this extension bag explicitly below.
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
    public string Name { get; set; } = "";
    public string Fantasy { get; set; } = "";
    public string Category { get; set; } = "generic";
    public string DamageClass { get; set; } = "generic";
    public string Runtime { get; set; } = "none";
    public string VisualIdentity { get; set; } = "";
    public string[] NotableEffects { get; set; } = Array.Empty<string>();

    public void Normalize()
    {
        Name = string.IsNullOrWhiteSpace(Name) ? "" : Name.Trim()[..Math.Min(Name.Trim().Length, 80)];
        Fantasy = string.IsNullOrWhiteSpace(Fantasy) ? "" : Fantasy.Trim()[..Math.Min(Fantasy.Trim().Length, 180)];
        Category = string.IsNullOrWhiteSpace(Category) ? "generic" : Category.Trim()[..Math.Min(Category.Trim().Length, 32)];
        DamageClass = string.IsNullOrWhiteSpace(DamageClass) ? "generic" : DamageClass.Trim()[..Math.Min(DamageClass.Trim().Length, 32)];
        Runtime = string.IsNullOrWhiteSpace(Runtime) ? "none" : Runtime.Trim()[..Math.Min(Runtime.Trim().Length, 32)];
        VisualIdentity = string.IsNullOrWhiteSpace(VisualIdentity) ? "" : VisualIdentity.Trim()[..Math.Min(VisualIdentity.Trim().Length, 180)];
        NotableEffects = (NotableEffects ?? Array.Empty<string>()).Where(x => !string.IsNullOrWhiteSpace(x)).Select(x => x.Trim()[..Math.Min(x.Trim().Length, 64)]).Distinct(StringComparer.OrdinalIgnoreCase).Take(8).ToArray();
    }
}

public sealed class RuntimeArchetypeSpec
{
    public string Schema { get; set; } = "infini.runtime-archetype.v1";
    public string Source { get; set; } = "";
    public string Family { get; set; } = "";
    public string VanillaProjectileId { get; set; } = "";
    public string VanillaItemId { get; set; } = "";
    public string AiType { get; set; } = "";
    public bool Channelled { get; set; }
    public bool UsesHeldProjectile { get; set; }
    public string PhaseModel { get; set; } = "";
    public Dictionary<string, JsonElement> OverrideKnobs { get; set; } = new();
    public string SupportStatus { get; set; } = "";
    public List<string> SupportNotes { get; set; } = new();

    private static string Clean(string? value, int maxLen)
    {
        string s = value ?? "";
        if (s.Length > maxLen) s = s[..maxLen];
        return s.Replace('\0', ' ').Trim();
    }

    private static JsonElement JsonValue(object value) => JsonSerializer.SerializeToElement(value);

    private static int ClampKnob(JsonElement value, int min, int max, int fallback)
    {
        try
        {
            double raw = value.ValueKind switch
            {
                JsonValueKind.Number => value.GetDouble(),
                JsonValueKind.String when double.TryParse(value.GetString(), out double parsed) => parsed,
                _ => fallback,
            };
            if (double.IsNaN(raw) || double.IsInfinity(raw)) raw = fallback;
            return Math.Min(max, Math.Max(min, (int)Math.Round(raw)));
        }
        catch { return fallback; }
    }

    public void Normalize()
    {
        Schema = string.IsNullOrWhiteSpace(Schema) ? "infini.runtime-archetype.v1" : Clean(Schema, 64);
        Source = Clean(Source, 32).ToLowerInvariant().Replace('-', '_');
        if (Source is not ("" or "none" or "generated" or "vanilla" or "hybrid")) Source = "generated";
        SupportNotes ??= new List<string>();
        Family = Clean(Family, 48).ToLowerInvariant().Replace('-', '_');
        if (string.IsNullOrWhiteSpace(Family)) Family = "custom_executor";
        if (Family is not ("custom_executor" or "boomerang" or "yoyo" or "flail" or "whip" or "held_swing" or "held_thrust" or "channel_beam" or "charge_release" or "overhead_barrage" or "sentry" or "secondary_attack" or "unsupported"))
        {
            SupportNotes.Add($"unknown_family:{Family}");
            Family = "unsupported";
        }
        VanillaProjectileId = Clean(VanillaProjectileId, 64);
        VanillaItemId = Clean(VanillaItemId, 64);
        AiType = Clean(AiType, 64);
        PhaseModel = Clean(PhaseModel, 48).ToLowerInvariant().Replace('-', '_');
        if (Family == "boomerang") PhaseModel = "outbound_return";
        if (string.IsNullOrWhiteSpace(PhaseModel)) PhaseModel = Family switch
        {
            "boomerang" => "outbound_return",
            "yoyo" or "channel_beam" => "channel_hold",
            "charge_release" or "overhead_barrage" => "charge_release",
            "sentry" => "none",
            "held_swing" or "held_thrust" or "whip" => "swing_phase",
            _ => "none",
        };
        if (PhaseModel is not ("none" or "outbound_return" or "charge_release" or "swing_phase" or "channel_hold")) PhaseModel = "none";
        OverrideKnobs ??= new Dictionary<string, JsonElement>();
        var normalized = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (var pair in OverrideKnobs)
        {
            string key = Clean(pair.Key, 64);
            if (string.IsNullOrWhiteSpace(key)) continue;
            normalized[key] = key switch
            {
                "returnDelayTicks" => JsonValue(ClampKnob(pair.Value, 0, 180, 0)),
                "outboundPierce" => JsonValue(ClampKnob(pair.Value, -1, 20, 0)),
                "returnPierce" => JsonValue(ClampKnob(pair.Value, -1, 50, 0)),
                "localImmunityTicks" => JsonValue(ClampKnob(pair.Value, 0, 60, 0)),
                "arcDegrees" => JsonValue(ClampKnob(pair.Value, 10, 220, 110)),
                "windupTicks" => JsonValue(ClampKnob(pair.Value, 0, 90, 0)),
                "activeTicks" => JsonValue(ClampKnob(pair.Value, 1, 120, 12)),
                "recoveryTicks" => JsonValue(ClampKnob(pair.Value, 0, 120, 0)),
                "chargeTicks" => JsonValue(ClampKnob(pair.Value, 0, 300, 0)),
                "beamWidthPx" => JsonValue(ClampKnob(pair.Value, 2, 96, 18)),
                "maxActiveProjectiles" => JsonValue(ClampKnob(pair.Value, 0, 32, 1)),
                _ => pair.Value,
            };
        }
        OverrideKnobs = normalized;
        SupportStatus = Clean(SupportStatus, 48).ToLowerInvariant().Replace('-', '_');
        if (Family is "custom_executor" or "boomerang" or "yoyo" or "flail" or "whip" or "held_swing" or "held_thrust" or "channel_beam" or "charge_release" or "overhead_barrage" or "sentry") SupportStatus = "executable";
        if (Family is "yoyo" or "channel_beam" or "charge_release") Channelled = true;
        if (Family is "yoyo" or "flail" or "whip" or "held_thrust" or "channel_beam" or "charge_release") UsesHeldProjectile = true;
        if (string.IsNullOrWhiteSpace(SupportStatus)) SupportStatus = Family == "unsupported" ? "unsupported" : "preserved_intent";
        SupportNotes = (SupportNotes ?? new List<string>()).Where(x => !string.IsNullOrWhiteSpace(x)).Select(x => Clean(x, 160)).Distinct(StringComparer.OrdinalIgnoreCase).Take(16).ToList();
    }
}

public sealed class RuntimeContractSpec
{
    public string Schema { get; set; } = "infini.runtime-contract.v2";
    public string PrimaryVerb { get; set; } = "";
    public string ControlStyle { get; set; } = "";
    public List<string> MustFeelLike { get; set; } = new();
    public List<string> MustNotFeelLike { get; set; } = new();
    public List<string> StateFields { get; set; } = new();
    public List<string> SyncFields { get; set; } = new();
    public List<string> VisualStateFields { get; set; } = new();
    public List<string> PlayerViewTimeline { get; set; } = new();
    public List<MechanicClaimSpec> MechanicClaims { get; set; } = new();
    public List<string> UnsupportedPromises { get; set; } = new();
    public string ExecutionStatus { get; set; } = "";

    private static string Clean(string? value, int maxLen)
    {
        string s = value ?? "";
        if (s.Length > maxLen) s = s[..maxLen];
        return s.Replace('\0', ' ').Trim();
    }

    private static List<string> CleanList(List<string>? values, int maxItems, int maxLen)
        => (values ?? new List<string>()).Where(x => !string.IsNullOrWhiteSpace(x)).Select(x => Clean(x, maxLen)).Distinct(StringComparer.OrdinalIgnoreCase).Take(maxItems).ToList();

    public void Normalize()
    {
        Schema = "infini.runtime-contract.v2";
        PrimaryVerb = Clean(PrimaryVerb, 120);
        ControlStyle = Clean(ControlStyle, 48).ToLowerInvariant().Replace('_', '-');
        if (ControlStyle is not ("" or "tap" or "hold-to-channel" or "right-click-alt" or "combo" or "passive" or "on-hit-trigger")) ControlStyle = "";
        MustFeelLike = CleanList(MustFeelLike, 8, 80);
        MustNotFeelLike = CleanList(MustNotFeelLike, 8, 80);
        StateFields = CleanList(StateFields, 16, 48);
        SyncFields = CleanList(SyncFields, 16, 48);
        VisualStateFields = CleanList(VisualStateFields, 16, 48);
        PlayerViewTimeline = CleanList(PlayerViewTimeline, 8, 180);
        MechanicClaims = (MechanicClaims ?? new List<MechanicClaimSpec>()).Where(x => x is not null).Take(16).ToList();
        foreach (var claim in MechanicClaims) claim.Normalize();
        UnsupportedPromises = CleanList(UnsupportedPromises, 24, 120);
        ExecutionStatus = Clean(ExecutionStatus, 48).ToLowerInvariant().Replace('-', '_');
        if (ExecutionStatus is not ("" or "executable" or "partial" or "visual_only" or "unsupported")) ExecutionStatus = "";
    }
}

public sealed class MechanicClaimSpec
{
    public string Claim { get; set; } = "";
    public string Backing { get; set; } = "";
    public List<MechanicBackingRefSpec> BackingRefs { get; set; } = new();
    public string Status { get; set; } = "";

    private static string Clean(string? value, int maxLen)
    {
        string s = value ?? "";
        if (s.Length > maxLen) s = s[..maxLen];
        return s.Replace('\0', ' ').Trim();
    }

    public void Normalize()
    {
        Claim = Clean(Claim, 220);
        Backing = Clean(Backing, 160);
        BackingRefs = (BackingRefs ?? new List<MechanicBackingRefSpec>()).Where(x => x is not null).Take(12).ToList();
        foreach (var backingRef in BackingRefs) backingRef.Normalize();
        Status = Clean(Status, 48).ToLowerInvariant().Replace('-', '_');
        if (Status is not ("" or "executable" or "partial" or "visual_only" or "unsupported" or "ambiguous")) Status = "";
    }
}

public sealed class MechanicBackingRefSpec
{
    public string Source { get; set; } = "";
    public int CallIndex { get; set; } = -1;
    public string Fn { get; set; } = "";
    public string Field { get; set; } = "";
    public JsonElement Expected { get; set; }

    private static string Clean(string? value, int maxLen)
    {
        string s = value ?? "";
        if (s.Length > maxLen) s = s[..maxLen];
        return s.Replace('\0', ' ').Trim();
    }

    public void Normalize()
    {
        Source = Clean(Source, 32);
        if (Source is not ("compiledAttack" or "runtimeArchetype" or "engineCall")) Source = "";
        CallIndex = Source == "engineCall" ? Math.Max(-1, CallIndex) : -1;
        Fn = Source == "engineCall" ? Clean(Fn, 64).ToLowerInvariant() : "";
        Field = Clean(Field, 64);
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
        LightColorName = RuntimeColorPolicy.Normalize(LightColorName);
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
    public int UseStyle { get; set; } = ItemUseStyleID.Swing;
    public bool AutoReuse { get; set; } = true;
    public bool Consumable { get; set; } = false;
    public int ManaCost { get; set; } = 0;
    public int Rarity { get; set; } = ItemRarityID.White;
    public int Value { get; set; } = 100;
    public int MaxStack { get; set; } = 1;
    // v0.4.4: stack granted by one generated craft. Needed for LLM-authored ammo/material batches.
    public int CraftYield { get; set; } = 1;
    // v0.4.5: optional actual Terraria ammo type. Empty means consumable thrown/used stack, not bow/gun ammo.
    public string AmmoFor { get; set; } = "";
    public bool ChannelUse { get; set; } = false;
    public int ConsumeChancePercent { get; set; } = 100;
    public int Width { get; set; } = 24;
    public int Height { get; set; } = 24;
    public float ItemScale { get; set; } = 1f;
    public bool UseTurn { get; set; } = false;
    public int HoldoutOffsetX { get; set; } = 0;
    public int HoldoutOffsetY { get; set; } = 0;

    // Authored use/draw affordance fields with concrete runtime consumers.
    public string HeldVisibility { get; set; } = "";
    public string ReleaseTiming { get; set; } = "";
    public string HandPose { get; set; } = "";
    public int InitialOffsetPx { get; set; } = 0;

    public int HealLife { get; set; } = 0;
    public int HealMana { get; set; } = 0;
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

    // Explicit utility engineCalls. These are inert unless authored by runtimePlan.
    public string AltUseMode { get; set; } = ""; // mobility|generated_buff|light|none
    public string AltMobilityMode { get; set; } = "";
    public int AltMobilityRangeTiles { get; set; } = 0;
    public int AltMobilityCooldownTicks { get; set; } = 0;
    public bool AltMobilitySafeTileOnly { get; set; } = true;
    public GeneratedBuffSpec AltGeneratedBuff { get; set; } = new();
    public GeneratedBuffSpec HoldGeneratedBuff { get; set; } = new();
    public float HoldLightStrength { get; set; } = 0f;
    public string HoldLightColorName { get; set; } = "";
    public string UseConditionMode { get; set; } = ""; // none|grounded|not_wet|life_above|mana_above
    public int UseConditionMinLife { get; set; } = 0;
    public int UseConditionMinMana { get; set; } = 0;
    public RuntimeStateSpec RuntimeState { get; set; } = new();
    public RejectedEngineCallSpec[] RejectedEngineCalls { get; set; } = Array.Empty<RejectedEngineCallSpec>();
}

public sealed class RuntimeStateSpec
{
    public string ExecutionStatus { get; set; } = "";
    public StateMeterSpec[] StateMeters { get; set; } = Array.Empty<StateMeterSpec>();
    public TriggeredActionSpec[] TriggeredActions { get; set; } = Array.Empty<TriggeredActionSpec>();
}

public sealed class StateMeterSpec
{
    public string Id { get; set; } = "";
    public string Label { get; set; } = "";
    public int MaxValue { get; set; } = 3;
    public int InitialValue { get; set; } = 0;
    public int GainOnUse { get; set; } = 0;
    public int GainOnHit { get; set; } = 0;
    public int GainOnKill { get; set; } = 0;
    public int SpendOnUse { get; set; } = 0;
    public int SpendOnAltUse { get; set; } = 0;
    public float DecayPerSecond { get; set; } = 0f;
    public int CooldownTicks { get; set; } = 0;
    public int ModeCount { get; set; } = 0;
}

public sealed class TriggeredActionSpec
{
    public string Trigger { get; set; } = "";
    public string Action { get; set; } = "";
    public string MeterId { get; set; } = "";
    public int RequiredValue { get; set; } = 0;
    public int SpendValue { get; set; } = 0;
    public int CooldownTicks { get; set; } = 0;
    public string Note { get; set; } = "";
}

public sealed class RejectedEngineCallSpec
{
    public string Fn { get; set; } = "";
    public string Reason { get; set; } = "";
    public string Policy { get; set; } = "";
    public string Family { get; set; } = "";
    public string Action { get; set; } = "";
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
    public float LightStrength { get; set; } = 0f;
    public string LightColorName { get; set; } = "";
    public bool HasAnyEffect => Defense != 0 || MaxLife != 0 || MaxMana != 0 || LifeRegen != 0 || ManaRegen != 0
        || MovementSpeed != 0f || MaxRunSpeed != 0f || JumpSpeed != 0f
        || GenericDamage != 0f || MeleeDamage != 0f || RangedDamage != 0f || MagicDamage != 0f || SummonDamage != 0f
        || GenericCrit != 0f || AttackSpeed != 0f || Knockback != 0f
        || FallDamageImmune || LavaImmune || WaterWalk || MinionSlots != 0 || SentrySlots != 0
        || ManaCostReduction != 0f || AmmoSaveChance != 0f || Aggro != 0 || Endurance != 0f || ArmorPenetration != 0f
        || LightStrength != 0f;
}

public sealed class ArmorSpec
{
    public bool Enabled { get; set; } = false;
    public string Slot { get; set; } = "body"; // head, body, legs
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
    public float WhipRange { get; set; } = 0f; // future/debug; C# currently preserves but does not execute a custom whip range hook
    public float SummonTagDamage { get; set; } = 0f; // future/debug; generated whips/minions do not execute tag damage yet
    public float LightStrength { get; set; } = 0f;
    public string LightColorName { get; set; } = "";

    public string SetBonusText { get; set; } = "";
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
public sealed class AttackSpec
{
    // True only when this item has an authored generated runtime executor
    // (projectile / held generated attack / custom magic path). It does not mean
    // "can deal damage": tools and melee items may still hit through Terraria's
    // vanilla item hitbox using Gameplay.Damage.
    public bool Enabled { get; set; } = false;
    public string Delivery { get; set; } = "none"; // compatibility/use-style hint; RuntimeFamily is authoritative for execution
    public string RuntimeFamily { get; set; } = GeneratedRuntimeFamilyPolicy.None; // canonical values live in GeneratedRuntimeFamilyPolicy
    public string WeaponFamily { get; set; } = ""; // broadsword, spear, bow, gun, staff, flail, yoyo, whip, etc.
    public string ProjectileFamily { get; set; } = ""; // optional visual/projectile family emitted by authoring compiler
    public string AmmoKind { get; set; } = ""; // empty, arrow, bullet, rocket; advisory unless actual ammo output
    public int UseStyleCode { get; set; } = ItemUseStyleID.None; // explicit Terraria.ItemUseStyleID subset emitted by runtime compiler
    public bool HideUseGraphic { get; set; } = false; // explicit noUseGraphic affordance, not inferred from prose
    public bool DisableItemMeleeHitbox { get; set; } = false; // explicit noMelee affordance
    public bool OwnerHitCheck { get; set; } = false; // explicit held/owner-checked projectile affordance
    public bool ChannelUse { get; set; } = false; // explicit channelled use affordance for yoyo/beam-like generated weapons
    public string Stage { get; set; } = "early";
    public float PowerBudget { get; set; } = 1f;
    public string DamageClass { get; set; } = "generic"; // exact projectile damage class; shared resolver owns item/projectile mapping
    public string Movement { get; set; } = "straight"; // straight, slow_homing, gravity_arc, drift, boomerang, bounce, phase
    public string Effect { get; set; } = "dust"; // dust, electric, slime, star, flame, frost, leaf, shadow, poison, blood, honey, sand, lunar
    public string OnHit { get; set; } = "none"; // none, burst, split, chain, burn, frostburn, poison, shadowflame, starburst, bleed
    public int MovementCode { get; set; } = 0;
    public int EffectCode { get; set; } = 0;
    public int OnHitCode { get; set; } = 0;
    public float Speed { get; set; } = 8f;
    public float RangeTiles { get; set; } = 35f; // targeting range and exact held-beam reach
    public float HomingStrength { get; set; } = 0f; // explicit steering strength; 0 selects executor default
    public float BeamWidthPx { get; set; } = 14f; // used only by RuntimeFamily=beam
    public int BeamChargeTicks { get; set; } = 0; // bounded warmup before full beam power
    public int ChargeTicks { get; set; } = 45; // RuntimeFamily=charge_release full-charge duration
    public float ChargePowerMultiplier { get; set; } = 1.6f; // maximum released damage/knockback multiplier
    public int DelayTicks { get; set; } = 0; // overhead_barrage telegraph before bounded authored projectiles descend
    public int Lifetime { get; set; } = 90;
    public int Pierce { get; set; } = 1;
    public float Scale { get; set; } = 1f;
    public int ProjectileWidth { get; set; } = 14;
    public int ProjectileHeight { get; set; } = 14;
    public float ProjectileScale { get; set; } = 1f;
    public float HitboxScale { get; set; } = 1f;
    public int ExplosionRadius { get; set; } = 0; // compat/debug alias; runtime uses the split radii below
    public int ImpactVfxRadiusPx { get; set; } = 0;
    public int AoeDamageRadiusPx { get; set; } = 0;
    public int ContactForgivenessPx { get; set; } = 0;
    public int ExtraUpdates { get; set; } = 0;
    public bool TileCollide { get; set; } = true;
    public int BounceCount { get; set; } = 0;
    public int SplitCount { get; set; } = 0;
    public int ChainCount { get; set; } = 0;
    public float PullStrength { get; set; } = 0f;
    public string PullMode { get; set; } = "none";
    public int ImmunityCooldown { get; set; } = 10;
    public int TrailLength { get; set; } = 4;
    public int ShotCount { get; set; } = 1;
    public float SpreadRadians { get; set; } = 0f;
    public int ProcMode { get; set; } = 0; // 0 none, 1 proximity burst, 2 vortex spawn, 3 blackhole pull, 4 radial burst

    // v0.4.4: true when mechanics came from runtimePlan.engineCalls. In this mode
    // the projectile runtime must not parse prose to create gameplay child projectiles.
    public bool RuntimePlanAuthored { get; set; } = false;
    public string SecondaryTrigger { get; set; } = GeneratedSecondaryTriggerPolicy.OnHit;
    public float SecondarySpreadRadians { get; set; } = 0.45f;
    public float SecondaryDamageMultiplier { get; set; } = 0.35f;
    public int SecondaryLifetimeTicks { get; set; } = 24;
    public string SentryPlacement { get; set; } = "grounded";
    public int SentryAttackIntervalTicks { get; set; } = 45;
    public float SentryTargetRangeTiles { get; set; } = 30f;
    public int SentryLifetimeTicks { get; set; } = 3600;
    public float SameTargetBias { get; set; } = 0.0f;
    public string DebuffHint { get; set; } = "";
    public int DebuffTime { get; set; } = 0;
    public string SecondaryMaterial { get; set; } = "";
    public string SecondaryProjectileShape { get; set; } = "";

    // v2.10: Derived technical guardrails. These are not creative tags; they are engine-pressure limits.
    public int MaxChildProjectiles { get; set; } = 16;
    public int MaxChildDepth { get; set; } = 1;
    public int DustSpawnDenom { get; set; } = 3;
    public int BurstDustCap { get; set; } = 20;
    public Dictionary<string, float> EngineMetrics { get; set; } = new();

    // Presentation/audio layer. LLM may author exact catalog ids and bounded controls; server derives only safe fallbacks.
    public string VisualMode { get; set; } = "projectile"; // projectile, slash_arc, slash_plus_projectile, beam, falling_projectile, orbiting_projectile
    public string TrailStyle { get; set; } = "dust";
    public string ImpactStyle { get; set; } = "small_flash";
    public string PrimaryColorName { get; set; } = "white";
    public float RuntimeLightStrength { get; set; } = 0f;
    public string MobilityMode { get; set; } = "";
    public int MobilityRangeTiles { get; set; } = 0;
    public int MobilityCooldownTicks { get; set; } = 0;
    public bool MobilitySafeTileOnly { get; set; } = true;
    public float SoundPitch { get; set; } = 0f;
    public float SoundVolume { get; set; } = 0.85f;
    public float SoundPitchVariance { get; set; } = 0.18f;

    // Presentation/debug pattern only. Runtime behavior is selected by Delivery/WeaponFamily/MovementCode.
    public string Pattern { get; set; } = "basic";

    public string ProjectileShape { get; set; } = "";
    public string ProjectileMotion { get; set; } = "";
    public string ProjectileRotation { get; set; } = "";
    public string ProjectileTrail { get; set; } = "";
    public string ProjectileImpact { get; set; } = "";

    // Exact sound-catalog contract. "terraria_vanilla" ids resolve through the
    // built-in acoustic-role catalog; other sources remain available to the future
    // explicit asset catalog seam. Runtime never keyword-classifies names/tooltips.
    public string SoundCatalogSource { get; set; } = "";
    public string SoundUseCatalogId { get; set; } = "";
    public string SoundImpactCatalogId { get; set; } = "";
    public string SoundUseCatalogPath { get; set; } = "";
    public string SoundImpactCatalogPath { get; set; } = "";

    // v0.3.3 visual-model integration: separate generated assets for the flying
    // projectile and its impact flash. These are runtime PNG paths loaded by
    // RuntimeSpriteCache; if absent, GeneratedProjectile falls back to primitive drawing.
    public string ProjectileSpritePath { get; set; } = "";
    public string ProjectileSpriteUrl { get; set; } = "";
    public string ProjectileSpriteStatus { get; set; } = "";
    public string ProjectileSpritePrompt { get; set; } = "";
    public float ProjectileSpriteScore { get; set; } = 0f;
    public string ImpactSpritePath { get; set; } = "";
    public string ImpactSpriteUrl { get; set; } = "";
    public string ImpactSpriteStatus { get; set; } = "";
    public string ImpactSpritePrompt { get; set; } = "";
    public float ImpactSpriteScore { get; set; } = 0f;

    // v0.3.4: visual asset pack. Children/fields use their own sprites instead of
    // inheriting the main bolt, so a return spark, echo, trap or rune can be visible.
    public string ChildSpritePath { get; set; } = "";
    public string ChildSpriteUrl { get; set; } = "";
    public string ChildSpriteStatus { get; set; } = "";
    public string ChildSpritePrompt { get; set; } = "";
    public float ChildSpriteScore { get; set; } = 0f;
    public string FieldSpritePath { get; set; } = "";
    public string FieldSpriteUrl { get; set; } = "";
    public string FieldSpriteStatus { get; set; } = "";
    public string FieldSpritePrompt { get; set; } = "";
    public float FieldSpriteScore { get; set; } = 0f;
    public string VisualAnimationPlan { get; set; } = "";

    // v0.3.16 hybrid VFX manifest compiled by LocalGenerator once per generated item.
    // GeneratedProjectile executes this frozen data; it does not re-parse prompt prose every tick.
    public string VfxManifestJson { get; set; } = "";

    public AttackSpec CloneForRuntimeSpawn()
    {
        var clone = (AttackSpec)MemberwiseClone();
        clone.EngineMetrics = EngineMetrics is null ? new Dictionary<string, float>() : new Dictionary<string, float>(EngineMetrics);
        return clone;
    }
}


// =============================================================================
// NAV: VISUAL_AND_PRESENTATION_CONTRACT
// =============================================================================
public sealed class VisualSpec
{
    public string ObjectType { get; set; } = "generic_item";
    public string Style { get; set; } = "terraria_item_sprite";
    public string[] RequiredAnchors { get; set; } = Array.Empty<string>();
    public string[] Palette { get; set; } = Array.Empty<string>();
    public string ImagePrompt { get; set; } = "small pixel art item icon, solid magenta key background";
    public string ProjectileImagePrompt { get; set; } = "";
    public string ImpactImagePrompt { get; set; } = "";
    public string ChildImagePrompt { get; set; } = "";
    public string FieldImagePrompt { get; set; } = "";
    public string NegativePrompt { get; set; } = "scene, background, character, realistic render, blurry, text, watermark";
    public string AssetManifestPath { get; set; } = "";
    public string SpriteStatus { get; set; } = "placeholder"; // placeholder, prompt_only, generated, fallback, failed
    public string SpritePath { get; set; } = "";
    public string SpriteRawPath { get; set; } = "";
    public string SpriteUrl { get; set; } = "";
    public float PreservationScore { get; set; } = 0f;
    public float VisualJudgeScore { get; set; } = 0f;
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
    public string VisualSoulTooltip { get; set; } = "";
}


public sealed class PresentationGenomeSpec
{
    public string Schema { get; set; } = "presentationGenome.v1";
    public string[] Palette { get; set; } = Array.Empty<string>();
    public HeldSpriteSpec HeldSprite { get; set; } = new();
    public AttackVisualSpec AttackVisual { get; set; } = new();
    public ProjectileVisualSpec ProjectileVisual { get; set; } = new();
    public ImpactVisualSpec ImpactVisual { get; set; } = new();
    public TrailVisualSpec TrailVisual { get; set; } = new();
}

public sealed class HeldSpriteSpec
{
    public string Family { get; set; } = "generic";
    public string Silhouette { get; set; } = "generic_item";
    public string SizeClass { get; set; } = "medium";
    public string Accent { get; set; } = "white";
}

public sealed class AttackVisualSpec
{
    public string Mode { get; set; } = "projectile";
    public string Movement { get; set; } = "straight";
    public string Effect { get; set; } = "dust";
    public string OnHit { get; set; } = "none";
    public string ArcStyle { get; set; } = "none";
    public string Flash { get; set; } = "small_flash";
    public bool Glow { get; set; } = false;
}

public sealed class ProjectileVisualSpec
{
    public bool Enabled { get; set; } = false;
    public string Shape { get; set; } = "bolt";
    public string TrailStyle { get; set; } = "dust";
    public string Color { get; set; } = "white";
    public int Frames { get; set; } = 1;
}

public sealed class ImpactVisualSpec
{
    public string Style { get; set; } = "small_flash";
    public string Size { get; set; } = "small";
    public string Color { get; set; } = "white";
}

public sealed class TrailVisualSpec
{
    public string Style { get; set; } = "dust";
    public float Density { get; set; } = 0.25f;
    public string Color { get; set; } = "white";
}
