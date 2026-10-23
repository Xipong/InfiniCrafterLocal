#nullable enable
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.UI;
using Terraria.Localization;
using Terraria.ModLoader;
namespace InfiniCrafterLocal.Common.Commands;
public sealed class InfiniEffectsCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "ifceffects";
    public override string Description => "Inspect current generated effects, individual durations and lifecycle cleanup.";
    public override void Action(CommandCaller caller, string input, string[] args)
    {
        var owner = caller.Player.GetModPlayer<InfiniCraftPlayer>();
        var snapshot = owner.CaptureGeneratedUtilityBuffPresentation();
        caller.Reply($"Generated contributions: {snapshot.Entries.Count}; remaining: {(snapshot.Current.RemainingTicks + 59) / 60}s.");
        foreach (var status in GeneratedUtilityBuffStatusView.Build(snapshot, Language.ActiveCulture.CultureInfo))
            caller.Reply(status.Label + "\n" + status.Tooltip);
        foreach (var row in owner.CaptureGeneratedItemExhaustion())
            caller.Reply($"{row.ItemName}: {(row.RemainingTicks + 59) / 60}s exhaustion [{row.ItemId}]");
        if (owner.LastGeneratedUtilityRetirement is { } retired)
            caller.Reply($"Last cleanup: {retired.Reason}; retired {retired.Contributions} contributions and {retired.ExhaustionEntries} exhaustion entries.");
    }
}
