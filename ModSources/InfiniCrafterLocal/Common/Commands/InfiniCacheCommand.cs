#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

/// <summary>
/// Client-side diagnostics and manual warm/clear controls for generated runtime PNG textures.
/// This does not delete generated JSON or PNG files from disk and does not affect gameplay balance.
/// </summary>
public sealed class InfiniCacheCommand : ModCommand
{
    public override CommandType Type => CommandType.Chat;
    public override string Command => "infinicache";
    public override string Usage => "/infinicache [stats|warm|clear|resetbad] [held|inventory|registry] [limit]";
    public override string Description => "Show, warm, or clear the InfiniCraft runtime sprite cache.";

    public override void Action(CommandCaller caller, string input, string[] args)
    {
        string action = args.Length > 0 ? args[0].Trim().ToLowerInvariant() : "stats";
        switch (action)
        {
            case "stats":
            case "status":
                ReplyStats(caller);
                return;
            case "clear":
                ClearCache(caller);
                return;
            case "resetbad":
            case "reset":
                ResetBad(caller);
                return;
            case "warm":
            case "prefetch":
                Warm(caller, args.Skip(1).ToArray());
                return;
            default:
                caller.Reply($"Usage: {Usage}", Color.Orange);
                return;
        }
    }

    private static void ReplyStats(CommandCaller caller)
    {
        var snapshot = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.GetDebugSnapshot();
        var assets = global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.GetDebugSnapshot();
        int registryCount = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.Snapshot().Length ?? 0;
        if (snapshot is null)
        {
            caller.Reply("InfiniCraft cache: runtime sprite cache unavailable.", Color.Orange);
            return;
        }
        string assetText = assets is null
            ? ""
            : $" | asset files {assets.CacheFileCount}, downloading {assets.InFlightCount}, missing {assets.KnownMissingCount}";
        caller.Reply(
            $"InfiniCraft cache: sprites {snapshot.TextureCount}/{snapshot.MaxCachedTextures}, bad {snapshot.MissingOrBadCount}, approx {FormatBytes(snapshot.EstimatedTextureBytes)}, max side {snapshot.MaxTextureDimensionPixels}px, max PNG {snapshot.MaxTextureFileMegabytes}MB | hits {snapshot.HitCount}, misses {snapshot.MissCount}, loads {snapshot.LoadSuccessCount}, evicted {snapshot.EvictionCount}, rejected file {snapshot.RejectedFileSizeCount}, rejected size {snapshot.RejectedDimensionCount}, failed {snapshot.FailedLoadCount} | registry {registryCount}{assetText}",
            Color.LightSkyBlue);
    }

    private static void ClearCache(CommandCaller caller)
    {
        int removed = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.Clear(clearMissingOrBad: true) ?? 0;
        caller.Reply($"InfiniCraft cache: cleared {removed} resident runtime sprite texture(s). Disk PNG/JSON files were not deleted.", Color.LightSkyBlue);
    }

    private static void ResetBad(CommandCaller caller)
    {
        int removed = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.ClearMissingOrBad() ?? 0;
        global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.ResetRetryState();
        caller.Reply($"InfiniCraft cache: cleared {removed} missing/bad sprite backoff record(s) and reset asset retry state.", Color.LightSkyBlue);
    }

    private static void Warm(CommandCaller caller, string[] args)
    {
        if (Main.dedServ)
        {
            caller.Reply("InfiniCraft cache: dedicated server has no client GPU sprite cache to warm.", Color.Orange);
            return;
        }

        Player player = caller.Player;
        if (player is null || !player.active)
        {
            caller.Reply("InfiniCraft cache: no active player for warm scope.", Color.Orange);
            return;
        }

        string scope = args.Length > 0 ? args[0].Trim().ToLowerInvariant() : "inventory";
        int limit = 64;
        if (args.Length > 1 && int.TryParse(args[1], out int parsed))
            limit = Math.Clamp(parsed, 1, 512);

        GeneratedItemData[] selected = scope switch
        {
            "held" => DataFromItem(player.HeldItem) is GeneratedItemData held ? new[] { held } : Array.Empty<GeneratedItemData>(),
            "registry" or "all" => global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.Snapshot().Take(limit).ToArray() ?? Array.Empty<GeneratedItemData>(),
            _ => InventoryGeneratedItems(player).Take(limit).ToArray(),
        };

        int itemCount = 0;
        int pathCount = 0;
        int loaded = 0;
        foreach (var data in selected)
        {
            if (data is null) continue;
            itemCount++;
            try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(data, forceRetry: false); } catch { }
            foreach (string path in RuntimeSpritePaths(data))
            {
                pathCount++;
                Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.TryGet(path);
                if (texture is not null)
                    loaded++;
            }
        }

        var snapshot = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.GetDebugSnapshot();
        string cacheText = snapshot is null ? "" : $" Cache now {snapshot.TextureCount}/{snapshot.MaxCachedTextures}, approx {FormatBytes(snapshot.EstimatedTextureBytes)}.";
        caller.Reply($"InfiniCraft cache: warmed scope '{scope}' over {itemCount} generated item(s), {loaded}/{pathCount} sprite path(s) loaded locally.{cacheText}", Color.LightSkyBlue);
    }

    private static IEnumerable<GeneratedItemData> InventoryGeneratedItems(Player player)
    {
        foreach (var data in ItemsFromArray(player.inventory)) yield return data;
        foreach (var data in ItemsFromArray(player.armor)) yield return data;
        foreach (var data in ItemsFromArray(player.miscEquips)) yield return data;
    }

    private static IEnumerable<GeneratedItemData> ItemsFromArray(Item[]? items)
    {
        if (items is null) yield break;
        foreach (Item item in items)
        {
            var data = DataFromItem(item);
            if (data is not null && !string.IsNullOrWhiteSpace(data.Id) && !string.Equals(data.Id, "placeholder", StringComparison.OrdinalIgnoreCase))
                yield return data;
        }
    }

    private static GeneratedItemData? DataFromItem(Item? item)
    {
        if (item is null || item.IsAir) return null;
        if (item.ModItem is GeneratedItem generated) return generated.Data;
        return null;
    }

    private static IEnumerable<string> RuntimeSpritePaths(GeneratedItemData data)
    {
        if (!string.IsNullOrWhiteSpace(data.Visual?.SpritePath)) yield return data.Visual.SpritePath;
        if (!string.IsNullOrWhiteSpace(data.Visual?.EquipOverlayPath)) yield return data.Visual.EquipOverlayPath;
        foreach (RuntimeEntitySpec entity in data.RuntimeProgram.Entities)
            if (!string.IsNullOrWhiteSpace(entity?.Visual?.SpritePath))
                yield return entity.Visual.SpritePath;
    }

    private static string FormatBytes(long bytes)
    {
        if (bytes < 1024L) return bytes + " B";
        double kb = bytes / 1024.0;
        if (kb < 1024.0) return kb.ToString("0.0") + " KB";
        double mb = kb / 1024.0;
        return mb.ToString("0.0") + " MB";
    }
}
