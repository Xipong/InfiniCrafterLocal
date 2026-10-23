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
    private static void NativeTraversalBuilding()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            int range = player.blockRange; float tiles = player.tileSpeed, walls = player.wallSpeed;
            NativeUtilityItem("\"buildRangeTiles\":3,\"tileSpeedBonusPercent\":25,\"wallSpeedBonusPercent\":50,\"autoPaint\":true,\"rulerGrid\":true").UpdateAccessory(player, true);
            Equal(range + 3, player.blockRange, "reach composes with native tools");
            Equal(tiles + .25f, player.tileSpeed, "tile speed is native additive bonus");
            Equal(walls + .5f, player.wallSpeed, "wall speed independent");
            Equal(true, player.autoPaint && player.rulerGrid, "paint and grid native consumers enabled");
            Equal(true, player.rulerLine, "native baseline ruler remains untouched");
            NativeUtilityItem("\"buildRangeTiles\":2").UpdateAccessory(player, false);
            Equal(range + 5, player.blockRange, "range combines additively");
            player.ResetEffects();
            Equal(range, player.blockRange, "range expires on reset");
            Equal(tiles, player.tileSpeed, "tile speed expires on reset");
            Equal(false, player.autoPaint || player.rulerGrid, "builder flags expire");
            foreach (string field in new[] { "buildRangeTiles", "tileSpeedBonusPercent", "wallSpeedBonusPercent" }) {
                bool rejected = false;
                try { NativeUtilityItem("\"" + field + "\":101"); } catch (InvalidOperationException) { rejected = true; }
                Equal(true, rejected, "strict building bound " + field);
            }
        });
    }
    private static void NativeTraversalGravity()
    {
        WithPlayer((player, _) => {
            player.ResetEffects();
            player.gravDir = -1f; player.fallStart = 123;
            NativeUtilityItem("\"gravityControl\":true,\"featherFall\":true,\"extraFallTiles\":12").UpdateAccessory(player, false);
            Equal(true, player.gravControl && player.slowFall, "native gravity and slow-fall grants");
            Equal(12, player.extraFall, "authored fall threshold in tiles");
            Equal(-1f, player.gravDir, "equip never forces orientation");
            Equal(123, player.fallStart, "equip never erases actual fall distance");
            Equal(false, player.noFallDmg, "finite fall allowance is not immunity");
            NativeUtilityItem("\"extraFallTiles\":7").UpdateAccessory(player, true);
            Equal(19, player.extraFall, "fall allowance composes additively");
            player.ResetEffects();
            Equal(false, player.gravControl || player.slowFall, "native reset removes control grants");
            Equal(0, player.extraFall, "native reset removes fall allowance");
            foreach (string invalid in new[] { "null", "101", "-1", "1.5" }) {
                bool rejected = false;
                try { NativeUtilityItem("\"extraFallTiles\":" + invalid); } catch (InvalidOperationException) { rejected = true; }
                Equal(true, rejected, "strict fall allowance bound " + invalid);
            }
        });
        WithForgePresentationLanguages(locale => {
            var data = NativeUtilityItem("\"gravityControl\":true,\"featherFall\":true,\"extraFallTiles\":12").Data;
            var host = TooltipSecondaryHost(data);
            string guide = string.Join("\n", InfiniCrafterLocal.Content.Items.GeneratedItem.RuntimeGuide(host.Data));
            Equal(false, guide.Contains("Mods.InfiniCrafterLocal"), "localized gravity guide " + locale);
            Equal(true, guide.Contains("12"), "guide includes actual safe fall allowance");
        });
    }
}
