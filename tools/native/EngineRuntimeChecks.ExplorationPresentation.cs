#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Content.Items;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ExplorationPresentation(GeneratedItem generated, params string[] fields)
    {
        typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(generated, new TooltipProbeMod());
        string before = generated.Data.ToNetworkJson();
        WithForgePresentationLanguages(locale => {
            var rows = new List<TooltipLine>(); generated.ModifyRuntimeTooltips(rows, true);
            foreach (string field in fields)
            {
                string name = "InfiniEquipment" + char.ToUpperInvariant(field[0]) + field[1..];
                Equal(true, rows.Any(row => row.Name == name && !row.Text.Contains("Mods.InfiniCrafterLocal.", StringComparison.Ordinal)),
                    "localized exact native exploration fact " + field + " " + locale);
            }
        });
        Equal(before, generated.Data.ToNetworkJson(), "exploration tooltip is read only");
    }
}
