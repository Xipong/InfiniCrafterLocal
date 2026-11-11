using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private abstract class ConsumerAbstractPlayer : ModPlayer
    {
        public ConsumerAbstractPlayer Other = null!;
        public abstract bool HasState();
        public bool ReadState() => HasState();
        public override void PostUpdateEquips()
        {
            // Visit the same helper first with an unknown receiver, then this.
            Other.ReadState();
            if (ReadState()) Player.statDefense += 61;
        }
    }
    private sealed class ConsumerConcretePlayer : ConsumerAbstractPlayer
    {
        public bool Active;
        public override bool HasState() => Active;
    }
    private abstract class ConsumerAbstractNpc : GlobalNPC
    {
        public abstract bool HasState();
        public override void UpdateLifeRegen(NPC npc, ref int damage)
        {
            if (HasState()) npc.lifeRegen -= 67;
        }
    }
    private sealed class ConsumerConcreteNpc : ConsumerAbstractNpc
    {
        public bool Active;
        public override bool HasState() => Active;
    }
    private sealed class ConsumerInheritedItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            player.GetModPlayer<ConsumerConcretePlayer>().Active = true;
            return true;
        }
        public override void OnHitNPC(Player player, NPC target, NPC.HitInfo hit, int damageDone)
            => target.GetGlobalNPC<ConsumerConcreteNpc>().Active = true;
    }
    private sealed class ConsumerForeignPlayer : ConsumerAbstractPlayer
    {
        public bool Active;
        public override bool HasState() => Active;
        public override void PostUpdateEquips()
        {
            if (Other.ReadState()) Player.statDefense += 71;
        }
    }
    private sealed class ConsumerForeignItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            player.GetModPlayer<ConsumerForeignPlayer>().Active = true;
            return true;
        }
    }
    private class ConsumerVirtualPlayer : ModPlayer
    {
        public bool Active;
        public virtual bool HasState() => false;
    }
    private sealed class ConsumerBaseCallingPlayer : ConsumerVirtualPlayer
    {
        public override bool HasState() => Active;
        public override void PostUpdateEquips()
        {
            if (base.HasState()) Player.statDefense += 73;
        }
    }
    private sealed class ConsumerBaseCallingItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            player.GetModPlayer<ConsumerBaseCallingPlayer>().Active = true;
            return true;
        }
    }
    private sealed class ConsumerForeignDeclarationPlayer : ModPlayer
    {
        public bool Active;
        public override string ToString() => Active ? "active" : "inactive";
        public override void PostUpdateEquips()
        {
            if (((object)this).ToString() == "active") Player.statDefense += 79;
        }
    }
    private sealed class ConsumerForeignDeclarationItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            player.GetModPlayer<ConsumerForeignDeclarationPlayer>().Active = true;
            return true;
        }
    }

    private static void ParentSourceGraphDiscoversInheritedFieldConsumers()
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object source = Activator.CreateInstance(graphType, nonPublic: true)!;
        graphType.GetField("rosterRead", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(source, true);
        var consumers = (IList)graphType.GetField("consumers", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(source)!;
        consumers.Add((typeof(ConsumerConcretePlayer), typeof(ModPlayer)));
        consumers.Add((typeof(ConsumerConcreteNpc), typeof(GlobalNPC)));
        object events = graphType.GetField("ItemEvents", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(source, new object[]
            { typeof(ConsumerInheritedItem), typeof(ModItem), events, "parent_ModItem", "event_signature" });
        var graph = (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(source, null)!;
        foreach (var (hook, helper, field) in new[]
        {
            ("ConsumerAbstractPlayer.PostUpdateEquips(", "ConsumerConcretePlayer.HasState(", ".statDefense"),
            ("ConsumerAbstractNpc.UpdateLifeRegen(", "ConsumerConcreteNpc.HasState(", ".lifeRegen"),
        })
        {
            JsonObject? consumer = SelectionNode(graph, hook);
            Equal(true, consumer?["values"] is JsonObject, "inherited field consumer is discovered: " + hook);
            Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(edge => edge["kind"]?.GetValue<string>() == "registered_field_consumer_candidate"
                && edge["to"]?.GetValue<int>() == consumer!["id"]!.GetValue<int>()), "consumer is linked to watched state: " + hook);
            Equal(true, SelectionNode(graph, helper)?["values"] is JsonObject, "captured concrete state reader is retained: " + helper);
            Equal(true, consumer!["values"]!.AsObject().Select(value => value.Value?[1]).OfType<JsonObject>()
                .Where(value => value["member"] is JsonValue).Any(value => graph["members"]![value["member"]!.GetValue<int>()]!["name"]!.GetValue<string>()
                    .EndsWith(field, StringComparison.Ordinal)), "focused consumer retains the effect guarded by virtual state: " + field);
        }
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphConsumerKeepsUnknownReceiver()
    {
        JsonObject graph = SelectionCapture(typeof(ConsumerForeignItem), consumer: typeof(ConsumerForeignPlayer));
        Equal(true, SelectionNode(graph, "ConsumerForeignItem.UseItem(")?["values"] is JsonObject, "foreign-receiver fixture has its actual state-writing root");
        Equal(true, SelectionNode(graph, "ConsumerForeignPlayer.PostUpdateEquips(") is null, "unknown helper receiver does not borrow the registered concrete type");
        Equal(true, SelectionNode(graph, "ConsumerForeignPlayer.HasState(") is null, "foreign abstract helper does not admit the captured override");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphConsumerKeepsDirectBaseCall()
    {
        JsonObject graph = SelectionCapture(typeof(ConsumerBaseCallingItem), consumer: typeof(ConsumerBaseCallingPlayer));
        Equal(true, SelectionNode(graph, "ConsumerBaseCallingItem.UseItem(")?["values"] is JsonObject, "base-call fixture has its actual state-writing root");
        Equal(true, SelectionNode(graph, "ConsumerBaseCallingPlayer.PostUpdateEquips(") is null, "direct base call cannot be redispatched into the state-reading override");
        Equal(true, SelectionNode(graph, "ConsumerBaseCallingPlayer.HasState(") is null, "unreached override is not added as consumer evidence");
        AssertSelectionReferences(graph);
    }

    private static void ParentSourceGraphConsumerKeepsDeclarationAssemblyBoundary()
    {
        JsonObject graph = SelectionCapture(typeof(ConsumerForeignDeclarationItem), consumer: typeof(ConsumerForeignDeclarationPlayer));
        Equal(true, SelectionNode(graph, "ConsumerForeignDeclarationItem.UseItem(")?["values"] is JsonObject, "foreign-declaration fixture has its actual state-writing root");
        Equal(true, SelectionNode(graph, "ConsumerForeignDeclarationPlayer.PostUpdateEquips(") is null,
            "a foreign assembly declaration cannot cross the source boundary through a local override");
        Equal(true, SelectionNode(graph, "ConsumerForeignDeclarationPlayer.ToString(") is null,
            "unfollowed foreign declaration does not introduce local override evidence");
        AssertSelectionReferences(graph);
    }
}
