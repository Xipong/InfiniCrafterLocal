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
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("SourceMemoBudgetFixture"), AssemblyBuilderAccess.Run);
        var module = assembly.DefineDynamicModule("source");
        using var cache = new GeneratorClient.ParentSourceGraphCache(shared: true);
        MethodInfo? firstMethod = null;
        MethodInfo? latestMethod = null;
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
            latestMethod = method;
            object source = constructor.Invoke(new object?[] { method, null, null, null });
            var blocks = (IDictionary)SparseLocalMember(source, "Blocks");
            var roots = SparseLocalMember(source, "Statements");
            string projection = ((JsonObject)project.Invoke(source, new[] { roots, 64 })!).ToJsonString();
            if (index == 0)
            {
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
                Equal(projection, ((JsonObject)project.Invoke(source, new[] { roots, 64 })!).ToJsonString(),
                    "prior reachability and control queries do not change the published source");
            }
            int codeCount = ((ICollection)SparseLocalMember(source, "Code")).Count;
            cache.Remember(method, source, null, codeCount, blocks.Count);
            Equal(true, cache.TryGet(method, out _, out _), "the active large method remains cacheable");
        }
        Equal(false, cache.TryGet(firstMethod!, out _, out _), "older large source is evicted under aggregate pressure");
        Equal(true, cache.TryGet(latestMethod!, out _, out _), "recent large source remains accessible");
        cache.Dispose();
        Equal(false, cache.TryGet(latestMethod!, out _, out _), "disposed cache cannot return retained source");
    }
}
