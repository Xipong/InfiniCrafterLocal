#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    [ThreadStatic] private static ParentSourceGraphCache? activeParentSourceGraphCache;

    private static ParentSourceGraphCache SharedParentSourceGraphCache = new(shared: true);
    internal static ParentSourceGraphCache.Statistics ParentSourceCacheStatistics => SharedParentSourceGraphCache.Snapshot();

    private static ParentSourceMethod ReadCompleteSourceMethod(MethodBase method)
    {
        currentParentAnalysis?.ThrowIfCancelled();
        var cache = activeParentSourceGraphCache ?? currentParentAnalysis?.SourceCache;
        if (cache is not null && cache.TryGet(method, out object? retained, out string? refusal))
        {
            if (refusal is not null) throw new NotSupportedException(refusal);
            return (ParentSourceMethod)retained!;
        }
        try
        {
            var body = new ParentSourceMethod(method);
            currentParentAnalysis?.ThrowIfCancelled();
            cache?.Remember(method, body, null, body.Code.Count, body.Blocks.Count);
            return body;
        }
        catch (NotSupportedException error)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            cache?.Remember(method, null, error.Message, 0, 0);
            throw;
        }
    }

    // Synchronous diagnostic scopes retain their thread-local cache. Live craft
    // and export share a bounded, unload-invalidated cache of compiled methods.
    // Entries contain compiled source only, never Item/Player/global instances,
    // live values, parent-specific slices or graph decisions. Complete-method
    // source projections use a separate byte-bounded memo below.
    internal sealed class ParentSourceGraphCache : IDisposable
    {
        internal const int MethodLimit = 256, InstructionLimit = 65_536;
        internal const long MethodByteLimit = 128L * 1024 * 1024;
        private readonly int thread = Environment.CurrentManagedThreadId;
        private readonly bool shared;
        private readonly object gate = new();
        private readonly LinkedList<MethodBase> order = new();
        private long weight;
        // Pure complete-method projections are expensive even after IL/CFG
        // decoding is cached. Store immutable JSON, never graph member indices,
        // live values, native identity slices or mutable caller-owned nodes.
        internal const long ProjectionByteLimit = 16L * 1024 * 1024;
        private readonly Dictionary<(MethodBase Method, string Key), ProjectionEntry> projections = new();
        private readonly LinkedList<(MethodBase Method, string Key)> projectionOrder = new();
        private long projectionBytes;

        internal ParentSourceGraphCache(bool shared = false) => this.shared = shared;
        private sealed record MethodEntry(object? Body, string? Refusal, long Weight, LinkedListNode<MethodBase>? Node);
        private sealed record ProjectionEntry(object Value, long Weight, LinkedListNode<(MethodBase Method, string Key)> Node);
        private readonly Dictionary<MethodBase, MethodEntry> entries = new();
        private int instructions, scopes;
        private bool disposed;
        private long hits, misses, refusalHits, evictions, rejected, projectionHits, projectionMisses, projectionEvictions;

        internal readonly record struct Statistics(long Hits, long Misses, long RefusalHits, long Evictions, long Rejected,
            int Methods, long EstimatedMethodBytes, long ProjectionHits, long ProjectionMisses, long ProjectionEvictions,
            int Projections, long ProjectionBytes);

        internal Statistics Snapshot()
        {
            CheckThread();
            lock (gate) return new(hits, misses, refusalHits, evictions, rejected, entries.Count, weight,
                projectionHits, projectionMisses, projectionEvictions, projections.Count, projectionBytes);
        }

        internal IDisposable Enter()
        {
            CheckThread();
            ObjectDisposedException.ThrowIf(disposed, this);
            var scope = new Scope(this, activeParentSourceGraphCache);
            scopes++;
            activeParentSourceGraphCache = this;
            return scope;
        }

        internal bool TryGet(MethodBase method, out object? body, out string? refusal)
        {
            CheckThread();
            lock (gate)
            {
                if (entries.TryGetValue(method, out var entry))
                {
                    if (entry.Node is not null) { order.Remove(entry.Node); order.AddLast(entry.Node); }
                    hits++; if (entry.Refusal is not null) refusalHits++;
                    body = entry.Body; refusal = entry.Refusal; return true;
                }
                misses++; body = null; refusal = null; return false;
            }
        }

        internal void Remember(MethodBase method, object? body, string? refusal, int codeCount, int blocks)
        {
            CheckThread();
            lock (gate)
            {
                if (disposed || entries.ContainsKey(method)) return;
                if (shared)
                {
                    // Core collections are already built; count their retained
                    // shape, including shared strings only once. Reserve
                    // separately for bounded lazy CFG memos, not B² HashSets.
                    long cost = body is ParentSourceMethod source ? EstimateRetainedBytes(source)
                        : 1024L + codeCount * 256L + Math.Min(4L * 1024 * 1024, blocks * (long)blocks * 80)
                            + (refusal?.Length ?? 0) * (long)sizeof(char);
                    if (cost > MethodByteLimit) { rejected++; return; }
                    while (order.First is { } oldest && (entries.Count >= MethodLimit || weight + cost > MethodByteLimit))
                    {
                        weight -= entries[oldest.Value].Weight;
                        entries.Remove(oldest.Value); order.RemoveFirst(); evictions++;
                    }
                    entries.Add(method, new(body, refusal, cost, order.AddLast(method))); weight += cost;
                }
                else
                {
                    if (entries.Count >= MethodLimit || blocks > 128 || codeCount > 4096 || instructions + codeCount > InstructionLimit)
                    { rejected++; return; }
                    entries.Add(method, new(body, refusal, 0, null)); instructions += codeCount;
                }
            }
        }

        internal bool TryGetProjection(MethodBase method, string key, out string? json)
            => TryGetProjectionValue(method, "raw:" + key, out json);

        internal void RememberProjection(MethodBase method, string key, string json)
            => RememberProjectionValue(method, "raw:" + key, json, json.Length * (long)sizeof(char));

        internal bool TryGetGraphProjection(MethodBase method, string key, out SourceGraphProjection? projection)
            => TryGetProjectionValue(method, "graph:" + key, out projection);

        internal void RememberGraphProjection(MethodBase method, string key, SourceGraphProjection projection)
            => RememberProjectionValue(method, "graph:" + key, projection, projection.RetainedBytes);

        private bool TryGetProjectionValue<T>(MethodBase method, string key, out T? value) where T : class
        {
            CheckThread();
            lock (gate)
            {
                if (projections.TryGetValue((method, key), out var retained) && retained.Value is T typed)
                {
                    projectionOrder.Remove(retained.Node); projectionOrder.AddLast(retained.Node);
                    projectionHits++; value = typed; return true;
                }
                projectionMisses++; value = null; return false;
            }
        }

        private void RememberProjectionValue(MethodBase method, string key, object value, long valueBytes)
        {
            CheckThread();
            long bytes = 256L + key.Length * (long)sizeof(char) + valueBytes;
            if (bytes > ProjectionByteLimit) return;
            lock (gate)
            {
                if (disposed || projections.ContainsKey((method, key))) return;
                while (projectionOrder.First is { } oldest && (projections.Count >= 2048 || projectionBytes + bytes > ProjectionByteLimit))
                {
                    projectionBytes -= projections[oldest.Value].Weight;
                    projections.Remove(oldest.Value); projectionOrder.RemoveFirst(); projectionEvictions++;
                }
                projections.Add((method, key), new(value, bytes, projectionOrder.AddLast((method, key)))); projectionBytes += bytes;
            }
        }

        private static long EstimateRetainedBytes(ParentSourceMethod source)
        {
            // Conservative accounting, not a CLR heap measurement. Capacities
            // account for list backing arrays; dictionary/set allowances include
            // spare buckets. Immutable strings are counted by reference. The
            // reaching-definition solver's intermediate maps are not retained.
            long bytes = 2048 + source.LazyMemoReservationBytes + source.Code.Capacity * 8L
                + source.Statements.Capacity * 8L + source.Values.Count * 80L + source.Blocks.Count * 160L
                + (source.EscapedLocals.Count + source.WrittenArguments.Count + source.CompleteCallPrefixes.Count) * 64L;
            var strings = new HashSet<string>(ReferenceEqualityComparer.Instance);
            void Text(string value) { if (strings.Add(value)) bytes += 32L + value.Length * 2L; }
            foreach (var instruction in source.Code)
            {
                bytes += 64; Text(instruction.Op);
                if (instruction.Arg is string text) Text(text);
                else if (instruction.Arg is int[] targets) bytes += 32L + targets.Length * 4L;
                else if (instruction.Arg is not null) bytes += 32;
            }
            foreach (var value in source.Values.Values)
            {
                bytes += 112L + value.Inputs.Capacity * 8L; Text(value.Id); Text(value.Op);
                if (value.Operand is string operand) Text(operand);
                foreach (string input in value.Inputs) Text(input);
            }
            foreach (var block in source.Blocks.Values)
            {
                bytes += 256L + block.Next.Capacity * 4L + block.Code.Capacity * 8L + block.Exit.Capacity * 8L
                    + block.Next.Count * 32L; // predecessor lists and references
                foreach (string value in block.Exit) Text(value);
            }
            bytes += 40L + source.Unknown.Capacity * 8L;
            foreach (string unknown in source.Unknown) Text(unknown);
            return bytes;
        }

        public void Dispose()
        {
            CheckThread();
            if (scopes != 0) throw new InvalidOperationException("Exit source capture scopes before disposing the cache.");
            lock (gate)
            {
                entries.Clear(); order.Clear(); instructions = 0; weight = 0;
                projections.Clear(); projectionOrder.Clear(); projectionBytes = 0; disposed = true;
            }
        }

        private void CheckThread()
        {
            if (!shared && Environment.CurrentManagedThreadId != thread)
                throw new InvalidOperationException("Source capture cache belongs to one capture thread.");
        }

        private sealed class Scope : IDisposable
        {
            private ParentSourceGraphCache? owner;
            private readonly ParentSourceGraphCache? previous;
            internal Scope(ParentSourceGraphCache owner, ParentSourceGraphCache? previous)
            { this.owner = owner; this.previous = previous; }
            public void Dispose()
            {
                if (owner is null) return;
                owner.CheckThread();
                if (activeParentSourceGraphCache != owner)
                    throw new InvalidOperationException("Source capture scopes must exit in reverse order.");
                activeParentSourceGraphCache = previous;
                owner.scopes--; owner = null;
            }
        }
    }
}
