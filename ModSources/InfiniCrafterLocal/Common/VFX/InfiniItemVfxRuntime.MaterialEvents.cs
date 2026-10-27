#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
namespace InfiniCrafterLocal.Common.VFX;
internal readonly record struct InfiniItemVfxSnapshot(Vector2 Center,Vector2 Tip,Vector2 Forward,Vector2 Velocity)
{
    internal static InfiniItemVfxSnapshot Capture(Player player)=>new(player.Center,player.itemLocation,
        player.itemRotation.ToRotationVector2()*(player.direction<0?-1:1),player.velocity);
    internal bool Valid=>Finite(Center)&&Finite(Tip)&&Finite(Forward)&&Finite(Velocity)&&Math.Abs(Forward.LengthSquared()-1)<0.001f;
    private static bool Finite(Vector2 p)=>float.IsFinite(p.X)&&float.IsFinite(p.Y);
    internal VfxSourceFrame Frame(string anchor,Vector2 point)=>new(anchor=="hitPoint"?point:anchor is "tip" or "tipHistory"?Tip:Center,
        anchor=="velocity"?Velocity.SafeNormalize(Forward):Forward,Velocity){SourceCenter=Center};
}
public static partial class InfiniItemVfxRuntime
{
    private sealed record MaterialItemEvent(int Owner,long Token,ulong Occurrence,string ItemId,string EntityId,string Event,Vector2 Point,InfiniItemVfxSnapshot Snapshot);
    private const byte MaterialItemPacketVersion=5;
    private static readonly VfxOrderedPeerStream MaterialItemEventStream=new();
    private const ulong PendingItemEventLifetimeTicks = 60;
    private const int MaxPendingItemEventsPerOwner = 64;
    private sealed record PendingItemEvent(MaterialItemEvent Event, Player Player, object? Socket, ulong Tick);
    private static readonly List<PendingItemEvent>?[] PendingItemEvents = new List<PendingItemEvent>?[Main.maxPlayers];
    private static bool AcceptMaterialItemEvent(MaterialItemEvent p)
        =>Main.netMode==NetmodeID.Server?MaterialItemEventStream.AcceptOwner(p.Owner,p.Occurrence):MaterialItemEventStream.AcceptRelay(p.Occurrence);
    private static void WriteMaterialItemEvent(BinaryWriter writer,MaterialItemEvent p)
    {
        writer.Write(MaterialItemPacketVersion);writer.Write((byte)p.Owner);writer.Write(p.Token);writer.Write(p.Occurrence);
        writer.Write(p.ItemId);writer.Write(p.EntityId);writer.Write(p.Event);
        foreach(var v in new[]{p.Point,p.Snapshot.Center,p.Snapshot.Tip,p.Snapshot.Forward,p.Snapshot.Velocity}){writer.Write(v.X);writer.Write(v.Y);}
    }
    private static MaterialItemEvent ReadMaterialItemEvent(BinaryReader reader)
    {
        int owner=reader.ReadByte();long token=reader.ReadInt64();ulong occurrence=reader.ReadUInt64();
        string item=reader.ReadString(),entity=reader.ReadString(),ev=reader.ReadString();
        Vector2 Read()=>new(reader.ReadSingle(),reader.ReadSingle());
        var point=Read();var snapshot=new InfiniItemVfxSnapshot(Read(),Read(),Read(),Read());
        if(owner<0||owner>=Main.maxPlayers||token==0||occurrence==0||item.Length is 0 or >96||entity.Length is 0 or >48
            ||ev.Length>24||!RuntimeEventKind.IsKnown(ev)||!Finite(point)||!snapshot.Valid)throw new InvalidDataException("invalid material item snapshot");
        return new(owner,token,occurrence,item,entity,ev,point,snapshot);
    }
    // One bounded publication witness per player connection. This is presentation
    // transport state, not gameplay admission; repeated hits never resync inventory.
    private static readonly (long Token, int Slot, Player? Player, object? Socket)[] HeldEventWitnesses
        = new (long, int, Player?, object?)[Main.maxPlayers];

    private static bool PublishHeldEventWitness(Player player, GeneratedItem item, long token)
    {
        int owner = player.whoAmI, slot = player.selectedItem;
        if (owner < 0 || owner >= HeldEventWitnesses.Length || slot < 0 || slot >= player.inventory.Length
            || !ReferenceEquals(player.inventory[slot], item.Item)) return false;
        object? socket = Netplay.Connection?.Socket;
        var previous = HeldEventWitnesses[owner];
        // A -> silent B -> A can leave the server on B while A's item witness
        // is still cached. Selection is cheap and must precede every held claim.
        NetMessage.SendData(MessageID.PlayerControls, number: owner);
        if (previous.Token == token && previous.Slot == slot && ReferenceEquals(previous.Player, player)
            && ReferenceEquals(previous.Socket, socket)) return true;
        // Native end-of-frame sync can follow the first use/hit ModPacket. Publish
        // only its exact item first on the same ordered connection.
        NetMessage.SendData(MessageID.SyncEquipment, number: owner,
            number2: PlayerItemSlotID.Inventory0 + slot, number3: item.Item.prefix);
        HeldEventWitnesses[owner] = (token, slot, player, socket);
        return true;
    }

    private static void SendItemEvent(Player player,GeneratedItemData data,string entityId,string ev,Vector2 point)
    {
        if(EventSourceItem(player,data.Id,ev) is not GeneratedItem gi)return;
        ObserveItemPresentationSlot(player, gi.Item, ev is RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill);
        var payload=new MaterialItemEvent(player.whoAmI,gi.PresentationToken,MaterialItemEventStream.NewOwnerOccurrence(),data.Id,entityId,ev,point,InfiniItemVfxSnapshot.Capture(player));
        if(!payload.Snapshot.Valid||InfiniCrafterLocalMod.Instance is null)return;
        // Reactive equipment has its own functional/modded-slot registration;
        // do not invent an inventory slot or relax its existing server token fence.
        if(ev is not (RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill)
            && !PublishHeldEventWitness(player,gi,payload.Token))return;
        var packet=InfiniCrafterLocalMod.Instance.GetPacket();packet.Write(Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);WriteMaterialItemEvent(packet,payload);packet.Send();
    }
    private static void EmitMaterialItemSnapshot(GeneratedItemData data,MaterialItemEvent payload,VfxSourceBinding? binding,MaterialEventAllowance allowance)
    {
        foreach(var slot in data.VfxManifest.Slots)if(slot.PlacementBindingId is null&&slot.EntityId==payload.EntityId&&slot.Event==payload.Event&&InfiniDetachedVfxSystem.HasSnapshotVfx(slot))
            InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data,payload.EntityId,slot,$"item:{payload.Owner}:{data.Id}:{payload.EntityId}",payload.Snapshot.Frame(slot.Anchor,payload.Point),binding,itemBudget:true,allowance:allowance);
    }
    private static bool HasCurrentItemToken(Player player, MaterialItemEvent p)
        => EventSourceItem(player,p.ItemId,p.Event) is GeneratedItem gi && gi.PresentationToken == p.Token;
    private static string ItemEventChannel(MaterialItemEvent p)
        => p.Event is RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill ? "equipment:"+p.ItemId : "held";
    // A real ItemIO synchronization can arrive after the first VFX packet. Keep
    // bounded claims in transport order until the server's existing item token
    // matches. Never overwrite the authoritative item or accept a client token
    // as proof by itself.
    private static void DrainPendingItemEvents(int? owner = null)
    {
        if (Main.netMode != NetmodeID.Server) return;
        int first = owner ?? 0, last = owner.HasValue ? owner.Value + 1 : PendingItemEvents.Length;
        for (int ownerIndex=first; ownerIndex<last; ownerIndex++)
        {
            var queue=PendingItemEvents[ownerIndex]; if(queue is null)continue;
            var blocked = new HashSet<string>(StringComparer.Ordinal);
            for (int i=0; i<queue.Count;)
            {
                var pending=queue[i]; var p=pending.Event; var player=Main.player[p.Owner];
                object? socket=Netplay.Clients[p.Owner]?.Socket; ulong now=Main.GameUpdateCount;
                if (player is not { active: true } || !ReferenceEquals(player,pending.Player)
                    || !ReferenceEquals(socket,pending.Socket) || now<pending.Tick
                    || now-pending.Tick>PendingItemEventLifetimeTicks)
                { queue.RemoveAt(i); continue; }
                string channel=ItemEventChannel(p);
                if (blocked.Contains(channel)) { i++; continue; }
                if (EventSourceItem(player,p.ItemId,p.Event) is not GeneratedItem gi || gi.PresentationToken!=p.Token)
                { blocked.Add(channel); i++; continue; }
                queue.RemoveAt(i);
                if (!HasExactSlot(gi.Data,p.EntityId,p.Event)) continue;
                var entity=gi.Data.RuntimeProgram.TryGetEntity(p.EntityId);
                if (entity is null || !GeneratedItemRegistryService.IsCurrentWorldData(gi.Data)) continue;
                try { RuntimeEventKind.ValidateProducer(entity,p.Event,gi.Data.RuntimeProgram.Bindings.Any(b=>b.UsePolicy.ContactDamage),
                    gi.Data.RuntimeProgram.Bindings.Any(b=>b.Input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse&&b.UsePolicy.Action.Kind!=RuntimeBindingAction.PlaceItem),
                    gi.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped) is not null); } catch { continue; }
                var packet=InfiniCrafterLocalMod.Instance?.GetPacket(); if (packet is null) continue;
                packet.Write(Common.InfiniNetPacketIds.SyncGeneratedItemVfxEvent);
                WriteMaterialItemEvent(packet,p with { Occurrence=MaterialItemEventStream.NewRelayOccurrence() });
                packet.Send(-1,p.Owner);
            }
            if(queue.Count==0)PendingItemEvents[ownerIndex]=null;
        }
    }
    internal static void UpdatePendingItemEvents() => DrainPendingItemEvents();
    private static void HandleMaterialItemEvent(BinaryReader reader,int sender)
    {
        MaterialItemEvent p;try{p=ReadMaterialItemEvent(reader);}catch{return;}
        var player=Main.player[p.Owner];
        if(Main.netMode==NetmodeID.Server) {
            if(sender!=p.Owner||player is not{active:true})return;
            DrainPendingItemEvents(p.Owner);
            var queue=PendingItemEvents[p.Owner]??=new();
            if (!AcceptMaterialItemEvent(p) || !AdmitRemoteEvent(p.Owner)) return;
            // An already authoritative newer source supersedes mismatched older
            // claims; do not stall its events or revive those stale snapshots if
            // an old item is later selected again. Matching queued occurrences
            // have already been drained in order above.
            if (HasCurrentItemToken(player,p))
                queue.RemoveAll(x=>ItemEventChannel(x.Event)==ItemEventChannel(p) && !HasCurrentItemToken(player,x.Event));
            if(queue.Count>=MaxPendingItemEventsPerOwner)return;
            queue.Add(new(p,player,Netplay.Clients[p.Owner]?.Socket,Main.GameUpdateCount));
            DrainPendingItemEvents(p.Owner); return;
        }
        if(p.Owner==Main.myPlayer)return;
        GeneratedItemData? data=player is not null&&EventSourceItem(player,p.ItemId,p.Event) is GeneratedItem held?held.Data:null;
        if(data is null&&InfiniCrafterLocalMod.GeneratedItems?.TryGet(p.ItemId,out var registered)==true)data=registered;
        if(data is null||!GeneratedItemRegistryService.IsCurrentWorldData(data)||!HasExactSlot(data,p.EntityId,p.Event)||!AcceptMaterialItemEvent(p)||!AdmitRemoteEvent(p.Owner))return;
        VfxSourceBinding? binding=player is not null&&EventSourceItem(player,p.ItemId,p.Event) is GeneratedItem live&&live.PresentationToken==p.Token?VfxSourceBinding.Capture(player,live.Item,data):null;
        var allowance=new MaterialEventAllowance(data.VfxManifest.Budget.MaxParticlesTotal);
        EmitMaterialItemSnapshot(data,p,binding,allowance);
        // Simple renderers retain their live-player anchors; the admitted
        // occurrence, not item useTime, identifies each event.
        if(player is{active:true})EmitLocal(player,data,p.EntityId,p.Event,eventPosition:p.Event is "on_hit" or "on_crit" or "on_hurt" or "on_enemy_kill"?p.Point:null,includeMaterials:false,sharedAllowance:allowance);
    }
}
