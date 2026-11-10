#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using MonoMod.RuntimeDetour;
using MonoMod.Cil;
using Terraria;
using Terraria.GameContent.Prefixes;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// tModLoader caches prefix categories by Item.type, but all generated weapons
/// and accessories share one proxy type. Keep the native category rules local
/// to the actual instance; rolling, eligibility and prefix effects remain native.
/// </summary>
public sealed class GeneratedPrefixCategorySystem : ModSystem
{
    private Hook? _categoriesHook;
    private ILHook? _eligibilityHook;
    private ILHook? _statEffectHook;

    public override void Load()
    {
        if (_categoriesHook is not null)
            throw new InvalidOperationException("Generated prefix category hook already installed");
        MethodInfo categories = typeof(Item).GetMethod(nameof(Item.GetPrefixCategories),
            BindingFlags.Instance | BindingFlags.Public, null, Type.EmptyTypes, null)
            ?? throw new InvalidOperationException("tML native Item.GetPrefixCategories signature unavailable");
        if (categories.ReturnType != typeof(List<PrefixCategory>))
            throw new InvalidOperationException("tML native prefix category return type changed");
        try
        {
            _categoriesHook = new Hook(categories,
                (Func<Func<Item, List<PrefixCategory>>, Item, List<PrefixCategory>>)NativeGetPrefixCategories);
            MethodInfo eligibility = typeof(Item).GetMethod(nameof(Item.CanHavePrefixes), Type.EmptyTypes)
                ?? throw new InvalidOperationException("tML native prefix eligibility signature unavailable");
            Type byRef = typeof(float).MakeByRefType();
            MethodInfo statEffect = typeof(Item).GetMethod("TryGetPrefixStatMultipliersForItem",
                BindingFlags.Instance | BindingFlags.NonPublic, null,
                new[] { typeof(int), byRef, byRef, byRef, byRef, byRef, byRef, typeof(int).MakeByRefType() }, null)
                ?? throw new InvalidOperationException("tML native prefix stat-effect signature unavailable");
            if (eligibility.ReturnType != typeof(bool) || statEffect.ReturnType != typeof(bool))
                throw new InvalidOperationException("tML native prefix check return type changed");
            _eligibilityHook = new ILHook(eligibility, il => ProjectDamageChecks(il, 1));
            _statEffectHook = new ILHook(statEffect, il => ProjectDamageChecks(il, 2));
        }
        catch { Unload(); throw; }
    }

    public override void Unload()
    {
        _statEffectHook?.Dispose();
        _statEffectHook = null;
        _eligibilityHook?.Dispose();
        _eligibilityHook = null;
        _categoriesHook?.Dispose();
        _categoriesHook = null;
    }

    // Technical engine projection, not authored data repair: the native body
    // damage predicate cannot represent a damaging projectile-only composition.
    // No ModItem eligibility hook exists before CanHavePrefixes' damage gate.
    // Replace only those reads, preserving native type/stack/ammo/accessory gates,
    // rounding, categories, AllowPrefix, roll and application. Item.damage itself
    // remains zero, including while mod/global prefix callbacks execute.
    private static void ProjectDamageChecks(ILContext il, int expectedReads)
    {
        int reads = 0;
        foreach (var instruction in il.Body.Instructions)
            if (instruction.MatchLdfld<Item>(nameof(Item.damage))) reads++;
        if (reads != expectedReads)
            throw new InvalidOperationException("Generated prefix damage check native source shape changed");
        var cursor = new ILCursor(il);
        while (cursor.TryGotoNext(MoveType.Before, instruction => instruction.MatchLdfld<Item>(nameof(Item.damage))))
        {
            cursor.Remove();
            cursor.EmitDelegate<Func<Item, int>>(PrefixDamageCheckBasis);
        }
    }

    private static int PrefixDamageCheckBasis(Item item)
    {
        if (item.damage != 0 || item.ModItem is not GeneratedItem generated
            || generated.Data.Gameplay.Damage != 0)
            return item.damage;
        int damage = 0;
        foreach (RuntimeBindingSpec binding in generated.Data.RuntimeProgram.Bindings)
        {
            if (binding.Input is not (RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse or RuntimeInputKind.Hold)
                || binding.UsePolicy.Action.Kind != RuntimeBindingAction.SpawnEntity)
                continue;
            RuntimeEntitySpec? root = generated.Data.RuntimeProgram.TryGetEntity(binding.UsePolicy.Action.TargetId);
            if (root is not null && root.IsProjectileEntity && root.Spawn.Enabled && root.Damage.Enabled)
                damage = Math.Max(damage, root.Damage.Damage);
        }
        return damage;
    }

    private static List<PrefixCategory> NativeGetPrefixCategories(
        Func<Item, List<PrefixCategory>> orig, Item item)
    {
        if (item.ModItem is not GeneratedItem generated)
            return orig(item);

        // Match the existing non-usable accessory projection in ApplyToItem.
        // Its neutral damage class must not admit weapon-only crit prefixes.
        // An active hybrid keeps native weapon categories even with zero body
        // damage: its spawned roots, use speed or mana can still benefit.
        bool accessory = item.IsAPrefixableAccessory();
        bool passiveAccessory = accessory
            && generated.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse) is null
            && generated.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.AlternateUse) is null;

        // Otherwise match native Item.GetPrefixCategories, including explicit
        // type-set overrides, for the actual instance.
        // Do not cache the returned mutable list on the type or another item.
        var categories = new List<PrefixCategory>(5);
        if (!passiveAccessory)
        {
            if (PrefixLegacy.ItemSets.SwordsHammersAxesPicks[item.type] || generated.MeleePrefix())
                categories.Add(PrefixCategory.Melee);
            if (PrefixLegacy.ItemSets.GunsBows[item.type] || generated.RangedPrefix())
                categories.Add(PrefixCategory.Ranged);
            if (PrefixLegacy.ItemSets.MagicAndSummon[item.type] || generated.MagicPrefix())
                categories.Add(PrefixCategory.Magic);
            if (PrefixLegacy.ItemSets.SpearsMacesChainsawsDrillsPunchCannon[item.type]
                || PrefixLegacy.ItemSets.BoomerangsChakrams[item.type]
                || PrefixLegacy.ItemSets.ItemsThatCanHaveLegendary2[item.type]
                || generated.WeaponPrefix() || categories.Count != 0)
                categories.Add(PrefixCategory.AnyWeapon);
        }
        if (accessory) categories.Add(PrefixCategory.Accessory);
        return categories;
    }
}
