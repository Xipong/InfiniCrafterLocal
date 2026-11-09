using System;
using System.Reflection;
using System.Collections;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference RawCacheCreateUnrooted(GeneratorClient.ParentAnalysis analysis, MethodBase method, JsonObject program)
    {
        object key = new();
        analysis.RememberRawObservation(key, "motion", program, new[] { method });
        return new WeakReference(key);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference RawCacheFillBudget(GeneratorClient.ParentAnalysis analysis, MethodBase method, JsonObject program, object[] keys)
    {
        object key = new();
        analysis.RememberRawObservation(key, "motion", program, new[] { method });
        for (int i = 0; i < 3; i++) analysis.RememberRawObservation(keys[i], "motion", program, new[] { method });
        analysis.RememberRawObservation(keys[3], "motion", program, new[] { method });
        Equal(false, analysis.TryRawObservation(keys[3], "motion", out _, out _), "total budget initially full");
        var weak = new WeakReference(key);
        GC.KeepAlive(key);
        return weak;
    }

    private static void RawObservationCacheIsolation()
    {
        Equal(true, GeneratorClient.IsDeterministicRawObservationRefusal(new NotSupportedException("connected_source_dependency_count_bound:193>192")), "deterministic dependency bound may be reused");
        Equal(true, GeneratorClient.IsDeterministicRawObservationRefusal(new NotSupportedException("connected_source_expression_work_bound:12001>12000")), "deterministic work bound may be reused");
        Equal(false, GeneratorClient.IsDeterministicRawObservationRefusal(new NotSupportedException("dependency_resolution_failed")), "other refusals stay retryable");
        Equal(false, GeneratorClient.IsDeterministicRawObservationRefusal(new InvalidOperationException("connected_source_dependency_count_bound:193>192")), "other exception types stay retryable");
        using var analysis = new GeneratorClient.ParentAnalysis();
        object body = new(); object other = new();
        MethodBase method = typeof(string).GetMethod(nameof(string.ToString), Type.EmptyTypes)!;
        var original = new JsonObject { ["first"] = 1, ["nested"] = new JsonObject { ["value"] = "a" }, ["last"] = null };
        analysis.RememberRawObservation(body, "motion", original, new[] { method });
        original["first"] = 99;
        Equal(true, analysis.TryRawObservation(body, "motion", out var hit, out var references), "same body and role hit");
        Equal("{\"first\":1,\"nested\":{\"value\":\"a\"},\"last\":null}", hit!.ToJsonString(), "exact initial JSON/order retained");
        Equal(true, references!.Length == 1 && references[0] == method, "references retained");
        references[0] = typeof(object).GetMethod(nameof(ToString), Type.EmptyTypes)!;
        hit["nested"]!["value"] = "mutated";
        Equal(true, analysis.TryRawObservation(body, "motion", out var second, out _), "second hit");
        Equal("a", second!["nested"]!["value"]!.GetValue<string>(), "independent mutable wrappers");
        Equal(true, analysis.TryRawObservation(body, "motion", out _, out var secondReferences) && secondReferences![0] == method,
            "reference arrays cannot mutate cached result");
        Equal(false, analysis.TryRawObservation(other, "motion", out _, out _), "distinct body misses");
        Equal(false, analysis.TryRawObservation(body, "draw", out _, out _), "distinct role misses");
        using var fresh = new GeneratorClient.ParentAnalysis();
        Equal(false, fresh.TryRawObservation(body, "motion", out _, out _), "different request misses");
        using var cancellation = new CancellationTokenSource();
        using var cancelled = new GeneratorClient.ParentAnalysis(cancellation.Token);
        cancellation.Cancel();
        bool threw = false;
        try { cancelled.RememberRawObservation(body, "motion", original, new[] { method }); }
        catch (OperationCanceledException) { threw = true; }
        Equal(true, threw, "cancelled work is not published");
        threw = false;
        try { cancelled.TryRawObservation(body, "motion", out _, out _); }
        catch (OperationCanceledException) { threw = true; }
        Equal(true, threw, "cancelled lookup is refused");
        using var capacity = new GeneratorClient.ParentAnalysis();
        object[] keys = new object[9];
        for (int i = 0; i < keys.Length; i++) keys[i] = new object();
        for (int i = 0; i < keys.Length; i++) capacity.RememberRawObservation(keys[i], "motion", original, new[] { method });
        Equal(true, capacity.TryRawObservation(keys[7], "motion", out _, out _), "eighth entry admitted");
        Equal(false, capacity.TryRawObservation(keys[8], "motion", out _, out _), "ninth entry refused");
        using var bytes = new GeneratorClient.ParentAnalysis();
        var huge = new JsonObject { ["value"] = new string('x', 256 * 1024) };
        bytes.RememberRawObservation(keys[0], "motion", huge, new[] { method });
        Equal(false, bytes.TryRawObservation(keys[0], "motion", out _, out _), "oversized entry refused");
        var quarter = new JsonObject { ["value"] = new string('x', 250000) };
        for (int i = 0; i < 5; i++) bytes.RememberRawObservation(keys[i], "motion", quarter, new[] { method });
        Equal(true, bytes.TryRawObservation(keys[3], "motion", out _, out _), "four entries under total limit admitted");
        Equal(false, bytes.TryRawObservation(keys[4], "motion", out _, out _), "fifth entry over total limit refused");
        var weak = new GeneratorClient.ParentAnalysis();
        WeakReference dead = RawCacheCreateUnrooted(weak, method, original);
        for (int i = 0; i < 4 && dead.IsAlive; i++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
        Equal(false, dead.IsAlive, "cache key does not keep source IR alive");
        // Looking up another identity prunes the dead entry and returns its budget.
        Equal(false, weak.TryRawObservation(keys[0], "motion", out _, out _), "prune probe misses");
        for (int i = 0; i < 8; i++) weak.RememberRawObservation(keys[i], "motion", original, new[] { method });
        Equal(true, weak.TryRawObservation(keys[7], "motion", out _, out _), "dead key frees one of eight slots");
        using var reclaimedBudget = new GeneratorClient.ParentAnalysis();
        WeakReference deadLarge = RawCacheFillBudget(reclaimedBudget, method, quarter, keys);
        for (int i = 0; i < 4 && deadLarge.IsAlive; i++) { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
        Equal(false, deadLarge.IsAlive, "large key is collectible");
        reclaimedBudget.RememberRawObservation(keys[3], "motion", quarter, new[] { method });
        Equal(true, reclaimedBudget.TryRawObservation(keys[3], "motion", out _, out _), "pruning reclaims character budget");
        weak.Dispose();
        var field = typeof(GeneratorClient.ParentAnalysis).GetField("rawObservations", BindingFlags.NonPublic | BindingFlags.Instance)!;
        Equal(0, ((ICollection)field.GetValue(weak)!).Count, "dispose releases entries");
        GC.KeepAlive(keys);
    }
}
