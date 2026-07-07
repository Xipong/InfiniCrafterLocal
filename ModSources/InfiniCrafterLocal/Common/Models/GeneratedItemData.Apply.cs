#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Audio;
using System;
using System.Linq;
using Terraria;
using Terraria.Audio;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

// AGENT MAP: DTO -> Terraria Item application boundary.
// This file maps explicit GeneratedItemData fields onto Item stats/equipment/tool
// flags and proxy state. It should not inspect prompt/flavor/name text to infer
// mechanics; if a mechanic is real it needs an explicit normalized field.
public sealed partial class GeneratedItemData
{
// =============================================================================
// NAV: GENERATED_ITEM_APPLY_TO_ITEM
// =============================================================================

    private static DamageClass ResolveDamageClass(string? raw)
    {
        string value = (raw ?? "").Trim();
        string norm = value.ToLowerInvariant().Replace("-", "_").Replace(" ", "_");
        return norm switch
        {
            "melee" => DamageClass.Melee,
            "melee_no_speed" => DamageClass.MeleeNoSpeed,
            "ranged" => DamageClass.Ranged,
            "magic" => DamageClass.Magic,
            "summon" => DamageClass.Summon,
            "summon_melee_speed" => DamageClass.SummonMeleeSpeed,
            // Throwing/Rogue-like classes are modded in many 1.4 packs; resolve dynamically instead of hardcoding.
            "throwing" or "rogue" => ResolveModDamageClass(value) ?? DamageClass.Ranged,
            "generic" or "" => DamageClass.Generic,
            _ => ResolveModDamageClass(value) ?? DamageClass.Generic
        };
    }

    private static DamageClass? ResolveModDamageClass(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        string value = raw.Trim();
        try
        {
            if (ModContent.TryFind<DamageClass>(value, out var direct))
                return direct;
        }
        catch { }
        string[] splitters = { "/", ":", "." };
        foreach (string sep in splitters)
        {
            int idx = value.IndexOf(sep, StringComparison.Ordinal);
            if (idx <= 0 || idx >= value.Length - sep.Length) continue;
            string modName = value[..idx];
            string className = value[(idx + sep.Length)..];
            try
            {
                if (ModLoader.TryGetMod(modName, out Mod mod) && mod.TryFind<DamageClass>(className, out var cls))
                    return cls;
            }
            catch { }
        }
        return null;
    }

    private static string AttackRuntimeFamily(AttackSpec? attack)
    {
        if (attack is null) return "none";
        string r = NormalizeRuntimeFamily(attack.RuntimeFamily);
        return r == "none" ? "none" : r;
    }

    public void ApplyToItem(Item item)
    {
        Normalize();
        item.SetNameOverride(Name);
        item.width = Math.Max(16, Gameplay.Width);
        item.height = Math.Max(16, Gameplay.Height);
        item.value = Math.Max(0, Gameplay.Value);
        item.rare = Gameplay.Rarity;
        item.maxStack = Math.Max(1, Gameplay.MaxStack);

        item.damage = Math.Max(0, Gameplay.Damage);
        item.knockBack = Gameplay.Knockback;
        item.useTime = Math.Max(10, Gameplay.UseTime);
        item.useAnimation = Math.Max(10, Gameplay.UseAnimation);
        item.useStyle = Gameplay.UseStyle;
        item.autoReuse = Gameplay.AutoReuse;
        item.consumable = Gameplay.Consumable;
        item.mana = Math.Max(0, Gameplay.ManaCost);
        item.scale = 1f; // dynamic held-item scale is applied in ModItem.ModifyItemScale
        item.useTurn = Gameplay.UseTurn;
        item.channel = Gameplay.ChannelUse;
        item.noUseGraphic = false;
        item.noMelee = false;
        item.healLife = Math.Max(0, Gameplay.HealLife);
        item.healMana = Math.Max(0, Gameplay.HealMana);
        item.buffType = Gameplay.BuffCode;
        item.buffTime = Gameplay.BuffTime;
        item.pick = Math.Max(0, Gameplay.PickPower);
        item.axe = Math.Max(0, Gameplay.AxePower);
        item.hammer = Math.Max(0, Gameplay.HammerPower);
        bool isArmor = Gameplay.Kind == "armor" || Category == "armor" || Armor.Enabled;
        bool isAccessory = !isArmor && (Gameplay.Kind == "accessory" || Category == "accessory" || Accessory.Enabled);
        item.accessory = isAccessory;
        if (isArmor)
        {
            item.defense = Math.Max(0, Armor.Defense);
            item.damage = 0;
            item.knockBack = 0f;
            item.useStyle = ItemUseStyleID.None;
            item.useTime = 10;
            item.useAnimation = 10;
            item.noUseGraphic = true;
            item.noMelee = true;
            item.autoReuse = false;
            item.consumable = false;
            item.maxStack = 1;
            item.accessory = false;
        }
        else if (isAccessory)
        {
            item.damage = 0;
            item.useStyle = ItemUseStyleID.None;
            item.useTime = 10;
            item.useAnimation = 10;
            item.noUseGraphic = true;
            item.noMelee = true;
            item.autoReuse = false;
            item.consumable = false;
            item.maxStack = 1;
        }

        item.DamageType = ResolveDamageClass(Gameplay.DamageClass);

        if (!isAccessory && !isArmor && Gameplay.Consumable)
        {
            item.UseSound = SoundID.Item3;
        }

        bool hasRuntimeItemSpriteForHeldUse = !string.IsNullOrWhiteSpace(Visual.SpritePath) && !isAccessory && !isArmor;

        string ammoFor = (Gameplay.AmmoFor ?? "").Trim().ToLowerInvariant();
        bool actualAmmo = !isAccessory && !isArmor && Gameplay.Kind == "ammo" && (ammoFor is "arrow" or "arrows" or "bullet" or "bullets");
        if (actualAmmo)
        {
            item.consumable = true;
            item.noMelee = true;
            item.noUseGraphic = true;
            item.useStyle = ItemUseStyleID.None;
            item.ammo = ammoFor switch
            {
                "arrow" or "arrows" => AmmoID.Arrow,
                "bullet" or "bullets" => AmmoID.Bullet,
                _ => ItemID.None
            };
            item.shoot = ammoFor switch
            {
                "arrow" or "arrows" => ProjectileID.WoodenArrowFriendly,
                "bullet" or "bullets" => ProjectileID.Bullet,
                _ => ProjectileID.None
            };
        }

        if (!isAccessory && !isArmor && Attack.Enabled && !actualAmmo)
        {
            string runtimeFamily = AttackRuntimeFamily(Attack);
            bool thrustLike = runtimeFamily == "thrust";
            bool flailLike = runtimeFamily == "flail";
            bool yoyoLike = runtimeFamily == "yoyo";
            bool whipLike = runtimeFamily == "whip";
            if (Attack.UseStyleCode > ItemUseStyleID.None)
                item.useStyle = Attack.UseStyleCode;
            item.noMelee = Attack.DisableItemMeleeHitbox;
            item.noUseGraphic = Attack.HideUseGraphic;
            item.channel = Attack.ChannelUse;
            item.shoot = ModContent.ProjectileType<global::InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile>();
            item.shootSpeed = Math.Max(1f, Attack.Speed);
            string family = (Attack.WeaponFamily ?? "").Trim().ToLowerInvariant();
            string ammoKind = (Attack.AmmoKind ?? Gameplay.AmmoFor ?? "").Trim().ToLowerInvariant();
            bool bowLike = family is "bow" or "repeater" or "crossbow" || ammoKind is "arrow" or "arrows";
            bool gunLike = family is "gun" or "shotgun" or "musket" or "pistol" || ammoKind is "bullet" or "bullets";
            bool launcherLike = family is "launcher" or "rocket_launcher" || ammoKind is "rocket" or "rockets";

            // v0.4.57: vanilla held-item drawing can only use the static ModItem.Texture.
            // When an AI-authored runtime PNG exists, hide that static placeholder for every
            // weapon delivery (including swing) and let GeneratedHeldItemDrawLayer draw the
            // per-instance sprite from Data.Visual.SpritePath instead.
            bool hasRuntimeItemSprite = hasRuntimeItemSpriteForHeldUse;

            if (thrustLike)
            {
                // Vanilla spear affordance: the ModProjectile is a held/owner-checked
                // thrust projection, not a free-flying bolt or sword swing.
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile + " thrust").Trim(), runtimeFamily, Attack.Effect);
            }
            else if (flailLike)
            {
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile + " flail chain").Trim(), runtimeFamily, Attack.Effect);
            }
            else if (yoyoLike)
            {
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.channel = true;
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile + " yoyo").Trim(), runtimeFamily, Attack.Effect);
            }
            else if (whipLike)
            {
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile + " whip lash").Trim(), runtimeFamily, Attack.Effect);
            }
            else if (bowLike)
            {
                // Preserve vanilla bow affordance: consume arrows and use bow sound, while still
                // spawning the generated projectile in Shoot().
                item.useAmmo = AmmoID.Arrow;
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile + " bow arrow").Trim(), runtimeFamily, Attack.Effect);
                item.noUseGraphic = true;
            }
            else if (gunLike)
            {
                item.useAmmo = AmmoID.Bullet;
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile + " gun bullet").Trim(), runtimeFamily, Attack.Effect);
                item.noUseGraphic = true;
            }
            else if (launcherLike)
            {
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile + " launcher rocket").Trim(), runtimeFamily, Attack.Effect);
                item.noUseGraphic = true;
            }
            else
            {
                item.UseSound = UseSoundForProfile((Attack.SoundUse + " " + Attack.UseSoundProfile).Trim(), runtimeFamily, Attack.Effect);
                if (hasRuntimeItemSprite || IsFreeProjectileFamily(runtimeFamily))
                    item.noUseGraphic = true;
            }
        }

        if (!isAccessory && !isArmor && !actualAmmo && hasRuntimeItemSpriteForHeldUse && item.useStyle > ItemUseStyleID.None)
        {
            // Generated item texture is per-instance and cannot be represented by
            // ModItem.Texture. Hide the static placeholder and let
            // GeneratedHeldItemDrawLayer render the actual Z-Image sprite for tools,
            // potions/throwables and weapons alike.
            item.noUseGraphic = true;
        }

        RecordAppliedItemTrace(item, isArmor, isAccessory, actualAmmo);
    }
    private static bool IsThrustDelivery(string? delivery)
    {
        string d = (delivery ?? "").Trim().ToLowerInvariant();
        return d is "thrust" or "spear" or "spear_thrust" or "held_thrust" or "polearm" or "lance" or "pike" or "trident" or "halberd" or "naginata" or "stab" or "rapier" or "shortsword" or "short_sword";
    }


    private static bool IsFlailDelivery(string? delivery, string? family = null)
    {
        string d = (delivery ?? "").Trim().ToLowerInvariant();
        string f = (family ?? "").Trim().ToLowerInvariant();
        return d is "flail" or "chain_flail" || f is "flail" or "chain_flail" or "mace" or "anchor" or "ball_and_chain";
    }

    private static bool IsYoyoDelivery(string? delivery, string? family = null)
    {
        string d = (delivery ?? "").Trim().ToLowerInvariant();
        string f = (family ?? "").Trim().ToLowerInvariant();
        return d is "yoyo" or "yo_yo" || f is "yoyo" or "yo_yo";
    }

    private static bool IsWhipDelivery(string? delivery, string? family = null)
    {
        string d = (delivery ?? "").Trim().ToLowerInvariant();
        string f = (family ?? "").Trim().ToLowerInvariant();
        return d is "whip" or "lash" || f is "whip" or "lash";
    }


    private static bool IsFreeProjectileFamily(string? runtimeFamily)
    {
        string f = (runtimeFamily ?? "").Trim().ToLowerInvariant();
        return f is "shoot" or "cast" or "throw" or "returning" or "summon" or "flail" or "yoyo" or "whip";
    }

    private Terraria.Audio.SoundStyle UseSoundForProfile(string profile, string runtimeFamily, string effect)
    {
        string taxonomy = string.Join(" ", new[]
        {
            profile,
            Attack.WeaponSubfamily ?? "",
            Attack.ProjectileFamily ?? "",
            string.Join(" ", Attack.AttackPatternTags ?? Array.Empty<string>()),
            Attack.SoundUseSearchQuery ?? ""
        }.Where(x => !string.IsNullOrWhiteSpace(x)));
        return InfiniSoundLibrary.ForUse(
            taxonomy,
            runtimeFamily,
            effect,
            Attack.SoundVolume,
            Attack.SoundPitch,
            Attack.SoundUseCatalogId,
            Attack.SoundUseCatalogPath,
            Attack.SoundUseSearchQuery ?? "",
            Attack.SoundCatalogSource ?? "");
    }

}
