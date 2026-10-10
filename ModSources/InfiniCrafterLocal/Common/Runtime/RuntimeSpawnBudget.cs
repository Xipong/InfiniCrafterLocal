#nullable enable
using System;
using System.Collections.Generic;
using Terraria;

namespace InfiniCrafterLocal.Common.Runtime;

/// <summary>
/// Owner-local spawn accounting. Default ledgers spend a lifetime allowance;
/// explicitly selected pools count pending reservations and living descendants.
/// Nested pools retain every ancestor limit. Peer snapshots never construct one.
/// </summary>
internal sealed class RuntimeSpawnBudget
{
    private readonly int _capacity;
    private readonly bool _concurrent;
    private readonly RuntimeSpawnBudget? _parent;
    private readonly HashSet<RuntimeSpawnLease> _live = new();
    public int Remaining { get; private set; }

    public RuntimeSpawnBudget(int remaining, bool concurrent = false, RuntimeSpawnBudget? parent = null)
    {
        _capacity = Remaining = Math.Max(0, remaining);
        _concurrent = concurrent;
        _parent = parent;
    }

    public int Reserve(int count)
    {
        ReapRetired();
        int granted = Math.Min(Math.Max(0, count), Remaining);
        if (_parent is not null) granted = _parent.Reserve(granted);
        Remaining -= granted;
        return granted;
    }

    // Only unused or cancelled reservations use Return. Successful lifetime
    // spawns are never refunded by death; concurrent occupancy uses its lease.
    public void Return(int count)
    {
        int refunded = Math.Min(Math.Max(0, count), _capacity - Remaining);
        Remaining += refunded;
        _parent?.Return(refunded);
    }

    internal RuntimeSpawnLease TrackLive(Projectile projectile, Func<bool> currentIncarnation)
    {
        var lease = new RuntimeSpawnLease(this, projectile, currentIncarnation);
        Register(lease);
        return lease;
    }

    private void Register(RuntimeSpawnLease lease)
    {
        if (_concurrent) _live.Add(lease);
        _parent?.Register(lease);
    }

    internal void Retire(RuntimeSpawnLease lease)
    {
        if (_concurrent && _live.Remove(lease)) Remaining = Math.Min(_capacity, Remaining + 1);
        _parent?.Retire(lease);
    }

    private void ReapRetired()
    {
        // Native retirement usually invokes OnKill. Also handle active=false
        // and host reuse, so the live cap cannot leak when a hook is bypassed.
        if (_live.Count == 0) return;
        foreach (RuntimeSpawnLease lease in new List<RuntimeSpawnLease>(_live))
            if (!lease.IsLive) lease.Release();
    }
}

internal sealed class RuntimeSpawnLease
{
    private readonly RuntimeSpawnBudget _budget;
    private readonly Projectile _projectile;
    private readonly Func<bool> _currentIncarnation;
    private bool _released;

    internal RuntimeSpawnLease(RuntimeSpawnBudget budget, Projectile projectile, Func<bool> currentIncarnation)
    {
        _budget = budget; _projectile = projectile; _currentIncarnation = currentIncarnation;
    }
    internal bool IsLive => !_released && _projectile.active && _currentIncarnation();
    internal void Release()
    {
        if (_released) return;
        _released = true;
        _budget.Retire(this);
    }
}
