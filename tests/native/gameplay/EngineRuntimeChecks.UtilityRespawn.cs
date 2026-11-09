using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void UtilityRespawnCorrelationRejectsOtherLives()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var owner = players[0]; var server = players[1];
            var shortBuff = new GeneratedBuffSpec { DurationTicks = 72000, LifeRegen = 5 };
            var longBuff = new GeneratedBuffSpec { DurationTicks = 72001, MovementSpeed = .1f };
            byte[] Snapshot() {
                peers.Sent.Clear(); server.Effects.SyncPlayer(0, -1, false);
                return peers.Sent.Single(packet => packet[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            }
            byte[] OwnerRespawn() {
                AirJumpPeerMode(peers, owner, 0); owner.Player.dead = true;
                owner.Effects.UpdateDead(); peers.Sent.Clear(); owner.Effects.OnRespawn();
                owner.Player.dead = false;
                return peers.Sent.Single(packet => packet[0] == InfiniNetPacketIds.RequestGeneratedUtilityRespawnSync);
            }
            byte[] Reply(byte[] request) {
                AirJumpPeerMode(peers, server, 1); peers.Sent.Clear(); peers.Receive(request, 0);
                return peers.Sent.Single(packet => packet[0] == InfiniNetPacketIds.GeneratedUtilityRespawnSync);
            }
            void NativeStats(float movement, string phase) {
                owner.Player.lifeRegen = 0; owner.Player.moveSpeed = 0;
                owner.Effects.ResetEffects(); owner.Effects.PostUpdateEquips();
                Equal(5, owner.Player.lifeRegen, phase + ": short survivor executes");
                Equal(movement, owner.Player.moveSpeed, phase + ": native movement");
            }

            AirJumpPeerMode(peers, server, 1);
            server.Effects.ApplyGeneratedUtilityBuff(shortBuff); server.Effects.ApplyGeneratedUtilityBuff(longBuff);
            byte[] old = Snapshot();
            AirJumpPeerMode(peers, owner, 0); peers.Receive(old, 256);
            byte[] firstRequest = OwnerRespawn();
            AirJumpPeerMode(peers, server, 1); peers.Sent.Clear();
            peers.Receive(firstRequest, 0);
            Equal(0, peers.Sent.Count, "live server that has not observed native respawn must not acknowledge");
            server.Player.dead = true; peers.Receive(firstRequest, 0);
            Equal(0, peers.Sent.Count, "dead server must not acknowledge");
            // No server UpdateDead tick: the native respawn hook must still retire.
            server.Effects.OnRespawn();
            Equal(1, server.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "native respawn retires old long row even without a dead update frame");
            peers.Receive(firstRequest, 0);
            Equal(0, peers.Sent.Count, "OnRespawn acknowledgement waits until native dead flag clears");
            server.Player.dead = false;
            server.Effects.ApplyGeneratedUtilityBuff(longBuff);
            byte[] firstReply = Reply(firstRequest);
            AirJumpPeerMode(peers, owner, 0); peers.Receive(firstReply, 0); NativeStats(0, "nonserver reply rejected");
            peers.Receive(old, 256); NativeStats(0, "nonserver reply did not open fence");

            // A new death/respawn invalidates an exact but delayed previous reply.
            MaterialClock(200);
            byte[] secondRequest = OwnerRespawn();
            Equal(false, firstRequest.SequenceEqual(secondRequest), "each respawn owns a fresh opaque nonce");
            peers.Receive(firstReply, 256); peers.Receive(old, 256); NativeStats(0, "previous-life ack cannot reopen current fence");
            // Fresh owner prediction is not erased by a pre-ack ordinary correction.
            owner.Effects.ApplyGeneratedUtilityBuff(longBuff);
            peers.Receive(old, 256); NativeStats(.1f, "fresh prediction survives waiting fence");
            var tick = typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityRespawnSync", BindingFlags.Instance | BindingFlags.NonPublic)!;
            peers.Sent.Clear(); for (int i = 0; i < 60; i++) tick.Invoke(owner.Effects, null);
            Equal(true, secondRequest.SequenceEqual(peers.Sent.Single()), "retry carries the same nonce rather than advancing life identity");

            AirJumpPeerMode(peers, server, 1); server.Player.dead = true;
            server.Effects.UpdateDead(); server.Effects.OnRespawn(); server.Player.dead = false;
            byte[] secondReply = Reply(secondRequest);
            AirJumpPeerMode(peers, owner, 0);
            bool malformedRejected = false;
            try { peers.Receive(secondReply[..^1], 256); } catch (Exception) { malformedRejected = true; }
            Equal(true, malformedRejected, "truncated matching reply rejected before replacing owner state");
            peers.Receive(old, 256); NativeStats(.1f, "malformed matching reply leaves pending barrier and fresh prediction intact");
            peers.Receive(secondReply, 256); NativeStats(0, "matching reply authoritatively corrects fresh prediction");
            AirJumpPeerMode(peers, server, 1); server.Effects.ApplyGeneratedUtilityBuff(longBuff);
            byte[] fresh = Snapshot();
            AirJumpPeerMode(peers, owner, 0); peers.Receive(fresh, 256); NativeStats(.1f, "post-ack normal fresh snapshot accepted");
            peers.Receive(secondReply, 256); NativeStats(.1f, "duplicate acknowledged reply ignored instead of rolling back fresh state");

            // Reset clears pending scope; neither an old reply nor an old request
            // can establish a barrier in a newly entered world/session.
            byte[] thirdRequest = OwnerRespawn();
            AirJumpPeerMode(peers, server, 1); server.Player.dead = true; server.Effects.OnRespawn(); server.Player.dead = false;
            byte[] thirdReply = Reply(thirdRequest);
            AirJumpPeerMode(peers, owner, 0); owner.Effects.OnEnterWorld();
            peers.Receive(thirdReply, 256);
            Equal(0, owner.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "old-world reply ignored after owner reset");
            AirJumpPeerMode(peers, server, 1); server.Effects.ClearGeneratedUtilityState(); peers.Sent.Clear(); peers.Receive(thirdRequest, 0);
            Equal(0, peers.Sent.Count, "world reset also clears server respawn observation");
        });
    }

    private static void UtilityRespawnRetiresExhaustionAndRejectsSpoof()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var owner = players[0]; var server = players[1];
            var data = AirJumpNetworkBuff("respawn_exhaustion", 600, held: false, exhaustion: 1200);
            peers.Register(data);
            var buff = data.RuntimeProgram.EffectGroups![0].GeneratedBuff!;
            AirJumpPeerMode(peers, server, 1);
            Equal(true, server.Effects.ApplyGeneratedUtilityBuff(buff, source: data), "server exhaustion source activated");
            peers.Sent.Clear(); server.Effects.SyncPlayer(0, -1, false);
            byte[] old = peers.Sent.Single();
            AirJumpPeerMode(peers, owner, 0); peers.Receive(old, 256);
            Equal(1, owner.Effects.CaptureGeneratedItemExhaustion().Count, "initial exhaustion mirrored");
            owner.Player.dead = true; owner.Effects.UpdateDead(); peers.Sent.Clear(); owner.Effects.OnRespawn(); owner.Player.dead = false;
            byte[] request = peers.Sent.Single(packet => packet[0] == InfiniNetPacketIds.RequestGeneratedUtilityRespawnSync);
            peers.Receive(old, 256);
            Equal(0, owner.Effects.CaptureGeneratedItemExhaustion().Count, "stale snapshot cannot restore retired exhaustion");
            Equal(true, owner.Effects.ApplyGeneratedUtilityBuff(buff, source: data), "fresh local exhaustion allowed while awaiting ack");
            peers.Receive(old, 256);
            Equal(1, owner.Effects.CaptureGeneratedItemExhaustion().Count, "fresh local exhaustion prediction preserved");
            AirJumpPeerMode(peers, server, 1); server.Player.dead = true; server.Effects.OnRespawn(); server.Player.dead = false;
            Equal(0, server.Effects.CaptureGeneratedItemExhaustion().Count, "respawn guard retires server exhaustion without UpdateDead");
            peers.Sent.Clear(); peers.Receive(request, 1);
            Equal(0, peers.Sent.Count, "request for another owner is rejected");
            peers.Receive(request, 0);
            byte[] reply = peers.Sent.Single(packet => packet[0] == InfiniNetPacketIds.GeneratedUtilityRespawnSync);
            AirJumpPeerMode(peers, owner, 0); peers.Receive(reply, 256);
            Equal(0, owner.Effects.CaptureGeneratedItemExhaustion().Count, "correlated server reply corrects local exhaustion prediction");
            AirJumpPeerMode(peers, server, 1); server.Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            peers.Sent.Clear(); server.Effects.SyncPlayer(0, -1, false); byte[] fresh = peers.Sent.Single();
            AirJumpPeerMode(peers, owner, 0); peers.Receive(fresh, 256);
            Equal(1, owner.Effects.CaptureGeneratedItemExhaustion().Count, "fresh authoritative exhaustion admitted after ack");
        });
    }
    private static void UtilityRespawnScopeAndPendingActivations()
    {
        foreach (bool reconnect in new[] { false, true })
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var owner = players[0]; var server = players[1];
            var connection = Netplay.Connection; var socket = connection.Socket; int world = Terraria.Main.worldID;
            try {
                AirJumpPeerMode(peers, owner, 0); owner.Player.dead = true; owner.Effects.UpdateDead(); peers.Sent.Clear();
                owner.Effects.OnRespawn(); owner.Player.dead = false;
                byte[] request = peers.Sent.Single();
                AirJumpPeerMode(peers, server, 1); server.Player.dead = true; server.Effects.OnRespawn(); server.Player.dead = false;
                server.Effects.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 0, JumpBoost = 1 });
                peers.Sent.Clear(); peers.Receive(request, 0); byte[] reply = peers.Sent.Single();
                AirJumpPeerMode(peers, owner, 0);
                if (reconnect) connection.Socket = (Terraria.Net.Sockets.ISocket)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Net.Sockets.TcpSocket));
                else Terraria.Main.worldID = unchecked(world + 1);
                peers.Receive(reply, 256);
                Equal(0, owner.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "old reply cannot cross " + (reconnect ? "socket" : "world") + " scope");
                peers.Sent.Clear();
                var tick = typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityRespawnSync", BindingFlags.Instance | BindingFlags.NonPublic)!;
                for (int i = 0; i < 120; i++) tick.Invoke(owner.Effects, null);
                Equal(0, peers.Sent.Count, "old request is not retried into a new authority scope");
            } finally { connection.Socket = socket; Terraria.Main.worldID = world; }
        });
        // The same native Spawn hook must close queued activations even if the
        // engine consumed death/spawn together and never visited UpdateDead.
        using (var state = new NativeActorState()) {
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            WithPlayer((player, owner) => {
                player.active = true; player.whoAmI = 0; Terraria.Main.player[0] = player;
                var data = GeneratedItemData.Placeholder();
                data.RuntimeProgram.EffectGroups = new[] { new RuntimeItemEffectGroupSpec { Id = "delayed", GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 72001, LifeRegen = 5 } } };
                var body = new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody };
                var action = new RuntimeEventActionSpec { ActionCode = RuntimeEventActionCode.ApplyGeneratedBuff, Event = RuntimeEventKind.OnHurt, EffectGroupId = "delayed", DelayTicks = 10 };
                MaterialClock(100);
                Equal(true, InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.TrySchedule(data, body, action, player,
                    new Terraria.DataStructures.EntitySource_Misc("InfiniRuntimeEquipmentReaction"), Microsoft.Xna.Framework.Vector2.Zero, Microsoft.Xna.Framework.Vector2.UnitX, null, 0, 0,
                    new InfiniCrafterLocal.Common.Runtime.RuntimeSpawnBudget(0)), "prior-life delayed utility queued");
                player.dead = true; owner.OnRespawn(); player.dead = false;
                // A fresh activation in the SAME clock tick is a different life.
                Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, ManaRegen = 2 }, activationTick: Terraria.Main.GameUpdateCount), "fresh same-tick activation remains valid");
                MaterialClock(111); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Update();
                Equal(1, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "respawn retires only prior pending utility, retaining fresh activation");
                Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Current.LifeRegen, "prior-life delayed long effect cannot re-enter authority");
            });
            InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
        }
        using (var f = new QuickUtilityPeers()) {
            byte[] prepare = f.Prepare(), ready = f.Ready(prepare);
            f.Mode(1); f.Owner.dead = true; f.OwnerBuff.OnRespawn(); f.Owner.dead = false;
            f.Peers.Sent.Clear(); f.Peers.Receive(ready, 256);
            Equal(0, f.Peers.Sent.Count, "owner respawn revokes pending Ready without prune frame");
        }
        using (var f = new QuickUtilityPeers()) {
            byte[] prepare = f.Prepare(), ready = f.Ready(prepare), commit = f.Commit(ready);
            f.Mode(2); f.Server.dead = true; f.ServerBuff.OnRespawn(); f.Server.dead = false;
            f.ReceiveServer(commit); Equal(0, f.Ticks(f.ServerBuff), "server respawn revokes pending quick ticket without prune frame");
            f.ReceiveServer(prepare); Equal(0, f.Peers.Sent.Count, "quick-use replay cursor survives respawn revocation");
        }
    }
}
