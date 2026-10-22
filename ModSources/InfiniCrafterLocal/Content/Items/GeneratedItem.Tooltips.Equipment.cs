#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    // Read the exact equipment action/DTO consumed by UpdateAccessory/UpdateEquip.
    // Never project Item, hydrate, infer stats from parents, or advertise inactive data.
    private static void AddRuntimeEquipmentStats(GeneratedItemData data, Action<string, string, object[]> add,
        Action<string, string, object[]> detail)
    {
        RuntimeBindingSpec? binding = data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.EquipPassive
            || data.RuntimeProgram.TryGetEntity(binding.UsePolicy.Action.TargetId)?.Kind != RuntimeEntityKind.ItemBody)
            return;
        AccessorySpec? a = data.Accessory.Enabled ? data.Accessory : null;
        ArmorSpec? armor = data.Armor.Enabled ? data.Armor : null;
        if (a is null && armor is null) return;
        string input = RuntimeTooltipText("InputEquipped");
        void Stat(string name, string key, float value)
        {
            if (!float.IsFinite(value) || value == 0f) return;
            add("Equipment" + name, key, new object[] { input, (value > 0 ? "+" : "") + RuntimeTooltipNumber(value) });
        }
        void Percent(string name, string key, float value)
        {
            if (!float.IsFinite(value) || value == 0f) return;
            add("Equipment" + name, key, new object[] { input, RuntimeTooltipSignedPercent(value) });
        }
        void Flag(string name, bool enabled)
        {
            if (enabled) detail("Equipment" + name, "Equipment" + name, new object[] { input });
        }
        Stat("MaxLife", "EquipmentMaxLife", a?.MaxLife ?? armor!.MaxLife);
        Stat("MaxMana", "EquipmentMaxMana", a?.MaxMana ?? armor!.MaxMana);
        // Native lifeRegen is half-HP/s points; manaRegenBonus is NOT mana/s.
        Stat("LifeRegen", "EquipmentLifeRegen", a is not null ? a.LifeRegen / 2f : armor!.LifeRegen / 2f);
        Stat("ManaRegen", "EquipmentManaRegen", a?.ManaRegen ?? armor!.ManaRegen);
        Percent("Movement", "EquipmentMovement", a?.MovementSpeed ?? armor!.MovementSpeed);
        Stat("MaxRunSpeed", "EquipmentMaxRunSpeed", PlayerDisplayUnits.BlocksPerSecond(a?.MaxRunSpeed ?? armor!.MaxRunSpeed));
        Stat("Jump", "EquipmentJump", PlayerDisplayUnits.BlocksPerSecond(a?.JumpSpeed ?? armor!.JumpSpeed));
        Percent("GenericDamage", "EquipmentGenericDamage", a?.GenericDamage ?? armor!.GenericDamage);
        Percent("MeleeDamage", "EquipmentMeleeDamage", a?.MeleeDamage ?? armor!.MeleeDamage);
        Percent("RangedDamage", "EquipmentRangedDamage", a?.RangedDamage ?? armor!.RangedDamage);
        Percent("MagicDamage", "EquipmentMagicDamage", a?.MagicDamage ?? armor!.MagicDamage);
        Percent("SummonDamage", "EquipmentSummonDamage", a?.SummonDamage ?? armor!.SummonDamage);
        Stat("Crit", "EquipmentCrit", a?.GenericCrit ?? armor!.GenericCrit);
        Percent("AttackSpeed", "EquipmentAttackSpeed", a?.AttackSpeed ?? armor!.AttackSpeed);
        Percent("Knockback", "EquipmentKnockback", a?.Knockback ?? armor!.Knockback);
        Stat("Minions", "EquipmentMinions", a?.MinionSlots ?? armor!.MinionSlots);
        Stat("Sentries", "EquipmentSentries", a?.SentrySlots ?? armor!.SentrySlots);
        // These executors only admit a positive reduction; do not claim a negative one.
        float manaReduction = a?.ManaCostReduction ?? armor!.ManaCostReduction;
        if (manaReduction > 0f) Percent("ManaCost", "EquipmentManaCost", -manaReduction);
        float ammoSaving = a?.AmmoSaveChance ?? armor!.AmmoSaveChance;
        if (ammoSaving > 0f) Percent("AmmoSave", "EquipmentAmmoSave", Math.Clamp(ammoSaving, 0f, 0.9999f));
        Stat("Aggro", "EquipmentAggro", a?.Aggro ?? armor!.Aggro);
        Percent("Endurance", "EquipmentEndurance", a?.Endurance ?? armor!.Endurance);
        Stat("ArmorPenetration", "EquipmentArmorPenetration", a?.ArmorPenetration ?? armor!.ArmorPenetration);
        Percent("WhipRange", "EquipmentWhipRange", a?.WhipRange ?? armor!.WhipRange);
        float summonTag = a?.SummonTagDamage ?? armor!.SummonTagDamage;
        if (summonTag > 0f) Percent("SummonTag", "EquipmentSummonTag", Math.Clamp(summonTag, 0f, 3f));
        Flag("NoFallDamage", a?.FallDamageImmune ?? armor!.FallDamageImmune);
        Flag("LavaImmune", a?.LavaImmune ?? armor!.LavaImmune);
        Flag("WaterWalk", a?.WaterWalk ?? armor!.WaterWalk);
        float light = a is not null ? a.LightStrength : armor!.LightStrength;
        if (light > 0f) Stat("Light", "EquipmentLight", Math.Clamp(light, 0f, 1.5f));
        if (a is not null)
        {
            Flag("WireVision", a.WireVision); Flag("IceSkate", a.IceSkate);
            Flag("NoKnockback", a.NoKnockback); Flag("FireWalk", a.FireWalk);
            Stat("RocketBoots", "EquipmentRocketBoots", a.RocketBoots);
            Stat("SprintFloor", "EquipmentSprintFloor", PlayerDisplayUnits.BlocksPerSecond(a.AccRunSpeed));
        }
        // Item.defense remains on the native tooltip, including prefixes. Do not
        // repeat authored defense as though it were a second equipped contribution.
    }
}
