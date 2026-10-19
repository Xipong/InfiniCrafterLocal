#nullable enable
using System;
using System.Linq;
using System.Reflection;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;

namespace InfiniCrafterLocal.Common.Systems;
public sealed partial class GeneratedPlacementLedgerSystem
{
    private static ILHook? _nativeChestSaveGuard;
    private static ILHook? _nativeChestPostAllocationGuard;
    private static ILHook? _nativeChestCreateAllocationGuard;
    private static void InstallNativeChestSaveGuard()
    {
        // Guard the exact native mutation seam below, not unrelated DLL bytes.
        _nativeChestSaveGuard=new ILHook(typeof(Terraria.IO.WorldFile).GetMethod("SaveChests",BindingFlags.Static|BindingFlags.NonPublic|BindingFlags.Public)!,il=>{
            var instructions=il.Body.Instructions;
            int[] sites=Enumerable.Range(0,Math.Max(0,instructions.Count-5)).Where(i=>instructions[i].MatchLdloc(3)
                && (instructions[i+1].OpCode==OpCodes.Brfalse_S || instructions[i+1].OpCode==OpCodes.Brfalse)
                && instructions[i+2].MatchLdsfld<Main>(nameof(Main.chest)) && instructions[i+3].MatchLdloc(1)
                && instructions[i+4].OpCode==OpCodes.Ldnull && instructions[i+5].OpCode==OpCodes.Stelem_Ref).ToArray();
            if(sites.Length!=1 || il.Body.ExceptionHandlers.Count!=0 || il.Body.Variables.Count!=11
                || il.Body.Variables[1].VariableType.MetadataType!=MetadataType.Int32
                || il.Body.Variables[2].VariableType.FullName!="Terraria.Chest"
                || il.Body.Variables[3].VariableType.MetadataType!=MetadataType.Boolean)
                throw new InvalidOperationException("native chest SaveChests prune seam changed");
            var cursor=new ILCursor(il){Index=sites[0]+1};cursor.Emit(OpCodes.Ldloc_1);
            cursor.EmitDelegate<Func<bool,int,bool>>((invalid,index)=>invalid && !PreserveNativeChestClaimInventoryForSave(index));
        },applyByDefault:false);
        _nativeChestSaveGuard.Apply();
    }

    private static void InstallNativeChestAllocationGuards()
    {
        _nativeChestPostAllocationGuard=AllocationGuard(nameof(Chest.AfterPlacement_Hook),1,5,3);
        _nativeChestPostAllocationGuard.Apply();
        _nativeChestCreateAllocationGuard=AllocationGuard(nameof(Chest.CreateChest),0,2,4);
        _nativeChestCreateAllocationGuard.Apply();
    }
    private static ILHook AllocationGuard(string name,int indexLocal,int localCount,int fieldDistance)
        => new ILHook(typeof(Chest).GetMethod(name)!,il=>{
            var instructions=il.Body.Instructions;
            int[] sites=Enumerable.Range(fieldDistance,instructions.Count-fieldDistance).Where(i=>instructions[i].OpCode==OpCodes.Stelem_Ref
                && instructions[i-fieldDistance].MatchLdsfld<Main>(nameof(Main.chest))
                && instructions[i-fieldDistance+1].MatchLdloc(indexLocal)).ToArray();
            if(sites.Length!=1 || il.Body.Variables.Count!=localCount || il.Body.ExceptionHandlers.Count!=0
                || il.Body.Variables[indexLocal].VariableType.MetadataType!=MetadataType.Int32)
                throw new InvalidOperationException("native chest allocation seam changed: "+name);
            var cursor=new ILCursor(il){Index=sites[0]+1};cursor.Emit(OpCodes.Ldloc,il.Body.Variables[indexLocal]);
            cursor.Emit(OpCodes.Ldsfld,typeof(Main).GetField(nameof(Main.chest))!);
            cursor.Emit(OpCodes.Ldloc,il.Body.Variables[indexLocal]);cursor.Emit(OpCodes.Ldelem_Ref);
            cursor.Emit(OpCodes.Ldarg_0);cursor.Emit(OpCodes.Ldarg_1);
            cursor.Emit(name==nameof(Chest.AfterPlacement_Hook) ? OpCodes.Ldc_I4_1 : OpCodes.Ldc_I4_0);
            cursor.EmitDelegate<Action<int,Chest,int,int,bool>>(ObserveNativeChestAllocation);
        },applyByDefault:false);
    private static void ObserveNativeChestAllocation(int index,Chest actor,int x,int y,bool postHook)
    {
        NativeChestAttempt? attempt=_nativeChestAttempt;
        if(attempt is null || attempt.World!=_nativeChestWorld || attempt.CallbackCount!=1
            || x!=attempt.X || y!=(postHook ? attempt.Y+1 : attempt.Y)
            || index<0 || index>=Main.chest.Length || index>=attempt.BeforeActors.Length || attempt.BeforeActors[index] is not null
            || !ReferenceEquals(Main.chest[index],actor)) return;
        // Witness the actual native array assignment, NOT a later FindChest or
        // a scan for actors introduced by another placement/foreign callback.
        attempt.Index=index;attempt.Actor=actor;
    }

    private static bool PreserveNativeChestClaimInventoryForSave(int index)
    {
        if(index<0 || index>=Main.chest.Length || Main.chest[index] is not Chest actor) return false;
        foreach(PlacementGroup group in Groups.Values.Where(IsNativeChestGroup))
        {
            if(group.NativeChestNeedsRebind) NativeChestHealthy(group);
            bool bound=group.ChestWorld==_nativeChestWorld && ReferenceEquals(group.BoundChest,actor);
            bool claimedCoordinate=group.Cells.Count==4 && group.Cells.Distinct().Count()==4
                && group.Cells.All(cell=>cell.Layer==GeneratedPlacementLayer.Tile)
                && group.Cells.Min(cell=>cell.X)==actor.x && group.Cells.Max(cell=>cell.X)==actor.x+1
                && group.Cells.Min(cell=>cell.Y)==actor.y && group.Cells.Max(cell=>cell.Y)==actor.y+1;
            if(bound || claimedCoordinate)
            {
                // Preserve the EXISTING native inventory in the EXISTING native
                // stream even when a foreign actor/invalid witness prevents binding.
                // This is preservation, NOT adoption, footprint repair, contents
                // copying, item ejection or inventory recreation. Unrelated foreign
                // pruning remains native; the exact material claim stays diagnosed.
                DiagnoseNativeChest(group,bound ? "damaged_native_footprint" : "unresolved_native_actor_preserved_for_save");return true;
            }
        }
        return false;
    }
}
