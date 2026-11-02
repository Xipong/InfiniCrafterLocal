using System;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static byte[] NativeUseWire(GeneratedItem item)
    {
        using var stream = new MemoryStream(); item.NetSend(new BinaryWriter(stream)); return stream.ToArray();
    }
    private static void NativeUsePeerMode(ReviewPeers peers, int mode, int local)
    {
        peers.Mode(mode, local);
        Terraria.Main.projectile = Enumerable.Range(0, Terraria.Main.maxProjectiles).Select(i => new Projectile { whoAmI = i }).ToArray();
    }
    private static void NativeUsePreparePlayer(Player player)
    {
        player.whoAmI = 0; player.active = true; player.selectedItem = 0;
        player.statMana = player.statManaMax2 = 100; player.manaCost = 1f;
        Terraria.Main.player[0] = player;
    }
    private static void NativeUseSnapshotQuickUseKeepsHeldIntent()
    {
        using var f = new QuickUtilityPeers(initialSync: true);
        Terraria.Main.projectile = Enumerable.Range(0, Terraria.Main.maxProjectiles).Select(i => new Projectile { whoAmI = i }).ToArray();
        var data = NativeFishingFixture(true); data.Id = "held_fishing_during_quick_use"; data.Normalize(); f.Peers.Register(data);
        var held = MobilityConsumptionHost(data); f.Owner.inventory[1] = held.Item; f.Owner.selectedItem = 1;
        f.Owner.altFunctionUse = 2; Equal(true, held.CanUseItem(f.Owner), "selected alternate rod before quick use");
        var prior = held.NativeUseProjection;
        f.Quick(); // real native QuickHeal and existing activation ticket, not selected-item input
        int sends = f.EquipmentSends;
        f.OwnerBuff.PublishNativeUseProjection(held, RuntimeInputKind.AlternateUse);
        Equal(sends, f.EquipmentSends, "quick utility does not replace held selector authority");
        Equal(prior, held.NativeUseProjection, "held revision is unchanged by unselected utility use");
        f.OwnerBuff.PreItemCheck();
        Equal(25, held.Item.fishingPole, "quick use does not reset persistent held fishing projection");
    }

    private static void NativeUseSnapshotCursorInventoryBoundary()
    {
        using var actors = new MobilityConsumptionNativeScope(); using var peers = new ReviewPeers();
        using var send = PersistenceObserveNetworkSend((_, __) => { });
        int cursor = PlayerItemSlotID.InventoryMouseItem - PlayerItemSlotID.Inventory0;
        Equal(58, cursor, "installed native mouse inventory index");
        Equal(true, PlayerItemSlotID.CanRelay[PlayerItemSlotID.InventoryMouseItem], "native cursor equipment relay allowed");
        foreach (bool alternate in new[] { false, true }) {
            var data = NativeFishingFixture(alternate); data.Id = "native_cursor_" + alternate;
            data.Normalize(); GeneratedItemRegistryService.StampCurrentWorld(data); peers.Registry.RegisterLocal(data, false, false);
            byte[] wire = Array.Empty<byte>();
            WithPlayer((owner, _) => {
                NativeUsePreparePlayer(owner); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 0);
                owner.selectedItem = cursor; var item = MobilityConsumptionHost(data); owner.inventory[cursor] = item.Item;
                // ALT here tests the transport domain, not native right-click acquisition:
                // native ManageRightClickFeatures intentionally skips the cursor slot.
                owner.altFunctionUse = alternate ? 2 : 0;
                Equal(true, item.CanUseItem(owner), "cursor projection intent");
                Equal((byte)cursor, item.NativeUseProjection!.Value.Slot, "cursor index encoded");
                Equal(true, item.NativeUseProjection!.Value.Valid, "cursor snapshot admitted");
                Equal(false, (item.NativeUseProjection!.Value with { Slot = (byte)(cursor + 1) }).Valid, "equipment outside inventory rejected");
                wire = NativeUseWire(item);
            });
            WithPlayer((remote, state) => {
                NativeUsePreparePlayer(remote); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 1); remote.selectedItem = cursor;
                var item = MobilityConsumptionHost(GeneratedItemData.Placeholder()); item.NetReceive(new BinaryReader(new MemoryStream(wire)));
                remote.inventory[cursor] = item.Item; state.PreItemCheck();
                Equal(25, item.Item.fishingPole, "cursor serialized fishing projection survives");
                Equal(ProjectileID.BobberWooden, item.Item.shoot, "cursor native shoot identity");
                Equal(0, item.UseCalls, "cursor receiver no activation");
            });
        }
    }

    private static void NativeUseSnapshotSerializedPeers()
    {
        using var actors = new MobilityConsumptionNativeScope();
        using var peers = new ReviewPeers();
        int equipmentSends = 0;
        using var send = PersistenceObserveNetworkSend((message, _) => { if (message == MessageID.SyncEquipment) equipmentSends++; });
        var data = NativeFishingFixture(true); data.Id = "native_alt_snapshot";
        data.Normalize(); GeneratedItemRegistryService.StampCurrentWorld(data);
        peers.Registry.RegisterLocal(data, false, false);
        byte[] alternate = Array.Empty<byte>(), primary = Array.Empty<byte>();
        long token = 0;
        WithPlayer((owner, ownerState) => {
            NativeUsePreparePlayer(owner); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 0);
            var item = MobilityConsumptionHost(data); owner.inventory[0] = item.Item;
            owner.altFunctionUse = 2;
            Equal(true, item.CanUseItem(owner), "local alternate intent admits");
            Equal(1, equipmentSends, "intent uses one existing equipment sync before native shot");
            Equal(100, owner.statMana, "projection sync is not payment");
            Equal(0, item.UseCalls, "projection sync is not a successful-use event");
            alternate = NativeUseWire(item); token = item.PresentationToken;
            using (var read = new BinaryReader(new MemoryStream(alternate))) Equal(9, read.ReadInt32(), "active projection has explicit version");
            owner.altFunctionUse = 0; owner.itemAnimation = 0;
            ownerState.PreItemCheck();
            Equal(25, item.Item.fishingPole, "idle animation end never resets selected fishing projection");
            Equal(1, equipmentSends, "idle native selector reset is not a new input");
            Equal(true, item.CanUseItem(owner), "deliberate primary intent");
            Equal(2, equipmentSends, "changed intent publishes newer snapshot");
            Equal(0, item.Item.fishingPole, "primary ordinary action cancels native rod identity");
            primary = NativeUseWire(item);
        });
        byte[] relay = Array.Empty<byte>();
        WithPlayer((server, state) => {
            NativeUsePreparePlayer(server); NativeUsePeerMode(peers, NetmodeID.Server, 255);
            var received = MobilityConsumptionHost(GeneratedItemData.Placeholder());
            received.NetReceive(new BinaryReader(new MemoryStream(alternate))); server.inventory[0] = received.Item;
            state.PreItemCheck();
            Equal(token, received.PresentationToken, "native item identity survives owner to server");
            Equal(25, received.Item.fishingPole, "server restores alternate despite native selector zero");
            Equal(ProjectileID.BobberWooden, received.Item.shoot, "server native bobber identity");
            Equal(100, server.statMana, "server receipt does not pay"); Equal(0, received.UseCalls, "server receipt does not activate");
            relay = NativeUseWire(received);
            var next = MobilityConsumptionHost(GeneratedItemData.Placeholder()); next.NetReceive(new BinaryReader(new MemoryStream(primary)));
            server.inventory[0] = next.Item; state.PreItemCheck();
            Equal(0, next.Item.fishingPole, "new primary intent reaches server");
            var stale = MobilityConsumptionHost(GeneratedItemData.Placeholder()); stale.NetReceive(new BinaryReader(new MemoryStream(alternate)));
            server.inventory[0] = stale.Item; state.PreItemCheck();
            Equal(0, stale.Item.fishingPole, "older replacement cannot resurrect alternate rod");
            Equal((byte)0, stale.NativeUseProjection!.Value.Input, "last accepted selector retained without data backup");
        });
        WithPlayer((remote, state) => {
            NativeUsePreparePlayer(remote); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 1);
            var received = MobilityConsumptionHost(GeneratedItemData.Placeholder());
            received.NetReceive(new BinaryReader(new MemoryStream(relay))); remote.inventory[0] = received.Item;
            state.PreItemCheck();
            Equal(25, received.Item.fishingPole, "fresh remote peer accepts latest initial revision");
            Equal(ProjectileID.BobberWooden, received.Item.shoot, "relay keeps native bobber fields");
            Equal(0, received.UseCalls, "remote receipt emits no use callback");
            Equal(100, remote.statMana, "remote receipt has no resource side effect");
        });
    }

    private static void NativeUseSnapshotCompactHydrationAndRefusals()
    {
        using var actors = new MobilityConsumptionNativeScope(); using var peers = new ReviewPeers();
        using var send = PersistenceObserveNetworkSend((_, __) => { });
        var data = NativeFishingFixture(true); data.Id = "native_alt_pending"; data.Visual.SpritePath = "valid.png"; data.Normalize();
        GeneratedItemRegistryService.StampCurrentWorld(data); peers.Registry.RegisterLocal(data, false, false);
        byte[] wire = Array.Empty<byte>();
        WithPlayer((owner, _) => {
            NativeUsePreparePlayer(owner); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 0);
            var host = MobilityConsumptionHost(data); owner.inventory[0] = host.Item; owner.altFunctionUse = 2;
            Equal(true, host.CanUseItem(owner), "pending fixture owner intent"); wire = NativeUseWire(host);
        });
        var registry = typeof(InfiniMod).GetProperty("GeneratedItems")!;
        WithPlayer((remote, state) => {
            NativeUsePreparePlayer(remote); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 1);
            using var lateRegistry = new GeneratedItemRegistryService();
            registry.SetValue(null, lateRegistry);
            var held = MobilityConsumptionHost(GeneratedItemData.Placeholder());
            held.NetReceive(new BinaryReader(new MemoryStream(wire))); remote.inventory[0] = held.Item;
            Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(held.Data), "actual compact reference remains unresolved");
            Equal(true, state.ResolveNativeUseProjection(held) is null, "pending alternate never becomes primary");
            using var forwarded = new MemoryStream(); held.NetSend(new BinaryWriter(forwarded));
            Equal(false, lateRegistry.TryGet(data.Id, out _), "no prepopulated canonical definition on late peer");
            peers.Mod.HandlePacket(new BinaryReader(new MemoryStream(AssetLifecycleDefinitionPacket(data))), 256);
            Equal(true, lateRegistry.TryGet(data.Id, out _), "actual async definition packet passes decompression/hash/registry admission");
            MaterialClock((uint)Terraria.Main.GameUpdateCount + 91);
            Equal(true, held.CanUseItem(remote), "existing hydration retry resolves late native selector");
            state.PreItemCheck();
            Equal(false, GeneratedItemData.IsPlayerSaveReferenceOnly(held.Data), "existing registry hydration resolves definition");
            Equal(25, held.Item.fishingPole, "alternate snapshot survives SetData during hydration");
            Equal((byte)1, held.NativeUseProjection!.Value.Input, "accepted input is not replaced by default primary");
            foreach (int length in new[] { 0, 3, wire.Length - 1 }) {
                var truncated = MobilityConsumptionHost(GeneratedItemData.Placeholder());
                truncated.NetReceive(new BinaryReader(new MemoryStream(wire.Take(length).ToArray())));
                remote.inventory[0] = truncated.Item;
                Equal(true, state.ResolveNativeUseProjection(truncated) is null, "truncated snapshot cannot fall back to primary");
            }
            remote.inventory[0] = held.Item;
            Equal(true, state.ResolveNativeUseProjection(held) is not null, "malformed replacement does not erase accepted revision fence");
            registry.SetValue(null, peers.Registry);
        });
    }
    private static void NativeUseSnapshotLifecycleAndMalformedInputs()
    {
        using var actors = new MobilityConsumptionNativeScope(); using var peers = new ReviewPeers();
        int sends = 0;
        using var send = PersistenceObserveNetworkSend((message, _) => { if (message == MessageID.SyncEquipment) sends++; });
        var data = NativeFishingFixture(true); data.Id = "native_alt_lifecycle"; data.Normalize();
        GeneratedItemRegistryService.StampCurrentWorld(data); peers.Registry.RegisterLocal(data, false, false);
        byte[] wire = Array.Empty<byte>();
        WithPlayer((owner, state) => {
            NativeUsePreparePlayer(owner); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 0);
            var item = MobilityConsumptionHost(data); owner.inventory[0] = item.Item; owner.altFunctionUse = 2;
            Equal(true, item.CanUseItem(owner), "lifecycle alternate intent");
            ulong first = item.NativeUseProjection!.Value.Revision;
            owner.selectedItem = 1; owner.inventory[1] = new Item(ItemID.CopperShortsword);
            state.PreItemCheck();
            Equal(0, item.Item.fishingPole, "actual slot switch resets departed native projection");
            Equal(true, item.NativeUseProjection!.Value.Revision > first, "switch reset publishes a newer revision");
            owner.selectedItem = 0; owner.altFunctionUse = 2;
            Equal(true, item.CanUseItem(owner), "new intentional alternate after reselect");
            wire = NativeUseWire(item);
            owner.dead = true; state.PreItemCheck();
            Equal(0, item.Item.fishingPole, "death resets selected native fields");
            Equal(0, item.UseCalls, "lifecycle never replays gameplay callbacks");
            Equal(100, owner.statMana, "lifecycle never pays resources");
        });
        using var parser = new BinaryReader(new MemoryStream(wire));
        parser.ReadInt32(); parser.ReadString(); long tokenOffset = parser.BaseStream.Position;
        parser.ReadInt64(); parser.ReadInt32(); parser.ReadBoolean();
        int ownerOffset = (int)parser.BaseStream.Position; parser.ReadByte();
        int slotOffset = (int)parser.BaseStream.Position; parser.ReadByte();
        int revisionOffset = (int)parser.BaseStream.Position; parser.ReadUInt64();
        int inputOffset = (int)parser.BaseStream.Position;
        WithPlayer((remote, state) => {
            NativeUsePreparePlayer(remote); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 1);
            foreach (string reason in new[] { "version", "zero-token", "zero-revision", "unknown-input", "wrong-owner", "wrong-slot", "wrong-definition" }) {
                byte[] bad = (byte[])wire.Clone();
                switch (reason) {
                    case "version": Array.Copy(BitConverter.GetBytes(99), bad, 4); break;
                    case "zero-token": Array.Clear(bad, (int)tokenOffset, 8); break;
                    case "zero-revision": Array.Clear(bad, revisionOffset, 8); break;
                    case "unknown-input": bad[inputOffset] = 2; break;
                    case "wrong-owner": bad[ownerOffset] = 1; break;
                    case "wrong-slot": bad[slotOffset] = 1; break;
                    case "wrong-definition": bad[^1] ^= 1; break;
                }
                var rejected = MobilityConsumptionHost(GeneratedItemData.Placeholder());
                rejected.NetReceive(new BinaryReader(new MemoryStream(bad))); remote.inventory[0] = rejected.Item;
                Equal(true, state.ResolveNativeUseProjection(rejected) is null, reason + " refuses native selector");
                Equal(0, rejected.UseCalls, reason + " cannot activate effects");
            }
            var valid = MobilityConsumptionHost(GeneratedItemData.Placeholder());
            valid.NetReceive(new BinaryReader(new MemoryStream(wire))); remote.inventory[0] = valid.Item;
            Equal(true, state.ResolveNativeUseProjection(valid) is not null, "invalid inputs cannot poison a fresh valid revision");
            Equal(25, valid.Item.fishingPole, "valid alternate resumes exact native fields");
        });
    }

    private static void NativeUseSnapshotSwitchBackKeepsOwnerOrder()
    {
        using var actors = new MobilityConsumptionNativeScope(); using var peers = new ReviewPeers();
        using var send = PersistenceObserveNetworkSend((_, __) => { });
        foreach (bool alternate in new[] { false, true }) {
            var a = NativeFishingFixture(true); a.Id = "switch_a_" + alternate; a.Normalize();
            var b = NativeFishingFixture(true); b.Id = "switch_b_" + alternate; b.Normalize();
            foreach (var data in new[] { a, b }) { GeneratedItemRegistryService.StampCurrentWorld(data); peers.Registry.RegisterLocal(data, false, false); }
            var packets = new byte[3][]; var revisions = new ulong[3];
            WithPlayer((owner, state) => {
                NativeUsePreparePlayer(owner); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 0);
                var first = MobilityConsumptionHost(a); var second = MobilityConsumptionHost(b);
                owner.inventory[0] = first.Item; owner.inventory[1] = second.Item;
                for (int step = 0; step < 3; step++) {
                    owner.selectedItem = step == 1 ? 1 : 0;
                    state.PreItemCheck(); owner.altFunctionUse = alternate ? 2 : 0;
                    var held = step == 1 ? second : first;
                    Equal(true, held.CanUseItem(owner), "A B A explicit input");
                    revisions[step] = held.NativeUseProjection!.Value.Revision;
                    packets[step] = NativeUseWire(held);
                    if (step > 0) Equal(true, revisions[step] > revisions[step - 1], "A B A must advance owner order even when an item's input is unchanged");
                }
            });
            WithPlayer((remote, state) => {
                NativeUsePreparePlayer(remote); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 1);
                for (int step = 0; step < 3; step++) {
                    remote.selectedItem = step == 1 ? 1 : 0;
                    var item = MobilityConsumptionHost(GeneratedItemData.Placeholder());
                    item.NetReceive(new BinaryReader(new MemoryStream(packets[step]))); remote.inventory[remote.selectedItem] = item.Item;
                    Equal(true, state.ResolveNativeUseProjection(item) is not null, "serialized A B A receiver admits each current intent");
                    Equal(revisions[step], item.NativeUseProjection!.Value.Revision, "receiver retains new owner revision");
                    Equal(alternate ? 25 : 0, item.Item.fishingPole, "A B A projects exact selected action");
                }
            });
        }
    }

    private static void NativeUseSnapshotConnectionGenerationReset()
    {
        using var actors = new MobilityConsumptionNativeScope(); using var peers = new ReviewPeers();
        using var send = PersistenceObserveNetworkSend((_, __) => { });
        var data = NativeFishingFixture(true); data.Id = "native_alt_reconnect"; data.Normalize();
        GeneratedItemRegistryService.StampCurrentWorld(data); peers.Registry.RegisterLocal(data, false, false);
        byte[] oldWire = Array.Empty<byte>(), newWire = Array.Empty<byte>();
        WithPlayer((owner, state) => {
            NativeUsePreparePlayer(owner); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 0);
            var item = MobilityConsumptionHost(data); owner.inventory[0] = item.Item;
            foreach (int input in new[] { 2, 0, 2 }) { owner.altFunctionUse = input; Equal(true, item.CanUseItem(owner), "old connection actual input"); }
            oldWire = NativeUseWire(item);
            state.PlayerDisconnect(); state.PlayerConnect();
            var fresh = MobilityConsumptionHost(data); owner.inventory[0] = fresh.Item; owner.altFunctionUse = 2;
            Equal(true, fresh.CanUseItem(owner), "new connection actual input");
            Equal(1UL, fresh.NativeUseProjection!.Value.Revision, "new connection starts its own owner revision");
            newWire = NativeUseWire(fresh);
        });
        WithPlayer((remote, state) => {
            NativeUsePreparePlayer(remote); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 1);
            var old = MobilityConsumptionHost(GeneratedItemData.Placeholder()); old.NetReceive(new BinaryReader(new MemoryStream(oldWire)));
            remote.inventory[0] = old.Item; Equal(true, state.ResolveNativeUseProjection(old) is not null, "old peer snapshot admitted");
            state.PlayerDisconnect(); state.PlayerConnect();
            var fresh = MobilityConsumptionHost(GeneratedItemData.Placeholder()); fresh.NetReceive(new BinaryReader(new MemoryStream(newWire)));
            remote.inventory[0] = fresh.Item;
            Equal(true, state.ResolveNativeUseProjection(fresh) is not null, "reconnected owner is not rejected against old revision");
            Equal(25, fresh.Item.fishingPole, "reconnected alternate projects native fields");
        });
    }

}
