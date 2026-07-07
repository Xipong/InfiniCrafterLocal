#nullable enable
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Terraria;

namespace InfiniCrafterLocal.Common.Models;

public sealed partial class GeneratedItemData
{
    // Compact dev-only record used by /infiniitem trace. It is runtime-only:
    // never serialized, never networked, and not shown in normal tooltips.
    [JsonIgnore]
    public string? LastAppliedTrace { get; private set; }

    private string BuildAppliedTrace()
    {
        bool isArmor = Gameplay.Kind == "armor" || Category == "armor" || Armor.Enabled;
        bool isAccessory = !isArmor && (Gameplay.Kind == "accessory" || Category == "accessory" || Accessory.Enabled);
        var parts = new List<string>();
        void F(string label, object? val) => parts.Add($"{label}={val?.ToString() ?? string.Empty}");

        F("name", Name);
        F("category", Category);
        F("kind", Gameplay.Kind);
        F("damageClass", Gameplay.DamageClass);
        F("damage", Gameplay.Damage);
        F("useTime", Gameplay.UseTime);
        F("useAnimation", Gameplay.UseAnimation);
        F("useStyle", Gameplay.UseStyle);
        F("knockback", Gameplay.Knockback);
        F("rare", Gameplay.Rarity);
        F("value", Gameplay.Value);
        F("maxStack", Gameplay.MaxStack);
        F("mana", Gameplay.ManaCost);
        F("consumable", Gameplay.Consumable);

        if (Attack.Enabled && !isAccessory && !isArmor)
        {
            F("shoot", "GeneratedProjectile");
            F("shootSpeed", Attack.Speed);
            F("runtimeFamily", AttackRuntimeFamily(Attack));
            F("delivery", Attack.Delivery);
            F("movement", Attack.Movement);
            F("weaponFamily", Attack.WeaponFamily);
            F("shotCount", Attack.ShotCount);
            F("pierce", Attack.Pierce);
            F("splitCount", Attack.SplitCount);
            F("maxChildProjectiles", Attack.MaxChildProjectiles);
            F("onHit", Attack.OnHit);
            F("aoeRadiusPx", Attack.AoeDamageRadiusPx);
            F("burstDustCap", Attack.BurstDustCap);
            F("explosionRadius", Attack.ExplosionRadius);
            F("trailLength", Attack.TrailLength);
            F("effect", Attack.Effect);
        }
        if (isArmor)
        {
            F("defense", Armor.Defense);
            F("slot", Armor.Slot);
            F("setBonusText", Armor.SetBonusText);
        }
        if (isAccessory)
        {
            F("acc.defense", Accessory.Defense);
            F("acc.lifeRegen", Accessory.LifeRegen);
            F("acc.manaRegen", Accessory.ManaRegen);
            F("acc.manaCostReduction", Accessory.ManaCostReduction);
            F("acc.genericDamage", Accessory.GenericDamage);
            F("acc.genericCrit", Accessory.GenericCrit);
            F("acc.movementSpeed", Accessory.MovementSpeed);
            F("acc.endurance", Accessory.Endurance);
            F("acc.armorPenetration", Accessory.ArmorPenetration);
            F("acc.aggro", Accessory.Aggro);
        }
        return string.Join(" | ", parts);
    }

    internal void StampAppliedTrace() => LastAppliedTrace = BuildAppliedTrace();

    private void SetDebugJson(string key, object value)
    {
        if (string.IsNullOrWhiteSpace(key))
            return;
        Debug ??= new Dictionary<string, JsonElement>();
        try
        {
            Debug[key] = JsonSerializer.SerializeToElement(value, Options);
        }
        catch (InvalidOperationException) { }
        catch (NotSupportedException) { }
        catch (ArgumentException) { }
    }

    private void RecordAppliedItemTrace(Item item, bool isArmor, bool isAccessory, bool actualAmmo)
    {
        SetDebugJson("appliedTrace", new
        {
            schema = "infini.applied-trace.v1",
            item = new
            {
                damage = item.damage,
                useTime = item.useTime,
                useStyle = item.useStyle,
                damageClass = Gameplay.DamageClass,
                shoot = item.shoot,
                shootSpeed = item.shootSpeed,
                knockback = item.knockBack,
                rare = item.rare,
                value = item.value,
                defense = item.defense,
                accessory = item.accessory,
                actualAmmo,
                noMelee = item.noMelee,
                noUseGraphic = item.noUseGraphic,
                channel = item.channel
            },
            armor = new
            {
                applied = isArmor,
                defense = isArmor ? item.defense : 0,
                slot = Armor.Slot,
                updateEquip = new
                {
                    Armor.MaxLife,
                    Armor.MaxMana,
                    Armor.LifeRegen,
                    Armor.ManaRegen,
                    Armor.MovementSpeed,
                    Armor.MaxRunSpeed,
                    Armor.JumpSpeed,
                    Armor.GenericDamage,
                    Armor.MeleeDamage,
                    Armor.RangedDamage,
                    Armor.MagicDamage,
                    Armor.SummonDamage,
                    Armor.GenericCrit,
                    Armor.AttackSpeed,
                    Armor.Knockback,
                    Armor.MinionSlots,
                    Armor.SentrySlots,
                    Armor.ManaCostReduction,
                    Armor.AmmoSaveChance,
                    Armor.Aggro,
                    Armor.Endurance,
                    Armor.ArmorPenetration
                },
                setBonus = new
                {
                    Armor.SetKey,
                    Armor.SetBonusText,
                    Armor.SetBonusGenericDamage,
                    Armor.SetBonusMeleeDamage,
                    Armor.SetBonusRangedDamage,
                    Armor.SetBonusMagicDamage,
                    Armor.SetBonusSummonDamage,
                    Armor.SetBonusGenericCrit,
                    Armor.SetBonusMovementSpeed,
                    Armor.SetBonusLifeRegen,
                    Armor.SetBonusManaRegen,
                    Armor.SetBonusMinionSlots,
                    Armor.SetBonusSentrySlots,
                    Armor.SetBonusManaCostReduction,
                    Armor.SetBonusAmmoSaveChance,
                    Armor.SetBonusAggro,
                    Armor.SetBonusEndurance,
                    Armor.SetBonusArmorPenetration
                }
            },
            accessory = new
            {
                applied = isAccessory,
                updateEquip = new
                {
                    Accessory.Defense,
                    Accessory.MaxLife,
                    Accessory.MaxMana,
                    Accessory.LifeRegen,
                    Accessory.ManaRegen,
                    Accessory.MovementSpeed,
                    Accessory.MaxRunSpeed,
                    Accessory.JumpSpeed,
                    Accessory.GenericDamage,
                    Accessory.MeleeDamage,
                    Accessory.RangedDamage,
                    Accessory.MagicDamage,
                    Accessory.SummonDamage,
                    Accessory.GenericCrit,
                    Accessory.AttackSpeed,
                    Accessory.Knockback,
                    Accessory.MinionSlots,
                    Accessory.SentrySlots,
                    Accessory.ManaCostReduction,
                    Accessory.AmmoSaveChance,
                    Accessory.Aggro,
                    Accessory.Endurance,
                    Accessory.ArmorPenetration
                }
            },
            projectile = new
            {
                applied = Attack.Enabled && !isArmor && !isAccessory && !actualAmmo,
                Attack.RuntimeFamily,
                Attack.Delivery,
                Attack.Movement,
                Attack.ShotCount,
                Attack.Pierce,
                Attack.OnHit,
                Attack.SplitCount,
                Attack.ChainCount,
                Attack.MaxChildProjectiles,
                Attack.TrailLength,
                Attack.BurstDustCap,
                Attack.Effect,
                fieldRadius = Attack.AoeDamageRadiusPx,
                Attack.RuntimePlanAuthored
            }
        });
        StampAppliedTrace();
    }
}
