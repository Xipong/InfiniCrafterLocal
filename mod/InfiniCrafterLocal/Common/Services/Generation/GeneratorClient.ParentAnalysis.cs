#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Capture live data on the caller's game thread, then resolve the source-only
    // portions on the generation/export worker. Markers are internal transfer
    // values: neither HTTP nor dump publication can see an unresolved marker.
    [ThreadStatic] private static ParentAnalysis? currentParentAnalysis;
    internal sealed class ParentAnalysis : IDisposable
    {
        private sealed record DeferredJob(Func<JsonNode?> Analyze, string Label);

        private readonly string markerKey = "$infiniSourceAnalysis:" + Guid.NewGuid().ToString("N");
        internal readonly ParentSourceGraphCache SourceCache = SharedParentSourceGraphCache;
        private readonly List<DeferredJob> jobs = new();
        private readonly Dictionary<int, JsonNode?> completed = new();
        private readonly HashSet<int> omitNull = new();
        private readonly CancellationTokenSource lifetime;
        private static CancellationTokenSource worldLifetime = new();
        private static readonly ConcurrentQueue<Action> mainWork = new();
        private readonly int captureThread = Environment.CurrentManagedThreadId;
        private static bool ProfileJobs => string.Equals(
            Environment.GetEnvironmentVariable("INFINI_PARENT_ANALYSIS_PROFILE"), "1", StringComparison.Ordinal);

        internal ParentAnalysis(CancellationToken cancellation = default)
            => lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellation, worldLifetime.Token);

        internal IDisposable Enter()
        {
            var prior = currentParentAnalysis;
            currentParentAnalysis = this;
            return new ExitScope(() => currentParentAnalysis = prior);
        }

        internal JsonObject Defer(Func<JsonNode?> analyze, bool omitIfNull = false)
        {
            lifetime.Token.ThrowIfCancellationRequested();
            int id = jobs.Count;
            string label = (analyze.Method.DeclaringType?.FullName ?? "<unknown>") + "." + analyze.Method.Name;
            jobs.Add(new DeferredJob(analyze, label));
            if (omitIfNull) omitNull.Add(id);
            return new JsonObject { [markerKey] = id };
        }

        internal JsonNode? Resolve(JsonNode? node, CancellationToken cancellation = default)
        {
            RequireWorker();
            using var registration = cancellation.Register(lifetime.Cancel);
            using var scope = Enter();
            return ResolveNode(node);
        }

        private JsonNode? ResolveNode(JsonNode? node)
        {
            lifetime.Token.ThrowIfCancellationRequested();
            if (node is JsonObject obj)
            {
                if (obj[markerKey] is JsonValue marker)
                {
                    int id = marker.GetValue<int>();
                    if (!completed.TryGetValue(id, out var result))
                    {
                        DeferredJob job = jobs[id];
                        JsonNode? produced;
                        if (ProfileJobs)
                        {
                            long before = GC.GetTotalAllocatedBytes(precise: true);
                            var elapsed = Stopwatch.StartNew();
                            produced = job.Analyze();
                            elapsed.Stop();
                            long allocated = GC.GetTotalAllocatedBytes(precise: true) - before;
                            Console.Error.WriteLine("PARENT_JOB id=" + id
                                + " ms=" + elapsed.Elapsed.TotalMilliseconds.ToString("F3", System.Globalization.CultureInfo.InvariantCulture)
                                + " allocated=" + allocated
                                + " label=" + job.Label);
                        }
                        else produced = job.Analyze();
                        completed[id] = result = ResolveNode(produced);
                    }
                    var copy = result?.DeepClone();
                    // Callers may attach coverage/texture observations to the
                    // placeholder after capture. Keep those exact observations.
                    if (copy is JsonObject resolved)
                        foreach (var property in obj.Where(p => p.Key != markerKey))
                            resolved[property.Key] = ResolveNode(property.Value?.DeepClone());
                    return copy;
                }
                foreach (string key in obj.Select(p => p.Key).ToArray())
                {
                    JsonNode? value = obj[key]; obj.Remove(key);
                    bool optional = value is JsonObject deferred && deferred[markerKey] is JsonValue markerId
                        && omitNull.Contains(markerId.GetValue<int>());
                    JsonNode? resolved = ResolveNode(value);
                    if (resolved is not null || !optional) obj[key] = resolved;
                }
            }
            else if (node is JsonArray array)
                for (int index = 0; index < array.Count; index++)
                {
                    JsonNode? value = array[index]; array[index] = null;
                    array[index] = ResolveNode(value);
                }
            return node;
        }

        // Worker requests contain only IDs/metadata closures; the callback itself
        // executes in Pump, with this capture context restored for child profiles.
        internal T OnMain<T>(Func<T> capture)
        {
            lifetime.Token.ThrowIfCancellationRequested();
            if (Environment.CurrentManagedThreadId == captureThread) return capture();
            var completion = new System.Threading.Tasks.TaskCompletionSource<T>(
                System.Threading.Tasks.TaskCreationOptions.RunContinuationsAsynchronously);
            CancellationToken token = lifetime.Token;
            int state = 0; // queued, running, or cancelled before capture
            using var registration = token.Register(() =>
            {
                if (Interlocked.CompareExchange(ref state, 2, 0) == 0) completion.TrySetCanceled(token);
            });
            mainWork.Enqueue(() =>
            {
                // Once a hook/snapshot has started, its owning thread finishes
                // before the worker can dispose the capture context. Cancellation
                // still prevents its result from reaching HTTP/publication.
                if (Interlocked.CompareExchange(ref state, 1, 0) != 0) return;
                try
                {
                    if (Environment.CurrentManagedThreadId != captureThread)
                        throw new InvalidOperationException("Source snapshots must run on their originating game thread.");
                    using var scope = Enter(); completion.TrySetResult(capture());
                }
                catch (Exception error) { completion.TrySetException(error); }
            });
            return completion.Task.GetAwaiter().GetResult();
        }

        internal static void Pump()
        {
            var elapsed = Stopwatch.StartNew();
            for (int count = 0; count < 16 && elapsed.ElapsedMilliseconds < 2 && mainWork.TryDequeue(out var work); count++) work();
        }

        internal static void Invalidate()
        {
            var previous = Interlocked.Exchange(ref worldLifetime, new CancellationTokenSource());
            previous.Cancel();
            while (mainWork.TryDequeue(out _)) { }
            Interlocked.Exchange(ref SharedParentSourceGraphCache, new ParentSourceGraphCache(shared: true)).Dispose();
            ClearProjectileAttackCaches();
        }

        internal void ThrowIfCancelled() => lifetime.Token.ThrowIfCancellationRequested();
        internal CancellationToken Cancellation => lifetime.Token;

        internal void RequireWorker()
        {
            if (Environment.CurrentManagedThreadId == captureThread)
                throw new InvalidOperationException("Deferred parent analysis must run on a worker.");
        }
        public void Dispose() { lifetime.Cancel(); lifetime.Dispose(); jobs.Clear(); completed.Clear(); omitNull.Clear(); }
        private sealed class ExitScope(Action exit) : IDisposable { public void Dispose() => exit(); }
    }

    private static T SourceSnapshotOnMain<T>(Func<T> capture)
        => currentParentAnalysis is { } analysis ? analysis.OnMain(capture) : capture();
}
