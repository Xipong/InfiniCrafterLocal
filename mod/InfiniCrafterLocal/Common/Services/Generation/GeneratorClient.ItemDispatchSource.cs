#nullable enable
using System;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;
using ICSharpCode.Decompiler.TypeSystem;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Native dispatchers are source candidates, not executed item hooks. Typed
    // identity comparisons select relevant syntax only; they do not prove that
    // this is the captured item, that an enclosing guard passes, or that a call
    // executes. No item IDs, names or equipment categories select behavior here.
    private static JsonObject CaptureNativeItemDispatchReference(int itemType)
    {
        JsonObject Analyze()
        {
            var result = new JsonObject {
                ["source"] = "conditional_native_item_dispatch_csharp", ["version"] = 1,
                ["relevanceItemType"] = itemType,
                ["scope"] = "Read-only conditional source excerpts, not execution or final player stats. Item.type equality is a relevance witness, not receiver identity proof. Original guards and true bodies are retained; alternate branches, local bindings, callers, callees, hooks and enclosing control may remain unresolved. Other dispatcher roots and non-equality dispatch are not covered.",
                ["roots"] = new JsonArray(),
                ["limits"] = new JsonObject { ["regionsPerRoot"] = 16, ["charactersPerRegion"] = 24000, ["charactersPerRoot"] = 64000 },
                ["unknowns"] = new JsonArray("dispatcher_coverage_partial; absence_not_proved", "source_receiver_identity_and_runtime_entry_not_proved")
            };
            foreach (string name in new[] { "ApplyEquipFunctional", "ItemCheck_Inner" })
            {
                currentParentAnalysis?.ThrowIfCancelled();
                var methods = typeof(Player).GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                    .Where(method => method.Name == name).ToArray();
                var root = new JsonObject { ["root"] = name, ["records"] = new JsonArray(), ["unknowns"] = new JsonArray() };
                result["roots"]!.AsArray().Add(root);
                if (methods.Length != 1) { root["unknowns"]!.AsArray().Add("dispatcher_method_missing_or_ambiguous"); continue; }
                var method = methods[0]; root["rootCertificate"] = MethodSourceIdentity(method);
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(currentParentAnalysis?.Cancellation ?? CancellationToken.None);
                timeout.CancelAfter(TimeSpan.FromSeconds(20));
                try
                {
                    while (!Monitor.TryEnter(nativeCSharpGate, 50)) timeout.Token.ThrowIfCancellationRequested();
                    try
                    {
                        var input = new JsonObject { ["type"] = itemType };
                        if (TryReadNativeSourceProjection("item_dispatch", method, input, timeout.Token, out var projection)
                            && projection["root"] is JsonValue packedRoot && packedRoot.TryGetValue<string>(out string? packedName) && packedName == name
                            && projection["records"] is JsonArray && projection["unknowns"] is JsonArray
                            && JsonNode.DeepEquals(projection["rootCertificate"], root["rootCertificate"]))
                        {
                            timeout.Token.ThrowIfCancellationRequested();
                            foreach (var property in projection) root[property.Key] = property.Value?.DeepClone();
                        }
                        else
                        {
                            BuildNativeItemDispatchRegions(GetNativeCSharpDocument(method, timeout.Token), itemType, root, timeout.Token);
                            timeout.Token.ThrowIfCancellationRequested();
                            RecordNativeSourceProjection("item_dispatch", method, input, root, timeout.Token);
                        }
                    }
                    finally { Monitor.Exit(nativeCSharpGate); }
                }
                catch (OperationCanceledException) { currentParentAnalysis?.ThrowIfCancelled(); root["unknowns"]!.AsArray().Add("dispatcher_decompilation_time_bound"); }
                catch (Exception error) when (error is not OutOfMemoryException)
                { root["unknowns"]!.AsArray().Add("dispatcher_source:" + error.GetType().Name); }
            }
            return result;
        }
        return currentParentAnalysis is { } analysis ? analysis.Defer(Analyze) : Analyze();
    }

    private static bool ItemDispatchIdentity(BinaryOperatorExpression comparison, int itemType)
    {
        if (comparison.Operator != BinaryOperatorType.Equality) return false;
        bool Field(Expression value) => value.GetSymbol() is IField field
            && field.DeclaringType.FullName == typeof(Item).FullName && field.Name == "type";
        return Field(comparison.Left) && comparison.Right is PrimitiveExpression { Value: int right } && right == itemType
            || Field(comparison.Right) && comparison.Left is PrimitiveExpression { Value: int left } && left == itemType;
    }

    private static void BuildNativeItemDispatchRegions(NativeCSharpDocument document, int itemType, JsonObject root, CancellationToken cancellation, int regionLimit = 16, int regionCharacters = 24000, int totalCharacters = 64000)
    {
        var records = root["records"]!.AsArray(); var gaps = root["unknowns"]!.AsArray();
        var branches = document.Declaration.Body.Descendants.OfType<IfElseStatement>()
            .Where(branch => branch.Condition.DescendantsAndSelf.OfType<BinaryOperatorExpression>().Any(test => ItemDispatchIdentity(test, itemType))).ToArray();
        int characters = 0, count = 0;
        foreach (var branch in branches)
        {
            cancellation.ThrowIfCancellationRequested();
            if (branches.Any(outer => outer != branch && (branch == outer.TrueStatement || branch.Ancestors.Contains(outer.TrueStatement)))) continue;
            if (++count > regionLimit) { gaps.Add("dispatcher_region_count_bound"); break; }
            var excerpt = CloneCSharpTrueArm(branch);
            var rendered = RenderCSharp(excerpt, includeLocations: false);
            if (rendered.Code.Length > regionCharacters || characters + rendered.Code.Length > totalCharacters)
            { gaps.Add("dispatcher_region_character_bound; entire_region_omitted"); continue; }
            var enclosing = new JsonArray();
            foreach (var outer in branch.Ancestors.OfType<IfElseStatement>().Reverse())
                enclosing.Add(new JsonObject { ["condition"] = RenderCSharp(outer.Condition, includeLocations: false).Code.Trim(),
                    ["requiredArm"] = (branch == outer.TrueStatement || branch.Ancestors.Contains(outer.TrueStatement)) ? "true" : "false" });
            var offsets = branch.Condition.DescendantsAndSelf.Concat(branch.TrueStatement.DescendantsAndSelf).SelectMany(node => node.Annotations.OfType<ILInstruction>())
                .SelectMany(instruction => instruction.ILRanges).Where(range => range.End > range.Start)
                .Select(range => range.Start).Distinct().Order().ToArray();
            string sha = CSharpHash(Encoding.UTF8.GetBytes(rendered.Code));
            var record = MethodSourceIdentity(document.Method);
            record["id"] = "item_dispatch:" + document.Method.Module.ModuleVersionId + ":" + document.Method.MetadataToken + ":" + sha;
            record["metadataToken"] = document.Method.MetadataToken; record["assemblySha256"] = document.Module.Sha256;
            record["coverage"] = "conditional_source_region_with_unresolved_inputs";
            record["code"] = rendered.Code; record["codeSha256"] = sha;
            record["entryCondition"] = RenderCSharp(branch.Condition, includeLocations: false).Code.Trim();
            record["enclosingConditions"] = enclosing;
            record["sourceIlOffsets"] = new JsonArray(offsets.Select(offset => (JsonNode?)JsonValue.Create(offset)).ToArray());
            record["unknowns"] = new JsonArray("local_bindings_and_receiver_aliases_not_evaluated", "enclosing_loops_exceptions_callers_and_hooks_unresolved", "false_arm_and_other_regions_not_included; absence_not_proved");
            record["decompiler"] = new JsonObject { ["name"] = "ICSharpCode.Decompiler", ["version"] = NativeCSharpVersion,
                ["assemblySha256"] = NativeCSharpDecompilerSha256, ["settings"] = "csharp_default_no_indentation_v1" };
            records.Add(record); characters += rendered.Code.Length;
        }
        if (records.Count == 0) gaps.Add("no_admitted_Item_type_equality_region; absence_not_proved");
    }
}
