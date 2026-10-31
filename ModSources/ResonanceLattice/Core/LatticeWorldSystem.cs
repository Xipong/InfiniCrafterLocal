#nullable enable
using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using ResonanceLattice.Content.Tiles;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace ResonanceLattice.Core;

/// <summary>
/// Authoritative owner of the lattice: node registry, network graph, simulation, persistence,
/// networking and rendering. Split into partials:
/// Graph (union-find + spatial hash), Sim (flow/surge), Persistence (world save + join sync),
/// Net (incremental packets), Render (arc drawing).
/// </summary>
public sealed partial class LatticeWorldSystem : ModSystem
{
    internal static readonly Dictionary<Point16, LatticeNode> Nodes = new();
    internal static readonly List<LatticeNetwork> Networks = new();
    internal static IReadOnlyList<LatticeNetwork> NetworksView => Networks;
    internal static event Action? TopologyChanged;

    private static readonly List<ILatticeSink> Sinks = new();
    private static Dictionary<(int cx, int cy), List<LatticeNode>> _buckets = new();

    private static bool _topologyDirty = true;
    private static int _topologyVersion;
    private static int _lastSentTopologyVersion = -1;
    private static int _simTimer;
    private static int _syncTimer;
    private static int _reconcileTimer;
    private static int _chargeVersion;
    private static int _lastSyncedChargeVersion = -1;
    private static readonly Dictionary<int, int> _lastInjectRequestTick = new();
    private static readonly Dictionary<Point16, float> _pendingCharges = new();

    // ------------------------------------------------------------------
    // Lifecycle
    // ------------------------------------------------------------------

    public override void OnWorldLoad() => ResetState();

    public override void ClearWorld() => ResetState();

    public override void OnWorldUnload() => ResetState();

    public override void Unload() => ResetState();

    private static void ResetState()
    {
        Nodes.Clear();
        Networks.Clear();
        Sinks.Clear();
        _buckets = new Dictionary<(int, int), List<LatticeNode>>();
        _topologyDirty = true;
        _topologyVersion = 0;
        _lastSentTopologyVersion = -1;
        _simTimer = 0;
        _syncTimer = 0;
        _reconcileTimer = 0;
        _chargeVersion = 0;
        _lastSyncedChargeVersion = -1;
        _lastInjectRequestTick.Clear();
        _pendingCharges.Clear();
    }

    /// <summary>After world load the tiles exist, so the initial registry is a one-time full scan.</summary>
    public override void PostWorldLoad()
    {
        FullScan();
        foreach (KeyValuePair<Point16, float> pair in _pendingCharges)
            if (Nodes.TryGetValue(pair.Key, out LatticeNode? node))
                node.Charge = pair.Value;
        _pendingCharges.Clear();
        _topologyDirty = true;
    }

    // ------------------------------------------------------------------
    // Node registry (runs on every machine; idempotent, derived from tiles)
    // ------------------------------------------------------------------

    internal static bool NotifyNodePlaced(Point16 tile)
    {
        if (Nodes.ContainsKey(tile))
            return true;
        if (Nodes.Count >= LatticeLimits.MaxNodesPerWorld)
            return false;
        Nodes.Add(tile, new LatticeNode(tile));
        MarkTopologyDirty();
        return true;
    }

    internal static void NotifyNodeRemoved(Point16 tile)
    {
        if (Nodes.Remove(tile))
            MarkTopologyDirty();
    }

    private static void MarkTopologyDirty()
    {
        _topologyDirty = true;
        _topologyVersion++;
    }

    internal static void BumpChargeVersion()
    {
        if (ResonanceLattice.IsAuthoritative)
            _chargeVersion++;
    }

    private void FullScan()
    {
        int crystalType = ModContent.TileType<ResonantCrystalTile>();
        for (int x = 0; x < Main.maxTilesX; x++)
        {
            for (int y = 0; y < Main.maxTilesY; y++)
            {
                Tile tile = Main.tile[x, y];
                if (tile.HasTile && tile.TileType == crystalType)
                    NotifyNodePlaced(new Point16(x, y));
            }
        }
    }

    internal static void EnsureDiscoveredAround(Vector2 worldCenter, float radiusTiles)
    {
        int crystalType = ModContent.TileType<ResonantCrystalTile>();
        float radiusPx = radiusTiles * 16f;
        int x0 = Math.Clamp((int)((worldCenter.X - radiusPx) / 16f), 0, Main.maxTilesX - 1);
        int x1 = Math.Clamp((int)((worldCenter.X + radiusPx) / 16f), 0, Main.maxTilesX - 1);
        int y0 = Math.Clamp((int)((worldCenter.Y - radiusPx) / 16f), 0, Main.maxTilesY - 1);
        int y1 = Math.Clamp((int)((worldCenter.Y + radiusPx) / 16f), 0, Main.maxTilesY - 1);
        for (int x = x0; x <= x1; x++)
        {
            for (int y = y0; y <= y1; y++)
            {
                Tile tile = Main.tile[x, y];
                if (tile.HasTile && tile.TileType == crystalType)
                    NotifyNodePlaced(new Point16(x, y));
            }
        }
    }

    // ------------------------------------------------------------------
    // Queries
    // ------------------------------------------------------------------

    internal static LatticeNetwork? NetworkAtTile(Point16 tile)
    {
        EnsureGraph();
        return Nodes.TryGetValue(tile, out LatticeNode? node) && node.NetworkId >= 0 && node.NetworkId < Networks.Count
            ? Networks[node.NetworkId]
            : null;
    }

    internal static LatticeNetwork? NetworkNearWorldPos(Vector2 worldPos, float maxDistanceTiles)
    {
        EnsureGraph();
        LatticeNode? best = NearestNode(worldPos, maxDistanceTiles);
        return best is not null && best.NetworkId >= 0 && best.NetworkId < Networks.Count ? Networks[best.NetworkId] : null;
    }

    internal static LatticeNode? NearestNode(Vector2 worldPos, float maxDistanceTiles)
    {
        EnsureGraph();
        float maxDist = maxDistanceTiles * 16f;
        LatticeNode? best = null;
        float bestDist = maxDist;
        foreach (LatticeNode node in QueryBucketRadius((int)(worldPos.X / 16f), (int)(worldPos.Y / 16f), maxDistanceTiles + 1f))
        {
            float d = Vector2.Distance(worldPos, node.WorldCenter);
            if (d <= bestDist)
            {
                bestDist = d;
                best = node;
            }
        }
        return best;
    }

    // ------------------------------------------------------------------
    // Charge transfer (authoritative only)
    // ------------------------------------------------------------------

    internal static float InjectChargeAt(Vector2 worldPos, float amount)
    {
        LatticeNetwork? network = NetworkNearWorldPos(worldPos, LatticeLimits.LinkRangeTiles * 1.5f);
        if (network is null)
            return 0f;
        LatticeNode? node = NearestNode(worldPos, LatticeLimits.LinkRangeTiles * 1.5f);
        if (node is null)
            return 0f;
        float cap = LatticeLimits.NodeCapacity * LatticeLimits.MaxOverchargeFactor;
        float applied = Math.Min(amount, cap - node.Charge);
        if (applied <= 0f)
            return 0f;
        node.Charge += applied;
        ClampNetworkOvercharge(network);
        BumpChargeVersion();
        return applied;
    }

    internal static float ConsumeChargeAt(Vector2 worldPos, float amount)
    {
        LatticeNetwork? network = NetworkNearWorldPos(worldPos, LatticeLimits.LinkRangeTiles * 1.5f);
        if (network is null || amount <= 0f)
            return 0f;
        return DrainNetwork(network, amount);
    }

    /// <summary>Drain up to <paramref name="amount"/> from a network, proportionally from all nodes.</summary>
    internal static float DrainNetwork(LatticeNetwork network, float amount)
    {
        float pool = network.TotalCharge();
        if (pool <= 0f)
            return 0f;
        float drained = Math.Min(amount, pool);
        for (int i = 0; i < network.Nodes.Count; i++)
        {
            LatticeNode node = network.Nodes[i];
            node.Charge -= drained * (node.Charge / pool);
            if (node.Charge < 0f)
                node.Charge = 0f;
        }
        BumpChargeVersion();
        return drained;
    }

    private static void ClampNetworkOvercharge(LatticeNetwork network)
    {
        float pool = network.TotalCharge();
        float cap = network.Capacity * LatticeLimits.MaxOverchargeFactor;
        if (pool <= cap)
            return;
        float scale = cap / pool;
        for (int i = 0; i < network.Nodes.Count; i++)
            network.Nodes[i].Charge *= scale;
    }

    // ------------------------------------------------------------------
    // Sinks
    // ------------------------------------------------------------------

    internal static void RegisterSink(ILatticeSink sink)
    {
        if (!Sinks.Contains(sink))
            Sinks.Add(sink);
    }

    internal static void UnregisterSink(ILatticeSink sink) => Sinks.Remove(sink);

    // ------------------------------------------------------------------
    // Per-tick driver
    // ------------------------------------------------------------------

    public override void PostUpdateWorld()
    {
        if (ResonanceLattice.IsAuthoritative)
        {
            _reconcileTimer++;
            if (_reconcileTimer >= LatticeLimits.ReconcileIntervalTicks)
            {
                _reconcileTimer = 0;
                Reconcile();
            }

            _simTimer++;
            if (_simTimer >= LatticeLimits.SimIntervalTicks)
            {
                _simTimer = 0;
                SimulateTick();
            }

            _syncTimer++;
            if (_syncTimer >= LatticeLimits.ChargeSyncIntervalTicks)
            {
                _syncTimer = 0;
                SyncTick();
            }
        }
        else
        {
            // Clients only keep the graph fresh for rendering/light.
            EnsureGraph();
        }
    }

    /// <summary>
    /// Periodic bounded reconciliation: drop nodes whose tile vanished through a path the
    /// hooks did not see, and discover nodes placed near active players.
    /// </summary>
    private static void Reconcile()
    {
        int crystalType = ModContent.TileType<ResonantCrystalTile>();
        List<Point16>? stale = null;
        foreach (KeyValuePair<Point16, LatticeNode> pair in Nodes)
        {
            Tile tile = Framing.GetTileSafely(pair.Key.X, pair.Key.Y);
            if (!tile.HasTile || tile.TileType != crystalType)
                (stale ??= new List<Point16>()).Add(pair.Key);
        }
        if (stale is not null)
            foreach (Point16 p in stale)
                NotifyNodeRemoved(p);

        for (int i = 0; i < Main.maxPlayers; i++)
        {
            Player player = Main.player[i];
            if (player.active && !player.dead)
                EnsureDiscoveredAround(player.Center, LatticeLimits.PlayerDiscoveryRadiusTiles);
        }
    }
}
