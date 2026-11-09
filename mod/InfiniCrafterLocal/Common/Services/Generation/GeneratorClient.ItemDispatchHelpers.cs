#nullable enable
using System;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;
using ICSharpCode.Decompiler.TypeSystem;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Source relevance only, not execution or receiver identity. Follow one
    // direct native call when its immutable int argument came from Item.type.
    // No names, item IDs, recursive graph walks, alias inference or value guesses.
    private static bool ItemDispatchImmutableVariable(AstNode body, ILVariable variable)
        => !body.Descendants.OfType<IdentifierExpression>().Where(node => node.GetILVariable() == variable).Any(use =>
            use.Ancestors.TakeWhile(node => node != body).Any(node => node is DirectionExpression or UndocumentedExpression
                or UnaryOperatorExpression { Operator: UnaryOperatorType.Increment or UnaryOperatorType.Decrement
                    or UnaryOperatorType.PostIncrement or UnaryOperatorType.PostDecrement or UnaryOperatorType.AddressOf }
                || node is AssignmentExpression assignment && assignment.Left.DescendantsAndSelf.Contains(use)));

    private static AstNode? ItemDispatchArgumentSource(NativeCSharpDocument document, Expression argument, InvocationExpression invocation)
    {
        if (ItemDispatchTypeField(argument)) return argument;
        if (argument is not IdentifierExpression identifier || identifier.GetILVariable() is not { } variable || variable.Kind == VariableKind.Parameter
            || !ItemDispatchImmutableVariable(document.Declaration.Body, variable)) return null;
        var declarations = document.Declaration.Body.Descendants.OfType<VariableInitializer>().Where(node => node.GetILVariable() == variable).ToArray();
        if (declarations.Length != 1 || !ItemDispatchTypeField(declarations[0].Initializer)
            || declarations[0].Parent is not VariableDeclarationStatement statement || statement.Parent is not BlockStatement block) return null;
        // Lexical dominance, including a fresh local on each loop iteration.
        var callStatement = invocation.Ancestors.OfType<Statement>().FirstOrDefault(node => node.Parent == block);
        var statements = block.Statements.ToArray();
        if (callStatement is null || Array.IndexOf(statements, statement) >= Array.IndexOf(statements, callStatement)
            || document.Declaration.Body.Descendants.Any(node => node is GotoStatement or LabelStatement
                or LambdaExpression or AnonymousMethodExpression or LocalFunctionDeclarationStatement)) return null;
        return statement;
    }

    private static JsonArray ItemDispatchCallerConditions(InvocationExpression invocation)
    {
        var conditions = new JsonArray();
        foreach (var branch in invocation.Ancestors.OfType<IfElseStatement>().Reverse())
            conditions.Add(new JsonObject { ["condition"] = RenderCSharp(branch.Condition, includeLocations: false).Code.Trim(),
                ["requiredArm"] = invocation.Ancestors.Contains(branch.TrueStatement) ? "true" : "false" });
        return conditions;
    }

    private static void BuildNativeItemDispatchHelpers(NativeCSharpDocument document, int itemType, JsonObject root, CancellationToken cancellation,
        int callLimit = 8, int regionLimit = 16, int regionCharacters = 24000, int totalCharacters = 64000)
    {
        var records = root["records"]!.AsArray(); var gaps = root["unknowns"]!.AsArray();
        var instructions = AttackCode(document.Method);
        var callIndex = new NativeSourceCallIndex(document.Method);
        var helpers = new Dictionary<MethodInfo, NativeCSharpDocument>();
        int inspected = 0, characters = records.Sum(record => record!["code"]!.GetValue<string>().Length);
        void ClearEmptyRegionGap()
        {
            if (records.Count == 0) return;
            for (int i = gaps.Count - 1; i >= 0; i--)
                if (gaps[i]?.GetValue<string>() == "no_admitted_Item_type_equality_region; absence_not_proved") gaps.RemoveAt(i);
        }
        foreach (var invocation in document.Declaration.Body.Descendants.OfType<InvocationExpression>())
        {
            cancellation.ThrowIfCancellationRequested();
            if (invocation.Parent is not ExpressionStatement || invocation.GetSymbol() is not IMethod symbol || symbol.IsVirtual || symbol.DeclaringType.FullName != document.Method.DeclaringType?.FullName
                || invocation.Arguments.Count != symbol.Parameters.Count || invocation.Arguments.Any(argument => argument is NamedArgumentExpression)
                || invocation.Ancestors.Any(node => node is LambdaExpression or AnonymousMethodExpression or LocalFunctionDeclarationStatement
                    or SwitchStatement or ForeachStatement or WhileStatement or DoWhileStatement or TryCatchStatement or UsingStatement or LockStatement)) continue;
            var arguments = invocation.Arguments.ToArray();
            for (int parameter = 0; parameter < arguments.Length; parameter++)
            {
                var source = ItemDispatchArgumentSource(document, arguments[parameter], invocation);
                if (source is null) continue;
                var offsets = callIndex.Match(invocation, symbol);
                if (offsets.Count != 1) continue;
                var offset = offsets.Single();
                if (instructions.Single(instruction => instruction.Offset == offset).Arg is not MethodInfo target
                    || target.Module != document.Method.Module || target.DeclaringType != document.Method.DeclaringType
                    || target.IsVirtual || target.IsGenericMethod || target.GetMethodBody() is null
                    || target.GetParameters().Length != arguments.Length || target.GetParameters()[parameter].ParameterType != typeof(int)) continue;
                if (++inspected > callLimit) { gaps.Add("dispatcher_helper_call_bound"); ClearEmptyRegionGap(); return; }
                // Reuse this root's verified immutable module snapshot. Direct
                // document construction verifies the helper's exact method body
                // and avoids borrowing a cached document from another owner.
                if (!helpers.TryGetValue(target, out var helper))
                    helpers.Add(target, helper = new NativeCSharpDocument(target, document.Module, cancellation));
                // The admitted helper shape has only lexical blocks/if guards.
                // Other control needs a separate source-context proof.
                if (helper.Declaration.Body.Descendants.Any(node => node is ForStatement or ForeachStatement or WhileStatement or DoWhileStatement
                    or SwitchStatement or TryCatchStatement or UsingStatement or LockStatement or GotoStatement or LabelStatement
                    or LambdaExpression or AnonymousMethodExpression or LocalFunctionDeclarationStatement)) continue;
                var variables = helper.Declaration.Body.Descendants.OfType<IdentifierExpression>().Select(node => node.GetILVariable())
                    .Where(variable => variable is not null && variable.Kind == VariableKind.Parameter && variable.Index == parameter).Distinct().ToArray();
                if (variables.Length != 1 || !ItemDispatchImmutableVariable(helper.Declaration.Body, variables[0]!)) continue;
                var candidates = new JsonObject { ["records"] = new JsonArray(), ["unknowns"] = new JsonArray() };
                BuildNativeItemDispatchRegionsCore(helper, itemType, candidates, cancellation, regionLimit, regionCharacters, totalCharacters,
                    value => value is IdentifierExpression identifier && identifier.GetILVariable() == variables[0]);
                foreach (var gap in candidates["unknowns"]!.AsArray())
                    if (gap!.GetValue<string>() != "no_admitted_Item_type_equality_region; absence_not_proved") gaps.Add("helper:" + gap.GetValue<string>());
                if (candidates["records"]!.AsArray().Count == 0) continue;
                var binding = MethodSourceIdentity(document.Method);
                binding["sourceCallIlOffset"] = offset; binding["parameterIndex"] = parameter;
                binding["call"] = RenderCSharp(invocation, includeLocations: false).Code.Trim();
                binding["identitySource"] = RenderCSharp(source, includeLocations: false).Code.Trim();
                binding["enclosingConditions"] = ItemDispatchCallerConditions(invocation);
                var loops = new JsonArray();
                foreach (var loop in invocation.Ancestors.OfType<ForStatement>().Reverse())
                {
                    var header = (ForStatement)loop.Clone(); header.EmbeddedStatement = new EmptyStatement();
                    loops.Add(RenderCSharp(header, includeLocations: false).Code.Trim());
                }
                binding["enclosingForLoops"] = loops;
                binding["scope"] = "immutable_int_argument_from_Item_type; source_relevance_only; receiver_and_execution_not_proved";
                int bindingCharacters = binding.ToJsonString().Length;
                if (bindingCharacters > regionCharacters) { gaps.Add("dispatcher_helper_binding_character_bound"); continue; }
                foreach (var candidate in candidates["records"]!.AsArray())
                {
                    cancellation.ThrowIfCancellationRequested();
                    var existing = records.OfType<JsonObject>().FirstOrDefault(record => record["id"]!.GetValue<string>() == candidate!["id"]!.GetValue<string>());
                    int codeCharacters = existing is null ? candidate!["code"]!.GetValue<string>().Length : 0;
                    if (existing is null && records.Count >= regionLimit || characters + codeCharacters + bindingCharacters > totalCharacters)
                    { gaps.Add("dispatcher_helper_region_or_character_bound; entire_binding_omitted"); continue; }
                    if (existing is null) { existing = candidate!.DeepClone().AsObject(); records.Add(existing); }
                    var bindings = existing["callerBindings"] as JsonArray;
                    if (bindings is null) { bindings = new JsonArray(); existing["callerBindings"] = bindings; }
                    if (!bindings.Any(value => JsonNode.DeepEquals(value, binding)))
                    { bindings.Add(binding.DeepClone()); characters += codeCharacters + bindingCharacters; }
                }
            }
        }
        ClearEmptyRegionGap();
    }
}
