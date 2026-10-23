#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    // Local owned refunds only. Remote escrow remains server-owned and is never
    // represented as a locally claimable row or reconstructed from this view.
    public readonly record struct CraftRefundRow(int Index, string Name, int Stack, int Prefix, string GeneratedId);
    public bool PauseCraftRefundDelivery { get; private set; }

    public IReadOnlyList<CraftRefundRow> CaptureCraftRefunds()
    {
        var rows = new List<CraftRefundRow>();
        for (int i = 0; i < _deferredExitRefunds.Count; i++)
        {
            Item item = _deferredExitRefunds[i];
            if (item is null || item.IsAir || item.stack <= 0) continue;
            rows.Add(new(i, item.Name, item.stack, item.prefix,
                item.ModItem is GeneratedItem generated ? generated.Data?.Id ?? "" : ""));
        }
        return rows.AsReadOnly();
    }

    public bool SetCraftRefundDeliveryPaused(bool paused)
    {
        if (Main.netMode == NetmodeID.Server || Player.whoAmI != Main.myPlayer) return false;
        PauseCraftRefundDelivery = paused;
        return true;
    }

    // Explicit claims deliver only into inventory. A full inventory leaves the
    // exact remainder owned by the existing persisted queue, never on the ground.
    public int ClaimCraftRefunds(int? onlyIndex = null)
    {
        if (Main.netMode == NetmodeID.Server || Player.whoAmI != Main.myPlayer || Player.dead) return 0;
        int delivered = 0;
        for (int i = _deferredExitRefunds.Count - 1; i >= 0; i--)
        {
            if (onlyIndex.HasValue && i != onlyIndex.Value) continue;
            Item item = _deferredExitRefunds[i];
            int before = item?.stack ?? 0;
            if (item is null || item.IsAir || before <= 0) { _deferredExitRefunds.RemoveAt(i); continue; }
            bool complete = TryDeliverRefund(item, allowWorldDrop: false);
            delivered += complete ? before : before - item.stack;
            if (complete) _deferredExitRefunds.RemoveAt(i);
        }
        return delivered;
    }
}
