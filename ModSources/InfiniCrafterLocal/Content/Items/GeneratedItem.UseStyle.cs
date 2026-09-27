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
        // Match vanilla's itemRotation -> composite-arm conversion (Rapier use
        // style). itemRotation is already gravity-adjusted; SetCompositeArmFront /
        // Back apply gravity themselves, while the quarter turn depends on facing.
        float rotation = player.itemRotation * player.gravDir - MathHelper.PiOver2 * player.direction;
        player.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, rotation);
        if (pose == "two_handed")
            player.SetCompositeArmBack(true, Player.CompositeArmStretchAmount.Full, rotation);
    }
}
