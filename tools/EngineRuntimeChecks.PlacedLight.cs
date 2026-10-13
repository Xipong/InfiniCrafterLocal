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

}
