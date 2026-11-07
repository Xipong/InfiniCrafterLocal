using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private uint? _lastGeneratedUseNoticeTick;

    internal static string GeneratedUseFeedbackText(string key, params object[] args)
        => Language.GetTextValue("Mods.InfiniCrafterLocal.UseFeedback." + key, args);

    // Shared by this player's items: auto-reuse and swapping items cannot flood chat.
    // Unsigned elapsed time also handles the native update counter wrapping.
    internal bool TryReserveGeneratedUseNotice(uint tick)
    {
        if (_lastGeneratedUseNoticeTick is uint previous && unchecked(tick - previous) < 60)
            return false;
        _lastGeneratedUseNoticeTick = tick;
        return true;
    }

    internal void NotifyGeneratedUseRefusal(string message)
    {
        if (Main.dedServ || Main.netMode == NetmodeID.Server || Player.whoAmI != Main.myPlayer
            || string.IsNullOrWhiteSpace(message) || !TryReserveGeneratedUseNotice(Main.GameUpdateCount))
            return;
        Main.NewText(message, Color.OrangeRed);
    }
}
