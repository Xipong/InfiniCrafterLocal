#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.VFX;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

// Deterministic validation/engine-bound normalization for the v5 low-level wire.
// This file may clamp hard Terraria/performance limits and translate exact use-style
// names to ItemUseStyleID. It must not invent movement, attachment, delivery,
// controllers, events, entity kinds, or any gameplay value from prose/category.
public sealed partial class GeneratedItemData
{
    private static int ClampInt(int value, int min, int max) => Math.Min(max, Math.Max(min, value));
    private static float ClampFloat(float value, float min, float max) => MathF.Min(max, MathF.Max(min, value));

    private static string SafeText(string? value, int maxLen)
    {
        string text = (value ?? "").Trim();
        return text.Length <= maxLen ? text : text[..maxLen];
    }

    private static string[] SafeTextArray(string[]? values, int maxItems = 32, int maxLen = 64)
        => (values ?? Array.Empty<string>())
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .Select(x => SafeText(x, maxLen))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(maxItems)
            .ToArray();

    private static string NormalizeRequiredHexColor(string? value, string label)
    {
        string text = (value ?? "").Trim().ToLowerInvariant();
        if (text.Length == 7 && text[0] == '#' && text.Skip(1).All(Uri.IsHexDigit))
            return text;
        throw new InvalidDataException($"{label} must be a #RRGGBB color");
    }

    public void Normalize()
    {
        if (SchemaVersion != 5)
            throw new InvalidDataException($"Unsupported generated item schemaVersion {SchemaVersion}; only 5 is accepted");
        RuntimeApiVersion = SafeText(RuntimeApiVersion, 48);
        if (!string.Equals(RuntimeApiVersion, RuntimeProgramSpec.CurrentApiVersion, StringComparison.Ordinal))
            throw new InvalidDataException($"Unsupported runtimeApiVersion '{RuntimeApiVersion}'");

        Id = SafeText(Id, 64);
        RecipeKey = SafeText(RecipeKey, 120);
        Name = SafeText(Name, 80);
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidDataException("name must be non-blank");
        ParentA = SafeText(ParentA, 80);
        ParentB = SafeText(ParentB, 80);
        MergeMode = SafeText(MergeMode, 32);
        Category = SafeText(Category, 32).ToLowerInvariant();
        SourceMode = SafeText(SourceMode, 32).ToLowerInvariant();
        Tags = SafeTextArray(Tags, 32, 64);

        Canonical ??= new CanonicalSpec();
        SourceRepresentation ??= Array.Empty<SourceRepresentationSpec>();
        Inheritance ??= Array.Empty<InheritanceSpec>();
        LossBudget ??= new LossBudgetSpec();
        RecipeMeta ??= new RecipeMetaSpec();
        ItemKnowledge ??= new ItemKnowledgeSpec();
        GeneratedParentSummary ??= new GeneratedParentSummarySpec();
        Gameplay ??= new GameplaySpec();
        Accessory ??= new AccessorySpec();
        Armor ??= new ArmorSpec();
        RuntimeProgram ??= new RuntimeProgramSpec();
        Visual ??= new VisualSpec();
        VfxManifest ??= new VfxManifestSpec();
        Debug ??= new Dictionary<string, System.Text.Json.JsonElement>();
        ExtensionData ??= new Dictionary<string, System.Text.Json.JsonElement>();

        RejectRetiredArchitectureFields();
        NormalizeGameplay();
        NormalizeEquipment();
        NormalizeVisual();
        RuntimeProgram.NormalizeAndValidate();
        ValidateBindingCapabilityProjection();
        if (!string.Equals(RuntimeProgram.ApiVersion, RuntimeApiVersion, StringComparison.Ordinal))
            throw new InvalidDataException("top-level runtimeApiVersion does not match runtimeProgram.apiVersion");
        VfxManifest.Normalize();
        ValidateVfxEntityEventReferences();
        GeneratedParentSummary.Normalize();

        RecipeMeta.WorldId = SafeText(RecipeMeta.WorldId, 32);
        RecipeMeta.AssetTransport = SafeText(RecipeMeta.AssetTransport, 32);
        RecipeMeta.AssetBaseUrl = SafeText(RecipeMeta.AssetBaseUrl, 500);
        RecipeMeta.AssetFiles = SafeTextArray(RecipeMeta.AssetFiles, 64, 180);
    }

    private void ValidateBindingCapabilityProjection()
    {
        bool hasExplicitUseEffects = Gameplay.HealLife > 0
            || Gameplay.HealMana > 0
            || (Gameplay.ExtraBuffs?.Length ?? 0) > 0
            || Gameplay.GeneratedBuff?.HasAnyEffect == true
            || !string.IsNullOrWhiteSpace(Gameplay.MobilityMode);
        bool hasExplicitEquipment = Accessory.Enabled || Armor.Enabled;

        foreach (RuntimeBindingSpec binding in RuntimeProgram.Bindings)
        {
            string action = binding.UsePolicy.Action.Kind;
            if (action == RuntimeBindingAction.ApplyItemEffects && !hasExplicitUseEffects)
                throw new InvalidDataException($"binding '{binding.Id}' apply_item_effects has no compiled item effect capability");
            if (action == RuntimeBindingAction.EquipPassive && !hasExplicitEquipment)
                throw new InvalidDataException($"binding '{binding.Id}' equip_passive has no compiled accessory/armor capability");
        }
    }

    private void RejectRetiredArchitectureFields()
    {
        string[] retired =
        {
            "attack", "runtimePlan", "runtimeCompiled", "runtimeAffordance",
            "runtimeArchetype", "weaponFamily", "runtimeFamily", "presentationGenome",
        };
        foreach (string key in retired)
            if (ExtensionData.ContainsKey(key))
                throw new InvalidDataException($"Retired generated-item field '{key}' is not accepted by runtime v5");
    }

    private void NormalizeGameplay()
    {
        Gameplay.Kind = SafeText(Gameplay.Kind, 32).ToLowerInvariant();
        Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129);
        _ = TerrariaRuntimeVocabulary.ResolveDamageClass(Gameplay.DamageClass);
        Gameplay.Damage = ClampInt(Gameplay.Damage, 0, 2000);
        Gameplay.Knockback = ClampFloat(Gameplay.Knockback, 0f, 20f);
        Gameplay.UseTime = ClampInt(Gameplay.UseTime, 1, 600);
        Gameplay.UseAnimation = ClampInt(Gameplay.UseAnimation, 1, 600);
        Gameplay.UseStyleName = SafeText(Gameplay.UseStyleName, 32).ToLowerInvariant();
        Gameplay.UseStyle = TerrariaRuntimeVocabulary.ResolveItemUseStyle(Gameplay.UseStyleName);
        Gameplay.ManaCost = ClampInt(Gameplay.ManaCost, 0, 500);
        if (Gameplay.Rarity < 0 || Gameplay.Rarity >= RarityLoader.RarityCount)
            throw new InvalidDataException($"rarity ID {Gameplay.Rarity} is not loaded");
        Gameplay.Value = ClampInt(Gameplay.Value, 0, 100_000_000);
        Gameplay.MaxStack = ClampInt(Gameplay.MaxStack, 1, 9999);
        Gameplay.CraftYield = ClampInt(Gameplay.CraftYield, 1, 9999);
        Gameplay.AmmoCategory = SafeText(Gameplay.AmmoCategory, 32).ToLowerInvariant();
        _ = TerrariaRuntimeVocabulary.ResolveAmmoCategory(Gameplay.AmmoCategory);
        Gameplay.AmmoProjectileId = Gameplay.AmmoCategory.Length == 0
            ? ProjectileID.None
            : Gameplay.AmmoProjectileId;
        if (Gameplay.AmmoCategory.Length > 0
            && (Gameplay.AmmoProjectileId <= ProjectileID.None || Gameplay.AmmoProjectileId >= ProjectileID.Count))
            throw new InvalidDataException($"ammo projectile ID {Gameplay.AmmoProjectileId} is not a vanilla ProjectileID");
        Gameplay.AmmoShootSpeedPxPerTick = ClampFloat(Gameplay.AmmoShootSpeedPxPerTick, -20f, 80f);

        Gameplay.Width = ClampInt(Gameplay.Width, 8, 256);
        Gameplay.Height = ClampInt(Gameplay.Height, 8, 256);
        Gameplay.ItemScale = ClampFloat(Gameplay.ItemScale, 0.25f, 4f);
        Gameplay.HoldoutOffsetX = ClampInt(Gameplay.HoldoutOffsetX, -96, 96);
        Gameplay.HoldoutOffsetY = ClampInt(Gameplay.HoldoutOffsetY, -96, 96);
        Gameplay.ReleaseTiming = SafeText(Gameplay.ReleaseTiming, 32).ToLowerInvariant();
        Gameplay.HandPose = SafeText(Gameplay.HandPose, 32).ToLowerInvariant();
        Gameplay.HealLife = ClampInt(Gameplay.HealLife, 0, 500);
        Gameplay.HealMana = ClampInt(Gameplay.HealMana, 0, 500);
        if (Gameplay.BuffCode < 0 || Gameplay.BuffCode >= BuffLoader.BuffCount)
            throw new InvalidDataException($"buff ID {Gameplay.BuffCode} is not loaded");
        Gameplay.BuffTime = ClampInt(Gameplay.BuffTime, 0, 21600);
        Gameplay.ExtraBuffs = (Gameplay.ExtraBuffs ?? Array.Empty<BuffEntrySpec>())
            .Select(x =>
            {
                if (x is null)
                    throw new InvalidDataException("extra buff row cannot be null");
                if (x.BuffCode <= 0 || x.BuffCode >= BuffLoader.BuffCount)
                    throw new InvalidDataException($"extra buff ID {x.BuffCode} is not loaded");
                if (x.BuffTime <= 0)
                    throw new InvalidDataException($"extra buff ID {x.BuffCode} requires positive duration");
                return new BuffEntrySpec
                {
                    BuffCode = x.BuffCode,
                    BuffTime = ClampInt(x.BuffTime, 1, 21600),
                };
            })
            .Take(16)
            .ToArray();
        Gameplay.GeneratedBuff ??= new GeneratedBuffSpec();
        Gameplay.GeneratedBuff.Normalize();
        Gameplay.PickPower = ClampInt(Gameplay.PickPower, 0, 1000);
        Gameplay.AxePower = ClampInt(Gameplay.AxePower, 0, 100);
        Gameplay.HammerPower = ClampInt(Gameplay.HammerPower, 0, 1000);

        Gameplay.MobilityMode = SafeText(Gameplay.MobilityMode, 32).ToLowerInvariant();
        if (Gameplay.MobilityMode is not ("" or "recall_home" or "blink_to_cursor"))
            throw new InvalidDataException($"Unsupported move_player_on_use mode '{Gameplay.MobilityMode}'");
        Gameplay.MobilityRangeTiles = ClampInt(Gameplay.MobilityRangeTiles, 0, 80);
        Gameplay.MobilityCooldownTicks = ClampInt(Gameplay.MobilityCooldownTicks, 0, 36000);
        Gameplay.MiningSpeedScale = ClampFloat(Gameplay.MiningSpeedScale, 0.1f, 4f);
        Gameplay.HoldLightStrength = ClampFloat(Gameplay.HoldLightStrength, 0f, 1.5f);
        Gameplay.HoldLightColorName = RuntimeColorPolicy.NormalizeRequired(Gameplay.HoldLightColorName, allowEmpty: Gameplay.HoldLightStrength <= 0f);
        Gameplay.UseConditionMode = SafeText(Gameplay.UseConditionMode, 32).ToLowerInvariant();
        if (Gameplay.UseConditionMode is not ("" or "none" or "grounded" or "not_wet" or "life_above" or "mana_above"))
            throw new InvalidDataException($"Unsupported use condition '{Gameplay.UseConditionMode}'");
        Gameplay.UseConditionMinLife = ClampInt(Gameplay.UseConditionMinLife, 0, 10000);
        Gameplay.UseConditionMinMana = ClampInt(Gameplay.UseConditionMinMana, 0, 10000);
    }

    private void NormalizeEquipment()
    {
        Accessory.Defense = ClampInt(Accessory.Defense, -100, 500);
        Accessory.MaxLife = ClampInt(Accessory.MaxLife, -500, 5000);
        Accessory.MaxMana = ClampInt(Accessory.MaxMana, -500, 5000);
        Accessory.LifeRegen = ClampInt(Accessory.LifeRegen, -120, 120);
        Accessory.ManaRegen = ClampInt(Accessory.ManaRegen, -120, 120);
        Accessory.MovementSpeed = ClampFloat(Accessory.MovementSpeed, -0.5f, 2f);
        Accessory.GenericDamage = ClampFloat(Accessory.GenericDamage, -0.9f, 3f);
        Accessory.GenericCrit = ClampFloat(Accessory.GenericCrit, -100f, 100f);
        Accessory.Endurance = ClampFloat(Accessory.Endurance, 0f, 0.75f);
        Accessory.MinionSlots = ClampInt(Accessory.MinionSlots, 0, 20);
        Accessory.SentrySlots = ClampInt(Accessory.SentrySlots, 0, 10);
        Accessory.LightStrength = ClampFloat(Accessory.LightStrength, 0f, 1.5f);
        Accessory.LightColorName = RuntimeColorPolicy.NormalizeRequired(Accessory.LightColorName, allowEmpty: Accessory.LightStrength <= 0f);

        Armor.Slot = SafeText(Armor.Slot, 16).ToLowerInvariant();
        if (Armor.Enabled && Armor.Slot is not ("head" or "body" or "legs"))
            throw new InvalidDataException($"Unsupported enabled armor slot '{Armor.Slot}'");
        if (!Armor.Enabled && Armor.Slot is not ("" or "head" or "body" or "legs"))
            Armor.Slot = "";
        Armor.SetKey = SafeText(Armor.SetKey, 64);
        Armor.Defense = ClampInt(Armor.Defense, 0, 500);
        Armor.MaxLife = ClampInt(Armor.MaxLife, -500, 5000);
        Armor.MaxMana = ClampInt(Armor.MaxMana, -500, 5000);
        Armor.MovementSpeed = ClampFloat(Armor.MovementSpeed, -0.5f, 2f);
        Armor.GenericDamage = ClampFloat(Armor.GenericDamage, -0.9f, 3f);
        Armor.GenericCrit = ClampFloat(Armor.GenericCrit, -100f, 100f);
        Armor.SetBonusGenericDamage = ClampFloat(Armor.SetBonusGenericDamage, -0.9f, 3f);
        Armor.SetBonusMovementSpeed = ClampFloat(Armor.SetBonusMovementSpeed, -0.5f, 2f);
        Armor.SetBonusLifeRegen = ClampInt(Armor.SetBonusLifeRegen, -120, 120);
    }

    private void NormalizeVisual()
    {
        Visual.ObjectType = SafeText(Visual.ObjectType, 64);
        Visual.Style = SafeText(Visual.Style, 64);
        Visual.RequiredAnchors = SafeTextArray(Visual.RequiredAnchors, 16, 80);
        Visual.Palette = SafeTextArray(Visual.Palette, 8, 48);
        Visual.ImagePrompt = SafeText(Visual.ImagePrompt, 1600);
        Visual.NegativePrompt = SafeText(Visual.NegativePrompt, 700);
        Visual.SpriteStatus = SafeText(Visual.SpriteStatus, 48).ToLowerInvariant();
        Visual.SpritePath = SafeText(Visual.SpritePath, 260);
        Visual.SpriteRawPath = SafeText(Visual.SpriteRawPath, 260);
        Visual.SpriteUrl = SafeText(Visual.SpriteUrl, 500);
        Visual.EquipOverlayStatus = SafeText(Visual.EquipOverlayStatus, 48).ToLowerInvariant();
        Visual.EquipOverlayPath = SafeText(Visual.EquipOverlayPath, 260);
        Visual.EquipOverlayUrl = SafeText(Visual.EquipOverlayUrl, 500);
        Visual.PreferredCanvasSize = Visual.PreferredCanvasSize <= 20 ? 16 : Visual.PreferredCanvasSize <= 28 ? 24 : Visual.PreferredCanvasSize <= 40 ? 32 : Visual.PreferredCanvasSize <= 56 ? 48 : Visual.PreferredCanvasSize <= 80 ? 64 : Visual.PreferredCanvasSize <= 112 ? 96 : 128;
        Visual.InventoryScale = ClampFloat(Visual.InventoryScale, 0.25f, 4f);
        Visual.WorldScale = ClampFloat(Visual.WorldScale, 0.25f, 4f);
        Visual.DrawOffsetX = ClampInt(Visual.DrawOffsetX, -256, 256);
        Visual.DrawOffsetY = ClampInt(Visual.DrawOffsetY, -256, 256);
        Visual.DominantColorHex = NormalizeRequiredHexColor(Visual.DominantColorHex, "visual.dominantColorHex");
        Visual.AccentColorHex = NormalizeRequiredHexColor(Visual.AccentColorHex, "visual.accentColorHex");
        Visual.SpriteTechnicalScore = ClampFloat(Visual.SpriteTechnicalScore, 0f, 1f);
        Visual.EquipOverlayScore = ClampFloat(Visual.EquipOverlayScore, 0f, 1f);
        bool inertReference = SourceMode is "player_save_ref" or "corrupt_reference";
        if (!inertReference && SourceMode is not ("developer_fixture" or "test_fixture")
            && (string.IsNullOrWhiteSpace(Visual.SpritePath)
                || Visual.SpriteStatus is "" or "failed" or "prompt_only" or "placeholder" or "backend_config_error"))
            throw new InvalidDataException("Required generated item PNG is unavailable; placeholders are not accepted");
        if (Accessory.Enabled && Armor.Enabled)
            throw new InvalidDataException("A runtime item cannot enable both accessory and armor capabilities");
        if (!inertReference && (Accessory.Enabled || Armor.Enabled)
            && (string.IsNullOrWhiteSpace(Visual.EquipOverlayPath)
                || Visual.EquipOverlayStatus is "" or "failed" or "prompt_only" or "placeholder" or "backend_config_error"))
            throw new InvalidDataException("Required equipment overlay PNG is unavailable");
    }

    private void ValidateVfxEntityEventReferences()
    {
        foreach (VfxSlotSpec slot in VfxManifest.Slots ?? Array.Empty<VfxSlotSpec>())
        {
            if (slot is null) continue;
            RuntimeEntitySpec? entity = RuntimeProgram.TryGetEntity(slot.EntityId);
            if (entity is null)
                throw new InvalidDataException($"VFX slot '{slot.Id}' references unknown entity '{slot.EntityId}'");
            bool emitted = slot.Event == RuntimeEventKind.OnSpawn
                || RuntimeProgram.Bindings.Any(x => x.UsePolicy.Action.TargetId == entity.Id && slot.Event == RuntimeEventKind.OnUse)
                || entity.Events.Any(x => x.Event == slot.Event)
                || (entity.Damage.Enabled && slot.Event is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                || (entity.Collision.TileCollide && slot.Event == RuntimeEventKind.OnTileCollision)
                || slot.Event is RuntimeEventKind.OnExpire or RuntimeEventKind.OnKill;
            if (!emitted)
                throw new InvalidDataException($"VFX slot '{slot.Id}' binds unavailable event '{slot.Event}' on '{entity.Id}'");
            if (slot.TextureRole == "impact"
                && SourceMode is not ("developer_fixture" or "test_fixture")
                && (string.IsNullOrWhiteSpace(entity.Visual.ImpactSpritePath)
                    || entity.Visual.ImpactSpriteStatus is "" or "failed" or "prompt_only" or "placeholder" or "backend_config_error"))
                throw new InvalidDataException($"VFX slot '{slot.Id}' requires an authored impact PNG for '{entity.Id}'");
        }
    }
}
