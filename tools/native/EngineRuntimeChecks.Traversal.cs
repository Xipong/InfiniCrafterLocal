using System;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void NativeTraversalJumps()
    {
        typeof(ExtraJumpLoader).GetMethod("ResizeArrays", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!.Invoke(null, null);
        WithPlayer((player, _) => {
            player.ResetEffects();
            var item = NativeUtilityItem("\"jumpCloud\":true,\"jumpSandstorm\":true,\"jumpBlizzard\":false");
            ref var cloud = ref player.GetJumpState(ExtraJump.CloudInABottle);
            cloud.Available = false;
            item.UpdateAccessory(player, true);
            Equal(true, cloud.Enabled, "cloud grant reaches native state");
            Equal(false, cloud.Available, "equip never refills spent jump");
            Equal(true, player.GetJumpState(ExtraJump.SandstormInABottle).Enabled, "independent sandstorm grant");
            Equal(false, player.GetJumpState(ExtraJump.BlizzardInABottle).Enabled, "explicit false remains inert");
            player.RefreshMovementAbilities(doubleJumps: true);
            Equal(true, cloud.Available, "native movement refresh owns recharge");
            player.ResetEffects();
            Equal(false, cloud.Enabled, "native reset expires unequipped jumps");
            Equal(false, NativeUtilityItem("\"defense\":1").Data.ToNetworkJson().Contains("jumpCloud"), "absence survives network DTO");
            bool rejected = false;
            try { NativeUtilityItem("\"jumpCloud\":null"); } catch (InvalidOperationException) { rejected = true; }
            Equal(true, rejected, "present null rejected");
        });
    }
}
