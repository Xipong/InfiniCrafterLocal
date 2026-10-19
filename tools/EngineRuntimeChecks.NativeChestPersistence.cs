#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;
internal static partial class EngineRuntimeChecks
{
 private static void WithNativeChestRegisteredItem(Action<int> check)
 {
  var saved=new Dictionary<FieldInfo,object?>();
  void Capture(Type type,bool recursive=false){if(type.ContainsGenericParameters)return;foreach(var f in type.GetFields(PersistenceStatic).Where(f=>!f.IsInitOnly&&!f.IsLiteral))saved[f]=f.GetValue(null);if(recursive)foreach(var n in type.GetNestedTypes(BindingFlags.Public|BindingFlags.NonPublic))Capture(n,true);}
  foreach(var type in new[]{typeof(ItemID),typeof(AmmoID),typeof(Terraria.GameContent.Prefixes.PrefixLegacy),typeof(ItemUseStyleID),typeof(Item),typeof(Terraria.Main),typeof(Lang),typeof(Terraria.GameContent.TextureAssets),typeof(RecipeLoader),typeof(PrefixLoader)})Capture(type,type==typeof(ItemID)||type==typeof(AmmoID)||type==typeof(Terraria.GameContent.Prefixes.PrefixLegacy)||type==typeof(ItemUseStyleID));
  var items=(IList<ModItem>)typeof(ItemLoader).GetField("items",PersistenceStatic)!.GetValue(null)!;int count=items.Count;
  var countProperty=typeof(ItemLoader).GetProperty("ItemCount")!;int oldCount=(int)countProperty.GetValue(null)!;
  var singleton=typeof(ContentInstance<GeneratedItem>).GetProperty("Instance")!;object? old=singleton.GetValue(null);
  var lookup=typeof(ModTypeLookup<ModItem>);var maps=lookup.GetFields(PersistenceStatic).Where(f=>f.GetValue(null) is IDictionary).Select(f=>(Map:(IDictionary)f.GetValue(null)!,Rows:((IDictionary)f.GetValue(null)!).Cast<DictionaryEntry>().ToArray())).ToArray();
  var factories=(IList)typeof(SetFactory).GetField("SetFactories",PersistenceStatic)!.GetValue(null)!;object[] factoryRows=factories.Cast<object>().ToArray();
  try{
   var template=new GeneratedItem();var shell=new Item();
   typeof(ModType<Item>).GetProperty("Entity",PersistenceInstance)!.SetValue(template,shell);
   var mod=new global::InfiniCrafterLocal.InfiniCrafterLocalMod();
   typeof(Mod).GetProperty("File",PersistenceInstance)!.SetValue(mod,Activator.CreateInstance(typeof(Terraria.ModLoader.Core.TmodFile),PersistenceInstance,null,new object[]{"", "InfiniCrafterLocal",new Version(1,0)},null));
   typeof(ModType).GetProperty("Mod")!.SetValue(template,mod);
   typeof(ModType<Item,ModItem>).GetField("_isCloneable",PersistenceInstance)!.SetValue(template,true);
   int type=(int)typeof(ItemLoader).GetMethod("Register",PersistenceStatic)!.Invoke(null,new object[]{template})!;shell.type=type;
   typeof(Item).GetProperty("ModItem")!.SetValue(shell,template);singleton.SetValue(null,template);
   typeof(ModTypeLookup<ModItem>).GetMethod("Register",PersistenceStatic)!.Invoke(null,new object[]{template});
   factories.Clear();typeof(ItemLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,new object[]{true});
   typeof(PrefixLoader).GetMethod("ResizeArrays",PersistenceStatic)!.Invoke(null,null);
   check(type);
  }finally{
   singleton.SetValue(null,old);while(items.Count>count)items.RemoveAt(items.Count-1);countProperty.SetValue(null,oldCount);
   foreach(var map in maps){map.Map.Clear();foreach(var row in map.Rows)map.Map.Add(row.Key,row.Value);}
   foreach(var pair in saved)pair.Key.SetValue(null,pair.Value);
   factories.Clear();foreach(var row in factoryRows)factories.Add(row);
  }
 }
 private static void NativeChestNativeSaveLoadAndOpen(){NativeChestSaveLoadScenario(TileID.Containers,0);NativeChestSaveLoadScenario(TileID.Containers2,16);}
 private static void NativeChestSaveLoadScenario(int tileType,int style){WithNativeChestWorld((player,ledger)=>WithNativeChestRegisteredItem(type=>{
  using var peers=new ReviewPeers();peers.Mode(NetmodeID.SinglePlayer,0);Terraria.Main.player[0]=player;Terraria.Main.dedServ=true;
  for(int i=0;i<3;i++)Terraria.Main.chest[i]=new Chest{x=10+i*3,y=10};
  var source=NativeChestItem(player,"chest-save",tileType:tileType,style:style);var placement=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;peers.Register(source.Data);
  Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,placement,40,40),"native save intent");NativeChestPlayerPlace(player);
  int original=Chest.FindChest(40,39);Equal(3,original,"source actor deliberately not packed index zero");
  var chest=Terraria.Main.chest[original];chest.name="literal native chest name";chest.item[0]=new Item(ItemID.Wood,7);
  var contents=GeneratedPrefixFixture();contents.Id="native-chest-contents";peers.Register(contents);
  var stored=new Item(type);var generated=(GeneratedItem)stored.ModItem;GeneratedPrefixSetData(generated,contents);stored.stack=2;
  Equal(true,stored.Prefix(PrefixID.Legendary),"actual native generated contents prefix");chest.item[1]=stored;
  var triggersField=typeof(Terraria.GameInput.PlayerInput).GetField("Triggers",PersistenceStatic)!;var oldTriggers=triggersField.GetValue(null);
  var triggers=new Terraria.GameInput.TriggersPack();foreach(var field in typeof(Terraria.GameInput.TriggersPack).GetFields(PersistenceInstance))
   if(field.GetValue(triggers) is Terraria.GameInput.TriggersSet set)foreach(var prop in typeof(Terraria.GameInput.TriggersSet).GetProperties().Where(p=>p.PropertyType==typeof(bool)&&p.CanWrite))prop.SetValue(set,false);
  triggersField.SetValue(null,triggers);using var restoreTriggers=new PersistenceRestore(()=>triggersField.SetValue(null,oldTriggers));
  typeof(Player).GetMethod("OpenChest",PersistenceInstance)!.Invoke(player,new object[]{40,39,original});
  Equal(original,player.chest,"actual native OpenChest selects native inventory");Equal(40,player.chestX,"actual native open coordinates");
  var ledgerSave=PersistenceNbtRoundtrip(PlacedLedgerSaved(ledger));
  var worldIO=typeof(ItemIO).Assembly.GetType("Terraria.ModLoader.IO.WorldIO",true)!;
  using var memory=new MemoryStream();using(var writer=new BinaryWriter(memory,System.Text.Encoding.UTF8,true))typeof(Terraria.IO.WorldFile).GetMethod("SaveChests",PersistenceStatic)!.Invoke(null,new object[]{writer});
  var modRows=(List<TagCompound>)worldIO.GetMethod("SaveChestInventory",PersistenceStatic)!.Invoke(null,null)!;
  modRows=PersistenceNbtRoundtrip(new TagCompound{["chests"]=modRows}).GetList<TagCompound>("chests").ToList();
  Terraria.Main.chest=new Chest[8000];memory.Position=0;using(var reader=new BinaryReader(memory,System.Text.Encoding.UTF8,true))typeof(Terraria.IO.WorldFile).GetMethod("LoadChests",PersistenceStatic)!.Invoke(null,new object[]{reader});
  worldIO.GetMethod("LoadChestInventory",PersistenceStatic)!.Invoke(null,new object[]{modRows});
  player.chest=-1; // native world-entry resets an open UI, never caches old chest indices
  ledger.LoadWorldData(ledgerSave);ledger.PostUpdateWorld();
  int packed=Chest.FindChest(40,39);Equal(0,packed,"native load repacks indices, no cached index authority");
  var restored=Terraria.Main.chest[packed];Equal(chest.name,restored.name,"native name persists");Equal(7,restored.item[0].stack,"native vanilla slot persists");
  Equal(true,restored.item[1].ModItem is GeneratedItem,"real WorldIO native inventory restores registered generated item");
  var rebound=(GeneratedItem)restored.item[1].ModItem;rebound.CanUseItem(player);
  Equal(contents.Id,rebound.Data.Id,"generated definition identity persists through native contents save");Equal(2,restored.item[1].stack,"generated stack survives");Equal((int)PrefixID.Legendary,(int)restored.item[1].prefix,"generated prefix survives");
  Equal(1,PlacedLedgerGroups(ledger).Count,"single existing material claim rebinds by coordinate");
  Equal(false,PlacedLedgerGroups(ledger).Single().ContainsKey("nativeChestDiagnostic"),"legitimate native reload is healthy");
  restored.item[0].TurnToAir();restored.item[1].TurnToAir();Equal(true,Chest.DestroyChest(40,39),"rebound native actor can be emptied and removed");
  for(int x=40;x<42;x++)for(int y=39;y<41;y++){var cell=Terraria.Main.tile[x,y];cell.HasTile=false;}
  ledger.PostUpdateWorld();Equal(0,PlacedLedgerGroups(ledger).Count,"rebound actor removal releases only original material claim");
 }));}
 private static void NativeChestExactReturnUsesOnlyExistingPendingOwner()=>NativeChestExactReturnScenario(false);
 private static void NativeChestPostLoadBreakBeforeMaintenance(){foreach(var tuple in new[]{(TileID.Containers,0),(TileID.Containers,51),(TileID.Containers2,0),(TileID.Containers2,16)})NativeChestExactReturnScenario(true,tuple.Item1,tuple.Item2);}
 private static void NativeChestExactReturnScenario(bool reload,int tileType=TileID.Containers,int style=17){WithNativeChestWorld((player,ledger)=>WithNativeChestRegisteredItem(type=>{
  using var pool=new NativeItemPoolState();var random=Terraria.Main.rand;Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(17);bool gen=WorldGen.gen;WorldGen.gen=false;
  var dropField=typeof(ItemLoader).Assembly.GetType("Terraria.ModLoader.TileLoader",true)!.GetField("HookCanDrop",PersistenceStatic)!;object? oldDrop=dropField.GetValue(null);dropField.SetValue(null,new Func<int,int,int,bool>[] {new GeneratedPlacementLedgerTile().CanDrop});
  try{
   Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item(ItemID.Wood,3){active=true}).ToArray();Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];Item[] before=(Item[])Terraria.Main.item.Clone();
   var data=PlacementPrefixData();data.Id="native-chest-exact-prefix-return";var placement=data.RuntimeProgram.Bindings[1].UsePolicy.Action.Placement!;placement.WallId=-1;placement.TileId=tileType;placement.PlaceStyle=style;
   if(reload){placement=new(){TileId=tileType,WallId=-1,PlaceStyle=style};data.RuntimeProgram.Bindings[1].UsePolicy.Action.Placement=placement;}
   var item=new Item(type);var source=(GeneratedItem)item.ModItem;GeneratedPrefixSetData(source,data);player.inventory[0]=item;
   Equal(true,item.Prefix(PrefixID.Legendary),"native placed material prefix accepted");string exact=data.ToNetworkJson();player.altFunctionUse=2;
   Equal(true,source.CanUseItem(player),"actual alternate native chest placement consumer");NativeChestPlayerPlace(player);Equal(true,ItemLoader.ConsumeItem(item,player),"one native SP material debit receipt");
   item.stack--; // native caller's stack debit, after the real ConsumeItem dispatch
   if(reload){
    var save=PersistenceNbtRoundtrip(PlacedLedgerSaved(ledger));
    using var memory=new MemoryStream();using(var writer=new BinaryWriter(memory,System.Text.Encoding.UTF8,true))typeof(Terraria.IO.WorldFile).GetMethod("SaveChests",PersistenceStatic)!.Invoke(null,new object[]{writer});
    Terraria.Main.chest=new Chest[8000];memory.Position=0;using(var reader=new BinaryReader(memory,System.Text.Encoding.UTF8,true))typeof(Terraria.IO.WorldFile).GetMethod("LoadChests",PersistenceStatic)!.Invoke(null,new object[]{reader});
    ledger.LoadWorldData(save);
    Equal(true,PlacedIdentityMap("Groups").Values.Cast<object>().All(g=>g.GetType().GetProperty("BoundChest")!.GetValue(g) is null),"loaded claim is unbound before any maintenance/presentation visit");
   }
   WorldGen.KillTile(40,40);Equal(-1,Chest.FindChest(40,39),"real empty native chest break");ledger.PostUpdateWorld();
   Equal(0,PlacedLedgerGroups(ledger).Count,"native break before first maintenance retires the material group");
   for(int retry=0;retry<3;retry++){
    var save=PlacedLedgerSaved(ledger);var claim=save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Single();
    Equal(exact,claim.GetString("definitionJson"),"pending keeps exact complete authored definition");Equal((int)PrefixID.Legendary,claim.GetCompound("nativePrefix").GetInt("infiniNativePrefix"),"pending keeps exact source prefix");
    ledger.LoadWorldData(PersistenceNbtRoundtrip(save));ledger.PostUpdateWorld();
   }
   Equal(true,Terraria.Main.item.Select((current,i)=>ReferenceEquals(current,before[i])&&current.stack==3&&current.active).All(v=>v),"full native pool never replaces any occupied drop");
   Terraria.Main.item[5].active=false;Terraria.Main.timeItemSlotCannotBeReusedFor[5]=0;ledger.PostUpdateWorld();
   var returned=Terraria.Main.item[5];Equal(true,returned.ModItem is GeneratedItem,"real native NewItem created registered generated return");
   Equal(data.Id,((GeneratedItem)returned.ModItem).Data.Id,"native returned exact generated identity");Equal(exact,((GeneratedItem)returned.ModItem).Data.ToNetworkJson(),"native return retained authored body/light/VFX/behavior definition bytes");
   Equal((int)PrefixID.Legendary,(int)returned.prefix,"native prefix restored on actual returned instance");Equal(1,returned.stack,"one generated return item");
   Equal(0,PlacedLedgerSaved(ledger).GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"existing pending owner retired only after real allocation");
   Equal(false,GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Tile,40,40),"duplicate break has no second material claim");ledger.PostUpdateWorld();Equal(1,Terraria.Main.item.Count(i=>i.active&&i.ModItem is GeneratedItem),"one returned generated native item, no shadow queue");
  }finally{dropField.SetValue(null,oldDrop);WorldGen.gen=gen;Terraria.Main.rand=random;}
 }));}

}
