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
            typeof(ModType<Item>).GetProperty("Entity", PersistenceInstance)!.SetValue(generated, item);
            typeof(Item).GetProperty("ModItem", PersistenceInstance)!.SetValue(item, generated);
            typeof(GeneratedItem).GetProperty("Data", PersistenceInstance)!.SetValue(generated, data);
            Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is not null, "strict native placement fixture is valid");
            player.inventory[0] = item; player.selectedItem = 0;
            void Packet(bool intent, ulong sequence, int x = 40, int y = 40)
            {
                using var stream = new MemoryStream();
                using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                {
                    writer.Write((int)typeof(GeneratedPlacementLedgerSystem).GetField("PlacementProtocolVersion", PersistenceStatic)!.GetRawConstantValue()!); writer.Write(sequence);
                    writer.Write((byte)(intent ? 0 : 2)); writer.Write(x); writer.Write(y);
                    if (intent) writer.Write(0UL);
                }
                stream.Position = 0; using var reader = new BinaryReader(stream);
                if (intent) GeneratedPlacementLedgerSystem.HandlePlacementIntentPacket(reader, 0);
                else GeneratedPlacementLedgerSystem.HandlePlacementPacket(reader, 0);
            }
            Tile cell = Terraria.Main.tile[40, 40]; cell.WallType = 0;
            Packet(true, 1); cell.WallType = 1; Packet(false, 1);
            Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "server-captured intent commits exact changed cell");
            var save = new TagCompound(); ledger.SaveWorldData(save);
            Equal(data.Id, save.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0].GetString("generatedItemId"), "identity comes from server-held generated item");
            Packet(false, 1); var repeated = new TagCompound(); ledger.SaveWorldData(repeated);
            Equal(1, repeated.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Count, "notify replay does not create another material return");
            // A late notify may not create a new authorization from after-state.
            Packet(false, 2, 41, 40);
            Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 41, 40), "late/unarmed notify cannot authorize");
            Packet(true, 2, int.MinValue, int.MaxValue); Packet(false, 2, int.MaxValue, int.MinValue);
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
            void Packet(bool intent, ulong sequence, int x = 40, int y = 40, byte layer = 2)
            {
                using var stream = new MemoryStream();
                using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) {
                    writer.Write((int)typeof(GeneratedPlacementLedgerSystem).GetField("PlacementProtocolVersion", PersistenceStatic)!.GetRawConstantValue()!); writer.Write(sequence); writer.Write(intent ? (byte)0 : layer); writer.Write(x); writer.Write(y);
                    if (intent) writer.Write(0UL);
                }
                stream.Position = 0; using var reader = new BinaryReader(stream);
                if (intent) GeneratedPlacementLedgerSystem.HandlePlacementIntentPacket(reader, 0);
                else GeneratedPlacementLedgerSystem.HandlePlacementPacket(reader, 0);
            }
            Tile cell = Terraria.Main.tile[40, 40];
            foreach (string scenario in new[] { "late", "notify_before_mutation", "unarmed", "already_placed", "expired", "rate_replay", "player_replaced", "bounds", "wrong_target" })
            {
                ledger.ClearWorld(); MaterialClock(100); Terraria.Main.player[0] = player; cell.WallType = 0;
                if (scenario is "unarmed" or "already_placed") cell.WallType = 1;
                if (scenario != "unarmed") Packet(true, 1);
                if (scenario == "notify_before_mutation") { Packet(false, 1); ledger.PostUpdateWorld(); }
                if (scenario == "late") MaterialClock(140);
                if (scenario == "expired") { MaterialClock(221); ledger.PostUpdateWorld(); }
                if (scenario == "rate_replay") { Packet(true, 2); Packet(true, 1); }
                if (scenario == "bounds") { ledger.ClearWorld(); Packet(true, 1, int.MinValue, int.MaxValue); Packet(false, 1, int.MaxValue, int.MinValue); }
                if (scenario == "player_replaced") Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, position = player.position };
                cell.WallType = 1;
                if (scenario == "wrong_target") { Packet(false, 1, 41); Packet(false, 1, layer: 1); }
                if (scenario == "rate_replay") Packet(false, 2);
                Packet(false, 1); ledger.PostUpdateWorld(); Packet(false, 1);
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
                typeof(ModType<Item>).GetProperty("Entity", PersistenceInstance)!.SetValue(generated, item);
                typeof(Item).GetProperty("ModItem", PersistenceInstance)!.SetValue(item, generated);
                typeof(GeneratedItem).GetProperty("Data", PersistenceInstance)!.SetValue(generated, data);
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
                        writer.Write(1); writer.Write(origin); writer.Write(new string('d', 32)); writer.Write((byte)3);
                        writer.Write((sbyte)0); writer.Write(true); writer.Write("");
                    }
                    wire.Position = 0; using var reader = new BinaryReader(wire); InfiniCraftPlayer.HandleStationEscrowResultPacket(reader, 0);
                }
                Response(new string('e', 32));
                Equal(true, modPlayer.HasPendingStationEscrowOperation, "foreign origin cannot settle pending operation");
                Equal(0, player.inventory.Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "foreign authority cannot mint material");
                Response(scope); Response(scope);
                Equal(false, modPlayer.HasPendingStationEscrowOperation, "matching response settles once");
                Equal(1, player.inventory.Sum(i => i.type == ItemID.CopperShortsword ? i.stack : 0), "matching attested return applies once, replay rejected");
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
        Equal(1, reader.ReadInt32(), "scoped request version");
        Equal(scope, reader.ReadString(), "fresh request names only current authority, never dormant origin");
        reader.ReadString(); string operation = reader.ReadString(); byte action = reader.ReadByte(); sbyte index = reader.ReadSByte();
        Equal((byte)1, action, "one fresh deposit request");
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) {
            writer.Write(InfiniCrafterLocal.Common.InfiniNetPacketIds.StationEscrowResult);
            writer.Write(1); writer.Write(scope); writer.Write(operation); writer.Write(action); writer.Write(index); writer.Write(true); writer.Write("");
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

    private static IDisposable PersistenceItemCheckHooks(InfiniCraftPlayer modPlayer)
    {
        var restores = new List<Action>();
        foreach (string name in new[] { "HookPreItemCheck", "HookPostItemCheck" }) {
            object hook = typeof(PlayerLoader).GetField(name, PersistenceStatic)!.GetValue(null)!;
            FieldInfo indices = hook.GetType().GetField("indices", PersistenceInstance)!;
            FieldInfo defaults = hook.GetType().GetField("defaultInstances", PersistenceInstance)!;
            object oldIndices = indices.GetValue(hook)!, oldDefaults = defaults.GetValue(hook)!;
            hook.GetType().GetMethod("Update")!.Invoke(hook, new object[] { new ModPlayer[] { modPlayer } });
            restores.Add(() => { indices.SetValue(hook, oldIndices); defaults.SetValue(hook, oldDefaults); });
        }
        return new PersistenceRestore(() => { foreach (Action restore in restores) restore(); });
    }

    private static GeneratedItem PersistenceItemCheckItem(GeneratedItemData data)
    {
        // ReviewItem's bare Item shell intentionally skips vanilla defaults. Native
        // ItemCheck needs real non-fishing, non-mount, non-potion defaults too.
        var item = new Item(ItemID.WoodenSword, 1);
        var generated = new GeneratedItem();
        typeof(ModType<Item>).GetProperty("Entity", PersistenceInstance)!.SetValue(generated, item);
        typeof(Item).GetProperty("ModItem", PersistenceInstance)!.SetValue(item, generated);
        typeof(GeneratedItem).GetProperty("Data", PersistenceInstance)!.SetValue(generated, data);
        data.ApplyToItem(item);
        return generated;
    }

    private sealed class PersistenceNativeUseBoundary : Exception { }
    private delegate void PersistenceNativeStartOriginal(Player player, Item item);
    private delegate void PersistenceNativeStartObserver(PersistenceNativeStartOriginal original, Player player, Item item);

    private static void NativeItemCheckRetriesUnstartedPlacementAfterReadyWithoutAutoReuse()
    {
        WithPersistenceTilemap((_, ledger) => {
            var scenarios = new[] { "sp", "autoreuse", "repress", "released", "item_changed", "player_changed", "data_changed", "data_mutated", "selector_changed", "target_changed", "expired", "wrong_sequence", "held_nonauto" };
            int x = Player.tileTargetX, y = Player.tileTargetY;
            var oldNpcs = Terraria.Main.npc; var oldView = Terraria.Main.GameViewMatrix;
            try {
                Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Microsoft.Xna.Framework.Graphics.Viewport(0, 0, 800, 600));
                PersistenceMatrix(scenarios.Select(scenario => ("native ItemCheck " + scenario, (Action)(() => {
                    ledger.ClearWorld(); using var peers = new ReviewPeers();
                    WithPlayer((client, modPlayer) => {
                        modPlayer.Initialize(); using var hooks = PersistenceItemCheckHooks(modPlayer);
                        client.whoAmI = 0; client.active = true; client.position = new Microsoft.Xna.Framework.Vector2(640, 640);
                        client.controlUseItem = true; client.releaseUseItem = true; client.selectedItem = 0; client.direction = 1;
                        var data = PersistencePlacementData("native-latch-" + scenario);
                        data.Gameplay.AutoReuse = scenario == "autoreuse"; data.Gameplay.UseStyle = ItemUseStyleID.Swing;
                        data.Gameplay.UseTime = data.Gameplay.UseAnimation = 20; data.Gameplay.ManaCost = 0; data.Gameplay.HoldLightStrength = 0;
                        data = GeneratedItemData.FromJson(data.ToNetworkJson())
                            ?? throw new InvalidOperationException("strict latch fixture failed actual FromJson");
                        peers.Register(data);
                        var generated = PersistenceItemCheckItem(data); client.inventory[0] = generated.Item;
                        var server = new Player { whoAmI = 0, active = true, position = client.position };
                        var serverData = GeneratedItemData.FromJson(data.ToNetworkJson())!;
                        var serverItem = PersistenceItemCheckItem(serverData); server.inventory[0] = serverItem.Item;
                        peers.Mode(scenario == "sp" ? NetmodeID.SinglePlayer : NetmodeID.MultiplayerClient, 0);
                        Terraria.Main.dedServ = true; Terraria.Main.player[0] = client;
                        Player.tileTargetX = Player.tileTargetY = 40; MaterialClock(100); Terraria.Main.tile[40, 40].WallType = 0;
                        Equal(scenario == "autoreuse", client.CanAutoReuseItem(generated.Item), "authored native autoReuse control; no accessory/global override");
                        int starts = 0;
                        PersistenceNativeStartObserver observe = (original, player, item) => {
                            if (player.whoAmI == 0) { starts++; throw new PersistenceNativeUseBoundary(); }
                            original(player, item);
                        };
                        using var entry = new MonoMod.RuntimeDetour.Hook(typeof(Player).GetMethod("ItemCheck_StartActualUse", PersistenceInstance)!, observe);
                        void Check(Player player) { try { player.ItemCheck(); } catch (PersistenceNativeUseBoundary) { } }
                        using var network = PersistenceObserveNetworkSend((_, __) => { });
                        Check(client);
                        if (scenario == "sp") { Equal(1, starts, "SP first press reaches actual native start entry"); return; }
                        Equal(0, starts, "no actual use before ready");
                        Equal(false, client.releaseUseItem, "native first refused hook consumed release latch");
                        Equal(1, peers.Sent.Count, "one actual intent from real native ItemCheck");
                        Equal(InfiniCrafterLocal.Common.InfiniNetPacketIds.RequestGeneratedPlacementIntent, peers.Sent[0][0], "real native intent id");
                        byte[] intent = peers.Sent[0]; peers.Sent.Clear();
                        peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server; peers.Receive(intent, 0);
                        Equal(1, peers.Sent.Count, "server-produced ready"); byte[] ready = peers.Sent[0]; peers.Sent.Clear();
                        ((System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("PendingAuthorizations", PersistenceStatic)!.GetValue(null)!).Clear();
                        peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.dedServ = true; Terraria.Main.player[0] = client;
                        if (scenario == "released") { client.controlUseItem = false; Check(client); }
                        if (scenario == "item_changed") client.inventory[0] = PersistenceItemCheckItem(data).Item;
                        if (scenario == "player_changed") Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, position = client.position };
                        if (scenario == "data_changed") typeof(GeneratedItem).GetProperty("Data", PersistenceInstance)!.SetValue(generated, GeneratedItemData.FromJson(data.ToNetworkJson()));
                        if (scenario == "data_mutated") data.Name = "mutated after intent";
                        if (scenario == "selector_changed") client.altFunctionUse = 2;
                        if (scenario == "target_changed") Player.tileTargetX = 41;
                        if (scenario == "expired") MaterialClock(221); else MaterialClock(101);
                        if (scenario == "wrong_sequence") BitConverter.GetBytes(999UL).CopyTo(ready, 5);
                        peers.Receive(ready);
                        if (scenario == "repress") { client.controlUseItem = false; Check(client); client.controlUseItem = true; MaterialClock(102); }
                        Check(client);
                        if (scenario == "repress" && starts == 0) {
                            // A lifecycle fence may retire a released activation;
                            // the new press then needs its own genuine ready.
                            byte[] next = peers.Sent.Single(); peers.Sent.Clear();
                            peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server; peers.Receive(next, 0);
                            byte[] nextReady = peers.Sent.Single(); peers.Sent.Clear();
                            ((System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("PendingAuthorizations", PersistenceStatic)!.GetValue(null)!).Clear();
                            peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.dedServ = true; Terraria.Main.player[0] = client; peers.Receive(nextReady);
                            MaterialClock(103); Check(client);
                        }
                        bool canStart = scenario is "autoreuse" or "held_nonauto" or "repress";
                        Equal(canStart ? 1 : 0, starts, "same held activation reaches native start; lifecycle controls cannot start old activation");
                        Equal(0, (int)Terraria.Main.tile[40, 40].WallType, "throwing native start observer performs no fake world placement");
                        Equal(1, generated.Item.stack, "boundary observer performs no fake stack consumption");
                        Equal(scenario == "autoreuse", generated.Item.autoReuse, "authored AutoReuse remains unchanged");
                        if (scenario == "held_nonauto") {
                            // The observer aborts before native start's body; emulate only
                            // the native latch retirement, never success/world mutation.
                            client.releaseUseItem = false; Check(client);
                            Equal(1, starts, "one-shot native retry cannot turn held non-auto item into repeated starts");
                        }
                    });
                }))));
            }
            finally { Player.tileTargetX = x; Player.tileTargetY = y; Terraria.Main.npc = oldNpcs; Terraria.Main.GameViewMatrix = oldView; }
        });
    }

    private static byte[] PersistencePlacementNotify(ulong sequence, int x, int y, byte layer = 2)
    {
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) {
            writer.Write(InfiniCrafterLocal.Common.InfiniNetPacketIds.NotifyGeneratedPlacement); writer.Write((int)typeof(GeneratedPlacementLedgerSystem).GetField("PlacementProtocolVersion", PersistenceStatic)!.GetRawConstantValue()!);
            writer.Write(sequence); writer.Write(layer); writer.Write(x); writer.Write(y);
        }
        return stream.ToArray();
    }

    private static void UnmutatedAbandonedPlacementDoesNotStallNewTarget()
    {
        WithPersistenceTilemap((player, ledger) => {
            var data = PersistencePlacementData(); var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            PersistenceMatrix(new (string, Action)[] {
                ("SP abandoned unmutated target supersession", () => {
                    ledger.ClearWorld(); Terraria.Main.netMode = NetmodeID.SinglePlayer; MaterialClock(100);
                    Terraria.Main.tile[40, 40].WallType = Terraria.Main.tile[41, 40].WallType = 0;
                    Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40, 40), "SP before-state A captured");
                    MaterialClock(101);
                    Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 41, 40), "unmutated abandoned A does not stall legitimate B target");
                    Terraria.Main.tile[40, 40].WallType = 1;
                    Equal(false, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "retired A change cannot commit B snapshot");
                    Terraria.Main.tile[41, 40].WallType = 1;
                    Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "only fresh B before-state commits");
                    Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "retired A is never tracked");
                    Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 41, 40), "fresh B tracked once");
                }),
                ("MP native client change retires ordered unmutated A only", () => {
                    ledger.ClearWorld(); using var peers = new ReviewPeers(); peers.Register(data);
                    int x = Player.tileTargetX, y = Player.tileTargetY;
                    try {
                        var client = new Player { whoAmI = 0, active = true, position = player.position };
                        var server = new Player { whoAmI = 0, active = true, position = player.position };
                        var clientItem = ReviewItem(data); client.inventory[0] = clientItem.Item;
                        server.inventory[0] = ReviewItem(GeneratedItemData.FromJson(data.ToNetworkJson())!).Item;
                        var auths = (System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("PendingAuthorizations", PersistenceStatic)!.GetValue(null)!;
                        Player.tileTargetX = Player.tileTargetY = 40; MaterialClock(100);
                        Terraria.Main.tile[40, 40].WallType = Terraria.Main.tile[41, 40].WallType = 0;
                        peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client;
                        Equal(false, clientItem.CanUseItem(client), "A sends real client intent without mutating");
                        byte[] aIntent = peers.Sent.Single(); peers.Sent.Clear();
                        peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server; peers.Receive(aIntent, 0);
                        object a = auths[0]!; byte[] aReady = peers.Sent.Single(); peers.Sent.Clear(); auths.Clear();
                        peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client; peers.Receive(aReady);
                        Player.tileTargetX = 41; MaterialClock(101);
                        Equal(false, clientItem.CanUseItem(client), "real client hook retires mismatched local A");
                        MaterialClock(102); Equal(false, clientItem.CanUseItem(client), "B waits for fresh server before-state");
                        byte[] bIntent = peers.Sent.Single(); peers.Sent.Clear();
                        auths[0] = a; peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server; peers.Receive(bIntent, 0);
                        Equal(true, auths[0] is not null && !ReferenceEquals(a, auths[0]), "server supersedes only unmutated unnotified A with fresh B before-state");
                        byte[] bReady = peers.Sent.Single(); peers.Sent.Clear(); object b = auths[0]!;
                        auths.Clear(); peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client; peers.Receive(bReady);
                        Equal(true, clientItem.CanUseItem(client), "exact new B ready admits B");
                        auths.Clear(); auths[0] = b; peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server;
                        Terraria.Main.tile[40, 40].WallType = 1;
                        peers.Receive(PersistencePlacementNotify(1, 40, 40), 0);
                        Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "late retired A notify cannot reconstruct snapshot");
                        Terraria.Main.tile[41, 40].WallType = 1;
                        peers.Receive(PersistencePlacementNotify(2, 41, 40), 0); peers.Receive(PersistencePlacementNotify(2, 41, 40), 0);
                        Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 41, 40), "new B exact notify commits once");
                        var save = new TagCompound(); ledger.SaveWorldData(save);
                        Equal(1, save.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Count, "only B owns one exact material return");
                    }
                    finally { Player.tileTargetX = x; Player.tileTargetY = y; }
                }),
                ("native changed A cannot be superseded", () => {
                    ledger.ClearWorld(); Terraria.Main.netMode = NetmodeID.SinglePlayer; MaterialClock(100);
                    Terraria.Main.tile[40, 40].WallType = Terraria.Main.tile[41, 40].WallType = 0;
                    Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40, 40), "before A");
                    Terraria.Main.tile[40, 40].WallType = 1; MaterialClock(101);
                    Equal(false, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 41, 40), "actual A completion cannot be discarded");
                    Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "A completion still returns exact material");
                }),
                ("MP supersession preserves mutated/notified A and requires exact retirement", () => {
                    PersistenceMatrix(new[] { "native_changed", "notify_received", "wrong_retirement", "expired" }.Select(scenario => ("MP retirement " + scenario, (Action)(() => {
                        ledger.ClearWorld(); using var peers = new ReviewPeers(); peers.Register(data);
                        int x = Player.tileTargetX, y = Player.tileTargetY;
                        try {
                            var client = new Player { whoAmI = 0, active = true, position = player.position };
                            var server = new Player { whoAmI = 0, active = true, position = player.position };
                            var generated = ReviewItem(data); client.inventory[0] = generated.Item;
                            server.inventory[0] = ReviewItem(GeneratedItemData.FromJson(data.ToNetworkJson())!).Item;
                            var auths = (System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("PendingAuthorizations", PersistenceStatic)!.GetValue(null)!;
                            Player.tileTargetX = Player.tileTargetY = 40; MaterialClock(100);
                            Terraria.Main.tile[40, 40].WallType = Terraria.Main.tile[41, 40].WallType = 0;
                            peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client;
                            Equal(false, generated.CanUseItem(client), "A intent uses actual client hook");
                            byte[] intent = peers.Sent.Single(); peers.Sent.Clear();
                            peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server; peers.Receive(intent, 0);
                            object a = auths[0]!; byte[] ready = peers.Sent.Single(); peers.Sent.Clear(); auths.Clear();
                            peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client; peers.Receive(ready);
                            Player.tileTargetX = 41; MaterialClock(101); Equal(false, generated.CanUseItem(client), "retire unchanged local A");
                            MaterialClock(102); Equal(false, generated.CanUseItem(client), "new B still waits for server");
                            byte[] next = peers.Sent.Single(); peers.Sent.Clear();
                            using (var payload = new BinaryReader(new MemoryStream(next))) {
                                payload.ReadByte(); Equal((int)typeof(GeneratedPlacementLedgerSystem).GetField("PlacementProtocolVersion", PersistenceStatic)!.GetRawConstantValue()!, payload.ReadInt32(), "versioned ordered supersession");
                                Equal(2UL, payload.ReadUInt64(), "new actual intent sequence"); payload.ReadByte(); payload.ReadInt32(); payload.ReadInt32();
                                Equal(1UL, payload.ReadUInt64(), "actual request names exact retired A");
                            }
                            if (scenario == "wrong_retirement") BitConverter.GetBytes(999UL).CopyTo(next, next.Length - sizeof(ulong));
                            auths[0] = a; peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server;
                            if (scenario == "native_changed") Terraria.Main.tile[40, 40].WallType = 1;
                            if (scenario == "notify_received") peers.Receive(PersistencePlacementNotify(1, 40, 40), 0);
                            if (scenario == "expired") MaterialClock(221);
                            peers.Receive(next, 0);
                            byte[] response = peers.Sent.Single(); peers.Sent.Clear();
                            using (var payload = new BinaryReader(new MemoryStream(response))) {
                                payload.ReadByte(); payload.ReadInt32(); payload.ReadUInt64();
                                Equal(scenario == "expired", payload.ReadBoolean(), "only expiry permits B in refusal controls");
                            }
                            Equal(scenario != "expired", ReferenceEquals(a, auths[0]), "native change/notify/wrong retirement cannot discard A");
                            if (scenario == "expired") {
                                Terraria.Main.tile[40, 40].WallType = 1; peers.Receive(PersistencePlacementNotify(1, 40, 40), 0);
                                Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "expired A notify cannot borrow B snapshot");
                                Terraria.Main.tile[41, 40].WallType = 1; peers.Receive(PersistencePlacementNotify(2, 41, 40), 0);
                                Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 41, 40), "fresh B remains usable after old expiry");
                            }
                            else {
                                Terraria.Main.tile[40, 40].WallType = 1; peers.Receive(PersistencePlacementNotify(1, 40, 40), 0);
                                Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 40, 40), "preserved A can complete through its actual notify");
                                Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 41, 40), "refused B never grants material");
                            }
                        }
                        finally { Player.tileTargetX = x; Player.tileTargetY = y; }
                    }))));
                }),
            });
        });
    }

    private static void PlacementReadyCannotApproveDifferentServerResolvedBinding()
    {
        WithPersistenceTilemap((player, ledger) => {
            int x = Player.tileTargetX, y = Player.tileTargetY;
            try {
                PersistenceMatrix(new[] { "same", "different_id_wall", "same_id_different_definition", "different_style" }.Select(scenario => ("ready identity " + scenario, (Action)(() => {
                    ledger.ClearWorld(); using var peers = new ReviewPeers();
                    var clientData = PersistencePlacementData("client-wall-1"); peers.Register(clientData);
                    var serverData = GeneratedItemData.FromJson(clientData.ToNetworkJson())!;
                    if (scenario == "different_id_wall") { serverData.Id = "server-wall-2"; serverData.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.WallId = 2; }
                    if (scenario == "same_id_different_definition") serverData.Name = "different exact definition";
                    if (scenario == "different_style") serverData.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.PlaceStyle = 1;
                    serverData = GeneratedItemData.FromJson(serverData.ToNetworkJson())
                        ?? throw new InvalidOperationException("independently strict server-held definition failed actual FromJson");
                    var client = new Player { whoAmI = 0, active = true, position = player.position };
                    var server = new Player { whoAmI = 0, active = true, position = player.position };
                    var generated = ReviewItem(clientData); client.inventory[0] = generated.Item; server.inventory[0] = ReviewItem(serverData).Item;
                    Player.tileTargetX = Player.tileTargetY = 40; Terraria.Main.tile[40, 40].WallType = 0;
                    peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client;
                    Equal(false, generated.CanUseItem(client), "client never grants own definition authority");
                    byte[] intent = peers.Sent.Single(); peers.Sent.Clear();
                    peers.Mode(NetmodeID.Server, 255); Terraria.Main.player[0] = server; peers.Receive(intent, 0);
                    byte[] ready = peers.Sent.Single(); peers.Sent.Clear();
                    var auths = (System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("PendingAuthorizations", PersistenceStatic)!.GetValue(null)!;
                    Equal(1, auths.Count, "server authorization uses its independently resolved held definition"); auths.Clear();
                    peers.Mode(NetmodeID.MultiplayerClient, 0); Terraria.Main.player[0] = client; peers.Receive(ready);
                    Equal(scenario == "same", generated.CanUseItem(client), "ready cannot approve a different server-derived identity/type/style/definition");
                    Equal(0, (int)Terraria.Main.tile[40, 40].WallType, "mismatch never mutates native wall");
                    Equal(1, generated.Item.stack, "mismatch never consumes native item");
                }))));
            }
            finally { Player.tileTargetX = x; Player.tileTargetY = y; }
        });
    }

    private static string PersistenceRawBytes(TagCompound tag)
    {
        using var stream = new MemoryStream(); TagIO.ToStream(tag, stream, compress: false);
        return Convert.ToBase64String(stream.ToArray());
    }

    private static TagCompound PersistenceQuarantineEnvelope(string group, bool requeued = false)
        => new() {
            ["claim"] = new TagCompound { ["groupId"] = group, ["generatedItemId"] = "exact_return_id",
                ["definitionJson"] = "{broken-original-" + group, ["x"] = 40, ["y"] = 40, ["rawExtension"] = group },
            ["cause"] = "definition_invalid", ["requeued"] = requeued,
            ["requeueDefinitionJson"] = "", ["lastFailureCause"] = "",
        };

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

    private static void MalformedQuarantineEnvelopePreservesHealthyNeighbors()
    {
        using var serializer = WithPersistenceBoolSerializer();
        WithPersistenceTilemap((_, ledger) => {
            var variants = new List<(string, Action)>();
            foreach (string field in new[] { "valid", "claim", "cause", "requeued", "requeueDefinitionJson", "lastFailureCause" })
            foreach (int position in new[] { 0, 1, 2 })
            {
                string f = field; int p = position;
                variants.Add(($"quarantine envelope {f} at {p}", () => {
                    var bad = PersistenceQuarantineEnvelope("q-bad");
                    bad["unknownEnvelopeField"] = "literal-unrecognized-payload";
                    if (f != "valid") bad[f] = f == "claim" ? "not a compound" : f == "requeued" ? "not a boolean" : 17;
                    string literal = PersistenceRawBytes(bad);
                    var head = PersistenceQuarantineEnvelope("q-head"); var tail = PersistenceQuarantineEnvelope("q-tail");
                    var rows = new List<TagCompound> { head, tail }; rows.Insert(p, bad);
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementReturnQuarantineV1"] = rows }));
                    for (int round = 0; round < 3; round++) {
                        var save = new TagCompound(); ledger.SaveWorldData(save);
                        var healthy = save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1");
                        Equal(f == "valid" ? 3 : 2, healthy.Count, "canonical envelopes only; malformed row cannot become a fabricated claim");
                        foreach (TagCompound original in new[] { head, tail })
                            Equal(PersistenceRawBytes(original.GetCompound("claim")), PersistenceRawBytes(healthy.Single(r => r.GetCompound("claim").GetString("groupId") == original.GetCompound("claim").GetString("groupId")).GetCompound("claim")), "healthy sibling claim survives verbatim");
                        var raw = save.GetList<TagCompound>("infiniGeneratedPlacementRawQuarantineEnvelopesV1");
                        Equal(f == "valid" ? 0 : 1, raw.Count, "malformed full envelope is retained in separate versioned read-only bucket");
                        if (f != "valid") Equal(literal, PersistenceRawBytes(raw[0]), "full malformed envelope/type/extension is literal after each reload");
                        ledger.LoadWorldData(PersistenceNbtRoundtrip(save));
                    }
                    var data = PersistencePlacementData("exact_return_id");
                    InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
                    string json = data.ToNetworkJson();
                    if (f != "valid") Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("q-bad", json), "raw malformed envelope cannot grant recovery authority");
                    Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("q-tail", json), "valid healthy tail remains requeueable");
                    var after = new TagCompound(); ledger.SaveWorldData(after); ledger.LoadWorldData(PersistenceNbtRoundtrip(after));
                    Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("q-tail", json), "healthy requeue replay remains idempotent after reload");
                    var repeated = new TagCompound(); ledger.SaveWorldData(repeated);
                    Equal(1, repeated.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "one exact healthy pending owner");
                }));
            }
            PersistenceMatrix(variants);
        });
    }

    private static void QuarantineRequeueReceiptDoesNotCountAsSecondMaterialOwner()
    {
        using var serializer = WithPersistenceBoolSerializer();
        WithPersistenceTilemap((player, ledger) => {
            var data = PersistencePlacementData("exact_return_id");
            InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
            string json = data.ToNetworkJson();
            Equal(true, GeneratedItemData.FromJson(json) is not null, "strict current-world repair fixture");
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            PersistenceMatrix(new (string, Action)[] {
                ("distinct live owner ceiling refuses new grant", () => {
                    var rows = Enumerable.Range(0, 8192).Select(i => PersistenceQuarantineEnvelope("capacity-" + i)).ToList();
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementReturnQuarantineV1"] = rows }));
                    Terraria.Main.tile[40, 40].WallType = 0;
                    Equal(false, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40, 40), "full live material capacity refuses before mutation");
                    var save = new TagCompound(); ledger.SaveWorldData(save);
                    Equal(8192, save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1").Count, "no claim discarded to free capacity");
                }),
                ("requeue has one material owner not two", () => {
                    var rows = Enumerable.Range(0, 8191).Select(i => PersistenceQuarantineEnvelope("capacity-" + i)).ToList();
                    string raw = PersistenceRawBytes(rows[0].GetCompound("claim"));
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementReturnQuarantineV1"] = rows }));
                    Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("capacity-0", json), "real requeue admits one owner");
                    Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("capacity-0", json), "same payload replay adds no owner");
                    var changed = GeneratedItemData.FromJson(json)!; changed.Name = "different replacement";
                    Equal(false, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("capacity-0", changed.ToNetworkJson()), "changed payload cannot borrow receipt");
                    var save = new TagCompound(); ledger.SaveWorldData(save);
                    Equal(8191, save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1").Count, "forensic journal retained");
                    Equal(raw, PersistenceRawBytes(save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1")[0].GetCompound("claim")), "original raw claim unchanged");
                    Equal(1, save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "one pending owner only");
                    Terraria.Main.tile[40, 40].WallType = 0;
                    Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40, 40), "8190 quarantined plus one pending leaves one authorization slot");
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(save));
                    Equal(true, GeneratedPlacementLedgerSystem.TryRequeueQuarantinedReturn("capacity-0", json), "idempotence survives reload");
                    var after = new TagCompound(); ledger.SaveWorldData(after);
                    Equal(1, after.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "reload replay never duplicates");
                }),
                ("receipt-only journal is not material capacity", () => {
                    var rows = Enumerable.Range(0, 8192).Select(i => PersistenceQuarantineEnvelope("receipt-" + i, requeued: true)).ToList();
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementReturnQuarantineV1"] = rows }));
                    Terraria.Main.tile[40, 40].WallType = 0;
                    Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40, 40), "no live material owners in receipt-only saved-state fixture");
                    var save = new TagCompound(); ledger.SaveWorldData(save);
                    Equal(8192, save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1").Count, "receipt history never silently deleted");
                    Equal(0, save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "fixture does not pretend to deliver or spawn items");
                }),
            });
        });
    }

    private static void PendingRawMalformedAndOverflowRowsKeepValidNeighbors()
    {
        using var serializer = WithPersistenceBoolSerializer();
        WithPersistenceTilemap((_, ledger) => {
            string json = PersistencePlacementData("exact_return_id").ToNetworkJson();
            TagCompound Row(string group) => new() { ["groupId"] = group, ["generatedItemId"] = "exact_return_id",
                ["definitionJson"] = json, ["x"] = 40, ["y"] = 40, ["rawExtension"] = group };
            foreach (bool reverse in new[] { false, true }) {
                var badX = Row("bad-coordinate"); badX["x"] = "not an integer";
                var badId = Row("bad-identity"); badId["generatedItemId"] = "";
                var rows = new List<TagCompound> { badX, Row("valid-middle"), badId };
                if (reverse) rows.Reverse();
                ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementReturnsV2"] = rows }));
                for (int round = 0; round < 3; round++) {
                    var save = new TagCompound(); ledger.SaveWorldData(save);
                    Equal(1, save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "valid middle owns one pending return");
                    Equal("valid-middle", save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2")[0].GetString("groupId"), "valid sibling identity retained");
                    var raw = save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1");
                    foreach (var bad in new[] { badX, badId })
                        Equal(PersistenceRawBytes(bad), PersistenceRawBytes(raw.Single(r => r.GetCompound("claim").GetString("groupId") == bad.GetString("groupId")).GetCompound("claim")), "malformed pending raw bytes retained");
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(save));
                }
            }
            var malformed = Row("malformed-head"); malformed["x"] = "literal-overflow-head";
            var overflow = Enumerable.Range(0, 8193).Select(i => Row("pending-" + i)).ToList(); overflow.Insert(0, malformed);
            ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementReturnsV2"] = overflow }));
            for (int round = 0; round < 2; round++) {
                var save = new TagCompound(); ledger.SaveWorldData(save);
                var pending = save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2");
                var raw = save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1");
                Equal(8192, pending.Count, "malformed head consumes no valid pending admission slot");
                Equal(2, raw.Count, "malformed head and valid overflow remain durable");
                var retained = pending.Concat(raw.Select(r => r.GetCompound("claim"))).ToDictionary(r => r.GetString("groupId"), StringComparer.Ordinal);
                Equal(8194, retained.Count, "every literal source group retains exactly one material owner");
                foreach (TagCompound source in overflow)
                    Equal(PersistenceRawBytes(source), PersistenceRawBytes(retained[source.GetString("groupId")]), "pending/overflow literal roster retained");
                ledger.LoadWorldData(PersistenceNbtRoundtrip(save));
            }
        });
    }
}
