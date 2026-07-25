#nullable enable
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    public override void UseStyle(Player player, Rectangle heldItemFrame)
    {
        base.UseStyle(player, heldItemFrame);
        if (player.itemAnimation <= 0) return;
        string pose = Data.RuntimeProgram.ItemUse.HandPose;
        if (pose.Length == 0) return;
        float rotation = player.itemRotation - MathHelper.PiOver2 * player.gravDir;
        player.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, rotation);
        if (pose == "two_handed")
            player.SetCompositeArmBack(true, Player.CompositeArmStretchAmount.Full, rotation);
    }
}
