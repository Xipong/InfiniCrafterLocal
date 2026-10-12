using System;
using System.Collections;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static void AssetLifecycleSpriteOwnershipDiagnostics()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string path = Path.Combine(Terraria.Program.SavePath, "ownership.png"); File.WriteAllBytes(path, AssetOwnerCanonical);
            var item = probe.Item("lifecycle_ownership", path); probe.Draw(item); probe.Cache.Clear();
            var snapshot = probe.Cache.GetDebugSnapshot();
            long Value(string name) {
                var property = snapshot.GetType().GetProperty(name);
                Equal(true, property is not null, "diagnostic field exists: " + name);
                return Convert.ToInt64(property!.GetValue(snapshot));
            }
            Equal(0, snapshot.TextureCount, "Clear removes resident lookup immediately");
            Equal(0L, snapshot.EstimatedTextureBytes, "retained resident estimate keeps existing meaning");
            Equal(1L, Value("PendingRetirementCount"), "pending owner remains visible before legal drain");
            Equal(1L, Value("OwnedTextureCount"), "owned means resident plus deferred");
            Equal(4096L, Value("EstimatedOwnedTextureBytes"), "32x32 RGBA CPU shell remains owned");
            Equal(0L, Value("CapacityRefusalCount"), "ordinary load and Clear are not capacity refusals");
            probe.Batch.End(); probe.DrainOwnerQueue(); snapshot = probe.Cache.GetDebugSnapshot();
            Equal(0L, Value("OwnedTextureCount"), "legal owner callback releases ownership");
            Equal(0L, Value("EstimatedOwnedTextureBytes"), "post-drain owned estimate is zero");
            probe.Batch.Begin();
            for (int i = 0; i < snapshot.MaxCachedTextures * 2; i++) { probe.Draw(item); probe.Cache.Invalidate(path); }
            long beforeMiss = probe.Cache.GetDebugSnapshot().MissCount;
            Equal(true, probe.Cache.TryGet(path) is null, "withheld retirement saturates actual admission boundary");
            snapshot = probe.Cache.GetDebugSnapshot();
            Equal(1L, Value("CapacityRefusalCount"), "one actual capacity refusal is counted");
            Equal(beforeMiss + 1, snapshot.MissCount, "existing miss counter still counts refusal");
            Equal(0, snapshot.MissingOrBadCount, "pressure is not bad-file backoff");
            Equal((long)snapshot.MaxCachedTextures * 2, Value("OwnedTextureCount"), "snapshot includes all pending resources at capacity");
        });
    }

    private static byte[] AssetLifecycleDefinitionPacket(GeneratedItemData data, string? hashOverride = null)
    {
        byte[] raw = Encoding.UTF8.GetBytes(data.ToNetworkJson());
        using var compressed = new MemoryStream();
        using (var deflate = new DeflateStream(compressed, CompressionLevel.Fastest, true)) deflate.Write(raw);
        byte[] packed = compressed.ToArray(); using var wire = new MemoryStream();
        using (var writer = new BinaryWriter(wire, Encoding.UTF8, true)) {
            writer.Write(GeneratedItemRegistryService.PacketNotifyGeneratedItem); writer.Write((byte)1);
            writer.Write(data.Id); writer.Write(hashOverride ?? Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant());
            writer.Write(raw.Length); writer.Write(packed.Length); writer.Write((ushort)0); writer.Write((ushort)1);
            writer.Write((byte)1); writer.Write("valid.png"); writer.Write(AssetOwnerCanonical.Length);
            writer.Write(Convert.ToHexString(SHA256.HashData(AssetOwnerCanonical)).ToLowerInvariant());
            writer.Write((ushort)packed.Length); writer.Write(packed);
        }
        return wire.ToArray();
    }

    private static void AssetLifecycleMalformedDefinitionPackets()
    {
        int oldMode = Terraria.Main.netMode; var property = typeof(InfiniMod).GetProperty("GeneratedItems")!;
        object? oldRegistry = property.GetValue(null);
        try {
            Terraria.Main.netMode = 1; using var registry = new GeneratedItemRegistryService(); property.SetValue(null, registry);
            var data = AssetOwnerData("lifecycle_valid_packet", "valid.png");
            byte[] valid = AssetLifecycleDefinitionPacket(data);
            var mod = new InfiniMod();
            foreach (int length in Enumerable.Range(1, valid.Length - 1)) {
                mod.HandlePacket(new BinaryReader(new MemoryStream(valid.Take(length).ToArray())), 256);
                Equal(false, registry.TryGet(data.Id, out _), "every truncated header/descriptor/chunk refuses before definition mutation; length=" + length);
            }
            registry.HandlePacket(GeneratedItemRegistryService.PacketNotifyGeneratedItem, new BinaryReader(new MemoryStream()), 256);
            mod.HandlePacket(new BinaryReader(new MemoryStream(new[] { GeneratedItemRegistryService.PacketNotifyGeneratedItem, (byte)2 })), 256);
            byte[] hugeString = { GeneratedItemRegistryService.PacketNotifyGeneratedItem, 1, 255, 255, 255, 255, 7 };
            mod.HandlePacket(new BinaryReader(new MemoryStream(hugeString)), 256);
            mod.HandlePacket(new BinaryReader(new MemoryStream(AssetLifecycleDefinitionPacket(data, new string('0', 64)))), 256);
            Equal(false, registry.TryGet(data.Id, out _), "wrong compressed definition SHA refuses");
            using var sync = new GeneratedAssetSyncService();
            sync.HandleAssetChunkPacket(new BinaryReader(new MemoryStream()), 256);
            mod.HandlePacket(new BinaryReader(new MemoryStream(valid)), 256);
            Equal(true, registry.TryGet(data.Id, out _), "actual root router accepts healthy compressed SHA definition");
        } finally { property.SetValue(null, oldRegistry); Terraria.Main.netMode = oldMode; }
    }

    private static void AssetLifecycleServerDescriptorReplacement()
    {
        using var sync = new GeneratedAssetSyncService(); using var registry = new GeneratedItemRegistryService();
        string dir = Path.Combine(Terraria.Program.SavePath, "descriptor-replace"); Directory.CreateDirectory(dir);
        string aPath = Path.Combine(dir, "a.png"), bPath = Path.Combine(dir, "b.png");
        File.WriteAllBytes(aPath, AssetOwnerCanonical); File.WriteAllBytes(bPath, AssetOwnerOtherColor);
        var a = AssetOwnerData("lifecycle_refresh", aPath); registry.RegisterLocal(a, false, false);
        Equal("a.png", sync.BuildServerAssetDescriptors(a).Single().FileName, "initial descriptor");
        var b = AssetOwnerData(a.Id, bPath); registry.RegisterLocal(b, false, false);
        Equal("b.png", sync.BuildServerAssetDescriptors(b).Single().FileName, "same-ID replacement rebinds exact filename, not cardinality");
        Equal(true, sync.HasCompleteServerAssetRoster(b), "replacement roster exactly complete");
        string sameName = Path.Combine(dir, "other", "b.png"); Directory.CreateDirectory(Path.GetDirectoryName(sameName)!); File.WriteAllBytes(sameName, AssetOwnerCanonical);
        var moved = AssetOwnerData(a.Id, sameName);
        Equal(Convert.ToHexString(SHA256.HashData(AssetOwnerCanonical)).ToLowerInvariant(), sync.BuildServerAssetDescriptors(moved).Single().Sha256,
            "same filename with changed declared path rebinds source");
        File.WriteAllBytes(sameName, AssetOwnerOtherColor); File.SetLastWriteTimeUtc(sameName, DateTime.UtcNow.AddMinutes(1));
        Equal(Convert.ToHexString(SHA256.HashData(AssetOwnerOtherColor)).ToLowerInvariant(), sync.BuildServerAssetDescriptors(moved).Single().Sha256,
            "changed source stat rebinds descriptor hash");
        File.Delete(sameName); Equal(false, sync.HasCompleteServerAssetRoster(moved), "stale descriptor cannot certify missing source");
        int oldWorld = Terraria.Main.worldID;
        try {
            Terraria.Main.worldID = 42999;
            var otherWorld = AssetOwnerData(a.Id, bPath);
            Equal("b.png", sync.BuildServerAssetDescriptors(otherWorld).Single().FileName, "same service uses other world definition identity");
            Equal(0, sync.BuildServerAssetDescriptors(a).Length, "foreign definition cannot access same-ID server descriptor");
        } finally { Terraria.Main.worldID = oldWorld; }
        Equal("a.png", sync.BuildServerAssetDescriptors(a).Single().FileName, "returning world does not borrow other world's roster");
    }

    private static void AssetLifecycleCertifiedHydrationCoalesces()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            uint oldTick = Terraria.Main.GameUpdateCount;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            string file = "lifecycle_hot.png", path = Path.Combine(probe.Sync.CacheRoot, file);
            File.WriteAllBytes(path, AssetOwnerCanonical);
            var data = AssetOwnerData("lifecycle_hot", path); peers.Registry.RegisterLocal(data, false, false);
            var descriptors = probe.Sync.BuildServerAssetDescriptors(data);
            probe.Sync.RegisterRemoteAssetDescriptors(data.Id, descriptors); probe.Sync.EnsureAssetsForData(data);
            Equal(path, probe.Sync.ResolveCertifiedLocalPath(path)!, "fixture is lifecycle-certified before inventory calls");
            int reads = 0;
            using var hook = new MonoMod.RuntimeDetour.ILHook(typeof(GeneratedAssetSyncService).GetMethod("IsValidCachedAsset", BindingFlags.Static | BindingFlags.NonPublic)!, il => {
                var sites = il.Body.Instructions.Where(i => i.OpCode == Mono.Cecil.Cil.OpCodes.Call && i.Operand is Mono.Cecil.MethodReference m
                    && m.DeclaringType.FullName == typeof(File).FullName && m.Name == "ReadAllBytes").ToArray();
                Equal(1, sites.Length, "one actual PNG body read site");
                var c = new MonoMod.Cil.ILCursor(il); c.Goto(sites[0]); c.EmitDelegate<Func<string,string>>(p => { reads++; return p; });
            });
            try {
                var items = Enumerable.Range(0, 60).Select(_ => ReviewItem(data)).ToArray();
                foreach (uint tick in new uint[] { 100, 101, 190 }) {
                    clock.SetValue(null, tick); reads = 0;
                    foreach (var item in items) probe.Draw(item);
                    Console.WriteLine($"DETAIL: certified inventory instances=60 tick={tick} PNG body reads={reads}");
                    Equal(0, reads, "unchanged certified proof/stat avoids per-instance PNG reads");
                }
                Equal(1L, probe.Cache.GetDebugSnapshot().LoadSuccessCount, "one successful CPU texture admission");
                Equal(179L, probe.Cache.GetDebugSnapshot().HitCount, "179 actual hot cache consumers");
                probe.Sync.EnsureAssetsForData(data, true); Equal(1, reads, "explicit force retry revalidates body");
                File.WriteAllBytes(path, AssetOwnerOtherColor); File.SetLastWriteTimeUtc(path, DateTime.UtcNow.AddMinutes(1));
                probe.Sync.EnsureAssetsForData(data); Equal(2, reads, "changed file stat rechecks body even inside cadence");
                Equal(true, probe.Sync.ResolveCertifiedLocalPath(path) is null, "different hash cannot retain old proof");
                probe.Sync.RegisterRemoteAssetDescriptors(data.Id, new[] { new GeneratedAssetWireDescriptor { FileName = file,
                    Length = AssetOwnerOtherColor.Length, Sha256 = Convert.ToHexString(SHA256.HashData(AssetOwnerOtherColor)).ToLowerInvariant() } });
                probe.Sync.EnsureAssetsForData(data); Equal(3, reads, "changed descriptor revalidates changed identity");
                Equal(path, probe.Sync.ResolveCertifiedLocalPath(path)!, "new admitted descriptor gets its own proof");
                // Change the source inside the actual read boundary, not between calls.
                using (var race = new MonoMod.RuntimeDetour.ILHook(typeof(GeneratedAssetSyncService).GetMethod("IsValidCachedAsset", BindingFlags.Static | BindingFlags.NonPublic)!, il => {
                    var site = il.Body.Instructions.Single(i => i.OpCode == Mono.Cecil.Cil.OpCodes.Call && i.Operand is Mono.Cecil.MethodReference m
                        && m.DeclaringType.FullName == typeof(File).FullName && m.Name == "ReadAllBytes");
                    var c = new MonoMod.Cil.ILCursor(il); c.Goto(site); c.EmitDelegate<Func<string,string>>(p => {
                        File.SetLastWriteTimeUtc(p, DateTime.UtcNow.AddMinutes(2)); return p;
                    });
                })) probe.Sync.EnsureAssetsForData(data, true);
                Equal(true, probe.Sync.ResolveCertifiedLocalPath(path) is null, "stat-changing validation race cannot publish proof");
                // Existing world lifecycle revokes descriptor/cache proofs without moving files.
                peers.Registry.ReloadLocalCacheForCurrentWorld();
                probe.Sync.EnsureAssetsForData(data);
                Equal(true, probe.Sync.ResolveCertifiedLocalPath(path) is null, "world reload cannot inherit previous descriptor proof");
            } finally { clock.SetValue(null, oldTick); }
        });
    }

    private static void AssetLifecycleWorldScopedPersistence()
    {
        int oldWorld = Terraria.Main.worldID;
        try {
            Terraria.Main.worldID = 42101;
            using var registry = new GeneratedItemRegistryService();
            var a = AssetOwnerData("lifecycle_disk_collision", "a.png"); a.Gameplay.Damage = 31;
            registry.RegisterLocal(a, true, false); registry.ReloadLocalCacheForCurrentWorld();
            Equal(31, registry.TryGet(a.Id, out var initial) ? initial.Gameplay.Damage : -1, "world A roundtrip");
            Terraria.Main.worldID = 42102; registry.ReloadLocalCacheForCurrentWorld();
            var b = AssetOwnerData(a.Id, "b.png"); b.Gameplay.Damage = 77;
            registry.RegisterLocal(b, true, false); registry.ReloadLocalCacheForCurrentWorld();
            Equal(77, registry.TryGet(b.Id, out var second) ? second.Gameplay.Damage : -1, "world B roundtrip");
            Terraria.Main.worldID = 42101; registry.ReloadLocalCacheForCurrentWorld();
            Equal(31, registry.TryGet(a.Id, out var returned) ? returned.Gameplay.Damage : -1, "world A survives shared ID in world B");
            var historical = AssetOwnerData("lifecycle_historical", "history.png"); historical.Gameplay.Damage = 19;
            string path = Path.Combine(registry.StoreRoot, historical.Id + ".json"); File.WriteAllText(path, historical.ToLocalCacheJson());
            string before = File.ReadAllText(path);
            registry.ReloadLocalCacheForCurrentWorld();
            Equal(19, registry.TryGet(historical.Id, out var legacy) ? legacy.Gameplay.Damage : -1, "valid same-world historical file remains readable");
            historical.Gameplay.Damage = 23; registry.RegisterLocal(historical, true, false);
            registry.ReloadLocalCacheForCurrentWorld();
            Equal(23, registry.TryGet(historical.Id, out var latest) ? latest.Gameplay.Damage : -1, "scoped record wins over historical same-world record");
            Equal(before, File.ReadAllText(path), "historical file is never migrated or rewritten");
            Terraria.Main.worldID = 42102; registry.ReloadLocalCacheForCurrentWorld();
            Equal(false, registry.TryGet(historical.Id, out _), "foreign historical ownership cannot be fallback");
            string prefix = new string('a', 63);
            var firstLong = AssetOwnerData(prefix + "x", "first.png"); firstLong.Gameplay.Damage = 41;
            var secondLong = AssetOwnerData(prefix + "y", "second.png"); secondLong.Gameplay.Damage = 42;
            registry.RegisterLocal(firstLong, true, false); registry.RegisterLocal(secondLong, true, false);
            registry.ReloadLocalCacheForCurrentWorld();
            Equal(41, registry.TryGet(firstLong.Id, out var firstExact) ? firstExact.Gameplay.Damage : -1, "bounded storage key preserves maximum-length canonical ID");
            Equal(42, registry.TryGet(secondLong.Id, out var secondExact) ? secondExact.Gameplay.Damage : -1, "second exact long ID persists independently");
        } finally { Terraria.Main.worldID = oldWorld; }
    }

    private static void AssetLifecycleReferenceWorldFence()
    {
        int oldWorld = Terraria.Main.worldID, oldMode = Terraria.Main.netMode;
        var property = typeof(InfiniMod).GetProperty("GeneratedItems")!;
        object? oldRegistry = property.GetValue(null);
        try {
            Terraria.Main.worldID = 42001; Terraria.Main.netMode = 0;
            using var registry = new GeneratedItemRegistryService(); property.SetValue(null, registry);
            var data = AssetOwnerData("lifecycle_world_collision", "world.png");
            data.Gameplay.Damage = 47; data.Normalize(); registry.RegisterLocal(data, false, false);
            foreach (string world in new[] { "42001", "42002", "", "0" }) {
                var reference = GeneratedItemData.FromPlayerSaveJson(data.ToPlayerSaveJson())!;
                reference.RecipeMeta.WorldId = world;
                var item = ReviewItem(GeneratedItemData.Placeholder());
                item.LoadData(new Terraria.ModLoader.IO.TagCompound { { "infiniJson", reference.ToPlayerSaveJson() } });
                typeof(GeneratedItem).GetMethod("EnsureRuntimeHydration", AssetOwnerInstance)!.Invoke(item, new object?[] { null });
                Equal(world, item.Data.RecipeMeta.WorldId, "LoadData hydration preserves incoming world=" + world);
                Equal(world == "42001" ? 47 : 0, item.Item.damage, "foreign reference cannot borrow native gameplay");
                var presented = (GeneratedItemData)typeof(GeneratedItem).GetMethod("PresentationData", AssetOwnerInstance)!.Invoke(item, null)!;
                Equal(world, presented.RecipeMeta.WorldId, "presentation cannot substitute another world's ID");
                using var stream = new MemoryStream();
                using (var writer = new BinaryWriter(stream, Encoding.UTF8, true)) { writer.Write(7); writer.Write(reference.ToPlayerSaveJson()); writer.Write(0); }
                stream.Position = 0; var network = ReviewItem(GeneratedItemData.Placeholder()); network.NetReceive(new BinaryReader(stream));
                Equal(world, network.Data.RecipeMeta.WorldId, "NetReceive preserves incoming world=" + world);
                Equal(world == "42001" ? 47 : 0, network.Item.damage, "network gameplay follows world fence");
                if (world != "42001") {
                    Terraria.Main.netMode = 1;
                    typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(item, -9999);
                    typeof(GeneratedItem).GetMethod("EnsureRuntimeHydration", AssetOwnerInstance)!.Invoke(item, new object?[] { null });
                    Equal(0, registry.GetHydrationDebugSnapshot().HydrationRequestSentCount, "foreign/absent reference never sends ID-only request");
                    Terraria.Main.netMode = 0;
                }
            }
            // Zero is a literal world identity, not a generic absent/invalid sentinel.
            Terraria.Main.worldID = 0; registry.ReloadLocalCacheForCurrentWorld();
            GeneratedItemRegistryService.StampCurrentWorld(data); registry.RegisterLocal(data, false, false);
            var zero = ReviewItem(GeneratedItemData.Placeholder());
            zero.LoadData(new Terraria.ModLoader.IO.TagCompound { { "infiniJson", data.ToPlayerSaveJson() } });
            typeof(GeneratedItem).GetMethod("EnsureRuntimeHydration", AssetOwnerInstance)!.Invoke(zero, new object?[] { null });
            Equal(47, zero.Item.damage, "literal world zero remains valid when current");
        } finally { property.SetValue(null, oldRegistry); Terraria.Main.worldID = oldWorld; Terraria.Main.netMode = oldMode; }
    }
}
