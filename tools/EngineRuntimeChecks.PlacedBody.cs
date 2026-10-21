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
            player.inventory[player.selectedItem] = ReviewItem(data).Item;
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
            byte[] snapshot = PlacedLedgerSnapshot(ledger);
            ledger.ClearWorld(); Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            PlacedLedgerReceiveSnapshot(ledger, snapshot);
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
