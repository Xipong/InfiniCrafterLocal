#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata.Ecma335;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;
using ICSharpCode.Decompiler.TypeSystem;
using InfiniCrafterLocal.Common.Analysis;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private const string MechanicsIdentityAssumption = "Approximate readable view: captured Projectile.type/aiStyle assumed stable across opaque calls. Not a certified identity proof or executed gameplay. Strict source remains separate. Potentially reachable explicit identity-field stores/addresses, unknown receiver binding and unsupported control scopes prevent pruning.";

    private static bool MechanicsIdentityField(Expression expression, out string name, bool capturedReceiverOnly = true)
    {
        name = "";
        if (expression.GetSymbol() is not IField field || field.DeclaringType.FullName != typeof(Projectile).FullName
            || field.Name is not ("type" or "aiStyle")) return false;
        if (capturedReceiverOnly && expression is not IdentifierExpression
            && expression is not MemberReferenceExpression { Target: ThisReferenceExpression or BaseReferenceExpression }) return false;
        name = field.Name; return true;
    }

    // Deliberately no evaluation of calls, getters, locals, tables or arithmetic.
    // Unknown left operands remain unknown even when an algebraic result seems
    // constant: their side effects must execute before short-circuit selection.
    private static bool? MechanicsCondition(Expression expression, int type, int style)
    {
        if (expression is ParenthesizedExpression parens) return MechanicsCondition(parens.Expression, type, style);
        if (expression is PrimitiveExpression { Value: bool value }) return value;
        if (expression is UnaryOperatorExpression { Operator: UnaryOperatorType.Not } unary)
        { var inner = MechanicsCondition(unary.Expression, type, style); return inner is null ? null : !inner.Value; }
        if (expression is not BinaryOperatorExpression binary) return null;
        if (binary.Operator is BinaryOperatorType.ConditionalAnd or BinaryOperatorType.ConditionalOr)
        {
            bool? left = MechanicsCondition(binary.Left, type, style);
            if (left is null) return null;
            if (binary.Operator == BinaryOperatorType.ConditionalAnd && !left.Value) return false;
            if (binary.Operator == BinaryOperatorType.ConditionalOr && left.Value) return true;
            return MechanicsCondition(binary.Right, type, style);
        }
        int? Integer(Expression item)
        {
            if (item is ParenthesizedExpression parenthesized) return Integer(parenthesized.Expression);
            if (item is PrimitiveExpression { Value: int literal }) return literal;
            return MechanicsIdentityField(item, out string field) ? field == "type" ? type : style : null;
        }
        int? a = Integer(binary.Left), b = Integer(binary.Right);
        if (a is null || b is null) return null;
        return binary.Operator switch {
            BinaryOperatorType.Equality => a == b, BinaryOperatorType.InEquality => a != b,
            BinaryOperatorType.LessThan => a < b, BinaryOperatorType.LessThanOrEqual => a <= b,
            BinaryOperatorType.GreaterThan => a > b, BinaryOperatorType.GreaterThanOrEqual => a >= b,
            _ => null
        };
    }

    // An explicit store outside a retained excerpt may be ignored only when
    // its own typed AST expression is in a false identity arm. Every other
    // explicit store/address in the original method still vetoes specialization,
    // so the assumptions cannot hide a preceding or unknown-path identity change.
    private static bool MechanicsExcludedIdentityAccess(NativeCSharpDocument document, int offset, int type, int style)
    {
        bool Under(AstNode node, AstNode ancestor) => node == ancestor || node.Ancestors.Contains(ancestor);
        bool Excluded(AstNode node)
        {
            foreach (var branch in node.Ancestors.OfType<IfElseStatement>())
            {
                bool? condition = MechanicsCondition(branch.Condition, type, style);
                if (condition is null) continue;
                var discarded = condition.Value ? branch.FalseStatement : branch.TrueStatement;
                if (!Under(node, discarded)) continue;
                // Local decompiler gotos inside a discarded arm are harmless.
                // An inbound jump would bypass its guard and invalidates this
                // exclusion. Goto-case scopes remain unsupported here.
                var labels = discarded.DescendantsAndSelf.OfType<LabelStatement>().Select(label => label.Label).ToHashSet();
                if (document.Tree.Descendants.OfType<GotoStatement>().Any(jump => labels.Contains(jump.Label) && !Under(jump, discarded))
                    || document.Tree.Descendants.OfType<GotoCaseStatement>().Any()) continue;
                return true;
            }
            return false;
        }
        var accesses = document.Declaration.Body.Descendants.OfType<Expression>().Where(node =>
            node is AssignmentExpression assignment && MechanicsIdentityField(assignment.Left, out _, false)
            || node is UnaryOperatorExpression unary && unary.Operator is UnaryOperatorType.Increment or UnaryOperatorType.Decrement
                or UnaryOperatorType.PostIncrement or UnaryOperatorType.PostDecrement && MechanicsIdentityField(unary.Expression, out _, false)
            || node is DirectionExpression direction && direction.Expression.DescendantsAndSelf.OfType<Expression>()
                .Any(value => MechanicsIdentityField(value, out _, false)))
            .Where(node => node.DescendantsAndSelf.SelectMany(child => child.Annotations.OfType<ILInstruction>())
                .Any(instruction => instruction.ILRanges.Any(range => range.Start <= offset && offset < range.End)
                    // ILSpy assigns a ++/-- node the arithmetic range, ending
                    // exactly at its following stfld, rather than the store's
                    // range. Accept only that adjacent native store boundary.
                    || node is UnaryOperatorExpression && instruction is NumericCompoundAssign
                        && instruction.ILRanges.Any(range => range.End == offset)
                        && AttackCode(document.Method).Any(code => code.Offset == offset && code.Op == "stfld"
                            && code.Arg is FieldInfo field && field.DeclaringType == typeof(Projectile)
                            && MechanicsIdentityField(((UnaryOperatorExpression)node).Expression, out string name, false)
                            && name == field.Name))).ToArray();
        return accesses.Length > 0 && accesses.All(Excluded);
    }

    private static string? MechanicsPruningRefusal(NativeCSharpDocument document, AstNode? region = null, int type = 0, int style = 0)
    {
        if (region is null && document.Method.GetMethodBody()!.ExceptionHandlingClauses.Count != 0) return "exception_scope_not_pruned";
        if (document.Method.IsStatic || document.Method.DeclaringType is null || !typeof(Projectile).IsAssignableFrom(document.Method.DeclaringType)) return "captured_this_receiver_not_established";
        // Read-only IL veto also covers unsafe &field syntax, not just the
        // decompiler's ref/out DirectionExpression representation.
        foreach (var instruction in AttackCode(document.Method))
            if (instruction.Arg is FieldInfo field && field.DeclaringType == typeof(Projectile) && field.Name is "type" or "aiStyle")
            {
                if (region is not null && instruction.Op is "stfld" or "ldflda"
                    && MechanicsExcludedIdentityAccess(document, instruction.Offset, type, style)) continue;
                if (instruction.Op == "ldflda") return "identity_field_address_exposure_not_pruned";
                if (instruction.Op == "stfld") return "explicit_identity_write_not_pruned";
            }
        foreach (var node in (region ?? document.Declaration.Body).DescendantsAndSelf)
        {
            if (node is GotoStatement or GotoCaseStatement or LabelStatement or LambdaExpression or AnonymousMethodExpression or LocalFunctionDeclarationStatement)
                return "nonlocal_control_or_nested_scope_not_pruned";
            if (node is AssignmentExpression assignment && MechanicsIdentityField(assignment.Left, out _, false)) return "explicit_identity_write_not_pruned";
            if (node is UnaryOperatorExpression unary && unary.Operator is UnaryOperatorType.Increment or UnaryOperatorType.Decrement or UnaryOperatorType.PostIncrement or UnaryOperatorType.PostDecrement
                && MechanicsIdentityField(unary.Expression, out _, false)) return "explicit_identity_write_not_pruned";
            if (node is DirectionExpression direction && direction.Expression.DescendantsAndSelf.OfType<Expression>().Any(value => MechanicsIdentityField(value, out _, false)))
                return "identity_address_exposure_not_pruned";
        }
        return null;
    }

    // One index per source projection, shared by removed/retained calls and
    // spawn candidates. Keep the exact old token/type/name predicate: a name or
    // enclosing IL span alone cannot establish a call (especially an overload).
    private sealed class NativeSourceCallIndex
    {
        private readonly Dictionary<(int Token, string? Type, string Name), List<AmmoIl>> calls = new();

        internal NativeSourceCallIndex(MethodInfo method)
        {
            foreach (var instruction in AttackCode(method))
            {
                if (instruction.Op is not ("call" or "callvirt") || instruction.Arg is not MethodBase called) continue;
                var key = (called.MetadataToken, called.DeclaringType?.FullName, called.Name);
                if (!calls.TryGetValue(key, out var offsets)) calls.Add(key, offsets = new());
                offsets.Add(instruction);
            }
            foreach (var offsets in calls.Values) offsets.Sort((left, right) => left.Offset.CompareTo(right.Offset));
        }

        internal HashSet<int> Match(InvocationExpression invocation, IMethod symbol, bool lifecycleSpawn = false)
        {
            var matches = new HashSet<int>();
            if (!calls.TryGetValue((MetadataTokens.GetToken(symbol.MetadataToken), symbol.DeclaringType.FullName, symbol.Name), out var offsets))
                return matches;
            foreach (var range in invocation.DescendantsAndSelf.SelectMany(node => node.Annotations.OfType<ILInstruction>())
                .SelectMany(instruction => instruction.ILRanges).Where(range => range.End > range.Start))
            {
                int first = 0, last = offsets.Count;
                while (first < last)
                {
                    int middle = first + (last - first) / 2;
                    if (offsets[middle].Offset < range.Start) first = middle + 1;
                    else last = middle;
                }
                // Search each real half-open range, never the enclosing span:
                // holes must not admit calls; overlapping annotations count once.
                for (int i = first; i < offsets.Count && offsets[i].Offset < range.End; i++)
                {
                    // Lifecycle has a stronger native signature proof than the
                    // mechanics view. Apply it only to exact indexed candidates.
                    if (lifecycleSpawn && (offsets[i].Arg is not MethodInfo called || called.DeclaringType != typeof(Projectile)
                        || called.GetParameters().Length != symbol.Parameters.Count)) continue;
                    matches.Add(offsets[i].Offset);
                }
            }
            return matches;
        }
    }

    private static HashSet<int> MechanicsCallOffsets(IEnumerable<InvocationExpression> invocations, NativeSourceCallIndex index, JsonArray unknowns, bool includeAmbiguous = false)
    {
        var offsets = new HashSet<int>();
        foreach (var invocation in invocations)
        {
            if (invocation.GetSymbol() is not IMethod symbol) continue;
            var matches = index.Match(invocation, symbol);
            if (matches.Count == 1) offsets.Add(matches.Single());
            else if (!unknowns.Any(value => value?.GetValue<string>() == "some_call_offsets_not_uniquely_mapped"))
                unknowns.Add("some_call_offsets_not_uniquely_mapped");
            if (includeAmbiguous) offsets.UnionWith(matches);
        }
        return offsets;
    }

    // A deliberately flow-insensitive upper bound, not a local evaluator. Every
    // surviving write to a bound local must be an integer literal. Include even
    // overwritten/later writes: extra candidates are safe; a missing one is not.
    // Only full methods admitted by the identity/control checks can use this.
    private static JsonArray MechanicsSpawnTypeCandidates(SyntaxTree tree, NativeSourceCallIndex callIndex, JsonArray gaps)
    {
        int[]? Candidates(Expression expression)
        {
            if (expression is PrimitiveExpression { Value: int literal }) return new[] { literal };
            if (expression is not IdentifierExpression identifier || identifier.GetILVariable() is not { } variable
                || variable.Kind == VariableKind.Parameter) return null;
            var declarations = tree.Descendants.OfType<VariableInitializer>()
                .Where(node => node.GetILVariable() == variable).ToArray();
            if (declarations.Length != 1 || declarations[0].Initializer is not PrimitiveExpression { Value: int initial }) return null;
            var values = new HashSet<int> { initial };
            foreach (var use in tree.Descendants.OfType<IdentifierExpression>().Where(node => node.GetILVariable() == variable))
            {
                AstNode target = use;
                while (target.Parent is ParenthesizedExpression) target = target.Parent;
                if (use.Ancestors.Any(node => node is DirectionExpression or UnaryOperatorExpression or UndocumentedExpression)) return null;
                if (use.Ancestors.OfType<AssignmentExpression>().Any(assignment =>
                    assignment.Left.DescendantsAndSelf.Contains(use) && assignment.Left != target)) return null;
                if (target.Parent is AssignmentExpression assignment && assignment.Left == target)
                {
                    if (assignment.Operator != AssignmentOperatorType.Assign || assignment.Right is not PrimitiveExpression { Value: int value }) return null;
                    values.Add(value);
                }
            }
            return values.Order().ToArray();
        }
        var result = new JsonArray();
        foreach (var invocation in tree.Descendants.OfType<InvocationExpression>())
        {
            if (invocation.GetSymbol() is not IMethod symbol || !symbol.IsStatic
                || symbol.DeclaringType.FullName != typeof(Projectile).FullName || symbol.Name != "NewProjectile") continue;
            int index = symbol.Parameters.ToList().FindIndex(parameter => parameter.Name == "Type");
            if (index < 0 || invocation.Arguments.Count <= index
                || invocation.Arguments.Any(argument => argument is NamedArgumentExpression)) continue;
            var candidates = Candidates(invocation.Arguments.ElementAt(index));
            if (candidates is null) continue;
            var offsets = MechanicsCallOffsets(new[] { invocation }, callIndex, gaps);
            if (offsets.Count != 1) continue;
            result.Add(new JsonObject { ["at"] = offsets.Single(),
                ["projectileTypes"] = new JsonArray(candidates.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray()),
                ["scope"] = "all_surviving_local_writes_are_integer_literals; conservative_union_not_execution" });
        }
        return result;
    }

    // Only syntactically unconditional exits from the method. Never infer an
    // exit through a condition, loop, switch, break or continue. Nested lexical
    // blocks retain their scopes; only their following siblings are unreachable.
    private static bool MechanicsTerminatesBlock(Statement statement) => statement is ReturnStatement or ThrowStatement
        || statement is BlockStatement block && block.Statements.LastOrDefault() is { } last && MechanicsTerminatesBlock(last);

    private static JsonObject BuildMechanicsSourceRecord(NativeCSharpDocument document, int type, int style, CancellationToken cancellation, bool capturedReceiverBound = true)
    {
        return BuildMechanicsSourceView(document, type, style, cancellation, capturedReceiverBound, null);
    }

    // Normalization of a declared lossy source view, never runtime lowering.
    // Reuse only closed regions admitted by the strict reader. Keep each outer
    // guard: its identity may match but reaching it is still unproved.
    private static JsonObject BuildMechanicsSourceView(NativeCSharpDocument document, int type, int style,
        CancellationToken cancellation, bool capturedReceiverBound, JsonObject? conditionalRecord)
    {
        cancellation.ThrowIfCancellationRequested();
        // Strict closed regions need only the method shell, not the potentially
        // enormous dispatcher body. Clone under nativeCSharpGate and restore the
        // source AST immediately; per-view pruning still owns its private tree.
        bool conditional = conditionalRecord?["coverage"]?.GetValue<string>() == "conditional_ast_regions";
        var tree = conditional ? CloneCSharpWithoutBody(document.Tree, document.Declaration)
            : (SyntaxTree)document.Tree.Clone();
        var gaps = new JsonArray();
        var retainedGuards = new HashSet<IfElseStatement>();
        string? refusal;
        if (conditional)
        {
            var offsets = conditionalRecord!["entryGuards"]!.AsArray().OfType<JsonObject>()
                .Select(guard => guard["ilOffset"]!.GetValue<int>()).ToHashSet();
            var ends = CSharpConditionalEnds(document.Method);
            var candidates = document.Tree.Descendants.OfType<IfElseStatement>()
                .Select(branch => ReadCSharpGuard(branch, ends)).OfType<CSharpGuard>()
                .Where(guard => offsets.Contains(guard.Offset)).ToArray();
            if (candidates.Length != offsets.Count || candidates.Length == 0)
                throw new NotSupportedException("mechanics_conditional_guards_not_mapped");
            var declaration = tree.Descendants.OfType<MethodDeclaration>().Single();
            declaration.Body = new BlockStatement();
            foreach (var candidate in candidates)
            {
                string? regionRefusal = CSharpRegionRefusal(candidate.Branch.TrueStatement, document.Method)
                    ?? MechanicsPruningRefusal(document, candidate.Branch.TrueStatement, type, style);
                if (regionRefusal is not null) throw new NotSupportedException(regionRefusal);
                var branch = CloneCSharpTrueArm(candidate.Branch);
                declaration.Body.Statements.Add(branch); retainedGuards.Add(branch);
            }
            refusal = capturedReceiverBound ? null : "captured_receiver_binding_unproved";
            gaps.Add("conditional_source_excerpts; original_guards_must_be_reached; enclosing_dispatch_and_runtime_hooks_unknown");
        }
        else refusal = capturedReceiverBound ? MechanicsPruningRefusal(document) : "captured_receiver_binding_unproved";
        int removed = 0, removedSections = 0, removedUnreachable = 0, removedEmpty = 0;
        var removedInvocations = new HashSet<InvocationExpression>();
        if (refusal is null)
        {
            // Postorder rewrites retained children before their parent. The
            // tree is private: move the selected arm instead of cloning it again.
            // Switch containers stay in place, so break targets do not change.
            foreach (var node in tree.Descendants.Reverse().ToArray())
            {
                cancellation.ThrowIfCancellationRequested();
                if (!node.Ancestors.Contains(tree)) continue;
                if (node is IfElseStatement branch)
                {
                    if (retainedGuards.Contains(branch)) continue;
                    bool? condition = MechanicsCondition(branch.Condition, type, style);
                    if (condition is null) continue;
                    var selected = condition.Value ? branch.TrueStatement : branch.FalseStatement;
                    var discarded = condition.Value ? branch.FalseStatement : branch.TrueStatement;
                    removedInvocations.UnionWith(discarded.DescendantsAndSelf.OfType<InvocationExpression>());
                    removedInvocations.UnionWith(branch.Condition.DescendantsAndSelf.OfType<InvocationExpression>());
                    ReplaceOwnedCSharpStatement(branch, selected); removed++;
                }
                else if (node is SwitchStatement switched)
                {
                    Expression expression = switched.Expression;
                    while (expression is ParenthesizedExpression parens) expression = parens.Expression;
                    if (!MechanicsIdentityField(expression, out string field)) continue;
                    int identity = field == "type" ? type : style;
                    // No patterns, arithmetic, enum conversions or guessed labels.
                    if (switched.SwitchSections.SelectMany(section => section.CaseLabels)
                        .Any(label => !label.Expression.IsNull && label.Expression is not PrimitiveExpression { Value: int })) continue;
                    var selected = switched.SwitchSections.FirstOrDefault(section => section.CaseLabels
                        .Any(label => label.Expression is PrimitiveExpression { Value: int value } && value == identity))
                        ?? switched.SwitchSections.FirstOrDefault(section => section.CaseLabels.Any(label => label.Expression.IsNull));
                    foreach (var section in switched.SwitchSections.ToArray())
                    {
                        if (section == selected) continue;
                        removedInvocations.UnionWith(section.Descendants.OfType<InvocationExpression>());
                        section.Remove(); removedSections++;
                    }
                    // Pure captured field read with no matching section has no effects.
                    if (selected is null) switched.ReplaceWith(new EmptyStatement());
                }
                else if (node is BlockStatement block)
                {
                    bool terminated = false;
                    foreach (var statement in block.Statements.ToArray())
                    {
                        if (terminated)
                        {
                            removedInvocations.UnionWith(statement.DescendantsAndSelf.OfType<InvocationExpression>());
                            statement.Remove(); removedUnreachable++;
                        }
                        else if (statement is EmptyStatement)
                        {
                            statement.Remove(); removedEmpty++;
                        }
                        else terminated = MechanicsTerminatesBlock(statement);
                    }
                }
            }
        }
        else gaps.Add(refusal);
        var callIndex = new NativeSourceCallIndex(document.Method);
        var removedCalls = MechanicsCallOffsets(removedInvocations, callIndex, gaps);
        var remainingCalls = MechanicsCallOffsets(tree.Descendants.OfType<InvocationExpression>(), callIndex, gaps, includeAmbiguous: true);
        removedCalls.ExceptWith(remainingCalls);
        var spawnTypes = refusal is null && conditionalRecord is null
            ? MechanicsSpawnTypeCandidates(tree, callIndex, gaps) : new JsonArray();
        var rendered = RenderCSharp(tree, includeLocations: false);
        if (rendered.Code.Length > NativeCSharpRecordLimit) throw new NotSupportedException("mechanics_source_character_bound; strict_source_retained");
        var record = MethodSourceIdentity(document.Method);
        record["coverage"] = retainedGuards.Count > 0 ? "approximate_identity_ast_regions" : removed + removedSections + removedUnreachable > 0 ? "approximate_identity_ast_method" : "unpruned_method";
        if (retainedGuards.Count > 0) record["entryGuards"] = conditionalRecord!["entryGuards"]!.DeepClone();
        record["approximation"] = MechanicsIdentityAssumption;
        record["receiverBinding"] = capturedReceiverBound ? "captured_actor_source_binding" : "unproved";
        record["removedConditionalCount"] = removed;
        record["removedSwitchSectionCount"] = removedSections;
        record["removedUnreachableStatementCount"] = removedUnreachable;
        record["removedEmptyStatementCount"] = removedEmpty;
        record["code"] = rendered.Code; record["codeSha256"] = SourceAnalysisBuffers.HashUtf8(rendered.Code, cancellation);
        record["assemblySha256"] = document.Module.Sha256;
        record["excludedCallOffsets"] = new JsonArray(removedCalls.Order().Select(offset => (JsonNode?)JsonValue.Create(offset)).ToArray());
        if (spawnTypes.Count > 0) record["spawnTypeCandidates"] = spawnTypes;
        record["unresolved"] = gaps;
        return record;
    }

    private static JsonObject? CaptureProjectileMechanicsSource(Projectile projectile)
    {
        if (projectile.ModProjectile is not null || projectile.type <= Terraria.ID.ProjectileID.None || projectile.type >= Terraria.ID.ProjectileID.Count) return null;
        int type = projectile.type, style = projectile.aiStyle;
        JsonObject Analyze() => ProjectileAttackSource(type, style).CloneMechanics()
            ?? new JsonObject { ["source"] = "native_mechanics_source", ["version"] = 1, ["identity"] = new JsonObject { ["type"] = type, ["aiStyle"] = style }, ["approximation"] = MechanicsIdentityAssumption, ["records"] = new JsonArray(), ["unresolved"] = new JsonArray("mechanics_source_unavailable") };
        return currentParentAnalysis is { } analysis ? analysis.Defer(Analyze) : Analyze();
    }
}
