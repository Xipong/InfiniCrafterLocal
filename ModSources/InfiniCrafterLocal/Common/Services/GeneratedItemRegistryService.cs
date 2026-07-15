#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

// AGENT MAP: world-scoped generated item registry and background hydration gate.
// Full sanitized definitions/plans are allowed here, but only as hydration by
// generatedItemId/specHash-equivalent identity: deduplicated, cached, coalesced
// while in-flight, and never repeated per projectile, per hit, or per VFX event.
// Combat packets should carry compact ids/state and hydrate through this registry.
public sealed class GeneratedHydrationDebugSnapshot
{
    public int InFlightCount { get; init; }
    public int CacheHitCount { get; init; }
    public int CacheMissCount { get; init; }
    public int RetryCount { get; init; }
    public int DuplicateSuppressedCount { get; init; }
    public int HydrationRequestSentCount { get; init; }
    public int CachedDefinitionCount { get; init; }
}

/// <summary>
/// Per-world runtime registry for generated items.
///
/// Important contract:
/// - GeneratedItemData is synchronized once when an item is created/discovered.
/// - Combat/projectile packets only carry compact runtime state + generated item id.
/// - Remote clients restore visuals/VFX from this local registry/cache, not from per-shot JSON.
/// </summary>
public sealed class GeneratedItemRegistryService : IDisposable
{
    public const byte PacketNotifyGeneratedItem = InfiniNetPacketIds.NotifyGeneratedItem;
    public const byte PacketRequestGeneratedRegistry = InfiniNetPacketIds.RequestGeneratedRegistry;
    public const byte PacketRequestGeneratedRegistryForceAssets = InfiniNetPacketIds.RequestGeneratedRegistryForceAssets;
    public const byte PacketRequestGeneratedItemById = InfiniNetPacketIds.RequestGeneratedItemById;

    private const int HydrationRequestRetryTicks = 90;
    private const int FullHydrationRequestRetryTicks = 5 * 60;
    private const int MaxHydrationRequestStateEntries = 2048;
    private const int HydrationRequestStateStaleTicks = 15 * 60;
    private readonly Dictionary<string, GeneratedItemData> _byId = new(StringComparer.Ordinal);
    private readonly Dictionary<string, int> _inFlightGeneratedItemHydration = new(StringComparer.Ordinal);
    private readonly Dictionary<string, int> _lastGeneratedItemHydrationRequestTick = new(StringComparer.Ordinal);
    private bool _fullHydrationInFlight;
    private int _lastFullHydrationRequestTick = -FullHydrationRequestRetryTicks;
    private int _hydrationCacheHitCount;
    private int _hydrationCacheMissCount;
    private int _hydrationRetryCount;
    private int _hydrationDuplicateSuppressedCount;
    private int _hydrationRequestSentCount;
    private readonly object _lock = new();

    public string StoreRoot { get; }

    public static string CurrentWorldIdString()
    {
        try { return Main.worldID.ToString(); }
        catch { return ""; }
    }

    public static bool IsCurrentWorldData(GeneratedItemData? data)
    {
        if (data is null || data.RecipeMeta is null) return false;
        if (!data.RecipeMeta.WorldScoped) return false;
        string expected = CurrentWorldIdString();
        string actual = (data.RecipeMeta.WorldId ?? "").Trim();
        return !string.IsNullOrWhiteSpace(expected)
            && !string.IsNullOrWhiteSpace(actual)
            && string.Equals(actual, expected, StringComparison.Ordinal);
    }

    public static void StampCurrentWorld(GeneratedItemData? data)
    {
        if (data is null) return;
        data.RecipeMeta ??= new RecipeMetaSpec();
        data.RecipeMeta.WorldScoped = true;
        data.RecipeMeta.WorldId = CurrentWorldIdString();
    }

    public void ReloadLocalCacheForCurrentWorld()
    {
        lock (_lock)
        {
            _byId.Clear();
            _inFlightGeneratedItemHydration.Clear();
            _lastGeneratedItemHydrationRequestTick.Clear();
            _fullHydrationInFlight = false;
            _lastFullHydrationRequestTick = -FullHydrationRequestRetryTicks;
        }
        LoadLocalCache();
    }

    public GeneratedItemRegistryService()
    {
        string save = string.IsNullOrWhiteSpace(Main.SavePath) ? AppContext.BaseDirectory : Main.SavePath;
        StoreRoot = Path.Combine(save, "InfiniCrafterLocal", "generated_items");
        Directory.CreateDirectory(StoreRoot);
        LoadLocalCache();
    }

    public void Dispose()
    {
        lock (_lock)
        {
            _byId.Clear();
            _inFlightGeneratedItemHydration.Clear();
            _lastGeneratedItemHydrationRequestTick.Clear();
            _fullHydrationInFlight = false;
        }
    }

    public bool TryGet(string? id, out GeneratedItemData data)
    {
        data = null!;
        if (string.IsNullOrWhiteSpace(id)) return false;
        lock (_lock) return _byId.TryGetValue(id, out data!);
    }

    public GeneratedHydrationDebugSnapshot GetHydrationDebugSnapshot()
    {
        lock (_lock)
        {
            return new GeneratedHydrationDebugSnapshot
            {
                InFlightCount = _inFlightGeneratedItemHydration.Count + (_fullHydrationInFlight ? 1 : 0),
                CacheHitCount = _hydrationCacheHitCount,
                CacheMissCount = _hydrationCacheMissCount,
                RetryCount = _hydrationRetryCount,
                DuplicateSuppressedCount = _hydrationDuplicateSuppressedCount,
                HydrationRequestSentCount = _hydrationRequestSentCount,
                CachedDefinitionCount = _byId.Count,
            };
        }
    }

    public AttackSpec? TryGetAttack(string? id)
    {
        if (!TryGet(id, out var data) || data.Attack is null)
            return null;
        // Cheap deep clone through the already-normalizing generated item contract.
        return GeneratedItemData.FromJson(data.ToJson())?.Attack;
    }

    public VfxManifestSpec TryGetVfxManifest(string? id)
    {
        if (!TryGet(id, out var data))
            return new VfxManifestSpec();
        if (data.VfxManifest is not null && data.VfxManifest.HasSlots)
        {
            data.VfxManifest.Normalize();
            return data.VfxManifest;
        }
        return VfxManifestSpec.FromJson(data.Attack?.VfxManifestJson);
    }

    public void RegisterLocal(GeneratedItemData? data, bool persist = true, bool ensureAssets = true)
    {
        if (data is null) return;
        data.Normalize();
        if (string.IsNullOrWhiteSpace(data.Id) || string.Equals(data.Id, "placeholder", StringComparison.OrdinalIgnoreCase))
            return;
        if (!IsCurrentWorldData(data))
            return;

        lock (_lock)
        {
            _byId[data.Id] = data;
            _inFlightGeneratedItemHydration.Remove(data.Id);
            _lastGeneratedItemHydrationRequestTick.Remove(data.Id);
            _fullHydrationInFlight = false;
        }
        if (persist) PersistOne(data);
        if (ensureAssets)
            InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(data);
        GeneratedProjectile.FlushPendingProjectileVisualSyncForGeneratedItem(data.Id);
        GeneratedProjectile.FlushPendingVfxEventsForGeneratedItem(data.Id);
    }

    public void PublishGeneratedItem(GeneratedItemData? data, int toClient = -1, int ignoreClient = -1)
    {
        if (data is null) return;
        RegisterLocal(data);

        if (Main.netMode == NetmodeID.SinglePlayer)
            return;

        var networkData = PrepareForNetworkSync(data, forceHostAssetMetadata: Main.netMode == NetmodeID.Server);
        var packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketNotifyGeneratedItem);
        packet.Write(networkData.ToNetworkJson());
        if (Main.netMode == NetmodeID.Server)
            packet.Send(toClient, ignoreClient);
        else
            packet.Send();
    }

    public void RequestFullSyncFromServer(bool forceAssetRetry = false)
    {
        if (Main.netMode == NetmodeID.SinglePlayer)
        {
            ForceEnsureAllLocalAssets(forceAssetRetry);
            return;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        if (!ShouldStartFullHydrationRequest())
            return;
        if (forceAssetRetry)
            InfiniCrafterLocalMod.AssetSync?.ResetRetryState();
        var packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(forceAssetRetry ? PacketRequestGeneratedRegistryForceAssets : PacketRequestGeneratedRegistry);
        packet.Send();
    }

    public void RequestOneFromServer(string? generatedItemId, bool forceAssetRetry = true)
    {
        string id = (generatedItemId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id))
            return;
        if (Main.netMode == NetmodeID.SinglePlayer)
        {
            if (TryGet(id, out var data))
                InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(data, forceRetry: forceAssetRetry);
            return;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;
        if (TryGet(id, out var cachedData))
        {
            InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(cachedData, forceRetry: forceAssetRetry);
            return;
        }
        if (!ShouldStartSingleHydrationRequest(id))
            return;
        if (forceAssetRetry)
            InfiniCrafterLocalMod.AssetSync?.ResetRetryState();
        var packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketRequestGeneratedItemById);
        packet.Write(id.Length <= 96 ? id : id[..96]);
        packet.Write(forceAssetRetry);
        packet.Send();
    }

    private bool ShouldStartSingleHydrationRequest(string id)
    {
        int now = (int)Main.GameUpdateCount;
        lock (_lock)
        {
            PruneHydrationRequestStateLocked(now);
            if (_byId.ContainsKey(id))
            {
                _hydrationCacheHitCount++;
                return false;
            }
            bool hadPreviousRequest = _lastGeneratedItemHydrationRequestTick.TryGetValue(id, out int last);
            if (_inFlightGeneratedItemHydration.TryGetValue(id, out int inFlightTick)
                && hadPreviousRequest
                && now - Math.Max(last, inFlightTick) < HydrationRequestRetryTicks)
            {
                _hydrationDuplicateSuppressedCount++;
                return false;
            }
            _hydrationCacheMissCount++;
            if (hadPreviousRequest)
                _hydrationRetryCount++;
            _inFlightGeneratedItemHydration[id] = now;
            _lastGeneratedItemHydrationRequestTick[id] = now;
            PruneHydrationRequestStateLocked(now);
            _hydrationRequestSentCount++;
            return true;
        }
    }

    private void PruneHydrationRequestStateLocked(int now)
    {
        EnforceBoundedTickDictionary(_lastGeneratedItemHydrationRequestTick, now, MaxHydrationRequestStateEntries, HydrationRequestStateStaleTicks);
        EnforceBoundedTickDictionary(_inFlightGeneratedItemHydration, now, MaxHydrationRequestStateEntries, HydrationRequestStateStaleTicks);
    }

    private static void EnforceBoundedTickDictionary(Dictionary<string, int> map, int now, int maxEntries, int maxAgeTicks)
    {
        foreach (string stale in map.Where(x => now - x.Value >= maxAgeTicks).Select(x => x.Key).ToList())
            map.Remove(stale);

        if (map.Count <= maxEntries)
            return;

        foreach (string key in map.OrderBy(x => x.Value).Take(map.Count - maxEntries).Select(x => x.Key).ToList())
            map.Remove(key);
    }

    private bool ShouldStartFullHydrationRequest()
    {
        int now = (int)Main.GameUpdateCount;
        lock (_lock)
        {
            if (_fullHydrationInFlight && now - _lastFullHydrationRequestTick < FullHydrationRequestRetryTicks)
            {
                _hydrationDuplicateSuppressedCount++;
                return false;
            }
            if (_lastFullHydrationRequestTick >= 0)
                _hydrationRetryCount++;
            _fullHydrationInFlight = true;
            _lastFullHydrationRequestTick = now;
            _hydrationRequestSentCount++;
            return true;
        }
    }

    public void ForceEnsureAllLocalAssets(bool forceRetry = false)
    {
        var snapshot = Snapshot();
        if (forceRetry)
            InfiniCrafterLocalMod.AssetSync?.ResetRetryState();
        foreach (var data in snapshot)
            InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(data, forceRetry: forceRetry);
    }

    private static GeneratedItemData PrepareForNetworkSync(GeneratedItemData data, bool forceHostAssetMetadata)
    {
        var clone = GeneratedItemData.FromJson(data.ToNetworkJson()) ?? data;
        if (forceHostAssetMetadata)
            StampHostAssetSyncMetadata(clone, force: true);
        return clone;
    }

    private static void StampHostAssetSyncMetadata(GeneratedItemData data, bool force)
    {
        if (data is null) return;
        data.RecipeMeta ??= new RecipeMetaSpec();
        string baseUrl = InfiniCrafterLocalMod.Generator?.AssetBaseUrlForSharing() ?? "";
        if (force || string.IsNullOrWhiteSpace(data.RecipeMeta.AssetBaseUrl))
            data.RecipeMeta.AssetBaseUrl = baseUrl;
        var files = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
        if (files.Length > 0)
            data.RecipeMeta.AssetFiles = files;
    }

    public void HandlePacket(byte packetType, BinaryReader reader, int whoAmI)
    {
        if (packetType == PacketNotifyGeneratedItem)
        {
            string json = reader.ReadString();

            // Registry notifications are server -> client only. A client must not be
            // able to commit GeneratedItemData into the server registry directly;
            // multiplayer crafting is server-authoritative via PacketRequestServerCraft
            // and receives an explicit CraftCommitResult ACK/FAIL.
            if (Main.netMode == NetmodeID.Server)
                return;

            var data = GeneratedItemData.FromJson(json);
            if (data is null) return;
            RegisterLocal(data);
            return;
        }

        if (packetType == PacketRequestGeneratedRegistry || packetType == PacketRequestGeneratedRegistryForceAssets)
        {
            if (Main.netMode != NetmodeID.Server)
                return;

            // /getinfini is a requester-local catch-up path.  Do NOT call
            // the normal new-item asset broadcast helper here: it rebroadcasts asset notifications
            // to every client and can flood Host & Play with HTTP asset retries while the
            // server is supposed to keep crafting.  The requesting client already clears
            // its local retry/backoff before sending PacketRequestGeneratedRegistryForceAssets;
            // receiving PacketNotifyGeneratedItem is enough to re-run EnsureAssetsForData().
            foreach (var data in Snapshot())
            {
                // Important: do not write the transport clone back here. /getinfini is a
                // read-only catch-up request; PrepareForNetworkSync intentionally creates a
                // transport clone stamped with host asset metadata.  Persisting that clone
                // back into the server registry can downgrade the authoritative full item
                // record after a repair sync and poison later generated-parent crafts.
                var networkData = PrepareForNetworkSync(data, forceHostAssetMetadata: true);
                var packet = InfiniCrafterLocalMod.Instance.GetPacket();
                packet.Write(PacketNotifyGeneratedItem);
                packet.Write(networkData.ToNetworkJson());
                packet.Send(whoAmI);
            }
            return;
        }

        if (packetType == PacketRequestGeneratedItemById)
        {
            string id = reader.ReadString();
            bool forceAssets = reader.ReadBoolean();
            if (Main.netMode != NetmodeID.Server)
                return;
            if (!TryGet(id, out var data))
                return;
            var networkData = PrepareForNetworkSync(data, forceHostAssetMetadata: true);
            var packet = InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketNotifyGeneratedItem);
            packet.Write(networkData.ToNetworkJson());
            packet.Send(whoAmI);
            return;
        }
    }

    public GeneratedItemData[] Snapshot()
    {
        lock (_lock) return _byId.Values.Where(IsCurrentWorldData).ToArray();
    }

    private void LoadLocalCache()
    {
        try
        {
            if (!Directory.Exists(StoreRoot)) return;
            foreach (string file in Directory.EnumerateFiles(StoreRoot, "*.json"))
            {
                try
                {
                    var data = GeneratedItemData.FromJson(File.ReadAllText(file));
                    if (data is not null && !string.IsNullOrWhiteSpace(data.Id) && IsCurrentWorldData(data))
                        _byId[data.Id] = data;
                }
                catch { }
            }
        }
        catch { }
    }

    private void PersistOne(GeneratedItemData data)
    {
        string tempPath = "";
        try
        {
            Directory.CreateDirectory(StoreRoot);
            string safe = SafeFileName(data.Id);
            if (string.IsNullOrWhiteSpace(safe)) return;
            string path = Path.Combine(StoreRoot, safe + ".json");
            tempPath = Path.Combine(StoreRoot, $".{safe}.{Guid.NewGuid():N}.tmp");
            // Local disk cache is not a network packet: keep the full item/debug/prompt
            // contract so tooltips and /infinidumppicture remain useful after restart.
            using (var stream = new FileStream(tempPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false)))
            {
                writer.Write(data.ToLocalCacheJson());
                writer.Flush();
                stream.Flush(flushToDisk: true);
            }
            File.Move(tempPath, path, overwrite: true);
            tempPath = "";
        }
        catch { }
        finally
        {
            if (!string.IsNullOrWhiteSpace(tempPath))
            {
                try { if (File.Exists(tempPath)) File.Delete(tempPath); } catch { }
            }
        }
    }

    private static string SafeFileName(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "";
        raw = raw.Trim();
        if (raw.Length > 80) raw = raw[..80];
        foreach (char c in raw)
            if (!(char.IsLetterOrDigit(c) || c == '_' || c == '-'))
                return "";
        return raw;
    }
}
