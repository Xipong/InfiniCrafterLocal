using System;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentSourceGraphNeverReplacesCoreWithUtilityPrefix()
    {
        // Metadata-only fixture: neither AI nor its emitted helper is invoked.
        var assembly = AssemblyBuilder.DefineDynamicAssembly(
            new AssemblyName("MonotoneCore" + Guid.NewGuid().ToString("N")), AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("fixture").DefineType(
            "CoreNoiseProjectile", TypeAttributes.Public, typeof(ModProjectile));
        var helper = type.DefineMethod("VisualOnly", MethodAttributes.Public | MethodAttributes.Static,
            typeof(void), Enumerable.Repeat(typeof(int), 8).ToArray());
        helper.GetILGenerator().Emit(OpCodes.Ret);
        var ai = type.DefineMethod("AI", MethodAttributes.Public | MethodAttributes.Virtual, typeof(void), Type.EmptyTypes);
        var il = ai.GetILGenerator();
        for (int call = 0; call < 160; call++)
        {
            for (int argument = 0; argument < 8; argument++) il.Emit(OpCodes.Ldc_I4, call + argument);
            il.Emit(OpCodes.Call, helper);
        }
        var spawn = typeof(Projectile).GetMethod(nameof(Projectile.NewProjectile), new[] {
            typeof(IEntitySource), typeof(float), typeof(float), typeof(float), typeof(float),
            typeof(int), typeof(int), typeof(float), typeof(int), typeof(float), typeof(float), typeof(float) })!;
        il.Emit(OpCodes.Ldnull);
        for (int value = 0; value < 4; value++) il.Emit(OpCodes.Ldc_R4, 0f);
        il.Emit(OpCodes.Ldc_I4_1); il.Emit(OpCodes.Ldc_I4_2); il.Emit(OpCodes.Ldc_R4, 0f); il.Emit(OpCodes.Ldc_I4_M1);
        for (int value = 0; value < 3; value++) il.Emit(OpCodes.Ldc_R4, 0f);
        il.Emit(OpCodes.Call, spawn); il.Emit(OpCodes.Pop); il.Emit(OpCodes.Ret);
        type.DefineMethodOverride(ai, typeof(ModProjectile).GetMethod(nameof(ModProjectile.AI))!);
        JsonObject graph = SelectionCaptureProjectile(type.CreateType()!);
        JsonObject node = SelectionNode(graph, "CoreNoiseProjectile.AI(")!;
        Equal(true, node?["values"] is JsonObject, "mechanical core retains an AI body");
        Equal(true, SelectionValueMembers(graph, node!).Any(member => member.Contains(".NewProjectile(", StringComparison.Ordinal)),
            "maximal-row upgrades must not replace an already fitting spawn core with decorative void-call prefixes");
        AssertSelectionReferences(graph);
    }
    private abstract class RefusalBaseProjectile : ModProjectile
    {
        public abstract void Step();
    }
    private sealed class RefusalCoreProjectile : RefusalBaseProjectile
    {
        public RefusalBaseProjectile Other = null!;
        public override void AI() { Other.Step(); Projectile.damage = 7; }
        public override void Step() { Projectile.damage = 11; }
    }
    private static void ParentSourceGraphKeepsOmittedCallsiteRefusals()
    {
        JsonObject graph = SelectionCaptureProjectile(typeof(RefusalCoreProjectile));
        Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge =>
            edge["sourceCoverage"]?.GetValue<string>() == "callsite_omitted_from_source_slice"
            && edge["to"] is null && edge["unresolved"]?.GetValue<string>().Contains("virtual_receiver_not_bound", StringComparison.Ordinal) == true),
            "compaction keeps the precise unknown-receiver refusal even when its callsite is omitted");
        AssertSelectionReferences(graph);
    }

    private static void FillOpaqueLocal(ref float value) { value = 1f; }
    private static float ConditionalRefEvidence(ref float other, bool gate)
    {
        float value = 0f;
        FillOpaqueLocal(ref value);
        if (gate) FillOpaqueLocal(ref value);
        other = 7f;
        return value;
    }
    private static void ParentSourceGraphRefWritesPreserveTheirConditions()
    {
        Type graphType = typeof(InfiniCrafterLocal.Common.Services.GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        object body = graphType.GetMethod("Read", flags)!.Invoke(graph,
            new object[] { typeof(EngineRuntimeChecks).GetMethod(nameof(ConditionalRefEvidence), BindingFlags.Static | BindingFlags.NonPublic)! })!;
        Type bodyType = body.GetType(), valueType = bodyType.GetNestedType("Value", BindingFlags.NonPublic)!;
        var statements = (System.Collections.IEnumerable)bodyType.GetField("Statements", flags)!.GetValue(body)!;
        var op = valueType.GetField("Op", flags)!;
        object[] returns = statements.Cast<object>().Where(value => (string)op.GetValue(value)! == "ret").ToArray();
        Array roots = Array.CreateInstance(valueType, returns.Length);
        for (int index = 0; index < returns.Length; index++) roots.SetValue(returns[index], index);
        var row = (JsonObject)bodyType.GetMethod("Project", flags)!.Invoke(body, new object[] { roots, 64 })!;
        var values = row["values"]!.AsObject();
        JsonNode write = values.Last(value => value.Value![0]!.GetValue<string>() == "call").Value!;
        Equal(false, values.Any(value => value.Value![0]!.GetValue<string>().StartsWith("stind", StringComparison.Ordinal)),
            "a write through an unrelated ref argument does not enter the local's provenance");
        Equal(true, row["possibleLocalWrites"] is JsonObject, "opaque local reads link their possible source writes explicitly");
        JsonArray block = row["blocks"]!.AsArray().OfType<JsonArray>().Single(candidate => candidate[0]!.GetValue<int>() == write[3]!.GetValue<int>());
        Equal(true, block[3]!.AsArray().Count > 0, "late-added possible ref writes retain their enclosing live condition");
        Equal(true, block[3]!.AsArray().All(guard => values.ContainsKey(guard!.GetValue<string>())), "every ref-write guard has retained source evidence");
    }

    private static Microsoft.Xna.Framework.Vector2 RefVectorSource(Projectile actor, bool gate)
    {
        var vector = actor.Center - actor.position;
        vector.Normalize();
        if (gate) vector *= 6f;
        var decoration = default(Microsoft.Xna.Framework.Vector2);
        RefVectorNoise(ref decoration);
        return vector;
    }
    private static void RefVectorNoise(ref Microsoft.Xna.Framework.Vector2 value) { value.X = 123f; }
    private static void ParentSourceGraphRetainsOpaqueVectorProvenance()
    {
        Type graphType = typeof(InfiniCrafterLocal.Common.Services.GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        object body = graphType.GetMethod("Read", flags)!.Invoke(graph,
            new object[] { typeof(EngineRuntimeChecks).GetMethod(nameof(RefVectorSource), BindingFlags.Static | BindingFlags.NonPublic)! })!;
        Type bodyType = body.GetType(), valueType = bodyType.GetNestedType("Value", BindingFlags.NonPublic)!;
        var statements = (System.Collections.IEnumerable)bodyType.GetField("Statements", flags)!.GetValue(body)!;
        var op = valueType.GetField("Op", flags)!;
        object[] returns = statements.Cast<object>().Where(value => (string)op.GetValue(value)! == "ret").ToArray();
        Array roots = Array.CreateInstance(valueType, returns.Length);
        for (int index = 0; index < returns.Length; index++) roots.SetValue(returns[index], index);
        var row = (JsonObject)bodyType.GetMethod("Project", flags)!.Invoke(body, new object[] { roots, 64 })!;
        var values = row["values"]!.AsObject();
        Equal(true, values.Any(value => value.Value![1]?.ToString().Contains("Normalize", StringComparison.Ordinal) == true),
            "escaped vector provenance includes its instance mutation source without executing it");
        Equal(true, values.Any(value => value.Value![1]?.ToString().Contains("op_Subtraction", StringComparison.Ordinal) == true),
            "the target-vector construction is retained alongside the opaque ref read");
        Equal(false, values.Any(value => value.Value![1]?.ToString().Contains(nameof(RefVectorNoise), StringComparison.Ordinal) == true),
            "an unrelated decoration ref call is not a dependency of the returned vector");
        Equal(true, values.Any(value => value.Value![0]!.GetValue<string>() == "address_exposed_local"),
            "possible source writes do not manufacture a precise mutated SSA value");
        Equal(true, row["unresolved"]!.AsArray().Any(value => value!.GetValue<string>() == "address_exposed_local_value_unresolved"),
            "an opaque local remains explicitly unresolved even when its possible source writes are shown");
        var refs = row["possibleLocalWrites"]!.AsObject();
        Equal(true, refs.All(pair => values.ContainsKey(pair.Key) && pair.Value!.AsArray().All(id => values.ContainsKey(id!.GetValue<string>()))),
            "provenance links reference retained source rows");
    }

    private sealed class GuardedChargeProjectile : ModProjectile
    {
        private int charge;
        private int visualState;
        private void AdvanceCharge() { charge++; }
        private void Decorate() { visualState++; }
        public override void AI()
        {
            AdvanceCharge(); Decorate();
            if (charge > 10) Projectile.NewProjectile(null, 0f, 0f, 1f, 1f, 1, 1, 0f);
        }
    }
    private static void ParentSourceGraphKeepsHelpersFeedingMechanicalGuards()
    {
        JsonObject graph = SelectionCaptureProjectile(typeof(GuardedChargeProjectile));
        JsonObject node = SelectionNode(graph, "GuardedChargeProjectile.AI(")!;
        string[] members = SelectionValueMembers(graph, node);
        Equal(true, members.Any(member => member.Contains(".AdvanceCharge(", StringComparison.Ordinal)),
            "a helper writing mod state read by the spawn guard remains causal evidence");
        Equal(false, members.Any(member => member.Contains(".Decorate(", StringComparison.Ordinal)),
            "an unrelated mod-field helper is not a mechanical dependency merely because it shares an assembly");
        AssertSelectionReferences(graph);
    } private static MethodInfo BuildSourceAliasDiamonds(int depth) {
  var a=AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("AliasDiamonds"+depth),AssemblyBuilderAccess.Run);
  var t=a.DefineDynamicModule("fixture").DefineType("AliasDiamondSource",TypeAttributes.Public);
  var m=t.DefineMethod("Source",MethodAttributes.Public|MethodAttributes.Static,typeof(float),new[]{typeof(bool)}); var il=m.GetILGenerator();
  var x=il.DeclareLocal(typeof(float));var p=il.DeclareLocal(typeof(float).MakeByRefType());
  il.Emit(OpCodes.Ldc_R4,0f);il.Emit(OpCodes.Stloc,x);il.Emit(OpCodes.Ldloca,x);il.Emit(OpCodes.Stloc,p);
  for(int i=0;i<depth;i++) {
   var next=il.DeclareLocal(typeof(float).MakeByRefType());var other=il.DefineLabel();var join=il.DefineLabel();
   il.Emit(OpCodes.Ldarg_0);il.Emit(OpCodes.Brfalse,other);il.Emit(OpCodes.Ldloc,p);il.Emit(OpCodes.Stloc,next);il.Emit(OpCodes.Br,join);
   il.MarkLabel(other);il.Emit(OpCodes.Ldloc,p);il.Emit(OpCodes.Stloc,next);il.MarkLabel(join);p=next;
  }
  il.Emit(OpCodes.Ldloc,p);il.Emit(OpCodes.Ldc_R4,2f);il.Emit(OpCodes.Stind_R4);il.Emit(OpCodes.Ldloc,x);il.Emit(OpCodes.Ret);
  return t.CreateType()!.GetMethod("Source")!;
 }

    private static void ParentSourceGraphBoundsSharedAliasTraversal()
    {
        MethodInfo method = BuildSourceAliasDiamonds(40);
        Type graphType = typeof(InfiniCrafterLocal.Common.Services.GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        object body = graphType.GetMethod("Read", flags)!.Invoke(graph, new object[] { method })!;
        Type bodyType = body.GetType(), valueType = bodyType.GetNestedType("Value", BindingFlags.NonPublic)!;
        var statements = (System.Collections.IEnumerable)bodyType.GetField("Statements", flags)!.GetValue(body)!;
        var op = valueType.GetField("Op", flags)!;
        object[] returns = statements.Cast<object>().Where(value => (string)op.GetValue(value)! == "ret").ToArray();
        Array roots = Array.CreateInstance(valueType, returns.Length);
        for (int index = 0; index < returns.Length; index++) roots.SetValue(returns[index], index);
        var row = (JsonObject)bodyType.GetMethod("Project", flags)!.Invoke(body, new object[] { roots, 64 })!;
        Equal(true, row["unresolved"]!.AsArray().Any(value => value!.GetValue<string>() == "possible_local_address_bound"),
            "a shared alias DAG uses one traversal work bound, not an exponential per-path expansion");
        Equal(true, row["unresolved"]!.AsArray().Any(value => value!.GetValue<string>() == "address_exposed_local_value_unresolved"),
            "bounded alias evidence never upgrades an opaque local to a precise value");
    }

}
