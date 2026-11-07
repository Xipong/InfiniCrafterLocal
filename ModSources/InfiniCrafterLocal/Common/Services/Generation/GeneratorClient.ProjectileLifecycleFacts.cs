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

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Conservative IL/dataflow preflight for AST equality queries. Returning
    // false is allowed only when every relevant branch input was resolved and
    // no branch can compare the requested field with the captured literal.
    // Any unsupported/ambiguous dataflow returns true and keeps the ILSpy path.
    private static bool SourceMayCompareFieldToInt(ParentSourceMethod body, Type declaringType, string fieldName, int literal)
    {
        bool uncertain = false;

        bool Matches(string id, Func<ParentSourceMethod.Value, bool> predicate, int depth = 0)
        {
            if (depth > 8) { uncertain = true; return false; }
            var definitions = body.Definitions(id).ToArray();
            if (definitions.Length == 0) { uncertain = true; return false; }
            foreach (var definition in definitions)
            {
                if (definition.Op.StartsWith("unresolved_", StringComparison.Ordinal))
                { uncertain = true; continue; }
                if (predicate(definition)) return true;
                if (definition.Inputs.Count == 1 && (definition.Op.StartsWith("conv.", StringComparison.Ordinal)
                    || definition.Op is "box" or "unbox.any"))
                    if (Matches(definition.Inputs[0], predicate, depth + 1)) return true;
            }
            return false;
        }

        bool IsField(string id) => Matches(id, value => value.Op == "ldfld"
            && value.Operand is FieldInfo field && field.DeclaringType == declaringType && field.Name == fieldName);
        bool IsLiteral(string id) => Matches(id, value => value.Op == "const" && Equals(value.Operand, literal));
        bool Pair(IReadOnlyList<string> inputs) => inputs.Count == 2
            && (IsField(inputs[0]) && IsLiteral(inputs[1]) || IsField(inputs[1]) && IsLiteral(inputs[0]));

        foreach (var branch in body.Statements)
        {
            if ((branch.Op.StartsWith("beq", StringComparison.Ordinal) || branch.Op.StartsWith("bne", StringComparison.Ordinal))
                && Pair(branch.Inputs))
                return true;

            if (branch.Op is not ("brtrue" or "brtrue.s" or "brfalse" or "brfalse.s") || branch.Inputs.Count != 1)
                continue;
            var tests = body.Definitions(branch.Inputs[0]).ToArray();
            if (tests.Length == 0) { uncertain = true; continue; }
            foreach (var test in tests)
            {
                if (test.Op.StartsWith("unresolved_", StringComparison.Ordinal)) { uncertain = true; continue; }
                if (test.Op == "ceq" && Pair(test.Inputs)) return true;
            }
        }
        return uncertain;
    }

    // Additive read-only source evidence, not an identity proof or a graph
    // replacement. The complete original guard and lexical body stay together.
    private const string LifecycleScope = "Conditional source regions only. The original guard must be reached; enclosing flow, hooks, captured-entry identity preservation and all other Kill regions remain unknown. Live type/owner/state predicates are not evaluated. No source record proves execution or absence of other effects.";
    private const string LifecycleCallScope = "conditional_lifecycle_source_candidate; full_guards_and_arguments_in_source_region; enclosing_flow_hooks_and_entry_identity_unknown; not_an_executed_spawn";
    private const int LifecycleRegionLimit = 16, LifecycleRegionCharacters = 24000, LifecycleTotalCharacters = 64000;

    private static JsonObject CaptureProjectileLifecycleSource(int type, int style, JsonArray references)
    {
        var method = typeof(Projectile).GetMethod("Kill", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic, null, Type.EmptyTypes, null);
        var result = LifecycleEnvelope(type, style);
        if (method is null) { result["unresolved"]!.AsArray().Add("Kill_root_missing"); return result; }
        result["rootCertificate"] = MethodSourceIdentity(method);
        currentParentAnalysis?.ThrowIfCancelled();
        // Query the same exact IL/dataflow graph before constructing C# syntax.
        // A false result means no branch can feed the AST equality recognizer.
        bool mayMatch;
        try
        {
            var source = ReadCompleteSourceMethod(method);
            mayMatch = SourceMayCompareFieldToInt(source, typeof(Projectile), "type", type)
                || SourceMayCompareFieldToInt(source, typeof(Projectile), "aiStyle", style);
        }
        catch (NotSupportedException) { mayMatch = true; }
        if (!mayMatch)
        {
            result["unresolved"]!.AsArray().Add("Kill_no_admitted_matching_spawn_region; absence_not_proved");
            return result;
        }
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(currentParentAnalysis?.Cancellation ?? CancellationToken.None);
        timeout.CancelAfter(TimeSpan.FromSeconds(20));
        try
        {
            var pendingReferences = new JsonArray();
            while (!Monitor.TryEnter(nativeCSharpGate, 50)) timeout.Token.ThrowIfCancellationRequested();
            try { result = BuildProjectileLifecycleSource(GetNativeCSharpDocument(method, timeout.Token), type, style, pendingReferences, timeout.Token); }
            finally { Monitor.Exit(nativeCSharpGate); }
            foreach (var reference in pendingReferences) references.Add(reference!.DeepClone());
        }
        catch (OperationCanceledException)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            result["unresolved"]!.AsArray().Add("Kill_source_decompilation_time_bound");
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        { result["unresolved"]!.AsArray().Add("Kill_source:" + (error is NotSupportedException ? error.Message : error.GetType().Name)); }
        return result;
    }

    private static JsonObject LifecycleEnvelope(int type, int style) => new()
    {
        ["source"] = "verified_conditional_native_lifecycle_csharp", ["version"] = 1, ["root"] = "Kill",
        ["relevanceIdentity"] = new JsonObject { ["Projectile.type"] = type, ["Projectile.aiStyle"] = style },
        ["scope"] = LifecycleScope, ["records"] = new JsonArray(),
        ["unresolved"] = new JsonArray("Kill_coverage_partial; other_regions_and_callees_unresolved", "entry_identity_preservation_not_proved; receiver_passing_calls_and_hooks_not_evaluated")
    };

    private static bool LifecycleIdentityEquality(BinaryOperatorExpression comparison, out string field, out int literal)
    {
        field = ""; literal = 0;
        if (comparison.Operator != BinaryOperatorType.Equality) return false;
        bool Read(Expression expression, out string name)
        {
            name = "";
            if (expression.GetSymbol() is not IField member || member.DeclaringType.FullName != typeof(Projectile).FullName
                || member.Name is not ("type" or "aiStyle")
                || expression is not (IdentifierExpression or MemberReferenceExpression { Target: ThisReferenceExpression or BaseReferenceExpression })) return false;
            name = member.Name; return true;
        }
        if (Read(comparison.Left, out field) && comparison.Right is PrimitiveExpression { Value: int right }) { literal = right; return true; }
        if (Read(comparison.Right, out field) && comparison.Left is PrimitiveExpression { Value: int left }) { literal = left; return true; }
        return false;
    }

    private static bool LifecycleSpawn(InvocationExpression expression)
        => expression.GetSymbol() is IMethod method && method.DeclaringType.FullName == typeof(Projectile).FullName
            && method.Name is "NewProjectile" or "NewProjectileDirect";

    private static JsonObject BuildProjectileLifecycleSource(NativeCSharpDocument document, int type, int style,
        JsonArray references, CancellationToken cancellation, int regionLimit = LifecycleRegionLimit,
        int regionCharacters = LifecycleRegionCharacters, int totalCharacters = LifecycleTotalCharacters)
    {
        cancellation.ThrowIfCancellationRequested();
        var result = LifecycleEnvelope(type, style);
        var method = document.Method; result["rootCertificate"] = MethodSourceIdentity(method);
        var records = result["records"]!.AsArray(); var gaps = result["unresolved"]!.AsArray();
        NativeSourceCallIndex? callIndex = null; var ends = CSharpConditionalEnds(method);
        bool Matching(IfElseStatement branch)
        {
            cancellation.ThrowIfCancellationRequested();
            return branch.Condition.DescendantsAndSelf.OfType<BinaryOperatorExpression>()
                .Any(comparison => LifecycleIdentityEquality(comparison, out var field, out int literal)
                    && literal == (field == "type" ? type : style));
        }
        var candidates = document.Declaration.Body.Descendants.OfType<IfElseStatement>()
            .Where(branch => Matching(branch) && branch.TrueStatement.DescendantsAndSelf.OfType<InvocationExpression>().Any(LifecycleSpawn)).ToArray();
        int count = 0, characters = 0;
        foreach (var branch in candidates)
        {
            cancellation.ThrowIfCancellationRequested();
            // An outer matching region owns its nested source, including all
            // conditions and mutations. A refused outer body is never cropped.
            if (candidates.Any(outer => outer != branch && branch.Ancestors.Contains(outer.TrueStatement))) continue;
            int regionOffset = branch.Annotations.OfType<ILInstruction>().Select(instruction => instruction.StartILOffset).DefaultIfEmpty(-1).Min();
            string label = "region_il@" + regionOffset.ToString(CultureInfo.InvariantCulture);
            try
            {
                if (++count > regionLimit) throw new NotSupportedException("lifecycle_region_count_bound");
                var excerpt = (IfElseStatement)branch.Clone(); excerpt.FalseStatement = Statement.Null;
                string? refusal = CSharpRegionRefusal(branch.TrueStatement, method);
                if (refusal is not null) throw new NotSupportedException(refusal);
                // Check the guard as well as its body. A local read computed
                // before this region cannot silently become a live field read.
                refusal = CSharpRegionRefusal(excerpt, method);
                if (refusal is not null) throw new NotSupportedException(refusal);
                var rendered = RenderCSharp(excerpt);
                cancellation.ThrowIfCancellationRequested();
                if (rendered.Code.Length > regionCharacters) throw new NotSupportedException("lifecycle_region_character_bound");
                if (characters + rendered.Code.Length > totalCharacters) throw new NotSupportedException("lifecycle_total_character_bound");
                var witnesses = new JsonArray();
                foreach (var comparison in branch.Condition.DescendantsAndSelf.OfType<BinaryOperatorExpression>())
                {
                    if (!LifecycleIdentityEquality(comparison, out var field, out int literal)
                        || literal != (field == "type" ? type : style)) continue;
                    // This typed AST read is a relevance witness only. It does
                    // not choose an edge, even when the captured ID matches it.
                    witnesses.Add(new JsonObject { ["field"] = "Terraria.Projectile." + field, ["literal"] = literal });
                }
                if (witnesses.Count == 0) throw new NotSupportedException("lifecycle_typed_identity_witness_missing");
                var sites = new JsonArray(); var rows = new List<JsonObject>(); var offsets = new HashSet<int>();
                foreach (var invocation in branch.TrueStatement.DescendantsAndSelf.OfType<InvocationExpression>().Where(LifecycleSpawn))
                {
                    cancellation.ThrowIfCancellationRequested();
                    var symbol = (IMethod)invocation.GetSymbol()!;
                    var calls = (callIndex ??= new NativeSourceCallIndex(method)).Match(invocation, symbol, lifecycleSpawn: true);
                    if (calls.Count != 1) throw new NotSupportedException("lifecycle_spawn_il_mapping_not_unique");
                    int at = calls.Single(); offsets.Add(at);
                    int parameter = symbol.Parameters.ToList().FindIndex(value => string.Equals(value.Name, "Type", StringComparison.OrdinalIgnoreCase));
                    var arguments = invocation.Arguments.ToArray(); var types = new JsonArray();
                    if (parameter >= 0 && parameter < arguments.Length && arguments[parameter] is PrimitiveExpression { Value: int id }) types.Add(id);
                    // These are source anchors, not branch truth assertions. All
                    // compound/owner/state/loop predicates remain in the code.
                    var predicates = new JsonArray();
                    foreach (var control in invocation.Ancestors.TakeWhile(node => node != branch.Parent).OfType<IfElseStatement>())
                        foreach (int offset in control.Condition.DescendantsAndSelf.Prepend(control).SelectMany(node => node.Annotations.OfType<ILInstruction>())
                            .SelectMany(instruction => instruction.ILRanges).Where(range => ends.TryGetValue(range.Start, out int end) && range.End == end)
                            .Select(range => range.Start).Distinct().Order())
                        { string key = "b" + offset.ToString(CultureInfo.InvariantCulture); if (!predicates.Any(value => value!.GetValue<string>() == key)) predicates.Add(key); offsets.Add(offset); }
                    var row = MethodSourceIdentity(method); row["at"] = at; row["projectileTypes"] = types;
                    row["requiredPredicates"] = predicates;
                    row["unresolved"] = LifecycleCallScope + (types.Count == 0 ? "; spawn_type_requires_runtime_expression" : "");
                    rows.Add(row); sites.Add(row.DeepClone());
                }
                if (sites.Count == 0) throw new NotSupportedException("lifecycle_spawn_site_missing");
                string sha = CSharpHash(Encoding.UTF8.GetBytes(rendered.Code));
                var record = MethodSourceIdentity(method);
                record["id"] = "lifecycle:" + method.Module.ModuleVersionId + ":" + method.MetadataToken + ":" + sha;
                record["metadataToken"] = method.MetadataToken; record["assemblySha256"] = document.Module.Sha256;
                record["decompiler"] = new JsonObject { ["name"] = "ICSharpCode.Decompiler", ["version"] = NativeCSharpVersion,
                    ["assemblySha256"] = NativeCSharpDecompilerSha256, ["settings"] = "csharp_default_no_indentation_v1" };
                record["coverage"] = "conditional_closed_lexical_region";
                record["code"] = rendered.Code; record["codeSha256"] = sha;
                record["entryCondition"] = RenderCSharp(branch.Condition, includeLocations: false).Code.Trim();
                record["identityWitnesses"] = witnesses; record["spawnSites"] = sites;
                record["locations"] = new JsonArray(offsets.Order().Select(offset =>
                {
                    var match = rendered.Locations.Where(location => location.Start <= offset && offset < location.End)
                        .OrderBy(location => location.End - location.Start).ThenBy(location => location.EndLine - location.StartLine).FirstOrDefault();
                    return (JsonNode?) (match is null ? new JsonObject { ["ilOffset"] = offset, ["unresolved"] = "decompiler_source_location_unavailable" }
                        : new JsonObject { ["ilOffset"] = offset, ["startLine"] = match.StartLine, ["endLine"] = match.EndLine });
                }).ToArray());
                records.Add(record); characters += rendered.Code.Length;
                foreach (var row in rows) references.Add(row);
            }
            catch (Exception error) when (error is not OutOfMemoryException && error is not OperationCanceledException)
            { gaps.Add(label + ":" + (error is NotSupportedException ? error.Message : error.GetType().Name)); }
        }
        if (records.Count == 0) gaps.Add("Kill_no_admitted_matching_spawn_region; absence_not_proved");
        cancellation.ThrowIfCancellationRequested();
        return result;
    }
}
