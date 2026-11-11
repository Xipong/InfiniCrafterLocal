#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed partial class ParentSourceMethod
    {
        // Pure facts of this decoded method (including its particular slice).
        // Never key these by MethodBase: a slice must not inherit full CFG facts.
        private ProjectionDependencies? projectionDependencies;
        private readonly Dictionary<string, bool> dependencyBounds = new(StringComparer.Ordinal);

        internal static long DependencyMemoByteLimit(int instructions) => 4096L + instructions * 256L;

        private sealed class ProjectionDependencies
        {
            internal readonly Dictionary<int, Value[]> WritesByLocal;
            internal readonly Value[] Branches;
            internal readonly bool AddressBound;
            internal readonly long RetainedBytes;

            internal ProjectionDependencies(Dictionary<int, List<Value>> writes, Value[] branches, bool addressBound)
            {
                WritesByLocal = writes.ToDictionary(pair => pair.Key, pair => pair.Value.ToArray());
                Branches = branches;
                AddressBound = addressBound;
                // Conservative dictionary/array overhead plus reference slots.
                RetainedBytes = 256L + writes.Count * 128L + branches.Length * 8L
                    + writes.Values.Sum(rows => rows.Count * 16L);
            }
        }

        private ProjectionDependencies GetProjectionDependencies()
        {
            lock (memoGate)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                if (projectionDependencies is not null) return projectionDependencies;
                ProjectionDependencies result = BuildProjectionDependencies();
                currentParentAnalysis?.ThrowIfCancelled();
                // Unusual methods with many address aliases still project exactly
                // as before, but cannot retain an unbounded cross-product index.
                // Reserve 64 bytes per bounded dependency memo entry separately.
                if (result.RetainedBytes <= DependencyMemoByteLimit(Code.Count) - Math.Min(Code.Count, 4096) * 64L)
                    projectionDependencies = result;
                return result;
            }
        }

        private ProjectionDependencies BuildProjectionDependencies()
        {
            bool addressBound = false;
            // These are possible source writes, not reaching SSA definitions.
            // In particular a ref call remains opaque and is never evaluated.
            HashSet<int> AddressSlots(string id)
            {
                var result = new HashSet<int>();
                var seen = new HashSet<string>(StringComparer.Ordinal);
                var pending = new Stack<string>(); pending.Push(id);
                while (pending.Count > 0 && seen.Count < 128)
                {
                    string next = pending.Pop();
                    if (!seen.Add(next) || !Values.TryGetValue(next, out var value)) continue;
                    if (value.Op == "ldloca" && value.Operand is int slot) result.Add(slot);
                    else if (value.Op is "ldloc" or "stloc" or "predecessor_stack_alternatives")
                        foreach (string input in value.Inputs) pending.Push(input);
                    else if (value.Op == "ldflda" && value.Inputs.Count > 0) pending.Push(value.Inputs[0]);
                }
                if (pending.Count > 0) addressBound = true;
                return result;
            }
            var writesByLocal = new Dictionary<int, List<Value>>();
            foreach (var statement in Statements)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                var slots = new HashSet<int>();
                if (statement.Op == "stloc" && statement.Operand is int slot) slots.Add(slot);
                if (statement.Inputs.Count > 0 && (statement.Op.StartsWith("stind", StringComparison.Ordinal)
                    || statement.Op is "stobj" or "initobj" or "cpobj" or "stfld"))
                    slots.UnionWith(AddressSlots(statement.Inputs[0]));
                if (statement.Op is "call" or "callvirt" or "newobj" && statement.Operand is MethodBase call)
                {
                    var parameters = call.GetParameters();
                    for (int index = 0; index < statement.Inputs.Count; index++)
                    {
                        int parameter = index - (call.IsStatic || statement.Op == "newobj" ? 0 : 1);
                        if (parameter < 0 || parameter < parameters.Length && parameters[parameter].ParameterType.IsByRef)
                            slots.UnionWith(AddressSlots(statement.Inputs[index]));
                    }
                }
                foreach (int local in slots)
                {
                    if (!writesByLocal.TryGetValue(local, out var list)) writesByLocal[local] = list = new();
                    list.Add(statement);
                }
            }
            var branches = Statements.Where(value => value.Op == "switch"
                || IsBranch(new AmmoIl(value.At, value.Op, value.Operand))).ToArray();
            return new ProjectionDependencies(writesByLocal, branches, addressBound);
        }

        private bool ExceedsDependencyBound(Value value)
        {
            if (value.Op is not ("ldloc" or "predecessor_stack_alternatives")) return false;
            lock (memoGate)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                if (dependencyBounds.TryGetValue(value.Id, out bool cached)) return cached;
                bool result = ComputeDependencyBound(value);
                currentParentAnalysis?.ThrowIfCancelled();
                if (dependencyBounds.Count < Math.Min(Code.Count, 4096)) dependencyBounds.Add(value.Id, result);
                return result;
            }
        }

        private bool ComputeDependencyBound(Value value)
        {
            if (value.Op is not ("ldloc" or "predecessor_stack_alternatives")) return false;
            var seen = new HashSet<string>(); var pending = new Stack<string>(value.Inputs);
            while (pending.Count > 0)
            {
                string next = pending.Pop();
                if (!seen.Add(next) || !Values.TryGetValue(next, out var dependency)) continue;
                if (seen.Count > 96) return true;
                foreach (string input in dependency.Inputs) pending.Push(input);
            }
            return false;
        }
    }
}
