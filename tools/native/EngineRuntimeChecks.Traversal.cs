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
    private static void NativeTraversalAquatic()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            var item = NativeUtilityItem("\"swimFlipper\":true,\"divingHelm\":true,\"waterFloat\":true,\"underwaterBreathing\":false");
            item.UpdateAccessory(player, false);
            Equal(true, player.GetJumpState(ExtraJump.Flipper).Enabled, "native swim jump enabled");
            Equal(true, player.GetJumpState(ExtraJump.Flipper).Available, "native flipper repeats while swimming");
            Equal(true, player.accDivingHelm, "breath conservation enabled");
            Equal(42, player.breathCDMax, "actual native diving breath cadence is six times baseline seven");
            Equal(false, player.gills, "water breathing independently disabled");
            player.controlDown = false;
            Equal(true, player.ShouldFloatInWater, "native flotation consumer");
            player.controlDown = true;
            Equal(false, player.ShouldFloatInWater, "down input overrides buoyancy");
            player.ResetEffects();
            Equal(false, player.accDivingHelm || player.canFloatInWater || player.gills, "all aquatic effects expire");
            NativeUtilityItem("\"underwaterBreathing\":true").UpdateAccessory(player, true);
            Equal(true, player.gills, "independent gills without swim grants");
            Equal(false, player.GetJumpState(ExtraJump.Flipper).Enabled, "gills does not bundle swim");
        });
        using var actors = new NativeActorState();
        WithPersistenceTilemap((_, _) => WithPlayer((player, _) => {
            Terraria.Main.myPlayer = 0; player.whoAmI = 0; Terraria.Main.player[0] = player;
            player.position = new Microsoft.Xna.Framework.Vector2(640, 640); player.gravDir = 1;
            player.ResetEffects();
            NativeUtilityItem("\"underwaterBreathing\":true").UpdateAccessory(player, false);
            player.breath = 100; Terraria.Main.getGoodWorld = false;
            player.CheckDrowning();
            Equal(103, player.breath, "ordinary world gills preserve air breathing");
            Terraria.Main.getGoodWorld = true; player.breath = 100; player.breathCD = player.breathCDMax - 1;
            player.lavaWet = true; // suppress cosmetic bubble allocation, not drowning logic
            player.CheckDrowning();
            Equal(99, player.breath, "native special-seed gills require water");
        }));
    }
    private static void NativeTraversalClimbing()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            NativeUtilityItem("\"wallGrip\":2,\"autoJump\":true,\"frogJump\":true").UpdateAccessory(player, false);
            Equal(2, player.spikedBoots, "wall cling native level");
            NativeUtilityItem("\"wallGrip\":1").UpdateAccessory(player, false);
            Equal(2, player.spikedBoots, "weaker grip cannot erase cling");
            Equal(true, player.autoJump, "held button native repeat");
            int fall = player.extraFall; float jump = player.jumpSpeedBoost;
            player.UpdateJumpHeight();
            Equal(fall + 15, player.extraFall, "actual frog consumer adds safe fall");
            Equal(jump + 2.4f, player.jumpSpeedBoost, "actual frog consumer raises jump");
            player.ResetEffects();
            Equal(0, player.spikedBoots, "unequip removes grip");
            Equal(false, player.autoJump || player.frogLegJumpBoost, "unequip removes vertical grants");
            foreach (string invalid in new[] { "null", "3", "-1", "1.5", "true" }) {
                bool rejected = false;
                try { NativeUtilityItem("\"wallGrip\":" + invalid); } catch (InvalidOperationException) { rejected = true; }
                Equal(true, rejected, "wall grip strict native range " + invalid);
            }
        });
    }
}
