using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void Issue345ReturnOneAckDelayedAuthorityRefundIsOneTime()
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers();
        using var network = PersistenceObserveNetworkSend((_, __) => { });
        var world = new GeneratedStationEscrowStateSystem();
        Item oldMouse = Terraria.Main.mouseItem;
        try
        {
            WithPlayer((player, owner) =>
            {
                owner.Initialize(); player.whoAmI = 0; player.active = true;
                Terraria.Main.player[0] = player; peers.Mode(NetmodeID.MultiplayerClient, 0);
                for (int i = 0; i < 58; i++) player.inventory[i] = new Item(ItemID.StoneBlock, 9999);
                string scope = new string('a', 32);
                PersistenceReceiveScope(world, scope);
                owner.ToggleJournalFavorite("removed");
                Terraria.Main.mouseItem = new Item(ItemID.CopperShortsword, 1);
                peers.Sent.Clear();
                Equal(true, owner.TryPutMouseItemIntoInput(0), "real deposit owns one cursor unit");
                PersistenceFinishDeposit(peers, peers.Sent.Single(), scope);
                peers.Sent.Clear();
                Equal(true, owner.TryClearInputToInventory(0), "real ReturnOne request starts");
                using var request = new BinaryReader(new MemoryStream(peers.Sent.Single()));
                Equal(InfiniCrafterLocal.Common.InfiniNetPacketIds.RequestStationEscrow, request.ReadByte(), "real request dispatcher");
                Equal(3, request.ReadInt32(), "real request version");
                Equal(scope, request.ReadString(), "ReturnOne exact scope");
                request.ReadString(); string operation = request.ReadString();
                Equal((byte)3, request.ReadByte(), "ReturnOne action");
                Equal((sbyte)0, request.ReadSByte(), "ReturnOne slot");
                using var ack = new MemoryStream();
                using (var writer = new BinaryWriter(ack, System.Text.Encoding.UTF8, true))
                {
                    writer.Write(InfiniCrafterLocal.Common.InfiniNetPacketIds.StationEscrowResult);
                    writer.Write(3); writer.Write(scope); writer.Write(operation);
                    writer.Write((byte)3); writer.Write((sbyte)0); writer.Write(true); writer.Write("");
                }
                peers.Receive(ack.ToArray()); peers.Receive(ack.ToArray());
                Equal(false, owner.HasPendingStationEscrowOperation, "ReturnOne ACK settles once");
                Equal(true, owner.InputA.IsAir, "ReturnOne ACK retires remote mirror");
                var full = new TagCompound(); owner.SaveData(full);
                Equal(1, full.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "actual ACK retains exactly one undeliverable refund");
                Equal(ItemID.CopperShortsword, ItemIO.Load(full.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Single()).type, "actual ACK saves exact ItemIO identity");
                world.ClearWorld();
                owner.Initialize(); owner.LoadData(PersistenceNbtRoundtrip(full)); owner.OnEnterWorld();
                Equal(false, owner.EnsureRemoteStationAuthority(), "reconnect has no scope yet");
                Equal(0, player.inventory.Take(58).Count(i => i.type == ItemID.CopperShortsword), "full inventory cannot accept delayed refund");
                PersistenceReceiveScope(world, scope);
                player.inventory[0].TurnToAir();
                owner.ToggleJournalFavorite("removed"); owner.ToggleJournalFavorite("added");
                owner.PostUpdate();
                Equal(1, player.inventory.Take(58).Where(i => i.type == ItemID.CopperShortsword).Sum(i => i.stack), "PostUpdate restores authority and delivers exact refund");
                for (int round = 0; round < 3; round++)
                {
                    var saved = new TagCompound(); owner.SaveData(saved);
                    Equal(0, saved.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "ACK refund is retired before active claim save");
                    owner.Initialize(); owner.LoadData(PersistenceNbtRoundtrip(saved)); owner.OnEnterWorld(); owner.PostUpdate();
                    Equal(1, player.inventory.Take(58).Where(i => i.type == ItemID.CopperShortsword).Sum(i => i.stack), "actual ReturnOne ACK refund never duplicates after reload");
                    Equal(false, owner.IsJournalFavorite("removed"), "removed favorite survives ACK recovery save");
                    Equal(true, owner.IsJournalFavorite("added"), "added favorite survives ACK recovery save");
                }
            });
        }
        finally { world.ClearWorld(); Terraria.Main.mouseItem = oldMouse; }
    }

    private static void Issue345EscrowRefundDeliveredOnlyOnce()
        => Issue345EscrowSaveRoundtrip(checkFavorites: false);

    private static void Issue345EscrowFavoritesRemainCurrent()
        => Issue345EscrowSaveRoundtrip(checkFavorites: true);

    private static void Issue345EscrowNestedHistoryCannotRestoreRetiredFields()
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers();
        var world = new GeneratedStationEscrowStateSystem();
        try
        {
            WithPlayer((player, owner) =>
            {
                owner.Initialize(); peers.Mode(NetmodeID.MultiplayerClient, 0);
                string scope = new string('a', 32);
                var claim = new TagCompound
                {
                    ["infiniStationEscrowClientId"] = new string('c', 32),
                    ["infiniStationEscrowRemoteAuthority"] = true,
                    ["infiniStationEscrowOriginScopeV1"] = scope,
                    ["infiniStationEscrowMirror"] = new List<TagCompound>
                    {
                        new() { ["index"] = 0, ["item"] = ItemIO.Save(new Item(ItemID.Wood, 1)) }
                    },
                    ["infiniPendingStationEscrow"] = new TagCompound
                    {
                        ["operationId"] = new string('d', 32), ["action"] = 3, ["index"] = 0
                    }
                };
                owner.LoadData(PersistenceNbtRoundtrip(claim)); PersistenceReceiveScope(world, scope);
                Equal(true, owner.EnsureRemoteStationAuthority(), "exact claim restored");
                var saved = new TagCompound(); owner.SaveData(saved);
                Equal(true, saved.ContainsKey("infiniActiveRemoteStationClaimV1"), "opaque active history is nested");
                saved.Remove("infiniStationEscrowMirror"); saved.Remove("infiniPendingStationEscrow");
                owner.Initialize(); owner.LoadData(PersistenceNbtRoundtrip(saved));
                Equal(true, owner.EnsureRemoteStationAuthority(), "root scope still exact");
                Equal(false, owner.HasPendingStationEscrowOperation, "absent root operation cannot return from nested history");
                Equal(true, owner.InputA.IsAir, "absent root material cannot return from nested history");
                saved["infiniStationEscrowOriginScopeV1"] = new string('b', 32);
                owner.Initialize(); owner.LoadData(PersistenceNbtRoundtrip(saved));
                Equal(true, owner.EnsureRemoteStationAuthority(), "foreign root allows unrelated fresh work");
                Equal(true, owner.InputA.IsAir, "nested old matching origin cannot confer authority");
                Equal(false, owner.HasPendingStationEscrowOperation, "foreign root cannot replay nested operation");
            });
        }
        finally { world.ClearWorld(); }
    }

    private static void Issue345EscrowSaveRoundtrip(bool checkFavorites)
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers();
        using var network = PersistenceObserveNetworkSend((_, __) => { });
        var world = new GeneratedStationEscrowStateSystem();
        string current = new string('a', 32);
        try
        {
            foreach (string origin in new[] { current, new string('b', 32), "", new string('A', 32) })
            WithPlayer((player, owner) =>
            {
                owner.Initialize(); player.whoAmI = 0; player.active = true;
                Terraria.Main.player[0] = player;
                peers.Mode(NetmodeID.MultiplayerClient, 0);
                // Capacity initially unavailable: native refund delivery must stay pending.
                for (int i = 0; i < 58; i++) player.inventory[i] = new Item(ItemID.StoneBlock, 9999);
                var claim = new TagCompound
                {
                    ["infiniStationEscrowClientId"] = new string('c', 32),
                    ["infiniStationEscrowRemoteAuthority"] = true,
                    ["infiniStationEscrowOriginScopeV1"] = origin,
                    ["infiniStationEscrowMirror"] = new List<TagCompound>
                    {
                        new() { ["index"] = 0, ["item"] = ItemIO.Save(new Item(ItemID.CopperShortsword, 1)) }
                    },
                    ["infiniDeferredCraftRefundsV1"] = new List<TagCompound> { ItemIO.Save(new Item(ItemID.Wood, 7)) },
                    ["infiniJournalFavorites"] = new List<string> { Terraria.Main.worldID + ":removed" },
                    ["foreignExtension"] = new TagCompound { ["literal"] = "keep-nested" },
                    ["infiniPendingCraftRefunds"] = new List<TagCompound> { ItemIO.Save(new Item(ItemID.GoldBar, 9)) }
                };
                owner.LoadData(PersistenceNbtRoundtrip(claim));
                PersistenceReceiveScope(world, current);
                owner.OnEnterWorld();
                var blocked = new TagCompound(); owner.SaveData(blocked);
                Equal(7, ItemIO.Load(blocked.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Single()).stack,
                    "undelivered refund survives active or dormant escrow save");
                owner.Initialize(); owner.LoadData(PersistenceNbtRoundtrip(blocked));
                player.inventory[0].TurnToAir();
                owner.OnEnterWorld();
                Equal(7, player.inventory.Take(58).Where(i => i.type == ItemID.Wood).Sum(i => i.stack), "native delivery returns exact saved quantity");
                owner.ToggleJournalFavorite("removed"); owner.ToggleJournalFavorite("added");
                for (int round = 0; round < 3; round++)
                {
                    var saved = new TagCompound(); owner.SaveData(saved);
                    var nbt = PersistenceNbtRoundtrip(saved);
                    if (checkFavorites)
                    {
                        Equal(false, nbt.GetList<string>("infiniJournalFavorites").Contains(Terraria.Main.worldID + ":removed"), "removed favorite cannot return from old claim");
                        Equal(true, nbt.GetList<string>("infiniJournalFavorites").Contains(Terraria.Main.worldID + ":added"), "new favorite survives active claim save");
                    }
                    else
                    {
                        Equal(0, nbt.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "delivered refund cannot return from old claim");
                        Equal(false, nbt.ContainsKey("infiniPendingCraftRefunds"), "claim-local legacy refund cannot overwrite live root refunds");
                    }
                    owner.Initialize(); owner.LoadData(nbt); owner.OnEnterWorld();
                    Equal(7, player.inventory.Take(58).Where(i => i.type == ItemID.Wood).Sum(i => i.stack), "repeated native save/load cannot deliver twice");
                    Equal(origin == current, !owner.InputA.IsAir, "only exact literal scope hydrates escrow mirror");
                    Equal(false, nbt.ContainsKey("foreignExtension"), "opaque claim fields cannot overwrite player root");
                }
                peers.Mode(NetmodeID.SinglePlayer, 0); owner.AbortTransientCraftForWorldExit();
                var parked = new TagCompound(); owner.SaveData(parked);
                Equal(true, PersistenceDormantClaims(PersistenceNbtRoundtrip(parked)).Any(c =>
                    c.GetString("infiniStationEscrowOriginScopeV1") == origin
                    && c.GetCompound("foreignExtension").GetString("literal") == "keep-nested"), "opaque claim fields survive reload and repark unchanged");
                Equal(0, player.inventory.Take(58).Where(i => i.type == ItemID.GoldBar).Sum(i => i.stack), "stale remote-claim refund never becomes local material");
            });
        }
        finally { world.ClearWorld(); }
    }
}
