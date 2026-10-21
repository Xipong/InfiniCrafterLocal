#nullable enable
using System.Collections.Generic;
using System.Globalization;
using InfiniCrafterLocal.Common.Players;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.UI;

internal sealed record GeneratedItemExhaustionStatusRow(
    string ItemId, string DefinitionIdentity, string ItemName, int RemainingTicks,
    string IconPath, string Label, string Tooltip);

// Per-definition rows are already owned/deduplicated by the player's live table.
// Do not combine names, effects or timers, and do not infer identity from prose.
internal static class GeneratedItemExhaustionStatusView
{
    internal const string IconPath = "InfiniCrafterLocal/Assets/Exhaustion";
    private const string Key = "Mods.InfiniCrafterLocal.RuntimeTooltip.";

    internal static IReadOnlyList<GeneratedItemExhaustionStatusRow> Build(
        IReadOnlyList<GeneratedItemExhaustionStatus> snapshot, CultureInfo culture)
    {
        var rows = new List<GeneratedItemExhaustionStatusRow>(snapshot.Count);
        foreach (GeneratedItemExhaustionStatus entry in snapshot)
        {
            if (entry.RemainingTicks <= 0) continue;
            string name = GeneratedStatusTooltipView.LiteralName(entry.ItemName);
            string display = GeneratedStatusTooltipView.CountdownSeconds(entry.RemainingTicks, culture);
            string time = Language.GetTextValue(Key + "Time", display);
            rows.Add(new(entry.ItemId, entry.DefinitionIdentity, name, entry.RemainingTicks,
                IconPath, Language.GetTextValue(Key + "ExhaustionStatus", name),
                Language.GetTextValue(Key + "ExhaustionRemaining", time)));
        }
        return rows.AsReadOnly();
    }

}
