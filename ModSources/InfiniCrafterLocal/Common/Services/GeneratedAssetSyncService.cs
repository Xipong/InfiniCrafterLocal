#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

public sealed class GeneratedAssetSyncDebugSnapshot
{
    public int CacheFileCount { get; init; }
    public int InFlightCount { get; init; }
    public int KnownMissingCount { get; init; }
    public int CacheHitCount { get; init; }
    public int CacheMissCount { get; init; }
    public int RetryCount { get; init; }
    public int DuplicateSuppressedCount { get; init; }
    public int DownloadStartedCount { get; init; }
    public int QueuedChunkCount { get; init; }
}

internal sealed class GeneratedAssetWireDescriptor
{
    public string FileName { get; init; } = "";
    public int Length { get; init; }
    public string Sha256 { get; init; } = "";
    internal string SourcePath { get; init; } = "";
}

/// <summary>
/// One outbound choke point for generated definitions and final gameplay PNGs.
/// Packet transport is primary for Host & Play; bounded HTTP remains a fallback/data plane
/// for a future central server. Files become visible only after SHA-256 verification and
/// atomic .part replacement, so renderers never observe a partial PNG.
/// </summary>
public sealed class GeneratedAssetSyncService : IDisposable
{
    public const int ChunkPayloadBytes = 48 * 1024;
    public const int ChunksPerSecondPerClient = 16;
    public const int HttpDownloadConcurrency = 4;
    public const int MaxAssetBytes = 8 * 1024 * 1024;
    public const int MaxAssetBundleBytes = 16 * 1024 * 1024;
    public const int MaxAssetFiles = 32;

    private const byte AssetTransportVersion = 2;
    private const byte AssetBundlePayloadVersion = 1;
    private const int MaxOutboundChunksPerClient = 512;
    private const int MaxIncomingTransfers = 256;
    private const int MaxInFlightDownloads = 256;
    private const int MaxKnownMissing = 512;
    private const int PacketFallbackDelayTicks = 2 * 60;
    private const int IncomingTransferStaleTicks = 30 * 60;
    private const int ServerAssetRequestCooldownTicks = 90;
    private const int ServerAssetRequestStateStaleTicks = 30 * 60;
    private const int MaxServerAssetRequestStates = 512;
    private const int MaxPngDimensionPixels = 512;
    private static readonly uint[] PngCrcTable = BuildPngCrcTable();
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(12) };
    private static readonly SemaphoreSlim HttpSlots = new(HttpDownloadConcurrency, HttpDownloadConcurrency);
    private static readonly TimeSpan InFlightPruneAge = TimeSpan.FromMinutes(2);
    private static readonly TimeSpan KnownMissingPruneAge = TimeSpan.FromMinutes(5);
    private static readonly TimeSpan MissingRetryAfter = TimeSpan.FromSeconds(30);

    private sealed class QueuedPacket
    {
        public string Key { get; init; } = "";
        public Action<ModPacket> Write { get; init; } = null!;
    }

    private sealed class ClientOutboundQueue
    {
        public readonly Queue<QueuedPacket> Priority = new();
        public readonly Queue<QueuedPacket> Background = new();
        public readonly HashSet<string> QueuedKeys = new(StringComparer.Ordinal);
        public int TokenUnits = 60;
    }

    private sealed class VerifiedServerAsset
    {
        public GeneratedAssetWireDescriptor Descriptor { get; init; } = null!;
        public byte[] Bytes { get; init; } = Array.Empty<byte>();
    }

    private sealed class IncomingAssetTransfer
    {
        public string ItemId { get; init; } = "";
        public string FileName { get; init; } = "";
        public string Sha256 { get; init; } = "";
        public int TotalLength { get; init; }
        public byte[][] Chunks { get; init; } = Array.Empty<byte[]>();
        public int ReceivedCount { get; set; }
        public int LastTick { get; set; }
    }

    private sealed class PendingPacketAsset
    {
        public string ItemId { get; init; } = "";
        public string FileName { get; init; } = "";
        public int RequestedTick { get; set; }
    }

    private readonly Dictionary<string, DateTime> _inFlight = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, DateTime> _knownMissing = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<int, ClientOutboundQueue> _outbound = new();
    private readonly Dictionary<string, IncomingAssetTransfer> _incoming = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, PendingPacketAsset> _pendingPacketAssets = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, int> _serverAssetRequestTicks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Dictionary<string, GeneratedAssetWireDescriptor>> _remoteDescriptorsByItem = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Dictionary<string, GeneratedAssetWireDescriptor>> _serverDescriptorsByItem = new(StringComparer.Ordinal);
    private int _cacheHitCount;
    private int _cacheMissCount;
    private int _retryCount;
    private int _duplicateSuppressedCount;
    private int _downloadStartedCount;
    private readonly object _lock = new();

    public string CacheRoot { get; }

    public GeneratedAssetSyncService()
    {
        string save = string.IsNullOrWhiteSpace(Main.SavePath) ? AppContext.BaseDirectory : Main.SavePath;
        CacheRoot = Path.Combine(save, "InfiniCrafterLocal", "asset_cache");
        Directory.CreateDirectory(CacheRoot);
    }

    public void Dispose()
    {
        lock (_lock)
        {
            _inFlight.Clear();
            _knownMissing.Clear();
            _outbound.Clear();
            _incoming.Clear();
            _pendingPacketAssets.Clear();
            _serverAssetRequestTicks.Clear();
            _remoteDescriptorsByItem.Clear();
            _serverDescriptorsByItem.Clear();
        }
    }

    public string? ResolveLocalPath(string? originalPath)
    {
        string file = FileNameFromPath(originalPath);
        if (string.IsNullOrWhiteSpace(file)) return null;
        string local = Path.Combine(CacheRoot, file);
        return File.Exists(local) ? local : null;
    }

    public void EnsureAssetsForData(GeneratedItemData? data)
        => EnsureAssetsForData(data, forceRetry: false);

    internal static bool IsHttpAssetTransport(GeneratedItemData? data)
        => string.Equals(data?.RecipeMeta?.AssetTransport, "http", StringComparison.OrdinalIgnoreCase);

    public void EnsureAssetsForData(GeneratedItemData? data, bool forceRetry)
    {
        if (data is null || Main.dedServ) return;
        if (!GeneratedItemRegistryService.IsCurrentWorldData(data)) return;

        string itemId = (data.Id ?? "").Trim();
        string[] files = AssetFilesFromData(data).ToArray();
        var missing = new List<string>();
        foreach (string file in files)
        {
            string local = Path.Combine(CacheRoot, file);
            GeneratedAssetWireDescriptor? descriptor = TryGetRemoteDescriptor(itemId, file);
            bool valid = IsValidCachedAsset(local, descriptor);
            if (valid && !forceRetry)
            {
                lock (_lock) _cacheHitCount++;
                continue;
            }
            lock (_lock) _cacheMissCount++;
            missing.Add(file);
        }

        if (missing.Count == 0)
            return;

        if (Main.netMode == NetmodeID.MultiplayerClient && !string.IsNullOrWhiteSpace(itemId))
        {
            if (IsHttpAssetTransport(data))
            {
                string httpBaseUrl = BestBaseUrl(data);
                if (!string.IsNullOrWhiteSpace(httpBaseUrl))
                    QueueDownloads(httpBaseUrl, missing, forceRetry: forceRetry, itemId: itemId);
                return;
            }
            SendAssetRequest(itemId, missing);
            int now = (int)Main.GameUpdateCount;
            lock (_lock)
            {
                foreach (string file in missing)
                {
                    string key = AssetKey(itemId, file);
                    _pendingPacketAssets[key] = new PendingPacketAsset
                    {
                        ItemId = itemId,
                        FileName = file,
                        RequestedTick = now,
                    };
                }
            }
            return;
        }

        string baseUrl = BestBaseUrl(data);
        if (!string.IsNullOrWhiteSpace(baseUrl))
            QueueDownloads(baseUrl, missing, forceRetry: forceRetry);
    }

    internal bool NeedsRemoteDescriptorRefresh(GeneratedItemData? data, bool forceRetry)
    {
        if (data is null || Main.netMode != NetmodeID.MultiplayerClient)
            return false;
        if (!GeneratedItemRegistryService.IsCurrentWorldData(data))
            return false;

        string itemId = (data.Id ?? "").Trim();
        if (string.IsNullOrWhiteSpace(itemId))
            return false;

        foreach (string file in AssetFilesFromData(data))
        {
            string local = Path.Combine(CacheRoot, file);
            GeneratedAssetWireDescriptor? descriptor = TryGetRemoteDescriptor(itemId, file);
            if (NeedsDescriptorRefreshForAsset(local, descriptor, forceRetry))
                return true;
        }
        return false;
    }

    private static bool NeedsDescriptorRefreshForAsset(string local, GeneratedAssetWireDescriptor? descriptor, bool forceRetry)
        => descriptor is null && (forceRetry || !IsValidCachedAsset(local, descriptor: null));

    internal void RegisterRemoteAssetDescriptors(string itemId, IEnumerable<GeneratedAssetWireDescriptor> descriptors)
    {
        itemId = (itemId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(itemId)) return;
        var map = new Dictionary<string, GeneratedAssetWireDescriptor>(StringComparer.OrdinalIgnoreCase);
        foreach (GeneratedAssetWireDescriptor descriptor in descriptors ?? Array.Empty<GeneratedAssetWireDescriptor>())
        {
            string file = SanitizeFileName(descriptor.FileName);
            if (string.IsNullOrWhiteSpace(file) || !IsSha256Hex(descriptor.Sha256)) continue;
            if (descriptor.Length <= 0 || descriptor.Length > MaxAssetBytes) continue;
            map[file] = new GeneratedAssetWireDescriptor
            {
                FileName = file,
                Length = descriptor.Length,
                Sha256 = descriptor.Sha256.ToLowerInvariant(),
            };
        }
        lock (_lock) _remoteDescriptorsByItem[itemId] = map;
    }

    internal GeneratedAssetWireDescriptor[] BuildServerAssetDescriptors(GeneratedItemData data)
    {
        string itemId = (data.Id ?? "").Trim();
        if (!string.IsNullOrWhiteSpace(itemId))
        {
            lock (_lock)
            {
                if (_serverDescriptorsByItem.TryGetValue(itemId, out Dictionary<string, GeneratedAssetWireDescriptor>? cached))
                    return cached.Values.ToArray();
            }
        }

        var descriptors = new List<GeneratedAssetWireDescriptor>();
        foreach (string rawPath in RuntimeAssetPaths(data))
        {
            string file = FileNameFromPath(rawPath);
            if (string.IsNullOrWhiteSpace(file)) continue;
            string source = ResolveServerSourcePath(rawPath, file);
            if (string.IsNullOrWhiteSpace(source)) continue;
            try
            {
                var info = new FileInfo(source);
                if (!info.Exists || info.Length <= 0 || info.Length > MaxAssetBytes) continue;
                string hash = ComputeFileSha256Hex(source);
                descriptors.Add(new GeneratedAssetWireDescriptor
                {
                    FileName = file,
                    Length = checked((int)info.Length),
                    Sha256 = hash,
                    SourcePath = source,
                });
            }
            catch { }
        }

        GeneratedAssetWireDescriptor[] result = descriptors
            .GroupBy(x => x.FileName, StringComparer.OrdinalIgnoreCase)
            .Select(x => x.First())
            .Take(MaxAssetFiles + 1)
            .ToArray();
        if (result.Length > MaxAssetFiles || result.Sum(x => (long)x.Length) > MaxAssetBundleBytes)
            result = Array.Empty<GeneratedAssetWireDescriptor>();
        if (!string.IsNullOrWhiteSpace(itemId))
        {
            lock (_lock)
            {
                if (result.Length > 0)
                    _serverDescriptorsByItem[itemId] = result.ToDictionary(x => x.FileName, StringComparer.OrdinalIgnoreCase);
                else
                    _serverDescriptorsByItem.Remove(itemId);
            }
        }
        return result;
    }

    internal bool HasCompleteServerAssetRoster(GeneratedItemData data)
    {
        string[] files = AssetFilesFromData(data).ToArray();
        if (files.Length == 0)
            return true;
        GeneratedAssetWireDescriptor[] descriptors = BuildServerAssetDescriptors(data);
        return descriptors.Length == files.Length
            && descriptors.Sum(x => (long)x.Length) <= MaxAssetBundleBytes;
    }

    internal void EnqueueTransferPacket(int toClient, string key, bool highPriority, Action<ModPacket> write)
    {
        if (Main.netMode != NetmodeID.Server || toClient < 0 || toClient >= Main.maxPlayers || write is null)
            return;
        lock (_lock)
        {
            if (!_outbound.TryGetValue(toClient, out ClientOutboundQueue? queue))
            {
                queue = new ClientOutboundQueue();
                _outbound[toClient] = queue;
            }
            string priorityKey = key + "|priority";
            string backgroundKey = key + "|background";
            string queueKey = highPriority ? priorityKey : backgroundKey;

            if (highPriority && queue.QueuedKeys.Contains(backgroundKey))
            {
                RemoveQueuedPacket(queue.Background, backgroundKey);
                queue.QueuedKeys.Remove(backgroundKey);
            }
            else if (!highPriority && queue.QueuedKeys.Contains(priorityKey))
            {
                _duplicateSuppressedCount++;
                return;
            }

            if (!queue.QueuedKeys.Add(queueKey))
            {
                _duplicateSuppressedCount++;
                return;
            }
            if (queue.Priority.Count + queue.Background.Count >= MaxOutboundChunksPerClient)
            {
                if (!highPriority || queue.Background.Count == 0)
                {
                    queue.QueuedKeys.Remove(queueKey);
                    _duplicateSuppressedCount++;
                    return;
                }
                QueuedPacket dropped = queue.Background.Dequeue();
                queue.QueuedKeys.Remove(dropped.Key);
            }
            var queued = new QueuedPacket { Key = queueKey, Write = write };
            if (highPriority) queue.Priority.Enqueue(queued);
            else queue.Background.Enqueue(queued);
        }
    }

    private static bool RemoveQueuedPacket(Queue<QueuedPacket> queue, string key)
    {
        bool removed = false;
        int count = queue.Count;
        for (int i = 0; i < count; i++)
        {
            QueuedPacket candidate = queue.Dequeue();
            if (!removed && string.Equals(candidate.Key, key, StringComparison.Ordinal))
            {
                removed = true;
                continue;
            }
            queue.Enqueue(candidate);
        }
        return removed;
    }

    public void UpdateTransfers()
    {
        if (Main.netMode == NetmodeID.Server)
            UpdateServerTransfers();
        else if (Main.netMode == NetmodeID.MultiplayerClient)
            UpdateClientFallbacks();
    }

    private void UpdateServerTransfers()
    {
        List<(int client, QueuedPacket packet)> sends = new();
        lock (_lock)
        {
            foreach ((int client, ClientOutboundQueue queue) in _outbound.ToArray())
            {
                if (client < 0 || client >= Main.maxPlayers || !Main.player[client].active)
                {
                    _outbound.Remove(client);
                    continue;
                }
                queue.TokenUnits = Math.Min(120, queue.TokenUnits + ChunksPerSecondPerClient);
                if (queue.TokenUnits < 60) continue;
                QueuedPacket? next = queue.Priority.Count > 0
                    ? queue.Priority.Dequeue()
                    : queue.Background.Count > 0 ? queue.Background.Dequeue() : null;
                if (next is null) continue;
                queue.TokenUnits -= 60;
                queue.QueuedKeys.Remove(next.Key);
                sends.Add((client, next));
            }
        }

        foreach ((int client, QueuedPacket queued) in sends)
        {
            try
            {
                ModPacket packet = InfiniCrafterLocalMod.Instance.GetPacket();
                queued.Write(packet);
                packet.Send(client);
            }
            catch { }
        }
    }

    private void UpdateClientFallbacks()
    {
        int now = (int)Main.GameUpdateCount;
        var retry = new List<PendingPacketAsset>();
        lock (_lock)
        {
            foreach ((string key, PendingPacketAsset pending) in _pendingPacketAssets.ToArray())
            {
                string local = Path.Combine(CacheRoot, pending.FileName);
                GeneratedAssetWireDescriptor? descriptor = TryGetRemoteDescriptor(pending.ItemId, pending.FileName);
                if (IsValidCachedAsset(local, descriptor))
                {
                    _pendingPacketAssets.Remove(key);
                    continue;
                }
                if (now - pending.RequestedTick < PacketFallbackDelayTicks)
                    continue;
                pending.RequestedTick = now;
                retry.Add(pending);
            }
            foreach (string stale in _incoming.Where(x => now - x.Value.LastTick > IncomingTransferStaleTicks).Select(x => x.Key).ToArray())
                _incoming.Remove(stale);
            while (_incoming.Count > MaxIncomingTransfers)
                _incoming.Remove(_incoming.OrderBy(x => x.Value.LastTick).First().Key);
        }

        foreach (PendingPacketAsset pending in retry)
            SendAssetRequest(pending.ItemId, new[] { pending.FileName });
    }

    public void HandleAssetRequestPacket(BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.Server || whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;

        byte version;
        string itemId;
        byte count;
        try
        {
            version = reader.ReadByte();
            itemId = reader.ReadString().Trim();
            count = reader.ReadByte();
        }
        catch
        {
            return;
        }
        if (version != AssetTransportVersion || string.IsNullOrWhiteSpace(itemId) || itemId.Length > 96 || count <= 0 || count > MaxAssetFiles)
            return;

        var requested = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            for (int i = 0; i < count; i++)
            {
                string file = SanitizeFileName(reader.ReadString());
                if (string.IsNullOrWhiteSpace(file))
                    return;
                requested.Add(file);
            }
        }
        catch
        {
            return;
        }
        if (requested.Count == 0
            || InfiniCrafterLocalMod.GeneratedItems is null
            || !InfiniCrafterLocalMod.GeneratedItems.TryGet(itemId, out GeneratedItemData data)
            || !ShouldStartServerAssetRequest(whoAmI, itemId, requested))
            return;

        GeneratedAssetWireDescriptor[] descriptors = BuildServerAssetDescriptors(data);
        var verified = new List<VerifiedServerAsset>();
        foreach (GeneratedAssetWireDescriptor descriptor in descriptors)
        {
            if (!requested.Contains(descriptor.FileName) || string.IsNullOrWhiteSpace(descriptor.SourcePath))
                continue;
            byte[] bytes;
            try { bytes = File.ReadAllBytes(descriptor.SourcePath); }
            catch { continue; }
            if (bytes.Length != descriptor.Length || bytes.Length <= 0 || bytes.Length > MaxAssetBytes)
                continue;
            if (!IsCompletePng(bytes) || !string.Equals(ComputeSha256Hex(bytes), descriptor.Sha256, StringComparison.OrdinalIgnoreCase))
                continue;
            verified.Add(new VerifiedServerAsset { Descriptor = descriptor, Bytes = bytes });
        }
        EnqueueAssetBundles(whoAmI, itemId, verified);
    }

    private bool ShouldStartServerAssetRequest(int whoAmI, string itemId, IEnumerable<string> files)
    {
        if (!files.Any(x => !string.IsNullOrWhiteSpace(x)))
            return false;
        string key = whoAmI + "|" + itemId;
        int now = (int)Main.GameUpdateCount;
        lock (_lock)
        {
            foreach (string stale in _serverAssetRequestTicks
                .Where(x => now - x.Value > ServerAssetRequestStateStaleTicks)
                .Select(x => x.Key)
                .ToArray())
                _serverAssetRequestTicks.Remove(stale);
            if (_serverAssetRequestTicks.TryGetValue(key, out int last)
                && now - last < ServerAssetRequestCooldownTicks)
            {
                _duplicateSuppressedCount++;
                return false;
            }
            _serverAssetRequestTicks[key] = now;
            while (_serverAssetRequestTicks.Count > MaxServerAssetRequestStates)
                _serverAssetRequestTicks.Remove(_serverAssetRequestTicks.OrderBy(x => x.Value).First().Key);
            return true;
        }
    }

    public void HandleAssetChunkPacket(BinaryReader reader, int whoAmI)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient)
            return;

        byte version;
        string itemId;
        string bundleHash;
        int totalLength;
        ushort chunkIndex;
        ushort chunkCount;
        ushort chunkLength;
        try
        {
            version = reader.ReadByte();
            itemId = reader.ReadString().Trim();
            bundleHash = reader.ReadString().Trim().ToLowerInvariant();
            totalLength = reader.ReadInt32();
            chunkIndex = reader.ReadUInt16();
            chunkCount = reader.ReadUInt16();
            chunkLength = reader.ReadUInt16();
        }
        catch
        {
            return;
        }

        if (version != AssetTransportVersion
            || string.IsNullOrWhiteSpace(itemId)
            || itemId.Length > 96
            || !IsSha256Hex(bundleHash)
            || totalLength <= 0
            || totalLength > MaxAssetBundleBytes
            || chunkCount <= 0
            || chunkCount > 512
            || chunkIndex >= chunkCount
            || chunkLength <= 0
            || chunkLength > ChunkPayloadBytes)
            return;
        if (InfiniCrafterLocalMod.GeneratedItems is null
            || !InfiniCrafterLocalMod.GeneratedItems.TryGet(itemId, out GeneratedItemData data)
            || IsHttpAssetTransport(data))
            return;

        byte[] chunk;
        try { chunk = reader.ReadBytes(chunkLength); }
        catch { return; }
        if (chunk.Length != chunkLength)
            return;

        string key = itemId + "|bundle|" + bundleHash;
        byte[]? complete = null;
        lock (_lock)
        {
            int now = (int)Main.GameUpdateCount;
            foreach (PendingPacketAsset pending in _pendingPacketAssets.Values.Where(x => string.Equals(x.ItemId, itemId, StringComparison.Ordinal)))
                pending.RequestedTick = now;
            if (!_incoming.TryGetValue(key, out IncomingAssetTransfer? transfer)
                || transfer.TotalLength != totalLength
                || transfer.Chunks.Length != chunkCount)
            {
                transfer = new IncomingAssetTransfer
                {
                    ItemId = itemId,
                    Sha256 = bundleHash,
                    TotalLength = totalLength,
                    Chunks = new byte[chunkCount][],
                    LastTick = now,
                };
                _incoming[key] = transfer;
            }
            transfer.LastTick = now;
            if (transfer.Chunks[chunkIndex] is null)
            {
                transfer.Chunks[chunkIndex] = chunk;
                transfer.ReceivedCount++;
            }
            if (transfer.ReceivedCount == transfer.Chunks.Length)
            {
                int assembledLength = transfer.Chunks.Sum(x => x?.Length ?? 0);
                if (assembledLength == transfer.TotalLength)
                {
                    complete = new byte[assembledLength];
                    int offset = 0;
                    foreach (byte[] part in transfer.Chunks)
                    {
                        Buffer.BlockCopy(part, 0, complete, offset, part.Length);
                        offset += part.Length;
                    }
                }
                _incoming.Remove(key);
            }
        }

        if (complete is null || !string.Equals(ComputeSha256Hex(complete), bundleHash, StringComparison.OrdinalIgnoreCase))
            return;
        if (!TryReadVerifiedAssetBundle(itemId, complete, out List<VerifiedServerAsset> assets))
        {
            InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(
                itemId,
                forceAssetRetry: true,
                forceDefinitionRefresh: true);
            return;
        }
        foreach (VerifiedServerAsset asset in assets)
            CommitVerifiedAsset(itemId, asset.Descriptor.FileName, asset.Bytes, asset.Descriptor.Sha256);
    }

    private bool TryReadVerifiedAssetBundle(string itemId, byte[] payload, out List<VerifiedServerAsset> assets)
    {
        assets = new List<VerifiedServerAsset>();
        try
        {
            using var stream = new MemoryStream(payload, writable: false);
            using var reader = new BinaryReader(stream);
            byte version = reader.ReadByte();
            byte count = reader.ReadByte();
            if (version != AssetBundlePayloadVersion || count <= 0 || count > MaxAssetFiles)
                return false;
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < count; i++)
            {
                string file = SanitizeFileName(reader.ReadString());
                string hash = reader.ReadString().Trim().ToLowerInvariant();
                int length = reader.ReadInt32();
                if (string.IsNullOrWhiteSpace(file) || !seen.Add(file) || !IsSha256Hex(hash) || length <= 0 || length > MaxAssetBytes)
                    return false;
                byte[] bytes = reader.ReadBytes(length);
                if (bytes.Length != length || !IsCompletePng(bytes) || !string.Equals(ComputeSha256Hex(bytes), hash, StringComparison.OrdinalIgnoreCase))
                    return false;
                GeneratedAssetWireDescriptor? expected = TryGetRemoteDescriptor(itemId, file);
                if (expected is null
                    || expected.Length != length
                    || !string.Equals(expected.Sha256, hash, StringComparison.OrdinalIgnoreCase))
                    return false;
                assets.Add(new VerifiedServerAsset { Descriptor = expected, Bytes = bytes });
            }
            return stream.Position == stream.Length && assets.Count == count;
        }
        catch
        {
            assets.Clear();
            return false;
        }
    }

    private void EnqueueAssetBundles(int toClient, string itemId, IReadOnlyList<VerifiedServerAsset> assets)
    {
        var group = new List<VerifiedServerAsset>();
        int estimatedBytes = 2;
        foreach (VerifiedServerAsset asset in assets.Take(MaxAssetFiles))
        {
            int entryBytes = asset.Bytes.Length + asset.Descriptor.FileName.Length * 2 + asset.Descriptor.Sha256.Length + 16;
            if (group.Count > 0 && estimatedBytes + entryBytes > MaxAssetBundleBytes)
            {
                EnqueueAssetBundle(toClient, itemId, group);
                group.Clear();
                estimatedBytes = 2;
            }
            group.Add(asset);
            estimatedBytes += entryBytes;
        }
        if (group.Count > 0)
            EnqueueAssetBundle(toClient, itemId, group);
    }

    private void EnqueueAssetBundle(int toClient, string itemId, IReadOnlyList<VerifiedServerAsset> assets)
    {
        byte[] bundle;
        using (var output = new MemoryStream())
        {
            using (var writer = new BinaryWriter(output, System.Text.Encoding.UTF8, leaveOpen: true))
            {
                writer.Write(AssetBundlePayloadVersion);
                writer.Write((byte)assets.Count);
                foreach (VerifiedServerAsset asset in assets)
                {
                    writer.Write(asset.Descriptor.FileName);
                    writer.Write(asset.Descriptor.Sha256);
                    writer.Write(asset.Bytes.Length);
                    writer.Write(asset.Bytes);
                }
            }
            bundle = output.ToArray();
        }
        if (bundle.Length <= 0 || bundle.Length > MaxAssetBundleBytes)
            return;

        string bundleHash = ComputeSha256Hex(bundle);
        int chunkCount = Math.Max(1, (bundle.Length + ChunkPayloadBytes - 1) / ChunkPayloadBytes);
        for (int index = 0; index < chunkCount; index++)
        {
            int offset = index * ChunkPayloadBytes;
            int length = Math.Min(ChunkPayloadBytes, bundle.Length - offset);
            byte[] chunk = new byte[length];
            Buffer.BlockCopy(bundle, offset, chunk, 0, length);
            int capturedIndex = index;
            EnqueueTransferPacket(
                toClient,
                $"assetbundle:{itemId}:{bundleHash}:{capturedIndex}",
                highPriority: true,
                packet =>
                {
                    packet.Write(InfiniNetPacketIds.GeneratedAssetChunk);
                    packet.Write(AssetTransportVersion);
                    packet.Write(itemId);
                    packet.Write(bundleHash);
                    packet.Write(bundle.Length);
                    packet.Write((ushort)capturedIndex);
                    packet.Write((ushort)chunkCount);
                    packet.Write((ushort)chunk.Length);
                    packet.Write(chunk);
                });
        }
    }

    private void SendAssetRequest(string itemId, IEnumerable<string> files)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient) return;
        string[] safe = files.Select(SanitizeFileName).Where(x => !string.IsNullOrWhiteSpace(x)).Distinct(StringComparer.OrdinalIgnoreCase).Take(MaxAssetFiles).ToArray();
        if (safe.Length == 0) return;
        ModPacket packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(InfiniNetPacketIds.RequestGeneratedAsset);
        packet.Write(AssetTransportVersion);
        packet.Write(itemId.Length <= 96 ? itemId : itemId[..96]);
        packet.Write((byte)safe.Length);
        foreach (string file in safe) packet.Write(file);
        packet.Send();
    }

    public void ResetRetryState()
    {
        lock (_lock)
        {
            _knownMissing.Clear();
            _pendingPacketAssets.Clear();
        }
        LocalHttpQuietFailure.ClearAll();
    }

    public GeneratedAssetSyncDebugSnapshot GetDebugSnapshot()
    {
        int cacheFiles = 0;
        try
        {
            if (Directory.Exists(CacheRoot))
                cacheFiles = Directory.EnumerateFiles(CacheRoot, "*.png", SearchOption.TopDirectoryOnly).Count();
        }
        catch { }

        lock (_lock)
        {
            return new GeneratedAssetSyncDebugSnapshot
            {
                CacheFileCount = cacheFiles,
                InFlightCount = _inFlight.Count + _incoming.Count,
                KnownMissingCount = _knownMissing.Count,
                CacheHitCount = _cacheHitCount,
                CacheMissCount = _cacheMissCount,
                RetryCount = _retryCount,
                DuplicateSuppressedCount = _duplicateSuppressedCount,
                DownloadStartedCount = _downloadStartedCount,
                QueuedChunkCount = _outbound.Values.Sum(x => x.Priority.Count + x.Background.Count),
            };
        }
    }

    public void QueueDownloads(string baseUrl, IEnumerable<string> files, bool forceRetry = false, string itemId = "")
    {
        if (Main.dedServ) return;
        baseUrl = SanitizeBaseUrl(baseUrl);
        if (string.IsNullOrWhiteSpace(baseUrl)) return;
        DateTime now = DateTime.UtcNow;
        string endpointGuardKey = "asset:" + baseUrl;
        if (forceRetry) LocalHttpQuietFailure.Clear(endpointGuardKey);
        else if (LocalHttpQuietFailure.ShouldSkip(endpointGuardKey)) return;

        foreach (string raw in files ?? Array.Empty<string>())
        {
            string file = SanitizeFileName(raw);
            if (string.IsNullOrWhiteSpace(file)) continue;
            string local = Path.Combine(CacheRoot, file);
            GeneratedAssetWireDescriptor? descriptor = string.IsNullOrWhiteSpace(itemId)
                ? TryFindRemoteDescriptor(file)
                : TryGetRemoteDescriptor(itemId, file);
            if (Main.netMode == NetmodeID.MultiplayerClient && descriptor is null)
                continue;
            if (IsValidCachedAsset(local, descriptor) && !forceRetry)
            {
                lock (_lock) _cacheHitCount++;
                continue;
            }
            string key = baseUrl + "|" + itemId + "|" + file;
            lock (_lock)
            {
                ClearExpiredInFlightAndMissingLocked(now);
                _cacheMissCount++;
                if (_inFlight.ContainsKey(key))
                {
                    _duplicateSuppressedCount++;
                    continue;
                }
                if (!forceRetry && _knownMissing.TryGetValue(key, out DateTime lastMissing))
                {
                    if (now - lastMissing < MissingRetryAfter)
                    {
                        _duplicateSuppressedCount++;
                        continue;
                    }
                    _knownMissing.Remove(key);
                    _retryCount++;
                }
                if (forceRetry && _knownMissing.Remove(key)) _retryCount++;
                if (_inFlight.Count >= MaxInFlightDownloads)
                {
                    _duplicateSuppressedCount++;
                    continue;
                }
                _inFlight[key] = now;
                _downloadStartedCount++;
            }
            _ = DownloadOneAsync(baseUrl, itemId, file, local, key, descriptor);
        }
    }

    private async Task DownloadOneAsync(string baseUrl, string itemId, string file, string local, string key, GeneratedAssetWireDescriptor? descriptor)
    {
        await HttpSlots.WaitAsync().ConfigureAwait(false);
        bool integrityFailure = false;
        try
        {
            Directory.CreateDirectory(CacheRoot);
            string url = baseUrl.TrimEnd('/') + "/get_asset?file=" + Uri.EscapeDataString(file);
            byte[] bytes = await DownloadAssetBytesWithBoundedStreamAsync(url).ConfigureAwait(false);
            LocalHttpQuietFailure.Clear("asset:" + SanitizeBaseUrl(baseUrl));
            if (bytes.Length <= 0 || bytes.Length > MaxAssetBytes)
            {
                integrityFailure = true;
                throw new InvalidDataException("asset size out of range");
            }
            if (!IsCompletePng(bytes))
            {
                integrityFailure = true;
                throw new InvalidDataException("asset is not png");
            }
            string actualHash = ComputeSha256Hex(bytes);
            if (descriptor is not null && (descriptor.Length != bytes.Length || !string.Equals(descriptor.Sha256, actualHash, StringComparison.OrdinalIgnoreCase)))
            {
                integrityFailure = true;
                throw new InvalidDataException("asset hash mismatch");
            }
            CommitVerifiedAsset(itemId, file, bytes, actualHash);
        }
        catch (Exception ex)
        {
            if (LocalHttpQuietFailure.IsExpectedOffline(ex))
                LocalHttpQuietFailure.Record("asset:" + SanitizeBaseUrl(baseUrl), ex, TimeSpan.FromSeconds(60));
            lock (_lock) _knownMissing[key] = DateTime.UtcNow;
            if (integrityFailure && Main.netMode == NetmodeID.MultiplayerClient && !string.IsNullOrWhiteSpace(itemId))
            {
                Main.QueueMainThreadAction(() => InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(
                    itemId,
                    forceAssetRetry: true,
                    forceDefinitionRefresh: true));
            }
        }
        finally
        {
            HttpSlots.Release();
            lock (_lock)
            {
                _inFlight.Remove(key);
                ClearExpiredInFlightAndMissingLocked(DateTime.UtcNow);
            }
        }
    }

    private void CommitVerifiedAsset(string itemId, string file, byte[] bytes, string expectedHash)
    {
        if (!IsCompletePng(bytes) || !string.Equals(ComputeSha256Hex(bytes), expectedHash, StringComparison.OrdinalIgnoreCase))
            return;
        string local = Path.Combine(CacheRoot, file);
        string partPath = local + ".part";
        try
        {
            Directory.CreateDirectory(CacheRoot);
            lock (_lock)
            {
                File.WriteAllBytes(partPath, bytes);
                File.Move(partPath, local, overwrite: true);
                foreach (string key in _pendingPacketAssets.Where(x =>
                    string.Equals(x.Value.ItemId, itemId, StringComparison.Ordinal)
                    && string.Equals(x.Value.FileName, file, StringComparison.OrdinalIgnoreCase)).Select(x => x.Key).ToArray())
                    _pendingPacketAssets.Remove(key);
            }
            Main.QueueMainThreadAction(() => InfiniCrafterLocalMod.Sprites?.Invalidate(local));
        }
        catch
        {
            try { if (File.Exists(partPath)) File.Delete(partPath); } catch { }
        }
    }

    private async Task<byte[]> DownloadAssetBytesWithBoundedStreamAsync(string url)
    {
        using HttpResponseMessage response = await Http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        long? contentLength = response.Content.Headers.ContentLength;
        if (contentLength.HasValue && contentLength.Value > MaxAssetBytes)
            throw new InvalidDataException($"asset size {contentLength.Value} exceeds maximum {MaxAssetBytes}");
        await using Stream stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
        using MemoryStream memory = new(capacity: (int)Math.Min(Math.Max(contentLength.GetValueOrDefault(1024), 1024), MaxAssetBytes + 1024));
        byte[] buffer = new byte[8192];
        int total = 0;
        while (true)
        {
            int read = await stream.ReadAsync(buffer.AsMemory(0, buffer.Length)).ConfigureAwait(false);
            if (read <= 0) break;
            total += read;
            if (total > MaxAssetBytes) throw new InvalidDataException($"asset size exceeded maximum {MaxAssetBytes}");
            await memory.WriteAsync(buffer.AsMemory(0, read)).ConfigureAwait(false);
        }
        return memory.ToArray();
    }

    private GeneratedAssetWireDescriptor? TryGetRemoteDescriptor(string itemId, string file)
    {
        lock (_lock)
            return _remoteDescriptorsByItem.TryGetValue(itemId, out var map) && map.TryGetValue(file, out var descriptor) ? descriptor : null;
    }

    private GeneratedAssetWireDescriptor? TryFindRemoteDescriptor(string file)
    {
        lock (_lock)
        {
            foreach (var map in _remoteDescriptorsByItem.Values)
                if (map.TryGetValue(file, out GeneratedAssetWireDescriptor? descriptor)) return descriptor;
        }
        return null;
    }

    private static bool IsValidCachedAsset(string local, GeneratedAssetWireDescriptor? descriptor)
    {
        try
        {
            if (!File.Exists(local)) return false;
            var info = new FileInfo(local);
            if (info.Length <= 0 || info.Length > MaxAssetBytes) return false;
            byte[] bytes = File.ReadAllBytes(local);
            if (!IsCompletePng(bytes)) return false;
            if (descriptor is null) return true;
            if (bytes.Length != descriptor.Length) return false;
            return string.Equals(ComputeSha256Hex(bytes), descriptor.Sha256, StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }

    private string ResolveServerSourcePath(string rawPath, string file)
    {
        try { if (!string.IsNullOrWhiteSpace(rawPath) && File.Exists(rawPath)) return Path.GetFullPath(rawPath); } catch { }
        try
        {
            string cached = Path.Combine(CacheRoot, file);
            if (File.Exists(cached)) return cached;
        }
        catch { }
        return "";
    }

    private static IEnumerable<string> RuntimeAssetPaths(GeneratedItemData data)
    {
        yield return data.Visual?.SpritePath ?? "";
        yield return data.Visual?.EquipOverlayPath ?? "";
        foreach (RuntimeEntitySpec entity in data.RuntimeProgram.Entities)
            if (entity?.Visual is not null)
            {
                yield return entity.Visual.SpritePath ?? "";
                yield return entity.Visual.ImpactSpritePath ?? "";
            }
    }

    public static IEnumerable<string> AssetFilesFromData(GeneratedItemData data)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string path in RuntimeAssetPaths(data))
        {
            string file = FileNameFromPath(path);
            if (!string.IsNullOrWhiteSpace(file) && file.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                seen.Add(file);
        }
        if (seen.Count > MaxAssetFiles)
            throw new InvalidDataException($"generated asset roster exceeds {MaxAssetFiles} files");
        return seen.ToArray();
    }

    public static string FileNameFromPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) return "";
        string p = path.Trim();
        if (Uri.TryCreate(p, UriKind.Absolute, out var uri) && (uri.Scheme == "http" || uri.Scheme == "https")) p = uri.LocalPath;
        p = p.Replace('\\', '/');
        return SanitizeFileName(Path.GetFileName(p));
    }

    private static string SanitizeFileName(string? file)
    {
        if (string.IsNullOrWhiteSpace(file)) return "";
        file = Path.GetFileName(file.Trim());
        if (file.Length > 160 || !file.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) return "";
        foreach (char c in file)
            if (!(char.IsLetterOrDigit(c) || c == '.' || c == '_' || c == '-' || c == '@' || c == '+')) return "";
        return file;
    }

    private static string SanitizeBaseUrl(string? url)
    {
        if (string.IsNullOrWhiteSpace(url)) return "";
        url = url.Trim().TrimEnd('/');
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri)) return "";
        if (uri.Scheme != "http" && uri.Scheme != "https") return "";
        return uri.GetLeftPart(UriPartial.Authority);
    }

    private string BestBaseUrl(GeneratedItemData data)
    {
        string meta = SanitizeBaseUrl(data.RecipeMeta?.AssetBaseUrl ?? "");
        if (!string.IsNullOrWhiteSpace(meta)) return meta;
        return InfiniCrafterLocalMod.Generator?.AssetBaseUrlForSharing() ?? "";
    }

    private static string AssetKey(string itemId, string file) => itemId + "|" + file;
    private static bool IsSha256Hex(string value) => value.Length == 64 && value.All(Uri.IsHexDigit);
    private static string ComputeSha256Hex(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static string ComputeFileSha256Hex(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }
    private static bool IsCompletePng(byte[] bytes)
    {
        try
        {
            ReadOnlySpan<byte> png = bytes;
            if (!HasPngSignature(png)) return false;

            int offset = 8;
            bool seenIhdr = false;
            bool seenPlte = false;
            bool seenIdat = false;
            bool idatEnded = false;
            int width = 0;
            int height = 0;
            byte bitDepth = 0;
            byte colorType = 0;
            byte interlace = 0;
            using var idat = new MemoryStream();

            while (offset <= png.Length - 12)
            {
                uint rawLength = BinaryPrimitives.ReadUInt32BigEndian(png.Slice(offset, 4));
                if (rawLength > MaxAssetBytes) return false;
                int length = (int)rawLength;
                int dataOffset = offset + 8;
                int crcOffset = dataOffset + length;
                if (crcOffset < dataOffset || crcOffset + 4 > png.Length) return false;

                ReadOnlySpan<byte> typeBytes = png.Slice(offset + 4, 4);
                ReadOnlySpan<byte> dataBytes = png.Slice(dataOffset, length);
                uint storedCrc = BinaryPrimitives.ReadUInt32BigEndian(png.Slice(crcOffset, 4));
                if (storedCrc != ComputePngChunkCrc(typeBytes, dataBytes)) return false;
                uint type = BinaryPrimitives.ReadUInt32BigEndian(typeBytes);
                offset = crcOffset + 4;

                switch (type)
                {
                    case 0x49484452: // IHDR
                        if (seenIhdr || seenIdat || length != 13) return false;
                        width = checked((int)BinaryPrimitives.ReadUInt32BigEndian(dataBytes.Slice(0, 4)));
                        height = checked((int)BinaryPrimitives.ReadUInt32BigEndian(dataBytes.Slice(4, 4)));
                        bitDepth = dataBytes[8];
                        colorType = dataBytes[9];
                        if (width <= 0 || width > MaxPngDimensionPixels || height <= 0 || height > MaxPngDimensionPixels)
                            return false;
                        if (!IsValidPngBitDepth(colorType, bitDepth)
                            || dataBytes[10] != 0
                            || dataBytes[11] != 0
                            || dataBytes[12] > 1)
                            return false;
                        interlace = dataBytes[12];
                        seenIhdr = true;
                        break;

                    case 0x504C5445: // PLTE
                        if (!seenIhdr || seenIdat || seenPlte || length == 0 || length % 3 != 0 || length > 768)
                            return false;
                        seenPlte = true;
                        break;

                    case 0x49444154: // IDAT
                        if (!seenIhdr || idatEnded || length == 0 || idat.Length + length > MaxAssetBytes)
                            return false;
                        idat.Write(dataBytes);
                        seenIdat = true;
                        break;

                    case 0x49454E44: // IEND
                        if (!seenIhdr || !seenIdat || length != 0 || offset != png.Length)
                            return false;
                        if (colorType == 3 && !seenPlte)
                            return false;
                        return ValidatePngScanlines(idat.ToArray(), width, height, bitDepth, colorType, interlace);

                    default:
                        if (!seenIhdr) return false;
                        if (seenIdat) idatEnded = true;
                        // Unknown critical chunks are not valid in the PNG contract.
                        if ((typeBytes[0] & 0x20) == 0) return false;
                        break;
                }
            }
            return false;
        }
        catch
        {
            return false;
        }
    }

    private static bool HasPngSignature(ReadOnlySpan<byte> bytes)
        => bytes.Length >= 8 && bytes[0] == 0x89 && bytes[1] == 0x50 && bytes[2] == 0x4E && bytes[3] == 0x47
           && bytes[4] == 0x0D && bytes[5] == 0x0A && bytes[6] == 0x1A && bytes[7] == 0x0A;

    private static bool IsValidPngBitDepth(byte colorType, byte bitDepth)
        => colorType switch
        {
            0 => bitDepth is 1 or 2 or 4 or 8 or 16,
            2 => bitDepth is 8 or 16,
            3 => bitDepth is 1 or 2 or 4 or 8,
            4 => bitDepth is 8 or 16,
            6 => bitDepth is 8 or 16,
            _ => false,
        };

    private static bool ValidatePngScanlines(byte[] compressed, int width, int height, byte bitDepth, byte colorType, byte interlace)
    {
        int channels = colorType switch { 0 => 1, 2 => 3, 3 => 1, 4 => 2, 6 => 4, _ => 0 };
        if (channels == 0) return false;
        int bitsPerPixel = checked(channels * bitDepth);
        long expected = interlace == 0
            ? (long)height * (1L + ((long)width * bitsPerPixel + 7L) / 8L)
            : ExpectedAdam7Bytes(width, height, bitsPerPixel);
        if (expected <= 0 || expected > MaxAssetBytes) return false;

        byte[] raw = new byte[(int)expected];
        try
        {
            using var input = new MemoryStream(compressed, writable: false);
            using var zlib = new ZLibStream(input, CompressionMode.Decompress);
            int total = 0;
            while (total < raw.Length)
            {
                int read = zlib.Read(raw, total, raw.Length - total);
                if (read <= 0) break;
                total += read;
            }
            if (total != raw.Length || zlib.ReadByte() != -1)
                return false;
        }
        catch
        {
            return false;
        }

        int cursor = 0;
        if (interlace == 0)
            return ValidatePngPassFilters(raw, ref cursor, width, height, bitsPerPixel) && cursor == raw.Length;

        int[] startX = { 0, 4, 0, 2, 0, 1, 0 };
        int[] startY = { 0, 0, 4, 0, 2, 0, 1 };
        int[] stepX = { 8, 8, 4, 4, 2, 2, 1 };
        int[] stepY = { 8, 8, 8, 4, 4, 2, 2 };
        for (int pass = 0; pass < 7; pass++)
        {
            int passWidth = width <= startX[pass] ? 0 : (width - startX[pass] + stepX[pass] - 1) / stepX[pass];
            int passHeight = height <= startY[pass] ? 0 : (height - startY[pass] + stepY[pass] - 1) / stepY[pass];
            if (!ValidatePngPassFilters(raw, ref cursor, passWidth, passHeight, bitsPerPixel))
                return false;
        }
        return cursor == raw.Length;
    }

    private static long ExpectedAdam7Bytes(int width, int height, int bitsPerPixel)
    {
        int[] startX = { 0, 4, 0, 2, 0, 1, 0 };
        int[] startY = { 0, 0, 4, 0, 2, 0, 1 };
        int[] stepX = { 8, 8, 4, 4, 2, 2, 1 };
        int[] stepY = { 8, 8, 8, 4, 4, 2, 2 };
        long total = 0;
        for (int pass = 0; pass < 7; pass++)
        {
            int passWidth = width <= startX[pass] ? 0 : (width - startX[pass] + stepX[pass] - 1) / stepX[pass];
            int passHeight = height <= startY[pass] ? 0 : (height - startY[pass] + stepY[pass] - 1) / stepY[pass];
            if (passWidth > 0 && passHeight > 0)
                total += (long)passHeight * (1L + ((long)passWidth * bitsPerPixel + 7L) / 8L);
        }
        return total;
    }

    private static bool ValidatePngPassFilters(byte[] raw, ref int cursor, int width, int height, int bitsPerPixel)
    {
        if (width <= 0 || height <= 0) return true;
        int rowBytes = checked((int)(((long)width * bitsPerPixel + 7L) / 8L));
        for (int row = 0; row < height; row++)
        {
            if (cursor >= raw.Length || raw[cursor] > 4 || cursor + 1 + rowBytes > raw.Length)
                return false;
            cursor += 1 + rowBytes;
        }
        return true;
    }

    private static uint[] BuildPngCrcTable()
    {
        var table = new uint[256];
        for (int i = 0; i < table.Length; i++)
        {
            uint value = (uint)i;
            for (int bit = 0; bit < 8; bit++)
                value = (value & 1) != 0 ? 0xEDB88320u ^ (value >> 1) : value >> 1;
            table[i] = value;
        }
        return table;
    }

    private static uint ComputePngChunkCrc(ReadOnlySpan<byte> type, ReadOnlySpan<byte> data)
    {
        uint crc = 0xFFFFFFFFu;
        foreach (byte value in type)
            crc = PngCrcTable[(crc ^ value) & 0xFF] ^ (crc >> 8);
        foreach (byte value in data)
            crc = PngCrcTable[(crc ^ value) & 0xFF] ^ (crc >> 8);
        return crc ^ 0xFFFFFFFFu;
    }

    private static void PruneMapByCountAndAge(Dictionary<string, DateTime> map, DateTime now, int maxEntries, TimeSpan maxAge)
    {
        foreach (string stale in map.Where(x => now - x.Value >= maxAge).Select(x => x.Key).ToList()) map.Remove(stale);
        if (map.Count <= maxEntries) return;
        foreach (string key in map.OrderBy(x => x.Value).Take(map.Count - maxEntries).Select(x => x.Key).ToList()) map.Remove(key);
    }

    private void ClearExpiredInFlightAndMissingLocked(DateTime now)
    {
        PruneMapByCountAndAge(_inFlight, now, MaxInFlightDownloads, InFlightPruneAge);
        PruneMapByCountAndAge(_knownMissing, now, MaxKnownMissing, KnownMissingPruneAge);
    }

    public static string GuessLanBaseUrlFromEndpoint(string endpoint)
    {
        try
        {
            var uri = new Uri(endpoint);
            int port = uri.Port > 0 ? uri.Port : 5055;
            bool parsed = IPAddress.TryParse(uri.Host, out var ip);
            if (!parsed || ip is null || !IsUsablePeerIPv4(ip))
            {
                IPAddress? firstLan = null;
                foreach (var address in Dns.GetHostEntry(Dns.GetHostName()).AddressList)
                {
                    if (!IsUsablePeerIPv4(address)) continue;
                    if (address.ToString().StartsWith("26.", StringComparison.Ordinal)) return $"{uri.Scheme}://{address}:{port}";
                    firstLan ??= address;
                }
                if (firstLan is not null) return $"{uri.Scheme}://{firstLan}:{port}";
                return parsed && ip is not null && IPAddress.IsLoopback(ip) ? $"{uri.Scheme}://{uri.Host}:{port}" : "";
            }
            return $"{uri.Scheme}://{uri.Host}:{port}";
        }
        catch { return ""; }
    }

    private static bool IsUsablePeerIPv4(IPAddress address)
    {
        if (address.AddressFamily != AddressFamily.InterNetwork || IPAddress.IsLoopback(address)) return false;
        byte[] bytes = address.GetAddressBytes();
        if (bytes.Length != 4 || (bytes[0] == 169 && bytes[1] == 254)) return false;
        return bytes[0] != 0 && bytes[0] < 224;
    }
}
