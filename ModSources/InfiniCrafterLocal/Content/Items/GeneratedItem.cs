#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Content.Items;

// AGENT MAP: one tModLoader proxy item type for many generated item instances.
// SetData() applies the explicit GeneratedItemData DTO to the Terraria Item;
// save/net paths strip unsafe bulk; use/equipment/shoot hooks execute only
// supported fields. Do not infer gameplay from display name, tooltip, prompt,
// flavor text, or Debug/ExtensionData.
public partial class GeneratedItem : ModItem
{
    private const int GeneratedItemNetPayloadVersion = 4;
    private const int MaxGeneratedAoeTargetsPerHit = 16;
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedItem";
    protected override bool CloneNewInstances => true;
    public GeneratedItemData Data { get; private set; } = GeneratedItemData.Placeholder();
    private static int _lowNoiseWarningCount;
    private int _lastUseBlockedNoticeTick = -9999;
    private int _lastAltUseBlockedNoticeTick = -9999;
    private int _lastRuntimeHydrationTouchTick = -9999;
    private bool _applyingGeneratedSwingAoeDamage;

    private static void LogLowNoiseWarning(string context, Exception ex)
    {
        if (_lowNoiseWarningCount >= 8)
            return;
        _lowNoiseWarningCount++;
        try
        {
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn($"[GeneratedItem] {context}: {ex.GetType().Name}: {ex.Message}");
        }
        catch { }
    }

    public override ModItem Clone(Item newEntity)
    {
        var clone = (GeneratedItem)base.Clone(newEntity);
        try
        {
            // CloneNewInstances routes item copies through Clone(). GeneratedItem carries a
            // mutable reference-typed per-instance payload, so relying on tML's reflective
            // cloning rules is unsafe for player-file load, inventory cloning, and refund
            // backups. Keep the clone compact and side-effect free; asset registry hydration
            // happens later through SetData/NetReceive/craft commit paths.
            string json = (Data ?? GeneratedItemData.Placeholder()).ToNetworkJson();
            clone.Data = GeneratedItemData.FromJson(json) ?? GeneratedItemData.Placeholder();
        }
        catch
        {
            clone.Data = GeneratedItemData.Placeholder();
        }
        return clone;
    }

    public void SetData(GeneratedItemData data) => SetData(data, ensureAssets: true, registerLocal: true);

    private void SetData(GeneratedItemData data, bool ensureAssets, bool registerLocal = true, bool notifyNetState = true)
    {
        Data = data ?? GeneratedItemData.Placeholder();

        try
        {
            Data.ApplyToItem(Item);
        }
        catch (Exception ex)
        {
            // Player/character loading must never be bricked by one malformed generated
            // item payload. Fall back to a harmless placeholder instead of letting tML
            // mark the whole character as UnknownError on the selection screen.
            LogLowNoiseWarning($"ApplyToItem failed for generated item '{Data?.Id ?? "unknown"}', falling back to placeholder", ex);
            Data = GeneratedItemData.Placeholder();
            try { Data.ApplyToItem(Item); } catch (Exception placeholderEx) { LogLowNoiseWarning("Placeholder ApplyToItem also failed", placeholderEx); }
        }

        // Character select / player-file load is a fragile path in tModLoader: it should
        // deserialize the item only, not touch the per-world registry, disk asset cache,
        // HTTP asset sync, or background download tasks.  Runtime registry/asset hydration
        // is requested again when a freshly crafted/synced item is received or used in-world.
        if (registerLocal)
        {
            try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RegisterLocal(Data, ensureAssets: ensureAssets); }
            catch (Exception ex) { LogLowNoiseWarning($"RegisterLocal failed for generated item '{Data?.Id ?? "unknown"}'", ex); }
        }

        if (notifyNetState && registerLocal && Main.netMode != NetmodeID.SinglePlayer)
        {
            try { Item.NetStateChanged(); } catch { }
        }
    }

    public override void SetDefaults()
    {
        Data ??= GeneratedItemData.Placeholder();
        try { Data.ApplyToItem(Item); }
        catch (Exception ex)
        {
            LogLowNoiseWarning($"SetDefaults ApplyToItem failed for generated item '{Data?.Id ?? "unknown"}', falling back to placeholder", ex);
            Data = GeneratedItemData.Placeholder();
            try { Data.ApplyToItem(Item); } catch (Exception placeholderEx) { LogLowNoiseWarning("SetDefaults placeholder ApplyToItem also failed", placeholderEx); }
        }
    }

    public override void SaveData(TagCompound tag)
    {
        try
        {
            tag["infiniJson"] = (Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson();
        }
        catch
        {
            tag["infiniJson"] = GeneratedItemData.Placeholder().ToPlayerSaveJson();
        }
    }

    public override void LoadData(TagCompound tag)
    {
        try
        {
            string json = SafeGetString(tag, "infiniJson");
            SetData(GeneratedItemData.FromPlayerSaveJson(json) ?? GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false);
        }
        catch
        {
            try { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false); } catch { }
        }
    }

    private static string SafeGetString(TagCompound tag, string key)
    {
        try
        {
            if (tag is null || !tag.ContainsKey(key)) return "";
            return tag.GetString(key) ?? "";
        }
        catch
        {
            return "";
        }
    }

    private void EnsureRuntimeHydration(Player? player = null)
    {
        string id = (Data?.Id ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id) || string.Equals(id, "placeholder", StringComparison.OrdinalIgnoreCase))
            return;
        int now = (int)Main.GameUpdateCount;
        if (now - _lastRuntimeHydrationTouchTick < 90)
            return;
        _lastRuntimeHydrationTouchTick = now;
        try
        {
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (registry is null)
                return;
            if (registry.TryGet(id, out var cachedData))
            {
                if (GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                    SetData(cachedData, ensureAssets: false, registerLocal: false, notifyNetState: false);
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(cachedData, forceRetry: false);
                return;
            }
            if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RegisterLocal(Data, persist: false, ensureAssets: true);
            if (Main.netMode == NetmodeID.MultiplayerClient)
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: false);
        }
        catch (Exception ex)
        {
            LogLowNoiseWarning($"Runtime hydration touch failed for generated item '{id}'", ex);
        }
    }

    private GeneratedItemData ResolveRuntimeDataForPresentation()
    {
        GeneratedItemData current = Data ?? GeneratedItemData.Placeholder();
        if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
            return current;

        string id = (Data?.Id ?? "").Trim();
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (!string.IsNullOrWhiteSpace(id)
            && registry is not null
            && registry.TryGet(id, out var canonical)
            && GeneratedItemRegistryService.IsCurrentWorldData(canonical))
            return canonical;

        return current;
    }

    public override void NetSend(BinaryWriter writer)
    {
        writer.Write(GeneratedItemNetPayloadVersion);
        // ModItem NetSend runs in both directions. Send only a compact identity
        // reference here; full definitions move through the server-authoritative
        // registry hydration packets instead of letting an item-container sync
        // carry client-authored gameplay state into the server.
        try { writer.Write((Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson()); }
        catch { writer.Write(GeneratedItemData.Placeholder().ToPlayerSaveJson()); }
    }

    public override void NetReceive(BinaryReader reader)
    {
        try
        {
            int version = reader.ReadInt32();
            if (version != GeneratedItemNetPayloadVersion)
                throw new InvalidDataException($"Unsupported GeneratedItem net payload version {version}");
            var reference = GeneratedItemData.FromPlayerSaveJson(reader.ReadString()) ?? GeneratedItemData.Placeholder();
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            GeneratedItemData resolved = reference;
            if (!string.IsNullOrWhiteSpace(reference.Id)
                && registry is not null
                && registry.TryGet(reference.Id, out var canonical)
                && GeneratedItemRegistryService.IsCurrentWorldData(canonical))
                resolved = canonical;
            SetData(resolved, ensureAssets: false, registerLocal: false, notifyNetState: false);
            // Item/container sync is allowed to carry only the compact id. Kick one
            // deduplicated registry hydration now so ground/inventory/held drawing
            // does not remain on the static placeholder until the item is used.
            EnsureRuntimeHydration();
        }
        catch { try { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false); } catch { } }
    }

    public override bool CanStack(Item source)
    {
        // GeneratedItem is one ModItem type with per-instance JSON. Do not let different
        // generated results collapse into the same stack. Same recipe/id may stack if future
        // categories intentionally allow stack > 1.
        if (source.ModItem is not GeneratedItem other)
            return false;
        return string.Equals(Data?.Id, other.Data?.Id, StringComparison.Ordinal)
            && string.Equals(Data?.RecipeKey, other.Data?.RecipeKey, StringComparison.Ordinal);
    }

    public override void ModifyTooltips(List<TooltipLine> tooltips)
    {
        EnsureRuntimeHydration();
        GeneratedItemData data = Data ?? GeneratedItemData.Placeholder();
        GameplaySpec gameplay = data.Gameplay ?? new GameplaySpec();
        AccessorySpec accessory = data.Accessory ?? new AccessorySpec();
        ArmorSpec armor = data.Armor ?? new ArmorSpec();
        AttackSpec attack = data.Attack ?? new AttackSpec();
        VisualSpec visual = data.Visual ?? new VisualSpec();
        RecipeMetaSpec recipeMeta = data.RecipeMeta ?? new RecipeMetaSpec();
        ItemKnowledgeSpec itemKnowledge = data.ItemKnowledge ?? new ItemKnowledgeSpec();
        VfxManifestSpec vfxManifest = data.VfxManifest ?? new VfxManifestSpec();
        string[] requiredAnchors = visual.RequiredAnchors ?? Array.Empty<string>();
        BuffEntrySpec[] extraBuffs = gameplay.ExtraBuffs ?? Array.Empty<BuffEntrySpec>();
        VfxSlotSpec[] vfxSlots = vfxManifest.Slots ?? Array.Empty<VfxSlotSpec>();

        tooltips.Add(new TooltipLine(Mod, "InfiniParents", $"Recipe: {data.ParentA} + {data.ParentB}") { OverrideColor = Color.LightSkyBlue });
        tooltips.Add(new TooltipLine(Mod, "InfiniMerge", $"Merge: {data.MergeMode} / {data.Category} / {data.SourceMode}") { OverrideColor = Color.Gray });
        if (!string.IsNullOrWhiteSpace(data.Tooltip))
            tooltips.Add(new TooltipLine(Mod, "InfiniFlavor", data.Tooltip));

        if (armor.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniArmor", ArmorSummary()) { OverrideColor = Color.LightSteelBlue });
        if (accessory.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniAccessory", AccessorySummary()) { OverrideColor = Color.LightGreen });
        string altSummary = AltUseSummary();
        if (!string.IsNullOrWhiteSpace(altSummary))
            tooltips.Add(new TooltipLine(Mod, "InfiniAltUse", altSummary) { OverrideColor = Color.LightGoldenrodYellow });
        string useUtilitySummary = GeneratedUtilitySummary(gameplay.GeneratedBuff, "On use");
        if (!string.IsNullOrWhiteSpace(useUtilitySummary))
            tooltips.Add(new TooltipLine(Mod, "InfiniUseUtility", useUtilitySummary) { OverrideColor = Color.LightGreen });
        string holdUtilitySummary = GeneratedUtilitySummary(gameplay.HoldGeneratedBuff, "While held");
        if (!string.IsNullOrWhiteSpace(holdUtilitySummary))
            tooltips.Add(new TooltipLine(Mod, "InfiniHoldUtility", holdUtilitySummary) { OverrideColor = Color.LightCyan });
        string conditionSummary = UseConditionSummary(gameplay);
        if (!string.IsNullOrWhiteSpace(conditionSummary))
            tooltips.Add(new TooltipLine(Mod, "InfiniUseCondition", conditionSummary) { OverrideColor = Color.LightSalmon });
        string generatedCombatSummary = CompactGeneratedCombatSummary(data);
        if (!string.IsNullOrWhiteSpace(generatedCombatSummary))
            tooltips.Add(new TooltipLine(Mod, "InfiniCombatQoL", generatedCombatSummary) { OverrideColor = Color.SandyBrown });

        bool debugTooltips = Main.keyState.IsKeyDown(Keys.LeftShift) || Main.keyState.IsKeyDown(Keys.RightShift);
        if (!debugTooltips)
        {
            tooltips.Add(new TooltipLine(Mod, "InfiniDebugHint", "Hold Shift for InfiniCraft debug") { OverrideColor = Color.DarkGray });
            return;
        }

        if (recipeMeta.GenerationDepth > 0)
            tooltips.Add(new TooltipLine(Mod, "InfiniDepth", $"Depth: {recipeMeta.GenerationDepth} / {recipeMeta.RecipeCoherence}") { OverrideColor = Color.MediumPurple });
        if (!string.IsNullOrWhiteSpace(gameplay.Stage))
            tooltips.Add(new TooltipLine(Mod, "InfiniStage", $"Stage: {gameplay.Stage} / budget {gameplay.PowerBudget:0.00}") { OverrideColor = Color.LightGoldenrodYellow });
        if (!string.IsNullOrWhiteSpace(itemKnowledge.StrongestTier) && itemKnowledge.StrongestTier != "unknown")
            tooltips.Add(new TooltipLine(Mod, "InfiniKnowledge", $"Input hint: {itemKnowledge.StrongestTier}") { OverrideColor = Color.LightCyan });
        if (requiredAnchors.Length > 0)
            tooltips.Add(new TooltipLine(Mod, "InfiniAnchors", "Anchors: " + string.Join(", ", requiredAnchors)) { OverrideColor = Color.Silver });
        if (!string.IsNullOrWhiteSpace(visual.SpriteStatus))
            tooltips.Add(new TooltipLine(Mod, "InfiniSpriteStatus", $"Sprite: {visual.SpriteStatus} technical {visual.SpriteTechnicalScore:0.00}; semantic {visual.SemanticReviewStatus}") { OverrideColor = Color.DarkGray });
        if (extraBuffs.Length > 1)
            tooltips.Add(new TooltipLine(Mod, "InfiniExtraBuffs", $"Use buffs: {extraBuffs.Length} channels") { OverrideColor = Color.LightGreen });
        if (!string.IsNullOrWhiteSpace(gameplay.MobilityMode))
            tooltips.Add(new TooltipLine(Mod, "InfiniMobility", $"Mobility: {gameplay.MobilityMode} / {gameplay.MobilityRangeTiles} tiles / cd {gameplay.MobilityCooldownTicks}t") { OverrideColor = Color.LightSteelBlue });
        if (gameplay.ConsumeChancePercent < 100 && gameplay.Consumable)
            tooltips.Add(new TooltipLine(Mod, "InfiniConsume", $"Consume chance: {gameplay.ConsumeChancePercent}%") { OverrideColor = Color.LightSalmon });
        if (!string.IsNullOrWhiteSpace(attack.ProjectileSpriteStatus))
            tooltips.Add(new TooltipLine(Mod, "InfiniProjectileSpriteStatus", $"Projectile sprite: {attack.ProjectileSpriteStatus} score {attack.ProjectileSpriteScore:0.00}") { OverrideColor = Color.DarkGray });
        if (!string.IsNullOrWhiteSpace(attack.ChildSpriteStatus) || !string.IsNullOrWhiteSpace(attack.FieldSpriteStatus))
            tooltips.Add(new TooltipLine(Mod, "InfiniVisualPackStatus", $"Visual pack: child {attack.ChildSpriteStatus}, field {attack.FieldSpriteStatus}") { OverrideColor = Color.DarkGray });
        if (gameplay.ItemScale > 1.01f || visual.InventoryScale > 1.01f || visual.WorldScale > 1.01f)
            tooltips.Add(new TooltipLine(Mod, "InfiniScale", $"Scale: item {gameplay.ItemScale:0.00}, inv {visual.InventoryScale:0.00}, world {visual.WorldScale:0.00}") { OverrideColor = Color.Goldenrod });

        tooltips.Add(new TooltipLine(Mod, "InfiniDamagePath", DamagePathSummary(data)) { OverrideColor = Color.SandyBrown });
        if (attack.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniGeneratedExecutorProfile", $"Generated executor: {attack.RuntimeFamily} / {attack.Movement} / {attack.Effect} / {attack.OnHit}") { OverrideColor = Color.Orange });
        if (attack.Enabled && !string.IsNullOrWhiteSpace(attack.VisualMode))
            tooltips.Add(new TooltipLine(Mod, "InfiniPresentation", $"Visual: {attack.VisualMode} / {attack.TrailStyle} / {attack.ImpactStyle}") { OverrideColor = Color.LightPink });
        if (vfxManifest.HasSlots)
            tooltips.Add(new TooltipLine(Mod, "InfiniVfxManifest", $"VFX: {vfxManifest.RecipeId} ({vfxSlots.Length} slots, conf {vfxManifest.Confidence:0.00})") { OverrideColor = Color.MediumAquamarine });
        if (attack.Enabled && (attack.ProjectileScale > 1.01f || attack.HitboxScale > 1.01f || attack.AoeDamageRadiusPx > 0 || attack.ImpactVfxRadiusPx > 0 || attack.ContactForgivenessPx > 0))
            tooltips.Add(new TooltipLine(Mod, "InfiniAttackSize", $"Attack size: proj {attack.ProjectileScale:0.00}, hitbox {attack.HitboxScale:0.00}, aoe {attack.AoeDamageRadiusPx / 16f:0.00}t, vfx {attack.ImpactVfxRadiusPx}px, contact +{attack.ContactForgivenessPx}px") { OverrideColor = Color.OrangeRed });
        if (attack.Enabled && attack.EngineMetrics is not null && attack.EngineMetrics.TryGetValue("activeProjectileEstimate", out float activeEstimate))
        {
            string dustText = attack.DustSpawnDenom <= 0 ? "off" : $"1/{Math.Max(1, attack.DustSpawnDenom)}";
            tooltips.Add(new TooltipLine(Mod, "InfiniEnginePressure", $"Engine estimate: ~{activeEstimate:0.0} active proj, dust {dustText}") { OverrideColor = Color.DarkGray });
        }
    }

    private static bool HasVanillaItemHitboxDamage(GeneratedItemData? data)
    {
        if (data is null || data.Accessory.Enabled || data.Armor.Enabled)
            return false;
        if (data.Gameplay.Damage <= 0)
            return false;
        string kind = (data.Gameplay.Kind ?? "").Trim().ToLowerInvariant();
        if (kind is "ammo" or "accessory" or "material" or "furniture")
            return false;
        // Attack.Enabled means "generated runtime executor exists"; vanilla item
        // melee/tool hitboxes are a separate Terraria damage path.
        if (data.Attack.Enabled && data.Attack.DisableItemMeleeHitbox)
            return false;
        return data.Gameplay.UseStyle > ItemUseStyleID.None;
    }

    private static string DamagePathSummary(GeneratedItemData? data)
    {
        if (data is null)
            return "Damage path: missing generated data";
        bool generatedExecutor = data.Attack.Enabled;
        bool vanillaHitbox = HasVanillaItemHitboxDamage(data);
        if (generatedExecutor && vanillaHitbox)
            return $"Damage path: generated executor + vanilla hitbox ({data.Gameplay.Damage} item dmg)";
        if (generatedExecutor)
            return $"Damage path: generated runtime executor ({data.Attack.RuntimeFamily})";
        if (vanillaHitbox)
            return $"Damage path: vanilla item/tool hitbox only ({data.Gameplay.Damage} item dmg; no generated projectile executor)";
        if (data.Gameplay.Damage > 0)
            return $"Damage path: item damage {data.Gameplay.Damage}, but vanilla hitbox disabled/unsupported";
        return "Damage path: utility/non-damaging item";
    }

    private string ArmorSummary()
    {
        var a = Data.Armor;
        var parts = new List<string>();
        if (a.Defense != 0) parts.Add($"{a.Defense} def");
        if (a.MaxLife != 0) parts.Add($"+{a.MaxLife} life");
        if (a.MaxMana != 0) parts.Add($"+{a.MaxMana} mana");
        if (a.LifeRegen != 0) parts.Add($"+{a.LifeRegen} life regen");
        if (a.ManaRegen != 0) parts.Add($"+{a.ManaRegen} mana regen");
        if (a.GenericDamage != 0) parts.Add($"+{a.GenericDamage * 100f:0}% dmg");
        if (a.MeleeDamage != 0) parts.Add($"+{a.MeleeDamage * 100f:0}% melee");
        if (a.RangedDamage != 0) parts.Add($"+{a.RangedDamage * 100f:0}% ranged");
        if (a.MagicDamage != 0) parts.Add($"+{a.MagicDamage * 100f:0}% magic");
        if (a.SummonDamage != 0) parts.Add($"+{a.SummonDamage * 100f:0}% summon");
        if (a.GenericCrit != 0) parts.Add($"+{a.GenericCrit:0}% crit");
        if (a.AttackSpeed != 0) parts.Add($"+{a.AttackSpeed * 100f:0}% speed");
        if (a.Knockback != 0) parts.Add($"+{a.Knockback:0.##} kb");
        if (a.MovementSpeed != 0) parts.Add($"+{a.MovementSpeed * 100f:0}% move");
        if (a.MaxRunSpeed != 0) parts.Add($"+{a.MaxRunSpeed:0.##} run");
        if (a.JumpSpeed != 0) parts.Add($"+{a.JumpSpeed:0.##} jump");
        if (a.MinionSlots != 0) parts.Add($"+{a.MinionSlots} minions");
        if (a.SentrySlots != 0) parts.Add($"+{a.SentrySlots} sentries");
        if (a.ManaCostReduction != 0f) parts.Add($"-{a.ManaCostReduction * 100f:0}% mana cost");
        if (a.AmmoSaveChance != 0f) parts.Add($"{a.AmmoSaveChance * 100f:0}% ammo save");
        if (a.Aggro != 0) parts.Add($"{a.Aggro:+#;-#;0} aggro");
        if (a.Endurance != 0f) parts.Add($"+{a.Endurance * 100f:0}% DR");
        if (a.ArmorPenetration != 0f) parts.Add($"+{a.ArmorPenetration:0.#} armor pen");
        if (a.WhipRange != 0f) parts.Add($"+{a.WhipRange * 100f:0}% whip range");
        if (a.SummonTagDamage != 0f) parts.Add($"+{a.SummonTagDamage * 100f:0}% generated whip tag damage");
        if (a.FallDamageImmune) parts.Add("fall immunity");
        if (a.LavaImmune) parts.Add("lava immunity");
        if (a.WaterWalk) parts.Add("water walk");
        if (a.LightStrength > 0f) parts.Add(string.IsNullOrWhiteSpace(a.LightColorName) ? "light" : $"{a.LightColorName} light");
        if (!string.IsNullOrWhiteSpace(a.SetKey)) parts.Add($"set {a.SetKey}");
        if (!string.IsNullOrWhiteSpace(a.SetBonusText)) parts.Add("set bonus ready");
        string slot = string.IsNullOrWhiteSpace(a.Slot) ? "body" : a.Slot;
        string head = string.IsNullOrWhiteSpace(a.Archetype) || a.Archetype == "hybrid" ? $"Armor ({slot})" : $"Armor ({slot}, {a.Archetype})";
        return parts.Count == 0 ? head : head + ": " + string.Join(", ", parts);
    }

    private string AccessorySummary()
    {
        var a = Data.Accessory;
        var parts = new List<string>();
        if (a.Defense != 0) parts.Add($"+{a.Defense} def");
        if (a.MaxLife != 0) parts.Add($"+{a.MaxLife} life");
        if (a.MaxMana != 0) parts.Add($"+{a.MaxMana} mana");
        if (a.LifeRegen != 0) parts.Add($"+{a.LifeRegen} life regen");
        if (a.ManaRegen != 0) parts.Add($"+{a.ManaRegen} mana regen");
        if (a.GenericDamage != 0) parts.Add($"+{a.GenericDamage * 100f:0}% dmg");
        if (a.MeleeDamage != 0) parts.Add($"+{a.MeleeDamage * 100f:0}% melee");
        if (a.RangedDamage != 0) parts.Add($"+{a.RangedDamage * 100f:0}% ranged");
        if (a.MagicDamage != 0) parts.Add($"+{a.MagicDamage * 100f:0}% magic");
        if (a.SummonDamage != 0) parts.Add($"+{a.SummonDamage * 100f:0}% summon");
        if (a.GenericCrit != 0) parts.Add($"+{a.GenericCrit:0}% crit");
        if (a.AttackSpeed != 0) parts.Add($"+{a.AttackSpeed * 100f:0}% speed");
        if (a.Knockback != 0) parts.Add($"+{a.Knockback:0.##} kb");
        if (a.MovementSpeed != 0) parts.Add($"+{a.MovementSpeed * 100f:0}% move");
        if (a.MaxRunSpeed != 0) parts.Add($"+{a.MaxRunSpeed:0.##} run");
        if (a.JumpSpeed != 0) parts.Add($"+{a.JumpSpeed:0.##} jump");
        if (a.MinionSlots != 0) parts.Add($"+{a.MinionSlots} minions");
        if (a.SentrySlots != 0) parts.Add($"+{a.SentrySlots} sentries");
        if (a.ManaCostReduction != 0f) parts.Add($"-{a.ManaCostReduction * 100f:0}% mana cost");
        if (a.AmmoSaveChance != 0f) parts.Add($"{a.AmmoSaveChance * 100f:0}% ammo save");
        if (a.Aggro != 0) parts.Add($"{a.Aggro:+#;-#;0} aggro");
        if (a.Endurance != 0f) parts.Add($"+{a.Endurance * 100f:0}% DR");
        if (a.ArmorPenetration != 0f) parts.Add($"+{a.ArmorPenetration:0.#} armor pen");
        if (a.WhipRange != 0f) parts.Add($"+{a.WhipRange * 100f:0}% whip range");
        if (a.SummonTagDamage != 0f) parts.Add($"+{a.SummonTagDamage * 100f:0}% generated whip tag damage");
        if (a.FallDamageImmune) parts.Add("fall immunity");
        if (a.LavaImmune) parts.Add("lava immunity");
        if (a.WaterWalk) parts.Add("water walk");
        if (a.LightStrength > 0f) parts.Add(string.IsNullOrWhiteSpace(a.LightColorName) ? "light" : $"{a.LightColorName} light");
        string head = string.IsNullOrWhiteSpace(a.Archetype) || a.Archetype == "generic" ? "Accessory" : $"Accessory ({a.Archetype})";
        return parts.Count == 0 ? head : head + ": " + string.Join(", ", parts);
    }

    public override bool AltFunctionUse(Player player)
    {
        return HasExecutableAltUse(Data?.Gameplay);
    }

    private static bool HasExecutableAltUse(GameplaySpec? gp)
    {
        if (gp is null) return false;
        string mode = (gp.AltUseMode ?? "").Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(mode) || mode == "none") return false;
        if (mode == "mobility")
        {
            string mobilityMode = (gp.AltMobilityMode ?? "").Trim().ToLowerInvariant();
            return mobilityMode == "recall_home"
                || (mobilityMode == "blink_to_cursor" && gp.AltMobilityRangeTiles > 0);
        }
        if (mode == "generated_buff")
            return gp.AltGeneratedBuff is not null && gp.AltGeneratedBuff.HasAnyEffect;
        if (mode == "light")
            return gp.AltGeneratedBuff is not null
                && gp.AltGeneratedBuff.HasAnyEffect
                && gp.AltGeneratedBuff.EmitLightStrength > 0f;
        return false;
    }

    private string AltUseSummary()
    {
        var gp = Data?.Gameplay;
        if (!HasExecutableAltUse(gp)) return "";
        string mode = (gp!.AltUseMode ?? "").Trim().ToLowerInvariant();
        string prefix = "Alt use (Right Click / ПКМ): ";
        if (mode == "mobility")
        {
            string kind = string.IsNullOrWhiteSpace(gp.AltMobilityMode) ? "mobility" : gp.AltMobilityMode.Trim();
            string range = gp.AltMobilityRangeTiles > 0 ? $", {gp.AltMobilityRangeTiles} tiles" : "";
            string cooldown = gp.AltMobilityCooldownTicks > 0 ? $", cooldown {Math.Max(1, (int)Math.Ceiling(gp.AltMobilityCooldownTicks / 60f))}s" : "";
            return prefix + kind + range + cooldown;
        }
        if (mode == "generated_buff" && gp.AltGeneratedBuff is not null && gp.AltGeneratedBuff.HasAnyEffect)
            return prefix + GeneratedUtilitySummary(gp.AltGeneratedBuff, "");
        if (mode == "light")
            return prefix + $"light pulse ({AltLightStrength(gp):0.00}, {Math.Max(1, (int)Math.Ceiling((gp.AltGeneratedBuff?.DurationTicks ?? 0) / 60f))}s)";
        return prefix + mode;
    }

    private static string GeneratedUtilitySummary(GeneratedBuffSpec? buff, string prefix)
    {
        if (buff is null || !buff.HasAnyEffect) return "";
        var parts = new List<string>();
        if (Math.Abs(buff.MiningSpeedMultiplier - 1f) > 0.01f) parts.Add($"mining time x{buff.MiningSpeedMultiplier:0.00}");
        if (buff.EmitLightStrength > 0f) parts.Add(string.IsNullOrWhiteSpace(buff.LightColorName) ? "light" : $"{buff.LightColorName} light");
        if (buff.OreSenseRadiusTiles > 0) parts.Add($"ore sense {buff.OreSenseRadiusTiles} tiles");
        if (buff.MovementSpeed != 0f) parts.Add($"{buff.MovementSpeed * 100f:+0;-0;0}% move");
        if (buff.JumpBoost > 0f) parts.Add($"+{buff.JumpBoost:0.##} jump");
        if (buff.ManaRegen > 0) parts.Add($"+{buff.ManaRegen} mana regen");
        if (buff.LifeRegen > 0) parts.Add($"+{buff.LifeRegen} life regen");
        int seconds = Math.Max(1, (int)Math.Ceiling(buff.DurationTicks / 60f));
        string head = string.IsNullOrWhiteSpace(prefix) ? $"{seconds}s" : $"{prefix} ({seconds}s)";
        return parts.Count == 0 ? head : head + ": " + string.Join(", ", parts);
    }

    private static float AltLightStrength(GameplaySpec? gp)
    {
        if (gp is null) return 0f;
        return Math.Clamp(gp.AltGeneratedBuff?.EmitLightStrength ?? 0f, 0f, 1.5f);
    }


    private static string UseConditionSummary(GameplaySpec? gp)
    {
        if (gp is null) return "";
        string mode = (gp.UseConditionMode ?? "").Trim().ToLowerInvariant();
        return mode switch
        {
            "grounded" => "Requires ground contact",
            "not_wet" => "Cannot be used while wet",
            "life_above" => $"Requires at least {Math.Max(0, gp.UseConditionMinLife)} life",
            "mana_above" => $"Requires at least {Math.Max(0, gp.UseConditionMinMana)} mana",
            _ => "",
        };
    }

    private static string CompactGeneratedCombatSummary(GeneratedItemData? data)
    {
        if (data is null || data.Accessory.Enabled || data.Armor.Enabled) return "";
        if (!data.Attack.Enabled)
        {
            if (data.Gameplay.PickPower > 0 || data.Gameplay.AxePower > 0 || data.Gameplay.HammerPower > 0)
            {
                string speed = Math.Abs(data.Gameplay.MiningSpeedScale - 1f) > 0.01f ? $", mine x{Math.Clamp(data.Gameplay.MiningSpeedScale, 0.25f, 2f):0.00}" : "";
                return $"Tool QoL: pick {data.Gameplay.PickPower}, axe {data.Gameplay.AxePower * 5}, hammer {data.Gameplay.HammerPower}{speed}";
            }
            return "";
        }

        string runtime = string.IsNullOrWhiteSpace(data.Attack.RuntimeFamily) ? "generated" : data.Attack.RuntimeFamily.Trim();
        string family = data.Attack.WeaponFamily?.Trim() ?? "";
        string label = string.IsNullOrWhiteSpace(family) ? runtime : $"{runtime} / {family}";
        string impactMobility = ImpactMobilitySummary(data.Attack);
        string swingOnHit = SwingOnHitSummary(data.Attack);
        return $"Generated combat: {label}{impactMobility}{swingOnHit}";
    }

    private static string SwingOnHitSummary(AttackSpec? attack)
    {
        if (attack is null) return "";
        if (!GeneratedRuntimeFamilyPolicy.Is(attack.RuntimeFamily, GeneratedRuntimeFamilyPolicy.Swing)) return "";
        string label = attack.OnHitCode switch
        {
            1 => "impact dust",
            4 => "burn",
            5 => "frostburn",
            6 => "poison",
            7 => "shadowflame",
            9 => "bleed",
            10 => "impact pulse",
            17 => "small lifesteal",
            18 => "overhead barrage",
            _ => "",
        };
        return string.IsNullOrWhiteSpace(label) ? "" : $" · melee {label}";
    }

    private static string ImpactMobilitySummary(AttackSpec? attack)
    {
        if (attack is null) return "";
        string mode = (attack.MobilityMode ?? "").Trim().ToLowerInvariant();
        if (mode != "blink_to_projectile_impact") return "";
        string range = attack.MobilityRangeTiles > 0 ? $", {Math.Clamp(attack.MobilityRangeTiles, 1, 80)}t" : "";
        string cooldown = attack.MobilityCooldownTicks > 0 ? $", {Math.Max(1, (int)Math.Ceiling(attack.MobilityCooldownTicks / 60f))}s cd" : "";
        return $" · impact blink{range}{cooldown}";
    }

    internal static string UseBlockedReason(Player player, GameplaySpec? gp)
    {
        if (gp is null) return "";
        string mode = (gp.UseConditionMode ?? "").Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(mode) || mode == "none") return "";
        if (mode == "grounded" && player.velocity.Y != 0f) return "Need solid ground";
        if (mode == "not_wet" && player.wet) return "Cannot use while wet";
        if (mode == "life_above" && player.statLife < gp.UseConditionMinLife) return $"Need {Math.Max(0, gp.UseConditionMinLife)} life";
        if (mode == "mana_above" && player.statMana < gp.UseConditionMinMana) return $"Need {Math.Max(0, gp.UseConditionMinMana)} mana";
        return "";
    }

    private string UseBlockedReason(Player player) => UseBlockedReason(player, Data?.Gameplay);

    private void ShowLocalUseFeedback(Player player, string message, ref int lastTick, Color color)
    {
        if (string.IsNullOrWhiteSpace(message) || Main.netMode == NetmodeID.Server || player.whoAmI != Main.myPlayer)
            return;
        int tick = (int)Main.GameUpdateCount;
        if (tick - lastTick < 45)
            return;
        lastTick = tick;
        CombatText.NewText(player.Hitbox, color, message);
    }

    public override bool CanUseItem(Player player)
    {
        EnsureRuntimeHydration(player);
        var gp = Data?.Gameplay;
        if (gp is null) return base.CanUseItem(player);

        if (player.altFunctionUse == 2 && HasExecutableAltUse(gp))
        {
            string altMode = (gp.AltUseMode ?? "").Trim().ToLowerInvariant();
            if (altMode == "mobility")
            {
                var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
                if (modPlayer.GeneratedMobilityCooldownTicks > 0)
                {
                    ShowLocalUseFeedback(player, $"Mobility cooldown: {modPlayer.GeneratedMobilityCooldownSeconds}s", ref _lastAltUseBlockedNoticeTick, Color.Orange);
                    return false;
                }
            }
        }
        else if (!string.IsNullOrWhiteSpace(gp.MobilityMode))
        {
            var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
            if (modPlayer.GeneratedMobilityCooldownTicks > 0)
            {
                ShowLocalUseFeedback(player, $"Mobility cooldown: {modPlayer.GeneratedMobilityCooldownSeconds}s", ref _lastUseBlockedNoticeTick, Color.Orange);
                return false;
            }
        }

        string runtimeFamily = AttackRuntimeFamily(Data?.Attack);
        if (GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Beam)
            || GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.ChargeRelease))
        {
            int generatedProjectileType = ModContent.ProjectileType<global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile>();
            for (int i = 0; i < Main.maxProjectiles; i++)
            {
                Projectile active = Main.projectile[i];
                if (!active.active || active.owner != player.whoAmI || active.type != generatedProjectileType)
                    continue;
                if (active.ModProjectile is global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile generated
                    && (generated.IsActiveBeamFor(Data?.Id) || generated.IsActiveChargeFor(Data?.Id)))
                    return false;
            }
        }

        string blocked = UseBlockedReason(player);
        if (!string.IsNullOrWhiteSpace(blocked))
        {
            ShowLocalUseFeedback(player, blocked, ref _lastUseBlockedNoticeTick, Color.Orange);
            return false;
        }
        return base.CanUseItem(player);
    }

    public override bool ConsumeItem(Player player)
    {
        int chance = Data?.Gameplay?.ConsumeChancePercent ?? 100;
        if (chance >= 100) return base.ConsumeItem(player);
        if (chance <= 0) return false;
        return Main.rand.Next(100) < chance;
    }


    public override bool? UseItem(Player player)
    {
        EnsureRuntimeHydration(player);
        var gp = Data?.Gameplay;
        var modPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        bool runLocalAction = InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player);
        bool runPlayerGameplay = InfiniRuntimeAuthority.ShouldRunPlayerGameplay(player);
        bool alt = player.altFunctionUse == 2 && gp is not null && !string.IsNullOrWhiteSpace(gp.AltUseMode);
        if (alt)
        {
            if (Main.netMode == NetmodeID.MultiplayerClient && runLocalAction)
            {
                modPlayer.RequestGeneratedAltUseFromServer(Data?.Id ?? "", alternateUse: true, Main.MouseWorld);
                return true;
            }
            // Dedicated/listen servers execute generated alt effects only through
            // the validated intent packet. Terraria may also call this hook for the
            // same use; running both paths would refresh buffs and emit two syncs.
            if (Main.netMode == NetmodeID.Server)
                return true;
            if (runLocalAction || runPlayerGameplay)
            {
                string mode = (gp!.AltUseMode ?? "").Trim().ToLowerInvariant();
                bool used = false;
                if (runLocalAction && mode == "mobility")
                {
                    used = modPlayer.TryRunGeneratedMobility(gp.AltMobilityMode, gp.AltMobilityRangeTiles, gp.AltMobilityCooldownTicks, gp.AltMobilitySafeTileOnly);
                    if (!used)
                        ShowLocalUseFeedback(player, modPlayer.LastGeneratedMobilityFailureMessage, ref _lastAltUseBlockedNoticeTick, Color.Orange);
                }
                if (runPlayerGameplay && mode == "generated_buff" && gp.AltGeneratedBuff is not null && gp.AltGeneratedBuff.HasAnyEffect)
                {
                    modPlayer.ApplyGeneratedUtilityBuff(gp.AltGeneratedBuff, syncNetwork: Main.netMode == NetmodeID.Server);
                    used = true;
                }
                if (runPlayerGameplay && mode == "light" && gp.AltGeneratedBuff is not null && gp.AltGeneratedBuff.HasAnyEffect)
                {
                    modPlayer.ApplyGeneratedUtilityBuff(gp.AltGeneratedBuff, syncNetwork: Main.netMode == NetmodeID.Server);
                    used = gp.AltGeneratedBuff.EmitLightStrength > 0f;
                }
                return used;
            }
            return true;
        }

        // Vanilla Item.buffType supports only one buff slot. Generated potion/utility items
        // can carry a small explicit ExtraBuffs list so two potion parents do not collapse
        // into one mismatched buffType/buffTime pair. This only executes concrete buff ids
        // already serialized in Gameplay; no prompt text is interpreted here.
        if (runPlayerGameplay && gp?.ExtraBuffs is { Length: > 0 })
        {
            foreach (var buff in gp.ExtraBuffs)
            {
                if (buff is null || buff.BuffCode <= InfiniTerrariaSentinels.NoBuffType || buff.BuffTime <= 0)
                    continue;
                player.AddBuff(buff.BuffCode, buff.BuffTime);
            }
        }
        if (runPlayerGameplay && gp?.GeneratedBuff is not null && gp.GeneratedBuff.HasAnyEffect)
            modPlayer.ApplyGeneratedUtilityBuff(gp.GeneratedBuff, syncNetwork: Main.netMode == NetmodeID.Server);
        if (runLocalAction && gp is not null && !string.IsNullOrWhiteSpace(gp.MobilityMode))
        {
            if (Main.netMode == NetmodeID.MultiplayerClient)
                modPlayer.RequestGeneratedAltUseFromServer(Data?.Id ?? "", alternateUse: false, Main.MouseWorld);
            else
                modPlayer.TryRunGeneratedMobility(gp);
        }
        return base.UseItem(player);
    }

    public override void HoldItem(Player player)
    {
        EnsureRuntimeHydration(player);
        float strength = 0f;
        string colorName = Data?.Attack?.PrimaryColorName ?? "";
        if (Data?.Attack is not null && Data.Attack.RuntimeLightStrength > 0f)
            strength = Math.Max(strength, Math.Clamp(Data.Attack.RuntimeLightStrength, 0.02f, 0.75f) * 0.8f);
        if (Data?.Gameplay is not null && Data.Gameplay.HoldLightStrength > 0f)
        {
            strength = Math.Max(strength, Math.Clamp(Data.Gameplay.HoldLightStrength, 0.02f, 1.5f));
            if (!string.IsNullOrWhiteSpace(Data.Gameplay.HoldLightColorName))
                colorName = Data.Gameplay.HoldLightColorName;
        }
        if (strength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(colorName, Color.White);
            Lighting.AddLight(player.Center, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
        }


        if (Data?.Gameplay?.HoldGeneratedBuff is not null && Data.Gameplay.HoldGeneratedBuff.HasAnyEffect && InfiniRuntimeAuthority.ShouldRunPlayerGameplay(player))
            player.GetModPlayer<InfiniCraftPlayer>().ApplyGeneratedUtilityBuff(Data.Gameplay.HoldGeneratedBuff);

        ApplyAuthoredToolMiningSpeed(player, Data?.Gameplay);
    }

    private static void ApplyAuthoredToolMiningSpeed(Player player, GameplaySpec? gp)
    {
        if (player is null || gp is null)
            return;
        if (gp.PickPower <= 0 && gp.AxePower <= 0 && gp.HammerPower <= 0)
            return;
        float scale = Math.Clamp(gp.MiningSpeedScale <= 0f ? 1f : gp.MiningSpeedScale, 0.25f, 2f);
        if (Math.Abs(scale - 1f) <= 0.001f)
            return;
        // Player.pickSpeed is inverse speed in Terraria: lower values mine faster.
        // miningSpeedScale is authored as intuitive multiplier, so x1.35 divides pickSpeed by 1.35.
        player.pickSpeed /= scale;
    }


    public override void UpdateEquip(Player player)
    {
        EnsureRuntimeHydration(player);
        ApplyGeneratedArmorEffects(player, Data?.Armor);
    }

    private static void ApplyGeneratedArmorEffects(Player player, ArmorSpec? a)
    {
        if (a is null || !a.Enabled)
            return;

        // Defense is carried by Item.defense for armor pieces.  UpdateEquip applies
        // only non-defense modifiers so the stat is not double-counted.
        player.statLifeMax2 += a.MaxLife;
        player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen;
        player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed;
        player.maxRunSpeed += a.MaxRunSpeed;
        player.jumpSpeedBoost += a.JumpSpeed;
        player.GetDamage(DamageClass.Generic) += a.GenericDamage;
        player.GetDamage(DamageClass.Melee) += a.MeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.RangedDamage;
        player.GetDamage(DamageClass.Magic) += a.MagicDamage;
        player.GetDamage(DamageClass.Summon) += a.SummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.GenericCrit;
        player.GetAttackSpeed(DamageClass.Generic) += a.AttackSpeed;
        player.GetKnockback(DamageClass.Generic) += a.Knockback;
        player.maxMinions += a.MinionSlots;
        player.maxTurrets += a.SentrySlots;
        if (a.ManaCostReduction > 0f)
            player.manaCost = Math.Max(0.1f, player.manaCost - a.ManaCostReduction);
        var generatedPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        generatedPlayer.AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
        generatedPlayer.AddGeneratedSummonTagDamage(a.SummonTagDamage);
        player.whipRangeMultiplier += a.WhipRange;
        player.aggro += a.Aggro;
        player.endurance += a.Endurance;
        player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration;
        if (a.FallDamageImmune) player.noFallDmg = true;
        if (a.LavaImmune) player.lavaImmune = true;
        if (a.WaterWalk) player.waterWalk = true;
        if (a.LightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = string.IsNullOrWhiteSpace(a.LightColorName)
                ? Color.White
                : RuntimeColorPolicy.Resolve(a.LightColorName, Color.White);
            float strength = Math.Clamp(a.LightStrength, 0.02f, 1.5f);
            Lighting.AddLight(player.Center, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
        }
    }

    public override bool IsArmorSet(Item head, Item body, Item legs)
    {
        if (Data?.Armor is null || !Data.Armor.Enabled || Data.Armor.Slot != "head" || string.IsNullOrWhiteSpace(Data.Armor.SetKey))
            return false;
        return HasGeneratedArmorSetPiece(head, "head", Data.Armor.SetKey)
            && HasGeneratedArmorSetPiece(body, "body", Data.Armor.SetKey)
            && HasGeneratedArmorSetPiece(legs, "legs", Data.Armor.SetKey);
    }

    private static bool HasGeneratedArmorSetPiece(Item item, string slot, string setKey)
    {
        if (item?.ModItem is not GeneratedItem generated || generated.Data?.Armor is null)
            return false;
        var armor = generated.Data.Armor;
        return armor.Enabled
            && string.Equals(armor.Slot, slot, StringComparison.OrdinalIgnoreCase)
            && string.Equals(armor.SetKey, setKey, StringComparison.OrdinalIgnoreCase);
    }

    public override void UpdateArmorSet(Player player)
    {
        var a = Data?.Armor;
        if (a is null || !a.Enabled || a.Slot != "head")
            return;
        if (!string.IsNullOrWhiteSpace(a.SetBonusText))
            player.setBonus = a.SetBonusText;
        player.GetDamage(DamageClass.Generic) += a.SetBonusGenericDamage;
        player.GetDamage(DamageClass.Melee) += a.SetBonusMeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.SetBonusRangedDamage;
        player.GetDamage(DamageClass.Magic) += a.SetBonusMagicDamage;
        player.GetDamage(DamageClass.Summon) += a.SetBonusSummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.SetBonusGenericCrit;
        player.moveSpeed += a.SetBonusMovementSpeed;
        player.lifeRegen += a.SetBonusLifeRegen;
        player.manaRegenBonus += a.SetBonusManaRegen;
        player.maxMinions += a.SetBonusMinionSlots;
        player.maxTurrets += a.SetBonusSentrySlots;
        if (a.SetBonusManaCostReduction > 0f)
            player.manaCost = Math.Max(0.1f, player.manaCost - a.SetBonusManaCostReduction);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.SetBonusAmmoSaveChance);
        player.aggro += a.SetBonusAggro;
        player.endurance += a.SetBonusEndurance;
        player.GetArmorPenetration(DamageClass.Generic) += a.SetBonusArmorPenetration;
    }

    public override void UpdateAccessory(Player player, bool hideVisual)
    {
        EnsureRuntimeHydration(player);
        if (Data?.Accessory is null || !Data.Accessory.Enabled)
            return;

        var a = Data.Accessory;
        player.statDefense += a.Defense;
        player.statLifeMax2 += a.MaxLife;
        player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen;
        player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed;
        player.maxRunSpeed += a.MaxRunSpeed;
        player.jumpSpeedBoost += a.JumpSpeed;
        player.GetDamage(DamageClass.Generic) += a.GenericDamage;
        player.GetDamage(DamageClass.Melee) += a.MeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.RangedDamage;
        player.GetDamage(DamageClass.Magic) += a.MagicDamage;
        player.GetDamage(DamageClass.Summon) += a.SummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.GenericCrit;
        player.GetAttackSpeed(DamageClass.Generic) += a.AttackSpeed;
        player.GetKnockback(DamageClass.Generic) += a.Knockback;
        player.maxMinions += a.MinionSlots;
        player.maxTurrets += a.SentrySlots;
        if (a.ManaCostReduction > 0f)
            player.manaCost = Math.Max(0.1f, player.manaCost - a.ManaCostReduction);
        var generatedPlayer = player.GetModPlayer<InfiniCraftPlayer>();
        generatedPlayer.AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
        generatedPlayer.AddGeneratedSummonTagDamage(a.SummonTagDamage);
        player.whipRangeMultiplier += a.WhipRange;
        player.aggro += a.Aggro;
        player.endurance += a.Endurance;
        player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration;
        if (a.FallDamageImmune) player.noFallDmg = true;
        if (a.LavaImmune) player.lavaImmune = true;
        if (a.WaterWalk) player.waterWalk = true;
        if (a.LightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(a.LightColorName, Color.White);
            float strength = Math.Clamp(a.LightStrength, 0.02f, 1.5f);
            Lighting.AddLight(player.Center, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
        }
    }

    public override Vector2? HoldoutOffset() => new Vector2(Data.Gameplay.HoldoutOffsetX, Data.Gameplay.HoldoutOffsetY);

    public override void ModifyItemScale(Player player, ref float scale)
    {
        if (Data?.Gameplay is null) return;
        scale *= Math.Clamp(Data.Gameplay.ItemScale, 0.55f, 1.55f);
    }

    public override void UseItemHitbox(Player player, ref Rectangle hitbox, ref bool noHitbox)
    {
        string runtimeFamily = AttackRuntimeFamily(Data.Attack);
        if (!Data.Attack.Enabled
            || (!GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Swing)
                && !GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Thrust)))
            return;

        float scale = Math.Clamp(Math.Max(1f, Data.Attack.HitboxScale), 1f, 1.85f);
        int radiusBonus = MeleeHitboxRadiusBonus(Data.Attack);
        int inflateX = (int)(hitbox.Width * (scale - 1f) * 0.5f) + radiusBonus;
        int inflateY = (int)(hitbox.Height * (scale - 1f) * 0.5f) + radiusBonus;
        if (inflateX > 0 || inflateY > 0)
            hitbox.Inflate(inflateX, inflateY);
    }


    private static int MeleeHitboxRadiusBonus(AttackSpec attack)
    {
        if (attack is null) return 0;
        return attack.ContactForgivenessPx > 0
            ? Math.Clamp(attack.ContactForgivenessPx, 0, 14)
            : 0;
    }

    public override void OnHitNPC(Player player, NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (_applyingGeneratedSwingAoeDamage
            || player.whoAmI != Main.myPlayer
            || Data?.Attack is null
            || !Data.Attack.Enabled)
            return;
        if (!GeneratedRuntimeFamilyPolicy.Is(AttackRuntimeFamily(Data.Attack), GeneratedRuntimeFamilyPolicy.Swing))
            return;
        if (!Data.Attack.RuntimePlanAuthored)
            return;

        if (GeneratedMeleeOnHitEffectsEnabled())
        {
            ApplyGeneratedSwingAoeDamage(player, target, Data.Attack);
            ApplyGeneratedSwingOnHitEffects(player, target, Data.Attack, damageDone, Data.Id);
        }

        // Explicit real secondary projectiles authored by runtimePlan stay allowed for
        // melee-core swings, but only when the planner described an actual secondary
        // body/material. Otherwise a sword/hammer with a purely visual impact role can
        // accidentally become a hidden on-hit projectile weapon.
        if (!HasExplicitSwingSecondaryProjectile(Data.Attack))
            return;

        int count = Math.Clamp(Data.Attack.SplitCount > 0 ? Data.Attack.SplitCount : Data.Attack.MaxChildProjectiles, 0, 3);
        if (count <= 0 || Data.Attack.SecondaryDamageMultiplier <= 0f)
            return;

        int maxChildren = Math.Clamp(Data.Attack.MaxChildProjectiles <= 0 ? count : Data.Attack.MaxChildProjectiles, 0, 4);
        count = Math.Min(count, maxChildren);
        if (count <= 0)
            return;

        float damageMult = Math.Clamp(Data.Attack.SecondaryDamageMultiplier, 0.02f, 0.35f);
        int childDamage = Math.Max(0, (int)Math.Round(Math.Max(0, damageDone) * damageMult));
        float speed = Math.Clamp(Math.Max(4f, Data.Attack.Speed * 0.82f), 3f, 18f);
        float spread = Math.Clamp(Data.Attack.SecondarySpreadRadians > 0f ? Data.Attack.SecondarySpreadRadians : Data.Attack.SpreadRadians, 0f, MathHelper.ToRadians(60f));
        Vector2 baseDir = player.DirectionTo(target.Center);
        if (baseDir.LengthSquared() < 0.01f)
            baseDir = new Vector2(player.direction == 0 ? 1 : player.direction, 0f);

        AttackSpec childSpec = SwingSecondarySpec(Data.Attack);
        for (int i = 0; i < count; i++)
        {
            float offset = count == 1 ? 0f : MathHelper.Lerp(-spread * 0.5f, spread * 0.5f, i / (float)(count - 1));
            Vector2 velocity = baseDir.SafeNormalize(Vector2.UnitX * player.direction).RotatedBy(offset) * speed;
            Vector2 origin = target.Center - baseDir.SafeNormalize(Vector2.UnitX) * 12f;
            int idx = Projectile.NewProjectile(
                player.GetSource_Misc("InfiniCraftSwingSecondary"),
                origin,
                velocity,
                ModContent.ProjectileType<global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile>(),
                childDamage,
                Item.knockBack * 0.35f,
                player.whoAmI,
                childSpec.MovementCode,
                childSpec.EffectCode,
                childSpec.OnHitCode
            );
            if (idx >= 0 && idx < Main.maxProjectiles && Main.projectile[idx].ModProjectile is global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile generatedProjectile)
            {
                Main.projectile[idx].localAI[1] = 1f;
                Main.projectile[idx].localAI[2] = Main.projectile[idx].identity + 1f;
                generatedProjectile.ApplyGeneratedSpec(
                    childSpec,
                    new VfxManifestSpec(),
                    Data.Id,
                    GeneratedProjectileRuntimeVariant.SwingSecondary);
                Main.projectile[idx].netUpdate = true;
                generatedProjectile.BroadcastVisualSync();
            }
        }
    }

    private static bool GeneratedMeleeOnHitEffectsEnabled()
    {
        try { return ModContent.GetInstance<InfiniGameplayQolConfig>()?.EnableGeneratedMeleeOnHitEffects ?? true; }
        catch { return true; }
    }

    private void ApplyGeneratedSwingAoeDamage(Player player, NPC directTarget, AttackSpec attack)
    {
        int radius = Math.Clamp(attack.AoeDamageRadiusPx, 0, 160);
        if (radius <= 0
            || _applyingGeneratedSwingAoeDamage
            || !InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player))
            return;

        Vector2 center = directTarget.Center;
        Rectangle aoeHitbox = new(
            (int)center.X - radius,
            (int)center.Y - radius,
            radius * 2,
            radius * 2);
        int damage = Math.Max(1, player.GetWeaponDamage(Item));
        float knockback = player.GetWeaponKnockback(Item);
        int affectedTargets = 0;

        _applyingGeneratedSwingAoeDamage = true;
        try
        {
            for (int i = 0; i < Main.maxNPCs && affectedTargets < MaxGeneratedAoeTargetsPerHit; i++)
            {
                NPC npc = Main.npc[i];
                if (npc is null
                    || !npc.active
                    || npc.life <= 0
                    || npc.friendly
                    || npc.dontTakeDamage
                    || npc.whoAmI == directTarget.whoAmI
                    || !aoeHitbox.Intersects(npc.Hitbox))
                    continue;

                int hitDirection = npc.Center.X >= center.X ? 1 : -1;
                player.ApplyDamageToNPC(npc, damage, knockback, hitDirection, false, Item.DamageType, false);
                affectedTargets++;
            }
        }
        finally
        {
            _applyingGeneratedSwingAoeDamage = false;
        }
    }

    private static void ApplyGeneratedSwingOnHitEffects(Player player, NPC target, AttackSpec attack, int damageDone, string generatedItemId)
    {
        if (player is null || target is null || attack is null) return;
        int onHit = attack.OnHitCode;
        if (onHit <= 0) return;
        int debuffTime = Math.Clamp(attack.DebuffTime, 0, 600);
        switch (onHit)
        {
            case 1:
                EmitGeneratedSwingImpactDust(target.Center, attack.EffectCode, Math.Min(attack.BurstDustCap, 14), 1.25f);
                break;
            case 4:
                if (debuffTime >= 30) target.AddBuff(BuffID.OnFire, debuffTime);
                EmitGeneratedSwingImpactDust(target.Center, attack.EffectCode, Math.Min(attack.BurstDustCap, 10), 1.05f);
                break;
            case 5:
                if (debuffTime >= 30) target.AddBuff(BuffID.Frostburn, debuffTime);
                EmitGeneratedSwingImpactDust(target.Center, attack.EffectCode, Math.Min(attack.BurstDustCap, 10), 1.05f);
                break;
            case 6:
                if (debuffTime >= 30) target.AddBuff(BuffID.Poisoned, debuffTime);
                EmitGeneratedSwingImpactDust(target.Center, attack.EffectCode, Math.Min(attack.BurstDustCap, 10), 1.05f);
                break;
            case 7:
                if (debuffTime >= 30) target.AddBuff(BuffID.ShadowFlame, debuffTime);
                EmitGeneratedSwingImpactDust(target.Center, attack.EffectCode, Math.Min(attack.BurstDustCap, 12), 1.15f);
                break;
            case 9:
                if (debuffTime >= 30) target.AddBuff(BuffID.Bleeding, debuffTime);
                EmitGeneratedSwingImpactDust(target.Center, 9, Math.Min(attack.BurstDustCap, 8), 1.0f);
                break;
            case 10:
                EmitGeneratedSwingImpactDust(target.Center, attack.EffectCode, Math.Clamp(attack.BurstDustCap, 0, 24), 1.45f);
                break;
            case 17:
                HealGeneratedSwingOwner(player, damageDone);
                EmitGeneratedSwingImpactDust(target.Center, attack.EffectCode, Math.Min(attack.BurstDustCap, 8), 1.0f);
                break;
            case 18:
                SpawnGeneratedSwingOverheadBarrage(player, target, attack, damageDone, generatedItemId);
                break;
        }
    }



    private static void HealGeneratedSwingOwner(Player player, int damageDone)
    {
        if (player is null || !player.active || player.dead) return;
        int heal = Math.Clamp(Math.Max(1, damageDone / 5), 1, 4);
        if (player.statLife >= player.statLifeMax2) return;
        player.Heal(heal);
    }

    private static void SpawnGeneratedSwingOverheadBarrage(Player player, NPC target, AttackSpec attack, int damageDone, string generatedItemId)
    {
        if (player is null || target is null || attack is null) return;
        if (player.whoAmI != Main.myPlayer) return;
        int requested = Math.Max(0, attack.SplitCount > 0 ? attack.SplitCount : attack.MaxChildProjectiles);
        int cap = Math.Clamp(attack.MaxChildProjectiles > 0 ? attack.MaxChildProjectiles : requested, 0, 8);
        int count = Math.Min(requested, cap);
        if (count <= 0 || attack.SecondaryDamageMultiplier <= 0f) return;

        AttackSpec childSpec = SwingSecondarySpec(attack);
        GeneratedOverheadBarragePolicy.ConfigureChild(childSpec, attack);
        float damageMult = Math.Clamp(attack.SecondaryDamageMultiplier, 0f, 1f);
        int childDamage = Math.Max(0, (int)Math.Round(Math.Max(0, damageDone) * damageMult));
        float rootId = Main.rand.Next(1, 1_000_000);

        for (int i = 0; i < count; i++)
        {
            (Vector2 origin, Vector2 velocity) = GeneratedOverheadBarragePolicy.Sample(
                target.Center,
                i,
                count,
                attack.SecondarySpreadRadians,
                childSpec.Speed);
            int idx = Projectile.NewProjectile(
                player.GetSource_Misc("InfiniCraftSwingOverheadBarrage"),
                origin,
                velocity,
                ModContent.ProjectileType<global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile>(),
                childDamage,
                0.35f,
                player.whoAmI,
                childSpec.MovementCode,
                childSpec.EffectCode,
                childSpec.OnHitCode
            );
            if (idx >= 0 && idx < Main.maxProjectiles && Main.projectile[idx].ModProjectile is global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile generatedProjectile)
            {
                Main.projectile[idx].localAI[1] = 1f;
                Main.projectile[idx].localAI[2] = rootId;
                generatedProjectile.ApplyGeneratedSpec(
                    childSpec,
                    new VfxManifestSpec(),
                    generatedItemId,
                    GeneratedProjectileRuntimeVariant.SwingOverheadSecondary);
                Main.projectile[idx].netUpdate = true;
                generatedProjectile.BroadcastVisualSync();
            }
        }
    }

    private static void EmitGeneratedSwingImpactDust(Vector2 center, int effectCode, int requestedCount, float speedScale)
    {
        if (Main.netMode == NetmodeID.Server) return;
        int dustType = GeneratedSwingDustType(effectCode);
        int count = Math.Clamp(requestedCount, 0, 24);
        for (int i = 0; i < count; i++)
        {
            Vector2 velocity = Vector2.UnitX.RotatedBy(MathHelper.TwoPi * i / Math.Max(1, count)) * Main.rand.NextFloat(0.8f, 2.2f) * Math.Clamp(speedScale, 0.4f, 2.5f);
            int idx = Dust.NewDust(center - new Vector2(4f, 4f), 8, 8, dustType, velocity.X, velocity.Y, 120, default(Color), Main.rand.NextFloat(0.75f, 1.25f));
            if (idx >= 0 && idx < Main.maxDust)
                Main.dust[idx].noGravity = true;
        }
    }

    private static int GeneratedSwingDustType(int effectCode)
    {
        return effectCode switch
        {
            1 => DustID.Electric,
            2 => DustID.t_Slime,
            3 => DustID.YellowStarDust,
            4 => DustID.Torch,
            5 => DustID.Ice,
            6 => DustID.Grass,
            7 => DustID.Shadowflame,
            8 => DustID.GreenTorch,
            9 => DustID.RedTorch,
            10 => DustID.YellowTorch,
            11 => DustID.Sand,
            12 => DustID.PinkTorch,
            13 => DustID.GemSapphire,
            14 => DustID.PurpleTorch,
            _ => DustID.Smoke,
        };
    }

    private static bool HasExplicitSwingSecondaryProjectile(AttackSpec attack)
    {
        return !string.IsNullOrWhiteSpace(attack.SecondaryProjectileShape)
            || !string.IsNullOrWhiteSpace(attack.SecondaryMaterial);
    }

    private static AttackSpec SwingSecondarySpec(AttackSpec parent)
        => GeneratedChildSpecPolicy.CreateSwingSecondary(parent);

    public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
    {
        if (!Data.Attack.Enabled) return false;
        Vector2 safeVelocity = velocity.LengthSquared() < 0.01f
            ? Vector2.UnitX.RotatedBy(player.direction == -1 ? MathHelper.Pi : 0) * Data.Attack.Speed
            : velocity.SafeNormalize(Vector2.UnitX * player.direction) * Data.Attack.Speed;

        if (!Data.Attack.RuntimePlanAuthored)
            return false;

        string runtimeFamily = AttackRuntimeFamily(Data.Attack);
        // v0.4.109: a broadsword/axe/hammer swing is melee-core by default.
        // Optional acorn/seed/shard emissions come from explicit secondary calls
        // handled in OnHitNPC; do not materialize the held weapon as a flying sword.
        if (GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Swing))
            return false;
        bool thrustLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Thrust);
        bool chargeReleaseLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.ChargeRelease);
        bool sentryLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Sentry);
        bool beamLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Beam);
        bool overheadBarrage = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.OverheadBarrage);
        if (sentryLike)
            return ShootGeneratedSentry(player, source, damage, knockback);
        bool singleRuntime = IsSingleRuntimeProjectileFamily(runtimeFamily);
        int shots = singleRuntime ? 1 : Math.Clamp(Data.Attack.ShotCount, 1, 9);
        float spread = singleRuntime ? 0f : Math.Clamp(Data.Attack.SpreadRadians, 0f, MathHelper.ToRadians(60f));
        bool lob = Data.Attack.MovementCode == 2 || Data.Attack.Movement == "gravity_arc";

        for (int i = 0; i < shots; i++)
        {
            float offset = shots == 1 ? 0f : MathHelper.Lerp(-spread * 0.5f, spread * 0.5f, i / (float)(shots - 1));
            Vector2 shotVelocity = overheadBarrage ? Vector2.Zero : safeVelocity.RotatedBy(offset);
            if (lob && !overheadBarrage) shotVelocity.Y -= Math.Max(1.2f, Data.Attack.Speed * 0.18f);
            Vector2 spawnPosition = overheadBarrage
                ? OverheadBarrageTarget(player, position, safeVelocity, Data.Attack.RangeTiles)
                : ((thrustLike || beamLike || chargeReleaseLike) ? player.MountedCenter : position);
            int projectileIndex = Projectile.NewProjectile(
                source,
                spawnPosition,
                shotVelocity,
                ModContent.ProjectileType<global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile>(),
                damage,
                knockback,
                player.whoAmI,
                Data.Attack.MovementCode,
                Data.Attack.EffectCode,
                Data.Attack.OnHitCode
            );

            if (projectileIndex >= 0 && projectileIndex < Main.maxProjectiles && Main.projectile[projectileIndex].ModProjectile is global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile generatedProjectile)
            {
                // Vanilla-style combat: the projectile carries only a generated item id
                // plus compact AI state. The full GeneratedItemData/VFX manifest was synced
                // once when the item entered the world/registry.
                generatedProjectile.ApplyGeneratedSpec(Data.Attack, Data.VfxManifest, Data.Id);
                Main.projectile[projectileIndex].netUpdate = true;
                generatedProjectile.BroadcastVisualSync();
            }
        }
        return false;
    }

    private static string AttackRuntimeFamily(AttackSpec? attack)
        => GeneratedRuntimeFamilyPolicy.Normalize(attack?.RuntimeFamily);

    private static bool IsSingleRuntimeProjectileFamily(string runtimeFamily)
        => GeneratedRuntimeFamilyPolicy.UsesHeldProjectile(runtimeFamily)
            || GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.OverheadBarrage)
            || GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Sentry);

    private static Vector2 OverheadBarrageTarget(Player player, Vector2 fallbackOrigin, Vector2 fallbackVelocity, float rangeTiles)
    {
        Vector2 origin = player.MountedCenter;
        Vector2 requested = player.whoAmI == Main.myPlayer
            ? Main.MouseWorld
            : fallbackOrigin + fallbackVelocity.SafeNormalize(Vector2.UnitX * player.direction) * Math.Clamp(rangeTiles * 16f, 64f, 1920f);
        Vector2 delta = requested - origin;
        float maxRange = Math.Clamp(rangeTiles > 0f ? rangeTiles * 16f : 560f, 64f, 1920f);
        if (delta.LengthSquared() > maxRange * maxRange)
            requested = origin + delta.SafeNormalize(Vector2.UnitX * player.direction) * maxRange;
        return requested;
    }

    // Experimental runtime inventory drawing. If it causes compile/API issues on your tML build,
    // comment this method out; generated items will still function with the placeholder texture.
    public override bool PreDrawInInventory(SpriteBatch spriteBatch, Vector2 position, Rectangle frame, Color drawColor, Color itemColor, Vector2 origin, float scale)
    {
        EnsureRuntimeHydration();
        GeneratedItemData drawData = ResolveRuntimeDataForPresentation();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(drawData.Visual.SpritePath);
        if (texture is null) return true;
        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        var drawOrigin = source.Size() / 2f;
        float finalScale = scale * Math.Clamp(drawData.Visual.InventoryScale, 0.55f, 1.55f);
        Vector2 finalPos = position + new Vector2(drawData.Visual.DrawOffsetX, drawData.Visual.DrawOffsetY);
        spriteBatch.Draw(texture, finalPos, source, drawColor, 0f, drawOrigin, finalScale, SpriteEffects.None, 0f);
        return false;
    }

    public override bool PreDrawInWorld(SpriteBatch spriteBatch, Color lightColor, Color alphaColor, ref float rotation, ref float scale, int whoAmI)
    {
        EnsureRuntimeHydration();
        GeneratedItemData drawData = ResolveRuntimeDataForPresentation();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(drawData.Visual.SpritePath);
        if (texture is null) return true;
        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        var drawOrigin = source.Size() / 2f;
        float finalScale = scale * Math.Clamp(drawData.Visual.WorldScale, 0.55f, 1.75f);
        Vector2 drawPosition = Item.Bottom - Main.screenPosition - new Vector2(0, drawOrigin.Y * finalScale);
        drawPosition += new Vector2(drawData.Visual.DrawOffsetX, drawData.Visual.DrawOffsetY);
        spriteBatch.Draw(texture, drawPosition, source, lightColor, rotation, drawOrigin, finalScale, SpriteEffects.None, 0f);
        return false;
    }
}
