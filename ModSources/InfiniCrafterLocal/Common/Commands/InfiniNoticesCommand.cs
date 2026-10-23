#nullable enable
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.UI;
using Terraria.Localization;
using Terraria.ModLoader;
namespace InfiniCrafterLocal.Common.Commands;
public sealed class InfiniNoticesCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "ifcnotices";
    public override string Usage => "/ifcnotices [clear]";
    public override string Description => CraftNotificationUISystem.Text("Help");
    public override void Action(CommandCaller caller, string input, string[] args)
    {
        var owner = caller.Player.GetModPlayer<InfiniCraftPlayer>();
        if (args.Length == 1 && args[0] == "clear") owner.AcknowledgeAllCraftNotifications();
        foreach (var row in owner.CaptureCraftNotifications())
            caller.Reply(CraftNotificationUISystem.Text("CommandRow", row.Lane + 1,
                CraftNotificationUISystem.OutcomeLabel(row.Outcome.Kind), row.Outcome.Message,
                Language.GetTextValue("Mods.InfiniCrafterLocal.StationUI.HistoryMaterials" + row.Outcome.Materials)));
        caller.Reply(CraftNotificationUISystem.Text("CommandSummary", owner.UnreadCraftNotificationCount, owner.OverflowCraftNotificationCount));
    }
}
