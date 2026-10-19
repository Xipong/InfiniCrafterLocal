#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.DataStructures;
using Terraria.ObjectData;
using Terraria.ID;
using Terraria.ModLoader.IO;
using Terraria.ModLoader;
using MonoMod.RuntimeDetour;

namespace InfiniCrafterLocal.Common.Systems;

public sealed partial class GeneratedPlacementLedgerSystem
{
    private sealed record NativeChestDefinitionCertificate(string Json,string Binding,string Hash,int TileType,int Style,bool Valid);
    private sealed class NativeChestAttempt
    {
        public PlacementAuthorization Authorization { get; init; } = null!;
        public int X { get; init; }
        public int Y { get; init; }
        public ulong World { get; init; }
        public Chest?[] BeforeActors { get; init; } = null!;
        public Chest? Actor { get; set; }
        public int Index { get; set; } = -1;
        public int CallbackCount { get; set; }
        public int NativeResult { get; set; } = -1;
        public bool CallbackReturned { get; set; }
        public bool TilesWritten { get; set; }
        public bool Succeeded { get; set; }
    }
    private static readonly List<Hook> NativeChestHooks = new();
    [ThreadStatic] private static NativeChestAttempt? _nativeChestAttempt;
    private static ulong _nativeChestWorld;
    private static int _nativeChestMaintenanceCursor;
    private const int MaxNativeChestMaintenanceVisits = 32;
    private delegate TileObject NativePlayerPlaceOrig(Player player,bool newObject,TileObject data,int tileType);
    private delegate int NativeChestPostOrig(int x,int y,int type,int style,int direction,int alternate);
    private delegate bool NativeTilePlaceOrig(TileObject data);

    private static bool NativeChestInventory(Chest? actor)
        => actor?.item is { Length: 40 } slots && slots.All(item => item is not null);
    private static bool HasNativeChestOutcome(PlacementAuthorization authorization)
    {
        NativeChestAttempt? attempt=authorization.ChestAttempt;
        return attempt is { Succeeded: true, CallbackCount: 1, CallbackReturned: true, TilesWritten: true }
            && attempt.NativeResult==attempt.Index
            && ReferenceEquals(attempt.Authorization,authorization) && attempt.World==_nativeChestWorld
            && attempt.Index>=0 && attempt.Index<Main.chest.Length
            && ReferenceEquals(Main.chest[attempt.Index],attempt.Actor)
            && NativeChestInventory(attempt.Actor) && attempt.Actor!.x==attempt.X && attempt.Actor.y==attempt.Y
            && Main.chest.Count(actor=>actor is not null && actor.x==attempt.X && actor.y==attempt.Y)==1;
    }

    private static void InstallNativeChestHooks()
    {
        if (NativeChestHooks.Count!=0 || !GeneratedPlacedBodyNativeAdapter.FeatureAvailable) return;
        try
        {
            NativeChestHooks.Add(new Hook(typeof(Player).GetMethod("PlaceThing_Tiles_PlaceIt",
                BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic)!,
                (Func<NativePlayerPlaceOrig,Player,bool,TileObject,int,TileObject>)NativeChestPlayerPlace));
            NativeChestHooks.Add(new Hook(typeof(TileObject).GetMethod(nameof(TileObject.Place))!,
                (Func<NativeTilePlaceOrig,TileObject,bool>)NativeChestTilePlace));
            NativeChestHooks.Add(new Hook(typeof(Chest).GetMethod(nameof(Chest.CreateChest))!,
                (Func<NativeChestCreateOrig,int,int,int,int>)NativeChestCreate));
            NativeChestHooks.Add(new Hook(typeof(MessageBuffer).GetMethod(nameof(MessageBuffer.GetData))!,
                (NativeChestGetDataHook)NativeChestGetData));
            NativeChestHooks.Add(new Hook(typeof(Chest).GetMethod(nameof(Chest.DestroyChest))!,
                (Func<NativeChestDestroyOrig,int,int,bool>)NativeChestDestroy));
            NativeChestHooks.Add(new Hook(typeof(Chest).GetMethod(nameof(Chest.AfterPlacement_Hook))!,
                (Func<NativeChestPostOrig,int,int,int,int,int,int,int>)NativeChestPost));
            InstallNativeChestSaveGuard();
            InstallNativeChestAllocationGuards();
        }
        catch { UnloadNativeChestHooks(); throw; }
    }
    private static void UnloadNativeChestHooks()
    {
        _nativeChestPostAllocationGuard?.Dispose();_nativeChestPostAllocationGuard=null;
        _nativeChestCreateAllocationGuard?.Dispose();_nativeChestCreateAllocationGuard=null;
        _nativeChestSaveGuard?.Dispose();_nativeChestSaveGuard=null;
        for(int i=NativeChestHooks.Count-1;i>=0;i--) { NativeChestHooks[i].Dispose(); NativeChestHooks.RemoveAt(i); }
        _nativeChestAttempt=null;
    }
    private static bool NativeChestSourceCurrent(PlacementAuthorization authorization,Player player)
        => ReferenceEquals(authorization.SourcePlayer,player) && ReferenceEquals(Main.player[player.whoAmI],player)
            && player.active && !player.dead && ReferenceEquals(player.HeldItem,authorization.SourceItem)
            && authorization.SourceItem is { stack: > 0 } && player.HeldItem.ModItem is Content.Items.GeneratedItem generated
            && ReferenceEquals(generated.Data,authorization.SourceData)
            && ResolvePlacementPrefixEnvelope(authorization.NativePrefixEnvelope)
                ==Content.Items.GeneratedItem.ResolvePlacementPrefix(generated.CapturePlacementPrefix())
            && (int)Main.GameUpdateCount<=authorization.ExpiresAtTick
            && WithinPlacementReach(player,authorization.TargetX,authorization.TargetY)
            && PlacementDefinitionHash(authorization.SourceData!.ToNetworkJson())==authorization.DefinitionHash;
    private static NativeChestAttempt? BeginNativeChestAttempt(PlacementAuthorization authorization,TileObject data)
    {
        if (_nativeChestAttempt is not null || !AdmitNativeChestMetadata(authorization.ExactPlacement!)
            || authorization.SourcePlayer is not Player player || !NativeChestSourceCurrent(authorization,player)
            || data.type!=authorization.ExactPlacement!.TileId || data.style!=authorization.ExactPlacement.PlaceStyle || data.alternate!=0
            || !TileLoader.CanPlace(authorization.TargetX,authorization.TargetY,data.type)
            || authorization.TargetX<data.xCoord || authorization.TargetX>data.xCoord+1
            || authorization.TargetY<data.yCoord || authorization.TargetY>data.yCoord+1
            || !WorldGen.InWorld(data.xCoord,data.yCoord,2) || !WorldGen.InWorld(data.xCoord+1,data.yCoord+2,2)
            || Main.chest is not { Length: 8000 } || Chest.FindEmptyChest(data.xCoord,data.yCoord,data.type,data.style,1,0)<0)
            return null;
        for(int x=data.xCoord;x<data.xCoord+2;x++) for(int y=data.yCoord;y<data.yCoord+2;y++)
            if(Main.tile[x,y].HasTile || Placements.ContainsKey(new(GeneratedPlacementLayer.Tile,x,y))
                || TileEntity.ByPosition.ContainsKey(new Point16(x,y))) return null;
        if(!TileObject.CanPlace(authorization.TargetX,authorization.TargetY,data.type,data.style,player.direction,
            out TileObject native,false,null) || native.xCoord!=data.xCoord || native.yCoord!=data.yCoord
            || native.type!=data.type || native.style!=data.style || native.alternate!=0) return null;
        return new NativeChestAttempt { Authorization=authorization,X=data.xCoord,Y=data.yCoord,
            World=_nativeChestWorld,BeforeActors=(Chest?[])Main.chest.Clone() };
    }
    private static TileObject NativeChestPlayerPlace(NativePlayerPlaceOrig orig,Player player,bool newObject,TileObject data,int tileType)
    {
        if(!PendingAuthorizations.TryGetValue(player.whoAmI,out PlacementAuthorization? authorization)
            || !IsNativeChestPlacement(authorization.ExactPlacement))
            return player.HeldItem.ModItem is Content.Items.GeneratedItem && (NativeChestPlaceAction(tileType)>=0 || NativeChestPlaceAction(data.type)>=0)
                ? data : orig(player,newObject,data,tileType);
        if(!newObject || tileType!=authorization.ExactPlacement!.TileId) return data;
        if(Main.netMode==NetmodeID.MultiplayerClient){SendNativeChestRequest(authorization,data);return data;}
        if(Main.netMode!=NetmodeID.SinglePlayer) return data;
        NativeChestAttempt? attempt=BeginNativeChestAttempt(authorization,data);
        if(attempt is null) return data;
        authorization.ChestAttempt=attempt;_nativeChestAttempt=attempt;
        try
        {
            TileObject result=orig(player,newObject,data,tileType);
            attempt.Succeeded=attempt.CallbackCount==1 && attempt.Index>=0;
            if(HasNativeChestOutcome(authorization) && TryCommitAuthorizedPlacement(player)) return result;
        }
        catch(Exception e) { ReportPlacedBodyAdmissionFailure("native chest placement aborted: "+e.GetType().Name); }
        finally { _nativeChestAttempt=null; }
        AbortNativeChestAttempt(attempt);
        PendingAuthorizations.Remove(player.whoAmI);
        return data;
    }
    private static bool NativeChestTilePlace(NativeTilePlaceOrig orig,TileObject data)
    {
        NativeChestAttempt? attempt=_nativeChestAttempt;
        bool result=orig(data);
        if(attempt is not null && data.type==attempt.Authorization.ExactPlacement!.TileId && data.style==attempt.Authorization.ExactPlacement.PlaceStyle && data.xCoord==attempt.X && data.yCoord==attempt.Y)
            attempt.TilesWritten=result;
        return result;
    }
    private static int NativeChestPost(NativeChestPostOrig orig,int x,int y,int type,int style,int direction,int alternate)
    {
        NativeChestAttempt? attempt=_nativeChestAttempt;
        if(attempt is null) return orig(x,y,type,style,direction,alternate);
        if(type!=attempt.Authorization.ExactPlacement!.TileId || style!=attempt.Authorization.ExactPlacement.PlaceStyle || x!=attempt.X || y!=attempt.Y+1 || alternate!=0) return -1;
        attempt.CallbackCount++;
        int index=orig(x,y,type,style,direction,alternate);
        attempt.NativeResult=index;attempt.CallbackReturned=true;
        return index;
    }
    private static void AbortNativeChestAttempt(NativeChestAttempt attempt)
    {
        if(attempt.World!=_nativeChestWorld) return;
        if(attempt.Actor is not null && attempt.Index>=0 && attempt.Index<Main.chest.Length
            && ReferenceEquals(Main.chest[attempt.Index],attempt.Actor))
        {
            Chest actor=attempt.Actor;
            if(actor.item is not { Length: 40 } || actor.item.Any(item=>item is { type: > 0, stack: > 0 }))
            { ReportPlacedBodyAdmissionFailure("native chest abort refused: nonempty or foreign actor; source retained"); return; }
            if(actor.x!=attempt.X || actor.y!=attempt.Y)
            {
                // CreateChest assigns its new array slot BEFORE coordinates and
                // Items. A fault there cannot use coordinate-based DestroyChest:
                // it would target some other actor (or return true without removal).
                // Release ONLY this observed, before-null, unpublished empty slot.
                if(attempt.CallbackReturned || attempt.BeforeActors[attempt.Index] is not null)
                { ReportPlacedBodyAdmissionFailure("native chest partial abort refused: foreign actor; source retained");return; }
                // A stale native player.chest integer can refer to this reused
                // index; it is neither ownership of this unpublished actor nor a
                // contents predicate. Leave unrelated native UI state unchanged.
                Main.chest[attempt.Index]=null;
            }
            else if(Chest.FindChest(attempt.X,attempt.Y)!=attempt.Index
                || !Chest.DestroyChest(attempt.X,attempt.Y))
            { ReportPlacedBodyAdmissionFailure("native chest abort refused: native removal failed; source retained");return; }
        }
        // The bounded native TileObject.Place writer owns only these originally
        // empty cells. Never KillTile/drop, clear foreign frames, or erase contents.
        for(int x=attempt.X;x<attempt.X+2;x++) for(int y=attempt.Y;y<attempt.Y+2;y++)
        {
            Tile cell=Main.tile[x,y];
            if(TryResolveMaterialFootprint(x,y,attempt.Authorization.ExactPlacement!.TileId,attempt.Authorization.ExactPlacement.PlaceStyle,
                out int ox,out int oy,out int width,out int height) && ox==attempt.X && oy==attempt.Y && width==2 && height==2) cell.HasTile=false;
        }
    }
    private static TagCompound? CaptureNativeChestWitness(PlacementAuthorization authorization)
    {
        if(!IsNativeChestPlacement(authorization.ExactPlacement) || !HasNativeChestOutcome(authorization)) return null;
        NativeChestAttempt attempt=authorization.ChestAttempt!;
        return new TagCompound { ["version"]=1,["x"]=attempt.X,["y"]=attempt.Y,["tileType"]=authorization.ExactPlacement!.TileId,["nativeStyle"]=authorization.ExactPlacement.PlaceStyle,
            ["bindingId"]=authorization.PlacementBindingId,["definitionHash"]=authorization.DefinitionHash };
    }


    private delegate bool NativeChestDestroyOrig(int x,int y);
    private static bool NativeChestDestroy(NativeChestDestroyOrig orig,int x,int y)
    {
        // Destruction can precede the first bounded maintenance/presentation visit
        // after load. Resolve only the claim at this native origin while the actor
        // and footprint still exist; never rebind a live (already observed) claim.
        PlacementGroup? owner=null;
        if(Placements.TryGetValue(new(GeneratedPlacementLayer.Tile,x,y),out string? id)
            && Groups.TryGetValue(id,out PlacementGroup? group) && group.NativeChest is not null)
        {
            if(group.NativeChestNeedsRebind && ReadNativeChestWitness(group,out int px,out int py) && px==x && py==y)
                NativeChestHealthy(group);
            if(group.ChestWorld==_nativeChestWorld && group.BoundChest is Chest actor && actor.x==x && actor.y==y
                && group.BoundChestIndex>=0 && group.BoundChestIndex<Main.chest.Length
                && ReferenceEquals(Main.chest[group.BoundChestIndex],actor)) owner=group;
        }
        bool result=orig(x,y);
        if(result && owner is not null && !Main.chest.Any(actor=>ReferenceEquals(actor,owner.BoundChest)))
            owner.NativeChestRemoved=true;
        return result;
    }
    private static bool IsNativeChestGroup(PlacementGroup group)
        => group.NativeChest is not null || group.RawNativeChestEnvelope is not null;
    private static bool ReadNativeChestWitness(PlacementGroup group,out int x,out int y)
    {
        x=y=0;
        TagCompound? witness=group.NativeChest;
        try
        {
            if(witness is null || !HasPlacedBodyInt(witness,"version") || witness.GetInt("version")!=1
                || !HasPlacedBodyInt(witness,"x") || !HasPlacedBodyInt(witness,"y")
                || !HasPlacedBodyInt(witness,"tileType") || !HasPlacedBodyInt(witness,"nativeStyle")
                || witness["definitionHash"] is not string hash
                || witness["bindingId"] is not string binding) return false;
            NativeChestDefinitionCertificate? certificate=group.ChestDefinitionCertificate;
            if(certificate is null || certificate.Json!=group.DefinitionJson || certificate.Binding!=binding || certificate.Hash!=hash
                || certificate.TileType!=witness.GetInt("tileType") || certificate.Style!=witness.GetInt("nativeStyle"))
            {
                GeneratedItemData? data=GeneratedItemData.FromJson(group.DefinitionJson);
                bool valid=data is not null && data.Id==group.GeneratedItemId
                    && GeneratedItemRegistryService.DefinitionIdentity(data)==hash
                    && data.RuntimeProgram.Bindings.SingleOrDefault(b=>b.Id==binding)?.UsePolicy.Action.Placement is RuntimePlacementSpec placement
                    && IsNativeChestPlacement(placement) && placement.TileId==witness.GetInt("tileType") && placement.PlaceStyle==witness.GetInt("nativeStyle");
                certificate=group.ChestDefinitionCertificate=new(group.DefinitionJson,binding,hash,witness.GetInt("tileType"),witness.GetInt("nativeStyle"),valid);
            }
            if(!certificate.Valid) return false;
            x=witness.GetInt("x");y=witness.GetInt("y");
            return group.Cells.Count==4 && group.Cells.Distinct().Count()==4 && group.Cells.All(cell=>cell.Layer==GeneratedPlacementLayer.Tile
                && cell.X>=witness.GetInt("x") && cell.X<=witness.GetInt("x")+1 && cell.Y>=witness.GetInt("y") && cell.Y<=witness.GetInt("y")+1);
        }
        catch{return false;}
    }
    private static bool NativeChestFootprint(PlacementGroup group,int x,int y)
        => group.Cells.All(cell=>TryResolveMaterialFootprint(cell.X,cell.Y,group.NativeChest!.GetInt("tileType"),group.NativeChest.GetInt("nativeStyle"),out int ox,out int oy,out int w,out int h)
            && ox==x && oy==y && w==2 && h==2);
    private static void DiagnoseNativeChest(PlacementGroup group,string reason)
    {
        if(group.NativeChestDiagnostic==reason) return;
        group.NativeChestDiagnostic=reason;
        ReportPlacedBodyAdmissionFailure("native chest "+group.GroupId+": "+reason+"; native contents/material claim retained");
    }
    private static bool NativeChestHealthy(PlacementGroup group)
    {
        if(!IsNativeChestGroup(group)) return true;
        if(!ReadNativeChestWitness(group,out int x,out int y)) { DiagnoseNativeChest(group,"invalid_lifecycle_witness");return false; }
        if(group.NativeChestNeedsRebind)
        {
            // Only a legitimate world load grants this one coordinate rebind.
            // Native save/load repacks indices; no cached index or recreated contents.
            group.NativeChestNeedsRebind=false;group.ChestWorld=_nativeChestWorld;
            int index=Chest.FindChest(x,y);
            if(index>=0 && NativeChestInventory(Main.chest[index]) && NativeChestFootprint(group,x,y)) { group.BoundChest=Main.chest[index];group.BoundChestIndex=index; }
        }
        Chest? actor=group.BoundChest;
        if(group.ChestWorld!=_nativeChestWorld || actor is null || actor.x!=x || actor.y!=y
            || !NativeChestInventory(actor) || group.BoundChestIndex<0 || group.BoundChestIndex>=Main.chest.Length
            || !ReferenceEquals(Main.chest[group.BoundChestIndex],actor)
            || Main.chest.Count(current=>current is not null && current.x==x && current.y==y)!=1)
        { DiagnoseNativeChest(group,"missing_or_foreign_native_actor");return false; }
        if(!NativeChestFootprint(group,x,y)) { DiagnoseNativeChest(group,"damaged_native_footprint");return false; }
        return true;
    }
    private static bool NativeChestProjectionLive(PlacementGroup group)
    {
        if(!IsNativeChestGroup(group)) return true;
        if(group.NativeChestNeedsRebind) NativeChestHealthy(group);
        Chest? actor=group.BoundChest;
        return group.NativeChest is not null && !group.NativeChestRemoved && group.ChestWorld==_nativeChestWorld
            && group.BoundChestIndex>=0 && group.BoundChestIndex<Main.chest.Length
            && ReferenceEquals(Main.chest[group.BoundChestIndex],actor) && NativeChestInventory(actor)
            && actor!.x==group.NativeChest.GetInt("x") && actor.y==group.NativeChest.GetInt("y")
            && NativeChestFootprint(group,actor.x,actor.y);
    }

    private static bool CanReleaseNativeChest(PlacementGroup group)
    {
        if(!IsNativeChestGroup(group)) return true;
        if(!ReadNativeChestWitness(group,out int x,out int y) || !group.NativeChestRemoved) return false;
        return Chest.FindChest(x,y)<0 && group.Cells.All(cell=>!Main.tile[cell.X,cell.Y].HasTile);
    }
    private static void RetireNativeChests()
    {
        PlacementGroup[] native=Groups.Values.Where(IsNativeChestGroup).ToArray();
        if(native.Length==0){_nativeChestMaintenanceCursor=0;return;}
        _nativeChestMaintenanceCursor%=native.Length;
        int visits=Math.Min(MaxNativeChestMaintenanceVisits,native.Length);
        for(int i=0;i<visits;i++)
        {
            PlacementGroup group=native[_nativeChestMaintenanceCursor];
            _nativeChestMaintenanceCursor=(_nativeChestMaintenanceCursor+1)%native.Length;
            if(CanReleaseNativeChest(group))
            { GeneratedPlacementKey cell=group.Cells[0];TryQueueReturn(cell.Layer,cell.X,cell.Y); }
            else NativeChestHealthy(group);
        }
    }

    // Native message-34 operation translation, not a generated-item preset.
    // Both vanilla BasicChest tiles use the same native inventory/callback family.
    // Dressers and modded callback families are not certified by this 2x2 bridge.
    private static int NativeChestPlaceAction(int tileType)
        => tileType==TileID.Containers ? 0 : tileType==TileID.Containers2 ? 4 : -1;
    private static bool IsNativeChestPlacement(RuntimePlacementSpec? placement)
        => placement is { WallId: < 0, PlaceStyle: >= 0 } && NativeChestPlaceAction(placement.TileId)>=0
            && TileID.Sets.BasicChest[placement.TileId]
            && placement.PlaceStyle < (placement.TileId==TileID.Containers ? Chest.chestItemSpawn.Length : Chest.chestItemSpawn2.Length);

    private static bool AdmitNativeChestMetadata(RuntimePlacementSpec placement)
    {
        if (!IsNativeChestPlacement(placement) || NativeChestHooks.Count != 6 || _nativeChestSaveGuard is null || _nativeChestPostAllocationGuard is null || _nativeChestCreateAllocationGuard is null || !GeneratedPlacedBodyNativeAdapter.FeatureAvailable
            || placement.PlacedBody is not null && !GeneratedPlacedBodyNativeAdapter.TryAdmitNative(placement.TileId,null,false,out _)) return false;
        try
        {
            // A native veto is executed before mutation. Unknown post-place hooks,
            // unlike vetoes, can introduce another actor/contents owner.
            if(typeof(TileLoader).GetField("HookPlaceInWorld",BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)?.GetValue(null)
                is not Array { Length: 0 }) return false;
            var data = TileObjectData.GetTileData(placement.TileId,placement.PlaceStyle);
            if (data is null) return false;
            var alternates = typeof(TileObjectData).GetProperty("Alternates",BindingFlags.Instance|BindingFlags.NonPublic);
            if (alternates is null) return false;
            var rows = alternates.GetValue(data) as List<TileObjectData>;
            if (rows is { Count: > 256 }) return false;
            return Proved(data) && (rows is null || rows.All(row => row is not null && Proved(row)));
        }
        catch { return false; }

        static bool Hook(PlacementHook value,string name,bool processed)
        {
            Delegate? callback=value.hook;
            MethodInfo? native=typeof(Chest).GetMethod(name,BindingFlags.Static|BindingFlags.Public,null,
                Enumerable.Repeat(typeof(int),6).ToArray(),null);
            return callback is not null && callback.Target is null && callback.GetInvocationList().Length==1
                && callback.Method==native && callback.Method.Module.Assembly==typeof(Chest).Assembly
                && value.badReturn==-1 && value.badResponse==0 && value.processedCoordinates==processed;
        }
        static bool Proved(TileObjectData row)
            => row.Width==2 && row.Height==2 && row.Origin.X==0 && row.Origin.Y==1
                && row.CoordinateWidth==16 && row.CoordinatePadding==2
                && row.CoordinateHeights.SequenceEqual(new[]{16,18}) && row.StyleHorizontal
                && row.CoordinateFullWidth==36 && row.CoordinateFullHeight==38 && row.StyleWrapLimit==0 && row.StyleMultiplier==1
                && (int)row.AnchorBottom.type==11 && row.AnchorBottom.tileCount==2 && row.AnchorBottom.checkStart==0
                && row.AnchorTop.tileCount==0 && row.AnchorLeft.tileCount==0 && row.AnchorRight.tileCount==0
                && row.HookPlaceOverride.hook is null && row.HookPostPlaceEveryone.hook is null
                && Hook(row.HookCheckIfCanPlace,nameof(Chest.FindEmptyChest),true)
                && Hook(row.HookPostPlaceMyPlayer,nameof(Chest.AfterPlacement_Hook),false);
    }
}
