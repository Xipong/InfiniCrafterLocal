using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static bool SegmentHitsCardInterior(Vector2 start, Vector2 end, Vector2 center)
    {
        // Slab clipping against the full label+icon reservation, slightly inset to allow borders.
        float min = 0, max = 1;
        bool Clip(float origin, float delta, float low, float high)
        {
            if (Math.Abs(delta) < 0.00001f) return origin > low && origin < high;
            float a = (low - origin) / delta, b = (high - origin) / delta;
            if (a > b) (a, b) = (b, a);
            min = Math.Max(min, a); max = Math.Min(max, b);
            return min < max;
        }
        return Clip(start.X, end.X - start.X, center.X - RecipeLineageGraph.NodeWidth / 2 + .01f,
                center.X + RecipeLineageGraph.NodeWidth / 2 - .01f)
            && Clip(start.Y, end.Y - start.Y, center.Y - RecipeLineageGraph.NodeHeight / 2 + .01f,
                center.Y + RecipeLineageGraph.NodeHeight / 2 - .01f);
    }

    private static void RecipeLineageUsesExactBoundedDag()
    {
        GeneratedItemData Entry(string id, params string[] parents)
        {
            var data = GeneratedItemData.Placeholder(); data.Id = id; data.Name = "Same caption";
            data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = "17";
            data.RecipeMeta.ParentIdentities = parents;
            data.ParentA = data.ParentB = "Same caption";
            return data;
        }
        var a = Entry("a", "item:Terraria:Wood:9", "item:Terraria:StoneBlock:3");
        var b = Entry("b", "generated:a", "item:Terraria:Wood:9");
        var root = Entry("root", "generated:a", "generated:b");
        var foreign = Entry("a", "item:Terraria:DirtBlock:2", "item:Terraria:DirtBlock:2");
        foreign.RecipeMeta.WorldId = "18";
        root.RecipeMeta.GenerationDepth = 999;
        a.RecipeMeta.GenerationDepth = 800;
        var graph = RecipeLineageGraph.Build(root, new[] { foreign, root, b, a });
        Equal(5, graph.Nodes.Length, "shared generated and native ancestors deduplicate by exact identity");
        Equal(3, graph.Nodes[graph.RootIndex].Level, "rank derives from actual ancestry");
        Equal(2, graph.Nodes.Count(n => n.Kind == RecipeLineageGraph.NodeKind.Native && n.Level == 0), "native roots form bottom layer");
        Equal(false, graph.Nodes.Any(n => n.Identity.Contains("DirtBlock")), "foreign world ancestry never leaks");
        var nativeAlias = Entry("native-alias", "item:Terraria/Wood:900", "item:Terraria:Wood:9");
        var stableNative = RecipeLineageGraph.Build(nativeAlias, new[] { nativeAlias });
        Equal(2, stableNative.Nodes.Length, "registered native fullname survives transport syntax and session ID changes");
        Equal(2, stableNative.Edges.Single().Multiplicity, "stable native A plus A retains both inputs");
        var repeat = Entry("repeat", "generated:a", "generated:a");
        var doubled = RecipeLineageGraph.Build(repeat, new[] { repeat, a });
        Equal(2, doubled.Edges.Single(e => e.Child == doubled.RootIndex).Multiplicity, "A plus A retains quantity two on shared edge");
        var missing = Entry("missing", "generated:not-known", "generated:a");
        var unknown = RecipeLineageGraph.Build(missing, new[] { missing });
        Equal(2, unknown.Nodes.Count(n => n.Kind == RecipeLineageGraph.NodeKind.Missing), "same caption does not resolve undiscovered identities");
        var slots = Entry("slots");
        Equal(2, RecipeLineageGraph.Build(slots, new[] { slots }).Nodes.Count(n => n.Kind == RecipeLineageGraph.NodeKind.Missing), "missing parent slots remain distinct");
        var cycleA = Entry("cycle-a", "generated:cycle-b", "item:Terraria:Wood:9");
        var cycleB = Entry("cycle-b", "generated:cycle-a", "item:Terraria:Wood:9");
        var cycle = RecipeLineageGraph.Build(cycleA, new[] { cycleA, cycleB });
        Equal(1, cycle.Nodes.Count(n => n.Kind == RecipeLineageGraph.NodeKind.Cycle), "corrupt back edge visibly terminates");
        Equal(1, cycle.Nodes.Count(n => n.Identity == "generated:cycle-a"), "cycle does not duplicate actual item");
        var limited = RecipeLineageGraph.Build(root, new[] { root, a, b }, 4);
        Equal(true, limited.IsTruncated && limited.Nodes.Length <= 4, "budget remains bounded and visible");
        Equal(1, limited.Nodes.Count(n => n.Kind == RecipeLineageGraph.NodeKind.Truncated), "one truthful cutoff marker");
        var cutoffLeaf = Entry("cutoff-leaf", "item:Terraria:Wood:9", "item:Terraria:StoneBlock:3");
        var cutoffMiddle = Entry("cutoff-middle", "generated:cutoff-leaf", "item:Terraria:DirtBlock:2");
        var cutoffRoot = Entry("cutoff-root", "generated:cutoff-middle", "item:Terraria:Gel:23");
        var aggregate = RecipeLineageGraph.Build(cutoffRoot, new[] { cutoffRoot, cutoffMiddle, cutoffLeaf }, 4);
        int cutoffLeafIndex = Array.FindIndex(aggregate.Nodes, n => n.Identity == "generated:cutoff-leaf");
        Equal(1, aggregate.Edges.Single(e => e.Child == cutoffLeafIndex).Multiplicity,
            "different omitted ingredients do not become false A plus A quantity");
        var reordered = RecipeLineageGraph.Build(root, new[] { a, b, root });
        Equal(string.Join(";", graph.Nodes.Select(n => n.Identity + n.Position)), string.Join(";", reordered.Nodes.Select(n => n.Identity + n.Position)), "layout deterministic independent of discovery enumeration");
        var oneUnknown = RecipeLineageGraph.Build(missing, new[] { missing, a });
        Equal(1, oneUnknown.Nodes.Count(n => n.Kind == RecipeLineageGraph.NodeKind.Missing), "missing branch does not block healthy branch");
        var diamond = Entry("diamond", "generated:b", "generated:other");
        var other = Entry("other", "generated:a", "item:Terraria:StoneBlock:3");
        var shared = RecipeLineageGraph.Build(diamond, new[] { diamond, other, a, b });
        Equal(1, shared.Nodes.Count(n => n.Identity == "generated:a"), "diamond grandparent represented once");
        Equal(false, shared.Nodes.Any(n => n.Kind == RecipeLineageGraph.NodeKind.Cycle), "diamond is not a cycle");
        var chain = Enumerable.Range(0, 600).Select(i => Entry("chain-" + i,
            i == 0 ? "item:Terraria:StoneBlock:3" : "generated:chain-" + (i - 1), "item:Terraria:Wood:9")).ToArray();
        var deep = RecipeLineageGraph.Build(chain[79], chain);
        Equal(80, deep.Nodes[0].Level, "deep chain ranks from edges, not saved depth");
        Equal(82, deep.Nodes.Length, "deep chain reuses native ancestor without duplicate nodes");
        Equal(false, deep.IsTruncated, "ordinary deep ancestry is complete");
        var boundedDeep = RecipeLineageGraph.Build(chain[599], chain, 2048);
        Equal(true, boundedDeep.IsTruncated, "extreme depth stops visibly before exhausting stack");
        Equal(true, boundedDeep.Nodes.Length <= 2048, "extreme depth respects node cap");
        foreach (var candidate in new[] { graph, doubled, unknown, cycle, limited, oneUnknown, shared, deep, aggregate })
        {
            foreach (var edge in candidate.Edges)
            {
                Equal(true, candidate.Nodes[edge.Parent].Level < candidate.Nodes[edge.Child].Level, "every displayed edge ascends");
                Equal(true, edge.Path.Length >= 2, "all edges have explicit routed geometry");
                Equal(candidate.Nodes[edge.Parent].Position.Y - 28, edge.Path[0].Y,
                    "outgoing connection touches actual well instead of floating above it");
                Equal(candidate.Nodes[edge.Child].Position.Y + RecipeLineageGraph.NodeHeight / 2, edge.Path[^1].Y,
                    "incoming connection preserves caption reservation");
                for (int segment = 1; segment < edge.Path.Length; segment++)
                for (int node = 0; node < candidate.Nodes.Length; node++)
                {
                    if (node == edge.Parent || node == edge.Child) continue;
                    var center = candidate.Nodes[node].Position;
                    Equal(false, SegmentHitsCardInterior(edge.Path[segment - 1], edge.Path[segment], center),
                        "routed links never pass through unrelated cards or captions");
                }
            }
            for (int i = 0; i < candidate.Nodes.Length; i++)
            for (int j = i + 1; j < candidate.Nodes.Length; j++)
            {
                Vector2 d = candidate.Nodes[i].Position - candidate.Nodes[j].Position;
                Equal(false, Math.Abs(d.X) < RecipeLineageGraph.NodeWidth && Math.Abs(d.Y) < RecipeLineageGraph.NodeHeight, "node caption reservations do not overlap");
            }
        }
    }
}
