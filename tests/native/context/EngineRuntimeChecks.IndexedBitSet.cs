using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Analysis;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags IndexedFlags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

    private static HashSet<int> IndexedReachOracle(Dictionary<int, List<int>> graph, int start, int? join = null)
    {
        // A queue/set reference, independent of the production stack and bit layout.
        var facts = new HashSet<int> { start };
        var pending = new Queue<int>(graph[start]);
        while (pending.Count > 0)
        {
            int next = pending.Dequeue();
            if (next == join || !facts.Add(next)) continue;
            foreach (int target in graph[next]) pending.Enqueue(target);
        }
        return facts;
    }

    private static void IndexedBitSetTraversalMatchesHashSetOracle()
    {
        foreach (int count in new[] { 1, 63, 64, 65, 127, 128, 2048 })
        {
            // Descending, nonconsecutive offsets deliberately differ from bit indices.
            int[] nodes = Enumerable.Range(0, count).Select(index => 1001 + (count - index) * 17).ToArray();
            var indices = nodes.Select((node, index) => (node, index)).ToDictionary(pair => pair.node, pair => pair.index);
            var graph = nodes.ToDictionary(node => node, _ => new List<int>());
            for (int index = 0; index + 1 < count; index++)
            {
                // Leave a disconnected terminal node; include duplicate edges,
                // self loops, backedges and diamonds in the remaining component.
                if (count > 3 && index == count - 2) continue;
                graph[nodes[index]].Add(nodes[index + 1]);
                graph[nodes[index]].Add(nodes[index + 1]);
                if (index % 7 == 0) graph[nodes[index]].Add(nodes[index]);
                if (index > 2 && index % 7 == 3) graph[nodes[index]].Add(nodes[index - 3]);
                if (index + 2 < count - 1 && index % 5 == 0) graph[nodes[index]].Add(nodes[index + 2]);
            }
            foreach (int start in nodes)
            {
                Verify(IndexedBitSet.Reach(start, indices, graph, static next => next), IndexedReachOracle(graph, start));
                foreach (int join in new[] { -1, start, nodes[count / 2] }.Distinct())
                    Verify(IndexedBitSet.ControlledRegion(start, join, indices, graph, static next => next),
                        IndexedReachOracle(graph, start, join));
                Verify(IndexedBitSet.Singleton(start, indices), new HashSet<int> { start });
            }
            ulong[] first = IndexedBitSet.Reach(nodes[0], indices, graph, static next => next);
            ulong[] second = IndexedBitSet.Reach(nodes[0], indices, graph, static next => next);
            Equal(false, ReferenceEquals(first, second), "different rows own separate final arrays");
            ulong before = second[0]; first[0] = 0;
            Equal(before, second[0], "a caller-owned row cannot mutate another result");

            void Verify(ulong[] words, HashSet<int> expected)
            {
                Equal((count + 63) / 64, words.Length, "compact row has exactly the required words");
                for (int bit = 0; bit < nodes.Length; bit++)
                    Equal(expected.Contains(nodes[bit]), (words[bit >> 6] & (1UL << (bit & 63))) != 0,
                        "indexed membership agrees with independent graph traversal");
                if ((count & 63) != 0)
                    Equal(0UL, words[^1] >> (count & 63), "unused high bits remain clear");
            }
        }
    }

    private static MethodInfo IndexedGraphFixture(bool duplicateOnly = false)
    {
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("IndexedGraph" + Guid.NewGuid().ToString("N")), AssemblyBuilderAccess.Run);
        var owner = assembly.DefineDynamicModule("source").DefineType("Graph", TypeAttributes.Public);
        var builder = owner.DefineMethod("Read", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int) });
        var il = builder.GetILGenerator();
        var left = il.DefineLabel();
        il.Emit(OpCodes.Ldarg_0);
        if (duplicateOnly)
        {
            // Both switch cases and fallthrough share one successor.
            il.Emit(OpCodes.Switch, new[] { left, left });
            il.MarkLabel(left); il.Emit(OpCodes.Ldc_I4_0); il.Emit(OpCodes.Ret);
        }
        else
        {
            var right = il.DefineLabel(); var join = il.DefineLabel(); var loop = il.DefineLabel();
            il.Emit(OpCodes.Switch, new[] { left, left, loop });
            il.Emit(OpCodes.Br, right);
            il.MarkLabel(left); il.Emit(OpCodes.Nop); il.Emit(OpCodes.Br, join);
            il.MarkLabel(right); il.Emit(OpCodes.Nop); il.Emit(OpCodes.Br, join);
            il.MarkLabel(join); il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Brtrue, loop);
            il.Emit(OpCodes.Ldc_I4_0); il.Emit(OpCodes.Ret);
            il.MarkLabel(loop); il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Beq, left);
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Brtrue, loop);
            il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Ret);
            // An unreachable block must remain addressable by Reach/ControlledRegion.
            il.Emit(OpCodes.Ldc_I4_2); il.Emit(OpCodes.Ret);
        }
        return owner.CreateType()!.GetMethod("Read")!;
    }

    private static object IndexedSource(MethodInfo method, object? code = null, object? next = null, Dictionary<int, int>? selected = null)
    {
        Type sourceType = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        return sourceType.GetConstructors(IndexedFlags).Single(candidate => candidate.GetParameters().Length == 4)
            .Invoke(new object?[] { method, code, next, selected });
    }

    private static void ParentSourceCompactRowsMatchGraphOracle()
    {
        MethodInfo method = IndexedGraphFixture();
        object source = IndexedSource(method);
        Verify(source);
        var blocks = (IDictionary)SparseLocalMember(source, "Blocks");
        object branch = blocks.Values.Cast<object>().First(block => ((List<int>)SparseLocalMember(block, "Next")).Distinct().Count() > 1);
        int start = (int)SparseLocalMember(branch, "Start");
        foreach (int successor in ((List<int>)SparseLocalMember(branch, "Next")).Distinct())
            Verify(IndexedSource(method, selected: new Dictionary<int, int> { [start] = successor }));

        // Retain the entry switch only: its other CFG targets are real external stubs.
        var code = (IList)SparseLocalMember(source, "Code");
        var slice = (IList)Activator.CreateInstance(code.GetType())!;
        var next = new Dictionary<int, int>();
        for (int index = 0; index + 1 < code.Count; index++)
            next[(int)SparseLocalMember(code[index]!, "Offset")] = (int)SparseLocalMember(code[index + 1]!, "Offset");
        object entry = blocks.Values.Cast<object>().Single(block => (int)SparseLocalMember(block, "Start") == 0);
        foreach (object instruction in (IEnumerable)SparseLocalMember(entry, "Code")) slice.Add(instruction);
        object sliced = IndexedSource(method, slice, next);
        Equal(true, ((List<string>)SparseLocalMember(sliced, "Unknown")).Contains("source_slice_entry_and_external_CFG_targets_unresolved"),
            "slice fixture keeps its explicit unknown boundary");
        Verify(sliced);
        Verify(IndexedSource(IndexedGraphFixture(duplicateOnly: true)));

        static void Verify(object body)
        {
            var members = (IDictionary)SparseLocalMember(body, "Blocks");
            // Exercise the established dictionary enumeration order, not numeric sorting.
            var reversed = members.Keys.Cast<int>().Reverse().Select(key => (key, members[key])).ToArray();
            members.Clear();
            foreach (var (key, value) in reversed) members.Add(key, value);
            int[] order = members.Keys.Cast<int>().ToArray();
            var graph = order.ToDictionary(node => node, node => (List<int>)SparseLocalMember(members[node]!, "Next"));
            int[] active = order.Where(node => (int)SparseLocalMember(members[node]!, "Height") >= 0).ToArray();
            int[] universe = active.Append(-1).ToArray();
            var postdom = universe.ToDictionary(node => node, node => node == -1 ? new HashSet<int> { -1 } : universe.ToHashSet());
            bool changed;
            int rounds = 0;
            do
            {
                changed = false;
                foreach (int node in active.Reverse())
                {
                    int[] successors = graph[node].Count == 0 ? new[] { -1 } : graph[node].ToArray();
                    var facts = new HashSet<int>(postdom[successors[0]]);
                    foreach (int successor in successors.Skip(1)) facts.IntersectWith(postdom[successor]);
                    facts.Add(node);
                    if (!facts.SetEquals(postdom[node])) { postdom[node] = facts; changed = true; }
                }
                Equal(true, ++rounds < 1000, "independent postdominator reference converges");
            } while (changed);
            MethodInfo reach = body.GetType().GetMethod("Reach", IndexedFlags)!;
            MethodInfo control = body.GetType().GetMethod("ControlledRegion", IndexedFlags)!;
            MethodInfo project = body.GetType().GetMethod("Project", IndexedFlags)!;
            object roots = SparseLocalMember(body, "Statements");
            string before = ((JsonObject)project.Invoke(body, new[] { roots, 64 })!).ToJsonString();
            var ownedArrays = new HashSet<ulong[]>();
            var snapshots = new List<(ulong[] Words, ulong[] Copy)>();
            foreach (int node in order)
            {
                var expectedControl = new HashSet<int> { node };
                if (graph[node].Distinct().Count() >= 2)
                {
                    int join = universe.Where(candidate => candidate != node && postdom[node].Contains(candidate))
                        .OrderByDescending(candidate => postdom[candidate].Count).DefaultIfEmpty(-1).First();
                    expectedControl = IndexedReachOracle(graph, node, join);
                }
                foreach (var (query, expected) in new[] { (reach, IndexedReachOracle(graph, node)), (control, expectedControl) })
                {
                    object facts = query.Invoke(body, new object[] { node })!;
                    Equal(true, order.Where(expected.Contains).SequenceEqual(((IEnumerable)facts).Cast<int>()),
                        "production BlockSet preserves canonical order and exact reference membership");
                    Equal(true, ReferenceEquals(facts, query.Invoke(body, new object[] { node })), "warm queries reuse the complete immutable row");
                    MethodInfo contains = facts.GetType().GetMethod("Contains", IndexedFlags)!;
                    foreach (int candidate in order.Append(int.MaxValue))
                        Equal(expected.Contains(candidate), (bool)contains.Invoke(facts, new object[] { candidate })!, "production Contains agrees with enumeration and rejects unknown offsets");
                    var words = (ulong[])SparseLocalMember(facts, "words");
                    Equal(true, ownedArrays.Add(words), "each retained row exclusively owns its array");
                    snapshots.Add((words, (ulong[])words.Clone()));
                }
            }
            foreach (var (words, copy) in snapshots)
                Equal(true, copy.SequenceEqual(words), "building later rows does not mutate published rows");
            Equal(before, ((JsonObject)project.Invoke(body, new[] { roots, 64 })!).ToJsonString(),
                "complete raw, selected and sliced projections stay byte-exact after memo fill");
            long limit = (long)body.GetType().GetMethod("ReachabilityMemoByteLimit", BindingFlags.Static | BindingFlags.NonPublic)!
                .Invoke(null, new object[] { order.Length })!;
            Equal(limit, (long)SparseLocalMember(body, "reachabilityMemoBytes"), "both complete memo tables keep the existing reserved accounting");
        }
    }

    private static void ParentSourceCompactRowsPublishAtomically()
    {
        object body = IndexedSource(IndexedGraphFixture());
        var blocks = (IDictionary)SparseLocalMember(body, "Blocks");
        var reachMemo = (IDictionary)SparseLocalMember(body, "reachable");
        var controlMemo = (IDictionary)SparseLocalMember(body, "controlRegions");
        MethodInfo reach = body.GetType().GetMethod("Reach", IndexedFlags)!;
        MethodInfo control = body.GetType().GetMethod("ControlledRegion", IndexedFlags)!;
        int entry = 0;
        var graph = blocks.Keys.Cast<int>().ToDictionary(node => node, node => (List<int>)SparseLocalMember(blocks[node]!, "Next"));
        int terminal = IndexedReachOracle(graph, entry).First(node => graph[node].Count == 0);
        graph[terminal].Add(int.MaxValue);
        Refuses<KeyNotFoundException>(reach, entry);
        AssertEmpty();
        graph[terminal].Clear();

        using (var cancellation = new CancellationTokenSource())
        using (var analysis = new GeneratorClient.ParentAnalysis(cancellation.Token))
        using (analysis.Enter())
        {
            cancellation.Cancel();
            Refuses<OperationCanceledException>(control, entry);
            AssertEmpty();
            Equal(true, body.GetType().GetField("postdominators", IndexedFlags)!.GetValue(body) is null,
                "cancelled fixed point cannot publish a postdominator matrix");
        }
        object complete = control.Invoke(body, new object[] { entry })!;
        Equal(true, ((IEnumerable)complete).Cast<int>().Contains(entry), "retry publishes a complete control region");
        object retained = reach.Invoke(body, new object[] { terminal })!;
        var retainedWords = (ulong[])SparseLocalMember(retained, "words");
        ulong[] snapshot = (ulong[])retainedWords.Clone();
        long charged = (long)SparseLocalMember(body, "reachabilityMemoBytes");
        graph[terminal].Add(int.MaxValue);
        Refuses<KeyNotFoundException>(reach, entry);
        Equal(1, reachMemo.Count, "failed additional reach row is never retained");
        Equal(charged, (long)SparseLocalMember(body, "reachabilityMemoBytes"), "failed row does not consume the cache budget");
        Equal(true, snapshot.SequenceEqual(retainedWords), "failed traversal leaves earlier published words intact");
        graph[terminal].Clear();
        object recovered = reach.Invoke(body, new object[] { entry })!;
        Equal(true, IndexedReachOracle(graph, entry).SetEquals(((IEnumerable)recovered).Cast<int>()), "retry starts with a clean row after partial traversal failure");

        void AssertEmpty()
        {
            Equal(0, reachMemo.Count + controlMemo.Count, "refused construction publishes no row");
            Equal(0L, (long)SparseLocalMember(body, "reachabilityMemoBytes"), "refused first construction has no charged layout");
            foreach (string field in new[] { "blockSetNodes", "blockSetIndices" })
                Equal(true, body.GetType().GetField(field, IndexedFlags)!.GetValue(body) is null, "refused first construction leaves its candidate layout private");
        }
        void Refuses<T>(MethodInfo query, int start) where T : Exception
        {
            bool refused = false;
            try { query.Invoke(body, new object[] { start }); }
            catch (TargetInvocationException error) when (error.InnerException is T) { refused = true; }
            Equal(true, refused, "failed graph construction propagates its original refusal");
        }
    }
}
