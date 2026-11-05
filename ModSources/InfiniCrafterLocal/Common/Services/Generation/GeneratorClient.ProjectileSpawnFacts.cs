#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed record ProjectileSpawnSlices(List<JsonObject> Programs, JsonArray References, HashSet<MethodBase> Methods);

    private static bool IsProjectileSpawnSource(ParentSourceMethod.Value value)
        => value.Operand is MethodInfo method && method.DeclaringType == typeof(Projectile)
            && method.Name is "NewProjectile" or "NewProjectileDirect";

    private static ProjectileSpawnSlices CaptureProjectileSpawnSlices(ParentSourceMethod body, AttackIdentitySelection? identity,
        int siteLimit = 32, int expressionLimit = 24000, int perSiteExpressionLimit = 12000)
        => CaptureProjectileSourceSlices(body, identity, "motion", IsProjectileSpawnSource, "spawn", siteLimit, expressionLimit, perSiteExpressionLimit);

    private static ProjectileSpawnSlices CaptureProjectileAdditionalEffectSlices(ParentSourceMethod body, AttackIdentitySelection? identity,
        string role, int siteLimit = 32, int expressionLimit = 24000, int perSiteExpressionLimit = 12000)
    {
        var established = new AttackSourceObservation(body, role, selection: identity);
        bool Additional(ParentSourceMethod.Value value)
        {
            if (established.IsRoot(value)) return false;
            // Keep calls and writes as syntax. No callee effect is evaluated or
            // certified pure, and no actor field name chooses generated behavior.
            return value.Op == "stfld" && value.Operand is FieldInfo field
                    && (field.DeclaringType == typeof(Projectile) || field.DeclaringType == typeof(Entity))
                || value.Operand is MethodInfo call
                    && (call.IsSpecialName && call.Name.StartsWith("set_", StringComparison.Ordinal)
                        && (call.DeclaringType == typeof(Projectile) || call.DeclaringType == typeof(Entity))
                        || call.GetParameters().Any(p => p.ParameterType.IsArray || p.ParameterType.IsByRef));
        }
        return CaptureProjectileSourceSlices(body, identity, role, Additional, "effect", siteLimit, expressionLimit, perSiteExpressionLimit);
    }

    private static ProjectileSpawnSlices CaptureProjectileSourceSlices(ParentSourceMethod body, AttackIdentitySelection? identity,
        string role, Func<ParentSourceMethod.Value, bool> source, string label,
        int siteLimit, int expressionLimit, int perSiteExpressionLimit)
    {
        var programs = new List<JsonObject>(); var references = new JsonArray(); var methods = new HashSet<MethodBase>();
        int sites = 0, work = 0;
        foreach (var call in body.Statements.Where(source)
            .Where(v => identity is null || identity.Reachable.Contains(v.Block)).OrderBy(v => v.At))
        {
            currentParentAnalysis?.ThrowIfCancelled();
            try
            {
                if (++sites > siteLimit) throw new NotSupportedException(label + "_source_site_count_bound");
                // The existing source serializer follows only this sink's values
                // and control dependencies. Other roots get independent budgets;
                // no loop is executed, unrolled or sampled.
                var observation = new AttackSourceObservation(body, role, new[] { call }, identity) { ExpressionLimit = perSiteExpressionLimit };
                observation.AdditionalExpressionWork = () => {
                    currentParentAnalysis?.ThrowIfCancelled();
                    if (++work > expressionLimit) throw new NotSupportedException(label + "_source_expression_work_bound");
                };
                JsonObject program = observation.Finish();
                foreach (var reference in observation.LiteralProjectileSpawns(program)) references.Add(reference!.DeepClone());
                methods.UnionWith(observation.ReferencedMethods);
                if (identity is not null)
                {
                    program["identitySelection"] = identity.Receipt.DeepClone();
                    var envelope = MethodSourceIdentity(body.Method);
                    envelope["coverage"] = "unknown";
                    envelope["unresolved"] = "unspecialized_" + label + "_site_not_captured; bounded_captured_identity_source_slice_only";
                    envelope["identitySelected"] = program;
                    program = envelope;
                }
                if (!programs.Any(existing => TryMergeProjectileSourcePrograms(existing, program))) programs.Add(program);
            }
            catch (Exception error) when (error is not OutOfMemoryException && error is not OperationCanceledException)
            {
                string reason = error is NotSupportedException ? error.Message : error.GetType().Name;
                // Every refused source site stays visible. Empty predicates here
                // are not a claim of unconditional execution: closure is unknown.
                if (IsProjectileSpawnSource(call))
                {
                    var reference = MethodSourceIdentity(body.Method);
                    reference["at"] = call.At;
                    reference["requiredPredicates"] = new JsonArray();
                    reference["projectileTypes"] = new JsonArray();
                    reference["unresolved"] = "spawn_source_slice_unavailable:" + reason;
                    references.Add(reference);
                }
                var program = MethodSourceIdentity(body.Method);
                program["observations"] = new JsonArray(); program["dependencies"] = new JsonObject();
                program["predicates"] = new JsonArray(); program["symbols"] = new JsonObject();
                program["coverage"] = "unknown";
                program["unresolved"] = label + "_source_site@" + call.At + ":" + reason;
                programs.Add(program);
            }
        }
        return new(programs, references, methods);
    }

    private static bool TryMergeProjectileSourcePrograms(JsonObject destination, JsonObject addition)
    {
        // Exact source-table union only. Overloaded symbol aliases, different
        // identity proofs or conflicting rows remain separate programs rather
        // than selecting a preferred value or rewriting expressions.
        bool selected = destination["identitySelected"] is JsonObject;
        if (selected != (addition["identitySelected"] is JsonObject)) return false;
        if (selected)
        {
            // A selected graph can supplement an established all-identity
            // capture. Known outer graph tables stay in that original capture;
            // unfamiliar wrapper metadata must never disappear during union.
            foreach (string key in new[] { "method", "sourceModuleVersionId", "sourceMethodSha256" })
                if (!JsonNode.DeepEquals(destination[key], addition[key])) return false;
            var knownWrapper = new[] { "method", "sourceModuleVersionId", "sourceMethodSha256", "coverage", "unresolved", "identitySelected",
                "observations", "dependencies", "predicates", "symbols", "identitySelectionUnavailable" };
            foreach (string key in destination.Select(p => p.Key).Concat(addition.Select(p => p.Key)).Distinct().Except(knownWrapper))
                if (!JsonNode.DeepEquals(destination[key], addition[key])) return false;
        }
        var target = selected ? destination["identitySelected"]!.AsObject() : destination;
        var source = selected ? addition["identitySelected"]!.AsObject() : addition;
        foreach (string key in new[] { "method", "sourceModuleVersionId", "sourceMethodSha256", "coverage", "identitySelection" })
            if (!JsonNode.DeepEquals(target[key], source[key])) return false;
        foreach (string key in new[] { "dependencies", "symbols" })
        {
            if (target[key] is not JsonObject left || source[key] is not JsonObject right) return false;
            foreach (var field in right)
                if (left.TryGetPropertyValue(field.Key, out var value) && !JsonNode.DeepEquals(value, field.Value)) return false;
        }
        foreach (var (key, identityKey) in new[] { ("observations", "at"), ("predicates", "id") })
        {
            if (target[key] is not JsonArray left || source[key] is not JsonArray right) return false;
            foreach (var rows in new[] { left, right })
            {
                var identities = new HashSet<string>(StringComparer.Ordinal);
                foreach (var row in rows)
                    if (row is not JsonObject value || value["at"] is not JsonValue offset || !offset.TryGetValue<int>(out _)
                        || value[identityKey] is null || !identities.Add(value[identityKey]!.ToJsonString())) return false;
            }
            foreach (var row in right)
            {
                var match = left.FirstOrDefault(value => JsonNode.DeepEquals(value?[identityKey], row?[identityKey]));
                if (match is not null && !JsonNode.DeepEquals(match, row)) return false;
            }
        }
        foreach (string key in target.Select(p => p.Key).Concat(source.Select(p => p.Key)).Distinct()
            .Except(new[] { "method", "sourceModuleVersionId", "sourceMethodSha256", "coverage", "identitySelection", "dependencies", "symbols", "observations", "predicates", "unresolved" }))
            if (!JsonNode.DeepEquals(target[key], source[key])) return false;
        if ((target["unresolved"] is not null && target["unresolved"] is not JsonArray)
            || (source["unresolved"] is not null && source["unresolved"] is not JsonArray)) return false;
        foreach (string key in new[] { "dependencies", "symbols" })
            foreach (var field in source[key]!.AsObject())
                if (!target[key]!.AsObject().ContainsKey(field.Key)) target[key]![field.Key] = field.Value?.DeepClone();
        foreach (var (key, identityKey) in new[] { ("observations", "at"), ("predicates", "id") })
        {
            var rows = target[key]!.AsArray();
            foreach (var row in source[key]!.AsArray())
                if (!rows.Any(value => JsonNode.DeepEquals(value?[identityKey], row?[identityKey]))) rows.Add(row!.DeepClone());
            target[key] = new JsonArray(rows.OrderBy(row => row!["at"]!.GetValue<int>()).Select(row => row!.DeepClone()).ToArray());
        }
        if (source["unresolved"] is JsonArray extra)
        {
            var unresolved = target["unresolved"] as JsonArray ?? new JsonArray();
            foreach (var reason in extra)
                if (!unresolved.Any(value => JsonNode.DeepEquals(value, reason))) unresolved.Add(reason?.DeepClone());
            if (target["unresolved"] is null) target["unresolved"] = unresolved;
        }
        return true;
    }

    internal static JsonObject InspectProjectileSpawnSource(MethodInfo method, int type, int style,
        int siteLimit = 32, int expressionLimit = 24000, int perSiteExpressionLimit = 12000)
    {
        var body = new ParentSourceMethod(method);
        var identity = new AttackIdentitySelection(body, type, style);
        var selected = new ParentSourceMethod(method, selectedSuccessors: identity.Selected);
        var effects = CaptureProjectileSpawnSlices(selected, identity, siteLimit, expressionLimit, perSiteExpressionLimit);
        return new JsonObject { ["programs"] = new JsonArray(effects.Programs.Select(p => (JsonNode?)p).ToArray()),
            ["sourceCalls"] = effects.References };
    }
}
