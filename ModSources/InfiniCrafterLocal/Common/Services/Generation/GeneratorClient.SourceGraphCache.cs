#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    [ThreadStatic] private static ParentSourceGraphCache? activeParentSourceGraphCache;

    private static ParentSourceGraphCache SharedParentSourceGraphCache = new(shared: true);

    private static ParentSourceMethod ReadCompleteSourceMethod(MethodBase method)
    {
        var cache = activeParentSourceGraphCache ?? currentParentAnalysis?.SourceCache;
        if (cache is not null && cache.TryGet(method, out object? retained, out string? refusal))
        {
            if (refusal is not null) throw new NotSupportedException(refusal);
            return (ParentSourceMethod)retained!;
        }
        try
        {
            var body = new ParentSourceMethod(method);
            cache?.Remember(method, body, null, body.Code.Count, body.Blocks.Count);
            return body;
        }
        catch (NotSupportedException error)
        {
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
        private readonly int thread = Environment.CurrentManagedThreadId;
        private readonly bool shared;
        private readonly object gate = new();
        private readonly Queue<(MethodBase Method, long Weight)> order = new();
        private long weight;
        // Pure complete-method projections are expensive even after IL/CFG
        // decoding is cached. Store immutable JSON, never graph member indices,
        // live values, native identity slices or mutable caller-owned nodes.
        internal const long ProjectionByteLimit = 16L * 1024 * 1024;
        private readonly Dictionary<(MethodBase Method, string Key), object> projections = new();
        private readonly Queue<((MethodBase Method, string Key) Key, long Weight)> projectionOrder = new();
        private long projectionBytes;

        internal ParentSourceGraphCache(bool shared = false) => this.shared = shared;
        private readonly Dictionary<MethodBase, (object? Body, string? Refusal)> entries = new();
        private int instructions, scopes;
        private bool disposed;

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
                { body = entry.Body; refusal = entry.Refusal; return true; }
                body = null; refusal = null; return false;
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
                    // Account for the immutable value/CFG IR plus the largest
                    // lazy compact postdominator matrix. This is deliberately
                    // conservative, but no longer prices the removed per-cell
                    // HashSet representation and rejects useful large methods.
                    const long limit = 128L * 1024 * 1024;
                    long postdomWords = ((long)blocks + 64L) / 64L;
                    long cost = 4096L + codeCount * 512L + blocks * 1024L
                        + blocks * postdomWords * sizeof(ulong);
                    if (cost > limit) return;
                    while (order.Count > 0 && (entries.Count >= MethodLimit || weight + cost > limit))
                    {
                        var oldest = order.Dequeue(); entries.Remove(oldest.Method); weight -= oldest.Weight;
                    }
                    entries.Add(method, (body, refusal)); order.Enqueue((method, cost)); weight += cost;
                }
                else
                {
                    if (entries.Count >= MethodLimit || blocks > 128 || codeCount > 4096 || instructions + codeCount > InstructionLimit) return;
                    entries.Add(method, (body, refusal)); instructions += codeCount;
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
                if (projections.TryGetValue((method, key), out object? retained) && retained is T typed)
                { value = typed; return true; }
                value = null; return false;
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
                while (projectionOrder.Count > 0 && (projections.Count >= 2048 || projectionBytes + bytes > ProjectionByteLimit))
                {
                    var oldest = projectionOrder.Dequeue();
                    projections.Remove(oldest.Key); projectionBytes -= oldest.Weight;
                }
                projections.Add((method, key), value);
                projectionOrder.Enqueue(((method, key), bytes)); projectionBytes += bytes;
            }
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
