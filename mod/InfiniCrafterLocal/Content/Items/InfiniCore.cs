#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.Localization;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

public sealed class InfiniCore : ModItem
{
    public override string Texture => "InfiniCrafterLocal/Assets/InfiniCore";

    public override void SetStaticDefaults()
    {
        // Atlas cells: 48px artwork + 2 transparent rows required by native GetFrame.
        Main.RegisterItemAnimation(Type, new DrawAnimationVertical(5, 24));
        ItemID.Sets.AnimatesAsSoul[Type] = true;
    }

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

    public override void ModifyTooltips(List<TooltipLine> tooltips)
    {
        foreach (TooltipLine line in tooltips)
        {
            if (line.Mod != "Terraria" || line.Name != "ItemName" || string.IsNullOrEmpty(line.Text))
                continue;
            // Presentation only: preserve the plain localized Item name and any foreign markup.
            if (line.Text.IndexOfAny(new[] { '[', ']', '\\', '\r', '\n' }) >= 0)
                return;
            int[] starts = StringInfo.ParseCombiningCharacters(line.Text);
            var text = new StringBuilder(line.Text.Length * 14);
            float phase = Main.GlobalTimeWrappedHourly % 4f / 4f;
            for (int i = 0; i < starts.Length; i++)
            {
                float position = starts.Length == 1 ? 0f : i / (float)(starts.Length - 1);
                float wave = (MathF.Sin((position * 0.85f - phase) * MathHelper.TwoPi) + 1f) * 0.5f;
                Color color = wave < 0.5f
                    ? Color.Lerp(new Color(255, 133, 69), new Color(255, 228, 158), wave * 2f)
                    : Color.Lerp(new Color(255, 228, 158), new Color(130, 225, 255), (wave - 0.5f) * 2f);
                int end = i + 1 < starts.Length ? starts[i + 1] : line.Text.Length;
                text.Append("[c/")
                    .Append(color.R.ToString("X2", CultureInfo.InvariantCulture))
                    .Append(color.G.ToString("X2", CultureInfo.InvariantCulture))
                    .Append(color.B.ToString("X2", CultureInfo.InvariantCulture))
                    .Append(':').Append(line.Text, starts[i], end - starts[i]).Append(']');
            }
            line.Text = text.ToString();
            return;
        }
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
        CombatText.NewText(player.Hitbox, Color.LightSkyBlue, Language.GetTextValue("Mods.InfiniCrafterLocal.StationUI.CoreOpened"));
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
