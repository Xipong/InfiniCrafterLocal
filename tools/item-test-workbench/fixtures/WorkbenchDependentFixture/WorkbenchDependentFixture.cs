#nullable enable
using System;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using WorkbenchObserverFixture;

// This independent test mod has an actual assembly and declared mod dependency.
// Its item uses the other mod's registered projectile; neither owns host code.
namespace WorkbenchDependentFixture;

public sealed class WorkbenchDependentFixture : Mod
{
    public override void Load()
    {
        if (!global::WorkbenchObserverFixture.WorkbenchObserverFixture.Loaded)
            throw new InvalidOperationException("Dependency Load must run before dependent Load");
    }
}

public sealed class DependentItem : ModItem
{
    public override string Texture => "Terraria/Images/Item_98";
    public override void SetDefaults()
    {
        Item.width = 20;
        Item.height = 20;
        Item.damage = 20;
        Item.DamageType = DamageClass.Ranged;
        Item.useTime = 20;
        Item.useAnimation = 20;
        Item.useStyle = ItemUseStyleID.Shoot;
        Item.noMelee = true;
        Item.shoot = ModContent.ProjectileType<ProbeProjectile>();
        Item.shootSpeed = 8;
        Item.knockBack = 0;
    }
}

// An independently autoloaded native hook modifies the dependent item's damage.
// The verifier disables just this hook for a real combat ablation.
public sealed class DependentGlobalItem : GlobalItem
{
    public override void ModifyWeaponDamage(Item item, Player player, ref StatModifier damage)
    {
        if (item.type == ModContent.ItemType<DependentItem>() &&
            !string.Equals(Environment.GetEnvironmentVariable("IFC_FIXTURE_DISABLE_DEPENDENT_DAMAGE"), "1", StringComparison.Ordinal))
            damage.Flat += 7;
    }
}
