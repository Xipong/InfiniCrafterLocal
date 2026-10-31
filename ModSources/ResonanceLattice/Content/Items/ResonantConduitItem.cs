#nullable enable
using ResonanceLattice.Content.Tiles;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace ResonanceLattice.Content.Items;

/// <summary>
/// Places a Resonant Crystal conductor node. The tile's own hooks register it into the
/// lattice; this item is only the delivery mechanism, so any other mod can place the same
/// tile (or call <see cref="Core.ResonanceLattice.NotifyNodePlaced"/>) and join the grid.
/// </summary>
public sealed class ResonantConduitItem : ModItem
{
    public override void SetDefaults()
    {
        Item.width = 22;
        Item.height = 22;
        Item.maxStack = 999;
        Item.consumable = true;
        Item.useStyle = ItemUseStyleID.Swing;
        Item.useTime = 15;
        Item.useAnimation = 15;
        Item.useTurn = true;
        Item.createTile = ModContent.TileType<ResonantCrystalTile>();
        Item.value = Item.buyPrice(silver: 5);
        Item.rare = ItemRarityID.Blue;
    }

    public override void AddRecipes()
    {
        CreateRecipe(5)
            .AddIngredient(ItemID.StoneBlock, 10)
            .AddIngredient(ItemID.FallenStar, 1)
            .AddTile(TileID.WorkBenches)
            .Register();
    }
}
