#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks { private static void StationPicker() {
var inventory = Enumerable.Range(0, 60).Select(_ => new Terraria.Item()).ToArray();
        inventory[0].SetDefaults(Terraria.ID.ItemID.CopperOre); inventory[0].stack = 5;
        inventory[1].SetDefaults(Terraria.ID.ItemID.CopperOre); inventory[1].stack = 10;
        inventory[2].SetDefaults(Terraria.ID.ItemID.CopperOre); inventory[2].favorited = true;
        inventory[58].SetDefaults(Terraria.ID.ItemID.CopperOre);
        var slots = InfiniCraftStationUISystem.IngredientPickerSlots(inventory, "", true);
        Equal(true, slots.SequenceEqual(new[] { 1, 0 }), "Picker includes only eligible owned inventory, sorts quantity deterministically.");
        Equal(true, InfiniCraftStationUISystem.IngredientPickerSlots(inventory, "unmatched query", false).Length == 0, "Search excludes unmatched candidates.");
        Equal(true, inventory[0].stack == 5 && inventory[1].stack == 10, "Browsing must not transfer inventory.");
} }
