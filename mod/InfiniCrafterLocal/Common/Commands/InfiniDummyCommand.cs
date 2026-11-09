#nullable enable
using System;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed class InfiniDummyCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infinidummy";
    public override string Usage => "/infinidummy [count]";
    public override string Description => "Give yourself Target Dummy item(s) for testing generated weapon damage.";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        Player player = caller.Player;
        if (player is null) return;
        int count = 1;
        if (args.Length > 0 && int.TryParse(args[0], out int parsed))
            count = Math.Clamp(parsed, 1, 99);
        player.QuickSpawnItem(player.GetSource_Misc("InfiniCraftDummyCommand"), ItemID.TargetDummy, count);
        Main.NewText($"InfiniCraft: Target Dummy x{count} added to inventory.", 120, 220, 255);
    }
}
