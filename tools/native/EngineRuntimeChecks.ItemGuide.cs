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
            var data = GeneratedItemData.Placeholder();
            data.Gameplay.ManaCost = 17;
            var host = TooltipSecondaryHost(data);
            data = host.Data;
            var before = data.ToNetworkJson();
            var tooltip = new System.Collections.Generic.List<Terraria.ModLoader.TooltipLine>();
            host.ModifyRuntimeTooltips(tooltip, true);
            Equal(string.Join("\n", tooltip.Select(r => r.Text)), string.Join("\n", InfiniCrafterLocal.Content.Items.GeneratedItem.RuntimeGuide(data)), "atlas and inventory share actual facts " + locale);
            Equal(before, data.ToNetworkJson(), "guide never hydrates or normalizes authored item");
        });
 }
}
