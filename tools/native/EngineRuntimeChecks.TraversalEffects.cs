using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void PlayerTraversalUsesNativeFieldsAndReset()
    {
        using var actors = new NativeActorState();
        WithPlayer((player, effects) => {
            player.active = true; player.statLife = 50;
            using var hooks = new NativeUtilityPlayerHooks(effects);
            var item = NativeUtilityItem("\"playerEffect\":{\"autoJump\":true,\"gravityControl\":true,\"gravityMultiplier\":0.5,\"maxFallSpeedPxPerTick\":4,\"safeFallDistanceBlocks\":9,\"waterBreathing\":true,\"swimJump\":true,\"waterBuoyancy\":true,\"wallSlideAndJump\":true,\"wallCling\":true,\"breathCapacityBonus\":60}");
            player.ResetEffects(); item.UpdateAccessory(player, true);
            player.gravity = .4f; player.maxFallSpeed = 10;
            effects.PostUpdateRunSpeeds();
            Equal(true, player.autoJump, "native repeated jump input enabled");
            Equal(true, player.gravControl, "native gravity controls enabled");
            Equal(.2f, player.gravity, "authored multiplier changes the actual gravity before integration");
            Equal(4f, player.maxFallSpeed, "authored fall speed reaches actual native cap");
            Equal(9, player.extraFall, "safe distance is separate from fall immunity");
            Equal(false, player.noFallDmg, "safe distance does not silently grant immunity");
            Equal(true, player.gills, "water breathing reaches native consumer");
            Equal(true, player.accFlipper, "swim input reaches native consumer");
            Equal(true, player.canFloatInWater, "buoyancy reaches native consumer");
            Equal(2, player.spikedBoots, "strongest explicit wall contact mechanic wins");
            Equal(260, player.breathMax, "breath capacity is independent from breathing mode");
            player.ResetEffects(); item.UpdateAccessory(player, true);
            Equal(260, player.breathMax, "native reset prevents breath bonus accumulating each tick");
            player.ResetEffects();
            Equal(200, player.breathMax, "removing source restores native breath capacity");
            Equal(false, player.autoJump, "removing source retires jump-input modifier");
            Equal(false, player.gills, "removing source retires breathing modifier");
        });
    }

    private static void PlayerTraversalBuffPhysicsAndCodec()
    {
        using var actors = new NativeActorState();
        WithPlayer((player, effects) => {
            player.active = true; player.statLife = 50;
            var modifier = new PlayerEffectSpec { GravityMultiplier = .5f, MaxFallSpeedPxPerTick = 4,
                AutoJump = true, BreathCapacityBonus = 60, SafeFallDistanceBlocks = 9 };
            Equal(true, effects.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 2, PlayerEffect = modifier }), "traversal-only generated buff admitted");
            effects.ResetEffects(); effects.PostUpdateEquips();
            player.gravity = .4f; player.maxFallSpeed = 10; effects.PostUpdateRunSpeeds();
            Equal(.2f, player.gravity, "buff and equipment share real gravity execution");
            Equal(4f, player.maxFallSpeed, "buff contributes native fall-speed cap");
            using var stream = new System.IO.MemoryStream();
            using (var writer = new System.IO.BinaryWriter(stream, System.Text.Encoding.UTF8, true)) modifier.Write(writer);
            stream.Position = 0;
            var read = PlayerEffectSpec.Read(new System.IO.BinaryReader(stream));
            Equal(true, PlayerEffectSpec.SameEffect(modifier, read), "typed binary codec preserves all traversal values");
            effects.ResetEffects(); effects.PostUpdateEquips();
            effects.ResetEffects(); effects.PostUpdateEquips();
            player.gravity = .4f; player.maxFallSpeed = 10; effects.PostUpdateRunSpeeds();
            Equal(.4f, player.gravity, "expired buff retires gravity contribution");
            Equal(10f, player.maxFallSpeed, "expired buff retires fall-speed cap");
        });
    }
    private static void PlayerTraversalBuffRetainsSourceAndSpentCharges()
    {
        using var native = new NativeAirJumpScope();
        using var registry = new FrontHandRepairScope();
        WithPlayer((player, effects) => {
            player.active = true; player.statLife = 50; player.whoAmI = 0; player.gravDir = 1;
            Terraria.Main.player[0] = player;
            var data = NamedItemEffectsFixture(); data.Id = "airjump-buff-codec"; data.SourceMode = "test_fixture";
            data.RuntimeProgram.EffectGroups![0].GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 3,
                PlayerEffect = new PlayerEffectSpec { AirJump = new PlayerAirJumpSpec { Count = 1, LaunchSpeedPxPerTick = 8, HoldDurationTicks = 3 } } };
            data = GeneratedItemData.FromJson(data.ToNetworkJson()) ?? throw new System.InvalidOperationException("jump buff fixture refused");
            registry.Register(data);
            var buff = data.RuntimeProgram.EffectGroups![0].GeneratedBuff!;
            Equal(true, effects.ApplyGeneratedUtilityBuff(buff, source:data), "exact authored named buff admitted");
            ResetNativeAirJumpTick(player, effects); effects.PostUpdateEquips();
            Equal(true, effects.TryGetLiveAirJumpSource(data.Id, out _, out long generation), "buff resolves source without a held or equipped item");
            Equal(true, generation < 0, "buff lifetime token is disjoint from equipment tokens");
            var binding = InfiniCrafterLocal.Common.VFX.VfxSourceBinding.CaptureAirJump(player, data.Id, generation)!;
            player.RefreshExtraJumps(); Terraria.ModLoader.ExtraJumpLoader.ProcessJumps(player);
            Equal(-8f, player.velocity.Y, "actual buff contributes authored native jump");
            using var snapshot = new System.IO.MemoryStream();
            typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!
                .Invoke(effects, new object[] { new System.IO.BinaryWriter(snapshot) });
            snapshot.Position = 1;
            typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!
                .Invoke(effects, new object[] { new System.IO.BinaryReader(snapshot) });
            ResetNativeAirJumpTick(player, effects); effects.PostUpdateEquips();
            Equal(true, effects.TryGetLiveAirJumpSource(data.Id, out _, out long restored), "typed snapshot rehydrates the exact source component");
            Equal(generation, restored, "snapshot preserves lifetime identity");
            Equal(true, binding.IsLive, "snapshot of same lifetime retains attached VFX");
            for (int tick = 0; tick < 3; tick++) { ResetNativeAirJumpTick(player, effects); effects.PostUpdateEquips(); }
            Equal(false, binding.IsLive, "actual buff expiry retires attached source");
            Equal(false, native.Jump.CanStart(player), "expired actual buff supplies no native jump");
            Equal(true, effects.ApplyGeneratedUtilityBuff(buff, source:data), "same authored buff may start another lifetime");
            ResetNativeAirJumpTick(player, effects); effects.PostUpdateEquips();
            Equal(true, effects.TryGetLiveAirJumpSource(data.Id, out _, out long renewed), "renewed buff resolves independently");
            Equal(true, renewed < generation, "renewed lifetime never reuses source token");
            Equal(false, binding.IsLive, "old attachment does not revive with equal buff");
            Equal(false, native.Jump.CanStart(player), "renewed airborne buff does not refill the spent component charge");
        });
    }

}
