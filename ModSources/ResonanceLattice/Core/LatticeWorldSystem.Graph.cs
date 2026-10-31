#nullable enable
using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria.DataStructures;

namespace ResonanceLattice.Core;

/// <summary>Graph rebuild: spatial hash + BFS union into <see cref="LatticeNetwork"/> components.</summary>
public sealed partial class LatticeWorldSystem
{
    private static void EnsureGraph()
    {
        if (_topologyDirty)
            RebuildGraph();
    }

    private static void RebuildGraph()
    {
        _topologyDirty = false;
        Networks.Clear();
        _buckets.Clear();

        foreach (LatticeNode node in Nodes.Values)
        {
            node.NetworkId = -1;
            var key = (node.Tile.X >> 4, node.Tile.Y >> 4);
            if (!_buckets.TryGetValue(key, out List<LatticeNode>? bucket))
                _buckets[key] = bucket = new List<LatticeNode>(4);
            bucket.Add(node);
        }

        float linkRange = LatticeLimits.LinkRangeTiles * 16f;
        var queue = new Queue<LatticeNode>();
        int nextId = 0;
        foreach (LatticeNode seed in Nodes.Values)
        {
            if (seed.NetworkId != -1)
                continue;
            var network = new LatticeNetwork { Id = nextId++ };
            seed.NetworkId = network.Id;
            queue.Enqueue(seed);
            while (queue.Count > 0)
            {
                LatticeNode current = queue.Dequeue();
                network.Nodes.Add(current);
                foreach (LatticeNode neighbor in QueryBucketRadius(current.Tile.X, current.Tile.Y, LatticeLimits.LinkRangeTiles + 1f))
                {
                    if (neighbor.NetworkId != -1)
                        continue;
                    if (Vector2.Distance(current.WorldCenter, neighbor.WorldCenter) > linkRange)
                        continue;
                    neighbor.NetworkId = network.Id;
                    network.Edges.Add((current, neighbor));
                    queue.Enqueue(neighbor);
                }
            }
            Networks.Add(network);
        }

        TopologyChanged?.Invoke();
    }

    /// <summary>All nodes in buckets overlapping the given tile radius (Euclidean filter is done by callers).</summary>
    private static IEnumerable<LatticeNode> QueryBucketRadius(int tileX, int tileY, float radiusTiles)
    {
        int reach = (int)Math.Ceiling(radiusTiles / 16f) + 1;
        int cx = tileX >> 4;
        int cy = tileY >> 4;
        for (int bx = cx - reach; bx <= cx + reach; bx++)
        {
            for (int by = cy - reach; by <= cy + reach; by++)
            {
                if (_buckets.TryGetValue((bx, by), out List<LatticeNode>? bucket))
                    foreach (LatticeNode node in bucket)
                        yield return node;
            }
        }
    }
}
