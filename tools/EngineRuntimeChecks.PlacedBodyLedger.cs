using System;
using System.IO;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    // Reuse the real CPU tilemap, registry/ModPacket interception and native NBT helpers.
    // No replacement material owner, fake successful native spawn or new transport.
    private static void WithPlacedLedger(Action<Player, GeneratedPlacementLedgerSystem> check)
    {
        using var boolSerializer = WithPersistenceBoolSerializer();
        var field = typeof(Terraria.ObjectData.TileObjectData).GetField("_data", PersistenceStatic)!;
        object? old = field.GetValue(null);
        field.SetValue(null, Enumerable.Repeat<Terraria.ObjectData.TileObjectData>(null!, Terraria.ModLoader.TileLoader.TileCount).ToList());
        try { WithPersistenceTilemap((player,ledger) => {
            ledger.PostSetupContent();
            try { check(player,ledger); }
            finally { ledger.Unload(); }
        }); }
        finally { field.SetValue(null, old); }
    }

    private static GeneratedItemData PlacedLedgerData(string id)
    {
        var data = PersistencePlacementData(id);
        GeneratedItemRegistryService.StampCurrentWorld(data);
        var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
        placement.TileId = TileID.Stone; placement.WallId = -1;
        placement.PlacedBody = new RuntimePlacedBodySpec { RenderSizePx = 37,
            FootprintAnchorX = 0.25, FootprintAnchorY = 1, ImagePivotX = 0.125, ImagePivotY = 0.75,
            OffsetXPx = -13, OffsetYPx = 17, RotationDegrees = -45.5, FlipX = true, FlipY = false };
        return data;
    }

    private static TagCompound PlacedLedgerSaved(GeneratedPlacementLedgerSystem ledger)
    { var tag = new TagCompound(); ledger.SaveWorldData(tag); return tag; }

    private static List<TagCompound> PlacedLedgerGroups(GeneratedPlacementLedgerSystem ledger)
        => PlacedLedgerSaved(ledger).GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").ToList();

    private static byte[] PlacedLedgerSnapshot(GeneratedPlacementLedgerSystem ledger)
    {
        using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream, Encoding.UTF8, true);
        ledger.NetSend(writer); return stream.ToArray();
    }

    private static void PlacedLedgerReceiveSnapshot(GeneratedPlacementLedgerSystem ledger, byte[] bytes)
    {
        using var reader = new BinaryReader(new MemoryStream(bytes)); ledger.NetReceive(reader);
        Equal(reader.BaseStream.Length, reader.BaseStream.Position, "initial snapshot completely consumed");
    }

    private static TagCompound PlacedLedgerRow(GeneratedItemData data, int index, object? body = null)
    {
        var row = new TagCompound {
            ["groupId"] = index.ToString("x32"), ["generatedItemId"] = data.Id, ["definitionJson"] = data.ToNetworkJson(),
            ["cells"] = new List<TagCompound> { new() { ["layer"] = 1, ["x"] = 1 + index % 90, ["y"] = 1 + index / 90 } },
        };
        row["placedBody"] = body ?? new TagCompound { ["version"] = 1, ["bindingId"] = "place",
            ["definitionHash"] = GeneratedItemRegistryService.DefinitionIdentity(data), ["tileType"] = (int)TileID.Stone, ["nativeStyle"] = 0 };
        return row;
    }

    private static void PlacedLedgerLoadRows(GeneratedPlacementLedgerSystem ledger, IEnumerable<TagCompound> rows)
        => ledger.LoadWorldData(PersistenceNbtRoundtrip(new TagCompound { ["infiniGeneratedPlacementLedgerV2"] = rows.ToList() }));

    private delegate bool PlacedDecode(int x, int y, int type, int style,
        out int ox, out int oy, out int width, out int height, out int alternate);


    private static void PlacedBodyUsesActualNativePoseAndRejectsIndependentActors()
    {
        WithPlacedLedger((player,ledger) => {
            Terraria.ObjectData.TileObjectData.Initialize();
            var data = PlacedLedgerData("native-pose-control");
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            placement.TileId = TileID.Torches;
            MethodInfo decode = typeof(GeneratedPlacementLedgerSystem).GetMethod("TryResolveNativeFootprint",PersistenceStatic)!;
            foreach (int frame in new[]{0,22,44,66,88,110})
            {
                ledger.ClearWorld(); var tile = Terraria.Main.tile[40,40]; tile.HasTile = false;
                Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"real torch floor/wall variants are certified native placements");
                tile.HasTile=true;tile.TileType=TileID.Torches;tile.TileFrameX=(short)frame;tile.TileFrameY=0;
                Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"actual packed alternate/orientation commits exact native body");
                var witness=PlacedLedgerGroups(ledger).Single().GetCompound("placedBody");
                Equal(frame/22,witness.GetInt("nativeAlternate"),"GetTileInfo packed remainder is not alternate ordinal");
                Equal(1,PlacedLedgerGroups(ledger).Single().GetList<TagCompound>("cells").Count,"native one-cell torch never absorbs neighboring bodies");
                tile.TileFrameX=(short)((frame+66)%132);
                Equal(true,(bool)typeof(GeneratedPlacementLedgerSystem).GetMethod("ShouldSuppressPlacedBody",PersistenceStatic)!.Invoke(null,new object[]{40,40})!,"legitimate wired frames keep selected presentation and material");
            }
            ledger.ClearWorld(); var unsupportedTile=Terraria.Main.tile[40,40]; unsupportedTile.HasTile=false;
            placement.TileId=TileID.TargetDummy;
            Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"independent actor constructor is refused even before ByPosition actor exists");
            Equal(false,Terraria.Main.tile[40,40].HasTile,"unsupported actor creates no native tile");
        });
    }

    private static void PlacedBodyCosmeticDecodeCannotEraseMaterial()
    {
        WithPlacedLedger((player, ledger) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; var data = PlacedLedgerData("cosmetic-failure-material");
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            var target = Terraria.Main.tile[40,40]; var adjacent = Terraria.Main.tile[41,40];
            target.HasTile = adjacent.HasTile = false;
            Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40,40), "real selected placement authorizes");
            Equal(false, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "unchanged native before-state cannot mint material");
            target.HasTile = adjacent.HasTile = true; target.TileType = adjacent.TileType = TileID.Stone;
            PlacedDecode fail = (int x, int y, int type, int style, out int ox, out int oy, out int w, out int h, out int alt) => {
                ox = oy = w = h = alt = 0; throw new InvalidDataException("fixture post-native cosmetic decoder fault");
            };
            using (var hook = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedPlacementLedgerSystem).GetMethod("TryResolveNativeFootprint", PersistenceStatic)!, fail))
                Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "cosmetic fault cannot abandon native material success");
            Equal(true, GeneratedPlacementLedgerSystem.TryConsumePlacementReceipt(player), "exact material receipt still charges accepted use");
            Equal(false, GeneratedPlacementLedgerSystem.TryConsumePlacementReceipt(player), "material receipt cannot charge twice");
            Equal(false, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Tile, 41,40), "adjacent simultaneous same-type tile not absorbed");
            var row = PlacedLedgerGroups(ledger).Single(); var witness = row.GetCompound("placedBody");
            Equal(1, row.GetList<TagCompound>("cells").Count, "one exact owned material cell");
            Equal("place", witness.GetString("bindingId"), "opt-in binding survives unexpected decode");
            Equal(GeneratedItemRegistryService.DefinitionIdentity(data), witness.GetString("definitionHash"), "selection remains hash-bound");
            Equal("native_footprint_decode_error", witness.GetString("failure"), "cosmetic failure is diagnosed");
            string raw = PersistenceRawBytes(witness); var saved = PlacedLedgerSaved(ledger);
            ledger.LoadWorldData(PersistenceNbtRoundtrip(saved));
            Equal(raw, PersistenceRawBytes(PlacedLedgerGroups(ledger).Single().GetCompound("placedBody")), "native NBT retains raw diagnostic witness");
            Equal(data.ToNetworkJson(), PlacedLedgerGroups(ledger).Single().GetString("definitionJson"), "exact material definition never substituted");
        });
    }

    private static IDictionary PlacedLedgerRegistryRows(ReviewPeers peers)
        => (IDictionary)peers.Registry.GetType().GetField("_byId", PersistenceInstance)!.GetValue(peers.Registry)!;

    private static void PlacedBodyHydrationIsBoundedFairAndSessionScoped()
    {
        WithPlacedLedger((_, ledger) => {
            using var peers = new ReviewPeers(); var definitions = Enumerable.Range(1, 65).Select(i => PlacedLedgerData("hydration-" + i)).ToArray();
            peers.Mode(NetmodeID.SinglePlayer, 0); PlacedLedgerLoadRows(ledger, definitions.Select((d,i) => PlacedLedgerRow(d,i+1)));
            byte[] snapshot = PlacedLedgerSnapshot(ledger); ledger.ClearWorld(); PlacedLedgerRegistryRows(peers).Clear();
            peers.Mode(NetmodeID.MultiplayerClient, 0); PlacedLedgerReceiveSnapshot(ledger, snapshot); peers.Sent.Clear();
            MaterialClock(200); ledger.PostUpdateEverything();
            Equal(32, peers.Sent.Count, "all-client derived hydration visits at most 32 unresolved definitions");
            ledger.PostUpdateEverything(); Equal(32, peers.Sent.Count, "same world tick cannot refill hydration visit budget");
            peers.Sent.Clear(); MaterialClock(201); ledger.PostUpdateEverything();
            Equal(32, peers.Sent.Count, "second round visits the next 32 instead of starving behind first missing 32");
            var wrong = GeneratedItemData.FromJson(definitions[64].ToNetworkJson())!; wrong.Name = "same ID wrong canonical hash";
            peers.Register(wrong); peers.Sent.Clear(); MaterialClock(202); ledger.PostUpdateEverything();
            Equal(0, PlacedLedgerGroups(ledger).Count(g => g.GetString("definitionJson").Length != 0), "wrong same-ID registry definition cannot hydrate late tail");
            peers.Register(definitions[64]); MaterialClock(203); ledger.PostUpdateEverything();
            MaterialClock(204); ledger.PostUpdateEverything();
            Equal(definitions[64].ToNetworkJson(), PlacedLedgerGroups(ledger).Single(g => g.GetString("generatedItemId") == definitions[64].Id).GetString("definitionJson"), "round robin returns to late tail after valid definition arrives");
            var connection = Netplay.Connection; var oldSocket = connection.Socket;
            try {
                connection.Socket = (Terraria.Net.Sockets.ISocket)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Net.Sockets.TcpSocket));
                MaterialClock(205); ledger.PostUpdateEverything();
                Equal(0, PlacedLedgerGroups(ledger).Count, "replacement server transport retires old mirrors and derived queue");
                PlacedLedgerReceiveSnapshot(ledger, snapshot);
                Equal(65, PlacedLedgerGroups(ledger).Count, "new sender session accepts fresh initial snapshot");
            } finally { connection.Socket = oldSocket; }
            ledger.ClearWorld(); peers.Sent.Clear(); MaterialClock(206); ledger.PostUpdateEverything();
            Equal(0, peers.Sent.Count, "ClearWorld removes derived hydration references");
        });
    }

    private delegate void PlacedPublishOrig(GeneratedItemRegistryService self, GeneratedItemData? data, int toClient, int ignoreClient);
    private delegate void PlacedPublishHook(PlacedPublishOrig orig, GeneratedItemRegistryService self, GeneratedItemData? data, int toClient, int ignoreClient);

    private static void PlacedBodyRestoreUsesExistingRegistryWithoutReplacingConflicts()
    {
        WithPlacedLedger((_, ledger) => {
            using var peers = new ReviewPeers(); var data = PlacedLedgerData("restore-registry");
            peers.Mode(NetmodeID.Server,255); var valid = PlacedLedgerRow(data,1); PlacedLedgerRegistryRows(peers).Clear();
            var publications = new List<string>();
            PlacedPublishHook observe = (orig, self, definition, to, ignore) => {
                publications.Add(GeneratedItemRegistryService.DefinitionIdentity(definition!)); orig(self, definition, to, ignore);
            };
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedItemRegistryService).GetMethod("PublishGeneratedItem")!, observe);
            PlacedLedgerLoadRows(ledger, new[] { valid });
            Equal(true, peers.Registry.TryGet(data.Id, out var restored), "valid opt-in durable definition restored into existing registry");
            Equal(GeneratedItemRegistryService.DefinitionIdentity(data), GeneratedItemRegistryService.DefinitionIdentity(restored), "restore uses canonical identity owner");
            PlacedLedgerSnapshot(ledger);
            Equal(true, publications.Contains(GeneratedItemRegistryService.DefinitionIdentity(data)), "join snapshot publishes restored opt-in through existing registry transport");
            var wrong = GeneratedItemData.FromJson(data.ToNetworkJson())!; wrong.Name = "conflicting same-ID registry owner"; peers.Register(wrong);
            string wrongHash = GeneratedItemRegistryService.DefinitionIdentity(wrong); publications.Clear();
            PlacedLedgerLoadRows(ledger, new[] { valid }); PlacedLedgerSnapshot(ledger);
            Equal(true, peers.Registry.TryGet(data.Id, out var retained), "registry conflict stays visible");
            Equal(wrongHash, GeneratedItemRegistryService.DefinitionIdentity(retained), "load/join cannot silently overwrite wrong same-ID hash");
            Equal(0, publications.Count, "conflicting placement does not publish replacement definition");
            var bad = PlacedLedgerRow(data,2); bad.GetCompound("placedBody")["definitionHash"] = 7;
            bad.GetCompound("placedBody")["unknownField"] = new byte[] { 1, 2, 3 };
            var nonCompound = PlacedLedgerRow(data,3,"literal malformed cosmetic witness");
            var absent = PlacedLedgerRow(data,4); absent.Remove("placedBody");
            string raw = PersistenceRawBytes(bad.GetCompound("placedBody"));
            PlacedLedgerLoadRows(ledger, new[] { valid, bad, nonCompound, absent });
            var saved = PlacedLedgerSaved(ledger); ledger.LoadWorldData(PersistenceNbtRoundtrip(saved)); var rows = PlacedLedgerGroups(ledger);
            Equal(4, rows.Count, "malformed/absent cosmetic neighbors retain healthy material groups");
            Equal(raw, PersistenceRawBytes(rows[1].GetCompound("placedBody")), "raw malformed compound witness survives native NBT cycles");
            Equal("literal malformed cosmetic witness", rows[2].GetString("placedBody"), "raw noncompound witness is not discarded or repaired");
            Equal(false, rows[3].ContainsKey("placedBody"), "historical absent body remains absent");
            byte[] rawJoin = PlacedLedgerSnapshot(ledger); ledger.ClearWorld(); peers.Mode(NetmodeID.MultiplayerClient,0);
            PlacedLedgerReceiveSnapshot(ledger,rawJoin); var joined = PlacedLedgerGroups(ledger);
            Equal(4,joined.Count,"initial snapshot retains healthy material beside malformed cosmetic witnesses");
            Equal(raw,PersistenceRawBytes(joined[1].GetCompound("placedBody")),"initial snapshot retains raw malformed compound witness");
            Equal("literal malformed cosmetic witness",joined[2].GetString("placedBody"),"compact join retains raw noncompound witness");
            Equal(false,joined[3].ContainsKey("placedBody"),"compact join does not opt absent historical body in");
            var oversized = PlacedLedgerRow(data,5); byte[] opaque = new byte[80 * 1024]; new Random(1729).NextBytes(opaque);
            oversized.GetCompound("placedBody")["opaqueCosmetic"] = opaque;
            peers.Mode(NetmodeID.Server,255); PlacedLedgerLoadRows(ledger,rows.Append(oversized));
            string oversizedRaw = PersistenceRawBytes(PlacedLedgerGroups(ledger)[4].GetCompound("placedBody"));
            byte[] boundedJoin = PlacedLedgerSnapshot(ledger);
            Equal(oversizedRaw,PersistenceRawBytes(PlacedLedgerGroups(ledger)[4].GetCompound("placedBody")),"bounded network witness does not rewrite full authoritative NBT");
            ledger.ClearWorld(); peers.Mode(NetmodeID.MultiplayerClient,0); PlacedLedgerReceiveSnapshot(ledger,boundedJoin);
            Equal(5,PlacedLedgerGroups(ledger).Count,"oversized optional cosmetics cannot prevent complete healthy material snapshot");
            var boundedWitness = PlacedLedgerGroups(ledger)[4].GetCompound("placedBody");
            Equal("placed_witness_size",boundedWitness.GetString("failure"),"existing witness wire bound yields a diagnostic instead of abandoning material");
            Equal("place",boundedWitness.GetString("bindingId"),"bounded failure retains explicit selection identity");
        });
    }

    private static byte[] PlacedLedgerLive(ulong revision, TagCompound row, byte[]? encodedBody = null)
    {
        using var stream = new MemoryStream(); using var writer = new BinaryWriter(stream, Encoding.UTF8, true);
        writer.Write(InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
        writer.Write((int)typeof(GeneratedPlacementLedgerSystem).GetField("PayloadVersion", PersistenceStatic)!.GetRawConstantValue()!);
        writer.Write(revision); writer.Write(false); writer.Write(row.GetString("groupId")); writer.Write(row.GetString("generatedItemId"));
        var cells = row.GetList<TagCompound>("cells"); writer.Write(cells.Count);
        foreach (var cell in cells) { writer.Write((byte)cell.GetInt("layer")); writer.Write(cell.GetInt("x")); writer.Write(cell.GetInt("y")); }
        writer.Write(row.ContainsKey("placedBody"));
        if (row.ContainsKey("placedBody")) {
            using var body = new MemoryStream(); TagIO.ToStream(row.GetCompound("placedBody"), body, compress: true);
            byte[] bytes = encodedBody ?? body.ToArray(); writer.Write(bytes.Length); writer.Write(bytes);
        }
        return stream.ToArray();
    }

    private static void PlacedBodyServerStreamAndSnapshotControls()
    {
        WithPlacedLedger((player, ledger) => {
            using var peers = new ReviewPeers(); var data = PlacedLedgerData("actual-server-placed-body"); peers.Register(data);
            peers.Mode(NetmodeID.Server,255); Terraria.Main.player[0] = player;
            var cell = Terraria.Main.tile[40,40]; cell.HasTile = false;
            Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!,40,40), "server captures native before-state");
            cell.HasTile = true; cell.TileType = TileID.Stone;
            Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "real server commit owns exact material");
            byte[] commit = peers.Sent.Single(p => p[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
            var saved = PlacedLedgerSaved(ledger); byte[] snapshot = PlacedLedgerSnapshot(ledger); peers.Sent.Clear();
            Equal(true, GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile,40,40), "real server removal moves material into durable return owner");
            byte[] remove = peers.Sent.Single(p => p[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
            Equal(1, PlacedLedgerSaved(ledger).GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "no material loss when native spawn unavailable");
            ledger.ClearWorld(); PlacedLedgerRegistryRows(peers).Clear(); peers.Sent.Clear(); peers.Mode(NetmodeID.MultiplayerClient,0);
            peers.Receive(commit,0); Equal(0, PlacedLedgerGroups(ledger).Count, "client sender cannot author placed mirror");
            peers.Receive(commit); peers.Receive(commit); Equal(1, PlacedLedgerGroups(ledger).Count, "server-issued live commit accepted exactly once");
            PlacedLedgerReceiveSnapshot(ledger,snapshot); Equal(1, PlacedLedgerGroups(ledger).Count, "initial snapshot of same server revision remains usable after live arrival");
            var wrongLiveDefinition = GeneratedItemData.FromJson(data.ToNetworkJson())!; wrongLiveDefinition.Name = "wrong late live definition";
            peers.Register(wrongLiveDefinition); MaterialClock(200); ledger.PostUpdateEverything();
            Equal(0,PlacedLedgerGroups(ledger).Single().GetString("definitionJson").Length,"live commit never borrows wrong same-ID definition");
            peers.Register(data); MaterialClock(201); ledger.PostUpdateEverything();
            Equal(data.ToNetworkJson(),PlacedLedgerGroups(ledger).Single().GetString("definitionJson"),"live commit hydrates after exact definition arrives late");
            peers.Receive(remove); peers.Receive(commit); peers.Receive(remove);
            Equal(0, PlacedLedgerGroups(ledger).Count, "removed group cannot resurrect from old commit/replay");
            Equal(0, PlacedLedgerSaved(ledger).GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "client mirrors never become material return owners");
            PlacedLedgerReceiveSnapshot(ledger,snapshot); Equal(0, PlacedLedgerGroups(ledger).Count, "stale initial snapshot cannot rewind live stream");
            ledger.ClearWorld(); peers.Receive(commit); peers.Register(data); MaterialClock(202); ledger.PostUpdateEverything();
            int ProjectionCount() => ((IEnumerable)typeof(GeneratedPlacementLedgerSystem).GetMethod("VisiblePlacedBodies",PersistenceStatic)!.Invoke(null,null)!).Cast<object>().Count();
            Equal(1,ProjectionCount(),"exact live selected group produces one projection");
            var replacedProjection = (TagCompound)saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single().Clone();
            replacedProjection.GetCompound("placedBody")["bindingId"] = "unknown_binding";
            peers.Receive(PlacedLedgerLive(3,replacedProjection)); MaterialClock(203); ledger.PostUpdateEverything();
            Equal(0,ProjectionCount(),"same-ID replacement cannot render a prior binding's cached root PNG");
            var misplacedGeometry = (TagCompound)saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single().Clone();
            misplacedGeometry.GetCompound("placedBody")["originX"] = 41;
            var neighbor = Terraria.Main.tile[41,40]; neighbor.HasTile=true; neighbor.TileType=TileID.Stone;
            peers.Receive(PlacedLedgerLive(4,misplacedGeometry)); MaterialClock(204); ledger.PostUpdateEverything();
            Equal(0,ProjectionCount(),"valid selection identity with a shifted witness cannot project onto an unowned neighbor");
            Equal(40,PlacedLedgerGroups(ledger).Single().GetList<TagCompound>("cells").Single().GetInt("x"),"declined cosmetics preserve exact material coordinate");
            Equal(41,PlacedLedgerGroups(ledger).Single().GetCompound("placedBody").GetInt("originX"),"invalid raw cosmetic witness is retained without normalization");
            MethodInfo selectedCell = typeof(GeneratedPlacementLedgerSystem).GetMethod("ShouldSuppressPlacedBody",PersistenceStatic)!;
            Equal(true,(bool)selectedCell.Invoke(null,new object[]{40,40})!,"declined pose cannot restore native body for accepted selected material");
            Equal(false,(bool)selectedCell.Invoke(null,new object[]{41,40})!,"unowned neighbor remains native after malformed witness");
            ledger.ClearWorld(); peers.Receive(PlacedLedgerLive(1, PlacedLedgerRow(data,1), new byte[] { 8, 7, 6 }));
            Equal(1, PlacedLedgerGroups(ledger).Count, "fully framed malformed cosmetic bytes do not erase valid material envelope");
            var malformed = PlacedLedgerGroups(ledger).Single().GetCompound("placedBody");
            Equal("placed_witness_decode_error", malformed.GetString("failure"), "malformed cosmetic transport is diagnosed");
            Equal(Convert.ToBase64String(new byte[] { 8,7,6 }), Convert.ToBase64String(malformed.GetByteArray("rawWitnessBytes")), "exact bad compressed bytes retained as raw witness");
            var healthy = PlacedLedgerRow(data,2); peers.Receive(PlacedLedgerLive(2,healthy));
            var overlapping = PlacedLedgerRow(data,3); overlapping["cells"] = healthy.GetList<TagCompound>("cells").Select(x => (TagCompound)x.Clone()).ToList();
            peers.Receive(PlacedLedgerLive(3,overlapping)); Equal(2, PlacedLedgerGroups(ledger).Count, "overlap rejected atomically");
            byte[] wrongVersion = PlacedLedgerLive(3,PlacedLedgerRow(data,4)); BitConverter.GetBytes(-1).CopyTo(wrongVersion,1); peers.Receive(wrongVersion);
            Equal(2, PlacedLedgerGroups(ledger).Count, "unsupported live payload version cannot mutate mirrors");
            byte[] truncated = PlacedLedgerLive(3,PlacedLedgerRow(data,4));
            bool refused = false; try { peers.Receive(truncated[..^1]); } catch (Exception) { refused = true; }
            Equal(true, refused, "truncated transport envelope remains refusal, not a cosmetic error");
            Equal(2, PlacedLedgerGroups(ledger).Count, "truncated envelope preserves existing healthy mirrors");
            bool snapshotRefused = false;
            try { PlacedLedgerReceiveSnapshot(ledger,snapshot[..^1]); } catch (Exception) { snapshotRefused = true; }
            Equal(true, snapshotRefused, "malformed initial snapshot rejected before publication");
            Equal(2, PlacedLedgerGroups(ledger).Count, "malformed snapshot cannot clear healthy material mirrors");
            // Envelope-only capacity cases do not read Tilemap storage. The existing
            // fixture owns/reverts world dimensions; widen InWorld just for these rows.
            Terraria.Main.maxTilesX = Terraria.Main.maxTilesY = 300;
            int maxGroups = (int)typeof(GeneratedPlacementLedgerSystem).GetField("MaxGroups",PersistenceStatic)!.GetRawConstantValue()!;
            int maxCells = (int)typeof(GeneratedPlacementLedgerSystem).GetField("MaxCells",PersistenceStatic)!.GetRawConstantValue()!;
            int perGroup = (int)typeof(GeneratedPlacementLedgerSystem).GetField("MaxCellsPerGroup",PersistenceStatic)!.GetRawConstantValue()!;
            string capacityDefinition = data.ToNetworkJson();
            TagCompound CapacityRow(int group, int start, int count) {
                return new TagCompound { ["groupId"] = group.ToString("x32"), ["generatedItemId"] = data.Id,
                    ["definitionJson"] = capacityDefinition,
                    ["cells"] = Enumerable.Range(start,count).Select(i => new TagCompound { ["layer"] = 1, ["x"] = 1 + i % 298, ["y"] = 1 + i / 298 }).ToList() };
            }
            void CapacityLoadRows(IEnumerable<TagCompound> rows) {
                // Capacity is a network envelope contract; NBT fidelity has its
                // separate small raw-witness observer above. Reuse one immutable
                // valid definition here instead of native-serializing it 8192 times.
                ledger.LoadWorldData(new TagCompound { ["infiniGeneratedPlacementLedgerV2"] = rows.ToList() });
            }
            peers.Mode(NetmodeID.SinglePlayer,0); CapacityLoadRows(Enumerable.Range(1,maxGroups).Select(i => CapacityRow(i,i-1,1)));
            byte[] groupFull = PlacedLedgerSnapshot(ledger); ledger.ClearWorld(); peers.Mode(NetmodeID.MultiplayerClient,0); PlacedLedgerReceiveSnapshot(ledger,groupFull);
            peers.Receive(PlacedLedgerLive(1,CapacityRow(maxGroups+1,maxGroups,1)));
            Equal(maxGroups,PlacedLedgerGroups(ledger).Count,"live group capacity exact-bound plus one refused");
            peers.Mode(NetmodeID.SinglePlayer,0); CapacityLoadRows(Enumerable.Range(1,maxCells/perGroup).Select(i => CapacityRow(i,(i-1)*perGroup,perGroup)));
            byte[] cellFull = PlacedLedgerSnapshot(ledger); ledger.ClearWorld(); peers.Mode(NetmodeID.MultiplayerClient,0); PlacedLedgerReceiveSnapshot(ledger,cellFull);
            peers.Receive(PlacedLedgerLive(1,CapacityRow(maxGroups+2,maxCells,1)));
            Equal(maxCells,PlacedLedgerGroups(ledger).Sum(g => g.GetList<TagCompound>("cells").Count),"live aggregate cell capacity exact-bound plus one refused");
            var replacement = CapacityRow(1,0,perGroup); peers.Receive(PlacedLedgerLive(2,replacement));
            Equal(maxCells,PlacedLedgerGroups(ledger).Sum(g => g.GetList<TagCompound>("cells").Count),"same-ID replacement at full capacity credits only its old cells");
            byte[] InitialRows(IEnumerable<TagCompound> rows, int? countOverride = null, int? versionOverride = null) {
                var list = rows.ToList(); using var output = new MemoryStream(); using var writer = new BinaryWriter(output,Encoding.UTF8,true);
                writer.Write(versionOverride ?? (int)typeof(GeneratedPlacementLedgerSystem).GetField("PayloadVersion",PersistenceStatic)!.GetRawConstantValue()!);
                writer.Write(3UL); writer.Write(countOverride ?? list.Count);
                foreach (var row in list) {
                    byte[] live = PlacedLedgerLive(3,row);
                    writer.Write(live[(sizeof(byte)+sizeof(int)+sizeof(ulong)+sizeof(bool))..]);
                }
                return output.ToArray();
            }
            foreach (var invalid in new[] {
                InitialRows(Array.Empty<TagCompound>(),versionOverride: -1),
                InitialRows(Array.Empty<TagCompound>(),countOverride: maxGroups+1),
                InitialRows(new[] { replacement,replacement }),
                InitialRows(Enumerable.Range(1,maxCells/perGroup).Select(i => CapacityRow(i,(i-1)*perGroup,perGroup))
                    .Append(CapacityRow(maxGroups+2,maxCells,1))) }) {
                bool rejected = false; try { PlacedLedgerReceiveSnapshot(ledger,invalid); } catch (InvalidDataException) { rejected = true; }
                Equal(true,rejected,"initial version/identity/group-capacity/aggregate-cell-capacity refuses atomically");
                Equal(maxCells,PlacedLedgerGroups(ledger).Sum(g => g.GetList<TagCompound>("cells").Count),"rejected initial controls preserve healthy existing mirror");
            }
        });
    }
}
