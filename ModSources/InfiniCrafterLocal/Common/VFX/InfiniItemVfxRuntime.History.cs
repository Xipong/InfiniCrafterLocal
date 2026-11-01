#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using Terraria.GameContent;

namespace InfiniCrafterLocal.Common.VFX;

public static partial class InfiniItemVfxRuntime
{
    // One exact active use per player, never a history inferred from animation counters.
    private sealed class HeldHistory
    {
        internal readonly Player Player;
        internal readonly Item Item;
        internal readonly GeneratedItemData Data;
        internal readonly object Generation;
        internal readonly string Entity;
        internal readonly Dictionary<string,List<VfxTrailSample>> Samples=new(StringComparer.Ordinal);
        internal List<DrawData>? Cache;
        internal int Index;
        internal DrawData? PendingDraw;
        internal ulong RegisteredTick;
        internal Texture2D? Texture;
        internal readonly ulong UseTick;
        internal bool AwaitingFirstDraw;
        internal HeldHistory(Player player,GeneratedItem item,string entity)
        {
            (Player,Item,Data,Generation,Entity)=(player,item.Item,item.Data,item.PresentationGeneration,entity);
            UseTick=Main.GameUpdateCount;
            AwaitingFirstDraw=Main.netMode==Terraria.ID.NetmodeID.MultiplayerClient&&player.whoAmI!=Main.myPlayer;
        }
    }
    private static readonly HeldHistory?[] ItemHistories=new HeldHistory?[Main.maxPlayers];

    internal static void LoadItemHistory()
    {
        On_PlayerDrawLayers.DrawPlayer_TransformDrawData+=TransformHeldHistory;
        On_PlayerDrawLayers.DrawPlayer_RenderAllLayers+=DrawHeldHistory;
        On_Player.Teleport+=TeleportHistory;
    }
    internal static void UnloadItemHistory()
    {
        On_PlayerDrawLayers.DrawPlayer_TransformDrawData-=TransformHeldHistory;
        On_PlayerDrawLayers.DrawPlayer_RenderAllLayers-=DrawHeldHistory;
        On_Player.Teleport-=TeleportHistory;
        Array.Clear(ItemHistories);
    }
    private static void TeleportHistory(On_Player.orig_Teleport orig,Player player,Vector2 position,int style,int extraInfo)
    {
        if(player.whoAmI>=0&&player.whoAmI<ItemHistories.Length)ItemHistories[player.whoAmI]=null;
        orig(player,position,style,extraInfo);
    }
    private static void BeginHeldHistory(Player player,GeneratedItemData data,string entity)
    {
        if(Main.dedServ||player.whoAmI<0||player.whoAmI>=ItemHistories.Length
            ||player.HeldItem?.ModItem is not GeneratedItem item||!ReferenceEquals(item.Data,data))return;
        ItemHistories[player.whoAmI]=null;
        foreach(var slot in data.VfxManifest.Slots)
            if(slot.EntityId==entity&&slot.Event=="on_use"&&slot.Trail is not null) {
                ItemHistories[player.whoAmI]=new(player,item,entity);return;
            }
    }
    private static HeldHistory? ActiveHeldHistory(Player player)
    {
        int owner=player.whoAmI;
        if(owner<0||owner>=ItemHistories.Length)return null;
        var state=ItemHistories[owner];
        if(state is null)return null;
        if(!player.active||player.dead||player.frozen
            ||!ReferenceEquals(Main.player[owner],player)||!ReferenceEquals(state.Player,player)
            ||!ReferenceEquals(player.HeldItem,state.Item)||player.HeldItem.ModItem is not GeneratedItem item
            ||!ReferenceEquals(item.Data,state.Data)||!ReferenceEquals(item.PresentationGeneration,state.Generation)) {
            ItemHistories[owner]=null;return null;
        }
        ulong now=Main.GameUpdateCount;
        if(state.AwaitingFirstDraw&&(now<state.UseTick||now-state.UseTick>54)) {
            ItemHistories[owner]=null;return null;
        }
        bool visible=GeneratedHeldItemPresentation.TryGetVisibleHeldSpriteData(new PlayerDrawSet{drawPlayer=player},out var resolved);
        if(resolved is not null&&!ReferenceEquals(resolved,state.Data)) {
            ItemHistories[owner]=null;return null;
        }
        if(!visible) {
            // An accepted remote use may precede native ItemCheck/first draw.
            // Keep only bounded empty history; never manufacture animation/pose.
            if(state.AwaitingFirstDraw)return null;
            ItemHistories[owner]=null;return null;
        }
        return state;
    }
    internal static void PruneHeldHistory()
    {
        for(int i=0;i<ItemHistories.Length;i++)
            if(ItemHistories[i] is {} state)ActiveHeldHistory(state.Player);
    }
    // The native ModItem hook supplies the body before ItemLoader appends it.
    // PostModify/later layers may edit the cache: resolve an unambiguous witness
    // only after those callbacks and before native coordinate transforms.
    internal static void RegisterHeldHistoryDraw(ref PlayerDrawSet draw, in DrawData body)
    {
        if(draw.shadow!=0||ActiveHeldHistory(draw.drawPlayer) is not {} state)return;
        if(draw.heldItem?.ModItem is not GeneratedItem nativeItem
            ||(!ReferenceEquals(nativeItem.Data,state.Data)&&!ReferenceEquals(nativeItem.NativeHeldSourceData,state.Data)))return;
        state.Cache=draw.DrawDataCache;state.Index=-1;state.RegisteredTick=Main.GameUpdateCount;
        state.Texture=body.texture;state.PendingDraw=body;
    }
    internal static void ResolveHeldHistoryDraw(ref PlayerDrawSet draw)
    {
        if(draw.shadow!=0||ActiveHeldHistory(draw.drawPlayer) is not {} state)return;
        state.Index=-1;
        if(state.RegisteredTick!=Main.GameUpdateCount||!ReferenceEquals(state.Cache,draw.DrawDataCache)||state.PendingDraw is not DrawData pending)return;
        int match=-1;
        for(int i=0;i<draw.DrawDataCache.Count;i++) if(draw.DrawDataCache[i].Equals(pending)) {
            if(match>=0) {state.PendingDraw=null;return;}
            match=i;
        }
        state.Index=match;state.PendingDraw=null;
    }
    private static void TransformHeldHistory(On_PlayerDrawLayers.orig_DrawPlayer_TransformDrawData orig,ref PlayerDrawSet draw)
    {
        ResolveHeldHistoryDraw(ref draw);
        orig(ref draw);
    }
    internal static Vector2 HeldHistoryPoint(in DrawData draw,Vector2 local)
    {
        var frame=draw.sourceRect??draw.texture.Bounds;
        if((draw.effect&SpriteEffects.FlipHorizontally)!=0)local.X=frame.Width-local.X;
        if((draw.effect&SpriteEffects.FlipVertically)!=0)local.Y=frame.Height-local.Y;
        return draw.position+((local-draw.origin)*draw.scale).RotatedBy(draw.rotation)+Main.screenPosition;
    }
    private static VfxTrailPose HeldHistoryPose(in DrawData draw,Texture2D texture,VfxHistoryTrailSpec trail)
    {
        // Item stamps keep actual final native scale. Other explicit texture frames
        // share that pose and texel scale; no invented aiming or silhouette alignment.
        return new(draw.rotation,draw.scale*trail.Scale!.Value,draw.effect,0,new Vector2(texture.Width,texture.Height)*.5f);
    }
    private static void CaptureHeldHistory(HeldHistory state,in DrawData draw)
    {
        state.AwaitingFirstDraw=false;
        ulong now=Main.GameUpdateCount;
        var frame=draw.sourceRect??draw.texture.Bounds;
        Vector2 center=new(frame.Width*.5f,frame.Height*.5f);
        float angle=MathHelper.ToRadians(state.Data.Visual.ForwardAngleDegrees!.Value);
        Vector2 axis=new(MathF.Cos(angle),MathF.Sin(angle));
        float edge=Math.Min(Math.Abs(axis.X)>1e-6f?center.X/Math.Abs(axis.X):float.PositiveInfinity,
                            Math.Abs(axis.Y)>1e-6f?center.Y/Math.Abs(axis.Y):float.PositiveInfinity);
        foreach(var slot in state.Data.VfxManifest.Slots) {
            if(slot.EntityId!=state.Entity||slot.Event!="on_use"||slot.Trail is not {} trail)continue;
            if(!state.Samples.TryGetValue(slot.Id,out var samples))state.Samples[slot.Id]=samples=new();
            samples.RemoveAll(s=>now<s.Tick||now-s.Tick>=32);
            if(samples.Count>0&&samples[0].Tick==now)continue;
            Vector2 point=HeldHistoryPoint(draw,trail.Source=="tip"?center+axis*edge:center);
            if(!Finite(point))continue;
            VfxTrailPose? pose=null;
            if(trail.Draw=="sprites"&&InfiniVfxRuntime.TrailTexture(state.Data,state.Entity,trail,out _) is {} texture)
                pose=HeldHistoryPose(draw,texture,trail);
            if(samples.Count==32)samples.RemoveAt(31);
            samples.Insert(0,new(now,point,pose));
        }
    }
    private static void DrawHeldHistoryLayer(HeldHistory state,in DrawData draw,string layer)
    {
        foreach(var slot in state.Data.VfxManifest.Slots) {
            if(slot.Layer!=layer||slot.Trail is not {} trail||!state.Samples.TryGetValue(slot.Id,out var samples))continue;
            DrawHeldHistorySlot(state.Data,state.Entity,state.Player.whoAmI,slot,samples,draw);
        }
    }
    private static void DrawHeldHistorySlot(GeneratedItemData data,string entity,int owner,VfxSlotSpec slot,IReadOnlyList<VfxTrailSample> samples,DrawData draw)
    {
        var trail=slot.Trail!;
        Texture2D? texture=null;VfxTrailPose? pose=null;
        if(trail.Draw=="sprites") {
            texture=InfiniVfxRuntime.TrailTexture(data,entity,trail,out _);
            if(texture is null)return;
            if(trail.Pose=="current")pose=HeldHistoryPose(draw,texture,trail);
        }
        InfiniVfxRuntime.DrawExplicitTrailSamples(TextureAssets.MagicPixel.Value,texture,samples,trail,slot.Blend!,Main.GameUpdateCount,pose,
            ()=>InfiniDetachedVfxSystem.TrySpendSourceDraw($"item:{owner}:{data.Id}:{entity}",data.VfxManifest.Budget.MaxDrawCalls,1));
    }
    private static void DrawHeldHistory(On_PlayerDrawLayers.orig_DrawPlayer_RenderAllLayers orig,ref PlayerDrawSet draw)
    {
        HeldHistory? state=null;DrawData body=default;
        if(draw.shadow==0&&ActiveHeldHistory(draw.drawPlayer) is {} candidate) {
            if(candidate.RegisteredTick==Main.GameUpdateCount&&ReferenceEquals(candidate.Cache,draw.DrawDataCache)&&candidate.Index>=0&&candidate.Index<draw.DrawDataCache.Count
                &&ReferenceEquals(draw.DrawDataCache[candidate.Index].texture,candidate.Texture)) {
                body=draw.DrawDataCache[candidate.Index];
                if(body.color.A>0&&Finite(body.position)&&Finite(body.scale)&&float.IsFinite(body.rotation)) {state=candidate;CaptureHeldHistory(state,body);}
            }
            // A subsequent player render must register its own exact visible entry.
            candidate.Cache=null;candidate.Texture=null;candidate.PendingDraw=null;
        }
        if(state is not null)DrawHeldHistoryLayer(state,body,"BeforePlayer");
        orig(ref draw);
        if(state is not null)DrawHeldHistoryLayer(state,body,"AfterPlayer");
    }
}
