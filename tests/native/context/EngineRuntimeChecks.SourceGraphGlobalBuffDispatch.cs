using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int GlobalBuffSourceExecutions;

    private sealed class CapturedGlobalBuffItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            GlobalBuffSourceExecutions++;
            player.AddBuff(BuffID.Ironskin, 120);
            return true;
        }
    }
    private abstract class CapturedGlobalBuffBase : GlobalBuff
    {
        public CapturedGlobalBuffBase Other = null!;
        protected abstract bool Allowed(Player player);
        public bool ReadAllowed(Player player) => Allowed(player);
        protected abstract int Amount();
        public override void Update(int type, Player player, ref int buffIndex)
        {
            GlobalBuffSourceExecutions++;
            if (Allowed(player)) player.statDefense += Amount();
        }
        public override bool ReApply(int type, Player player, int time, int buffIndex)
            => PlayerReApply(player);
        protected abstract bool PlayerReApply(Player player);
    }
    private sealed class CapturedGlobalBuffA : CapturedGlobalBuffBase
    {
        protected override bool Allowed(Player player) => player.wet;
        protected override int Amount() => 83;
        protected override bool PlayerReApply(Player player)
        {
            if (player.wet) player.lifeRegen += 101;
            return false;
        }
    }
    private sealed class CapturedGlobalBuffB : CapturedGlobalBuffBase
    {
        protected override bool Allowed(Player player) => player.lavaWet;
        protected override int Amount() => 89;
        protected override bool PlayerReApply(Player player)
        {
            if (player.lavaWet) player.lifeRegen += 103;
            return false;
        }
    }
    private sealed class ForeignGlobalBuff : CapturedGlobalBuffBase
    {
        protected override bool Allowed(Player player) => player.honeyWet;
        protected override int Amount() => 107;
        protected override bool PlayerReApply(Player player) => false;
        public override void Update(int type, Player player, ref int buffIndex)
        {
            if (OtherAllowed(player)) player.statDefense += 109;
        }
        private bool OtherAllowed(Player player) => Other.ReadAllowed(player);
    }
    private class DirectBaseGlobalBuff : GlobalBuff
    {
        protected virtual void Apply(Player player) => player.lifeRegen += 113;
    }
    private sealed class DirectCallingGlobalBuff : DirectBaseGlobalBuff
    {
        public override void Update(int type, Player player, ref int buffIndex) => base.Apply(player);
        protected override void Apply(Player player) => player.statDefense += 127;
    }

    private static JsonObject CaptureGlobalBuffGraph(params Type[] owners)
    {
        // Supply the main-thread roster snapshot, then exercise the actual Item
        // -> AddBuff -> Buff -> deferred GlobalBuff source-discovery path.
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object source = Activator.CreateInstance(graphType, nonPublic: true)!;
        graphType.GetField("rosterRead", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(source, true);
        var consumers = (IList)graphType.GetField("consumers", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(source)!;
        foreach (Type owner in owners) consumers.Add((owner, typeof(GlobalBuff)));
        object events = graphType.GetField("ItemEvents", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(source, new object[]
            { typeof(CapturedGlobalBuffItem), typeof(ModItem), events, "parent_ModItem", "event_signature" });
        return (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(source, null)!;
    }

    private static string GlobalBuffNodeName(JsonObject graph, JsonObject node)
        => graph["members"]![node["method"]!.GetValue<int>()]!["name"]!.GetValue<string>();

    private static void AssertGlobalBuffSource(JsonObject graph, string name, int amount, string? guard = null)
    {
        JsonObject? node = SelectionNode(graph, name);
        Equal(true, node?["values"] is JsonObject, "captured GlobalBuff helper body is retained: " + name);
        var values = node!["values"]!.AsObject().Select(value => value.Value!).ToArray();
        Equal(true, values.Any(value => value[0]?.GetValue<string>() == "const"
            && value[1] is JsonValue literal && literal.TryGetValue<int>(out int number) && number == amount),
            "captured GlobalBuff helper retains its own literal amount: " + name);
        if (guard is null) return;
        Equal(true, values.Any(value => value[1] is JsonObject operand && operand["member"] is JsonNode member
            && graph["members"]![member.GetValue<int>()]!["name"]!.GetValue<string>().EndsWith(guard, StringComparison.Ordinal)),
            "captured GlobalBuff helper retains its own player condition: " + name);
        Equal(true, node["blocks"]!.AsArray().OfType<JsonArray>().Any(block => block[2] is not null),
            "captured GlobalBuff helper does not flatten its conditional effect: " + name);
    }

    private static void ParentSourceGraphGlobalBuffSeparatesCapturedReceivers()
    {
        GlobalBuffSourceExecutions = 0;
        JsonObject graph = CaptureGlobalBuffGraph(typeof(CapturedGlobalBuffA), typeof(CapturedGlobalBuffB));
        Equal(0, GlobalBuffSourceExecutions, "capturing GlobalBuff source never executes item or buff hooks");
        Equal(true, SelectionNode(graph, "CapturedGlobalBuffItem.UseItem(")?["values"] is JsonObject,
            "the fixture enters through the actual item AddBuff source request");
        foreach (string hook in new[] { "Update", "ReApply" })
        {
            var entries = graph["nodes"]!.AsArray().OfType<JsonObject>().Where(node =>
                GlobalBuffNodeName(graph, node).Contains("CapturedGlobalBuffBase." + hook + "(", StringComparison.Ordinal)).ToArray();
            Equal(2, entries.Length, "two loaded concrete GlobalBuff owners keep separate inherited " + hook + " nodes");
            string[] expectedHelpers = hook == "Update" ? new[] { "Allowed", "Amount" } : new[] { "PlayerReApply" };
            string[] targets = entries.Select(entry =>
            {
                int id = entry["id"]!.GetValue<int>();
                Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge =>
                    edge["kind"]?.GetValue<string>() == "loaded_GlobalBuff_candidate" && edge["to"]?.GetValue<int>() == id),
                    "inherited " + hook + " is reached from the loaded GlobalBuff roster");
                var links = graph["edges"]!.AsArray().OfType<JsonObject>().Where(edge => edge["from"]?.GetValue<int>() == id
                    && edge["kind"]?.GetValue<string>() == "captured_receiver_virtual_helper_candidate").ToArray();
                Equal(expectedHelpers.Length, links.Length, "each inherited " + hook + " reaches only its concrete helper slots");
                var names = links.Select(edge => GlobalBuffNodeName(graph, graph["nodes"]![edge["to"]!.GetValue<int>()]!.AsObject())).ToArray();
                string owner = names[0].Contains("CapturedGlobalBuffA.", StringComparison.Ordinal) ? "CapturedGlobalBuffA" : "CapturedGlobalBuffB";
                foreach (string helper in expectedHelpers)
                    Equal(true, names.Any(name => name.Contains(owner + "." + helper + "(", StringComparison.Ordinal)),
                        "one inherited invocation cannot mix the two concrete GlobalBuff implementations");
                return owner;
            }).ToArray();
            Equal(2, targets.Distinct().Count(), "both concrete GlobalBuff owners remain reachable for " + hook);
        }
        foreach (var (owner, guard) in new[] { ("CapturedGlobalBuffA", ".wet"), ("CapturedGlobalBuffB", ".lavaWet") })
        {
            JsonObject? allowed = SelectionNode(graph, owner + ".Allowed(");
            Equal(true, allowed?["values"] is JsonObject, "the concrete GlobalBuff condition has source evidence");
            Equal(true, allowed!["values"]!.AsObject().Any(value => value.Value?[1] is JsonObject operand
                && operand["member"] is JsonNode member
                && graph["members"]![member.GetValue<int>()]!["name"]!.GetValue<string>().EndsWith(guard, StringComparison.Ordinal)),
                "each GlobalBuff Update retains its own condition instead of borrowing the other owner's guard");
        }
        foreach (JsonObject update in graph["nodes"]!.AsArray().OfType<JsonObject>().Where(node =>
            GlobalBuffNodeName(graph, node).Contains("CapturedGlobalBuffBase.Update(", StringComparison.Ordinal)))
        {
            Equal(true, update["values"]!.AsObject().Any(value => value.Value?[1] is JsonObject operand
                && operand["member"] is JsonNode member
                && graph["members"]![member.GetValue<int>()]!["name"]!.GetValue<string>().EndsWith(".statDefense", StringComparison.Ordinal)),
                "each inherited GlobalBuff Update retains its mechanical field write");
            Equal(true, update["blocks"]!.AsArray().OfType<JsonArray>().Any(block => block[2] is not null),
                "each inherited GlobalBuff Update retains its conditional control flow");
        }
        AssertGlobalBuffSource(graph, "CapturedGlobalBuffA.Amount(", 83);
        AssertGlobalBuffSource(graph, "CapturedGlobalBuffB.Amount(", 89);
        AssertGlobalBuffSource(graph, "CapturedGlobalBuffA.PlayerReApply(", 101, ".wet");
        AssertGlobalBuffSource(graph, "CapturedGlobalBuffB.PlayerReApply(", 103, ".lavaWet");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphGlobalBuffKeepsDispatchBoundaries()
    {
        JsonObject foreign = CaptureGlobalBuffGraph(typeof(ForeignGlobalBuff));
        Equal(true, SelectionNode(foreign, "ForeignGlobalBuff.Update(")?["values"] is JsonObject,
            "the foreign-receiver fixture has a retained loaded GlobalBuff hook");
        Equal(true, SelectionNode(foreign, "ForeignGlobalBuff.Allowed(") is null,
            "a foreign GlobalBuff receiver cannot borrow the captured concrete type");
        Equal(true, foreign["edges"]!.AsArray().OfType<JsonObject>().Any(edge =>
            edge["unresolved"]?.GetValue<string>().Contains("virtual", StringComparison.Ordinal) == true),
            "the foreign receiver's abstract slot remains explicitly unresolved");
        JsonObject direct = CaptureGlobalBuffGraph(typeof(DirectCallingGlobalBuff));
        JsonObject? update = SelectionNode(direct, "DirectCallingGlobalBuff.Update(");
        JsonObject? parent = SelectionNode(direct, "DirectBaseGlobalBuff.Apply(");
        Equal(true, update?["values"] is JsonObject && parent?["values"] is JsonObject,
            "a GlobalBuff explicit base call retains its exact base body");
        Equal(true, SelectionNode(direct, "DirectCallingGlobalBuff.Apply(") is null,
            "a GlobalBuff explicit base call is not virtually redispatched");
        Equal(true, direct["edges"]!.AsArray().OfType<JsonObject>().Any(edge =>
            edge["from"]?.GetValue<int>() == update!["id"]!.GetValue<int>()
            && edge["to"]?.GetValue<int>() == parent!["id"]!.GetValue<int>()
            && edge["kind"]?.GetValue<string>() == "helper_source"),
            "the GlobalBuff base-call edge preserves direct-call semantics");
        AssertGlobalBuffSource(direct, "DirectBaseGlobalBuff.Apply(", 113);
        AssertSelectionReferences(foreign);
        AssertSelectionReferences(direct);
    }
}
