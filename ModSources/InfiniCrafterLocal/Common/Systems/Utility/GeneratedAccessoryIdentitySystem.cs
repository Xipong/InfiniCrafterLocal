#nullable enable
using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// Fix: native accessory checks see one proxy type for all generated definitions.
/// Substitute definition identity only at the equip/swap comparison callsites;
/// native slot eligibility, wing exclusions and other mods' vetoes still run.
/// </summary>
public sealed class GeneratedAccessoryIdentitySystem : ModSystem
{
    private ILHook? _checkHook;
    private ILHook? _swapHook;
    private static Func<Item, Item, bool>? _nativeIdentity;
    private const BindingFlags StaticPrivate = BindingFlags.Static | BindingFlags.NonPublic;

    public override void Load()
    {
        if (_checkHook is not null || _swapHook is not null) throw Guard("already installed");
        MethodInfo check = typeof(ItemSlot).GetMethod("AccCheck_ForPlayer", StaticPrivate, null,
            new[] { typeof(Player), typeof(Item[]), typeof(Item), typeof(int) }, null)
            ?? throw Guard("AccCheck_ForPlayer signature missing");
        MethodInfo swap = typeof(ItemSlot).GetMethod("AccessorySwap", StaticPrivate, null,
            new[] { typeof(Player), typeof(Item), typeof(Item).MakeByRefType() }, null)
            ?? throw Guard("AccessorySwap signature missing");
        if (check.ReturnType != typeof(bool) || swap.ReturnType != typeof(bool))
            throw Guard("native accessory return contract mismatch");
        // IsTheSameAs is internal in the official runtime assembly. Bind its
        // exact signature once; never copy its implementation or patch it globally.
        MethodInfo identity = typeof(Item).GetMethod("IsTheSameAs", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            null, new[] { typeof(Item) }, null) ?? throw Guard("Item.IsTheSameAs signature missing");
        if (identity.ReturnType != typeof(bool)) throw Guard("native item identity return contract mismatch");
        try
        {
            _nativeIdentity = identity.CreateDelegate<Func<Item, Item, bool>>();
            _checkHook = new ILHook(check, PatchCheck);
            _swapHook = new ILHook(swap, PatchSwap);
            Mod?.Logger?.Info("fix:generated_accessory_definition_identity: installed guarded native equip/swap comparisons");
        }
        catch { Unload(); throw; }
    }

    public override void Unload()
    {
        _swapHook?.Dispose(); _swapHook = null;
        _checkHook?.Dispose(); _checkHook = null;
        _nativeIdentity = null;
    }

    private static InvalidOperationException Guard(string reason)
        => new("Generated accessory identity native bridge: " + reason);

    private static bool SameAccessory(Item left, Item right)
    {
        if (TryDefinitionId(left, out string leftId) && TryDefinitionId(right, out string rightId))
            return string.Equals(leftId, rightId, StringComparison.Ordinal);
        return (_nativeIdentity ?? throw Guard("native identity is unavailable"))(left, right);
    }

    private static bool TryDefinitionId(Item item, out string id)
    {
        id = "";
        if (item.IsAir || !item.accessory || item.ModItem is not GeneratedItem generated
            || generated.Data is not { Accessory.Enabled: true } data
            || GeneratedItemData.IsPlayerSaveReferenceOnly(data) || string.IsNullOrWhiteSpace(data.Id))
            return false;
        id = data.Id;
        return true;
    }

    private static Instruction[] IdentityCalls(ILContext il)
    {
        var sites = il.Body.Instructions.Where(i => (i.OpCode == OpCodes.Call || i.OpCode == OpCodes.Callvirt)
            && i.Operand is MethodReference method
            && method.FullName == "System.Boolean Terraria.Item::IsTheSameAs(Terraria.Item)").ToArray();
        if (sites.Length != 2 || sites.Any(i => i.Next is null
            || i.Next.OpCode != OpCodes.Brfalse && i.Next.OpCode != OpCodes.Brfalse_S))
            throw Guard(il.Method.Name + " identity callsite shape mismatch; no patch applied");
        return sites;
    }

    private static void PatchCheck(ILContext il)
    {
        Instruction[] sites = IdentityCalls(il);
        Instruction first = sites[0], duplicate = sites[1];
        // Exact source bundles and return meanings, independent of IL offsets.
        if (sites.Any(i => il.Body.Instructions.IndexOf(i) < 4
                || il.Body.Instructions.IndexOf(i) + 3 >= il.Body.Instructions.Count)
            || !first.Previous.MatchLdarg(2) || first.Previous.Previous.OpCode != OpCodes.Ldelem_Ref
            || !first.Previous.Previous.Previous.MatchLdarg(3)
            || !first.Previous.Previous.Previous.Previous.MatchLdarg(1)
            || !first.Next.Next.MatchLdcI4(0) || first.Next.Next.Next.OpCode != OpCodes.Ret
            || duplicate.Previous.OpCode != OpCodes.Ldelem_Ref
            || !duplicate.Previous.Previous.MatchLdloc(out _)
            || !duplicate.Previous.Previous.Previous.MatchLdarg(1)
            || !duplicate.Previous.Previous.Previous.Previous.MatchLdarg(2)
            || !duplicate.Next.Next.MatchLdcI4(1) || duplicate.Next.Next.Next.OpCode != OpCodes.Ret)
            throw Guard("AccCheck_ForPlayer identity source/return shape mismatch; no patch applied");
        ReplaceCalls(il, sites);
    }

    private static void PatchSwap(ILContext il)
    {
        Instruction[] sites = IdentityCalls(il);
        Instruction vanilla = sites[0], modded = sites[1];
        if (sites.Any(i => il.Body.Instructions.IndexOf(i) < 5)
            || vanilla.Previous.OpCode != OpCodes.Ldelem_Ref
            || !vanilla.Previous.Previous.MatchLdloc(out _)
            || !vanilla.Previous.Previous.Previous.MatchLdfld<Player>(nameof(Player.armor))
            || !vanilla.Previous.Previous.Previous.Previous.MatchLdarg(0)
            || !vanilla.Previous.Previous.Previous.Previous.Previous.MatchLdarg(1)
            || modded.Previous.OpCode != OpCodes.Ldelem_Ref
            || !modded.Previous.Previous.MatchLdloc(out _)
            || !modded.Previous.Previous.Previous.MatchLdloc(out int accessoryLocal)
            || !modded.Previous.Previous.Previous.Previous.MatchLdarg(1)
            || !il.Body.Instructions.Any(i => i.MatchLdfld("Terraria.ModLoader.Default.ModAccessorySlotPlayer", "exAccessorySlot")
                && i.Next is not null && i.Next.MatchStloc(accessoryLocal)))
            throw Guard("AccessorySwap identity source shape mismatch; no patch applied");
        ReplaceCalls(il, sites);
    }

    private static void ReplaceCalls(ILContext il, Instruction[] sites)
    {
        // Validate every site before modifying any instruction. Keeping the same
        // instruction objects preserves labels, branches and the native stack.
        MethodReference replacement = il.Method.Module.ImportReference(
            typeof(GeneratedAccessoryIdentitySystem).GetMethod(nameof(SameAccessory), StaticPrivate)!);
        foreach (Instruction site in sites)
        {
            site.OpCode = OpCodes.Call;
            site.Operand = replacement;
        }
    }
}
