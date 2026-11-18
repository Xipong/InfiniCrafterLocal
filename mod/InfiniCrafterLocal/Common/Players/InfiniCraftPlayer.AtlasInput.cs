#nullable enable
using InfiniCrafterLocal.Common.UI;
using Terraria;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    public override void SetControls()
    {
        if (!RecipeJournalUISystem.BlocksItemUse(Player)) return;
        Player.controlUseItem = false;
        Player.controlUseTile = false;
        Player.controlThrow = false;
        Player.channel = false;
        Player.mouseInterface = true;
    }

    // Native fast-use can reassert controlUseItem after SetControls. Reject it
    // at normal item admission without skipping ItemCheck or its timers.
    public override bool CanUseItem(Item item) => !RecipeJournalUISystem.BlocksItemUse(Player);
}