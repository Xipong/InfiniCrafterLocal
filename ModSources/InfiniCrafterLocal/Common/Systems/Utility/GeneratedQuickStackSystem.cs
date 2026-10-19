#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Content.Items;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.GameContent;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.Systems;

/// <summary>
/// A single proxy Item.type represents many unrelated generated definitions.
/// Old nearby-chest paths use Item.IsTheSameAs; the newer global
/// QuickStack groups by shared netID. Open-chest operations use exact identity.
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
            // The legacy method was removed in 1.4.5; optional exact
            // equality detour is needed only for older native chest routines.
            MethodInfo? same = typeof(Item).GetMethod("IsTheSameAs",
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance, null,
                new[] { typeof(Item) }, null);
            MethodInfo? legacyQuick = typeof(ChestUI).GetMethod(nameof(ChestUI.QuickStack),
                BindingFlags.Public | BindingFlags.Static, null, Type.EmptyTypes, null);
            MethodInfo? quickWithContext = typeof(ChestUI).GetMethod(nameof(ChestUI.QuickStack),
                BindingFlags.Public | BindingFlags.Static, null,
                new[] { typeof(ContainerTransferContext), typeof(bool) }, null);
            if (same is not null)
                _hooks.Add(new Hook(same, (Func<Func<Item, Item, bool>, Item, Item, bool>)NativeSameItem));
            if (legacyQuick is not null)
                _hooks.Add(new Hook(legacyQuick, (Action<Action>)OpenChestQuickStack));
            if (quickWithContext is not null)
                _hooks.Add(new Hook(quickWithContext,
                    (Action<Action<ContainerTransferContext, bool>, ContainerTransferContext, bool>)OpenChestQuickStackWithContext));
            if (legacyQuick is null && quickWithContext is null)
                throw new InvalidOperationException("Unsupported native ChestUI.QuickStack signature");
            MethodInfo nearby = typeof(Player).GetMethod(nameof(Player.QuickStackAllChests),
                BindingFlags.Instance | BindingFlags.Public, null, Type.EmptyTypes, null)
                ?? throw new InvalidOperationException("native Player.QuickStackAllChests signature unavailable");
            _hooks.Add(new Hook(nearby, (Action<Action<Player>, Player>)NearbyQuickStack));
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

    // Terraria's global nearby quickstack indexes chests by the shared item
    // netID (and 1.4.5 Similar Stack can choose categories). There is no safe
    // per-definition target selector in this API. Do not let generated items
    // enter that path and end up in an unrelated chest; explicit opened-chest
    // QuickStack remains available for an exact matching definition.
    private static void NearbyQuickStack(Action<Player> orig, Player player)
    {
        if (player is null) return;
        WithExactQuickStackCandidates(player.inventory, Array.Empty<Item>(), () => {
            if (player.bank4?.item is Item[] voidVault)
                WithExactQuickStackCandidates(voidVault, Array.Empty<Item>(), () => orig(player));
            else
                orig(player);
        });
    }

    private static void OpenChestQuickStack(Action orig)
        => WithQuickStackGuard(orig);

    private static void OpenChestQuickStackWithContext(Action<ContainerTransferContext, bool> orig,
        ContainerTransferContext context, bool voidStack)
        => WithQuickStackGuard(() => orig(context, voidStack));

    private static void WithQuickStackGuard(Action native)
    {
        if (Main.netMode == Terraria.ID.NetmodeID.Server || Main.LocalPlayer is not { } player)
        {
            native();
            return;
        }
        Item[] container;
        try { ChestUI.GetContainerUsageInfo(out _, out container); }
        catch { container = Array.Empty<Item>(); } // refuse unrelated generated candidates on unavailable metadata
        WithExactQuickStackCandidates(player.inventory, container, native);
    }
}
