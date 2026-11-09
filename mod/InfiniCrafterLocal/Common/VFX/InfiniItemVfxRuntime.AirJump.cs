#nullable enable
using System;
using System.IO;
using System.Collections.Generic;
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
    // A buff can outlive its item. Its synchronized live row (or real functional
    // equipment), including the final movement tick, witnesses this event.
    private const byte AirJumpPacketVersion=6;
    private sealed record AirJumpEvent(int Owner,long Generation,ulong Occurrence,string ItemId,
        string Definition,string EntityId,Vector2 Point,InfiniItemVfxSnapshot Snapshot);

    private sealed record PendingAirJumpEvent(AirJumpEvent Event, Player Player, object? Socket,
        VfxSourceBinding Source, ulong Tick);
    private static readonly List<PendingAirJumpEvent> PendingAirJumpEvents = new();

    internal static void FlushPendingAirJumpEvents(Player? owner = null)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient) return;
        for (int index = 0; index < PendingAirJumpEvents.Count;)
        {
            var pending = PendingAirJumpEvents[index];
            if (owner is not null && !ReferenceEquals(owner, pending.Player)) { index++; continue; }
            if (!ReferenceEquals(Netplay.Connection?.Socket, pending.Socket) || !pending.Source.IsLive
                || Main.GameUpdateCount < pending.Tick || Main.GameUpdateCount - pending.Tick > PendingItemEventLifetimeTicks)
            { PendingAirJumpEvents.RemoveAt(index); continue; }
            if (!pending.Player.GetModPlayer<InfiniCraftPlayer>().TryGetAirJumpNetworkGeneration(
                pending.Event.ItemId, pending.Event.Generation, out long generation)) { index++; continue; }
            PendingAirJumpEvents.RemoveAt(index);
            SendAirJumpEvent(pending.Event with { Generation = generation });
        }
    }

    private static void SendAirJumpEvent(AirJumpEvent payload)
    {
        var packet=InfiniCrafterLocalMod.Instance?.GetPacket();if(packet is null)return;
        // Allocate the ordered transport sequence only when sending. A queued
        // prediction must not arrive behind newer equipment/material packets.
        payload=payload with { Occurrence=MaterialItemEventStream.NewOwnerOccurrence() };
        packet.Write(Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);WriteAirJumpEvent(packet,payload);packet.Send();
    }

    public static void EmitAndSyncJump(Player player,GeneratedItemData source,Vector2 point,long sourceGeneration)
    {
        if(player is null||!player.active||player.dead||!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player)||!Finite(point)
            ||!player.GetModPlayer<InfiniCraftPlayer>().TryGetLiveAirJumpSource(source.Id,out var live,out long generation,
                sourceGeneration)
            ||!live.HasAirJumpProducer||!HasExactSlot(live,live.RuntimeProgram.ItemEntityId,RuntimeEventKind.OnJump)
            ||GeneratedItemRegistryService.DefinitionIdentity(live)!=GeneratedItemRegistryService.DefinitionIdentity(source))return;
        string entityId=live.RuntimeProgram.ItemEntityId;
        var snapshot=InfiniItemVfxSnapshot.CaptureAirJump(player);
        if(!snapshot.Valid)return;
        EmitLocal(player,live,entityId,RuntimeEventKind.OnJump,eventPosition:point,
            sourceBinding:VfxSourceBinding.CaptureAirJump(player,live.Id,generation),capturedSnapshot:snapshot);
        if(player.whoAmI!=Main.myPlayer||Main.netMode!=NetmodeID.MultiplayerClient
            ||InfiniCrafterLocalMod.Instance is null)return;
        var payload=new AirJumpEvent(player.whoAmI,generation,0,
            live.Id,GeneratedItemRegistryService.DefinitionIdentity(live),entityId,point,snapshot);
        var effects=player.GetModPlayer<InfiniCraftPlayer>();
        if(effects.TryGetAirJumpNetworkGeneration(live.Id,generation,out long authoritative))
            SendAirJumpEvent(payload with { Generation=authoritative });
        else
        {
            FlushPendingAirJumpEvents();
            if(PendingAirJumpEvents.Count<MaxPendingItemEventsPerOwner)
                PendingAirJumpEvents.Add(new(payload,player,Netplay.Connection?.Socket,
                    VfxSourceBinding.CaptureAirJump(player,live.Id,generation),Main.GameUpdateCount));
        }
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
        if(p.Owner>=Main.player.Length
            ||Main.netMode==NetmodeID.MultiplayerClient&&sender!=256)return;
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
            sharedAllowance:allowance,sourceBinding:binding,capturedSnapshot:p.Snapshot);
    }
}
