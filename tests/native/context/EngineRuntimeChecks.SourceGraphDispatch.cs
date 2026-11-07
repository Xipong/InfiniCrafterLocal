using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private abstract class SelectionAbstractHoldout : ModProjectile
    {
        public override void AI() => HoldoutStep();
        public abstract void HoldoutStep();
    }
    private sealed class SelectionConcreteHoldoutA : SelectionAbstractHoldout
    {
        public override void HoldoutStep() => EmitA();
        private void EmitA() => Terraria.Projectile.NewProjectile(null!, 0f, 0f, 1f, 0f, 1, 2, 0f);
    }
    private sealed class SelectionConcreteHoldoutB : SelectionAbstractHoldout
    {
        public override void HoldoutStep() => EmitB();
        private void EmitB() => Terraria.Projectile.NewProjectile(null!, 0f, 0f, -1f, 0f, 2, 3, 0f);
    }
    private class SelectionVirtualBase : ModProjectile
    {
        public override void AI() => Step();
        public virtual void Step() { Projectile.ai[0] = 41f; }
    }
    private sealed class SelectionBaseCallingHoldout : SelectionVirtualBase
    {
        public override void Step() { base.Step(); Projectile.ai[1] = 43f; }
    }
    private sealed class SelectionHiddenHoldout : SelectionVirtualBase
    {
        public new void Step() { Projectile.ai[1] = 47f; }
    }
    private sealed class SelectionUnknownHoldout : SelectionAbstractHoldout
    {
        public SelectionAbstractHoldout Other = null!;
        public override void AI() => Other.HoldoutStep();
        public override void HoldoutStep() { Projectile.ai[1] = 53f; }
    }
    private sealed class SelectionMixedCallerProjectile : ModProjectile
    {
        public override void AI() => InstanceStep(1);
        private void InstanceStep(int type) => StaticStep(type);
        private static void StaticStep(int type) => Terraria.Projectile.NewProjectile(null!, 0f, 0f, 1f, 0f, type, 2, 0f);
    }

    private static void ParentSourceGraphCarriesCallerInvocationAcrossStaticHelpers()
    {
        JsonObject graph = SelectionCaptureProjectile(typeof(SelectionMixedCallerProjectile));
        Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge =>
            edge["kind"]?.GetValue<string>() == "conditional_projectile_spawn_candidate"
            && (edge["context"] is JsonValue literal && literal.TryGetValue<int>(out int id) && id == 1
                || edge["context"] is JsonObject context && context["projectileId"]?.GetValue<int>() == 1)),
            "literal root argument reaches the spawn across an instance-to-static receiver transition");
        Equal(false, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge =>
            edge["kind"]?.GetValue<string>() == "projectile_spawn" && edge["unresolved"]?.GetValue<string>().StartsWith("identity_requires_helper", StringComparison.Ordinal) == true),
            "a proven literal does not become an unknown runtime helper argument");
        AssertSelectionReferences(graph);
    }

    private sealed class SelectionRefLocalProjectile : ModProjectile
    {
        private static void Fill(ref float length) { length = 71f; }
        public override void AI()
        {
            float length = 0f;
            Fill(ref length);
            Projectile.localAI[1] = length;
        }
    }

    private static void ParentSourceGraphGroupsRefLocalOutputs()
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        object body = graphType.GetMethod("Read", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph,
            new object[] { typeof(SelectionRefLocalProjectile).GetMethod(nameof(SelectionRefLocalProjectile.AI))! })!;
        var statements = (System.Collections.IList)body.GetType().GetField("Statements", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(body)!;
        Type valueType = body.GetType().GetNestedType("Value", BindingFlags.NonPublic)!;
        FieldInfo op = valueType.GetField("Op", BindingFlags.Instance | BindingFlags.NonPublic)!;
        FieldInfo operand = valueType.GetField("Operand", BindingFlags.Instance | BindingFlags.NonPublic)!;
        object[] roots = statements.Cast<object>().Where(value => (string)op.GetValue(value)! != "stloc").ToArray();
        Array selected = Array.CreateInstance(valueType, roots.Length);
        for (int index = 0; index < roots.Length; index++) selected.SetValue(roots[index], index);
        var groups = (Array)graphType.GetMethod("StatementGroups", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { body, selected })!;
        bool bundled = groups.Cast<Array>().Any(group => group.Cast<object>().Any(value => operand.GetValue(value) is MethodInfo method && method.Name == "Fill")
            && group.Cast<object>().Any(value => ((string)op.GetValue(value)!).StartsWith("stelem", StringComparison.Ordinal)));
        Equal(true, bundled, "ref-local output store is selected atomically with its potential writer, not assigned a guessed value");
        JsonObject exported = SelectionCaptureProjectile(typeof(SelectionRefLocalProjectile));
        Equal(true, exported.ToJsonString().Contains("address_exposed_local", StringComparison.Ordinal),
            "source keeps the by-ref local value explicitly opaque");
    }

    private sealed class SelectionPaletteProjectile : ModProjectile
    {
        private static int Palette(int[] colors) => colors[0];
        public override void AI()
        {
            Palette(new[] { 3, 5, 7 });
            Projectile.velocity.X *= 0.5f;
        }
    }

    private static void ParentSourceGraphActorStatePrecedesCosmeticArrays()
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        object body = graphType.GetMethod("Read", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph,
            new object[] { typeof(SelectionPaletteProjectile).GetMethod(nameof(SelectionPaletteProjectile.AI))! })!;
        var statements = (System.Collections.IList)body.GetType().GetField("Statements", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(body)!;
        Type valueType = body.GetType().GetNestedType("Value", BindingFlags.NonPublic)!;
        FieldInfo op = valueType.GetField("Op", BindingFlags.Instance | BindingFlags.NonPublic)!;
        FieldInfo operand = valueType.GetField("Operand", BindingFlags.Instance | BindingFlags.NonPublic)!;
        object[] roots = statements.Cast<object>().Where(value => (string)op.GetValue(value)! != "stloc").ToArray();
        Array selected = Array.CreateInstance(valueType, roots.Length);
        for (int index = 0; index < roots.Length; index++) selected.SetValue(roots[index], index);
        var groups = (Array)graphType.GetMethod("StatementGroups", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { body, selected })!;
        object[] first = ((Array)groups.GetValue(0)!).Cast<object>().ToArray();
        Equal(true, first.Any(value => operand.GetValue(value) is FieldInfo field && field.Name == "X"
            || ((string)op.GetValue(value)!).StartsWith("stind", StringComparison.Ordinal)),
            "nested actor velocity component write precedes an unrelated array-taking palette helper");
        Equal(false, first.Any(value => operand.GetValue(value) is MethodInfo method && method.Name == "Palette"),
            "an array parameter alone is not evidence of gameplay geometry");
    }

    private sealed class SelectionGeometryProjectile : ModProjectile
    {
        private static float Shade(float value) => value + 0.25f;
        public override void AI()
        {
            Shade(0f);
            Shade(1f);
            Shade(2f);
            Shade(3f);
            Shade(4f);
            Shade(5f);
            Shade(6f);
            Shade(7f);
            Shade(8f);
            Shade(9f);
            Shade(10f);
            Shade(11f);
            Shade(12f);
            Shade(13f);
            Shade(14f);
            Shade(15f);
            Shade(16f);
            Shade(17f);
            Shade(18f);
            Shade(19f);
            Shade(20f);
            Shade(21f);
            Shade(22f);
            Shade(23f);
            Shade(24f);
            Shade(25f);
            Shade(26f);
            Shade(27f);
            Shade(28f);
            Shade(29f);
            Shade(30f);
            Shade(31f);
            Shade(32f);
            Shade(33f);
            Shade(34f);
            Shade(35f);
            Shade(36f);
            Shade(37f);
            Shade(38f);
            Shade(39f);
            Shade(40f);
            Shade(41f);
            Shade(42f);
            Shade(43f);
            Shade(44f);
            Shade(45f);
            Shade(46f);
            Shade(47f);
            Shade(48f);
            Shade(49f);
            Shade(50f);
            Shade(51f);
            Shade(52f);
            Shade(53f);
            Shade(54f);
            Shade(55f);
            Shade(56f);
            Shade(57f);
            Shade(58f);
            Shade(59f);
            Shade(60f);
            Shade(61f);
            Shade(62f);
            Shade(63f);
            Shade(64f);
            Shade(65f);
            Shade(66f);
            Shade(67f);
            Shade(68f);
            Shade(69f);
            Shade(70f);
            Shade(71f);
            Shade(72f);
            Shade(73f);
            Shade(74f);
            Shade(75f);
            Shade(76f);
            Shade(77f);
            Shade(78f);
            Shade(79f);
            var samples = new float[2];
            Collision.LaserScan(Projectile.Center, Projectile.velocity, Projectile.width, 2000f, samples);
            Projectile.localAI[1] = (samples[0] + samples[1]) / 2f;
        }
        public override bool? Colliding(Rectangle projHitbox, Rectangle targetHitbox)
        {
            float hit = 0f;
            return Collision.CheckAABBvLineCollision(new Vector2(targetHitbox.X, targetHitbox.Y),
                new Vector2(targetHitbox.Width, targetHitbox.Height), Projectile.Center,
                Projectile.Center + Projectile.velocity * Projectile.localAI[1], 22f * Projectile.scale, ref hit);
        }
    }

    private static JsonObject SelectionCaptureProjectile(params Type[] types)
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        graphType.GetField("rosterRead", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(graph, true);
        object events = graphType.GetField("ProjectileEvents", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        MethodInfo hooks = graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!;
        foreach (Type type in types) hooks.Invoke(graph, new object[] { type, typeof(ModProjectile), events, "captured_fixture_projectile", "event_signature" });
        return (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
    }

    private static void ParentSourceGraphResolvesCapturedVirtualReceiver()
    {
        JsonObject graph = SelectionCaptureProjectile(typeof(SelectionConcreteHoldoutA));
        Equal(true, SelectionNode(graph, "SelectionConcreteHoldoutA.HoldoutStep(")?["values"] is JsonObject,
            "inherited AI resolves the abstract virtual slot on the captured concrete receiver");
        Equal(true, SelectionNode(graph, "SelectionConcreteHoldoutA.EmitA(")?["values"] is JsonObject,
            "the resolved override retains its child-spawn helper");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphSeparatesReceiverContexts()
    {
        JsonObject graph = SelectionCaptureProjectile(typeof(SelectionConcreteHoldoutA), typeof(SelectionConcreteHoldoutB));
        JsonObject[] entries = graph["nodes"]!.AsArray().OfType<JsonObject>().Where(row =>
            graph["members"]![row["method"]!.GetValue<int>()]!["name"]!.GetValue<string>().Contains("SelectionAbstractHoldout.AI(", StringComparison.Ordinal)).ToArray();
        Equal(2, entries.Length, "two concrete receiver contexts do not share one ambiguous inherited-AI node");
        var destinations = new HashSet<string>();
        foreach (var entry in entries)
        {
            JsonObject[] links = graph["edges"]!.AsArray().OfType<JsonObject>().Where(edge => edge["from"]?.GetValue<int>() == entry["id"]!.GetValue<int>()
                && edge["kind"]?.GetValue<string>() == "captured_receiver_virtual_helper_candidate").ToArray();
            Equal(1, links.Length, "each concrete invocation has exactly its own virtual target");
            int id = links[0]["to"]!.GetValue<int>();
            destinations.Add(graph["members"]![graph["nodes"]![id]!["method"]!.GetValue<int>()]!["name"]!.GetValue<string>());
        }
        Equal(2, destinations.Count, "distinct captured types reach distinct implementations");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphKeepsVirtualDispatchBoundaries()
    {
        JsonObject baseCall = SelectionCaptureProjectile(typeof(SelectionBaseCallingHoldout));
        JsonObject derived = SelectionNode(baseCall, "SelectionBaseCallingHoldout.Step(")!;
        JsonObject parent = SelectionNode(baseCall, "SelectionVirtualBase.Step(")!;
        Equal(true, derived?["values"] is JsonObject && parent?["values"] is JsonObject, "explicit base.call retains the base implementation");
        Equal(true, baseCall["edges"]!.AsArray().OfType<JsonObject>().Any(edge => edge["from"]?.GetValue<int>() == derived!["id"]!.GetValue<int>()
            && edge["to"]?.GetValue<int>() == parent!["id"]!.GetValue<int>() && edge["kind"]?.GetValue<string>() == "helper_source"), "direct base.call is not virtual redispatch");
        JsonObject hidden = SelectionCaptureProjectile(typeof(SelectionHiddenHoldout));
        Equal(true, SelectionNode(hidden, "SelectionVirtualBase.Step(")?["values"] is JsonObject, "hidden newslot method does not replace a different virtual slot");
        Equal(true, SelectionNode(hidden, "SelectionHiddenHoldout.Step(") is null, "hidden method is not a candidate for the base virtual slot");
        JsonObject unknown = SelectionCaptureProjectile(typeof(SelectionUnknownHoldout));
        Equal(true, SelectionNode(unknown, "SelectionUnknownHoldout.HoldoutStep(") is null, "an unrelated receiver must not borrow the root concrete type");
        Equal(true, unknown["edges"]!.AsArray().OfType<JsonObject>().Any(edge => edge["unresolved"]?.GetValue<string>().Contains("virtual", StringComparison.Ordinal) == true),
            "abstract call on an unknown receiver is explicit unresolved evidence");
        AssertSelectionReferences(baseCall); AssertSelectionReferences(hidden); AssertSelectionReferences(unknown);
    }

    private static void ParentSourceGraphRetainsGeometryBeforeUtilityInventory()
    {
        JsonObject graph = SelectionCaptureProjectile(typeof(SelectionGeometryProjectile));
        JsonObject? ai = SelectionNode(graph, "SelectionGeometryProjectile.AI(");
        Equal(true, ai?["values"] is JsonObject, "geometry AI has source evidence");
        string[] members = ai!["values"]!.AsObject().Select(value => value.Value?[1]).OfType<JsonObject>()
            .Where(value => value["member"] is JsonNode).Select(value => graph["members"]![value["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()).ToArray();
        Equal(true, members.Any(name => name.Contains(".LaserScan(", StringComparison.Ordinal)), "an array-writing external call survives unrelated helper crowding");
        Equal(true, ai["values"]!.AsObject().Any(value => value.Value?[0]?.GetValue<string>().StartsWith("stelem", StringComparison.Ordinal) == true),
            "the geometry array write is retained, not only the scan name");
        JsonObject? collision = SelectionNode(graph, "SelectionGeometryProjectile.Colliding(");
        Equal(true, collision?["values"] is JsonObject, "the return-valued collision root keeps a body");
        Equal(true, graph["members"]!.AsArray().OfType<JsonObject>().Any(row => row["name"]!.GetValue<string>().Contains(".CheckAABBvLineCollision(", StringComparison.Ordinal)),
            "native line-collision evidence is present");
        AssertSelectionReferences(graph);
    }
}
