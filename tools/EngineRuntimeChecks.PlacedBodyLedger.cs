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

    private static void PlacedBodyCosmeticDecodeCannotEraseMaterial()
    {
        WithPlacedLedger((player, ledger) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; var data = PlacedLedgerData("cosmetic-failure-material");
            player.inventory[player.selectedItem] = ReviewItem(data).Item;
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            var target = Terraria.Main.tile[40,40]; var adjacent = Terraria.Main.tile[41,40];
            target.HasTile = adjacent.HasTile = false;
            Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40,40), "real selected placement authorizes");
            Equal(false, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "unchanged native before-state cannot mint material");
            target.HasTile = adjacent.HasTile = true; target.TileType = adjacent.TileType = TileID.Stone;
            int decoderVisits = 0;
            PlacedDecode fail = (int x, int y, int type, int style, out int ox, out int oy, out int w, out int h, out int alt) => {
                decoderVisits++; ox = oy = w = h = alt = 0;
                throw new InvalidDataException("fixture post-native cosmetic decoder fault");
            };
            using (var hook = new MonoMod.RuntimeDetour.ILHook(
                typeof(GeneratedPlacementLedgerSystem).GetMethod("CapturePlacedBodyWitness", PersistenceStatic)!, il => {
                    var sites = il.Body.Instructions.Where(ins => ins.OpCode == Mono.Cecil.Cil.OpCodes.Call
                        && ins.Operand is Mono.Cecil.MethodReference method
                        && method.DeclaringType.FullName == typeof(GeneratedPlacementLedgerSystem).FullName
                        && method.Name == "TryResolveNativeFootprint" && method.Parameters.Count == 9).ToArray();
                    Equal(1, sites.Length, "one exact post-material cosmetic decoder call site");
                    var cursor = new MonoMod.Cil.ILCursor(il); cursor.Goto(sites[0]); cursor.Remove();
                    cursor.EmitDelegate(fail);
                }))
                Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "cosmetic fault cannot abandon native material success");
            Equal(1, decoderVisits, "cosmetic exception injection reached the actual post-material caller");
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

}
