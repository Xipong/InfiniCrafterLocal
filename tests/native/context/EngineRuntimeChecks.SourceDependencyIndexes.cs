using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static void SourceDependencyRefWrite(ref int value) => value += 3;
    private static int SourceDependencyFixture(bool choose, int input)
    {
        int local = input;
        if (choose) SourceDependencyRefWrite(ref local);
        else local = input + 1;
        return local;
    }

    private static void ParentSourceDependencyIndexesPreserveProjection()
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        MethodInfo method = typeof(EngineRuntimeChecks).GetMethod(nameof(SourceDependencyFixture), BindingFlags.Static | BindingFlags.NonPublic)!;
        object Create(object? code = null) => Activator.CreateInstance(type, flags, null,
            new object?[] { method, code, null, null }, null)!;
        object body = Create();
        var roots = (IList)SparseLocalMember(body, "Statements");
        var reversed = (IList)Activator.CreateInstance(roots.GetType())!;
        foreach (object value in roots.Cast<object>().Reverse()) reversed.Add(value);
        var singleton = (IList)Activator.CreateInstance(roots.GetType())!;
        singleton.Add(roots[roots.Count - 1]);
        var empty = (IList)Activator.CreateInstance(roots.GetType())!;
        var indexMethod = type.GetMethod("GetProjectionDependencies", flags)!;
        var project = type.GetMethod("Project", flags)!;
        var dependency = type.GetMethod("ExceedsDependencyBound", flags)!;
        var indexField = type.GetField("projectionDependencies", flags)!;
        string Project(object source, IList selected, int limit) =>
            ((JsonObject)project.Invoke(source, new object[] { selected, limit })!).ToJsonString();
        object index = indexMethod.Invoke(body, null)!;
        VerifyDependencyScanner(body, index);
        foreach (object value in ((IDictionary)SparseLocalMember(body, "Values")).Values)
            Equal(IndependentDependencyBound(body, value), (bool)dependency.Invoke(body, new[] { value })!,
                "memoized dependency bound agrees with independent original traversal");
        foreach (IList selected in new[] { roots, reversed, singleton, empty })
            foreach (int limit in new[] { 0, 1, 64 })
            {
                string warm = Project(body, selected, limit);
                object fresh = Create();
                Equal(warm, Project(fresh, selected, limit), "warm dependency index preserves exact roots/order/control projection");
                Equal(true, ReferenceEquals(index, indexMethod.Invoke(body, null)), "projection reuses the same completed method index");
            }
        string expected = Project(body, roots, 64);
        Parallel.For(0, 16, _ =>
        {
            if (Project(body, roots, 64) != expected) throw new InvalidOperationException("Concurrent dependency projection changed JSON.");
        });
        object sliced = Create(SparseLocalMember(body, "Code"));
        object sliceIndex = indexMethod.Invoke(sliced, null)!;
        Equal(false, ReferenceEquals(index, sliceIndex), "slice owns its dependency index even when method identity matches");
        VerifyDependencyScanner(sliced, sliceIndex);
        Equal(true, Project(sliced, (IList)SparseLocalMember(sliced, "Statements"), 64)
            .Contains("source_slice_entry_and_external_CFG_targets_unresolved", StringComparison.Ordinal),
            "slice retains original unresolved CFG provenance");
        // Keep a decoded cold instance ready before entering cancellation.
        indexField.SetValue(sliced, null);
        using var cancellation = new CancellationTokenSource();
        using var analysis = new GeneratorClient.ParentAnalysis(cancellation.Token);
        cancellation.Cancel();
        using (analysis.Enter())
        {
            foreach (object target in new[] { body, sliced })
            {
                bool cancelled = false;
                try { indexMethod.Invoke(target, null); }
                catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { cancelled = true; }
                Equal(true, cancelled, "both warm and cold dependency indexes honor cancelled analysis");
                if (!ReferenceEquals(target, body)) Equal(null, indexField.GetValue(target), "cancelled cold scan never publishes an index");
            }
        }
        Equal(expected, Project(body, roots, 64), "cancelled reader cannot poison retained index");

    }

    private static bool IndependentDependencyBound(object body, object value)
    {
        string op = (string)SparseLocalMember(value, "Op");
        if (op is not ("ldloc" or "predecessor_stack_alternatives")) return false;
        var values = (IDictionary)SparseLocalMember(body, "Values");
        var seen = new HashSet<string>();
        var pending = new Stack<string>((List<string>)SparseLocalMember(value, "Inputs"));
        while (pending.Count > 0)
        {
            string id = pending.Pop();
            if (!seen.Add(id) || !values.Contains(id)) continue;
            if (seen.Count > 96) return true;
            foreach (string input in (List<string>)SparseLocalMember(values[id]!, "Inputs")) pending.Push(input);
        }
        return false;
    }

    private static void VerifyDependencyScanner(object body, object index)
    {
        var values = (IDictionary)SparseLocalMember(body, "Values");
        var expected = new Dictionary<int, List<string>>();
        bool addressBound = false;
        HashSet<int> Addresses(string id)
        {
            var slots = new HashSet<int>(); var seen = new HashSet<string>();
            var pending = new Stack<string>(); pending.Push(id);
            while (pending.Count > 0 && seen.Count < 128)
            {
                string next = pending.Pop();
                if (!seen.Add(next) || !values.Contains(next)) continue;
                object value = values[next]!;
                string op = (string)SparseLocalMember(value, "Op");
                var inputs = (List<string>)SparseLocalMember(value, "Inputs");
                if (op == "ldloca" && SparseLocalMember(value, "Operand") is int local) slots.Add(local);
                else if (op is "ldloc" or "stloc" or "predecessor_stack_alternatives")
                    foreach (string input in inputs) pending.Push(input);
                else if (op == "ldflda" && inputs.Count > 0) pending.Push(inputs[0]);
            }
            addressBound |= pending.Count > 0;
            return slots;
        }
        foreach (object statement in (IEnumerable)SparseLocalMember(body, "Statements"))
        {
            string op = (string)SparseLocalMember(statement, "Op");
            object? operand = statement.GetType().GetField("Operand", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(statement);
            var inputs = (List<string>)SparseLocalMember(statement, "Inputs");
            var slots = new HashSet<int>();
            if (op == "stloc" && operand is int slot) slots.Add(slot);
            if (inputs.Count > 0 && (op.StartsWith("stind", StringComparison.Ordinal) || op is "stobj" or "initobj" or "cpobj" or "stfld"))
                slots.UnionWith(Addresses(inputs[0]));
            if (op is "call" or "callvirt" or "newobj" && operand is MethodBase call)
            {
                var parameters = call.GetParameters();
                for (int n = 0; n < inputs.Count; n++)
                {
                    int parameter = n - (call.IsStatic || op == "newobj" ? 0 : 1);
                    if (parameter < 0 || parameter < parameters.Length && parameters[parameter].ParameterType.IsByRef)
                        slots.UnionWith(Addresses(inputs[n]));
                }
            }
            foreach (int local in slots)
            {
                if (!expected.TryGetValue(local, out var writes)) expected[local] = writes = new();
                writes.Add((string)SparseLocalMember(statement, "Id"));
            }
        }
        bool IsBranch(object value)
        {
            string op = (string)SparseLocalMember(value, "Op");
            return op == "switch" || new[] { "br", "beq", "bne", "bge", "bgt", "ble", "blt", "leave" }
                .Any(prefix => op.StartsWith(prefix, StringComparison.Ordinal));
        }
        Equal(string.Join(",", ((IEnumerable)SparseLocalMember(body, "Statements")).Cast<object>()
            .Where(IsBranch).Select(value => SparseLocalMember(value, "Id"))),
            string.Join(",", ((IEnumerable)SparseLocalMember(index, "Branches")).Cast<object>()
                .Select(value => SparseLocalMember(value, "Id"))), "static branch rows preserve source order");
        var actual = (IDictionary)SparseLocalMember(index, "WritesByLocal");
        Equal(expected.Count, actual.Count, "indexed locals match original address scanner");
        foreach (var pair in expected)
            Equal(string.Join(",", pair.Value), string.Join(",", ((IEnumerable)actual[pair.Key]!).Cast<object>()
                .Select(value => (string)SparseLocalMember(value, "Id"))), "write candidates retain exact statement order");
        Equal(addressBound, (bool)SparseLocalMember(index, "AddressBound"), "address traversal bound is retained exactly");
    }

    private static void ParentSourceDependencyIndexesStayBounded()
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        MethodInfo method = typeof(EngineRuntimeChecks).GetMethod(nameof(SourceDependencyFixture), BindingFlags.Static | BindingFlags.NonPublic)!;
        object body = Activator.CreateInstance(type, flags, null, new object?[] { method, null, null, null }, null)!;
        Type valueType = type.GetNestedType("Value", BindingFlags.NonPublic)!;
        var values = (IDictionary)SparseLocalMember(body, "Values");
        var statements = (IList)SparseLocalMember(body, "Statements");
        object Value(string id, string op, object? operand, params string[] inputs)
        {
            object value = Activator.CreateInstance(valueType, true)!;
            foreach (var pair in new[] { ("Id", (object?)id), ("Op", op), ("Operand", operand), ("Inputs", inputs.ToList()) })
                valueType.GetField(pair.Item1, flags)!.SetValue(value, pair.Item2);
            return value;
        }
        // Adversarial decoded graph exercises the safety boundary without
        // invoking a fixture method or relying on compiler local elimination.
        for (int n = 0; n < 130; n++) values.Add("chain" + n,
            Value("chain" + n, "ldloc", 0, n == 129 ? "missing" : "chain" + (n + 1)));
        object addressWrite = Value("address-write", "stind.i4", null, "chain0");
        statements.Add(addressWrite);
        var get = type.GetMethod("GetProjectionDependencies", flags)!;
        object index = get.Invoke(body, null)!;
        VerifyDependencyScanner(body, index);
        Equal(true, (bool)SparseLocalMember(index, "AddressBound"), "unfinished 128-node address traversal remains unresolved");
        var exceeds = type.GetMethod("ExceedsDependencyBound", flags)!;
        Equal(true, (bool)exceeds.Invoke(body, new[] { values["chain0"] })!, "more than 96 dependencies remain opaque");
        Equal(false, (bool)exceeds.Invoke(body, new[] { Value("exact96", "ldloc", 0, "chain34") })!,
            "exactly 96 present dependencies remain transparent");
        Equal(true, (bool)exceeds.Invoke(body, new[] { Value("over96", "ldloc", 0, "chain33") })!,
            "the 97th present dependency crosses the unchanged bound");
        int codeCount = ((ICollection)SparseLocalMember(body, "Code")).Count;
        for (int n = 0; n < codeCount + 20; n++)
            exceeds.Invoke(body, new[] { Value("memo" + n, "ldloc", 0) });
        int memoCount = ((IDictionary)SparseLocalMember(body, "dependencyBounds")).Count;
        Equal(Math.Min(codeCount, 4096), memoCount, "boolean memo stops at its exact per-method entry bound");
        long limit = (long)type.GetMethod("DependencyMemoByteLimit", BindingFlags.Static | BindingFlags.NonPublic)!
            .Invoke(null, new object[] { codeCount })!;
        Equal(true, (long)SparseLocalMember(index, "RetainedBytes") + memoCount * 64L <= limit,
            "retained index and dependency booleans fit reserved memory");
        type.GetField("projectionDependencies", flags)!.SetValue(body, null);
        for (int n = 0; n < codeCount * 4 + 100; n++) statements.Add(Value("store" + n, "stloc", n));
        object oversized = get.Invoke(body, null)!;
        VerifyDependencyScanner(body, oversized);
        Equal(null, type.GetField("projectionDependencies", flags)!.GetValue(body), "oversized index is usable but never retained");
        Equal(false, ReferenceEquals(oversized, get.Invoke(body, null)), "unretained index rebuilds without semantic refusal");
    }
}
