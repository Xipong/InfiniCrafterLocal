#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

// AGENT MAP: C# side of final-asset HTTP sync.
// Packets carry only sanitized filenames and a base URL. This service downloads,
// validates, caches and resolves those files. Do not add raw image/JSON bytes to
// Terraria packets and do not accept arbitrary paths from peers.
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
}

/// <summary>
/// Lightweight LAN asset sync for generated sprites/manifests.
/// Terraria packets carry only tiny metadata (base URL + filenames); PNG/JSON bytes are fetched
/// in the background over the LocalGenerator HTTP server and cached per client.
/// </summary>
public sealed class GeneratedAssetSyncService : IDisposable
{
    public const byte PacketNotifyGeneratedAssets = InfiniNetPacketIds.NotifyGeneratedAssets;
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(12) };
    private readonly HashSet<string> _inFlight = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, DateTime> _knownMissing = new(StringComparer.OrdinalIgnoreCase);
    private static readonly TimeSpan MissingRetryAfter = TimeSpan.FromSeconds(30);
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
    {
        EnsureAssetsForData(data, forceRetry: false);
    }

    public void EnsureAssetsForData(GeneratedItemData? data, bool forceRetry)
    {
        if (data is null || Main.dedServ) return;
        if (!GeneratedItemRegistryService.IsCurrentWorldData(data)) return;
        string baseUrl = BestBaseUrl(data);
        if (string.IsNullOrWhiteSpace(baseUrl)) return;
        QueueDownloads(baseUrl, AssetFilesFromData(data), forceRetry: forceRetry);
    }

    public void ResetRetryState()
    {
        lock (_lock)
        {
            _knownMissing.Clear();
        }
        LocalHttpQuietFailure.ClearAll();
    }

    public GeneratedAssetSyncDebugSnapshot GetDebugSnapshot()
    {
        int cacheFiles = 0;
        try
        {
            if (Directory.Exists(CacheRoot))
                cacheFiles = Directory.EnumerateFiles(CacheRoot, "*.*", SearchOption.TopDirectoryOnly).Count();
        }
        catch { }

        lock (_lock)
        {
            return new GeneratedAssetSyncDebugSnapshot
            {
                CacheFileCount = cacheFiles,
                InFlightCount = _inFlight.Count,
                KnownMissingCount = _knownMissing.Count,
                CacheHitCount = _cacheHitCount,
                CacheMissCount = _cacheMissCount,
                RetryCount = _retryCount,
                DuplicateSuppressedCount = _duplicateSuppressedCount,
                DownloadStartedCount = _downloadStartedCount,
            };
        }
    }

    public void NotifyNewItemCrafted(GeneratedItemData? data)
    {
        if (data is null) return;
        if (!GeneratedItemRegistryService.IsCurrentWorldData(data)) return;
        var files = AssetFilesFromData(data).ToArray();
        if (files.Length == 0) return;
        string baseUrl = BestBaseUrl(data);
        if (string.IsNullOrWhiteSpace(baseUrl)) return;

        // Local cache registration first, then notify other peers.
        QueueDownloads(baseUrl, files);

        if (Main.netMode == NetmodeID.SinglePlayer)
            return;

        var packet = InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(PacketNotifyGeneratedAssets);
        packet.Write((byte)Math.Min(files.Length, 64));
        packet.Write(baseUrl);
        packet.Write(data.Id ?? "");
        packet.Write(data.RecipeKey ?? "");
        foreach (string file in files.Take(64))
            packet.Write(file);
        packet.Send();
    }

    public void HandlePacket(BinaryReader reader, int whoAmI)
    {
        byte count = reader.ReadByte();
        string baseUrl = SanitizeBaseUrl(reader.ReadString());
        string itemId = reader.ReadString();
        string recipeKey = reader.ReadString();
        var files = new List<string>();
        for (int i = 0; i < count; i++)
        {
            string file = SanitizeFileName(reader.ReadString());
            if (!string.IsNullOrWhiteSpace(file)) files.Add(file);
        }

        if (Main.netMode == NetmodeID.Server)
        {
            // Relay the tiny notification to all other clients. No PNG/JSON payload travels through Terraria.
            var packet = InfiniCrafterLocalMod.Instance.GetPacket();
            packet.Write(PacketNotifyGeneratedAssets);
            packet.Write((byte)Math.Min(files.Count, 64));
            packet.Write(baseUrl);
            packet.Write(itemId ?? "");
            packet.Write(recipeKey ?? "");
            foreach (string file in files.Take(64))
                packet.Write(file);
            packet.Send(-1, whoAmI);
            return;
        }

        QueueDownloads(baseUrl, files);
    }

    public void QueueDownloads(string baseUrl, IEnumerable<string> files, bool forceRetry = false)
    {
        if (Main.dedServ) return;
        baseUrl = SanitizeBaseUrl(baseUrl);
        if (string.IsNullOrWhiteSpace(baseUrl)) return;
        string endpointGuardKey = "asset:" + baseUrl;
        if (forceRetry)
            LocalHttpQuietFailure.Clear(endpointGuardKey);
        else if (LocalHttpQuietFailure.ShouldSkip(endpointGuardKey)) return;
        foreach (string raw in files ?? Array.Empty<string>())
        {
            string file = SanitizeFileName(raw);
            if (string.IsNullOrWhiteSpace(file)) continue;
            string local = Path.Combine(CacheRoot, file);
            if (File.Exists(local))
            {
                lock (_lock) _cacheHitCount++;
                continue;
            }
            string key = baseUrl + "|" + file;
            lock (_lock)
            {
                _cacheMissCount++;
                if (_inFlight.Contains(key))
                {
                    _duplicateSuppressedCount++;
                    continue;
                }
                if (!forceRetry && _knownMissing.TryGetValue(key, out DateTime lastMissing))
                {
                    if (DateTime.UtcNow - lastMissing < MissingRetryAfter)
                    {
                        _duplicateSuppressedCount++;
                        continue;
                    }
                    _knownMissing.Remove(key);
                    _retryCount++;
                }
                if (forceRetry && _knownMissing.Remove(key))
                    _retryCount++;
                _inFlight.Add(key);
                _downloadStartedCount++;
            }
            _ = Task.Run(async () => await DownloadOneAsync(baseUrl, file, local, key));
        }
    }

    private async Task DownloadOneAsync(string baseUrl, string file, string local, string key)
    {
        try
        {
            Directory.CreateDirectory(CacheRoot);
            string url = baseUrl.TrimEnd('/') + "/get_asset?file=" + Uri.EscapeDataString(file);
            byte[] bytes = await Http.GetByteArrayAsync(url).ConfigureAwait(false);
            LocalHttpQuietFailure.Clear("asset:" + SanitizeBaseUrl(baseUrl));
            if (bytes.Length <= 0 || bytes.Length > 8 * 1024 * 1024)
                throw new InvalidDataException("asset size out of range");
            if (file.EndsWith(".png", StringComparison.OrdinalIgnoreCase) && !LooksLikePng(bytes))
                throw new InvalidDataException("asset is not png");
            string tmp = local + ".tmp";
            await File.WriteAllBytesAsync(tmp, bytes).ConfigureAwait(false);
            if (File.Exists(local)) File.Delete(local);
            File.Move(tmp, local);
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites?.Invalidate(local);
        }
        catch (Exception ex)
        {
            if (LocalHttpQuietFailure.IsExpectedOffline(ex))
                LocalHttpQuietFailure.Record("asset:" + SanitizeBaseUrl(baseUrl), ex, TimeSpan.FromSeconds(60));
            lock (_lock) _knownMissing[key] = DateTime.UtcNow;
        }
        finally
        {
            lock (_lock) _inFlight.Remove(key);
        }
    }

    private static bool LooksLikePng(byte[] bytes)
        => bytes.Length >= 8 && bytes[0] == 0x89 && bytes[1] == 0x50 && bytes[2] == 0x4E && bytes[3] == 0x47;

    private string BestBaseUrl(GeneratedItemData data)
    {
        string meta = SanitizeBaseUrl(data.RecipeMeta?.AssetBaseUrl ?? "");
        if (!string.IsNullOrWhiteSpace(meta)) return meta;
        return InfiniCrafterLocalMod.Generator.AssetBaseUrlForSharing();
    }

    public static IEnumerable<string> AssetFilesFromData(GeneratedItemData data)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        void Add(string? path)
        {
            string file = FileNameFromPath(path);
            if (!string.IsNullOrWhiteSpace(file)) seen.Add(file);
        }
        if (data.RecipeMeta?.AssetFiles is { Length: > 0 })
        {
            foreach (string file in data.RecipeMeta.AssetFiles)
                Add(file);
        }
        // Final gameplay-facing assets only. Raw generation intermediates are not required in multiplayer.
        Add(data.Visual?.SpritePath);
        Add(data.Visual?.AssetManifestPath);
        Add(data.Attack?.ProjectileSpritePath);
        Add(data.Attack?.ImpactSpritePath);
        Add(data.Attack?.ChildSpritePath);
        Add(data.Attack?.FieldSpritePath);
        return seen.Take(64).ToArray();
    }

    public static string FileNameFromPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) return "";
        string p = path.Trim();
        if (Uri.TryCreate(p, UriKind.Absolute, out var uri) && (uri.Scheme == "http" || uri.Scheme == "https"))
            p = uri.LocalPath;
        p = p.Replace('\\', '/');
        string file = Path.GetFileName(p);
        return SanitizeFileName(file);
    }

    private static string SanitizeFileName(string? file)
    {
        if (string.IsNullOrWhiteSpace(file)) return "";
        file = Path.GetFileName(file.Trim());
        if (file.Length > 160) return "";
        if (!file.EndsWith(".png", StringComparison.OrdinalIgnoreCase) && !file.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) return "";
        foreach (char c in file)
        {
            if (!(char.IsLetterOrDigit(c) || c == '.' || c == '_' || c == '-' || c == '@' || c == '+'))
                return "";
        }
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

    public static string GuessLanBaseUrlFromEndpoint(string endpoint)
    {
        try
        {
            var uri = new Uri(endpoint);
            int port = uri.Port > 0 ? uri.Port : 5055;
            if (!IPAddress.TryParse(uri.Host, out var ip) || IPAddress.IsLoopback(ip))
            {
                // Multiplayer asset HTTP is meant for peers. If Radmin VPN is active,
                // prefer its 26.x address over normal LAN adapters: Steam can carry
                // Terraria gameplay, but it will not proxy our /get_asset HTTP calls.
                IPAddress? firstLan = null;
                foreach (var address in Dns.GetHostEntry(Dns.GetHostName()).AddressList)
                {
                    if (address.AddressFamily != AddressFamily.InterNetwork || IPAddress.IsLoopback(address))
                        continue;
                    if (address.ToString().StartsWith("26.", StringComparison.Ordinal))
                        return $"{uri.Scheme}://{address}:{port}";
                    firstLan ??= address;
                }
                if (firstLan is not null)
                    return $"{uri.Scheme}://{firstLan}:{port}";
            }
            return $"{uri.Scheme}://{uri.Host}:{port}";
        }
        catch
        {
            return "";
        }
    }
}
