#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;

namespace InfiniCrafterLocal.Common.Players;

public partial class InfiniCraftPlayer
{
    private Projectile? _generatedChannelRoot;
    private int _generatedChannelIdentity;
    private Item? _generatedChannelItem;

    internal void TrackGeneratedChannelRoot(Projectile projectile, GeneratedItemData data)
    {
        // The native item action owns admission and StartChanneling. Hydration,
        // peers and descendant spawns cannot manufacture a local channel owner.
        if (!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player) || !Player.channel
            || Player.HeldItem.ModItem is not GeneratedItem held || !ReferenceEquals(held.Data, data))
            return;
        _generatedChannelRoot = projectile;
        _generatedChannelIdentity = projectile.identity;
        _generatedChannelItem = Player.HeldItem;
    }

    internal void CompleteGeneratedChannelRoot(Projectile projectile)
    {
        if (!ReferenceEquals(_generatedChannelRoot, projectile)
            || _generatedChannelIdentity != projectile.identity) return;
        Item? item = _generatedChannelItem;
        _generatedChannelRoot = null;
        _generatedChannelItem = null;
        // A retired root may outlive its item selection. Never cancel a newer
        // channel belonging to another physical item (including another copy).
        if (InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player)
            && ReferenceEquals(Player.HeldItem, item)) Player.channel = false;
    }
}
