using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static object SourceControlFlowFixture(int[][] edges, int[]? insertionOrder = null, HashSet<int>? unreachable = null)
    {
        Type sourceType = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        var constructor = sourceType.GetConstructors(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic).Single();
        var method = typeof(EngineRuntimeChecks).GetMethod(nameof(SourceControlFlowFixtureBody), BindingFlags.Static | BindingFlags.NonPublic)!;
        object source = constructor.Invoke(new object?[] { method, null, null, null });
        var blocks = (IDictionary)SparseLocalMember(source, "Blocks");
        Type blockType = sourceType.GetNestedType("Block", BindingFlags.NonPublic)!;
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.NonPublic;
        // Only a fresh uncached analyzer is mutated. Explicit CFGs cover
        // non-terminating and disconnected components without executing IL.
        blocks.Clear();
        foreach (int index in insertionOrder ?? Enumerable.Range(0, edges.Length).ToArray())
        {
            object block = Activator.CreateInstance(blockType, nonPublic: true)!;
            blockType.GetField("Start", fields)!.SetValue(block, index);
            blockType.GetField("Height", fields)!.SetValue(block, unreachable?.Contains(index) == true ? -1 : 0);
            blockType.GetField("Next", fields)!.SetValue(block, edges[index].ToList());
            blocks.Add(index, block);
        }
        return source;
    }

    private static int SourceControlFlowFixtureBody(int value) => value;

    private static void VerifySourceControlFlow(object source, string fixture)
    {
        Type sourceType = source.GetType();
        var blocks = ((IDictionary)SparseLocalMember(source, "Blocks")).Values.Cast<object>().ToArray();
        int Start(object block) => (int)SparseLocalMember(block, "Start");
        List<int> Next(object block) => (List<int>)SparseLocalMember(block, "Next");
        var byStart = blocks.ToDictionary(Start);
        var active = blocks.Where(block => (int)SparseLocalMember(block, "Height") >= 0).ToArray();
        var dense = new Dictionary<int, HashSet<int>>();
        // Independent original solver, including HashSet enumeration order in
        // tied joins. Do not derive expected answers from production bit rows.
        bool changed = active.Any(block => Next(block).Distinct().Count() > 1); int passes = 0;
        if (changed)
        {
            var all = active.Select(Start).Append(-1).ToHashSet();
            dense = all.ToDictionary(start => start,
                start => start == -1 ? new HashSet<int> { -1 } : new HashSet<int>(all));
        }
        while (changed)
        {
            if (++passes > 2048) throw new InvalidOperationException("dense postdominator oracle did not converge");
            changed = false;
            foreach (object block in active.Reverse())
            {
                int[] successors = Next(block).Count == 0 ? new[] { -1 } : Next(block).ToArray();
                var common = new HashSet<int>(dense[successors[0]]);
                foreach (int successor in successors.Skip(1)) common.IntersectWith(dense[successor]);
                common.Add(Start(block));
                if (!common.SetEquals(dense[Start(block)])) { dense[Start(block)] = common; changed = true; }
            }
        }
        MethodInfo controlled = sourceType.GetMethod("ControlledRegion", BindingFlags.Instance | BindingFlags.NonPublic)!;
        MethodInfo reach = sourceType.GetMethod("Reach", BindingFlags.Instance | BindingFlags.NonPublic)!;
        foreach (object block in active)
        {
            int start = Start(block);
            var expected = new HashSet<int> { start };
            if (Next(block).Distinct().Count() > 1)
            {
                int join = dense[start].Where(candidate => candidate != start)
                    .OrderByDescending(candidate => dense[candidate].Count).FirstOrDefault(-1);
                var pending = new Stack<int>(Next(block));
                while (pending.Count > 0)
                {
                    int next = pending.Pop();
                    if (next == join || !expected.Add(next)) continue;
                    foreach (int successor in Next(byStart[next])) pending.Push(successor);
                }
            }
            var actual = (HashSet<int>)controlled.Invoke(source, new object[] { start })!;
            Equal(true, expected.SetEquals(actual), fixture + " dense controlled region at " + start);
            var reached = new HashSet<int>(); var work = new Stack<int>(); work.Push(start);
            while (work.Count > 0)
            {
                int next = work.Pop(); if (!reached.Add(next)) continue;
                foreach (int successor in Next(byStart[next])) work.Push(successor);
            }
            Equal(true, reached.SetEquals((HashSet<int>)reach.Invoke(source, new object[] { start })!),
                fixture + " exact reachability at " + start);
        }
    }

    private static void ParentSourceControlFlowMatchesDenseOracle()
    {
        int[][][] fixtures =
        {
            new[] { new[] { 1, 2 }, new[] { 3 }, new[] { 3 }, Array.Empty<int>() },
            new[] { new[] { 1, 2 }, Array.Empty<int>(), Array.Empty<int>() },
            new[] { new[] { 1, 3 }, new[] { 2 }, new[] { 1, 3 }, Array.Empty<int>() },
            new[] { new[] { 1, 2 }, new[] { 2 }, new[] { 1 } },
            new[] { new[] { 1, 3 }, new[] { 2 }, new[] { 1 }, Array.Empty<int>() },
            new[] { new[] { 1, 2 }, new[] { 2, 3 }, new[] { 1, 3 }, Array.Empty<int>() },
            new[] { new[] { 1, 1, 2 }, new[] { 3 }, new[] { 3 }, Array.Empty<int>() },
            new[] { new[] { 0, 1 }, Array.Empty<int>() },
            new[] { new[] { 1, 2 }, Array.Empty<int>(), Array.Empty<int>(), new[] { 4, 3 }, new[] { 3 } },
        };
        for (int index = 0; index < fixtures.Length; index++)
        {
            VerifySourceControlFlow(SourceControlFlowFixture(fixtures[index]), "CFG " + index);
            VerifySourceControlFlow(SourceControlFlowFixture(fixtures[index], Enumerable.Range(0, fixtures[index].Length).Reverse().ToArray()),
                "reordered CFG " + index);
        }
        VerifySourceControlFlow(SourceControlFlowFixture(fixtures[^1], unreachable: new HashSet<int> { 3, 4 }), "unreachable SCC");
        var random = new Random(333);
        for (int sample = 0; sample < 40; sample++)
        {
            int count = random.Next(3, 15);
            int[][] edges = Enumerable.Range(0, count).Select(_ => Enumerable.Range(0, random.Next(4))
                .Select(_ => random.Next(count)).ToArray()).ToArray();
            VerifySourceControlFlow(SourceControlFlowFixture(edges, Enumerable.Range(0, count).OrderBy(_ => random.Next()).ToArray()),
                "deterministic CFG " + sample);
        }
        // Include the synthetic exit in every 64-bit boundary calculation.
        foreach (int count in new[] { 62, 63, 64, 126, 127, 128 })
        {
            int[][] edges = Enumerable.Range(0, count).Select(index => new[] { index + 1, index + 2 }
                .Where(next => next < count).ToArray()).ToArray();
            VerifySourceControlFlow(SourceControlFlowFixture(edges), "word boundary " + count);
        }
        // A real prefix slice creates empty external CFG target blocks. Their
        // synthetic exits participate in the same oracle as decoded blocks.
        var method = SharedLocalFixture("ControlPrefixSlice", (il, local) =>
        {
            var other = il.DefineLabel();
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Brfalse, other);
            il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Ret);
            il.MarkLabel(other); il.Emit(OpCodes.Ldc_I4_2); il.Emit(OpCodes.Ret);
        });
        Type sourceType = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        var constructor = sourceType.GetConstructors(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic).Single();
        object full = constructor.Invoke(new object?[] { method, null, null, null });
        var code = (IList)SparseLocalMember(full, "Code");
        var prefix = (IList)Activator.CreateInstance(code.GetType())!;
        prefix.Add(code[0]); prefix.Add(code[1]);
        var nextOffsets = new Dictionary<int, int>();
        for (int n = 0; n + 1 < code.Count; n++)
            nextOffsets[(int)SparseLocalMember(code[n]!, "Offset")] = (int)SparseLocalMember(code[n + 1]!, "Offset");
        object sliced = constructor.Invoke(new object?[] { method, prefix, nextOffsets, null });
        Equal(2, ((IDictionary)SparseLocalMember(sliced, "Blocks")).Values.Cast<object>()
            .Count(block => ((IList)SparseLocalMember(block, "Code")).Count == 0), "prefix has two external target stubs");
        VerifySourceControlFlow(sliced, "external target slice");
    }

    private static void ParentSourceControlMemoIsBounded()
    {
        const int count = 512;
        object source = SourceControlFlowFixture(Enumerable.Range(0, count)
            .Select(index => new[] { (index + 1) % count, (index + 2) % count }).ToArray());
        Type type = source.GetType();
        MethodInfo reach = type.GetMethod("Reach", BindingFlags.Instance | BindingFlags.NonPublic)!;
        MethodInfo controlled = type.GetMethod("ControlledRegion", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var all = Enumerable.Range(0, count).ToHashSet();
        for (int start = 0; start < count; start++)
        {
            Equal(true, all.SetEquals((HashSet<int>)reach.Invoke(source, new object[] { start })!), "bounded memo retains exact reach result");
            var expected = new HashSet<int>(all); expected.Remove(start == 0 ? 1 : 0);
            Equal(true, expected.SetEquals((HashSet<int>)controlled.Invoke(source, new object[] { start })!), "bounded memo retains exact closed-SCC region");
        }
        long retained = (long)SparseLocalMember(source, "lazySetMemoBytes");
        long budget = (long)SparseLocalMember(source, "LazySetMemoBudgetBytes");
        Equal(true, retained > 0 && retained <= budget && budget == 4L * 1024 * 1024, "lazy CFG sets stay within their byte budget");
        var memo = (IDictionary)SparseLocalMember(source, "reachable");
        Equal(true, memo.Count < count, "fixture exceeds retained reachability capacity");
        int missed = Enumerable.Range(0, count).First(start => !memo.Contains(start));
        var first = (HashSet<int>)reach.Invoke(source, new object[] { missed })!;
        var second = (HashSet<int>)reach.Invoke(source, new object[] { missed })!;
        Equal(false, ReferenceEquals(first, second), "over-budget results are recomputed without retention");
        Equal(true, first.SetEquals(second) && all.SetEquals(second), "recomputation is lossless");
        Equal(count, ((IDictionary)SparseLocalMember(source, "postdominators")).Count, "only one join per active block is retained");
        object tiny = SourceControlFlowFixture(new[] { Array.Empty<int>() });
        Equal(true, (long)SparseLocalMember(tiny, "LazyMemoReservationBytes") < 1024,
            "tiny methods reserve their possible memo footprint instead of four MiB");
    }
}
