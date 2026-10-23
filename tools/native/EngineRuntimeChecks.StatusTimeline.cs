using System;
using System.Globalization;
using System.Linq;
using InfiniCrafterLocal.Common.UI;

internal static partial class EngineRuntimeChecks
{
    private static void QolStatusTimeline()
    {
        var early = new GeneratedUtilityBuffValues(61, 1, 0, "white", 0, .2f, 0, 0, 0);
        var later = early with { RemainingTicks = 180 };
        var rows = GeneratedStatusTimelineView.Build(new(later, new[] { later, early, early }),
            Array.Empty<GeneratedItemExhaustionStatusRow>(), new(120, 0, "mobility", "remaining"),
            Array.Empty<GeneratedReactionCooldownStatusRow>(), CultureInfo.GetCultureInfo("en-US"));
        Equal(4, rows.Count, "timeline retains independent equal contributions and cooldown");
        Equal("61,61,120,180", string.Join(",", rows.Select(r => r.RemainingTicks)), "chronological actual deadlines");
        Equal("2", GeneratedStatusTooltipView.CountdownSeconds(rows[0].RemainingTicks, CultureInfo.InvariantCulture), "timeline positive remainder rounds upward");
        Equal(61, early.RemainingTicks, "presentation cannot decrement the source clock");
    }
}
