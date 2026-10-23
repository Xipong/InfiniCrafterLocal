#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed class InfiniDefinitionsCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "ifcdefinitions";
    public override string Usage => "/ifcdefinitions [held|retry]";
    public override string Description => DefinitionRecoveryView.Text("Help");
    public override void Action(CommandCaller caller, string input, string[] args)
    {
        string action = args.Length == 0 ? "status" : args[0].ToLowerInvariant();
        if (args.Length > 1 || action is not ("status" or "held" or "retry")) { caller.Reply(Usage); return; }
        var items = (action == "held" ? new[] { caller.Player.HeldItem } : caller.Player.inventory.Take(58))
            .Where(i => !i.IsAir && i.ModItem is GeneratedItem).Select(i => (GeneratedItem)i.ModItem).ToArray();
        if (items.Length == 0) { caller.Reply(DefinitionRecoveryView.Text("Empty")); return; }
        int attempted = 0;
        // Every physical cached reference may hydrate; missing ids are still coalesced by the registry.
        if (action == "retry") foreach (var item in items) if (item.RecoverDefinition()) attempted++;
        foreach (var group in items.GroupBy(i => (i.Data.RecipeMeta.WorldId, i.Data.Id)))
        {
            var item = group.First();
            caller.Reply(GeneratedStatusTooltipView.LiteralName(item.Data.Name) + " × " + group.Count()
                + ": " + DefinitionRecoveryView.Describe(item.Data));
            if (action == "held") caller.Reply(DefinitionRecoveryView.Text("Identity", item.Data.Id, item.Data.RecipeMeta.WorldId));
        }
        caller.Reply(action == "retry" ? DefinitionRecoveryView.Text("Retried", attempted) : DefinitionRecoveryView.Text("Help"));
    }
}
