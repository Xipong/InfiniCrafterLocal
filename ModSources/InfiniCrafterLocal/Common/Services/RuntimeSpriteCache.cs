#nullable enable
using InfiniCrafterLocal.Common.Config;
using Microsoft.Xna.Framework;
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
        public readonly float LocalForwardRadians;
        public long LastAccessTick;

        public CachedTexture(Texture2D texture, float localForwardRadians, long lastAccessTick)
        {
            Texture = texture;
            LocalForwardRadians = localForwardRadians;
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
    private const float PrincipalAxisMinimumAnisotropy = 2.5f;
    private const float ForwardTipMinimumAnisotropy = 8f;
    private const byte PrincipalAxisAlphaThreshold = 8;
    private const double ForwardEndpointFraction = 0.24;
    private const double ForwardEndpointRatio = 0.82;
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

    public Texture2D? TryGet(string path) => TryGet(path, out _);

    public Texture2D? TryGet(string path, out float localForwardRadians)
    {
        localForwardRadians = 0f;
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
                    localForwardRadians = cached.LocalForwardRadians;
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

                localForwardRadians = MeasureLocalForwardRadians(tex);
                _textures[key] = new CachedTexture(tex, localForwardRadians, ++_accessCounter);
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

    private static float MeasureLocalForwardRadians(Texture2D texture)
    {
        try
        {
            int width = texture.Width;
            int height = texture.Height;
            if (width <= 0 || height <= 0) return 0f;
            var pixels = new Color[checked(width * height)];
            texture.GetData(pixels);

            int count = 0;
            double sumX = 0.0;
            double sumY = 0.0;
            for (int y = 0; y < height; y++)
            {
                int row = y * width;
                for (int x = 0; x < width; x++)
                {
                    if (pixels[row + x].A < PrincipalAxisAlphaThreshold) continue;
                    count++;
                    sumX += x;
                    sumY += y;
                }
            }
            if (count < 4) return 0f;

            double meanX = sumX / count;
            double meanY = sumY / count;
            double varianceX = 0.0;
            double varianceY = 0.0;
            double covariance = 0.0;
            for (int y = 0; y < height; y++)
            {
                int row = y * width;
                for (int x = 0; x < width; x++)
                {
                    if (pixels[row + x].A < PrincipalAxisAlphaThreshold) continue;
                    double dx = x - meanX;
                    double dy = y - meanY;
                    varianceX += dx * dx;
                    varianceY += dy * dy;
                    covariance += dx * dy;
                }
            }
            varianceX /= count;
            varianceY /= count;
            covariance /= count;
            double trace = varianceX + varianceY;
            double discriminant = Math.Sqrt(Math.Max(
                0.0,
                (varianceX - varianceY) * (varianceX - varianceY) + 4.0 * covariance * covariance
            ));
            double major = Math.Max(0.0, (trace + discriminant) * 0.5);
            double minor = Math.Max(1e-9, (trace - discriminant) * 0.5);
            double anisotropy = major / minor;
            if (anisotropy < PrincipalAxisMinimumAnisotropy) return 0f;

            double angle = 0.5 * Math.Atan2(2.0 * covariance, varianceX - varianceY);
            if (anisotropy >= ForwardTipMinimumAnisotropy)
            {
                double axisX = Math.Cos(angle);
                double axisY = Math.Sin(angle);
                double minProjection = double.MaxValue;
                double maxProjection = double.MinValue;
                for (int y = 0; y < height; y++)
                {
                    int row = y * width;
                    for (int x = 0; x < width; x++)
                    {
                        if (pixels[row + x].A < PrincipalAxisAlphaThreshold) continue;
                        double projection = (x - meanX) * axisX + (y - meanY) * axisY;
                        minProjection = Math.Min(minProjection, projection);
                        maxProjection = Math.Max(maxProjection, projection);
                    }
                }

                double endpointWidth = Math.Max(1e-6, (maxProjection - minProjection) * ForwardEndpointFraction);
                int negativeEndpointPixels = 0;
                int positiveEndpointPixels = 0;
                for (int y = 0; y < height; y++)
                {
                    int row = y * width;
                    for (int x = 0; x < width; x++)
                    {
                        if (pixels[row + x].A < PrincipalAxisAlphaThreshold) continue;
                        double projection = (x - meanX) * axisX + (y - meanY) * axisY;
                        if (projection <= minProjection + endpointWidth) negativeEndpointPixels++;
                        if (projection >= maxProjection - endpointWidth) positiveEndpointPixels++;
                    }
                }
                if (
                    negativeEndpointPixels > 0
                    && positiveEndpointPixels > 0
                    && negativeEndpointPixels < positiveEndpointPixels * ForwardEndpointRatio
                )
                    angle += Math.PI;
            }
            return MathHelper.WrapAngle((float)angle);
        }
        catch
        {
            // Presentation metadata failure must not make an otherwise valid PNG unusable.
            return 0f;
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
