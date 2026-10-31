#nullable enable
using System.Collections.Generic;
using System.IO;
using Terraria.DataStructures;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace ResonanceLattice.Core;

/// <summary>
/// World-save lifecycle: node charges persist in the world file via TagCompound, and the
/// node set itself is re-derived from the actual tiles on load (vanilla already persists
/// tiles). <see cref="NetSend"/>/<see cref="NetReceive"/> piggyback on tModLoader's world-data
/// sync so a client that joins mid-session receives the full lattice immediately.
/// </summary>
public sealed partial class LatticeWorldSystem
{
    private const string NodesTagKey = "latticeNodes";

    public override void SaveWorldData(TagCompound tag)
    {
        var list = new List<TagCompound>(Nodes.Count);
        foreach (LatticeNode node in Nodes.Values)
        {
            var entry = new TagCompound
            {
                ["x"] = node.Tile.X,
                ["y"] = node.Tile.Y,
                ["c"] = node.Charge,
            };
            list.Add(entry);
        }
        tag[NodesTagKey] = list;
    }

    public override void LoadWorldData(TagCompound tag)
    {
        _pendingCharges.Clear();
        if (!tag.ContainsKey(NodesTagKey))
            return;
        foreach (TagCompound entry in tag.GetList<TagCompound>(NodesTagKey))
        {
            var key = new Point16(entry.GetInt("x"), entry.GetInt("y"));
            _pendingCharges[key] = entry.GetFloat("c");
        }
    }

    public override void NetSend(BinaryWriter writer)
    {
        // Join sync: full node list with authoritative charge values.
        writer.Write(Nodes.Count);
        foreach (LatticeNode node in Nodes.Values)
        {
            writer.Write((short)node.Tile.X);
            writer.Write((short)node.Tile.Y);
            writer.Write(node.Charge);
        }
    }

    public override void NetReceive(BinaryReader reader)
    {
        int count = reader.ReadInt32();
        if (count < 0 || count > LatticeLimits.MaxNodesPerWorld)
            return;
        for (int i = 0; i < count; i++)
        {
            var tile = new Point16(reader.ReadInt16(), reader.ReadInt16());
            float charge = reader.ReadSingle();
            if (Nodes.TryGetValue(tile, out LatticeNode? node))
                node.Charge = charge;
            else if (Nodes.Count < LatticeLimits.MaxNodesPerWorld)
            {
                var created = new LatticeNode(tile) { Charge = charge };
                Nodes.Add(tile, created);
                MarkTopologyDirty();
            }
        }
    }
}
