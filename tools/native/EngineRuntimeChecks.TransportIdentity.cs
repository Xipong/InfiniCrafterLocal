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
                // Establish an actual observed snapshot through production discovery
                // against a loopback double. Private cache fields are not observations.
                var discovery = new CraftHttpFixture(0) { DiscoveryJson =
                    "{\"multiplayer\":{\"assetTransport\":\"" + transport + "\",\"assetPublicBaseUrl\":\"" + PublicUrl + "\"}}" };
                try
                {
                    var generator = new GeneratorClient { Endpoint = discovery.Endpoint };
                    generator.RefreshAssetTransportMetadata();
                    Equal(1, discovery.DiscoveryRequests, "PB-02 observes actual host discovery");
                    GeneratorProperty.SetValue(null, generator);
                }
                finally { discovery.DisposeAsync().AsTask().GetAwaiter().GetResult(); }
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
        data.Visual.RenderSizePx=32; data.Visual.ForwardAngleDegrees=0;
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
                ("VFX", d => d.VfxManifest.Budget.MaxDrawCalls += 1),
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

}
