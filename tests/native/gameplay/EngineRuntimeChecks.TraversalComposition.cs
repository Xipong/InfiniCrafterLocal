using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Only pre-fix hooks/APIs are used, so the same observers can be overlaid on
    // the baseline for RED. No world loop, movement detour or synthesized native tail.
    private static GeneratedItem TraversalCompositionItem(string effect)
    {
        var fixture = NativeUtilityItem("\"playerEffect\":{" + effect + "}");
        var item = new Item();
        item.SetDefaults(ItemID.CopperShortsword);
        AttachItem(fixture, item, fixture.Data);
        fixture.Data.ApplyToItem(item);
        return fixture;
    }

    private static Item TraversalNativeItem(int type)
    {
        var item = new Item();
        item.SetDefaults(type);
        return item;
    }

    private static void PrepareTraversalCompositionPlayer(Player player)
    {
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        // Avoid unrelated local music-box/UI paths; single-player gameplay
        // authority still runs. NativeActorState restores these globals.
        Terraria.Main.myPlayer = 255;
        player.whoAmI = 0;
        Terraria.Main.player[0] = player;
        player.active = true;
        player.dead = false;
        player.statLife = 50;
        player.gravDir = 1;
        player.selectedItem = 0;
    }

    private static void NativeTraversalWallGrantsComposeAfterEquipment()
    {
        using var actors = new NativeActorState();
        using var jumps = new NativeAirJumpScope();
        var failures = new List<string>();
        foreach (bool cling in new[] { false, true })
        foreach (bool generatedFirst in new[] { false, true })
        foreach (bool hidden in new[] { false, true })
        foreach (int[] nativeTypes in new[] { Array.Empty<int>(), new[] { 953 }, new[] { 975 }, new[] { 953, 975 } })
        {
            string label = $"{(cling ? "cling" : "slide")}, generatedFirst={generatedFirst}, hidden={hidden}, native={string.Join(",", nativeTypes)}";
            try
            {
                WithPlayer((player, owner) => {
                    PrepareTraversalCompositionPlayer(player);
                    using var hooks = new NativeUtilityPlayerHooks(owner);
                    var generated = TraversalCompositionItem((cling ? "\"wallCling\":true" : "\"wallSlideAndJump\":true")
                        + ",\"breathCapacityBonus\":7");
                    for (int tick = 0; tick < 2; tick++)
                    {
                        player.ResetEffects();
                        // Real native accessory function -> ItemLoader -> GeneratedItem.
                        if (generatedFirst) player.ApplyEquipFunctional(generated.Item, hidden);
                        foreach (int type in nativeTypes) player.ApplyEquipFunctional(TraversalNativeItem(type), hidden);
                        if (!generatedFirst) player.ApplyEquipFunctional(generated.Item, hidden);
                        PlayerLoader.PostUpdateEquips(player);
                        Equal(Math.Max(cling ? 2 : 1, nativeTypes.Length), player.spikedBoots, label + " final mode");
                        Equal(207, player.breathMax, label + " unrelated contribution exactly once per tick");
                    }
                    player.ResetEffects();
                    foreach (int type in nativeTypes) player.ApplyEquipFunctional(TraversalNativeItem(type), hidden);
                    PlayerLoader.PostUpdateEquips(player);
                    Equal(nativeTypes.Length, player.spikedBoots, label + " generated donor removed, native donors retained");
                    Equal(200, player.breathMax, label + " unrelated contribution retires");
                    player.ResetEffects();
                    PlayerLoader.PostUpdateEquips(player);
                    Equal(0, player.spikedBoots, label + " all donors removed");
                });
            }
            catch (Exception error) { failures.Add(label + ": " + error.Message); }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void NativeTraversalWallBuffComposesBeforeFinalGrant()
    {
        using var actors = new NativeActorState();
        using var jumps = new NativeAirJumpScope();
        WithPlayer((player, owner) => {
            PrepareTraversalCompositionPlayer(player);
            using var hooks = new NativeUtilityPlayerHooks(owner);
            foreach (bool clingBuff in new[] { false, true })
            {
                // Separate inputs: the late buff must not disappear behind an
                // earlier generated floor. Neither input enables both flags.
                var equipment = TraversalCompositionItem(clingBuff ? "\"wallSlideAndJump\":true" : "\"wallCling\":true");
                Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec {
                    DurationTicks = 1,
                    PlayerEffect = clingBuff ? new PlayerEffectSpec { WallCling = true }
                        : new PlayerEffectSpec { WallSlideAndJump = true },
                }), "one-tick independent wall buff admitted");
                player.ResetEffects();
                player.ApplyEquipFunctional(equipment.Item, true);
                PlayerLoader.PostUpdateEquips(player);
                Equal(2, player.spikedBoots, "buff and equipment compose before final wall grant");
                player.ResetEffects();
                player.ApplyEquipFunctional(TraversalNativeItem(953), true);
                PlayerLoader.PostUpdateEquips(player);
                Equal(1, player.spikedBoots, "expired buff and removed equipment cannot strengthen a native slide grant");
            }
            player.ResetEffects();
            player.ApplyEquipFunctional(TraversalNativeItem(953), true);
            player.ApplyEquipFunctional(TraversalNativeItem(975), true);
            PlayerLoader.PostUpdateEquips(player);
            Equal(2, player.spikedBoots, "two ordinary native climbing accessories still compose to cling");
        });
    }

    private static void NativeTraversalBuoyancyEquipmentDoesNotGrantFlipper()
        => NativeTraversalWaterComposition(fromBuff: false);

    private static void NativeTraversalBuoyancyBuffDoesNotGrantFlipper()
        => NativeTraversalWaterComposition(fromBuff: true);

    private static void NativeTraversalWaterComposition(bool fromBuff)
    {
        using var actors = new NativeActorState();
        using var jumps = new NativeAirJumpScope();
        var failures = new List<string>();
        // Independent single-feature inputs, not a fixture with both flags set.
        foreach (bool buoyancy in new[] { false, true })
        foreach (int nativeType in new[] { 0, ItemID.Flipper, 4404 }) // 4404: native Inner Tube buoyancy.
        foreach (bool generatedFirst in new[] { false, true })
        {
            string label = $"{(fromBuff ? "buff" : "equipment")}/{(buoyancy ? "buoyancy" : "swim")}, native={nativeType}, generatedFirst={generatedFirst}";
            try
            {
                WithPlayer((player, owner) => {
                    PrepareTraversalCompositionPlayer(player);
                    using var hooks = new NativeUtilityPlayerHooks(owner);
                    var generated = TraversalCompositionItem(buoyancy ? "\"waterBuoyancy\":true" : "\"swimJump\":true");
                    if (fromBuff)
                        Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec {
                            DurationTicks = 2, PlayerEffect = generated.Data.Accessory.PlayerEffect,
                        }), label + " independent buff admitted");
                    int generatedSlot = generatedFirst ? 3 : 4, nativeSlot = generatedFirst ? 4 : 3;
                    if (!fromBuff) player.armor[generatedSlot] = generated.Item;
                    if (nativeType != 0) player.armor[nativeSlot] = TraversalNativeItem(nativeType);
                    void Tick()
                    {
                        player.ResetEffects(); // Native flags and production accumulators reset through PlayerLoader.
                        player.wet = true;
                        player.controlDown = false;
                        // Full actual equipment function, including ApplyEquipFunctional,
                        // ItemLoader hooks and wet && ShouldFloatInWater -> accFlipper.
                        player.UpdateEquips(player.whoAmI);
                        PlayerLoader.PostUpdateEquips(player);
                    }
                    for (int tick = 0; tick < 2; tick++)
                    {
                        Tick();
                        AssertTraversalWaterState(player, buoyancy || nativeType == 4404,
                            !buoyancy || nativeType != 0, label + " active tick " + tick);
                    }
                    player.armor[generatedSlot] = new Item();
                    Tick(); // A two-tick buff has now expired too.
                    AssertTraversalWaterState(player, nativeType == 4404, nativeType != 0,
                        label + " generated removal/expiry preserves native equipment");
                    player.armor[nativeSlot] = new Item();
                    Tick();
                    AssertTraversalWaterState(player, false, false, label + " all sources removed");
                });
            }
            catch (Exception error) { failures.Add(label + ": " + error.Message); }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void AssertTraversalWaterState(Player player, bool buoyancy, bool swim, string label)
    {
        Equal(buoyancy, player.canFloatInWater, label + " buoyancy grant");
        Equal(buoyancy, player.ShouldFloatInWater, label + " actual wet buoyancy eligibility");
        Equal(swim, player.accFlipper, label + " native flipper flag");
        Equal(swim, player.GetJumpState(ExtraJump.Flipper).Enabled, label + " native FlipperJump enabled");
        Equal(swim, player.GetJumpState(ExtraJump.Flipper).Available, label + " native FlipperJump available");
        player.jump = 0;
        player.velocity = Vector2.UnitY;
        ExtraJumpLoader.ProcessJumps(player);
        Equal(swim, player.GetJumpState(ExtraJump.Flipper).Active, label + " actual native jump dispatch");
        Equal(swim, player.jump > 0 && player.velocity.Y < 0, label + " actual native jump impulse");
        if (!swim) Equal(Vector2.UnitY, player.velocity, label + " buoyancy alone cannot launch a swimming jump");
        player.StopExtraJumpInProgress();
    }
}
