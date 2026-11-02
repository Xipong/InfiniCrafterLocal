#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Players;

/// <summary>Definition/image readiness for native HeldItem; never a second pose or animation owner.</summary>
public static class GeneratedHeldItemPresentation
{
    private const int HeldAssetRetryTicks = 90;
    private static readonly Dictionary<string,int> HeldAssetRequestTicks=new(StringComparer.OrdinalIgnoreCase);

    internal static bool HasReadyHeldSprite(PlayerDrawSet draw)
        => TryGetVisibleHeldSpriteData(draw,out var data)
            && global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.TryGet(data!.Visual.SpritePath) is not null;

    internal static bool TryGetVisibleHeldSpriteData(PlayerDrawSet draw,out GeneratedItemData? data)
    {
        data=null;
        var player=draw.drawPlayer;
        if(player is null||!player.active||player.dead||player.frozen)return false;
        Item held=player.HeldItem;
        if(held is null||held.IsAir||held.ModItem is not GeneratedItem item)return false;
        data=item.Data;
        Item presentationItem=held;
        string id=(data.Id??"").Trim();
        // Native lastVisualizedSelectedItem is a clone. Never place the current
        // definition on another selected item's still-cached native draw pose.
        if(draw.heldItem?.ModItem is GeneratedItem nativeItem) {
            if(!string.Equals(id,(nativeItem.Data.Id??"").Trim(),StringComparison.Ordinal)) {data=null;return false;}
            // Artwork and calibration belong to the same accepted snapshot that
            // native HeldItem used for its pose, even during same-ID replacement.
            data=nativeItem.Data;presentationItem=draw.heldItem;
        }
        if(GeneratedItemData.IsPlayerSaveReferenceOnly(data)) {
            RequestHeldItemCatchup(id,null);data=null;return false;
        }
        if(data.Visual.RenderSizePx is null||data.Visual.ForwardAngleDegrees is null)return false;
        if(player.itemAnimation<=0||presentationItem.noUseGraphic||presentationItem.useStyle<=ItemUseStyleID.None)return false;
        if(string.IsNullOrWhiteSpace(data.Visual.SpritePath)) {RequestHeldItemCatchup(id,null);return false;}
        if(global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.TryGet(data.Visual.SpritePath) is null) {
            RequestHeldItemCatchup(id,data.Visual.SpritePath);
        }
        return true;
    }

    public static void ClearAssetRequests()
    {
        lock(HeldAssetRequestTicks)HeldAssetRequestTicks.Clear();
    }
    private static void RequestHeldItemCatchup(string? generatedItemId, string? spritePath)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        string id = (generatedItemId ?? "").Trim();
        string asset = HasPngPath(spritePath) ? GeneratedAssetSyncService.FileNameFromPath(spritePath) : "";
        string key = !string.IsNullOrWhiteSpace(id) ? "item:" + id : "asset:" + asset;
        if (string.IsNullOrWhiteSpace(key) || key == "asset:")
            return;
        int now = (int)Main.GameUpdateCount;
        lock (HeldAssetRequestTicks)
        {
            if (HeldAssetRequestTicks.TryGetValue(key, out int last) && now - last < HeldAssetRetryTicks)
                return;
            HeldAssetRequestTicks[key] = now;
        }
        if (!string.IsNullOrWhiteSpace(id))
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: true);
        else
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer(forceAssetRetry: true);
    }

    private static bool HasPngPath(string? value)
    {
        string s = (value ?? "").Trim();
        return s.EndsWith(".png", StringComparison.OrdinalIgnoreCase) || s.Contains(".png", StringComparison.OrdinalIgnoreCase);
    }

}
