#nullable enable
using InfiniCrafterLocal.Content.Projectiles;
using System;
using System.Linq;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Exact v5 DTO -> Terraria Item projection. The projection may translate one
/// authored capability into the tModLoader fields required to express that same
/// capability, but it never chooses a weapon archetype, movement, delivery path,
/// attachment, controller, or lifecycle from category/name/prose.
/// </summary>
public sealed partial class GeneratedItemData
{
    private const int NoPlacementType = -1;

    internal static (bool IsArmor, bool IsAccessory) ResolveEquipmentRoles(
        GameplaySpec gameplay,
        AccessorySpec accessory,
        ArmorSpec armor)
    {
        _ = gameplay; // UI category is deliberately not gameplay authority.
        bool isArmor = armor?.Enabled == true;
        bool isAccessory = accessory?.Enabled == true;
        if (isArmor && isAccessory)
            throw new InvalidOperationException("A generated item cannot be both armor and accessory");
        return (isArmor, isAccessory);
    }

    public void ApplyToItem(Item item)
    {
        Normalize();
        (bool isArmor, bool isAccessory) = ResolveEquipmentRoles(Gameplay, Accessory, Armor);

        item.SetNameOverride(Name);
        item.width = Math.Max(8, Gameplay.Width);
        item.height = Math.Max(8, Gameplay.Height);
        item.value = Math.Max(0, Gameplay.Value);
        item.rare = Gameplay.Rarity;
        item.maxStack = Math.Max(1, Gameplay.MaxStack);
        item.scale = 1f; // Per-instance authored scale is applied in ModifyItemScale.

        item.damage = Math.Max(0, Gameplay.Damage);
        item.knockBack = Gameplay.Knockback;
        item.DamageType = TerrariaRuntimeVocabulary.ResolveDamageClass(Gameplay.DamageClass);
        item.useTime = Math.Max(1, Gameplay.UseTime);
        item.useAnimation = Math.Max(1, Gameplay.UseAnimation);
        item.useStyle = Gameplay.UseStyle;
        item.autoReuse = Gameplay.AutoReuse;
        item.useTurn = Gameplay.UseTurn;
        item.channel = RuntimeProgram.ItemUse.Channel;
        item.noUseGraphic = RuntimeProgram.ItemUse.HideUseGraphic;
        item.noMelee = RuntimeProgram.PrimaryOwner != RuntimeProgramSpec.ItemBodyOwner
            || RuntimeProgram.ItemUse.DisableMeleeHitbox
            || !RuntimeProgram.ItemContact.Enabled;
        item.mana = Math.Max(0, Gameplay.ManaCost);
        item.consumable = Gameplay.Consumable;
        item.healLife = Math.Max(0, Gameplay.HealLife);
        item.healMana = Math.Max(0, Gameplay.HealMana);
        item.potion = Gameplay.Potion;
        item.buffType = Gameplay.BuffCode;
        item.buffTime = Gameplay.BuffTime;
        item.pick = Math.Max(0, Gameplay.PickPower);
        item.axe = Math.Max(0, Gameplay.AxePower);
        item.hammer = Math.Max(0, Gameplay.HammerPower);
        item.createTile = Gameplay.CreateTile;
        item.createWall = Gameplay.CreateWall;
        item.placeStyle = Math.Max(0, Gameplay.PlaceStyle);
        item.accessory = isAccessory;

        // The low-level binding is the only reason to install the generated
        // projectile proxy. It does not matter whether the item looks like a
        // sword, bow, staff, sentry, furniture, or none of those.
        RuntimeBindingSpec? primary = RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse);
        RuntimeBindingSpec? alternate = RuntimeProgram.BindingForInput(RuntimeInputKind.AlternateUse);
        bool spawnsRuntimeEntity = primary?.Action == RuntimeBindingAction.SpawnEntity
            || alternate?.Action == RuntimeBindingAction.SpawnEntity;
        item.shoot = spawnsRuntimeEntity ? ModContent.ProjectileType<GeneratedProjectile>() : ProjectileID.None;
        RuntimeEntitySpec? primaryEntity = primary?.Action == RuntimeBindingAction.SpawnEntity
            ? RuntimeProgram.TryGetEntity(primary.Target)
            : null;
        item.shootSpeed = primaryEntity?.Spawn.SpeedPxPerTick ?? 0f;

        // Exact Terraria ammo-item projection. Item.ammo means “this item is ammo”;
        // Item.useAmmo would mean “this weapon consumes ammo” and is intentionally not
        // inferred here. The projectile ID is authored explicitly rather than selected
        // from a family/category table.
        item.ammo = TerrariaRuntimeVocabulary.ResolveAmmoCategory(Gameplay.AmmoCategory);
        item.notAmmo = Gameplay.NotAmmo;
        if (item.ammo != AmmoID.None)
        {
            item.shoot = Gameplay.AmmoProjectileId;
            item.shootSpeed = Gameplay.AmmoShootSpeedPxPerTick;
            item.noMelee = true;
        }

        bool placeable = item.createTile > NoPlacementType || item.createWall > NoPlacementType;
        if (placeable && RuntimeProgram.Bindings.Any(x => x.Action == RuntimeBindingAction.PlaceItem))
        {
            // These are tModLoader plumbing obligations of the explicitly
            // authored place_item binding, not an inferred gameplay design.
            item.useTurn = true;
            item.noMelee = true;
        }

        if (isArmor)
        {
            item.defense = Math.Max(0, Armor.Defense);
            ConfigureNonUsableEquipmentItem(item);
        }
        else if (isAccessory)
        {
            item.defense = Math.Max(0, Accessory.Defense);
            ConfigureNonUsableEquipmentItem(item);
        }

        // Sound is supplied by exact entity/event VFX slots. There is no
        // category/family-derived fallback sound at this gameplay boundary.
        item.UseSound = null;
    }

    private static void ConfigureNonUsableEquipmentItem(Item item)
    {
        item.damage = 0;
        item.knockBack = 0f;
        item.useStyle = ItemUseStyleID.None;
        item.useTime = 1;
        item.useAnimation = 1;
        item.noUseGraphic = true;
        item.noMelee = true;
        item.autoReuse = false;
        item.channel = false;
        item.consumable = false;
        item.maxStack = 1;
        item.shoot = ProjectileID.None;
    }
}
