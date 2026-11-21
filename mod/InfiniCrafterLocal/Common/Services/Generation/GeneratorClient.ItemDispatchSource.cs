#nullable enable
using System;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;
using ICSharpCode.Decompiler.TypeSystem;
using Terraria;
using SwitchSection = ICSharpCode.Decompiler.CSharp.Syntax.SwitchSection;

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
                ["scope"] = "Read-only conditional source excerpts, not execution or final player stats. Item.type equality is a relevance witness, not receiver identity proof. Positive equality guards retain their true bodies; literal switches retain the selector and complete matching section. One-hop integer helper candidates carry explicit immutable Item.type argument bindings; this does not establish the captured receiver or execution. Alternate branches, other local bindings, callers, callees, hooks and enclosing control may remain unresolved. Other dispatcher roots and unsupported dispatch shapes are not covered.",
                ["roots"] = new JsonArray(),
                ["limits"] = new JsonObject { ["regionsPerRoot"] = 16, ["charactersPerRegion"] = 24000, ["charactersPerRoot"] = 64000, ["helperCallSitesPerRoot"] = 8, ["helperDepth"] = 1 },
                ["unknowns"] = new JsonArray("dispatcher_coverage_partial; absence_not_proved", "source_receiver_identity_and_runtime_entry_not_proved")
            };
            foreach (string name in new[] { "ApplyEquipFunctional", "ItemCheck_Inner", "ItemCheck_Shoot", "UpdateEquips" })
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
                        var input = new JsonObject { ["type"] = itemType, ["identityForwardingVersion"] = 2 };
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
                            var document = GetNativeCSharpDocument(method, timeout.Token);
                            BuildNativeItemDispatchRegions(document, itemType, root, timeout.Token);
                            BuildNativeItemDispatchHelpers(document, itemType, root, timeout.Token);
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

    private static bool ItemDispatchTypeField(Expression value) => value.GetSymbol() is IField field
        && field.DeclaringType.FullName == typeof(Item).FullName && field.Name == "type";

    private static bool ItemDispatchIdentity(BinaryOperatorExpression comparison, int itemType, Func<Expression, bool> identity)
        => comparison.Operator == BinaryOperatorType.Equality
            && (identity(comparison.Left) && comparison.Right is PrimitiveExpression { Value: int right } && right == itemType
                || identity(comparison.Right) && comparison.Left is PrimitiveExpression { Value: int left } && left == itemType);

    private static void BuildNativeItemDispatchRegions(NativeCSharpDocument document, int itemType, JsonObject root, CancellationToken cancellation, int regionLimit = 16, int regionCharacters = 24000, int totalCharacters = 64000)
        => BuildNativeItemDispatchRegionsCore(document, itemType, root, cancellation, regionLimit, regionCharacters, totalCharacters, ItemDispatchTypeField);

    private sealed record ItemDispatchRegion(int Site, AstNode Body, Expression Condition, Func<Statement> Excerpt);

    private static IEnumerable<ItemDispatchRegion> ItemDispatchRegions(NativeCSharpDocument document, int itemType,
        Func<Expression, bool> identity, JsonArray gaps, CancellationToken cancellation)
    {
        int site = 0;
        foreach (var node in document.Declaration.Body.Descendants)
        {
            cancellation.ThrowIfCancellationRequested();
            site++;
            if (node is IfElseStatement branch && branch.Condition.DescendantsAndSelf.OfType<BinaryOperatorExpression>()
                .Any(test => PositiveIdentityEquality(test, branch.Condition) && ItemDispatchIdentity(test, itemType, identity)))
                yield return new(site, branch.TrueStatement, branch.Condition, () => CloneCSharpTrueArm(branch));
            else if (node is SwitchSection section && section.Parent is SwitchStatement switched && identity(switched.Expression)
                && section.CaseLabels.Any(label => label.Expression is PrimitiveExpression { Value: int value } && value == itemType))
            {
                if (section.CaseLabels.Any(label => label.Expression is not PrimitiveExpression { Value: int })
                    || section.Descendants.Any(child => child is GotoCaseStatement or GotoDefaultStatement or GotoStatement))
                {
                    gaps.Add("dispatcher_switch_label_or_transfer_unsupported");
                    continue;
                }
                yield return new(site, section, switched.Expression, () => CloneSelectedSwitchSection(switched, section));
            }
        }
    }

    private static void BuildNativeItemDispatchRegionsCore(NativeCSharpDocument document, int itemType, JsonObject root, CancellationToken cancellation,
        int regionLimit, int regionCharacters, int totalCharacters, Func<Expression, bool> identity)
    {
        var records = root["records"]!.AsArray(); var gaps = root["unknowns"]!.AsArray();
        var regions = ItemDispatchRegions(document, itemType, identity, gaps, cancellation).ToArray();
        var admitted = new HashSet<AstNode>();
        int characters = 0;
        foreach (var region in regions)
        {
            cancellation.ThrowIfCancellationRequested();
            if (region.Body.Ancestors.Any(admitted.Contains)) continue;
            if (admitted.Count >= regionLimit) { gaps.Add("dispatcher_region_count_bound"); break; }
            var excerpt = region.Excerpt();
            var rendered = RenderCSharp(excerpt, includeLocations: false);
            if (rendered.Code.Length > regionCharacters || characters + rendered.Code.Length > totalCharacters)
            { gaps.Add("dispatcher_region_character_bound; entire_region_omitted"); continue; }
            var offsets = region.Condition.DescendantsAndSelf.Concat(region.Body.DescendantsAndSelf).SelectMany(node => node.Annotations.OfType<ILInstruction>())
                .SelectMany(instruction => instruction.ILRanges).Where(range => range.End > range.Start)
                .Select(range => range.Start).Distinct().Order().ToArray();
            string sha = CSharpHash(Encoding.UTF8.GetBytes(rendered.Code));
            var record = MethodSourceIdentity(document.Method);
            record["id"] = "item_dispatch:" + document.Method.Module.ModuleVersionId + ":" + document.Method.MetadataToken + ":" + region.Site + ":" + sha;
            record["metadataToken"] = document.Method.MetadataToken; record["assemblySha256"] = document.Module.Sha256;
            record["coverage"] = "conditional_source_region_with_unresolved_inputs";
            record["code"] = rendered.Code; record["codeSha256"] = sha;
            record["entryCondition"] = RenderCSharp(region.Condition, includeLocations: false).Code.Trim();
            record["enclosingConditions"] = EnclosingSourceConditions(region.Body);
            record["sourceIlOffsets"] = new JsonArray(offsets.Select(offset => (JsonNode?)JsonValue.Create(offset)).ToArray());
            record["unknowns"] = new JsonArray("local_bindings_and_receiver_aliases_not_evaluated", "enclosing_loops_exceptions_callers_and_hooks_unresolved", "false_arm_and_other_regions_not_included; absence_not_proved");
            record["decompiler"] = new JsonObject { ["name"] = "ICSharpCode.Decompiler", ["version"] = NativeCSharpVersion,
                ["assemblySha256"] = NativeCSharpDecompilerSha256, ["settings"] = "csharp_default_no_indentation_v1" };
            records.Add(record); admitted.Add(region.Body); characters += rendered.Code.Length;
        }
        if (records.Count == 0) gaps.Add("no_admitted_Item_type_region; absence_not_proved");
    }
}
