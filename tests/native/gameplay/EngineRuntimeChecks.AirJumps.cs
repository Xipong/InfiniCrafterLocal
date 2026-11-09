#nullable enable
using System;
using System.Collections;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Register the production ExtraJump without launching tML, a world or GPU.
    // Player allocates its native jump-state array after this scope is created.
    private sealed class NativeAirJumpScope : IDisposable
    {
        private const BindingFlags Static = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        private readonly IList jumps = (IList)typeof(ExtraJumpLoader).GetField("ExtraJumps", Static)!.GetValue(null)!;
        private readonly FieldInfo ordered = typeof(ExtraJumpLoader).GetField("orderedJumps", Static)!;
        private readonly PropertyInfo singleton = typeof(ContentInstance<GeneratedAirJump>).GetProperty("Instance")!;
        private readonly object? previousOrder, previousSingleton;
        private readonly int previousCount, height;
        private readonly float speed;
        internal readonly GeneratedAirJump Jump = new();

        public NativeAirJumpScope()
        {
            previousCount = jumps.Count; previousOrder = ordered.GetValue(null); previousSingleton = singleton.GetValue(null);
            height = Player.jumpHeight; speed = Player.jumpSpeed;
            int type = (int)typeof(ExtraJumpLoader).GetMethod("Add", Static)!.Invoke(null, new object[] { Jump })!;
            typeof(ExtraJump).GetProperty("Type")!.SetValue(Jump, type);
            singleton.SetValue(null, Jump);
            typeof(ExtraJumpLoader).GetMethod("ResizeArrays", Static)!.Invoke(null, null);
            Player.jumpHeight = 15; Player.jumpSpeed = 5.01f;
        }

        public void Dispose()
        {
            while (jumps.Count > previousCount) jumps.RemoveAt(jumps.Count - 1);
            ordered.SetValue(null, previousOrder); singleton.SetValue(null, previousSingleton);
            Player.jumpHeight = height; Player.jumpSpeed = speed;
        }
    }

    private static GeneratedItemData AirJumpSource(string id)
    {
        var data = NativeUtilityItem("\"playerEffect\":{\"airJump\":{\"count\":2,\"launchSpeedPxPerTick\":9.25,\"holdDurationTicks\":4,\"horizontalAccelerationMultiplier\":1.5,\"horizontalSpeedMultiplier\":2}}").Data;
        data.Id = id;
        GeneratedItemRegistryService.StampCurrentWorld(data);
        return data;
    }

    private static void NativeJumpMovement(Player player)
        // Exercise the production detour with the real native movement body;
        // this loader-free harness does not install process-global detours.
        => GeneratedAirJumpLifecycleSystem.JumpMovement(
            p => typeof(Player).GetMethod("JumpMovement", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.Invoke(p, null), player);

    private static void ResetNativeAirJumpTick(Player player, InfiniCraftPlayer owner)
    {
        typeof(ExtraJumpLoader).GetMethod("ResetEnableFlags", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { player });
        owner.ResetEffects();
    }

    private static void AuthoredAirJumpUsesNativeDurationAndMovement()
    {
        using var scope = new NativeAirJumpScope();
        WithPlayer((player, owner) => {
            player.active = true; player.gravDir = 1; player.velocity = Vector2.UnitY;
            var source = AirJumpSource("airjump-motion");
            ResetNativeAirJumpTick(player, owner);
            owner.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect!.AirJump!, 11);
            player.RefreshExtraJumps();
            player.controlJump = player.releaseJump = true;
            NativeJumpMovement(player);
            Equal(true, player.GetJumpState(scope.Jump).Active, "native loader starts the custom jump");
            Equal(4, player.jump, "native duration multiplier preserves authored ticks");
            Equal(-9.25f, player.velocity.Y, "authored launch replaces native common speed");
            Equal(true, player.GetJumpState(scope.Jump).Available, "remaining authored charge reuses native slot");
            player.runAcceleration = 0.1f; player.maxRunSpeed = 3;
            ExtraJumpLoader.UpdateHorizontalSpeeds(player);
            Equal(0.15f, player.runAcceleration, "active native jump applies authored acceleration");
            Equal(6f, player.maxRunSpeed, "active native jump applies authored speed multiplier");
            owner.PreUpdateMovement();
            for (int frame = 1; frame < 4; frame++) {
                owner.PreUpdate(); NativeJumpMovement(player);
                Equal(-9.25f, player.velocity.Y, "native held movement consumes the authored speed at its impulse");
                owner.PreUpdateMovement();
                Equal(-9.25f, player.velocity.Y, "late movement hook does not rewrite the authored impulse");
            }
            owner.PreUpdate(); NativeJumpMovement(player);
            Equal(false, player.GetJumpState(scope.Jump).Active, "authored hold window stops before next native impulse");
            Equal(0, player.jump, "native held timer is stopped with the active jump");
            Equal(-9.25f, player.velocity.Y, "expiry cannot insert a vanilla jump-speed impulse");
            player.releaseJump = true; player.gravDir = -1;
            NativeJumpMovement(player);
            Equal(9.25f, player.velocity.Y, "authored launch follows inverted gravity");
            Equal(false, player.GetJumpState(scope.Jump).Available, "last authored charge is consumed");
            player.controlJump = false; NativeJumpMovement(player); player.StopExtraJumpInProgress();
            Equal(false, player.GetJumpState(scope.Jump).Active, "native release cancellation remains effective");
        });
    }

    private static void AuthoredAirJumpCannotRefillFromEquipmentSwap()
    {
        using var scope = new NativeAirJumpScope();
        WithPlayer((player, owner) => {
            player.active = true; player.gravDir = 1;
            var source = AirJumpSource("airjump-first");
            var other = AirJumpSource("airjump-late");
            var movement = source.Accessory.PlayerEffect!.AirJump!;
            ResetNativeAirJumpTick(player, owner); owner.RegisterAirJumpGrant(source, movement, 11);
            player.RefreshExtraJumps(); ExtraJumpLoader.ProcessJumps(player);
            Equal(true, player.GetJumpState(scope.Jump).Available, "one charge remains after first jump");
            ResetNativeAirJumpTick(player, owner); owner.RegisterAirJumpGrant(other, movement, 21);
            Equal(false, scope.Jump.CanStart(player), "newly equipped airborne definition has no refreshed charges");
            ResetNativeAirJumpTick(player, owner); owner.RegisterAirJumpGrant(source, movement, 12);
            ExtraJumpLoader.ProcessJumps(player);
            Equal(false, player.GetJumpState(scope.Jump).Available, "a different physical copy spends the same last definition charge");
            ResetNativeAirJumpTick(player, owner); owner.RegisterAirJumpGrant(source, movement, 13);
            Equal(false, scope.Jump.CanStart(player), "same-definition replacement cannot refill spent charges");
            player.RefreshExtraJumps();
            Equal(true, scope.Jump.CanStart(player), "native ground or grapple refresh restores authored charges");
            ExtraJumpLoader.ProcessJumps(player);
            Equal(true, player.GetJumpState(scope.Jump).Available, "count is restored exactly by native refresh");
            ResetNativeAirJumpTick(player, owner);
            typeof(ExtraJumpLoader).GetMethod("ConsumeAndStopUnavailableJumps", BindingFlags.Static | BindingFlags.NonPublic)!
                .Invoke(null, new object[] { player });
            owner.RegisterAirJumpGrant(source, movement, 14);
            Equal(false, player.GetJumpState(scope.Jump).Available, "unequip and enable does not restore native availability midair");
        });
    }

    private static void AuthoredAirJumpSourceLifetimeRetiresVfx()
    {
        using var actors = new NativeActorState();
        using var scope = new NativeAirJumpScope();
        WithPlayer((player, owner) => {
            player.active = true; player.whoAmI = 0; Terraria.Main.player[0] = player;
            var source = AirJumpSource("airjump-lifetime");
            var movement = source.Accessory.PlayerEffect!.AirJump!;
            var host = ReviewItem(source); player.armor[3] = host.Item;
            long firstGeneration = host.PresentationToken;
            ResetNativeAirJumpTick(player, owner); owner.RegisterAirJumpGrant(source, movement, firstGeneration);
            var binding = VfxSourceBinding.CaptureAirJump(player, source.Id, firstGeneration)!;
            Equal(true, binding.IsLive, "active source has a live VFX binding before charge consumption");
            player.RefreshExtraJumps(); ExtraJumpLoader.ProcessJumps(player); ExtraJumpLoader.ProcessJumps(player);
            Equal(true, binding.IsLive, "spending all charges does not retire a still-equipped source");
            Equal(true, binding.TryFrame("self", out _), "source binding resolves owner motion");
            player.armor[3] = new Item(); ResetNativeAirJumpTick(player, owner);
            Equal(false, binding.IsLive, "equipment or buff expiry retires its source binding");
            var replacement = ReviewItem(source); player.armor[3] = replacement.Item;
            long renewedGeneration = replacement.PresentationToken;
            owner.RegisterAirJumpGrant(source, movement, renewedGeneration);
            Equal(false, binding.IsLive, "same definition with a new lifetime cannot revive detached VFX");
            var renewed = VfxSourceBinding.CaptureAirJump(player, source.Id, renewedGeneration)!;
            Equal(true, renewed.IsLive, "renewed source gets its own valid binding");
            player.RefreshExtraJumps(); ExtraJumpLoader.ProcessJumps(player);
            Equal(true, player.GetJumpState(scope.Jump).Available, "death fixture has an unused charge");
            player.dead = true; owner.UpdateDead();
            Equal(false, renewed.IsLive, "death clears grants and presentation lifetime");
            player.dead = false; ResetNativeAirJumpTick(player, owner);
            owner.RegisterAirJumpGrant(source, movement, renewedGeneration);
            Equal(false, scope.Jump.CanStart(player), "actual UpdateDead retires the ledger before an airborne respawn");
            Equal(false, renewed.IsLive, "same physical source after respawn cannot revive a dead-life VFX binding");
            var respawned = VfxSourceBinding.CaptureAirJump(player, source.Id, renewedGeneration);
            Equal(true, respawned.IsLive, "new life can create a new presentation binding");
            new GeneratedAirJumpLifecycleSystem().OnWorldUnload();
            owner.RegisterAirJumpGrant(source, movement, renewedGeneration);
            Equal(false, respawned.IsLive, "world retirement fences old bindings even when the source token returns");
        });
    }

    private static void AuthoredAirJumpPreservesDownstreamMovement()
    {
        using var scope = new NativeAirJumpScope();
        WithPlayer((player, owner) => {
            player.active = true;
            var source = AirJumpSource("airjump-native-phases");
            float nativeSpeed = Player.jumpSpeed;
            foreach (float gravityDirection in new[] { 1f, -1f }) {
                player.StopExtraJumpInProgress();
                player.gravDir = gravityDirection; player.velocity = Vector2.UnitY;
                ResetNativeAirJumpTick(player, owner);
                owner.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect!.AirJump!, 11);
                player.RefreshExtraJumps(); player.controlJump = player.releaseJump = true;
                for (int tick = 0; tick < 4; tick++) {
                    NativeJumpMovement(player);
                    Equal(-9.25f * gravityDirection, player.velocity.Y, "native start/hold has the selected impulse");
                    Equal(nativeSpeed, Player.jumpSpeed, "shared jump speed restored before downstream movement");
                    // Explicit seam emulation, not a complete Player.Update:
                    // native gravity and other movement run AFTER JumpMovement
                    // and BEFORE the ModPlayer PreUpdateMovement hook.
                    player.gravity = .4f;
                    player.velocity.Y += player.gravity * gravityDirection;
                    float afterGravity = player.velocity.Y;
                    owner.PreUpdateMovement();
                    Equal(afterGravity, player.velocity.Y, "authored held jump cannot erase native gravity");
                    player.velocity.Y *= .8f;
                    float afterOtherMovement = player.velocity.Y;
                    owner.PreUpdateMovement();
                    Equal(afterOtherMovement, player.velocity.Y, "late movement changes remain authoritative");
                }
                float expiredVelocity = player.velocity.Y;
                NativeJumpMovement(player);
                Equal(false, player.GetJumpState(scope.Jump).Active, "exact hold duration ends at native impulse boundary");
                Equal(expiredVelocity, player.velocity.Y, "expiration does not add a vanilla-speed impulse");
            }
            player.RefreshExtraJumps(); player.controlJump = player.releaseJump = true;
            NativeJumpMovement(player);
            bool threw = false;
            try {
                GeneratedAirJumpLifecycleSystem.JumpMovement(_ => {
                    Equal(9.25f, Player.jumpSpeed, "authored speed is scoped to the native held consumer");
                    throw new InvalidOperationException("native movement test failure");
                }, player);
            }
            catch (InvalidOperationException error) when (error.Message == "native movement test failure") { threw = true; }
            Equal(true, threw, "movement failure is not swallowed");
            Equal(nativeSpeed, Player.jumpSpeed, "native failure cannot leak authored speed into another player");
        });
    }

    private static void AuthoredAirJumpRetiresSourceBeforeNativeImpulse()
    {
        using var scope = new NativeAirJumpScope();
        WithPlayer((player, owner) => {
            player.active = true; player.gravDir = 1; player.velocity = Vector2.UnitY;
            var first = AirJumpSource("airjump-retired");
            var second = AirJumpSource("airjump-retained");
            second.Accessory.PlayerEffect!.AirJump = second.Accessory.PlayerEffect.AirJump! with { LaunchSpeedPxPerTick = 12f };
            ResetNativeAirJumpTick(player, owner);
            owner.RegisterAirJumpGrant(first, first.Accessory.PlayerEffect!.AirJump!, 11);
            owner.RegisterAirJumpGrant(second, second.Accessory.PlayerEffect!.AirJump!, 21);
            player.RefreshExtraJumps(); player.controlJump = player.releaseJump = true;
            NativeJumpMovement(player);
            Equal(-9.25f, player.velocity.Y, "first component owns the active held jump");
            ResetNativeAirJumpTick(player, owner);
            owner.RegisterAirJumpGrant(second, second.Accessory.PlayerEffect.AirJump!, 21);
            Equal(true, player.GetJumpState(scope.Jump).Enabled, "another source keeps the shared native slot enabled");
            player.velocity.Y = -2f;
            NativeJumpMovement(player);
            Equal(false, player.GetJumpState(scope.Jump).Active, "retired active source is stopped before native hold");
            Equal(0, player.jump, "retired source cannot leave a native hold timer");
            Equal(-2f, player.velocity.Y, "source retirement cannot leak one vanilla-speed impulse");
            Equal(true, player.GetJumpState(scope.Jump).Available, "retiring one source does not spend the other source");
            player.releaseJump = true; NativeJumpMovement(player);
            Equal(-12f, player.velocity.Y, "next input consumes the still-live independent source");
        });
    }

    private sealed class AirJumpDurationModifier : ModPlayer
    {
        public override void ModifyExtraJumpDurationMultiplier(ExtraJump jump, ref float duration)
        {
            if (jump is GeneratedAirJump) duration *= 2f;
        }
    }

    private static void AuthoredAirJumpComponentsKeepIndependentCharges()
    {
        using var actors = new NativeActorState();
        using var scope = new NativeAirJumpScope();
        using var registry = new FrontHandRepairScope();
        WithPlayer((player, owner) => {
            player.active = true; player.whoAmI = 0; player.gravDir = 1; Terraria.Main.player[0] = player;
            var source = NamedItemEffectsFixture();
            source.Id = "airjump-composition"; source.SourceMode = "test_fixture";
            GeneratedItemRegistryService.StampCurrentWorld(source);
            var first = new PlayerAirJumpSpec { Count = 1, LaunchSpeedPxPerTick = 7f, HoldDurationTicks = 4 };
            var second = first with { Count = 2, LaunchSpeedPxPerTick = 12f };
            source.RuntimeProgram.EffectGroups![0].GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 2,
                PlayerEffect = new PlayerEffectSpec { AirJump = first } };
            source.RuntimeProgram.EffectGroups[1].GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 4,
                PlayerEffect = new PlayerEffectSpec { AirJump = second } };
            source = GeneratedItemData.FromJson(source.ToNetworkJson())
                ?? throw new InvalidOperationException("same-item jump component fixture rejected");
            registry.Register(source);
            ResetNativeAirJumpTick(player, owner);
            owner.RegisterAirJumpGrant(source, first with { LaunchSpeedPxPerTick = 8 }, -1, "group:primary_effects");
            owner.RegisterAirJumpGrant(source, first, -1, "group:missing");
            Equal(false, owner.CanStartGeneratedAirJump(), "different movement or a missing component cannot grant native movement");
            Equal(false, owner.TryGetLiveAirJumpSource(source.Id, out _, out _),
                "a fabricated grant is not a live presentation source");
            var firstBuff = source.RuntimeProgram.EffectGroups![0].GeneratedBuff!;
            var secondBuff = source.RuntimeProgram.EffectGroups[1].GeneratedBuff!;
            Equal(true, owner.ApplyGeneratedUtilityBuff(firstBuff, source: source), "first exact named buff admitted");
            Equal(true, owner.ApplyGeneratedUtilityBuff(secondBuff, source: source), "second exact named buff admitted");
            ResetNativeAirJumpTick(player, owner); owner.PostUpdateEquips();
            var rows = AirJumpBuffRows(owner);
            var firstBinding = VfxSourceBinding.CaptureAirJump(player, source.Id, rows[0].Generation);
            var secondBinding = VfxSourceBinding.CaptureAirJump(player, source.Id, rows[1].Generation);
            Equal(true, firstBinding.IsLive, "first named group source lifetime is independently live");
            Equal(true, secondBinding.IsLive, "second same-item named buff lifetime is independently live");
            player.RefreshExtraJumps(); ExtraJumpLoader.ProcessJumps(player);
            Equal(-7f, player.velocity.Y, "first authored component supplies its own charge and motion");
            ExtraJumpLoader.ProcessJumps(player);
            Equal(-12f, player.velocity.Y, "next component retains its distinct authored motion");
            Equal(true, player.GetJumpState(scope.Jump).Available, "second component has an independent remaining charge");
            ExtraJumpLoader.ProcessJumps(player);
            Equal(false, player.GetJumpState(scope.Jump).Available, "all component counts are consumed exactly");
            ResetNativeAirJumpTick(player, owner); owner.PostUpdateEquips();
            Equal(true, firstBinding.IsLive, "first component retains its final movement tick");
            ResetNativeAirJumpTick(player, owner);
            Equal(false, firstBinding.IsLive, "expired component cannot retain VFX through another same-item buff");
            Equal(true, secondBinding.IsLive, "the exact remaining component lifetime keeps its VFX");
            Equal(true, owner.ApplyGeneratedUtilityBuff(firstBuff, source: source), "expired component starts a new actual lifetime");
            Equal(true, owner.ApplyGeneratedUtilityBuff(secondBuff, source: source), "still-live component refresh keeps its actual lifetime");
            ResetNativeAirJumpTick(player, owner); owner.PostUpdateEquips();
            Equal(false, scope.Jump.CanStart(player), "renewing or refreshing either lifetime cannot refill its component ledger airborne");
            Equal(false, firstBinding.IsLive, "a new same-component lifetime cannot revive its retired binding");
            Equal(true, secondBinding.IsLive, "refresh of the uninterrupted component retains its binding");
        });
    }

    private static void AuthoredAirJumpDurationPreservesNativeHooks()
    {
        using var scope = new NativeAirJumpScope();
        WithPlayer((player, owner) => {
            player.active = true;
            var source = AirJumpSource("airjump-duration");
            foreach (int height in new[] { 1, 3, 15, 20, 23, 25, 30 })
                for (int ticks = 1; ticks <= 120; ticks++) {
                    Player.jumpHeight = height;
                    source.Accessory.PlayerEffect!.AirJump = source.Accessory.PlayerEffect.AirJump! with { HoldDurationTicks = ticks };
                    ResetNativeAirJumpTick(player, owner);
                    owner.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect.AirJump!, 11);
                    player.RefreshExtraJumps(); ExtraJumpLoader.ProcessJumps(player);
                    Equal(ticks, player.jump, "native jump-height product preserves every baseline authored duration");
                }

            const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            object hook = typeof(PlayerLoader).GetField("HookModifyExtraJumpDurationMultiplier", statics)!.GetValue(null)!;
            FieldInfo indices = hook.GetType().GetField("indices", instance)!;
            FieldInfo defaults = hook.GetType().GetField("defaultInstances", instance)!;
            object oldIndices = indices.GetValue(hook)!, oldDefaults = defaults.GetValue(hook)!;
            var roster = typeof(Player).GetField("modPlayers", instance)!;
            object oldRoster = roster.GetValue(player)!;
            try {
                var modifier = new AirJumpDurationModifier();
                typeof(ModPlayer).GetProperty("Index")!.SetValue(modifier, (ushort)1);
                typeof(ModType<Player>).GetProperty("Entity", instance)!.SetValue(modifier, player);
                roster.SetValue(player, new ModPlayer[] { owner, modifier });
                hook.GetType().GetMethod("Update")!.Invoke(hook, new object[] { new ModPlayer[] { owner, modifier } });
                Player.jumpHeight = 15;
                source.Accessory.PlayerEffect!.AirJump = source.Accessory.PlayerEffect.AirJump! with { HoldDurationTicks = 7 };
                ResetNativeAirJumpTick(player, owner);
                owner.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect.AirJump!, 11);
                player.RefreshExtraJumps(); ExtraJumpLoader.ProcessJumps(player);
                Equal(14, player.jump, "native ModPlayer duration modifier still executes after authored duration");
            }
            finally {
                indices.SetValue(hook, oldIndices); defaults.SetValue(hook, oldDefaults); roster.SetValue(player, oldRoster);
            }
        });
    }
}
