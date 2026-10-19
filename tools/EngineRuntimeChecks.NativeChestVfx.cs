#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Common.VFX;
using Terraria;
using Terraria.ID;
internal static partial class EngineRuntimeChecks
{
 private static void NativeChestPreservesAuthoredBodyLightVfxAndActorLiveness(){NativeChestPresentationScenario(TileID.Containers,0);NativeChestPresentationScenario(TileID.Containers2,0);NativeChestPresentationScenario(TileID.Containers,0,true);}
 private static void NativeChestPresentationScenario(int tileType,int style,bool mixedStyle=false){WithNativeChestWorld((player,ledger)=>WithVfxGeometryQueue((batch,texture,count,positions,colors)=>WithLighting((config,lights)=>{
  ulong tick=Terraria.Main.GameUpdateCount;var system=new InfiniDetachedVfxSystem();using var cache=new BorrowedSpriteCache();
  try{
   system.OnWorldUnload();config.ParticleSpawnMultiplier=1;config.PresentationLightMultiplier=0;
   var wire=PlacedVfxWire();var selected=wire["runtimeProgram"]!["bindings"]![0]!["usePolicy"]!["action"]!["placement"]!.AsObject();
   selected["tileId"]=tileType;selected["placeStyle"]=style;selected["placedBody"]=JsonSerializer.SerializeToNode(PlacedLedgerData("literal-body").RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!.PlacedBody,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase});
   selected["placedLight"]=new JsonObject{["strength"]=.625,["color"]="cyan"};
   var data=ParseMaterialElement(wire);GeneratedItemRegistryService.StampCurrentWorld(data);
   string path=Path.GetFullPath("native-chest-authored-vfx.png");cache.Textures.Add(path,Activator.CreateInstance(cache.Record,texture,0f,0L)!);data.VfxManifest.Assets![0].SpritePath=path;
   var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;string exact=data.ToNetworkJson();var source=ReviewItem(data);source.Item.createTile=tileType;source.Item.placeStyle=style;player.inventory[0]=source.Item;
   Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,placement,40,40),"literal composed native chest authorization");Terraria.Main.dedServ=true;NativeChestPlayerPlace(player);
   var actor=Terraria.Main.chest[Chest.FindChest(40,39)];actor.item[0]=new Item(ItemID.Wood,19);
   Terraria.Main.dedServ=false;MaterialClock(tick+1);ledger.PostUpdateEverything();system.PostUpdateEverything();
   Equal(true,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"authored PNG remains selected over actual native chest body");Equal(1,GeneratedPlacementLedgerSystem.VisiblePlacedBodies().Count(),"exact body projection survives native actor creation");
   Equal(1,lights.Count,"authored placed light reaches real native CPU lighting independent of VFX multiplier");Equal(1,OwnedMaterialQueue().Count,"authored independent placed VFX remains executable");
   typeof(InfiniDetachedVfxSystem).GetMethod("DrawMaterialSprites",PersistenceStatic)!.Invoke(null,new object[]{"BeforeProjectiles",batch,(Action)(()=>{})});Equal(2,count(),"actual authored chest VFX reaches native FNA CPU quad submission");
   Equal(false,Chest.DestroyChest(40,39),"native populated refusal never retires authored presentation");Equal(true,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"native populated refusal preserves body");
   if(mixedStyle){
    var cell=Terraria.Main.tile[41,40];short frame=cell.TileFrameX;cell.TileFrameX+=36;
    Equal(false,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"mixed-style native footprint cannot inherit authored body");
    Equal(1,PlacedLedgerGroups(ledger).Count,"mixed-style refusal retains original material claim");
    Equal(19,actor.item[0].stack,"mixed-style refusal preserves native inventory");cell.TileFrameX=frame;
    Equal(true,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"intact native style restores same actor projection");
   }
   int index=Chest.FindChest(40,39);Terraria.Main.chest[index]=new Chest{x=40,y=39,item=Enumerable.Range(0,40).Select(_=>new Item()).ToArray()};
   lights.Clear();MaterialClock(tick+2);ledger.PostUpdateWorld();ledger.PostUpdateEverything();system.PostUpdateEverything();
   Equal(false,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"foreign native actor cannot inherit authored body");Equal(0,lights.Count,"foreign native actor cannot inherit authored placed light");Equal(0,OwnedMaterialQueue().Count,"foreign native actor cannot inherit authored VFX activation");
   Equal(1,PlacedLedgerGroups(ledger).Count,"projection refusal cannot erase material claim");Equal(19,actor.item[0].stack,"projection refusal never clears original native contents");Equal(exact,data.ToNetworkJson(),"no authored body/light/VFX/behavior is rewritten or stripped");
  }finally{cache.Textures.Clear();system.OnWorldUnload();MaterialClock(tick);}
 })));}
}
