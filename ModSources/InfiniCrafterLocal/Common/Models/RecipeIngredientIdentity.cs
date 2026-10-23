#nullable enable
using System;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
namespace InfiniCrafterLocal.Common.Models;
internal static class RecipeIngredientIdentity
{
    internal static string Of(Item? item, string world)
    {
        if (item is null || item.IsAir) return "";
        if (item.ModItem is GeneratedItem generated)
            return generated.Data.RecipeMeta.WorldScoped && generated.Data.RecipeMeta.WorldId == world
                && !GeneratedItemData.IsPlayerSaveReferenceOnly(generated.Data) ? "generated:" + generated.Data.Id : "";
        string name = item.ModItem is { } mod ? mod.Mod.Name + "/" + mod.Name : "Terraria/" + ItemID.Search.GetName(item.type);
        return "item:" + name + ":" + item.type;
    }
}
