using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    // Retain the existing real Pillow-produced 2x2 RGBA PNG fixture.
    private static readonly byte[] AssetLifetimePng = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGMUDJ76n4GBgYGJAQoAHTQB/GtRKAwAAAAASUVORK5CYII=");
    private static readonly TimeSpan AssetSetupBound = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan AssetRetirementBound = TimeSpan.FromMilliseconds(500);
    private static readonly TimeSpan AssetCleanupBound = TimeSpan.FromSeconds(10);
    private static SemaphoreSlim AssetHttpSlots => (SemaphoreSlim)typeof(GeneratedAssetSyncService)
        .GetField("HttpSlots", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;

    private static void LocalAssetDownloadsKeepGeneratorOrigin()
    {
        var generatorProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod)
            .GetProperty("Generator", BindingFlags.Static | BindingFlags.Public)!;
        object? oldGenerator = generatorProperty.GetValue(null);
        int oldMode = Terraria.Main.netMode;
        string? oldPublicUrl = Environment.GetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL");
        var generator = new GeneratorClient { Endpoint = "http://127.0.0.1:5055/combine" };
        const string publicUrl = "http://192.0.2.42:5055";
        var discovery = new CraftHttpFixture(0) { DiscoveryJson =
            "{\"multiplayer\":{\"assetTransport\":\"http\",\"assetPublicBaseUrl\":\"" + publicUrl + "\"}}" };
        try
        {
            generator.Endpoint = discovery.Endpoint;
            generator.RefreshAssetTransportMetadata();
            Equal(1, discovery.DiscoveryRequests, "sharing URL established by actual observation");
        }
        finally { discovery.DisposeAsync().AsTask().GetAwaiter().GetResult(); }
        generator.Endpoint = "http://127.0.0.1:5055/combine";
        var select = typeof(GeneratedAssetSyncService).GetMethod("BestBaseUrl", BindingFlags.Instance | BindingFlags.NonPublic)!;
        using var service = new GeneratedAssetSyncService();
        try
        {
            generatorProperty.SetValue(null, generator);
            foreach (string publicOverride in new[] { "", publicUrl })
            foreach (int mode in new[] { Terraria.ID.NetmodeID.SinglePlayer, Terraria.ID.NetmodeID.Server, Terraria.ID.NetmodeID.MultiplayerClient })
            foreach (string metadataUrl in new[] { "", publicUrl })
            {
                Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", publicOverride);
                Terraria.Main.netMode = mode;
                var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
                data.RecipeMeta.AssetBaseUrl = metadataUrl;
                string before = data.ToJson();
                string expected = mode == Terraria.ID.NetmodeID.MultiplayerClient ? publicUrl : "http://127.0.0.1:5055";
                Equal(expected, (string)select.Invoke(service, new object[] { data })!, "download origin follows local generator, not friend sharing URL; mode=" + mode);
                Equal(before, data.ToJson(), "routing never mutates the accepted recipe");
                Equal(publicUrl, generator.AssetBaseUrlForSharing(), "peer sharing origin remains independent");
            }
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            generator.Endpoint = "not-an-http-endpoint";
            var invalid = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
            invalid.RecipeMeta.AssetBaseUrl = publicUrl;
            Equal("", (string)select.Invoke(service, new object[] { invalid })!, "invalid local endpoint cannot silently borrow the friend URL");
            generatorProperty.SetValue(null, null);
            Equal(publicUrl, (string)select.Invoke(service, new object[] { invalid })!, "metadata remains the source when no local generator exists");
        }
        finally
        {
            generatorProperty.SetValue(null, oldGenerator);
            Terraria.Main.netMode = oldMode;
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", oldPublicUrl);
        }
    }

    private static Task AssetLifetimeDownload(GeneratedAssetSyncService service, AssetHeldResponse server, string file)
        => (Task)typeof(GeneratedAssetSyncService).GetMethod("DownloadOneAsync", BindingFlags.Instance | BindingFlags.NonPublic)!
            .Invoke(service, new object?[] { server.BaseUrl, "", file, Path.Combine(service.CacheRoot, file), server.BaseUrl + "||" + file, null })!;
    private static string AssetLifetimeFile() => "asset_lifetime_" + Guid.NewGuid().ToString("N") + ".png";
    private static void DeleteAssetLifetimeFiles(GeneratedAssetSyncService service, string file)
    {
        File.Delete(Path.Combine(service.CacheRoot, file)); File.Delete(Path.Combine(service.CacheRoot, file) + ".part");
    }
    private static void CheckStoppedAssetLifetime(GeneratedAssetSyncService service, AssetHeldResponse server, string file)
    {
        Equal(false, File.Exists(Path.Combine(service.CacheRoot, file)), "disposed worker cannot publish");
        Equal(false, File.Exists(Path.Combine(service.CacheRoot, file) + ".part"), "disposed worker leaves no part");
        Equal(0, service.GetDebugSnapshot().KnownMissingCount, "disposed worker cannot resurrect retry state");
        Equal(0, service.GetDebugSnapshot().InFlightCount, "disposed worker retires in-flight state");
        bool oldDedicated = Terraria.Main.dedServ;
        try {
            Terraria.Main.dedServ = false;
            service.QueueDownloads(server.BaseUrl, new[] { file }, forceRetry: true);
            Equal(0, service.GetDebugSnapshot().DownloadStartedCount, "disposed public queue remains fenced");
        } finally { Terraria.Main.dedServ = oldDedicated; }
    }
    private static void CheckAssetLifetimePermits()
    {
        SemaphoreSlim slots = AssetHttpSlots; int expected = GeneratedAssetSyncService.HttpDownloadConcurrency, acquired = 0;
        Equal(expected, slots.CurrentCount, "all real HTTP permits restored");
        try {
            for (; acquired < expected; acquired++) Equal(true, slots.Wait(0), "reacquire each real HTTP permit");
            bool excess = slots.Wait(0);
            if (excess) slots.Release();
            Equal(false, excess, "no excess HTTP permit");
        } finally { if (acquired > 0) slots.Release(acquired); }
        Equal(expected, slots.CurrentCount, "restore exactly the fixture-owned permits");
    }
    private static async Task DrainAssetLifetimeWorker(Task? worker, AssetHeldResponse server)
    {
        server.Release();
        if (worker is null) return;
        try { await worker.WaitAsync(AssetCleanupBound); }
        catch (OperationCanceledException) when (worker.IsCanceled) { }
        catch (TimeoutException) {
            server.Abort();
            try { await worker.WaitAsync(AssetSetupBound); }
            catch (OperationCanceledException) when (worker.IsCanceled) { }
            throw new InvalidOperationException("Asset worker exceeded cleanup bound after fixture release; real socket aborted");
        }
    }

    private static async Task CheckDisposedAssetDownloadsAsync()
    {
        var failures = new List<string>();
        foreach (bool disposed in new[] { false, true })
        foreach (string outcome in new[] { "png", "invalid_png", "http_error" })
        {
            bool valid = outcome == "png";
            using var service = new GeneratedAssetSyncService(); string file = AssetLifetimeFile();
            string local = Path.Combine(service.CacheRoot, file);
            await using var server = new AssetHeldResponse(file, valid ? AssetLifetimePng : Encoding.ASCII.GetBytes("not a PNG"),
                errorStatus: outcome == "http_error", allowDisconnect: disposed);
            Task? worker = null;
            try {
                CheckAssetLifetimePermits(); worker = AssetLifetimeDownload(service, server, file);
                await server.Barrier.Task.WaitAsync(AssetSetupBound);
                Equal(false, worker.IsCompleted, "actual worker waits behind body/status barrier");
                if (disposed) service.Dispose();
                await DrainAssetLifetimeWorker(worker, server); await server.CloseAsync();
                Equal(valid && !disposed, File.Exists(local), "published file: disposed=" + disposed + ", outcome=" + outcome);
                if (valid && !disposed) Equal(true, AssetLifetimePng.SequenceEqual(File.ReadAllBytes(local)), "active service commits exact verified bytes");
                Equal(!disposed && !valid ? 1 : 0, service.GetDebugSnapshot().KnownMissingCount,
                    "retry state: disposed=" + disposed + ", outcome=" + outcome);
                Equal(false, File.Exists(local + ".part"), "no leftover partial file");
                if (disposed) CheckStoppedAssetLifetime(service, server, file);
            }
            catch (Exception error) { failures.Add("disposed=" + disposed + ", outcome=" + outcome + ": " + error); }
            finally {
                service.Dispose(); await DrainAssetLifetimeWorker(worker, server);
                CheckAssetLifetimePermits(); DeleteAssetLifetimeFiles(service, file);
            }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    // One bounded loopback fixture for the retained six controls and both regressions.
    // A cancelled client may close before a held HTTP-error status can be written.
    private sealed class AssetHeldResponse : IAsyncDisposable
    {
        private readonly TcpListener listener = new(IPAddress.Loopback, 0);
        private readonly CancellationTokenSource stop = new();
        private readonly TaskCompletionSource<bool> release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly Task serve;
        private readonly bool allowDisconnect;
        private TcpClient? client;
        private int released;
        private Exception? failure;
        internal readonly TaskCompletionSource<bool> Barrier = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly TaskCompletionSource<bool> RequestReceived = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal string BaseUrl { get; }
        internal bool ReleaseIssued => Volatile.Read(ref released) != 0;
        internal int BodyBytesWritten { get; private set; }
        internal AssetHeldResponse(string file, byte[] body, bool errorStatus = false, bool allowDisconnect = false)
        {
            this.allowDisconnect = allowDisconnect; listener.Start();
            BaseUrl = "http://127.0.0.1:" + ((IPEndPoint)listener.LocalEndpoint).Port;
            serve = Task.Run(async () => {
                try {
                    client = await listener.AcceptTcpClientAsync(stop.Token);
                    using TcpClient accepted = client; await using NetworkStream stream = accepted.GetStream();
                    using var request = new MemoryStream(); byte[] buffer = new byte[1024];
                    while (true) {
                        int count = await stream.ReadAsync(buffer.AsMemory(), stop.Token);
                        if (count == 0) throw new IOException("peer closed before complete request");
                        request.Write(buffer, 0, count);
                        if (request.Length > 8192) throw new InvalidOperationException("loopback request exceeds bounded headers");
                        string text = Encoding.ASCII.GetString(request.ToArray());
                        if (!text.Contains("\r\n\r\n", StringComparison.Ordinal)) continue;
                        Equal("GET /get_asset?file=" + Uri.EscapeDataString(file) + " HTTP/1.1", text.Split("\r\n", StringSplitOptions.None)[0], "actual canonical HTTP route");
                        RequestReceived.TrySetResult(true); break;
                    }
                    if (errorStatus) { Barrier.TrySetResult(true); await release.Task.WaitAsync(stop.Token); }
                    string status = errorStatus ? "500 Internal Server Error" : "200 OK";
                    byte[] headers = Encoding.ASCII.GetBytes("HTTP/1.1 " + status + "\r\nContent-Type: image/png\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\n\r\n");
                    await stream.WriteAsync(headers.AsMemory(), stop.Token); await stream.FlushAsync(stop.Token);
                    if (!errorStatus) { Barrier.TrySetResult(true); await release.Task.WaitAsync(stop.Token); }
                    await stream.WriteAsync(body.AsMemory(), stop.Token); await stream.FlushAsync(stop.Token); BodyBytesWritten = body.Length;
                }
                catch (Exception error) { failure = error; Barrier.TrySetException(error); }
            });
        }
        internal void Release() { Interlocked.Exchange(ref released, 1); release.TrySetResult(true); }
        internal void Abort() { stop.Cancel(); listener.Stop(); client?.Dispose(); }
        internal async Task CloseAsync()
        {
            Release();
            if (RequestReceived.Task.IsCompleted) await serve.WaitAsync(AssetSetupBound);
            Abort(); await serve.WaitAsync(AssetSetupBound);
            if (failure is null) return;
            if (!RequestReceived.Task.IsCompleted && failure is OperationCanceledException && stop.IsCancellationRequested) return;
            if (allowDisconnect && RequestReceived.Task.IsCompleted && ReleaseIssued && failure is IOException or SocketException) return;
            throw new InvalidOperationException("loopback fixture failed", failure);
        }
        public async ValueTask DisposeAsync() { try { await CloseAsync(); } finally { stop.Dispose(); } }
    }
}
