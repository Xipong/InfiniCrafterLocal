using System;
using System.IO;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;
using System.Linq;

internal static partial class EngineRuntimeChecks
{
    private static void PlacedLightOwnsFootprintNotPlayerAndPersists()
    {
        WithPlacedLedger((player, ledger) => WithLighting((config, lights) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var data = PersistencePlacementData("authored-station-light");
            GeneratedItemRegistryService.StampCurrentWorld(data);
            var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
            var placement = JsonSerializer.Deserialize<RuntimePlacementSpec>("{\"tileId\":1,\"wallId\":-1,\"placeStyle\":0,\"placedLight\":{\"strength\":0.625,\"color\":\"cyan\"}}", options)!;
            data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement = placement;
            player.inventory[player.selectedItem] = ReviewItem(data).Item;
            var cell = Terraria.Main.tile[40,40]; cell.HasTile = false;
            config.PresentationLightMultiplier = 0; // gameplay light is independent of VFX tuning
            Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"light-only placement authorizes exact source");
            ledger.PostUpdateEverything(); Equal(0, lights.Count,"no committed group means no light even while held");
            cell.HasTile = true; cell.TileType = TileID.Stone;
            Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"light-only exact material commit");
            var neighbor = Terraria.Main.tile[41,40]; neighbor.HasTile=true; neighbor.TileType=TileID.Stone;
            player.position = new Vector2(64,64); // no light at owner/held item
            void AssertOwnLight() {
                lights.Clear(); ledger.PostUpdateEverything(); Equal(1,lights.Count,"one emission per exact group");
                object light = lights[0]!;
                Equal(new Point(40,40),(Point)light.GetType().GetField("Position")!.GetValue(light)!,"light at own footprint not player or neighbor");
                Equal(new Color(90,235,255).ToVector3()*0.625f,(Vector3)light.GetType().GetField("Color")!.GetValue(light)!,"explicit color/strength reach installed LightingEngine CPU queue");
            }
            AssertOwnLight();
            Equal(false,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,40),"light does not select PNG or suppress native sprite");
            var saved=PersistenceNbtRoundtrip(PlacedLedgerSaved(ledger));
            ledger.ClearWorld(); lights.Clear(); ledger.PostUpdateEverything(); Equal(0,lights.Count,"clear retires derived lights");
            ledger.LoadWorldData(saved); AssertOwnLight();
            Equal(false,new GeneratedPlacementLedgerTile().CanDrop(40,40,TileID.Stone),"break returns sole exact generated material");
            lights.Clear(); ledger.PostUpdateEverything(); Equal(0,lights.Count,"returned group immediately stops emitting");
            ledger.LoadWorldData(saved); cell.HasTile=false; lights.Clear(); ledger.PostUpdateEverything();
            Equal(0,lights.Count,"missing tile stops light before bounded return maintenance");
            ledger.PostUpdateWorld(); Equal(0,PlacedLedgerGroups(ledger).Count,"removed native footprint retires material");
            cell.HasTile=true; cell.TileType=TileID.Dirt; ledger.LoadWorldData(saved); lights.Clear();ledger.PostUpdateEverything();
            Equal(0,lights.Count,"foreign replacement tile cannot borrow committed light");
            ledger.PostUpdateWorld();Equal(0,PlacedLedgerGroups(ledger).Count,"foreign replacement retires exact old footprint");
            cell.TileType=TileID.Stone; ledger.LoadWorldData(saved); AssertOwnLight();
            ledger.Unload(); lights.Clear(); ledger.PostUpdateEverything(); Equal(0,lights.Count,"unload cannot recreate cached lighting");
        }));
    }

    private static void PlacedLightMirrorAuthenticatesServerAndExactDefinition()
    {
        WithPlacedLedger((player, ledger) => WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            var data = PersistencePlacementData("server-owned-light"); GeneratedItemRegistryService.StampCurrentWorld(data);
            var placement = JsonSerializer.Deserialize<RuntimePlacementSpec>("{\"tileId\":1,\"wallId\":-1,\"placeStyle\":0,\"placedLight\":{\"strength\":0.5,\"color\":\"red\"}}",
                new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!;
            data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement = placement;
            peers.Register(data); peers.Mode(NetmodeID.Server,255); Terraria.Main.player[0]=player;
            player.inventory[player.selectedItem] = ReviewItem(data).Item;
            var cell=Terraria.Main.tile[40,40]; cell.HasTile=false;
            Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"server owns light placement before-state");
            cell.HasTile=true; cell.TileType=TileID.Stone;
            Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"server commit");
            byte[] commit=peers.Sent.Single(p=>p[0]==InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
            byte[] snapshot=PlacedLedgerSnapshot(ledger); var saved=PlacedLedgerSaved(ledger);
            peers.Sent.Clear(); GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile,40,40);
            byte[] remove=peers.Sent.Single(p=>p[0]==InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
            BitConverter.GetBytes(4UL).CopyTo(remove,5);
            ledger.ClearWorld(); PlacedLedgerRegistryRows(peers).Clear(); peers.Sent.Clear(); peers.Mode(NetmodeID.MultiplayerClient,0);
            peers.Receive(commit,0); ledger.PostUpdateEverything(); Equal(0,lights.Count,"client cannot author light mirror");
            peers.Receive(commit); MaterialClock(500); ledger.PostUpdateEverything(); Equal(0,lights.Count,"missing definition cannot infer light");
            var wrong=GeneratedItemData.FromJson(data.ToNetworkJson())!; wrong.Name="untrusted replacement"; peers.Register(wrong);
            MaterialClock(501); ledger.PostUpdateEverything(); Equal(0,lights.Count,"same-ID wrong hash cannot provide light");
            peers.Register(data); MaterialClock(502); ledger.PostUpdateEverything(); Equal(1,lights.Count,"exact late definition hydrates independently of PNG");
            lights.Clear(); PlacedLedgerReceiveSnapshot(ledger,snapshot); MaterialClock(503); ledger.PostUpdateEverything(); Equal(1,lights.Count,"initial snapshot lights exact same group");
            var bad=(TagCompound)saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single().Clone();
            bad.GetCompound("placedBody")["definitionHash"]="foreign"; bad.GetCompound("placedBody")["unknown"]="retain literal";
            peers.Receive(PlacedLedgerLive(2,bad)); lights.Clear(); MaterialClock(504); ledger.PostUpdateEverything(); Equal(0,lights.Count,"malformed witness quarantines light only");
            Equal("retain literal",PlacedLedgerGroups(ledger).Single().GetCompound("placedBody").GetString("unknown"),"raw malformed witness preserved");
            Equal(1,PlacedLedgerGroups(ledger).Count,"light refusal does not lose material owner");
            peers.Receive(PlacedLedgerLive(3,saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single()));
            MaterialClock(505); ledger.PostUpdateEverything();
            peers.Receive(remove); peers.Receive(commit); lights.Clear(); ledger.PostUpdateEverything();
            Equal(0,lights.Count,"removal and stale commit cannot resurrect light");
            Equal(0,PlacedLedgerSaved(ledger).GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"client never owns return material");
        }));
    }

    private static void PlacedLightMultiCellAndWorldUnload()
    {
        WithPlacedLedger((player,ledger) => WithLighting((_,lights) => {
            Terraria.ObjectData.TileObjectData.Initialize();
            Terraria.Main.netMode=NetmodeID.SinglePlayer;
            var data=PlacedLedgerData("independent-workbench-light");
            var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            placement.PlacedLight=new RuntimePlacedLightSpec { Strength=1.5, Color="purple" };
            placement.TileId=TileID.WorkBenches;
            player.inventory[player.selectedItem]=ReviewItem(data).Item;
            var a=Terraria.Main.tile[40,40];var b=Terraria.Main.tile[41,40];a.HasTile=b.HasTile=false;
            Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"native workbench admits independent composed light");
            a.HasTile=b.HasTile=true;a.TileType=b.TileType=TileID.WorkBenches;a.TileFrameX=0;b.TileFrameX=18;a.TileFrameY=b.TileFrameY=0;
            Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"multi-cell footprint committed exactly once");
            ledger.PostUpdateEverything();Equal(1,lights.Count,"multi-cell and composed PNG still exactly one light");
            object light=lights[0]!;Equal(new Point(41,40),(Point)light.GetType().GetField("Position")!.GetValue(light)!,"deterministic own center cell");
            Equal(2,PlacedLedgerGroups(ledger).Single().GetList<TagCompound>("cells").Count,"exact workbench cells");
            ledger.OnWorldUnload();lights.Clear();ledger.PostUpdateEverything();Equal(0,lights.Count,"actual world unload dispatcher retires light");
            placement.TileId=TileID.TargetDummy; var target=Terraria.Main.tile[42,40];target.HasTile=false;
            Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,42,40),"independent actor refused before mutation");
        }));
    }

    private static void PlacedLightSurvivesOptionalPoseDecoderFailure()
    {
        WithPlacedLedger((player, ledger) => WithLighting((_, lights) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var data = PlacedLedgerData("light-independent-of-pose");
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            placement.PlacedLight = new RuntimePlacedLightSpec { Strength = 0.5, Color = "cyan" };
            player.inventory[player.selectedItem] = ReviewItem(data).Item;
            var target = Terraria.Main.tile[40,40]; target.HasTile = false;
            Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40), "composed placement admitted");
            target.HasTile = true; target.TileType = TileID.Stone;
            int visits = 0;
            PlacedDecode fail = (int x, int y, int type, int style, out int ox, out int oy, out int w, out int h, out int alt) => {
                visits++; ox = oy = w = h = alt = 0;
                throw new InvalidDataException("optional cosmetic pose decoder unavailable");
            };
            using (var hook = new MonoMod.RuntimeDetour.ILHook(
                typeof(GeneratedPlacementLedgerSystem).GetMethod("CapturePlacedBodyWitness", PersistenceStatic)!, il => {
                    var site = il.Body.Instructions.Single(ins => ins.OpCode == Mono.Cecil.Cil.OpCodes.Call
                        && ins.Operand is Mono.Cecil.MethodReference method
                        && method.DeclaringType.FullName == typeof(GeneratedPlacementLedgerSystem).FullName
                        && method.Name == "TryResolveNativeFootprint" && method.Parameters.Count == 9);
                    var cursor = new MonoMod.Cil.ILCursor(il); cursor.Goto(site); cursor.Remove(); cursor.EmitDelegate(fail);
                }))
                Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "optional pose failure preserves material commit");
            Equal(1,visits,"real optional decoder fault reached");
            ledger.PostUpdateEverything();
            Equal(1,lights.Count,"independent authored light survives cosmetic pose failure");
            Equal(new Point(40,40),(Point)lights[0]!.GetType().GetField("Position")!.GetValue(lights[0])!,"light remains at proven material footprint");
            Equal(0,GeneratedPlacementLedgerSystem.VisiblePlacedBodies().Count(),"failed PNG pose remains pending rather than repaired");
            var saved = PersistenceNbtRoundtrip(PlacedLedgerSaved(ledger)); ledger.ClearWorld(); ledger.LoadWorldData(saved);
            lights.Clear(); ledger.PostUpdateEverything(); Equal(1,lights.Count,"independent material geometry persists through NBT");
            Equal("native_footprint_decode_error",PlacedLedgerGroups(ledger).Single().GetCompound("placedBody").GetString("failure"),"literal cosmetic diagnostic retained");
        }));
    }

    private static void PlacedLightWitnessReloadRequiresTypedIdentity()
        => PlacedLightWitnessRequiresTypedIdentity(mirror: false);

    private static void PlacedLightWitnessMirrorRequiresTypedIdentity()
        => PlacedLightWitnessRequiresTypedIdentity(mirror: true);

    private static void PlacedLightWitnessRequiresTypedIdentity(bool mirror)
    {
        WithPlacedLedger((player, ledger) => WithLighting((_, lights) => {
            using var peers = new ReviewPeers();
            peers.Mode(NetmodeID.SinglePlayer,0);
            var data = PlacedLedgerData("typed-zero-witness");
            var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
            placement.TileId = TileID.Dirt; placement.PlaceStyle = 0;
            placement.PlacedLight = new RuntimePlacedLightSpec { Strength = 0.625, Color = "cyan" };
            player.inventory[player.selectedItem] = ReviewItem(data).Item;
            var cell = Terraria.Main.tile[40,40]; cell.HasTile = false;
            Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"typed witness real authorization");
            cell.HasTile = true; cell.TileType = TileID.Dirt;
            Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"typed witness real material commit");
            var saved = PlacedLedgerSaved(ledger);
            var valid = saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single();
            Equal(typeof(int),valid.GetCompound("placedBody")["tileType"].GetType(),"Dirt zero is present NBT int");
            Equal(typeof(int),valid.GetCompound("placedBody")["nativeStyle"].GetType(),"style zero is present NBT int");

            void Observe(string label, Action<TagCompound>? corrupt, bool accepted)
            {
                var row = (TagCompound)valid.Clone(); var witness = row.GetCompound("placedBody");
                corrupt?.Invoke(witness);
                witness["unknownWitnessBytes"] = new byte[] { 0, 7, 255 };
                string raw = PersistenceRawBytes(witness);
                string cells = PersistenceRawBytes(new TagCompound { ["cells"] = row.GetList<TagCompound>("cells") });
                ledger.ClearWorld(); PlacedLedgerRegistryRows(peers).Clear();
                if (mirror)
                {
                    peers.Register(data); peers.Mode(NetmodeID.MultiplayerClient,0);
                    peers.Receive(PlacedLedgerLive(1,row)); MaterialClock(600);
                }
                else
                {
                    peers.Mode(NetmodeID.SinglePlayer,0);
                    var input = new TagCompound { ["infiniGeneratedPlacementLedgerV2"] = new System.Collections.Generic.List<TagCompound> { row } };
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(input));
                }
                lights.Clear(); ledger.PostUpdateEverything();
                Equal(accepted ? 1 : 0,lights.Count,$"{(mirror ? "mirror" : "reload")} {label}: malformed witness cannot authenticate zero light");
                Equal(accepted && label != "PNG failure" ? 1 : 0,GeneratedPlacementLedgerSystem.VisiblePlacedBodies().Count(),label + ": body uses same identity/geometry projection; PNG failure stays pending");
                if ((label.StartsWith("tileType") || label.StartsWith("nativeStyle") || label == "valid typed zero")
                    && label != "nativeStyle wrong int")
                    Equal(accepted,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,40),label + ": native suppression shares selection admission");
                // Explicit foreign tile identity is an ordinary material replacement.
                // Missing/malformed optional identity must not retire healthy material.
                if (label != "tileType wrong int") ledger.PostUpdateWorld();
                var retained = PlacedLedgerGroups(ledger).Single();
                Equal(row.GetString("groupId"),retained.GetString("groupId"),label + ": exact material group retained");
                Equal(row.GetString("generatedItemId"),retained.GetString("generatedItemId"),label + ": material identity retained");
                Equal(cells,PersistenceRawBytes(new TagCompound { ["cells"] = retained.GetList<TagCompound>("cells") }),label + ": all material cells retained");
                Equal(raw,PersistenceRawBytes(retained.GetCompound("placedBody")),label + ": literal malformed witness retained");
                if (!mirror)
                {
                    Equal(data.ToNetworkJson(),retained.GetString("definitionJson"),label + ": exact material definition retained");
                    if (label.StartsWith("tileType") || label.StartsWith("nativeStyle"))
                        Equal(accepted,peers.Registry.TryGet(data.Id,out GeneratedItemData restored),label + ": restore cannot publish defaulted selection");
                }
                Console.WriteLine($"WITNESS-CASE PASS: {(mirror ? "mirror" : "reload")}: {label}; lights={lights.Count}; raw witness/material retained");
            }
            Observe("valid typed zero",null,true);
            foreach (string key in new[] { "nativeStyle", "tileType" })
            {
                Observe(key + " absent",w => w.Remove(key),false);
                Observe(key + " wrong int",w => w[key] = 1,false);
                foreach (object malformed in new object[] { (byte)0, (short)0, 0L, 0f, 0d, false, "0", new TagCompound() })
                    Observe(key + " wrong NBT type " + malformed.GetType().Name,w => w[key] = malformed,false);
            }
            foreach (string key in new[] { "version", "originX", "originY", "width", "height" })
            {
                Observe(key + " absent",w => w.Remove(key),false);
                Observe(key + " wrong NBT type",w => w[key] = 0L,false);
            }
            Observe("wrong origin",w => w["originX"] = 39,false);
            Observe("PNG failure",w => w["failure"] = "native_footprint_decode_error",true);
        }));
    }

    private static void PlacedLightDtoIsStrictAndIndependent()
    {
        Equal(true, typeof(RuntimePlacementSpec).GetProperty("PlacedLight") is not null, "independent placed light DTO exists");
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
        RuntimePlacementSpec Decode(string light, int tile = 1, int wall = -1) => JsonSerializer.Deserialize<RuntimePlacementSpec>(
            $"{{\"tileId\":{tile},\"wallId\":{wall},\"placeStyle\":0,\"placedLight\":{light}}}", options)!;
        var exact = Decode("{\"strength\":0.625,\"color\":\"cyan\"}"); exact.NormalizeAndValidate();
        Equal(false, JsonSerializer.Serialize(new RuntimePlacementSpec { TileId = 1 }, options).Contains("placedLight"), "absence does not create light");
        Equal(0.625, JsonDocument.Parse(JsonSerializer.Serialize(exact, options)).RootElement.GetProperty("placedLight").GetProperty("strength").GetDouble(), "exact strength survives native normalization");
        foreach (string bad in new[] { "null", "{}", "[]", "{\"strength\":0.5}", "{\"color\":\"cyan\"}",
            "{\"strength\":0,\"color\":\"cyan\"}", "{\"strength\":1.51,\"color\":\"cyan\"}",
            "{\"strength\":1.50000000000000000000001,\"color\":\"cyan\"}",
            "{\"strength\":0.009999999999999999999999,\"color\":\"cyan\"}",
            "{\"strength\":0.5,\"color\":\"unknown\"}", "{\"strength\":0.5,\"color\":\" Cyan \"}",
            "{\"strength\":true,\"color\":\"cyan\"}", "{\"strength\":0.5,\"color\":\"cyan\",\"foreign\":1}" })
        {
            bool refused = false; try { Decode(bad).NormalizeAndValidate(); }
            catch (Exception e) when (e is JsonException or InvalidDataException or ArgumentException) { refused = true; }
            Equal(true, refused, "present malformed light refused: " + bad);
        }
        bool wallRefused = false; try { Decode("{\"strength\":0.5,\"color\":\"cyan\"}", -1, 1).NormalizeAndValidate(); }
        catch (InvalidDataException) { wallRefused = true; }
        Equal(true, wallRefused, "walls are not tile light footprints");
    }
}
