using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Commands;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void PumpParentAnalysis(Task task)
    {
        var elapsed = System.Diagnostics.Stopwatch.StartNew();
        while (!task.IsCompleted && elapsed.Elapsed < TimeSpan.FromSeconds(90))
        { GeneratorClient.ParentAnalysis.Pump(); Thread.Sleep(1); }
        Equal(true, task.IsCompleted, "source worker completes while the owning thread services snapshots");
        task.GetAwaiter().GetResult();
    }

    private static void ParentAnalysisWorkerSnapshotsAndCancellation()
    {
        int main = Environment.CurrentManagedThreadId, analyzed = 0, captures = 0;
        using var analysis = new GeneratorClient.ParentAnalysis();
        JsonObject root;
        using (analysis.Enter())
        {
            var marker = analysis.Defer(() =>
            {
                Equal(false, main == Environment.CurrentManagedThreadId, "pure source work stays off the capture thread");
                analyzed++;
                return analysis.OnMain(() =>
                {
                    Equal(main, Environment.CurrentManagedThreadId, "dependency snapshot is captured on the game thread");
                    captures++;
                    return new JsonObject { ["value"] = 17, ["child"] = analysis.Defer(() => new JsonObject { ["complete"] = true }) };
                });
            });
            root = new JsonObject { ["a"] = marker, ["b"] = marker.DeepClone() };
            root["a"]!["coverage"] = "captured";
        }
        Equal(0, analyzed, "capture never starts expensive source analysis");
        var worker = Task.Run(() => analysis.Resolve(root));
        PumpParentAnalysis(worker);
        var result = worker.Result!;
        Equal(1, analyzed, "cloned envelope markers resolve one canonical source observation");
        Equal(1, captures, "child live snapshot is not duplicated for envelope projections");
        Equal(17, result["b"]!["value"]!.GetValue<int>(), "complete data reaches both projections");
        Equal(true, result["a"]!["child"]!["complete"]!.GetValue<bool>(), "nested child analysis completes before publication");
        Equal("captured", result["a"]!["coverage"]!.GetValue<string>(), "caller-added observations survive deferred replacement");
        Equal(false, result.ToJsonString().Contains("$infiniSourceAnalysis", StringComparison.Ordinal), "internal markers cannot leak into a resolved payload");

        using var cancellation = new CancellationTokenSource();
        using var cancelled = new GeneratorClient.ParentAnalysis(cancellation.Token);
        using var waiting = new ManualResetEventSlim();
        var pending = Task.Run(() =>
        {
            waiting.Set();
            return cancelled.OnMain(() => { captures++; return 1; });
        });
        Equal(true, waiting.Wait(TimeSpan.FromSeconds(5)), "worker reaches the main-thread handoff");
        cancellation.Cancel();
        bool retired = false;
        try { pending.GetAwaiter().GetResult(); } catch (OperationCanceledException) { retired = true; }
        GeneratorClient.ParentAnalysis.Pump();
        Equal(true, retired, "cancellation releases a worker waiting for a game snapshot");
        Equal(1, captures, "retired callbacks never access live game state");
    }

    private static void ParentDeferredCraftMatchesSynchronousFacts()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var client = new GeneratorClient();
        foreach (int type in new[] { ItemID.SilverWatch, ItemID.MiningPotion, ItemID.TerraBlade, ItemID.Boomstick })
        {
            var item = new Item(type); var second = new Item(ItemID.Wood); var player = new Player();
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            JsonNode expected = JsonNode.Parse(client.Prepare(item, second, player).PayloadJson)!;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            var request = client.PrepareDeferred(item, second, player);
            bool earlyReadRefused = false;
            try { _ = request.PayloadJson; } catch (InvalidOperationException) { earlyReadRefused = true; }
            Equal(true, earlyReadRefused, "main-thread payload access fails immediately instead of blocking or exposing partial facts");
            item.damage += 123; item.stack += 4; player.name = "changed after capture";
            PumpParentAnalysis(Task.Run(request.CompleteAnalysis));
            JsonNode actual = JsonNode.Parse(request.PayloadJson)!;
            Equal(true, JsonNode.DeepEquals(expected, actual), type + " async craft preserves every synchronous source/game field");
            string frozen = request.PayloadJson;
            request.CompleteAnalysis();
            Equal(frozen, request.PayloadJson, "transport retries reuse exactly the completed frozen payload");
        }
    }

    private static void ParentSharedSourceCacheBoundsAndInvalidation()
    {
        MethodInfo method = typeof(GraphConsumer).GetMethod("UpdateLifeRegen")!;
        using var cache = new GeneratorClient.ParentSourceGraphCache(shared: true);
        object body = new();
        cache.Remember(method, body, null, 11890, 1026);
        Equal(true, cache.TryGet(method, out var retained, out _), "large shared hook is cacheable rather than decoded for every item");
        Equal(true, ReferenceEquals(body, retained), "cache retains the exact compiled source");
        MethodInfo[] methods = typeof(string).GetMethods().Concat(typeof(Enumerable).GetMethods()).Distinct().Take(257).ToArray();
        foreach (var candidate in methods) cache.Remember(candidate, null, "exception_regions", 0, 0);
        Equal(false, cache.TryGet(methods[0], out _, out _), "shared cache evicts old entries at its bounded method capacity");
        Equal(true, cache.TryGet(methods[^1], out _, out _), "new source can replace old cache entries without being refused");
        using var session = new GeneratorClient.ParentAnalysis();
        session.SourceCache.Remember(method, body, null, 11890, 1026);
        GeneratorClient.ParentAnalysis.Invalidate();
        Equal(false, session.SourceCache.TryGet(method, out _, out _), "world/mod invalidation releases compiled assembly references");
        session.SourceCache.Remember(method, body, null, 11890, 1026);
        Equal(false, session.SourceCache.TryGet(method, out _, out _), "an old worker cannot repopulate an invalidated source cache");
    }

    private static void RuntimeDumpResolvesSourceBeforePublication()
    {
        string root = Directory.CreateTempSubdirectory("ifc-dump-analysis-").FullName;
        try
        {
            int main = Environment.CurrentManagedThreadId, snapshots = 0;
            // Capture real rows: source graphs/native projectile profiles use the
            // same deferred machinery as live crafting, including child profiles.
            using var state = new NativeActorState();
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            var export = new RuntimeDumpExport(root, 3, 1, type =>
            {
                Equal(main, Environment.CurrentManagedThreadId, "item defaults and tooltip capture remain on the main thread");
                snapshots++;
                return GeneratorClient.ToWireItem(new Item(type == 1 ? ItemID.SilverWatch : ItemID.TerraBlade));
            }, _ => null, DumpTestEnvironment());
            var elapsed = System.Diagnostics.Stopwatch.StartNew();
            while (!export.Completion.IsCompleted && elapsed.Elapsed < TimeSpan.FromSeconds(90))
            { GeneratorClient.ParentAnalysis.Pump(); export.Pump(); Thread.Sleep(1); }
            Equal(true, export.Completion.IsCompleted, "export source analysis finishes with game updates still running");
            var manifest = export.Completion.GetAwaiter().GetResult();
            var rows = File.ReadAllLines(Path.Combine(root, manifest["files"]!["items"]!["path"]!.GetValue<string>()));
            Equal(2, snapshots, "native snapshots are captured exactly once");
            Equal(2, rows.Length, "all captured definitions reach the published pair");
            foreach (string row in rows)
            {
                Equal(false, row.Contains("$infiniSourceAnalysis", StringComparison.Ordinal), "no unresolved transfer markers enter dump JSONL");
                Equal("parent_reachable_compiled_source_graph", JsonNode.Parse(row)!["parentSourceGraph"]!["source"]!.GetValue<string>(), "published rows contain the complete graph projection");
            }
        }
        finally { Directory.Delete(root, true); }
    }

    private static void WaitForQueuedParentSnapshot()
    {
        var queue = (System.Collections.ICollection)typeof(GeneratorClient.ParentAnalysis)
            .GetField("mainWork", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var elapsed = System.Diagnostics.Stopwatch.StartNew();
        while (queue.Count == 0 && elapsed.Elapsed < TimeSpan.FromSeconds(30)) Thread.Sleep(1);
        Equal(true, queue.Count > 0, "source worker is waiting for a game-thread dependency snapshot");
    }

    private static void ParentAnalysisExportCancellationAndWorldRetirement()
    {
        string root = Directory.CreateTempSubdirectory("ifc-dump-source-cancel-").FullName;
        try
        {
            GeneratorClient.ParentAnalysis.Pump();
            InfiniDumpCommand.PublishSnapshot(root, w => w.WriteLine("{\"type\":1}"),
                w => w.WriteLine("{\"type\":1}"), DumpTestEnvironment());
            string manifest = Path.Combine(root, InfiniDumpCommand.DumpManifestName);
            string accepted = File.ReadAllText(manifest);
            int callbacks = 0;
            var export = new RuntimeDumpExport(root, 2, 1, type =>
            {
                var session = (GeneratorClient.ParentAnalysis)typeof(GeneratorClient)
                    .GetField("currentParentAnalysis", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
                return session.Defer(() => session.OnMain(() =>
                { callbacks++; return new JsonObject { ["type"] = type, ["complete"] = true }; }));
            }, _ => null, DumpTestEnvironment());
            export.Pump();
            WaitForQueuedParentSnapshot();
            // Exercise the actual unload/cancel entrypoint, not just a detached
            // token: the export worker owns its unpublished files and sessions.
            Task.Run(export.RequestCancellation).GetAwaiter().GetResult();
            bool cancelled = false;
            try { export.Completion.GetAwaiter().GetResult(); }
            catch (OperationCanceledException) { cancelled = true; }
            GeneratorClient.ParentAnalysis.Pump();
            Equal(true, cancelled, "export cancellation retires a source worker waiting on main");
            Equal(0, callbacks, "retired export never runs queued game callbacks");
            Equal(accepted, File.ReadAllText(manifest), "source-analysis cancellation preserves the previous atomic pair");
            Equal(1, Directory.GetDirectories(Path.Combine(root, "runtime_dump_snapshots")).Length,
                "source-analysis cancellation cleans its unpublished files");

            using var state = new NativeActorState();
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            var request = new GeneratorClient().PrepareDeferred(new Item(ItemID.MiningPotion), new Item(ItemID.Wood), new Player());
            var worker = Task.Run(request.CompleteAnalysis);
            WaitForQueuedParentSnapshot();
            GeneratorClient.ParentAnalysis.Invalidate();
            bool retired = false;
            try { worker.GetAwaiter().GetResult(); } catch (OperationCanceledException) { retired = true; }
            Equal(true, retired, "world retirement cancels a real pending craft source analysis");
            bool payloadRefused = false;
            try { _ = request.PayloadJson; } catch (InvalidOperationException) { payloadRefused = true; }
            Equal(true, payloadRefused, "retired craft can never expose its incomplete transfer payload");
            GeneratorClient.ParentAnalysis.Pump();
        }
        finally { Directory.Delete(root, true); }
    }

    private static void RuntimeDumpWriterExactByteAndRowBounds()
    {
        string root = Directory.CreateTempSubdirectory("ifc-dump-writer-bounds-").FullName;
        try
        {
            Type type = typeof(InfiniDumpCommand).GetNestedType("BoundedDumpWriter", BindingFlags.NonPublic)!;
            StreamWriter Open(string name) => (StreamWriter)Activator.CreateInstance(type,
                BindingFlags.Instance | BindingFlags.NonPublic, null, new object[] { Path.Combine(root, name) }, null)!;
            using (var writer = Open("bytes.jsonl"))
            {
                const string row = "{\"name\":\"я\"}";
                long bytes = System.Text.Encoding.UTF8.GetByteCount(row + writer.NewLine);
                // Model bytes already streamed without allocating/writing 512 MiB.
                // The real writer executes both the exact-boundary and overflow writes.
                type.GetField("bytes", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(writer, InfiniDumpCommand.DumpFileByteLimit - bytes);
                writer.WriteLine(row);
                bool refused = false;
                try { writer.WriteLine("{}"); } catch (InvalidDataException) { refused = true; }
                Equal(true, refused, "UTF-8 byte count admits the exact bound and refuses the next record before write");
            }
            Equal(1, File.ReadAllLines(Path.Combine(root, "bytes.jsonl")).Length, "overflow never writes a partial extra JSONL record");
            using (var writer = Open("rows.jsonl"))
            {
                type.GetField("rows", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(writer, InfiniDumpCommand.DumpRowLimit - 1);
                writer.WriteLine("{}");
                bool refused = false;
                try { writer.WriteLine("{}"); } catch (InvalidDataException) { refused = true; }
                Equal(true, refused, "row count admits the exact bound and rejects the next row");
            }
            Equal(1, File.ReadAllLines(Path.Combine(root, "rows.jsonl")).Length, "row overflow does not append data");
        }
        finally { Directory.Delete(root, true); }
    }
}
