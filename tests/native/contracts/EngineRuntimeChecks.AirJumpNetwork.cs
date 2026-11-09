#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using MonoMod.Cil;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compilable observers: actual independent Player/ModPlayer peers,
    // production source writers/readers and packet handler. Only socket Send and
    // the final native light submission are intercepted, not source/event admission.
    private sealed record AirJumpNetworkPeer(Player Player, InfiniCraftPlayer Effects);
    private sealed class AirJumpEmissionProbe : IDisposable
    {
        internal readonly List<Vector2> Emitted = new();
        private readonly MonoMod.RuntimeDetour.ILHook hook;
        internal AirJumpEmissionProbe()
        {
            hook = new(typeof(Lighting).GetMethod(nameof(Lighting.AddLight), new[] { typeof(Vector2), typeof(Vector3) })!, il => {
                var cursor = new ILCursor(il);
                cursor.Emit(Mono.Cecil.Cil.OpCodes.Ldarg_0);
                cursor.EmitDelegate<Action<Vector2>>(point => Emitted.Add(point));
                cursor.Emit(Mono.Cecil.Cil.OpCodes.Ret);
            });
        }
        public void Dispose() => hook.Dispose();
    }

    private static void WithAirJumpNetwork(Action<ReviewPeers, NativeAirJumpScope, AirJumpEmissionProbe, AirJumpNetworkPeer[]> check)
    {
        using var jumps = new NativeAirJumpScope();
        using var peers = new ReviewPeers();
        using var emission = new AirJumpEmissionProbe();
        InfiniItemVfxRuntime.ClearUseEventCaches();
        try {
            WithPlayer((owner, ownerEffects) => WithPlayer((server, serverEffects) => WithPlayer((remote, remoteEffects) => {
                var players = new[] { new AirJumpNetworkPeer(owner, ownerEffects), new AirJumpNetworkPeer(server, serverEffects), new AirJumpNetworkPeer(remote, remoteEffects) };
                foreach (var peer in players) {
                    peer.Player.active = true; peer.Player.whoAmI = 0;
                    peer.Player.statLife = peer.Player.statLifeMax2 = 100;
                    peer.Player.statMana = 20; peer.Player.gravDir = peer.Player.direction = 1;
                    peer.Player.Center = new Vector2(100, 150); peer.Player.selectedItem = 0;
                }
                check(peers, jumps, emission, players);
            })));
        }
        finally { InfiniItemVfxRuntime.ClearUseEventCaches(); }
    }

    private static void AirJumpPeerMode(ReviewPeers peers, AirJumpNetworkPeer peer, int role)
    {
        peers.Mode(role == 1 ? NetmodeID.Server : NetmodeID.MultiplayerClient, role == 1 ? 255 : role == 2 ? 2 : 0);
        Terraria.Main.player[0] = peer.Player;
    }

    private static GeneratedItemData AirJumpNetworkBuff(string id, int duration, bool held = true, int exhaustion = 0)
    {
        var data = NamedItemEffectsFixture();
        data.Id = id; data.Name = id; data.SourceMode = "test_fixture";
        data.RuntimeProgram.EffectGroups![0] = new RuntimeItemEffectGroupSpec { Id = "primary_effects",
            GeneratedBuff = new GeneratedBuffSpec { DurationTicks = duration, ExhaustionTicks = exhaustion,
                PlayerEffect = new PlayerEffectSpec { AirJump = new PlayerAirJumpSpec {
                    Count = 2, LaunchSpeedPxPerTick = 8, HoldDurationTicks = 4 } } } };
        if (held) data.RuntimeProgram.HeldEffectGroupId = "primary_effects";
        data.VfxManifest = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnJump);
        GeneratedItemRegistryService.StampCurrentWorld(data);
        return GeneratedItemData.FromJson(data.ToNetworkJson())
            ?? throw new InvalidOperationException("network air-jump fixture refused");
    }

    private static GeneratedItem AirJumpCopyItem(GeneratedItem source)
    {
        var copy = MobilityConsumptionHost(source.Data);
        using var wire = new MemoryStream();
        source.NetSend(new BinaryWriter(wire)); wire.Position = 0;
        copy.NetReceive(new BinaryReader(wire));
        Equal(source.Data.Id, copy.Data.Id, "real compact item source synchronization hydrates the receiver");
        return copy;
    }

    private static byte[] AirJumpUtilitySnapshot(InfiniCraftPlayer effects)
    {
        byte[] state = ExhaustionSnapshot(effects);
        return new[] { InfiniNetPacketIds.SyncGeneratedUtilityBuff }.Concat(state).ToArray();
    }

    private static List<(long Generation, int Ticks, string Component)> AirJumpBuffRows(InfiniCraftPlayer effects)
    {
        var rows = new List<(long, int, string)>();
        foreach (object row in (IEnumerable)typeof(InfiniCraftPlayer).GetField("_activeGeneratedUtilityBuffs", MobilityConsumptionFlags)!.GetValue(effects)!) {
            object Read(string name) => row.GetType().GetField(name)!.GetValue(row)!;
            rows.Add(((long)Read("SourceGeneration"), (int)Read("Ticks"), (string)Read("SourceComponent")));
        }
        return rows;
    }

    private static byte[] AirJumpTakeEvent(ReviewPeers peers)
    {
        byte[][] packets = peers.Sent.Where(p => p[0] == InfiniNetPacketIds.SyncGeneratedItemVfxEvent).ToArray();
        Equal(1, packets.Length, "one production jump event packet");
        peers.Sent.Clear(); return packets[0];
    }

    private static byte[] AirJumpNativeClaim(ReviewPeers peers, NativeAirJumpScope jumps, AirJumpNetworkPeer owner)
    {
        AirJumpPeerMode(peers, owner, 0); peers.Sent.Clear();
        owner.Player.RefreshExtraJumps();
        bool sound = true; jumps.Jump.OnStarted(owner.Player, ref sound);
        Equal(false, sound, "native authored jump keeps silence policy");
        return AirJumpTakeEvent(peers);
    }

    private static void AirJumpHeldOneTickNetworkLifetime() => AirJumpHeldNetworkLifetime(1);
    private static void AirJumpHeldTwoTickNetworkLifetime() => AirJumpHeldNetworkLifetime(2);
    private static void AirJumpHeldTenTickNetworkLifetime() => AirJumpHeldNetworkLifetime(10);
    private static void AirJumpHeldNetworkLifetime(int duration)
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_held_" + duration, duration); peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            var ownerItem = MobilityConsumptionHost(data);
            var items = new[] { ownerItem, AirJumpCopyItem(ownerItem), AirJumpCopyItem(ownerItem) };
            for (int role = 0; role < players.Length; role++) {
                AirJumpPeerMode(peers, players[role], role);
                players[role].Player.inventory[0] = items[role].Item;
                ResetNativeAirJumpTick(players[role].Player, players[role].Effects);
            }
            // No manual RegisterAirJumpGrant: real HoldItem is the only producer.
            AirJumpPeerMode(peers, players[0], 0); items[0].HoldItem(players[0].Player);
            AirJumpPeerMode(peers, players[1], 1); peers.Sent.Clear(); items[1].HoldItem(players[1].Player);
            byte[] snapshot = peers.Sent.Single(p => p[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            int snapshots = 1; peers.Sent.Clear();
            long generation = AirJumpBuffRows(players[1].Effects).Single().Generation;
            AirJumpPeerMode(peers, players[2], 2); items[2].HoldItem(players[2].Player);
            Equal(0, AirJumpBuffRows(players[2].Effects).Count, "remote held definition alone cannot activate a utility buff");
            peers.Receive(snapshot);
            var binding = VfxSourceBinding.CaptureAirJump(players[2].Player, data.Id, generation);
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(snapshot);
            bool spent = false;
            for (uint tick = 101; tick <= 131; tick++) {
                MaterialClock(tick);
                for (int role = 0; role < players.Length; role++) {
                    var peer = players[role]; AirJumpPeerMode(peers, peer, role);
                    ResetNativeAirJumpTick(peer.Player, peer.Effects); peer.Effects.PostUpdateEquips();
                    items[role].HoldItem(peer.Player);
                    if (role == 1) {
                        foreach (byte[] update in peers.Sent.Where(p => p[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff).ToArray()) {
                            snapshots++; AirJumpPeerMode(peers, players[2], 2); peers.Receive(update);
                        }
                        peers.Sent.Clear();
                    }
                }
                if (tick == 129) {
                    for (int role = 0; role < players.Length; role++) {
                        AirJumpPeerMode(peers, players[role], role);
                        var rows = AirJumpBuffRows(players[role].Effects);
                        Equal(1, rows.Count, "continuous held row survives snapshot gap on role=" + role + " duration=" + duration);
                        var row = rows.Single();
                        Equal(generation, row.Generation, "continuous duration=" + duration + " keeps its exact generation on role=" + role);
                        Equal(duration, row.Ticks, "admitted held lifetime continues before the next 30-tick snapshot");
                    }
                    Equal(true, binding.IsLive, "observer attachment survives short continuous held duration");
                    byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
                    AirJumpPeerMode(peers, players[1], 1); peers.Receive(claim, 0);
                    byte[] relay = AirJumpTakeEvent(peers);
                    AirJumpPeerMode(peers, players[2], 2); int before = emission.Emitted.Count;
                    peers.Receive(relay); peers.Receive(relay);
                    Equal(before + 1, emission.Emitted.Count, "held jump reaches observer exactly once between snapshots");
                    AirJumpPeerMode(peers, players[0], 0);
                    bool sound = true; jumps.Jump.OnStarted(players[0].Player, ref sound); peers.Sent.Clear();
                    Equal(false, jumps.Jump.CanStart(players[0].Player), "all owner charges spent"); spent = true;
                }
            }
            Equal(2, snapshots, "continuity needs no per-tick utility traffic");
            AirJumpPeerMode(peers, players[0], 0);
            Equal(true, spent, "spent-charge control executed");
            Equal(false, jumps.Jump.CanStart(players[0].Player), "continued held lifetime never refills airborne charges");
            Equal(100, players[0].Player.statLife, "holding does not dispatch unselected native healing");
            Equal(20, players[0].Player.statMana, "holding does not dispatch alternate mana healing");
            Equal(0f, players[0].Player.jumpSpeedBoost, "unselected alternate numeric jump buff stays inactive");
        });
    }

    private static void AirJumpBuffSnapshotAdmitsBeforeEquipTick()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_snapshot_first", 10, held: false); peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            var ownerItem = MobilityConsumptionHost(data); players[0].Player.inventory[0] = ownerItem.Item;
            ownerItem.UseItem(players[0].Player);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            // The server's own accepted activation is live, but its equip hook
            // has not run. Client snapshots are never gameplay activation.
            AirJumpPeerMode(peers, players[1], 1);
            var serverItem = AirJumpCopyItem(ownerItem); players[1].Player.inventory[0] = serverItem.Item;
            Equal(true, players[1].Effects.ApplyGeneratedUtilityBuff(
                serverItem.Data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: serverItem.Data), "server accepts canonical buff activation");
            peers.Sent.Clear();
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(snapshot);
            byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
            AirJumpPeerMode(peers, players[1], 1);
            byte[] beforeServer = ExhaustionSnapshot(players[1].Effects);
            peers.Receive(claim, 0); byte[] relay = AirJumpTakeEvent(peers);
            Equal(true, beforeServer.SequenceEqual(ExhaustionSnapshot(players[1].Effects)), "server VFX claim cannot alter buff state");
            Equal(false, players[1].Player.GetJumpState(jumps.Jump).Enabled, "server cosmetic read does not enable gameplay jump");
            AirJumpPeerMode(peers, players[2], 2); peers.Receive(snapshot);
            byte[] beforeRemote = ExhaustionSnapshot(players[2].Effects);
            int before = emission.Emitted.Count;
            peers.Receive(relay); peers.Receive(relay);
            Equal(before + 1, emission.Emitted.Count, "snapshot then event in one receive batch emits without PostUpdateEquips");
            Equal(true, beforeRemote.SequenceEqual(ExhaustionSnapshot(players[2].Effects)), "remote presentation leaves utility state byte-identical");
            Equal(false, players[2].Player.GetJumpState(jumps.Jump).Enabled, "receiving VFX cannot enable ExtraJump");
            Equal(false, jumps.Jump.CanStart(players[2].Player), "receiving VFX cannot manufacture charges");
        });
    }

    private static void AirJumpEquipmentSyncAdmitsBeforeEquipTick()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpSource("jump_equipment_first"); data.SourceMode = "test_fixture";
            data.VfxManifest = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnJump);
            data.Normalize(); peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            var ownerItem = MobilityConsumptionHost(data); players[0].Player.armor[3] = ownerItem.Item;
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); ownerItem.UpdateAccessory(players[0].Player, false);
            players[0].Effects.PostUpdateEquips();
            byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
            AirJumpPeerMode(peers, players[1], 1);
            var serverItem = AirJumpCopyItem(ownerItem); players[1].Player.armor[3] = serverItem.Item;
            peers.Receive(claim, 0); byte[] relay = AirJumpTakeEvent(peers);
            Equal(false, players[1].Player.GetJumpState(jumps.Jump).Enabled, "server item sync is not equipment gameplay dispatch");
            AirJumpPeerMode(peers, players[2], 2);
            var remoteItem = AirJumpCopyItem(serverItem); players[2].Player.armor[3] = remoteItem.Item;
            int before = emission.Emitted.Count; peers.Receive(relay);
            Equal(before + 1, emission.Emitted.Count, "real item NetReceive then relay works before UpdateAccessory");
            Equal(false, players[2].Player.GetJumpState(jumps.Jump).Enabled, "observer native source read cannot grant jump availability");
            long generation = ownerItem.PresentationToken;
            var binding = VfxSourceBinding.CaptureAirJump(players[2].Player, data.Id, generation);
            Equal(true, binding.IsLive, "actual functional source is live immediately");
            players[2].Player.armor[3] = new Item(); players[2].Player.armor[13] = remoteItem.Item;
            Equal(false, players[2].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _, generation), "vanity cannot witness gameplay jump");
            Equal(false, binding.IsLive, "unequip retires an attached event before another equip pass");
            players[2].Player.armor[13] = new Item(); players[2].Player.armor[8] = remoteItem.Item;
            Equal(false, players[2].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _, generation), "locked native accessory slot is not functional");
            players[2].Player.armor[8] = new Item(); players[2].Player.inventory[0] = remoteItem.Item;
            Equal(false, players[2].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _, generation), "holding accessory is not equipping it");
            players[2].Player.inventory[0] = new Item(); players[2].Player.armor[3] = remoteItem.Item;
            Equal(false, binding.IsLive, "observed retired attachment cannot revive on re-equip");
            var liveAgain = VfxSourceBinding.CaptureAirJump(players[2].Player, data.Id, generation);
            Equal(true, liveAgain.IsLive, "new event may attach to actual current source");
            players[2].Player.armor[3] = MobilityConsumptionHost(data).Item;
            Equal(false, players[2].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _, generation), "same definition without synchronized item token cannot borrow old generation");
            Equal(false, liveAgain.IsLive, "replacement retires old physical source");
        });
    }

    private static void AirJumpNetworkRetiresExpiredAndExhaustedSources()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_retirement", 2); peers.Register(data);
            AirJumpPeerMode(peers, players[1], 1);
            var held = MobilityConsumptionHost(data); players[1].Player.inventory[0] = held.Item; held.HoldItem(players[1].Player);
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            long generation = AirJumpBuffRows(players[1].Effects).Single().Generation;
            AirJumpPeerMode(peers, players[2], 2);
            var remoteItem = AirJumpCopyItem(held); players[2].Player.inventory[0] = remoteItem.Item; peers.Receive(snapshot);
            var binding = VfxSourceBinding.CaptureAirJump(players[2].Player, data.Id, generation);
            Equal(true, binding.IsLive, "accepted live buff can bind before equipment tick");
            // Do not query IsLive at the expiry edge. A subsequent identical
            // authority snapshot still must not resurrect the old attachment.
            players[2].Player.selectedItem = 1;
            for (int tick = 0; tick < 2; tick++) {
                ResetNativeAirJumpTick(players[2].Player, players[2].Effects); players[2].Effects.PostUpdateEquips();
            }
            Equal(0, AirJumpBuffRows(players[2].Effects).Count, "switching away restores exact ordinary countdown");
            ResetNativeAirJumpTick(players[2].Player, players[2].Effects);
            peers.Receive(snapshot);
            Equal(false, binding.IsLive, "reappearing same wire generation after actual expiry cannot revive old VFX");
            var newBinding = VfxSourceBinding.CaptureAirJump(players[2].Player, data.Id, generation);
            peers.Receive(snapshot);
            Equal(true, newBinding.IsLive, "correction of an uninterrupted live row preserves attachment identity");
            players[2].Player.dead = true; players[2].Effects.UpdateDead(); players[2].Player.dead = false;
            Equal(false, newBinding.IsLive, "death fences a newly received short-buff attachment before its next equipment tick");
            var afterDeath = VfxSourceBinding.CaptureAirJump(players[2].Player, data.Id, generation);
            Equal(true, afterDeath.IsLive, "retained post-death short buff admits a new binding, not the old life");
            new GeneratedAirJumpLifecycleSystem().OnWorldUnload();
            Equal(false, afterDeath.IsLive, "world retirement fences a source even with no gameplay grants");

            var exhausted = AirJumpNetworkBuff("jump_exhausted", 2, exhaustion: 60); peers.Register(exhausted);
            AirJumpPeerMode(peers, players[1], 1); players[1].Effects.ClearGeneratedUtilityState();
            var tiredItem = MobilityConsumptionHost(exhausted); players[1].Player.inventory[0] = tiredItem.Item;
            tiredItem.HoldItem(players[1].Player);
            Equal(true, players[1].Effects.HasGeneratedItemExhaustion(exhausted), "held exhaustion actually starts");
            for (uint tick = 101; tick <= 102; tick++) {
                MaterialClock(tick); ResetNativeAirJumpTick(players[1].Player, players[1].Effects);
                players[1].Effects.PostUpdateEquips(); tiredItem.HoldItem(players[1].Player);
            }
            Equal(0, AirJumpBuffRows(players[1].Effects).Count, "held source cannot pin an exhausted buff");
            ResetNativeAirJumpTick(players[1].Player, players[1].Effects);
            Equal(false, players[1].Effects.TryGetLiveAirJumpSource(exhausted.Id, out _, out _), "exhausted expired source cannot admit presentation");

            var ordinary = new GeneratedBuffSpec { DurationTicks = 2, JumpBoost = 1 };
            players[1].Effects.ApplyGeneratedUtilityBuff(ordinary);
            for (int tick = 0; tick < 2; tick++) players[1].Effects.PostUpdateEquips();
            Equal(0, ExhaustionBuffTicks(players[1].Effects), "ordinary nonheld numeric buff expiry is unchanged");
        });
    }

    private static void AirJumpHeldContinuationRequiresExactSource()
    {
        foreach (string mismatch in new[] { "component", "definition", "item", "same-item-exhaustion" })
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_exact_continuity", 2);
            data.RuntimeProgram.EffectGroups![1] = new RuntimeItemEffectGroupSpec { Id = "alternate_effects",
                GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 2,
                    PlayerEffect = data.RuntimeProgram.EffectGroups[0].GeneratedBuff!.PlayerEffect } };
            if (mismatch == "same-item-exhaustion")
                data.RuntimeProgram.EffectGroups[1].GeneratedBuff!.ExhaustionTicks = 60;
            data = GeneratedItemData.FromJson(data.ToNetworkJson())!; peers.Register(data);
            AirJumpPeerMode(peers, players[1], 1);
            var sourceItem = MobilityConsumptionHost(data); players[1].Player.inventory[0] = sourceItem.Item;
            Equal(true, players[1].Effects.ApplyGeneratedUtilityBuff(
                data.RuntimeProgram.EffectGroups![mismatch == "component" ? 1 : 0].GeneratedBuff, source: data), "server starts selected component");
            if (mismatch == "same-item-exhaustion")
                Equal(true, players[1].Effects.ApplyGeneratedUtilityBuff(
                    data.RuntimeProgram.EffectGroups[1].GeneratedBuff, source: data), "same-item companion starts exhaustion");
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            var heldData = GeneratedItemData.FromJson(data.ToNetworkJson())!;
            if (mismatch == "item") heldData.Id = "another_held_source";
            if (mismatch == "definition") {
                var effect = heldData.RuntimeProgram.EffectGroups![0].GeneratedBuff!.PlayerEffect!;
                effect.AirJump = effect.AirJump! with { Count = 3 };
            }
            // Keep the changed held definition canonical on the receiving peer;
            // normal HoldItem hydration must not silently restore the old one.
            if (mismatch is "definition" or "item") peers.Register(heldData);
            AirJumpPeerMode(peers, players[2], 2);
            players[2].Player.inventory[0] = MobilityConsumptionHost(heldData).Item;
            peers.Receive(snapshot);
            for (int tick = 0; tick < 2; tick++) {
                ResetNativeAirJumpTick(players[2].Player, players[2].Effects);
                players[2].Effects.PostUpdateEquips();
                ((GeneratedItem)players[2].Player.HeldItem.ModItem!).HoldItem(players[2].Player);
            }
            Equal(0, AirJumpBuffRows(players[2].Effects).Count, "held continuation refuses mismatched " + mismatch);
            ResetNativeAirJumpTick(players[2].Player, players[2].Effects);
            Equal(false, players[2].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _), "no stale-grant admission after " + mismatch + " expiry");
        });
    }

    private static byte[] AirJumpRewriteClaim(byte[] bytes, long? generation = null, ulong? occurrence = null,
        string? definition = null, string? entity = null)
    {
        using var input = new BinaryReader(new MemoryStream(bytes));
        using var output = new MemoryStream(); using var writer = new BinaryWriter(output);
        writer.Write(input.ReadByte()); writer.Write(input.ReadByte()); writer.Write(input.ReadByte());
        long oldGeneration = input.ReadInt64(); ulong oldOccurrence = input.ReadUInt64();
        writer.Write(generation ?? oldGeneration); writer.Write(occurrence ?? oldOccurrence);
        writer.Write(input.ReadString());
        string oldDefinition = input.ReadString(), oldEntity = input.ReadString();
        writer.Write(definition ?? oldDefinition); writer.Write(entity ?? oldEntity);
        writer.Write(input.ReadBytes((int)(input.BaseStream.Length - input.BaseStream.Position)));
        return output.ToArray();
    }

    private static void AirJumpNetworkRejectsUnownedClaimsAndPreservesBudgets()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_authority", 10, held: false); peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            var item = MobilityConsumptionHost(data); players[0].Player.inventory[0] = item.Item; item.UseItem(players[0].Player);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            AirJumpPeerMode(peers, players[1], 1);
            var serverItem = AirJumpCopyItem(item); players[1].Player.inventory[0] = serverItem.Item;
            players[1].Effects.ApplyGeneratedUtilityBuff(serverItem.Data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: serverItem.Data);
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(snapshot);
            byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
            AirJumpPeerMode(peers, players[1], 1); players[1].Effects.ClearGeneratedUtilityState();
            peers.Receive(snapshot, 0); peers.Sent.Clear();
            Equal(0, AirJumpBuffRows(players[1].Effects).Count, "client snapshot cannot create a server buff");
            peers.Receive(claim, 0);
            Equal(0, peers.Sent.Count, "unowned jump event cannot create its own source");
            AirJumpPeerMode(peers, players[2], 2); peers.Receive(snapshot, 0);
            Equal(0, AirJumpBuffRows(players[2].Effects).Count, "observer accepts utility state only from server");
            AirJumpPeerMode(peers, players[1], 1);
            Equal(true, players[1].Effects.ApplyGeneratedUtilityBuff(
                serverItem.Data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: serverItem.Data), "server starts its own canonical buff");
            snapshot = AirJumpUtilitySnapshot(players[1].Effects); peers.Sent.Clear();
            peers.Receive(claim, 0);
            Equal(0, peers.Sent.Count, "old exact generation cannot bind to a replacement authority lifetime");
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(snapshot);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            claim = AirJumpNativeClaim(peers, jumps, players[0]);
            AirJumpPeerMode(peers, players[1], 1);
            byte[] stateBefore = ExhaustionSnapshot(players[1].Effects);
            peers.Receive(claim, 1);
            peers.Receive(AirJumpRewriteClaim(claim, generation: -123), 0);
            peers.Receive(AirJumpRewriteClaim(claim, definition: new string('b', 64)), 0);
            peers.Receive(AirJumpRewriteClaim(claim, entity: "unrelated"), 0);
            peers.Receive(claim[..^1], 0);
            string world = data.RecipeMeta.WorldId; data.RecipeMeta.WorldId = "foreign-world";
            peers.Receive(claim, 0); data.RecipeMeta.WorldId = world;
            players[1].Player.dead = true; peers.Receive(claim, 0); players[1].Player.dead = false;
            Equal(0, peers.Sent.Count, "sender/generation/definition/entity/length/world/death fences reject hostile claims");
            Equal(true, stateBefore.SequenceEqual(ExhaustionSnapshot(players[1].Effects)), "refused VFX cannot mutate authoritative gameplay state");
            peers.Receive(claim, 0); byte[] relay = AirJumpTakeEvent(peers);
            peers.Receive(claim, 0); Equal(0, peers.Sent.Count, "server rejects a replay");
            AirJumpPeerMode(peers, players[2], 2); peers.Receive(snapshot);
            int before = emission.Emitted.Count; peers.Receive(relay, 0);
            Equal(before, emission.Emitted.Count, "direct peer cannot impersonate the server relay");
            peers.Receive(relay); peers.Receive(relay);
            Equal(before + 1, emission.Emitted.Count, "valid server relay emits once after hostile traffic");
            Equal(false, jumps.Jump.CanStart(players[2].Player), "network admission cannot allocate gameplay charges");
            // Existing bound, not a new test-only production constant. Synthetic
            // sequences isolate rate admission from the native charge ledger.
            int cap = (int)typeof(InfiniItemVfxRuntime).GetField("MaxRemoteEventsPerPlayerPerTick", BindingFlags.Static | BindingFlags.NonPublic)!.GetRawConstantValue()!;
            MaterialClock(200); AirJumpPeerMode(peers, players[1], 1); peers.Sent.Clear();
            for (int index = 0; index <= cap; index++) peers.Receive(AirJumpRewriteClaim(claim, occurrence: (ulong)(1000 + index)), 0);
            Equal(cap, peers.Sent.Count, "pre-equip source admission keeps the existing bounded server budget");
            byte[][] relays = peers.Sent.ToArray(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[2], 2); before = emission.Emitted.Count;
            foreach (byte[] packet in relays) peers.Receive(packet);
            peers.Receive(AirJumpRewriteClaim(relays[^1], occurrence: 10000));
            Equal(before + cap, emission.Emitted.Count, "observer budget remains bounded independently");
            Equal(true, stateBefore.SequenceEqual(ExhaustionSnapshot(players[1].Effects)), "even budget pressure cannot refresh buff duration or charges");
        });
    }

    private static void AirJumpLastBuffTickKeepsMovementPresentation()
    {
        foreach (int duration in new[] { 1, 2, 10 })
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_final_tick_" + duration, duration, held: false); peers.Register(data);
            for (int role = 0; role < 2; role++) {
                AirJumpPeerMode(peers, players[role], role);
                Equal(true, players[role].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff,
                    source: data), "owner predicts and authority activates final-tick source");
            }
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            long generation = AirJumpBuffRows(players[1].Effects).Single().Generation;
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(snapshot);
            AirJumpPeerMode(peers, players[2], 2); peers.Receive(snapshot);
            var binding = VfxSourceBinding.CaptureAirJump(players[2].Player, data.Id, generation);
            for (uint tick = 101; tick < 101 + duration; tick++) {
                MaterialClock(tick);
                for (int role = 0; role < 3; role++) {
                    AirJumpPeerMode(peers, players[role], role);
                    ResetNativeAirJumpTick(players[role].Player, players[role].Effects);
                    players[role].Effects.PostUpdateEquips();
                }
            }
            Equal(0, AirJumpBuffRows(players[0].Effects).Count, "final stat tick removes the active buff row");
            int before = emission.Emitted.Count;
            byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
            Equal(before + 1, emission.Emitted.Count, "final-tick native jump emits locally exactly once");
            AirJumpPeerMode(peers, players[2], 2);
            Equal(true, binding.IsLive, "final-tick attachment stays live through native movement");
            AirJumpPeerMode(peers, players[1], 1); peers.Receive(claim, 0);
            byte[] relay = AirJumpTakeEvent(peers);
            AirJumpPeerMode(peers, players[2], 2); before = emission.Emitted.Count;
            peers.Receive(relay); peers.Receive(relay);
            Equal(before + 1, emission.Emitted.Count, "final-tick relay emits once on the observer");
            MaterialClock((uint)(102 + duration));
            for (int role = 0; role < 3; role++) {
                AirJumpPeerMode(peers, players[role], role);
                ResetNativeAirJumpTick(players[role].Player, players[role].Effects);
                Equal(false, players[role].Effects.CanStartGeneratedAirJump(), "next update cannot reuse final-tick grants");
                Equal(false, players[role].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _, generation),
                    "next update retires exact final-tick presentation source");
            }
            Equal(false, binding.IsLive, "final-tick attachment retires without a new buff");
            AirJumpPeerMode(peers, players[1], 1); peers.Sent.Clear();
            peers.Receive(AirJumpRewriteClaim(claim, occurrence: 1234), 0);
            Equal(0, peers.Sent.Count, "new occurrence cannot revive expired final-tick source");
        });
    }

    private static void AirJumpPredictionReconcilesIndependentComponents()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_prediction_components", 10, held: false);
            data.RuntimeProgram.EffectGroups![1] = new RuntimeItemEffectGroupSpec { Id = "alternate_effects",
                GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 10,
                    PlayerEffect = new PlayerEffectSpec { AirJump = new PlayerAirJumpSpec {
                        Count = 1, LaunchSpeedPxPerTick = 12, HoldDurationTicks = 3 } } } };
            data = GeneratedItemData.FromJson(data.ToNetworkJson())!; peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            // A refused/expired owner-only prediction advances only the local counter.
            var abandoned = AirJumpNetworkBuff("jump_abandoned_prediction", 10, held: false); peers.Register(abandoned);
            players[0].Effects.ApplyGeneratedUtilityBuff(abandoned.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: abandoned);
            players[0].Effects.ClearGeneratedUtilityState();
            foreach (var group in data.RuntimeProgram.EffectGroups!)
                players[0].Effects.ApplyGeneratedUtilityBuff(group.GeneratedBuff, source: data);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            var predicted = AirJumpBuffRows(players[0].Effects);
            var firstBinding = VfxSourceBinding.CaptureAirJump(players[0].Player, data.Id, predicted[0].Generation);
            var secondBinding = VfxSourceBinding.CaptureAirJump(players[0].Player, data.Id, predicted[1].Generation);
            peers.Sent.Clear(); players[0].Player.RefreshExtraJumps();
            bool sound = true;
            for (int index = 0; index < 3; index++) jumps.Jump.OnStarted(players[0].Player, ref sound);
            Equal(-12f, players[0].Player.velocity.Y, "independent companion charge uses its authored movement");
            Equal(false, jumps.Jump.CanStart(players[0].Player), "both component ledgers are spent before confirmation");
            Equal(0, peers.Sent.Count, "unconfirmed source tokens are not sent as server identities");
            // A confirmed equipment event can overtake pending buff events on
            // the shared transport. Allocate their wire order when actually sent.
            var equipment = AirJumpSource("jump_prediction_equipment"); equipment.SourceMode = "test_fixture";
            equipment.VfxManifest = LightManifest(equipment.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnJump);
            equipment.Normalize(); peers.Register(equipment);
            var equipped = MobilityConsumptionHost(equipment); players[0].Player.armor[3] = equipped.Item;
            InfiniItemVfxRuntime.EmitAndSyncJump(players[0].Player, equipment, players[0].Player.Center, equipped.PresentationToken);
            byte[] equipmentClaim = AirJumpTakeEvent(peers);
            AirJumpPeerMode(peers, players[1], 1);
            players[1].Player.armor[3] = AirJumpCopyItem(equipped).Item;
            peers.Receive(equipmentClaim, 0); AirJumpTakeEvent(peers);
            int localEmissions = emission.Emitted.Count;
            Vector2 originalPoint = players[0].Player.Center;
            players[0].Player.Center += new Vector2(200, 300);
            // Deliberately reverse authority allocation order as well as count.
            foreach (var group in data.RuntimeProgram.EffectGroups.Reverse())
                players[1].Effects.ApplyGeneratedUtilityBuff(group.GeneratedBuff, source: data);
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            var authoritative = AirJumpBuffRows(players[1].Effects);
            Equal(false, predicted.Select(p => p.Generation).SequenceEqual(authoritative.Select(p => p.Generation)),
                "fixture genuinely diverges peer generation counters");
            AirJumpPeerMode(peers, players[0], 0); peers.Sent.Clear(); peers.Receive(snapshot);
            byte[][] claims = peers.Sent.Where(p => p[0] == InfiniNetPacketIds.SyncGeneratedItemVfxEvent).ToArray();
            Equal(3, claims.Length, "confirmation sends every independent pending occurrence once");
            Equal(localEmissions, emission.Emitted.Count, "authority correction does not replay owner presentation");
            Equal(true, firstBinding.IsLive && secondBinding.IsLive, "same live predicted attachments survive exact component confirmation");
            Equal(false, jumps.Jump.CanStart(players[0].Player), "confirmation never refills either component ledger");
            peers.Sent.Clear(); peers.Receive(snapshot);
            Equal(0, peers.Sent.Count, "repeated snapshot cannot retransmit consumed occurrences");
            AirJumpPeerMode(peers, players[1], 1);
            foreach (byte[] claim in claims) peers.Receive(claim, 0);
            byte[][] relays = peers.Sent.ToArray(); peers.Sent.Clear();
            Equal(3, relays.Length, "server accepts corrected exact generations for both components");
            AirJumpPeerMode(peers, players[2], 2); peers.Receive(snapshot);
            int before = emission.Emitted.Count;
            foreach (byte[] relay in relays) { peers.Receive(relay); peers.Receive(relay); }
            Equal(before + 3, emission.Emitted.Count, "observer receives multiplicity without replay duplication");
            Equal(true, emission.Emitted.Skip(before).All(point => point == originalPoint),
                "queued events retain their original jump frame, not confirmation-time position");
        });
    }

    private static void AirJumpPredictionCannotRebindRetiredLifetime()
    {
        foreach (string retirement in new[] { "expiry", "death", "correction", "world" })
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_prediction_retirement", 1, held: false); peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            players[0].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            players[0].Player.RefreshExtraJumps(); peers.Sent.Clear(); bool sound = true;
            jumps.Jump.OnStarted(players[0].Player, ref sound);
            Equal(0, peers.Sent.Count, "prediction waits for authority before its source is confirmed");
            if (retirement == "expiry") {
                MaterialClock(101); ResetNativeAirJumpTick(players[0].Player, players[0].Effects);
            } else if (retirement == "death") {
                players[0].Player.dead = true; players[0].Effects.UpdateDead(); players[0].Player.dead = false;
            } else if (retirement == "world") new GeneratedAirJumpLifecycleSystem().OnWorldUnload();
            else {
                AirJumpPeerMode(peers, players[1], 1); byte[] empty = AirJumpUtilitySnapshot(players[1].Effects);
                AirJumpPeerMode(peers, players[0], 0); peers.Receive(empty);
            }
            // A fresh equal-looking prediction/authority row must never inherit
            // the old pending event, including when IsLive was not polled at expiry.
            AirJumpPeerMode(peers, players[0], 0);
            players[0].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            AirJumpPeerMode(peers, players[1], 1);
            players[1].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            AirJumpPeerMode(peers, players[0], 0); peers.Sent.Clear(); peers.Receive(snapshot);
            Equal(0, peers.Sent.Count, "old pending event cannot rebind after " + retirement);
        });
    }


    private static void AirJumpPredictionRejectsAmbiguousOldConfirmation()
    {
        AirJumpPredictionRecoversAfterAuthorityFence();
        AirJumpRecoveryRejectsRetiredFence();
        AirJumpRecoveryRetainsLaterRetirements();
        AirJumpRecoveryWaitsForAsyncUtility();
        foreach (string retirement in new[] { "expiry", "same-tick", "eviction", "correction" })
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_ambiguous_prediction", retirement == "eviction" ? 10 : 1, held: false); peers.Register(data);
            AirJumpPeerMode(peers, players[1], 1);
            byte[] earlierEmptySnapshot = AirJumpUtilitySnapshot(players[1].Effects);
            players[1].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            byte[] oldSnapshot = AirJumpUtilitySnapshot(players[1].Effects);
            AirJumpPeerMode(peers, players[0], 0);
            players[0].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            if (retirement == "expiry") { MaterialClock(101); ResetNativeAirJumpTick(players[0].Player, players[0].Effects); }
            if (retirement == "correction") peers.Receive(earlierEmptySnapshot);
            if (retirement == "eviction")
                for (int index = 1; index <= 32; index++)
                    players[0].Effects.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 20, MovementSpeed = index / 100f });
            players[0].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            players[0].Player.RefreshExtraJumps(); bool sound = true; peers.Sent.Clear();
            jumps.Jump.OnStarted(players[0].Player, ref sound);
            Equal(0, peers.Sent.Count, "new prediction waits independently of its retired predecessor");
            peers.Receive(oldSnapshot);
            Equal(0, peers.Sent.Count, "first unseen old authority cannot confirm a replacement prediction");
            Equal(false, players[0].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _, 0),
                "unassigned zero alias cannot resolve a confirmed source");
            AirJumpPeerMode(peers, players[1], 1); players[1].Effects.ClearGeneratedUtilityState();
            players[1].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            byte[] latestSnapshot = AirJumpUtilitySnapshot(players[1].Effects);
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(latestSnapshot);
            Equal(0, peers.Sent.Count, "later exact authority also cannot revive discarded ambiguous event");
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
            AirJumpPeerMode(peers, players[1], 1); peers.Receive(claim, 0); AirJumpTakeEvent(peers);
        });
    }


    private static void AirJumpPredictionRecoversAfterAuthorityFence()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_recover_prediction", 10, held: false); peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            var buff = data.RuntimeProgram.EffectGroups![0].GeneratedBuff;
            players[0].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            players[0].Effects.ClearGeneratedUtilityState();
            // Fill the bounded retirement history, then repeat an existing
            // key at capacity. Only a genuinely new key may overflow it.
            for (int index = 0; index < 31; index++) {
                var other = AirJumpNetworkBuff("jump_retired_" + index, 10, held: false); peers.Register(other);
                players[0].Effects.ApplyGeneratedUtilityBuff(other.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: other);
                players[0].Effects.ClearGeneratedUtilityState();
            }
            players[0].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            players[0].Effects.ClearGeneratedUtilityState();
            bool Overflow() => (bool)typeof(InfiniCraftPlayer).GetField("_airJumpPredictionHistoryOverflow", MobilityConsumptionFlags)!.GetValue(players[0].Effects)!;
            Equal(false, Overflow(), "retiring duplicate at capacity does not overflow history");
            var overflow = AirJumpNetworkBuff("jump_retired_overflow", 10, held: false); peers.Register(overflow);
            players[0].Effects.ApplyGeneratedUtilityBuff(overflow.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: overflow);
            players[0].Effects.ClearGeneratedUtilityState();
            Equal(true, Overflow(), "distinct retirement beyond capacity fails closed until fence");
            // Drive the real utility synchronization tick, not a manufactured
            // acknowledgement or a mutation of private correlation state.
            peers.Sent.Clear();
            typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityRespawnSync", MobilityConsumptionFlags)!
                .Invoke(players[0].Effects, null);
            Equal(1, peers.Sent.Count, "retired prediction requests a bounded authority fence");
            byte[] request = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[1], 1);
            players[1].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            byte[] oldSnapshot = AirJumpUtilitySnapshot(players[1].Effects);
            peers.Receive(request, 0);
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything();
            Equal(1, peers.Sent.Count, "authority returns one correlated generation fence");
            byte[] reply = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[0], 0);
            var unrelatedReply = (byte[])reply.Clone(); unrelatedReply[2] ^= 1;
            peers.Receive(unrelatedReply); peers.Receive(reply, 0);
            Equal(true, Overflow(), "wrong nonce or nonserver reply cannot release history");
            peers.Receive(oldSnapshot); peers.Receive(reply);
            Equal(false, Overflow(), "correlated fence recovers overflow without evicting unknown history");
            Equal(0, peers.Sent.Count, "fence cannot revive retired prediction");
            bool sound = true;
            players[0].Effects.ClearGeneratedUtilityState();
            players[0].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            players[0].Player.RefreshExtraJumps(); jumps.Jump.OnStarted(players[0].Player, ref sound);
            Equal(0, peers.Sent.Count, "fresh predicted occurrence still waits for authority");
            AirJumpPeerMode(peers, players[1], 1); players[1].Effects.ClearGeneratedUtilityState();
            players[1].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(snapshot);
            byte[] claim = AirJumpTakeEvent(peers);
            peers.Receive(snapshot); peers.Receive(reply);
            Equal(0, peers.Sent.Count, "replayed snapshot and fence cannot resend occurrence");
            AirJumpPeerMode(peers, players[1], 1); peers.Receive(claim, 0); AirJumpTakeEvent(peers);
        });
    }

    private static void AirJumpRecoveryRetainsLaterRetirements()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_inflight_retirement", 1, held: false); peers.Register(data);
            var buff = data.RuntimeProgram.EffectGroups![0].GeneratedBuff;
            void TickSync() => typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityRespawnSync", MobilityConsumptionFlags)!.Invoke(players[0].Effects, null);
            int HistoryCount() => ((IDictionary)typeof(InfiniCraftPlayer).GetField("_retiredAirJumpPredictions", MobilityConsumptionFlags)!.GetValue(players[0].Effects)!).Count;
            AirJumpPeerMode(peers, players[0], 0);
            players[0].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            players[0].Effects.ClearGeneratedUtilityState(); peers.Sent.Clear(); TickSync();
            byte[] request = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[1], 1);
            players[1].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            peers.Receive(request, 0);
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything(); byte[] reply = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[0], 0);
            players[0].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            MaterialClock(101); ResetNativeAirJumpTick(players[0].Player, players[0].Effects);
            peers.Receive(reply);
            Equal(1, HistoryCount(), "earlier fence cannot clear a retirement allocated after its request");
            TickSync(); request = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[1], 1); peers.Receive(request, 0);
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything();
            reply = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(reply);
            Equal(0, HistoryCount(), "next ordered fence safely recovers the later retirement");
        });
    }

    private static void AirJumpRecoveryWaitsForAsyncUtility()
    {
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var data = AirJumpNetworkBuff("jump_delayed_fence", 10, held: false); peers.Register(data);
            AirJumpPeerMode(peers, players[0], 0);
            players[0].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            players[0].Effects.ClearGeneratedUtilityState(); peers.Sent.Clear();
            typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityRespawnSync", MobilityConsumptionFlags)!.Invoke(players[0].Effects, null);
            byte[] request = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[1], 1);
            var action = new RuntimeEventActionSpec { ActionCode = RuntimeEventActionCode.ApplyGeneratedBuff,
                Event = RuntimeEventKind.OnHurt, EffectGroupId = "primary_effects", DelayTicks = 10 };
            Equal(true, InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.TrySchedule(data,
                new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, action, players[1].Player,
                new Terraria.DataStructures.EntitySource_Misc("InfiniRuntimeEquipmentReaction"), Vector2.Zero, Vector2.UnitX,
                null, 0, 0, new InfiniCrafterLocal.Common.Runtime.RuntimeSpawnBudget(0)), "server queued utility predates fence");
            peers.Receive(request, 0);
            Equal(0, peers.Sent.Count, "packet arrival alone cannot acknowledge delayed utility");
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything();
            Equal(0, peers.Sent.Count, "pending delayed utility keeps fence closed");
            MaterialClock(111); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Update();
            Equal(1, AirJumpBuffRows(players[1].Effects).Count, "delayed production action actually allocated authority generation");
            peers.Sent.Clear(); players[1].Player.itemAnimation = 1;
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything();
            Equal(0, peers.Sent.Count, "native use in progress keeps fence closed");
            players[1].Player.itemAnimation = 0;
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything();
            Equal(1, peers.Sent.Count, "drained native update acknowledges fence");
            byte[] reply = peers.Sent.Single(); peers.Sent.Clear();
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(reply);
            Equal(AirJumpBuffRows(players[1].Effects).Single().Generation,
                (long)typeof(InfiniCraftPlayer).GetField("_lastAuthoritativeBuffGeneration", MobilityConsumptionFlags)!.GetValue(players[0].Effects)!,
                "fence watermark includes late delayed allocation");
            InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
        });
        using (var f = new QuickUtilityPeers()) {
            var data = AirJumpNetworkBuff("jump_quick_fence", 10, held: false); f.Peers.Register(data);
            f.Mode(1); f.OwnerBuff.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            f.OwnerBuff.ClearGeneratedUtilityState();
            byte[] prepare = f.Prepare();
            var tick = typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityRespawnSync", MobilityConsumptionFlags)!;
            f.Peers.Sent.Clear(); tick.Invoke(f.OwnerBuff, null);
            Equal(0, f.Peers.Sent.Count, "local Prepare waiting for Ready cannot send a premature fence");
            byte[] ready = f.Ready(prepare), commit = f.Commit(ready);
            f.Mode(1); f.Owner.itemAnimation = f.Owner.itemTime = 0; f.Owner.controlUseItem = false;
            f.Peers.Sent.Clear(); tick.Invoke(f.OwnerBuff, null);
            byte[] request = f.Peers.Sent.Single(); f.Peers.Sent.Clear();
            // Intentionally deliver request before Commit to prove server-side
            // pending tickets are checked independently of the owner's gate.
            f.ReceiveServer(request); new GeneratedAirJumpLifecycleSystem().PostUpdateEverything();
            Equal(0, f.Peers.Sent.Count, "server Ready awaiting Commit keeps fence closed");
            f.ReceiveServer(commit); f.Peers.Sent.Clear();
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything();
            Equal(1, f.Peers.Sent.Count, "consumed one-shot ticket permits fence after native update");
        }
    }

    private static void AirJumpRecoveryRejectsRetiredFence()
    {
        foreach (string boundary in new[] { "death", "world", "connection" })
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var connection = Netplay.Connection; var socket = connection.Socket;
            try {
                var data = AirJumpNetworkBuff("jump_old_fence", 10, held: false); peers.Register(data);
                var buff = data.RuntimeProgram.EffectGroups![0].GeneratedBuff;
                AirJumpPeerMode(peers, players[0], 0);
                players[0].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
                players[0].Effects.ClearGeneratedUtilityState(); peers.Sent.Clear();
                typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityRespawnSync", MobilityConsumptionFlags)!.Invoke(players[0].Effects, null);
                byte[] request = peers.Sent.Single(); peers.Sent.Clear();
                AirJumpPeerMode(peers, players[1], 1);
                players[1].Effects.ApplyGeneratedUtilityBuff(buff, source: data);
                peers.Receive(request, 0);
            new GeneratedAirJumpLifecycleSystem().PostUpdateEverything(); byte[] reply = peers.Sent.Single(); peers.Sent.Clear();
                AirJumpPeerMode(peers, players[0], 0);
                if (boundary == "death") {
                    players[0].Player.dead = true; players[0].Effects.UpdateDead(); players[0].Player.dead = false;
                } else if (boundary == "world") new GeneratedAirJumpLifecycleSystem().OnWorldUnload();
                else connection.Socket = (Terraria.Net.Sockets.ISocket)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Net.Sockets.TcpSocket));
                peers.Receive(reply);
                Equal(0L, (long)typeof(InfiniCraftPlayer).GetField("_lastAuthoritativeBuffGeneration", MobilityConsumptionFlags)!.GetValue(players[0].Effects)!,
                    "retired fence cannot import the old authority watermark after " + boundary);
            } finally { connection.Socket = socket; }
        });
    }

    private static void AirJumpPredictionNewWorldResetsAuthorityHistory()
    {
        foreach (bool reconnect in new[] { false, true })
        WithAirJumpNetwork((peers, jumps, emission, players) => {
            var connection = Netplay.Connection; var oldSocket = connection.Socket;
            try {
            var data = AirJumpNetworkBuff("jump_new_authority", 10, held: false); peers.Register(data);
            AirJumpPeerMode(peers, players[1], 1);
            for (int index = 0; index < 4; index++) {
                players[1].Effects.ClearGeneratedUtilityState();
                players[1].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            }
            byte[] oldSnapshot = AirJumpUtilitySnapshot(players[1].Effects);
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(oldSnapshot);
            long oldAuthority = AirJumpBuffRows(players[0].Effects).Single().Generation;
            if (reconnect)
                connection.Socket = (Terraria.Net.Sockets.ISocket)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Net.Sockets.TcpSocket));
            else new GeneratedAirJumpLifecycleSystem().OnWorldUnload();
            Equal(false, players[0].Effects.TryGetLiveAirJumpSource(data.Id, out _, out _, oldAuthority),
                "old source is retired immediately at world/connection boundary");
            players[0].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            ResetNativeAirJumpTick(players[0].Player, players[0].Effects); players[0].Effects.PostUpdateEquips();
            players[0].Player.RefreshExtraJumps(); bool sound = true; peers.Sent.Clear();
            jumps.Jump.OnStarted(players[0].Player, ref sound);
            Equal(0, peers.Sent.Count, "new world prediction cannot borrow an old confirmed source");
            // The unused third independent peer stands in for a fresh server.
            AirJumpPeerMode(peers, players[2], 1);
            players[2].Effects.ApplyGeneratedUtilityBuff(data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: data);
            byte[] newSnapshot = AirJumpUtilitySnapshot(players[2].Effects);
            Equal(true, AirJumpBuffRows(players[2].Effects).Single().Generation > oldAuthority,
                "new authority really has a shorter generation history");
            AirJumpPeerMode(peers, players[0], 0); peers.Receive(newSnapshot);
            byte[] claim = AirJumpTakeEvent(peers);
            AirJumpPeerMode(peers, players[2], 1); peers.Receive(claim, 0); AirJumpTakeEvent(peers);
            } finally { connection.Socket = oldSocket; }
        });
    }

}
