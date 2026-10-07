#nullable enable
using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using Terraria.ID;
using Terraria.ModLoader.IO;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    // Uses only baseline methods/types. The unchanged ReviewPeers intercepts socket
    // Send, not preparation/serialization/admission/hash/hydration. No direct _byId
    // insertion is used for positive controls; clearing it only resets a peer cache.
    private sealed class Pb02HostMetadata : IDisposable
    {
        internal readonly PropertyInfo GeneratorProperty = typeof(InfiniMod).GetProperty("Generator")!;
        internal readonly PropertyInfo AssetProperty = typeof(InfiniMod).GetProperty("AssetSync")!;
        private readonly object? previousGenerator, previousAssets;
        private readonly string? previousUrl = Environment.GetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL");
        internal const string PublicUrl = "http://192.0.2.42:5055";
        internal Pb02HostMetadata(string? transport)
        {
            previousGenerator = GeneratorProperty.GetValue(null);
            previousAssets = AssetProperty.GetValue(null);
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", null);
            AssetProperty.SetValue(null, null);
            if (transport is null) GeneratorProperty.SetValue(null, null);
            else
            {
                var generator = new GeneratorClient { Endpoint = "http://192.0.2.42:5055/combine" };
                typeof(GeneratorClient).GetField("_cachedGeneratorAssetTransport", PersistenceInstance)!.SetValue(generator, transport);
                typeof(GeneratorClient).GetField("_cachedGeneratorAssetPublicBaseUrl", PersistenceInstance)!.SetValue(generator, PublicUrl);
                // Cache contents stand for a completed host metadata probe. The real
                // StampAssetTransportMetadata runs; no discovery HTTP is issued.
                typeof(GeneratorClient).GetField("_nextGeneratorAssetPublicBaseUrlProbeUtc", PersistenceInstance)!.SetValue(generator, DateTime.MaxValue);
                GeneratorProperty.SetValue(null, generator);
            }
        }
        public void Dispose()
        {
            GeneratorProperty.SetValue(null, previousGenerator);
            AssetProperty.SetValue(null, previousAssets);
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", previousUrl);
        }
    }

    private static GeneratedItemData Pb02Data(string id, string transport)
    {
        var data = PlacedLedgerData(id);
        data.RecipeMeta.AssetTransport = transport;
        data.RecipeMeta.AssetBaseUrl = transport == "http" ? "http://192.0.2.17:5055" : "";
        data.RecipeMeta.AssetFiles = new[] { "stale_host_roster.png" };
        // Normalize once before observing caller immutability, not inside a test hash.
        data.Normalize();
        return data;
    }

    private static GeneratedItemData Pb02Prepare(GeneratedItemData data, bool force = true)
        => (GeneratedItemData)typeof(GeneratedItemRegistryService).GetMethod("PrepareForNetworkSync", PersistenceStatic)!
            .Invoke(null, new object[] { data, force })!;

    private static void Pb02PreparationHttpToNative() => Pb02Preparation("http", "native");
    private static void Pb02PreparationNativeToHttp() => Pb02Preparation("native", "http");
    private static void Pb02PreparationHttpWithoutGenerator() => Pb02Preparation("http", null);

    private static void Pb02Preparation(string from, string? hostTransport)
    {
        WithPlacedLedger((_, __) => {
            using var peers = new ReviewPeers();
            using var metadata = new Pb02HostMetadata(hostTransport);
            peers.Mode(NetmodeID.Server, 255);
            var source = Pb02Data("pb02-prepare-" + from + "-" + (hostTransport ?? "no-generator"), from);
            string before = source.ToJson(), identity = GeneratedItemRegistryService.DefinitionIdentity(source);
            var unforced = Pb02Prepare(source, force: false);
            Equal(from, unforced.RecipeMeta.AssetTransport, "unforced preparation retains accepted routing metadata");
            var outgoing = Pb02Prepare(source);
            string expectedTransport = hostTransport ?? "native";
            Equal(expectedTransport, outgoing.RecipeMeta.AssetTransport, "production host preparation actually changes transport direction");
            Equal(expectedTransport == "http" ? Pb02HostMetadata.PublicUrl : "", outgoing.RecipeMeta.AssetBaseUrl, "production stamp uses the current host URL/mode");
            Equal(string.Join(",", GeneratedAssetSyncService.AssetFilesFromData(source)), string.Join(",", outgoing.RecipeMeta.AssetFiles), "production stamp reconstructs the asset roster");
            Equal(false, ReferenceEquals(source, outgoing), "real preparation clones the definition");
            Equal(before, source.ToJson(), "host preparation/hash cannot rewrite accepted caller metadata or authored definition");
            var accepted = JsonNode.Parse(source.ToNetworkJson())!;
            var prepared = JsonNode.Parse(outgoing.ToNetworkJson())!;
            foreach (string field in new[] { "id", "recipeKey", "sourceMode", "name", "parentA", "parentB", "canonical", "gameplay", "runtimeProgram", "visual", "vfxManifest" })
                Equal(accepted[field]!.ToJsonString(), prepared[field]!.ToJsonString(), "host transport preserves authored network field " + field);
            Equal(source.RecipeMeta.WorldId, outgoing.RecipeMeta.WorldId, "world identity is not transport metadata");
            Equal(source.RecipeMeta.WorldScoped, outgoing.RecipeMeta.WorldScoped, "world-scoped authority remains exact");
            Equal(identity, GeneratedItemRegistryService.DefinitionIdentity(outgoing), "PB-02 actual PrepareForNetworkSync must preserve canonical definition identity");
        });
    }

    private static byte[][] Pb02DefinitionPackets(ReviewPeers peers, GeneratedAssetSyncService sync, GeneratedItemData source)
    {
        peers.Mode(NetmodeID.Server, 255); peers.Sent.Clear();
        // Exercise the real producer, including its PrepareForNetworkSync and raw
        // transport SHA/Deflate/chunk/descriptors. Do not manufacture Notify bytes.
        typeof(GeneratedItemRegistryService).GetMethod("EnqueueDefinitionForClient", PersistenceInstance)!
            .Invoke(peers.Registry, new object[] { source, 0, true });
        for (int i = 0; i < 512; i++) sync.UpdateTransfers();
        byte[][] packets = peers.Sent.Where(p => p[0] == InfiniNetPacketIds.NotifyGeneratedItem).ToArray();
        Equal(true, packets.Length > 0, "real registry producer emits bounded definition chunks");
        return packets;
    }

    private static byte[] Pb02WrongTransportHash(byte[] packet)
    {
        byte[] changed = (byte[])packet.Clone();
        using var reader = new BinaryReader(new MemoryStream(changed));
        reader.ReadByte(); reader.ReadByte(); reader.ReadString();
        string hash = reader.ReadString();
        Equal(64, hash.Length, "real producer raw transport SHA is separate from gameplay identity");
        int offset = checked((int)reader.BaseStream.Position - hash.Length);
        changed[offset] = changed[offset] == (byte)'0' ? (byte)'1' : (byte)'0';
        return changed;
    }

    private static void Pb02LateHydrationHttpToNative() => Pb02LateHydration("http", "native");
    private static void Pb02LateHydrationNativeToHttp() => Pb02LateHydration("native", "http");

    private static void Pb02LateHydration(string from, string to)
    {
        WithPlacedLedger((player, ledger) => {
            using var peers = new ReviewPeers();
            using var metadata = new Pb02HostMetadata(to);
            using var serverAssets = new GeneratedAssetSyncService();
            using var clientAssets = new GeneratedAssetSyncService();
            var source = Pb02Data("pb02-late-" + from + "-" + to, from);
            string file = "pb02_" + Guid.NewGuid().ToString("N") + ".png";
            string path = Path.Combine(Terraria.Program.SavePath, file);
            File.WriteAllBytes(path, AssetLifetimePng);
            try
            {
                source.Visual.SpritePath = path; source.Visual.SpriteStatus = "generated";
                source.Normalize(); string sourceBefore = source.ToJson();
                peers.Mode(NetmodeID.SinglePlayer, 0); Terraria.Main.player[0] = player;
                var placement = source.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
                var cell = Terraria.Main.tile[40,40]; cell.HasTile = false;
                Equal(true, GeneratedPlacementLedgerSystem.AuthorizePlacement(player, source, placement, 40,40), "actual opt-in placement captures pre-restamp identity");
                cell.HasTile = true; cell.TileType = TileID.Stone;
                Equal(true, GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player), "actual material commit captures a real placed witness");
                var saved = PlacedLedgerSaved(ledger);
                var row = saved.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Single();
                string witnessHash = row.GetCompound("placedBody").GetString("definitionHash");
                Equal(GeneratedItemRegistryService.DefinitionIdentity(source), witnessHash, "saved witness uses the canonical owner, not a hand-constructed hash");
                string rawWitness = PersistenceRawBytes(row.GetCompound("placedBody"));
                ledger.LoadWorldData(PersistenceNbtRoundtrip(saved));
                Equal(rawWitness, PersistenceRawBytes(PlacedLedgerGroups(ledger).Single().GetCompound("placedBody")), "native NBT reload keeps the captured witness literal");
                byte[] snapshot = PlacedLedgerSnapshot(ledger);
                var outgoing = Pb02Prepare(source);
                Equal(to, outgoing.RecipeMeta.AssetTransport, "real late-definition preparation uses opposite host transport");
                metadata.AssetProperty.SetValue(null, serverAssets);
                var descriptor = serverAssets.BuildServerAssetDescriptors(source).Single();
                byte[][] packets = Pb02DefinitionPackets(peers, serverAssets, source);
                var foreign = GeneratedItemData.FromJson(source.ToNetworkJson())!;
                foreign.RecipeMeta.WorldId = "pb02_foreign_world";
                byte[][] foreignPackets = Pb02DefinitionPackets(peers, serverAssets, foreign);
                var gameplayConflict = GeneratedItemData.FromJson(source.ToNetworkJson())!;
                gameplayConflict.Gameplay.Damage += 1;
                var transformConflict = GeneratedItemData.FromJson(source.ToNetworkJson())!;
                Pb02ShiftTransform(transformConflict);
                byte[][][] contentConflictPackets = new[] {
                    Pb02DefinitionPackets(peers, serverAssets, gameplayConflict),
                    Pb02DefinitionPackets(peers, serverAssets, transformConflict),
                };
                ledger.ClearWorld(); PlacedLedgerRegistryRows(peers).Clear();
                foreach (byte[] packet in packets) peers.Receive(packet);
                Equal(false, peers.Registry.TryGet(source.Id, out _), "server cannot accept incoming client-authored definition chunks");
                peers.Mode(NetmodeID.MultiplayerClient, 0);
                // CPU admission only: keep actual descriptor registration, prevent
                // asset download workers and graphics initialization in this observer.
                Terraria.Main.dedServ = true;
                metadata.AssetProperty.SetValue(null, clientAssets);
                PlacedLedgerReceiveSnapshot(ledger, snapshot);
                MaterialClock(200); ledger.PostUpdateEverything();
                Equal(0, PlacedLedgerGroups(ledger).Single().GetString("definitionJson").Length, "snapshot waits for an actual late registry definition");
                foreach (byte[] packet in packets) peers.Receive(Pb02WrongTransportHash(packet));
                Equal(false, peers.Registry.TryGet(source.Id, out _), "canonical equivalence never disables raw transport SHA verification");
                foreach (byte[] packet in foreignPackets) peers.Receive(packet);
                Equal(false, peers.Registry.TryGet(source.Id, out _), "foreign source-world bytes do not enter the registry");
                int tick = 201;
                foreach (byte[][] conflictPackets in contentConflictPackets)
                {
                    foreach (byte[] packet in conflictPackets) peers.Receive(packet);
                    Equal(true, peers.Registry.TryGet(source.Id, out var conflict), "actual same-ID content mutation arrives via registry admission");
                    Equal(false, witnessHash == GeneratedItemRegistryService.DefinitionIdentity(conflict), "real gameplay/transform mutation remains a different definition");
                    MaterialClock((ulong)tick++); ledger.PostUpdateEverything();
                    Equal(0, PlacedLedgerGroups(ledger).Single().GetString("definitionJson").Length, "late hydration refuses same-ID gameplay/transform hash conflict");
                    Equal(rawWitness, PersistenceRawBytes(PlacedLedgerGroups(ledger).Single().GetCompound("placedBody")), "refused conflict cannot weaken the saved witness");
                }
                foreach (byte[] packet in packets) peers.Receive(packet);
                Equal(true, peers.Registry.TryGet(source.Id, out var received), "actual verified late Notify chunks enter RegisterLocal through production admission");
                Equal(outgoing.ToNetworkJson(), received.ToNetworkJson(), "registry receives the production prepared definition, not a fixture insertion");
                var remoteDescriptor = (GeneratedAssetWireDescriptor)typeof(GeneratedAssetSyncService)
                    .GetMethod("TryGetRemoteDescriptor", PersistenceInstance)!.Invoke(clientAssets, new object[] { source.Id, file })!;
                Equal(descriptor.Length, remoteDescriptor.Length, "existing asset descriptor retains exact certified length");
                Equal(descriptor.Sha256, remoteDescriptor.Sha256, "existing asset descriptor retains exact PNG SHA");
                CommitAssetOwner(clientAssets, source.Id, file, AssetLifetimePng);
                Equal(Path.Combine(clientAssets.CacheRoot, file), clientAssets.ResolveCertifiedLocalPath(file)!, "unchanged byte owner certifies exact PNG after transport restamp");
                MaterialClock((ulong)tick); ledger.PostUpdateEverything();
                var hydrated = PlacedLedgerGroups(ledger).Single();
                // On the baseline this is the PB-02 RED: received mode is correct,
                // but its identity misses the saved pre-restamp witness.
                Equal(received.ToNetworkJson(), hydrated.GetString("definitionJson"), "PB-02 actual late-definition hydration accepts equivalent host transport");
                Equal(witnessHash, GeneratedItemRegistryService.DefinitionIdentity(received), "accepted hydration is still exact canonical identity matching");
                Equal(rawWitness, PersistenceRawBytes(hydrated.GetCompound("placedBody")), "hydration cannot rewrite or migrate the placed witness");
                Equal(sourceBefore, source.ToJson(), "registry publication/preparation preserves accepted source bytes");
            }
            finally
            {
                File.Delete(path); File.Delete(Path.Combine(clientAssets.CacheRoot, file));
                File.Delete(Path.Combine(clientAssets.CacheRoot, file) + ".part");
            }
        });
    }

    private static void Pb02ShiftTransform(GeneratedItemData data)
    {
        var placement=data.RuntimeProgram.Bindings[0].UsePolicy.Action.Placement!;
        var body=placement.PlacedBody!;
        placement.PlacedBody=new RuntimePlacedBodySpec { RenderSizePx=body.RenderSizePx,
            FootprintAnchorX=body.FootprintAnchorX,FootprintAnchorY=body.FootprintAnchorY,
            ImagePivotX=body.ImagePivotX,ImagePivotY=body.ImagePivotY,
            OffsetXPx=body.OffsetXPx+1,OffsetYPx=body.OffsetYPx,
            RotationDegrees=body.RotationDegrees,FlipX=body.FlipX,FlipY=body.FlipY };
    }

    private static void Pb02IdentityRetainsAuthoredDifferences()
    {
        WithPlacedLedger((_, __) => {
            using var peers = new ReviewPeers(); using var metadata = new Pb02HostMetadata("native");
            var source = Pb02Data("pb02-authored-fences", "http");
            string sourcePng=Path.Combine(Terraria.Program.SavePath,"pb02_source_png_"+Guid.NewGuid().ToString("N")+".png");
            string alternatePng=Path.Combine(Terraria.Program.SavePath,"pb02_authored_png_"+Guid.NewGuid().ToString("N")+".png");
            File.WriteAllBytes(sourcePng,AssetLifetimePng); File.WriteAllBytes(alternatePng,AssetLifetimePng);
            source.Visual.SpritePath=sourcePng;source.Visual.SpriteStatus="generated";
            string identity = GeneratedItemRegistryService.DefinitionIdentity(source);
            try {
            (string Name, Action<GeneratedItemData> Mutate)[] mutations = {
                ("gameplay", d => d.Gameplay.Damage += 1),
                ("placed transform", Pb02ShiftTransform),
                ("item identity", d => d.Id = "pb02-other-id"),
                ("recipe identity", d => d.RecipeKey = "pb02-other-recipe"),
                ("source identity", d => d.SourceMode = "generated"),
                ("source world", d => d.RecipeMeta.WorldId = "pb02_other_world"),
                ("world scope", d => d.RecipeMeta.WorldScoped = false),
                ("Visual", d => d.Visual.WorldScale = 1.25f),
                ("VFX", d => d.VfxManifest.Seed += 1),
                ("PNG identity", d => { d.Visual.SpritePath = alternatePng; d.Visual.SpriteStatus = "generated"; }),
            };
            foreach (var mutation in mutations)
            {
                var changed = GeneratedItemData.FromJson(source.ToNetworkJson())!;
                mutation.Mutate(changed);
                Equal(false, identity == GeneratedItemRegistryService.DefinitionIdentity(changed), "real canonical identity still differs for " + mutation.Name);
                Equal(false, identity == GeneratedItemRegistryService.DefinitionIdentity(Pb02Prepare(changed)), "transport equivalence cannot erase " + mutation.Name);
            }
            } finally { File.Delete(sourcePng); File.Delete(alternatePng); }
        });
    }

    private static void Pb02RestoreRefusesSameIdContentConflicts()
    {
        WithPlacedLedger((_, ledger) => {
            using var peers = new ReviewPeers(); using var metadata = new Pb02HostMetadata("native");
            peers.Mode(NetmodeID.SinglePlayer, 0);
            var source = Pb02Data("pb02-restore-conflict", "http");
            var valid = PlacedLedgerRow(source, 1);
            PlacedLedgerLoadRows(ledger, new[] { valid });
            object group = ((IDictionary)typeof(GeneratedPlacementLedgerSystem).GetField("Groups", PersistenceStatic)!.GetValue(null)!).Values.Cast<object>().Single();
            MethodInfo restore = typeof(GeneratedPlacementLedgerSystem).GetMethod("RestorePlacedBodyDefinition", PersistenceStatic)!;
            var equivalent = Pb02Prepare(source);
            peers.Registry.RegisterLocal(equivalent, persist: false, ensureAssets: false);
            Equal(true, (bool)restore.Invoke(null, new object[] { group, false })!, "same-ID equivalent transport is accepted at the real restoration conflict fence");
            foreach (bool transform in new[] { false, true })
            {
                var wrong = GeneratedItemData.FromJson(equivalent.ToNetworkJson())!;
                if (transform) Pb02ShiftTransform(wrong);
                else wrong.Gameplay.Damage += 1;
                peers.Registry.RegisterLocal(wrong, persist: false, ensureAssets: false);
                string conflictHash = GeneratedItemRegistryService.DefinitionIdentity(wrong);
                Equal(false, (bool)restore.Invoke(null, new object[] { group, false })!, "real same-ID gameplay/transform conflict refuses instead of ignoring hash mismatch");
                Equal(true, peers.Registry.TryGet(source.Id, out var retained), "existing same-ID conflict remains visible");
                Equal(conflictHash, GeneratedItemRegistryService.DefinitionIdentity(retained), "refused restoration cannot overwrite existing registry owner");
            }
            Equal(valid.GetString("definitionJson"), PlacedLedgerGroups(ledger).Single().GetString("definitionJson"), "conflict refusal retains exact durable material definition");
        });
    }

    private static void Pb02NativeDefaultHashBytesStayUnchanged()
    {
        WithPlacedLedger((_, __) => {
            var data = PlacedLedgerData("pb02-native-default-bytes");
            Equal("native", data.RecipeMeta.AssetTransport, "existing initializer is the canonical transport representative");
            data.RecipeMeta.AssetBaseUrl = "";
            data.RecipeMeta.AssetFiles = GeneratedAssetSyncService.AssetFilesFromData(data).ToArray();
            var network = GeneratedItemData.FromJson(data.ToNetworkJson())!;
            string bytes = network.ToNetworkJson();
            // This is the raw digest of an already canonical native fixture, not a
            // duplicate gameplay hash algorithm or a placed-only fallback. Both old
            // and new owners must hash these exact same native-default wire bytes.
            string rawHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(bytes))).ToLowerInvariant();
            Equal(rawHash, GeneratedItemRegistryService.DefinitionIdentity(network), "all-native default identity bytes remain identical to baseline canonical input");
            Equal(bytes, network.ToNetworkJson(), "identity normalization is clone-only");
        });
    }
}
