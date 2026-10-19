#nullable enable
using System;
using System.Linq;
using System.Reflection;
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
        // Guard the actual native mutation seam. An unrelated assembly change
        // or a different set of compiler locals does not change this contract.
        _nativeChestSaveGuard=new ILHook(typeof(Terraria.IO.WorldFile).GetMethod("SaveChests",BindingFlags.Static|BindingFlags.NonPublic|BindingFlags.Public)!,il=>{
            var instructions=il.Body.Instructions;
            int[] sites=Enumerable.Range(4,Math.Max(0,instructions.Count-4)).Where(i=>
                instructions[i].OpCode==OpCodes.Stelem_Ref && instructions[i-1].OpCode==OpCodes.Ldnull
                && instructions[i-3].MatchLdsfld<Main>(nameof(Main.chest))
                && instructions[i-4].OpCode.Code is Code.Brfalse or Code.Brfalse_S).ToArray();
            if(sites.Length!=1)
                throw new InvalidOperationException("native chest SaveChests prune seam changed");
            Instruction indexLoad=instructions[sites[0]-2];
            var cursor=new ILCursor(il){Index=sites[0]-4};
            if(indexLoad.Operand is VariableDefinition local) cursor.Emit(indexLoad.OpCode,local);
            else if(indexLoad.OpCode.Code is Code.Ldloc_0 or Code.Ldloc_1 or Code.Ldloc_2 or Code.Ldloc_3)
                cursor.Emit(indexLoad.OpCode);
            else throw new InvalidOperationException("native chest SaveChests index load changed");
            // The same predicate also owns native serialized chest count. Alter
            // it before the branch, not merely the null assignment afterwards.
            cursor.EmitDelegate<Func<bool,int,bool>>((invalid,index)=>
                invalid && !PreserveNativeChestClaimInventoryForSave(index));
        },applyByDefault:false);
        _nativeChestSaveGuard.Apply();
    }

    private static void InstallNativeChestAllocationGuards()
    {
        _nativeChestPostAllocationGuard=AllocationGuard(nameof(Chest.AfterPlacement_Hook),true);
        _nativeChestPostAllocationGuard.Apply();
        _nativeChestCreateAllocationGuard=AllocationGuard(nameof(Chest.CreateChest),false);
        _nativeChestCreateAllocationGuard.Apply();
    }
    private static ILHook AllocationGuard(string name,bool postHook)
        => new ILHook(typeof(Chest).GetMethod(name)!,il=>{
            var instructions=il.Body.Instructions;
            // Native code stores either its freshly constructed Chest temporary,
            // or new Chest(bool) directly. Both leave array/index/actor on stack.
            // A later Chest.item element store has another field/array read and
            // cannot match these direct Main.chest assignment shapes.
            int[] sites=Enumerable.Range(3,Math.Max(0,instructions.Count-3)).Where(i=>
                instructions[i].OpCode==OpCodes.Stelem_Ref && instructions[i-1].OpCode!=OpCodes.Ldnull
                && (instructions[i-3].MatchLdsfld<Main>(nameof(Main.chest))
                    || i>=4 && instructions[i-4].MatchLdsfld<Main>(nameof(Main.chest)))).ToArray();
            if(sites.Length!=1)
                throw new InvalidOperationException("native chest allocation seam changed: "+name);
            var cursor=new ILCursor(il){Index=sites[0]};cursor.Remove();
            cursor.Emit(OpCodes.Ldarg_0);cursor.Emit(OpCodes.Ldarg_1);
            cursor.Emit(postHook ? OpCodes.Ldc_I4_1 : OpCodes.Ldc_I4_0);
            cursor.EmitDelegate<Action<Chest[],int,Chest,int,int,bool>>((actors,index,actor,x,y,post)=>{
                actors[index]=actor;
                if(ReferenceEquals(actors,Main.chest)) ObserveNativeChestAllocation(index,actor,x,y,post);
            });
        },applyByDefault:false);
    private static void ObserveNativeChestAllocation(int index,Chest actor,int x,int y,bool postHook)
    {
        NativeChestAttempt? attempt=_nativeChestAttempt;
        if(attempt is null || attempt.World!=_nativeChestWorld || attempt.CallbackCount!=1
            || x!=attempt.X || y!=(postHook ? attempt.Y+1 : attempt.Y)
            || index<0 || index>=Main.chest.Length || index>=attempt.BeforeActors.Length || attempt.BeforeActors[index] is not null
            || attempt.BeforeActors.Any(previous=>ReferenceEquals(previous,actor))
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
