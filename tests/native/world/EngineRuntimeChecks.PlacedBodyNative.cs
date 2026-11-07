#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Tiles;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;
using Terraria.ObjectData;

internal static partial class EngineRuntimeChecks
{
    // Headless CPU fixture: a genuine production ModTile is registered at a
    // controlled physical ID. The real symbolic resolver is never replaced.
    private sealed class OwnedTileFixture : IDisposable
    {
        internal static Dictionary<string, GeneratedOwnedTile> Map =>
            (Dictionary<string, GeneratedOwnedTile>)typeof(GeneratedOwnedTiles).GetField("Tiles",PersistenceStatic)!.GetValue(null)!;
        private readonly Dictionary<string, GeneratedOwnedTile> previous = new(Map);
        internal readonly GeneratedOwnedTile Tile;
        internal OwnedTileFixture()
        {
            var shape = new RuntimeOwnedTileSpec { Width = 1, Height = 1, Collision = "open", Support = "unanchored" };
            Tile = new GeneratedOwnedTile(shape);
            SetType(Tile, TileID.Stone);
            Map.Clear(); Map.Add(shape.Key, Tile);
        }
        internal static void SetType(GeneratedOwnedTile tile, int type)
            => typeof(ModTile).GetProperty("Type",BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance)!.SetValue(tile,checked((ushort)type));
        public void Dispose()
        { Map.Clear(); foreach (var row in previous) Map.Add(row.Key,row.Value); }
    }

    private static void OwnedTileShapeAndSymbolicIdentityStayExact()
    {
        WithPlacedLedger((_,_) => {
            var data = PlacedLedgerData("owned-structural-contract");
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            placement.NormalizeAndValidate();
            string key = placement.OwnedTile!.Key;
            Equal(TileID.Stone, GeneratedOwnedTiles.Resolve(placement), "owned shape resolves registered engine address");
            var tile = OwnedTileFixture.Map[key];
            try {
                OwnedTileFixture.SetType(tile, TileID.Dirt);
                Equal(TileID.Dirt, GeneratedOwnedTiles.Resolve(placement), "load-order change resolves through stable structural key");
                Equal(key, placement.OwnedTile.Key, "physical registration never changes authored identity");
                Equal(false, tile.PreDraw(40,40,null!), "owned ModTile suppresses only its own registration texture");
                Equal(0, tile.GetItemDrops(40,40).Count(), "ledger owns sole generated item return");
                Equal(false,tile.Slope(40,40),"hammer cannot change authored rectangular collision");
            }
            finally { OwnedTileFixture.SetType(tile, TileID.Stone); }
            var json = JsonNode.Parse(data.ToNetworkJson())!;
            var selected = json["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]!;
            foreach ((string field, JsonNode? value) in new (string, JsonNode?)[] {
                ("width",JsonValue.Create(0)),("height",JsonValue.Create(17)),("width",JsonValue.Create(true)),
                ("collision",JsonValue.Create("platform")),("support",JsonValue.Create("parent")) }) {
                var bad = json.DeepClone(); bad["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]!["ownedTile"]![field]=value;
                Equal(null,GeneratedItemData.FromJson(bad.ToJsonString()),"invalid authored structure refuses: "+field);
            }
            foreach (string field in new[]{"width","height","collision","support"}) {
                var bad=json.DeepClone();bad["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]!["ownedTile"]!.AsObject().Remove(field);
                Equal(null,GeneratedItemData.FromJson(bad.ToJsonString()),"missing structure never inferred: "+field);
            }
            foreach (string field in new[]{"tileId","wallId","placeStyle"}) {
                var bad=json.DeepClone();bad["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]![field]=1;
                Equal(null,GeneratedItemData.FromJson(bad.ToJsonString()),"owned cannot mix a native selector: "+field);
            }
            selected.AsObject().Remove("placedBody");
            Equal(null,GeneratedItemData.FromJson(json.ToJsonString()),"owned placement cannot be invisible without explicit sprite");
        });
    }

    private static void OwnedTileStructuralRegistrationUsesAuthoredShape()
    {
        WithPlacedLedger((_,_) => {
            bool solid=Terraria.Main.tileSolid[TileID.Stone], frame=Terraria.Main.tileFrameImportant[TileID.Stone], attach=Terraria.Main.tileNoAttach[TileID.Stone];
            try {
                TileObjectData.Initialize();
                foreach (var shape in new[] {
                    new RuntimeOwnedTileSpec { Width=1, Height=1, Collision="open", Support="unanchored" },
                    new RuntimeOwnedTileSpec { Width=3, Height=2, Collision="solid", Support="floor" },
                    new RuntimeOwnedTileSpec { Width=16, Height=16, Collision="open", Support="wall" } }) {
                    var tile=new GeneratedOwnedTile(shape);OwnedTileFixture.SetType(tile,TileID.Stone);
                    tile.SetStaticDefaults();
                    var actual=TileObjectData.GetTileData(TileID.Stone,0);
                    Equal(shape.Width,actual.Width,"authored rectangle width reaches real TileObjectData");
                    Equal(shape.Height,actual.Height,"authored rectangle height reaches real TileObjectData");
                    Equal(shape.Width/2,(int)actual.Origin.X,"technical placement origin is deterministic horizontal center");
                    Equal(shape.Height-1,(int)actual.Origin.Y,"technical placement origin is bottom row");
                    Equal(shape.Collision=="solid",Terraria.Main.tileSolid[TileID.Stone],"only explicit solid choice blocks movement");
                    var cell=Terraria.Main.tile[40,40];cell.HasTile=true;cell.TileType=TileID.Stone;
                    Equal(shape.Collision=="solid",Collision.SolidCollision(new Microsoft.Xna.Framework.Vector2(640,640),16,16),"native collision consumer executes authored solidity");
                    cell.HasTile=false;
                    Equal(shape.Support=="floor"?shape.Width:0,actual.AnchorBottom.tileCount,"floor support spans explicit footprint width");
                    Equal(shape.Support=="wall",actual.AnchorWall,"only explicit wall support requires backing wall");
                    Equal(0,actual.AnchorTop.tileCount+actual.AnchorLeft.tileCount+actual.AnchorRight.tileCount,"no inferred extra anchors");
                    Equal(false,actual.WaterDeath||actual.LavaDeath,"owned primitive has no inherited liquid death behavior");
                    Equal(true,actual.CoordinateHeights.All(height=>height==16),"footprint cell geometry is fixed technical projection");
                    Equal(false,tile.PreDraw(40,40,null!),"registration texture never becomes a placeholder draw");
                }
            }
            finally {Terraria.Main.tileSolid[TileID.Stone]=solid;Terraria.Main.tileFrameImportant[TileID.Stone]=frame;Terraria.Main.tileNoAttach[TileID.Stone]=attach;}
        });
    }

    private static void OwnedTileLegacyWorldRefusesWithoutSaveLoss()
    {
        WithPlacedLedger((player,ledger) => {
            var data=PlacedLedgerData("owned-live-before-refusal");
            var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            player.inventory[0]=ReviewItem(data).Item;
            Terraria.Main.netMode=NetmodeID.SinglePlayer;
            var cell=Terraria.Main.tile[40,40];cell.HasTile=false;
            Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"new owned source authorizes");
            cell.HasTile=true;cell.TileType=TileID.Stone;
            Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"new owned claim commits");
            var valid=PlacedLedgerSaved(ledger);
            var witness=valid.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single().GetCompound("placedBody");
            Equal(placement.OwnedTile!.Key,witness.GetString("ownedTileKey"),"persisted witness owns symbolic structure, not load order");
            var registered=OwnedTileFixture.Map[placement.OwnedTile.Key];
            try {
                OwnedTileFixture.SetType(registered,TileID.Dirt);cell.TileType=TileID.Dirt;
                ledger.LoadWorldData(PersistenceNbtRoundtrip(valid));ledger.PostUpdateEverything();
                Equal(1,GeneratedPlacementLedgerSystem.VisiblePlacedBodies().Count(),"saved symbolic structure follows current physical registration");
                Equal(TileID.Stone,witness.GetInt("tileType"),"historical numeric observation stays unchanged");
            }
            finally {OwnedTileFixture.SetType(registered,TileID.Stone);cell.TileType=TileID.Stone;ledger.LoadWorldData(valid);}
            var legacy=PersistenceNbtRoundtrip(valid);
            var row=legacy.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single();
            var old=JsonNode.Parse(row.GetString("definitionJson"))!;
            var selected=old["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]!.AsObject();
            selected.Remove("ownedTile");selected["tileId"]=TileID.Stone;
            row["definitionJson"]=old.ToJsonString();
            Equal(null,GeneratedItemData.FromJson(row.GetString("definitionJson")),"retired native+PNG is not silently interpreted as owned");
            string before=PersistenceRawBytes(legacy);
            bool loadRefused=false,saveRefused=false;
            try { ledger.LoadWorldData(legacy); } catch(InvalidDataException) { loadRefused=true; }
            var output=new TagCompound { ["keep"]="existing world" };
            try { ledger.SaveWorldData(output); } catch(InvalidDataException) { saveRefused=true; }
            Equal(true,loadRefused,"retired world rejected before material ledger clear");
            Equal(true,saveRefused,"failed world load cannot overwrite retained ledger with empty save");
            Equal(1,output.Count,"save refusal writes no replacement fields");
            Equal(before,PersistenceRawBytes(legacy),"original legacy claim bytes retained unchanged");
            ledger.LoadWorldData(valid);
            Equal(1,PlacedLedgerGroups(ledger).Count,"valid world reload recovers original live ownership");
        });
    }
}
