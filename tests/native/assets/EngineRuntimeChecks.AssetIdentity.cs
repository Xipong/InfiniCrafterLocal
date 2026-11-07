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
    private delegate bool AssetValidateOriginal(string path, GeneratedAssetWireDescriptor? descriptor);
    private delegate bool AssetValidateHook(AssetValidateOriginal original, string path, GeneratedAssetWireDescriptor? descriptor);

    private static IDisposable ObserveRuntimeSpriteFileOpen(Action<string> observe)
    {
        // Observe the caller's exact IL site: optimized JIT code may inline File.OpenRead.
        // The two-argument API now forwards to the exact selected-generation
        // loader which returns alpha bounds and support hull. Observe the actual I/O owner.
        return new MonoMod.RuntimeDetour.ILHook(typeof(RuntimeSpriteCache).GetMethod("TryGet", BindingFlags.Instance | BindingFlags.NonPublic,
            null, new[] { typeof(string), typeof(float).MakeByRefType(), typeof(Rectangle?).MakeByRefType(), typeof(Vector2[]).MakeByRefType() }, null)!, il => {
            var sites = il.Body.Instructions.Where(ins => ins.OpCode == Mono.Cecil.Cil.OpCodes.Call
                && ins.Operand is Mono.Cecil.MethodReference method && method.DeclaringType.FullName == typeof(File).FullName
                && method.Name == nameof(File.OpenRead) && method.Parameters.Count == 1
                && method.Parameters[0].ParameterType.FullName == typeof(string).FullName
                && method.ReturnType.FullName == typeof(FileStream).FullName).ToArray();
            Equal(1, sites.Length, "one instrumented runtime sprite File.OpenRead call site");
            var cursor = new MonoMod.Cil.ILCursor(il); cursor.Goto(sites[0]);
            cursor.EmitDelegate<Func<string, string>>(path => { observe(path); return path; });
        });
    }

    private static readonly byte[] AssetOwnerCanonical = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAP0lEQVR4nGNgGAWjYKQDRlwS1zMlJ1DTIs3pzwuwiTNR0xJywKgDRh0w6oBRB4w6YNQBow4YdcCoA0bBKBgFAKl2BChncJIaAAAAAElFTkSuQmCC");
    private static readonly byte[] AssetOwnerOtherColor = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAP0lEQVR4nGNgGAWjYKQDRlwSkvsCJlDToudOGwqwiTNR0xJywKgDRh0w6oBRB4w6YNQBow4YdcCoA0bBKBgFAJnWBCigX3ypAAAAAElFTkSuQmCC");
    private static readonly BindingFlags AssetOwnerInstance = BindingFlags.Instance | BindingFlags.NonPublic;

    private static GeneratedItemData AssetOwnerData(string id, string path)
    {
        var wire = System.Text.Json.Nodes.JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!.AsObject();
        wire["id"] = id; wire["sourceMode"] = "generated";
        wire["visual"]!["spritePath"] = path; wire["visual"]!["spriteStatus"] = "generated";
        wire["visual"]!["renderSizePx"] = 32; wire["visual"]!["forwardAngleDegrees"] = 0;
        var data = ParseMaterialElement(wire);
        Equal(path.Trim(), data.Visual.SpritePath, "asset fixture selector survives strict admission without truncation");
        GeneratedItemRegistryService.StampCurrentWorld(data);
        return data;
    }

    private static void CommitAssetOwner(GeneratedAssetSyncService sync, string id, string file, byte[] bytes)
        => typeof(GeneratedAssetSyncService).GetMethod("CommitVerifiedAsset", AssetOwnerInstance)!.Invoke(sync,
            new object[] { id, file, bytes, Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() });

    private static void DrawAssetOwner(GeneratedItem item)
    {
        // Existing selection/backoff observers explicitly prepare at lifecycle
        // before borrowing through inventory. Cold Draw itself is tested separately.
        InfiniMod.Sprites?.TryGet(item.Data.Visual.SpritePath);
        item.PreDrawInInventory(null!, Vector2.Zero, new Rectangle(0, 0, 32, 32), Color.White, Color.White, Vector2.Zero, 1);
    }

    private static void RuntimeSpriteConflictingCertificatesPreserveInventoryOwnership()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            foreach (bool reverse in new[] { false, true })
            {
                using var probe = new AssetInvalidationProbe();
                string file = "shared_" + Guid.NewGuid().ToString("N") + ".png";
                string shadow = Path.Combine(Terraria.Program.SavePath, file);
                File.WriteAllBytes(shadow, AssetOwnerOtherColor);
                var a = AssetOwnerData("conflict_a", file); var b = AssetOwnerData("conflict_b", shadow);
                var aDescriptor = new GeneratedAssetWireDescriptor { FileName = file, Length = AssetOwnerCanonical.Length, Sha256 = ImageHash(AssetOwnerCanonical) };
                var bDescriptor = new GeneratedAssetWireDescriptor { FileName = file, Length = AssetOwnerOtherColor.Length, Sha256 = ImageHash(AssetOwnerOtherColor) };
                foreach (var data in reverse ? new[] { b, a } : new[] { a, b })
                    probe.Sync.RegisterRemoteAssetDescriptors(data.Id, new[] { data == a ? aDescriptor : bDescriptor });
                CommitAssetOwner(probe.Sync, a.Id, file, AssetOwnerCanonical);
                Equal(true, probe.Sync.ResolveCertifiedLocalPath(file) is null, "conflicting manifests have no global basename proof");
                Equal(true, probe.Cache.TryGet(file) is null, "conflict cannot use indexed bytes without unique proof");
                Equal(true, probe.Cache.TryGet(shadow) is null, "conflict cannot authorize raw shadow bytes");
                Equal(0, probe.Loads.Count, "refusal occurs before decode");
                probe.Sync.RegisterRemoteAssetDescriptors(b.Id, Array.Empty<GeneratedAssetWireDescriptor>());
                var item = probe.Item(a.Id, file);
                probe.Draw(item);
                Equal(true, AssetOwnerCanonical.SequenceEqual(probe.Loads.Single().Bytes), "removing conflict exposes only the certified owner");
                probe.Sync.RegisterRemoteAssetDescriptors(b.Id, new[] { aDescriptor });
                probe.Sync.RegisterRemoteAssetDescriptors(a.Id, Array.Empty<GeneratedAssetWireDescriptor>());
                Equal(true, probe.Cache.TryGet(file) is not null, "equal identities can retain their existing proof");
                probe.Sync.RegisterRemoteAssetDescriptors(b.Id, new[] { bDescriptor });
                Equal(true, probe.Cache.TryGet(file) is null, "changed identity cannot borrow hot cached bytes");
                probe.Sync.RegisterRemoteAssetDescriptors(a.Id, new[] { aDescriptor });
                probe.Sync.RegisterRemoteAssetDescriptors(b.Id, Array.Empty<GeneratedAssetWireDescriptor>());
                probe.Sync.EnsureAssetsForData(a);
                string canonical = probe.Sync.ResolveLocalPath(file)!;
                File.WriteAllBytes(canonical, new byte[] { 1, 2, 3 });
                probe.Sync.EnsureAssetsForData(a);
                Equal(true, probe.Cache.TryGet(shadow) is null, "bad canonical bytes cannot fall back to raw local PNG");
                CommitAssetOwner(probe.Sync, a.Id, file, AssetOwnerCanonical);
                Equal(true, probe.Cache.TryGet(file) is not null, "restoring immutable bytes recertifies the owner");
                probe.Sync.Dispose();
                Equal(true, probe.Cache.TryGet(shadow) is null, "disposed authority cannot be replaced by raw path access");
                Equal(true, File.ReadAllBytes(shadow).SequenceEqual(AssetOwnerOtherColor), "raw shadow bytes were never modified");
                Equal(0, probe.Sync.GetDebugSnapshot().DownloadStartedCount, "fixture starts no downloads");
            }
        });
    }

    private static string PublishAssetOwner(GeneratedAssetSyncService sync, string id, string file, byte[] bytes)
    {
        var data = AssetOwnerData(id, file);
        string canonical = new SharedImageStore(sync.CacheRoot).Publish(file, bytes, data.RecipeMeta.WorldId,
            Terraria.Main.worldName, id, data.Name, "item");
        // The wire selector is the published canonical transfer name, not the
        // private harness's possibly >260-character storage path. Keep filesystem
        // ownership separate from DTO bounds and certify the selector callers use.
        string selector = Path.GetFileName(canonical);
        data.Visual.SpritePath = selector;
        Equal(canonical, sync.ResolveLocalPath(selector)!, "fixture resolves only its published indexed final");
        if (Terraria.Main.dedServ)
        {
            // Dedicated servers produce manifests; they never enter client texture certification.
            var descriptor = sync.BuildServerAssetDescriptors(data).Single();
            Equal(selector, descriptor.FileName, "server manifest retains the published transfer name");
            Equal(ImageHash(bytes), descriptor.Sha256, "server manifest certifies exact immutable PNG bytes");
            return canonical;
        }
        // Fixture admission has no presentation owner yet; callers observe their
        // own explicit preparation/retirement queues after setup.
        var sprites = typeof(InfiniMod).GetProperty("Sprites")!;
        object? previous = sprites.GetValue(null);
        try { sprites.SetValue(null, null); sync.EnsureAssetsForData(data); }
        finally { sprites.SetValue(null, previous); }
        Equal(canonical, sync.ResolveCertifiedLocalPath(selector)!, "fixture uses current publication and certification");
        return canonical;
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
            Action<string> open = path => {
                if (!observing) return;
                fileAttempts++; Equal(canonicalPath, Path.GetFullPath(path), "failed read uses the selected normalized owner");
                throw new InvalidOperationException("controlled file/decode failure before GPU work");
            };
            using var hook = ObserveRuntimeSpriteFileOpen(open);
            try {
                sprites.SetValue(null, cache); assetSync.SetValue(null, sync);
                var data = AssetOwnerData("selected_retry", originalPath);
                CommitAssetOwner(sync, data.Id, file, AssetOwnerCanonical);
                canonicalPath = sync.ResolveLocalPath(file)!;
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

    // Real inventory -> cache -> FNA CPU queue. Decode/readback/upload/disposal
    // are observed only at their GPU boundaries; this is not native GPU proof.
    private sealed class AssetInvalidationProbe : IDisposable
    {
        internal readonly RuntimeSpriteCache Cache = new();
        internal readonly GeneratedAssetSyncService Sync = new();
        internal readonly SpriteBatch Batch;
        internal readonly List<(string Path, byte[] Bytes, Texture2D Texture, int Thread)> Loads = new();
        internal readonly List<(Texture2D Texture, int Thread)> Disposals = new();
        internal int Reads, Uploads, Flushes, Attempts;
        internal bool FailDecode;
        private bool cleaningUp;
        internal readonly int OwnerThread = Environment.CurrentManagedThreadId;
        private readonly PropertyInfo sprites = typeof(InfiniMod).GetProperty("Sprites")!;
        private readonly PropertyInfo assetSync = typeof(InfiniMod).GetProperty("AssetSync")!;
        private readonly FieldInfo actions = typeof(Terraria.Main).GetField("_mainThreadActions", BindingFlags.Static | BindingFlags.NonPublic)!;
        private readonly object? oldSprites, oldSync, oldActions;
        private readonly GraphicsDeviceManager oldGraphics = Terraria.Main.graphics;
        private readonly SpriteBatch oldBatch = Terraria.Main.spriteBatch;
        private readonly List<IDisposable> hooks = new();
        private readonly FieldInfo count = typeof(SpriteBatch).GetField("numSprites", AssetOwnerInstance)!;
        private readonly FieldInfo textureInfo = typeof(SpriteBatch).GetField("textureInfo", AssetOwnerInstance)!;
        internal int QueuedSprites => (int)count.GetValue(Batch)!;
        internal int QueuedActions => ((System.Collections.Concurrent.ConcurrentQueue<Action>)actions.GetValue(null)!).Count;

        internal AssetInvalidationProbe()
        {
            oldSprites = sprites.GetValue(null); oldSync = assetSync.GetValue(null); oldActions = actions.GetValue(null);
            actions.SetValue(null, new System.Collections.Concurrent.ConcurrentQueue<Action>());
            sprites.SetValue(null, Cache); assetSync.SetValue(null, Sync);
            Terraria.Main.graphics = (GraphicsDeviceManager)RuntimeHelpers.GetUninitializedObject(typeof(GraphicsDeviceManager));
            GC.SuppressFinalize(Terraria.Main.graphics);
            Batch = CpuSpriteBatch(128);
            Terraria.Main.spriteBatch = Batch;
            Func<GraphicsDevice, Stream, Texture2D> load = (_, stream) => {
                Attempts++;
                if (FailDecode) throw new InvalidOperationException("controlled decode boundary failure, no GPU");
                using var memory = new MemoryStream(); stream.CopyTo(memory);
                var texture = CpuTexture(32, 32);
                Loads.Add((Path.GetFullPath(((FileStream)stream).Name), memory.ToArray(), texture, Environment.CurrentManagedThreadId));
                return texture;
            };
            hooks.Add(new MonoMod.RuntimeDetour.Hook(typeof(Texture2D).GetMethod("FromStream", new[] { typeof(GraphicsDevice), typeof(Stream) })!, load));
            Action<Texture2D, Color[]> read = (_, pixels) => { Reads++; Array.Fill(pixels, Color.White); };
            Action<Texture2D, Color[]> upload = (_, _) => Uploads++;
            Action<GraphicsResource> dispose = resource => Disposals.Add(((Texture2D)resource, Environment.CurrentManagedThreadId));
            // Retain canonical selection/cache logic, replacing only GPU calls.
            SpriteGpuBoundaries(hooks.Add, read, upload, dispose);
            Action<SpriteBatch> flush = batch => {
                int n = (int)count.GetValue(batch)!;
                var textures = (Texture2D[])textureInfo.GetValue(batch)!;
                if (!cleaningUp)
                    for (int i = 0; i < n; i++) Equal(false, Disposals.Any(d => ReferenceEquals(d.Texture, textures[i])), "queued texture stays alive until real FNA End/Flush boundary");
                Flushes++; count.SetValue(batch, 0);
            };
            hooks.Add(new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", AssetOwnerInstance)!, flush));
            Batch.Begin();
        }

        internal GeneratedItem Item(string id, string path)
        {
            var item = ReviewItem(AssetOwnerData(id, path));
            typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(item, (int)Terraria.Main.GameUpdateCount);
            return item;
        }

        internal Texture2D Draw(GeneratedItem item)
        {
            // This observer owns explicit CPU preparation before real draw. Do
            // not weaken lease/retirement stress by draining borrowers here.
            Cache.TryGet(item.Data.Visual.SpritePath);
            int before = QueuedSprites;
            Equal(false, item.PreDrawInInventory(Batch, Vector2.Zero, new Rectangle(0, 0, 32, 32), Color.White, Color.White, Vector2.Zero, 1), "real inventory consumer queues runtime sprite");
            Equal(before + 1, QueuedSprites, "inventory submits exactly one real FNA sprite");
            return ((Texture2D[])textureInfo.GetValue(Batch)!)[before];
        }

        internal void DrainOwnerQueue()
        {
            Equal(false, (bool)typeof(SpriteBatch).GetField("beginCalled", AssetOwnerInstance)!.GetValue(Batch)!, "owner callback is exercised only after End");
            // Installed Main.Update calls this after base.Update, outside Draw.
            typeof(Terraria.Main).GetMethod("ConsumeAllMainThreadActions", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, null);
        }

        public void Dispose()
        {
            try {
                // Cleanup must not mask the assertion that exposed an early disposal.
                cleaningUp = true;
                if ((bool)typeof(SpriteBatch).GetField("beginCalled", AssetOwnerInstance)!.GetValue(Batch)!) Batch.End();
                Cache.Dispose(); DrainOwnerQueue(); Sync.Dispose();
            } finally {
                for (int i = hooks.Count - 1; i >= 0; i--) hooks[i].Dispose();
                sprites.SetValue(null, oldSprites); assetSync.SetValue(null, oldSync); actions.SetValue(null, oldActions);
                Terraria.Main.graphics = oldGraphics; Terraria.Main.spriteBatch = oldBatch;
            }
        }
    }

    private static void RuntimeSpriteInvalidationReloadsInventoryWithoutRetiringQueuedTexture()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string path = PublishAssetOwner(probe.Sync, "invalidate", "invalidate.png", AssetOwnerCanonical);
            string other = PublishAssetOwner(probe.Sync, "independent", "independent.png", AssetOwnerCanonical);
            var item = probe.Item("invalidate", Path.GetFileName(path)); var independent = probe.Item("independent", Path.GetFileName(other));
            Texture2D first = probe.Draw(item);
            Equal(true, ReferenceEquals(first, probe.Draw(item)), "unchanged hot inventory keeps exact texture");
            Texture2D unrelated = probe.Draw(independent);
            Equal(2, probe.Loads.Count, "initial target and unrelated load only once");
            System.Threading.Tasks.Task.Run(() => { for (int i = 0; i < 4; i++) probe.Cache.Invalidate(path); }).GetAwaiter().GetResult();
            Equal(0, probe.Disposals.Count, "downloader invalidation cannot dispose queued texture");
            Equal(2, probe.Uploads, "downloader invalidation cannot upload");
            Texture2D refreshed = probe.Draw(item);
            Equal(false, ReferenceEquals(first, refreshed), "invalidation must not return old loaded Texture2D");
            Equal(3, probe.Loads.Count, "one lazy replacement load through inventory");
            Equal(true, AssetOwnerCanonical.SequenceEqual(probe.Loads[^1].Bytes), "invalidation reloads only the same certified immutable bytes");
            Equal(true, ReferenceEquals(unrelated, probe.Draw(independent)), "one invalidation does not flush unrelated hot asset");
            Equal(true, ReferenceEquals(refreshed, probe.Draw(item)), "replacement is itself a hot hit");
            Equal(3, probe.Uploads, "replacement conversion/upload occurs once, not per draw");
            Equal(0, probe.Disposals.Count, "old queued texture is retained until owner boundary");
            probe.Batch.End(); probe.DrainOwnerQueue();
            Equal(1, probe.Disposals.Count, "repeated invalidation retires old texture exactly once");
            Equal(true, ReferenceEquals(first, probe.Disposals.Single().Texture), "retirement targets only stale generation");
            Equal(probe.OwnerThread, probe.Disposals.Single().Thread, "retirement runs on the owner thread");
            Equal(true, probe.Loads.All(l => l.Thread == probe.OwnerThread), "all loads run on consumer owner thread");
            probe.DrainOwnerQueue(); Equal(1, probe.Disposals.Count, "no disposal replay");
            System.Threading.Tasks.Task.Run(() => probe.Cache.Invalidate(path)).GetAwaiter().GetResult();
            probe.DrainOwnerQueue();
            Equal(2, probe.Disposals.Count, "unused replacement retires without another Draw or TryGet");
            Equal(3, probe.Loads.Count, "retirement alone never reloads or uploads");
            Equal(false, probe.Disposals.Any(d => ReferenceEquals(d.Texture, unrelated)), "independent indexed asset stays owned and alive");
            Equal(Path.GetFileName(path), item.Data.Visual.SpritePath, "no authored selector rewrite");
            Equal(0, probe.Sync.GetDebugSnapshot().DownloadStartedCount, "CPU observer starts no downloads");
        });
        Console.WriteLine("DETAIL: certified-file invalidation via inventory/FNA queue; repeated worker invalidation; independent hot asset; deferred owner disposal; GPU boundaries intercepted");
    }

    private static void RuntimeSpriteInvalidationAliasesUseSelectedOwnerAndBackoffKey()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers();
            string? oldRoot = Environment.GetEnvironmentVariable("ICL_INVALIDATION_ROOT");
            Environment.SetEnvironmentVariable("ICL_INVALIDATION_ROOT", Terraria.Program.SavePath);
            try {
                foreach (string scenario in new[] { "local-shadow", "relative-padded", "environment", "stale-windows", "url" }) {
                    using var probe = new AssetInvalidationProbe();
                    string file = "alias_" + Guid.NewGuid().ToString("N") + ".png";
                    string original = Path.Combine(Terraria.Program.SavePath, file), canonical = Path.GetFullPath(Path.Combine(probe.Sync.CacheRoot, file));
                    File.WriteAllBytes(original, AssetOwnerOtherColor);
                    string selector = scenario switch {
                        "relative-padded" => "  " + Path.GetRelativePath(Environment.CurrentDirectory, original) + "  ",
                        "environment" => "%ICL_INVALIDATION_ROOT%/" + file,
                        "stale-windows" => @"Z:\unavailable-owner\" + file,
                        "url" => "https://offline.invalid/" + file,
                        _ => original,
                    };
                    CommitAssetOwner(probe.Sync, "alias", file, AssetOwnerCanonical);
                    canonical = probe.Sync.ResolveLocalPath(file)!;
                    probe.Batch.End(); probe.DrainOwnerQueue(); probe.Batch.Begin();
                    var item = probe.Item("alias", selector);
                    string storedSelector = item.Data.Visual.SpritePath;
                    Texture2D first = probe.Draw(item);
                    Equal(canonical, probe.Loads.Single().Path, "initial certified owner: " + scenario);
                    System.Threading.Tasks.Task.Run(() => probe.Cache.Invalidate(selector)).GetAwaiter().GetResult();
                    Texture2D refreshed = probe.Draw(item);
                    Equal(false, ReferenceEquals(first, refreshed), "alias invalidation removes selected canonical hot entry: " + scenario);
                    Equal(canonical, probe.Loads[^1].Path, "alias reload preserves certified byte owner: " + scenario);
                    Equal(true, AssetOwnerCanonical.SequenceEqual(probe.Loads[^1].Bytes), "alias cannot promote different local shadow bytes: " + scenario);
                    Equal(storedSelector, item.Data.Visual.SpritePath, "stored authored selector unchanged: " + scenario);
                    // A failed refresh must not resurrect the stale hot texture or
                    // back off on the authored alias instead of the selected owner.
                    probe.FailDecode = true; probe.Cache.Invalidate(canonical);
                    DrawAssetOwner(item); DrawAssetOwner(item);
                    Equal(3, probe.Attempts, "failure then same-key backoff makes one attempt: " + scenario);
                    var negative = (Dictionary<string, DateTime>)typeof(RuntimeSpriteCache).GetField("_missingOrBad", AssetOwnerInstance)!.GetValue(probe.Cache)!;
                    Equal(canonical, negative.Keys.Single(), "failure backoff retains selected full key: " + scenario);
                    probe.Cache.Invalidate(selector); Equal(0, negative.Count, "alias clears the selected owner's negative key: " + scenario);
                    DrawAssetOwner(item); DrawAssetOwner(item); Equal(4, probe.Attempts, "one invalidation retry then renewed backoff: " + scenario);
                    probe.FailDecode = false; probe.Cache.Invalidate(selector);
                    Texture2D recovered = probe.Draw(item);
                    Equal(false, ReferenceEquals(refreshed, recovered), "recovery publishes only a fresh resource: " + scenario);
                    Equal(5, probe.Attempts, "one successful recovery attempt: " + scenario);
                    probe.Batch.End(); probe.DrainOwnerQueue();
                    Equal(2, probe.Disposals.Count, "both invalidated successful generations retire once: " + scenario);
                    Console.WriteLine("DETAIL: invalidation alias=" + scenario + " canonical loads=3 failedAttempts=2 negative-key-preserved=1");
                }
            } finally { Environment.SetEnvironmentVariable("ICL_INVALIDATION_ROOT", oldRoot); }
        });
    }

    private static void RuntimeSpriteInvalidationClearAndDisposeFencePendingRetirement()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string path = PublishAssetOwner(probe.Sync, "retirement", "retirement-lifecycle.png", AssetOwnerCanonical);
            var item = probe.Item("retirement", Path.GetFileName(path));
            probe.Draw(item);
            for (int generation = 0; generation < 2; generation++) {
                System.Threading.Tasks.Task.Run(() => { for (int i = 0; i < 20; i++) probe.Cache.Invalidate(path); }).GetAwaiter().GetResult();
                probe.Draw(item);
            }
            Equal(1, probe.QueuedActions, "multiple loaded generations share one retirement callback");
            Equal(0, probe.Disposals.Count, "no early disposal of any queued generation");
            string failed = PublishAssetOwner(probe.Sync, "failed-retirement", "failed-retirement.png", AssetOwnerCanonical);
            probe.FailDecode = true; probe.Cache.TryGet(failed); probe.FailDecode = false;
            Equal(1, probe.Cache.GetDebugSnapshot().MissingOrBadCount, "negative control exists before clear");
            probe.Batch.End();
            Equal(1, probe.Cache.Clear(clearMissingOrBad: false), "Clear return preserves active-entry count");
            Equal(0, probe.Disposals.Count, "Clear only retires ownership; Main.Update reclaims live and pending resources");
            Equal(1, probe.Cache.GetDebugSnapshot().MissingOrBadCount, "Clear(false) preserves negative backoff");
            Equal(1, probe.QueuedActions, "the already-enqueued callback remains harmless and coalesced");
            probe.Batch.Begin(); Texture2D fresh = probe.Draw(item);
            Equal(false, probe.Disposals.Any(d => ReferenceEquals(d.Texture, fresh)), "Clear permits a new independent loaded generation");
            System.Threading.Tasks.Task.Run(() => probe.Cache.Invalidate(path)).GetAwaiter().GetResult();
            Equal(1, probe.QueuedActions, "new retirement before old callback reuses its owner boundary");
            probe.Batch.End(); probe.DrainOwnerQueue();
            Equal(4, probe.Disposals.Count, "old callback does not redispose cleared generations");
            Equal(4, probe.Disposals.Select(d => d.Texture).Distinct().Count(), "each reclaimed generation appears once");
            probe.Batch.Begin(); probe.Draw(item); probe.Batch.End();
            probe.Cache.Dispose();
            Equal(4, probe.Disposals.Count, "Dispose retires final texture without synchronous disposal");
            Equal(0, probe.Cache.GetDebugSnapshot().MissingOrBadCount, "Dispose clears negative backoff");
            Equal(true, probe.Cache.TryGet(path) is null, "disposed cache cannot recreate resources after unload");
            probe.Cache.Invalidate(path); probe.Cache.Dispose(); probe.DrainOwnerQueue();
            Equal(5, probe.Loads.Count, "late use and invalidation cannot reload disposed cache");
            Equal(5, probe.Disposals.Count, "repeated Dispose and pending callback cannot double-dispose");
        });
        Console.WriteLine("DETAIL: repeated generations retire via one owner callback; Clear(false) preserves backoff; Clear/Dispose reclaim retired resources; no post-dispose resurrection");
    }

    private delegate int AssetClearOriginal(RuntimeSpriteCache cache, bool clearMissingOrBad);
    private delegate int AssetClearHook(AssetClearOriginal original, RuntimeSpriteCache cache, bool clearMissingOrBad);

    private static int SpriteOwnedResources(RuntimeSpriteCache cache)
        => cache.GetDebugSnapshot().TextureCount + ((IList)typeof(RuntimeSpriteCache).GetField("_retiredTextures", AssetOwnerInstance)!.GetValue(cache)!).Count;

    private static void WithSpriteCapacity(Action action)
    {
        var config = typeof(Terraria.ModLoader.ContentInstance<InfiniCrafterLocal.Common.Config.InfiniGameplayQolConfig>).GetProperty("Instance")!;
        object? prior = config.GetValue(null);
        config.SetValue(null, new InfiniCrafterLocal.Common.Config.InfiniGameplayQolConfig { RuntimeSpriteCacheMaxTextures = 64 });
        try { action(); } finally { config.SetValue(null, prior); }
    }

    private static void RuntimeSpriteLruRetainsQueuedBorrowersUntilOwnerDrain()
    {
        WithLighting((_, __) => WithSpriteCapacity(() => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string firstPath = PublishAssetOwner(probe.Sync, "lru", "lru-first.png", AssetOwnerCanonical);
            Texture2D first = probe.Draw(probe.Item("lru", Path.GetFileName(firstPath)));
            var drawData = new Terraria.DataStructures.DrawData(first, Vector2.Zero, first.Bounds, Color.White, 0f, Vector2.Zero, 1f, SpriteEffects.None, 0f);
            int capacity = probe.Cache.GetDebugSnapshot().MaxCachedTextures;
            for (int i = 0; i < capacity; i++) {
                string path = PublishAssetOwner(probe.Sync, "lru-" + i, "lru-" + i + ".png", AssetOwnerCanonical);
                Equal(true, probe.Cache.TryGet(path) is not null, "LRU replacement admits a real cache load");
            }
            Equal(capacity, probe.Cache.GetDebugSnapshot().TextureCount, "LRU preserves resident cap");
            Equal(1L, probe.Cache.GetDebugSnapshot().EvictionCount, "one actual LRU eviction");
            Equal(0, probe.Disposals.Count, "LRU cannot dispose a texture already borrowed by SpriteBatch/DrawData");
            drawData.Draw(probe.Batch);
            Equal(2, probe.QueuedSprites, "evicted DrawData still submits its borrowed texture before End");
            Equal(1, probe.QueuedActions, "LRU uses existing coalesced owner retirement");
            probe.Batch.End(); probe.DrainOwnerQueue();
            Equal(true, ReferenceEquals(first, probe.Disposals.Single().Texture), "LRU disposes exactly its evicted generation after borrowers end");
            probe.Cache.Clear(); probe.DrainOwnerQueue();
            Equal(capacity + 1, probe.Disposals.Count, "LRU plus teardown reclaim every loaded texture once");
            Equal(true, probe.Disposals.All(d => d.Thread == probe.OwnerThread), "all admitted-resource retirement belongs to owner drain");
        }));
    }

    private static void RuntimeSpriteWorkerClearAndModUnloadDeferBorrowedResources()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string path = PublishAssetOwner(probe.Sync, "worker", "worker-teardown.png", AssetOwnerCanonical);
            Texture2D first = probe.Draw(probe.Item("worker", Path.GetFileName(path)));
            var drawData = new Terraria.DataStructures.DrawData(first, Vector2.Zero, first.Bounds, Color.White, 0f, Vector2.Zero, 1f, SpriteEffects.None, 0f);
            string failed = PublishAssetOwner(probe.Sync, "failed-worker", "failed-worker.png", AssetOwnerCanonical);
            probe.FailDecode = true; probe.Cache.TryGet(failed); probe.FailDecode = false;
            int removed = System.Threading.Tasks.Task.Run(() => probe.Cache.Clear(false)).GetAwaiter().GetResult();
            Equal(1, removed, "worker Clear return still counts active entries");
            Equal(0, probe.Cache.GetDebugSnapshot().TextureCount, "worker Clear immediately removes lookup authority");
            Equal(1, probe.Cache.GetDebugSnapshot().MissingOrBadCount, "Clear(false) retains negative backoff");
            int clearDisposals = probe.Disposals.Count;
            drawData.Draw(probe.Batch);
            Texture2D second = probe.Draw(probe.Item("worker", Path.GetFileName(path)));
            Equal(false, ReferenceEquals(first, second), "Clear allows independent fresh load while old generation is retired");
            int worker = System.Threading.Tasks.Task.Run(() => { int thread = Environment.CurrentManagedThreadId; peers.Mod.Unload(); return thread; }).GetAwaiter().GetResult();
            Equal(false, worker == probe.OwnerThread, "actual Mod.Unload hook executed on isolated worker");
            Console.WriteLine($"DETAIL: ownerThread={probe.OwnerThread} unloadWorker={worker} disposedAfterWorkerClear={clearDisposals} disposedAfterWorkerUnload={probe.Disposals.Count}; queuedBorrowers={probe.QueuedSprites}");
            Equal(0, clearDisposals, "worker Clear cannot dispose borrowed graphics resource");
            Equal(0, probe.Disposals.Count, "worker Mod.Unload cannot dispose queued borrower");
            Equal(0, probe.Cache.GetDebugSnapshot().TextureCount, "unload removes active authority");
            Equal(0, probe.Cache.GetDebugSnapshot().MissingOrBadCount, "unload clears negative authority");
            Equal(true, probe.Cache.TryGet(path) is null, "disposed cache never resurrects before callback");
            probe.Cache.Invalidate(path); probe.Cache.Dispose();
            Equal(1, probe.QueuedActions, "Clear/Unload share one captured-cache callback");
            using var replacement = new RuntimeSpriteCache(); typeof(InfiniMod).GetProperty("Sprites")!.SetValue(null, replacement);
            probe.Batch.End(); probe.DrainOwnerQueue();
            Equal(2, probe.Disposals.Count, "owner callback reclaims both old-cache generations");
            Equal(2, probe.Disposals.Select(d => d.Texture).Distinct().Count(), "worker lifecycle never double-disposes");
            Equal(true, probe.Disposals.All(d => d.Thread == probe.OwnerThread), "worker teardown marshals all resource retirement to owner");
            Equal(0, SpriteOwnedResources(probe.Cache), "disposed old cache owns no resources after drain");
            Equal(0, replacement.GetDebugSnapshot().TextureCount, "captured old callback never mutates replacement cache");
            probe.DrainOwnerQueue(); Equal(2, probe.Disposals.Count, "teardown callback cannot replay");
        });
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
            string sandbox = Path.Combine(Terraria.Program.SavePath, "ao"); Directory.CreateDirectory(sandbox);
            bool observing = false; string? opened = null; byte[]? openedBytes = null; int validationsDuringDraw = 0;
            Action<string> open = path => {
                if (!observing) return;
                opened = Path.GetFullPath(path);
                using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
                using var memory = new MemoryStream(); stream.CopyTo(memory); openedBytes = memory.ToArray();
                throw new InvalidOperationException("CPU path observer stops before GPU decoding");
            };
            AssetValidateHook validate = (original, path, descriptor) => { if (observing) validationsDuringDraw++; return original(path, descriptor); };
            using var openHook = ObserveRuntimeSpriteFileOpen(open);
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
                            local = sync.ResolveLocalPath(file)!;
                            sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                        } else if (scenario.StartsWith("changed-", StringComparison.Ordinal)) {
                            typeof(GeneratedAssetSyncService).GetMethod("CommitVerifiedAsset", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(sync, new object[] { "asset_owner_review", file, canonical, hash });
                            local = sync.ResolveLocalPath(file)!;
                            sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                            if (scenario == "changed-descriptor-local") {
                                descriptor = new GeneratedAssetWireDescriptor { FileName = file, Length = otherColor.Length, Sha256 = Convert.ToHexString(SHA256.HashData(otherColor)).ToLowerInvariant() };
                                sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                            } else {
                                File.WriteAllBytes(local, scenario == "changed-certified-corrupt" ? new byte[] { 4, 3, 2, 1 } : otherColor);
                                // Stat-based freshness is the declared boundary. Immediate
                                // same-length writes can share Windows timestamp resolution.
                                File.SetLastWriteTimeUtc(local, DateTime.UtcNow.AddMinutes(1));
                            }
                        } else if (scenario != "no-sync-local") {
                            if (scenario != "unverified-sync-local") sync.RegisterRemoteAssetDescriptors("asset_owner_review", new[] { descriptor });
                            File.WriteAllBytes(local, scenario == "corrupt-sync-local" ? new byte[] { 4, 3, 2, 1 } : otherColor);
                        }
                        var wire = System.Text.Json.Nodes.JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!.AsObject();
                        wire["id"] = "asset_owner_review"; wire["sourceMode"] = "generated";
                        wire["visual"]!["spritePath"] = originalPath; wire["visual"]!["spriteStatus"] = "generated";
                        wire["visual"]!["renderSizePx"] = 32; wire["visual"]!["forwardAngleDegrees"] = 0;
                        var data = ParseMaterialElement(wire); peers.Register(data);
                        // Real runtime asset lifecycle verifies before the Draw entry.
                        if (scenario != "no-sync-local") sync.EnsureAssetsForData(data);
                        var item = ReviewItem(data);
                        typeof(GeneratedItem).GetField("_lastHydrationTick", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(item, (int)Terraria.Main.GameUpdateCount);
                        opened = null; openedBytes = null; validationsDuringDraw = 0; observing = true;
                        try { DrawAssetOwner(item); }
                        finally { observing = false; }
                        Equal(verified ? Path.GetFullPath(local) : "", opened ?? "", "inventory requires current indexed certificate, never raw local access: " + scenario);
                        if (verified) Equal(true, canonical.SequenceEqual(openedBytes ?? Array.Empty<byte>()), "consumer bytes equal certified PNG: " + scenario);
                        else Equal(true, openedBytes is null, "unproven bytes cannot reach a file open: " + scenario);
                        Equal(0, validationsDuringDraw, "Draw never runs complete PNG/hash validation: " + scenario);
                        Equal(originalPath, data.Visual.SpritePath, "path ownership does not rewrite authored metadata: " + scenario);
                        Equal(0, sync.GetDebugSnapshot().DownloadStartedCount, "test has no download side effects"); observed++;
                        // Exercise the actual hot cache hit, not a replacement resolver.
                        var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D)); GC.SuppressFinalize(texture);
                        string cacheKey = Path.GetFullPath(verified ? local : originalPath);
                        textureEntries[cacheKey] = Activator.CreateInstance(typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!, texture, 0f, 0L)!;
                        observing = true;
                        try { for (int i = 0; i < 5; i++) Equal(verified, ReferenceEquals(texture, cache.TryGet(originalPath)), "hot entry cannot bypass current certificate: " + scenario); }
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
