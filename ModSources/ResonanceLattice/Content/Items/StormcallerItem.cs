#nullable enable
using ResonanceLattice.Content.Projectiles;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace ResonanceLattice.Content.Items;

/// <summary>
/// Magic weapon that fires lattice bolts. Each bolt carries charge into the grid on impact
/// and marks hit enemies (they take bonus damage from all sources). The item itself only
/// sets vanilla shooting fields — the lattice integration lives in the projectile.
/// </summary>
public sealed class StormcallerItem : ModItem
{
    public override void SetDefaults()
    {
        Item.width = 34;
        Item.height = 34;
        Item.damage = 16;
        Item.DamageType = DamageClass.Magic;
        Item.mana = 6;
        Item.knockBack = 3f;
        Item.useStyle = ItemUseStyleID.Shoot;
        Item.useTime = 22;
        Item.useAnimation = 22;
        Item.shoot = ModContent.ProjectileType<LatticeBoltProjectile>();
        Item.shootSpeed = 14f;
        Item.noMelee = true;
        Item.autoReuse = true;
        Item.UseSound = SoundID.Item20;
        Item.value = Item.buyPrice(gold: 2);
        Item.rare = ItemRarityID.Blue;
    }

    public override void AddRecipes()
    {
        CreateRecipe()
            .AddIngredient(ItemID.ManaCrystal, 2)
            .AddIngredient(ItemID.FallenStar, 3)
            .AddIngredient(ItemID.SoulofLight, 2)
            .AddTile(TileID.Anvils)
            .Register();
    }
}
