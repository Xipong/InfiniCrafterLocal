using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ParticleLibrary.Core.V3.Particles;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Uses only baseline APIs so test-only archived source builds and fails behaviorally.
    private static JsonObject PlacedVfxWire(bool library = false)
    {
        var data = PersistencePlacementData("placed-vfx-cpu-fixture");
        var wire = JsonNode.Parse(data.ToJson())!.AsObject();
        var placement = wire["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]!;
        placement["tileId"]=1;placement["wallId"]=-1;placement["placeStyle"]=0;
        placement["placedVfx"] = new JsonObject { ["minFrameY"] = 0, ["maxFrameY"] = 35 };
        var manifest = MaterialElementWire("source")["vfxManifest"]!.DeepClone().AsObject();
        var slot = library ? LibrarySlotWire() : manifest["slots"]![0]!.DeepClone().AsObject();
        slot["entityId"] = data.RuntimeProgram.ItemEntityId; slot["placementBindingId"] = "place";
        manifest["slots"] = new JsonArray(slot);
        if (library) manifest.Remove("assets");
        wire["vfxManifest"] = manifest;
        return wire;
    }

    private static void PlacedVfxDtoAndSelectorAdmission()
    {
        WithPlacedLedger((_, _) => {
            var valid = PlacedVfxWire();
            Equal(true, GeneratedItemData.FromJson(valid.ToJsonString()) is not null,"new opt-in wire must reach real joined native DTO admission");
            foreach (var selector in new JsonNode?[] { null, JsonValue.Create("missing"), JsonValue.Create(1) }) {
                var bad=valid.DeepClone(); bad["vfxManifest"]!["slots"]![0]!["placementBindingId"]=selector?.DeepClone();
                Equal(null,GeneratedItemData.FromJson(bad.ToJsonString()),"selector is exact nonnull accepted placement binding");
            }
            foreach (string key in new[]{"minFrameY","maxFrameY"}) {
                var bad=valid.DeepClone(); bad["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]!["placedVfx"]![key]=-1;
                Equal(null,GeneratedItemData.FromJson(bad.ToJsonString()),"frame bounds reject rather than clamp");
            }
            var plain=JsonNode.Parse(PersistencePlacementData("old").ToJson())!;
            Equal(false,plain.ToJsonString().Contains("placedVfx"),"absent old component remains absent");
            Equal(false,plain.ToJsonString().Contains("placementBindingId"),"absent old selector remains absent");
        });
    }

    private static void PlacedVfxTwoInstancesGateAndGenerationDraw()
    {
        WithPlacedLedger((player,ledger) => WithVfxGeometryQueue((batch,texture,count,positions,colors) => WithLighting((config,lights) => {
            ulong tick=Terraria.Main.GameUpdateCount; var system=new InfiniDetachedVfxSystem();
            using var cache=new BorrowedSpriteCache();
            try {
                system.OnWorldUnload(); config.ParticleSpawnMultiplier=1; config.PresentationLightMultiplier=1;
                var data=ParseMaterialElement(PlacedVfxWire()); GeneratedItemRegistryService.StampCurrentWorld(data);
                string path=Path.GetFullPath("placed-vfx-flame.png");
                cache.Textures.Add(path,Activator.CreateInstance(cache.Record,texture,0f,0L)!);
                data.VfxManifest.Assets![0].SpritePath=path;
                var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                player.inventory[player.selectedItem]=ReviewItem(data).Item;
                void Place(int x) {
                    var tile=Terraria.Main.tile[x,40];tile.HasTile=false;
                    Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,x,40),"authenticated real placement authorization");
                    tile.HasTile=true;tile.TileType=TileID.Stone;tile.TileFrameY=0;
                    Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"existing sole ledger commits");
                }
                InfiniItemVfxRuntime.OnPeriodic(player,data,data.RuntimeProgram.ItemEntityId,player.HeldItem);
                system.PostUpdateEverything();Equal(0,OwnedMaterialQueue().Count,"in-hand spriteElement selector never registers a placed emitter");
                Place(40);Place(44);
                player.dead=true; // placed source has no dependency on held owner survival
                void Update(ulong t) { MaterialClock(t);ledger.PostUpdateEverything();system.PostUpdateEverything(); }
                Update(tick+1);Equal(2,OwnedMaterialQueue().Count,"two independent committed sources emit once");
                Update(tick+1);Equal(2,OwnedMaterialQueue().Count,"same-world-tick repeated hook cannot duplicate");
                var first=OwnedMaterialQueue()[0]!;
                object binding=first.GetType().GetField("Binding",PersistenceInstance)!.GetValue(first)!;
                object generation=binding.GetType().GetProperty("Generation",PersistenceInstance)!.GetValue(binding)!;
                var draw=typeof(InfiniDetachedVfxSystem).GetMethod("DrawMaterialSprites",PersistenceStatic)!;
                draw.Invoke(null,new object[]{"BeforeProjectiles",batch,(Action)(()=>{})});
                Equal(4,count(),"both independent spriteElement sources reach actual FNA quad queue");
                AssertVfxNear(new Vector2(651,646)-Terraria.Main.screenPosition,VfxVertexCenter(positions(0)),"footprint center plus authored right/down offsets");
                AssertVfxNear(new Vector2(715,646)-Terraria.Main.screenPosition,VfxVertexCenter(positions(2)),"second footprint independent center");
                Terraria.Main.tile[40,40].TileFrameY=36; Update(tick+2);
                Equal(false,(bool)binding.GetType().GetProperty("IsLive",PersistenceInstance)!.GetValue(binding)!,"off retires exact activation");
                Equal(2,OwnedMaterialQueue().Count,"off first source retires attached flames; other source continues");
                Terraria.Main.tile[40,40].TileFrameY=0; Update(tick+3);
                Equal(false,(bool)binding.GetType().GetProperty("IsLive",PersistenceInstance)!.GetValue(binding)!,"old binding cannot resurrect on reenable");
                Equal(true,OwnedMaterialQueue().Cast<object>().Any(e=>e.GetType().GetField("Binding",PersistenceInstance)!.GetValue(e) is object b
                    && !ReferenceEquals(generation,b.GetType().GetProperty("Generation",PersistenceInstance)!.GetValue(b))),"reenable creates fresh generation");
                Equal(false,new GeneratedPlacementLedgerTile().CanDrop(40,40,TileID.Stone),"return ownership unchanged");
                Update(tick+4);Equal(1,PlacedLedgerGroups(ledger).Count,"exact one surviving material owner");
                var removed=Terraria.Main.tile[44,40];removed.HasTile=false; Update(tick+5);Equal(0,OwnedMaterialQueue().Count,"native support/removal gate stops source without Draw");
                ledger.ClearWorld();system.OnWorldUnload();Equal(0,OwnedMaterialQueue().Count,"world clear retires caches");
            } finally { cache.Textures.Clear();system.OnWorldUnload();MaterialClock(tick);player.dead=false; }
        })));
    }

    private static void PlacedVfxFinalPythonDeliveryRuns()
    {
        WithPlacedLedger((player,ledger)=>WithVfxGeometryQueue((batch,texture,count,positions,colors)=>WithLighting((config,lights)=>{
            ulong tick=Terraria.Main.GameUpdateCount;var system=new InfiniDetachedVfxSystem();using var cache=new BorrowedSpriteCache();
            try {
                system.OnWorldUnload();config.ParticleSpawnMultiplier=1;config.PresentationLightMultiplier=1;
                var data=GeneratedItemData.FromJson(File.ReadAllText("LocalGenerator/tests/fixtures/placed_vfx_final_wire.json"));
                if(data is null){ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson",out var error);throw new InvalidOperationException("actual Python final delivery rejected: "+error?.Message);}
                GeneratedItemRegistryService.StampCurrentWorld(data);
                var placement=data.RuntimeProgram.Bindings.Single(b=>b.Id=="alternate_install").UsePolicy.Action.Placement!;
                cache.Textures.Add(Path.GetFullPath(data.VfxManifest.Assets![0].SpritePath),Activator.CreateInstance(cache.Record,texture,0f,0L)!);
                player.inventory[player.selectedItem]=ReviewItem(data).Item;
                var tile=Terraria.Main.tile[40,40];tile.HasTile=false;
                Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"actual final Python wire authorizes unchanged native placement");
                tile.HasTile=true;tile.TileType=TileID.Stone;tile.TileFrameY=0;
                Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"actual final wire uses sole existing material commit");
                // Item/placed periodic material cadence uses world ticks, not PNG frames.
                MaterialClock(600);ledger.PostUpdateEverything();system.PostUpdateEverything();
                Equal(3,OwnedMaterialQueue().Count,"both authored independent flame assets and library burst registered from final delivery");
                MaterialClock(601);ledger.PostUpdateEverything();system.PostUpdateEverything();
                var draw=typeof(InfiniDetachedVfxSystem).GetMethod("DrawMaterialSprites",PersistenceStatic)!;
                draw.Invoke(null,new object[]{"BeforeProjectiles",batch,(Action)(()=>{})});
                Equal(4,count(),"actual Director output reaches existing independent textured FNA quads");
                Equal(2,lights.Count,"actual final light slot reaches native CPU lighting queue");
                cache.Textures.Clear();int before=count();draw.Invoke(null,new object[]{"BeforeProjectiles",batch,(Action)(()=>{})});
                Equal(before,count(),"unavailable textures are silent, never root-PNG substitutes");
            }finally{cache.Textures.Clear();system.OnWorldUnload();MaterialClock(tick);}
        })));
    }

    private static void PlacedVfxMirrorHydratesExactDefinitionAndRetires()
    {
        WithPlacedLedger((player,ledger)=>WithLighting((config,_)=>{
            using var peers=new ReviewPeers();var system=new InfiniDetachedVfxSystem();ulong tick=Terraria.Main.GameUpdateCount;
            try {
                system.OnWorldUnload();config.ParticleSpawnMultiplier=1;
                var data=ParseMaterialElement(PlacedVfxWire());GeneratedItemRegistryService.StampCurrentWorld(data);
                var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                peers.Register(data);peers.Mode(NetmodeID.Server,255);Terraria.Main.player[0]=player;
                player.inventory[player.selectedItem]=ReviewItem(data).Item;
                var tile=Terraria.Main.tile[40,40];tile.HasTile=false;
                Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"server alone authorizes material source");
                tile.HasTile=true;tile.TileType=TileID.Stone;tile.TileFrameY=0;
                Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"server alone commits material source");
                byte[] commit=peers.Sent.Single(p=>p[0]==InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
                peers.Sent.Clear();GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile,40,40);
                byte[] removal=peers.Sent.Single(p=>p[0]==InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedPlacedBodyLedger);
                ledger.ClearWorld();PlacedLedgerRegistryRows(peers).Clear();peers.Sent.Clear();peers.Mode(NetmodeID.MultiplayerClient,0);
                void Update(ulong t){MaterialClock(t);ledger.PostUpdateEverything();system.PostUpdateEverything();}
                peers.Receive(commit,0);Update(tick+1);Equal(0,OwnedMaterialQueue().Count,"untrusted client cannot create placed source mirror");
                peers.Receive(commit);Update(tick+2);Equal(0,OwnedMaterialQueue().Count,"late definition absence remains absent, no inferred flames");
                var wrong=GeneratedItemData.FromJson(data.ToNetworkJson())!;wrong.Name="same id wrong definition";peers.Register(wrong);
                Update(tick+3);Equal(0,OwnedMaterialQueue().Count,"same ID wrong hash cannot hydrate source");
                peers.Register(data);Update(tick+4);Equal(1,OwnedMaterialQueue().Count,"actual all-client hook emits after exact late hydration");
                object emission=OwnedMaterialQueue()[0]!;object binding=emission.GetType().GetField("Binding",PersistenceInstance)!.GetValue(emission)!;
                var saved=PlacedLedgerSaved(ledger);
                ledger.ClearWorld();ledger.LoadWorldData(saved);Update(tick+5);
                Equal(false,(bool)binding.GetType().GetProperty("IsLive",PersistenceInstance)!.GetValue(binding)!,"reload at identical coordinates/ID cannot resurrect retained old generation");
                Equal(1,OwnedMaterialQueue().Count,"replacement retained group starts independently");
                peers.Receive(removal);peers.Receive(commit);Update(tick+6);Equal(0,OwnedMaterialQueue().Count,"return/removal and stale network replay retire attached source");
                Equal(0,PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"client never acquires material return authority");
            }finally{system.OnWorldUnload();MaterialClock(tick);}
        }));
    }

    private static void PlacedVfxContinuousBurstBudgets()
    {
        WithPlacedLedger((player,ledger)=>WithLighting((config,_)=>{
            ulong tick=Terraria.Main.GameUpdateCount;var system=new InfiniDetachedVfxSystem();
            try {
                system.OnWorldUnload();config.ParticleSpawnMultiplier=1;
                var data=ParseMaterialElement(PlacedVfxWire());data.VfxManifest.Budget.MaxParticlesTotal=1;
                GeneratedItemRegistryService.StampCurrentWorld(data);
                player.inventory[player.selectedItem]=ReviewItem(data).Item;
                var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                foreach(int x in new[]{40,44}) {
                    var tile=Terraria.Main.tile[x,40];tile.HasTile=false;
                    Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,x,40),"burst auth");
                    tile.HasTile=true;tile.TileType=TileID.Stone;tile.TileFrameY=0;
                    Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"burst commit");
                }
                for(int i=1;i<=90;i++) {
                    MaterialClock(tick+(ulong)i);ledger.PostUpdateEverything();system.PostUpdateEverything();
                    var queue=OwnedMaterialQueue();
                    Equal(true,queue.Count>0&&queue.Count<=24,"indefinite source uses bounded concurrent records beyond historical maxTotal");
                    foreach(object emission in queue) {
                        var particles=(Array)emission.GetType().GetField("Particles",PersistenceInstance)!.GetValue(emission)!;
                        Equal(1,particles.Length,"each independent due burst consumes its own explicit maxParticlesTotal allowance");
                    }
                }
            } finally {system.OnWorldUnload();MaterialClock(tick);}
        }));
    }

    private static void PlacedVfxLibraryAndLightRealConsumers()
    {
        WithPlacedLedger((player,ledger) => WithVfxGeometryQueue((batch,texture,count,positions,colors) => WithLighting((config,lights) => {
            ulong tick=Terraria.Main.GameUpdateCount;var system=new InfiniDetachedVfxSystem();
            var type=typeof(InfiniDetachedVfxSystem);
            var buffersField=type.GetField("LibraryBuffers",PersistenceStatic)!;var starField=type.GetField("LibraryStar",PersistenceStatic)!;
            object? oldBuffers=buffersField.GetValue(null),oldStar=starField.GetValue(null);
            // Real native CPU buffers; only GPU allocations/upload/draw are absent.
            var bufferType=type.GetNestedType("LibraryBuffer",BindingFlags.NonPublic)!;
            var buffers=Array.CreateInstance(bufferType,4);
            for(int i=0;i<4;i++) {
                // GeometryBuffer constructor owns logging/GPU registration; CPU
                // storage is supplied at that resource boundary, not emission.
                var buffer=System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(bufferType);
                bufferType.GetField("Instances",PersistenceInstance)!.SetValue(buffer,new ParticleInstance[2048]);
                buffers.SetValue(buffer,i);
            }
            try {
                LibraryInvoke("LoadLibrary");system.OnWorldUnload();buffersField.SetValue(null,buffers);starField.SetValue(null,texture);
                config.EnableParticleLibraryBackend=true;config.ParticleSpawnMultiplier=1;config.PresentationLightMultiplier=1;
                var wire=PlacedVfxWire(true);
                var slots=wire["vfxManifest"]!["slots"]!.AsArray();
                slots.Add(new JsonObject { ["id"]="placed_light",["entityId"]="placed_item",["placementBindingId"]="place",
                    ["event"]="periodic",["rendererKind"]="lightCue",["anchor"]="self",["repeatEvery"]=1,["scale"]=1,["color"]=RgbWire(255,90,20) });
                slots[1]!["entityId"]=slots[0]!["entityId"]!.DeepClone();
                var data=ParseMaterialElement(wire);GeneratedItemRegistryService.StampCurrentWorld(data);
                var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                player.inventory[player.selectedItem]=ReviewItem(data).Item;
                var tile=Terraria.Main.tile[40,40];tile.HasTile=false;
                Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"library place auth");
                tile.HasTile=true;tile.TileType=TileID.Stone;tile.TileFrameY=0;
                Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"library place commit");
                MaterialClock(tick+1);ledger.PostUpdateEverything();system.PostUpdateEverything();
                Equal(1,OwnedMaterialQueue().Count,"placed library uses real native emission queue");
                var emission=OwnedMaterialQueue()[0]!;
                var state=emission.GetType().GetField("Library",PersistenceInstance)!.GetValue(emission)!;
                var particles=(ParticleInfo[])state.GetType().GetField("Particles",PersistenceInstance)!.GetValue(state)!;
                Equal(2,particles.Length,"real native ParticleInfo instances created, not a mocked emitter");
                MaterialClock(tick+2);system.PostUpdateEverything();
                particles=(ParticleInfo[])state.GetType().GetField("Particles",PersistenceInstance)!.GetValue(state)!;
                Equal(new System.Numerics.Vector2(650,647),particles[0].Position,"actual world-only library update integrates velocity drag acceleration");
                LibraryInvoke("DrawLibraryParticles","BeforeProjectiles",null);
                var instances=(ParticleInstance[])bufferType.GetField("Instances",PersistenceInstance)!.GetValue(buffers.GetValue(0))!;
                Equal(new Vector4(650,647,particles[0].Scale.X,particles[0].Scale.Y),instances[0].Position_Scale,"real existing instanced draw CPU queue consumes placed particles");
                Equal(2,lights.Count,"placed light reaches installed LightingEngine CPU queue on both world ticks");
                lights.Clear();InfiniItemVfxRuntime.OnPeriodic(player,data,data.RuntimeProgram.ItemEntityId,player.HeldItem);
                Equal(0,lights.Count,"held item excludes placed light");Equal(2,OwnedMaterialQueue().Count,"held item excludes placed library");
                tile.TileFrameY=36;MaterialClock(tick+32);ledger.PostUpdateEverything();system.PostUpdateEverything();
                Equal(0,OwnedMaterialQueue().Count,"world library bounded readiness/lifetime expires after gate off");Equal(0,lights.Count,"off prevents new light");
                bool prior=Terraria.Main.dedServ;Terraria.Main.dedServ=true;
                try {tile.TileFrameY=0;MaterialClock(tick+33);ledger.PostUpdateEverything();system.PostUpdateEverything();Equal(0,OwnedMaterialQueue().Count,"dedicated server silent");}
                finally{Terraria.Main.dedServ=prior;}
            }finally{system.OnWorldUnload();buffersField.SetValue(null,oldBuffers);starField.SetValue(null,oldStar);MaterialClock(tick);}
        })));
    }
}
