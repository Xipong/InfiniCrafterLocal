#nullable enable
using InfiniCrafterLocal.Common.Config;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.IO;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

// AGENT MAP: client runtime PNG loader/cache.
// This is a presentation layer: validate path/size/dimensions, cache hits and
// failures, and fall back to placeholders. It must not decide gameplay success
// or repair generated item contracts.
public sealed class RuntimeSpriteCacheDebugSnapshot
{
    public int TextureCount { get; init; }
    public int MissingOrBadCount { get; init; }
    public int MaxCachedTextures { get; init; }
    public int MaxTextureDimensionPixels { get; init; }
    public int MaxTextureFileMegabytes { get; init; }
    public long EstimatedTextureBytes { get; init; }
    public long HitCount { get; init; }
    public long MissCount { get; init; }
    public long LoadSuccessCount { get; init; }
    public long EvictionCount { get; init; }
    public long RejectedFileSizeCount { get; init; }
    public long RejectedDimensionCount { get; init; }
    public long FailedLoadCount { get; init; }
}

/// <summary>
/// Experimental runtime PNG loader for generated sprites.
/// tModLoader's normal ModItem.Texture is static, so this cache is only used by optional draw hooks.
/// If a sprite path is missing or invalid, the normal placeholder texture is used.
/// </summary>
public sealed class RuntimeSpriteCache : IDisposable
{
    private sealed class CachedTexture
    {
        public readonly Texture2D Texture;
        public long LastAccessTick;

        public CachedTexture(Texture2D texture, long lastAccessTick)
        {
            Texture = texture;
            LastAccessTick = lastAccessTick;
        }
    }

    private readonly Dictionary<string, CachedTexture> _textures = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, DateTime> _missingOrBad = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _lock = new();
    private static readonly TimeSpan MissingRetryAfter = TimeSpan.FromSeconds(30);
    private const int DefaultMaxCachedTextures = 512;
    private const int MinCachedTextures = 64;
    private const int MaxCachedTexturesHardLimit = 2048;
    private const int DefaultMaxTextureDimensionPixels = 192;
    private const int MinTextureDimensionPixels = 32;
    private const int MaxTextureDimensionPixelsHardLimit = 512;
    private const int DefaultMaxTextureFileMegabytes = 8;
    private const int MinTextureFileMegabytes = 1;
    private const int MaxTextureFileMegabytesHardLimit = 64;
    private const int MaxMissingOrBadRecords = 256;
    private long _accessCounter;
    private long _hitCount;
    private long _missCount;
    private long _loadSuccessCount;
    private long _evictionCount;
    private long _rejectedFileSizeCount;
    private long _rejectedDimensionCount;
    private long _failedLoadCount;

    private readonly struct RuntimeSpriteLimits
    {
        public readonly int MaxCachedTextures;
        public readonly int MaxTextureDimensionPixels;
        public readonly long MaxTextureFileBytes;
        public readonly int MaxTextureFileMegabytes;

        public RuntimeSpriteLimits(int maxCachedTextures, int maxTextureDimensionPixels, int maxTextureFileMegabytes)
        {
            MaxCachedTextures = maxCachedTextures;
            MaxTextureDimensionPixels = maxTextureDimensionPixels;
            MaxTextureFileMegabytes = maxTextureFileMegabytes;
            MaxTextureFileBytes = (long)maxTextureFileMegabytes * 1024L * 1024L;
        }
    }

    public Texture2D? TryGet(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || Main.dedServ) return null;
        lock (_lock)
        {
            try
            {
                path = Environment.ExpandEnvironmentVariables(path).Trim();
                if (path.Length > 320 || !path.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                {
                    _missCount++;
                    return null;
                }
                string key = Path.GetFullPath(path);
                if (!File.Exists(key))
                {
                    string? synced = global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.ResolveLocalPath(path);
                    if (!string.IsNullOrWhiteSpace(synced) && File.Exists(synced))
                        key = Path.GetFullPath(synced);
                }
                if (_textures.TryGetValue(key, out var cached))
                {
                    _hitCount++;
                    cached.LastAccessTick = ++_accessCounter;
                    return cached.Texture;
                }
                if (_missingOrBad.TryGetValue(key, out DateTime lastBad))
                {
                    if (DateTime.UtcNow - lastBad < MissingRetryAfter)
                    {
                        _missCount++;
                        return null;
                    }
                    _missingOrBad.Remove(key);
                }
                if (!File.Exists(key))
                {
                    _missCount++;
                    RememberMissingOrBad(key);
                    return null;
                }

                RuntimeSpriteLimits limits = EffectiveLimits();
                if (!IsRuntimePngFileSizeAllowed(key, limits.MaxTextureFileBytes))
                {
                    _missCount++;
                    _rejectedFileSizeCount++;
                    RememberMissingOrBad(key);
                    return null;
                }

                using var stream = File.OpenRead(key);
                var tex = Texture2D.FromStream(Main.graphics.GraphicsDevice, stream);
                if (tex.Width > limits.MaxTextureDimensionPixels || tex.Height > limits.MaxTextureDimensionPixels)
                {
                    _missCount++;
                    _rejectedDimensionCount++;
                    try { tex.Dispose(); } catch { }
                    RememberMissingOrBad(key);
                    return null;
                }

                _textures[key] = new CachedTexture(tex, ++_accessCounter);
                _loadSuccessCount++;
                TrimTextureCacheIfNeeded(limits.MaxCachedTextures);
                return tex;
            }
            catch
            {
                _missCount++;
                _failedLoadCount++;
                try
                {
                    string bad = Environment.ExpandEnvironmentVariables(path ?? "");
                    if (!string.IsNullOrWhiteSpace(bad))
                        RememberMissingOrBad(bad);
                }
                catch { }
                return null;
            }
        }
    }

    public RuntimeSpriteCacheDebugSnapshot GetDebugSnapshot()
    {
        lock (_lock)
        {
            RuntimeSpriteLimits limits = EffectiveLimits();
            long estimatedBytes = 0;
            foreach (var cached in _textures.Values)
            {
                try { estimatedBytes += (long)Math.Max(0, cached.Texture.Width) * Math.Max(0, cached.Texture.Height) * 4L; }
                catch { }
            }
            return new RuntimeSpriteCacheDebugSnapshot
            {
                TextureCount = _textures.Count,
                MissingOrBadCount = _missingOrBad.Count,
                MaxCachedTextures = limits.MaxCachedTextures,
                MaxTextureDimensionPixels = limits.MaxTextureDimensionPixels,
                MaxTextureFileMegabytes = limits.MaxTextureFileMegabytes,
                EstimatedTextureBytes = estimatedBytes,
                HitCount = _hitCount,
                MissCount = _missCount,
                LoadSuccessCount = _loadSuccessCount,
                EvictionCount = _evictionCount,
                RejectedFileSizeCount = _rejectedFileSizeCount,
                RejectedDimensionCount = _rejectedDimensionCount,
                FailedLoadCount = _failedLoadCount,
            };
        }
    }

    public int Clear(bool clearMissingOrBad = true)
    {
        lock (_lock)
        {
            int removed = _textures.Count;
            foreach (var cached in _textures.Values)
            {
                try { cached.Texture.Dispose(); } catch { }
            }
            _textures.Clear();
            if (clearMissingOrBad)
                _missingOrBad.Clear();
            return removed;
        }
    }

    public int ClearMissingOrBad()
    {
        lock (_lock)
        {
            int removed = _missingOrBad.Count;
            _missingOrBad.Clear();
            return removed;
        }
    }

    private static RuntimeSpriteLimits EffectiveLimits()
    {
        try
        {
            var config = ModContent.GetInstance<InfiniGameplayQolConfig>();
            int maxCachedTextures = Math.Clamp(config?.RuntimeSpriteCacheMaxTextures ?? DefaultMaxCachedTextures, MinCachedTextures, MaxCachedTexturesHardLimit);
            int maxDimensionPixels = Math.Clamp(config?.RuntimeSpriteMaxDimensionPixels ?? DefaultMaxTextureDimensionPixels, MinTextureDimensionPixels, MaxTextureDimensionPixelsHardLimit);
            int maxFileMegabytes = Math.Clamp(config?.RuntimeSpriteMaxPngFileMegabytes ?? DefaultMaxTextureFileMegabytes, MinTextureFileMegabytes, MaxTextureFileMegabytesHardLimit);
            return new RuntimeSpriteLimits(maxCachedTextures, maxDimensionPixels, maxFileMegabytes);
        }
        catch
        {
            return new RuntimeSpriteLimits(DefaultMaxCachedTextures, DefaultMaxTextureDimensionPixels, DefaultMaxTextureFileMegabytes);
        }
    }

    private static bool IsRuntimePngFileSizeAllowed(string key, long maxTextureFileBytes)
    {
        try
        {
            return new FileInfo(key).Length <= maxTextureFileBytes;
        }
        catch
        {
            return false;
        }
    }

    private void RememberMissingOrBad(string key)
    {
        if (string.IsNullOrWhiteSpace(key)) return;
        _missingOrBad[key] = DateTime.UtcNow;
        TrimMissingOrBadCacheIfNeeded();
    }

    private void TrimTextureCacheIfNeeded(int maxCachedTextures)
    {
        while (_textures.Count > maxCachedTextures)
        {
            string? oldestKey = null;
            long oldestAccess = long.MaxValue;
            foreach (var pair in _textures)
            {
                if (pair.Value.LastAccessTick >= oldestAccess) continue;
                oldestAccess = pair.Value.LastAccessTick;
                oldestKey = pair.Key;
            }
            if (oldestKey is null) return;
            var texture = _textures[oldestKey].Texture;
            _textures.Remove(oldestKey);
            _evictionCount++;
            try { texture.Dispose(); } catch { }
        }
    }

    private void TrimMissingOrBadCacheIfNeeded()
    {
        while (_missingOrBad.Count > MaxMissingOrBadRecords)
        {
            string? oldestKey = null;
            DateTime oldestAccess = DateTime.MaxValue;
            foreach (var pair in _missingOrBad)
            {
                if (pair.Value >= oldestAccess) continue;
                oldestAccess = pair.Value;
                oldestKey = pair.Key;
            }
            if (oldestKey is null) return;
            _missingOrBad.Remove(oldestKey);
        }
    }

    public void Invalidate(string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) return;
        lock (_lock)
        {
            try
            {
                string key = Path.GetFullPath(Environment.ExpandEnvironmentVariables(path).Trim());
                // Asset downloads happen on a background task. Do not dispose/recreate
                // Texture2D from that thread; only clear the negative lookup cache so the
                // next draw-thread TryGet() can load the freshly downloaded PNG.
                _missingOrBad.Remove(key);
                _missingOrBad.Remove(path.Trim());
            }
            catch
            {
                try { _missingOrBad.Remove(path.Trim()); } catch { }
            }
        }
    }

    public void Dispose()
    {
        Clear(clearMissingOrBad: true);
    }
}
