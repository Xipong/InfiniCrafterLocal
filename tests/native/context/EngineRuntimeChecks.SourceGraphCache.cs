using System;
using System.Collections;
using System.Reflection;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentSourceGraphSkipsUnneededConsumerScan()
    {
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(type, nonPublic: true)!;
        var consumers = (IList)type.GetField("consumers", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!;
        consumers.Add((typeof(GraphConsumer), typeof(GlobalNPC)));
        type.GetField("rosterRead", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(graph, true);
        var result = (JsonObject)type.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
        Equal(0, (int)type.GetField("scanCount", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!,
            "an empty watched field set must not decompile unrelated mod consumers");
        Equal(0, result["edges"]!.AsArray().Count, "no missing field can manufacture a consumer edge");
    }

    private static void ParentSourceGraphCacheReusesOnlyCompiledSource()
    {
        GraphSourceExecutions = 0;
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        MethodInfo read = graphType.GetMethod("Read", BindingFlags.Instance | BindingFlags.NonPublic)!;
        object Graph() => Activator.CreateInstance(graphType, nonPublic: true)!;
        MethodInfo method = typeof(GraphConsumer).GetMethod("UpdateLifeRegen")!;
        MethodInfo refused = typeof(GraphTryItem).GetMethod("UseItem")!;
        object? Read(object graph, MethodInfo target) => read.Invoke(graph, new object[] { target });
        JsonObject Capture(Type owner)
        {
            object graph = Graph();
            graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new object[]
                { owner, typeof(ModItem), new System.Collections.Generic.HashSet<string>(new[] { "UseItem" }), "parent_ModItem", "event_signature" });
            return (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
        }
        string ordinary = Capture(typeof(GraphItem)).ToJsonString();
        string ordinaryRefused = Capture(typeof(GraphTryItem)).ToJsonString();
        object first = Read(Graph(), method)!;
        // Inject an invalid CFG edge only into this fresh, uncached analyzer to
        // exercise exceptional memoization deterministically, without running
        // thousands of iterations or any gameplay body.
        Type sourceType = first.GetType();
        var blocks = (IDictionary)sourceType.GetField("Blocks", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(first)!;
        object branch = blocks.Values.Cast<object>().First(block =>
            ((IList)block.GetType().GetField("Next", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(block)!).Count > 1);
        var successors = (IList)branch.GetType().GetField("Next", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(branch)!;
        int original = (int)successors[0]!;
        int start = (int)branch.GetType().GetField("Start", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(branch)!;
        MethodInfo control = sourceType.GetMethod("ControlledRegion", BindingFlags.Instance | BindingFlags.NonPublic)!;
        successors[0] = int.MaxValue;
        bool failed = false;
        try { control.Invoke(first, new object[] { start }); }
        catch (TargetInvocationException error) when (error.InnerException is System.Collections.Generic.KeyNotFoundException) { failed = true; }
        Equal(true, failed, "fixture interrupts the control-dependency solver");
        Equal<object?>(null, sourceType.GetField("postdominators", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(first),
            "failed CFG solve never publishes partial memoized facts");
        successors[0] = original;
        control.Invoke(first, new object[] { start });
        Equal(false, ReferenceEquals(first, Read(Graph(), method)), "live captures are not retained globally");
        using var cache = new GeneratorClient.ParentSourceGraphCache();
        using (cache.Enter())
        {
            Equal(ordinary, Capture(typeof(GraphItem)).ToJsonString(), "cached capture preserves complete canonical graph projection");
            Equal(ordinary, Capture(typeof(GraphItem)).ToJsonString(), "second projection cannot mutate cached source");
            Equal(ordinaryRefused, Capture(typeof(GraphTryItem)).ToJsonString(), "cached exception refusal preserves graph evidence");
            object cached = Read(Graph(), method)!;
            Equal(true, ReferenceEquals(cached, Read(Graph(), method)), "dump rows reuse complete compiled source without re-decoding");
            Equal(true, cache.TryGet(method, out object? retained, out string? reason), "successful source is cached");
            Equal(true, ReferenceEquals(cached, retained), "cache retains only the analyzer body");
            object sliced = Graph();
            var slices = (IDictionary)graphType.GetField("nativeSlices", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(sliced)!;
            object code = cached.GetType().GetField("Code", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(cached)!;
            slices.Add(method, Activator.CreateInstance(code.GetType())!);
            var next = (IDictionary)graphType.GetField("nativeNext", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(sliced)!;
            next.Add(method, new System.Collections.Generic.Dictionary<int, int>());
            Equal<object?>(null, Read(sliced, method), "parent-specific native slices cannot borrow a cached full method");
            Equal<string?>(null, reason, "valid source is not labeled unavailable");
            object refusalGraph = Graph();
            Equal<object?>(null, Read(refusalGraph, refused), "exception region remains unavailable");
            Equal(true, cache.TryGet(refused, out object? missing, out reason), "stable refusal is cached rather than thrown for every item");
            Equal<object?>(null, missing, "unsupported body is never invented");
            Equal("exception_regions", reason, "exact refusal reason survives cache");
            object secondRefusalGraph = Graph();
            Equal<object?>(null, Read(secondRefusalGraph, refused), "cached refusal remains unavailable");
            var failures = (IDictionary)graphType.GetField("readFailures", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(secondRefusalGraph)!;
            Equal("exception_regions", (string?)failures[refused], "each graph reports cached refusal explicitly");
            object boundGraph = Graph();
            graphType.GetField("scanCount", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(boundGraph, 1024);
            Equal<object?>(null, Read(boundGraph, method), "cache never bypasses per-parent source scan admission");
        }
        Equal(false, cache.TryGet(typeof(GraphIdentityDepthItem).GetMethod("OnHitNPC")!, out _, out _), "unread source has no inferred cache result");
        Equal(false, ReferenceEquals(first, Read(Graph(), method)), "leaving scope restores ordinary uncached capture");
        bool rejected = Task.Run(() =>
        {
            try { using var invalid = cache.Enter(); return false; }
            catch (InvalidOperationException) { return true; }
        }).GetAwaiter().GetResult();
        Equal(true, rejected, "mutable lazy CFG cache never crosses capture threads");
        cache.Dispose();
        Equal(false, cache.TryGet(method, out _, out _), "disposing export releases retained method/assembly references");
        bool disposed = false;
        try { using var invalid = cache.Enter(); }
        catch (ObjectDisposedException) { disposed = true; }
        Equal(true, disposed, "completed export cache cannot be re-entered");
        using var bounded = new GeneratorClient.ParentSourceGraphCache();
        bounded.Remember(method, new object(), null, 4097, 1);
        Equal(false, bounded.TryGet(method, out _, out _), "oversized method is not retained");
        bounded.Remember(method, new object(), null, 1, 129);
        Equal(false, bounded.TryGet(method, out _, out _), "large quadratic CFG cache is not retained");
        MethodInfo[] methods = typeof(string).GetMethods().Take(17).ToArray();
        foreach (MethodInfo candidate in methods) bounded.Remember(candidate, new object(), null, 4096, 1);
        Equal(true, bounded.TryGet(methods[15], out _, out _), "source cache admits exact aggregate IL boundary");
        Equal(false, bounded.TryGet(methods[16], out _, out _), "source cache refuses aggregate IL overflow without refusing capture");
        using var entries = new GeneratorClient.ParentSourceGraphCache();
        MethodInfo[] many = typeof(string).GetMethods().Concat(typeof(Enumerable).GetMethods()).Distinct().Take(257).ToArray();
        Equal(257, many.Length, "fixture provides enough distinct source identities");
        foreach (MethodInfo candidate in many) entries.Remember(candidate, null, "exception_regions", 0, 0);
        Equal(true, entries.TryGet(many[255], out _, out _), "exact entry bound is admitted");
        Equal(false, entries.TryGet(many[256], out _, out _), "even zero-instruction refusals obey retention bound");
        Equal(0, GraphSourceExecutions, "reading/refusing source never invokes game hooks");
    }
}
