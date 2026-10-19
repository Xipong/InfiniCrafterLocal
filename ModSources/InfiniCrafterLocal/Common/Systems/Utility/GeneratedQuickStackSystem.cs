#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Content.Items;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// A single proxy Item.type represents many unrelated generated definitions.
/// Terraria's nearby-chest search uses Item.IsTheSameAs and the open-chest
/// QuickStack prefilter uses netID; neither alone distinguishes those items.
/// Leave the native chest transfer, packet and inventory lifecycle untouched.
/// </summary>
public sealed class GeneratedQuickStackSystem : ModSystem
{
    private readonly List<Hook> _hooks = new();

    public override void Load()
    {
        if (_hooks.Count != 0) return;
        try
        {
            MethodInfo same = typeof(Item).GetMethod(nameof(Item.IsTheSameAs),
                BindingFlags.Public | BindingFlags.Instance, null, new[] { typeof(Item) }, null)
                ?? throw new InvalidOperationException("native Item.IsTheSameAs signature unavailable");
            MethodInfo? quick = typeof(ChestUI).GetMethod(nameof(ChestUI.QuickStack),
                BindingFlags.Public | BindingFlags.Static, null, Type.EmptyTypes, null);
            _hooks.Add(new Hook(same, (Func<Func<Item, Item, bool>, Item, Item, bool>)NativeSameItem));
            // The 1.4.4 UI has a no-argument QuickStack with a netID prefilter.
            // Newer tML builds changed that signature and route through hooked
            // Item.CanStack; the legacy prefilter does not exist in that shape.
            if (quick is not null)
                _hooks.Add(new Hook(quick, (Action<Action>)OpenChestQuickStack));
        }
        catch { Unload(); throw; }
    }

    public override void Unload()
    {
        for (int i = _hooks.Count - 1; i >= 0; i--) _hooks[i].Dispose();
        _hooks.Clear();
    }

    private static bool NativeSameItem(Func<Item, Item, bool> orig, Item item, Item other)
    {
        if (!orig(item, other)) return false;
        if (item.ModItem is GeneratedItem generated)
            return GeneratedItem.SameGeneratedStack(generated, other);
        // An unrelated Item using the same native type is not the generated source.
        return other.ModItem is not GeneratedItem;
    }

    internal static bool HasMatchingStoredItem(Item incoming, Item[] container)
    {
        if (incoming?.ModItem is not GeneratedItem || container is null) return false;
        foreach (Item candidate in container)
        {
            if (candidate is null || candidate.IsAir || candidate.type != incoming.type
                || candidate.prefix != incoming.prefix || candidate.ModItem is not GeneratedItem generated
                || !GeneratedItem.SameGeneratedStack(generated, incoming))
                continue;
            if (ItemLoader.CanStack(candidate, incoming))
                return true;
        }
        return false;
    }

    internal static void WithExactQuickStackCandidates(Item[] inventory, Item[] container, Action native)
    {
        var hidden = new List<(int Slot, Item Original)>();
        try
        {
            for (int i = 0; i < Math.Min(58, inventory.Length); i++)
            {
                Item original = inventory[i];
                if (original?.ModItem is not GeneratedItem || HasMatchingStoredItem(original, container))
                    continue;
                hidden.Add((i, original));
                // QuickStack only takes FROM inventory. It never fills an empty
                // player slot, so temporarily hiding this candidate is lossless.
                inventory[i] = new Item();
            }
            native();
        }
        finally
        {
            foreach (var (slot, original) in hidden)
                inventory[slot] = original;
        }
    }

    private static void OpenChestQuickStack(Action orig)
    {
        if (Main.netMode == Terraria.ID.NetmodeID.Server || Main.LocalPlayer is not { } player)
        {
            orig();
            return;
        }
        Item[] container;
        try { ChestUI.GetContainerUsageInfo(out _, out container); }
        catch { container = Array.Empty<Item>(); } // fail closed for generated candidates
        WithExactQuickStackCandidates(player.inventory, container, orig);
    }
}
