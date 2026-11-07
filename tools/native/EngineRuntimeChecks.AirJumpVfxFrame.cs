using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Collections;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using MonoMod.Cil;
using Mono.Cecil.Cil;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compatible: observe the actual event -> material consumer/relay,
    // not a newly introduced frame helper. No GPU or real PNG claim here.
    private static GeneratedItemData AirJumpFrameFixture(string id, string attachment = "world", string anchor = "hitPoint")
    {
        var source = AirJumpSource(id);
        source.VfxManifest = ParseMaterialElement(MaterialElementWire(attachment)).VfxManifest;
        var slot = source.VfxManifest.Slots[0];
        slot.EntityId = source.RuntimeProgram.ItemEntityId; slot.Event = RuntimeEventKind.OnJump;
        slot.Anchor = anchor; slot.RepeatEvery = 0;
        slot.Element!.Count = 1; slot.Element.OffsetForwardPx = -18; slot.Element.OffsetSidePx = 0;
        slot.Element.RotationRadians = MathHelper.PiOver2;
        slot.Element.SpeedMinPxPerTick = slot.Element.SpeedMaxPxPerTick = slot.Element.InheritVelocity = 0;
        source.Normalize();
        return source;
    }

    private static T AirJumpFrameField<T>(object owner, string field)
        => (T)owner.GetType().GetField(field, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.GetValue(owner)!;

    private static void AirJumpVfxGravityLocalAndLiveFrame()
    {
        using var jumps = new NativeAirJumpScope();
        using var peers = new ReviewPeers();
        var system = new InfiniDetachedVfxSystem();
        try {
            WithPlayer((player, effects) => {
                player.active = true; player.whoAmI = 0; Terraria.Main.player[0] = player;
                player.Center = new Vector2(400, 500);
                var source = AirJumpFrameFixture("jump_frame_local"); peers.Register(source);
                var host = ReviewItem(source); player.armor[3] = host.Item;
                effects.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect!.AirJump!, host.PresentationToken);
                peers.Mode(NetmodeID.SinglePlayer, 0);
                foreach (float gravity in new[] { 1f, -1f })
                foreach (int facing in new[] { 1, -1 })
                foreach (float heldAngle in new[] { 0f, 0.73f, -1.2f }) {
                    system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches();
                    player.gravDir = gravity; player.direction = facing; player.itemRotation = heldAngle;
                    player.itemLocation = new Vector2(-900, 1700); player.velocity = new Vector2(3, -8 * gravity);
                    Vector2 forward = new(0, -gravity);
                    InfiniItemVfxRuntime.EmitAndSyncJump(player, source, player.Center, host.PresentationToken);
                    Equal(1, OwnedMaterialQueue().Count, "actual local jump reaches material queue");
                    object emission = OwnedMaterialQueue()[0]!;
                    var frame = AirJumpFrameField<VfxSourceFrame>(emission, "InitialFrame");
                    AssertVfxNear(forward, frame.Forward, "jump forward is opposite gravity, not held aim/facing");
                    AssertVfxNear(player.Center, frame.Position, "jump origin remains player center");
                    AssertVfxNear(player.velocity, frame.Velocity, "actual velocity preserved separately from basis");
                    var particle = AirJumpFrameField<Array>(emission, "Particles").GetValue(0)!;
                    AssertVfxNear(player.Center - forward * 18, AirJumpFrameField<Vector2>(particle, "Position"), "negative forward offset is toward feet");
                    Equal(true, Math.Abs(AirJumpFrameField<float>(particle, "Rotation") - (forward.ToRotation() + MathHelper.PiOver2)) < 0.0001f,
                        "authored quarter-turn stays literal relative to jump frame");
                    var binding = VfxSourceBinding.CaptureAirJump(player, source.Id, host.PresentationToken);
                    foreach (string anchor in new[] { "self", "owner", "field", "velocity" }) {
                        Equal(true, binding.TryFrame(anchor, out var live), "live jump frame available");
                        AssertVfxNear(anchor == "velocity" ? Vector2.Normalize(player.velocity) : forward, live.Forward, "live binding uses same explicit basis");
                    }
                    player.velocity = Vector2.Zero;
                    Equal(true, binding.TryFrame("velocity", out var zero), "zero-velocity jump frame available");
                    AssertVfxNear(forward, zero.Forward, "zero velocity falls back to gravity basis, never item aim");
                    // Unrelated held-item consumers retain their prior orientation.
                    AssertVfxNear(heldAngle.ToRotationVector2() * facing, InfiniItemVfxSnapshot.Capture(player).Forward, "ordinary item frame unchanged");
                }
            });
        } finally { system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); }
    }

    private static void AirJumpVfxGravityCapturedRelay()
    {
        using var jumps = new NativeAirJumpScope();
        using var peers = new ReviewPeers();
        var system = new InfiniDetachedVfxSystem();
        var lights = new List<Vector2>();
        // Only final native light submission is intercepted; source admission,
        // packet codec/server handler and material emission all run normally.
        using var light = new MonoMod.RuntimeDetour.ILHook(typeof(Lighting).GetMethod(nameof(Lighting.AddLight), new[] { typeof(Vector2), typeof(Vector3) })!, il => {
            var cursor = new ILCursor(il); cursor.Emit(OpCodes.Ldarg_0);
            cursor.EmitDelegate<Action<Vector2>>(point => lights.Add(point)); cursor.Emit(OpCodes.Ret);
        });
        try {
            WithPlayer((player, effects) => {
                player.active = true; player.whoAmI = 0; Terraria.Main.player[0] = player;
                player.Center = new Vector2(400, 500); player.gravDir = 1; player.direction = -1;
                player.itemRotation = 0.73f; player.itemLocation = new Vector2(1700, -900); player.velocity = new Vector2(2, -8);
                var source = AirJumpFrameFixture("jump_frame_relay", anchor: "owner");
                var cue = LightManifest(source.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnJump).Slots[0];
                cue.Id = "jump_frame_light"; cue.Anchor = "owner";
                source.VfxManifest.Slots = source.VfxManifest.Slots.Append(cue).ToArray();
                source.Normalize(); peers.Register(source);
                var host = ReviewItem(source); player.armor[3] = host.Item;
                effects.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect!.AirJump!, host.PresentationToken);
                system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches();
                peers.Mode(NetmodeID.MultiplayerClient, 0);
                InfiniItemVfxRuntime.EmitAndSyncJump(player, source, player.Center, host.PresentationToken);
                Equal(1, peers.Sent.Count, "actual owner sends one snapshot");
                byte[] claim = peers.Sent.Single(); peers.Sent.Clear();
                system.OnWorldUnload(); lights.Clear();
                // Receiver state differs from the captured event: neither current
                // gravity, held pose nor position may rewrite a world emission.
                player.Center = new Vector2(800, 900); player.gravDir = -1;
                player.direction = 1; player.itemRotation = -1.3f; player.velocity = new Vector2(7, 6);
                peers.Mode(NetmodeID.Server, 255); peers.Receive(claim, 0);
                Equal(1, peers.Sent.Count, "server relays the authenticated captured event");
                byte[] relay = peers.Sent.Single(); peers.Sent.Clear();
                peers.Mode(NetmodeID.MultiplayerClient, 2); peers.Receive(relay);
                Equal(1, OwnedMaterialQueue().Count, "relay reaches actual material consumer once");
                var frame = AirJumpFrameField<VfxSourceFrame>(OwnedMaterialQueue()[0]!, "InitialFrame");
                AssertVfxNear(new Vector2(0, -1), frame.Forward, "relay retains event-time gravity basis");
                AssertVfxNear(new Vector2(400, 500), frame.Position, "world material retains event-time owner center");
                AssertVfxNear(new Vector2(2, -8), frame.Velocity, "relay retains event-time velocity");
                Equal(1, lights.Count, "nonmaterial light cue reaches consumer once");
                AssertVfxNear(new Vector2(400, 500), lights[0], "nonmaterial cue uses the same captured origin");
                peers.Receive(relay);
                Equal(1, OwnedMaterialQueue().Count, "replayed material is suppressed");
                Equal(1, lights.Count, "replayed light is suppressed");
            });
        } finally { system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); }
    }

    private static void AirJumpVfxGravitySourceAttachment()
    {
        using var jumps = new NativeAirJumpScope();
        using var peers = new ReviewPeers();
        var system = new InfiniDetachedVfxSystem();
        ulong tick = Terraria.Main.GameUpdateCount;
        try {
            WithPlayer((player, effects) => {
                player.active = true; player.whoAmI = 0; Terraria.Main.player[0] = player;
                player.Center = new Vector2(400, 500); player.gravDir = 1; player.direction = -1; player.itemRotation = 1;
                var source = AirJumpFrameFixture("jump_frame_attached", "source", "self"); peers.Register(source);
                var host = ReviewItem(source); player.armor[3] = host.Item;
                effects.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect!.AirJump!, host.PresentationToken);
                system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); peers.Mode(NetmodeID.SinglePlayer, 0);
                InfiniItemVfxRuntime.EmitAndSyncJump(player, source, player.Center, host.PresentationToken);
                Equal(1, OwnedMaterialQueue().Count, "source emission admitted");
                player.Center += new Vector2(10, 20); player.gravDir = -1; player.itemRotation = -2; player.direction = 1;
                MaterialClock(tick + 1); system.PostUpdateEverything();
                var emission = OwnedMaterialQueue()[0]!;
                var frame = AirJumpFrameField<VfxSourceFrame>(emission, "Frame");
                AssertVfxNear(Vector2.UnitY, frame.Forward, "source attachment follows live gravity, not held rotation");
                AssertVfxNear(player.Center, frame.Position, "source attachment follows live center");
                player.armor[3] = new Item();
                MaterialClock(tick + 2); system.PostUpdateEverything();
                Equal(0, OwnedMaterialQueue().Count, "exact source retirement still removes attached VFX");
            });
        } finally { system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); MaterialClock(tick); }
    }
}
