#nullable enable
using System;
using InfiniCrafterLocal.Common.Players;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed class InfiniRefundsCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "ifcrefunds";
    public override string Usage => "/ifcrefunds [pause|auto|claim [row]|page]";
    public override string Description => "Inspect and recover retained craft materials without dropping them.";
    public override void Action(CommandCaller caller, string input, string[] args)
    {
        var owner = caller.Player.GetModPlayer<InfiniCraftPlayer>();
        if (args.Length > 0 && args[0] is "pause" or "auto")
            owner.SetCraftRefundDeliveryPaused(args[0] == "pause");
        else if (args.Length > 0 && args[0] == "claim")
        {
            int? row = null;
            if (args.Length > 1)
            {
                if (!int.TryParse(args[1], out int value) || value < 1) { caller.Reply(Usage); return; }
                row = value - 1;
            }
            caller.Reply($"Returned {owner.ClaimCraftRefunds(row)} units to inventory. Full stacks remain retained.");
        }
        int page = 1;
        if (args.Length > 0 && int.TryParse(args[0], out int requested)) page = Math.Max(1, requested);
        var rows = owner.CaptureCraftRefunds();
        int pages = Math.Max(1, (rows.Count + 7) / 8); page = Math.Min(page, pages);
        caller.Reply($"Craft recovery: {rows.Count} retained stacks; delivery {(owner.PauseCraftRefundDelivery ? "paused" : "automatic")}; page {page}/{pages}.");
        for (int i = (page - 1) * 8; i < Math.Min(page * 8, rows.Count); i++)
        {
            var row = rows[i];
            caller.Reply($"{row.Index + 1}. {row.Name} ×{row.Stack} (prefix {row.Prefix})" +
                (row.GeneratedId.Length > 0 ? $" [{row.GeneratedId}]" : ""));
        }
        caller.Reply("/ifcrefunds pause retains future local refunds; claim [row] returns only what fits. auto resumes normal delivery. Server escrow is not a local claim.");
    }
}
