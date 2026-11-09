// Linked-source CPU checks. The packet capture boundary is not a Steam session.
using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.IO.Compression;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using InfiniCrafterLocal;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria.ID;
using Terraria.ModLoader;
using TMain = Terraria.Main;

internal static class Program
{
    private static int Main()
    {
        (string Name, Action Run)[] checks = {
            ("RGBA PNG roundtrip is byte-exact", Roundtrip),
            ("single-item reset preserves other native retry rosters", ScopedRetryReset),
            ("repeated ensures coalesce without postponing retries", RepeatedEnsures),
            ("retry batches all PNGs behind the item cooldown", RetryBatch),
            ("new sibling joins the outstanding item request", NewSibling),
            ("world reset retires packet work and retains cached files", WorldReset),
            ("replaced manifest retires removed PNG requests", ReplacedManifest),
            ("corrupt bundle is withheld and retried successfully", CorruptionRetry),
            ("duplicate chunks do not postpone recovery", DuplicateProgress),
            ("impossible chunk framing cannot allocate state", InvalidFraming),
            ("out-of-order and duplicate chunks preserve bytes", ReorderedChunks),
            ("descriptor mismatch and HTTP mode refuse native bytes", AdmissionControls),
            ("per-client send budget remains independent", Pacing),
            ("disposed service cannot recreate packet work", Disposed),
            ("stalled HTTP bodies release all slots for the next PNG", () => StalledHttpBodies().GetAwaiter().GetResult()),
            ("continuing HTTP body progress cannot renew the absolute deadline", () => SlowDripHttpBodies().GetAwaiter().GetResult()),
            ("disposing live HTTP work cancels readers and waiters without publication", () => DisposedHttpBodies().GetAwaiter().GetResult()),
        };
        int failures = 0;
        foreach (var check in checks)
        {
            try { check.Run(); Console.WriteLine("PASS " + check.Name); }
            catch (Exception error) { failures++; Console.WriteLine("FAIL " + check.Name + ": " + error); }
        }
        Console.WriteLine($"Asset transport checks: {checks.Length - failures}/{checks.Length} passed (linked source; no Steam session)");
        return failures == 0 ? 0 : 1;
    }

    private static async Task StalledHttpBodies()
    {
        string root = Path.Combine(Path.GetTempPath(), "ifc-http-check-" + Guid.NewGuid().ToString("N"));
        TMain.SavePath = root; TMain.netMode = 0; TMain.dedServ = false;
        InfiniCrafterLocalMod.GeneratedItems = null;
        byte[] png = Png(8, 8, 27);
        using var service = new GeneratedAssetSyncService();
        using var stopping = new CancellationTokenSource();
        using var headersSent = new CountdownEvent(GeneratedAssetSyncService.HttpDownloadConcurrency);
        var releaseBodies = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var fifthServed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var clients = new List<Task>();
        async Task Serve(TcpClient client)
        {
            using (client)
            {
                NetworkStream stream = client.GetStream();
                using var reader = new StreamReader(stream, Encoding.ASCII, leaveOpen: true);
                string request = await reader.ReadLineAsync(stopping.Token) ?? "";
                while (!string.IsNullOrEmpty(await reader.ReadLineAsync(stopping.Token))) { }
                bool good = request.Contains("http_good.png", StringComparison.Ordinal);
                byte[] header = Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Length: {png.Length}\r\nContent-Type: image/png\r\nConnection: close\r\n\r\n");
                await stream.WriteAsync(header, stopping.Token);
                await stream.WriteAsync(good ? png : png.AsMemory(0, 8), stopping.Token);
                await stream.FlushAsync(stopping.Token);
                if (good) fifthServed.SetResult();
                else { headersSent.Signal(); await releaseBodies.Task; }
            }
        }
        Task server = Task.Run(async () =>
        {
            try
            {
                while (!stopping.IsCancellationRequested)
                    clients.Add(Serve(await listener.AcceptTcpClientAsync(stopping.Token)));
            }
            catch (OperationCanceledException) when (stopping.IsCancellationRequested) { }
        });
        try
        {
            string url = "http://127.0.0.1:" + ((IPEndPoint)listener.LocalEndpoint).Port;
            service.QueueDownloads(url, Enumerable.Range(0, 4).Select(index => $"stall_{index}.png"));
            Require(headersSent.Wait(TimeSpan.FromSeconds(10)), "all four HTTP slots must receive headers and partial bodies");
            service.QueueDownloads(url, new[] { "http_good.png" });
            // The live body timeout is 12 seconds. This is a deadlock guard, not a speed assertion.
            await fifthServed.Task.WaitAsync(TimeSpan.FromSeconds(30));
            Require(SpinWait.SpinUntil(() => service.GetDebugSnapshot().InFlightCount == 0, TimeSpan.FromSeconds(10)), "download cleanup did not finish");
            string path = service.ResolveLocalPath("http_good.png") ?? "";
            Require(File.Exists(path) && File.ReadAllBytes(path).SequenceEqual(png), "fifth PNG was not committed byte-exactly");
            Require(service.GetDebugSnapshot().KnownMissingCount == 4, "timed-out bodies did not enter the bounded retry path");
            Require(!Directory.EnumerateFiles(service.CacheRoot, "stall_*.png", SearchOption.AllDirectories).Any(), "partial PNG escaped publication");
        }
        finally
        {
            service.Dispose();
            releaseBodies.TrySetResult();
            stopping.Cancel();
            await server;
            listener.Stop();
            await Task.WhenAll(clients);
            Require(SpinWait.SpinUntil(() => service.GetDebugSnapshot().InFlightCount == 0, TimeSpan.FromSeconds(10)), "cancelled downloads did not retire");
            Directory.Delete(root, recursive: true);
        }
    }

    // Real loopback HTTP only: the production downloader, deadline and shared slots
    // remain intact. The responder models peers that keep writing or never finish.
    private sealed class LoopbackHttpServer : IAsyncDisposable
    {
        private readonly TcpListener listener = new(IPAddress.Loopback, 0);
        private readonly CancellationTokenSource stopping = new();
        private readonly List<Task> clients = new();
        private readonly Task accepting;
        internal readonly ConcurrentQueue<string> Requests = new();
        internal string Url => "http://127.0.0.1:" + ((IPEndPoint)listener.LocalEndpoint).Port;

        internal LoopbackHttpServer(Func<string, NetworkStream, CancellationToken, Task> respond)
        {
            listener.Start();
            accepting = Accept();
            async Task Accept()
            {
                try
                {
                    while (!stopping.IsCancellationRequested)
                        clients.Add(Serve(await listener.AcceptTcpClientAsync(stopping.Token)));
                }
                catch (OperationCanceledException) when (stopping.IsCancellationRequested) { }
            }
            async Task Serve(TcpClient client)
            {
                using (client)
                {
                    client.NoDelay = true;
                    try
                    {
                        NetworkStream stream = client.GetStream();
                        using var reader = new StreamReader(stream, Encoding.ASCII, leaveOpen: true);
                        string request = await reader.ReadLineAsync(stopping.Token) ?? "";
                        while (!string.IsNullOrEmpty(await reader.ReadLineAsync(stopping.Token))) { }
                        Requests.Enqueue(request);
                        await respond(request, stream, stopping.Token);
                    }
                    catch (OperationCanceledException) when (stopping.IsCancellationRequested) { }
                    catch (IOException) when (stopping.IsCancellationRequested) { }
                }
            }
        }

        public async ValueTask DisposeAsync()
        {
            stopping.Cancel();
            try
            {
                await accepting;
                await Task.WhenAll(clients);
            }
            finally { listener.Stop(); stopping.Dispose(); }
        }
    }

    private static async Task WriteHttpPngPrefix(NetworkStream stream, byte[] png, CancellationToken token)
    {
        byte[] header = Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Length: {png.Length}\r\nContent-Type: image/png\r\nConnection: close\r\n\r\n");
        await stream.WriteAsync(header, token);
        await stream.WriteAsync(png.AsMemory(0, 8), token);
        await stream.FlushAsync(token);
    }

    private sealed class TemporaryHttpCache(string prefix) : IDisposable
    {
        internal string Root { get; } = Path.Combine(Path.GetTempPath(), prefix + Guid.NewGuid().ToString("N"));
        public void Dispose() { if (Directory.Exists(Root)) Directory.Delete(Root, recursive: true); }
    }

    private static async Task SlowDripHttpBodies()
    {
        using var cache = new TemporaryHttpCache("ifc-drip-check-");
        TMain.SavePath = cache.Root; TMain.netMode = 0; TMain.dedServ = false;
        InfiniCrafterLocalMod.GeneratedItems = null;
        byte[] png = Png(256, 256, 29);
        using var service = new GeneratedAssetSyncService();
        using var started = new CountdownEvent(GeneratedAssetSyncService.HttpDownloadConcurrency);
        var progress = new ConcurrentDictionary<string, int>();
        var recovered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using (var server = new LoopbackHttpServer(async (request, stream, token) =>
        {
            await WriteHttpPngPrefix(stream, png, token);
            if (request.Contains("drip_recovery.png", StringComparison.Ordinal))
            {
                await stream.WriteAsync(png.AsMemory(8), token);
                recovered.SetResult();
                return;
            }
            progress[request] = 0;
            started.Signal();
            try
            {
                // Every write makes real body progress, much more often than the
                // 12-second deadline. The valid PNG cannot finish within the guard.
                for (int offset = 8; offset < png.Length; offset += 64)
                {
                    await stream.WriteAsync(png.AsMemory(offset, Math.Min(64, png.Length - offset)), token);
                    await stream.FlushAsync(token);
                    progress[request]++;
                    await Task.Delay(TimeSpan.FromMilliseconds(100), token);
                }
                throw new InvalidOperationException("slow peer unexpectedly completed its entire PNG");
            }
            catch (IOException) { /* The deadline closes a still-progressing peer. */ }
        }))
        {
            try
            {
                service.QueueDownloads(server.Url, Enumerable.Range(0, 4).Select(index => $"drip_{index}.png"));
                Require(started.Wait(TimeSpan.FromSeconds(10)), "all slow peers must enter live body reads");
                service.QueueDownloads(server.Url, new[] { "drip_recovery.png" });
                // An inactivity timeout renewed on every chunk never releases a
                // slot here. This is the same deadlock guard as the stalled case.
                await recovered.Task.WaitAsync(TimeSpan.FromSeconds(30));
                Require(SpinWait.SpinUntil(() => service.GetDebugSnapshot().InFlightCount == 0, TimeSpan.FromSeconds(10)), "slow downloads did not retire");
                Require(progress.Count == 4 && progress.Values.All(count => count >= 3), "fixture did not deliver repeated body progress on all four peers");
                Require(service.GetDebugSnapshot().KnownMissingCount == 4, "slow body deadlines did not enter retry state");
                string path = service.ResolveLocalPath("drip_recovery.png") ?? "";
                Require(File.Exists(path) && File.ReadAllBytes(path).SequenceEqual(png), "post-deadline PNG did not retain exact bytes");
                Require(!Directory.EnumerateFiles(service.CacheRoot, "drip_*.png", SearchOption.AllDirectories).Any(path => Path.GetFileName(path) != "drip_recovery.png"), "slow partial body was published");
                Require(!Directory.EnumerateFiles(service.CacheRoot, "*.part", SearchOption.AllDirectories).Any(), "slow partial file escaped cleanup");
                Console.WriteLine("  slow HTTP body writes before retirement: " + string.Join(", ", progress.Values.OrderBy(count => count)));
            }
            finally { service.Dispose(); }
        }
    }

    private static async Task DisposedHttpBodies()
    {
        using var cache = new TemporaryHttpCache("ifc-dispose-http-check-");
        TMain.SavePath = Path.Combine(cache.Root, "retired"); TMain.netMode = 0; TMain.dedServ = false;
        InfiniCrafterLocalMod.GeneratedItems = null;
        byte[] png = Png(8, 8, 31);
        using var retired = new GeneratedAssetSyncService();
        TMain.SavePath = Path.Combine(cache.Root, "recovery");
        using var recovery = new GeneratedAssetSyncService();
        using var live = new CountdownEvent(GeneratedAssetSyncService.HttpDownloadConcurrency);
        using var closed = new CountdownEvent(GeneratedAssetSyncService.HttpDownloadConcurrency);
        using var reacquired = new CountdownEvent(GeneratedAssetSyncService.HttpDownloadConcurrency);
        var releaseRecovery = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using (var server = new LoopbackHttpServer(async (request, stream, token) =>
        {
            await WriteHttpPngPrefix(stream, png, token);
            if (request.Contains("recovery_", StringComparison.Ordinal))
            {
                reacquired.Signal();
                await releaseRecovery.Task.WaitAsync(token);
                await stream.WriteAsync(png.AsMemory(8), token);
                return;
            }
            live.Signal();
            try
            {
                int count = await stream.ReadAsync(new byte[1], token);
                Require(count == 0, "cancelled HTTP client sent unexpected bytes");
            }
            catch (IOException) { /* Cancellation may reset rather than close TCP. */ }
            closed.Signal();
        }))
        {
            try
            {
                retired.QueueDownloads(server.Url, Enumerable.Range(0, 4).Select(index => $"retired_{index}.png"));
                Require(live.Wait(TimeSpan.FromSeconds(10)), "four partial bodies must be live before disposal");
                retired.QueueDownloads(server.Url, new[] { "queued_before_dispose.png" });
                Require(retired.GetDebugSnapshot().InFlightCount == 5, "fifth worker must be waiting for an occupied HTTP slot");
                retired.Dispose();
                retired.QueueDownloads(server.Url, new[] { "queued_after_dispose.png" });
                // Dispose clears public bookkeeping synchronously, so that alone
                // is not cleanup evidence. Observe the live sockets close and make
                // another service simultaneously reacquire every shared HTTP slot.
                recovery.QueueDownloads(server.Url, Enumerable.Range(0, 4).Select(index => $"recovery_{index}.png"));
                Require(closed.Wait(TimeSpan.FromSeconds(5)), "Dispose did not cancel live HTTP readers before the body deadline");
                Require(reacquired.Wait(TimeSpan.FromSeconds(5)), "Dispose leaked a shared HTTP slot");
                Require(recovery.GetDebugSnapshot().InFlightCount == 4, "recovery fixture must hold all four slots at once");
                releaseRecovery.SetResult();
                Require(SpinWait.SpinUntil(() => recovery.GetDebugSnapshot().InFlightCount == 0, TimeSpan.FromSeconds(10)), "recovery downloads did not finish");
                for (int index = 0; index < 4; index++)
                {
                    string path = recovery.ResolveLocalPath($"recovery_{index}.png") ?? "";
                    Require(File.Exists(path) && File.ReadAllBytes(path).SequenceEqual(png), "reacquired slot failed byte-exact publication");
                }
                Require(server.Requests.Count == 8, "cancelled waiter or disposed service started a new HTTP request");
                Require(server.Requests.All(request => !request.Contains("queued_", StringComparison.Ordinal)), "disposed queued work reached the peer");
                Require(retired.GetDebugSnapshot().InFlightCount == 0 && retired.GetDebugSnapshot().KnownMissingCount == 0, "service cancellation became retryable work");
                Require(!Directory.EnumerateFiles(retired.CacheRoot, "*", SearchOption.AllDirectories).Any(), "retired service published partial or final bytes");
            }
            finally { retired.Dispose(); recovery.Dispose(); releaseRecovery.TrySetResult(); }
        }
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string root = Path.Combine(Path.GetTempPath(), "ifc-asset-check-" + Guid.NewGuid().ToString("N"));
        internal readonly GeneratedAssetSyncService Server, Client;
        internal readonly GeneratedItemRegistryService ServerRegistry = new(), ClientRegistry = new();
        internal readonly GeneratedItemData Data = new();
        internal readonly Dictionary<string, byte[]> Expected = new(StringComparer.OrdinalIgnoreCase);
        internal readonly Queue<byte[]> Requests = new(), Frames = new();
        internal readonly List<(int Client, byte[] Bytes)> Sent = new();
        internal uint Tick;
        internal int RequestCount;

        internal Fixture(int fileCount = 2, int side = 256)
        {
            Directory.CreateDirectory(root);
            TMain.SavePath = Path.Combine(root, "server"); Server = new();
            TMain.SavePath = Path.Combine(root, "client"); Client = new();
            var store = new SharedImageStore(Server.CacheRoot);
            var paths = new List<string>();
            for (int i = 0; i < fileCount; i++)
            {
                string file = $"probe_{i}.png";
                byte[] bytes = Png(side, side, i + 41);
                string path = store.Publish(file, bytes, Data.RecipeMeta.WorldId, "transport-check",
                    Data.Id, Data.Id, i == 0 ? "item" : "vfx");
                Expected[Path.GetFileName(path)] = bytes; paths.Add(path);
            }
            Data.Visual.SpritePath = paths[0];
            Data.VfxManifest.Assets = paths.Skip(1).Select(path => new VfxAssetSpec { SpritePath = path }).ToArray();
            ServerRegistry.Items[Data.Id] = Data; ClientRegistry.Items[Data.Id] = Data;
            TMain.player[1].active = TMain.player[2].active = true;
            ServerMode();
            var descriptors = Server.BuildServerAssetDescriptors(Data);
            Require(descriptors.Length == fileCount, "indexed server fixture exposes its complete initial and sibling PNG roster");
            Client.RegisterRemoteAssetDescriptors(Data.Id, descriptors);
            ModPacket.OnSend = (bytes, client) => {
                if (TMain.netMode == NetmodeID.MultiplayerClient) { Requests.Enqueue(bytes); RequestCount++; }
                else { Frames.Enqueue(bytes); Sent.Add((client, bytes)); }
            };
        }
        internal void ClientMode()
        {
            TMain.netMode = NetmodeID.MultiplayerClient; TMain.dedServ = false; TMain.GameUpdateCount = Tick;
            InfiniCrafterLocalMod.GeneratedItems = ClientRegistry;
        }
        internal void ServerMode()
        {
            TMain.netMode = NetmodeID.Server; TMain.dedServ = true; TMain.GameUpdateCount = Tick;
            InfiniCrafterLocalMod.GeneratedItems = ServerRegistry;
        }
        internal void Ensure(bool force = false, GeneratedItemData? data = null)
        {
            ClientMode(); Client.EnsureAssetsForData(data ?? Data, force);
        }
        internal void RetryAt(uint tick)
        {
            Tick = tick; ClientMode(); Client.UpdateTransfers();
        }
        internal void AcceptRequests()
        {
            ServerMode();
            while (Requests.TryDequeue(out byte[]? bytes))
            {
                using var reader = new BinaryReader(new MemoryStream(bytes));
                Require(reader.ReadByte() == InfiniNetPacketIds.RequestGeneratedAsset, "request route");
                Server.HandleAssetRequestPacket(reader, 1);
            }
        }
        internal List<byte[]> CollectFrames()
        {
            AcceptRequests();
            for (int i = 0; Server.GetDebugSnapshot().QueuedChunkCount > 0 && i < 4000; i++, Tick++)
            {
                ServerMode(); Server.UpdateTransfers();
            }
            Require(Server.GetDebugSnapshot().QueuedChunkCount == 0, "bounded queue drain");
            var result = Frames.ToList(); Frames.Clear();
            Require(result.Count > 0, "server produced actual bundle packets");
            Require(result.All(bytes => bytes.Length + 5 <= ushort.MaxValue), "tML packet envelope bound");
            return result;
        }
        internal void Receive(byte[] bytes)
        {
            ClientMode();
            using var reader = new BinaryReader(new MemoryStream(bytes));
            Require(reader.ReadByte() == InfiniNetPacketIds.GeneratedAssetChunk, "chunk route");
            Client.HandleAssetChunkPacket(reader, 256);
        }
        internal void DeliverAll()
        {
            foreach (byte[] bytes in CollectFrames()) Receive(bytes);
        }
        internal void AssertExactFiles()
        {
            foreach (var entry in Expected)
            {
                string path = Client.ResolveLocalPath(entry.Key) ?? throw new InvalidOperationException("missing " + entry.Key);
                Require(File.Exists(path), "missing " + entry.Key);
                Require(Path.GetFileName(Path.GetDirectoryName(path)) == "final", "received PNG is not in canonical final storage");
                Require(!File.Exists(Path.Combine(Client.CacheRoot, entry.Key)), "received PNG duplicated into flat cache");
                byte[] actual = File.ReadAllBytes(path);
                Require(actual.SequenceEqual(entry.Value), "bytes changed: " + entry.Key);
                Require(SHA256.HashData(actual).SequenceEqual(SHA256.HashData(entry.Value)), "SHA mismatch");
                Require(!File.Exists(path + ".part"), "partial file escaped commit");
            }
        }
        internal void AssertNoFiles() => Require(!Directory.EnumerateFiles(Client.CacheRoot, "*", SearchOption.AllDirectories)
            .Any(path => path.EndsWith(".png", StringComparison.OrdinalIgnoreCase) || path.EndsWith(".part", StringComparison.OrdinalIgnoreCase)), "unverified bytes reached cache");
        public void Dispose()
        {
            Server.Dispose(); Client.Dispose(); ModPacket.OnSend = (_, _) => { };
            InfiniCrafterLocalMod.GeneratedItems = null;
            Directory.Delete(root, recursive: true);
        }
    }

    private static string[] RequestFiles(byte[] bytes)
    {
        using var reader = new BinaryReader(new MemoryStream(bytes));
        Require(reader.ReadByte() == InfiniNetPacketIds.RequestGeneratedAsset, "request type");
        Require(reader.ReadByte() == 2, "retained asset transport v2");
        reader.ReadString();
        int count = reader.ReadByte();
        return Enumerable.Range(0, count).Select(_ => reader.ReadString()).ToArray();
    }

    private static void ScopedRetryReset()
    {
        using var f = new Fixture();
        var second = new GeneratedItemData { Id = "other_item" };
        second.Visual.SpritePath = f.Data.Visual.SpritePath;
        second.VfxManifest.Assets = f.Data.VfxManifest.Assets;
        f.ServerMode();
        f.Client.RegisterRemoteAssetDescriptors(second.Id, f.Server.BuildServerAssetDescriptors(f.Data));
        f.Ensure();
        f.Ensure(data: second);
        Require(f.Requests.Count == 2, "control: both items have pending PNGs");
        byte[] otherRequest = f.Requests.Last();
        f.Client.ResetRetryState(f.Data.Id);
        f.Requests.Clear();
        f.RetryAt(120);
        Require(f.Requests.Count == 1, "one item reset cancelled an unrelated pending roster");
        Require(f.Requests.Peek().SequenceEqual(otherRequest), "unrelated item lost original PNG request identity");
        f.Client.ResetRetryState();
        f.Requests.Clear();
        f.RetryAt(240);
        Require(f.Requests.Count == 0, "global reset did not clear all pending PNGs");
    }
    private static void Roundtrip()
    {
        using var f = new Fixture(2, 512); f.Ensure(); f.DeliverAll(); f.AssertExactFiles();
        Require(f.Sent.Count > 1, "fixture really crossed the chunk boundary");
        Require(f.Client.GetDebugSnapshot().InFlightCount == 0, "complete transfer retired");
    }
    private static void RepeatedEnsures()
    {
        using var f = new Fixture();
        for (uint tick = 0; tick < 120; tick++) { f.Tick = tick; f.Ensure(force: tick % 2 == 0); }
        Require(f.RequestCount == 1, "Ensure resent an in-flight request");
        f.Requests.Clear(); f.RetryAt(120);
        Require(f.Requests.Count == 1, "Ensure postponed the original retry clock");
        Require(RequestFiles(f.Requests.Peek()).Length == 2, "retry omitted sibling PNG");
    }
    private static void RetryBatch()
    {
        using var f = new Fixture(32, 4); f.Ensure(); f.Requests.Clear(); // explicitly lost initial request
        f.RetryAt(120);
        Require(f.Requests.Count == 1, "per-file retries collide with server's item-level cooldown");
        Require(RequestFiles(f.Requests.Peek()).Length == 32, "request did not contain the complete missing roster");
        f.DeliverAll(); f.AssertExactFiles();
    }
    private static void NewSibling()
    {
        using var f = new Fixture(3, 4);
        var first = new GeneratedItemData(); first.Visual.SpritePath = f.Data.Visual.SpritePath;
        f.Ensure(data: first); f.Tick = 30; f.Ensure();
        Require(f.RequestCount == 1, "new siblings sent a competing item request");
        f.Requests.Clear(); f.RetryAt(120);
        Require(f.Requests.Count == 1 && RequestFiles(f.Requests.Peek()).Length == 3, "new siblings did not join the original retry batch");
        f.DeliverAll(); f.AssertExactFiles();
    }
    private static void WorldReset()
    {
        using (var f = new Fixture())
        {
            f.Ensure(); f.AcceptRequests(); f.ServerMode(); f.Server.UpdateTransfers();
            f.Receive(f.Frames.Dequeue());
            Require(f.Client.GetDebugSnapshot().InFlightCount > 0, "partial transfer control");
            Require(f.Server.GetDebugSnapshot().QueuedChunkCount > 0, "queued sender control");
            f.Client.ResetWorldDescriptors(); f.Server.ResetWorldDescriptors();
            Require(f.Client.GetDebugSnapshot().InFlightCount == 0, "previous-world reassembly survives reset");
            Require(f.Server.GetDebugSnapshot().QueuedChunkCount == 0, "previous-world outbound work survives reset");
            f.RetryAt(1200); Require(f.Requests.Count == 0, "previous-world PNG retried against a new peer");
        }
        using (var f = new Fixture(1, 4))
        {
            f.Ensure(); f.DeliverAll(); f.AssertExactFiles();
            f.Client.ResetWorldDescriptors(); f.AssertExactFiles();
        }
    }
    private static void ReplacedManifest()
    {
        using var f = new Fixture(3, 4); f.Ensure(); f.Requests.Clear();
        f.ServerMode(); var retained = f.Server.BuildServerAssetDescriptors(f.Data).Take(2).ToArray();
        f.Client.RegisterRemoteAssetDescriptors(f.Data.Id, retained);
        f.RetryAt(120);
        Require(f.Requests.Count == 1, "one request after manifest replacement");
        Require(RequestFiles(f.Requests.Peek()).Order().SequenceEqual(retained.Select(x => x.FileName).Order()), "removed manifest file is still retried");
    }
    private static void CorruptionRetry()
    {
        using var f = new Fixture(); f.Ensure(); var frames = f.CollectFrames();
        frames[^1][^1] ^= 1;
        foreach (var frame in frames) f.Receive(frame);
        f.AssertNoFiles(); Require(f.Client.GetDebugSnapshot().InFlightCount == 0, "corrupt assembly not retired");
        f.RetryAt(f.Tick + 120);
        Require(f.Requests.Count == 1, "corrupt transfer must retry one whole missing roster");
        f.DeliverAll(); f.AssertExactFiles();
    }
    private static void DuplicateProgress()
    {
        using var f = new Fixture(); f.Ensure(); var frames = f.CollectFrames();
        uint start = f.Tick; f.Receive(frames[0]);
        f.Tick = start + 100; f.Receive(frames[0]);
        f.RetryAt(start + 120);
        Require(f.Requests.Count == 1, "duplicate payload prolonged a stalled transfer");
    }
    private static byte[] BadFrame(byte[] bytes, bool badCount)
    {
        using var reader = new BinaryReader(new MemoryStream(bytes));
        using var output = new MemoryStream(); using var writer = new BinaryWriter(output);
        writer.Write(reader.ReadByte()); writer.Write(reader.ReadByte());
        writer.Write(reader.ReadString()); writer.Write(reader.ReadString());
        writer.Write(reader.ReadInt32()); writer.Write(reader.ReadUInt16());
        ushort count = reader.ReadUInt16(), length = reader.ReadUInt16();
        writer.Write((ushort)(badCount ? count + 1 : count));
        writer.Write((ushort)(badCount ? length : length - 1));
        writer.Write(reader.ReadBytes(badCount ? length : length - 1));
        return output.ToArray();
    }
    private static void InvalidFraming()
    {
        foreach (bool badCount in new[] { true, false })
        {
            using var f = new Fixture(); f.Ensure(); byte[] first = f.CollectFrames()[0];
            f.Receive(BadFrame(first, badCount));
            Require(f.Client.GetDebugSnapshot().InFlightCount == 0, "impossible layout allocated transfer state");
            f.AssertNoFiles(); f.RetryAt(f.Tick + 120);
            Require(f.Requests.Count == 1, "malformed framing suppressed retry");
        }
    }
    private static void ReorderedChunks()
    {
        using var f = new Fixture(); f.Ensure(); var frames = f.CollectFrames();
        f.Receive(frames[^1]); f.Receive(frames[^1]);
        foreach (var frame in frames.AsEnumerable().Reverse()) f.Receive(frame);
        f.AssertExactFiles();
    }
    private static void AdmissionControls()
    {
        using (var f = new Fixture())
        {
            f.Ensure(); var frames = f.CollectFrames();
            f.Client.RegisterRemoteAssetDescriptors(f.Data.Id, f.Expected.Select(entry => new GeneratedAssetWireDescriptor {
                FileName = entry.Key, Length = entry.Value.Length, Sha256 = new string('0', 64),
            }));
            foreach (var frame in frames) f.Receive(frame);
            f.AssertNoFiles(); Require(f.ClientRegistry.RefreshRequests == 1, "descriptor mismatch did not request canonical refresh");
        }
        using (var f = new Fixture())
        {
            f.Ensure(); var frames = f.CollectFrames(); f.Data.RecipeMeta.AssetTransport = "http";
            foreach (var frame in frames) f.Receive(frame);
            f.AssertNoFiles(); Require(f.Client.GetDebugSnapshot().InFlightCount == 0, "HTTP item accepted native chunks");
        }
    }
    private static void Pacing()
    {
        using var f = new Fixture(1, 4); f.ServerMode();
        for (int client = 1; client <= 2; client++)
            for (int packet = 0; packet < 64; packet++) f.Server.EnqueueTransferPacket(client, "probe-" + packet, true, p => p.Write((byte)99));
        for (uint tick = 0; tick < 60; tick++) { f.Tick = tick; f.ServerMode(); f.Server.UpdateTransfers(); }
        Require(f.Sent.Count(x => x.Client == 1) == 17 && f.Sent.Count(x => x.Client == 2) == 17,
            "16 chunks/second plus initial credit must be independently enforced for each client");
    }
    private static void Disposed()
    {
        using var f = new Fixture(); f.Ensure(); var frames = f.CollectFrames();
        f.Server.Dispose(); f.Client.Dispose();
        f.ServerMode(); f.Server.EnqueueTransferPacket(1, "late", true, p => p.Write((byte)99));
        Require(f.Server.GetDebugSnapshot().QueuedChunkCount == 0, "disposed sender resurrected queue");
        f.Receive(frames[0]);
        Require(f.Client.GetDebugSnapshot().InFlightCount == 0, "disposed receiver resurrected assembly");
        f.AssertNoFiles();
    }

    // Independent standards-compliant RGBA fixture builder. Random alpha and RGB
    // produce multiple real PNG chunks without requiring Pillow, tML, or graphics.
    private static byte[] Png(int width, int height, int seed)
    {
        byte[] raw = new byte[height * (1 + width * 4)]; new Random(seed).NextBytes(raw);
        for (int y = 0; y < height; y++) raw[y * (1 + width * 4)] = 0;
        using var compressed = new MemoryStream();
        using (var zlib = new ZLibStream(compressed, CompressionLevel.Fastest, true)) zlib.Write(raw);
        using var output = new MemoryStream();
        output.Write(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 });
        byte[] ihdr = new byte[13]; BinaryPrimitives.WriteInt32BigEndian(ihdr, width);
        BinaryPrimitives.WriteInt32BigEndian(ihdr.AsSpan(4), height); ihdr[8] = 8; ihdr[9] = 6;
        Chunk(output, "IHDR", ihdr); Chunk(output, "IDAT", compressed.ToArray()); Chunk(output, "IEND", Array.Empty<byte>());
        return output.ToArray();
    }
    private static void Chunk(Stream output, string kind, byte[] data)
    {
        byte[] size = new byte[4], type = Encoding.ASCII.GetBytes(kind);
        BinaryPrimitives.WriteInt32BigEndian(size, data.Length); output.Write(size); output.Write(type); output.Write(data);
        uint crc = uint.MaxValue;
        foreach (byte value in type.Concat(data))
        {
            crc ^= value;
            for (int bit = 0; bit < 8; bit++) crc = (crc & 1) != 0 ? 0xedb88320u ^ (crc >> 1) : crc >> 1;
        }
        BinaryPrimitives.WriteUInt32BigEndian(size, crc ^ uint.MaxValue); output.Write(size);
    }
}
