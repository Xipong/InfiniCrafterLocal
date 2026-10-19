#nullable enable
using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    // Native message 34 has no activation identity and refunds a vanilla chest
    // directly on failure. Generated requests therefore carry its bounded native
    // tuple inside the EXISTING sequenced Notify envelope, not a bare message 34.
    // No prediction/debit means failure needs neither a refund nor a second ledger.
    private const byte NativeChestOutcomeMarker = 34;
    [ThreadStatic] private static MessageBuffer? _nativeChestPacketBuffer;
    [ThreadStatic] private static long _nativeChestPacketEnd;
    private static long NativeChestPacketRemaining(BinaryReader reader)
        => ReferenceEquals(_nativeChestPacketBuffer?.reader,reader)
            ? _nativeChestPacketEnd-reader.BaseStream.Position : reader.BaseStream.Length-reader.BaseStream.Position;
    private static void SendNativeChestRequest(PlacementAuthorization authorization,TileObject data)
    {
        if(authorization.NotifyReceived || authorization.Sequence==0 || BeginNativeChestAttempt(authorization,data) is null) return;
        ModPacket? packet=global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if(packet is null) return;
        packet.Write(Common.InfiniNetPacketIds.NotifyGeneratedPlacement);
        packet.Write(PlacementProtocolVersion);packet.Write(authorization.Sequence);packet.Write((byte)authorization.Layer);
        packet.Write(authorization.TargetX);packet.Write(authorization.TargetY);
        packet.Write(NativeChestOutcomeMarker);packet.Write((byte)NativeChestPlaceAction(authorization.ExactPlacement!.TileId)); // native place-chest action
        packet.Write(data.xCoord);packet.Write(data.yCoord+1);packet.Write(data.style);
        packet.Send();authorization.NotifyReceived=true;
    }
    private delegate int NativeChestCreateOrig(int x,int y,int id);
    private static int NativeChestCreate(NativeChestCreateOrig orig,int x,int y,int id)
    {
        NativeChestAttempt? attempt=_nativeChestAttempt;
        if(attempt is null || Main.netMode!=NetmodeID.Server || attempt.Authorization.Sequence==0
            || x!=attempt.X || y!=attempt.Y || id!=-1) return orig(x,y,id);
        attempt.CallbackCount++;
        int index=orig(x,y,id);
        attempt.NativeResult=index;attempt.CallbackReturned=true;
        return index;
    }
    private static void HandleNativeChestRequest(BinaryReader reader,Player player,PlacementAuthorization authorization)
    {
        // Consume and validate the complete native tuple before any state change.
        if(authorization.NotifyReceived || NativeChestPacketRemaining(reader)!=14
            || reader.ReadByte()!=NativeChestOutcomeMarker || reader.ReadByte()!=NativeChestPlaceAction(authorization.ExactPlacement!.TileId)) return;
        int x=reader.ReadInt32(),y=reader.ReadInt32(),style=reader.ReadInt32();
        if(style!=authorization.ExactPlacement!.PlaceStyle || x!=authorization.TargetX || y!=authorization.TargetY) return;
        authorization.NotifyReceived=true;
        int slot=Array.FindIndex(player.inventory,item=>ReferenceEquals(item,authorization.SourceItem));
        NativeChestAttempt? attempt=slot>=0 ? BeginNativeChestAttempt(authorization,new TileObject{
            xCoord=x,yCoord=y-1,type=authorization.ExactPlacement.TileId,style=style,alternate=0 }) : null;
        int index=-1;
        if(attempt is not null)
        {
            authorization.ChestAttempt=attempt;_nativeChestAttempt=attempt;
            try
            {
                // Same native operation as the vanilla message-34 server branch;
                // its native 40-slot inventory stays the only contents authority.
                int native=WorldGen.PlaceChest(x,y,(ushort)authorization.ExactPlacement.TileId,false,style);
                attempt.Succeeded=native>=0 && native==attempt.Index;
                if(HasNativeChestOutcome(authorization) && TryCommitAuthorizedPlacement(player))
                {
                    index=native;
                    Item source=authorization.SourceItem!;
                    TryConsumePlacementReceipt(player); // this authority performs the debit now, never again in ItemCheck
                    source.stack--;if(source.stack==0) source.TurnToAir();
                }
            }
            catch(Exception e){ReportPlacedBodyAdmissionFailure("native chest server abort: "+e.GetType().Name);}
            finally{_nativeChestAttempt=null;}
            if(index<0) AbortNativeChestAttempt(attempt);
        }
        PendingAuthorizations.Remove(player.whoAmI);
        if(index>=0)
        {
            // Preserve the native message-34 result for ordinary remote clients,
            // and native inventory synchronization. A bare failure is NOT sent:
            // this request never predicted cells and must never get a vanilla refund.
            try{NetMessage.SendData(MessageID.ChestUpdates,-1,-1,null,NativeChestPlaceAction(authorization.ExactPlacement!.TileId),x,y,style,index);}catch{}
            try{NetMessage.SendData(MessageID.SyncEquipment,-1,-1,null,player.whoAmI,slot);}catch{}
        }
        ModPacket? packet=global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.GetPacket();
        if(packet is null) return;
        packet.Write(Common.InfiniNetPacketIds.GeneratedPlacementIntentReady);
        packet.Write(PlacementProtocolVersion);packet.Write(authorization.Sequence);packet.Write(true);
        packet.Write(authorization.DefinitionHash);packet.Write(authorization.GroupId);
        packet.Write(NativeChestOutcomeMarker);packet.Write(index);packet.Write(slot);
        packet.Write(index>=0 ? authorization.SourceItem!.stack : -1);packet.Write(x);packet.Write(y);
        packet.Send(player.whoAmI);
    }
    private static void HandleNativeChestOutcome(BinaryReader reader,ulong sequence,bool accepted,string hash,string groupId)
    {
        if(NativeChestPacketRemaining(reader)!=21 || reader.ReadByte()!=NativeChestOutcomeMarker) return;
        int index=reader.ReadInt32(),slot=reader.ReadInt32(),remaining=reader.ReadInt32(),x=reader.ReadInt32(),y=reader.ReadInt32();
        if(!accepted || !ClientPlacementIntents.TryGetValue(Main.myPlayer,out ClientPlacementIntent? intent)
            || intent.Sequence!=sequence || !intent.Ready || intent.GroupId!=groupId || intent.DefinitionHash!=hash
            || !IsNativeChestPlacement(intent.Placement) || intent.X!=x || intent.Y!=y
            || !ReferenceEquals(Main.player[Main.myPlayer],intent.Player)
            || !PendingAuthorizations.TryGetValue(Main.myPlayer,out PlacementAuthorization? authorization)
            || !authorization.NotifyReceived || authorization.Sequence!=sequence || authorization.GroupId!=groupId
            || !ReferenceEquals(authorization.SourceItem,intent.Item) || !ReferenceEquals(authorization.SourceData,intent.Data)) return;
        if(index>=0 && index<8000 && slot>=0 && slot<intent.Player.inventory.Length && remaining>=0
            && intent.Player.inventory.Any(item=>ReferenceEquals(item,intent.Item))
            && PlacementDefinitionHash(intent.Data.ToNetworkJson())==hash)
        {
            // The exact captured instance, never whatever now occupies a slot.
            // Native SyncEquipment may already have replaced it with the same
            // authoritative stack; in that case that native update owns projection.
            intent.Item.stack=remaining;if(remaining==0) intent.Item.TurnToAir();
        }
        PendingAuthorizations.Remove(Main.myPlayer);ClientPlacementIntents.Remove(Main.myPlayer);
    }
    private delegate void NativeChestGetDataOrig(MessageBuffer self,int start,int length,out int messageType);
    private delegate void NativeChestGetDataHook(NativeChestGetDataOrig orig,MessageBuffer self,int start,int length,out int messageType);
    private static void NativeChestGetData(NativeChestGetDataOrig orig,MessageBuffer self,int start,int length,out int messageType)
    {
        if(Main.netMode==NetmodeID.Server && start>=0 && start<self.readBuffer.Length && length>=8 && length<=self.readBuffer.Length-start
            && self.readBuffer[start]==MessageID.ChestUpdates && self.readBuffer[start+1] is 0 or 4
            && self.whoAmI>=0 && self.whoAmI<Main.maxPlayers
            && Main.player[self.whoAmI]?.HeldItem.ModItem is GeneratedItem held
            && held.Data.RuntimeProgram.Bindings.Any(binding=>IsNativeChestPlacement(binding.UsePolicy.Action.Placement)))
        {
            // Generated traffic must use the authenticated envelope above. Raw
            // message-34 replays cannot bypass intent/debit or mint vanilla refunds.
            // Unrelated vanilla chest requests still execute the untouched branch.
            messageType=MessageID.ChestUpdates;return;
        }
        if(start>=0 && start<self.readBuffer.Length && length>0 && length<=self.readBuffer.Length-start
            && self.readBuffer[start]==MessageID.ModPacket)
        {
            // Native ModNet passes its reusable full-buffer BinaryReader through
            // unchanged. Stream.Length is NOT the packet boundary. Scope the
            // actual native frame, including nested dispatch and exception unwind.
            MessageBuffer? previous=_nativeChestPacketBuffer;long end=_nativeChestPacketEnd;
            _nativeChestPacketBuffer=self;_nativeChestPacketEnd=(long)start+length;
            try{orig(self,start,length,out messageType);}
            finally{_nativeChestPacketBuffer=previous;_nativeChestPacketEnd=end;}
            return;
        }
        orig(self,start,length,out messageType);
    }
}
