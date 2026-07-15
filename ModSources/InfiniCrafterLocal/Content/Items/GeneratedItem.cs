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
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedItem";
    protected override bool CloneNewInstances => true;
    public GeneratedItemData Data { get; private set; } = GeneratedItemData.Placeholder();
    private static int _lowNoiseWarningCount;
    private int _lastUseBlockedNoticeTick = -9999;
    private int _lastAltUseBlockedNoticeTick = -9999;
    private int _lastRuntimeHydrationTouchTick = -9999;

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
        if (!string.IsNullOrWhiteSpace(visual.VisualSoulTooltip) && VisualSoulAuraEligible(data))
            tooltips.Add(new TooltipLine(Mod, "InfiniVisualSoul", visual.VisualSoulTooltip) { OverrideColor = VisualSoulColor(data, Color.LightCyan) });
        if (armor.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniArmor", ArmorSummary()) { OverrideColor = Color.LightSteelBlue });
        if (accessory.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniAccessory", AccessorySummary()) { OverrideColor = Color.LightGreen });
        string altSummary = AltUseSummary();
        if (!string.IsNullOrWhiteSpace(altSummary))
            tooltips.Add(new TooltipLine(Mod, "InfiniAltUse", altSummary) { OverrideColor = Color.LightGoldenrodYellow });
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
            tooltips.Add(new TooltipLine(Mod, "InfiniSpriteStatus", $"Sprite: {visual.SpriteStatus} score {visual.VisualJudgeScore:0.00}") { OverrideColor = Color.DarkGray });
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
        string kind = (data.Gameplay.Kind ?? data.Category ?? "").Trim().ToLowerInvariant();
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
        if (a.WhipRange != 0f) parts.Add($"whip range {a.WhipRange * 100f:0}% future");
        if (a.SummonTagDamage != 0f) parts.Add($"tag dmg {a.SummonTagDamage * 100f:0}% future");
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
            return !string.IsNullOrWhiteSpace(gp.AltMobilityMode) || gp.AltMobilityRangeTiles > 0;
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
            return prefix + "generated utility buff";
        if (mode == "light")
            return prefix + $"light pulse ({AltLightStrength(gp):0.00})";
        return prefix + mode;
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

    private string UseBlockedReason(Player player)
    {
        var gp = Data?.Gameplay;
        if (gp is null) return "";
        string mode = (gp.UseConditionMode ?? "").Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(mode) || mode == "none") return "";
        if (mode == "grounded" && player.velocity.Y != 0f) return "Need solid ground";
        if (mode == "not_wet" && player.wet) return "Cannot use while wet";
        if (mode == "life_above" && player.statLife < gp.UseConditionMinLife) return $"Need {Math.Max(0, gp.UseConditionMinLife)} life";
        if (mode == "mana_above" && player.statMana < gp.UseConditionMinMana) return $"Need {Math.Max(0, gp.UseConditionMinMana)} mana";
        return "";
    }

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
                    modPlayer.ApplyGeneratedUtilityBuff(gp.AltGeneratedBuff);
                    used = true;
                }
                if (runPlayerGameplay && mode == "light" && gp.AltGeneratedBuff is not null && gp.AltGeneratedBuff.HasAnyEffect)
                {
                    modPlayer.ApplyGeneratedUtilityBuff(gp.AltGeneratedBuff);
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
            modPlayer.ApplyGeneratedUtilityBuff(gp.GeneratedBuff);
        if (runLocalAction && gp is not null)
            modPlayer.TryRunGeneratedMobility(gp);
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

        float soulGlow = VisualSoulGlow(Data) * 0.72f;
        if (soulGlow > 0.04f && Main.netMode != NetmodeID.Server)
        {
            Color c = VisualSoulColor(Data, RuntimeColorPolicy.Resolve(colorName, Color.White));
            Lighting.AddLight(player.Center, c.R / 255f * soulGlow, c.G / 255f * soulGlow, c.B / 255f * soulGlow);
            if (Main.rand.Next(100) < Math.Clamp((int)(soulGlow * 16f), 1, 14))
                SpawnSoulDust(player.Center + new Vector2(Main.rand.Next(-10, 11), Main.rand.Next(-20, 9)), c, 0.45f + soulGlow * 0.55f);
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

    public override void Update(ref float gravity, ref float maxFallSpeed)
    {
        float glow = VisualSoulGlow(Data) * 0.48f;
        if (glow <= 0.035f || Main.netMode == NetmodeID.Server)
            return;
        Color c = VisualSoulColor(Data, Color.White);
        Lighting.AddLight(Item.Center, c.R / 255f * glow, c.G / 255f * glow, c.B / 255f * glow);
        if (Main.rand.Next(120) < Math.Clamp((int)(glow * 10f), 1, 8))
            SpawnSoulDust(Item.Center + new Vector2(Main.rand.Next(-8, 9), Main.rand.Next(-8, 9)), c, 0.35f + glow * 0.45f);
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
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
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
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
        player.aggro += a.Aggro;
        player.endurance += a.Endurance;
        player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration;
        if (a.FallDamageImmune) player.noFallDmg = true;
        if (a.LavaImmune) player.lavaImmune = true;
        if (a.WaterWalk) player.waterWalk = true;
        if (a.LightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = string.IsNullOrWhiteSpace(a.LightColorName)
                ? VisualSoulColor(Data, Color.White)
                : RuntimeColorPolicy.Resolve(a.LightColorName, Color.White);
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
        if (player.whoAmI != Main.myPlayer || Data?.Attack is null || !Data.Attack.Enabled)
            return;
        if (!GeneratedRuntimeFamilyPolicy.Is(AttackRuntimeFamily(Data.Attack), GeneratedRuntimeFamilyPolicy.Swing))
            return;
        if (!Data.Attack.RuntimePlanAuthored)
            return;

        if (GeneratedMeleeOnHitEffectsEnabled())
            ApplyGeneratedSwingOnHitEffects(player, target, Data.Attack, damageDone, Data.Id);

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
        int childDamage = Math.Max(1, (int)Math.Round(Math.Max(1, damageDone) * damageMult));
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
                generatedProjectile.ApplyGeneratedSpec(childSpec, new VfxManifestSpec(), Data.Id);
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
        if (count <= 0) return;

        AttackSpec childSpec = SwingSecondarySpec(attack);
        GeneratedOverheadBarragePolicy.ConfigureChild(childSpec, attack);
        float damageMult = Math.Max(0.12f, attack.SecondaryDamageMultiplier <= 0f ? 0.42f : attack.SecondaryDamageMultiplier);
        int childDamage = Math.Max(1, (int)Math.Round(Math.Max(1, damageDone) * damageMult));
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
                generatedProjectile.ApplyGeneratedSpec(childSpec, new VfxManifestSpec(), generatedItemId);
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
    {
        int size = Math.Max(8, (int)Math.Round(Math.Min(parent.ProjectileWidth, parent.ProjectileHeight) * 0.55f));
        string material = string.IsNullOrWhiteSpace(parent.SecondaryMaterial) ? "material" : parent.SecondaryMaterial.Trim();
        string shape = string.IsNullOrWhiteSpace(parent.SecondaryProjectileShape)
            ? (material + " shard")
            : parent.SecondaryProjectileShape.Trim();
        return new AttackSpec
        {
            Enabled = true,
            RuntimePlanAuthored = true,
            RuntimeFamily = GeneratedRuntimeFamilyPolicy.Shoot,
            Delivery = "shoot",
            WeaponFamily = "secondary_projectile",
            ProjectileFamily = "secondary_projectile",
            Movement = "straight",
            MovementCode = 0,
            Effect = parent.Effect,
            EffectCode = parent.EffectCode,
            OnHit = "none",
            OnHitCode = 0,
            Speed = Math.Max(3f, parent.Speed * 0.82f),
            Lifetime = Math.Clamp(parent.SecondaryLifetimeTicks <= 0 ? 24 : parent.SecondaryLifetimeTicks, 6, 120),
            Pierce = 1,
            ProjectileWidth = size,
            ProjectileHeight = size,
            ProjectileScale = Math.Clamp(parent.ProjectileScale * 0.58f, 0.45f, 1.15f),
            HitboxScale = 1f,
            TileCollide = true,
            ExtraUpdates = Math.Min(1, parent.ExtraUpdates),
            ShotCount = 1,
            SplitCount = 0,
            MaxChildProjectiles = 0,
            MaxChildDepth = 0,
            DustSpawnDenom = Math.Max(4, parent.DustSpawnDenom + 1),
            BurstDustCap = Math.Max(0, parent.BurstDustCap / 2),
            SecondaryDamageMultiplier = 0f,
            SecondaryMaterial = material,
            SecondaryProjectileShape = shape,
            ProjectileShape = shape,
            ProjectileMotion = "short emitted shard from melee hit",
            ProjectileTrail = parent.ProjectileTrail,
            ProjectileImpact = parent.ProjectileImpact,
            PrimaryColorName = parent.PrimaryColorName,
            SoundUseCatalogId = parent.SoundUseCatalogId,
            SoundImpactCatalogId = parent.SoundImpactCatalogId,
            SoundCatalogSource = parent.SoundCatalogSource,
            SoundPitch = parent.SoundPitch,
            SoundVolume = parent.SoundVolume,
            SoundPitchVariance = parent.SoundPitchVariance,
            ProjectileSpritePath = parent.ChildSpritePath,
            ProjectileSpriteUrl = parent.ChildSpriteUrl,
            ProjectileSpriteStatus = parent.ChildSpriteStatus,
            ProjectileSpritePrompt = "",
            ProjectileSpriteScore = parent.ChildSpriteScore,
            ImpactSpritePath = parent.ImpactSpritePath,
            ImpactSpriteUrl = parent.ImpactSpriteUrl,
            ImpactSpriteStatus = parent.ImpactSpriteStatus,
            ImpactSpritePrompt = "",
            ImpactSpriteScore = parent.ImpactSpriteScore,
        };
    }

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
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(Data.Visual.SpritePath);
        if (texture is null) return true;
        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        var drawOrigin = source.Size() / 2f;
        float finalScale = scale * Math.Clamp(Data.Visual.InventoryScale, 0.55f, 1.55f);
        Vector2 finalPos = position + new Vector2(Data.Visual.DrawOffsetX, Data.Visual.DrawOffsetY);
        DrawSoulGlow(spriteBatch, texture, finalPos, source, drawOrigin, finalScale, 0f, SpriteEffects.None, Data, 0.72f);
        spriteBatch.Draw(texture, finalPos, source, DrawColorWithSoul(drawColor, Data, 0.18f), 0f, drawOrigin, finalScale, SpriteEffects.None, 0f);
        return false;
    }

    public override bool PreDrawInWorld(SpriteBatch spriteBatch, Color lightColor, Color alphaColor, ref float rotation, ref float scale, int whoAmI)
    {
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(Data.Visual.SpritePath);
        if (texture is null) return true;
        var source = new Rectangle(0, 0, texture.Width, texture.Height);
        var drawOrigin = source.Size() / 2f;
        float finalScale = scale * Math.Clamp(Data.Visual.WorldScale, 0.55f, 1.75f);
        Vector2 drawPosition = Item.Bottom - Main.screenPosition - new Vector2(0, drawOrigin.Y * finalScale);
        drawPosition += new Vector2(Data.Visual.DrawOffsetX, Data.Visual.DrawOffsetY);
        DrawSoulGlow(spriteBatch, texture, drawPosition, source, drawOrigin, finalScale, rotation, SpriteEffects.None, Data, 1.0f);
        spriteBatch.Draw(texture, drawPosition, source, DrawColorWithSoul(lightColor, Data, 0.24f), rotation, drawOrigin, finalScale, SpriteEffects.None, 0f);
        return false;
    }

    public static void AddSoulDrawData(List<DrawData> cache, Texture2D texture, Vector2 position, Rectangle source, Color drawColor, float rotation, Vector2 origin, float scale, SpriteEffects effects, GeneratedItemData? data, float glowBias = 1f)
    {
        if (cache is null || texture is null) return;
        float glow = VisualSoulGlow(data) * Math.Clamp(glowBias, 0f, 2f);
        if (glow > 0.025f)
        {
            Color c = VisualSoulColor(data, Color.White);
            float phase = SoulPhase(data);
            float pulse = 1f + MathF.Sin(Main.GlobalTimeWrappedHourly * (3.5f + VisualSoulPulse(data) * 4.5f) + phase) * (0.035f + VisualSoulPulse(data) * 0.055f);
            Color glowColor = c * Math.Clamp(0.10f + glow * 0.24f, 0f, 0.42f);
            cache.Add(new DrawData(texture, position, source, glowColor, rotation, origin, scale * (1.16f * pulse), effects, 0));
            if (glow > 0.35f)
                cache.Add(new DrawData(texture, position, source, c * Math.Clamp(glow * 0.10f, 0f, 0.25f), rotation, origin, scale * (1.34f * pulse), effects, 0));
        }
        cache.Add(new DrawData(texture, position, source, DrawColorWithSoul(drawColor, data, 0.18f), rotation, origin, scale, effects, 0));
    }

    private static void DrawSoulGlow(SpriteBatch spriteBatch, Texture2D texture, Vector2 position, Rectangle source, Vector2 origin, float scale, float rotation, SpriteEffects effects, GeneratedItemData? data, float glowBias)
    {
        float glow = VisualSoulGlow(data) * Math.Clamp(glowBias, 0f, 2f);
        if (glow <= 0.025f) return;
        Color c = VisualSoulColor(data, Color.White);
        float phase = SoulPhase(data);
        float pulse = 1f + MathF.Sin(Main.GlobalTimeWrappedHourly * (3.5f + VisualSoulPulse(data) * 4.5f) + phase) * (0.035f + VisualSoulPulse(data) * 0.055f);
        Color glowColor = c * Math.Clamp(0.10f + glow * 0.24f, 0f, 0.42f);
        spriteBatch.Draw(texture, position, source, glowColor, rotation, origin, scale * (1.16f * pulse), effects, 0f);
        if (glow > 0.35f)
            spriteBatch.Draw(texture, position, source, c * Math.Clamp(glow * 0.10f, 0f, 0.25f), rotation, origin, scale * (1.34f * pulse), effects, 0f);
    }

    private static Color DrawColorWithSoul(Color baseColor, GeneratedItemData? data, float amount)
    {
        float glow = VisualSoulGlow(data);
        if (glow <= 0.025f) return baseColor;
        return Color.Lerp(baseColor, VisualSoulColor(data, baseColor), Math.Clamp(amount * glow, 0f, 0.35f));
    }

    public static bool VisualSoulAuraEligible(GeneratedItemData? data)
    {
        if (data is null) return false;
        int depth = Math.Max(0, data.RecipeMeta?.GenerationDepth ?? 0);
        if (depth >= 6) return true;
        if (depth < 3) return false;
        return IsLateGameVisualSoulCandidate(data);
    }

    private static bool IsLateGameVisualSoulCandidate(GeneratedItemData data)
    {
        string stage = ((data.Gameplay?.Stage ?? data.Attack?.Stage ?? "") + " " + (data.Attack?.Stage ?? "")).Trim().ToLowerInvariant();
        if (stage.Contains("post_moonlord") || stage.Contains("moonlord") || stage.Contains("moon_lord")
            || stage.Contains("superboss") || stage.Contains("endgame") || stage.Contains("lunar")
            || stage.Contains("post_golem"))
            return true;

        int rarity = data.Gameplay?.Rarity ?? ItemRarityID.White;
        float power = Math.Max(data.Gameplay?.PowerBudget ?? 0f, data.Attack?.PowerBudget ?? 0f);
        int value = data.Gameplay?.Value ?? 0;
        return rarity >= 9 || power >= 3.0f || value >= 20000;
    }

    public static float VisualSoulAuraGlow(GeneratedItemData? data)
    {
        if (!VisualSoulAuraEligible(data)) return 0f;
        return VisualSoulGlow(data);
    }

    private static float VisualSoulGlow(GeneratedItemData? data)
    {
        if (!VisualSoulAuraEligible(data)) return 0f;
        float authored = data?.Visual?.VisualSoulGlow ?? 0f;
        if (authored > 0f) return Math.Clamp(authored, 0f, 1f);
        float judge = Math.Clamp(data?.Visual?.VisualJudgeScore ?? 0f, 0f, 1f);
        bool hasSprite = !string.IsNullOrWhiteSpace(data?.Visual?.SpritePath);
        bool vfx = data?.VfxManifest is not null && data.VfxManifest.HasSlots;
        return Math.Clamp((hasSprite ? 0.10f : 0f) + judge * 0.18f + (vfx ? 0.12f : 0f), 0f, 0.55f);
    }

    private static float VisualSoulPulse(GeneratedItemData? data)
        => Math.Clamp(data?.Visual?.VisualSoulPulse ?? 0.25f, 0f, 1f);

    public static Color VisualSoulColor(GeneratedItemData? data, Color fallback)
    {
        Color c = ColorFromHex(data?.Visual?.AccentColorHex, Color.Transparent);
        if (c.A > 0) return c;
        c = ColorFromHex(data?.Visual?.DominantColorHex, Color.Transparent);
        if (c.A > 0) return c;
        return fallback;
    }

    private static Color ColorFromHex(string? raw, Color fallback)
    {
        string s = (raw ?? "").Trim();
        if (s.StartsWith("#", StringComparison.Ordinal)) s = s[1..];
        if (s.Length != 6) return fallback;
        try
        {
            int r = Convert.ToInt32(s[0..2], 16);
            int g = Convert.ToInt32(s[2..4], 16);
            int b = Convert.ToInt32(s[4..6], 16);
            return new Color(r, g, b);
        }
        catch { return fallback; }
    }

    private static float SoulPhase(GeneratedItemData? data)
    {
        unchecked
        {
            string key = data?.Visual?.VisualSoulSignature ?? data?.Id ?? "";
            int h = 23;
            foreach (char c in key) h = h * 31 + c;
            uint uh = (uint)h;
            return (uh % 1024u) / 1024f * MathHelper.TwoPi;
        }
    }

    private static void SpawnSoulDust(Vector2 position, Color color, float scale)
    {
        if (Main.netMode == NetmodeID.Server) return;
        float angle = Main.rand.Next(628) / 100f;
        float speed = 0.15f + (float)Main.rand.NextDouble() * 0.85f;
        Vector2 velocity = new Vector2((float)Math.Cos(angle), (float)Math.Sin(angle)) * speed;
        int idx = Dust.NewDust(position, 2, 2, DustID.Torch, velocity.X, velocity.Y, 150, color, Math.Clamp(scale, 0.25f, 1.25f));
        if (idx >= 0 && idx < Main.maxDust)
        {
            Main.dust[idx].noGravity = true;
            Main.dust[idx].velocity *= 0.55f;
        }
    }
}
