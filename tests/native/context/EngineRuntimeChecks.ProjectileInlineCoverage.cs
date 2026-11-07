using System;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static int InlineEffectExecutions;
    private static void InlineArrayEffect(float[] samples) { InlineEffectExecutions++; samples[0] = 4f; }
    private static void InlineByrefEffect(ref float sample) { InlineEffectExecutions++; sample = 8f; }
    private static void InlineEffectSource(Projectile projectile)
    {
        projectile.rotation = projectile.ai[0];
        if (projectile.ai[0] > 30f) projectile.friendly = true;
        projectile.damage = 17;
        projectile.Opacity = projectile.ai[0] / 120f;
        InlineArrayEffect(projectile.localAI);
        InlineByrefEffect(ref projectile.ai[1]);
    }

    private static MethodInfo InlineBranchFloodSource()
    {
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("InlineBranches" + Guid.NewGuid().ToString("N")), AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("fixture").DefineType("Window", TypeAttributes.Public);
        var method = type.DefineMethod("Source", MethodAttributes.Public | MethodAttributes.Static, typeof(void), new[] { typeof(Projectile) });
        var il = method.GetILGenerator(); var end = il.DefineLabel();
        il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldfld, typeof(Projectile).GetField("aiStyle")!);
        il.Emit(OpCodes.Ldc_I4, 123); il.Emit(OpCodes.Bne_Un, end);
        for (int n = 0; n < 512; n++)
        {
            var next = il.DefineLabel();
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldfld, typeof(Projectile).GetField("active")!);
            il.Emit(OpCodes.Brfalse, next); il.Emit(OpCodes.Nop); il.MarkLabel(next);
        }
        il.MarkLabel(end); il.Emit(OpCodes.Ret);
        return type.CreateType()!.GetMethod("Source")!;
    }

    private static void ProjectileInlineEffectsRetainMutableSource()
    {
        InlineEffectExecutions = 0;
        foreach (string role in new[] { "dispatch", "motion" })
        {
            var facts = GeneratorClient.InspectProjectileAttackSource(typeof(EngineRuntimeChecks).GetMethod(nameof(InlineEffectSource), BindingFlags.Static | BindingFlags.NonPublic)!, role);
            var rows = facts["observations"]!.AsArray();
            Equal(true, rows.Any(row => row!["expression"]?.GetValue<string>().Contains("Projectile.friendly", StringComparison.Ordinal) == true
                && row["requiredPredicates"]!.AsArray().Count > 0), "friendly write keeps its source guard: " + role);
            Equal(true, rows.Any(row => row!["expression"]?.GetValue<string>().Contains("Projectile.damage", StringComparison.Ordinal) == true), "damage write is observed independently of motion: " + role);
            Equal(true, rows.Any(row => row!["call"]?.GetValue<string>() == "Projectile.set_Opacity"), "actor setter remains an explicit call: " + role);
            foreach (string method in new[] { nameof(InlineArrayEffect), nameof(InlineByrefEffect) })
                Equal(true, rows.Any(row => row!["call"]?.GetValue<string>().Contains(method, StringComparison.Ordinal) == true), "mutable argument call retained: " + method);
        }
        Equal(0, InlineEffectExecutions, "native source readers never execute setters or opaque mutable calls");
        // Independently constrain only the new effect closures. Their refusal
        // cannot mutate an already captured rotation/AI program into an empty one.
        const BindingFlags all = BindingFlags.Static | BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        var owner = typeof(GeneratorClient);
        var bodyType = owner.GetNestedType("ParentSourceMethod", all)!;
        var sourceMethod = typeof(EngineRuntimeChecks).GetMethod(nameof(InlineEffectSource), all)!;
        var body = Activator.CreateInstance(bodyType, all, null, new object?[] { sourceMethod, null, null, null }, null)!;
        var observerType = owner.GetNestedType("AttackSourceObservation", all)!;
        var observer = Activator.CreateInstance(observerType, all, null, new object?[] { body, "motion", null, null }, null)!;
        var established = (JsonObject)observerType.GetMethod("Finish", all)!.Invoke(observer, null)!;
        Equal(true, established["observations"]!.AsArray().Any(row => row!["expression"]?.GetValue<string>().Contains("Projectile.rotation", StringComparison.Ordinal) == true), "preservation oracle starts from a nonempty established motion fact");
        string before = established.ToJsonString();
        var refused = owner.GetMethod("CaptureProjectileAdditionalEffectSlices", all)!.Invoke(null,
            new object?[] { body, null, "motion", 32, 0, 12000 })!;
        var programs = (System.Collections.Generic.List<JsonObject>)refused.GetType().GetProperty("Programs", all)!.GetValue(refused)!;
        Equal(true, programs.Count > 0 && programs.All(program => program["coverage"]?.GetValue<string>() == "unknown"), "each refused added effect remains an explicit unknown source");
        foreach (var program in programs)
            Equal(false, (bool)owner.GetMethod("TryMergeProjectileSourcePrograms", all)!.Invoke(null, new object[] { established, program })!, "unknown extra closure cannot replace the captured baseline");
        Equal(before, established.ToJsonString(), "extra effect work exhaustion preserves every established source row");

        var flood = ReadParentWindows(InlineBranchFloodSource(), 123, meaningfulBudget: true);
        Equal(0, flood.Windows.Count, "branch-heavy inline region is bounded independently of raw instruction count");
        Equal(true, flood.Gaps.Contains("identity_window_control_flow_work_bound"), "branch work refusal stays explicit");
    }

    private static void ProjectileInlineLastPrismSourceRetainsAdmissionAndScan()
    {
        var reference = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = ProjectileID.LastPrismLaser, aiStyle = 84 });
        Equal(true, reference["motionDispatch"] is JsonObject, "source-proved inline style region is captured without an AI helper");
        var dispatch = reference["motionDispatch"]!.AsObject();
        var selected = dispatch["identitySelected"]?.AsObject() ?? dispatch;
        var rows = selected["observations"]!.AsArray();
        Equal(true, rows.Any(row => row!["expression"]?.GetValue<string>().Contains("Projectile.friendly", StringComparison.Ordinal) == true), "native delayed damage admission write survives");
        Equal(true, rows.Any(row => row!["call"]?.GetValue<string>() == "Projectile.set_Opacity"), "native opacity call survives");
        Equal(true, rows.Any(row => row!["call"]?.GetValue<string>() == "Collision.LaserScan"), "native blocking scan is an explicit mutable-array call");
        Equal(true, selected["predicates"]!.AsArray().Count > 0, "inline effect conditions remain unevaluated source predicates");
        Equal(true, selected["dependencies"]!.AsObject().Any(pair => pair.Value?["scope"]?.GetValue<string>().Contains("address_exposed_local", StringComparison.Ordinal) == true), "scan sample array use retains address and alias boundary");
        Equal(false, reference["coverage"]!["unresolved"]!.AsArray().Any(gap => gap!.GetValue<string>().Contains("identity_window_meaningful_instruction_bound", StringComparison.Ordinal)), "supported region is no longer rejected by obsolete instruction cutoff");
    }
}
