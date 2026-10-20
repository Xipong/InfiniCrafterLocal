#nullable enable
using System;
using System.Reflection;
using InfiniCrafterLocal.Content.Items;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// Terraria 1.4.4.9 uses Item.IsTheSameAs to select a nearby chest
/// BEFORE calling ItemLoader.TryStackItems. All generated definitions share
/// one proxy Item.type; reject a different definition at the native selector.
/// No custom chest/inventory routing, no modification of player slots.
/// </summary>
public sealed class GeneratedQuickStackSystem : ModSystem
{
    private Hook? _sameItemHook;

    public override void Load()
    {
        if (_sameItemHook is not null)
            throw new InvalidOperationException("Generated chest identity hook already installed");
        MethodInfo same = typeof(Item).GetMethod("IsTheSameAs",
            BindingFlags.Instance | BindingFlags.NonPublic, null, new[] { typeof(Item) }, null)
            ?? throw new InvalidOperationException("tML 1.4.4 native Item.IsTheSameAs signature unavailable");
        if (same.ReturnType != typeof(bool))
            throw new InvalidOperationException("tML 1.4.4 native chest identity return type changed");
        _sameItemHook = new Hook(same,
            (Func<Func<Item, Item, bool>, Item, Item, bool>)NativeSameItem);
    }

    public override void Unload()
    {
        _sameItemHook?.Dispose();
        _sameItemHook = null;
    }

    private static bool NativeSameItem(Func<Item, Item, bool> orig, Item item, Item other)
    {
        if (!orig(item, other)) return false;
        if (item.ModItem is GeneratedItem generated)
            return GeneratedItem.SameGeneratedStack(generated, other);
        // A vanilla/modded item cannot match a different generated instance
        // solely because they happen to have the same proxy type.
        return other.ModItem is not GeneratedItem;
    }
}
