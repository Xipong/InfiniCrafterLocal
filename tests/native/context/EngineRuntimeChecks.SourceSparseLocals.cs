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

        void Verify(object source)
        {
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
            var initial = method.GetMethodBody()!.LocalVariables.ToDictionary(local => local.LocalIndex,
                local => new HashSet<string> { "local_entry:" + local.LocalIndex });
            var incoming = reachable.ToDictionary(Start, _ => new Dictionary<int, HashSet<string>>());
            var outgoing = reachable.ToDictionary(Start, _ => new Dictionary<int, HashSet<string>>());
            bool changed = true; int passes = 0;
            // Original dense solver is independent of production state maps.
            // Compare only after this all-512-local fixed point converges.
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
            Equal(3, referenced.Count, "sparse fixture uses distant slots and an addressed local");
            Equal(3, values.Keys.Cast<string>().Count(key => key.StartsWith("local_entry:", StringComparison.Ordinal)), "509 unused local entries are absent");
            foreach (object block in reachable)
            {
                int key = Start(block);
                foreach (var pair in new[] { ("Incoming", incoming[key]), ("Outgoing", outgoing[key]) })
                {
                    var expected = pair.Item2.Where(row => referenced.Contains(row.Key)).ToDictionary(row => row.Key, row => row.Value);
                    Equal(true, Same(expected, (Dictionary<int, HashSet<string>>)SparseLocalMember(block, pair.Item1)), "dense/sparse " + pair.Item1 + " at " + key);
                }
                var state = Copy(incoming[key]);
                foreach (object instruction in (IEnumerable)SparseLocalMember(block, "Code"))
                {
                    string op = (string)SparseLocalMember(instruction, "Op");
                    string id = ((int)SparseLocalMember(instruction, "Offset")).ToString(CultureInfo.InvariantCulture);
                    if (op == "ldloc")
                    {
                        int local = (int)SparseLocalMember(instruction, "Arg");
                        string expectedOp = escaped.Contains(local) ? "address_exposed_local" : "ldloc";
                        string[] inputs = !escaped.Contains(local) && state.TryGetValue(local, out var definitions)
                            ? definitions.OrderBy(s => s, StringComparer.Ordinal).ToArray() : Array.Empty<string>();
                        Equal(expectedOp, (string)SparseLocalMember(values[id]!, "Op"), "dense load opcode at " + id);
                        Equal(true, inputs.SequenceEqual((List<string>)SparseLocalMember(values[id]!, "Inputs")), "dense reaching definitions at " + id);
                    }
                    if (op == "stloc") state[(int)SparseLocalMember(instruction, "Arg")] = new HashSet<string> { id };
                }
            }
            // Recreate the dense solver's original entry-value dictionary too;
            // the projection must remain byte exact with all 512 entries present.
            var valueType = sourceType.GetNestedType("Value", BindingFlags.NonPublic)!;
            foreach (var local in method.GetMethodBody()!.LocalVariables)
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
