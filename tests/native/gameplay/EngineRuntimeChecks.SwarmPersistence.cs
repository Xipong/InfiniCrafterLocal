using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags PersistenceStatic = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    private const BindingFlags PersistenceInstance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

    // Only the native built-in serializer is registered. SaveData/ItemIO/TagIO remain real.
    private static IDisposable WithPersistenceBoolSerializer()
    {
        var field = typeof(TagSerializer).GetField("serializers", PersistenceStatic)!;
        var serializers = (IDictionary<Type, TagSerializer>)field.GetValue(null)!;
        bool had = serializers.TryGetValue(typeof(bool), out TagSerializer? previous);
        if (!had)
            typeof(TagSerializer).GetMethod("AddSerializer", PersistenceStatic)!
                .Invoke(null, new object[] { new BoolTagSerializer() });
        return new PersistenceRestore(() => { if (had) serializers[typeof(bool)] = previous!; else serializers.Remove(typeof(bool)); });
    }

    private static TagCompound PersistenceNbtRoundtrip(TagCompound tag)
    {
        using var stream = new MemoryStream(); TagIO.ToStream(tag, stream, compress: false);
        using var input = new MemoryStream(stream.ToArray()); return TagIO.FromStream(input, compressed: false);
    }

    private sealed class PersistenceRestore(Action restore) : IDisposable
    {
        public void Dispose() => restore();
    }

    private static void RemoteEscrowMirrorNeverBecomesSinglePlayerMaterial()
    {
        using var serializer = WithPersistenceBoolSerializer();
        int oldMode = Terraria.Main.netMode;
        Item oldMouse = Terraria.Main.mouseItem;
        var world = new GeneratedStationEscrowStateSystem();
        try
        {
            foreach (string scope in new[] { "", new string('a', 32), new string('b', 32), new string('A', 32), "literal-old-origin" })
            {
                WithPlayer((player, loaded) =>
                {
                    loaded.Initialize();
                    foreach (var inventoryItem in player.inventory) inventoryItem.TurnToAir();
                    Terraria.Main.netMode = NetmodeID.SinglePlayer;
                    var oldClaim = new TagCompound {
                        ["infiniStationEscrowClientId"] = new string('c', 32),
                        ["infiniStationEscrowRemoteAuthority"] = true,
                        ["infiniStationEscrowOriginScopeV1"] = scope,
                        ["unknownClaimField"] = "literal-old-claim",
                        ["infiniStationEscrowMirror"] = new List<TagCompound> {
                            new() { ["index"] = 0, ["item"] = ItemIO.Save(new Item(ItemID.CopperShortsword, 1)) },
                        },
                    };
                    loaded.LoadData(PersistenceNbtRoundtrip(oldClaim));
                    Equal(true, loaded.InputA.IsAir, "unmatched/old remote mirror is not a material station slot");
                    loaded.ReturnStationInputs();
                    Equal(0, player.inventory.Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "remote mirror cannot refund in SP");
                    Terraria.Main.mouseItem = new Item(); Terraria.Main.mouseItem.TurnToAir();
                    Equal(false, loaded.TryTakeInputToMouse(0), "remote claim cannot become mouse material");
                    var save = new TagCompound(); loaded.SaveData(save);
                    var retained = save.GetCompound("infiniReadOnlyRemoteStationClaimV1");
                    Equal("literal-old-claim", retained.GetString("unknownClaimField"), "unknown old claim is retained raw");
                    Equal(scope, retained.GetString("infiniStationEscrowOriginScopeV1"), "origin is not guessed");
                    Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                    using var wire = new MemoryStream();
                    using (var writer = new BinaryWriter(wire, System.Text.Encoding.UTF8, true)) writer.Write(new string('a', 32));
                    wire.Position = 0; using var reader = new BinaryReader(wire); world.NetReceive(reader);
                    bool matched = loaded.EnsureRemoteStationAuthority();
                    Equal(true, matched, "foreign raw history does not disable fresh authority; only exact origin hydrates below");
                    Equal(scope != new string('a', 32), loaded.InputA.IsAir, "nonmatching/unknown origins remain read-only");
                    Terraria.Main.netMode = NetmodeID.SinglePlayer;
                    loaded.ReturnStationInputs();
                    Equal(false, loaded.TryTakeInputToMouse(0), "active remote mirror also refuses direct SP extraction");
                    Equal(0, player.inventory.Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "even an active known remote mirror cannot refund after netmode change");
                    loaded.AbortTransientCraftForWorldExit();
                    var exited = new TagCompound(); loaded.SaveData(exited);
                    Equal(0, exited.GetList<TagCompound>("infiniPendingCraftRefunds").Count, "world exit cannot save a remote mirror as local refundable material");
                    Equal(scope, PersistenceNbtRoundtrip(exited).GetCompound("infiniReadOnlyRemoteStationClaimV1").GetString("infiniStationEscrowOriginScopeV1"), "parked exact or unknown origin survives player serialization");
                });
            }
            WithPlayer((player, local) => {
                local.Initialize(); Terraria.Main.netMode = NetmodeID.SinglePlayer;
                foreach (var inventoryItem in player.inventory) inventoryItem.TurnToAir();
                local.InputA = new Item(ItemID.CopperShortsword, 1); local.ReturnStationInputs();
                Equal(1, player.inventory.Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "local SP material positive control");
            });
        }
        finally { world.ClearWorld(); Terraria.Main.netMode = oldMode; Terraria.Main.mouseItem = oldMouse; }
    }

    private static void WithPersistenceTilemap(Action<Player, GeneratedPlacementLedgerSystem> check)
    {
        var tileOwner = typeof(Player).Assembly.GetType("Terraria.TileData", true)!;
        uint originalLength = (uint)tileOwner.GetProperty("Length", PersistenceStatic)!.GetValue(null)!;
        // Tilemap is only an index view; TileData<T> owns process-static pinned arrays.
        // Snapshot each already-initialized backing owner before resizing it.
        var restoreArrays = new Dictionary<Type, Array>();
        var registered = tileOwner.GetField("OnSetLength", PersistenceStatic)!.GetValue(null) as Delegate;
        foreach (Delegate callback in registered?.GetInvocationList() ?? Array.Empty<Delegate>())
        {
            Type t = callback.Method.DeclaringType!;
            if (t.IsGenericType && t.GetGenericTypeDefinition().FullName == "Terraria.TileData`1")
                restoreArrays[t] = (Array)t.GetProperty("data", PersistenceStatic)!.GetValue(null)!;
        }
        var oldMap = Terraria.Main.tile; var players = Terraria.Main.player;
        int oldWidth = Terraria.Main.maxTilesX, oldHeight = Terraria.Main.maxTilesY, mode = Terraria.Main.netMode;
        ulong oldTick = Terraria.Main.GameUpdateCount;
        var ledger = new GeneratedPlacementLedgerSystem();
        try
        {
            Terraria.Main.maxTilesX = Terraria.Main.maxTilesY = 100;
            Terraria.Main.tile = (Tilemap)Activator.CreateInstance(typeof(Tilemap), PersistenceInstance, null, new object[] { (ushort)100, (ushort)100 }, null)!;
            Terraria.Main.player = new Player[Terraria.Main.maxPlayers];
            var player = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, position = new Microsoft.Xna.Framework.Vector2(640, 640) };
            Terraria.Main.netMode = NetmodeID.Server; ledger.ClearWorld(); check(player, ledger);
        }
        finally
        {
            ledger.ClearWorld(); tileOwner.GetMethod("SetLength", PersistenceStatic)!.Invoke(null, new object[] { originalLength });
            foreach (var pair in restoreArrays)
                Array.Copy(pair.Value, (Array)pair.Key.GetProperty("data", PersistenceStatic)!.GetValue(null)!, pair.Value.Length);
            Terraria.Main.tile = oldMap; Terraria.Main.player = players; Terraria.Main.maxTilesX = oldWidth; Terraria.Main.maxTilesY = oldHeight; Terraria.Main.netMode = mode; MaterialClock(oldTick);
        }
    }

    private static GeneratedItemData PersistencePlacementData(string id = "persistence-placement-witness")
    {
        var data = GeneratedItemData.Placeholder(); data.Id = id; data.SourceMode = "test_fixture";
        data.RuntimeProgram.ItemUse.Configured = true;
        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
            Id = "place", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec { StackCost = 1, Action = new RuntimeBindingActionSpec {
                Kind = RuntimeBindingAction.PlaceItem, TargetId = data.RuntimeProgram.ItemEntityId,
                Placement = new RuntimePlacementSpec { TileId = -1, WallId = 1, PlaceStyle = 0 },
            } },
        } };
        return data;
    }

    private static void NativePlacementIntentPrecedesMutationAndRejectsLateClaims()
    {
        WithPersistenceTilemap((player, ledger) =>
        {
            var data = PersistencePlacementData();
            var item = new Item(ItemID.WoodenSword, 1); var generated = new GeneratedItem();
            AttachItem(generated, item, data);
            Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is not null, "strict native placement fixture is valid");
            player.inventory[0] = item; player.selectedItem = 0;

            Tile cell = Terraria.Main.tile[40, 40]; cell.WallType = 0;
            ReceivePlacementPacket(true, 1); cell.WallType = 1; ReceivePlacementPacket(false, 1);
            Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "server-captured intent commits exact changed cell");
            var save = new TagCompound(); ledger.SaveWorldData(save);
            Equal(data.Id, save.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0].GetString("generatedItemId"), "identity comes from server-held generated item");
            ReceivePlacementPacket(false, 1); var repeated = new TagCompound(); ledger.SaveWorldData(repeated);
            Equal(1, repeated.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Count, "notify replay does not create another material return");
            // A late notify may not create a new authorization from after-state.
            ReceivePlacementPacket(false, 2, 41, 40);
            Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 41, 40), "late/unarmed notify cannot authorize");
            ReceivePlacementPacket(true, 2, int.MinValue, int.MaxValue); ReceivePlacementPacket(false, 2, int.MaxValue, int.MinValue);
            var wall = new GeneratedPlacementLedgerWall(); int dropType = 0;
            Equal(false, wall.Drop(40, 40, 1, ref dropType), "exact tracked wall suppresses vanilla fallback");
            var pending = new TagCompound(); ledger.SaveWorldData(pending);
            Equal(1, pending.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "stack-one exact return stays durable if content spawning unavailable");
            Equal(data.Id, pending.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2")[0].GetString("generatedItemId"), "return identity remains exact");
        });
    }

    private static void PlacementIntentRateReplayExpiryAndBeforeStateControls()
    {
        WithPersistenceTilemap((player, ledger) =>
        {
            var data = PersistencePlacementData(); player.inventory[0] = ReviewItem(data).Item;

            Tile cell = Terraria.Main.tile[40, 40];
            foreach (string scenario in new[] { "late", "notify_before_mutation", "unarmed", "already_placed", "expired", "rate_replay", "player_replaced", "bounds", "wrong_target" })
            {
                ledger.ClearWorld(); MaterialClock(100); Terraria.Main.player[0] = player; cell.WallType = 0;
                if (scenario is "unarmed" or "already_placed") cell.WallType = 1;
                if (scenario != "unarmed") ReceivePlacementPacket(true, 1);
                if (scenario == "notify_before_mutation") { ReceivePlacementPacket(false, 1); ledger.PostUpdateWorld(); }
                if (scenario == "late") MaterialClock(140);
                if (scenario == "expired") { MaterialClock(221); ledger.PostUpdateWorld(); }
                if (scenario == "rate_replay") { ReceivePlacementPacket(true, 2); ReceivePlacementPacket(true, 1); }
                if (scenario == "bounds") { ledger.ClearWorld(); ReceivePlacementPacket(true, 1, int.MinValue, int.MaxValue); ReceivePlacementPacket(false, 1, int.MaxValue, int.MinValue); }
                if (scenario == "player_replaced") Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, position = player.position };
                cell.WallType = 1;
                if (scenario == "wrong_target") { ReceivePlacementPacket(false, 1, 41); ReceivePlacementPacket(false, 1, layer: 1); }
                if (scenario == "rate_replay") ReceivePlacementPacket(false, 2);
                ReceivePlacementPacket(false, 1); ledger.PostUpdateWorld(); ReceivePlacementPacket(false, 1);
                bool accepted = scenario is "late" or "notify_before_mutation" or "rate_replay" or "wrong_target";
                Equal(accepted, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "bounded exact-before intent: " + scenario);
                var save = new TagCompound(); ledger.SaveWorldData(save);
                Equal(accepted ? 1 : 0, save.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Count, "no second material owner: " + scenario);
            }
        });
    }

    private static void PlacementClientWaitsForServerBeforeSnapshotAndSpendsOnce()
    {
        WithPersistenceTilemap((_, ledger) =>
        {
            // Existing CPU peer fixture calls real Mod.GetPacket/HandlePacket and
            // intercepts only socket Send. Ledger authorization maps are peer-local.
            using var peers = new ReviewPeers();
            int targetX = Player.tileTargetX, targetY = Player.tileTargetY;
            var authorizations = (System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem)
                .GetField("PendingAuthorizations", PersistenceStatic)!.GetValue(null)!;
            try
            {
                Player.tileTargetX = Player.tileTargetY = 40;
                var client = new Player { whoAmI = 0, active = true, position = new Microsoft.Xna.Framework.Vector2(640, 640) };
                var server = new Player { whoAmI = 0, active = true, position = client.position };
                var data = PersistencePlacementData();
                // This protocol observer starts with an already hydrated definition;
                // otherwise CanUseItem legitimately requests the registry as well.
                peers.Register(data);
                var generated = ReviewItem(data); client.inventory[0] = generated.Item;
                var serverData = GeneratedItemData.FromJson(data.ToNetworkJson())!;
                server.inventory[0] = ReviewItem(serverData).Item;
                peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client;
                Tile cell = Terraria.Main.tile[40, 40]; cell.WallType = 0;
                Equal(false, generated.CanUseItem(client), "client refuses vanilla use before server before-state fence");
                Equal(1, peers.Sent.Count, "one real intent packet");
                Equal(InfiniCrafterLocal.Common.InfiniNetPacketIds.RequestGeneratedPlacementIntent, peers.Sent[0][0], "intent packet routed by actual dispatcher");
                Equal(0, authorizations.Count, "client did not fake an authorization before ready");
                byte[] intent = peers.Sent[0]; peers.Sent.Clear();
                peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server; peers.Receive(intent, 0);
                Equal(1, authorizations.Count, "server captured native before-state from its held definition");
                object serverAuthorization = authorizations[0]!;
                Equal(1, peers.Sent.Count, "one ready response"); byte[] ready = peers.Sent[0]; peers.Sent.Clear();
                authorizations.Clear();
                peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client; peers.Receive(ready);
                Equal(true, generated.CanUseItem(client), "ready allows actual CanUseItem only after server snapshot");
                Equal(false, ItemLoader.ConsumeItem(generated.Item, client), "no native changed cell means no consumption");
                cell.WallType = 1; // Explicit native tile fixture, not WorldGen/socket proof.
                Equal(true, ItemLoader.ConsumeItem(generated.Item, client), "accepted native change spends stack one once");
                Equal(false, ItemLoader.ConsumeItem(generated.Item, client), "same receipt cannot spend twice");
                Equal(1, peers.Sent.Count, "one actual notify packet"); byte[] notify = peers.Sent[0]; peers.Sent.Clear();
                // Do not lend the client mirror group to the server ledger.
                ((System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("Groups", PersistenceStatic)!.GetValue(null)!).Clear();
                ((System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("Placements", PersistenceStatic)!.GetValue(null)!).Clear();
                authorizations[0] = serverAuthorization;
                peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server;
                MaterialClock(140); // Beyond the old 30-tick window, inside the fenced 120-tick intent window.
                peers.Receive(notify, 0); peers.Receive(notify, 0);
                Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "late notify finishes the original server before-state only");
                var save = new TagCompound(); ledger.SaveWorldData(save);
                Equal(1, save.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Count, "one server material owner, replay cannot duplicate");
                Equal(serverData.Id, save.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0].GetString("generatedItemId"), "server-held exact definition owns identity");
            }
            finally { Player.tileTargetX = targetX; Player.tileTargetY = targetY; }
        });
    }

    private static void LocalPlacementReceiptStillSpendsStackOneExactlyOnce()
    {
        WithPersistenceTilemap((player, ledger) =>
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            int x = Player.tileTargetX, y = Player.tileTargetY;
            try
            {
                Player.tileTargetX = Player.tileTargetY = 40;
                var data = PersistencePlacementData(); var item = new Item(ItemID.WoodenSword, 1); var generated = new GeneratedItem();
                AttachItem(generated, item, data);
                player.inventory[0] = item; player.selectedItem = 0;
                Tile cell = Terraria.Main.tile[40, 40]; cell.WallType = 0;
                Equal(true, generated.CanUseItem(player), "real local CanUseItem establishes before snapshot");
                Equal(false, ItemLoader.ConsumeItem(item, player), "no accepted native mutation means no spend");
                cell.WallType = 1;
                Equal(true, ItemLoader.ConsumeItem(item, player), "real accepted-placement gate spends stack one");
                Equal(false, ItemLoader.ConsumeItem(item, player), "same acceptance receipt is one-shot");
                Equal(1, item.stack, "gate observer does not pretend to execute vanilla stack arithmetic");
                int drop = 0; var wall = new GeneratedPlacementLedgerWall();
                Equal(false, wall.Drop(40, 40, 1, ref drop), "accepted generated wall always queues exact generated return, no chance roll");
                var save = new TagCompound(); ledger.SaveWorldData(save);
                Equal(1, save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "one exact pending return");
            }
            finally { Player.tileTargetX = x; Player.tileTargetY = y; }
        });
    }

    private static void ScopedRemoteEscrowResponseRequiresExactOrigin()
    {
        using var serializer = WithPersistenceBoolSerializer();
        var world = new GeneratedStationEscrowStateSystem();
        int mode = Terraria.Main.netMode, mine = Terraria.Main.myPlayer; var players = Terraria.Main.player;
        try
        {
            Terraria.Main.netMode = NetmodeID.Server; world.ClearWorld();
            var worldSave = new TagCompound(); world.SaveWorldData(worldSave);
            string scope = worldSave.GetString("infiniStationEscrowAuthorityScopeV1");
            Equal(32, scope.Length, "world mints an opaque authority token");
            world.LoadWorldData(PersistenceNbtRoundtrip(worldSave));
            Equal(true, GeneratedStationEscrowStateSystem.IsExactAuthorityScope(scope), "authority persists across world reload");
            WithPlayer((player, modPlayer) =>
            {
                Terraria.Main.player = new Player[Terraria.Main.maxPlayers]; Terraria.Main.player[0] = player; Terraria.Main.myPlayer = 0;
                player.whoAmI = 0; player.active = true; modPlayer.Initialize();
                foreach (var inventoryItem in player.inventory) inventoryItem.TurnToAir();
                Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                using var worldWire = new MemoryStream();
                using (var writer = new BinaryWriter(worldWire, System.Text.Encoding.UTF8, true)) world.NetSend(writer);
                world.ClearWorld(); worldWire.Position = 0; using (var reader = new BinaryReader(worldWire, System.Text.Encoding.UTF8, true)) world.NetReceive(reader);
                var claim = new TagCompound {
                    ["infiniStationEscrowClientId"] = new string('c', 32), ["infiniStationEscrowRemoteAuthority"] = true,
                    ["infiniStationEscrowOriginScopeV1"] = scope,
                    ["infiniStationEscrowMirror"] = new List<TagCompound> { new() { ["index"] = 0, ["item"] = ItemIO.Save(new Item(ItemID.CopperShortsword, 1)) } },
                    ["infiniPendingStationEscrow"] = new TagCompound { ["operationId"] = new string('d', 32), ["action"] = 3, ["index"] = 0 },
                };
                modPlayer.LoadData(claim); Equal(true, modPlayer.EnsureRemoteStationAuthority(), "same known authority restores remote work");
                void Response(string origin)
                {
                    using var wire = new MemoryStream();
                    using (var writer = new BinaryWriter(wire, System.Text.Encoding.UTF8, true)) {
                        writer.Write(3); writer.Write(origin); writer.Write(new string('d', 32)); writer.Write((byte)3);
                        writer.Write((sbyte)0); writer.Write(true); writer.Write("");
                    }
                    wire.Position = 0; using var reader = new BinaryReader(wire); InfiniCraftPlayer.HandleStationEscrowResultPacket(reader, 0);
                }
                int equipmentSends = 0;
                using var network = PersistenceObserveNetworkSend((message, slot) => {
                    Equal((int)MessageID.SyncEquipment, message, "attested return synchronizes native inventory");
                    Equal(0, slot, "attested return synchronizes exact delivered slot");
                    equipmentSends++;
                });
                Response(new string('e', 32));
                Equal(0, equipmentSends, "foreign origin cannot synchronize inventory");
                Equal(true, modPlayer.HasPendingStationEscrowOperation, "foreign origin cannot settle pending operation");
                Equal(0, player.inventory.Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "foreign authority cannot mint material");
                Response(scope); Response(scope);
                Equal(false, modPlayer.HasPendingStationEscrowOperation, "matching response settles once");
                Equal(1, player.inventory.Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "matching attested return applies once, replay rejected");
                Equal(1, equipmentSends, "matching return synchronizes once, replay rejected");
            });
        }
        finally { world.ClearWorld(); Terraria.Main.netMode = mode; Terraria.Main.myPlayer = mine; Terraria.Main.player = players; }
    }

    private static void PlacementQuarantineValidatedRequeueIsIdempotent()
    {
        using var serializer = WithPersistenceBoolSerializer();
        var ledger = new GeneratedPlacementLedgerSystem();
        int mode = Terraria.Main.netMode, width = Terraria.Main.maxTilesX, height = Terraria.Main.maxTilesY;
        Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.maxTilesX = Terraria.Main.maxTilesY = 100;
        try
        {
            var data = PersistencePlacementData("exact_return_id");
            InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
            string repaired = data.ToNetworkJson();
            Equal(true, GeneratedItemData.FromJson(repaired) is not null, "positive uses the real strict definition reader");
            ledger.LoadWorldData(new TagCompound { ["infiniGeneratedPlacementReturnsV2"] = new List<TagCompound> {
                new() { ["groupId"] = "quarantine-group", ["generatedItemId"] = data.Id, ["definitionJson"] = "{broken-original", ["x"] = 40, ["y"] = 40 },
            } });
            ledger.PostUpdateWorld();
            var wrong = PersistencePlacementData("other_return_id");
            InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(wrong);
            Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", wrong.ToNetworkJson()), "other generated identity cannot repair the claim");
            var inert = GeneratedItemData.Placeholder(); inert.Id = data.Id; inert.SourceMode = "test_fixture";
            InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(inert);
            Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", inert.ToNetworkJson()), "same-id inert proxy cannot repair a material placement");
            wrong.Id = data.Id; wrong.RecipeMeta.WorldId = "not-the-current-world";
            Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", wrong.ToNetworkJson()), "a different world cannot requeue the claim");
            Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", repaired), "validated exact identity can requeue");
            Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", repaired), "same requeue is idempotent");
            data.Name = "different replacement";
            Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", data.ToNetworkJson()), "changed payload is not an idempotent replay");
            var save = new TagCompound(); ledger.SaveWorldData(save);
            Equal(1, save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "one retry owner only");
            Equal("{broken-original", save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1")[0].GetCompound("claim").GetString("definitionJson"), "original forensic claim remains raw");
            ledger.LoadWorldData(PersistenceNbtRoundtrip(save));
            Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", repaired), "receipt survives reload without enqueuing twice");
            var after = new TagCompound(); ledger.SaveWorldData(after);
            Equal(1, after.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "reload replay cannot duplicate retry ownership");
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("quarantine-group", repaired), "client cannot requeue material");
        }
        finally { ledger.ClearWorld(); Terraria.Main.netMode = mode; Terraria.Main.maxTilesX = width; Terraria.Main.maxTilesY = height; }
    }

    private static void PermanentlyBrokenPlacementReturnSurvivesReload()
    {
        using var serializer = WithPersistenceBoolSerializer();
        var ledger = new GeneratedPlacementLedgerSystem();
        int oldMode = Terraria.Main.netMode, oldWidth = Terraria.Main.maxTilesX, oldHeight = Terraria.Main.maxTilesY;
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.maxTilesX = Terraria.Main.maxTilesY = 100;
        try
        {
            var wrongIdentity = PersistencePlacementData("different-native-id").ToNetworkJson();
            var inert = GeneratedItemData.Placeholder(); inert.Id = "broken-id"; inert.SourceMode = "test_fixture";
            foreach ((string id, string json, object x, string reason) in new (string, string, object, string)[] {
                ("broken-id", "{broken-json", 40, "definition_invalid"),
                ("broken-id", wrongIdentity, 40, "identity_mismatch"),
                ("broken-id", inert.ToNetworkJson(), 40, "definition_not_material_placement"),
                ("", "raw-nonempty-definition", 40, "claim_invalid"),
                ("broken-id", "{broken-json", -1, "claim_invalid"),
                ("broken-id", "{broken-json", "invalid coordinate", "claim_invalid"),
            })
            {
                var raw = new TagCompound { ["groupId"] = "broken-group", ["generatedItemId"] = id,
                    ["definitionJson"] = json, ["x"] = x, ["y"] = 40, ["unknownWitnessField"] = "keep-verbatim" };
                ledger.LoadWorldData(new TagCompound { ["infiniGeneratedPlacementReturnsV2"] = new List<TagCompound> { raw } });
                ledger.PostUpdateWorld();
                var save = new TagCompound(); ledger.SaveWorldData(save);
                var quarantine = save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1");
                Equal(1, quarantine.Count, "broken return remains durable");
                Equal(reason, quarantine[0].GetString("cause"), "stable diagnosed cause");
                Equal(json, quarantine[0].GetCompound("claim").GetString("definitionJson"), "original definition is not rewritten");
                Equal(id, quarantine[0].GetCompound("claim").GetString("generatedItemId"), "original identity is not guessed");
                Equal("keep-verbatim", quarantine[0].GetCompound("claim").GetString("unknownWitnessField"), "raw claim extensions survive");
                Equal(0, save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "quarantine does not retry per tick");
                ledger.LoadWorldData(PersistenceNbtRoundtrip(save)); ledger.PostUpdateWorld();
                var reloaded = new TagCompound(); ledger.SaveWorldData(reloaded);
                Equal(json, reloaded.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1")[0].GetCompound("claim").GetString("definitionJson"), "quarantine survives reload");
                Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("broken-group", "{still-invalid"), "invalid requeue cannot materialize a fallback");
                var material = PersistencePlacementData(id.Length == 0 ? "not-the-claim" : id);
                InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(material);
                if (reason == "claim_invalid")
                    Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("broken-group", material.ToNetworkJson()), "malformed claim cannot requeue even with a valid definition");
            }
        }
        finally { ledger.ClearWorld(); Terraria.Main.netMode = oldMode; Terraria.Main.maxTilesX = oldWidth; Terraria.Main.maxTilesY = oldHeight; }
    }

    private static void PersistenceReceiveScope(GeneratedStationEscrowStateSystem world, string scope)
    {
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) writer.Write(scope);
        stream.Position = 0; using var reader = new BinaryReader(stream); world.NetReceive(reader);
    }

    private static IEnumerable<TagCompound> PersistenceDormantClaims(TagCompound save)
    {
        if (save.ContainsKey("infiniReadOnlyRemoteStationClaimV1")) yield return save.GetCompound("infiniReadOnlyRemoteStationClaimV1");
        foreach (TagCompound claim in save.GetList<TagCompound>("infiniDormantRemoteStationClaimsV1")) yield return claim;
    }

    private static IDisposable PersistenceObserveNetworkSend(Action<int, int> observe)
    {
        Action<int, int, int, Terraria.Localization.NetworkText, int, float, float, float, int, int, int> send =
            (msg, remote, ignore, text, player, slot, a, b, c, d, e) => observe(msg, (int)slot);
        return new MonoMod.RuntimeDetour.Hook(typeof(NetMessage).GetMethod(nameof(NetMessage.SendData),
            new[] { typeof(int), typeof(int), typeof(int), typeof(Terraria.Localization.NetworkText), typeof(int),
                typeof(float), typeof(float), typeof(float), typeof(int), typeof(int), typeof(int) })!, send);
    }

    private static void PersistenceFinishDeposit(ReviewPeers peers, byte[] request, string scope)
    {
        using var reader = new BinaryReader(new MemoryStream(request));
        Equal(InfiniCrafterLocal.Common.InfiniNetPacketIds.RequestStationEscrow, reader.ReadByte(), "actual station request dispatcher id");
        Equal(3, reader.ReadInt32(), "scoped request version");
        Equal(scope, reader.ReadString(), "fresh request names only current authority, never dormant origin");
        reader.ReadString(); string operation = reader.ReadString(); byte action = reader.ReadByte(); sbyte index = reader.ReadSByte();
        Equal((byte)1, action, "one fresh deposit request");
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) {
            writer.Write(InfiniCrafterLocal.Common.InfiniNetPacketIds.StationEscrowResult);
            writer.Write(3); writer.Write(scope); writer.Write(operation); writer.Write(action); writer.Write(index); writer.Write(true); writer.Write("");
        }
        peers.Receive(stream.ToArray());
    }

    private static void EmptyLegacyRemoteMarkerDoesNotBrickFreshStationUse()
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers();
        var world = new GeneratedStationEscrowStateSystem(); Item oldMouse = Terraria.Main.mouseItem;
        try {
            PersistenceMatrix(new[] { "new", "legacy_empty", "foreign_empty" }.Select(scenario => (scenario, (Action)(() => {
                WithPlayer((player, modPlayer) => {
                    modPlayer.Initialize(); player.whoAmI = 0; player.active = true;
                    foreach (Item item in player.inventory) item.TurnToAir();
                    Terraria.Main.player[0] = player; peers.Mode(NetmodeID.MultiplayerClient, 0); peers.Sent.Clear();
                    string current = new string('b', 32);
                    var claim = new TagCompound { ["infiniStationEscrowClientId"] = new string('c', 32),
                        ["infiniStationEscrowRemoteAuthority"] = true, ["infiniStationEscrowMirror"] = new List<TagCompound>() };
                    if (scenario == "foreign_empty") claim["infiniStationEscrowOriginScopeV1"] = new string('a', 32);
                    if (scenario != "new") modPlayer.LoadData(PersistenceNbtRoundtrip(claim));
                    PersistenceReceiveScope(world, current);
                    int sends = 0;
                    using var network = PersistenceObserveNetworkSend((msg, slot) => {
                        Equal((int)MessageID.SyncEquipment, msg, "native cursor equipment sync"); Equal(58, slot, "exact cursor slot"); sends++;
                    });
                    for (int round = 0; round < 2; round++) {
                        Terraria.Main.mouseItem = new Item(ItemID.CopperShortsword, 1);
                        Equal(true, modPlayer.TryPutMouseItemIntoInput(round), "fresh actual TryPut succeeds for " + scenario);
                        Equal(true, Terraria.Main.mouseItem.IsAir, "only fresh cursor unit moved");
                        Equal(ItemID.CopperShortsword, modPlayer.StationInput(round).type, "fresh unit remains exact");
                        Equal(1, peers.Sent.Count, "one real fresh scoped request only");
                        PersistenceFinishDeposit(peers, peers.Sent[0], current); peers.Sent.Clear();
                        Equal(false, modPlayer.HasPendingStationEscrowOperation, "matching deposit result settles");
                        var save = new TagCompound(); modPlayer.SaveData(save);
                        modPlayer.Initialize(); modPlayer.LoadData(PersistenceNbtRoundtrip(save));
                        Equal(true, modPlayer.EnsureRemoteStationAuthority(), "fresh authority remains usable after native save/reload");
                    }
                    Equal(2, sends, "one native cursor sync per fresh unit");
                    Equal(0, player.inventory.Take(58).Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "empty history cannot mint refund material");
                });
            }))));
        }
        finally { world.ClearWorld(); Terraria.Main.mouseItem = oldMouse; }
    }

    private static void ForeignDormantClaimDoesNotBecomeCurrentAuthorityOrBlockFreshInputs()
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers(); var world = new GeneratedStationEscrowStateSystem(); Item oldMouse = Terraria.Main.mouseItem;
        try {
            PersistenceMatrix((from origin in new[] { "", new string('a', 32), new string('A', 32) }
                from material in new[] { false, true }
                select ("dormant origin '" + origin + "' material=" + material, (Action)(() => {
                WithPlayer((player, modPlayer) => {
                    modPlayer.Initialize(); player.whoAmI = 0; player.active = true;
                    foreach (Item item in player.inventory) item.TurnToAir();
                    Terraria.Main.player[0] = player; peers.Mode(NetmodeID.MultiplayerClient, 0); peers.Sent.Clear();
                    string a = new string('a', 32), b = new string('b', 32);
                    var old = new TagCompound { ["infiniStationEscrowClientId"] = new string('c', 32),
                        ["infiniStationEscrowRemoteAuthority"] = true, ["infiniStationEscrowOriginScopeV1"] = origin,
                        ["unknownClaimField"] = "literal-A-claim",
                        ["infiniStationEscrowMirror"] = material ? new List<TagCompound> { new() { ["index"] = 0, ["item"] = ItemIO.Save(new Item(ItemID.CopperShortsword, 1)) } } : new List<TagCompound>(),
                    };
                    if (material) old["infiniPendingStationEscrow"] = new TagCompound { ["operationId"] = new string('d', 32), ["action"] = 3, ["index"] = 0 };
                    string literal = PersistenceRawBytes(old);
                    modPlayer.LoadData(PersistenceNbtRoundtrip(old)); PersistenceReceiveScope(world, b);
                    Equal(true, modPlayer.EnsureRemoteStationAuthority(), "unrelated current world remains usable without hydrating foreign claim");
                    Equal(true, modPlayer.InputA.IsAir, "foreign/unscoped material never enters live slots");
                    using var network = PersistenceObserveNetworkSend((_, __) => { });
                    Terraria.Main.mouseItem = new Item(ItemID.WoodenSword, 1);
                    Equal(true, modPlayer.TryPutMouseItemIntoInput(0), "actual fresh B deposit is independent of dormant A");
                    Equal(ItemID.WoodenSword, modPlayer.InputA.type, "only fresh B material is projected");
                    Equal(1, peers.Sent.Count, "no old A operation/cancel sent to B");
                    PersistenceFinishDeposit(peers, peers.Sent[0], b); peers.Sent.Clear();
                    for (int round = 0; round < 3; round++) {
                        var save = new TagCompound(); modPlayer.SaveData(save);
                        Equal(true, PersistenceDormantClaims(save).Any(c => PersistenceRawBytes(c) == literal), "old complete raw claim retained without guessed token or overwrite");
                        modPlayer.Initialize(); modPlayer.LoadData(PersistenceNbtRoundtrip(save));
                        Equal(true, modPlayer.EnsureRemoteStationAuthority(), "B live authority restores beside unchanged A history");
                        Equal(ItemID.WoodenSword, modPlayer.InputA.type, "B restore never merges A copper");
                    }
                    peers.Mode(NetmodeID.SinglePlayer, 0); modPlayer.AbortTransientCraftForWorldExit();
                    var exited = new TagCompound(); modPlayer.SaveData(exited);
                    var dormant = PersistenceDormantClaims(exited).ToArray();
                    Equal(true, dormant.Any(c => PersistenceRawBytes(c) == literal), "parking B never overwrites A");
                    Equal(true, dormant.Any(c => c.GetString("infiniStationEscrowOriginScopeV1") == b && c.GetList<TagCompound>("infiniStationEscrowMirror").Count == 1), "B material remains separately scoped remote claim");
                    Equal(0, player.inventory.Take(58).Sum(i => i.type == ItemID.CopperShortsword || i.type == ItemID.WoodenSword ? i.stack : 0), "world exit has no remote material refund");
                    modPlayer.Initialize(); modPlayer.LoadData(PersistenceNbtRoundtrip(exited)); peers.Mode(NetmodeID.MultiplayerClient, 0); PersistenceReceiveScope(world, a);
                    Equal(true, modPlayer.EnsureRemoteStationAuthority(), "fresh A or exact A restore is reachable");
                    Equal(origin == a && material, !modPlayer.InputA.IsAir, "only literal exact A can restore A mirror");
                    if (origin == a && material) Equal(ItemID.CopperShortsword, modPlayer.InputA.type, "A mirror identity exact; no B material");
                    Equal(0, peers.Sent.Count, "no foreign history replay/cancel on scope change");
                    peers.Mode(NetmodeID.SinglePlayer, 0); modPlayer.AbortTransientCraftForWorldExit();
                    var final = new TagCompound(); modPlayer.SaveData(final);
                    Equal(true, PersistenceDormantClaims(final).Any(c => c.ContainsKey("unknownClaimField") && c.GetString("unknownClaimField") == "literal-A-claim" && c.GetString("infiniStationEscrowOriginScopeV1") == origin), "literal unknown extension survives exact restore/repark too");
                });
            }))));
        }
        finally { world.ClearWorld(); Terraria.Main.mouseItem = oldMouse; }
    }


    private delegate void PersistenceNativeStartOriginal(Player player, Item item);
    private delegate void PersistenceNativeStartObserver(PersistenceNativeStartOriginal original, Player player, Item item);

    private static byte[] PersistencePlacementNotify(ulong sequence, int x, int y, byte layer = 2)
        => PlacementPacket(false, sequence, x, y, layer, includePacketId: true);

    private static string PersistenceRawBytes(TagCompound tag)
    {
        using var stream = new MemoryStream(); TagIO.ToStream(tag, stream, compress: false);
        return Convert.ToBase64String(stream.ToArray());
    }

    private static void PersistenceMatrix(IEnumerable<(string Name, Action Case)> cases)
    {
        var failures = new List<string>();
        foreach (var (name, check) in cases)
        {
            try { check(); Console.WriteLine("PERSISTENCE-CASE PASS: " + name); }
            catch (Exception error) {
                failures.Add(name + ": " + error);
                Console.WriteLine("PERSISTENCE-CASE FAIL: " + name + ": " + error);
            }
        }
        Equal(0, failures.Count, string.Join("\n", failures));
    }

}
