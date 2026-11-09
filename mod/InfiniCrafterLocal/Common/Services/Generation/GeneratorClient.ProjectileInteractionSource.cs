#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
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
using SwitchSection = ICSharpCode.Decompiler.CSharp.Syntax.SwitchSection;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Read-only source supplements for effects outside AI. A matching typed
    // equality establishes relevance only, never a selected/executed branch.
    private const string InteractionScope = "Conditional source only: reach the shown guard first. Enclosing flow, hooks, captured-entry identity preservation, external local values and unshown callees remain unknown. Live predicates are not evaluated; no record proves execution or absence of other effects. Helper bodies are one-hop source, not inlined or executed.";
    private const int InteractionRegionLimit = 12, InteractionRegionCharacters = 16000, InteractionTotalCharacters = 48000;

    private static JsonObject InteractionEnvelope(int type, int style) => new()
    {
        ["source"] = "verified_conditional_native_interaction_csharp", ["version"] = 1,
        ["relevanceIdentity"] = new JsonObject { ["Projectile.type"] = type, ["Projectile.aiStyle"] = style },
        ["scope"] = InteractionScope, ["roots"] = new JsonArray()
    };

    private static JsonObject CaptureProjectileInteractionSource(int type, int style, Action<MethodBase> certify, JsonArray references)
    {
        var envelope = InteractionEnvelope(type, style);
        foreach (string root in new[] { "Damage", "StatusNPC", "HandleMovement" })
        {
            currentParentAnalysis?.ThrowIfCancelled();
            var result = new JsonObject { ["root"] = root, ["records"] = new JsonArray(), ["helpers"] = new JsonArray(),
                ["unresolved"] = new JsonArray("other_regions_and_callees_unresolved; absence_not_proved") };
            var methods = typeof(Projectile).GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                .Where(method => method.Name == root).ToArray();
            if (methods.Length != 1)
            { result["unresolved"]!.AsArray().Add("root_missing_or_ambiguous"); envelope["roots"]!.AsArray().Add(result); continue; }
            var method = methods[0];
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(currentParentAnalysis?.Cancellation ?? CancellationToken.None);
            timeout.CancelAfter(TimeSpan.FromSeconds(20));
            try
            {
                var input = new JsonObject { ["type"] = type, ["style"] = style };
                while (!Monitor.TryEnter(nativeCSharpGate, 50)) timeout.Token.ThrowIfCancellationRequested();
                try
                {
                    if (TryReadNativeSourceProjection("projectile_interaction", method, input, timeout.Token, out var packed)
                        && packed["root"]?.GetValue<string>() == root && packed["records"] is JsonArray
                        && packed["helpers"] is JsonArray && packed["unresolved"] is JsonArray
                        && JsonNode.DeepEquals(packed["rootCertificate"], MethodSourceIdentity(method))) result = packed.DeepClone().AsObject();
                    else
                    {
                        var document = GetNativeCSharpDocument(method, timeout.Token);
                        result = BuildProjectileInteractionSource(document, type, style, timeout.Token);
                        if (nativeSourcePackRecorder is not null)
                            RecordNativeSourceProjection("projectile_interaction", method, input, result, timeout.Token);
                    }
                    timeout.Token.ThrowIfCancellationRequested();
                }
                finally { Monitor.Exit(nativeCSharpGate); }
                certify(method);
                foreach (var record in result["records"]!.AsArray().Concat(result["helpers"]!.AsArray()))
                    foreach (var call in record!["spawnSites"]!.AsArray()) references.Add(call!.DeepClone());
                foreach (var helper in result["helpers"]!.AsArray().OfType<JsonObject>())
                    if (helper["metadataToken"] is JsonValue token && token.TryGetValue<int>(out int value)
                        && method.Module.ResolveMethod(value) is MethodInfo called
                        && called.DeclaringType == typeof(Projectile)
                        && JsonNode.DeepEquals(MethodSourceIdentity(called), new JsonObject {
                            ["method"] = helper["method"]!.DeepClone(),
                            ["sourceModuleVersionId"] = helper["sourceModuleVersionId"]!.DeepClone(),
                            ["sourceMethodSha256"] = helper["sourceMethodSha256"]!.DeepClone() })) certify(called);
            }
            catch (OperationCanceledException)
            { currentParentAnalysis?.ThrowIfCancelled(); result["unresolved"]!.AsArray().Add("source_decompilation_time_bound"); }
            catch (Exception error) when (error is not OutOfMemoryException)
            { result["unresolved"]!.AsArray().Add("source:" + (error is NotSupportedException ? error.Message : error.GetType().Name)); }
            envelope["roots"]!.AsArray().Add(result);
        }
        return envelope;
    }

    private static bool InteractionSourceFingerprintBacked(JsonObject attack)
    {
        if (attack["source"]?.ToString() != "read_only_native_attack_source"
            || attack["version"] is not JsonValue version || !version.TryGetValue<int>(out int ownerVersion) || ownerVersion != 1
            || attack["interactionSources"] is not JsonObject source
            || source["source"]?.ToString() != "verified_conditional_native_interaction_csharp"
            || source["version"] is not JsonValue viewVersion || !viewVersion.TryGetValue<int>(out int formatVersion) || formatVersion != 1
            || source["roots"] is not JsonArray { Count: 3 } roots || attack["sourceMethods"] is not JsonArray methods) return false;
        bool Backed(JsonObject record)
        {
            if (record["method"] is not JsonValue name || !name.TryGetValue<string>(out _)
                || record["sourceModuleVersionId"] is not JsonValue module || !module.TryGetValue<string>(out var mvid) || !Guid.TryParse(mvid, out _)
                || record["sourceMethodSha256"] is not JsonValue hash || !hash.TryGetValue<string>(out var sha)
                || sha is not { Length: 64 } || !sha.All(Uri.IsHexDigit)) return false;
            return methods.Any(method => JsonNode.DeepEquals(method, new JsonObject { ["method"] = name.DeepClone(),
                ["sourceModuleVersionId"] = module.DeepClone(), ["sourceMethodSha256"] = hash.DeepClone() }));
        }
        var names = new HashSet<string>(StringComparer.Ordinal);
        foreach (var node in roots)
        {
            if (node is not JsonObject root || root["root"]?.ToString() is not ("Damage" or "StatusNPC" or "HandleMovement")
                || !names.Add(root["root"]!.ToString())
                || root["rootCertificate"] is not JsonObject { Count: 3 } certificate || !Backed(certificate)
                || certificate["method"]?.ToString() != "Terraria.Projectile." + root["root"]!.ToString()
                || root["records"] is not JsonArray records || records.Any(record => record is not JsonObject region || !Backed(region)
                    || region["method"]?.ToString() != certificate["method"]!.ToString())
                || root["helpers"] is not JsonArray helpers || helpers.Any(helper => helper is not JsonObject record || !Backed(record))) return false;
        }
        return true;
    }

    private static JsonArray InteractionExternalInputs(AstNode region)
    {
        var declared = region.DescendantsAndSelf.OfType<VariableInitializer>().Select(node => node.GetILVariable())
            .Concat(region.DescendantsAndSelf.OfType<ForeachStatement>().Select(node => node.GetILVariable()))
            .Where(variable => variable is not null).ToHashSet();
        var result = new JsonArray();
        var seen = new HashSet<ILVariable>();
        foreach (var identifier in region.DescendantsAndSelf.OfType<IdentifierExpression>())
        {
            if (identifier.GetILVariable() is not { } variable || declared.Contains(variable) || !seen.Add(variable)) continue;
            result.Add(new JsonObject { ["name"] = identifier.Identifier, ["type"] = variable.Type.FullName,
                ["kind"] = variable.Kind == VariableKind.Parameter ? "method_parameter" : "external_local",
                ["scope"] = "symbolic_entry_value; reaching_definitions_and_current_value_not_captured" });
        }
        return result;
    }

    private static JsonObject InteractionSourceRecord(NativeCSharpDocument document, AstNode excerpt, string coverage)
    {
        var rendered = RenderOwnedCSharp(excerpt);
        string sha = CSharpHash(Encoding.UTF8.GetBytes(rendered.Code));
        var result = MethodSourceIdentity(document.Method);
        result["id"] = "interaction:" + document.Method.Module.ModuleVersionId + ":" + document.Method.MetadataToken + ":" + sha;
        result["metadataToken"] = document.Method.MetadataToken; result["assemblySha256"] = document.Module.Sha256;
        result["coverage"] = coverage; result["code"] = rendered.Code; result["codeSha256"] = sha;
        result["decompiler"] = new JsonObject { ["name"] = "ICSharpCode.Decompiler", ["version"] = NativeCSharpVersion,
            ["assemblySha256"] = NativeCSharpDecompilerSha256, ["settings"] = "csharp_default_no_indentation_v1" };
        return result;
    }

    private static JsonArray InteractionSpawnSites(NativeCSharpDocument document, AstNode region, JsonArray gaps, CancellationToken cancellation)
    {
        var result = new JsonArray(); NativeSourceCallIndex? index = null;
        var ends = CSharpConditionalEnds(document.Method);
        foreach (var invocation in region.DescendantsAndSelf.OfType<InvocationExpression>().Where(LifecycleSpawn))
        {
            cancellation.ThrowIfCancellationRequested();
            var symbol = (IMethod)invocation.GetSymbol()!;
            var offsets = (index ??= new NativeSourceCallIndex(document.Method)).Match(invocation, symbol, lifecycleSpawn: true);
            if (offsets.Count != 1) { gaps.Add("interaction_spawn_il_mapping_not_unique"); continue; }
            int parameter = symbol.Parameters.ToList().FindIndex(value => string.Equals(value.Name, "Type", StringComparison.OrdinalIgnoreCase));
            var arguments = invocation.Arguments.ToArray(); var types = new JsonArray();
            if (parameter >= 0 && parameter < arguments.Length && arguments[parameter] is PrimitiveExpression { Value: int literal }) types.Add(literal);
            var predicates = new JsonArray();
            foreach (var control in invocation.Ancestors.TakeWhile(node => node != region.Parent).OfType<IfElseStatement>())
                foreach (int offset in control.Condition.DescendantsAndSelf.Prepend(control).SelectMany(node => node.Annotations.OfType<ILInstruction>())
                    .SelectMany(instruction => instruction.ILRanges).Where(range => ends.TryGetValue(range.Start, out int end) && range.End == end)
                    .Select(range => range.Start).Distinct().Order())
                { string key = "b" + offset.ToString(CultureInfo.InvariantCulture); if (!predicates.Any(value => value!.GetValue<string>() == key)) predicates.Add(key); }
            var row = MethodSourceIdentity(document.Method); row["at"] = offsets.Single(); row["projectileTypes"] = types;
            row["requiredPredicates"] = predicates;
            row["unresolved"] = "conditional_interaction_source_candidate; guards_and_external_inputs_in_source; enclosing_flow_hooks_and_entry_identity_unknown; not_an_executed_spawn"
                + (types.Count == 0 ? "; spawn_type_requires_runtime_expression" : "");
            result.Add(row);
        }
        return result;
    }

    private static bool PositiveInteractionEquality(BinaryOperatorExpression comparison, Expression condition)
    {
        AstNode current = comparison;
        while (current != condition)
        {
            var parent = current.Parent;
            if (parent is not ParenthesizedExpression
                && parent is not BinaryOperatorExpression { Operator: BinaryOperatorType.ConditionalAnd or BinaryOperatorType.ConditionalOr }) return false;
            current = parent;
        }
        return true;
    }

    private sealed record InteractionRegion(AstNode Body, Func<Statement> Materialize, Expression Condition, JsonArray Witnesses);

    private static SwitchStatement CloneInteractionSwitchSection(SwitchStatement source, SwitchSection selected)
    {
        var original = source.SwitchSections.ToArray();
        try
        {
            foreach (var section in original) if (section != selected) section.Remove();
            return (SwitchStatement)source.Clone();
        }
        finally
        {
            foreach (var section in source.SwitchSections.ToArray()) section.Remove();
            foreach (var section in original) source.SwitchSections.Add(section);
        }
    }

    private static IEnumerable<InteractionRegion> InteractionRegions(NativeCSharpDocument document, int type, int style, CancellationToken cancellation)
    {
        foreach (var node in document.Declaration.Body.Descendants)
        {
            cancellation.ThrowIfCancellationRequested();
            if (node is IfElseStatement branch)
            {
                var witnesses = new JsonArray();
                foreach (var comparison in branch.Condition.DescendantsAndSelf.OfType<BinaryOperatorExpression>())
                    if (PositiveInteractionEquality(comparison, branch.Condition)
                        && LifecycleIdentityEquality(comparison, out var field, out int literal) && literal == (field == "type" ? type : style))
                        witnesses.Add(new JsonObject { ["field"] = "Terraria.Projectile." + field, ["literal"] = literal });
                if (witnesses.Count > 0) yield return new(branch.TrueStatement, () => CloneCSharpTrueArm(branch), branch.Condition, witnesses);
            }
            else if (node is SwitchSection section && section.Parent is SwitchStatement switched
                && switched.Expression.GetSymbol() is IField field && field.DeclaringType.FullName == typeof(Projectile).FullName
                && field.Name is "type" or "aiStyle"
                && (switched.Expression is IdentifierExpression or MemberReferenceExpression { Target: ThisReferenceExpression or BaseReferenceExpression })
                && section.CaseLabels.Any(label => label.Expression is PrimitiveExpression { Value: int literal }
                    && literal == (field.Name == "type" ? type : style)))
            {
                var witnesses = new JsonArray(new JsonObject { ["field"] = "Terraria.Projectile." + field.Name,
                    ["literal"] = field.Name == "type" ? type : style });
                yield return new(section, () => CloneInteractionSwitchSection(switched, section), switched.Expression, witnesses);
            }
        }
    }

    private static bool InteractionHelperDispatchExact(MethodInfo method)
        => !method.IsVirtual && !method.IsAbstract && !method.ContainsGenericParameters;

    private static JsonObject BuildProjectileInteractionSource(NativeCSharpDocument document, int type, int style,
        CancellationToken cancellation, int regionLimit = InteractionRegionLimit,
        int regionCharacters = InteractionRegionCharacters, int totalCharacters = InteractionTotalCharacters)
    {
        cancellation.ThrowIfCancellationRequested();
        var method = document.Method;
        var result = new JsonObject { ["root"] = method.Name, ["rootCertificate"] = MethodSourceIdentity(method),
            ["records"] = new JsonArray(), ["helpers"] = new JsonArray(),
            ["unresolved"] = new JsonArray("other_regions_and_callees_unresolved; absence_not_proved") };
        var records = result["records"]!.AsArray(); var helpers = result["helpers"]!.AsArray(); var gaps = result["unresolved"]!.AsArray();
        var candidates = InteractionRegions(document, type, style, cancellation).ToArray();
        var selectedArms = candidates.Select(region => region.Body).ToHashSet();
        var helperAttempts = new Dictionary<MethodInfo, string?>();
        NativeSourceCallIndex? callIndex = null;
        int count = 0, characters = 0;
        foreach (var region in candidates)
        {
            cancellation.ThrowIfCancellationRequested();
            if (region.Body.Ancestors.Any(selectedArms.Contains)) continue;
            string label = "region:" + (count + 1).ToString(CultureInfo.InvariantCulture);
            try
            {
                if (++count > regionLimit) throw new NotSupportedException("interaction_region_count_bound");
                if (region.Body is SwitchSection section && section.CaseLabels.Any(label => label.Expression is not PrimitiveExpression { Value: int }))
                    throw new NotSupportedException("interaction_switch_label_unsupported");
                if (region.Body.Ancestors.Any(node => node is TryCatchStatement or UsingStatement or LockStatement))
                    throw new NotSupportedException("csharp_region_nonlocal_control_unsupported");
                var excerpt = region.Materialize();
                var check = new BlockStatement(); check.Statements.Add(excerpt);
                string? refusal = CSharpRegionRefusal(check, method);
                if (refusal is not null && refusal != "csharp_region_external_local_dependency") throw new NotSupportedException(refusal);
                // Legacy refusal checks locals before exits. The wrapper retains
                // a selected switch's own break scope, but never an omitted loop.
                foreach (var exit in check.Descendants.Where(node => node is BreakStatement or ContinueStatement))
                    if (!exit.Ancestors.TakeWhile(node => node != check).Any(node => node is ForStatement
                        or ForeachStatement or WhileStatement or DoWhileStatement || exit is BreakStatement && node is SwitchStatement))
                        throw new NotSupportedException("csharp_region_nonlocal_control_unsupported");
                // Keep the actual local identifiers, never reinterpret them as
                // live fields or inferred damage. This source-only record does
                // not assert lexical closure or complete reaching definitions.
                var record = InteractionSourceRecord(document, excerpt, "conditional_source_region; external_inputs_explicit");
                int size = record["code"]!.GetValue<string>().Length;
                if (size > regionCharacters) throw new NotSupportedException("interaction_region_character_bound");
                if (characters + size > totalCharacters) throw new NotSupportedException("interaction_total_character_bound");
                // AST statement ranges can be coarse/nonlocal. This is only
                // an ordered region index; only matched callsites claim IL at.
                record["regionIndex"] = count;
                record["entryCondition"] = RenderCSharp(region.Condition, includeLocations: false).Code.Trim();
                record["externalInputs"] = InteractionExternalInputs(excerpt);
                record["identityWitnesses"] = region.Witnesses.DeepClone();
                record["spawnSites"] = InteractionSpawnSites(document, excerpt, gaps, cancellation);
                var links = new JsonArray(); record["helperCalls"] = links;
                records.Add(record); characters += size;
                foreach (var invocation in region.Body.DescendantsAndSelf.OfType<InvocationExpression>())
                {
                    cancellation.ThrowIfCancellationRequested();
                    if (invocation.GetSymbol() is not IMethod symbol || symbol.IsStatic || symbol.DeclaringType.FullName != typeof(Projectile).FullName
                        || invocation.Target is not (IdentifierExpression or MemberReferenceExpression { Target: ThisReferenceExpression or BaseReferenceExpression })) continue;
                    var calls = (callIndex ??= new NativeSourceCallIndex(method)).Match(invocation, symbol);
                    if (calls.Count != 1) { gaps.Add(label + ":helper_call_mapping_not_unique"); continue; }
                    int at = calls.Single();
                    if (AttackCode(method).Single(instruction => instruction.Offset == at).Arg is not MethodInfo called
                        || called.DeclaringType != typeof(Projectile) || called.Module != method.Module || called == method
                        || called.GetMethodBody() is null) continue;
                    var link = MethodSourceIdentity(called); link["at"] = at; links.Add(link);
                    if (!InteractionHelperDispatchExact(called)) { link["unresolved"] = "helper_virtual_or_open_generic_dispatch_unknown"; continue; }
                    if (helperAttempts.TryGetValue(called, out var previous))
                    { if (previous is not null) link["unresolved"] = previous; continue; }
                    if (helperAttempts.Count >= 4) { link["unresolved"] = "interaction_helper_count_bound"; continue; }
                    helperAttempts.Add(called, null);
                    try
                    {
                        var helper = GetNativeCSharpDocument(called, cancellation);
                        if (helper.Characters > regionCharacters || characters + helper.Characters > totalCharacters)
                            throw new NotSupportedException("interaction_helper_character_bound");
                        var helperRecord = InteractionSourceRecord(helper, helper.Tree.Clone(), "whole_method_source_only; one_hop_no_call_evaluation");
                        int helperSize = helperRecord["code"]!.GetValue<string>().Length;
                        if (helperSize > regionCharacters || characters + helperSize > totalCharacters)
                            throw new NotSupportedException("interaction_helper_character_bound");
                        helperRecord["spawnSites"] = InteractionSpawnSites(helper, helper.Tree, gaps, cancellation);
                        helpers.Add(helperRecord); characters += helperSize;
                    }
                    catch (Exception error) when (error is not OutOfMemoryException && error is not OperationCanceledException)
                    { string reason = error is NotSupportedException ? error.Message : error.GetType().Name;
                        helperAttempts[called] = reason; link["unresolved"] = reason; }
                }
            }
            catch (Exception error) when (error is not OutOfMemoryException && error is not OperationCanceledException)
            { gaps.Add(label + ":" + (error is NotSupportedException ? error.Message : error.GetType().Name)); }
        }
        if (records.Count == 0) gaps.Add("no_admitted_matching_region; absence_not_proved");
        cancellation.ThrowIfCancellationRequested();
        return result;
    }
}
