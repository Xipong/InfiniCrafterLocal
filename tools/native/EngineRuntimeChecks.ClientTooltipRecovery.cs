using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void ClientTooltipCorruptSaveCancellationRecovery()
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers();
        // No render loop: fill visual notification slots while executing the real result handler.
        Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
        var world = new GeneratedStationEscrowStateSystem();
        try
        {
            for (int lane = 0; lane < 3; lane++)
            {
                peers.Mode(NetmodeID.Server, 255); world.ClearWorld();
                using (var writer = new BinaryWriter(new MemoryStream())) world.NetSend(writer);
                string scope = GeneratedStationEscrowStateSystem.AuthorityScope;
                string token = new string('a', 32), requestId = new string((char)('b' + lane), 32);
                WithPlayer((serverPlayer, server) => {
                    EscrowBind(serverPlayer, server, token, 0);
                    var first = typeof(InfiniCraftPlayer).GetField("Input" + (char)('A' + lane * 2))!;
                    var second = typeof(InfiniCraftPlayer).GetField("Input" + (char)('B' + lane * 2))!;
                    first.SetValue(server, new Item(ItemID.CopperShortsword, 1));
                    second.SetValue(server, new Item(ItemID.Wood, 1));
                    GeneratedStationEscrowStateSystem.CaptureOwnerState(token, server);
                    WithPlayer((clientPlayer, client) => {
                        client.Initialize(); clientPlayer.active = true; clientPlayer.whoAmI = 1; Terraria.Main.player[1] = clientPlayer;
                        var request = new GeneratorClient.PreparedGenerationRequest {
                            RefundA = new Item(ItemID.CopperShortsword, 1), RefundB = new Item(ItemID.Wood, 1),
                            ClientTooltipA = new ClientTooltipObservation(new[] { "original" }, "en-US"),
                        };
                        var rows = new List<TagCompound>();
                        typeof(InfiniCraftPlayer).GetMethod("AddPendingRemoteCraftTag", PersistenceInstance)!.Invoke(client, new object[] { rows, lane, requestId, request });
                        rows[0]["clientTooltipA"] = new byte[] { 1 }; // A damaged optional observation, not lost material ownership.
                        typeof(InfiniCraftPlayer).GetMethod("RestorePendingRemoteCrafts", PersistenceInstance)!.Invoke(client, new object[] { rows });
                        typeof(InfiniCraftPlayer).GetField("_stationEscrowClientId", PersistenceInstance)!.SetValue(client, token);
                        typeof(InfiniCraftPlayer).GetField("_stationEscrowOriginScope", PersistenceInstance)!.SetValue(client, scope);
                        Equal(true, client.IsCraftLanePending(lane), "damaged save retains pending lane until authority resolves it");
                        Equal(false, GeneratedStationEscrowStateSystem.IsCraftPending(token, requestId), "initial craft packet never reached server");
                        peers.Mode(NetmodeID.MultiplayerClient, 1); peers.Sent.Clear();
                        typeof(InfiniCraftPlayer).GetMethod("ResendPendingRemoteCrafts", PersistenceInstance)!.Invoke(client, null);
                        Equal(1, peers.Sent.Count, "restored corrupt observation sends one cancellation");
                        byte[] cancel = peers.Sent.Single();
                        void ReceiveCancel(byte[] packet, int sender = 0)
                        {
                            peers.Mode(NetmodeID.Server, 255); peers.Sent.Clear();
                            using var reader = new BinaryReader(new MemoryStream(packet));
                            Equal(InfiniNetPacketIds.CancelServerCraft, reader.ReadByte(), "actual cancel sender opcode");
                            InfiniCraftPlayer.HandleCancelServerCraftPacket(reader, sender);
                        }
                        ReceiveCancel(cancel, sender: 1);
                        Equal(0, peers.Sent.Count, "another live session cannot cancel the owner request");
                        Equal(false, GeneratedStationEscrowStateSystem.TryReplayCraft(token, requestId, out _), "foreign session leaves no tombstone");
                        var wrongLane = (byte[])cancel.Clone();
                        using (var inspect = new BinaryReader(new MemoryStream(cancel))) {
                            inspect.ReadByte(); inspect.ReadInt32(); inspect.ReadString(); inspect.ReadString(); inspect.ReadString(); inspect.ReadString();
                            if (inspect.BaseStream.Position < inspect.BaseStream.Length)
                                wrongLane[inspect.BaseStream.Position] = (byte)((lane + 1) % 3);
                        }
                        ReceiveCancel(wrongLane);
                        Equal(0, peers.Sent.Count, "wrong lane escrow cannot create cancellation authority");
                        Equal(false, GeneratedStationEscrowStateSystem.TryReplayCraft(token, requestId, out _), "mismatched escrow leaves no tombstone");
                        ReceiveCancel(cancel);
                        Equal(1, peers.Sent.Count, "unknown request cancellation returns a terminal authority result");
                        byte[] result = peers.Sent.Single();
                        Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(token, requestId, out var outcome), "cancel leaves durable tombstone");
                        Equal(false, outcome.Success, "unknown cancelled request cannot become successful");
                        Equal(false, GeneratedStationEscrowStateSystem.IsCraftPending(token, requestId), "cancel tombstone is terminal");
                        Equal(ItemID.CopperShortsword, ((Item)first.GetValue(server)!).type, "server input A retained");
                        Equal(ItemID.Wood, ((Item)second.GetValue(server)!).type, "server input B retained");
                        Equal(1, ((Item)first.GetValue(server)!).stack, "server input A count unchanged");
                        Equal(1, ((Item)second.GetValue(server)!).stack, "server input B count unchanged");
                        var nextCancel = (byte[])cancel.Clone();
                        string nextRequestId = new string('f', 32);
                        using (var inspect = new BinaryReader(new MemoryStream(cancel))) {
                            inspect.ReadByte(); inspect.ReadInt32(); inspect.ReadString(); inspect.ReadString(); inspect.ReadString();
                            System.Text.Encoding.UTF8.GetBytes(nextRequestId).CopyTo(nextCancel, (int)inspect.BaseStream.Position - 32);
                        }
                        ReceiveCancel(nextCancel);
                        Equal(0, peers.Sent.Count, "fresh recovery in same lane/tick is deferred before journal allocation");
                        Equal(false, GeneratedStationEscrowStateSystem.TryReplayCraft(token, nextRequestId, out _), "rate-limited recovery creates no terminal entry");
                        Equal(false, GeneratedStationEscrowStateSystem.IsCraftPending(token, nextRequestId), "rate-limited recovery creates no pending entry");
                        serverPlayer.active = false;
                        try {
                            WithPlayer((replacementPlayer, replacement) => {
                                replacement.Initialize(); replacementPlayer.active = true; replacementPlayer.whoAmI = 0;
                                Terraria.Main.player[0] = replacementPlayer;
                                try {
                                    ReceiveCancel(nextCancel);
                                    Equal(0, peers.Sent.Count, "session rebind cannot reset the owner recovery cooldown");
                                    Equal(true, GeneratedStationEscrowStateSystem.IsBoundOwner(token, replacement), "reconnect restores the same durable owner");
                                }
                                finally { replacementPlayer.active = false; }
                            });
                        }
                        finally { serverPlayer.active = true; Terraria.Main.player[0] = serverPlayer; }
                        ReceiveCancel(cancel);
                        Equal(1, peers.Sent.Count, "same-id retry bypasses new-entry cooldown");
                        Equal(true, result.SequenceEqual(peers.Sent.Single()), "same-id replay stays exact during cooldown");
                        MaterialClock(Terraria.Main.GameUpdateCount + 59);
                        ReceiveCancel(nextCancel);
                        Equal(0, peers.Sent.Count, "cooldown lasts the full sixty ticks");
                        MaterialClock(Terraria.Main.GameUpdateCount + 1);
                        ReceiveCancel(nextCancel);
                        Equal(1, peers.Sent.Count, "next legitimate recovery succeeds after sixty ticks");
                        Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(token, nextRequestId, out var nextOutcome) && !nextOutcome.Success, "later recovery also has a durable cancellation outcome");
                        var savedWorld = new TagCompound();
                        world.SaveWorldData(savedWorld);
                        world.ClearWorld();
                        world.LoadWorldData(savedWorld);
                        Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(token, requestId, out var restoredOutcome), "cancel tombstone survives world reload");
                        Equal(false, restoredOutcome.Success, "reloaded tombstone remains cancelled");
                        ReceiveCancel(cancel);
                        Equal(1, peers.Sent.Count, "cancel retry returns exactly one result");
                        Equal(true, result.SequenceEqual(peers.Sent.Single()), "cancel retry has identical terminal outcome");
                        // A late initial request must replay the cancellation before even reading its optional observation.
                        using (var bytes = new MemoryStream()) {
                            using (var writer = new BinaryWriter(bytes, System.Text.Encoding.UTF8, true)) {
                                writer.Write(3); writer.Write(scope); writer.Write(token); writer.Write(requestId); writer.Write((byte)lane);
                                foreach (int type in new[] { ItemID.CopperShortsword, ItemID.Wood }) {
                                    writer.Write(type); writer.Write(0); writer.Write(1); writer.Write(""); writer.Write("");
                                }
                                writer.Write((byte)1); // Interrupted observation bytes cannot override the journal result.
                            }
                            peers.Sent.Clear(); bytes.Position = 0;
                            InfiniCraftPlayer.HandleRequestServerCraftPacket(new BinaryReader(bytes), 0);
                            Equal(1, peers.Sent.Count, "late initial request replays terminal cancellation");
                            Equal(true, result.SequenceEqual(peers.Sent.Single()), "malformed replay cannot change terminal result");
                        }
                        peers.Mode(NetmodeID.MultiplayerClient, 1); Terraria.Main.dedServ = true;
                        using (var reader = new BinaryReader(new MemoryStream(result))) {
                            Equal(InfiniNetPacketIds.CraftCommitResult, reader.ReadByte(), "actual terminal result opcode");
                            InfiniCraftPlayer.HandleCraftCommitResultPacket(reader, 255);
                        }
                        Equal(false, client.IsCraftLanePending(lane), "authority result clears restored pending lane");
                        Equal(ItemID.CopperShortsword, ((Item)first.GetValue(client)!).type, "client retains only station mirror A");
                        Equal(ItemID.Wood, ((Item)second.GetValue(client)!).type, "client retains only station mirror B");
                        Equal(0, serverPlayer.inventory.Take(58).Count(x => !x.IsAir), "server cancellation creates no inventory refund");
                        Equal(0, clientPlayer.inventory.Take(58).Count(x => !x.IsAir), "client cancellation creates no inventory refund");
                        Equal(false, GeneratedStationEscrowStateSystem.TryBeginCraft(token, requestId, lane), "late admission cannot reuse cancelled request id");
                    });
                });
            }
        }
        finally { world.ClearWorld(); }
    }
}
