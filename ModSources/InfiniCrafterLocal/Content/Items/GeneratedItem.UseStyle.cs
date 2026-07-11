#nullable enable
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    public override void UseStyle(Player player, Rectangle heldItemFrame)
    {
        base.UseStyle(player, heldItemFrame);
        if (player.itemAnimation <= 0 || Data?.Gameplay is null)
            return;

        string heldVisibility = (Data.Gameplay.HeldVisibility ?? "").Trim().ToLowerInvariant();
        if (heldVisibility is "hide_item" or "show_projectile")
            return;

        string pose = (Data.Gameplay.HandPose ?? "").Trim().ToLowerInvariant();
        if (pose is "" or "none")
            return;

        float armRotation = player.itemRotation - MathHelper.PiOver2 * player.gravDir;
        player.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, armRotation);
        if (pose == "two_hand")
            player.SetCompositeArmBack(true, Player.CompositeArmStretchAmount.Full, armRotation);
    }
}
