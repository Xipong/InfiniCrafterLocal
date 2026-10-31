#nullable enable
using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Audio;
using Terraria.ID;

namespace ResonanceLattice.Core;

/// <summary>
/// Authoritative simulation: ambient trickle, sink delivery under a flow budget, and
/// overload surges that arc lightning into nearby hostile NPCs. Runs only when
/// <see cref="ResonanceLattice.IsAuthoritative"/>, every <see cref="LatticeLimits.SimIntervalTicks"/>.
/// </summary>
public sealed partial class LatticeWorldSystem
{
    private static void SimulateTick()
    {
        EnsureGraph();
        if (Networks.Count == 0)
            return;

        AmbientTrickle();
        DeliverToSinks();
        HandleSurges();
    }

    /// <summary>Nodes exposed to the sky slowly resonate with daylight.</summary>
    private static void AmbientTrickle()
    {
        if (!Main.dayTime)
            return;
        bool changed = false;
        foreach (LatticeNode node in Nodes.Values)
        {
            if (node.Tile.Y >= Main.worldSurface)
                continue;
            Tile above = Main.tile[node.Tile.X, Math.Max(0, node.Tile.Y - 1)];
            if (above.HasTile && Main.tileSolid[above.TileType])
                continue;
            float before = node.Charge;
            node.Charge = Math.Min(node.Charge + LatticeLimits.AmbientSolarTricklePerTick, LatticeLimits.NodeCapacity);
            if (node.Charge != before)
                changed = true;
        }
        if (changed)
            BumpChargeVersion();
    }

    /// <summary>
    /// Serve registered sinks from each network's pool. Per network the total delivered per
    /// tick is capped by <see cref="LatticeLimits.MaxFlowPerTickPerNetwork"/> and higher
    /// priority sinks are served first.
    /// </summary>
    private static void DeliverToSinks()
    {
        if (Sinks.Count == 0)
            return;

        // Group sink requests by network.
        var byNetwork = new Dictionary<LatticeNetwork, List<(ILatticeSink sink, float request)>>();
        for (int i = Sinks.Count - 1; i >= 0; i--)
        {
            ILatticeSink sink = Sinks[i];
            LatticeNetwork? network = NetworkNearWorldPos(sink.Position, LatticeLimits.LinkRangeTiles * 1.5f);
            if (network is null)
                continue;
            float request = Math.Clamp(sink.RequestCharge(network), 0f, LatticeLimits.MaxSinkRequestPerTick);
            if (request <= 0f)
                continue;
            if (!byNetwork.TryGetValue(network, out var list))
                byNetwork[network] = list = new List<(ILatticeSink, float)>(4);
            list.Add((sink, request));
            if (list.Count > LatticeLimits.MaxSinksPerNetwork)
                break;
        }

        foreach (KeyValuePair<LatticeNetwork, List<(ILatticeSink sink, float request)>> pair in byNetwork)
        {
            LatticeNetwork network = pair.Key;
            List<(ILatticeSink sink, float request)> requests = pair.Value;
            requests.Sort(static (a, b) => b.sink.Priority.CompareTo(a.sink.Priority));
            float budget = LatticeLimits.MaxFlowPerTickPerNetwork;
            foreach ((ILatticeSink sink, float request) in requests)
            {
                if (budget <= 0f)
                    break;
                float delivered = Math.Min(request, budget);
                delivered = DrainNetwork(network, delivered);
                budget -= delivered;
                if (delivered > 0f)
                    sink.OnChargeDelivered(delivered);
            }
        }
    }

    /// <summary>Overcharged networks periodically discharge as lightning into nearby hostile NPCs.</summary>
    private static void HandleSurges()
    {
        for (int n = 0; n < Networks.Count; n++)
        {
            LatticeNetwork network = Networks[n];
            if (!network.IsSurging)
                continue;
            if ((Main.GameUpdateCount + (uint)network.Id) % (uint)LatticeLimits.SurgeIntervalTicks != 0u)
                continue;

            int hits = 0;
            for (int i = 0; i < Main.maxNPCs && hits < LatticeLimits.MaxSurgeTargetsPerPulse; i++)
            {
                NPC npc = Main.npc[i];
                if (!npc.active || npc.friendly || npc.townNPC || npc.dontTakeDamage)
                    continue;
                if (NearestNode(npc.Center, LatticeLimits.SurgeRadiusTiles) is not LatticeNode node || node.NetworkId != network.Id)
                    continue;
                int direction = npc.Center.X >= network.Center().X ? 1 : -1;
                npc.SimpleStrikeNPC(LatticeLimits.SurgeDamage, direction);
                SpawnArcDust(node.WorldCenter, npc.Center, 12);
                hits++;
            }

            if (hits > 0)
            {
                Vector2 center = network.Center();
                SoundEngine.PlaySound(SoundID.Thunder, center);
                DrainNetwork(network, network.Capacity * LatticeLimits.SurgeDrainFraction);
                foreach (LatticeNode node in network.Nodes)
                    if (Main.rand.NextBool(3))
                        SpawnArcDust(node.WorldCenter, node.WorldCenter + new Vector2(0, -24f), 4);
            }
        }
    }

    private static void SpawnArcDust(Vector2 from, Vector2 to, int count)
    {
        for (int i = 0; i < count; i++)
        {
            Vector2 pos = Vector2.Lerp(from, to, Main.rand.NextFloat());
            Dust dust = Dust.NewDust(pos, 0, 0, DustID.Electric, 0f, 0f, 100, default, 1.2f);
            dust.velocity = Main.rand.NextVector2Circular(2f, 2f);
            dust.noGravity = true;
        }
    }
}
