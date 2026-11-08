using System;
using System.Collections.Concurrent;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static async Task<string> DecodePreparedBody(HttpContent content)
    {
        using var input = new MemoryStream(await content.ReadAsByteArrayAsync());
        using Stream decoded = content.Headers.ContentEncoding.Contains("gzip")
            ? new GZipStream(input, CompressionMode.Decompress) : input;
        using var reader = new StreamReader(decoded, Encoding.UTF8);
        return await reader.ReadToEndAsync();
    }

    private static async Task CraftPreparedTransportReuseAsync()
    {
        var field = typeof(GeneratorClient.PreparedGenerationRequest).GetField("transportPayload", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var cacheField = typeof(GeneratorClient.PreparedGenerationRequest).GetField("cacheOnlyTransportPayload", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var withFlag = typeof(GeneratorClient).GetMethod("WithCacheOnlyFlag", BindingFlags.Static | BindingFlags.NonPublic)!;
        foreach (string json in new[] {
            " {\"unicode\":\"Тест\",\"zero\":0.0,\"false\":false,\"null\":null,\"cacheOnly\":false} ",
            "{\"source\":\"" + new string('x', 3 * 1024 * 1024) + "\",\"array\":[null,0,false,0.0]}"
        })
        {
            var request = new GeneratorClient.PreparedGenerationRequest { PayloadJson = json };
            object? first = null, firstCache = null;
            for (int retry = 0; retry < 3; retry++)
            {
                using var ordinary = request.CreateHttpContent(cacheOnly: false);
                using var cache = request.CreateHttpContent(cacheOnly: true);
                Equal(json, await DecodePreparedBody(ordinary), "every retry has original generation bytes");
                Equal((string)withFlag.Invoke(null, new object[] { json })!, await DecodePreparedBody(cache), "every poll has exact old cache-only bytes");
                Equal("utf-8", ordinary.Headers.ContentType!.CharSet!, "UTF-8 declaration survives body reuse");
                Equal("application/json", cache.Headers.ContentType!.MediaType!, "cache content type survives body reuse");
                if (retry == 0) { first = field.GetValue(request); firstCache = cacheField.GetValue(request); }
                Equal(true, ReferenceEquals(first, field.GetValue(request)), "ordinary immutable bytes reused");
                Equal(true, ReferenceEquals(firstCache, cacheField.GetValue(request)), "poll immutable bytes reused");
                Equal(false, ReferenceEquals(first, firstCache), "normal and cache-only bytes have separate ownership");
                byte[] borrower = await ordinary.ReadAsByteArrayAsync();
                borrower[0] ^= 255;
            }
            request.PayloadJson = "{\"changed\":true}";
            Equal(true, field.GetValue(request) is null && cacheField.GetValue(request) is null, "string replacement invalidates both variants");
            using var replaced = request.CreateHttpContent(false);
            Equal(request.PayloadJson, await DecodePreparedBody(replaced), "replacement never sends stale bytes");
            var node = JsonNode.Parse("{\"node\":[0,false,null]}")!;
            request.SetPayloadNode(node);
            using var nodeContent = request.CreateHttpContent(false);
            string frozen = request.PayloadJson;
            node["node"]![0] = 99;
            Equal(frozen, await DecodePreparedBody(nodeContent), "frozen bytes independent of mutable source tree");
            Equal(true, typeof(GeneratorClient.PreparedGenerationRequest).GetField("payloadNode", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(request) is null,
                "encoded tree released after freezing");
            using var analysis = new GeneratorClient.ParentAnalysis();
            request.Analysis = analysis;
            bool refused = false;
            try { using var blocked = request.CreateHttpContent(false); } catch (InvalidOperationException) { refused = true; }
            Equal(true, refused, "cached body cannot bypass pending-analysis admission guard");
            request.Analysis = null;
        }
    }

    private static void ParentChildSnapshotsOneHandoff()
    {
        using var state = new NativeActorState();
        var method = typeof(GeneratorClient).GetMethod("ReferencedProjectileSnapshots", BindingFlags.Static | BindingFlags.NonPublic)!;
        JsonArray Calls() => new(new JsonObject { ["projectileTypes"] = new JsonArray(-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, int.MaxValue) },
            new JsonObject { ["projectileTypes"] = new JsonArray(1, 3) });
        JsonObject expected = (JsonObject)method.Invoke(null, new object[] { Calls() })!;
        using var analysis = new GeneratorClient.ParentAnalysis();
        var worker = Task.Run(() =>
        {
            using var scope = analysis.Enter();
            return (JsonObject)method.Invoke(null, new object[] { Calls() })!;
        });
        var queue = (ConcurrentQueue<Action>)typeof(GeneratorClient.ParentAnalysis).GetField("mainWork", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        int handoffs = 0;
        var timeout = System.Diagnostics.Stopwatch.StartNew();
        while (!worker.IsCompleted && timeout.Elapsed < TimeSpan.FromSeconds(90))
        {
            if (queue.TryDequeue(out var capture)) { handoffs++; capture(); }
            else Thread.Sleep(1);
        }
        Equal(true, worker.IsCompleted, "child snapshot worker completes");
        JsonObject actual = worker.GetAwaiter().GetResult();
        Equal(10, handoffs, "one callback per unique positive ID including bounded/unregistered identities");
        var resolved = Task.Run(() => analysis.Resolve(actual));
        PumpParentAnalysis(resolved);
        Equal(expected.ToJsonString(), resolved.Result!.ToJsonString(), "combined handoff preserves exact source bytes and order");
        JsonArray references = actual["references"]!.AsArray();
        Equal(8, references.Count(row => row!["profile"] is not null), "profile limit remains eight");
        Equal("single_hop_profile_count_bound", references[^2]!["unresolved"]!.GetValue<string>(), "registered ninth identity remains explicit bound");
        Equal("spawn_projectile_identity_not_registered", references[^1]!["unresolved"]!.GetValue<string>(), "unregistered reason precedes bound");
        Equal("[0,1]", references[2]!["sourceCallIndices"]!.ToJsonString(), "all repeated callsites retained in order");
    }
}
