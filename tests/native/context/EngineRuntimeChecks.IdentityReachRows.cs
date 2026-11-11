using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static (object Selection, Dictionary<int, List<int>> Graph, int[] Nodes) IdentityReachFixture(int count)
    {
        object body = IndexedSource(IndexedGraphFixture());
        var blocks = (IDictionary)SparseLocalMember(body, "Blocks");
        Type blockType = blocks.Values.Cast<object>().First().GetType();
        blocks.Clear();
        int[] nodes = Enumerable.Range(0, count).Select(index => index == 0 ? 0 : 1001 + (count - index) * 17).ToArray();
        var graph = nodes.ToDictionary(node => node, _ => new List<int>());
        for (int index = 0; index + 1 < count; index++)
        {
            if (count > 3 && index == count - 2) continue;
            graph[nodes[index]].Add(nodes[index + 1]);
            graph[nodes[index]].Add(nodes[index + 1]);
            if (index % 7 == 0) graph[nodes[index]].Add(nodes[index]);
            if (index > 2 && index % 7 == 3) graph[nodes[index]].Add(nodes[index - 3]);
            if (index + 2 < count - 1 && index % 5 == 0) graph[nodes[index]].Add(nodes[index + 2]);
        }
        foreach (int node in nodes)
        {
            object block = Activator.CreateInstance(blockType, nonPublic: true)!;
            blockType.GetField("Start", IndexedFlags)!.SetValue(block, node);
            ((List<int>)SparseLocalMember(block, "Next")).AddRange(graph[node]);
            blocks.Add(node, block);
        }
        Type selectionType = typeof(GeneratorClient).GetNestedType("AttackIdentitySelection", BindingFlags.NonPublic)!;
        object selection = Activator.CreateInstance(selectionType, IndexedFlags, null,
            new object[] { body, 0, 0, false }, null)!;
        return (selection, graph, nodes);
    }

    // The old traversal is intentionally retained only as a test oracle. Its
    // stack and Work count define the existing refusal threshold, while the
    // queue oracle above checks membership independently of visitation order.
    private static (HashSet<int> Set, int Work) IdentityReachScanningOracle(
        Dictionary<int, List<int>> graph, Dictionary<int, int> selected, int start)
    {
        int work = 0;
        var reached = new HashSet<int>(); var pending = new Stack<int>(); pending.Push(start);
        while (pending.Count > 0)
        {
            work++; int block = pending.Pop(); if (!reached.Add(block)) continue;
            foreach (int next in selected.TryGetValue(block, out int chosen) ? new[] { chosen } : graph[block].ToArray()) pending.Push(next);
        }
        return (reached, work);
    }

    private static void IdentityReachRowsMatchScanningOracle()
    {
        foreach (int count in new[] { 1, 63, 64, 65, 127, 128, 129, 2048 })
        {
            var (selection, graph, nodes) = IdentityReachFixture(count);
            Type type = selection.GetType();
            var current = type.GetMethod("CurrentReach", IndexedFlags)!;
            var work = type.GetField("analysisWork", IndexedFlags)!;
            var memo = (IDictionary)SparseLocalMember(selection, "selectedReach");
            var selected = (Dictionary<int, int>)SparseLocalMember(selection, "Selected");
            // A later identity round chooses edges, then clears precisely the
            // derived rows. Independent methods and earlier rows stay isolated.
            for (int round = 0; round < 2; round++)
            {
                memo.Clear();
                if (round == 1)
                    foreach (int node in nodes.Where(node => graph[node].Count > 1)) selected[node] = graph[node][0];
                var chosenGraph = graph.ToDictionary(pair => pair.Key,
                    pair => selected.TryGetValue(pair.Key, out int chosen) ? new List<int> { chosen } : pair.Value);
                // Exhaust word boundaries; sample the maximum graph to keep
                // this oracle from adding quadratic allocation churn to CI.
                int[] starts = count <= 129 ? nodes : new[] { nodes[0], nodes[1], nodes[count / 2], nodes[^2], nodes[^1] };
                foreach (int start in starts)
                {
                    work.SetValue(selection, 0);
                    var expected = IdentityReachScanningOracle(graph, selected, start);
                    object result = current.Invoke(selection, new object[] { start })!;
                    Equal(true, expected.Set.SetEquals(((IEnumerable)result).Cast<int>()), "identity row membership matches old scanning");
                    Equal(true, expected.Set.SetEquals(IndexedReachOracle(chosenGraph, start)), "identity row matches independent queue oracle");
                    Equal(expected.Work, (int)work.GetValue(selection)!, "identity row keeps exact duplicate-edge work accounting");
                    Equal(true, ReferenceEquals(result, current.Invoke(selection, new object[] { start })), "same round reuses complete immutable row");
                    Equal(expected.Work, (int)work.GetValue(selection)!, "cache hit spends no proof work");
                }
            }
            // A failed row cannot be published; the same request can succeed
            // later with a fresh budget, without mutating another retained row.
            object oldRow = current.Invoke(selection, new object[] { nodes[0] })!;
            int[] oldMembers = ((IEnumerable)oldRow).Cast<int>().ToArray();
            memo.Clear();
            // Multi-block cases fail after the first row bit was populated.
            work.SetValue(selection, count == 1 ? 4_000_000 : 3_999_999);
            bool refused = false;
            try { current.Invoke(selection, new object[] { nodes[0] }); }
            catch (TargetInvocationException error) when (error.InnerException is NotSupportedException failure
                && failure.Message == "identity_control_flow_work_bound") { refused = true; }
            Equal(true, refused, "identity row preserves work-bound refusal");
            Equal(0, memo.Count, "work-bound refusal publishes no partial row");
            work.SetValue(selection, 0);
            object retried = current.Invoke(selection, new object[] { nodes[0] })!;
            Equal(true, oldMembers.ToHashSet().SetEquals(((IEnumerable)retried).Cast<int>()), "retry reconstructs complete row");
            Equal(true, oldMembers.SequenceEqual(((IEnumerable)oldRow).Cast<int>()), "old round row remains immutable");
        }
    }

    private static void IdentityReachRowsReduceAllocations()
    {
        var (selection, graph, nodes) = IdentityReachFixture(512);
        Type type = selection.GetType();
        var current = type.GetMethod("CurrentReach", IndexedFlags)!;
        var work = type.GetField("analysisWork", IndexedFlags)!;
        var memo = (IDictionary)SparseLocalMember(selection, "selectedReach");
        var selected = (Dictionary<int, int>)SparseLocalMember(selection, "Selected");
        long Measure(bool compact)
        {
            memo.Clear();
            long before = GC.GetAllocatedBytesForCurrentThread();
            foreach (int node in nodes)
            {
                if (compact) { work.SetValue(selection, 0); _ = current.Invoke(selection, new object[] { node }); }
                else _ = IdentityReachScanningOracle(graph, selected, node);
            }
            return GC.GetAllocatedBytesForCurrentThread() - before;
        }
        _ = Measure(true); _ = Measure(false);
        for (int repeat = 0; repeat < 3; repeat++)
        {
            long oldBytes = Measure(false), newBytes = Measure(true);
            Equal(true, newBytes * 2 < oldBytes, "identity rows allocate less than half the scanning oracle, including reflection overhead");
            Console.WriteLine("IDENTITY_REACH_ALLOC " + oldBytes + " -> " + newBytes);
        }
    }
}
