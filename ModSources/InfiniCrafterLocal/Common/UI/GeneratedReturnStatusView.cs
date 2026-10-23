#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using InfiniCrafterLocal.Content.Projectiles;

namespace InfiniCrafterLocal.Common.UI;

internal static class GeneratedReturnStatusView
{
    internal sealed record Row(string Name, string SpritePath, string Tooltip, int RemainingTicks);
    internal static IReadOnlyList<Row> Build(IEnumerable<GeneratedReturnStatus> statuses, CultureInfo culture)
    {
        bool ru = culture.TwoLetterISOLanguageName == "ru";
        return statuses.GroupBy(s => s.ItemId, StringComparer.Ordinal).Select(group =>
        {
            var first = group.First();
            string label = GeneratedStatusTooltipView.LiteralName(first.Name) + " ×" + group.Count();
            string detail = ru ? "Активные возвратные снаряды (занимают свои слоты):" : "Active returning projectiles (still occupying their slots):";
            foreach (var state in group.OrderBy(s => s.Phase, StringComparer.Ordinal).ThenBy(s => s.RemainingTicks))
            {
                string phase = state.Phase switch {
                    "waiting" => ru ? "Ожидает активации" : "Waiting for activation",
                    "returning" => ru ? "Возвращается" : "Returning",
                    "held" => ru ? "Удерживается; отпустите кнопку для возврата" : "Held; release input to return",
                    _ => ru ? "Летит от игрока" : "Outbound",
                };
                detail += "\n" + phase + " · " + state.DistanceBlocks.ToString("0.0", culture) + (ru ? " блоков" : " blocks");
                if (state.ReturnInTicks > 0) detail += (ru ? "; возврат через " : "; turns back in ") + GeneratedStatusTooltipView.CountdownSeconds(state.ReturnInTicks, culture) + (ru ? " с" : " s");
            }
            return new Row(label, first.SpritePath, detail, group.Max(s => s.RemainingTicks));
        }).ToArray();
    }
}
