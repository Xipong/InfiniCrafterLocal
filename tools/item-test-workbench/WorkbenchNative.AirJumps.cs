using System;
using System.Collections;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Loader-free stand registration must precede Player construction: the native
    // constructor sizes its ExtraJump states from the registered content count.
    // No grants, refresh, velocity, duration or VFX are supplied by this adapter.
    private sealed class WAirJumpBootstrap : IDisposable
    {
        private readonly IList jumps = (IList)typeof(ExtraJumpLoader).GetField("ExtraJumps", PersistenceStatic)!.GetValue(null)!;
        private readonly FieldInfo ordered = typeof(ExtraJumpLoader).GetField("orderedJumps", PersistenceStatic)!;
        private readonly PropertyInfo singleton = typeof(ContentInstance<GeneratedAirJump>).GetProperty("Instance")!;
        private readonly object? previousOrder, previousSingleton;
        private readonly int previousCount;
        private readonly GeneratedAirJumpLifecycleSystem lifecycle = new();
        private bool loaded;

        public WAirJumpBootstrap()
        {
            previousCount = jumps.Count;
            previousOrder = ordered.GetValue(null);
            previousSingleton = singleton.GetValue(null);
            try {
                var jump = new GeneratedAirJump();
                int type = (int)typeof(ExtraJumpLoader).GetMethod("Add", PersistenceStatic)!.Invoke(null, new object[] { jump })!;
                typeof(ExtraJump).GetProperty("Type")!.SetValue(jump, type);
                singleton.SetValue(null, jump);
                typeof(ExtraJumpLoader).GetMethod("ResizeArrays", PersistenceStatic)!.Invoke(null, null);
                lifecycle.Load();
                loaded = true;
            } catch { Dispose(); throw; }
        }

        public void Dispose()
        {
            if (loaded) { lifecycle.Unload(); loaded = false; }
            while (jumps.Count > previousCount) jumps.RemoveAt(jumps.Count - 1);
            ordered.SetValue(null, previousOrder);
            singleton.SetValue(null, previousSingleton);
        }
    }

    private delegate void WJumpStartedOriginal(GeneratedAirJump jump, Player player, ref bool playSound);
    private delegate void WJumpStartedObserver(WJumpStartedOriginal orig, GeneratedAirJump jump, Player player, ref bool playSound);

    private sealed class WAirJumpObserver : IDisposable
    {
        private readonly Hook started, movement, vfx;
        private int starts;

        public WAirJumpObserver(Player owner, Action<JsonObject> record)
        {
            started = new Hook(typeof(GeneratedAirJump).GetMethod(nameof(GeneratedAirJump.OnStarted))!,
                (WJumpStartedObserver)((WJumpStartedOriginal orig, GeneratedAirJump jump, Player player, ref bool playSound) => {
                    float before = player.velocity.Y;
                    orig(jump, player, ref playSound);
                    if (!ReferenceEquals(player, owner)) return;
                    starts++;
                    record(new JsonObject { ["kind"] = "native_extra_jump_started", ["nativeType"] = jump.Type,
                        ["vyBefore"] = before, ["vyAfter"] = player.velocity.Y, ["jumpTicks"] = player.jump,
                        ["availableAfter"] = player.GetJumpState(jump).Available, ["playSound"] = playSound,
                        ["dedServ"] = Terraria.Main.dedServ, ["entrypoint"] = "GeneratedAirJump.OnStarted (original returned)" });
                }));
            movement = new Hook(typeof(Player).GetMethod("JumpMovement", TestInstance)!,
                (Action<Action<Player>, Player>)((orig, player) => {
                    float before = player.velocity.Y, sharedSpeed = Player.jumpSpeed;
                    int jumpBefore = player.jump, startsBefore = starts;
                    orig(player);
                    if (!ReferenceEquals(player, owner) || !(player.controlJump || jumpBefore > 0)) return;
                    record(new JsonObject { ["kind"] = "native_jump_movement", ["vyBefore"] = before,
                        ["vyAfter"] = player.velocity.Y, ["jumpBefore"] = jumpBefore, ["jumpAfter"] = player.jump,
                        ["extraJumpStarted"] = starts != startsBefore,
                        ["groundJumpStarted"] = starts == startsBefore && before == 0 && jumpBefore == 0 && player.jump > 0 && player.velocity.Y * player.gravDir < 0,
                        ["sharedJumpSpeedBefore"] = sharedSpeed, ["sharedJumpSpeedAfter"] = Player.jumpSpeed,
                        ["extraJumpActive"] = player.GetJumpState<GeneratedAirJump>().Active,
                        ["entrypoint"] = "Player.JumpMovement with production GeneratedAirJumpLifecycleSystem detour" });
                }));
            vfx = new Hook(typeof(InfiniItemVfxRuntime).GetMethod(nameof(InfiniItemVfxRuntime.EmitAndSyncJump))!,
                (Action<Action<Player, GeneratedItemData, Vector2, long>, Player, GeneratedItemData, Vector2, long>)((orig, player, source, point, generation) => {
                    orig(player, source, point, generation);
                    if (ReferenceEquals(player, owner)) record(new JsonObject { ["kind"] = "native_air_jump_vfx_dispatch",
                        ["itemId"] = source.Id, ["sourceGeneration"] = generation, ["x"] = point.X, ["y"] = point.Y,
                        ["dedServ"] = Terraria.Main.dedServ, ["event"] = "on_jump",
                        ["scope"] = "Original EmitAndSyncJump returned; renderer snapshots/draws establish actual presentation" });
                }));
        }

        public void Dispose() { vfx.Dispose(); movement.Dispose(); started.Dispose(); }
    }
}
