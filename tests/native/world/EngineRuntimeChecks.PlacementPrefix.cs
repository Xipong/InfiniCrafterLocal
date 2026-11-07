using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData PlacementPrefixData()
    {
        var data = GeneratedPrefixFixture();
        data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Concat(new[] {
            new RuntimeBindingSpec {
                Id = "place", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec { StackCost = 1, Action = new RuntimeBindingActionSpec {
                    Kind = RuntimeBindingAction.PlaceItem, TargetId = data.RuntimeProgram.ItemEntityId,
                    Placement = new RuntimePlacementSpec { TileId = -1, WallId = 1, PlaceStyle = 0 },
                } },
            },
        }).ToArray();
        GeneratedItemRegistryService.StampCurrentWorld(data);
        return data;
    }

    private static byte[] PlacementPrefixIntent(ReviewPeers peers, GeneratedItem clientItem, Player serverPlayer)
    {
        int x = Player.tileTargetX, y = Player.tileTargetY;
        try
        {
            var client = new Player { whoAmI = 0, active = true, position = serverPlayer.position, altFunctionUse = 2 };
            client.inventory[0] = clientItem.Item; client.selectedItem = 0;
            Player.tileTargetX = Player.tileTargetY = 40;
            peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client; peers.Sent.Clear();
            Equal(false, GeneratedPlacementLedgerSystem.PreparePlacement(client, clientItem.Data,
                clientItem.Data.RuntimeProgram.Bindings[1].UsePolicy.Action.Placement!), "real client intent waits for server authority");
            return peers.Sent.Single();
        }
        finally
        {
            Player.tileTargetX = x; Player.tileTargetY = y;
            peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = serverPlayer;
        }
    }

    private static void PlacementPrefixServerSnapshotSurvivesEscrowSaveAndReturn()
    {
        WithGeneratedPrefixScope(() => WithPersistenceTilemap((player, ledger) =>
        {
            using var serializer = WithPersistenceBoolSerializer();
            using var peers = new ReviewPeers();
            foreach (int prefix in new[] { 0, (int)PrefixID.Legendary, (int)PrefixID.Broken, (int)PrefixID.Zealous })
            {
                ledger.ClearWorld(); peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = player;
                MaterialClock(100); Terraria.Main.tile[40, 40].WallType = 0;
                var data = PlacementPrefixData();
                var source = GeneratedPrefixHost(data);
                if (prefix != 0) Equal(true, source.Item.Prefix(prefix), "native prefix positive control");
                string expected = GeneratedPrefixStats(source.Item);
                // Exercise the real station's clone/restore seam before placement.
                WithPlayer((_, station) =>
                {
                    station.Initialize(); station.InputA = source.Item;
                    station.RestoreServerStationEscrowSlots(station.SnapshotServerStationEscrowSlots());
                    source = (GeneratedItem)station.InputA.ModItem;
                });
                data = source.Data;
                Equal(expected, GeneratedPrefixStats(source.Item), "escrow keeps native prefix instance state");
                var clientCopy = GeneratedPrefixHost(data);
                int clientPrefix = prefix == PrefixID.Broken ? PrefixID.Legendary : PrefixID.Broken;
                Equal(true, clientCopy.Item.Prefix(clientPrefix), "client uses same definition with a different prefix");
                player.inventory[0] = source.Item; player.selectedItem = 0;
                string canonical = data.ToNetworkJson();
                peers.Receive(PlacementPrefixIntent(peers, clientCopy, player), 0);
                // Vanilla can consume the last source stack before delayed notify.
                source.Item.TurnToAir(); Terraria.Main.tile[40, 40].WallType = 1;
                peers.Receive(PersistencePlacementNotify(1, 40, 40), 0);
                var saved = new TagCompound(); ledger.SaveWorldData(saved);
                TagCompound group = saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single();
                Equal(prefix, group.GetCompound("nativePrefix").GetInt("infiniNativePrefix"), "server-held snapshot, never client prefix or consumed item");
                Equal(canonical, group.GetString("definitionJson"), "instance prefix stays outside canonical definition");
                ledger.LoadWorldData(PersistenceNbtRoundtrip(saved));
                // Deliberately unavailable native allocation keeps the real return
                // claim durable. This is not a successful world-spawn simulation.
                Item[] priorItems = Terraria.Main.item;
                try
                {
                    Terraria.Main.item = Array.Empty<Item>();
                    Equal(true, GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Wall, 40, 40), "break queues the exact material owner");
                }
                finally { Terraria.Main.item = priorItems; }
                var pending = new TagCompound(); ledger.SaveWorldData(pending);
                ledger.LoadWorldData(PersistenceNbtRoundtrip(pending));
                var reloaded = new TagCompound(); ledger.SaveWorldData(reloaded);
                TagCompound claim = reloaded.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Single();
                int retained = GeneratedItem.ResolvePlacementPrefix(claim.GetCompound("nativePrefix"));
                var restored = GeneratedPrefixHost(data);
                Equal(true, restored.RestorePlacementPrefix(retained), "real return-prefix application seam accepts exact native token");
                Equal(expected, GeneratedPrefixStats(restored.Item), "returned native stats exactly match before placement");
                Equal(true, restored.RestorePlacementPrefix(retained), "repeated restore is idempotent");
                Equal(expected, GeneratedPrefixStats(restored.Item), "prefix stats are never multiplied twice");
            }
        }));
    }

    private static void PlacementPrefixMalformedIdentityIsDurableAndLegacyIsUnprefixed()
    {
        WithGeneratedPrefixScope(() => WithPersistenceTilemap((_, ledger) =>
        {
            using var serializer = WithPersistenceBoolSerializer();
            var data = PlacementPrefixData(); string json = data.ToNetworkJson();
            TagCompound Row(object? prefix) {
                var row = new TagCompound {
                    ["groupId"] = new string('a', 32), ["generatedItemId"] = data.Id, ["definitionJson"] = json,
                    ["cells"] = new List<TagCompound> { new() { ["layer"] = 2, ["x"] = 40, ["y"] = 40 } },
                };
                if (prefix is not null) row["nativePrefix"] = prefix;
                return row;
            }
            var legacy = Row(null);
            ledger.LoadWorldData(new TagCompound { ["infiniGeneratedPlacementLedgerV2"] = new List<TagCompound> { legacy } });
            var saved = new TagCompound(); ledger.SaveWorldData(saved);
            Equal(false, saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single().ContainsKey("nativePrefix"), "legacy absence stays literal");
            var unprefixed = GeneratedPrefixHost(data);
            unprefixed.Item.Prefix(PrefixID.Legendary);
            Equal(true, unprefixed.RestorePlacementPrefix(GeneratedItem.ResolvePlacementPrefix(null)), "legacy means exact prefix zero");
            Equal(0, (int)unprefixed.Item.prefix, "legacy restoration never rolls a replacement");
            var incompatible = GeneratedPrefixHost(GeneratedItemData.Placeholder());
            Equal(false, incompatible.RestorePlacementPrefix(PrefixID.Legendary), "native refusal is observable, never a forced token or reroll");
            Equal(0, (int)incompatible.Item.prefix, "refused prefix remains unclaimed");
            var bad = new object[] {
                "literal-bad-prefix", new TagCompound(),
                new TagCompound { ["infiniNativePrefix"] = -1 },
                new TagCompound { ["infiniNativePrefix"] = int.MaxValue },
                new TagCompound { ["infiniNativePrefix"] = (int)PrefixID.Count },
                new TagCompound { ["infiniNativePrefix"] = "wrong-type", ["infiniNativePrefixMod"] = "MissingMod", ["infiniNativePrefixName"] = "Prefix" },
                new TagCompound { ["infiniNativePrefix"] = (int)PrefixID.Count, ["infiniNativePrefixMod"] = "MissingMod" },
                new TagCompound { ["infiniNativePrefix"] = (int)PrefixID.Count, ["infiniNativePrefixMod"] = "MissingMod", ["infiniNativePrefixName"] = "Prefix" },
            };
            foreach (object identity in bad)
            {
                TagCompound row = Row(identity);
                string literal = PersistenceRawBytes(new TagCompound { ["nativePrefix"] = identity });
                ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementLedgerV2"] = new List<TagCompound> { row } }));
                Equal(true, GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Wall, 40, 40), "invalid prefix still retains material ownership");
                ledger.PostUpdateWorld();
                for (int round = 0; round < 2; round++)
                {
                    var quarantine = new TagCompound(); ledger.SaveWorldData(quarantine);
                    TagCompound envelope = quarantine.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1").Single();
                    Equal("prefix_identity_invalid", envelope.GetString("cause"), "specific refusal, never silent downgrade");
                    Equal(literal, PersistenceRawBytes(new TagCompound { ["nativePrefix"] = envelope.GetCompound("claim")["nativePrefix"] }), "malformed prefix retained literally");
                    Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn(new string('a', 32), json), "definition-only repair cannot replace invalid instance identity");
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(quarantine));
                }
            }
        }));
    }
}
