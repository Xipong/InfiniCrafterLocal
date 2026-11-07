using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static string ImageHash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static string ImageIndexPath(string root, string file)
        => Path.Combine(root, ".index", ImageHash(Encoding.UTF8.GetBytes(file.ToLowerInvariant())) + ".json");

    private static void SharedImagesStableReadableOwnership()
    {
        string root = Path.Combine(Terraria.Program.SavePath, "shared-readable");
        var store = new SharedImageStore(root);
        string path = store.Publish("item--abc.png", AssetOwnerCanonical, "42", "Мой мир / 🌍", "stable-id", "Звёздный меч", "item");
        Equal(true, path.Contains("Мой мир--73475cb40a568e8d"), "UTF8 hash and readable Unicode world folder agree with Python");
        Equal(true, path.Contains("Звёздный меч--"), "item label remains readable");
        Equal("final", Path.GetFileName(Path.GetDirectoryName(path)), "only final published PNGs are served");
        Equal(true, System.Text.RegularExpressions.Regex.IsMatch(Path.GetFileName(path), "^item--[a-f0-9]{64}\\.png$"), "wire token gains a readable role and stable digest without changing its alias");
        Equal(path, store.Resolve(Path.GetFileName(path))!.Path, "canonical filename and transport alias resolve the same single final");
        Equal(path, store.Publish("item--abc.png", AssetOwnerCanonical, "42", "Новое имя", "stable-id", "Переименован"), "renames retain stable identity directory");
        using (var identity = JsonDocument.Parse(File.ReadAllText(Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(path))!, ".identity.json"))))
            Equal("Переименован", identity.RootElement.GetProperty("name").GetString()!, "display metadata reflects rename without moving references");
        Equal(path, store.Resolve("ITEM--ABC.PNG")!.Path, "wire token aliases are case-insensitive across languages");
        Equal(1, Directory.GetFiles(root, "*.png", SearchOption.AllDirectories).Length, "idempotent publication never duplicates final bytes");
        string second = store.Publish("other.png", AssetOwnerCanonical, "43", "Мой мир / 🌍", "other-id", "Звёздный меч");
        Equal(false, Path.GetDirectoryName(second) == Path.GetDirectoryName(path), "same labels cannot merge different stable identities");
        bool conflict = false;
        try { store.Publish("item--abc.png", AssetOwnerOtherColor, "42", "Мой мир", "stable-id", "Меч"); }
        catch (IOException) { conflict = true; }
        Equal(true, conflict, "different byte identity cannot replace a live alias");
        File.Delete(path); conflict = false;
        try { store.Publish("item--abc.png", AssetOwnerOtherColor, "42", "Мой мир", "stable-id", "Меч"); }
        catch (IOException) { conflict = true; }
        Equal(true, conflict, "missing bytes do not erase historical alias integrity");
        Equal("A Б", SharedImageStore.SafeLabel("  A   Б_ /", "item"), "label normalization matches Python");
    }

    private static void SharedImagesIndexContainment()
    {
        string root = Path.Combine(Terraria.Program.SavePath, "shared-boundary");
        var store = new SharedImageStore(root);
        string file = "boundary.png", canonical = store.Publish(file, AssetOwnerCanonical, "w", "World", "i", "Item");
        string index = ImageIndexPath(root, file), original = File.ReadAllText(index);
        foreach (string target in new[] { "../outside/final/boundary.png", "/tmp/final/boundary.png", "C:/final/boundary.png", "worlds/diagnostics/final/boundary.png", "worlds/Diagnostics/final/boundary.png", "worlds/final/../boundary.png", "worlds\\final\\boundary.png" })
        {
            var json = System.Text.Json.Nodes.JsonNode.Parse(original)!;
            json["path"] = target; File.WriteAllText(index, json.ToJsonString());
            Equal(true, store.Resolve(file) is null, "untrusted index path is refused: " + target);
        }
        File.WriteAllText(index, original);
        string final = Path.GetDirectoryName(canonical)!, moved = final + "-outside";
        Directory.Move(final, moved); Directory.CreateSymbolicLink(final, moved);
        Equal(true, store.Resolve(file) is null, "linked final directory cannot bypass containment");
        Directory.Delete(final); Directory.Move(moved, final);
        File.WriteAllBytes(canonical, new byte[] { 1, 2 });
        Equal(true, store.Resolve(file) is null, "truncated final never resolves");
        Equal(true, store.Resolve("../boundary.png") is null, "wire basename cannot traverse");
    }

    private static void SharedImagesCurrentStoreOnly()
    {
        WithLighting((_, __) => {
            using var sync = new GeneratedAssetSyncService();
            string file = "shared_local_" + Guid.NewGuid().ToString("N") + ".png";
            var data = AssetOwnerData("shared-local", file);
            var store = new SharedImageStore(sync.CacheRoot);
            string canonical = store.Publish(file, AssetOwnerCanonical, data.RecipeMeta.WorldId, Terraria.Main.worldName, data.Id, data.Name);
            sync.EnsureAssetsForData(data);
            Equal(canonical, sync.ResolveCertifiedLocalPath(file)!, "current local generator final is certified in place");
            Equal(0, sync.GetDebugSnapshot().DownloadStartedCount, "current local final needs no HTTP copy");
            string oldRoot = Path.Combine(Terraria.Main.SavePath, "InfiniCrafterLocal", "asset_cache");
            Directory.CreateDirectory(oldRoot);
            string duplicate = Path.Combine(oldRoot, file);
            File.WriteAllBytes(duplicate, AssetOwnerCanonical);
            sync.EnsureAssetsForData(data);
            Equal(true, File.ReadAllBytes(duplicate).SequenceEqual(AssetOwnerCanonical), "retired cache is never adopted or cleaned");
            foreach (string directory in new[] { oldRoot, sync.CacheRoot, Terraria.Program.SavePath })
            {
                string oldFile = "unindexed_" + Guid.NewGuid().ToString("N") + ".png";
                string oldPath = Path.Combine(directory, oldFile);
                File.WriteAllBytes(oldPath, AssetOwnerCanonical);
                var oldData = AssetOwnerData("unindexed-" + oldFile, oldPath);
                Equal(true, sync.ResolveLocalPath(oldPath) is null, "raw or flat file is not an indexed final");
                Equal(0, sync.BuildServerAssetDescriptors(oldData).Length, "unindexed bytes cannot enter a server manifest");
                Equal(true, sync.ResolveCertifiedLocalPath(oldFile) is null, "unindexed bytes receive no certificate");
                Equal(true, File.ReadAllBytes(oldPath).SequenceEqual(AssetOwnerCanonical), "refusal preserves existing bytes");
                Equal(oldPath, oldData.Visual.SpritePath, "refusal never rewrites the definition");
            }
            string index = ImageIndexPath(sync.CacheRoot, file), goodIndex = File.ReadAllText(index);
            File.WriteAllText(index, "{broken");
            sync.ResetWorldDescriptors();
            Equal(true, sync.ResolveLocalPath(file) is null, "broken current index cannot borrow matching historical bytes");
            Equal(0, sync.BuildServerAssetDescriptors(data).Length, "broken index cannot publish a descriptor");
            Equal("{broken", File.ReadAllText(index), "refusal never replaces ownership metadata");
            File.WriteAllText(index, goodIndex);
        });
    }

    private static void SharedImagesPacketTransport()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var sync = new GeneratedAssetSyncService();
            int oldMode = Terraria.Main.netMode;
            try
            {
                Terraria.Main.netMode = 1;
                string file = "received_" + Guid.NewGuid().ToString("N") + ".png", hash = ImageHash(AssetOwnerCanonical);
                var data = AssetOwnerData("shared-packet", file);
                peers.Registry.RegisterLocal(data, persist: false, ensureAssets: false);
                sync.RegisterRemoteAssetDescriptors(data.Id, new[] { new GeneratedAssetWireDescriptor { FileName = file, Length = AssetOwnerCanonical.Length, Sha256 = hash } });
                sync.EnsureAssetsForData(data);
                using var bundle = new MemoryStream();
                using (var writer = new BinaryWriter(bundle, Encoding.UTF8, true))
                { writer.Write((byte)1); writer.Write((byte)1); writer.Write(file); writer.Write(hash); writer.Write(AssetOwnerCanonical.Length); writer.Write(AssetOwnerCanonical); }
                byte[] bytes = bundle.ToArray();
                using var packet = new MemoryStream();
                using (var writer = new BinaryWriter(packet, Encoding.UTF8, true))
                { writer.Write((byte)2); writer.Write(data.Id); writer.Write(ImageHash(bytes)); writer.Write(bytes.Length); writer.Write((ushort)0); writer.Write((ushort)1); writer.Write((ushort)bytes.Length); writer.Write(bytes); }
                packet.Position = 0; sync.HandleAssetChunkPacket(new BinaryReader(packet), 256);
                string canonical = sync.ResolveCertifiedLocalPath(file)!;
                Equal(true, !string.IsNullOrWhiteSpace(canonical) && canonical.Contains("final"), "unchanged v2 packet publishes shared final");
                Equal(true, File.ReadAllBytes(canonical).SequenceEqual(AssetOwnerCanonical), "packet keeps PNG identity");
                Equal(false, File.Exists(Path.Combine(sync.CacheRoot, file)), "packet receiver creates no flat duplicate");
                packet.Position = 0; sync.HandleAssetChunkPacket(new BinaryReader(packet), 256);
                Equal(canonical, sync.ResolveCertifiedLocalPath(file)!, "packet replay keeps same single canonical file");
            }
            finally { Terraria.Main.netMode = oldMode; }
        });
    }
    private static void SharedImagesExternalSourceBoundary()
    {
        var generatorProperty = typeof(InfiniMod).GetProperty("Generator")!;
        object? prior = generatorProperty.GetValue(null);
        int oldMode = Terraria.Main.netMode;
        using var sync = new GeneratedAssetSyncService();
        string path = Path.Combine(Terraria.Program.SavePath, "external-boundary.png");
        File.WriteAllBytes(path, AssetOwnerCanonical);
        var data = AssetOwnerData("external-boundary", path);
        try
        {
            foreach (int mode in new[] { 0, 1, 2 })
            foreach (string endpoint in new[] { "https://generator.example.invalid/combine", "http://127.0.0.1:5055/combine" })
            {
                Terraria.Main.netMode = mode;
                generatorProperty.SetValue(null, new GeneratorClient { Endpoint = endpoint });
                Equal(0, sync.BuildServerAssetDescriptors(data).Length, "neither a local endpoint nor a peer grants raw-path authority");
                Equal(true, sync.ResolveLocalPath(path) is null, "unindexed source never resolves");
            }
            Equal(true, File.ReadAllBytes(path).SequenceEqual(AssetOwnerCanonical), "refused source remains intact");
        }
        finally { generatorProperty.SetValue(null, prior); Terraria.Main.netMode = oldMode; }
    }

    private static async System.Threading.Tasks.Task SharedImagesLateHttpWorldRetirement()
    {
        int originalWorld = Terraria.Main.worldID;
        foreach (bool returnToSameWorld in new[] { false, true })
        foreach (string outcome in new[] { "png", "invalid_png", "http_error" })
        {
            using var sync = new GeneratedAssetSyncService();
            string file = "retired_world_" + Guid.NewGuid().ToString("N") + ".png";
            await using var server = new AssetHeldResponse(file,
                outcome == "png" ? AssetLifetimePng : Encoding.ASCII.GetBytes("not a PNG"), errorStatus: outcome == "http_error");
            System.Threading.Tasks.Task? worker = null;
            int before = Directory.GetFiles(sync.CacheRoot, "*.png", SearchOption.AllDirectories).Length;
            try
            {
                worker = AssetLifetimeDownload(sync, server, file);
                await server.Barrier.Task.WaitAsync(AssetSetupBound);
                Terraria.Main.worldID = originalWorld + 1; sync.ResetWorldDescriptors();
                if (returnToSameWorld) { Terraria.Main.worldID = originalWorld; sync.ResetWorldDescriptors(); }
                await DrainAssetLifetimeWorker(worker, server); await server.CloseAsync();
                Equal(true, sync.ResolveLocalPath(file) is null, "retired HTTP completion cannot borrow current world storage scope");
                Equal(before, Directory.GetFiles(sync.CacheRoot, "*.png", SearchOption.AllDirectories).Length, "world retirement cannot leave an orphan canonical PNG");
                Equal(0, sync.GetDebugSnapshot().KnownMissingCount, "retirement is not a provider failure");
            }
            finally { await DrainAssetLifetimeWorker(worker, server); Terraria.Main.worldID = originalWorld; }
        }
    }

    private static void SharedImagesRejectUncertifiedIndexedBytes()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string file = "integrity_" + Guid.NewGuid().ToString("N") + ".png";
            var data = AssetOwnerData("shared-integrity", file);
            var store = new SharedImageStore(probe.Sync.CacheRoot);
            string path = store.Publish(file, AssetOwnerCanonical, data.RecipeMeta.WorldId, Terraria.Main.worldName, data.Id, data.Name, "item");
            probe.Sync.EnsureAssetsForData(data);
            var item = probe.Item(data.Id, file);
            probe.Draw(item);
            Equal(1, probe.Loads.Count, "healthy indexed bytes enter the real runtime cache once");
            Equal(AssetOwnerCanonical.Length, AssetOwnerOtherColor.Length, "tamper control keeps the byte length");
            File.WriteAllBytes(path, AssetOwnerOtherColor); File.SetLastWriteTimeUtc(path, DateTime.UtcNow.AddMinutes(1));
            probe.Sync.EnsureAssetsForData(data);
            Equal(true, probe.Sync.ResolveCertifiedLocalPath(file) is null, "same-length different PNG loses SHA certificate");
            Equal(true, probe.Cache.TryGet(file) is null, "rejected indexed bytes cannot reuse the old hot texture");
            using var fresh = new RuntimeSpriteCache();
            Equal(true, fresh.TryGet(file) is null, "rejected indexed bytes cannot enter a fresh cache through ResolveLocalPath");
            Equal(1, probe.Loads.Count, "no untrusted decode or GPU boundary is reached");
        });
    }

    private static void SharedImagesWarmReconnectRequestsManifest()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            int oldMode = Terraria.Main.netMode;
            try
            {
                string file = "reconnect_" + Guid.NewGuid().ToString("N") + ".png";
                var data = AssetOwnerData("warm-reconnect", file);
                var store = new SharedImageStore(probe.Sync.CacheRoot);
                string canonical = store.Publish(file, AssetOwnerCanonical, data.RecipeMeta.WorldId, Terraria.Main.worldName, data.Id, data.Name, "item");
                peers.Registry.RegisterLocal(data, persist: false, ensureAssets: false);
                Terraria.Main.netMode = 1;
                probe.Sync.ResetWorldDescriptors();
                ushort KnownCount()
                {
                    using var bytes = new MemoryStream();
                    using (var writer = new BinaryWriter(bytes, Encoding.UTF8, true))
                        typeof(GeneratedItemRegistryService).GetMethod("WriteKnownDefinitionHashes", AssetOwnerInstance)!.Invoke(peers.Registry, new object[] { writer });
                    bytes.Position = 0; using var reader = new BinaryReader(bytes);
                    Equal((byte)1, reader.ReadByte(), "known-hash wire stays v1"); return reader.ReadUInt16();
                }
                Equal(true, probe.Sync.NeedsRemoteDescriptorRefresh(data, false), "valid warm PNG still needs the peer manifest after reconnect");
                Equal((ushort)0, KnownCount(), "initial sync does not suppress the missing authoritative descriptors");
                int requests = 0;
                Action<string, bool> request = (id, retry) => { Equal(data.Id, id, "refresh belongs to the cached item"); requests++; };
                using var hook = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedItemRegistryService).GetMethod("SendSingleHydrationRequest", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!, request);
                var item = ReviewItem(data);
                typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(item, -9999);
                typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetMethod("EnsureRuntimeHydration", AssetOwnerInstance)!.Invoke(item, new object?[] { null });
                Equal(1, requests, "normal cached-item hydration requests a manifest without forcing PNG redownload");
                probe.Sync.RegisterRemoteAssetDescriptors(data.Id, new[] { new GeneratedAssetWireDescriptor { FileName = file, Length = AssetOwnerCanonical.Length, Sha256 = ImageHash(AssetOwnerCanonical) } });
                probe.Sync.EnsureAssetsForData(data);
                Equal(false, probe.Sync.NeedsRemoteDescriptorRefresh(data, false), "received peer manifest closes reconnect work");
                Equal((ushort)1, KnownCount(), "only an authoritative complete cached definition may suppress retransmission");
                Equal(canonical, probe.Sync.ResolveCertifiedLocalPath(file)!, "existing PNG is certified in place after re-admission");
                Equal(0, probe.Sync.GetDebugSnapshot().DownloadStartedCount, "warm reconnect fetches no duplicate PNG");
                probe.Draw(item);
                Equal(1, probe.Loads.Count, "reconnected item reaches the real render consumer");
            }
            finally { Terraria.Main.netMode = oldMode; }
        });
    }

}
