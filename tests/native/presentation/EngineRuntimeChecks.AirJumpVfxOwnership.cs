using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using MonoMod.Cil;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void AirJumpVfxNativeStartAndRelayHaveOneOwnerOccurrence()
    {
        using var jumps = new NativeAirJumpScope();
        using var peers = new ReviewPeers();
        int emitted = 0;
        // Observe the current nativeLight consumer, intercepting only its final
        // engine submission. Local dispatch and authenticated snapshot relay both
        // reach this boundary; neither may borrow the retired lightCue path.
        using var observer = new MonoMod.RuntimeDetour.ILHook(
            typeof(Lighting).GetMethod(nameof(Lighting.AddLight), new[] { typeof(Vector2), typeof(Vector3) })!,
            il => {
                var cursor = new ILCursor(il);
                cursor.EmitDelegate<Action>(() => emitted++);
                cursor.Emit(Mono.Cecil.Cil.OpCodes.Ret);
            });
        InfiniItemVfxRuntime.ClearUseEventCaches();
        WithPlayer((player, owner) => {
            player.active = true; player.whoAmI = 0; player.statLife = 100;
            player.direction = 1; player.gravDir = 1; player.Center = new Vector2(40, 50);
            Terraria.Main.player[0] = player;
            var source = AirJumpSource("airjump_vfx_owner");
            source.VfxManifest = LightManifest(source.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnJump);
            source.Normalize(); peers.Register(source);
            var host = ReviewItem(source); player.armor[3] = host.Item;
            owner.RegisterAirJumpGrant(source, source.Accessory.PlayerEffect!.AirJump!, host.PresentationToken);
            void Start()
            {
                player.RefreshExtraJumps();
                bool sound = true;
                jumps.Jump.OnStarted(player, ref sound);
                Equal(false, sound, "actual native jump callback preserves authored silence");
            }
            peers.Mode(NetmodeID.SinglePlayer, 0); emitted = 0; Start();
            int single = emitted, singlePackets = peers.Sent.Count;
            peers.Sent.Clear();
            peers.Mode(NetmodeID.MultiplayerClient, 0); emitted = 0; Start();
            int owned = emitted, ownerPackets = peers.Sent.Count;
            Equal(1, ownerPackets, "actual owner OnStarted sends one claim");
            byte[] claim = peers.Sent[0]; peers.Sent.Clear();
            peers.Mode(NetmodeID.Server, 255); emitted = 0; Start();
            int server = emitted, serverStartPackets = peers.Sent.Count;
            peers.Receive(claim, 0);
            Equal(1, peers.Sent.Count, "production server admission relays owner claim once");
            byte[] relay = peers.Sent[0]; peers.Sent.Clear();
            peers.Mode(NetmodeID.MultiplayerClient, 2); emitted = 0; Start();
            int remoteStart = emitted, remoteStartPackets = peers.Sent.Count;
            peers.Receive(relay);
            int remoteCombined = emitted;
            peers.Receive(relay);
            // This is the removed-guard counterproof: old code gives 2 here.
            Equal(1, remoteCombined, "actual remote OnStarted plus authenticated relay emits one occurrence");
            Equal(1, emitted, "replayed relay cannot emit a second occurrence");
            Equal(0, remoteStart, "remote native callback waits for the owner relay");
            Equal(0, remoteStartPackets, "remote native callback cannot send a claim");
            Equal(0, server, "server native callback does not dispatch local presentation");
            Equal(0, serverStartPackets, "server native callback does not send a claim");
            Equal(1, single, "single-player native callback emits once");
            Equal(0, singlePackets, "single-player callback needs no network claim");
            Equal(1, owned, "multiplayer owner native callback emits once");

            // A second real jump at the same coordinates and world tick is a
            // fresh occurrence, not periodic work or a duplicate of the first.
            peers.Mode(NetmodeID.MultiplayerClient, 0); emitted = 0; Start();
            Equal(1, emitted, "fresh owner jump emits in the same world tick");
            Equal(1, peers.Sent.Count, "fresh owner jump sends its own claim");
            byte[] freshClaim = peers.Sent[0]; peers.Sent.Clear();
            peers.Mode(NetmodeID.Server, 255); emitted = 0;
            peers.Receive(freshClaim, 0);
            Equal(0, emitted, "server still does not render fresh jump");
            Equal(1, peers.Sent.Count, "fresh occurrence is relayed after the previous replay");
            byte[] freshRelay = peers.Sent[0]; peers.Sent.Clear();
            peers.Mode(NetmodeID.MultiplayerClient, 2); emitted = 0;
            peers.Receive(freshRelay);
            Equal(1, emitted, "remote current renderer receives the fresh occurrence");
            peers.Receive(relay); peers.Receive(freshRelay);
            Equal(1, emitted, "old and fresh replays cannot duplicate the new occurrence");
        });
        InfiniItemVfxRuntime.ClearUseEventCaches();
    }
}
