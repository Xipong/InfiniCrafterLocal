#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using System;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

// Native equipped effects and exact authored armor-set membership.
public partial class GeneratedItem
{
    public override void UpdateAccessory(Player player, bool hideVisual)
    {
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.EquipPassive || !Data.Accessory.Enabled) return;
        player.GetModPlayer<InfiniCraftPlayer>().RegisterReactiveEquipment(this);
        ApplyEquipmentEffects(player, Data.Accessory);
        RunPeriodicItemEvents(player, Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, Data.RuntimeProgram.ItemEntityId,Item);
    }

    public override void UpdateEquip(Player player)
    {
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.EquipPassive || !Data.Armor.Enabled) return;
        player.GetModPlayer<InfiniCraftPlayer>().RegisterReactiveEquipment(this);
        ApplyEquipmentEffects(player, Data.Armor);
        RunPeriodicItemEvents(player, Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, Data.RuntimeProgram.ItemEntityId,Item);
    }

    private static void ApplyEquipmentEffects(Player player, AccessorySpec a)
    {
        if (a.PlayerEffect is { } effect) player.GetModPlayer<InfiniCraftPlayer>().ApplyPlayerEffect(effect);
        // Terraria already applies Item.defense in Player.GrantArmorBenefits.
        player.statLifeMax2 += a.MaxLife; player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen; player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed; player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedMaxRunSpeedBonus(a.MaxRunSpeed); player.jumpSpeedBoost += a.JumpSpeed;
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
        if (a.WireVision) player.InfoAccMechShowWires = true;
        if (a.IceSkate) player.iceSkate = true;
        if (a.NoKnockback) player.noKnockback = true;
        if (a.FireWalk) player.fireWalk = true;
        // Native Player.Update owns rocketTime/refill/delay/thrust. Never refill per equip tick.
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedRocketBootsMode(a.RocketBoots);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAccRunSpeedFloor(a.AccRunSpeed);
        AddEquipmentLight(player, a.LightStrength, a.LightColorName);
    }

    private static void ApplyEquipmentEffects(Player player, ArmorSpec a)
    {
        if (a.PlayerEffect is { } effect) player.GetModPlayer<InfiniCraftPlayer>().ApplyPlayerEffect(effect);
        player.statLifeMax2 += a.MaxLife; player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen; player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed; player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedMaxRunSpeedBonus(a.MaxRunSpeed); player.jumpSpeedBoost += a.JumpSpeed;
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
        if (!armor.Enabled || !string.Equals(armor.Slot, "head", StringComparison.OrdinalIgnoreCase) || string.IsNullOrWhiteSpace(armor.SetKey)) return false;
        return IsSetPiece(head, "head", armor.SetKey) && IsSetPiece(body, "body", armor.SetKey) && IsSetPiece(legs, "legs", armor.SetKey);
    }

    private static bool IsSetPiece(Item item, string slot, string setKey)
        => item?.ModItem is GeneratedItem generated && generated.Data.Armor.Enabled
            && string.Equals(generated.Data.Armor.Slot, slot, StringComparison.OrdinalIgnoreCase)
            && string.Equals(generated.Data.Armor.SetKey, setKey, StringComparison.Ordinal);

    public override void UpdateArmorSet(Player player)
    {
        ArmorSpec a = Data.Armor;
        if (!a.Enabled || !string.Equals(a.Slot, "head", StringComparison.OrdinalIgnoreCase)) return;
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
}
