#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Source-only finite alternatives. This never invokes a method or field
    // accessor, runs a loop, or supplies a runtime default. Complete sets are
    // conservative unions, not a claim that every alternative will execute.
    // Partial sets retain explicit unknowns and cannot prove an exclusion.
    private sealed class SourceFiniteIntegers
    {
        internal sealed class Result
        {
            internal readonly SortedSet<int> Values = new();
            internal readonly SortedSet<string> Unknown = new(StringComparer.Ordinal);
        }

        private readonly ParentSourceMethod body;
        private readonly AttackIdentitySelection? identity;
        private readonly int workLimit, depthLimit, valueLimit;
        private readonly HashSet<string> active = new(StringComparer.Ordinal);
        private int work;

        // Match the existing definition walk, identity proof depth and local
        // reaching-definition limits. No child-profile/BFS budget is enlarged.
        internal SourceFiniteIntegers(ParentSourceMethod body, AttackIdentitySelection? identity,
            int workLimit = 256, int depthLimit = 64, int valueLimit = 8)
        {
            this.body = body; this.identity = identity;
            this.workLimit = Math.Clamp(workLimit, 0, 256);
            this.depthLimit = Math.Clamp(depthLimit, 0, 64);
            this.valueLimit = Math.Clamp(valueLimit, 0, 8);
        }

        internal Result Evaluate(string id) => Visit(id, 0);

        private bool Work(Result result)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            if (work++ < workLimit) return true;
            result.Unknown.Add("finite_integer_work_bound");
            return false;
        }

        private void Add(Result result, int value)
        {
            result.Values.Add(value);
            if (result.Values.Count <= valueLimit) return;
            result.Values.Remove(result.Values.Max);
            result.Unknown.Add("finite_integer_value_count_bound");
        }

        private void Union(Result destination, Result source)
        {
            destination.Unknown.UnionWith(source.Unknown);
            foreach (int value in source.Values) Add(destination, value);
        }

        private bool Included(string id)
            => identity is null || !body.Values.TryGetValue(id, out var value)
                || identity.Reachable.Contains(value.Block) || value.Op.StartsWith("unresolved", StringComparison.Ordinal);

        private Result Visit(string id, int depth)
        {
            var result = new Result();
            if (!Work(result)) return result;
            if (depth >= depthLimit) { result.Unknown.Add("finite_integer_depth_bound"); return result; }
            if (!active.Add(id)) { result.Unknown.Add("finite_integer_cycle"); return result; }
            try
            {
                if (!body.Values.TryGetValue(id, out var value))
                { result.Unknown.Add("finite_integer_missing_definition"); return result; }
                if (value.Op == "const" && value.Operand is int literal)
                { Add(result, literal); return result; }
                // Only the existing captured-receiver/per-read mutation proof
                // may turn an identity field into a number. A field name, item
                // shoot default, foreign receiver or post-hook local cannot.
                if (identity is not null && identity.TryCapturedIdentityLiteral(id, out int captured))
                { Add(result, captured); return result; }
                if (value.Op is "ldloc" or "stloc" or "predecessor_stack_alternatives")
                {
                    string[] inputs = value.Inputs.Where(Included)
                        .OrderBy(input => body.Values.TryGetValue(input, out var origin) ? origin.At : -1)
                        .ThenBy(input => input, StringComparer.Ordinal).ToArray();
                    if (inputs.Length == 0) result.Unknown.Add("finite_integer_missing_definition");
                    foreach (string input in inputs)
                    {
                        if (work >= workLimit) { result.Unknown.Add("finite_integer_work_bound"); break; }
                        Union(result, Visit(input, depth + 1));
                    }
                    return result;
                }
                // Only already-proved int32 values pass these conversions.
                // Float, int64, native-sized and address values stay unknown.
                if (value.Op is "conv.i4" or "conv.u4" && value.Inputs.Count == 1)
                { Union(result, Visit(value.Inputs[0], depth + 1)); return result; }
                if (value.Op is "add" or "sub" or "add.ovf" or "sub.ovf" && value.Inputs.Count == 2)
                {
                    Result left = Visit(value.Inputs[0], depth + 1), right = Visit(value.Inputs[1], depth + 1);
                    result.Unknown.UnionWith(left.Unknown); result.Unknown.UnionWith(right.Unknown);
                    foreach (int a in left.Values)
                    foreach (int b in right.Values)
                    {
                        if (!Work(result)) return result;
                        // IL add/sub wrap modulo 2^32. Checked signed operations
                        // can throw; never reinterpret that path as a value.
                        long sum = value.Op.StartsWith("add", StringComparison.Ordinal) ? (long)a + b : (long)a - b;
                        if (value.Op.EndsWith(".ovf", StringComparison.Ordinal) && (sum < int.MinValue || sum > int.MaxValue))
                            result.Unknown.Add("finite_integer_checked_overflow");
                        else Add(result, unchecked((int)sum));
                    }
                    return result;
                }
                result.Unknown.Add("finite_integer_runtime_or_unsupported_value");
                return result;
            }
            catch (NotSupportedException error)
            {
                // An optional identity proof exhausting its own budget cannot
                // erase known siblings or turn them into a complete set.
                result.Unknown.Add(error.Message);
                return result;
            }
            finally { active.Remove(id); }
        }
    }

    internal static JsonArray InspectFiniteIntegerSource(MethodInfo method, int type, int style,
        int workLimit = 256, int depthLimit = 64, int valueLimit = 8)
    {
        var body = new ParentSourceMethod(method);
        var identity = new AttackIdentitySelection(body, type, style);
        var selected = new ParentSourceMethod(method, selectedSuccessors: identity.Selected);
        var rows = new JsonArray();
        foreach (var returned in selected.Statements.Where(value => value.Op == "ret" && value.Inputs.Count == 1)
            .Where(value => identity.Reachable.Contains(value.Block)).OrderBy(value => value.At))
        {
            var values = new SourceFiniteIntegers(selected, identity, workLimit, depthLimit, valueLimit).Evaluate(returned.Inputs[0]);
            rows.Add(new JsonObject { ["at"] = returned.At,
                ["values"] = new JsonArray(values.Values.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray()),
                ["unknown"] = new JsonArray(values.Unknown.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray()) });
        }
        return rows;
    }
}
