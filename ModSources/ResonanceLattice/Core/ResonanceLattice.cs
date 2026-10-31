#nullable enable
using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;

namespace ResonanceLattice.Core;

/// <summary>
/// Public, reusable facade of the Resonance Lattice gameplay library.
///
/// Any content — ModItem, ModProjectile, ModNPC, ModPlayer, ModSystem or another mod — can:
/// <list type="bullet">
/// <item>feed charge into the grid with <see cref="InjectCharge"/> (safe to call on a client:
/// it becomes a validated server request),</item>
/// <item>draw charge out with <see cref="ConsumeCharge"/> or by registering an <see cref="ILatticeSink"/>,</item>
/// <item>query networks with <see cref="NetworkNearWorldPos"/> / <see cref="NetworkAtTile"/>,</item>
/// <item>track topology via <see cref="OnTopologyChanged"/>.</item>
/// </list>
/// All world-state mutation happens on the authoritative side (single player or server);
/// clients only render and send bounded requests.
/// </summary>
public static class ResonanceLattice
{
    /// <summary>True on single player and on the server — the only places lattice state may change.</summary>
    public static bool IsAuthoritative => Main.netMode != NetmodeID.MultiplayerClient;

    /// <summary>All currently known networks (read-only view; rebuilt on topology change).</summary>
    public static IReadOnlyList<LatticeNetwork> Networks => LatticeWorldSystem.NetworksView;

    /// <summary>Raised after the node set or network topology changed (all machines).</summary>
    public static event Action? OnTopologyChanged
    {
        add => LatticeWorldSystem.TopologyChanged += value;
        remove => LatticeWorldSystem.TopologyChanged -= value;
    }

    /// <summary>Called by conductor tile hooks when a node tile appears. Idempotent.</summary>
    public static bool NotifyNodePlaced(Point16 tile) => LatticeWorldSystem.NotifyNodePlaced(tile);

    /// <summary>Called by conductor tile hooks when a node tile disappears. Idempotent.</summary>
    public static void NotifyNodeRemoved(Point16 tile) => LatticeWorldSystem.NotifyNodeRemoved(tile);

    /// <summary>Scan a bounded box around a world position and register any conductor tiles found.</summary>
    public static void EnsureDiscoveredAround(Vector2 worldCenter, float radiusTiles)
        => LatticeWorldSystem.EnsureDiscoveredAround(worldCenter, radiusTiles);

    /// <summary>Network of the node at this tile, or null.</summary>
    public static LatticeNetwork? NetworkAtTile(Point16 tile) => LatticeWorldSystem.NetworkAtTile(tile);

    /// <summary>Network with a node within <paramref name="maxDistanceTiles"/> of the world position, or null.</summary>
    public static LatticeNetwork? NetworkNearWorldPos(Vector2 worldPos, float maxDistanceTiles)
        => LatticeWorldSystem.NetworkNearWorldPos(worldPos, maxDistanceTiles);

    /// <summary>
    /// Inject charge into the network nearest to <paramref name="worldPos"/>.
    /// On the authoritative side this applies immediately and returns the applied amount.
    /// On a multiplayer client this sends a rate-limited, server-validated request and returns 0.
    /// Returns 0 when no network is in range.
    /// </summary>
    public static float InjectCharge(Vector2 worldPos, float amount)
    {
        if (amount <= 0f)
            return 0f;
        if (!IsAuthoritative)
        {
            LatticeNet.SendInjectRequest(worldPos, amount);
            return 0f;
        }
        return LatticeWorldSystem.InjectChargeAt(worldPos, amount);
    }

    /// <summary>
    /// Consume charge from the network nearest to <paramref name="worldPos"/>.
    /// Authoritative side only; returns the amount actually removed.
    /// </summary>
    public static float ConsumeCharge(Vector2 worldPos, float amount)
        => IsAuthoritative ? LatticeWorldSystem.ConsumeChargeAt(worldPos, amount) : 0f;

    /// <summary>Register a charge consumer. Call <see cref="UnregisterSink"/> when the entity dies/unloads.</summary>
    public static void RegisterSink(ILatticeSink sink) => LatticeWorldSystem.RegisterSink(sink);

    public static void UnregisterSink(ILatticeSink sink) => LatticeWorldSystem.UnregisterSink(sink);
}
