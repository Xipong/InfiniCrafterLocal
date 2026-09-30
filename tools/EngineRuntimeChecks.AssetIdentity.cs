using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Collections;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private delegate FileStream AssetOpenOriginal(string path);
    private delegate FileStream AssetOpenHook(AssetOpenOriginal original, string path);
    private delegate bool AssetValidateOriginal(string path, GeneratedAssetWireDescriptor? descriptor);
    private delegate bool AssetValidateHook(AssetValidateOriginal original, string path, GeneratedAssetWireDescriptor? descriptor);

    private static readonly byte[] AssetOwnerCanonical = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAP0lEQVR4nGNgGAWjYKQDRlwS1zMlJ1DTIs3pzwuwiTNR0xJywKgDRh0w6oBRB4w6YNQBow4YdcCoA0bBKBgFAKl2BChncJIaAAAAAElFTkSuQmCC");
    private static readonly byte[] AssetOwnerOtherColor = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAP0lEQVR4nGNgGAWjYKQDRlwSkvsCJlDToudOGwqwiTNR0xJywKgDRh0w6oBRB4w6YNQBow4YdcCoA0bBKBgFAJnWBCigX3ypAAAAAElFTkSuQmCC");
    private static readonly BindingFlags AssetOwnerInstance = BindingFlags.Instance | BindingFlags.NonPublic;

    private static GeneratedItemData AssetOwnerData(string id, string path)
    {
        var wire = System.Text.Json.Nodes.JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!.AsObject();
        wire["id"] = id; wire["sourceMode"] = "generated";
        wire["visual"]!["spritePath"] = path; wire["visual"]!["spriteStatus"] = "generated";
        var data = ParseMaterialElement(wire);
        GeneratedItemRegistryService.StampCurrentWorld(data);
        return data;
    }

    private static void CommitAssetOwner(GeneratedAssetSyncService sync, string id, string file, byte[] bytes)
        => typeof(GeneratedAssetSyncService).GetMethod("CommitVerifiedAsset", AssetOwnerInstance)!.Invoke(sync,
            new object[] { id, file, bytes, Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() });

    private static void DrawAssetOwner(GeneratedItem item)
        => item.PreDrawInInventory(null!, Vector2.Zero, new Rectangle(0, 0, 32, 32), Color.White, Color.White, Vector2.Zero, 1);

    private static void RuntimeSpriteConflictingCertificatesPreserveInventoryOwnership()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var sprites = typeof(InfiniMod).GetProperty("Sprites")!;
            var assetSync = typeof(InfiniMod).GetProperty("AssetSync")!;
            object? priorSprites = sprites.GetValue(null), priorSync = assetSync.GetValue(null);
            string sandbox = Path.Combine(Terraria.Program.SavePath, "asset-conflicts"); Directory.CreateDirectory(sandbox);
            bool observing = false; string? opened = null; byte[]? bytes = null;
            AssetOpenHook open = (original, path) => {
                if (!observing) return original(path);
                opened = Path.GetFullPath(path);
                using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
                using var memory = new MemoryStream(); stream.CopyTo(memory); bytes = memory.ToArray();
                throw new InvalidOperationException("CPU inventory observer stops before GPU decode");
            };
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(File).GetMethod("OpenRead", new[] { typeof(string) })!, open);
            try {
                foreach (bool reverse in new[] { false, true }) {
                    using var sync = new GeneratedAssetSyncService(); using var cache = new RuntimeSpriteCache();
                    sprites.SetValue(null, cache); assetSync.SetValue(null, sync);
                    string file = "shared_" + Guid.NewGuid().ToString("N") + ".png";
                    string aPath = Path.Combine(sandbox, "a", file), bPath = Path.Combine(sandbox, "b", file);
                    Directory.CreateDirectory(Path.GetDirectoryName(aPath)!); Directory.CreateDirectory(Path.GetDirectoryName(bPath)!);
                    File.WriteAllBytes(aPath, AssetOwnerCanonical); File.WriteAllBytes(bPath, AssetOwnerOtherColor);
                    var a = AssetOwnerData("conflict_a", aPath); var b = AssetOwnerData("conflict_b", bPath);
                    var aDescriptors = sync.BuildServerAssetDescriptors(a); var bDescriptors = sync.BuildServerAssetDescriptors(b);
                    Equal(1, aDescriptors.Length, "real server A roster"); Equal(1, bDescriptors.Length, "real server B roster");
                    Equal(false, aDescriptors[0].Sha256 == bDescriptors[0].Sha256, "accepted same-name assets have different identities");
                    var registrationOrder = reverse ? new[] { b, a } : new[] { a, b };
                    foreach (var data in registrationOrder)
                        sync.RegisterRemoteAssetDescriptors(data.Id, data == a ? aDescriptors : bDescriptors);
                    CommitAssetOwner(sync, a.Id, file, AssetOwnerCanonical);
                    foreach (var data in registrationOrder)
                        peers.Registry.RegisterLocal(data, persist: false, ensureAssets: true);
                    var aItem = ReviewItem(a); var bItem = ReviewItem(b);
                    typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(bItem, (int)Terraria.Main.GameUpdateCount);
                    typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(aItem, -9999);
                    void Observe(GeneratedItem item, string expectedPath, byte[] expectedBytes) {
                        cache.ClearMissingOrBad(); opened = null; bytes = null; observing = true;
                        try { DrawAssetOwner(item); } finally { observing = false; }
                        Equal(Path.GetFullPath(expectedPath), opened ?? "", "actual inventory owner, reverse=" + reverse);
                        Equal(true, expectedBytes.SequenceEqual(bytes ?? Array.Empty<byte>()), "actual inventory bytes, reverse=" + reverse);
                    }
                    // Trigger A's real hydration first; the regression assertion must
                    // observe B borrowing different bytes, not A choosing an equal-byte alias.
                    observing = true;
                    try { DrawAssetOwner(aItem); } finally { observing = false; }
                    Observe(bItem, bPath, AssetOwnerOtherColor); Observe(aItem, aPath, AssetOwnerCanonical);
                    Equal(true, sync.ResolveCertifiedLocalPath(aPath) is null, "conflict forbids certificate priority even after hydration");
                    sync.RegisterRemoteAssetDescriptors(b.Id, Array.Empty<GeneratedAssetWireDescriptor>());
                    Observe(aItem, Path.Combine(sync.CacheRoot, file), AssetOwnerCanonical);
                    // Equal identities may share the existing proof; replacing a manifest must rebind it.
                    sync.RegisterRemoteAssetDescriptors(b.Id, aDescriptors);
                    sync.RegisterRemoteAssetDescriptors(a.Id, Array.Empty<GeneratedAssetWireDescriptor>());
                    Observe(aItem, Path.Combine(sync.CacheRoot, file), AssetOwnerCanonical);
                    sync.RegisterRemoteAssetDescriptors(a.Id, aDescriptors);
                    sync.RegisterRemoteAssetDescriptors(b.Id, bDescriptors);
                    Observe(bItem, bPath, AssetOwnerOtherColor);
                    sync.RegisterRemoteAssetDescriptors(b.Id, Array.Empty<GeneratedAssetWireDescriptor>());
                    File.WriteAllBytes(Path.Combine(sync.CacheRoot, file), new byte[] { 1, 2, 3 });
                    sync.EnsureAssetsForData(a);
                    Observe(aItem, aPath, AssetOwnerCanonical);
                    CommitAssetOwner(sync, a.Id, file, AssetOwnerCanonical);
                    Observe(aItem, Path.Combine(sync.CacheRoot, file), AssetOwnerCanonical);
                    sync.Dispose(); sync.RegisterRemoteAssetDescriptors(a.Id, aDescriptors);
                    Equal(true, sync.ResolveCertifiedLocalPath(aPath) is null, "disposal clears and cannot rebind the index");
                    Observe(aItem, aPath, AssetOwnerCanonical);
                    Equal(0, sync.GetDebugSnapshot().DownloadStartedCount, "ownership observer starts no downloads");
                    File.Delete(Path.Combine(sync.CacheRoot, file));
                }
            } finally { observing = false; sprites.SetValue(null, priorSprites); assetSync.SetValue(null, priorSync); Directory.Delete(sandbox, true); }
        });
        Console.WriteLine("DETAIL: same-filename conflict add/remove/equal/replacement/validation/commit/disposal through inventory; both registration orders");
    }

    private static void RuntimeSpriteCertifiedLookupHasConstantHotPathWork()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var sprites = typeof(InfiniMod).GetProperty("Sprites")!; var assetSync = typeof(InfiniMod).GetProperty("AssetSync")!;
            object? priorSprites = sprites.GetValue(null), priorSync = assetSync.GetValue(null);
            long lookups = 0; int validationCalls = 0; Texture2D? captured = null;
            // Increment-only IL observer over the real lookup, not a substitute resolver or timing claim.
            MonoMod.Cil.ILContext.Manipulator countLookup = il => {
                var sites = il.Body.Instructions.Where(ins => ins.Operand is Mono.Cecil.MethodReference method
                    && method.Name == "TryGetValue" && method.DeclaringType.FullName.Contains(nameof(GeneratedAssetWireDescriptor))).ToArray();
                Equal(1, sites.Length, "one instrumented descriptor lookup site");
                var cursor = new MonoMod.Cil.ILCursor(il); cursor.Goto(sites[0]);
                cursor.EmitDelegate<Action>(() => lookups++);
            };
            using var ilHook = new MonoMod.RuntimeDetour.ILHook(typeof(GeneratedAssetSyncService).GetMethod("ResolveCertifiedLocalPath", AssetOwnerInstance)!, countLookup);
            AssetValidateHook validate = (original, path, descriptor) => { validationCalls++; return original(path, descriptor); };
            using var validationHook = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedAssetSyncService).GetMethod("IsValidCachedAsset", BindingFlags.Static | BindingFlags.NonPublic)!, validate);
            AssetGetHook get = (original, cache, path) => { captured = original(cache, path); return null; };
            using var getHook = new MonoMod.RuntimeDetour.Hook(typeof(RuntimeSpriteCache).GetMethod("TryGet", new[] { typeof(string) })!, get);
            try {
                foreach (int retained in new[] { 1, 64, 256, 1024 }) foreach (bool certified in new[] { false, true }) {
                    using var sync = new GeneratedAssetSyncService(); using var cache = new RuntimeSpriteCache();
                    sprites.SetValue(null, cache); assetSync.SetValue(null, sync);
                    string file = "hot_" + Guid.NewGuid().ToString("N") + ".png", originalPath = Path.Combine(Terraria.Program.SavePath, file);
                    File.WriteAllBytes(originalPath, AssetOwnerCanonical);
                    string hash = Convert.ToHexString(SHA256.HashData(AssetOwnerCanonical)).ToLowerInvariant();
                    for (int i = 0; i < retained - (certified ? 1 : 0); i++)
                        sync.RegisterRemoteAssetDescriptors("noise_" + i, new[] { new GeneratedAssetWireDescriptor { FileName = "noise_" + i + ".png", Length = AssetOwnerCanonical.Length, Sha256 = hash } });
                    if (certified) CommitAssetOwner(sync, "hot", file, AssetOwnerCanonical);
                    var item = ReviewItem(AssetOwnerData("hot", originalPath));
                    typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(item, (int)Terraria.Main.GameUpdateCount);
                    var entries = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", AssetOwnerInstance)!.GetValue(cache)!;
                    var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D)); GC.SuppressFinalize(texture);
                    string key = Path.GetFullPath(certified ? Path.Combine(sync.CacheRoot, file) : originalPath);
                    entries[key] = Activator.CreateInstance(typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!, texture, 0f, 0L)!;
                    try {
                        lookups = 0; validationCalls = 0;
                        for (int i = 0; i < 100; i++) { DrawAssetOwner(item); Equal(true, ReferenceEquals(texture, captured), "real inventory hot texture reference"); }
                        Console.WriteLine($"DETAIL: retained={retained} certified={certified} hotCalls=100 descriptorLookups={lookups} validations={validationCalls}");
                        Equal(100L, lookups, "one hot lookup independent of retained-item count");
                        Equal(0, validationCalls, "no PNG/hash validation on hot calls");
                    } finally { entries.Clear(); File.Delete(originalPath); File.Delete(Path.Combine(sync.CacheRoot, file)); }
                }
            } finally { sprites.SetValue(null, priorSprites); assetSync.SetValue(null, priorSync); }
        });
    }

    private static void RuntimeSpriteSelectedOwnerFailureBacksOffAndRetries()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var sync = new GeneratedAssetSyncService(); using var cache = new RuntimeSpriteCache();
            var sprites = typeof(InfiniMod).GetProperty("Sprites")!; var assetSync = typeof(InfiniMod).GetProperty("AssetSync")!;
            object? priorSprites = sprites.GetValue(null), priorSync = assetSync.GetValue(null);
            string file = "retry_" + Guid.NewGuid().ToString("N") + ".png";
            string originalPath = Path.Combine(Terraria.Program.SavePath, file), canonicalPath = Path.GetFullPath(Path.Combine(sync.CacheRoot, file));
            File.WriteAllBytes(originalPath, AssetOwnerOtherColor);
            bool observing = false; int fileAttempts = 0;
            AssetOpenHook open = (original, path) => {
                if (!observing) return original(path);
                fileAttempts++; Equal(canonicalPath, Path.GetFullPath(path), "failed read uses the selected normalized owner");
                throw new InvalidOperationException("controlled file/decode failure before GPU work");
            };
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(File).GetMethod("OpenRead", new[] { typeof(string) })!, open);
            try {
                sprites.SetValue(null, cache); assetSync.SetValue(null, sync);
                var data = AssetOwnerData("selected_retry", originalPath);
                CommitAssetOwner(sync, data.Id, file, AssetOwnerCanonical);
                peers.Registry.RegisterLocal(data, persist: false, ensureAssets: true);
                // A relative, whitespace-padded selector must still remember the final full key.
                data.Visual.SpritePath = "  " + Path.GetRelativePath(Environment.CurrentDirectory, originalPath) + "  ";
                var item = ReviewItem(data);
                typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(item, (int)Terraria.Main.GameUpdateCount);
                var negative = (Dictionary<string, DateTime>)typeof(RuntimeSpriteCache).GetField("_missingOrBad", AssetOwnerInstance)!.GetValue(cache)!;
                observing = true;
                DrawAssetOwner(item); DrawAssetOwner(item);
                Equal(1, fileAttempts, "two same-tick inventory calls make only one file attempt");
                Equal(canonicalPath, negative.Keys.Single(), "catch records exactly the selected normalized key");
                negative[canonicalPath] = DateTime.UtcNow - TimeSpan.FromSeconds(31);
                DrawAssetOwner(item); Equal(2, fileAttempts, "expiry permits one new attempt");
                DrawAssetOwner(item); Equal(2, fileAttempts, "retry failure renews backoff on the same key");
                cache.Invalidate(canonicalPath); Equal(0, negative.Count, "lifecycle invalidation clears the selected owner key");
                DrawAssetOwner(item); DrawAssetOwner(item); Equal(3, fileAttempts, "invalidation allows one retry then backs off again");
                Equal(0, sync.GetDebugSnapshot().DownloadStartedCount, "backoff observer starts no downloads");
            } finally { observing = false; sprites.SetValue(null, priorSprites); assetSync.SetValue(null, priorSync); File.Delete(originalPath); File.Delete(canonicalPath); }
        });
        Console.WriteLine("DETAIL: selected owner same-tick attempts=1 expiry retry=1 invalidation retry=1; CPU decode failure boundary");
    }

    private delegate Texture2D? AssetGetOriginal(RuntimeSpriteCache cache, string path);
    private delegate Texture2D? AssetGetHook(AssetGetOriginal original, RuntimeSpriteCache cache, string path);

    private static void RuntimeSpriteConsumerUsesCertifiedAssetOwner()
    {
        // Exact PNGs from the independent frozen review's offline CPU fixtures.
        byte[] canonical = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAP0lEQVR4nGNgGAWjYKQDRlwS1zMlJ1DTIs3pzwuwiTNR0xJywKgDRh0w6oBRB4w6YNQBow4YdcCoA0bBKBgFAKl2BChncJIaAAAAAElFTkSuQmCC");
        byte[] otherColor = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAP0lEQVR4nGNgGAWjYKQDRlwSkvsCJlDToudOGwqwiTNR0xJywKgDRh0w6oBRB4w6YNQBow4YdcCoA0bBKBgFAJnWBCigX3ypAAAAAElFTkSuQmCC");
        string hash = Convert.ToHexString(SHA256.HashData(canonical)).ToLowerInvariant();
        var failures = new List<string>(); int observed = 0;
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            var spriteProperty = typeof(InfiniMod).GetProperty("Sprites")!;
            var syncProperty = typeof(InfiniMod).GetProperty("AssetSync")!;
            var priorSprites = spriteProperty.GetValue(null); var priorSync = syncProperty.GetValue(null);
            string sandbox = Path.Combine(Terraria.Program.SavePath, "asset-owner-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(sandbox);
            bool observing = false; string? opened = null; byte[]? openedBytes = null; int validationsDuringDraw = 0;
            AssetOpenHook open = (original, path) => {
                if (!observing) return original(path);
                opened = Path.GetFullPath(path);
                using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
                using var memory = new MemoryStream(); stream.CopyTo(memory); openedBytes = memory.ToArray();
                throw new InvalidOperationException("CPU path observer stops before GPU decoding");
            };
            AssetValidateHook validate = (original, path, descriptor) => { if (observing) validationsDuringDraw++; return original(path, descriptor); };
            using var openHook = new MonoMod.RuntimeDetour.Hook(typeof(File).GetMethod("OpenRead", new[] { typeof(string) })!, open);
            using var validationHook = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedAssetSyncService).GetMethod("IsValidCachedAsset", BindingFlags.Static | BindingFlags.NonPublic)!, validate);
            try {
                foreach (string scenario in new[] { "canonical", "other-color-shadow", "corrupt-shadow", "same-byte-alias", "stale-windows", "url", "no-sync-local", "unverified-sync-local", "corrupt-sync-local", "stale-sync-local", "changed-certified-corrupt", "changed-certified-stale", "changed-descriptor-local" }) {
                    using var sync = new GeneratedAssetSyncService(); using var cache = new RuntimeSpriteCache();
                    string file = "owner_" + Guid.NewGuid().ToString("N") + ".png";
                    string local = Path.Combine(sync.CacheRoot, file); string originalPath = Path.Combine(sandbox, file);
                    byte[] originalBytes = scenario == "other-color-shadow" ? otherColor : scenario == "corrupt-shadow" ? new byte[] { 1, 2, 3, 4 } : canonical;
                    File.WriteAllBytes(originalPath, originalBytes);
                    if (scenario == "stale-windows") originalPath = @"Z:\unavailable-owner\" + file;
                    if (scenario == "url") originalPath = "https://offline.invalid/" + file;
                    bool verified = scenario is "canonical" or "other-color-shadow" or "corrupt-shadow" or "same-byte-alias" or "stale-windows" or "url";
                    spriteProperty.SetValue(null, cache); syncProperty.SetValue(null, scenario == "no-sync-local" ? null : sync);
                    var textureEntries = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(cache)!;
                    try {
                        var descriptor = new GeneratedAssetWireDescriptor { FileName = file, Length = canonical.Length, Sha256 = hash };
                        if (verified) {
                            typeof(GeneratedAssetSyncService).GetMethod("CommitVerifiedAsset", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(sync, new object[] { "asset_owner_review", file, canonical, hash });
                            sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                        } else if (scenario.StartsWith("changed-", StringComparison.Ordinal)) {
                            typeof(GeneratedAssetSyncService).GetMethod("CommitVerifiedAsset", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(sync, new object[] { "asset_owner_review", file, canonical, hash });
                            sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                            if (scenario == "changed-descriptor-local") {
                                descriptor = new GeneratedAssetWireDescriptor { FileName = file, Length = otherColor.Length, Sha256 = Convert.ToHexString(SHA256.HashData(otherColor)).ToLowerInvariant() };
                                sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                            } else {
                                File.WriteAllBytes(local, scenario == "changed-certified-corrupt" ? new byte[] { 4, 3, 2, 1 } : otherColor);
                            }
                        } else if (scenario != "no-sync-local") {
                            if (scenario != "unverified-sync-local") sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                            File.WriteAllBytes(local, scenario == "corrupt-sync-local" ? new byte[] { 4, 3, 2, 1 } : otherColor);
                        }
                        var wire = System.Text.Json.Nodes.JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!.AsObject();
                        wire["id"] = "asset_owner_review"; wire["sourceMode"] = "generated";
                        wire["visual"]!["spritePath"] = originalPath; wire["visual"]!["spriteStatus"] = "generated";
                        var data = ParseMaterialElement(wire); peers.Register(data);
                        // Real runtime asset lifecycle verifies before the Draw entry.
                        if (scenario != "no-sync-local") sync.EnsureAssetsForData(data);
                        var item = ReviewItem(data);
                        typeof(GeneratedItem).GetField("_lastHydrationTick", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(item, (int)Terraria.Main.GameUpdateCount);
                        opened = null; openedBytes = null; validationsDuringDraw = 0; observing = true;
                        try { item.PreDrawInInventory(null!, Vector2.Zero, new Rectangle(0, 0, 32, 32), Color.White, Color.White, Vector2.Zero, 1); }
                        finally { observing = false; }
                        Equal(Path.GetFullPath(verified ? local : originalPath), opened ?? "", "real inventory consumer selects declared certified owner or valid local-only path: " + scenario);
                        Equal(true, canonical.SequenceEqual(openedBytes ?? Array.Empty<byte>()), "consumer bytes equal certified PNG or legitimate local-only PNG: " + scenario);
                        Equal(0, validationsDuringDraw, "Draw never runs complete PNG/hash validation: " + scenario);
                        Equal(originalPath, data.Visual.SpritePath, "path ownership does not rewrite authored metadata: " + scenario);
                        Equal(0, sync.GetDebugSnapshot().DownloadStartedCount, "test has no download side effects"); observed++;
                        // Exercise the actual hot cache hit, not a replacement resolver.
                        var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D)); GC.SuppressFinalize(texture);
                        string cacheKey = Path.GetFullPath(verified ? local : originalPath);
                        textureEntries[cacheKey] = Activator.CreateInstance(typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!, texture, 0f, 0L)!;
                        observing = true;
                        try { for (int i = 0; i < 5; i++) Equal(true, ReferenceEquals(texture, cache.TryGet(originalPath)), "hot path retains exact cache identity: " + scenario); }
                        finally { observing = false; }
                        Equal(0, validationsDuringDraw, "cache hits perform no PNG/hash revalidation: " + scenario);
                    } catch (Exception error) { failures.Add(scenario + ": " + error.Message); }
                    finally { observing = false; textureEntries.Clear(); File.Delete(local); }
                }
                using var empty = new RuntimeSpriteCache(); spriteProperty.SetValue(null, empty);
                opened = null; observing = true;
                try { Equal(true, empty.TryGet("") is null, "empty selector stays silent"); }
                finally { observing = false; }
                Equal(true, opened is null, "empty selector cannot choose another texture source");
            } finally { observing = false; spriteProperty.SetValue(null, priorSprites); syncProperty.SetValue(null, priorSync); Directory.Delete(sandbox, true); }
        });
        Console.WriteLine($"DETAIL: actual asset-owner inventory controls={observed}/13 empty=1; no GPU decoding");
        if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }
}
