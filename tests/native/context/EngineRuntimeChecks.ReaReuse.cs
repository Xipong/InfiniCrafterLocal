using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void ReaGuardFixture(Projectile projectile)
    {
        float value = projectile.ai[0];
        if (projectile.active)
        {
            if (value > 2) { value = MathF.Sin(value); projectile.rotation = value; projectile.scale = value * 2; }
            else value = projectile.ai[1];
            projectile.velocity.X += value;
            if (projectile.wet) { projectile.rotation += value; projectile.scale += value; }
        }
        projectile.position.Y += value;
    }
    private static object ReaMember(object owner, string name) => CSharpFixtureMember(owner, name);
    private static IEnumerable<object> ReaObjects(object value) => ((IEnumerable)value).Cast<object>();
    private static object ReaCall(object owner, string method, params object?[] args)
        => owner.GetType().GetMethod(method, CSharpFlags)!.Invoke(owner, args)!;
    private static object ReaObserver(object body, int limit)
    {
        var observer = PackSafetyCreate("AttackSourceObservation", body, "motion", null, null);
        observer.GetType().GetField("ExpressionLimit", CSharpFlags)!.SetValue(observer, limit);
        return observer;
    }
    // Independent copy of the previous lazy scan, not the memo implementation.
    private static JsonArray ReaScanningRequired(object observer, object value)
    {
        var body = ReaMember(observer, "body");
        int block = (int)ReaMember(value, "Block");
        var conditions = new JsonArray();
        foreach (var branch in ReaObjects(ReaMember(observer, "branches")))
        {
            int branchBlock = (int)ReaMember(branch, "Block");
            if (branchBlock == block || !(bool)ReaCall(ReaCall(body, "ControlledRegion", branchBlock), "Contains", block)) continue;
            int at = (int)ReaMember(branch, "At");
            string name = "b" + at;
            conditions.Add(name);
            if (!((HashSet<string>)ReaMember(observer, "predicateIds")).Add(name)) continue;
            var inputs = new JsonArray();
            foreach (string id in ReaObjects(ReaMember(branch, "Inputs"))) inputs.Add((string)ReaCall(observer, "Expression", id));
            var blocks = (IDictionary)ReaMember(body, "Blocks");
            var successors = new JsonArray();
            foreach (int next in ReaObjects(ReaMember(blocks[branchBlock]!, "Next"))) successors.Add(next);
            ((JsonArray)ReaMember(observer, "predicates")).Add(new JsonObject {
                ["id"] = name, ["at"] = at, ["op"] = (string)ReaMember(branch, "Op"),
                ["inputs"] = inputs, ["successors"] = successors });
        }
        return conditions;
    }
    private static string ReaOutcome(Func<JsonArray> action)
    {
        try { return action().ToJsonString(); }
        catch (Exception error)
        {
            while (error is TargetInvocationException { InnerException: not null }) error = error.InnerException;
            return error.GetType().Name + ":" + error.Message;
        }
    }
    private static void ReaGuardMemoMatchesScanningOracle()
    {
        var method = typeof(EngineRuntimeChecks).GetMethod(nameof(ReaGuardFixture), CSharpFlags)!;
        foreach (int limit in new[] { 0, 1, 8, 24, 12000 })
        {
            var body = PackSafetyCreate("ParentSourceMethod", method, null, null, null);
            var memo = ReaObserver(body, limit); var scan = ReaObserver(body, limit);
            var values = ReaObjects(ReaMember(body, "Statements")).ToArray();
            // Revisit blocks out of order, exercising completed hits, nested
            // expression registration and an interrupted first traversal.
            foreach (var value in values.Concat(values.Reverse()).Concat(values))
            {
                string actual = ReaOutcome(() => (JsonArray)ReaCall(memo, "Required", value));
                string expected = ReaOutcome(() => ReaScanningRequired(scan, value));
                Equal(expected, actual, "REA guard conditions/refusal match scan at limit " + limit);
                foreach (string field in new[] { "predicates", "dependencies", "symbols" })
                    Equal(((JsonNode)ReaMember(scan, field)).ToJsonString(), ((JsonNode)ReaMember(memo, field)).ToJsonString(), "REA exact field/order: " + field);
                Equal((int)ReaMember(scan, "expressionCount"), (int)ReaMember(memo, "expressionCount"), "REA expression budget unchanged");
                Equal(string.Join("|", ReaObjects(ReaMember(scan, "ReferencedMethods"))), string.Join("|", ReaObjects(ReaMember(memo, "ReferencedMethods"))), "REA reference order unchanged");
                if (actual.StartsWith("NotSupportedException:", StringComparison.Ordinal)) break;
            }
        }
        var completeBody = PackSafetyCreate("ParentSourceMethod", method, null, null, null);
        var complete = ReaObserver(completeBody, 12000);
        foreach (var value in ReaObjects(ReaMember(completeBody, "Statements")))
        {
            var first = (JsonArray)ReaCall(complete, "Required", value);
            string expected = first.ToJsonString(); first.Add("caller-mutation");
            Equal(expected, ((JsonArray)ReaCall(complete, "Required", value)).ToJsonString(), "REA guards return independent mutable arrays");
        }
    }
    private static bool ReaEntityOracle(MethodBase method)
    {
        if (method.DeclaringType != typeof(Entity) || method.IsVirtual || method.GetMethodBody() is null) return false;
        var code = (IEnumerable)CSharpOwner.GetMethod("AttackCode", CSharpFlags)!.Invoke(null, new object[] { method })!;
        foreach (var instruction in code)
        {
            string op = (string)ReaMember(instruction, "Op");
            object? arg = instruction.GetType().GetProperty("Arg", CSharpFlags)?.GetValue(instruction)
                ?? instruction.GetType().GetField("Arg", CSharpFlags)?.GetValue(instruction);
            if (op is "castclass" or "isinst" or "stsfld") return false;
            if (arg is FieldInfo field && (field.DeclaringType == typeof(Projectile) || !field.FieldType.IsValueType)) return false;
            if (arg is MethodBase call && (call.IsVirtual || call.GetParameters().Any(p => !p.ParameterType.IsValueType)
                || !call.IsStatic && call.DeclaringType?.IsValueType != true)) return false;
        }
        return true;
    }
    private static void ReaEntityMemoTracksDecodedBody()
    {
        var owner = CSharpOwner.GetNestedType("AttackIdentitySelection", CSharpFlags)!;
        var check = owner.GetMethod("BaseEntityValueAccessor", CSharpFlags)!;
        var methods = typeof(Entity).GetMethods(CSharpFlags).Cast<MethodBase>().Concat(new[] {
            typeof(Projectile).GetMethod("Kill", CSharpFlags, null, Type.EmptyTypes, null)!,
            typeof(EngineRuntimeChecks).GetMethod(nameof(ReaGuardFixture), CSharpFlags)! }).ToArray();
        int admitted = 0, rejected = 0;
        foreach (var method in methods)
        {
            bool expected = ReaEntityOracle(method);
            if (expected) admitted++; else rejected++;
            for (int n = 0; n < 3; n++) Equal(expected, (bool)check.Invoke(null, new object[] { method })!, "REA accessor all checks preserved: " + method.Name);
        }
        Equal(true, admitted > 0 && rejected > 0, "REA accessor exercises admission and rejection");
        var center = typeof(Entity).GetProperty("Center")!.GetMethod!;
        var attackCode = CSharpOwner.GetMethod("AttackCode", CSharpFlags)!;
        object before = attackCode.Invoke(null, new object[] { center })!;
        CSharpOwner.GetMethod("ClearProjectileAttackCaches", CSharpFlags)!.Invoke(null, null);
        object after = attackCode.Invoke(null, new object[] { center })!;
        Equal(false, ReferenceEquals(before, after), "REA cache reset obtains a new IL owner");
        Equal(ReaEntityOracle(center), (bool)check.Invoke(null, new object[] { center })!, "REA proof recomputes after reset");
    }
    private static void ReaAttachmentGroupingMatchesScanning()
    {
        var method = PackSafetyMethod();
        var identity = PackSafetyCertificate(method);
        var rows = new List<JsonObject>();
        for (int n = 0; n < 9; n++) { var row = (JsonObject)identity.DeepClone(); row["at"] = n; rows.Add(row); }
        rows[1]["method"] = "wrong"; rows[2]["sourceModuleVersionId"] = Guid.Empty.ToString(); rows[3]["sourceMethodSha256"] = "wrong";
        rows[4]["method"] = 7; rows[5].Remove("sourceMethodSha256");
        rows[6]["requiredPredicates"] = new JsonArray("b9", "b2", "b9", "b-1", "garbage");
        var calls = new JsonArray(rows.Select(row => (JsonNode?)row.DeepClone()).ToArray());
        calls.Add(null); calls.Add("nonobject");
        var type = CSharpOwner.GetNestedType("CSharpProgram", CSharpFlags)!;
        var programs = Array.CreateInstance(type, rows.Count);
        for (int n = 0; n < rows.Count; n++) programs.SetValue(Activator.CreateInstance(type, CSharpFlags, null, new object[] { rows[n], new object[] { "test", n } }, null), n);
        var grouped = PackSafetyCreate("CSharpAttachmentRows", programs, calls);
        object?[] findArgs = { method, null };
        var actual = (Array)grouped.GetType().GetMethod("Find", CSharpFlags)!.Invoke(grouped, findArgs)!;
        var match = CSharpOwner.GetMethod("CSharpProgramMatches", CSharpFlags)!;
        var expected = programs.Cast<object>().Where(program => (bool)match.Invoke(null, new[] { ReaMember(program, "Row"), method })!).ToArray();
        Equal(expected.Length, actual.Length, "REA exact identity grouping count");
        for (int n = 0; n < actual.Length; n++) Equal(true, ReferenceEquals(expected[n], actual.GetValue(n)), "REA original row order and references preserved");
        var oldLinks = (HashSet<int>)CSharpOwner.GetMethod("CSharpLinkOffsets", CSharpFlags)!.Invoke(null, new object[] { method, calls })!;
        var newLinks = (HashSet<int>)ReaCall(grouped, "Links", findArgs[1]);
        Equal(string.Join(",", oldLinks.Order()), string.Join(",", newLinks.Order()), "REA grouped calls preserve offsets/predicates");
        var oldInput = PackSafetyInput(method, actual, calls);
        var newInput = (JsonObject)CSharpOwner.GetMethod("CSharpProjectionInputForLinks", CSharpFlags)!.Invoke(null, new object[] { actual, newLinks, 91, 1, true })!;
        Equal(oldInput.ToJsonString(), newInput.ToJsonString(), "REA projection input remains exact bytes");
    }
}
