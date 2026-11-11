using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static void SpriteLocalPathsRetainUpperBound()
    {
        WithLighting((_, __) => {
            string? previous = Environment.GetEnvironmentVariable("INFINI_IMAGE_DIR");
            string root = Path.Combine(Terraria.Program.SavePath, "sprite-local-bound");
            for (int i = 0; i < 16; i++) root = Path.Combine(root, new string('p', 60));
            Environment.SetEnvironmentVariable("INFINI_IMAGE_DIR", root);
            try {
                using var peers = new ReviewPeers();
                using var probe = new AssetInvalidationProbe();
                string path = PublishAssetOwner(probe.Sync, "local-bound", "local-bound.png", AssetOwnerCanonical);
                string selector = Path.GetFileName(path);
                Equal(true, path.Length > 1024, "fixture exceeds the local path limit with a valid short selector");
                Equal(path, probe.Sync.ResolveCertifiedLocalPath(selector)!, "path bound is tested after real certification");
                Equal(true, probe.Cache.TryGet(selector) is null, "loader retains upper local path bound");
                Equal(true, probe.Cache.TryGetReady(selector) is null, "draw uses identical upper bound");
                Equal(0, probe.Loads.Count, "oversized certified path never reaches file loading");
                Equal(0, probe.QueuedActions, "oversized certified path never queues preparation");
            } finally { Environment.SetEnvironmentVariable("INFINI_IMAGE_DIR", previous); }
        });
    }

    private static void SpriteLocalPathsShareLoaderAndDrawLimits(bool longRoot)
    {
        WithLighting((_, __) => {
            string? previous = Environment.GetEnvironmentVariable("INFINI_IMAGE_DIR");
            string root = Path.Combine(Terraria.Program.SavePath, "sprite-local-path");
            if (longRoot)
                for (int i = 0; i < 4; i++) root = Path.Combine(root, new string('p', 60));
            Environment.SetEnvironmentVariable("INFINI_IMAGE_DIR", root);
            try {
                using var peers = new ReviewPeers();
                using var probe = new AssetInvalidationProbe();
                string path = PublishAssetOwner(probe.Sync, "local-path", "local-path.png", AssetOwnerCanonical);
                string selector = Path.GetFileName(path);
                Equal(longRoot, path.Length > 320, "fixture separates short selector from short/long local storage path");
                Equal(true, path.Length <= 1024, "fixture is within loader's accepted local path bound");
                Equal(true, selector.Length <= 160, "wire selector remains within its independent bound");
                Equal(path, probe.Sync.ResolveCertifiedLocalPath(selector)!, "real publication is lifecycle certified");
                var loaded = probe.Cache.TryGet(selector);
                Equal(true, loaded is not null, "loader reads the certified PNG");
                Equal(true, ReferenceEquals(loaded, probe.Cache.TryGetReady(selector)), "draw borrows the exact loaded texture");
                Equal(true, ReferenceEquals(loaded, probe.Cache.TryGetReady(path)), "canonical local path and short alias share the same ready generation");
                Equal(1, probe.Loads.Count, "ready cache hits never read PNG bodies again");
                Equal(true, AssetOwnerCanonical.SequenceEqual(probe.Loads[0].Bytes), "loader reads actual published bytes");

                probe.Cache.Invalidate(path);
                Equal(true, probe.Cache.TryGetReady(selector) is null, "cold draw queues preparation instead of loading");
                Equal(1, probe.Loads.Count, "cold draw performs no file read");
                probe.Batch.End();
                probe.DrainOwnerQueue();
                var prepared = probe.Cache.TryGetReady(selector);
                Equal(true, prepared is not null && !ReferenceEquals(loaded, prepared), "owner callback publishes a fresh ready generation");
                Equal(2, probe.Loads.Count, "queued cold preparation reads once");
                Equal(true, ReferenceEquals(prepared, probe.Cache.TryGet(selector)), "lifecycle loader and draw agree after queued preparation");

                string raw = Path.Combine(root, "unindexed.png");
                File.WriteAllBytes(raw, AssetOwnerCanonical);
                Equal(true, probe.Cache.TryGet(raw) is null, "local path length does not bypass indexed ownership");
                Equal(true, probe.Cache.TryGetReady(raw) is null, "draw rejects unindexed bytes too");
                Equal(2, probe.Loads.Count, "unindexed bytes are never read");
                Equal(0, probe.Sync.GetDebugSnapshot().DownloadStartedCount, "no network requests");
                Console.WriteLine($"DETAIL: local PNG path={path.Length}, selector={selector.Length}, actual file reads={probe.Loads.Count}; GPU boundaries intercepted");
            } finally { Environment.SetEnvironmentVariable("INFINI_IMAGE_DIR", previous); }
        });
    }
}
