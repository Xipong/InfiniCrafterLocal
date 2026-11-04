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
    // live values, JSON projections, parent-specific slices or graph decisions.
    internal sealed class ParentSourceGraphCache : IDisposable
    {
        internal const int MethodLimit = 256, InstructionLimit = 65_536;
        private readonly int thread = Environment.CurrentManagedThreadId;
        private readonly bool shared;
        private readonly object gate = new();
        private readonly Queue<(MethodBase Method, long Weight)> order = new();
        private long weight;
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
                    // Account for values plus worst-case lazy CFG sets. Large mod
                    // hooks remain cacheable; eviction only changes work, never facts.
                    const long limit = 128L * 1024 * 1024;
                    long cost = 1024L + codeCount * 256L + blocks * (long)blocks * 80;
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

        public void Dispose()
        {
            CheckThread();
            if (scopes != 0) throw new InvalidOperationException("Exit source capture scopes before disposing the cache.");
            lock (gate) { entries.Clear(); order.Clear(); instructions = 0; weight = 0; disposed = true; }
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
