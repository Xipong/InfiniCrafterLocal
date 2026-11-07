using System;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static async Task ServerAssetsPrepareCurrentGeneratorStoreAsync()
    {
        int oldMode = Terraria.Main.netMode; bool oldDedicated = Terraria.Main.dedServ;
        try
        {
            Terraria.Main.netMode = Terraria.ID.NetmodeID.Server; Terraria.Main.dedServ = true;
            using var sync = new GeneratedAssetSyncService();
            string file = AssetLifetimeFile();
            var data = AssetOwnerData("server_asset_" + Guid.NewGuid().ToString("N"), file);
            var external = new SharedImageStore(Path.Combine(Terraria.Program.SavePath, "standalone-generator-images"));
            string source = external.Publish(file, AssetOwnerCanonical, data.RecipeMeta.WorldId, "world", data.Id, data.Name, "item");
            file = Path.GetFileName(source);
            data.Visual.SpritePath = source;
            data.RecipeMeta.AssetBaseUrl = "http://192.0.2.42:5055"; // sharing URL cannot own host reads
            string before = data.ToJson();
            Equal(false, sync.HasCompleteServerAssetRoster(data), "current external indexed PNG needs explicit transport materialization");
            await using var server = new AssetHeldResponse(file, AssetOwnerCanonical);
            Task worker = sync.PrepareServerAssetsAsync(data, server.BaseUrl + "/combine", CancellationToken.None);
            await server.Barrier.Task.WaitAsync(AssetSetupBound);
            Equal(false, worker.IsCompleted, "MP generation awaits the complete asset body");
            Equal(true, sync.ResolveLocalPath(file) is null, "partial HTTP response has no indexed publication");
            server.Release(); await worker.WaitAsync(AssetSetupBound);
            Equal(true, sync.HasCompleteServerAssetRoster(data), "dedicated server can now commit its complete current roster");
            Equal(ImageHash(AssetOwnerCanonical), ImageHash(File.ReadAllBytes(sync.ResolveLocalPath(file)!)), "native index owns exact generator bytes");
            Equal(ImageHash(AssetOwnerCanonical), ImageHash(File.ReadAllBytes(source)), "external current store is not moved or rewritten");
            Equal(before, data.ToJson(), "transport materialization does not rewrite definition paths or authored fields");
            Equal(1, sync.GetDebugSnapshot().DownloadStartedCount, "one canonical generator request");
            await sync.PrepareServerAssetsAsync(data, server.BaseUrl + "/combine", CancellationToken.None);
            Equal(1, sync.GetDebugSnapshot().DownloadStartedCount, "shared/warm canonical bytes need no duplicate HTTP copy");
            CheckAssetLifetimePermits();
        }
        finally { Terraria.Main.netMode = oldMode; Terraria.Main.dedServ = oldDedicated; }
    }

    private static async Task ServerAssetsRefuseInvalidAndRetiredDownloadsAsync()
    {
        int oldMode = Terraria.Main.netMode; bool oldDedicated = Terraria.Main.dedServ;
        try
        {
            Terraria.Main.netMode = Terraria.ID.NetmodeID.Server; Terraria.Main.dedServ = true;
            foreach (string outcome in new[] { "invalid", "http_error", "oversize", "cancel", "world", "dispose" })
            {
                using var sync = new GeneratedAssetSyncService(); using var cancel = new CancellationTokenSource();
                string file = AssetLifetimeFile();
                var data = AssetOwnerData("server_refusal_" + Guid.NewGuid().ToString("N"), file);
                // Even a healthy raw selector cannot rescue failed current HTTP delivery.
                string raw = Path.Combine(Terraria.Program.SavePath, file);
                File.WriteAllBytes(raw, AssetOwnerCanonical); data.Visual.SpritePath = raw;
                byte[] body = outcome == "invalid" ? new byte[] { 1, 2, 3 }
                    : outcome == "oversize" ? new byte[GeneratedAssetSyncService.MaxAssetBytes + 1] : AssetOwnerCanonical;
                await using var server = new AssetHeldResponse(file, body, errorStatus: outcome == "http_error", allowDisconnect: true);
                Task worker = sync.PrepareServerAssetsAsync(data, server.BaseUrl + "/combine", cancel.Token);
                await server.Barrier.Task.WaitAsync(AssetSetupBound);
                if (outcome == "cancel") cancel.Cancel();
                if (outcome == "world") sync.ResetWorldDescriptors();
                if (outcome == "dispose") sync.Dispose();
                server.Release();
                bool refused = false;
                try { await worker.WaitAsync(AssetSetupBound); }
                catch (Exception error) when (error is InvalidDataException or OperationCanceledException or HttpRequestException) { refused = true; }
                Equal(true, refused, "invalid/retired server preparation fails before MP delivery: " + outcome);
                Equal(true, sync.ResolveLocalPath(file) is null, "refused preparation never publishes an indexed PNG: " + outcome);
                Equal(ImageHash(AssetOwnerCanonical), ImageHash(File.ReadAllBytes(raw)), "raw local source remains untouched: " + outcome);
                CheckAssetLifetimePermits();
            }
            using var bounded = new GeneratedAssetSyncService();
            foreach (bool malformed in new[] { true, false })
            {
                var data = AssetOwnerData("server_roster_bounds", "valid.png");
                if (malformed) data.Visual.SpritePath = "not-a-png-selector";
                else data.VfxManifest.Assets = Enumerable.Range(0, GeneratedAssetSyncService.MaxAssetFiles)
                    .Select(index => new VfxAssetSpec { SpritePath = "extra_" + index + ".png" }).ToArray();
                bool refused = false;
                try { await bounded.PrepareServerAssetsAsync(data, "http://127.0.0.1:1/combine", CancellationToken.None); }
                catch (InvalidDataException) { refused = true; }
                Equal(true, refused, "malformed or excessive declared roster is refused before network");
                Equal(0, bounded.GetDebugSnapshot().DownloadStartedCount, "invalid roster cannot collapse to success or start HTTP");
            }
        }
        finally { Terraria.Main.netMode = oldMode; Terraria.Main.dedServ = oldDedicated; }
    }

    private delegate Task ServerPreparationOriginal(GeneratedAssetSyncService self, GeneratedItemData data, string endpoint, CancellationToken token);
    private delegate Task ServerPreparationHook(ServerPreparationOriginal original, GeneratedAssetSyncService self, GeneratedItemData data, string endpoint, CancellationToken token);

    private static async Task ServerCraftAwaitsAssetsOnFreshAndCachePathsAsync()
    {
        int oldMode = Terraria.Main.netMode; bool oldDedicated = Terraria.Main.dedServ;
        var property = typeof(InfiniMod).GetProperty("AssetSync", BindingFlags.Static | BindingFlags.Public)!;
        object? prior = property.GetValue(null);
        try
        {
            Terraria.Main.netMode = Terraria.ID.NetmodeID.Server; Terraria.Main.dedServ = true;
            using var sync = new GeneratedAssetSyncService(); property.SetValue(null, sync);
            foreach (bool cacheHit in new[] { false, true })
            {
                var data = AssetOwnerData("server_boundary_" + Guid.NewGuid().ToString("N"), AssetLifetimeFile());
                await using var server = new CraftHttpFixture(0) { SuccessJson = data.ToJson(), CacheHit = cacheHit };
                var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var hook = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedAssetSyncService).GetMethod("PrepareServerAssetsAsync", BindingFlags.Instance | BindingFlags.NonPublic)!,
                    (ServerPreparationHook)((original, self, received, endpoint, token) => {
                        Equal(true, ReferenceEquals(sync, self), "generation uses its active native store");
                        Equal(data.Id, received.Id, "preparation receives accepted current definition");
                        Equal(server.Endpoint, endpoint, "host downloads use the same generator origin as craft");
                        entered.TrySetResult(true); return release.Task.WaitAsync(token);
                    }));
                var client = new GeneratorClient { Endpoint = server.Endpoint };
                var request = new GeneratorClient.PreparedGenerationRequest();
                Task<GeneratedItemData?> worker = Task.Run(() => client.GeneratePreparedBlocking(request));
                try
                {
                    await entered.Task.WaitAsync(AssetSetupBound);
                    Equal(false, worker.IsCompleted, "fresh/cache result cannot escape before asset preparation: " + cacheHit);
                    release.TrySetResult(true);
                    Equal(data.Id, (await worker.WaitAsync(AssetSetupBound))?.Id ?? "", "prepared fresh/cache result can reach main-thread MP commit: " + cacheHit);
                }
                finally { request.Cancel(); release.TrySetResult(true); await worker.WaitAsync(AssetSetupBound); }
            }
        }
        finally { property.SetValue(null, prior); Terraria.Main.netMode = oldMode; Terraria.Main.dedServ = oldDedicated; }
    }
}
