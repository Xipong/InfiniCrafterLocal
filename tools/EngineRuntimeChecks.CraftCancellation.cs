using System;
using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags CraftFields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

    private static void CraftCancellationRetiresAllOwners()
    {
        int oldMode = Terraria.Main.netMode;
        Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
        try
        {
            var owner = new InfiniCraftPlayer();
            var request = new GeneratorClient.PreparedGenerationRequest();
            typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, request);
            typeof(InfiniCraftPlayer).GetMethod("ClearCraft", CraftFields)!.Invoke(owner, null);
            Equal(true, request.CancellationToken.IsCancellationRequested, "ordinary retirement signals the exact request");
            request.Cancel(); // Repeated retirement is harmless and never refunds anything.
            Equal(false, request.FailureIsFatal, "retirement is not a failed recipe");
            Equal(true, new GeneratorClient().GeneratePreparedBlocking(request) is null, "retired request cannot start HTTP");

            Type jobType = typeof(InfiniCraftPlayer).GetNestedType("MultiDevCraftJob", BindingFlags.NonPublic)!;
            Array jobs = (Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", CraftFields)!.GetValue(owner)!;
            foreach (string operation in new[] { "TryCancelExtraServerCraft", "AbortMultiDevCraftsForWorldExit", "InitializeMultiDevCraftState" })
            {
                var requests = new[] { new GeneratorClient.PreparedGenerationRequest(), new GeneratorClient.PreparedGenerationRequest() };
                for (int index = 0; index < 2; index++)
                {
                    object job = Activator.CreateInstance(jobType, nonPublic: true)!;
                    jobType.GetField("Request", CraftFields)!.SetValue(job, requests[index]);
                    jobType.GetField("RequestId", CraftFields)!.SetValue(job, "request-" + index);
                    jobType.GetField("LaneIndex", CraftFields)!.SetValue(job, index + 1);
                    jobs.SetValue(job, index);
                }
                object[]? args = operation == "TryCancelExtraServerCraft" ? new object[] { "request-0", "test cancel" }
                    : operation == "AbortMultiDevCraftsForWorldExit" ? new object[] { false } : null;
                typeof(InfiniCraftPlayer).GetMethod(operation, CraftFields)!.Invoke(owner, args);
                Equal(true, requests[0].CancellationToken.IsCancellationRequested, operation + " retires first lane");
                Equal(operation != "TryCancelExtraServerCraft", requests[1].CancellationToken.IsCancellationRequested,
                    operation + " preserves independently active lane unless all owners retire");
                foreach (var retained in requests) retained.Cancel();
            }
        }
        finally { Terraria.Main.netMode = oldMode; }
    }

    private static void CraftCancellationInterruptsHttpAndRecovery()
        => CraftCancellationInterruptsHttpAndRecoveryAsync().GetAwaiter().GetResult();

    private static async Task CraftCancellationInterruptsHttpAndRecoveryAsync()
    {
        string? oldRecovery = Environment.GetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS");
        string? oldAttempts = Environment.GetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS");
        try
        {
            Environment.SetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS", "90");
            Environment.SetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS", "2");
            foreach (int heldOrdinal in new[] { 1, 2, 3 }) // Initial cache, generation, recovery cache.
            {
                await using var server = new CraftHttpFixture(heldOrdinal);
                var client = new GeneratorClient { Endpoint = server.Endpoint };
                var request = new GeneratorClient.PreparedGenerationRequest();
                Task<GeneratedItemData?> worker = Task.Run(() => client.GeneratePreparedBlocking(request));
                try
                {
                    await server.Held.Task.WaitAsync(TimeSpan.FromSeconds(5));
                    var owner = new InfiniCraftPlayer();
                    typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, request);
                    typeof(InfiniCraftPlayer).GetMethod("ClearCraft", CraftFields)!.Invoke(owner, null);
                    Equal(true, await worker.WaitAsync(TimeSpan.FromSeconds(1)) is null,
                        "retired craft returns while HTTP response is still withheld, phase " + heldOrdinal);
                    Equal(heldOrdinal, server.Requests.Count, "no post-cancellation poll or generation retry");
                    Equal(false, client.IsEndpointCoolingDown, "cancellation does not punish independent lanes");
                    Equal(false, request.FailureIsFatal, "no failure/refund outcome manufactured by HTTP cancellation");
                    server.FatalGeneration = true;
                    server.Release();
                    var independent = new GeneratorClient.PreparedGenerationRequest();
                    Equal(true, await Task.Run(() => client.GeneratePreparedBlocking(independent)).WaitAsync(TimeSpan.FromSeconds(5)) is null,
                        "independent request reaches explicit rejection");
                    Equal(422, independent.FailureStatusCode, "independent lane still reaches HTTP on the same endpoint");
                }
                finally { request.Cancel(); server.Release(); await worker.WaitAsync(TimeSpan.FromSeconds(5)); }
            }

            // Cancellation must also wake the local two-second recovery delay.
            await using var delayServer = new CraftHttpFixture(0);
            var delayClient = new GeneratorClient { Endpoint = delayServer.Endpoint };
            var delayRequest = new GeneratorClient.PreparedGenerationRequest();
            Task<GeneratedItemData?> delayWorker = Task.Run(() => delayClient.GeneratePreparedBlocking(delayRequest));
            try
            {
                await delayServer.RecoveryReplied.Task.WaitAsync(TimeSpan.FromSeconds(5));
                delayRequest.Cancel();
                Equal(true, await delayWorker.WaitAsync(TimeSpan.FromSeconds(1)) is null, "recovery delay is cancellable");
                Equal(3, delayServer.Requests.Count, "recovery cancellation starts no second full generation");
            }
            finally { delayRequest.Cancel(); await delayWorker.WaitAsync(TimeSpan.FromSeconds(5)); }
        }
        finally
        {
            Environment.SetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS", oldRecovery);
            Environment.SetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS", oldAttempts);
        }
    }

    private static void CraftCancellationRetiresMetadataWaiters()
        => CraftCancellationRetiresMetadataWaitersAsync().GetAwaiter().GetResult();

    private static async Task CraftCancellationRetiresMetadataWaitersAsync()
    {
        var data = GeneratedItemData.Placeholder();
        data.Id = "craft-metadata-control"; data.Name = "Craft metadata control"; data.SourceMode = "test_fixture";
        await using var server = new CraftHttpFixture(0) { SuccessJson = data.ToJson(), HoldDiscovery = true };
        var client = new GeneratorClient { Endpoint = server.Endpoint };
        server.HoldDiscovery = false;
        server.DiscoveryJson = "{\"multiplayer\":{\"assetTransport\":\"http\",\"assetPublicBaseUrl\":\"http://192.0.2.44:5055\"}}";
        await Task.Run(() => client.RefreshAssetTransportMetadata()).WaitAsync(TimeSpan.FromSeconds(5));
        server.HoldDiscovery = true;
        var request = new GeneratorClient.PreparedGenerationRequest();
        // Hold the real lock ourselves so the waiter proof is independent of
        // the production discovery request's 1.2-second timeout.
        object metadataLock = typeof(GeneratorClient).GetField("_assetPublicBaseUrlLock", CraftFields)!.GetValue(client)!;
        using (var waiting = new CancellationTokenSource())
        using (var entered = new ManualResetEventSlim())
        {
            Exception? waiterError = null;
            var waiter = new Thread(() => {
                entered.Set();
                try { client.RefreshAssetTransportMetadata(waiting.Token); }
                catch (Exception error) { waiterError = error; }
            });
            Monitor.Enter(metadataLock);
            try
            {
                waiter.Start();
                Equal(true, entered.Wait(TimeSpan.FromSeconds(5)), "second lane enters metadata lookup");
                Equal(true, SpinWait.SpinUntil(() => (waiter.ThreadState & ThreadState.WaitSleepJoin) != 0,
                    TimeSpan.FromSeconds(5)), "second lane waits on the actual shared metadata lock");
                waiting.Cancel();
                Equal(true, waiter.Join(TimeSpan.FromMilliseconds(500)), "metadata lock wait is cancellable");
                Equal(true, waiterError is OperationCanceledException, "waiting lane retires as cancellation");
                Equal(false, request.CancellationToken.IsCancellationRequested, "waiting lane never cancels independent request");
                Equal(1, server.DiscoveryRequests, "waiting lane starts no discovery request beyond accepted observation");
            }
            finally
            {
                waiting.Cancel();
                Monitor.Exit(metadataLock);
                waiter.Join(TimeSpan.FromSeconds(5));
            }
        }
        Task<GeneratedItemData?> worker = Task.Run(() => client.GeneratePreparedBlocking(request));
        try
        {
            await server.Held.Task.WaitAsync(TimeSpan.FromSeconds(5));
            request.Cancel();
            Equal(true, await worker.WaitAsync(TimeSpan.FromSeconds(1)) is null, "post-success metadata HTTP retires with craft");
            Equal("http://192.0.2.44:5055", (string)typeof(GeneratorClient).GetField("_cachedGeneratorAssetPublicBaseUrl", CraftFields)!.GetValue(client)!,
                "cancellation preserves previously accepted metadata");
            Equal("http", (string)typeof(GeneratorClient).GetField("_cachedGeneratorAssetTransport", CraftFields)!.GetValue(client)!,
                "cancellation does not reclassify transport as native");
            Equal("http", client.AssetTransportForSharing(), "cancel preserves accepted published snapshot");
            Equal("http://192.0.2.44:5055", client.AssetBaseUrlForSharing(), "cancel preserves published route");
            Equal(false, client.IsEndpointCoolingDown, "cancelled discovery is not endpoint outage");
            server.HoldDiscovery = false;
            server.Release();
            await Task.Run(() => client.RefreshAssetTransportMetadata()).WaitAsync(TimeSpan.FromSeconds(5));
            Equal(3, server.DiscoveryRequests, "independent refresh owns a fresh uncancelled token");
        }
        finally { request.Cancel(); server.Release(); await worker.WaitAsync(TimeSpan.FromSeconds(5)); }
    }

    private static void CraftCancellationKeepsLiveRetryAndDelivery()
        => CraftCancellationKeepsLiveRetryAndDeliveryAsync().GetAwaiter().GetResult();

    private static async Task CraftCancellationKeepsLiveRetryAndDeliveryAsync()
    {
        string? oldRecovery = Environment.GetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS");
        string? oldAttempts = Environment.GetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS");
        try
        {
            Environment.SetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS", "0");
            Environment.SetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS", "2");
            await using var retryServer = new CraftHttpFixture(0) { RejectSecondGeneration = true };
            var retryClient = new GeneratorClient { Endpoint = retryServer.Endpoint };
            var retryRequest = new GeneratorClient.PreparedGenerationRequest();
            Equal(true, await Task.Run(() => retryClient.GeneratePreparedBlocking(retryRequest)).WaitAsync(TimeSpan.FromSeconds(5)) is null,
                "live transient request retains existing retry");
            Equal("cache,generate,cache,generate", string.Join(",", retryServer.Requests), "exact live retry/cache topology");
            Equal(422, retryRequest.FailureStatusCode, "authoritative rejection still propagates");
            Equal(false, retryRequest.CancellationToken.IsCancellationRequested, "failure does not retire owner early");

            foreach (bool cacheHit in new[] { false, true })
            {
                var data = GeneratedItemData.Placeholder();
                data.Id = "craft-cancellation-control"; data.Name = "Craft cancellation control"; data.SourceMode = "test_fixture";
                await using var successServer = new CraftHttpFixture(0) { SuccessJson = data.ToJson(), CacheHit = cacheHit };
                var successClient = new GeneratorClient { Endpoint = successServer.Endpoint };
                var successRequest = new GeneratorClient.PreparedGenerationRequest();
                var result = await Task.Run(() => successClient.GeneratePreparedBlocking(successRequest)).WaitAsync(TimeSpan.FromSeconds(5));
                Equal(data.Id, result?.Id ?? "", "active request delivers " + (cacheHit ? "cached" : "fresh") + " result");
                Equal(false, successRequest.CancellationToken.IsCancellationRequested, "delivery does not cancel before owner consumes result");
                successRequest.Cancel();
                Equal(data.Id, result!.Id, "retirement leaves already delivered result intact");
            }
        }
        finally
        {
            Environment.SetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS", oldRecovery);
            Environment.SetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS", oldAttempts);
        }
    }

    // Real local HTTP against production GeneratorClient. No model/provider calls.
    private sealed class CraftHttpFixture : IAsyncDisposable
    {
        private readonly TcpListener listener = new(IPAddress.Loopback, 0);
        private readonly CancellationTokenSource stop = new();
        private readonly TaskCompletionSource<bool> release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly Task server;
        internal readonly TaskCompletionSource<bool> Held = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly TaskCompletionSource<bool> RecoveryReplied = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly ConcurrentQueue<string> Requests = new();
        internal string Endpoint { get; }
        internal volatile bool FatalGeneration;
        internal bool RejectSecondGeneration;
        internal string? SuccessJson;
        internal bool CacheHit;
        internal string DiscoveryJson = "{\"multiplayer\":{\"assetTransport\":\"native\",\"assetPublicBaseUrl\":\"\"}}";
        internal int DiscoveryStatus = 200;
        internal int FailureStatus = 422;
        internal string FailureJson = "{\"error\":\"offline_fixture\"}";
        internal volatile bool HoldDiscovery;
        private int discoveryRequests;
        internal int DiscoveryRequests => Volatile.Read(ref discoveryRequests);

        internal CraftHttpFixture(int heldOrdinal)
        {
            listener.Start();
            Endpoint = "http://127.0.0.1:" + ((IPEndPoint)listener.LocalEndpoint).Port + "/combine";
            server = Task.Run(async () => {
                int generations = 0;
                try
                {
                    while (!stop.IsCancellationRequested)
                    {
                        using TcpClient peer = await listener.AcceptTcpClientAsync(stop.Token);
                        await using NetworkStream stream = peer.GetStream();
                        using var reader = new StreamReader(stream, Encoding.UTF8, false, 1024, leaveOpen: true);
                        string? line = await reader.ReadLineAsync(stop.Token);
                        bool discovery = line == "GET /mp_connect.json HTTP/1.1";
                        if (!discovery) Equal("POST /combine HTTP/1.1", line ?? "", "canonical craft HTTP route");
                        int length = 0;
                        while (!string.IsNullOrEmpty(line = await reader.ReadLineAsync(stop.Token)))
                            if (line.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase)) length = int.Parse(line[15..].Trim());
                        if (discovery)
                        {
                            Interlocked.Increment(ref discoveryRequests);
                            bool heldDiscovery = HoldDiscovery;
                            if (heldDiscovery) { Held.TrySetResult(true); await release.Task.WaitAsync(stop.Token); }
                            byte[] bodyBytes = Encoding.UTF8.GetBytes(DiscoveryJson);
                            byte[] metadata = Encoding.ASCII.GetBytes($"HTTP/1.1 {DiscoveryStatus} Fixture\r\nContent-Length: {bodyBytes.Length}\r\nConnection: close\r\n\r\n").Concat(bodyBytes).ToArray();
                            try { await stream.WriteAsync(metadata, stop.Token); }
                            catch (Exception error) when (heldDiscovery && error is IOException or SocketException) { }
                            continue;
                        }
                        if (length < 1 || length > 8192) throw new InvalidDataException("bounded fixture expects ASCII request JSON");
                        char[] body = new char[length];
                        int received = 0;
                        while (received < length)
                        {
                            int count = await reader.ReadAsync(body.AsMemory(received), stop.Token);
                            if (count == 0) throw new EndOfStreamException("incomplete fixture request");
                            received += count;
                        }
                        using var payload = JsonDocument.Parse(new string(body));
                        bool cache = payload.RootElement.TryGetProperty("cacheOnly", out var flag) && flag.GetBoolean();
                        Requests.Enqueue(cache ? "cache" : "generate");
                        int ordinal = Requests.Count;
                        if (!cache) generations++;
                        if (ordinal == heldOrdinal) { Held.TrySetResult(true); await release.Task.WaitAsync(stop.Token); }
                        bool success = SuccessJson is not null && (!cache || CacheHit);
                        int status = success ? 200 : cache ? 404 : FatalGeneration || RejectSecondGeneration && generations > 1 ? FailureStatus : 503;
                        byte[] responseBody = Encoding.UTF8.GetBytes(success ? SuccessJson! : FailureJson);
                        byte[] headers = Encoding.ASCII.GetBytes($"HTTP/1.1 {status} Fixture\r\nContent-Type: application/json\r\nContent-Length: {responseBody.Length}\r\nConnection: close\r\n\r\n");
                        try { await stream.WriteAsync(headers, stop.Token); await stream.WriteAsync(responseBody, stop.Token); await stream.FlushAsync(stop.Token); }
                        catch (Exception error) when (ordinal == heldOrdinal && error is IOException or SocketException) { }
                        if (ordinal == 3) RecoveryReplied.TrySetResult(true);
                    }
                }
                catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
                catch (SocketException) when (stop.IsCancellationRequested) { }
                catch (ObjectDisposedException) when (stop.IsCancellationRequested) { } // Stop may race the next accept on Windows.
            });
        }
        internal void Release() => release.TrySetResult(true);
        public async ValueTask DisposeAsync()
        {
            stop.Cancel(); listener.Stop(); Release();
            try { await server.WaitAsync(TimeSpan.FromSeconds(5)); }
            finally { stop.Dispose(); }
        }
    }
}
