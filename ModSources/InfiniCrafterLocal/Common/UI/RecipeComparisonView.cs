#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.UI;

// Accepted base values, deliberately not estimated DPS or player/prefix-adjusted stats.
internal static class RecipeComparisonView
{
    internal readonly record struct Row(string Key, double Value, double Reference)
    {
        internal double Delta => Value - Reference;
    }
    internal static IReadOnlyList<Row> Compare(GeneratedItemData selected, GeneratedItemData reference)
    {
        var a = selected.Gameplay; var b = reference.Gameplay;
        return new Row[] {
            new("BaseDamage", a.Damage, b.Damage), new("UseTicks", a.UseTime, b.UseTime),
            new("AnimationTicks", a.UseAnimation, b.UseAnimation), new("Knockback", a.Knockback, b.Knockback),
            new("Mana", a.ManaCost, b.ManaCost), new("Pick", a.PickPower, b.PickPower),
            new("Axe", a.AxePower * 5, b.AxePower * 5), new("Hammer", a.HammerPower, b.HammerPower),
            new("Defense", selected.Accessory.Enabled ? selected.Accessory.Defense : selected.Armor.Defense,
                reference.Accessory.Enabled ? reference.Accessory.Defense : reference.Armor.Defense),
            new("Yield", a.CraftYield, b.CraftYield), new("Stack", a.MaxStack, b.MaxStack),
        };
    }
}
