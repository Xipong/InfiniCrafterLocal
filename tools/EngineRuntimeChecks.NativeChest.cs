using System;
using System.Linq;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.ObjectData;
internal static partial class EngineRuntimeChecks {
 private static void NativeChestAdmission(){
 WithNativeChestWorld((player,ledger)=>{
  var source=NativeChestItem(player,"native-admission",tileType:tileType,style:0);var placement=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
  var row=TileObjectData.GetTileData(tileType,0);Equal(true,TileID.Sets.BasicChest[tileType],"native BasicChest metadata family");
  Equal(nameof(Chest.FindEmptyChest),row.HookCheckIfCanPlace.hook.Method.Name,"native capacity callback");Equal(nameof(Chest.AfterPlacement_Hook),row.HookPostPlaceMyPlayer.hook.Method.Name,"native inventory callback");
  Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,placement,40,40),"native family authorizes with independent authored body");
  Console.WriteLine($"NATIVE_CHEST_FAMILY tileId={tileType} supportedStyle=0");
 }); }
 private static void NativeChestBareTilesCannotCommit(){ WithNativeChestWorld((player,ledger)=>{
 var old=Terraria.Main.chest;bool solid=Terraria.Main.tileSolid[1], frame=Terraria.Main.tileFrameImportant[21];
 try { Terraria.Main.chest=new Chest[8000];TileObjectData.Initialize();Terraria.Main.tileSolid[1]=true;Terraria.Main.tileFrameImportant[21]=true;
 Terraria.Main.netMode=NetmodeID.SinglePlayer;
 for(int x=40;x<42;x++){var t=Terraria.Main.tile[x,41];t.HasTile=true;t.TileType=1;}
 var data=PlacedLedgerData("chest-bare-red");var p=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;p.TileId=21;p.PlaceStyle=0;
 player.inventory[0]=ReviewItem(data).Item;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,data,p,40,40),"real chest authorized");
 var obj=new TileObject{xCoord=40,yCoord=39,type=21,style=0,alternate=0};
 Equal(true,TileObject.Place(obj),"real native tiles written");
 Equal(-1,Chest.FindChest(40,39),"bare TileObject.Place did not create inventory");
 Equal(false,GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player),"tiles without authenticated native callback outcome cannot charge or commit");
 } finally{Terraria.Main.chest=old;Terraria.Main.tileSolid[1]=solid;Terraria.Main.tileFrameImportant[21]=frame;}
 }); }

 private static void WithNativeChestWorld(Action<Player,GeneratedPlacementLedgerSystem> check){WithPlacedLedger((player,ledger)=>{
 int[] chestDrops=(int[])Chest.chestItemSpawn.Clone(),chestDrops2=(int[])Chest.chestItemSpawn2.Clone(),dresserDrops=(int[])Chest.dresserItemSpawn.Clone();
 var guide=Terraria.Main.guideItem;int recipes=Recipe.maxRecipes;Terraria.Main.guideItem=new Item();Recipe.maxRecipes=0;
 var old=Terraria.Main.chest;bool solid=Terraria.Main.tileSolid[1], frame=Terraria.Main.tileFrameImportant[21], container=Terraria.Main.tileContainer[21],frame2=Terraria.Main.tileFrameImportant[467],container2=Terraria.Main.tileContainer[467],ded=Terraria.Main.dedServ;
 var hookFields=typeof(Terraria.ModLoader.TileLoader).GetFields(PersistenceStatic).Where(f=>f.Name.StartsWith("Hook")&&f.FieldType.IsArray&&f.GetValue(null) is null).ToArray();
 foreach(var f in hookFields)f.SetValue(null,Array.CreateInstance(f.FieldType.GetElementType()!,0));
 int my=Terraria.Main.myPlayer,tx=Player.tileTargetX,ty=Player.tileTargetY;
 try{for(int i=0;i<Terraria.Main.player.Length;i++)Terraria.Main.player[i]??=new Player{whoAmI=i};Terraria.Main.chest=new Chest[8000];TileObjectData.Initialize();Terraria.Main.tileSolid[1]=true;Terraria.Main.tileFrameImportant[21]=true;Terraria.Main.tileContainer[21]=true;Terraria.Main.tileFrameImportant[467]=true;Terraria.Main.tileContainer[467]=true;
 Terraria.Main.netMode=NetmodeID.SinglePlayer;Terraria.Main.myPlayer=0;Terraria.Main.dedServ=true;Player.tileTargetX=40;Player.tileTargetY=40;
 for(int x=40;x<42;x++){var t=Terraria.Main.tile[x,41];t.HasTile=true;t.TileType=1;}
 check(player,ledger);
 }finally{Array.Copy(chestDrops,Chest.chestItemSpawn,chestDrops.Length);Array.Copy(chestDrops2,Chest.chestItemSpawn2,chestDrops2.Length);Array.Copy(dresserDrops,Chest.dresserItemSpawn,dresserDrops.Length);Terraria.Main.guideItem=guide;Recipe.maxRecipes=recipes;foreach(var f in hookFields)f.SetValue(null,null);Terraria.Main.chest=old;Terraria.Main.tileSolid[1]=solid;Terraria.Main.tileFrameImportant[21]=frame;Terraria.Main.tileContainer[21]=container;Terraria.Main.tileFrameImportant[467]=frame2;Terraria.Main.tileContainer[467]=container2;Terraria.Main.dedServ=ded;Terraria.Main.myPlayer=my;Player.tileTargetX=tx;Player.tileTargetY=ty;}
 });}
 private static InfiniCrafterLocal.Content.Items.GeneratedItem NativeChestItem(Player player,string id="native-chest",int? nativeType=null,int tileType=TileID.Containers,int style=0){
 var data=PlacedLedgerData(id);var p=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;p.TileId=tileType;p.PlaceStyle=style;
 var item=nativeType is int type ? (InfiniCrafterLocal.Content.Items.GeneratedItem)new Item(type).ModItem : ReviewItem(data);
 if(nativeType.HasValue)GeneratedPrefixSetData(item,data);
 player.inventory[0]=item.Item;item.Item.stack=3;item.Item.createTile=tileType;item.Item.placeStyle=style;return item;
 }
 private static void NativeChestPlayerPlace(Player player){
 int tileType=player.HeldItem.createTile,style=player.HeldItem.placeStyle;
 var obj=new TileObject{xCoord=40,yCoord=39,type=tileType,style=style,alternate=0};
 typeof(Player).GetMethod("PlaceThing_Tiles_PlaceIt",PersistenceInstance)!.Invoke(player,new object[]{true,obj,tileType});
 }
 private static void NativeChestCanonicalStylesAndRefusals(){
 WithNativeChestWorld((player,ledger)=>{
  int tile=TileID.Containers,style=0;
  var tuple=(tile,style);
  var source=NativeChestItem(player,"native-family",tileType:tuple.Item1,style:tuple.Item2);var placement=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
  Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,placement,40,40),$"ordinary native chest family/style authorizes {tuple}");NativeChestPlayerPlace(player);
  int index=Chest.FindChest(40,39);Equal(true,index>=0,$"native family callback allocated actor {tuple}");
  var row=PlacedLedgerGroups(ledger).Single().GetCompound("nativeChest");Equal((int)tuple.Item1,row.GetInt("tileType"),"witness exact native type");Equal(tuple.Item2,row.GetInt("nativeStyle"),"witness exact native style");
  Equal(true,Terraria.ModLoader.ItemLoader.ConsumeItem(source.Item,player),"generic native outcome has exact debit receipt");
  var actor=Terraria.Main.chest[index];actor.name=$"native {tile}/{style}";actor.item[0]=new Item(ItemID.Wood,7);
  var saved=PersistenceNbtRoundtrip(PlacedLedgerSaved(ledger));using var memory=new MemoryStream();
  using(var writer=new BinaryWriter(memory,System.Text.Encoding.UTF8,true))typeof(Terraria.IO.WorldFile).GetMethod("SaveChests",PersistenceStatic)!.Invoke(null,new object[]{writer});
  Terraria.Main.chest=new Chest[8000];memory.Position=0;using(var reader=new BinaryReader(memory,System.Text.Encoding.UTF8,true))typeof(Terraria.IO.WorldFile).GetMethod("LoadChests",PersistenceStatic)!.Invoke(null,new object[]{reader});
  ledger.LoadWorldData(saved);actor=Terraria.Main.chest[Chest.FindChest(40,39)];Equal(7,actor.item[0].stack,"native style contents survive save/load");Equal($"native {tile}/{style}",actor.name,"native style name survives save/load");
  Equal(false,Chest.DestroyChest(40,39),"load-pending populated actor still refuses native removal");Equal(1,PlacedLedgerGroups(ledger).Count,"populated refusal retains exact material claim");
  actor.item[0].TurnToAir();bool gen=WorldGen.gen;try{WorldGen.gen=true;WorldGen.KillTile(40,40);}finally{WorldGen.gen=gen;}
  Equal(-1,Chest.FindChest(40,39),"native style empty mining removes actual inventory");
  using var pool=new NativeItemPoolState();Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item{active=true}).ToArray();Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];
  ledger.PostUpdateWorld();Equal(0,PlacedLedgerGroups(ledger).Count,"native style empty removal retires material group");Equal(1,PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"native style removal uses sole pending-return owner");
  Console.WriteLine($"PASS native style lifecycle {tile}/{style}");
 });
 // Refuse even valid vanilla styles before native tiles, inventory, or claims exist.
 foreach(var rejected in new[]{(Tile:TileID.Containers,Style:1),(Tile:TileID.Containers,Style:2),
   (Tile:TileID.Containers,Style:17),(Tile:TileID.Containers,Style:51),
   (Tile:TileID.Containers2,Style:0),(Tile:TileID.Containers2,Style:1),
   (Tile:TileID.Containers2,Style:16)})
 WithNativeChestWorld((player,ledger)=>{
  var source=NativeChestItem(player,"native-unsupported-style",tileType:rejected.Tile,style:rejected.Style);
  var placement=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
  Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,placement,40,40),$"reject unsupported native chest style {rejected}");
  Equal(false,GeneratedPlacementLedgerSystem.PreparePlacement(player,source.Data,placement),"unsupported style cannot bypass authorization through ordinary placement");
  NativeChestPlayerPlace(player); // An intercepted native placement must not bypass the refusal.
  Equal(-1,Chest.FindChest(40,39),"unsupported style never allocates a native inventory");
  Equal(false,Terraria.Main.tile[40,39].HasTile,"unsupported style never places a tile");
  Equal(0,PlacedLedgerGroups(ledger).Count,"unsupported style never commits a material claim");
 });
 }
 private static void NativeChestSinglePlayerOutcome(){WithNativeChestWorld((player,ledger)=>{
 var item=NativeChestItem(player);var p=item.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,item.Data,p,40,40),"SP intent before native mutation");
 NativeChestPlayerPlace(player);
 int index=Chest.FindChest(40,39);Equal(true,index>=0,"real native post callback allocated actor");
 Equal(40,Terraria.Main.chest[index].item.Length,"native 40 slot inventory, not a shadow ledger");
 Equal(true,Terraria.Main.chest[index].item.All(i=>i is not null),"native Item slot initialization");
 Equal(true,Terraria.ModLoader.ItemLoader.ConsumeItem(item.Item,player),"native outcome has one exact consumption receipt");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(item.Item,player),"native outcome cannot spend twice");
 var row=PlacedLedgerGroups(ledger).Single();Equal(4,row.GetList<Terraria.ModLoader.IO.TagCompound>("cells").Count,"exact four material cells");
 Equal(true,row.ContainsKey("nativeChest"),"lifecycle witness independent of optional body");
 Equal(true,row.ContainsKey("placedBody"),"authored body retained");
 });}

 private static void NativeChestCallbackFaultRollsBack(){WithNativeChestWorld((player,ledger)=>{
 var item=NativeChestItem(player,"chest-fault");var p=item.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,item.Data,p,40,40),"authorized callback fault test");
 using(var fault=new MonoMod.RuntimeDetour.ILHook(typeof(Chest).GetMethod(nameof(Chest.AfterPlacement_Hook))!,il=>{
 foreach(var ret in il.Body.Instructions.Where(i=>i.OpCode==Mono.Cecil.Cil.OpCodes.Ret).ToArray()){
 var cursor=new MonoMod.Cil.ILCursor(il);cursor.Goto(ret);cursor.EmitDelegate<Func<int,int>>(value=>value>=0?throw new InvalidOperationException("scoped callback fault after native actor allocation"):value);}
 }))NativeChestPlayerPlace(player);
 Equal(-1,Chest.FindChest(40,39),"failed callback cannot orphan newly created empty native actor");
 Equal(0,Enumerable.Range(0,4).Count(i=>Terraria.Main.tile[40+i/2,39+i%2].HasTile),"failed callback cannot leave free native cells");
 Equal(0,PlacedLedgerGroups(ledger).Count,"failed native attempt has no successful claim");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(item.Item,player),"failed native attempt never debits");
 });}

 private static void NativeChestBreakWaitsForNativeRemoval(){WithNativeChestWorld((player,ledger)=>{
 using var pool=new NativeItemPoolState();Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item{active=true}).ToArray();Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];
 var item=NativeChestItem(player,"chest-break");var p=item.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,item.Data,p,40,40),"break test authorization");NativeChestPlayerPlace(player);
 var chest=Terraria.Main.chest[Chest.FindChest(40,39)];chest.item[0]=new Item(ItemID.Wood,7);
 Equal(false,Chest.CanDestroyChest(40,39),"native contents refuse destruction");
 Equal(false,Chest.DestroyChest(40,39),"actual native destroy preserves populated actor");
 Equal(false,new GeneratedPlacementLedgerTile().CanDrop(40,39,21),"native chest drop suppressed even before destruction");
 Equal(1,PlacedLedgerGroups(ledger).Count,"drop suppression alone cannot release generated material while native actor survives");
 bool gen=WorldGen.gen;try{WorldGen.gen=true;WorldGen.KillTile(40,40);}
 finally{WorldGen.gen=gen;}
 Equal(true,ReferenceEquals(chest,Terraria.Main.chest[Chest.FindChest(40,39)]),"native populated mining keeps same actor");
 Equal(7,chest.item[0].stack,"native contents retained");
 chest.item[0].TurnToAir();player.chest=Chest.FindChest(40,39);
 try{WorldGen.gen=true;WorldGen.KillTile(40,40);}finally{WorldGen.gen=gen;}
 ledger.PostUpdateWorld();
 Equal(-1,Chest.FindChest(40,39),"native empty break removes actor");
 Equal(-1,player.chest,"native open empty chest closes during removal");
 Equal(0,PlacedLedgerGroups(ledger).Count,"generated material releases after actual native removal");
 Equal(1,PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"one durable native prefix-preserving generated return");
 });}

 private static void NativeChestMultiplayerAuthenticatedOutcome()=>NativeChestMultiplayerScenario("success",TileID.Containers,0);
 private static void NativeChestMultiplayerRefusalMatrix(){foreach(string scenario in new[]{"full","collision","capacity_race","callback_fault","partial_actor_fault","partial_reused_open_slot","changed_source","changed_prefix","replayed"})NativeChestMultiplayerScenario(scenario,TileID.Containers,0);}
 private static void NativeChestMultiplayerScenario(string scenario,int tileType=TileID.Containers,int style=0){WithNativeChestWorld((player,ledger)=>WithNativeChestRegisteredItem(type=>{
 using var peers=new ReviewPeers();using var states=new PlacedIdentityPeerState();
 var players=Terraria.Main.player;Array.Resize(ref players,256);Terraria.Main.player=players;
 using var network=new NativeChestNetworkScope();
 typeof(Terraria.ModLoader.Mod).GetProperty("File",PersistenceInstance)!.SetValue(peers.Mod,Activator.CreateInstance(typeof(Terraria.ModLoader.Core.TmodFile),PersistenceInstance,null,new object[]{"", "InfiniCrafterLocal",new Version(1,0)},null));
 void Deliver(byte[] bytes,int sender=256)=>network.Receive(sender,MessageID.ModPacket,w=>{w.Write((byte)0);w.Write(bytes);});
 var client=player;var local=NativeChestItem(client,"chest-mp",type,tileType,style);peers.Register(local.Data);
 var server=new Player{whoAmI=0,active=true,position=client.position};var remote=NativeChestItem(server,"chest-mp",type,tileType,style);
 peers.Mode(NetmodeID.MultiplayerClient,0);Terraria.Main.player[0]=client;
 Equal(false,local.CanUseItem(client),"client waits genuine Ready");byte[] intent=peers.Sent.Single();peers.Sent.Clear();
 states.Server();peers.Mode(NetmodeID.Server,255);Terraria.Main.player[0]=server;Terraria.Main.player[255]=new Player{whoAmI=255};Deliver(intent,0);
 byte[] ready=peers.Sent.Single();peers.Sent.Clear();
 states.Client();peers.Mode(NetmodeID.MultiplayerClient,0);Terraria.Main.player[0]=client;Deliver(ready);
 Equal(true,local.CanUseItem(client),"client Ready permits native placement attempt");NativeChestPlayerPlace(client);
 Equal(false,Terraria.Main.tile[40,39].HasTile,"MP never creates provisional free footprint");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(local.Item,client),"client never speculatively spends before server native outcome");
 byte[] request=peers.Sent.Single();peers.Sent.Clear();
 states.Server();peers.Mode(NetmodeID.Server,255);Terraria.Main.player[0]=server;
 IDisposable? race=null;
 if(scenario=="full")for(int i=0;i<8000;i++)Terraria.Main.chest[i]=new Chest{x=10,y=10};
 if(scenario=="collision")Terraria.Main.chest[100]=new Chest{x=40,y=39,item=Enumerable.Range(0,40).Select(_=>new Item()).ToArray()};
 if(scenario=="changed_source")server.inventory[0]=new Item(ItemID.WaterChest,3);
 if(scenario=="changed_prefix")remote.Item.prefix=PrefixID.Broken;
 if(scenario=="capacity_race")race=new MonoMod.RuntimeDetour.ILHook(typeof(Chest).GetMethod(nameof(Chest.CreateChest))!,il=>new MonoMod.Cil.ILCursor(il).EmitDelegate<Action>(()=>{for(int i=0;i<8000;i++)Terraria.Main.chest[i]=new Chest{x=10,y=10};}));
 if(scenario=="callback_fault")race=new MonoMod.RuntimeDetour.ILHook(typeof(Chest).GetMethod(nameof(Chest.CreateChest))!,il=>{foreach(var ret in il.Body.Instructions.Where(i=>i.OpCode==Mono.Cecil.Cil.OpCodes.Ret).ToArray()){var cursor=new MonoMod.Cil.ILCursor(il);cursor.Goto(ret);cursor.EmitDelegate<Func<int,int>>(r=>r>=0?throw new InvalidOperationException("scoped server callback fault"):r);}});
 if(scenario=="partial_reused_open_slot")Terraria.Main.player[1].chest=0;
 if(scenario is "partial_actor_fault" or "partial_reused_open_slot")race=new MonoMod.RuntimeDetour.ILHook(typeof(GeneratedPlacementLedgerSystem).GetMethod("ObserveNativeChestAllocation",PersistenceStatic)!,il=>{foreach(var ret in il.Body.Instructions.Where(i=>i.OpCode==Mono.Cecil.Cil.OpCodes.Ret).ToArray()){var cursor=new MonoMod.Cil.ILCursor(il);cursor.Goto(ret);cursor.EmitDelegate<Action>(()=>throw new InvalidOperationException("scoped server allocation fault before native coordinates/slots"));}});
 if(scenario=="replayed"){var stale=(byte[])request.Clone();Array.Clear(stale,5,8);Deliver(stale,0);Equal(-1,Chest.FindChest(40,39),"stale sequence cannot run native placement");}
 try{Deliver(request,0);Deliver(request,0);}finally{race?.Dispose();}
 if(scenario is not ("success" or "replayed")){
  if(scenario is "partial_actor_fault" or "partial_reused_open_slot")Equal(0,Terraria.Main.chest.Count(actor=>actor is not null),"partial native server allocation cannot leave an orphan actor");
  Equal(3,remote.Item.stack,scenario+": unsuccessful server native outcome never debits");Equal(0,PlacedLedgerGroups(ledger).Count,scenario+": no successful material claim");
  Equal(0,Enumerable.Range(0,4).Count(i=>Terraria.Main.tile[40+i/2,39+i%2].HasTile),scenario+": no provisional/free tiles survive");
  byte[] refused=peers.Sent.Single(p=>p[0]==InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedPlacementIntentReady);
  Equal(0,network.Sockets[0].Sent.Count(bytes=>bytes[2]==MessageID.ChestUpdates),scenario+": no bare native failure/refund is sent for a generated request");
  states.Client();peers.Mode(NetmodeID.MultiplayerClient,0);Terraria.Main.player[0]=client;Deliver(refused);Deliver(refused);
  Equal(3,local.Item.stack,scenario+": authenticated failure preserves the exact client source without compensation");Equal(0,PlacedLedgerGroups(ledger).Count,scenario+": client cannot create return authority");
  Console.WriteLine("PASS native chest MP refusal scenario: "+scenario);return;
 }
 Equal(true,Chest.FindChest(40,39)>=0,"authenticated server request runs real native placement");
 Equal(2,remote.Item.stack,"exact server-held source spent once on native success");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(remote.Item,server),"server authoritative debit retires its native receipt too");
 byte[] nativeResult=network.Sockets[0].Sent.Single(bytes=>bytes[2]==MessageID.ChestUpdates);
 byte[] nativeInventory=network.Sockets[0].Sent.Single(bytes=>bytes[2]==MessageID.SyncEquipment);
 Equal(1,PlacedLedgerGroups(ledger).Count,"one sole material group, duplicate request harmless");
 byte[] outcome=peers.Sent.Single(p=>p[0]==InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedPlacementIntentReady);
 var echoes=peers.Sent.Where(p=>p[0]!=InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedPlacementIntentReady).ToArray();peers.Sent.Clear();
 states.Client();peers.Mode(NetmodeID.MultiplayerClient,0);Terraria.Main.player[0]=client;
 Terraria.Main.chest=new Chest[8000];for(int x=40;x<42;x++)for(int y=39;y<41;y++){var cell=Terraria.Main.tile[x,y];cell.HasTile=false;}
 network.ReceiveFrame(256,nativeResult);network.ReceiveFrame(256,nativeInventory);
 Equal(true,Chest.FindChest(40,39)>=0,"actual native message34 result creates the client native inventory");
 foreach(var echo in echoes)Deliver(echo);Deliver(outcome);Deliver(outcome);
 Equal(2,client.inventory[0].stack,"native inventory synchronization plus authenticated exact outcome debits once");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(local.Item,client),"late native consume cannot debit twice");
 Equal(1,PlacedLedgerGroups(ledger).Count,"original client joins exact server group");
 }));}

 private static void NativeChestGlobalCanPlaceUsesNativeVeto(){foreach(bool allow in new[]{false,true})WithNativeChestWorld((player,ledger)=>{
  var field=typeof(Terraria.ModLoader.TileLoader).GetField("HookCanPlace",PersistenceStatic)!;var previous=field.GetValue(null);int calls=0;
  field.SetValue(null,new Func<int,int,int,bool>[] {(_,_,_)=>{calls++;return allow;}});using var restore=new PersistenceRestore(()=>field.SetValue(null,previous));
  var source=NativeChestItem(player,"native-global-veto",tileType:TileID.Containers,style:0);var placement=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
  Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,placement,40,40),"native veto hook is not a foreign post-placement actor callback");NativeChestPlayerPlace(player);
  Equal(true,calls>0,"real native CanPlace executed global veto");Equal(allow,Chest.FindChest(40,39)>=0,"native global veto decides actual placement");
  Equal(allow,Terraria.ModLoader.ItemLoader.ConsumeItem(source.Item,player),"only native global-veto success can debit");Equal(allow?1:0,PlacedLedgerGroups(ledger).Count,"native veto never invents a claim");
 });}
 private static void NativeChestCanonicalStylesRespectNativeHooks(){
 foreach(var selection in new[]{(Type:TileID.Containers,Style:0,Allow:true),
  (Type:TileID.Containers,Style:0,Allow:false)}){
 WithNativeChestWorld((player,ledger)=>{
  var source=NativeChestItem(player,"ordinary-container",tileType:selection.Type,style:selection.Style);
  var placement=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
  if(selection.Type==TileID.Containers && selection.Style==0){
   placement=new InfiniCrafterLocal.Common.Models.RuntimePlacementSpec{TileId=selection.Type,WallId=-1,PlaceStyle=selection.Style};
   source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement=placement;
  }
  var globalPost=typeof(Terraria.ModLoader.TileLoader).GetField("HookPlaceInWorld",PersistenceStatic)!;var oldPost=globalPost.GetValue(null);
  var globalCheck=typeof(Terraria.ModLoader.TileLoader).GetField("HookCanPlace",PersistenceStatic)!;var oldCheck=globalCheck.GetValue(null);
  int checks=0,posts=0;
  try{
   globalPost.SetValue(null,new Action<int,int,int,Item>[] {(_,_,_,_)=>posts++});
   globalCheck.SetValue(null,new Func<int,int,int,bool>[] {(_,_,_)=>{checks++;return selection.Allow;}});
   Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,placement,40,40),"ordinary tile/style uses existing placement with other mods present");
   NativeChestPlayerPlace(player);
   Equal(selection.Allow,Chest.FindChest(40,39)>=0,"native CanPlace result controls storage mutation");
   Equal(true,checks>0,"native CanPlace remains authoritative");
   Equal(selection.Allow?1:0,posts,"native PlaceInWorld remains an ordinary placement callback");
   Equal(selection.Allow,Terraria.ModLoader.ItemLoader.ConsumeItem(source.Item,player),"only native placement success owns a debit");
   if(selection.Allow){
    var row=PlacedLedgerGroups(ledger).Single();
    Equal(selection.Type,row.GetCompound("nativeChest").GetInt("tileType"),"witness keeps authored native container type");
    Equal(selection.Style,row.GetCompound("nativeChest").GetInt("nativeStyle"),"witness keeps authored native container style");
    Equal(placement.PlacedBody is not null,row.ContainsKey("placedBody"),"presentation remains an independent explicit choice");
   }else Equal(0,PlacedLedgerGroups(ledger).Count,"native placement veto cannot create a material claim");
  }finally{globalPost.SetValue(null,oldPost);globalCheck.SetValue(null,oldCheck);}
 });
 }
 }
 private static void NativeChestMetadataAndCapacityRefuseBeforeMutation(){WithNativeChestWorld((player,ledger)=>{
 var item=NativeChestItem(player,"chest-admission-matrix");var placement=item.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 var data=TileObjectData.GetTileData(21,0);Console.WriteLine($"CHEST_ANCHOR bottom={(int)data.AnchorBottom.type} full={data.CoordinateFullWidth}x{data.CoordinateFullHeight} top={data.AnchorTop.tileCount} left={data.AnchorLeft.tileCount} right={data.AnchorRight.tileCount}");
 var original=data.HookPostPlaceMyPlayer;
 foreach(string fault in new[]{"delegate","multicast","badReturn","badResponse","coordinates","override","wrongStyle"}){
 try{
  var changed=original;
  switch(fault){case "delegate":changed.hook=(x,y,t,s,d,a)=>Chest.AfterPlacement_Hook(x,y,t,s,d,a);break;
   case "multicast":changed.hook+=original.hook;break;case "badReturn":changed.badReturn=0;break;case "badResponse":changed.badResponse=1;break;
   case "coordinates":changed.processedCoordinates=true;break;case "override":data.HookPlaceOverride=original;break;case "wrongStyle":placement.PlaceStyle=1;break;}
  data.HookPostPlaceMyPlayer=changed;
  Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,item.Data,placement,40,40),"uncertified native family/tuple refuses: "+fault);
  Equal(false,Terraria.Main.tile[40,39].HasTile,"unknown callback never mutates");
 }finally{data.HookPostPlaceMyPlayer=original;data.HookPlaceOverride=default;placement.PlaceStyle=0;}
 }
 var detached=new InfiniCrafterLocal.Common.Models.RuntimePlacementSpec{TileId=21,WallId=-1,PlaceStyle=0};
 Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,item.Data,detached,40,40),"detached same-type placement cannot erase the actual binding authored body/light/VFX");
 var plain=PersistencePlacementData("unselected-callback-family");plain.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement=new InfiniCrafterLocal.Common.Models.RuntimePlacementSpec{TileId=TileID.Dressers,WallId=-1,PlaceStyle=0};
 player.inventory[0]=ReviewItem(plain).Item;
 Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,plain,plain.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!,40,40),"uncertified 3x2 dresser callback remains fail closed without presentation too");
 player.inventory[0]=item.Item;
 for(int i=0;i<8000;i++)Terraria.Main.chest[i]=new Chest{x=10,y=10};
 Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,item.Data,placement,40,40),"full native chest capacity refuses before authorization/mutation");
 Terraria.Main.chest=new Chest[8000];Terraria.Main.chest[1]=new Chest{x=40,y=39};
 Equal(false,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,item.Data,placement,40,40),"existing coordinate refuses before mutation");
 });}
 private static void NativeChestSupportAndMalformedClaimsStayNative(){WithNativeChestWorld((player,ledger)=>{
 using var pool=new NativeItemPoolState();Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item{active=true}).ToArray();Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];
 var dropField=typeof(Terraria.ModLoader.TileLoader).GetField("HookCanDrop",PersistenceStatic)!;var old=dropField.GetValue(null);int drops=0;
 Func<int,int,int,bool> drop=(x,y,type)=>{drops++;Equal(1,PlacedLedgerGroups(ledger).Count,"native Drop-before-Destroy cannot release early");return new GeneratedPlacementLedgerTile().CanDrop(x,y,type);};
 dropField.SetValue(null,new[]{drop});using var restore=new PersistenceRestore(()=>dropField.SetValue(null,old));
 var source=NativeChestItem(player,"chest-support");var p=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,p,40,40),"support test intent");NativeChestPlayerPlace(player);
 var actor=Terraria.Main.chest[Chest.FindChest(40,39)];actor.item[4]=new Item(ItemID.Wood,19);
 for(int x=40;x<42;x++){var support=Terraria.Main.tile[x,41];support.HasTile=false;}
 typeof(WorldGen).GetMethod("CheckChest",PersistenceStatic)!.Invoke(null,new object[]{40,39,21});ledger.PostUpdateWorld();
 Equal(19,actor.item[4].stack,"native populated support loss retains slots");Equal(1,PlacedLedgerGroups(ledger).Count,"native populated support loss retains material");Equal(0,drops,"intact populated floating chest never enters native drop");
 var cell=Terraria.Main.tile[40,39];cell.HasTile=false;ledger.PostUpdateWorld();
 var damaged=PlacedLedgerGroups(ledger).Single();Equal("damaged_native_footprint",damaged.GetString("nativeChestDiagnostic"),"foreign partial damage explicitly diagnosed");
 Equal(0,PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"damaged populated actor never becomes invented refund");
 // Restore this fixture's foreign damage, then exercise legitimate empty support loss.
 cell.HasTile=true;actor.item[4].TurnToAir();
 typeof(WorldGen).GetMethod("CheckChest",PersistenceStatic)!.Invoke(null,new object[]{40,39,21});ledger.PostUpdateWorld();
 Equal(-1,Chest.FindChest(40,39),"native empty support loss destroys actor");Equal(true,drops>0,"actual native support-loss Drop hook observed");
 Equal(0,PlacedLedgerGroups(ledger).Count,"actual complete removal releases exact group");Equal(1,PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"one durable return after support loss");
 });}

 private static void NativeChestMalformedNativeSaveCannotPruneContents(){foreach(string scenario in new[]{"bound","foreign","malformed"})NativeChestMalformedNativeSaveScenario(scenario);}
 private static void NativeChestMalformedNativeSaveScenario(string scenario){WithNativeChestWorld((player,ledger)=>{
 var source=NativeChestItem(player,"chest-damaged-save");var p=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,p,40,40),"damaged save intent");NativeChestPlayerPlace(player);
 var actor=Terraria.Main.chest[Chest.FindChest(40,39)];actor.item[5]=new Item(ItemID.Wood,23);
 if(scenario=="foreign"){actor=new Chest{x=40,y=39,item=Enumerable.Range(0,40).Select(_=>new Item()).ToArray()};actor.item[5]=new Item(ItemID.Wood,23);Terraria.Main.chest[Chest.FindChest(40,39)]=actor;}
 if(scenario=="malformed"){var malformed=PlacedLedgerSaved(ledger);malformed.GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementLedgerV2")[0]["nativeChest"]="literal malformed lifecycle witness";ledger.LoadWorldData(malformed);}
 var cell=Terraria.Main.tile[40,39];cell.HasTile=false;ledger.PostUpdateWorld();
 var claim=PersistenceNbtRoundtrip(PlacedLedgerSaved(ledger));Terraria.Main.chest[7]=new Chest(true){x=20,y=20};
 using var memory=new MemoryStream();using(var writer=new BinaryWriter(memory,System.Text.Encoding.UTF8,true))typeof(Terraria.IO.WorldFile).GetMethod("SaveChests",PersistenceStatic)!.Invoke(null,new object[]{writer});
 Equal(true,Terraria.Main.chest.Any(current=>ReferenceEquals(current,actor)),"native save must not prune an owned damaged inventory");
 Equal(true,Terraria.Main.chest[7] is null,"foreign invalid vanilla chest keeps ordinary native pruning");
 Terraria.Main.chest=new Chest[8000];memory.Position=0;using(var reader=new BinaryReader(memory))typeof(Terraria.IO.WorldFile).GetMethod("LoadChests",PersistenceStatic)!.Invoke(null,new object[]{reader});
 ledger.LoadWorldData(claim);ledger.PostUpdateWorld();
 Equal(23,Terraria.Main.chest[Chest.FindChest(40,39)].item[5].stack,"native inventory stream preserves contents even in diagnosed foreign damage");
 Equal(1,PlacedLedgerGroups(ledger).Count,"diagnosed native damage keeps original material claim after legitimate load");
 Equal(false,Terraria.Main.tile[40,39].HasTile,"save/load never repairs authored footprint or creates cells");
 });}

 private static void NativeChestCallbackCollisionIsNotCallbackSuccess(){WithNativeChestWorld((player,ledger)=>{
 var source=NativeChestItem(player,"chest-collision-race");var p=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,p,40,40),"race admission initially has free capacity and no coordinate collision");
 var foreign=new Chest(true){x=40,y=39};foreign.item[0]=new Item(ItemID.Wood,17);
 using(var race=new MonoMod.RuntimeDetour.ILHook(typeof(Chest).GetMethod(nameof(Chest.AfterPlacement_Hook))!,il=>new MonoMod.Cil.ILCursor(il).EmitDelegate<Action>(()=>Terraria.Main.chest[100]=foreign)))NativeChestPlayerPlace(player);
 Equal(0,PlacedLedgerGroups(ledger).Count,"native callback -1 cannot be promoted by a later same-coordinate actor");
 Equal(true,ReferenceEquals(foreign,Terraria.Main.chest[100]),"foreign collision actor is not owned rollback material");Equal(17,foreign.item[0].stack,"foreign native contents untouched");
 Equal(0,Enumerable.Range(0,4).Count(i=>Terraria.Main.tile[40+i/2,39+i%2].HasTile),"only the failed attempt's new cells rolled back");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(source.Item,player),"collision outcome cannot spend");
 });}

 private static void NativeChestReceiptCannotSpendAnotherInstance(){WithNativeChestWorld((player,ledger)=>{
 var original=NativeChestItem(player,"chest-receipt-owner");var p=original.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,original.Data,p,40,40),"receipt owner before native mutation");NativeChestPlayerPlace(player);
 var other=NativeChestItem(player,"chest-receipt-foreign");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(other.Item,player),"a different held generated instance cannot spend the original native outcome");
 player.inventory[0]=original.Item;var reincarnated=new Player{whoAmI=0,active=true,position=player.position};reincarnated.inventory[0]=original.Item;Terraria.Main.player[0]=reincarnated;
 Equal(false,GeneratedPlacementLedgerSystem.TryConsumePlacementReceipt(reincarnated),"replacement native player incarnation cannot claim the original receipt");
 Terraria.Main.player[0]=player;Equal(true,Terraria.ModLoader.ItemLoader.ConsumeItem(original.Item,player),"only original native player and item spend the captured outcome once");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(original.Item,player),"exact receipt is one shot");
 });}

 private static void NativeChestLiveActorReplacementCannotRebind(){WithNativeChestWorld((player,ledger)=>{
 var source=NativeChestItem(player,"chest-live-incarnation");var p=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,p,40,40),"live identity intent");NativeChestPlayerPlace(player);
 int index=Chest.FindChest(40,39);var actor=Terraria.Main.chest[index];actor.item[0]=new Item(ItemID.Wood,19);
 Equal(true,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"authored body selected for genuine native actor");
 var foreign=new Chest{x=40,y=39,item=Enumerable.Range(0,40).Select(_=>new Item()).ToArray()};foreign.item[0]=new Item(ItemID.StoneBlock,3);Terraria.Main.chest[index]=foreign;
 ledger.PostUpdateWorld();Equal(false,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"foreign same-coordinate slot reuse is not the original body actor");
 Equal(1,PlacedLedgerGroups(ledger).Count,"foreign native replacement retains original exact material claim");Equal(19,actor.item[0].stack,"original contents never cleared");Equal(3,foreign.item[0].stack,"foreign contents never cleared");
 Terraria.Main.chest[index]=null!;Terraria.Main.chest[7]=actor;ledger.PostUpdateWorld();
 Equal(false,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"runtime array relocation is not a legitimate world-load rebind");
 actor.item[0].TurnToAir();Equal(true,Chest.DestroyChest(40,39),"native owner can remove relocated empty actor");
 for(int x=40;x<42;x++)for(int y=39;y<41;y++){var cell=Terraria.Main.tile[x,y];cell.HasTile=false;}
 ledger.PostUpdateWorld();Equal(1,PlacedLedgerGroups(ledger).Count,"destruction cannot adopt a live relocated actor as authenticated removal");
 Equal(0,PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"unobserved replacement/relocation cannot invent a generated refund");
 });}

 private static void NativeChestUntrackedPlayerPathCannotCreateStorage(){WithNativeChestWorld((player,ledger)=>{
 var source=NativeChestItem(player,"chest-untracked");NativeChestPlayerPlace(player);
 Equal(-1,Chest.FindChest(40,39),"untracked/stale native player path cannot create free generated storage");Equal(false,Terraria.Main.tile[40,39].HasTile,"no authorization means no native mutation");
 Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(source.Item,player),"untracked attempt cannot debit");
 });}

 private static void NativeChestPartialActorInitializationRollsBackOwnedSlot(){WithNativeChestWorld((player,ledger)=>{
 var source=NativeChestItem(player,"chest-partial-native-actor");var p=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,p,40,40),"partial native actor fault intent");
 using(var fault=new MonoMod.RuntimeDetour.ILHook(typeof(GeneratedPlacementLedgerSystem).GetMethod("ObserveNativeChestAllocation",PersistenceStatic)!,il=>{foreach(var ret in il.Body.Instructions.Where(i=>i.OpCode==Mono.Cecil.Cil.OpCodes.Ret).ToArray()){var cursor=new MonoMod.Cil.ILCursor(il);cursor.Goto(ret);cursor.EmitDelegate<Action>(()=>throw new InvalidOperationException("scoped fault after actual native actor assignment before coordinates/slots"));}}))NativeChestPlayerPlace(player);
 Equal(0,Terraria.Main.chest.Count(actor=>actor is not null),"only the observed newly allocated incomplete empty native actor is aborted");
 Equal(0,Enumerable.Range(0,4).Count(i=>Terraria.Main.tile[40+i/2,39+i%2].HasTile),"partial native actor fault aborts owned new cells");Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(source.Item,player),"partial native actor initialization cannot debit");
 });}

 private static void NativeChestUnsupportedGroundRefusesBeforeVanillaDrop(){WithNativeChestWorld((player,ledger)=>{
 using var pool=new NativeItemPoolState();Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item()).ToArray();Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];
 var random=Terraria.Main.rand;Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(17);bool gen=WorldGen.gen;WorldGen.gen=false;typeof(Chest).GetMethod("Initialize",PersistenceStatic)!.Invoke(null,null);
 try{
 var source=NativeChestItem(player,"chest-unsupported-ground");var p=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
 Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,p,40,40),"source intent captured before native support changes");
 for(int x=40;x<42;x++){var support=Terraria.Main.tile[x,41];support.HasTile=false;}
 NativeChestPlayerPlace(player);
 Equal(0,Terraria.Main.item.Count(item=>item.active&&item.type==ItemID.Chest),"predictable native support refusal cannot create a vanilla chest compensation/drop");
 Equal(0,Terraria.Main.chest.Count(actor=>actor is not null),"predictable support refusal never allocates a native actor");Equal(false,Terraria.Main.tile[40,39].HasTile,"unsupported native target never mutates");Equal(false,Terraria.ModLoader.ItemLoader.ConsumeItem(source.Item,player),"native support refusal never debits");
 }finally{Terraria.Main.rand=random;WorldGen.gen=gen;}
 });}

 private static void NativeChestMaintenanceBoundsNativeActorsAndDefinitionReads(){WithNativeChestWorld((player,ledger)=>{
 var data=PersistencePlacementData("native-chest-maintenance");var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;placement.TileId=21;placement.WallId=-1;placement.PlaceStyle=0;
 string json=data.ToNetworkJson(),hash=InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService.DefinitionIdentity(data);var rows=new System.Collections.Generic.List<Terraria.ModLoader.IO.TagCompound>();
 for(int i=0;i<40;i++){
  int x=20+i%10*4,y=20+i/10*4;for(int sx=x;sx<x+2;sx++){var support=Terraria.Main.tile[sx,y+2];support.HasTile=true;support.TileType=1;}
  Equal(true,WorldGen.PlaceChest(x,y+1,21,false,0)>=0,"actual native inventory for maintenance fixture");
  var cells=new System.Collections.Generic.List<Terraria.ModLoader.IO.TagCompound>();for(int cx=x;cx<x+2;cx++)for(int cy=y;cy<y+2;cy++)cells.Add(new(){["layer"]=1,["x"]=cx,["y"]=cy});
  rows.Add(new(){["groupId"]=(i+1).ToString("x32"),["generatedItemId"]=data.Id,["definitionJson"]=json,["cells"]=cells,["nativeChest"]=new Terraria.ModLoader.IO.TagCompound{["version"]=1,["x"]=x,["y"]=y,["tileType"]=21,["nativeStyle"]=0,["bindingId"]="place",["definitionHash"]=hash}});
 }
 ledger.LoadWorldData(new Terraria.ModLoader.IO.TagCompound{["infiniGeneratedPlacementLedgerV2"]=rows});int visits=0;
 using(var count=new MonoMod.RuntimeDetour.ILHook(typeof(GeneratedPlacementLedgerSystem).GetMethod("NativeChestHealthy",PersistenceStatic)!,il=>new MonoMod.Cil.ILCursor(il).EmitDelegate<Action>(()=>visits++))){ledger.PostUpdateWorld();Equal(true,visits<=32,"native chest reconciliation is bounded per world tick");ledger.PostUpdateWorld();}
 var groups=PlacedIdentityMap("Groups").Values.Cast<object>().ToArray();Equal(40,groups.Count(group=>group.GetType().GetProperty("BoundChest")!.GetValue(group) is Chest),"bounded maintenance eventually binds all actual native actors");
 int parses=0;using(var count=new MonoMod.RuntimeDetour.ILHook(typeof(InfiniCrafterLocal.Common.Models.GeneratedItemData).GetMethod("FromJson",new[]{typeof(string)})!,il=>new MonoMod.Cil.ILCursor(il).EmitDelegate<Action>(()=>parses++))){for(int i=0;i<3;i++)ledger.PostUpdateWorld();}
 Equal(0,parses,"steady-state native actor checks never reparse unchanged complete authored definitions every tick");
 var first=groups[0];var definition=first.GetType().GetProperty("DefinitionJson")!;var read=typeof(GeneratedPlacementLedgerSystem).GetMethod("ReadNativeChestWitness",PersistenceStatic)!;
 var different=InfiniCrafterLocal.Common.Models.GeneratedItemData.FromJson(json)!;different.Name="different exact definition";definition.SetValue(first,different.ToNetworkJson());
 Equal(false,(bool)read.Invoke(null,new object[]{first,0,0})!,"cached lifecycle certificate cannot borrow a changed same-ID definition");definition.SetValue(first,json);Equal(true,(bool)read.Invoke(null,new object[]{first,0,0})!,"exact immutable definition can be freshly certified again");
 });}

}
