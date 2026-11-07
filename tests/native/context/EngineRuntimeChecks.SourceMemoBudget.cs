using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static void ParentSourceMemoBudgetBoundsRetainedControlFacts()
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        Type sourceType = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        var constructor = sourceType.GetConstructors(flags).Single(candidate => candidate.GetParameters().Length == 4);
        MethodInfo project = sourceType.GetMethod("Project", flags)!;
        MethodInfo reach = sourceType.GetMethod("Reach", flags)!;
        MethodInfo control = sourceType.GetMethod("ControlledRegion", flags)!;
        MethodInfo budget = sourceType.GetMethod("ReachabilityMemoByteLimit", BindingFlags.Static | BindingFlags.NonPublic)!;
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("SourceMemoBudgetFixture"), AssemblyBuilderAccess.Run);
        var module = assembly.DefineDynamicModule("source");
        using var cache = new GeneratorClient.ParentSourceGraphCache(shared: true);
        var retained = (IDictionary)typeof(GeneratorClient.ParentSourceGraphCache).GetField("entries", flags)!.GetValue(cache)!;
        MethodInfo? firstMethod = null;
        bool sawEviction = false;
        for (int index = 0; index < 20; index++)
        {
            // Valid normal-flow IL: repeated early returns make large overlapping
            // control regions. The source is decoded/projected, never executed.
            var owner = module.DefineType("EarlyReturns" + index, TypeAttributes.Public);
            var builder = owner.DefineMethod("Read", MethodAttributes.Public | MethodAttributes.Static,
                typeof(int), new[] { typeof(int) });
            var il = builder.GetILGenerator();
            for (int n = 0; n < 1023; n++)
            {
                var next = il.DefineLabel();
                il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldc_I4, n); il.Emit(OpCodes.Bne_Un, next);
                il.Emit(OpCodes.Ldc_I4, n); il.Emit(OpCodes.Ret); il.MarkLabel(next);
            }
            il.Emit(OpCodes.Ldc_I4_M1); il.Emit(OpCodes.Ret);
            MethodInfo method = owner.CreateType()!.GetMethod("Read")!;
            firstMethod ??= method;
            object source = constructor.Invoke(new object?[] { method, null, null, null });
            var blocks = (IDictionary)SparseLocalMember(source, "Blocks");
            var roots = SparseLocalMember(source, "Statements");
            string projection = ((JsonObject)project.Invoke(source, new[] { roots, 64 })!).ToJsonString();
            long limit = (long)budget.Invoke(null, new object[] { blocks.Count })!;
            if (index == 0)
            {
                var regions = (IDictionary)SparseLocalMember(source, "controlRegions");
                Equal(1023, regions.Count, "projection memoizes every branching control region");
                foreach (int start in blocks.Keys)
                {
                    reach.Invoke(source, new object[] { start });
                    control.Invoke(source, new object[] { start });
                }
                Equal(blocks.Count, regions.Count, "all possible control queries remain memoized");
                Equal(blocks.Count, ((IDictionary)SparseLocalMember(source, "reachable")).Count, "all possible reach queries remain memoized");
                Equal(limit, (long)SparseLocalMember(source, "reachabilityMemoBytes"), "full combined memo occupies exactly its reserved accounting budget");
                Equal(projection, ((JsonObject)project.Invoke(source, new[] { roots, 64 })!).ToJsonString(),
                    "filling both complete memo tables preserves byte-exact source projection");
                int[] starts = blocks.Keys.Cast<int>().ToArray();
                foreach (int start in new[] { starts[0], starts[1], starts[starts.Length / 2], starts[^1] })
                {
                    var expectedReach = new HashSet<int>(); var pending = new Stack<int>(); pending.Push(start);
                    while (pending.Count > 0)
                    {
                        int next = pending.Pop(); if (!expectedReach.Add(next)) continue;
                        foreach (int successor in (List<int>)SparseLocalMember(blocks[next]!, "Next")) pending.Push(successor);
                    }
                    var expectedControl = ((List<int>)SparseLocalMember(blocks[start]!, "Next")).Count > 1
                        ? expectedReach : new HashSet<int> { start };
                    foreach (var sample in new[] { (reach, expectedReach), (control, expectedControl) })
                    {
                        object facts = sample.Item1.Invoke(source, new object[] { start })!;
                        Equal(true, sample.Item2.SetEquals(((IEnumerable)facts).Cast<int>()), "compact fact enumeration matches independent CFG traversal");
                        MethodInfo contains = facts.GetType().GetMethod("Contains", flags)!;
                        foreach (int node in starts.Append(int.MaxValue))
                            Equal(sample.Item2.Contains(node), (bool)contains.Invoke(facts, new object[] { node })!, "compact membership matches independent CFG traversal");
                    }
                }
            }
            int codeCount = ((ICollection)SparseLocalMember(source, "Code")).Count;
            cache.Remember(method, source, null, codeCount, blocks.Count);
            Equal(true, cache.TryGet(method, out var latest, out _), "bounded large compiled method remains cacheable");
            Equal(true, ReferenceEquals(source, latest), "cache retains the exact source body");
            long cacheMemoArrays = 0, reservedMemoBytes = 0;
            foreach (object entry in retained.Values)
            {
                object body = ((ValueTuple<object?, string?>)entry).Item1!;
                var bodyBlocks = (IDictionary)SparseLocalMember(body, "Blocks");
                long bodyLimit = (long)budget.Invoke(null, new object[] { bodyBlocks.Count })!;
                long charged = (long)SparseLocalMember(body, "reachabilityMemoBytes");
                long arrays = 0;
                foreach (string name in new[] { "reachable", "controlRegions" })
                    foreach (object facts in ((IDictionary)SparseLocalMember(body, name)).Values)
                    {
                        // Measure actual retained payload independently from
                        // production's capacity/overhead accounting formula.
                        var words = (ulong[])SparseLocalMember(facts, "words");
                        arrays += words.LongLength * sizeof(ulong);
                    }
                Equal(true, arrays <= charged && charged <= bodyLimit, "actual combined retained memo arrays fit their charged reserved budget");
                cacheMemoArrays += arrays;
                reservedMemoBytes += bodyLimit;
            }
            long cacheWeight = (long)typeof(GeneratorClient.ParentSourceGraphCache).GetField("weight", flags)!.GetValue(cache)!;
            Equal(true, cacheMemoArrays <= reservedMemoBytes && reservedMemoBytes <= cacheWeight
                && cacheWeight <= 128L * 1024 * 1024, "multi-method cache explicitly accounts bounded retained control facts");
            sawEviction |= retained.Count < index + 1;
        }
        Equal(true, sawEviction, "combined reserved memo cost triggers byte-budget eviction before the method-count limit");
        Equal(false, cache.TryGet(firstMethod!, out _, out _), "old large source is evicted under the accounted byte budget");
        cache.Dispose();
        Equal(0, retained.Count, "disposing source cache releases memo-owning bodies");
    }
}
