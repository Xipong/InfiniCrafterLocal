#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
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

/// <summary>
/// One proxy ModItem for many generated instances. Runtime behaviour is selected
/// exclusively by the accepted RuntimeProgramSpec binding/entity/component/event
/// graph. Display name, tooltip, category and parent prose never route gameplay.
/// </summary>
public partial class GeneratedItem : ModItem
{
    private const int GeneratedItemNetPayloadVersion = 5;
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedItem";
    protected override bool CloneNewInstances => true;
    public GeneratedItemData Data { get; private set; } = GeneratedItemData.Placeholder();
    private static int _warningCount;
    private int _lastHydrationTick = -9999;
    private int _lastBlockedNoticeTick = -9999;
    private int _itemEventSpawnBudget;

    private static void Warn(string context, Exception ex)
    {
        if (_warningCount++ >= 8) return;
        try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn($"[GeneratedItem] {context}: {ex.GetType().Name}: {ex.Message}"); }
        catch { }
    }

    public override ModItem Clone(Item newEntity)
    {
        var clone = (GeneratedItem)base.Clone(newEntity);
        try { clone.Data = GeneratedItemData.FromJson((Data ?? GeneratedItemData.Placeholder()).ToNetworkJson()) ?? GeneratedItemData.Placeholder(); }
        catch { clone.Data = GeneratedItemData.Placeholder(); }
        return clone;
    }

    public void SetData(GeneratedItemData data) => SetData(data, ensureAssets: true, registerLocal: true);

    private void SetData(GeneratedItemData data, bool ensureAssets, bool registerLocal, bool notifyNetState = true)
    {
        Data = data ?? GeneratedItemData.Placeholder();
        try { Data.ApplyToItem(Item); }
        catch (Exception ex)
        {
            Warn($"ApplyToItem failed for '{Data.Id}'", ex);
            Data = GeneratedItemData.Placeholder();
            try { Data.ApplyToItem(Item); } catch { }
        }
        if (registerLocal)
        {
            try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RegisterLocal(Data, ensureAssets: ensureAssets); }
            catch (Exception ex) { Warn($"RegisterLocal failed for '{Data.Id}'", ex); }
        }
        if (notifyNetState && registerLocal && Main.netMode != NetmodeID.SinglePlayer)
            try { Item.NetStateChanged(); } catch { }
    }

    public override void SetDefaults()
    {
        Data ??= GeneratedItemData.Placeholder();
        try { Data.ApplyToItem(Item); }
        catch
        {
            Data = GeneratedItemData.Placeholder();
            try { Data.ApplyToItem(Item); } catch { }
        }
    }

    public override void SaveData(TagCompound tag)
    {
        try { tag["infiniJson"] = (Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson(); }
        catch { tag["infiniJson"] = GeneratedItemData.Placeholder().ToPlayerSaveJson(); }
    }

    public override void LoadData(TagCompound tag)
    {
        try
        {
            string json = tag is not null && tag.ContainsKey("infiniJson") ? tag.GetString("infiniJson") ?? "" : "";
            SetData(GeneratedItemData.FromPlayerSaveJson(json) ?? GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false);
        }
        catch { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false); }
    }

    public override void NetSend(BinaryWriter writer)
    {
        writer.Write(GeneratedItemNetPayloadVersion);
        try { writer.Write((Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson()); }
        catch { writer.Write(GeneratedItemData.Placeholder().ToPlayerSaveJson()); }
    }

    public override void NetReceive(BinaryReader reader)
    {
        try
        {
            int version = reader.ReadInt32();
            if (version != GeneratedItemNetPayloadVersion)
                throw new InvalidDataException($"Unsupported generated item payload {version}");
            GeneratedItemData reference = GeneratedItemData.FromPlayerSaveJson(reader.ReadString()) ?? GeneratedItemData.Placeholder();
            GeneratedItemData resolved = reference;
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (!string.IsNullOrWhiteSpace(reference.Id) && registry is not null && registry.TryGet(reference.Id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical))
                resolved = canonical;
            SetData(resolved, ensureAssets: false, registerLocal: false, notifyNetState: false);
            EnsureRuntimeHydration();
        }
        catch { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false); }
    }

    private void EnsureRuntimeHydration(Player? player = null)
    {
        string id = (Data?.Id ?? "").Trim();
        if (id.Length == 0 || id == "placeholder") return;
        int now = (int)Main.GameUpdateCount;
        if (now - _lastHydrationTick < 90) return;
        _lastHydrationTick = now;
        try
        {
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (registry is null) return;
            if (registry.TryGet(id, out var canonical))
            {
                if (GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                    SetData(canonical, ensureAssets: false, registerLocal: false, notifyNetState: false);
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(canonical, forceRetry: false);
            }
            else if (Main.netMode == NetmodeID.MultiplayerClient)
                registry.RequestOneFromServer(id, forceAssetRetry: false);
            else if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                registry.RegisterLocal(Data, persist: false, ensureAssets: true);
        }
        catch (Exception ex) { Warn($"Runtime hydration failed for '{id}'", ex); }
    }

    private GeneratedItemData PresentationData()
    {
        if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data)) return Data;
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        return registry is not null && registry.TryGet(Data.Id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical)
            ? canonical : Data;
    }

    public override bool CanStack(Item source)
        => source.ModItem is GeneratedItem other
            && string.Equals(Data.Id, other.Data.Id, StringComparison.Ordinal)
            && string.Equals(Data.RecipeKey, other.Data.RecipeKey, StringComparison.Ordinal);

    public override void ModifyTooltips(List<TooltipLine> tooltips)
    {
        EnsureRuntimeHydration();
        GeneratedItemData data = PresentationData();
        tooltips.Add(new TooltipLine(Mod, "InfiniParents", $"Forged from {data.ParentA} + {data.ParentB}") { OverrideColor = Color.MediumPurple });
        if (!string.IsNullOrWhiteSpace(data.Tooltip))
            tooltips.Add(new TooltipLine(Mod, "InfiniGeneratedTooltip", data.Tooltip));
        RuntimeProgramSpec program = data.RuntimeProgram;
        string inputs = string.Join(", ", program.Bindings.Select(x => x.Input));
        tooltips.Add(new TooltipLine(Mod, "InfiniRuntimeProgram", $"Low-level runtime: {program.Entities.Length} entities, {program.Bindings.Length} bindings{(inputs.Length > 0 ? $" [{inputs}]" : "")}") { OverrideColor = Color.Orange });
        if (program.ItemContact.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniContact", $"Item contact hitbox: ×{program.ItemContact.HitboxScale:0.00}, +{program.ItemContact.ContactForgivenessPx}px") { OverrideColor = Color.SandyBrown });
        if (data.Accessory.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniAccessory", AccessorySummary(data.Accessory)) { OverrideColor = Color.LightGreen });
        if (data.Armor.Enabled)
            tooltips.Add(new TooltipLine(Mod, "InfiniArmor", ArmorSummary(data.Armor)) { OverrideColor = Color.LightSkyBlue });
        if (data.VfxManifest.HasSlots)
            tooltips.Add(new TooltipLine(Mod, "InfiniVfx", $"VFX: {data.VfxManifest.Slots.Length} exact entity/event slots") { OverrideColor = Color.MediumAquamarine });
    }

    private static string AccessorySummary(AccessorySpec a)
    {
        var values = new List<string>();
        if (a.Defense != 0) values.Add($"+{a.Defense} def");
        if (a.MaxLife != 0) values.Add($"+{a.MaxLife} life");
        if (a.MaxMana != 0) values.Add($"+{a.MaxMana} mana");
        if (a.GenericDamage != 0) values.Add($"+{a.GenericDamage * 100f:0}% dmg");
        if (a.MovementSpeed != 0) values.Add($"+{a.MovementSpeed * 100f:0}% move");
        return values.Count == 0 ? "Accessory" : "Accessory: " + string.Join(", ", values);
    }

    private static string ArmorSummary(ArmorSpec a)
    {
        var values = new List<string>();
        if (a.Defense != 0) values.Add($"{a.Defense} def");
        if (a.MaxLife != 0) values.Add($"+{a.MaxLife} life");
        if (a.GenericDamage != 0) values.Add($"+{a.GenericDamage * 100f:0}% dmg");
        return $"Armor ({a.Slot})" + (values.Count == 0 ? "" : ": " + string.Join(", ", values));
    }

    private RuntimeBindingSpec? ActiveUseBinding(Player player)
        => Data.RuntimeProgram.BindingForInput(player.altFunctionUse == 2 ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse);

    public override bool AltFunctionUse(Player player)
        => Data?.RuntimeProgram?.BindingForInput(RuntimeInputKind.AlternateUse) is not null;

    internal static string UseBlockedReason(Player player, GameplaySpec? gameplay)
    {
        if (player is null || gameplay is null) return "";
        return gameplay.UseConditionMode switch
        {
            "grounded" when player.velocity.Y != 0f => "Requires solid ground",
            "not_wet" when player.wet => "Cannot be used while wet",
            "life_above" when player.statLife < gameplay.UseConditionMinLife => $"Requires {gameplay.UseConditionMinLife} life",
            "mana_above" when player.statMana < gameplay.UseConditionMinMana => $"Requires {gameplay.UseConditionMinMana} mana",
            _ => "",
        };
    }

    public override bool CanUseItem(Player player)
    {
        EnsureRuntimeHydration(player);
        string blocked = UseBlockedReason(player, Data.Gameplay);
        if (!string.IsNullOrWhiteSpace(blocked))
        {
            if (player.whoAmI == Main.myPlayer && (int)Main.GameUpdateCount - _lastBlockedNoticeTick > 30)
            {
                _lastBlockedNoticeTick = (int)Main.GameUpdateCount;
                Main.NewText(blocked, Color.OrangeRed);
            }
            return false;
        }
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (binding is null) return false;
        if (binding.Action == RuntimeBindingAction.SpawnEntity)
        {
            RuntimeEntitySpec? entity = Data.RuntimeProgram.TryGetEntity(binding.Target);
            if (entity?.IsOwnerAttached == true)
            {
                foreach (Projectile projectile in Main.ActiveProjectiles)
                    if (projectile.owner == player.whoAmI && projectile.ModProjectile is GeneratedProjectile generated && generated.Matches(Data.Id, entity.Id))
                        return false;
            }
        }
        _itemEventSpawnBudget = Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation;
        return true;
    }

    public override bool ConsumeItem(Player player)
    {
        int chance = Math.Clamp(Data?.Gameplay?.ConsumeChancePercent ?? 100, 0, 100);
        return chance >= 100 || (chance > 0 && Main.rand.Next(100) < chance);
    }

    public override bool? UseItem(Player player)
    {
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (binding is null) return false;
        RuntimeEntitySpec itemEntity = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!;
        if (binding.Action == RuntimeBindingAction.ApplyItemEffects)
            ApplyItemEffects(player);
        RunItemEvent(player, itemEntity, RuntimeEventKind.OnUse, null, 0);
        InfiniItemVfxRuntime.EmitAndSyncEvent(player, Data, itemEntity.Id, RuntimeEventKind.OnUse);
        return true;
    }

    private void ApplyItemEffects(Player player)
    {
        GameplaySpec gp = Data.Gameplay;
        foreach (BuffEntrySpec buff in gp.ExtraBuffs ?? Array.Empty<BuffEntrySpec>())
            if (buff.BuffCode > 0 && buff.BuffTime > 0)
                player.AddBuff(buff.BuffCode, buff.BuffTime);
        if (gp.GeneratedBuff?.HasAnyEffect == true)
            player.GetModPlayer<InfiniCraftPlayer>().ApplyGeneratedUtilityBuff(gp.GeneratedBuff, syncNetwork: Main.netMode != NetmodeID.SinglePlayer);
        if (!string.IsNullOrWhiteSpace(gp.MobilityMode))
            player.GetModPlayer<InfiniCraftPlayer>().TryRunGeneratedMobility(gp);
    }

    public override void HoldItem(Player player)
    {
        EnsureRuntimeHydration(player);
        GameplaySpec gp = Data.Gameplay;
        if (gp.HoldLightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color color = RuntimeColorPolicy.Resolve(gp.HoldLightColorName, Color.White);
            float strength = Math.Clamp(gp.HoldLightStrength, 0f, 1.5f);
            Lighting.AddLight(player.Center, color.R / 255f * strength, color.G / 255f * strength, color.B / 255f * strength);
        }
        if ((gp.PickPower > 0 || gp.AxePower > 0 || gp.HammerPower > 0) && Math.Abs(gp.MiningSpeedScale - 1f) > 0.001f)
            player.pickSpeed /= Math.Clamp(gp.MiningSpeedScale, 0.1f, 4f);

        RuntimeBindingSpec? hold = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Hold);
        if (hold?.Action == RuntimeBindingAction.SpawnEntity && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player))
        {
            RuntimeEntitySpec? entity = Data.RuntimeProgram.TryGetEntity(hold.Target);
            bool exists = entity is not null && Main.ActiveProjectiles.Any(p => p.owner == player.whoAmI && p.ModProjectile is GeneratedProjectile g && g.Matches(Data.Id, entity.Id));
            if (!exists && entity is not null)
                GeneratedProjectile.SpawnRuntimeEntity(Data, entity.Id, player, player.GetSource_ItemUse(Item), player.Center, new Vector2(player.direction, 0f), 0, Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
        }
        RuntimeEntitySpec itemEntity = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!;
        RunPeriodicItemEvents(player, itemEntity);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, itemEntity.Id);
    }

    private void RunPeriodicItemEvents(Player player, RuntimeEntitySpec entity)
    {
        foreach (RuntimeEventActionSpec action in entity.ActionsFor(RuntimeEventKind.Periodic))
        {
            int period = Math.Max(6, action.PeriodTicks);
            if ((Main.GameUpdateCount + (ulong)action.Id.GetHashCode()) % (ulong)period != 0) continue;
            int budget = Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation;
            RuntimeProgramExecutor.ExecuteAction(Data, action, player, player.GetSource_Misc("InfiniRuntimePeriodic"), player.Center, new Vector2(player.direction, 0f), null, Data.Gameplay.Damage, 0, ref budget);
        }
    }

    private void RunItemEvent(Player player, RuntimeEntitySpec entity, string eventName, NPC? target, int damageDone)
    {
        int budget = _itemEventSpawnBudget > 0 ? _itemEventSpawnBudget : Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation;
        RuntimeProgramExecutor.RunEvent(Data, entity, eventName, player, player.GetSource_ItemUse(Item), target?.Center ?? player.Center, new Vector2(player.direction, 0f), target, damageDone, 0, ref budget);
        _itemEventSpawnBudget = budget;
    }

    public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
    {
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (binding?.Action != RuntimeBindingAction.SpawnEntity) return false;
        if (!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player)) return false;
        GeneratedProjectile.SpawnRuntimeEntity(Data, binding.Target, player, source, position, velocity.SafeNormalize(new Vector2(player.direction, 0f)), 0, Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
        return false;
    }

    public override Vector2? HoldoutOffset()
        => new(Data.RuntimeProgram.ItemUse.HoldoutOffsetX, Data.RuntimeProgram.ItemUse.HoldoutOffsetY);

    public override void ModifyItemScale(Player player, ref float scale)
        => scale *= Math.Clamp(Data.Gameplay.ItemScale, 0.25f, 4f);

    public override void UseItemHitbox(Player player, ref Rectangle hitbox, ref bool noHitbox)
    {
        RuntimeItemContactSpec contact = Data.RuntimeProgram.ItemContact;
        if (!contact.Enabled) { noHitbox = true; return; }
        float scale = contact.HitboxScale;
        int width = Math.Max(1, (int)MathF.Round(hitbox.Width * scale) + contact.ContactForgivenessPx * 2);
        int height = Math.Max(1, (int)MathF.Round(hitbox.Height * scale) + contact.ContactForgivenessPx * 2);
        hitbox = new Rectangle(hitbox.Center.X - width / 2, hitbox.Center.Y - height / 2, width, height);
    }

    public override void OnHitNPC(Player player, NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (!Data.RuntimeProgram.ItemContact.Enabled) return;
        RuntimeEntitySpec itemEntity = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!;
        RunItemEvent(player, itemEntity, RuntimeEventKind.OnHit, target, damageDone);
        if (hit.Crit) RunItemEvent(player, itemEntity, RuntimeEventKind.OnCrit, target, damageDone);
        InfiniItemVfxRuntime.EmitAndSyncEvent(player, Data, itemEntity.Id, RuntimeEventKind.OnHit);
        if (hit.Crit) InfiniItemVfxRuntime.EmitAndSyncEvent(player, Data, itemEntity.Id, RuntimeEventKind.OnCrit);
    }

    public override void UpdateAccessory(Player player, bool hideVisual)
    {
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        if (binding?.Action != RuntimeBindingAction.EquipPassive || !Data.Accessory.Enabled) return;
        ApplyEquipmentEffects(player, Data.Accessory);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, Data.RuntimeProgram.ItemEntityId);
    }

    public override void UpdateEquip(Player player)
    {
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        if (binding?.Action != RuntimeBindingAction.EquipPassive || !Data.Armor.Enabled) return;
        ApplyEquipmentEffects(player, Data.Armor);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, Data.RuntimeProgram.ItemEntityId);
    }

    private static void ApplyEquipmentEffects(Player player, AccessorySpec a)
    {
        player.statDefense += a.Defense;
        player.statLifeMax2 += a.MaxLife; player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen; player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed; player.maxRunSpeed += a.MaxRunSpeed; player.jumpSpeedBoost += a.JumpSpeed;
        player.GetDamage(DamageClass.Generic) += a.GenericDamage; player.GetDamage(DamageClass.Melee) += a.MeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.RangedDamage; player.GetDamage(DamageClass.Magic) += a.MagicDamage; player.GetDamage(DamageClass.Summon) += a.SummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.GenericCrit; player.GetAttackSpeed(DamageClass.Generic) += a.AttackSpeed; player.GetKnockback(DamageClass.Generic) += a.Knockback;
        player.maxMinions += a.MinionSlots; player.maxTurrets += a.SentrySlots;
        if (a.ManaCostReduction > 0f) player.manaCost = Math.Max(0.1f, player.manaCost - a.ManaCostReduction);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedSummonTagDamage(a.SummonTagDamage);
        player.aggro += a.Aggro; player.endurance += a.Endurance; player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration;
        player.whipRangeMultiplier += a.WhipRange;
        if (a.FallDamageImmune) player.noFallDmg = true; if (a.LavaImmune) player.lavaImmune = true; if (a.WaterWalk) player.waterWalk = true;
        AddEquipmentLight(player, a.LightStrength, a.LightColorName);
    }

    private static void ApplyEquipmentEffects(Player player, ArmorSpec a)
    {
        player.statLifeMax2 += a.MaxLife; player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen; player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed; player.maxRunSpeed += a.MaxRunSpeed; player.jumpSpeedBoost += a.JumpSpeed;
        player.GetDamage(DamageClass.Generic) += a.GenericDamage; player.GetDamage(DamageClass.Melee) += a.MeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.RangedDamage; player.GetDamage(DamageClass.Magic) += a.MagicDamage; player.GetDamage(DamageClass.Summon) += a.SummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.GenericCrit; player.GetAttackSpeed(DamageClass.Generic) += a.AttackSpeed; player.GetKnockback(DamageClass.Generic) += a.Knockback;
        player.maxMinions += a.MinionSlots; player.maxTurrets += a.SentrySlots;
        if (a.ManaCostReduction > 0f) player.manaCost = Math.Max(0.1f, player.manaCost - a.ManaCostReduction);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedSummonTagDamage(a.SummonTagDamage);
        player.aggro += a.Aggro; player.endurance += a.Endurance; player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration;
        player.whipRangeMultiplier += a.WhipRange;
        if (a.FallDamageImmune) player.noFallDmg = true; if (a.LavaImmune) player.lavaImmune = true; if (a.WaterWalk) player.waterWalk = true;
        AddEquipmentLight(player, a.LightStrength, a.LightColorName);
    }

    private static void AddEquipmentLight(Player player, float strength, string colorName)
    {
        if (strength <= 0f || Main.netMode == NetmodeID.Server) return;
        Color color = RuntimeColorPolicy.Resolve(colorName, Color.White);
        strength = Math.Clamp(strength, 0f, 1.5f);
        Lighting.AddLight(player.Center, color.R / 255f * strength, color.G / 255f * strength, color.B / 255f * strength);
    }

    public override bool IsArmorSet(Item head, Item body, Item legs)
    {
        ArmorSpec armor = Data.Armor;
        if (!armor.Enabled || armor.Slot != "head" || string.IsNullOrWhiteSpace(armor.SetKey)) return false;
        return IsSetPiece(head, "head", armor.SetKey) && IsSetPiece(body, "body", armor.SetKey) && IsSetPiece(legs, "legs", armor.SetKey);
    }

    private static bool IsSetPiece(Item item, string slot, string setKey)
        => item?.ModItem is GeneratedItem generated && generated.Data.Armor.Enabled
            && string.Equals(generated.Data.Armor.Slot, slot, StringComparison.Ordinal)
            && string.Equals(generated.Data.Armor.SetKey, setKey, StringComparison.Ordinal);

    public override void UpdateArmorSet(Player player)
    {
        ArmorSpec a = Data.Armor;
        if (!a.Enabled || a.Slot != "head") return;
        player.setBonus = a.SetBonusText;
        player.GetDamage(DamageClass.Generic) += a.SetBonusGenericDamage;
        player.GetDamage(DamageClass.Melee) += a.SetBonusMeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.SetBonusRangedDamage;
        player.GetDamage(DamageClass.Magic) += a.SetBonusMagicDamage;
        player.GetDamage(DamageClass.Summon) += a.SetBonusSummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.SetBonusGenericCrit;
        player.moveSpeed += a.SetBonusMovementSpeed; player.lifeRegen += a.SetBonusLifeRegen; player.manaRegenBonus += a.SetBonusManaRegen;
        player.maxMinions += a.SetBonusMinionSlots; player.maxTurrets += a.SetBonusSentrySlots;
        if (a.SetBonusManaCostReduction > 0f) player.manaCost = Math.Max(0.1f, player.manaCost - a.SetBonusManaCostReduction);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.SetBonusAmmoSaveChance);
        player.aggro += a.SetBonusAggro; player.endurance += a.SetBonusEndurance; player.GetArmorPenetration(DamageClass.Generic) += a.SetBonusArmorPenetration;
    }

    public override bool PreDrawInInventory(SpriteBatch spriteBatch, Vector2 position, Rectangle frame, Color drawColor, Color itemColor, Vector2 origin, float scale)
    {
        EnsureRuntimeHydration();
        GeneratedItemData data = PresentationData();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(data.Visual.SpritePath);
        if (texture is null) return true;
        Rectangle source = texture.Bounds;
        Vector2 drawOrigin = source.Size() / 2f;
        float fit = Math.Min(1f, Math.Max(frame.Width, frame.Height) / Math.Max(1f, Math.Max(texture.Width, texture.Height)));
        spriteBatch.Draw(texture, position + new Vector2(data.Visual.DrawOffsetX, data.Visual.DrawOffsetY), source, drawColor, 0f, drawOrigin, scale * fit * data.Visual.InventoryScale, SpriteEffects.None, 0f);
        return false;
    }

    public override bool PreDrawInWorld(SpriteBatch spriteBatch, Color lightColor, Color alphaColor, ref float rotation, ref float scale, int whoAmI)
    {
        EnsureRuntimeHydration();
        GeneratedItemData data = PresentationData();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(data.Visual.SpritePath);
        if (texture is null) return true;
        Rectangle source = texture.Bounds;
        Vector2 origin = source.Size() / 2f;
        float finalScale = scale * data.Visual.WorldScale;
        Vector2 drawPosition = Item.Bottom - Main.screenPosition - new Vector2(0f, origin.Y * finalScale) + new Vector2(data.Visual.DrawOffsetX, data.Visual.DrawOffsetY);
        spriteBatch.Draw(texture, drawPosition, source, alphaColor, rotation, origin, finalScale, SpriteEffects.None, 0f);
        return false;
    }
}
