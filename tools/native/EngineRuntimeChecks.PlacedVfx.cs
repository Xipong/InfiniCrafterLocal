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
    // Explicit current test counterpart; the captured delivery stays immutable
    // and is refused by the strict reader. This is not a production importer.
    private static string PlacedVfxCurrentVisibilityControlJson()
    {
        string raw = File.ReadAllText("LocalGenerator/tests/fixtures/placed_vfx_final_wire.json");
        Equal(true, GeneratedItemData.FromJson(raw) is null, "retired visibility envelope is refused");
        var node = System.Text.Json.Nodes.JsonNode.Parse(raw)!;
        Equal("immediate", node["gameplay"]!["releaseTiming"]!.GetValue<string>(), "exact archived gameplay visibility");
        Equal("immediate", node["runtimeProgram"]!["itemUse"]!["releaseTiming"]!.GetValue<string>(), "exact archived item visibility");
        node["gameplay"]!.AsObject().Remove("releaseTiming");
        node["runtimeProgram"]!["itemUse"]!.AsObject().Remove("releaseTiming");
        node["runtimeProgram"]!["itemUse"]!["hideUseGraphic"] = true; // Preserve the explicit old hidden override.
        return node.ToJsonString();
    }

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
                var data=GeneratedItemData.FromJson(PlacedVfxCurrentVisibilityControlJson());
                if(data is null){ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson",out var error);throw new InvalidOperationException("current placed-VFX control rejected: "+error?.Message);}
                GeneratedItemRegistryService.StampCurrentWorld(data);
                var placement=data.RuntimeProgram.Bindings.Single(b=>b.Id=="alternate_install").UsePolicy.Action.Placement!;
                cache.Textures.Add(Path.GetFullPath(data.VfxManifest.Assets![0].SpritePath),Activator.CreateInstance(cache.Record,texture,0f,0L)!);
                player.inventory[player.selectedItem]=ReviewItem(data).Item;
                var tile=Terraria.Main.tile[40,40];tile.HasTile=false;
                Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"current envelope with captured placement authorizes unchanged native placement");
                tile.HasTile=true;tile.TileType=TileID.Stone;tile.TileFrameY=0;
                Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"placement control uses sole existing material commit");
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
            Vector2 camera=Terraria.Main.screenPosition;
            int width=Terraria.Main.screenWidth,height=Terraria.Main.screenHeight;
            try {
                system.OnWorldUnload();config.ParticleSpawnMultiplier=1;config.EnableScreenCulling=true;
                // Hydration is observed in view; an unrelated prior camera must
                // not turn this identity/retirement scenario into an offscreen test.
                Terraria.Main.screenPosition=new Vector2(500,500);Terraria.Main.screenWidth=320;Terraria.Main.screenHeight=240;
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
            }finally{
                system.OnWorldUnload();MaterialClock(tick);
                Terraria.Main.screenPosition=camera;Terraria.Main.screenWidth=width;Terraria.Main.screenHeight=height;
            }
        }));
    }

    private static void PlacedVfxContinuousBurstBudgets()
    {
        WithPlacedLedger((player,ledger)=>WithLighting((config,_)=>{
            ulong tick=Terraria.Main.GameUpdateCount;var system=new InfiniDetachedVfxSystem();
            Vector2 camera=Terraria.Main.screenPosition;
            int width=Terraria.Main.screenWidth,height=Terraria.Main.screenHeight;
            try {
                system.OnWorldUnload();config.ParticleSpawnMultiplier=1;config.EnableScreenCulling=true;
                // The burst budget applies to these two visible placements.
                Terraria.Main.screenPosition=new Vector2(500,500);Terraria.Main.screenWidth=320;Terraria.Main.screenHeight=240;
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
            } finally {
                system.OnWorldUnload();MaterialClock(tick);
                Terraria.Main.screenPosition=camera;Terraria.Main.screenWidth=width;Terraria.Main.screenHeight=height;
            }
        }));
    }

    // Only the source boundary is instrumented. Admission, deduplication,
    // cadence, source replacement and actual emission queues are production code.
    private sealed class CountingPlacedVfxSource(object generation,Vector2 position) : VfxSourceBinding
    {
        internal int Checks;
        internal bool Live=true;
        internal override object Generation=>generation;
        internal override bool IsLive { get { Checks++;return Live; } }
        internal override bool TryFrame(string anchor,out VfxSourceFrame frame)
        {
            frame=new(position,Vector2.UnitX,Vector2.Zero) {SourceCenter=position};
            return anchor=="self"&&IsLive;
        }
    }

    private static void PlacedVfxRegistrationAndViewportRegressions()
    {
        WithPlacedLedger((_,ledger)=>WithLighting((config,_)=>{
            var system=new InfiniDetachedVfxSystem();ulong tick=Terraria.Main.GameUpdateCount;
            Vector2 camera=Terraria.Main.screenPosition;
            int width=Terraria.Main.screenWidth,height=Terraria.Main.screenHeight;
            var matrix=Terraria.Main.GameViewMatrix;Vector2 zoom=matrix?.Zoom??Vector2.One;
            bool culling=config.EnableScreenCulling;
            try {
                system.OnWorldUnload();config.ParticleSpawnMultiplier=1;config.EnableScreenCulling=true;
                Terraria.Main.screenPosition=new Vector2(500,500);Terraria.Main.screenWidth=320;Terraria.Main.screenHeight=240;
                if(matrix is not null)matrix.Zoom=Vector2.One;
                var data=ParseMaterialElement(PlacedVfxWire());
                data.VfxManifest.Slots[0].RepeatEvery=1;
                string before=data.ToNetworkJson();
                int Registrations()=>(int)typeof(InfiniDetachedVfxSystem).GetField("PeriodicElements",PersistenceStatic)!
                    .GetValue(null)!.GetType().GetProperty("Count")!.GetValue(
                        typeof(InfiniDetachedVfxSystem).GetField("PeriodicElements",PersistenceStatic)!.GetValue(null))!;
                void Register(CountingPlacedVfxSource source)=>InfiniDetachedVfxSystem.RegisterPeriodicElements(
                    data,data.RuntimeProgram.ItemEntityId,"review-source",source,item:true,placementBindingId:"place");
                void Update(ulong at){MaterialClock(at);system.PostUpdateEverything();}

                for(int i=0;i<600;i++)Register(new(new object(),new Vector2(100000,100000)));
                Equal(0,Registrations(),"distant sources cannot occupy periodic registration capacity");
                var nearby=new CountingPlacedVfxSource(new object(),new Vector2(648,648));Register(nearby);
                Equal(1,Registrations(),"one nearby source admitted after 600 distant ones");
                Update(tick+1);Equal(1,OwnedMaterialQueue().Count,"nearby source reaches actual emission queue");
                Terraria.Main.screenPosition=new Vector2(100000,100000);Update(tick+2);
                Equal(0,Registrations(),"camera departure frees registration, not the material claim");
                Equal(true,nearby.Live,"viewport culling does not retire source generation");
                Equal(1,OwnedMaterialQueue().Count,"existing bounded emission is not killed by camera departure");
                Terraria.Main.screenPosition=new Vector2(500,500);Register(nearby);Update(tick+3);
                Equal(2,OwnedMaterialQueue().Count,"reentry resumes world cadence with no missed-tick replay");

                system.OnWorldUnload();
                var sources=Enumerable.Range(0,96).Select(_=>new CountingPlacedVfxSource(new object(),new Vector2(648,648))).ToArray();
                foreach(var source in sources)Register(source);
                foreach(var source in sources)source.Checks=0;
                for(int pass=0;pass<8;pass++)foreach(var source in sources)Register(source);
                Equal(96,Registrations(),"repeated source visits are deduplicated");
                Equal(true,sources.Sum(source=>source.Checks)<=96*8*4,"linear liveness visits, not a full sweep per source");

                system.OnWorldUnload();object sameGeneration=new();
                var retired=new CountingPlacedVfxSource(sameGeneration,new Vector2(648,648));Register(retired);
                retired.Live=false;
                var replacement=new CountingPlacedVfxSource(sameGeneration,new Vector2(648,648));Register(replacement);
                Equal(1,Registrations(),"same-tick slot rebinding replaces only the stale same-generation registration");
                Update(tick+4);
                object emitted=OwnedMaterialQueue()[0]!;
                Equal(true,ReferenceEquals(replacement,emitted.GetType().GetField("Binding",PersistenceInstance)!.GetValue(emitted)),
                    "real emission binds the replacement, never stale pose");
                system.OnWorldUnload();config.EnableScreenCulling=false;
                Register(new(new object(),new Vector2(100000,100000)));
                Equal(1,Registrations(),"explicit client culling opt-out remains authoritative");
                Equal(before,data.ToNetworkJson(),"scheduling does not rewrite authored data or transport identity");
                Equal(0,PlacedLedgerGroups(ledger).Count,"scheduler probe acquires no material ownership");

                var intersects=typeof(InfiniDetachedVfxSystem).GetMethod("PlacedVfxIntersectsViewport",PersistenceStatic)
                    ??throw new InvalidOperationException("placed VFX needs conservative viewport admission");
                bool Visible(Vector2 point,double radius,int w,int h,Vector2 z)=>(bool)intersects.Invoke(null,
                    new object[]{point,radius,new Vector2(500,500),w,h,z})!;
                Equal(false,Visible(new Vector2(100000,100000),0,320,240,Vector2.One),"distant static emitter is outside view");
                Equal(true,Visible(new Vector2(100000,100000),200000,320,240,Vector2.One),"authored travel radius can reach the view");
                Equal(true,Visible(new Vector2(100000,100000),0,0,0,Vector2.One),"unknown headless viewport is not evidence for culling");
                Equal(false,Visible(new Vector2(150,620),0,320,240,Vector2.One),"source outside unzoomed view plus margin");
                Equal(true,Visible(new Vector2(150,620),0,320,240,new Vector2(.5f)),"zoom-out expands the world viewport");
            } finally {
                system.OnWorldUnload();MaterialClock(tick);config.EnableScreenCulling=culling;
                Terraria.Main.screenPosition=camera;Terraria.Main.screenWidth=width;Terraria.Main.screenHeight=height;
                if(matrix is not null)matrix.Zoom=zoom;
            }
        }));
    }

    private static void PlacedVfxInactiveLedgerBroadPhaseRetainsRetirement()
    {
        WithPlacedLedger((player,ledger) => WithLighting((config,_) => {
            var system = new InfiniDetachedVfxSystem();
            Vector2 camera = Terraria.Main.screenPosition;
            int width = Terraria.Main.screenWidth, height = Terraria.Main.screenHeight;
            var matrix = Terraria.Main.GameViewMatrix;
            Vector2 zoom = matrix?.Zoom ?? Vector2.One;
            bool culling = config.EnableScreenCulling;
            try
            {
                system.OnWorldUnload();
                config.EnableScreenCulling = true;
                Terraria.Main.screenWidth = 320; Terraria.Main.screenHeight = 240;
                if (matrix is not null) matrix.Zoom = Vector2.One;
                var data = ParseMaterialElement(PlacedVfxWire());
                GeneratedItemRegistryService.StampCurrentWorld(data);
                var placement = data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                player.inventory[player.selectedItem] = ReviewItem(data).Item;
                var tile = Terraria.Main.tile[40,40]; tile.HasTile = false;
                Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"inactive source placement authorization");
                tile.HasTile = true; tile.TileType = TileID.Stone; tile.TileFrameY = 0;
                Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"inactive source material commit");

                Terraria.Main.screenPosition = new Vector2(100000,100000);
                Equal(0,GeneratedPlacementLedgerSystem.ActivePlacedVfxSources().Count(),
                    "distant inactive particle-only source does not allocate a binding");
                Equal(1,PlacedLedgerGroups(ledger).Count,"offscreen culling retains material owner");
                Terraria.Main.screenPosition = new Vector2(600,600);
                var active = GeneratedPlacementLedgerSystem.ActivePlacedVfxSources().Single();
                object firstGeneration = active.Binding.Generation;
                Equal(true,active.Binding.IsLive,"nearby placement activates normally");

                Terraria.Main.screenPosition = new Vector2(100000,100000);
                tile.TileFrameY = 36;
                Equal(0,GeneratedPlacementLedgerSystem.ActivePlacedVfxSources().Count(),
                    "existing source still checks offscreen frame gate and retires");
                Equal(false,active.Binding.IsLive,"offscreen gate change retires existing generation");
                tile.TileFrameY = 0;
                Equal(0,GeneratedPlacementLedgerSystem.ActivePlacedVfxSources().Count(),
                    "reenabled but still distant placement cannot allocate new source");
                Terraria.Main.screenPosition = new Vector2(600,600);
                var again = GeneratedPlacementLedgerSystem.ActivePlacedVfxSources().Single();
                Equal(false,ReferenceEquals(firstGeneration,again.Binding.Generation),
                    "returning to viewport creates a fresh generation after gate retirement");
                Equal(1,PlacedLedgerGroups(ledger).Count,"broad phase never mutates material ledger");
            }
            finally
            {
                system.OnWorldUnload();
                config.EnableScreenCulling = culling;
                Terraria.Main.screenPosition = camera; Terraria.Main.screenWidth = width; Terraria.Main.screenHeight = height;
                if (matrix is not null) matrix.Zoom = zoom;
            }
        }));
    }

    private static void PlacedVfxLibraryAndLightRealConsumers()
    {
        WithPlacedLedger((player,ledger) => WithVfxGeometryQueue((batch,texture,count,positions,colors) => WithLighting((config,lights) => {
            ulong tick=Terraria.Main.GameUpdateCount;var system=new InfiniDetachedVfxSystem();
            var type=typeof(InfiniDetachedVfxSystem);
            var buffersField=type.GetField("LibraryBuffers",PersistenceStatic)!;var texturesField=type.GetField("LibraryTextures",PersistenceStatic)!;
            object? oldBuffers=buffersField.GetValue(null),oldTextures=((System.Collections.Generic.Dictionary<string,Microsoft.Xna.Framework.Graphics.Texture2D>)texturesField.GetValue(null)!).ToArray();
            var libraryTextures=(System.Collections.Generic.Dictionary<string,Microsoft.Xna.Framework.Graphics.Texture2D>)texturesField.GetValue(null)!;
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
                LibraryInvoke("LoadLibrary");system.OnWorldUnload();buffersField.SetValue(null,buffers);libraryTextures.Clear();libraryTextures["ParticleLibrary/Assets/Textures/Star"]=texture;
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
            }finally{system.OnWorldUnload();buffersField.SetValue(null,oldBuffers);libraryTextures.Clear();foreach(var pair in (System.Collections.Generic.KeyValuePair<string,Microsoft.Xna.Framework.Graphics.Texture2D>[])oldTextures!)libraryTextures.Add(pair.Key,pair.Value);MaterialClock(tick);}
        })));
    }
    private static void PlacedVfxOffscreenLightUsesExactSelectors()
    {
        foreach (string renderer in new[] { "lightCue", "nativeLight" })
        WithPlacedLedger((player,ledger)=>WithLighting((config,lights)=> {
            var system=new InfiniDetachedVfxSystem();ulong tick=Terraria.Main.GameUpdateCount;
            Vector2 camera=Terraria.Main.screenPosition;int width=Terraria.Main.screenWidth,height=Terraria.Main.screenHeight;
            bool culling=config.EnableScreenCulling;
            try {
                system.OnWorldUnload();config.EnableScreenCulling=true;config.PresentationLightMultiplier=1;
                Terraria.Main.screenWidth=320;Terraria.Main.screenHeight=240;
                Terraria.Main.screenPosition=new Vector2(100000,100000);
                var wire=PlacedVfxWire();
                string entity=wire["vfxManifest"]!["slots"]![0]!["entityId"]!.GetValue<string>();
                var row=new JsonObject { ["id"]="placed_light",["entityId"]=entity,["placementBindingId"]="place",
                    ["event"]="periodic",["rendererKind"]=renderer,["anchor"]="self",["repeatEvery"]=1,["color"]=RgbWire(255,90,20) };
                if(renderer=="lightCue")row["scale"]=1;
                else {row["startTick"]=0;row["light"]=new JsonObject{["intensity"]=.6};}
                wire["vfxManifest"]!["slots"]=new JsonArray(row);
                wire["vfxManifest"]!.AsObject().Remove("assets");
                foreach(string selector in new[]{"placementBindingId","entityId"}) {
                    var invalid=wire.DeepClone();invalid["vfxManifest"]!["slots"]![0]![selector]="unrelated";
                    Equal(null,GeneratedItemData.FromJson(invalid.ToJsonString()),renderer+" rejects unmatched "+selector+" before acceptance");
                }
                var data=ParseMaterialElement(wire);GeneratedItemRegistryService.StampCurrentWorld(data);
                var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                player.inventory[player.selectedItem]=ReviewItem(data).Item;
                var tile=Terraria.Main.tile[40,40];tile.HasTile=false;
                Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),renderer+" offscreen placement authorized");
                tile.HasTile=true;tile.TileType=TileID.Stone;tile.TileFrameY=0;
                Equal(true,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),renderer+" offscreen placement committed");
                var source=GeneratedPlacementLedgerSystem.ActivePlacedVfxSources().Single();
                Equal(true,source.Binding.IsLive,renderer+" inactive offscreen light allocates real source");
                Equal(true,InfiniDetachedVfxSystem.MayNeedPlacedVfxFrame(source.View),renderer+" exact view keeps light uncullable");
                Equal(false,InfiniDetachedVfxSystem.MayNeedPlacedVfxFrame(source.View with { BindingId="unrelated" }),renderer+" another binding cannot activate light source");
                Equal(false,InfiniDetachedVfxSystem.MayNeedPlacedVfxFrame(source.View with { EntityId="unrelated" }),renderer+" another entity cannot activate light source");
                MaterialClock(tick+1);ledger.PostUpdateEverything();system.PostUpdateEverything();
                Equal(1,lights.Count,renderer+" actual Lighting queue receives offscreen light");
                var actual=(Vector3)lights[0]!.GetType().GetField("Color")!.GetValue(lights[0])!;
                Equal(new Color(255,90,20).ToVector3()*(renderer=="lightCue"?.2f:.6f),actual,renderer+" preserves selected intensity");
                Equal(1,PlacedLedgerGroups(ledger).Count,"light admission never changes material ownership");
                lights.Clear();tile.TileFrameY=36;MaterialClock(tick+2);ledger.PostUpdateEverything();system.PostUpdateEverything();
                Equal(0,lights.Count,renderer+" offscreen frame gate disables native light consumer");
                Equal(false,source.Binding.IsLive,renderer+" offscreen gate retires generation");
            } finally {
                system.OnWorldUnload();MaterialClock(tick);config.EnableScreenCulling=culling;
                Terraria.Main.screenPosition=camera;Terraria.Main.screenWidth=width;Terraria.Main.screenHeight=height;
            }
        }));
    }

}
