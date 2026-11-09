using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static class SelectionNativeActor
    {
        public static void MechanicalAndDisplay(Projectile actor)
        {
            actor.alpha = 77; actor.frame = 3; actor.oldRot[0] = 5f;
            if (actor.wet) actor.velocity.X += 7f;
            actor.localAI[0] += 1f;
        }
        public static void Entry(Projectile actor) => Helper(actor);
        public static void Helper(Projectile actor)
        {
            if (actor.type == 1234) EffectA(actor);
            if (actor.type == 5678) EffectB(actor);
            if (actor.wet) actor.damage += 59;
            actor.scale *= 2f;
        }
        public static void EffectA(Projectile actor) { actor.damage += 31; }
        public static void EffectB(Projectile actor) { actor.damage += 37; }
        public static void Foreign(Projectile actor) { Helper(actor); Helper(Terraria.Main.projectile[0]); }
        public static void Changed(Projectile actor)
        {
            actor.type = 7654;
            if (actor.type == 1234) actor.damage += 41;
            else actor.damage += 43;
        }
    }

    private static void ParentSourceGraphKeepsRawSourceWhenIdentityProofIsBounded()
    {
        // A thousand early comparisons and 4500 later identity writes exceed
        // the optional proof's real work bound. No generated IL is executed.
        var assembly = System.Reflection.Emit.AssemblyBuilder.DefineDynamicAssembly(
            new AssemblyName("SourceGraphIdentityWorkBound"), System.Reflection.Emit.AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("fixture").DefineType("LateIdentityHazards", TypeAttributes.Public);
        var builder = type.DefineMethod("Source", MethodAttributes.Public | MethodAttributes.Static,
            typeof(void), new[] { typeof(Projectile) });
        var il = builder.GetILGenerator(); var exit = il.DefineLabel();
        FieldInfo identityField = typeof(Projectile).GetField("type")!;
        for (int index = 0; index < 1000; index++)
        {
            il.Emit(System.Reflection.Emit.OpCodes.Ldarg_0); il.Emit(System.Reflection.Emit.OpCodes.Ldfld, identityField);
            il.Emit(System.Reflection.Emit.OpCodes.Ldc_I4, index); il.Emit(System.Reflection.Emit.OpCodes.Beq, exit);
        }
        for (int index = 0; index < 4500; index++)
        {
            il.Emit(System.Reflection.Emit.OpCodes.Ldarg_0); il.Emit(System.Reflection.Emit.OpCodes.Ldc_I4_0);
            il.Emit(System.Reflection.Emit.OpCodes.Stfld, identityField);
        }
        il.Emit(System.Reflection.Emit.OpCodes.Ldarg_0); il.Emit(System.Reflection.Emit.OpCodes.Ldc_R4, 13f);
        il.Emit(System.Reflection.Emit.OpCodes.Stfld, typeof(Projectile).GetField("scale")!);
        il.MarkLabel(exit); il.Emit(System.Reflection.Emit.OpCodes.Ret);
        MethodInfo method = type.CreateType()!.GetMethod("Source")!;
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        Type contextType = graphType.GetNestedType("SourceInvocation", BindingFlags.NonPublic)!;
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        object context = Activator.CreateInstance(contextType, flags, null,
            new object?[] { null, typeof(Projectile), 9000, 1, false }, null)!;
        graphType.GetField("currentInvocation", flags)!.SetValue(graph, context);
        object? body = graphType.GetMethod("ReadInvocation", flags)!.Invoke(graph, new object[] { method });
        Equal(true, body is not null, "an optional identity work refusal does not discard readable raw source");
        var receipts = (System.Collections.IDictionary)graphType.GetField("nativeIdentityReceipts", flags)!.GetValue(graph)!;
        JsonObject receipt = receipts.Values.Cast<JsonObject>().Single();
        Equal("identity_control_flow_work_bound", receipt["selectionUnavailable"]!.GetValue<string>(),
            "the real proof-work bound is not mislabeled as a source scan failure");
        Equal(true, receipt["scope"]!.GetValue<string>().Contains("no_identity_based_child_admission", StringComparison.Ordinal),
            "raw fallback cannot silently retain captured-identity child admission");
        var unavailable = (HashSet<string>)graphType.GetField("nativeIdentityUnavailable", flags)!.GetValue(graph)!;
        Equal(1, unavailable.Count, "the invocation is explicitly marked unproved for follow-up discovery");
    }

    private static JsonObject SelectionCaptureNative(MethodInfo entry, params int[] identities)
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        Type contextType = graphType.GetNestedType("SourceInvocation", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        graphType.GetField("rosterRead", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(graph, true);
        MethodInfo add = graphType.GetMethod("Add", BindingFlags.Instance | BindingFlags.NonPublic)!;
        MethodInfo edge = graphType.GetMethod("Edge", BindingFlags.Instance | BindingFlags.NonPublic)!;
        foreach (int identity in identities)
        {
            object context = Activator.CreateInstance(contextType, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                binder: null, args: new object?[] { null, typeof(Projectile), identity, 1, false }, culture: null)!;
            int node = (int)add.Invoke(graph, new object?[] { entry, 0, null, context })!;
            ((HashSet<int>)graphType.GetField("principalNodes", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!).Add(node);
            edge.Invoke(graph, new object?[] { null, node, "captured_native_fixture", null, JsonValue.Create(identity), null });
        }
        return (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
    }

    private static string[] SelectionValueMembers(JsonObject graph, JsonObject node)
        => node["values"]!.AsObject().Select(value => value.Value?[1]).OfType<JsonObject>()
            .Where(value => value["member"] is JsonNode).Select(value => graph["members"]![value["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()).ToArray();

    private static void ParentSourceGraphSpecializesEachNativeActorContext()
    {
        var method = typeof(SelectionNativeActor).GetMethod(nameof(SelectionNativeActor.Entry))!;
        JsonObject graph = SelectionCaptureNative(method, 1234, 5678);
        JsonObject[] helpers = graph["nodes"]!.AsArray().OfType<JsonObject>().Where(node =>
            graph["members"]![node["method"]!.GetValue<int>()]!["name"]!.GetValue<string>().Contains("SelectionNativeActor.Helper(", StringComparison.Ordinal)).ToArray();
        Equal(2, helpers.Length, "a shared native helper has separate captured identity contexts");
        foreach (var helper in helpers)
        {
            int identity = helper["nativeIdentity"]!["projectileType"]!.GetValue<int>();
            string[] members = SelectionValueMembers(graph, helper);
            Equal(true, members.Any(name => name.Contains(identity == 1234 ? ".EffectA(" : ".EffectB(", StringComparison.Ordinal)), "the matching actor branch is retained");
            Equal(false, members.Any(name => name.Contains(identity == 1234 ? ".EffectB(" : ".EffectA(", StringComparison.Ordinal)), "another actor's call is not imported into this invocation");
            Equal(true, members.Any(name => name.EndsWith(".scale", StringComparison.Ordinal)), "source after the identity join is preserved");
            var values = helper["values"]!.AsObject();
            bool DependsOn(string id, Func<JsonArray, bool> predicate, HashSet<string> seen)
            {
                if (!seen.Add(id) || values[id] is not JsonArray value) return false;
                return predicate(value) || value[2]!.AsArray().Any(input => DependsOn(input!.GetValue<string>(), predicate, seen));
            }
            JsonNode wetWrite = values.First(pair => pair.Value is JsonArray value && value[0]?.GetValue<string>() == "stfld"
                && DependsOn(pair.Key, value => value[0]?.GetValue<string>() == "const" && value[1] is JsonValue literal
                    && literal.TryGetValue<int>(out int number) && number == 59, new HashSet<string>())).Value!;
            int blockId = wetWrite[3]!.GetValue<int>();
            JsonArray block = helper["blocks"]!.AsArray().OfType<JsonArray>().Single(row => row[0]!.GetValue<int>() == blockId);
            Equal(true, block[3]!.AsArray().Any(guard => DependsOn(guard!.GetValue<string>(), value => value[1] is JsonObject operand
                && operand["member"] is JsonNode member && graph["members"]![member.GetValue<int>()]!["name"]!.GetValue<string>().EndsWith(".wet", StringComparison.Ordinal),
                new HashSet<string>())), "strict identity specialization retains the live wet predicate on its damage write");
            Equal(true, helper["nativeIdentity"]!["selectedEdgeCount"]!.GetValue<int>() > 0, "the existing certified selector drives discovery");
        }
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphDoesNotBindForeignNativeActor()
    {
        JsonObject graph = SelectionCaptureNative(typeof(SelectionNativeActor).GetMethod(nameof(SelectionNativeActor.Foreign))!, 1234);
        JsonObject[] helpers = graph["nodes"]!.AsArray().OfType<JsonObject>().Where(node =>
            graph["members"]![node["method"]!.GetValue<int>()]!["name"]!.GetValue<string>().Contains("SelectionNativeActor.Helper(", StringComparison.Ordinal)).ToArray();
        Equal(2, helpers.Length, "a later foreign callsite cannot reuse an earlier bound callsite proof for the same helper");
        JsonObject? helper = helpers.SingleOrDefault(node => node["nativeIdentity"]?["projectileType"] is null);
        Equal(true, helper?["values"] is JsonObject, "unbound helper retains explicit source evidence");
        Equal(true, helper!["nativeIdentity"]!["projectileType"] is null, "a foreign projectile does not inherit captured type 1234");
        Equal(true, helper["nativeIdentity"]!["scope"]!.GetValue<string>().Contains("unbound_actor", StringComparison.Ordinal), "unbound identity remains explicit");
        Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge => edge["unresolved"]?.GetValue<string>().Contains("native_actor_identity_not_proven", StringComparison.Ordinal) == true),
            "the missing receiver proof is carried on the call edge");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphRetainsNativeIdentityHazards()
    {
        JsonObject graph = SelectionCaptureNative(typeof(SelectionNativeActor).GetMethod(nameof(SelectionNativeActor.Changed))!, 1234);
        JsonObject node = SelectionNode(graph, "SelectionNativeActor.Changed(")!;
        Equal(true, node["nativeIdentity"]!["blockedIdentityReadCount"]!.GetValue<int>() > 0, "captured identity is not assumed stable after a source identity write");
        Equal(true, graph["unresolved"]!.AsArray().Any(value => value?.GetValue<string>() == "native_identity_reads_blocked_after_effect"), "the proof refusal survives graph export");
        Equal(true, SelectionValueMembers(graph, node).Any(name => name.EndsWith(".type", StringComparison.Ordinal)), "the unresolved identity condition remains source evidence");
        AssertSelectionReferences(graph);
    }
    private static void ParentSourceGraphNativeCoreOmitsUnrelatedPresentation()
    {
        JsonObject graph = SelectionCaptureNative(typeof(SelectionNativeActor).GetMethod(nameof(SelectionNativeActor.MechanicalAndDisplay))!, 1234);
        JsonObject node = SelectionNode(graph, "SelectionNativeActor.MechanicalAndDisplay(")!;
        string[] members = SelectionValueMembers(graph, node);
        Equal(true, members.Any(name => name.EndsWith(".velocity", StringComparison.Ordinal)), "native actor motion remains a mechanical root");
        Equal(true, members.Any(name => name.EndsWith(".wet", StringComparison.Ordinal)), "motion keeps its live predicate");
        Equal(true, members.Any(name => name.EndsWith(".localAI", StringComparison.Ordinal)), "native AI state remains source evidence");
        Equal(false, members.Any(name => name.EndsWith(".alpha", StringComparison.Ordinal) || name.EndsWith(".frame", StringComparison.Ordinal)
            || name.EndsWith(".oldRot", StringComparison.Ordinal)), "unrelated presentation writes do not expand the native mechanical core");
        AssertSelectionReferences(graph);
    }
    private static void ParentSourceGraphKeepsLargeMechanicalBundle()
    {
        const int writes = 130;
        var assembly = System.Reflection.Emit.AssemblyBuilder.DefineDynamicAssembly(
            new AssemblyName("LargeMechanicalCore"), System.Reflection.Emit.AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("fixture").DefineType("LargeMechanicalCore", TypeAttributes.Public);
        var method = type.DefineMethod("Source", MethodAttributes.Public | MethodAttributes.Static,
            typeof(void), new[] { typeof(Projectile) });
        var il = method.GetILGenerator();
        for (int index = 0; index < writes; index++)
        {
            il.Emit(System.Reflection.Emit.OpCodes.Ldarg_0);
            il.Emit(System.Reflection.Emit.OpCodes.Ldc_I4, index);
            il.Emit(System.Reflection.Emit.OpCodes.Stfld, typeof(Projectile).GetField("damage")!);
        }
        il.Emit(System.Reflection.Emit.OpCodes.Ret);
        JsonObject graph = SelectionCaptureNative(type.CreateType()!.GetMethod("Source")!, 1234);
        JsonObject node = SelectionNode(graph, "LargeMechanicalCore.Source(")!;
        int retainedWrites = node["values"]?.AsObject().Count(value => value.Value![0]!.GetValue<string>() == "stfld") ?? 0;
        Equal(writes, retainedWrites, "a bounded mechanical bundle beyond the former 12k method limit is retained without a prefix fallback");
        Equal("mechanical_core", node["sourceSelection"]!.GetValue<string>(), "the complete source bundle is admitted as core, not a prefix fallback");
        AssertSelectionReferences(graph);
    }
}
