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
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

// AGENT MAP: inbound DTO normalization and safety clamps.
// Normalize ranges, sprite paths/status, runtime API support and future-field
// handling here. Do not silently convert unknown/prose fields into
// gameplay; unsupported data stays inert/debug-visible until runtime support exists.
public sealed partial class GeneratedItemData
{
    private static int ClampInt(int value, int min, int max) => Math.Min(max, Math.Max(min, value));
    private static float ClampFloat(float value, float min, float max) => MathF.Min(max, MathF.Max(min, value));
    private static string NormalizeSpriteStatus(string? raw)
    {
        string s = (raw ?? "").Trim().ToLowerInvariant();
        return s switch
        {
            "generated" or "generated_warn_invalid" or "prompt_only" or "failed" or "placeholder" or "fallback" or "fallback_after_failed_generation" => s,
            _ => string.IsNullOrWhiteSpace(s) ? "" : s
        };
    }

    private static bool SpriteStatusAllowsRuntimePath(string? status)
    {
        string s = NormalizeSpriteStatus(status);
        return !string.IsNullOrWhiteSpace(s) && s is not ("failed" or "prompt_only" or "placeholder" or "generated_warn_invalid");
    }

    private static string NormalizeSpritePathForStatus(string? path, string? status)
    {
        string s = NormalizeSpriteStatus(status);
        if (s is "failed" or "prompt_only" or "placeholder") return "";
        path = (path ?? "").Trim();
        if (path.Length > 400) return "";
        if (!path.EndsWith(".png", StringComparison.OrdinalIgnoreCase) && !path.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) return "";
        return path;
    }

    private static string ConventionalAssetFileName(string id, string suffix)
    {
        id = SafeText(id, 96).Trim();
        if (string.IsNullOrWhiteSpace(id)) return "";
        foreach (char c in id)
        {
            if (!(char.IsLetterOrDigit(c) || c == '_' || c == '-' || c == '.')) return "";
        }
        return string.IsNullOrWhiteSpace(suffix) ? id + ".png" : id + suffix + ".png";
    }

    private static BuffEntrySpec[] NormalizeExtraBuffs(BuffEntrySpec[]? source, int primaryBuffCode, int primaryBuffTime)
    {
        var outList = new List<BuffEntrySpec>();
        void Add(int code, int time)
        {
            time = ClampInt(time, 0, 21600);
            if (code <= InfiniTerrariaSentinels.NoBuffType || code >= BuffLoader.BuffCount || time <= 0) return;
            int idx = outList.FindIndex(x => x.BuffCode == code);
            if (idx >= 0)
            {
                if (time > outList[idx].BuffTime) outList[idx].BuffTime = time;
                return;
            }
            if (outList.Count < 4) outList.Add(new BuffEntrySpec { BuffCode = code, BuffTime = time });
        }
        Add(primaryBuffCode, primaryBuffTime);
        if (source is not null)
        {
            foreach (var buff in source)
                if (buff is not null) Add(buff.BuffCode, buff.BuffTime);
        }
        return outList.ToArray();
    }
    private static string NormalizeRuntimeApiVersion(string? value)
    {
        string s = SafeText(value, 32).Trim();
        return s;
    }

    private static string SafeText(string? value, int maxLen)
    {
        string s = value ?? "";
        if (s.Length > maxLen) s = s[..maxLen];
        return s.Replace('\0', ' ').Trim();
    }

    private static string NormalizeHexColor(string? value, string fallback = "#ffffff")
    {
        string s = SafeText(value, 16).Trim();
        if (string.IsNullOrWhiteSpace(s)) return fallback;
        if (!s.StartsWith("#", StringComparison.Ordinal)) s = "#" + s;
        if (s.Length != 7) return fallback;
        for (int i = 1; i < s.Length; i++)
        {
            char c = s[i];
            bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
            if (!ok) return fallback;
        }
        return s.ToLowerInvariant();
    }

    private static string[] SafeTextArray(string[]? values, int maxItems = 32, int maxLen = 64)
    {
        if (values is null || values.Length <= 0) return Array.Empty<string>();
        var list = new List<string>();
        foreach (string raw in values)
        {
            string s = SafeText(raw, maxLen);
            if (!string.IsNullOrWhiteSpace(s)) list.Add(s);
            if (list.Count >= maxItems) break;
        }
        return list.ToArray();
    }

    private static bool RuntimeApiSupported(string? value)
    {
        string s = NormalizeRuntimeApiVersion(value);
        return SupportedRuntimeApiVersions.Contains(s);
    }

    private static bool IsRuntimeFamily(string? value)
        => GeneratedRuntimeFamilyPolicy.IsCanonical(value);

    private static string NormalizeRuntimeFamily(string? value)
        => GeneratedRuntimeFamilyPolicy.Normalize(value);

    private static string NormalizePullMode(string? value, float pullStrength)
    {
        if (pullStrength <= 0f) return "none";
        string mode = SafeText(value, 24).ToLowerInvariant();
        return mode is "target_to_owner" or "owner_to_target" or "target_to_projectile" ? mode : "none";
    }

    private static string NormalizeArmorSlot(string? value)
    {
        string s = (value ?? "").Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "_");
        return s switch
        {
            "helmet" or "helm" or "hat" or "hood" or "mask" or "head" => "head",
            "chest" or "chestplate" or "breastplate" or "body" or "shirt" or "robe" or "torso" => "body",
            "legs" or "leggings" or "greaves" or "pants" or "boots" or "leg" => "legs",
            _ => ""
        };
    }

    private static bool RuntimeAttackContractSupported(AttackSpec? attack, string? runtimeApiVersion = null)
    {
        if (attack is null || !attack.Enabled) return true;
        if (!attack.RuntimePlanAuthored) return false;
        if (!IsRuntimeFamily(attack.RuntimeFamily)) return false;
        return attack.MovementCode >= 0 && attack.MovementCode <= MaxSupportedMovementCode
            && attack.EffectCode >= 0 && attack.EffectCode <= MaxSupportedEffectCode
            && attack.OnHitCode >= 0 && attack.OnHitCode <= MaxSupportedOnHitCode
            && attack.UseStyleCode >= ItemUseStyleID.None && attack.UseStyleCode <= InfiniTerrariaSentinels.MaxSupportedItemUseStyle;
    }

    private static GeneratedItemData MarkUnsupportedRuntimeAttack(GeneratedItemData data)
    {
        data.SourceMode = "failed";
        data.Tooltip = data.Attack is null || data.Attack.RuntimePlanAuthored
            ? $"Unsupported generated runtime opcode; update the mod/generator pair."
            : "Generated attack runtime is missing the current authored contract; regenerate this item.";
        if (data.Attack is not null)
            data.Attack.Enabled = false;
        if (data.Gameplay is not null)
            data.Gameplay.Damage = 0;
        return data;
    }


    public void Normalize()
    {
        RuntimeApiVersion = NormalizeRuntimeApiVersion(RuntimeApiVersion);
        Id = string.IsNullOrWhiteSpace(Id) ? Guid.NewGuid().ToString("N")[..12] : SafeText(Id, 64);
        RecipeKey = SafeText(RecipeKey, 80);
        Name = string.IsNullOrWhiteSpace(Name) ? "Generated Item" : SafeText(Name, 80);
        ParentA = string.IsNullOrWhiteSpace(ParentA) ? "Unknown" : SafeText(ParentA, 80);
        ParentB = string.IsNullOrWhiteSpace(ParentB) ? "Unknown" : SafeText(ParentB, 80);
        Tooltip = SafeText(Tooltip, 240);
        MergeMode = string.IsNullOrWhiteSpace(MergeMode) ? "literal" : SafeText(MergeMode, 32);
        Category = string.IsNullOrWhiteSpace(Category) ? "generic" : SafeText(Category, 32);
        SourceMode = string.IsNullOrWhiteSpace(SourceMode) ? "generated" : SafeText(SourceMode, 32);
        Tags = SafeTextArray(Tags, 32, 48);
        Canonical ??= new CanonicalSpec();
        SourceRepresentation ??= Array.Empty<SourceRepresentationSpec>();
        Inheritance ??= Array.Empty<InheritanceSpec>();
        LossBudget ??= new LossBudgetSpec();
        RecipeMeta ??= new RecipeMetaSpec();
        ItemKnowledge ??= new ItemKnowledgeSpec();
        GeneratedParentSummary ??= new GeneratedParentSummarySpec();
        GeneratedParentSummary.Normalize();
        Gameplay ??= new GameplaySpec();
        Accessory ??= new AccessorySpec();
        Armor ??= new ArmorSpec();
        Attack ??= new AttackSpec();
        Visual ??= new VisualSpec();
        PresentationGenome ??= new PresentationGenomeSpec();
        VfxManifest ??= new VfxManifestSpec();
        VfxManifest.Normalize();
        RuntimeArchetype ??= new RuntimeArchetypeSpec();
        RuntimeArchetype.Normalize();
        RuntimeContract ??= new RuntimeContractSpec();
        RuntimeContract.Normalize();
        Debug ??= new Dictionary<string, JsonElement>();
        ExtensionData ??= new Dictionary<string, JsonElement>();
        NormalizeGameplayVisualAndAttackRanges();
    }


    private void NormalizeGameplayVisualAndAttackRanges()
    {
        // Runtime item hitboxes should stay in Terraria-sized ranges.  The PNG canvas
        // may be 48/64 for readability, but the gameplay/world item box must not
        // recursively grow into huge 128-256px objects from generated-parent chains.
        Gameplay.Width = ClampInt(Gameplay.Width, 8, 64);
        Gameplay.Height = ClampInt(Gameplay.Height, 8, 64);
        Gameplay.UseTime = ClampInt(Gameplay.UseTime, 10, 3600);
        Gameplay.UseAnimation = ClampInt(Gameplay.UseAnimation, 6, 3600);
        Gameplay.MaxStack = ClampInt(Gameplay.MaxStack, 1, 9999);
        Gameplay.CraftYield = ClampInt(Gameplay.CraftYield, 1, 9999);
        Gameplay.ItemScale = ClampFloat(Gameplay.ItemScale, 0.55f, 1.55f);
        Gameplay.HoldoutOffsetX = ClampInt(Gameplay.HoldoutOffsetX, -256, 256);
        Gameplay.HoldoutOffsetY = ClampInt(Gameplay.HoldoutOffsetY, -256, 256);
        Gameplay.HeldVisibility = SafeText(Gameplay.HeldVisibility, 32);
        Gameplay.ReleaseTiming = SafeText(Gameplay.ReleaseTiming, 32);
        Gameplay.HandPose = SafeText(Gameplay.HandPose, 32);
        Gameplay.InitialOffsetPx = ClampInt(Gameplay.InitialOffsetPx, -64, 64);
        Gameplay.ConsumeChancePercent = ClampInt(Gameplay.ConsumeChancePercent <= 0 ? Gameplay.ConsumeChancePercent : Gameplay.ConsumeChancePercent, 0, 100);
        Gameplay.ManaCost = ClampInt(Gameplay.ManaCost, 0, 9999);
        Gameplay.HealLife = ClampInt(Gameplay.HealLife, 0, 500);
        Gameplay.HealMana = ClampInt(Gameplay.HealMana, 0, 500);
        Gameplay.BuffCode = Gameplay.BuffCode > InfiniTerrariaSentinels.NoBuffType && Gameplay.BuffCode < BuffLoader.BuffCount
            ? Gameplay.BuffCode
            : InfiniTerrariaSentinels.NoBuffType;
        Gameplay.BuffTime = ClampInt(Gameplay.BuffTime, 0, 21600);
        Gameplay.ExtraBuffs = NormalizeExtraBuffs(Gameplay.ExtraBuffs, Gameplay.BuffCode, Gameplay.BuffTime);
        Gameplay.GeneratedBuff ??= new GeneratedBuffSpec();
        Gameplay.GeneratedBuff.Normalize();
        if (Gameplay.BuffCode <= InfiniTerrariaSentinels.NoBuffType && Gameplay.ExtraBuffs.Length > 0)
        {
            Gameplay.BuffCode = Gameplay.ExtraBuffs[0].BuffCode;
            Gameplay.BuffTime = Gameplay.ExtraBuffs[0].BuffTime;
        }
        Gameplay.PickPower = ClampInt(Gameplay.PickPower, 0, 1000);
        Gameplay.AxePower = ClampInt(Gameplay.AxePower, 0, 200);
        Gameplay.HammerPower = ClampInt(Gameplay.HammerPower, 0, 1000);
        Gameplay.MobilityMode = SafeText(Gameplay.MobilityMode, 32);
        Gameplay.MobilityRangeTiles = ClampInt(Gameplay.MobilityRangeTiles, 0, 80);
        Gameplay.MobilityCooldownTicks = ClampInt(Gameplay.MobilityCooldownTicks, 0, 36000);
        Gameplay.MiningSpeedScale = ClampFloat(Gameplay.MiningSpeedScale, 0.25f, 2f);
        Gameplay.AltUseMode = SafeText(Gameplay.AltUseMode, 32);
        Gameplay.AltMobilityMode = SafeText(Gameplay.AltMobilityMode, 32);
        Gameplay.AltMobilityRangeTiles = ClampInt(Gameplay.AltMobilityRangeTiles, 0, 80);
        Gameplay.AltMobilityCooldownTicks = ClampInt(Gameplay.AltMobilityCooldownTicks, 0, 36000);
        // Held light is passive; alternate use remains explicit AltUseMode only.
        Gameplay.HoldLightStrength = ClampFloat(Gameplay.HoldLightStrength, 0f, 1.5f);
        Gameplay.HoldLightColorName = RuntimeColorPolicy.Normalize(Gameplay.HoldLightColorName);
        Gameplay.AltGeneratedBuff ??= new GeneratedBuffSpec();
        Gameplay.AltGeneratedBuff.Normalize();
        Gameplay.HoldGeneratedBuff ??= new GeneratedBuffSpec();
        Gameplay.HoldGeneratedBuff.Normalize();
        Gameplay.ExtractinatorOutputItemType = Gameplay.ExtractinatorOutputItemType > 0 && Gameplay.ExtractinatorOutputItemType < ItemLoader.ItemCount
            ? Gameplay.ExtractinatorOutputItemType
            : 0;
        Gameplay.ExtractinatorOutputStack = ClampInt(Gameplay.ExtractinatorOutputStack, 0, 999);
        Gameplay.UseConditionMode = SafeText(Gameplay.UseConditionMode, 32).Trim().ToLowerInvariant();
        if (Gameplay.UseConditionMode is not ("" or "none" or "grounded" or "not_wet" or "life_above" or "mana_above"))
            Gameplay.UseConditionMode = "";
        Gameplay.UseConditionMinLife = ClampInt(Gameplay.UseConditionMinLife, 0, 5000);
        Gameplay.UseConditionMinMana = ClampInt(Gameplay.UseConditionMinMana, 0, 5000);
        Gameplay.RuntimeState ??= new RuntimeStateSpec();
        Gameplay.RuntimeState.ExecutionStatus = SafeText(Gameplay.RuntimeState.ExecutionStatus, 64);
        Gameplay.RuntimeState.StateMeters = (Gameplay.RuntimeState.StateMeters ?? Array.Empty<StateMeterSpec>())
            .Where(x => x is not null)
            .Take(4)
            .Select(x => new StateMeterSpec
            {
                Id = SafeText(x.Id, 32),
                Label = SafeText(x.Label, 48),
                MaxValue = ClampInt(x.MaxValue, 1, 20),
                InitialValue = ClampInt(x.InitialValue, 0, 20),
                GainOnUse = ClampInt(x.GainOnUse, 0, 20),
                GainOnHit = ClampInt(x.GainOnHit, 0, 20),
                GainOnKill = ClampInt(x.GainOnKill, 0, 20),
                SpendOnUse = ClampInt(x.SpendOnUse, 0, 20),
                SpendOnAltUse = ClampInt(x.SpendOnAltUse, 0, 20),
                DecayPerSecond = ClampFloat(x.DecayPerSecond, 0f, 20f),
                CooldownTicks = ClampInt(x.CooldownTicks, 0, 3600),
                ModeCount = ClampInt(x.ModeCount, 0, 8),
            })
            .ToArray();
        foreach (var meter in Gameplay.RuntimeState.StateMeters)
        {
            if (string.IsNullOrWhiteSpace(meter.Id)) meter.Id = "meter";
            if (meter.InitialValue > meter.MaxValue) meter.InitialValue = meter.MaxValue;
        }
        Gameplay.RuntimeState.TriggeredActions = (Gameplay.RuntimeState.TriggeredActions ?? Array.Empty<TriggeredActionSpec>())
            .Where(x => x is not null)
            .Take(8)
            .Select(x => new TriggeredActionSpec
            {
                Trigger = SafeText(x.Trigger, 32),
                Action = SafeText(x.Action, 32),
                MeterId = SafeText(x.MeterId, 32),
                RequiredValue = ClampInt(x.RequiredValue, 0, 20),
                SpendValue = ClampInt(x.SpendValue, 0, 20),
                CooldownTicks = ClampInt(x.CooldownTicks, 0, 3600),
                Note = SafeText(x.Note, 80),
            })
            .ToArray();
        Gameplay.RejectedEngineCalls = (Gameplay.RejectedEngineCalls ?? Array.Empty<RejectedEngineCallSpec>())
            .Where(x => x is not null)
            .Take(16)
            .Select(x => new RejectedEngineCallSpec
            {
                Fn = SafeText(x.Fn, 48),
                Reason = SafeText(x.Reason, 80),
                Policy = SafeText(x.Policy, 96),
                Family = SafeText(x.Family, 48),
                Action = SafeText(x.Action, 48),
            })
            .ToArray();

        Accessory.Defense = ClampInt(Accessory.Defense, 0, 999);
        Accessory.MaxLife = ClampInt(Accessory.MaxLife, 0, 5000);
        Accessory.MaxMana = ClampInt(Accessory.MaxMana, 0, 5000);
        Accessory.LifeRegen = ClampInt(Accessory.LifeRegen, 0, 999);
        Accessory.ManaRegen = ClampInt(Accessory.ManaRegen, 0, 999);
        Accessory.MovementSpeed = ClampFloat(Accessory.MovementSpeed, 0f, 10f);
        Accessory.MaxRunSpeed = ClampFloat(Accessory.MaxRunSpeed, 0f, 200f);
        Accessory.JumpSpeed = ClampFloat(Accessory.JumpSpeed, 0f, 200f);
        Accessory.GenericDamage = ClampFloat(Accessory.GenericDamage, 0f, 10f);
        Accessory.MeleeDamage = ClampFloat(Accessory.MeleeDamage, 0f, 10f);
        Accessory.RangedDamage = ClampFloat(Accessory.RangedDamage, 0f, 10f);
        Accessory.MagicDamage = ClampFloat(Accessory.MagicDamage, 0f, 10f);
        Accessory.SummonDamage = ClampFloat(Accessory.SummonDamage, 0f, 10f);
        Accessory.GenericCrit = ClampFloat(Accessory.GenericCrit, 0f, 1000f);
        Accessory.AttackSpeed = ClampFloat(Accessory.AttackSpeed, 0f, 10f);
        Accessory.Knockback = ClampFloat(Accessory.Knockback, 0f, 100f);
        Accessory.MinionSlots = ClampInt(Accessory.MinionSlots, 0, 200);
        Accessory.SentrySlots = ClampInt(Accessory.SentrySlots, 0, 5);
        Accessory.ManaCostReduction = ClampFloat(Accessory.ManaCostReduction, 0f, 0.8f);
        Accessory.AmmoSaveChance = ClampFloat(Accessory.AmmoSaveChance, 0f, 0.75f);
        Accessory.Aggro = ClampInt(Accessory.Aggro, -2000, 2000);
        Accessory.Endurance = ClampFloat(Accessory.Endurance, 0f, 0.35f);
        Accessory.ArmorPenetration = ClampFloat(Accessory.ArmorPenetration, 0f, 80f);
        Accessory.LightStrength = ClampFloat(Accessory.LightStrength, 0f, 1.5f);
        Accessory.LightColorName = RuntimeColorPolicy.Normalize(Accessory.LightColorName);
        Accessory.Archetype = SafeText(Accessory.Archetype, 32);
        if (!Accessory.Enabled && Accessory.HasAnyEffect && (Category == "accessory" || Gameplay.Kind == "accessory"))
            Accessory.Enabled = true;

        Armor.Enabled = Armor.Enabled || Category == "armor" || Gameplay.Kind == "armor";
        Armor.Slot = NormalizeArmorSlot(Armor.Slot);
        Armor.SetKey = SafeText(Armor.SetKey, 64);
        Armor.Archetype = SafeText(Armor.Archetype, 32);
        Armor.Defense = ClampInt(Armor.Defense, 0, 80);
        Armor.MaxLife = ClampInt(Armor.MaxLife, 0, 500);
        Armor.MaxMana = ClampInt(Armor.MaxMana, 0, 500);
        Armor.LifeRegen = ClampInt(Armor.LifeRegen, 0, 120);
        Armor.ManaRegen = ClampInt(Armor.ManaRegen, 0, 120);
        Armor.MovementSpeed = ClampFloat(Armor.MovementSpeed, 0f, 2f);
        Armor.MaxRunSpeed = ClampFloat(Armor.MaxRunSpeed, 0f, 4f);
        Armor.JumpSpeed = ClampFloat(Armor.JumpSpeed, 0f, 8f);
        Armor.GenericDamage = ClampFloat(Armor.GenericDamage, 0f, 1f);
        Armor.MeleeDamage = ClampFloat(Armor.MeleeDamage, 0f, 1f);
        Armor.RangedDamage = ClampFloat(Armor.RangedDamage, 0f, 1f);
        Armor.MagicDamage = ClampFloat(Armor.MagicDamage, 0f, 1f);
        Armor.SummonDamage = ClampFloat(Armor.SummonDamage, 0f, 1f);
        Armor.GenericCrit = ClampFloat(Armor.GenericCrit, 0f, 100f);
        Armor.AttackSpeed = ClampFloat(Armor.AttackSpeed, 0f, 1f);
        Armor.Knockback = ClampFloat(Armor.Knockback, 0f, 5f);
        Armor.MinionSlots = ClampInt(Armor.MinionSlots, 0, 10);
        Armor.SentrySlots = ClampInt(Armor.SentrySlots, 0, 5);
        Armor.ManaCostReduction = ClampFloat(Armor.ManaCostReduction, 0f, 0.8f);
        Armor.AmmoSaveChance = ClampFloat(Armor.AmmoSaveChance, 0f, 0.75f);
        Armor.Aggro = ClampInt(Armor.Aggro, -1200, 1200);
        Armor.Endurance = ClampFloat(Armor.Endurance, 0f, 0.35f);
        Armor.ArmorPenetration = ClampFloat(Armor.ArmorPenetration, 0f, 80f);
        Armor.WhipRange = ClampFloat(Armor.WhipRange, 0f, 1.5f);
        Armor.SummonTagDamage = ClampFloat(Armor.SummonTagDamage, 0f, 0.75f);
        Armor.LightStrength = ClampFloat(Armor.LightStrength, 0f, 1.5f);
        Armor.LightColorName = RuntimeColorPolicy.Normalize(Armor.LightColorName);
        Armor.SetBonusText = SafeText(Armor.SetBonusText, 120);
        Armor.SetBonusGenericDamage = ClampFloat(Armor.SetBonusGenericDamage, 0f, 1f);
        Armor.SetBonusMeleeDamage = ClampFloat(Armor.SetBonusMeleeDamage, 0f, 1f);
        Armor.SetBonusRangedDamage = ClampFloat(Armor.SetBonusRangedDamage, 0f, 1f);
        Armor.SetBonusMagicDamage = ClampFloat(Armor.SetBonusMagicDamage, 0f, 1f);
        Armor.SetBonusSummonDamage = ClampFloat(Armor.SetBonusSummonDamage, 0f, 1f);
        Armor.SetBonusGenericCrit = ClampFloat(Armor.SetBonusGenericCrit, 0f, 100f);
        Armor.SetBonusMovementSpeed = ClampFloat(Armor.SetBonusMovementSpeed, 0f, 2f);
        Armor.SetBonusLifeRegen = ClampInt(Armor.SetBonusLifeRegen, 0, 120);
        Armor.SetBonusManaRegen = ClampInt(Armor.SetBonusManaRegen, 0, 120);
        Armor.SetBonusMinionSlots = ClampInt(Armor.SetBonusMinionSlots, 0, 10);
        Armor.SetBonusSentrySlots = ClampInt(Armor.SetBonusSentrySlots, 0, 5);
        Armor.SetBonusManaCostReduction = ClampFloat(Armor.SetBonusManaCostReduction, 0f, 0.8f);
        Armor.SetBonusAmmoSaveChance = ClampFloat(Armor.SetBonusAmmoSaveChance, 0f, 0.75f);
        Armor.SetBonusAggro = ClampInt(Armor.SetBonusAggro, -1200, 1200);
        Armor.SetBonusEndurance = ClampFloat(Armor.SetBonusEndurance, 0f, 0.35f);
        Armor.SetBonusArmorPenetration = ClampFloat(Armor.SetBonusArmorPenetration, 0f, 80f);

        Attack.Speed = ClampFloat(Attack.Speed, 0f, 250f);
        Attack.RangeTiles = ClampFloat(Attack.RangeTiles, 4f, 120f);
        Attack.HomingStrength = ClampFloat(Attack.HomingStrength, 0f, 1f);
        Attack.BeamWidthPx = ClampFloat(Attack.BeamWidthPx, 2f, 96f);
        Attack.BeamChargeTicks = ClampInt(Attack.BeamChargeTicks, 0, 300);
        Attack.ChargeTicks = ClampInt(Attack.ChargeTicks, 1, 300);
        Attack.ChargePowerMultiplier = ClampFloat(Attack.ChargePowerMultiplier, 1f, 3f);
        Attack.DelayTicks = ClampInt(Attack.DelayTicks, 0, 300);
        Attack.Lifetime = ClampInt(Attack.Lifetime, 1, 36000);
        Attack.Pierce = ClampInt(Attack.Pierce, -1, 9999);
        Attack.Scale = ClampFloat(Attack.Scale, 0.25f, 2.5f);
        Attack.ProjectileWidth = ClampInt(Attack.ProjectileWidth, 4, 96);
        Attack.ProjectileHeight = ClampInt(Attack.ProjectileHeight, 4, 96);
        Attack.ProjectileScale = ClampFloat(Attack.ProjectileScale, 0.35f, 2.25f);
        Attack.HitboxScale = ClampFloat(Attack.HitboxScale, 0.5f, 2.5f);
        Attack.ExplosionRadius = ClampInt(Attack.ExplosionRadius, 0, 128);
        Attack.ImpactVfxRadiusPx = ClampInt(Attack.ImpactVfxRadiusPx, 0, 192);
        Attack.AoeDamageRadiusPx = ClampInt(Attack.AoeDamageRadiusPx, 0, 160);
        Attack.ContactForgivenessPx = ClampInt(Attack.ContactForgivenessPx, 0, 32);
        Attack.ExtraUpdates = ClampInt(Attack.ExtraUpdates, 0, 240);
        Attack.BounceCount = ClampInt(Attack.BounceCount, 0, 128);
        Attack.SplitCount = ClampInt(Attack.SplitCount, 0, 128);
        Attack.ChainCount = ClampInt(Attack.ChainCount, 0, 128);
        Attack.PullStrength = ClampFloat(Attack.PullStrength, 0f, 1f);
        Attack.PullMode = NormalizePullMode(Attack.PullMode, Attack.PullStrength);
        if (Attack.PullMode == "none") Attack.PullStrength = 0f;
        Attack.ImmunityCooldown = ClampInt(Attack.ImmunityCooldown, 0, 600);
        Attack.TrailLength = ClampInt(Attack.TrailLength, 0, 600);
        Attack.ShotCount = ClampInt(Attack.ShotCount, 1, 128);
        Attack.SpreadRadians = ClampFloat(Attack.SpreadRadians, 0f, 6.4f);
        Attack.SecondaryTrigger = GeneratedSecondaryTriggerPolicy.NormalizeForRuntimeFamily(Attack.SecondaryTrigger, Attack.RuntimeFamily);
        Attack.SecondarySpreadRadians = ClampFloat(Attack.SecondarySpreadRadians, 0f, 6.4f);
        Attack.SecondaryDamageMultiplier = ClampFloat(Attack.SecondaryDamageMultiplier, 0f, 10f);
        Attack.SecondaryLifetimeTicks = ClampInt(Attack.SecondaryLifetimeTicks, 1, 36000);
        Attack.SentryPlacement = SafeText(Attack.SentryPlacement, 16);
        Attack.SentryAttackIntervalTicks = ClampInt(Attack.SentryAttackIntervalTicks, 12, 180);
        Attack.SentryTargetRangeTiles = ClampFloat(Attack.SentryTargetRangeTiles, 8f, 60f);
        Attack.SentryLifetimeTicks = ClampInt(Attack.SentryLifetimeTicks, 120, 36000);
        Attack.SameTargetBias = ClampFloat(Attack.SameTargetBias, 0f, 1f);
        Attack.MaxChildProjectiles = ClampInt(Attack.MaxChildProjectiles, 0, 512);
        Attack.MaxChildDepth = ClampInt(Attack.MaxChildDepth, 0, 16);
        Attack.DustSpawnDenom = Attack.DustSpawnDenom <= 0 ? 0 : ClampInt(Attack.DustSpawnDenom, 2, 240);
        Attack.BurstDustCap = ClampInt(Attack.BurstDustCap, 0, 2000);
        Attack.RuntimeLightStrength = ClampFloat(Attack.RuntimeLightStrength, 0f, 2f);
        Attack.MobilityMode = SafeText(Attack.MobilityMode, 32);
        Attack.MobilityRangeTiles = ClampInt(Attack.MobilityRangeTiles, 0, 80);
        Attack.MobilityCooldownTicks = ClampInt(Attack.MobilityCooldownTicks, 0, 36000);
        Attack.SoundVolume = ClampFloat(Attack.SoundVolume, 0.05f, 1f);
        Attack.SoundPitch = ClampFloat(Attack.SoundPitch, -0.9f, 0.9f);
        Attack.SoundPitchVariance = ClampFloat(Attack.SoundPitchVariance, 0f, 0.6f);
        Attack.DamageClass = SafeText(Attack.DamageClass, 96);
        if (string.IsNullOrWhiteSpace(Attack.DamageClass)) Attack.DamageClass = "generic";
        Attack.UseStyleCode = ClampInt(Attack.UseStyleCode, ItemUseStyleID.None, InfiniTerrariaSentinels.MaxSupportedItemUseStyle);
        Attack.RuntimeFamily = NormalizeRuntimeFamily(Attack.RuntimeFamily);
        if (!GeneratedRuntimeFamilyPolicy.HasValidExecutorContract(Attack))
        {
            Attack.RuntimeFamily = GeneratedRuntimeFamilyPolicy.None;
            Attack.Enabled = false;
        }
        Attack.SoundCatalogSource = SafeText(Attack.SoundCatalogSource, 48);
        Attack.SoundUseCatalogId = SafeText(Attack.SoundUseCatalogId, 64);
        Attack.SoundImpactCatalogId = SafeText(Attack.SoundImpactCatalogId, 64);
        Attack.SoundUseCatalogPath = SafeText(Attack.SoundUseCatalogPath, 240);
        Attack.SoundImpactCatalogPath = SafeText(Attack.SoundImpactCatalogPath, 240);
        Attack.PrimaryColorName = RuntimeColorPolicy.Normalize(Attack.PrimaryColorName, "white");

        Visual.PreferredCanvasSize = Visual.PreferredCanvasSize <= 20 ? 16 : Visual.PreferredCanvasSize <= 28 ? 24 : Visual.PreferredCanvasSize <= 40 ? 32 : Visual.PreferredCanvasSize <= 56 ? 48 : Visual.PreferredCanvasSize <= 80 ? 64 : Visual.PreferredCanvasSize <= 112 ? 96 : 128;
        Visual.InventoryScale = ClampFloat(Visual.InventoryScale, 0.55f, 1.55f);
        Visual.WorldScale = ClampFloat(Visual.WorldScale, 0.55f, 1.75f);
        Visual.DrawOffsetX = ClampInt(Visual.DrawOffsetX, -256, 256);
        Visual.DrawOffsetY = ClampInt(Visual.DrawOffsetY, -256, 256);
        Visual.VisualSoulSignature = SafeText(Visual.VisualSoulSignature, 32);
        Visual.VisualSoulArchetype = SafeText(Visual.VisualSoulArchetype, 32);
        Visual.DominantColorHex = NormalizeHexColor(Visual.DominantColorHex, "#ffffff");
        Visual.AccentColorHex = NormalizeHexColor(Visual.AccentColorHex, Visual.DominantColorHex);
        Visual.VisualSoulGlow = ClampFloat(Visual.VisualSoulGlow, 0f, 1f);
        Visual.VisualSoulPulse = ClampFloat(Visual.VisualSoulPulse, 0f, 1f);
        Visual.VisualSoulCoverage = ClampFloat(Visual.VisualSoulCoverage, 0f, 1f);
        Visual.VisualSoulEdgeDensity = ClampFloat(Visual.VisualSoulEdgeDensity, 0f, 1f);
        Visual.VisualSoulTooltip = SafeText(Visual.VisualSoulTooltip, 120);
        Visual.SpriteStatus = NormalizeSpriteStatus(Visual.SpriteStatus);
        Visual.SpritePath = NormalizeSpritePathForStatus(Visual.SpritePath, Visual.SpriteStatus);
        Visual.SpriteRawPath = NormalizeSpritePathForStatus(Visual.SpriteRawPath, Visual.SpriteStatus);
        if (string.IsNullOrWhiteSpace(Visual.SpritePath) && SpriteStatusAllowsRuntimePath(Visual.SpriteStatus))
            Visual.SpritePath = ConventionalAssetFileName(Id, "");
        Attack.ProjectileSpriteStatus = NormalizeSpriteStatus(Attack.ProjectileSpriteStatus);
        Attack.ProjectileSpritePath = NormalizeSpritePathForStatus(Attack.ProjectileSpritePath, Attack.ProjectileSpriteStatus);
        if (string.IsNullOrWhiteSpace(Attack.ProjectileSpritePath) && SpriteStatusAllowsRuntimePath(Attack.ProjectileSpriteStatus))
            Attack.ProjectileSpritePath = ConventionalAssetFileName(Id, "_projectile");
        Attack.ImpactSpriteStatus = NormalizeSpriteStatus(Attack.ImpactSpriteStatus);
        Attack.ImpactSpritePath = NormalizeSpritePathForStatus(Attack.ImpactSpritePath, Attack.ImpactSpriteStatus);
        if (string.IsNullOrWhiteSpace(Attack.ImpactSpritePath) && SpriteStatusAllowsRuntimePath(Attack.ImpactSpriteStatus))
            Attack.ImpactSpritePath = ConventionalAssetFileName(Id, "_impact");
        Attack.ChildSpriteStatus = NormalizeSpriteStatus(Attack.ChildSpriteStatus);
        Attack.ChildSpritePath = NormalizeSpritePathForStatus(Attack.ChildSpritePath, Attack.ChildSpriteStatus);
        if (string.IsNullOrWhiteSpace(Attack.ChildSpritePath) && SpriteStatusAllowsRuntimePath(Attack.ChildSpriteStatus))
            Attack.ChildSpritePath = ConventionalAssetFileName(Id, "_child");
        Attack.FieldSpriteStatus = NormalizeSpriteStatus(Attack.FieldSpriteStatus);
        Attack.FieldSpritePath = NormalizeSpritePathForStatus(Attack.FieldSpritePath, Attack.FieldSpriteStatus);
        if (string.IsNullOrWhiteSpace(Attack.FieldSpritePath) && SpriteStatusAllowsRuntimePath(Attack.FieldSpriteStatus))
            Attack.FieldSpritePath = ConventionalAssetFileName(Id, "_field");
    }

}
