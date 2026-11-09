using System;
using System.Linq;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Test-only diagnostic. Uses the existing socket capture, production SyncPlayer
    // writer and Mod.HandlePacket reader. No snapshot bytes or owner tables are edited.
    // Server packets remain FIFO: initial -> delayed pre-death -> death correction
    // -> fresh-life activation. Local death/respawn occurs while downlink is delayed.
    private static void UtilitySnapshotAfterRespawnBoundary()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var local = players[0];
            var server = players[1];
            var shortBuff = new GeneratedBuffSpec { DurationTicks = 6000, LifeRegen = 5 };
            var boundaryBuff = new GeneratedBuffSpec { DurationTicks = 72000, ManaRegen = 6 };
            var longBuff = new GeneratedBuffSpec { DurationTicks = 72001, MovementSpeed = .1f };
            var permanentBuff = new GeneratedBuffSpec { DurationTicks = 0, JumpBoost = 1f };

            byte[] Snapshot()
            {
                peers.Sent.Clear();
                server.Effects.SyncPlayer(0, -1, false);
                return peers.Sent.Single(packet => packet[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            }
            void NativeFrame()
            {
                local.Player.lifeRegen = local.Player.manaRegenBonus = 0;
                local.Player.moveSpeed = local.Player.jumpSpeedBoost = 0f;
                local.Effects.ResetEffects();
                local.Effects.PostUpdateEquips();
            }
            void ShortOnly(string phase)
            {
                var state = local.Effects.CaptureGeneratedUtilityBuffPresentation();
                Equal(2, state.Entries.Count, phase + ": only permitted short contributions remain");
                NativeFrame();
                Equal(5, local.Player.lifeRegen, phase + ": short buff executes");
                Equal(6, local.Player.manaRegenBonus, phase + ": exact twenty-minute buff executes");
                Equal(0f, local.Player.moveSpeed, phase + ": long contribution absent");
                Equal(0f, local.Player.jumpSpeedBoost, phase + ": permanent contribution absent");
            }

            AirJumpPeerMode(peers, server, 1);
            foreach (var buff in new[] { shortBuff, boundaryBuff, longBuff, permanentBuff })
                Equal(true, server.Effects.ApplyGeneratedUtilityBuff(buff), "server accepts canonical contribution");
            byte[] initial = Snapshot();
            AirJumpPeerMode(peers, local, 0);
            peers.Receive(initial, 256);
            Equal(4, local.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "initial authenticated state is live");

            // A distinct, later server snapshot is sent before the death notice.
            // Hold that packet, then hold the subsequent correction in FIFO order.
            MaterialClock(101);
            AirJumpPeerMode(peers, server, 1);
            byte[] delayed = Snapshot();
            MaterialClock(102);
            AirJumpPeerMode(peers, local, 0);
            local.Player.dead = true;
            local.Effects.UpdateDead();
            Equal(2, local.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "actual local death retires long and permanent contributions");
            MaterialClock(103);
            AirJumpPeerMode(peers, server, 1);
            server.Player.dead = true;
            peers.Sent.Clear();
            server.Effects.UpdateDead();
            byte[] correction = peers.Sent.Single(packet => packet[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            Equal(2, server.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "server death also retires contributions");

            AirJumpPeerMode(peers, local, 0);
            for (uint tick = 104; tick <= 1002; tick++) {
                MaterialClock(tick);
                local.Effects.UpdateDead();
            }
            MaterialClock(1003);
            // Native Player.Spawn calls OnRespawn before clearing dead.
            peers.Sent.Clear();
            local.Effects.OnRespawn();
            byte[]? resyncRequest = peers.Sent.SingleOrDefault(packet => packet[0] == 28);
            local.Player.dead = false;
            ShortOnly("before delayed delivery after local respawn");

            // Non-server sender control must remain rejected after respawn.
            peers.Receive(delayed, 0);
            ShortOnly("unauthenticated sender rejected");

            // The authentic delayed snapshot arrives first, with no reordering.
            MaterialClock(1004);
            peers.Receive(delayed, 256);
            NativeFrame();
            bool revivedLong = local.Player.moveSpeed == .1f;
            bool revivedPermanent = local.Player.jumpSpeedBoost == 1f;
            int revivedRows = local.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count;
            Console.WriteLine($"LIFE_BOUNDARY after_delayed_snapshot rows={revivedRows} long_native={local.Player.moveSpeed} permanent_native={local.Player.jumpSpeedBoost}");
            Equal(5, local.Player.lifeRegen, "late snapshot still preserves short buff control");
            Equal(6, local.Player.manaRegenBonus, "late snapshot still preserves twenty-minute control");

            // Ordered server correction subsequently arrives and repairs the owner.
            MaterialClock(1005);
            peers.Receive(correction, 256);
            ShortOnly("subsequent FIFO server death correction");
            Equal(2, server.Effects.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "client hydration did not revive authoritative server state");

            // Fresh same-effect activation after server respawn is valid and must not
            // be sacrificed by a blanket post-death or effect-identity rejection.
            MaterialClock(1006);
            AirJumpPeerMode(peers, server, 1);
            server.Effects.OnRespawn();
            server.Player.dead = false;
            Equal(true, server.Effects.ApplyGeneratedUtilityBuff(longBuff, activationTick: Terraria.Main.GameUpdateCount), "fresh long activation accepted");
            Equal(true, server.Effects.ApplyGeneratedUtilityBuff(permanentBuff, activationTick: Terraria.Main.GameUpdateCount), "fresh permanent activation accepted");
            byte[] fresh = Snapshot();
            // Baseline has no request; keep that path running to the original
            // stale-native-stats assertion. The fixed protocol must correlate it.
            byte[]? reply = null;
            if (resyncRequest is not null) {
                peers.Sent.Clear();
                peers.Receive(resyncRequest, 0);
                reply = peers.Sent.Single(packet => packet[0] == 29);
            }
            Equal(true, delayed.SequenceEqual(fresh), "pre-death and legitimate fresh-life state can have identical wire bytes");
            Console.WriteLine("LIFE_BOUNDARY old_and_fresh_snapshot_bytes=identical");
            AirJumpPeerMode(peers, local, 0);
            // Deliver exactly in server FIFO order: ordinary fresh activation
            // precedes the correlated reply and therefore remains fenced.
            peers.Receive(fresh, 256);
            if (reply is not null) {
                ShortOnly("fresh server activation before correlated acknowledgement");
                peers.Receive(reply, 256);
            }
            NativeFrame();
            Equal(.1f, local.Player.moveSpeed, "fresh-life long snapshot executes");
            Equal(1f, local.Player.jumpSpeedBoost, "fresh-life permanent snapshot executes");
            Console.WriteLine("LIFE_BOUNDARY controls=short_survival,exact_twenty_minutes,nonserver_rejection,ordered_correction,fresh_same_effect_snapshot all_passed");
            Equal(false, revivedLong || revivedPermanent, "authenticated pre-death snapshot must not reapply retired contributions after local respawn");
        });
    }
}
