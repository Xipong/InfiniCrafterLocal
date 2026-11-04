#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    [ThreadStatic] private static ParentSourceGraphCache? activeParentSourceGraphCache;

    // An export owns this cache; it is not a process-wide cache of collectible
    // mod assemblies. Enter only while capturing a batch on the owning thread.
    // Entries contain compiled source only, never Item/Player/global instances,
    // live values, JSON projections, parent-specific slices or graph decisions.
    internal sealed class ParentSourceGraphCache : IDisposable
    {
        internal const int MethodLimit = 256, InstructionLimit = 65_536;
        private readonly int thread = Environment.CurrentManagedThreadId;
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
            if (entries.TryGetValue(method, out var entry))
            { body = entry.Body; refusal = entry.Refusal; return true; }
            body = null; refusal = null; return false;
        }

        internal void Remember(MethodBase method, object? body, string? refusal, int codeCount, int blocks)
        {
            CheckThread();
            // Large methods still use the canonical analyzer, just not the cache.
            // The block limit also bounds its lazily memoized CFG sets.
            if (disposed || entries.ContainsKey(method) || entries.Count >= MethodLimit
                || blocks > 128 || codeCount > 4096 || instructions + codeCount > InstructionLimit) return;
            entries.Add(method, (body, refusal));
            instructions += codeCount;
        }

        public void Dispose()
        {
            CheckThread();
            if (scopes != 0) throw new InvalidOperationException("Exit source capture scopes before disposing the cache.");
            entries.Clear(); instructions = 0; disposed = true;
        }

        private void CheckThread()
        {
            if (Environment.CurrentManagedThreadId != thread)
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
