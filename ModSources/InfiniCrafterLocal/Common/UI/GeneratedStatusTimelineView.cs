#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace InfiniCrafterLocal.Common.UI;

internal static class GeneratedStatusTimelineView
{
    internal sealed record Row(int RemainingTicks, string Label, string Detail);
    internal static IReadOnlyList<Row> Build(GeneratedUtilityBuffPresentation effects,
        IReadOnlyList<GeneratedItemExhaustionStatusRow> exhaustion, GeneratedMobilityCooldownStatus? mobility,
        IReadOnlyList<GeneratedReactionCooldownStatusRow> reactions, CultureInfo culture)
    {
        var rows = new List<Row>();
        foreach (var contribution in effects.Entries)
        {
            if (contribution.RemainingTicks <= 0) continue;
            var fields = GeneratedUtilityBuffStatusView.Build(new(contribution, new[] { contribution }), culture);
            if (fields.Count == 0) continue;
            rows.Add(new(contribution.RemainingTicks, string.Join(" + ", fields.Select(f => f.Label)),
                string.Join("\n\n", fields.Select(f => f.Tooltip))));
        }
        rows.AddRange(exhaustion.Where(e => e.RemainingTicks > 0).Select(e => new Row(e.RemainingTicks, e.Label, e.Tooltip)));
        if (mobility is { RemainingTicks: > 0 }) rows.Add(new(mobility.RemainingTicks, mobility.Label, mobility.Tooltip));
        rows.AddRange(reactions.Where(r => r.RemainingTicks > 0).Select(r => new Row(r.RemainingTicks, r.Label, r.Tooltip)));
        // Keep multiplicity: equal contribution clocks still represent separate entries.
        return rows.OrderBy(r => r.RemainingTicks).ThenBy(r => r.Label, StringComparer.CurrentCulture).ToArray();
    }
}
