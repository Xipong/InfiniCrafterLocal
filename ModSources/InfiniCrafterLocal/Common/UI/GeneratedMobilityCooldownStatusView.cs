#nullable enable
using System.Globalization;
using Terraria.ID;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.UI;

internal sealed record GeneratedMobilityCooldownStatus(int RemainingTicks, int IconBuffType, string Label, string Tooltip);

// One shared player mobility timer, not per-item generated-buff exhaustion.
// The caller reads the existing owner; this adapter cannot start/extend a timer,
// occupy buff slots, block actions or impose native ChaosState penalties.
internal static class GeneratedMobilityCooldownStatusView
{
    private const string Key = "Mods.InfiniCrafterLocal.RuntimeTooltip.";

    internal static GeneratedMobilityCooldownStatus? Build(int remainingTicks, CultureInfo culture)
    {
        if (remainingTicks <= 0) return null;
        decimal seconds = remainingTicks / 60m;
        string display = seconds.ToString("0.###", culture);
        if (decimal.Round(seconds, 3) != seconds) display = "≈" + display;
        string time = Language.GetTextValue(Key + "Time", display);
        // Borrow only the native teleport-cooldown texture. Never apply its buff.
        return new(remainingTicks, BuffID.ChaosState,
            Language.GetTextValue(Key + "MobilityCooldownStatus"),
            Language.GetTextValue(Key + "MobilityCooldownRemaining", time));
    }
}
