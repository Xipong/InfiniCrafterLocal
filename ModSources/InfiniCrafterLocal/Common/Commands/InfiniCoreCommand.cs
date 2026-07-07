#nullable enable
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed class InfiniCoreCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infinicore";
    public override string Description => "Give yourself an InfiniCore for testing the InfiniCraft station.";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        if (caller.Player is null) return;
        caller.Player.QuickSpawnItem(caller.Player.GetSource_Misc("InfiniCraftCoreCommand"), ModContent.ItemType<InfiniCore>(), 1);
        Main.NewText("InfiniCore added. Open inventory to use the InfiniCraft station panel.", 120, 220, 255);
    }
}
