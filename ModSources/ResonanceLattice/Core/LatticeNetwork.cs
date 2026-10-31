#nullable enable
using System.Collections.Generic;
using Microsoft.Xna.Framework;

namespace ResonanceLattice.Core;

/// <summary>
/// A connected component of conductor nodes. Charge is pooled at network level for flow
/// budgeting (sum of member node charges); per-node charge still drives light and sync.
/// </summary>
public sealed class LatticeNetwork
{
    public int Id { get; internal set; }

    public readonly List<LatticeNode> Nodes = new();

    /// <summary>Undirected links between nodes, built during graph rebuild; used for arc rendering.</summary>
    public readonly List<(LatticeNode A, LatticeNode B)> Edges = new();

    /// <summary>Sum of member node charges. O(n) with n bounded by <see cref="LatticeLimits.MaxNodesPerWorld"/>.</summary>
    public float TotalCharge()
    {
        float sum = 0f;
        for (int i = 0; i < Nodes.Count; i++)
            sum += Nodes[i].Charge;
        return sum;
    }

    public float Capacity => Nodes.Count * LatticeLimits.NodeCapacity;

    /// <summary>Charge relative to capacity, clamped to [0, <see cref="LatticeLimits.MaxOverchargeFactor"/>].</summary>
    public float ChargeFraction => Capacity <= 0f ? 0f : MathHelper.Clamp(TotalCharge() / Capacity, 0f, LatticeLimits.MaxOverchargeFactor);

    /// <summary>True while the network holds more than its capacity and will surge.</summary>
    public bool IsSurging => TotalCharge() > Capacity;

    /// <summary>World-space centroid of the network, used for sounds and chat effects.</summary>
    public Vector2 Center()
    {
        if (Nodes.Count == 0)
            return Vector2.Zero;
        Vector2 sum = Vector2.Zero;
        for (int i = 0; i < Nodes.Count; i++)
            sum += Nodes[i].WorldCenter;
        return sum / Nodes.Count;
    }
}
