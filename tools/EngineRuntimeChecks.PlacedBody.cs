using System;
using System.Linq;
using System.IO;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using Terraria.ID;
using Terraria.ModLoader.IO;
using InfiniCrafterLocal.Common.Systems;

internal static partial class EngineRuntimeChecks
{
    private static void PlacedBodyDtoRequiresExplicitLosslessTransform()
    {
        var property = typeof(RuntimePlacementSpec).GetProperty("PlacedBody");
        Equal(true, property is not null, "opt-in placed-body DTO is available");
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
        const string body = "{\"renderSizePx\":37,\"footprintAnchorX\":0.25,\"footprintAnchorY\":1,\"imagePivotX\":0.125,\"imagePivotY\":0.75,\"offsetXPx\":-13,\"offsetYPx\":17,\"rotationDegrees\":-45.5,\"flipX\":true,\"flipY\":false}";
        RuntimePlacementSpec Decode(string payload) => JsonSerializer.Deserialize<RuntimePlacementSpec>(payload, options)!;
        var baseline = new RuntimePlacementSpec { TileId = TileID.Stone, WallId = -1, PlaceStyle = 0 };
        Equal(false, JsonSerializer.Serialize(baseline, options).Contains("placedBody"), "absent historical body stays absent");
        var exact = Decode("{\"tileId\":1,\"wallId\":-1,\"placeStyle\":0,\"placedBody\":" + body + "}");
        exact.NormalizeAndValidate();
        using (JsonDocument encoded = JsonDocument.Parse(JsonSerializer.Serialize(exact, options)))
        {
            var result = encoded.RootElement.GetProperty("placedBody");
            Equal(37, result.GetProperty("renderSizePx").GetInt32(), "exact explicit size");
            Equal(-45.5f, result.GetProperty("rotationDegrees").GetSingle(), "literal rotation preserved");
            Equal(-13, result.GetProperty("offsetXPx").GetInt32(), "negative offset preserved");
            Equal(true, result.GetProperty("flipX").GetBoolean(), "explicit flip preserved");
        }
        foreach (string invalid in new[] {
            "{\"tileId\":1,\"placedBody\":null}",
            "{\"tileId\":1,\"placedBody\":{}}",
            "{\"tileId\":1,\"placedBody\":" + body.Replace("\"renderSizePx\":37", "\"renderSizePx\":0") + "}",
            "{\"tileId\":1,\"placedBody\":" + body.Replace("\"footprintAnchorX\":0.25", "\"footprintAnchorX\":1.01") + "}",
            "{\"tileId\":-1,\"wallId\":1,\"placedBody\":" + body + "}" })
        {
            bool rejected = false;
            try { Decode(invalid).NormalizeAndValidate(); }
            catch (Exception ex) when (ex is JsonException || ex is InvalidDataException || ex is ArgumentException) { rejected = true; }
            Equal(true, rejected, "invalid present transform rejected without neutral defaults: " + invalid);
        }
    }

    private static void PlacedBodyLedgerKeepsExplicitIdentityAcrossSaveAndNetwork()
    {
        var tileDataField = typeof(Terraria.ObjectData.TileObjectData).GetField("_data", PersistenceStatic)!;
        object? oldTileData = tileDataField.GetValue(null);
        var tileData = new System.Collections.Generic.List<Terraria.ObjectData.TileObjectData>();
        for (int i = 0; i < Terraria.ModLoader.TileLoader.TileCount; i++) tileData.Add(null!);
        tileDataField.SetValue(null, tileData);
        try
        {
        WithPersistenceTilemap((player, ledger) =>
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var data = PersistencePlacementData("placed-body-witness");
            InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.StampCurrentWorld(data);
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            placement.TileId = TileID.Stone; placement.WallId = -1;
            placement.PlacedBody = new RuntimePlacedBodySpec { RenderSizePx = 37,
                FootprintAnchorX = 0.25, FootprintAnchorY = 1, ImagePivotX = 0.125, ImagePivotY = 0.75,
                OffsetXPx = -13, OffsetYPx = 17, RotationDegrees = -45.5, FlipX = true, FlipY = false };
            var native = Terraria.Main.tile[40,40]; native.HasTile = false;
            var adjacent = Terraria.Main.tile[41,40]; adjacent.HasTile = false;
            PlacedNativeCall("Unload");
            Equal(false, GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"unsupported complete native adapter refuses before material mutation");
            Equal(false,native.HasTile,"refusal leaves native world untouched");
            var pending = (System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("PendingAuthorizations",PersistenceStatic)!.GetValue(null)!;
            Equal(0,pending.Count,"unsupported body acquires no placement authorization");
            ledger.PostSetupContent();
            Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, data, placement, 40,40), "explicit selected binding authorizes");
            native.HasTile = adjacent.HasTile = true; native.TileType = adjacent.TileType = TileID.Stone;
            Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "exact committed material group");
            MethodInfo? suppress = typeof(GeneratedPlacementLedgerSystem).GetMethod("ShouldSuppressPlacedBody", PersistenceStatic);
            Equal(true,suppress is not null,"literal placed-body suppression predicate exists");
            ledger.PostUpdateEverything();
            Equal(true,(bool)suppress!.Invoke(null,new object[] { 40,40 })!,"opted-in cell hides native body independent of PNG availability");
            Equal(false,(bool)suppress.Invoke(null,new object[] { 41,40 })!,"unowned same-type neighbor keeps native body");
            var groupOwner = (System.Collections.IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("Groups",PersistenceStatic)!.GetValue(null)!;
            object selectedGroup = groupOwner.Values.Cast<object>().Single();
            var presentation = (TagCompound)selectedGroup.GetType().GetProperty("PlacedBody",BindingFlags.Public|BindingFlags.Instance)!.GetValue(selectedGroup)!;
            presentation["failure"] = "fixture_cosmetic_pose_unavailable";
            Equal(true,(bool)suppress.Invoke(null,new object[] { 40,40 })!,"accepted selected body never silently restores native image on cosmetic pose failure");
            presentation.Remove("failure");
            var saved = new TagCompound(); ledger.SaveWorldData(saved);
            var group = saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0];
            Equal(1, group.GetList<TagCompound>("cells").Count, "opted-in exact footprint cannot absorb adjacent same-type mutation");
            Equal(true, group.ContainsKey("placedBody"), "explicit body witness persists beside the material owner");
            var witness = group.GetCompound("placedBody");
            Equal("place", witness.GetString("bindingId"), "selected binding identity persists");
            Equal(true, witness.GetString("definitionHash").Length == 64, "canonical placed definition identity persists");
            ledger.LoadWorldData(PersistenceNbtRoundtrip(saved));
            var reloaded = new TagCompound(); ledger.SaveWorldData(reloaded);
            Equal("place", reloaded.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0].GetCompound("placedBody").GetString("bindingId"), "native NBT reload keeps presentation ownership");
            using var stream = new MemoryStream();
            using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) ledger.NetSend(writer);
            stream.Position = 0; ledger.ClearWorld(); Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            using (var reader = new BinaryReader(stream, System.Text.Encoding.UTF8, true)) ledger.NetReceive(reader);
            var mirrored = new TagCompound(); ledger.SaveWorldData(mirrored);
            var mirror = mirrored.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0];
            Equal(data.Id, mirror.GetString("generatedItemId"), "initial network snapshot exact id");
            Equal("place", mirror.GetCompound("placedBody").GetString("bindingId"), "initial snapshot includes selected presentation witness");
            Equal(0, mirror.GetString("definitionJson").Length, "compact snapshot does not duplicate full definitions per group");
            var registryProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems", PersistenceStatic)!;
            object? oldRegistry = registryProperty.GetValue(null);
            using var registry = new InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService();
            registryProperty.SetValue(null,registry);
            try
            {
                registry.RegisterLocal(data, persist: false, ensureAssets: false);
                ledger.PostUpdateEverything();
                var hydrated = new TagCompound(); ledger.SaveWorldData(hydrated);
                var exactMirror = hydrated.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2")[0];
                Equal(true, exactMirror.GetString("definitionJson").Length > 0, "existing registry hydrates exact hash-bound placed definition");
            }
            finally { registryProperty.SetValue(null,oldRegistry); }
            Equal(stream.Length, stream.Position, "complete versioned snapshot consumed");
            // Restore the authoritative NBT claim and remove native occupancy without
            // CanDrop (support loss/replacement paths can bypass that material hook).
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            ledger.LoadWorldData(PersistenceNbtRoundtrip(saved));
            native.HasTile = false;
            ledger.PostUpdateWorld();
            var broken = new TagCompound(); ledger.SaveWorldData(broken);
            Equal(0, broken.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Count, "missing native footprint retires placed presentation");
            Equal(1, broken.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count, "support loss keeps one durable exact generated return");
        });
        }
        finally { new GeneratedPlacementLedgerSystem().Unload(); tileDataField.SetValue(null, oldTileData); }
    }
}
