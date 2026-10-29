#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.VFX;

public static partial class InfiniItemVfxRuntime
{
    // A buff can outlive the item that granted it. Its exact active grant, never
    // the currently held item, witnesses this presentation-only occurrence.
    private const byte AirJumpPacketVersion=6;
    private sealed record AirJumpEvent(int Owner,long Generation,ulong Occurrence,string ItemId,
        string Definition,string EntityId,Vector2 Point,InfiniItemVfxSnapshot Snapshot);

    public static void EmitAndSyncJump(Player player,GeneratedItemData source,Vector2 point,long sourceGeneration)
    {
        if(player is null||!player.active||player.dead||!Finite(point)
            ||!player.GetModPlayer<InfiniCraftPlayer>().TryGetLiveAirJumpSource(source.Id,out var live,out long generation,
                sourceGeneration)
            ||!live.HasAirJumpProducer||!HasExactSlot(live,live.RuntimeProgram.ItemEntityId,RuntimeEventKind.OnJump)
            ||GeneratedItemRegistryService.DefinitionIdentity(live)!=GeneratedItemRegistryService.DefinitionIdentity(source))return;
        string entityId=live.RuntimeProgram.ItemEntityId;
        EmitLocal(player,live,entityId,RuntimeEventKind.OnJump,eventPosition:point,
            sourceBinding:VfxSourceBinding.CaptureAirJump(player,live.Id,generation));
        if(player.whoAmI!=Main.myPlayer||Main.netMode!=NetmodeID.MultiplayerClient
            ||InfiniCrafterLocalMod.Instance is null)return;
        var payload=new AirJumpEvent(player.whoAmI,generation,MaterialItemEventStream.NewOwnerOccurrence(),
            live.Id,GeneratedItemRegistryService.DefinitionIdentity(live),entityId,point,InfiniItemVfxSnapshot.Capture(player));
        if(!payload.Snapshot.Valid)return;
        var packet=InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);WriteAirJumpEvent(packet,payload);packet.Send();
    }

    private static void WriteAirJumpEvent(BinaryWriter writer,AirJumpEvent p)
    {
        writer.Write(AirJumpPacketVersion);writer.Write((byte)p.Owner);writer.Write(p.Generation);writer.Write(p.Occurrence);
        writer.Write(p.ItemId);writer.Write(p.Definition);writer.Write(p.EntityId);
        foreach(var v in new[]{p.Point,p.Snapshot.Center,p.Snapshot.Tip,p.Snapshot.Forward,p.Snapshot.Velocity})
        {writer.Write(v.X);writer.Write(v.Y);}
    }

    private static AirJumpEvent ReadAirJumpEvent(BinaryReader reader)
    {
        int owner=reader.ReadByte();long generation=reader.ReadInt64();ulong occurrence=reader.ReadUInt64();
        string item=ReadAirJumpText(reader,256),definition=ReadAirJumpText(reader,64),entity=ReadAirJumpText(reader,48);
        Vector2 Read()=>new(reader.ReadSingle(),reader.ReadSingle());
        var point=Read();var snapshot=new InfiniItemVfxSnapshot(Read(),Read(),Read(),Read());
        if(owner<0||owner>=Main.maxPlayers||generation==0||occurrence==0||item.Length==0
            ||definition.Length!=64||!definition.All(Uri.IsHexDigit)||entity.Length is 0 or >48
            ||!Finite(point)||!snapshot.Valid)throw new InvalidDataException("invalid air-jump presentation event");
        return new(owner,generation,occurrence,item,definition,entity,point,snapshot);
    }

    private static string ReadAirJumpText(BinaryReader reader,int maxBytes)
    {
        int count=reader.Read7BitEncodedInt();
        if(count<0||count>maxBytes)throw new InvalidDataException("air-jump text byte limit");
        byte[] bytes=reader.ReadBytes(count);
        if(bytes.Length!=count)throw new EndOfStreamException();
        return new UTF8Encoding(false,true).GetString(bytes);
    }

    private static bool TryResolveAirJumpEvent(AirJumpEvent p,Player player,out GeneratedItemData data)
    {
        data=null!;
        return player is{active:true,dead:false}
            &&player.GetModPlayer<InfiniCraftPlayer>().TryGetLiveAirJumpSource(p.ItemId,out data,out long generation,p.Generation)
            &&generation==p.Generation&&data.HasAirJumpProducer&&GeneratedItemRegistryService.IsCurrentWorldData(data)
            &&GeneratedItemRegistryService.DefinitionIdentity(data)==p.Definition
            &&p.EntityId==data.RuntimeProgram.ItemEntityId&&HasExactSlot(data,p.EntityId,RuntimeEventKind.OnJump);
    }

    private static void HandleAirJumpEvent(BinaryReader reader,int sender)
    {
        AirJumpEvent p;try{p=ReadAirJumpEvent(reader);}catch{return;}
        if(p.Owner>=Main.player.Length)return;
        Player player=Main.player[p.Owner];
        if(!TryResolveAirJumpEvent(p,player,out var data))return;
        if(Main.netMode==NetmodeID.Server)
        {
            if(sender!=p.Owner||!MaterialItemEventStream.AcceptOwner(p.Owner,p.Occurrence)||!AdmitRemoteEvent(p.Owner))return;
            var packet=InfiniCrafterLocalMod.Instance?.GetPacket();if(packet is null)return;
            packet.Write(Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
            WriteAirJumpEvent(packet,p with{Occurrence=MaterialItemEventStream.NewRelayOccurrence()});packet.Send(-1,p.Owner);
            return;
        }
        if(p.Owner==Main.myPlayer||!MaterialItemEventStream.AcceptRelay(p.Occurrence)||!AdmitRemoteEvent(p.Owner))return;
        var binding=VfxSourceBinding.CaptureAirJump(player,p.ItemId,p.Generation);
        var allowance=new MaterialEventAllowance(data.VfxManifest.Budget.MaxParticlesTotal);
        EmitMaterialItemSnapshot(data,new MaterialItemEvent(p.Owner,p.Generation,p.Occurrence,p.ItemId,p.EntityId,
            RuntimeEventKind.OnJump,p.Point,p.Snapshot),binding,allowance);
        EmitLocal(player,data,p.EntityId,RuntimeEventKind.OnJump,eventPosition:p.Point,includeMaterials:false,
            sharedAllowance:allowance,sourceBinding:binding);
    }
}
