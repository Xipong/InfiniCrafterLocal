#nullable enable
using Microsoft.Xna.Framework;
using ResonanceLattice.Core;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace ResonanceLattice.Content.Items;

/// <summary>
/// Consumable charge cell. Using it injects <see cref="LatticeLimits.CellChargeAmount"/>
/// into the nearest network. In multiplayer the using client sends a validated request to
/// the server (distance + cooldown + amount caps), so the item works identically for any mod
/// that calls <see cref="ResonanceLattice.InjectCharge"/>.
/// </summary>
public sealed class AetherCellItem : ModItem
{
    public override void SetDefaults()
    {
        Item.width = 20;
        Item.height = 24;
        Item.maxStack = 999;
        Item.consumable = true;
        Item.useStyle = ItemUseStyleID.HoldUp;
        Item.useTime = 25;
        Item.useAnimation = 25;
        Item.value = Item.buyPrice(silver: 20);
        Item.rare = ItemRarityID.Blue;
    }

    public override bool? UseItem(Player player)
    {
        // Single player applies directly; a multiplayer client sends a server request via
        // the facade. The server itself never applies remote players' item use directly.
        if (Main.netMode == NetmodeID.SinglePlayer
            || (Main.netMode == NetmodeID.MultiplayerClient && player.whoAmI == Main.myPlayer))
        {
            ResonanceLattice.InjectCharge(player.Center, LatticeLimits.CellChargeAmount);
        }
        return null;
    }

    public override void AddRecipes()
    {
        CreateRecipe(3)
            .AddIngredient(ItemID.FallenStar, 3)
            .AddIngredient(ItemID.ManaCrystal, 1)
            .AddTile(TileID.WorkBenches)
            .Register();
    }
}
