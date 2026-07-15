#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Audio;
using System;
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

    private static string AttackRuntimeFamily(AttackSpec? attack)
        => GeneratedRuntimeFamilyPolicy.Normalize(attack?.RuntimeFamily);

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
        item.useAnimation = Math.Max(6, Gameplay.UseAnimation);
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

        item.DamageType = GeneratedDamageClassPolicy.Resolve(Gameplay.DamageClass);

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
            bool thrustLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Thrust);
            bool flailLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Flail);
            bool yoyoLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Yoyo);
            bool whipLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Whip);
            bool chargeReleaseLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.ChargeRelease);
            bool sentryLike = GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Sentry);
            bool projectileOwnedUse = GeneratedRuntimeFamilyPolicy.IsProjectileOwned(runtimeFamily);
            projectileOwnedUse = projectileOwnedUse
                && GeneratedRuntimeFamilyPolicy.UsesProjectileOnlyItemAffordance(runtimeFamily, Attack.Delivery);
            if (Attack.UseStyleCode > ItemUseStyleID.None)
                item.useStyle = Attack.UseStyleCode;
            item.noMelee = Attack.DisableItemMeleeHitbox || projectileOwnedUse;
            item.noUseGraphic = Attack.HideUseGraphic || projectileOwnedUse;
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
                // Held-thrust geometry is projectile-owned, while Rapier vs Shoot style
                // remains the explicit authored Terraria animation affordance.
                item.useStyle = Attack.UseStyleCode > ItemUseStyleID.None
                    ? Attack.UseStyleCode
                    : ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
            }
            else if (flailLike)
            {
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
            }
            else if (yoyoLike)
            {
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.channel = true;
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
            }
            else if (whipLike)
            {
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
            }
            else if (chargeReleaseLike)
            {
                item.useStyle = ItemUseStyleID.Shoot;
                item.noUseGraphic = true;
                item.noMelee = true;
                item.channel = true;
                // Charge-release owns its use sound at the actual release frame.
                item.UseSound = null;
            }
            else if (sentryLike)
            {
                item.sentry = true;
                item.useStyle = ItemUseStyleID.Swing;
                item.noUseGraphic = false;
                item.noMelee = true;
                item.channel = false;
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
            }
            else if (bowLike)
            {
                // Preserve vanilla bow affordance: consume arrows and use bow sound, while still
                // spawning the generated projectile in Shoot().
                item.useAmmo = AmmoID.Arrow;
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
                item.noUseGraphic = true;
            }
            else if (gunLike)
            {
                item.useAmmo = AmmoID.Bullet;
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
                item.noUseGraphic = true;
            }
            else if (launcherLike)
            {
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
                item.noUseGraphic = true;
            }
            else
            {
                item.UseSound = UseSoundForCatalog(runtimeFamily, Attack.Effect);
                if (hasRuntimeItemSprite || projectileOwnedUse)
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
    private Terraria.Audio.SoundStyle UseSoundForCatalog(string runtimeFamily, string effect)
    {
        return InfiniSoundLibrary.ForUse(
            runtimeFamily,
            Attack.Delivery,
            effect,
            Attack.SoundVolume,
            Attack.SoundPitch,
            Attack.SoundPitchVariance,
            Attack.SoundUseCatalogId,
            Attack.SoundUseCatalogPath,
            Attack.SoundCatalogSource ?? "");
    }
}
