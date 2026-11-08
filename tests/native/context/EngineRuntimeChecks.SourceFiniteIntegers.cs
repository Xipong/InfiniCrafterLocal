using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static int FiniteSourceExecutions;
    private static Projectile? FiniteForeignActor = null;

    private static void FiniteSourceSpawn(Projectile p)
    {
        FiniteSourceExecutions++;
        if (p.type != 1009) return;
        int candidate = p.type;
        if (p.active)
        {
            int copy = candidate;
            candidate = copy + 1;
        }
        if (p.friendly) Projectile.NewProjectile(null, p.position, p.velocity, candidate, 17, 0f);
    }
    private static void FiniteSourceManyLiterals(Projectile p)
    {
        FiniteSourceExecutions++;
        Projectile.NewProjectile(null, p.position, p.velocity,
            p.ai[0] < 0 ? 7103 : p.ai[0] < 1 ? 7207 : p.ai[0] < 2 ? 7309 : p.ai[0] < 3 ? 7411 :
            p.ai[0] < 4 ? 7517 : p.ai[0] < 5 ? 7619 : p.ai[0] < 6 ? 7723 : p.ai[0] < 7 ? 7829 :
            p.ai[0] < 8 ? 7933 : 8039, 17, 0f);
    }

    private static int[] FiniteSourceLiteralOracle(MethodInfo method)
    {
        const BindingFlags any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
        var sourceType = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        var body = Activator.CreateInstance(sourceType, any, null, new object?[] { method, null, null, null }, null)!;
        var statements = ((System.Collections.IEnumerable)sourceType.GetField("Statements", any)!.GetValue(body)!).Cast<object>();
        object Operand(object value) => value.GetType().GetField("Operand", any)!.GetValue(value)!;
        var call = statements.Single(value => Operand(value) is MethodInfo called && called.DeclaringType == typeof(Projectile) && called.Name == "NewProjectile");
        var callee = (MethodInfo)Operand(call);
        int slot = Array.FindIndex(callee.GetParameters(), parameter => parameter.Name == "Type") + (callee.IsStatic ? 0 : 1);
        var inputs = (System.Collections.Generic.List<string>)call.GetType().GetField("Inputs", any)!.GetValue(call)!;
        var definitions = ((System.Collections.IEnumerable)sourceType.GetMethod("Definitions", any)!.Invoke(body, new object[] { inputs[slot] })!).Cast<object>();
        return definitions.Where(value => (string)value.GetType().GetField("Op", any)!.GetValue(value)! == "const" && Operand(value) is int)
            .Select(value => (int)Operand(value)).Distinct().ToArray();
    }

    private static int FiniteSourceCopies(Projectile p)
    {
        FiniteSourceExecutions++;
        int first = p.type;
        int copy = first;
        return p.active ? copy + 4 : copy - 2;
    }
    private static int FiniteSourceUnknownSibling(Projectile p)
        => p.active ? p.type + 11 : (int)p.ai[0];
    private static int FiniteSourceProducts(Projectile p)
    {
        int left = p.active ? 100 : 200;
        int right = p.friendly ? 3 : 9;
        return left + right;
    }
    private static int FiniteSourceForeign(Projectile p) => FiniteForeignActor!.type + 1;
    private static int FiniteSourceMutated(Projectile p) { p.type = 2099; return p.type + 1; }
    private static void FiniteSourceMutateActor(Projectile p) { FiniteSourceExecutions++; p.type = 2111; }
    private static int FiniteSourceMutatingHelper(Projectile p) { FiniteSourceMutateActor(p); return p.type + 1; }
    private static int FiniteSourceReceiverCopy(Projectile p) { Projectile copy = p; return copy.type + 1; }
    private static void FiniteSourceChange(ref int value) { FiniteSourceExecutions++; value = 3079; }
    private static int FiniteSourceIdentityAddress(Projectile p) { FiniteSourceChange(ref p.type); return p.type + 1; }
    private static int FiniteSourceLocalAddress(Projectile p)
    {
        int copy = p.type;
        FiniteSourceChange(ref copy);
        return copy + 1;
    }
    private static int FiniteSourceActorWritten(Projectile p)
    {
        p = FiniteForeignActor!;
        return p.type + 1;
    }
    private static int FiniteSourceBeforeMutation(Projectile p)
    {
        int copy = p.type;
        p.type = 4127;
        return copy + 1;
    }
    private static int FiniteSourceBackedge(Projectile p)
    {
        int copy = 0;
        while (p.active)
        {
            copy = p.type;
            p.type = 5087;
        }
        return copy;
    }
    private static int FiniteSourceCycle(Projectile p)
    {
        int copy = 6131;
        while (p.active) copy += 1;
        return copy;
    }
    private static int FiniteSourceWrapAdd(Projectile p) => unchecked(p.type + 1);
    private static int FiniteSourceWrapSubtract(Projectile p) => unchecked(p.type - 1);
    private static int FiniteSourceCheckedAdd(Projectile p) => checked(p.type + 1);
    private static int FiniteSourceCheckedSubtract(Projectile p) => checked(p.type - 1);
    private static int FiniteSourceOpaqueCall(Projectile p) => FiniteSourceRuntime(p.type);
    private static int FiniteSourceRuntime(int value) { FiniteSourceExecutions++; return value + 1; }
    private static int FiniteSourceDifferentWidth(Projectile p) => (int)((long)p.type + 1L);
    private static int FiniteSourceStyle(Projectile p) => p.aiStyle + 1;

    private static JsonArray FiniteSource(string method, int type = 1009, int style = 307,
        int workLimit = 256, int depthLimit = 64, int valueLimit = 8)
        => GeneratorClient.InspectFiniteIntegerSource(typeof(EngineRuntimeChecks).GetMethod(method,
            BindingFlags.Static | BindingFlags.NonPublic)!, type, style, workLimit, depthLimit, valueLimit);
    private static int[] FiniteValues(JsonArray rows)
        => rows.SelectMany(row => row!["values"]!.AsArray()).Select(value => value!.GetValue<int>()).Distinct().Order().ToArray();
    private static string FiniteUnknown(JsonArray rows)
        => string.Join("; ", rows.SelectMany(row => row!["unknown"]!.AsArray()).Select(value => value!.GetValue<string>()));
    private static void SourceFiniteIntegersPreserveAlternativesAndUnknowns()
    {
        FiniteSourceExecutions = 0;
        var spawn = GeneratorClient.InspectProjectileSpawnSource(typeof(EngineRuntimeChecks).GetMethod(nameof(FiniteSourceSpawn),
            BindingFlags.Static | BindingFlags.NonPublic)!, 1009, 307);
        var call = spawn["sourceCalls"]!.AsArray().Single()!.AsObject();
        Equal("1009,1010", string.Join(",", call["projectileTypes"]!.AsArray().Select(value => value!.GetValue<int>())),
            "captured identity copy and add provide both conditional type alternatives");
        Equal(false, call.ContainsKey("unresolved"), "fully bounded integer source has no type unknown");
        Equal(true, call["requiredPredicates"]!.AsArray().Count > 0, "source call still requires its unknown runtime guard");
        Equal(true, spawn.ToJsonString().Contains("Entity.active", StringComparison.Ordinal), "runtime choice remains in source closure");
        var literalMethod = typeof(EngineRuntimeChecks).GetMethod(nameof(FiniteSourceManyLiterals), BindingFlags.Static | BindingFlags.NonPublic)!;
        var literalOracle = FiniteSourceLiteralOracle(literalMethod);
        Equal(10, literalOracle.Length, "nested stack-join fixture exceeds the arithmetic set budget in the old literal extractor");
        var manyLiterals = GeneratorClient.InspectProjectileSpawnSource(literalMethod, 1009, 307);
        Equal(string.Join(",", literalOracle), string.Join(",", manyLiterals["sourceCalls"]![0]!["projectileTypes"]!.AsArray().Select(value => value!.GetValue<int>())),
            "bounded arithmetic must preserve every previously captured literal candidate and call link");
        Equal(false, manyLiterals["sourceCalls"]![0]!.AsObject().ContainsKey("unresolved"),
            "complete legacy literal evidence does not acquire an arithmetic cardinality refusal");
        var boundedProfiles = GeneratorClient.BuildReferencedProjectileSnapshots(manyLiterals["sourceCalls"]!.DeepClone().AsArray(),
            (id, allowed) => (true, allowed ? new JsonObject { ["type"] = id } : null, null))!["references"]!.AsArray();
        Equal(string.Join(",", literalOracle.Take(8)), string.Join(",", boundedProfiles.Where(row => row!["profile"] is JsonObject)
            .Select(row => row!["type"]!.GetValue<int>())), "original literal insertion order preserves first-eight profile priority");
        Equal(2, boundedProfiles.Count(row => row!["unresolved"]?.GetValue<string>() == "projectile_reference_profile_count_bound"),
            "overflow literals retain their exact existing profile-bound receipts");
        Equal(true, boundedProfiles.All(row => row!["sourceCallIndices"]!.AsArray().Single()!.GetValue<int>() == 0),
            "every retained and bounded literal keeps its original source-call link");
        var copy = FiniteSource(nameof(FiniteSourceCopies));
        Equal("1007,1013", string.Join(",", FiniteValues(copy)), "copies and stack/local joins retain arithmetic alternatives");
        Equal("", FiniteUnknown(copy), "supported arithmetic union is complete");
        Equal("103,109,203,209", string.Join(",", FiniteValues(FiniteSource(nameof(FiniteSourceProducts)))),
            "independent source alternatives form a conservative cross product without executing guards");
        Equal("308", string.Join(",", FiniteValues(FiniteSource(nameof(FiniteSourceStyle)))), "style shares actual receiver proof without ID rules");
        var partial = FiniteSource(nameof(FiniteSourceUnknownSibling));
        Equal("1020", string.Join(",", FiniteValues(partial)), "known sibling survives unsupported runtime expression");
        Equal(true, FiniteUnknown(partial).Contains("runtime_or_unsupported", StringComparison.Ordinal), "partial union cannot masquerade as complete");
        foreach (string method in new[] { nameof(FiniteSourceForeign), nameof(FiniteSourceMutated), nameof(FiniteSourceMutatingHelper), nameof(FiniteSourceIdentityAddress),
            nameof(FiniteSourceLocalAddress), nameof(FiniteSourceActorWritten), nameof(FiniteSourceOpaqueCall), nameof(FiniteSourceDifferentWidth) })
        {
            var unknown = FiniteSource(method);
            Equal(0, FiniteValues(unknown).Length, "unsafe or unsupported value is not guessed: " + method);
            Equal(true, FiniteUnknown(unknown).Length > 0, "unsafe boundary remains explicit: " + method);
        }
        Equal("1010", string.Join(",", FiniteValues(FiniteSource(nameof(FiniteSourceReceiverCopy)))), "receiver copies reuse the certified actor binding");
        Equal("1010", string.Join(",", FiniteValues(FiniteSource(nameof(FiniteSourceBeforeMutation)))),
            "per-read proof keeps a copy captured before a later non-looping mutation");
        var backedge = FiniteSource(nameof(FiniteSourceBackedge));
        Equal(false, FiniteValues(backedge).Contains(1009), "later mutation on a backedge blocks earlier actor read");
        Equal(true, FiniteUnknown(backedge).Length > 0, "backedge uncertainty remains explicit");
        var cycle = FiniteSource(nameof(FiniteSourceCycle));
        Equal(true, FiniteValues(cycle).Contains(6131), "acyclic initial sibling survives a recursive reaching definition");
        Equal(true, FiniteUnknown(cycle).Contains("finite_integer_cycle", StringComparison.Ordinal), "cycle is never silently dropped");
        Equal(copy.ToJsonString(), FiniteSource(nameof(FiniteSourceCopies)).ToJsonString(), "source alternatives are deterministic");
        Equal(0, FiniteSourceExecutions, "analysis never executes fixture, helper or spawn");
    }

    private static void SourceFiniteIntegersBoundWorkAndOverflow()
    {
        FiniteSourceExecutions = 0;
        Equal(int.MinValue, FiniteValues(FiniteSource(nameof(FiniteSourceWrapAdd), type: int.MaxValue)).Single(), "IL add wraps int32 explicitly");
        Equal(int.MaxValue, FiniteValues(FiniteSource(nameof(FiniteSourceWrapSubtract), type: int.MinValue)).Single(), "IL subtract wraps int32 explicitly");
        foreach (var pair in new[] { (nameof(FiniteSourceCheckedAdd), int.MaxValue), (nameof(FiniteSourceCheckedSubtract), int.MinValue) })
        {
            var overflow = FiniteSource(pair.Item1, type: pair.Item2);
            Equal(0, FiniteValues(overflow).Length, "checked overflow never becomes a wrapped candidate");
            Equal(true, FiniteUnknown(overflow).Contains("finite_integer_checked_overflow", StringComparison.Ordinal), "checked overflow path stays unresolved");
        }
        Equal(1010, FiniteValues(FiniteSource(nameof(FiniteSourceCheckedAdd))).Single(), "non-overflowing checked int32 addition stays supported");
        foreach (var pair in new[] {
            (Rows: FiniteSource(nameof(FiniteSourceCopies), workLimit: 0), Reason: "finite_integer_work_bound"),
            (Rows: FiniteSource(nameof(FiniteSourceCopies), depthLimit: 1), Reason: "finite_integer_depth_bound"),
            (Rows: FiniteSource(nameof(FiniteSourceProducts), valueLimit: 2), Reason: "finite_integer_value_count_bound") })
            Equal(true, FiniteUnknown(pair.Rows).Contains(pair.Reason, StringComparison.Ordinal), "each bounded refusal is explicit: " + pair.Reason);
        Equal("103,109", string.Join(",", FiniteValues(FiniteSource(nameof(FiniteSourceProducts), valueLimit: 2))),
            "cardinality truncation retains a deterministic partial set with unknown");
        Equal(0, FiniteSourceExecutions, "overflow and budget checks do not execute inspected methods");
    }

    private static void ProjectileFiniteSpawnVilethornReference()
    {
        var raw = JsonSerializer.SerializeToNode(GeneratorClient.ProjectileRawSnapshot(7, 0f, "finite_source_native_test", null, -1))!.AsObject();
        var calls = raw["referencedProjectiles"]!["sourceCalls"]!.AsArray();
        var call = calls.OfType<JsonObject>().Single(row => row["method"]!.GetValue<string>() == "Terraria.Projectile.VanillaAI"
            && row["projectileTypes"]!.AsArray().Any(value => value!.GetValue<int>() == 8));
        Equal("7,8", string.Join(",", call["projectileTypes"]!.AsArray().Select(value => value!.GetValue<int>())),
            "real native identity/copy/increment source yields conditional Vilethorn alternatives");
        Equal(true, call["requiredPredicates"]!.AsArray().Count > 0, "real native spawn keeps all conditional callsite guards");
        Equal(false, call.ContainsKey("unresolved"), "real selected integer expression is completely bounded");
        Equal(true, raw["referencedProjectiles"]!["references"]!.AsArray().Any(row => row!["type"]!.GetValue<int>() == 8),
            "canonical reference traversal captures the derived child without a family rule");
    }
}
