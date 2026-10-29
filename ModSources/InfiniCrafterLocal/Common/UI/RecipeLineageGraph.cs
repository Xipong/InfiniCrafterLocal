#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.UI;

// Read-only, bounded discovery graph. Neither captions nor saved GenerationDepth resolve ancestry.
internal sealed class RecipeLineageGraph
{
    internal const float NodeWidth = 144, NodeHeight = 104;
    internal enum NodeKind { Generated, Native, Missing, Cycle, Truncated }
    internal sealed class Node
    {
        internal string Key = "", Identity = "", Label = "";
        internal GeneratedItemData? Data;
        internal NodeKind Kind;
        internal int Level;
        internal Vector2 Position;
    }
    internal sealed class Edge
    {
        internal int Parent, Child, Multiplicity = 1;
        internal Vector2[] Path = Array.Empty<Vector2>();
    }
    internal Node[] Nodes = Array.Empty<Node>();
    internal Edge[] Edges = Array.Empty<Edge>();
    internal int RootIndex => 0;
    internal float Width, Height;
    internal bool IsTruncated;

    internal static RecipeLineageGraph Build(GeneratedItemData selected, IEnumerable<GeneratedItemData> known, int maxNodes = 512)
    {
        maxNodes = Math.Clamp(maxNodes, 4, 2048);
        var graph = new RecipeLineageGraph();
        string world = selected.RecipeMeta.WorldId;
        var records = RecipeJournalView.Entries(known, world, "", _ => false, false)
            .ToDictionary(d => "generated:" + d.Id, StringComparer.Ordinal);
        // A caller may not use an out-of-world/reference-only selection to reveal its ancestors.
        string rootIdentity = "generated:" + selected.Id;
        if (!records.ContainsKey(rootIdentity))
        {
            graph.Nodes = new[] { new Node { Key = world + "\n" + rootIdentity, Identity = rootIdentity,
                Label = selected.Name, Kind = NodeKind.Missing } };
            graph.Arrange();
            return graph;
        }
        var nodes = new List<Node>();
        var edges = new List<Edge>();
        var byIdentity = new Dictionary<string, int>(StringComparer.Ordinal);
        var visiting = new HashSet<string>(StringComparer.Ordinal);
        var cycleMarkers = new Dictionary<string, int>(StringComparer.Ordinal);
        int cutoff = -1;
        // Numeric native type IDs are session-local; the producer's registered fullname
        // is the stable identity. Only certified syntax is normalized, never captions.
        string IdentityKey(string identity) => RecipeNativeItemResolver.TryGetStableName(identity, out string fullName)
            ? "item:" + fullName : identity;
        int Add(string identity, string label, NodeKind kind, GeneratedItemData? data = null)
        {
            int index = nodes.Count;
            nodes.Add(new Node { Key = world + "\n" + IdentityKey(identity), Identity = identity, Label = label, Kind = kind, Data = data });
            if (kind is not NodeKind.Cycle and not NodeKind.Truncated) byIdentity[IdentityKey(identity)] = index;
            return index;
        }
        int Visit(string identity, string label, int depth)
        {
            if (visiting.Contains(identity))
            {
                // Cut only the corrupt back-edge, retaining the actual shared item node once.
                string marker = "cycle:" + identity;
                if (cycleMarkers.TryGetValue(identity, out int existingCycle)) return existingCycle;
                if (nodes.Count < maxNodes - 1)
                {
                    int cycle = Add(marker, label, NodeKind.Cycle);
                    cycleMarkers.Add(identity, cycle);
                    return cycle;
                }
            }
            else if (byIdentity.TryGetValue(IdentityKey(identity), out int existing)) return existing;
            if (nodes.Count >= maxNodes - 1 || depth >= 512)
            {
                graph.IsTruncated = true;
                if (cutoff < 0) cutoff = Add("truncated:", "…", NodeKind.Truncated);
                return cutoff;
            }
            records.TryGetValue(identity, out var data);
            var kind = data is not null ? NodeKind.Generated
                : identity.StartsWith("item:", StringComparison.Ordinal) ? NodeKind.Native : NodeKind.Missing;
            int current = Add(identity, data?.Name ?? label, kind, data);
            if (data is null) return current;
            visiting.Add(identity);
            for (int slot = 0; slot < 2; slot++)
            {
                string[]? ids = data.RecipeMeta.ParentIdentities;
                string parentIdentity = ids is not null && slot < ids.Length ? ids[slot] ?? "" : "";
                // Unknown slots cannot be merged by caption (even if their captions match).
                if (string.IsNullOrWhiteSpace(parentIdentity)) parentIdentity = "missing:" + identity + ":" + slot;
                int parent = Visit(parentIdentity, slot == 0 ? data.ParentA : data.ParentB, depth + 1);
                var repeated = edges.FirstOrDefault(e => e.Parent == parent && e.Child == current);
                if (repeated is not null)
                {
                    // The cutoff is an aggregate boundary, not one ingredient identity.
                    // Two different omitted parents must never be presented as A + A.
                    if (nodes[parent].Kind != NodeKind.Truncated) repeated.Multiplicity++;
                }
                else edges.Add(new Edge { Parent = parent, Child = current });
                nodes[current].Level = Math.Max(nodes[current].Level, nodes[parent].Level + 1);
            }
            visiting.Remove(identity);
            return current;
        }
        Visit(rootIdentity, selected.Name, 0);
        graph.Nodes = nodes.ToArray(); graph.Edges = edges.ToArray();
        graph.Arrange();
        return graph;
    }

    private sealed class Slot
    {
        internal int Node = -1, Level, Order;
        internal float X;
        internal readonly List<Slot> Below = new(), Above = new();
    }

    private void Arrange()
    {
        const float pitchX = 174, pitchY = 128, padding = 24;
        int top = Nodes.Max(n => n.Level);
        var layers = Enumerable.Range(0, top + 1).Select(_ => new List<Slot>()).ToArray();
        var real = new Slot[Nodes.Length];
        for (int i = 0; i < Nodes.Length; i++)
        {
            real[i] = new Slot { Node = i, Level = Nodes[i].Level };
            layers[real[i].Level].Add(real[i]);
        }
        // Long edges reserve empty slots at every crossed row. A line may cross another
        // line in a non-planar DAG, but never cuts through an unrelated item/caption.
        var routes = new List<Slot>[Edges.Length];
        var sharedLanes = new Dictionary<(int Parent, int Level), Slot>();
        for (int i = 0; i < Edges.Length; i++)
        {
            Edge edge = Edges[i];
            var route = routes[i] = new List<Slot> { real[edge.Parent] };
            for (int level = Nodes[edge.Parent].Level + 1; level < Nodes[edge.Child].Level; level++)
            {
                if (!sharedLanes.TryGetValue((edge.Parent, level), out var dummy))
                {
                    dummy = new Slot { Level = level };
                    sharedLanes.Add((edge.Parent, level), dummy);
                    layers[level].Add(dummy);
                }
                route.Add(dummy);
            }
            route.Add(real[edge.Child]);
            for (int j = 1; j < route.Count; j++)
            {
                if (!route[j - 1].Above.Contains(route[j])) route[j - 1].Above.Add(route[j]);
                if (!route[j].Below.Contains(route[j - 1])) route[j].Below.Add(route[j - 1]);
            }
        }
        void Orders() { foreach (var layer in layers) for (int i = 0; i < layer.Count; i++) layer[i].Order = i; }
        void SortLayer(int level, bool upward)
        {
            var sorted = layers[level].OrderBy(s => {
                var adjacent = upward ? s.Below : s.Above;
                return adjacent.Count == 0 ? s.Order : adjacent.Average(n => (double)n.Order);
            }).ThenBy(s => s.Order).ToList();
            layers[level] = sorted;
            for (int i = 0; i < sorted.Count; i++) sorted[i].Order = i;
        }
        Orders();
        for (int sweep = 0; sweep < 4; sweep++)
        {
            for (int level = 1; level <= top; level++) SortLayer(level, true);
            for (int level = top - 1; level >= 0; level--) SortLayer(level, false);
        }
        Width = layers.Max(l => l.Count) * pitchX + padding * 2;
        Height = top * pitchY + NodeHeight + padding * 2;
        float Y(int level) => padding + NodeHeight / 2 + (top - level) * pitchY;
        foreach (var layer in layers)
        foreach (var slot in layer)
        {
            slot.X = (Width - (layer.Count - 1) * pitchX) / 2 + slot.Order * pitchX;
            if (slot.Node >= 0) Nodes[slot.Node].Position = new Vector2(slot.X, Y(slot.Level));
        }
        for (int i = 0; i < Edges.Length; i++)
        {
            var route = routes[i]; var path = new List<Vector2>();
            for (int j = 0; j < route.Count; j++)
            {
                Slot slot = route[j]; float y = Y(slot.Level);
                if (j > 0) path.Add(new Vector2(slot.X, y + NodeHeight / 2));
                if (j < route.Count - 1)
                {
                    // Leave the real well vertically before entering the inter-row routing
                    // band; a direct diagonal from the well could cut neighboring captions.
                    if (j == 0) path.Add(new Vector2(slot.X, y - 28));
                    path.Add(new Vector2(slot.X, y - NodeHeight / 2));
                }
            }
            Edges[i].Path = path.ToArray();
        }
    }
}
