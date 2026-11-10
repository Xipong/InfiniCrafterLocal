using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Metadata-only hooks: none of these bodies or helpers is executed by capture.
    private sealed class OutputStateItem : ModItem
    {
        public static int Charge;
        public override void ModifyWeaponCrit(Player player, ref float crit)
        { Charge++; if (Charge >= 3 && player.wet) crit += 23f; }
        public override void ModifyWeaponDamage(Player player, ref StatModifier damage)
        { Charge++; if (Charge >= 3 && player.wet) damage *= 1.23f; }
        public override void ModifyWeaponKnockback(Player player, ref StatModifier knockback)
        { Charge++; if (Charge >= 3 && player.wet) knockback *= 1.37f; }
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback)
        {
            Charge++;
            if (Charge >= 3 && player.wet)
            { position.X += 11f; velocity.Y *= 13f; type = 17; damage += 19; knockback += 23f; }
        }
        public override void UseItemHitbox(Player player, ref Rectangle hitbox, ref bool noHitbox)
        { Charge++; if (Charge >= 3 && player.wet) { hitbox.Width += 29; noHitbox = true; } }
        public override void ModifyHitNPC(Player player, NPC target, ref NPC.HitModifiers modifiers)
        { Charge++; if (Charge >= 3 && player.wet) modifiers.SourceDamage.Flat += 31f; }
        public override bool CanUseItem(Player player)
        { Charge++; return Charge >= 3 && player.wet; }
        public override bool CanShoot(Player player)
        { Charge++; return Charge >= 3 && player.wet; }
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
        { Charge++; return Charge >= 3 && player.wet; }
    }

    private sealed class OutputAliasItem : ModItem
    {
        private static int charge;
        private static int Fill(ref float value) { value += 41f; return 0; }
        private static int FillModifier(ref StatModifier value) { value *= 1.41f; return 0; }
        public override void ModifyWeaponCrit(Player player, ref float crit)
        { charge++; ref float alias = ref crit; if (player.wet) Fill(ref alias); }
        public override void ModifyWeaponDamage(Player player, ref StatModifier damage)
        { charge++; if (player.wet) FillModifier(ref damage); }
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback)
        { charge++; if (player.wet) velocity.Normalize(); }
    }
    private sealed class OutputBuilder
    {
        public OutputBuilder(out float value) { value = 43f; }
        public OutputBuilder(ref StatModifier value) { value *= 1.43f; }
    }
    private sealed class OutputConstructorItem : ModItem
    {
        private static int charge;
        public override void ModifyWeaponCrit(Player player, ref float crit)
        { charge++; if (player.wet) _ = new OutputBuilder(out crit); }
        public override void ModifyWeaponDamage(Player player, ref StatModifier damage)
        { charge++; if (player.wet) _ = new OutputBuilder(ref damage); }
    }
    private readonly struct OutputReadonlyValue
    {
        public float Read() => 1f;
    }
    private struct OutputMutableValue
    {
        public readonly float Read() => 1f;
    }
    private sealed class OutputNoiseItem : ModItem
    {
        private static int charge;
        private static float storage;
        private static ref float Opaque() => ref storage;
        private static int LocalOutput(out float value) { value = 47f; return 0; }
        private static float CosmeticValue(float value) => value + 53f;
        public override void ModifyShootStats(Player player, ref Vector2 position, ref Vector2 velocity, ref int type, ref int damage, ref float knockback)
        {
            charge++;
            LocalOutput(out float local);
            CosmeticValue(local);
            _ = new OutputBuilder(out local);
            Vector2 vector = Vector2.Zero;
            vector.Normalize();
        }
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
        { charge++; velocity.Normalize(); _ = new OutputBuilder(out knockback); return true; }
        private static void OpaqueOutput(ref float value) { ref float unknown = ref Opaque(); unknown += 59f; }
        private static void ReassignedOutput(ref float value, ref float other) { value = ref other; value += 61f; }
        private static float ReadIn(in float value) => value;
        private static float ReadRefReadonly(ref readonly float value) => value;
        private static void RefReadonlyInput(ref float value) { _ = ReadRefReadonly(in value); }
        private static void RefReadonlyFormal(ref readonly float value) { _ = ReadRefReadonly(in value); }
        private static void MarshaledRef([System.Runtime.InteropServices.In] ref float value) { charge++; value += 71f; }
        private static int MarshaledHelper([System.Runtime.InteropServices.In] ref float value) { value += 73f; return 0; }
        private static void MarshaledCall(ref float value) { charge++; _ = MarshaledHelper(ref value); }
        private static void InOnlyInput(ref float value) { _ = ReadIn(in value); }
        private static void InOnlyFormal(in float value) { _ = ReadIn(in value); }
        private static void ReadonlyType(ref OutputReadonlyValue value) { _ = value.Read(); }
        private static void ReadonlyMethod(ref OutputMutableValue value) { _ = value.Read(); }
        private static void MixedOutput(ref float value, bool gate)
        { float local = 0f; ref float alias = ref (gate ? ref value : ref local); alias += 61f; }
        private static void BothOutputs(ref float first, ref float second, bool gate)
        { ref float alias = ref (gate ? ref first : ref second); alias += 67f; }

    }

    private static JsonObject CaptureOutputHook(Type owner, string hook)
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        graphType.GetField("rosterRead", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(graph, true);
        graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new object[]
            { owner, typeof(ModItem), new HashSet<string>(new[] { hook }), "parent_ModItem", "event_signature" });
        var result = (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
        AssertSelectionReferences(result);
        return result;
    }

    private static JsonObject OutputHookNode(JsonObject graph, Type owner, string hook)
        => SelectionNode(graph, owner.Name + "." + hook + "(") ?? throw new InvalidOperationException("Missing hook " + hook);
    private static bool HasOutputConstant(JsonObject node, string value)
        => node["values"]!.AsObject().Any(pair => (pair.Value![0]!.GetValue<string>() == "const"
                || pair.Value![0]!.GetValue<string>().StartsWith("ldc", StringComparison.Ordinal))
            && pair.Value![1]?.ToString() == value);
    private static void AssertOutputGuard(JsonObject graph, JsonObject node, string label)
    {
        Equal(true, SelectionValueMembers(graph, node).Any(member => member.EndsWith(".wet", StringComparison.Ordinal)), label + " retains the live wet gate");
        Equal(false, node["unresolvedEnclosingBranchCount"] is JsonValue, label + " complete small controls fit");
        Equal(true, node["blocks"]!.AsArray().OfType<JsonArray>().Any(block => block[3]!.AsArray().Count > 0), label + " retained effects remain conditional");
    }

    private static void AssertOutputEffectGuard(JsonObject graph, JsonObject node, JsonNode effect, string label)
    {
        var values = node["values"]!.AsObject();
        var block = node["blocks"]!.AsArray().OfType<JsonArray>().Single(row => row[0]!.GetValue<int>() == effect[3]!.GetValue<int>());
        var work = new Stack<string>(block[3]!.AsArray().Select(id => id!.GetValue<string>()));
        var seen = new HashSet<string>(StringComparer.Ordinal);
        while (work.Count > 0)
        {
            string id = work.Pop();
            if (!seen.Add(id)) continue;
            foreach (var input in values[id]![2]!.AsArray()) work.Push(input!.GetValue<string>());
        }
        Equal(true, seen.Any(id => values[id]![1] is JsonObject operand && operand["member"] is JsonNode member
            && graph["members"]![member.GetValue<int>()]!["name"]!.GetValue<string>().EndsWith(".wet", StringComparison.Ordinal)),
            label + " exact output store/call retains its own wet control dependency");
    }

    private static void ParentHookOutputsSurviveStateWrites()
    {
        OutputStateItem.Charge = 0;
        foreach (var (hook, literals, stores) in new[] {
            ("ModifyWeaponCrit", new[] { "23" }, 1), ("ModifyWeaponDamage", new[] { "1.23" }, 1),
            ("ModifyWeaponKnockback", new[] { "1.37" }, 1), ("ModifyShootStats", new[] { "11", "13", "17", "19", "23" }, 5),
            ("UseItemHitbox", new[] { "29" }, 2), ("ModifyHitNPC", new[] { "31" }, 1),
        })
        {
            JsonObject graph = CaptureOutputHook(typeof(OutputStateItem), hook);
            JsonObject node = OutputHookNode(graph, typeof(OutputStateItem), hook);
            foreach (string literal in literals) Equal(true, HasOutputConstant(node, literal), hook + " literal output " + literal + " survives a preceding state write");
            int outputs = node["values"]!.AsObject().Count(pair => pair.Value![0]!.GetValue<string>() is "stfld" or "stobj"
                || pair.Value![0]!.GetValue<string>().StartsWith("stind", StringComparison.Ordinal));
            Equal(stores, outputs, hook + " every exact output store is retained");
            foreach (JsonNode effect in node["values"]!.AsObject().Select(pair => pair.Value!).Where(value =>
                value[0]!.GetValue<string>() is "stfld" or "stobj" || value[0]!.GetValue<string>().StartsWith("stind", StringComparison.Ordinal)))
                AssertOutputEffectGuard(graph, node, effect, hook);
            AssertOutputGuard(graph, node, hook);
            Equal(true, graph.ToJsonString().Length < 10000, hook + " regression is not a saturated graph");
        }
        Equal(0, OutputStateItem.Charge, "reading compiled hooks never executes their state or output writes");
    }

    private static void ParentHookReturnOutputsSurviveStateWrites()
    {
        foreach (string hook in new[] { "CanUseItem", "CanShoot", "Shoot" })
        {
            JsonObject graph = CaptureOutputHook(typeof(OutputStateItem), hook);
            JsonObject node = OutputHookNode(graph, typeof(OutputStateItem), hook);
            Equal(true, node["values"]!.AsObject().Any(pair => pair.Value![0]!.GetValue<string>() == "ret"
                && pair.Value![2]!.AsArray().Count == 1), hook + " keeps its actual nonvoid return source");
            Equal(true, HasOutputConstant(node, "3"), hook + " return keeps its charge threshold");
            AssertOutputGuard(graph, node, hook);
        }
    }

    private static void ParentHookOutputsKeepAliasesAndConstructors()
    {
        foreach (var (owner, hook, effect) in new[] {
            (typeof(OutputAliasItem), "ModifyWeaponCrit", ".Fill("),
            (typeof(OutputAliasItem), "ModifyWeaponDamage", ".FillModifier("),
            (typeof(OutputAliasItem), "ModifyShootStats", ".Normalize("),
            (typeof(OutputConstructorItem), "ModifyWeaponCrit", "OutputBuilder..ctor("),
            (typeof(OutputConstructorItem), "ModifyWeaponDamage", "OutputBuilder..ctor("),
        })
        {
            JsonObject graph = CaptureOutputHook(owner, hook);
            JsonObject node = OutputHookNode(graph, owner, hook);
            Equal(true, SelectionValueMembers(graph, node).Any(member => member.Contains(effect, StringComparison.Ordinal)),
                owner.Name + "." + hook + " keeps output callsite and actual ref binding, not only a disconnected helper body");
            JsonNode call = node["values"]!.AsObject().Select(pair => pair.Value!).Single(value =>
                value[1] is JsonObject operand && operand["member"] is JsonNode member
                && graph["members"]![member.GetValue<int>()]!["name"]!.GetValue<string>().Contains(effect, StringComparison.Ordinal));
            AssertOutputEffectGuard(graph, node, call, owner.Name + "." + hook);
            AssertOutputGuard(graph, node, hook);
        }
    }

    private static (object Body, object[] Statements, Type GraphType) ReadOutputBody(MethodInfo method)
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        object body = graphType.GetMethod("Read", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new object[] { method })!;
        var statements = (IEnumerable)body.GetType().GetField("Statements", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(body)!;
        return (body, statements.Cast<object>().ToArray(), graphType);
    }
    private static string OutputOp(object value) => (string)value.GetType().GetField("Op", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(value)!;
    private static bool IsProvenOutput(object body, object value, Type graphType)
        => (bool)graphType.GetMethod("WritesMethodOutput", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new[] { body, value })!;

    private static void ParentHookOutputsRejectUnprovedAddresses()
    {
        foreach (string hook in new[] { "ModifyShootStats", "Shoot", "OpaqueOutput", "ReassignedOutput", "InOnlyInput", "InOnlyFormal", "RefReadonlyInput", "RefReadonlyFormal", "ReadonlyType", "ReadonlyMethod", "MixedOutput" })
        {
            var (body, statements, graphType) = ReadOutputBody(typeof(OutputNoiseItem).GetMethod(hook,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)!);
            Equal(false, statements.Where(value => OutputOp(value) != "ret").Any(value => IsProvenOutput(body, value, graphType)),
                hook + " does not prove local/byvalue/opaque/address-exposed arguments as formal outputs");
        }
        foreach (var (method, expected) in new[] {
            (typeof(OutputNoiseItem).GetMethod("BothOutputs", BindingFlags.Static | BindingFlags.NonPublic)!, true),
            (BuildOutputAliasChain(40), true), (BuildOutputAliasChain(80), false),
        })
        {
            var (body, statements, graphType) = ReadOutputBody(method);
            object store = statements.Single(value => OutputOp(value) == "stind.r4");
            Equal(expected, IsProvenOutput(body, store, graphType), method.Name + " bounds aliases without widening unknown output proof");
        }
        foreach (var (name, op) in new[] { ("MarshaledRef", "stind.r4"), ("MarshaledCall", "call") })
        {
            var (body, statements, graphType) = ReadOutputBody(typeof(OutputNoiseItem).GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)!);
            object output = statements.Single(value => OutputOp(value) == op);
            Equal(true, IsProvenOutput(body, output, graphType), name + " marshaling InAttribute does not make a managed ref readonly");
        }
        JsonObject graph = CaptureOutputHook(typeof(OutputNoiseItem), "ModifyShootStats");
        JsonObject node = OutputHookNode(graph, typeof(OutputNoiseItem), "ModifyShootStats");
        foreach (string noise in new[] { ".LocalOutput(", ".CosmeticValue(", "OutputBuilder..ctor(", ".Normalize(" })
            Equal(false, SelectionValueMembers(graph, node).Any(member => member.Contains(noise, StringComparison.Ordinal)),
                "an unused helper output does not become causal by its signature: " + noise);
    }

    private static MethodInfo BuildOutputAliasChain(int length)
    {
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("OutputAliasChain" + length), AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("fixture").DefineType("OutputAlias" + length, TypeAttributes.Public);
        var method = type.DefineMethod("Write", MethodAttributes.Public | MethodAttributes.Static, typeof(void),
            new[] { typeof(float).MakeByRefType() });
        var il = method.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        for (int index = 0; index < length; index++)
        {
            var local = il.DeclareLocal(typeof(float).MakeByRefType());
            il.Emit(OpCodes.Stloc, local); il.Emit(OpCodes.Ldloc, local);
        }
        il.Emit(OpCodes.Ldc_R4, 67f); il.Emit(OpCodes.Stind_R4); il.Emit(OpCodes.Ret);
        return type.CreateType()!.GetMethod("Write")!;
    }

    private static void ParentHookOutputSelectionPreservesReturnPriority()
    {
        foreach (var (hook, op, expected) in new[] { ("CanUseItem", "ret", 2), ("ModifyWeaponCrit", "stind.r4", 1) })
        {
            var (body, statements, graphType) = ReadOutputBody(typeof(OutputStateItem).GetMethod(hook)!);
            object[] selected = statements.Where(value => OutputOp(value) == op).ToArray();
            Equal(true, selected.Length > 0, hook + " has the expected compiled statement");
            foreach (object statement in selected)
                Equal(expected, (int)graphType.GetMethod("StatementPriority", BindingFlags.Static | BindingFlags.NonPublic)!
                    .Invoke(null, new[] { statement, body })!, hook + " preserves established optional-source ordering");
        }
    }

    private sealed class CapturedOutputItem : ModItem
    {
        public static int Executions;
        public override void ModifyWeaponDamage(Player player, ref StatModifier damage)
        { Executions++; if (Executions >= 3 && player.wet) damage *= 1.23f; }
    }
    private static void ParentHookOutputsReachNativeFactCapture()
    {
        using var state = new NativeActorState();
        CapturedOutputItem.Executions = 0;
        var item = new Item(ItemID.WoodenSword) { damage = 7, crit = 4 };
        var host = new CapturedOutputItem();
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, item);
        typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(item, host);
        object captured = typeof(GeneratorClient).GetMethod("CaptureParentNativeFacts", BindingFlags.Static | BindingFlags.NonPublic)!
            .Invoke(null, new object?[] { item, null })!;
        var facts = (JsonObject)captured.GetType().GetProperty("RuntimeFacts")!.GetValue(captured)!;
        JsonObject graph = facts["parentSourceGraph"]!.AsObject();
        JsonObject node = OutputHookNode(graph, typeof(CapturedOutputItem), "ModifyWeaponDamage");
        Equal(true, HasOutputConstant(node, "1.23"), "real native fact capture contains the exact conditional output source");
        AssertOutputGuard(graph, node, "native capture");
        Equal(7, facts["damage"]!.GetValue<int>(), "source selection never applies or guesses a live damage modifier");
        Equal(4, facts["crit"]!.GetValue<int>(), "base crit snapshot stays 4");
        Equal(0, CapturedOutputItem.Executions, "native fact capture never executes the hook");
        string? path = Environment.GetEnvironmentVariable("INFINI_HOOK_OUTPUT_PACKET");
        if (!string.IsNullOrEmpty(path)) System.IO.File.WriteAllText(path,
            new JsonObject { ["name"] = "conditional output fixture", ["runtimeFacts"] = facts.DeepClone(), ["parentSourceGraph"] = graph.DeepClone() }.ToJsonString());
    }
}
