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
    private sealed class GraphDamageItem : ModItem
    {
        public override void ModifyWeaponDamage(Player player, ref StatModifier damage)
        { GraphSourceExecutions++; if (player.wet) damage *= 1.5f; }
        public override void ModifyWeaponKnockback(Player player, ref StatModifier knockback)
        { GraphSourceExecutions++; knockback += 0.5f; }
    }
    private sealed class GraphDamageGlobal : GlobalItem
    {
        public override void ModifyWeaponDamage(Item item, Player player, ref StatModifier damage)
        { GraphSourceExecutions++; if (item.damage > 10) damage += 0.25f; }
        public override void ModifyWeaponKnockback(Item item, Player player, ref StatModifier knockback)
        { GraphSourceExecutions++; knockback *= 2f; }
    }
    private sealed class GraphDamagePlayer : ModPlayer
    {
        public override void ModifyWeaponDamage(Item item, ref StatModifier damage)
        { GraphSourceExecutions++; if (item.damage > 10) damage += 0.75f; }
        public override void ModifyWeaponKnockback(Item item, ref StatModifier knockback)
        { GraphSourceExecutions++; knockback *= 3f; }
    }

    private static void ParentSourceGraphKeepsWeaponModifiers()
    {
        GraphSourceExecutions = 0;
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        Type inputType = typeof(GeneratorClient).GetNestedType("SourceGraphItem", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        var roster = (IList)graphType.GetField("consumers", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!;
        roster.Add((typeof(GraphDamagePlayer), typeof(ModPlayer)));
        // Fixture only the captured owner roster. Discover actual event roots,
        // IL bodies, branches and members through the production Item entrypoint.
        object input = Activator.CreateInstance(inputType, new object?[] {
            typeof(GraphDamageItem), new[] { typeof(GraphDamageGlobal) }, false,
            0, 0, null, Array.Empty<Type>(), false })!;
        graphType.GetMethod("Item", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new[] { input });
        var result = (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
        foreach (var (type, owner) in new[] { (typeof(GraphDamageItem), "parent_ModItem"),
            (typeof(GraphDamageGlobal), "attached_GlobalItem"), (typeof(GraphDamagePlayer), "registered_ModPlayer_candidate") })
        foreach (string hook in new[] { "ModifyWeaponDamage", "ModifyWeaponKnockback" })
        {
            var roots = result["roots"]!.AsArray().OfType<JsonObject>()
                .Where(row => row["owner"]!.GetValue<string>() == owner && row["event"]!.GetValue<string>() == hook).ToArray();
            Equal(1, roots.Length, "exact weapon modifier root count: " + type.Name + "." + hook);
            var node = result["nodes"]!.AsArray().OfType<JsonObject>()
                .Single(row => row["id"]!.ToJsonString() == roots[0]["node"]!.ToJsonString());
            string method = result["members"]![node["method"]!.GetValue<int>()]!["name"]!.GetValue<string>();
            Equal(true, method.Contains(type.Name + "." + hook + "(", StringComparison.Ordinal), "root resolves to exact source owner");
            Equal(true, node["values"] is JsonObject values && values.Count > 0, "modifier source expressions retained");
            Equal(true, node["sha256"] is JsonValue, "modifier body certificate retained");
        }
        Equal(0, GraphSourceExecutions, "weapon modifier discovery never executes hooks");
    }
}
