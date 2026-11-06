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
    // the final lightCue renderer are intercepted, not source/event admission.
    private sealed record AirJumpNetworkPeer(Player Player, InfiniCraftPlayer Effects);
    private sealed class AirJumpEmissionProbe : IDisposable
    {
        internal readonly List<Player> Emitted = new();
        private readonly MonoMod.RuntimeDetour.ILHook hook;
        internal AirJumpEmissionProbe()
        {
            hook = new(typeof(InfiniItemVfxRuntime).GetMethod("EmitLocal", BindingFlags.Static | BindingFlags.NonPublic)!, il => {
                var cursor = new ILCursor(il);
                cursor.Emit(Mono.Cecil.Cil.OpCodes.Ldarg_0);
                cursor.Emit(Mono.Cecil.Cil.OpCodes.Ldarg_3);
                cursor.EmitDelegate<Action<Player, string>>((player, ev) => {
                    if (ev == RuntimeEventKind.OnJump) Emitted.Add(player);
                });
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
            byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
            // The server's own accepted activation is live, but its equip hook
            // has not run. Client snapshots are never gameplay activation.
            AirJumpPeerMode(peers, players[1], 1);
            var serverItem = AirJumpCopyItem(ownerItem); players[1].Player.inventory[0] = serverItem.Item;
            Equal(true, players[1].Effects.ApplyGeneratedUtilityBuff(
                serverItem.Data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: serverItem.Data), "server accepts canonical buff activation");
            peers.Sent.Clear();
            byte[] snapshot = AirJumpUtilitySnapshot(players[1].Effects);
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
            byte[] claim = AirJumpNativeClaim(peers, jumps, players[0]);
            byte[] snapshot = AirJumpUtilitySnapshot(players[0].Effects);
            AirJumpPeerMode(peers, players[1], 1); peers.Receive(snapshot, 0); peers.Sent.Clear();
            Equal(0, AirJumpBuffRows(players[1].Effects).Count, "client snapshot cannot create a server buff");
            peers.Receive(claim, 0);
            Equal(0, peers.Sent.Count, "unowned jump event cannot create its own source");
            AirJumpPeerMode(peers, players[2], 2); peers.Receive(snapshot, 0);
            Equal(0, AirJumpBuffRows(players[2].Effects).Count, "observer accepts utility state only from server");
            AirJumpPeerMode(peers, players[1], 1);
            var serverItem = AirJumpCopyItem(item); players[1].Player.inventory[0] = serverItem.Item;
            Equal(true, players[1].Effects.ApplyGeneratedUtilityBuff(
                serverItem.Data.RuntimeProgram.EffectGroups![0].GeneratedBuff, source: serverItem.Data), "server starts its own canonical buff");
            snapshot = AirJumpUtilitySnapshot(players[1].Effects); peers.Sent.Clear();
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
}
