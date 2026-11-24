using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;

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
        foreach (string json in new[] {
            " {\"unicode\":\"Тест\",\"zero\":0.0,\"false\":false,\"null\":null,\"cacheOnly\":false} ",
            "{\"source\":\"" + new string('x', 3 * 1024 * 1024) + "\",\"array\":[null,0,false,0.0]}"
        })
        {
            var request = new GeneratorClient.PreparedGenerationRequest { PayloadJson = json };
            for (int retry = 0; retry < 3; retry++)
            {
                using var ordinary = request.CreateHttpContent(cacheOnly: false);
                using var cache = request.CreateHttpContent(cacheOnly: true);
                Equal(json, await DecodePreparedBody(ordinary), "every retry has original generation bytes");
                var polled = JsonNode.Parse(await DecodePreparedBody(cache))!.AsObject();
                var original = JsonNode.Parse(json)!.AsObject();
                Equal(true, polled["cacheOnly"]!.GetValue<bool>(), "cache transport explicitly selects cache-only");
                original.Remove("cacheOnly");
                polled.Remove("cacheOnly");
                Equal(true, JsonNode.DeepEquals(original, polled), "each poll preserves all other values");
                Equal("utf-8", ordinary.Headers.ContentType!.CharSet!, "UTF-8 declaration survives body reuse");
                Equal("application/json", cache.Headers.ContentType!.MediaType!, "cache content type survives body reuse");
                byte[] borrower = await ordinary.ReadAsByteArrayAsync();
                borrower[0] ^= 255;
            }
            request.PayloadJson = "{\"changed\":true}";
            using var replaced = request.CreateHttpContent(false);
            Equal("{\"changed\":true}", await DecodePreparedBody(replaced), "replacement never sends stale generation bytes");
            using var replacedPoll = request.CreateHttpContent(true);
            var currentPoll = JsonNode.Parse(await DecodePreparedBody(replacedPoll))!.AsObject();
            Equal(true, JsonNode.DeepEquals(JsonNode.Parse("{\"changed\":true,\"cacheOnly\":true}"), currentPoll),
                "replacement never sends stale cache-only fields");
            var node = JsonNode.Parse("{\"node\":[0,false,null]}")!;
            request.SetPayloadNode(node);
            using var nodeContent = request.CreateHttpContent(false);
            string frozen = request.PayloadJson;
            node["node"]![0] = 99;
            Equal(frozen, await DecodePreparedBody(nodeContent), "frozen bytes independent of mutable source tree");
            using var nodeRetry = request.CreateHttpContent(false);
            Equal(frozen, await DecodePreparedBody(nodeRetry), "retry remains independent of later source-tree mutation");
            using var analysis = new GeneratorClient.ParentAnalysis();
            request.Analysis = analysis;
            bool refused = false;
            try { using var blocked = request.CreateHttpContent(false); } catch (InvalidOperationException) { refused = true; }
            Equal(true, refused, "cached body cannot bypass pending-analysis admission guard");
            request.Analysis = null;
        }
    }

    private static void ParentChildSnapshotsWorkerParity()
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
        PumpParentAnalysis(worker);
        var resolved = Task.Run(() => analysis.Resolve(worker.GetAwaiter().GetResult()));
        PumpParentAnalysis(resolved);
        JsonObject actual = resolved.Result!.AsObject();
        Equal(expected.ToJsonString(), actual.ToJsonString(), "worker and synchronous observation deliver exact source bytes");
        JsonArray references = actual["references"]!.AsArray();
        Equal(8, references.Count(row => row!["profile"] is not null), "profile limit remains eight");
        Equal("projectile_reference_profile_count_bound", references[^2]!["unresolved"]!.GetValue<string>(), "registered ninth identity remains explicit bound");
        Equal("spawn_projectile_identity_not_registered", references[^1]!["unresolved"]!.GetValue<string>(), "unregistered reason precedes bound");
        Equal("[0,1]", references[2]!["sourceCallIndices"]!.ToJsonString(), "all repeated callsites retained in order");
    }
}
