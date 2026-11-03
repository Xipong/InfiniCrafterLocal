#nullable enable
using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Reflection;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Disclosure, not another evaluator: retain discarded edge conditions and
    // recognize only a pure prefix plus a direct/one-conditional early return.
    // More complex alternatives remain explicitly unresolved, not absent.
    private static JsonObject DescribeIdentityAlternatives(ParentSourceMethod body, JsonObject full, JsonObject selected)
    {
        var cases = new JsonArray();
        var predicates = full["predicates"]!.AsArray().OfType<JsonObject>()
            .ToDictionary(p => p["at"]!.GetValue<int>());
        bool Pure(AmmoIl instruction)
        {
            string op = instruction.Op;
            return op is "nop" or "const" or "ldarg" or "ldloc" or "stloc" or "ldfld" or "ldsfld" or "ret" or "ceq" or "clt" or "clt.un" or "cgt" or "cgt.un"
                || op.StartsWith("ldc.", StringComparison.Ordinal) || op.StartsWith("ldelem.", StringComparison.Ordinal)
                || op.StartsWith("br", StringComparison.Ordinal) || op.StartsWith("beq", StringComparison.Ordinal)
                || op.StartsWith("bne", StringComparison.Ordinal) || op.StartsWith("blt", StringComparison.Ordinal)
                || op.StartsWith("ble", StringComparison.Ordinal) || op.StartsWith("bgt", StringComparison.Ordinal)
                || op.StartsWith("bge", StringComparison.Ordinal);
        }
        bool Returns(int block)
        {
            var seen = new System.Collections.Generic.HashSet<int>();
            while (seen.Add(block) && body.Blocks.TryGetValue(block, out var b) && b.Code.Count > 0 && b.Code.All(Pure))
            {
                if (b.Code[^1].Op == "ret") return true;
                if (b.Next.Count != 1) return false;
                block = b.Next[0];
            }
            return false;
        }
        JsonObject Condition(JsonObject predicate, int successor) => new()
        {
            ["at"] = predicate["at"]!.DeepClone(), ["op"] = predicate["op"]!.DeepClone(),
            ["inputs"] = predicate["inputs"]!.DeepClone(),
            ["successors"] = predicate["successors"]!.DeepClone(), ["chosenSuccessor"] = successor,
        };
        foreach (var edge in selected["identitySelection"]!["selectedEdges"]!.AsArray().OfType<JsonObject>())
        {
            int at = edge["at"]!.GetValue<int>(), chosen = edge["successor"]!.GetValue<int>();
            if (!predicates.TryGetValue(at, out var predicate)) continue;
            foreach (int alternative in predicate["successors"]!.AsArray().Select(n => n!.GetValue<int>()).Distinct().Where(n => n != chosen))
            {
                var conditions = new JsonArray(Condition(predicate, alternative));
                string effect = "discarded_path_effect_unresolved";
                // Use actual predecessor reachability, not instruction order:
                // a later-offset loop backedge can have changed state already.
                int guardBlock = edge["block"]!.GetValue<int>();
                var entryReach = body.Reach(body.Code[0].Offset);
                bool purePrefix = body.Blocks.Values.Where(b => entryReach.Contains(b.Start) && body.Reach(b.Start).Contains(guardBlock))
                    .SelectMany(b => b.Code).All(Pure);
                if (purePrefix)
                {
                    if (Returns(alternative)) effect = "returns_without_method_state_changes";
                    else if (body.Blocks.TryGetValue(alternative, out var block) && block.Code.All(Pure)
                        && predicates.TryGetValue(block.Code[^1].Offset, out var nested)
                        && block.Next.Count == 2 && block.Next.Count(Returns) == 1)
                    {
                        conditions.Add(Condition(nested, block.Next.Single(Returns)));
                        effect = "returns_without_method_state_changes";
                        // The sibling path is still part of the discarded edge.
                        // Do not erase it merely because one arm has a known return.
                        cases.Add(new JsonObject {
                            ["allConditions"] = new JsonArray(Condition(predicate, alternative), Condition(nested, block.Next.Single(n => !Returns(n)))),
                            ["effect"] = "discarded_path_effect_unresolved",
                        });
                    }
                }
                cases.Add(new JsonObject { ["allConditions"] = conditions, ["effect"] = effect });
            }
        }
        return new JsonObject { ["source"] = "excluded_identity_edges", ["version"] = 1,
            ["scope"] = "Alternative source clues, conditional on reaching the listed guard; not behavior of the captured entry identity. Early-return proof covers normal source control flow, not exceptions/detours. These are not selectable native-AI imports or guarantees of Author capability equivalence.",
            ["cases"] = cases };
    }

    internal static JsonObject InspectProjectileIdentityAlternatives(MethodInfo method, int type, int style)
    {
        var body = new ParentSourceMethod(method);
        var full = new AttackSourceObservation(body, "motion").Finish();
        var selected = InspectProjectileAttackIdentitySource(method, type, style);
        return DescribeIdentityAlternatives(body, full, selected);
    }
}
