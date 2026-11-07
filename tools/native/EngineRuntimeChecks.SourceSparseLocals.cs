using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static object SparseLocalMember(object instance, string name)
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        return instance.GetType().GetField(name, flags)?.GetValue(instance)
            ?? instance.GetType().GetProperty(name, flags)?.GetValue(instance)!;
    }

    private static MethodInfo SparseLocalFixture()
    {
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("SourceSparseLocalFixture"), AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("source").DefineType("SparseSource", TypeAttributes.Public);
        var method = type.DefineMethod("DiamondLoopAndAddress", MethodAttributes.Public | MethodAttributes.Static,
            typeof(int), new[] { typeof(bool), typeof(int) });
        var il = method.GetILGenerator();
        var locals = Enumerable.Range(0, 512).Select(_ => il.DeclareLocal(typeof(int))).ToArray();
        var other = il.DefineLabel(); var joined = il.DefineLabel(); var loop = il.DefineLabel();
        il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Brfalse, other);
        il.Emit(OpCodes.Ldarg_1); il.Emit(OpCodes.Stloc, locals[3]); il.Emit(OpCodes.Br, joined);
        il.MarkLabel(other); il.Emit(OpCodes.Ldc_I4, 7); il.Emit(OpCodes.Stloc, locals[3]);
        il.MarkLabel(joined); il.Emit(OpCodes.Ldloca, locals[511]); il.Emit(OpCodes.Initobj, typeof(int));
        il.Emit(OpCodes.Ldloc, locals[3]); il.Emit(OpCodes.Stloc, locals[256]);
        il.MarkLabel(loop); il.Emit(OpCodes.Ldloc, locals[256]); il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Add);
        il.Emit(OpCodes.Stloc, locals[256]); il.Emit(OpCodes.Ldloc, locals[256]); il.Emit(OpCodes.Ldarg_1); il.Emit(OpCodes.Blt, loop);
        il.Emit(OpCodes.Ldloc, locals[511]); il.Emit(OpCodes.Ldloc, locals[256]); il.Emit(OpCodes.Add); il.Emit(OpCodes.Ret);
        return type.CreateType()!.GetMethod(method.Name)!;
    }

    private static MethodInfo SharedLocalFixture(string name, Action<ILGenerator, LocalBuilder> emit)
    {
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName(name), AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("source").DefineType(name, TypeAttributes.Public);
        var method = type.DefineMethod("Read", MethodAttributes.Public | MethodAttributes.Static, typeof(int), new[] { typeof(int) });
        var il = method.GetILGenerator();
        emit(il, il.DeclareLocal(typeof(int)));
        return type.CreateType()!.GetMethod(method.Name)!;
    }

    private static void ParentSourceSparseLocalsMatchDenseOracle()
    {
        Type sourceType = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        var constructor = sourceType.GetConstructors(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic).Single();
        MethodInfo method = SparseLocalFixture();
        object Build(object? code = null, object? next = null, Dictionary<int, int>? selection = null)
            => constructor.Invoke(new object?[] { method, code, next, selection });
        var full = Build();
        Verify(full);
        var blocks = ((IDictionary)SparseLocalMember(full, "Blocks")).Values.Cast<object>().ToArray();
        var branch = blocks.First(b => ((List<int>)SparseLocalMember(b, "Next")).Distinct().Count() == 2);
        foreach (int successor in ((List<int>)SparseLocalMember(branch, "Next")).Distinct())
            Verify(Build(selection: new Dictionary<int, int> { [(int)SparseLocalMember(branch, "Start")] = successor }));
        // A real slice omits earlier assignments but retains the original local
        // table and successor offsets. Unknown entry definitions must survive.
        var code = (IList)SparseLocalMember(full, "Code");
        var sliced = (IList)Activator.CreateInstance(code.GetType())!;
        var next = new Dictionary<int, int>();
        for (int n = 0; n + 1 < code.Count; n++) next[(int)SparseLocalMember(code[n]!, "Offset")] = (int)SparseLocalMember(code[n + 1]!, "Offset");
        int start = code.Cast<object>().Where(i => (string)SparseLocalMember(i, "Op") == "ldloca")
            .Select(i => (int)SparseLocalMember(i, "Offset")).First();
        foreach (object instruction in code) if ((int)SparseLocalMember(instruction, "Offset") >= start) sliced.Add(instruction);
        Verify(Build(sliced, next));

        // The join grows a set also reaching a sibling return. Mutating a
        // published predecessor set would contaminate that sibling's load.
        VerifySharing(SharedLocalFixture("SharedSiblingJoin", (il, local) =>
        {
            var other = il.DefineLabel(); var sibling = il.DefineLabel(); var join = il.DefineLabel();
            il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Stloc, local);
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Brfalse, other);
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Beq, sibling);
            il.Emit(OpCodes.Br, join);
            il.MarkLabel(other); il.Emit(OpCodes.Ldc_I4_2); il.Emit(OpCodes.Stloc, local); il.Emit(OpCodes.Br, join);
            il.MarkLabel(sibling); il.Emit(OpCodes.Ldloc, local); il.Emit(OpCodes.Ret);
            il.MarkLabel(join); il.Emit(OpCodes.Ldloc, local); il.Emit(OpCodes.Ret);
        }));
        // A backedge into the entry must retain the unknown entry definition;
        // loads between stores must see only the most recent store.
        VerifySharing(SharedLocalFixture("SharedEntryBackedge", (il, local) =>
        {
            var entry = il.DefineLabel(); il.MarkLabel(entry);
            il.Emit(OpCodes.Ldloc, local); il.Emit(OpCodes.Pop);
            il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Stloc, local);
            il.Emit(OpCodes.Ldloc, local); il.Emit(OpCodes.Pop);
            il.Emit(OpCodes.Ldc_I4_2); il.Emit(OpCodes.Stloc, local);
            il.Emit(OpCodes.Ldloc, local); il.Emit(OpCodes.Pop);
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Brtrue, entry);
            il.Emit(OpCodes.Ldloc, local); il.Emit(OpCodes.Ret);
        }));
        foreach (int count in new[] { 8, 9 })
        {
            var fixture = SharedLocalFixture("SharedDefinitionBound" + count, (il, local) =>
            {
                var arms = Enumerable.Range(0, count).Select(_ => il.DefineLabel()).ToArray();
                var join = il.DefineLabel();
                il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Switch, arms); il.Emit(OpCodes.Br, arms[0]);
                for (int n = 0; n < count; n++)
                {
                    il.MarkLabel(arms[n]); il.Emit(OpCodes.Ldc_I4, n); il.Emit(OpCodes.Stloc, local); il.Emit(OpCodes.Br, join);
                }
                il.MarkLabel(join); il.Emit(OpCodes.Ldloc, local); il.Emit(OpCodes.Ret);
            });
            object source = VerifySharing(fixture);
            var values = ((IDictionary)SparseLocalMember(source, "Values")).Values.Cast<object>();
            object load = values.Single(v => (string)SparseLocalMember(v, "Op") is "ldloc" or "unresolved_local_definition_bound");
            Equal(count == 8 ? "ldloc" : "unresolved_local_definition_bound", (string)SparseLocalMember(load, "Op"), "eight/nine definition boundary opcode");
            Equal(count == 8 ? 8 : 0, ((List<string>)SparseLocalMember(load, "Inputs")).Count, "eight/nine definition boundary inputs");
        }

        // The entry jumps to the last physical block, then definitions travel
        // backwards through the layout one block per forward-scan round. The
        // worklist must preserve the old 512-round admission boundary exactly.
        foreach (int count in new[] { 511, 512 })
        {
            var fixture = SharedLocalFixture("LocalDataflowRounds" + count, (il, local) =>
            {
                var labels = Enumerable.Range(0, count).Select(_ => il.DefineLabel()).ToArray();
                il.Emit(OpCodes.Ldc_I4_7); il.Emit(OpCodes.Stloc, local); il.Emit(OpCodes.Br, labels[^1]);
                for (int index = 0; index < count; index++)
                {
                    il.MarkLabel(labels[index]); il.Emit(OpCodes.Ldloc, local);
                    if (index == 0) il.Emit(OpCodes.Ret);
                    else { il.Emit(OpCodes.Pop); il.Emit(OpCodes.Br, labels[index - 1]); }
                }
            });
            if (count == 511) VerifySharing(fixture);
            else
            {
                string? refusal = null;
                try { constructor.Invoke(new object?[] { fixture, null, null, null }); }
                catch (TargetInvocationException error) when (error.InnerException is NotSupportedException)
                { refusal = error.InnerException.Message; }
                Equal("local_dataflow_bound", refusal, "the verification round after 512 changing rounds is still refused");
            }
        }

        object VerifySharing(MethodInfo fixture)
        {
            object source = constructor.Invoke(new object?[] { fixture, null, null, null });
            Verify(source);
            return source;
        }

        void Verify(object source)
        {
            var sourceMethod = (MethodBase)SparseLocalMember(source, "Method");
            VerifySourceControlFlow(source, sourceMethod.Name);
            var reachable = ((IDictionary)SparseLocalMember(source, "Blocks")).Values.Cast<object>()
                .Where(b => (int)SparseLocalMember(b, "Height") >= 0).ToArray();
            int Start(object block) => (int)SparseLocalMember(block, "Start");
            var predecessors = (IDictionary)SparseLocalMember(source, "predecessors");
            var entries = (HashSet<int>)SparseLocalMember(source, "sliceEntries");
            var values = (IDictionary)SparseLocalMember(source, "Values");
            var escaped = (HashSet<int>)SparseLocalMember(source, "EscapedLocals");
            var roots = SparseLocalMember(source, "Statements");
            var project = sourceType.GetMethod("Project", BindingFlags.Instance | BindingFlags.NonPublic)!;
            string original = ((JsonObject)project.Invoke(source, new[] { roots, 64 })!).ToJsonString();
            Dictionary<int, HashSet<string>> Copy(Dictionary<int, HashSet<string>> state)
                => state.ToDictionary(pair => pair.Key, pair => new HashSet<string>(pair.Value));
            bool Same(Dictionary<int, HashSet<string>> left, Dictionary<int, HashSet<string>> right)
                => left.Count == right.Count && left.All(pair => right.TryGetValue(pair.Key, out var set) && pair.Value.SetEquals(set));
            var initial = sourceMethod.GetMethodBody()!.LocalVariables.ToDictionary(local => local.LocalIndex,
                local => new HashSet<string> { "local_entry:" + local.LocalIndex });
            var incoming = reachable.ToDictionary(Start, _ => new Dictionary<int, HashSet<string>>());
            var outgoing = reachable.ToDictionary(Start, _ => new Dictionary<int, HashSet<string>>());
            bool changed = true; int passes = 0;
            // Original dense solver independently keeps every intermediate
            // state. Production retains only the resulting Value dependencies;
            // compare observable loads and diagnostics after full convergence.
            while (changed)
            {
                if (++passes > 512) throw new InvalidOperationException("dense local oracle did not converge");
                changed = false;
                foreach (object block in reachable)
                {
                    int key = Start(block);
                    var entry = entries.Contains(key) ? Copy(initial) : new Dictionary<int, HashSet<string>>();
                    foreach (object predecessor in ((IEnumerable)predecessors[key]!).Cast<object>().Where(b => outgoing.ContainsKey(Start(b))))
                        foreach (var pair in outgoing[Start(predecessor)])
                        {
                            if (!entry.TryGetValue(pair.Key, out var set)) entry[pair.Key] = set = new HashSet<string>();
                            set.UnionWith(pair.Value);
                        }
                    var exit = Copy(entry);
                    foreach (object instruction in (IEnumerable)SparseLocalMember(block, "Code"))
                        if ((string)SparseLocalMember(instruction, "Op") == "stloc")
                            exit[(int)SparseLocalMember(instruction, "Arg")] = new HashSet<string> {
                                ((int)SparseLocalMember(instruction, "Offset")).ToString(CultureInfo.InvariantCulture) };
                    changed |= !Same(exit, outgoing[key]); incoming[key] = entry; outgoing[key] = exit;
                }
            }
            var referenced = ((IEnumerable)SparseLocalMember(source, "Code")).Cast<object>()
                .Where(i => (string)SparseLocalMember(i, "Op") is "ldloc" or "stloc" or "ldloca")
                .Select(i => (int)SparseLocalMember(i, "Arg")).ToHashSet();
            if (sourceMethod == method)
                Equal(3, referenced.Count, "sparse fixture uses distant slots and an addressed local");
            Equal(referenced.Count, values.Keys.Cast<string>().Count(key => key.StartsWith("local_entry:", StringComparison.Ordinal)), "only referenced local entries are present");
            var expectedUnknown = new List<string>();
            foreach (object block in reachable)
            {
                int key = Start(block);
                var state = Copy(incoming[key]);
                foreach (object instruction in (IEnumerable)SparseLocalMember(block, "Code"))
                {
                    string op = (string)SparseLocalMember(instruction, "Op");
                    string id = ((int)SparseLocalMember(instruction, "Offset")).ToString(CultureInfo.InvariantCulture);
                    if (op == "ldloc")
                    {
                        int local = (int)SparseLocalMember(instruction, "Arg");
                        state.TryGetValue(local, out var definitions);
                        bool bounded = !escaped.Contains(local) && definitions is not null && definitions.Count > 8;
                        string expectedOp = escaped.Contains(local) ? "address_exposed_local"
                            : bounded ? "unresolved_local_definition_bound" : "ldloc";
                        if (bounded) expectedUnknown.Add("local_" + local + "_has_" + definitions!.Count + "_reaching_definitions");
                        string[] inputs = !escaped.Contains(local) && !bounded && definitions is not null
                            ? definitions.OrderBy(s => s, StringComparer.Ordinal).ToArray() : Array.Empty<string>();
                        Equal(expectedOp, (string)SparseLocalMember(values[id]!, "Op"), "dense load opcode at " + id);
                        Equal(true, inputs.SequenceEqual((List<string>)SparseLocalMember(values[id]!, "Inputs")), "dense reaching definitions at " + id);
                    }
                    if (op == "stloc") state[(int)SparseLocalMember(instruction, "Arg")] = new HashSet<string> { id };
                }
            }
            Equal(true, expectedUnknown.SequenceEqual(((List<string>)SparseLocalMember(source, "Unknown"))
                .Where(reason => reason.StartsWith("local_", StringComparison.Ordinal))), "dense local definition bound diagnostics");
            // Recreate the dense solver's original entry-value dictionary too;
            // the projection must remain byte exact with all 512 entries present.
            var valueType = sourceType.GetNestedType("Value", BindingFlags.NonPublic)!;
            foreach (var local in sourceMethod.GetMethodBody()!.LocalVariables)
            {
                string id = "local_entry:" + local.LocalIndex;
                if (values.Contains(id)) continue;
                object entry = Activator.CreateInstance(valueType, nonPublic: true)!;
                valueType.GetField("Id", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(entry, id);
                valueType.GetField("Op", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(entry, "unresolved_local_entry");
                valueType.GetField("Operand", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(entry, local.LocalType);
                values[id] = entry;
            }
            Equal(original, ((JsonObject)project.Invoke(source, new[] { roots, 64 })!).ToJsonString(), "dense entry table and sparse table give byte-exact source projections");
        }
    }
}
