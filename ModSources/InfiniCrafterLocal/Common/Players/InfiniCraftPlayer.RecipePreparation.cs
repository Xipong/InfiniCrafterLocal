#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private string[]? _preparationParents;
    private int _preparationLane, _preparationNext;
    internal bool HasRecipePreparation => _preparationParents is not null;
    internal static int[] RecipeIngredientSlots(Player player, string world, string[] parents)
    {
        if (parents.Length != 2) return Array.Empty<int>();
        int[] slots = { -1, -1 };
        for (int p = 0; p < 2; p++)
            for (int i = 0; i < Math.Min(58, player.inventory.Length); i++)
            {
                Item item = player.inventory[i];
                string identity = RecipeIngredientIdentity.Of(item, world);
                string wanted = parents[p].StartsWith("item:Terraria:", StringComparison.Ordinal)
                    ? "item:Terraria/" + parents[p][14..] : parents[p];
                if (!InfiniCore.IsValidIngredient(item) || identity != wanted || item.stack <= (p == 1 && slots[0] == i ? 1 : 0)) continue;
                slots[p] = i; break;
            }
        return slots;
    }
    internal enum RecipePreparationReadiness { Ready, InvalidRecipe, Busy, CursorOccupied, LaneOccupied, MissingStock, ProtectedStock }
    internal RecipePreparationReadiness GetRecipePreparationReadiness(GeneratedItemData recipe, int lane)
    {
        if (lane < 0 || lane >= MultiDevWindowCount || recipe.RecipeMeta.ParentIdentities.Length != 2
            || recipe.RecipeMeta.WorldId != Main.worldID.ToString() || !recipe.RecipeMeta.WorldScoped
            || GeneratedItemData.IsPlayerSaveReferenceOnly(recipe)) return RecipePreparationReadiness.InvalidRecipe;
        if (HasRecipePreparation || HasPendingStationEscrowOperation || IsCraftLanePending(lane)) return RecipePreparationReadiness.Busy;
        if (!Main.mouseItem.IsAir) return RecipePreparationReadiness.CursorOccupied;
        if (!StationInput(lane * 2).IsAir || !StationInput(lane * 2 + 1).IsAir) return RecipePreparationReadiness.LaneOccupied;
        int[] slots = RecipeIngredientSlots(Player, recipe.RecipeMeta.WorldId, recipe.RecipeMeta.ParentIdentities);
        if (slots.All(i => i >= 0)) return RecipePreparationReadiness.Ready;
        var required = recipe.RecipeMeta.ParentIdentities.Select(id => id.Replace("item:Terraria:", "item:Terraria/", StringComparison.Ordinal))
            .GroupBy(id => id, StringComparer.Ordinal);
        bool protectedStock = true;
        foreach (var group in required)
        {
            long total = Player.inventory.Take(58).Where(item => !item.IsAir
                && RecipeIngredientIdentity.Of(item, recipe.RecipeMeta.WorldId) == group.Key
                && (item.favorited || InfiniCore.IsValidIngredient(item))).Sum(item => (long)Math.Max(0, item.stack));
            if (total < group.Count()) protectedStock = false;
        }
        return protectedStock ? RecipePreparationReadiness.ProtectedStock : RecipePreparationReadiness.MissingStock;
    }
    internal string RecipePreparationGuidance(GeneratedItemData recipe, int lane)
        => ForgePresentationText("Preparation" + GetRecipePreparationReadiness(recipe, lane));
    internal bool PrepareKnownRecipe(GeneratedItemData recipe, int lane)
    {
        if (GetRecipePreparationReadiness(recipe, lane) != RecipePreparationReadiness.Ready || !CanMutateStationInputs()) return false;
        int[] slots = RecipeIngredientSlots(Player, recipe.RecipeMeta.WorldId, recipe.RecipeMeta.ParentIdentities);
        if (slots.Length != 2 || slots.Any(i => i < 0)) return false;
        _preparationParents = (string[])recipe.RecipeMeta.ParentIdentities.Clone();
        _preparationLane = lane; _preparationNext = 0;
        return true;
    }
    internal void TickRecipePreparation()
    {
        if (_preparationParents is null) return;
        if (!IsCraftLaneVisible(_preparationLane) || !InfiniCraftStationUISystem.StationInteractionAvailable(Player) || !Main.mouseItem.IsAir || IsCraftLanePending(_preparationLane))
        { _preparationParents = null; return; }
        if (HasPendingStationEscrowOperation) return; // Exactly one durable MP operation at a time.
        if (_preparationNext >= 2) { _preparationParents = null; return; }
        if (_preparationNext == 1)
        {
            string deposited = RecipeIngredientIdentity.Of(StationInput(_preparationLane * 2), Main.worldID.ToString());
            string expected = _preparationParents[0].Replace("item:Terraria:", "item:Terraria/", StringComparison.Ordinal);
            if (deposited != expected) { _preparationParents = null; return; }
        }
        string needed = _preparationParents[_preparationNext].Replace("item:Terraria:", "item:Terraria/", StringComparison.Ordinal);
        int slot = Enumerable.Range(0, Math.Min(58, Player.inventory.Length)).FirstOrDefault(i =>
            InfiniCore.IsValidIngredient(Player.inventory[i]) && RecipeIngredientIdentity.Of(Player.inventory[i], Main.worldID.ToString()) == needed, -1);
        if (slot < 0 || !TryDepositInventoryItem(slot, _preparationLane * 2 + _preparationNext))
        { _preparationParents = null; return; }
        _preparationNext++;
    }
}
