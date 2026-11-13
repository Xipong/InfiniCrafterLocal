#nullable enable
using System;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp.Syntax;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Keep shared native defaults as source, not as fabricated segment profiles.
    // The captured root selects an excerpt, never the identity of a hook result.
    private static JsonObject? CaptureSharedProjectileDefaults(int type)
    {
        var roots = new JsonArray();
        // tML splits native defaults across these source owners. This names
        // methods, not items; hooks and wrapper execution remain unresolved.
        foreach (string name in new[] { "SetDefaults", "SetDefaults1", "SetDefaults2" })
        {
            var method = typeof(Projectile).GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                null, new[] { typeof(int) }, null);
            if (method is null) { roots.Add(new JsonObject { ["root"] = name, ["unresolved"] = "shared_defaults_method_unavailable" }); continue; }
            var source = CaptureSharedProjectileDefaultsMethod(method, type);
            if (source is not null) roots.Add(source);
        }
        return roots.Count == 0 ? null : new JsonObject {
            ["source"] = "conditional_shared_projectile_defaults", ["version"] = 1,
            ["relevanceType"] = type, ["roots"] = roots,
            ["scope"] = "Conditional source only, not segment profiles, executed defaults or hook-result identities. Shared source regions are selected by a finite type guard; wrappers, hooks, enclosing control and unmatched regions remain unresolved. Absence is not proved."
        };
    }

    private static JsonObject? CaptureSharedProjectileDefaultsMethod(MethodInfo method, int type)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(currentParentAnalysis?.Cancellation ?? CancellationToken.None);
        timeout.CancelAfter(TimeSpan.FromSeconds(20));
        try
        {
            while (!Monitor.TryEnter(nativeCSharpGate, 50)) timeout.Token.ThrowIfCancellationRequested();
            try
            {
                var input = new JsonObject { ["type"] = type, ["sharedDefaultsVersion"] = 1 };
                var certificate = MethodSourceIdentity(method);
                if (TryReadNativeSourceProjection("projectile_shared_defaults", method, input, timeout.Token, out var cached)
                    && cached.Count == 2 && cached.ContainsKey("result")
                    && (cached["result"] is null || cached["result"] is JsonObject)
                    && JsonNode.DeepEquals(cached["certificate"], certificate))
                    return cached["result"]?.DeepClone().AsObject();
                var document = GetNativeCSharpDocument(method, timeout.Token);
                var result = BuildSharedProjectileDefaults(document, type, timeout.Token);
                var projection = new JsonObject { ["certificate"] = certificate, ["result"] = result?.DeepClone() };
                RecordNativeSourceProjection("projectile_shared_defaults", method, input, projection, timeout.Token);
                return result;
            }
            finally { Monitor.Exit(nativeCSharpGate); }
        }
        catch (OperationCanceledException)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            return new JsonObject { ["unresolved"] = "shared_defaults_decompilation_time_bound" };
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        { return new JsonObject { ["unresolved"] = "shared_defaults_source:" + (error is NotSupportedException ? error.Message : error.GetType().Name) }; }
    }

    private static JsonObject? BuildSharedProjectileDefaults(NativeCSharpDocument document, int type,
        CancellationToken cancellation, int characterLimit = 24000)
    {
        cancellation.ThrowIfCancellationRequested();
        // Conservative finite relevance domains. Unknown conjuncts remain in
        // emitted source; unknown disjunctions cannot establish a finite domain.
        List<(long Low, long High)>? Domain(Expression expression)
        {
            cancellation.ThrowIfCancellationRequested();
            if (expression is ParenthesizedExpression parenthesized) return Domain(parenthesized.Expression);
            if (expression is not BinaryOperatorExpression binary) return null;
            if (binary.Operator is BinaryOperatorType.ConditionalAnd or BinaryOperatorType.ConditionalOr)
            {
                var left = Domain(binary.Left); var right = Domain(binary.Right);
                if (binary.Operator == BinaryOperatorType.ConditionalOr)
                {
                    if (left is null || right is null) return null;
                    var union = new List<(long Low, long High)>();
                    foreach (var range in left.Concat(right).OrderBy(range => range.Low))
                    {
                        cancellation.ThrowIfCancellationRequested();
                        if (union.Count > 0 && range.Low <= union[^1].High + 1)
                            union[^1] = (union[^1].Low, Math.Max(union[^1].High, range.High));
                        else union.Add(range);
                    }
                    return union;
                }
                if (left is null) return right;
                if (right is null) return left;
                // Domains are sorted disjoint intervals: linear intersection,
                // never a Cartesian expansion of repeated disjunctions.
                var intersection = new List<(long Low, long High)>();
                int i = 0, j = 0;
                while (i < left.Count && j < right.Count)
                {
                    cancellation.ThrowIfCancellationRequested();
                    long low = Math.Max(left[i].Low, right[j].Low), high = Math.Min(left[i].High, right[j].High);
                    if (low <= high) intersection.Add((low, high));
                    if (left[i].High < right[j].High) i++; else j++;
                }
                return intersection;
            }
            bool Field(Expression value) => MechanicsIdentityField(value, out string field) && field == "type";
            var op = binary.Operator; long literal;
            if (Field(binary.Left) && binary.Right is PrimitiveExpression { Value: int value }) literal = value;
            else if (Field(binary.Right) && binary.Left is PrimitiveExpression { Value: int reverse })
            {
                literal = reverse;
                op = op switch { BinaryOperatorType.GreaterThan => BinaryOperatorType.LessThan,
                    BinaryOperatorType.GreaterThanOrEqual => BinaryOperatorType.LessThanOrEqual,
                    BinaryOperatorType.LessThan => BinaryOperatorType.GreaterThan,
                    BinaryOperatorType.LessThanOrEqual => BinaryOperatorType.GreaterThanOrEqual, _ => op };
            }
            else return null;
            return op switch {
                BinaryOperatorType.Equality => new() { (literal, literal) },
                BinaryOperatorType.GreaterThan => new() { (literal + 1, int.MaxValue) },
                BinaryOperatorType.GreaterThanOrEqual => new() { (literal, int.MaxValue) },
                BinaryOperatorType.LessThan => new() { (int.MinValue, literal - 1) },
                BinaryOperatorType.LessThanOrEqual => new() { (int.MinValue, literal) },
                _ => null
            };
        }
        var branches = document.Declaration.Body.Descendants.OfType<IfElseStatement>().Where(branch => {
            cancellation.ThrowIfCancellationRequested();
            var domain = Domain(branch.Condition);
            return domain is not null && domain.Count > 0
                && domain.All(range => range.Low > int.MinValue && range.High < int.MaxValue)
                && domain.Any(range => type >= range.Low && type <= range.High)
                && (domain.Any(range => range.High > range.Low) || domain.Select(range => range.Low).Distinct().Count() > 1);
        }).ToArray();
        if (branches.Length == 0) return null;
        var records = new JsonArray(); var unknowns = new JsonArray(); int characters = 0;
        foreach (var branch in branches)
        {
            cancellation.ThrowIfCancellationRequested();
            if (branches.Any(outer => outer != branch && branch.Ancestors.Contains(outer.TrueStatement))) continue;
            string code = RenderCSharp(CloneCSharpTrueArm(branch), includeLocations: false).Code;
            if (records.Count >= 8 || characters + code.Length > characterLimit)
            { unknowns.Add("shared_defaults_region_bound; entire_region_omitted"); continue; }
            // Original compound guard and whole true body, including other type
            // arms, survive. Enclosing controls are not claimed to be resolved.
            var record = MethodSourceIdentity(document.Method);
            record["coverage"] = "conditional_shared_defaults_source";
            record["code"] = code;
            record["codeSha256"] = CSharpHash(Encoding.UTF8.GetBytes(code));
            records.Add(record); characters += code.Length;
        }
        return new JsonObject {
            ["source"] = "conditional_shared_projectile_defaults", ["version"] = 1,
            ["relevanceType"] = type,
            ["scope"] = "Shared native SetDefaults source selected by a finite type-guard relevance witness. Not executed defaults, not a segment profile or proof that a hook/spawn produces any listed type. Original guard and whole true body retained without identity specialization. Enclosing control, local bindings, other branches and hooks remain unresolved; absence is not proved.",
            ["records"] = records, ["unresolved"] = unknowns
        };
    }
}
