#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.Net;
using Terraria.Net.Sockets;
internal static partial class EngineRuntimeChecks
{
 private sealed class ChestCaptureSocket:ISocket
 {
  internal readonly List<byte[]> Sent=new();
  public void Close(){} public bool IsConnected()=>true;
  public void Connect(RemoteAddress address)=>throw new InvalidOperationException("CPU observer never connects");
  public void AsyncSend(byte[] data,int offset,int size,SocketSendCallback callback,object state){Sent.Add(data.AsSpan(offset,size).ToArray());callback?.Invoke(state);}
  public void AsyncReceive(byte[] data,int offset,int size,SocketReceiveCallback callback,object state)=>throw new InvalidOperationException("CPU observer never receives sockets");
  public bool IsDataAvailable()=>false;public void SendQueuedPackets(){}public bool StartListening(SocketConnectionAccepted callback)=>throw new InvalidOperationException("CPU observer never listens");public void StopListening(){}public RemoteAddress GetRemoteAddress()=>null!;
 }
 private sealed class NativeChestNetworkScope:IDisposable
 {
  private readonly MessageBuffer[] buffers=(MessageBuffer[])NetMessage.buffer.Clone();
  private readonly RemoteClient[] clients=(RemoteClient[])Netplay.Clients.Clone();
  private readonly System.Reflection.PropertyInfo diagnostics=typeof(Terraria.ModLoader.Mod).Assembly.GetType("Terraria.ModLoader.ModNet",true)!.GetProperty("ModNetDiagnosticsUI",PersistenceStatic)!;
  private readonly object? previousDiagnostics;
  internal readonly ChestCaptureSocket[] Sockets;
  internal NativeChestNetworkScope(){
   previousDiagnostics=diagnostics.GetValue(null);diagnostics.SetValue(null,new Terraria.UI.NetDiagnosticsUI());
   var players=Terraria.Main.player;Array.Resize(ref players,256);for(int i=0;i<players.Length;i++)players[i]??=new Player{whoAmI=i};Terraria.Main.player=players;
   Sockets=Enumerable.Range(0,Netplay.Clients.Length).Select(_=>new ChestCaptureSocket()).ToArray();
   for(int i=0;i<NetMessage.buffer.Length;i++){NetMessage.buffer[i]=new MessageBuffer{whoAmI=i,broadcast=true};typeof(MessageBuffer).GetMethod("ResetReader",PersistenceInstance)!.Invoke(NetMessage.buffer[i],null);typeof(MessageBuffer).GetMethod("ResetWriter",PersistenceInstance)!.Invoke(NetMessage.buffer[i],null);}
   for(int i=0;i<Netplay.Clients.Length;i++)Netplay.Clients[i]=new RemoteClient{Id=i,Socket=Sockets[i],IsActive=i<2,State=10};
  }
  internal void Receive(int who,byte type,Action<BinaryWriter> write){using var stream=new MemoryStream();using(var writer=new BinaryWriter(stream,System.Text.Encoding.UTF8,true)){writer.Write(type);write(writer);}byte[] bytes=stream.ToArray();var buffer=NetMessage.buffer[who];bytes.CopyTo(buffer.readBuffer,0);buffer.GetData(0,bytes.Length,out int observed);Equal((int)type,observed,"real native MessageBuffer decoded requested route");}
  internal void ReceiveFrame(int who,byte[] bytes){var buffer=NetMessage.buffer[who];bytes.AsSpan(2).CopyTo(buffer.readBuffer);buffer.GetData(0,bytes.Length-2,out int type);Equal((int)bytes[2],type,"actual native framed result receive");}
  internal void Clear(){foreach(var socket in Sockets)socket.Sent.Clear();}
  public void Dispose(){diagnostics.SetValue(null,previousDiagnostics);Array.Copy(buffers,NetMessage.buffer,buffers.Length);Array.Copy(clients,Netplay.Clients,clients.Length);}
 }
 private delegate bool NativeChestRemovalTestOrig(int x,int y);
 private static void NativeChestNativeMultiplayerInventoryAndExclusivity(){WithNativeChestWorld((player,ledger)=>WithNativeChestRegisteredItem(type=>{
  using var peers=new ReviewPeers();peers.Mode(NetmodeID.SinglePlayer,0);Terraria.Main.player[0]=player;Terraria.Main.dedServ=true;
  var source=NativeChestItem(player,"chest-network-native");peers.Register(source.Data);var p=source.Data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
  Equal(true,GeneratedPlacementLedgerSystem.AuthorizePlacement(player,source.Data,p,40,40),"native inventory net intent");NativeChestPlayerPlace(player);int index=Chest.FindChest(40,39);var actor=Terraria.Main.chest[index];actor.item[0]=new Item(ItemID.Wood,9);
  var contents=GeneratedPrefixFixture();contents.Id="native-network-contents";peers.Register(contents);var stored=new Item(type);var generated=(InfiniCrafterLocal.Content.Items.GeneratedItem)stored.ModItem;GeneratedPrefixSetData(generated,contents);stored.stack=2;Equal(true,stored.Prefix(PrefixID.Legendary),"native prefixed net contents");actor.item[1]=stored;
  using var network=new NativeChestNetworkScope();peers.Mode(NetmodeID.Server,255);Terraria.Main.player[0]=player;player.chest=-1;Terraria.Main.player[1].chest=-1;
  network.Receive(0,MessageID.RequestChestOpen,w=>{w.Write((short)40);w.Write((short)39);});
  byte[][] slots=network.Sockets[0].Sent.Where(bytes=>bytes[2]==MessageID.SyncChestItem).ToArray();
  Equal(40,slots.Length,"actual native open receive constructs all 40 ItemIO slot packets");Equal(index,player.chest,"native open request updates native player chest state");
  Equal(true,network.Sockets[0].Sent.Any(bytes=>bytes[2]==MessageID.SyncPlayerChest),"native open/name state packet constructed");
  network.Clear();network.Receive(1,MessageID.RequestChestOpen,w=>{w.Write((short)40);w.Write((short)39);});
  Equal(0,network.Sockets[1].Sent.Count(bytes=>bytes[2]==MessageID.SyncChestItem),"native UsingChest refuses concurrent second open");
  Netplay.Clients[1].TileSections[0,0]=true;int removalChecks=0;
  Func<NativeChestRemovalTestOrig,int,int,bool> observe=(orig,x,y)=>{removalChecks++;return orig(x,y);};
  using(var canRemove=new MonoMod.RuntimeDetour.Hook(typeof(Chest).GetMethod(nameof(Chest.CanDestroyChest))!,observe))
  using(var remove=new MonoMod.RuntimeDetour.Hook(typeof(Chest).GetMethod(nameof(Chest.DestroyChest))!,observe))
   for(int x=40;x<42;x++)for(int y=39;y<41;y++)network.Receive(1,MessageID.TileManipulation,w=>{w.Write((byte)0);w.Write((short)x);w.Write((short)y);w.Write((short)0);w.Write((byte)0);});
  Equal(true,removalChecks>0,"actual native MP mining receive reaches native chest contents authority");Equal(true,ReferenceEquals(actor,Terraria.Main.chest[index]),"native MP populated mining refuses removal from every cell");Equal(9,actor.item[0].stack,"native MP refusal retains vanilla contents");Equal(2,actor.item[1].stack,"native MP refusal retains generated contents");Equal(true,GeneratedPlacementLedgerSystem.ShouldSuppressPlacedBody(40,39),"native MP populated refusal preserves authored body");
  // Replay actual CPU-constructed packets through the native client ItemIO receiver.
  actor.item=Enumerable.Range(0,40).Select(_=>new Item()).ToArray();peers.Mode(NetmodeID.MultiplayerClient,0);
  foreach(byte[] bytes in slots){var buffer=NetMessage.buffer[256];bytes.AsSpan(2).CopyTo(buffer.readBuffer);buffer.GetData(0,bytes.Length-2,out int message);Equal((int)MessageID.SyncChestItem,message,"native chest slot receive route");}
  Equal(9,actor.item[0].stack,"native vanilla ItemIO slot delivery");Equal(true,actor.item[1].ModItem is InfiniCrafterLocal.Content.Items.GeneratedItem,"native real generated ItemIO slot delivery");
  Equal(contents.Id,((InfiniCrafterLocal.Content.Items.GeneratedItem)actor.item[1].ModItem).Data.Id,"generated network contents identity");Equal(2,actor.item[1].stack,"generated native network stack");Equal((int)PrefixID.Legendary,(int)actor.item[1].prefix,"generated native network prefix");
  using var pool=new NativeItemPoolState();Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item(ItemID.Wood,3){active=true}).ToArray();Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];
  var dropField=typeof(Terraria.ModLoader.TileLoader).GetField("HookCanDrop",PersistenceStatic)!;object? oldDrop=dropField.GetValue(null);dropField.SetValue(null,new Func<int,int,int,bool>[]{new GeneratedPlacementLedgerTile().CanDrop});using var restoreDrop=new PersistenceRestore(()=>dropField.SetValue(null,oldDrop));
  var random=Terraria.Main.rand;Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(17);using var restoreRandom=new PersistenceRestore(()=>Terraria.Main.rand=random);
  actor.item[0].TurnToAir();actor.item[1].TurnToAir();peers.Mode(NetmodeID.Server,255);
  network.Receive(1,MessageID.TileManipulation,w=>{w.Write((byte)0);w.Write((short)40);w.Write((short)40);w.Write((short)0);w.Write((byte)0);});ledger.PostUpdateWorld();
  Equal(-1,Chest.FindChest(40,39),"actual native MP empty mining removes actor");Equal(0,PlacedLedgerGroups(ledger).Count,"MP native complete removal retires exact material group");Equal(1,PlacedLedgerSaved(ledger).GetList<Terraria.ModLoader.IO.TagCompound>("infiniGeneratedPlacementReturnsV2").Count,"MP native removal joins one existing durable generated return");
 }));}
 private static void NativeChestRawMessage34CannotRefundGeneratedSource(){NativeChestRawMessageScenario(TileID.Containers,0);NativeChestRawMessageScenario(TileID.Containers2,4);}
 private static void NativeChestRawMessageScenario(int tileType,byte action){WithNativeChestWorld((player,ledger)=>{
  using var pool=new NativeItemPoolState();using var network=new NativeChestNetworkScope();
  Terraria.Main.item=Enumerable.Range(0,Terraria.Main.maxItems+1).Select(_=>new Item()).ToArray();Terraria.Main.timeItemSlotCannotBeReusedFor=new int[Terraria.Main.maxItems+1];
  var random=Terraria.Main.rand;Terraria.Main.rand=new Terraria.Utilities.UnifiedRandom(17);bool gen=WorldGen.gen;WorldGen.gen=false;
  try{
   typeof(Chest).GetMethod("Initialize",PersistenceStatic)!.Invoke(null,null);int vanillaItem=(tileType==TileID.Containers?Chest.chestItemSpawn:Chest.chestItemSpawn2)[0];
   var generated=NativeChestItem(player,"chest-raw-message",tileType:tileType,style:0);Terraria.Main.netMode=NetmodeID.Server;Terraria.Main.myPlayer=255;
   for(int i=0;i<8000;i++)Terraria.Main.chest[i]=new Chest{x=10,y=10};
   void FailedRequest()=>network.Receive(0,MessageID.ChestUpdates,w=>{w.Write(action);w.Write((short)40);w.Write((short)40);w.Write((short)0);w.Write((short)-1);});
   FailedRequest();Equal(0,Terraria.Main.item.Count(item=>item.active&&item.type==vanillaItem),"raw generated request cannot mint direct vanilla compensation");
   player.inventory[0]=new Item(vanillaItem,3);FailedRequest();
   Equal(1,Terraria.Main.item.Count(item=>item.active&&item.type==vanillaItem),"unrelated vanilla message-34 failure retains actual native family compensation");
   Equal(true,network.Sockets[0].Sent.Any(bytes=>bytes[2]==MessageID.ChestUpdates),"vanilla failure keeps native message-34 result");
  }finally{Terraria.Main.rand=random;WorldGen.gen=gen;}
 });}
}
