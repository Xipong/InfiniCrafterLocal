#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
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

    private const byte DefinitionTransportVersion = 1;
    private const byte DefinitionHashListVersion = 1;
    private const int MaxKnownDefinitionHashes = 512;
    private const int MaxDefinitionJsonBytes = 256 * 1024;
    private const int MaxIncomingDefinitionTransfers = 128;
    private const int IncomingDefinitionStaleTicks = 30 * 60;
    private const int HydrationRequestRetryTicks = 90;
    private const int FullHydrationRequestRetryTicks = 5 * 60;
    private const int MaxHydrationRequestStateEntries = 2048;
    private const int HydrationRequestStateStaleTicks = 15 * 60;
    private sealed class IncomingDefinitionTransfer
    {
        public string ItemId { get; init; } = "";
        public string Sha256 { get; init; } = "";
        public int UncompressedLength { get; init; }
        public int CompressedLength { get; init; }
        public byte[][] Chunks { get; init; } = Array.Empty<byte[]>();
        public GeneratedAssetWireDescriptor[] Descriptors { get; set; } = Array.Empty<GeneratedAssetWireDescriptor>();
        public int ReceivedCount { get; set; }
        public int LastTick { get; set; }
    }

    private readonly Dictionary<string, GeneratedItemData> _byId = new(StringComparer.Ordinal);
    private readonly Dictionary<string, IncomingDefinitionTransfer> _incomingDefinitions = new(StringComparer.Ordinal);
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
            _incomingDefinitions.Clear();
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
            _incomingDefinitions.Clear();
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

    public RuntimeProgramSpec? TryGetRuntimeProgram(string? id)
    {
        if (!TryGet(id, out GeneratedItemData data)) return null;
        GeneratedItemData? clone = GeneratedItemData.FromJson(data.ToJson());
        return clone?.RuntimeProgram;
    }

    public VfxManifestSpec TryGetVfxManifest(string? id)
    {
        if (!TryGet(id, out GeneratedItemData data)) return VfxManifestSpec.Empty();
        VfxManifestSpec manifest = VfxManifestSpec.FromJson(data.VfxManifest.ToJson());
        return manifest;
    }

    public void RegisterLocal(GeneratedItemData? data, bool persist = true, bool ensureAssets = true)
    {
        if (data is null) return;
        // Player files intentionally carry only a compact identity reference. Never let
        // inventory prefetch or another item-container path downgrade the authoritative
        // runtime record (and its sprite/VFX paths) to placeholder defaults.
        if (GeneratedItemData.IsPlayerSaveReferenceOnly(data))
        {
            GeneratedItemData? canonical = null;
            lock (_lock)
            {
                if (_byId.TryGetValue(data.Id, out GeneratedItemData? existing)
                    && existing is not null
                    && !GeneratedItemData.IsPlayerSaveReferenceOnly(existing))
                    canonical = existing;
            }
            if (ensureAssets && canonical is not null)
                InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(canonical);
            return;
        }
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
    }

    public void PublishGeneratedItem(GeneratedItemData? data, int toClient = -1, int ignoreClient = -1)
    {
        if (data is null) return;
        RegisterLocal(data);
        if (Main.netMode != NetmodeID.Server)
            return;
        InfiniCrafterLocalMod.Generator?.RefreshAssetTransportMetadata();

        if (toClient >= 0)
        {
            EnqueueDefinitionForClient(data, toClient, highPriority: true);
            return;
        }
        for (int client = 0; client < Main.maxPlayers; client++)
        {
            if (client == ignoreClient || !Main.player[client].active) continue;
            EnqueueDefinitionForClient(data, client, highPriority: true);
        }
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
        WriteKnownDefinitionHashes(packet);
        packet.Send();
    }

    public void RequestOneFromServer(
        string? generatedItemId,
        bool forceAssetRetry = true,
        bool forceDefinitionRefresh = false)
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
            GeneratedAssetSyncService? assetSync = InfiniCrafterLocalMod.AssetSync;
            if ((forceDefinitionRefresh || assetSync?.NeedsRemoteDescriptorRefresh(cachedData, forceAssetRetry) == true)
                && ShouldStartSingleHydrationRequest(id, allowCachedDefinition: true))
                SendSingleHydrationRequest(id, forceAssetRetry);
            assetSync?.EnsureAssetsForData(cachedData, forceRetry: forceAssetRetry);
            return;
        }
        if (!ShouldStartSingleHydrationRequest(id))
            return;
        SendSingleHydrationRequest(id, forceAssetRetry);
    }

    private static void SendSingleHydrationRequest(string id, bool forceAssetRetry)
    {
        if (forceAssetRetry)
            InfiniCrafterLocalMod.AssetSync?.ResetRetryState();
        var packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketRequestGeneratedItemById);
        packet.Write(id.Length <= 96 ? id : id[..96]);
        packet.Write(forceAssetRetry);
        packet.Send();
    }

    private bool ShouldStartSingleHydrationRequest(string id, bool allowCachedDefinition = false)
    {
        int now = (int)Main.GameUpdateCount;
        lock (_lock)
        {
            PruneHydrationRequestStateLocked(now);
            bool hasCachedDefinition = _byId.ContainsKey(id);
            if (hasCachedDefinition && !allowCachedDefinition)
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
            if (hasCachedDefinition)
                _hydrationCacheHitCount++;
            else
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

    private void WriteKnownDefinitionHashes(BinaryWriter writer)
    {
        GeneratedItemData[] known = Snapshot().Take(MaxKnownDefinitionHashes).ToArray();
        writer.Write(DefinitionHashListVersion);
        writer.Write((ushort)known.Length);
        foreach (GeneratedItemData data in known)
        {
            string id = data.Id ?? "";
            writer.Write(id.Length <= 96 ? id : id[..96]);
            writer.Write(ComputeDefinitionHash(data));
        }
    }

    private static Dictionary<string, string>? ReadKnownDefinitionHashes(BinaryReader reader)
    {
        try
        {
            byte version = reader.ReadByte();
            ushort count = reader.ReadUInt16();
            if (version != DefinitionHashListVersion || count > MaxKnownDefinitionHashes)
                return null;
            var result = new Dictionary<string, string>(StringComparer.Ordinal);
            for (int i = 0; i < count; i++)
            {
                string id = reader.ReadString().Trim();
                string hash = reader.ReadString().Trim().ToLowerInvariant();
                if (string.IsNullOrWhiteSpace(id) || id.Length > 96 || hash.Length != 64 || !hash.All(Uri.IsHexDigit))
                    return null;
                result[id] = hash;
            }
            return result;
        }
        catch
        {
            return null;
        }
    }

    private static string ComputeDefinitionHash(GeneratedItemData data)
    {
        string networkJson = data.ToNetworkJson();
        GeneratedItemData? clone = GeneratedItemData.FromJson(networkJson);
        if (clone is not null && clone.RecipeMeta is not null)
        {
            clone.RecipeMeta.AssetBaseUrl = "";
            clone.RecipeMeta.AssetFiles = GeneratedAssetSyncService.AssetFilesFromData(clone).ToArray();
            networkJson = clone.ToNetworkJson();
        }
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(networkJson))).ToLowerInvariant();
    }

    private static byte[] CompressDefinition(byte[] raw)
    {
        using var output = new MemoryStream();
        using (var deflate = new DeflateStream(output, CompressionLevel.Fastest, leaveOpen: true))
            deflate.Write(raw, 0, raw.Length);
        return output.ToArray();
    }

    private static byte[]? DecompressDefinition(byte[] compressed, int expectedLength)
    {
        if (expectedLength <= 0 || expectedLength > MaxDefinitionJsonBytes)
            return null;
        try
        {
            using var input = new MemoryStream(compressed, writable: false);
            using var deflate = new DeflateStream(input, CompressionMode.Decompress);
            using var output = new MemoryStream(expectedLength);
            byte[] buffer = new byte[8192];
            int total = 0;
            while (true)
            {
                int read = deflate.Read(buffer, 0, buffer.Length);
                if (read <= 0) break;
                total += read;
                if (total > expectedLength || total > MaxDefinitionJsonBytes) return null;
                output.Write(buffer, 0, read);
            }
            return total == expectedLength ? output.ToArray() : null;
        }
        catch { return null; }
    }

    private void EnqueueDefinitionForClient(GeneratedItemData data, int toClient, bool highPriority)
    {
        if (Main.netMode != NetmodeID.Server || InfiniCrafterLocalMod.AssetSync is null)
            return;
        GeneratedItemData networkData = PrepareForNetworkSync(data, forceHostAssetMetadata: true);
        byte[] raw = Encoding.UTF8.GetBytes(networkData.ToNetworkJson());
        if (raw.Length <= 0 || raw.Length > MaxDefinitionJsonBytes)
            return;
        byte[] compressed = CompressDefinition(raw);
        string transportHash = Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();
        string[] assetRoster = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
        GeneratedAssetWireDescriptor[] descriptors = InfiniCrafterLocalMod.AssetSync.BuildServerAssetDescriptors(data);
        if (assetRoster.Length > 0 && descriptors.Length != assetRoster.Length)
            return;
        int chunkCount = Math.Max(1, (compressed.Length + GeneratedAssetSyncService.ChunkPayloadBytes - 1) / GeneratedAssetSyncService.ChunkPayloadBytes);
        for (int index = 0; index < chunkCount; index++)
        {
            int offset = index * GeneratedAssetSyncService.ChunkPayloadBytes;
            int length = Math.Min(GeneratedAssetSyncService.ChunkPayloadBytes, compressed.Length - offset);
            byte[] payload = new byte[length];
            Buffer.BlockCopy(compressed, offset, payload, 0, length);
            int capturedIndex = index;
            InfiniCrafterLocalMod.AssetSync.EnqueueTransferPacket(
                toClient,
                $"definition:{networkData.Id}:{transportHash}:{capturedIndex}",
                highPriority,
                packet =>
                {
                    packet.Write(PacketNotifyGeneratedItem);
                    packet.Write(DefinitionTransportVersion);
                    packet.Write(networkData.Id.Length <= 96 ? networkData.Id : networkData.Id[..96]);
                    packet.Write(transportHash);
                    packet.Write(raw.Length);
                    packet.Write(compressed.Length);
                    packet.Write((ushort)capturedIndex);
                    packet.Write((ushort)chunkCount);
                    packet.Write((byte)Math.Min(descriptors.Length, GeneratedAssetSyncService.MaxAssetFiles));
                    foreach (GeneratedAssetWireDescriptor descriptor in descriptors.Take(GeneratedAssetSyncService.MaxAssetFiles))
                    {
                        packet.Write(descriptor.FileName);
                        packet.Write(descriptor.Length);
                        packet.Write(descriptor.Sha256);
                    }
                    packet.Write((ushort)payload.Length);
                    packet.Write(payload);
                });
        }
    }

    private void HandleDefinitionChunk(BinaryReader reader)
    {
        byte version = reader.ReadByte();
        string itemId = reader.ReadString().Trim();
        string hash = reader.ReadString().Trim().ToLowerInvariant();
        int uncompressedLength = reader.ReadInt32();
        int compressedLength = reader.ReadInt32();
        ushort chunkIndex = reader.ReadUInt16();
        ushort chunkCount = reader.ReadUInt16();
        byte descriptorCount = reader.ReadByte();
        if (descriptorCount > GeneratedAssetSyncService.MaxAssetFiles) return;
        var descriptors = new List<GeneratedAssetWireDescriptor>(descriptorCount);
        for (int i = 0; i < descriptorCount; i++)
        {
            string file = GeneratedAssetSyncService.FileNameFromPath(reader.ReadString());
            int length = reader.ReadInt32();
            string assetHash = reader.ReadString().Trim().ToLowerInvariant();
            if (!string.IsNullOrWhiteSpace(file) && length > 0 && length <= GeneratedAssetSyncService.MaxAssetBytes && assetHash.Length == 64 && assetHash.All(Uri.IsHexDigit))
                descriptors.Add(new GeneratedAssetWireDescriptor { FileName = file, Length = length, Sha256 = assetHash });
        }
        ushort chunkLength = reader.ReadUInt16();
        byte[] chunk = reader.ReadBytes(chunkLength);

        if (version != DefinitionTransportVersion || Main.netMode == NetmodeID.Server)
            return;
        if (string.IsNullOrWhiteSpace(itemId) || itemId.Length > 96 || hash.Length != 64 || !hash.All(Uri.IsHexDigit))
            return;
        if (uncompressedLength <= 0 || uncompressedLength > MaxDefinitionJsonBytes || compressedLength <= 0 || compressedLength > MaxDefinitionJsonBytes)
            return;
        if (chunkCount <= 0 || chunkCount > 64 || chunkIndex >= chunkCount || chunkLength <= 0 || chunkLength > GeneratedAssetSyncService.ChunkPayloadBytes || chunk.Length != chunkLength)
            return;

        string key = itemId + "|" + hash;
        byte[]? complete = null;
        GeneratedAssetWireDescriptor[] completedDescriptors = Array.Empty<GeneratedAssetWireDescriptor>();
        int now = (int)Main.GameUpdateCount;
        lock (_lock)
        {
            if (!_incomingDefinitions.TryGetValue(key, out IncomingDefinitionTransfer? transfer)
                || transfer.UncompressedLength != uncompressedLength
                || transfer.CompressedLength != compressedLength
                || transfer.Chunks.Length != chunkCount)
            {
                transfer = new IncomingDefinitionTransfer
                {
                    ItemId = itemId,
                    Sha256 = hash,
                    UncompressedLength = uncompressedLength,
                    CompressedLength = compressedLength,
                    Chunks = new byte[chunkCount][],
                    Descriptors = descriptors.ToArray(),
                    LastTick = now,
                };
                _incomingDefinitions[key] = transfer;
            }
            transfer.LastTick = now;
            if (transfer.Descriptors.Length == 0 && descriptors.Count > 0)
                transfer.Descriptors = descriptors.ToArray();
            if (transfer.Chunks[chunkIndex] is null)
            {
                transfer.Chunks[chunkIndex] = chunk;
                transfer.ReceivedCount++;
            }
            if (transfer.ReceivedCount == transfer.Chunks.Length)
            {
                int assembledLength = transfer.Chunks.Sum(x => x?.Length ?? 0);
                if (assembledLength == transfer.CompressedLength)
                {
                    complete = new byte[assembledLength];
                    int offset = 0;
                    foreach (byte[] part in transfer.Chunks)
                    {
                        Buffer.BlockCopy(part, 0, complete, offset, part.Length);
                        offset += part.Length;
                    }
                    completedDescriptors = transfer.Descriptors;
                }
                _incomingDefinitions.Remove(key);
            }
            foreach (string stale in _incomingDefinitions.Where(x => now - x.Value.LastTick > IncomingDefinitionStaleTicks).Select(x => x.Key).ToArray())
                _incomingDefinitions.Remove(stale);
            while (_incomingDefinitions.Count > MaxIncomingDefinitionTransfers)
                _incomingDefinitions.Remove(_incomingDefinitions.OrderBy(x => x.Value.LastTick).First().Key);
        }

        if (complete is null) return;
        byte[]? raw = DecompressDefinition(complete, uncompressedLength);
        if (raw is null || !string.Equals(Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant(), hash, StringComparison.Ordinal))
            return;
        GeneratedItemData? data = GeneratedItemData.FromJson(Encoding.UTF8.GetString(raw));
        if (data is null || !string.Equals(data.Id, itemId, StringComparison.Ordinal) || !IsCurrentWorldData(data))
            return;
        InfiniCrafterLocalMod.AssetSync?.RegisterRemoteAssetDescriptors(itemId, completedDescriptors);
        RegisterLocal(data);
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
        if (InfiniCrafterLocalMod.Generator is GeneratorClient generator)
            generator.StampAssetTransportMetadata(data, refreshBaseUrl: force);
        else
        {
            data.RecipeMeta.AssetTransport = "native";
            data.RecipeMeta.AssetBaseUrl = "";
        }
        data.RecipeMeta.AssetFiles = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
    }

    public void HandlePacket(byte packetType, BinaryReader reader, int whoAmI)
    {
        if (packetType == PacketNotifyGeneratedItem)
        {
            // Definition chunks are server -> client only. Clients never author registry data.
            if (Main.netMode == NetmodeID.Server)
                return;
            HandleDefinitionChunk(reader);
            return;
        }

        if (packetType == PacketRequestGeneratedRegistry || packetType == PacketRequestGeneratedRegistryForceAssets)
        {
            if (Main.netMode != NetmodeID.Server)
                return;

            Dictionary<string, string>? known = ReadKnownDefinitionHashes(reader);
            if (known is null)
                return;
            bool force = packetType == PacketRequestGeneratedRegistryForceAssets;
            foreach (GeneratedItemData data in Snapshot())
            {
                if (!force && known.TryGetValue(data.Id, out string? clientHash)
                    && string.Equals(clientHash, ComputeDefinitionHash(data), StringComparison.Ordinal))
                    continue;
                EnqueueDefinitionForClient(data, whoAmI, highPriority: false);
            }
            return;
        }

        if (packetType == PacketRequestGeneratedItemById)
        {
            if (Main.netMode != NetmodeID.Server)
                return;
            string id;
            try
            {
                id = reader.ReadString().Trim();
                _ = reader.ReadBoolean();
            }
            catch
            {
                return;
            }
            if (string.IsNullOrWhiteSpace(id) || id.Length > 96)
                return;
            if (!TryGet(id, out var data))
                return;
            EnqueueDefinitionForClient(data, whoAmI, highPriority: true);
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
                    string json = File.ReadAllText(file);
                    // Local cache files for every world share this directory. Do a
                    // schema-exact world-id prefilter before strict deserialization so
                    // stale records from unrelated worlds cannot flood diagnostics.
                    // Current-world records still pass through the strict boundary.
                    if (!CacheJsonTargetsCurrentWorld(json))
                        continue;
                    var data = GeneratedItemData.FromJson(json);
                    if (data is not null && !string.IsNullOrWhiteSpace(data.Id) && IsCurrentWorldData(data))
                        _byId[data.Id] = data;
                }
                catch { }
            }
        }
        catch { }
    }

    private static bool CacheJsonTargetsCurrentWorld(string json)
    {
        string expected = CurrentWorldIdString();
        if (string.IsNullOrWhiteSpace(json) || string.IsNullOrWhiteSpace(expected))
            return false;
        try
        {
            using JsonDocument doc = JsonDocument.Parse(json);
            JsonElement root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("recipeMeta", out JsonElement recipeMeta)
                || recipeMeta.ValueKind != JsonValueKind.Object
                || !recipeMeta.TryGetProperty("worldScoped", out JsonElement worldScoped)
                || worldScoped.ValueKind != JsonValueKind.True
                || !recipeMeta.TryGetProperty("worldId", out JsonElement worldId)
                || worldId.ValueKind != JsonValueKind.String)
                return false;
            return string.Equals(worldId.GetString()?.Trim(), expected, StringComparison.Ordinal);
        }
        catch
        {
            return false;
        }
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
