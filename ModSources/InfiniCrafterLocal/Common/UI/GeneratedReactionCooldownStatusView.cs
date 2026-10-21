#nullable enable
using System.Collections.Generic;
using System.Globalization;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.UI;

internal sealed record GeneratedReactionCooldownStatusRow(
    string ItemId, string ActionId, string SpritePath, int RemainingTicks, string Label, string Tooltip);

internal static class GeneratedReactionCooldownStatusView
{
    private const string Key = "Mods.InfiniCrafterLocal.RuntimeTooltip.";
    internal static IReadOnlyList<GeneratedReactionCooldownStatusRow> Build(
        IReadOnlyList<GeneratedReactionCooldownStatus> snapshot, CultureInfo culture)
    {
        var rows = new List<GeneratedReactionCooldownStatusRow>(snapshot.Count);
        foreach (var entry in snapshot)
        {
            if (entry.RemainingTicks <= 0 || entry.Event is not (RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill)) continue;
            string reaction = Language.GetTextValue(Key + (entry.Event == RuntimeEventKind.OnHurt ? "ReactionHurt" : "ReactionKill"));
            string time = Language.GetTextValue(Key + "Time", GeneratedStatusTooltipView.CountdownSeconds(entry.RemainingTicks, culture));
            rows.Add(new(entry.ItemId, entry.ActionId, entry.SpritePath, entry.RemainingTicks,
                Language.GetTextValue(Key + "ReactionCooldownStatus", GeneratedStatusTooltipView.LiteralName(entry.ItemName), reaction),
                Language.GetTextValue(Key + "ReactionCooldownRemaining", reaction, time)));
        }
        return rows.AsReadOnly();
    }
}
