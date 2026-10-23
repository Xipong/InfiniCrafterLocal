#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks { private static void StationInspection() {
        WithForgePresentationLanguages(locale => {
            var item = new Terraria.Item(Terraria.ID.ItemID.CopperPickaxe); item.damage = 37; item.pick = 55; item.stack = 2;
            var rows = InfiniCraftStationUISystem.StationInspectionRows(item);
            Equal(true, rows.Any(r => r.Contains("37")), "exact instance damage shown " + locale);
            Equal(true, rows.Any(r => r.Contains("55")), "exact tool power shown " + locale);
            Equal(false, rows.Any(r => r.Contains("Mods.InfiniCrafterLocal.")), "localized inspection " + locale);
            Equal(37, item.damage, "inspection does not apply a projection"); Equal(2, item.stack, "inspection does not take ingredients");
        });
} }
