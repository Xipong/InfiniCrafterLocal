#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
 private static void ItemGuide()
 {
        WithForgePresentationLanguages(locale => {
            var data = MobilityConsumptionFixture("recall_home", 1);
            data.Gameplay.ManaCost = 17;
            var host = TooltipSecondaryHost(data);
            data = host.Data;
            data.Gameplay.ManaCost = 17;
            var before = data.ToNetworkJson();
            var tooltip = new System.Collections.Generic.List<Terraria.ModLoader.TooltipLine>();
            host.ModifyRuntimeTooltips(tooltip, true);
            Equal(string.Join("\n", tooltip.Select(r => r.Text)), string.Join("\n", InfiniCrafterLocal.Content.Items.GeneratedItem.RuntimeGuide(data)), "atlas and inventory share actual facts " + locale);
            var all = InfiniCrafterLocal.Content.Items.GeneratedItem.RuntimeGuide(data);
            var controls = InfiniCrafterLocal.Content.Items.GeneratedItem.RuntimeGuide(data, InfiniCrafterLocal.Content.Items.GeneratedItem.GuideSection.Controls);
            Equal(true, controls.Count > 0 && controls.All(all.Contains), "section filter uses the same exact facts");
            Equal(0, InfiniCrafterLocal.Content.Items.GeneratedItem.RuntimeGuide(data, query: "no_such_fact_zzzz").Count, "search does not invent facts");
            var selected = InfiniCrafterLocal.Content.Items.GeneratedItem.RuntimeGuide(data, query: "17");
            Equal(true, selected.Count > 0, "actual mana contract searchable");
            Equal(before, data.ToNetworkJson(), "guide never hydrates or normalizes authored item");
        });
 }
}
