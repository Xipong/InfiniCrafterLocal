#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using MonoMod.RuntimeDetour;
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

    public override void Load()
    {
        if (_categoriesHook is not null)
            throw new InvalidOperationException("Generated prefix category hook already installed");
        MethodInfo categories = typeof(Item).GetMethod(nameof(Item.GetPrefixCategories),
            BindingFlags.Instance | BindingFlags.Public, null, Type.EmptyTypes, null)
            ?? throw new InvalidOperationException("tML native Item.GetPrefixCategories signature unavailable");
        if (categories.ReturnType != typeof(List<PrefixCategory>))
            throw new InvalidOperationException("tML native prefix category return type changed");
        _categoriesHook = new Hook(categories,
            (Func<Func<Item, List<PrefixCategory>>, Item, List<PrefixCategory>>)NativeGetPrefixCategories);
    }

    public override void Unload()
    {
        _categoriesHook?.Dispose();
        _categoriesHook = null;
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
