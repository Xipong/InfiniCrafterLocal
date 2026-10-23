#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.UI;
using Terraria;

namespace InfiniCrafterLocal.Common.Runtime;

// Presentation receipts observe native Heal; they cannot restore health or drive gameplay clocks.
internal static class RuntimeHealingFeedback
{
    internal sealed record Receipt(ulong Tick, string SourceName, int Requested, int Applied);
    internal sealed record View(int Requested, int Applied, string Label, string Tooltip);
    private static ConditionalWeakTable<Player, List<Receipt>> _history = new();
    internal static void Clear() => _history = new();
    internal static void Record(Player player, string sourceName, int requested, int applied, ulong tick)
    {
        if (requested <= 0 || applied < 0 || applied > requested) return;
        var history = _history.GetOrCreateValue(player);
        history.RemoveAll(row => row.Tick > tick || tick - row.Tick >= 600);
        if (history.Count == 32) history.RemoveAt(0);
        history.Add(new(tick, sourceName, requested, applied));
    }
    internal static View? Capture(Player player, ulong tick, CultureInfo culture)
    {
        if (!_history.TryGetValue(player, out var history)) return null;
        var rows = history.Where(row => tick >= row.Tick && tick - row.Tick < 600).ToArray();
        if (rows.Length == 0) return null;
        bool ru = culture.TwoLetterISOLanguageName == "ru";
        int requested = rows.Sum(row => row.Requested), applied = rows.Sum(row => row.Applied);
        string label = (ru ? "Вампиризм: +" : "Lifesteal: +") + applied.ToString(culture) + (ru ? " ОЗ" : " HP");
        string detail = ru ? "Последние 32 срабатывания за 10 с. Показано фактически восстановленное здоровье." : "Last 32 procs within 10 seconds. Shows health actually restored.";
        detail += "\n" + (ru ? "Доступное лечение: " : "Available healing: ") + requested.ToString(culture)
            + (ru ? "; не поместилось: " : "; excess: ") + (requested - applied).ToString(culture);
        foreach (var group in rows.GroupBy(row => row.SourceName, StringComparer.Ordinal))
            detail += "\n" + GeneratedStatusTooltipView.LiteralName(group.Key) + ": +" + group.Sum(row => row.Applied).ToString(culture)
                + " / " + group.Sum(row => row.Requested).ToString(culture) + " (×" + group.Count() + ")";
        return new(requested, applied, label, detail);
    }
}
