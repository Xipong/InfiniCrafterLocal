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

    private static void DisposedAssetDownloadCannotPublish()
        => CheckDisposedAssetDownloadsAsync().GetAwaiter().GetResult();
    private static void DisposedAssetDownloadRetiresWhileBodyIsWithheld()
        => CheckAssetBodyRetirementAsync().GetAwaiter().GetResult();
    private static void DisposedAssetDownloadRetiresWhileHttpSlotsAreHeld()
        => CheckAssetSlotRetirementAsync().GetAwaiter().GetResult();

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
    private static async Task CheckAssetRetiredBeforeRelease(Task worker, string boundary)
    {
        Equal(true, ReferenceEquals(worker, await Task.WhenAny(worker, Task.Delay(AssetRetirementBound))),
            "disposed worker retires within 500ms while " + boundary + " stays held");
        Equal(false, worker.IsFaulted, "disposed retirement is non-faulted: " + boundary);
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

    private static async Task CheckAssetBodyRetirementAsync()
    {
        using var retired = new GeneratedAssetSyncService(); using var active = new GeneratedAssetSyncService();
        string retiredFile = AssetLifetimeFile(), activeFile = AssetLifetimeFile();
        await using var retiredServer = new AssetHeldResponse(retiredFile, AssetLifetimePng, allowDisconnect: true);
        await using var activeServer = new AssetHeldResponse(activeFile, AssetLifetimePng);
        Task? retiredWorker = null, activeWorker = null;
        try {
            CheckAssetLifetimePermits();
            retiredWorker = AssetLifetimeDownload(retired, retiredServer, retiredFile);
            activeWorker = AssetLifetimeDownload(active, activeServer, activeFile);
            await Task.WhenAll(retiredServer.Barrier.Task, activeServer.Barrier.Task).WaitAsync(AssetSetupBound);
            Equal(GeneratedAssetSyncService.HttpDownloadConcurrency - 2, AssetHttpSlots.CurrentCount, "two real services own distinct permits");
            Equal(false, retiredWorker.IsCompleted || activeWorker.IsCompleted, "both workers pending at header-flush/body-withheld barriers");
            retired.Dispose(); retired.Dispose(); // Idempotence while an actual worker retires.
            await CheckAssetRetiredBeforeRelease(retiredWorker, "response body");
            Equal(false, retiredServer.ReleaseIssued, "no body release used to retire worker");
            Equal(0, retiredServer.BodyBytesWritten, "entire response body still withheld");
            Equal(false, activeWorker.IsCompleted, "disposing one service does not cancel its independent sibling");
            Equal(GeneratedAssetSyncService.HttpDownloadConcurrency - 1, AssetHttpSlots.CurrentCount, "only retired service returns its owned permit");
            CheckStoppedAssetLifetime(retired, retiredServer, retiredFile);
            await DrainAssetLifetimeWorker(activeWorker, activeServer); await activeServer.CloseAsync();
            Equal(true, AssetLifetimePng.SequenceEqual(File.ReadAllBytes(Path.Combine(active.CacheRoot, activeFile))), "independent active service still commits exact bytes");
            Equal(0, active.GetDebugSnapshot().KnownMissingCount, "independent active service is healthy");
            await DrainAssetLifetimeWorker(retiredWorker, retiredServer); await retiredServer.CloseAsync();
            CheckStoppedAssetLifetime(retired, retiredServer, retiredFile);
            Console.WriteLine("DETAIL: disposed HTTP body worker retired before release within 500ms; independent service stayed pending then committed; header flush is not an instruction-pointer body-read probe");
        }
        finally {
            retired.Dispose(); active.Dispose();
            await Task.WhenAll(DrainAssetLifetimeWorker(retiredWorker, retiredServer), DrainAssetLifetimeWorker(activeWorker, activeServer));
            CheckAssetLifetimePermits(); DeleteAssetLifetimeFiles(retired, retiredFile); DeleteAssetLifetimeFiles(active, activeFile);
        }
    }

    private static async Task CheckAssetSlotRetirementAsync()
    {
        using var retired = new GeneratedAssetSyncService(); using var active = new GeneratedAssetSyncService();
        string retiredFile = AssetLifetimeFile(), activeFile = AssetLifetimeFile();
        await using var retiredServer = new AssetHeldResponse(retiredFile, AssetLifetimePng, allowDisconnect: true);
        await using var activeServer = new AssetHeldResponse(activeFile, AssetLifetimePng);
        Task? retiredWorker = null, activeWorker = null; SemaphoreSlim slots = AssetHttpSlots; int held = 0;
        try {
            CheckAssetLifetimePermits();
            for (; held < GeneratedAssetSyncService.HttpDownloadConcurrency; held++) Equal(true, await slots.WaitAsync(AssetSetupBound), "fixture owns every HTTP permit");
            retiredWorker = AssetLifetimeDownload(retired, retiredServer, retiredFile);
            activeWorker = AssetLifetimeDownload(active, activeServer, activeFile);
            Equal(false, retiredWorker.IsCompleted || activeWorker.IsCompleted, "actual workers blocked at incomplete semaphore awaits");
            retired.Dispose(); retired.Dispose();
            await CheckAssetRetiredBeforeRelease(retiredWorker, "all HTTP slots");
            Equal(0, slots.CurrentCount, "cancelled waiter never releases a fixture-owned permit");
            Equal(false, retiredServer.RequestReceived.Task.IsCompleted || activeServer.RequestReceived.Task.IsCompleted, "no HTTP request while every permit stays held");
            Equal(false, activeWorker.IsCompleted, "independent service's waiter was not cancelled");
            // Exercise a worker starting after Dispose and CTS retirement, with slots still held.
            await CheckAssetRetiredBeforeRelease(AssetLifetimeDownload(retired, retiredServer, retiredFile), "all HTTP slots after prior disposal");
            Equal(0, slots.CurrentCount, "already-disposed worker also cannot release an unowned permit");
            slots.Release(held); held = 0;
            await activeServer.Barrier.Task.WaitAsync(AssetSetupBound);
            await DrainAssetLifetimeWorker(activeWorker, activeServer); await activeServer.CloseAsync();
            Equal(true, AssetLifetimePng.SequenceEqual(File.ReadAllBytes(Path.Combine(active.CacheRoot, activeFile))), "independent waiter publishes after fixture permits are released");
            await DrainAssetLifetimeWorker(retiredWorker, retiredServer); await retiredServer.CloseAsync();
            Equal(false, retiredServer.RequestReceived.Task.IsCompleted, "cancelled waiter never issues a late HTTP request");
            CheckStoppedAssetLifetime(retired, retiredServer, retiredFile);
            Console.WriteLine("DETAIL: disposed semaphore waiter retired within 500ms with all permits held; no request/unowned release; independent service completed after exact fixture release");
        }
        finally {
            if (held > 0) { slots.Release(held); held = 0; }
            retired.Dispose(); active.Dispose();
            await Task.WhenAll(DrainAssetLifetimeWorker(retiredWorker, retiredServer), DrainAssetLifetimeWorker(activeWorker, activeServer));
            CheckAssetLifetimePermits(); DeleteAssetLifetimeFiles(retired, retiredFile); DeleteAssetLifetimeFiles(active, activeFile);
        }
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
