#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Projectiles;
internal static partial class EngineRuntimeChecks
{
    private static void ChargeDashboard()
    {
        object a = new(), b = new();
        var half = new GeneratedChargeStatus(a, 90, 180, "A", 3);
        var ready = new GeneratedChargeStatus(b, 60, 60, "B", 1);
        Equal(.5f, half.RemainingSeconds, "subupdates converted to world seconds");
        var rows = GeneratedChargeUISystem.Dashboard(new[] { half, ready, half });
        Equal(2, rows.Length, "one row per physical generation"); Equal(b, rows[0].Source, "ready sources remain discoverable");
        Equal(0f, ready.RemainingSeconds, "ready has no false countdown");
        Equal(0, GeneratedChargeUISystem.Dashboard(Array.Empty<GeneratedChargeStatus>()).Length, "no stale rows after release");
        Equal(90, half.ChargeUpdates, "dashboard never advances gameplay clocks");
    }
}
