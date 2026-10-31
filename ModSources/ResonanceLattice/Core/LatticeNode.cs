#nullable enable
using Microsoft.Xna.Framework;
using Terraria.DataStructures;

namespace ResonanceLattice.Core;

/// <summary>
/// One conductor tile in the world. Charge is stored per node so that light, arcs and
/// sync all read the same value; network-level pools are just sums over member nodes.
/// </summary>
public sealed class LatticeNode
{
    public Point16 Tile { get; }

    /// <summary>Aether charge currently held by this node.</summary>
    public float Charge;

    /// <summary>Id of the <see cref="LatticeNetwork"/> this node belongs to, or -1 while the graph is dirty.</summary>
    public int NetworkId = -1;

    public LatticeNode(Point16 tile)
    {
        Tile = tile;
    }

    /// <summary>World-space center of the tile (16x16 tiles).</summary>
    public Vector2 WorldCenter => new(Tile.X * 16f + 8f, Tile.Y * 16f + 8f);
}
