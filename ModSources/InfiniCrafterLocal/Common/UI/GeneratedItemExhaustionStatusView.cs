#nullable enable
using System.Collections.Generic;
using System.Globalization;
using System.Text;
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
            string name = LiteralName(entry.ItemName);
            decimal seconds = entry.RemainingTicks / 60m;
            string display = seconds.ToString("0.###", culture);
            if (decimal.Round(seconds, 3) != seconds) display = "≈" + display;
            string time = Language.GetTextValue(Key + "Time", display);
            rows.Add(new(entry.ItemId, entry.DefinitionIdentity, name, entry.RemainingTicks,
                IconPath, Language.GetTextValue(Key + "ExhaustionStatus", name),
                Language.GetTextValue(Key + "ExhaustionRemaining", time)));
        }
        return rows.AsReadOnly();
    }

    // A display-only bound in Unicode scalars; never edit the record or Data.Name.
    // Removing brackets prevents Terraria chat tags; control/format/separator
    // characters cannot inject a second label or hide the mechanical explanation.
    private static string LiteralName(string value)
    {
        var result = new StringBuilder(96);
        int count = 0;
        foreach (Rune rune in (value ?? "").EnumerateRunes())
        {
            UnicodeCategory category = Rune.GetUnicodeCategory(rune);
            if (rune.Value is '[' or ']' || category is UnicodeCategory.Control
                or UnicodeCategory.Format or UnicodeCategory.LineSeparator or UnicodeCategory.ParagraphSeparator)
                continue;
            if (count++ >= 96) break;
            result.Append(rune.ToString());
        }
        return result.ToString();
    }
}
