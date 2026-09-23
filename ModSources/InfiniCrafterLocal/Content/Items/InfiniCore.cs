#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using System;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

public sealed class InfiniCore : ModItem
{
    public override string Texture => "InfiniCrafterLocal/Assets/InfiniCore";

    public override void SetDefaults()
    {
        Item.width = 28;
        Item.height = 28;
        Item.maxStack = 1;
        Item.value = Item.buyPrice(silver: 50);
        Item.rare = ItemRarityID.Blue;
        Item.useStyle = ItemUseStyleID.HoldUp;
        Item.useTime = 20;
        Item.useAnimation = 20;
    }

    public override bool CanRightClick() => true;

    // tML right-click consumption does not consult Item.consumable.
    public override bool ConsumeItem(Player player) => false;

    public override void RightClick(Player player)
    {
        // InfiniCore is now a station key, not an auto-consume button.
        // The actual craft uses explicit inventory UI input slots so the player controls
        // exactly which two items are sacrificed.
        Main.playerInventory = true;
        CombatText.NewText(player.Hitbox, Color.LightSkyBlue, "InfiniCraft: use the station panel in inventory");
    }

    internal static bool IsValidIngredient(Item item)
    {
        if (item is null || item.IsAir || item.favorited || item.stack <= 0) return false;
        if (item.type == ModContent.ItemType<InfiniCore>()) return false;
        return true;
    }

    public override void AddRecipes()
    {
        Recipe recipe = CreateRecipe();
        recipe.AddRecipeGroup(RecipeGroupID.Wood, 20);
        recipe.AddIngredient(ItemID.FallenStar, 1);
        recipe.Register();
    }
}
