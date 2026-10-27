using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int GraphSourceExecutions;
    private sealed class GraphItem : ModItem
    {
        public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
        {
            GraphSourceExecutions++;
            SpawnFromHelper(source, ProjectileID.WoodenArrowFriendly, position);
            return false;
        }
        private static void SpawnFromHelper(IEntitySource source, int type, Vector2 position)
        {
            Projectile.NewProjectile(source, position, Vector2.Zero, type, 17, 0);
        }
        public override void OnHitNPC(Player player, NPC target, NPC.HitInfo hit, int damageDone)
        {
            int buff = hit.Crit ? BuffID.Poisoned : BuffID.Ichor;
            int duration = Frames(damageDone);
            target.AddBuff(buff, duration);
            GraphNpc(target).Active = true;
        }
        private static int Frames(int seconds) => seconds * 60;
        private static GraphConsumer GraphNpc(NPC npc) => npc.GetGlobalNPC<GraphConsumer>();
        public override void OnHitPvp(Player player, Player target, Player.HurtInfo hurtInfo) => target.AddBuff(BuffID.OnFire, 77);
        public override bool? UseItem(Player player) { GraphSourceExecutions++; player.AddBuff(BuffID.Ironskin, 88); return true; }
        public override void UpdateAccessory(Player player, bool hideVisual)
        {
            player.statDefense += 5;
            player.GetDamage(DamageClass.Magic) *= 1.25f;
        }
        public override bool IsArmorSet(Item head, Item body, Item legs) => body.type == ItemID.IronChainmail && legs.type == ItemID.IronGreaves;
        public override void UpdateArmorSet(Player player) { if (player.wet) player.lifeRegen += 4; }
    }
    private sealed class GraphChild : ModProjectile
    {
        public override void AI() { if (Projectile.ai[0] > 0) Projectile.velocity.Y += 0.1f; }
        public override void OnKill(int timeLeft)
        {
            GraphSourceExecutions++;
            Projectile.NewProjectile(Projectile.GetSource_Death(), Projectile.Center, Vector2.Zero, ProjectileID.WoodenArrowFriendly, 7, 0);
        }
        public override void OnHitPlayer(Player target, Player.HurtInfo info) => target.AddBuff(BuffID.OnFire, (int)Projectile.ai[1]);
    }
    private sealed class GraphConsumer : GlobalNPC
    {
        public bool Active;
        public override void UpdateLifeRegen(NPC npc, ref int damage)
        {
            if (Active && npc.wet) { npc.lifeRegen -= 24; damage = 3; }
        }
    }
    private sealed class GraphTryItem : ModItem
    {
        public override bool? UseItem(Player player)
        {
            try { GraphSourceExecutions++; return true; }
            finally { GraphSourceExecutions++; }
        }
    }

    private static void ParentSourceGraphKeepsReachabilityConditionsAndEventOwnership()
    {
        GraphSourceExecutions = 0;
        int childId = ProjectileID.WoodenArrowFriendly;
        bool hadSample = ContentSamples.ProjectilesByType.TryGetValue(childId, out Projectile? oldSample);
        try
        {
            var child = new Projectile { type = childId };
            typeof(Projectile).GetProperty(nameof(Projectile.ModProjectile))!.SetValue(child, new GraphChild());
            ContentSamples.ProjectilesByType[childId] = child;
            var item = new Item { type = ItemID.Wood, stack = 1, useAmmo = 0, shoot = 0, createTile = -1 };
            typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(item, new GraphItem());
            Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
            object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
            // A source-roster fixture, not a mocked analyzer or gameplay executor.
            var roster = (IList)graphType.GetField("consumers", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!;
            roster.Add((typeof(GraphConsumer), typeof(GlobalNPC)));
            graphType.GetMethod("Item", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new object[] { item });
            var result = (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
            string? firstExport = Environment.GetEnvironmentVariable("INFINI_PARENT_GRAPH_PACKET");
            if (!string.IsNullOrEmpty(firstExport)) File.WriteAllText(firstExport, new JsonObject { ["name"] = "source fixture", ["parentSourceGraph"] = result.DeepClone() }.ToJsonString());
            Equal(0, GraphSourceExecutions, "source discovery never executes shoot/use/kill or helper bodies");
            var nodes = result["nodes"]!.AsArray().OfType<JsonObject>().ToArray();
            string json = result.ToJsonString();
            foreach (string name in new[] { ".Shoot(", ".SpawnFromHelper(", ".Frames(", ".OnHitPvp(", ".UpdateAccessory(", ".IsArmorSet(", ".UpdateArmorSet(", ".OnKill(", ".OnHitPlayer(", ".UpdateLifeRegen(" })
                Equal(true, nodes.Any(n => result["members"]![n["method"]!.GetValue<int>()]!["name"]!.GetValue<string>().Contains(name, StringComparison.Ordinal)), "reachable source delivered: " + name);
            JsonObject EventGraph(params string[] events)
            {
                object focused = Activator.CreateInstance(graphType, nonPublic: true)!;
                ((IList)graphType.GetField("consumers", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(focused)!).Add((typeof(GraphConsumer), typeof(GlobalNPC)));
                graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(focused, new object[]
                    { typeof(GraphItem), typeof(ModItem), new System.Collections.Generic.HashSet<string>(events, StringComparer.Ordinal), "parent_ModItem", "event_signature" });
                return (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(focused, null)!;
            }
            // The combined graph deliberately tests the finite transport bound.
            // Each source path also gets its own full semantic assertion, so an
            // omitted node cannot pass as inspected behavior.
            var combat = EventGraph("OnHitNPC", "OnHitPvp");
            var shooting = EventGraph("Shoot");
            var equipment = EventGraph("UpdateAccessory", "IsArmorSet", "UpdateArmorSet");
            Equal(true, combat["members"]!.AsArray().OfType<JsonObject>().Any(m => m["name"]!.GetValue<string>().Contains("Terraria.NPC+HitInfo.Crit", StringComparison.Ordinal)), "conditional buff identity retains typed crit source");
            Equal(true, combat["members"]!.AsArray().OfType<JsonObject>().Any(m => m["name"]!.GetValue<string>().EndsWith(".wet", StringComparison.Ordinal)), "consumer conjunction retains target condition");
            Equal(true, equipment.ToJsonString().Contains("Terraria.Player.statDefense", StringComparison.Ordinal), "typed equipment contribution survives");
            Equal(true, equipment.ToJsonString().Contains("op_Multiply", StringComparison.Ordinal), "ref StatModifier operator remains literal source");
            Equal(true, shooting["edges"]!.AsArray().OfType<JsonObject>().Any(e => e["kind"]?.GetValue<string>() == "conditional_projectile_spawn_candidate" && e["to"] is not null), "helper argument resolves actual registered projectile sample");
            Equal(true, shooting["edges"]!.AsArray().OfType<JsonObject>().Any(e => e["unresolved"]?.GetValue<string>() == "already_visited_projectile_identity"), "cyclic child graph deduplicates identities");
            foreach (JsonObject node in nodes.Where(n => n["values"] is JsonObject))
            {
                var values = node["values"]!.AsObject();
                foreach (var value in values)
                    foreach (JsonNode? input in value.Value![2]!.AsArray())
                        Equal(true, values.ContainsKey(input!.GetValue<string>()), "every source data reference resolves within its node");
            }
            var ids = nodes.Select(n => n["id"]!.GetValue<int>()).ToHashSet();
            foreach (JsonObject edge in result["edges"]!.AsArray().OfType<JsonObject>())
                foreach (string end in new[] { "from", "to" })
                    if (edge[end] is JsonNode id) Equal(true, ids.Contains(id.GetValue<int>()), "graph bounds never leave dangling method references");
            ModBuffSourceExecuted = 0;
            object buffGraph = Activator.CreateInstance(graphType, nonPublic: true)!;
            graphType.GetMethod("Hooks", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(buffGraph, new object[]
                { typeof(SourceDataBuff), typeof(ModBuff), new System.Collections.Generic.HashSet<string>(new[] { "SetStaticDefaults", "Update" }, StringComparer.Ordinal), "requested_ModBuff", "npc" });
            var linked = (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(buffGraph, null)!;
            Equal(true, linked["members"]!.AsArray().OfType<JsonObject>().Any(m => m["name"]!.GetValue<string>().EndsWith(".Strength", StringComparison.Ordinal)), "buff registration source follows the exact data initializer field");
            Equal(0, ModBuffSourceExecuted, "data graph never initializes mod statics or calls constructors");
            string? export = Environment.GetEnvironmentVariable("INFINI_PARENT_GRAPH_PACKET");
            if (!string.IsNullOrEmpty(export)) File.WriteAllText(export, new JsonObject { ["name"] = "source fixture", ["parentSourceGraph"] = result.DeepClone() }.ToJsonString());

            typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(item, new GraphTryItem());
            var unsupported = GeneratorClient.CaptureParentSourceGraph(item);
            Equal(true, unsupported.ToJsonString().Contains("unsupported_method_body_or_source_bound", StringComparison.Ordinal), "exception-bearing body is refused explicitly");
            Equal(0, GraphSourceExecutions, "unsupported source path also never executes gameplay");
        }
        finally
        {
            if (hadSample) ContentSamples.ProjectilesByType[childId] = oldSample!;
            else ContentSamples.ProjectilesByType.Remove(childId);
        }
    }
    private static void ParentSourceGraphKeepsConditionalNativeBuffConsumers()
    {
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        foreach (var pair in new[] { (BuffID.Oiled, "npc", ".oiled"), (BuffID.Daybreak, "npc", ".daybreak"),
                                     (BuffID.Sharpened, "player", "ArmorPenetration") })
        {
            object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
            graphType.GetMethod("Buff", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, new object?[] { pair.Item1, pair.Item2, null, null });
            var result = (JsonObject)graphType.GetMethod("Finish", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(graph, null)!;
            string? path = Environment.GetEnvironmentVariable("INFINI_NATIVE_GRAPH_DIR");
            if (!string.IsNullOrEmpty(path)) { Directory.CreateDirectory(path); File.WriteAllText(Path.Combine(path, pair.Item1 + ".json"), result.ToJsonString()); }
            var members = result["members"]!.AsArray().OfType<JsonObject>().Select(m => m["name"]!.GetValue<string>()).ToArray();
            Equal(true, members.Any(m => m.Contains(pair.Item3, StringComparison.OrdinalIgnoreCase)), "previously unsupported native buff source reaches graph: " + pair.Item3);
            Equal(true, result["nodes"]!.AsArray().OfType<JsonObject>().Any(n => n["values"] is JsonObject values && values.Count > 0 && n["sha256"] is JsonValue), "native slices keep source certificate and source definitions");
            if (pair.Item2 == "npc")
                Equal(true, members.Any(m => m.EndsWith(".lifeRegen", StringComparison.Ordinal)), "conditional native regen consumers are linked without a flat DPS claim");
        }
    }

    private static void ParentSourceGraphFollowsNativeProjectileWindows()
    {
        int id = ProjectileID.ClusterGrenadeI;
        bool existed = ContentSamples.ProjectilesByType.TryGetValue(id, out Projectile? original);
        try
        {
            var projectile = new Projectile();
            projectile.SetDefaults(id); // Fixture oracle only; capture never runs defaults.
            ContentSamples.ProjectilesByType[id] = projectile;
            var item = new Item { type = ItemID.Wood, stack = 1, shoot = id, createTile = -1 };
            JsonObject graph = GeneratorClient.CaptureParentSourceGraph(item);
            string? path = Environment.GetEnvironmentVariable("INFINI_NATIVE_GRAPH_DIR");
            if (!string.IsNullOrEmpty(path)) File.WriteAllText(Path.Combine(path, "projectile.json"), graph.ToJsonString());
            Equal(true, graph["edges"]!.AsArray().OfType<JsonObject>().Any(e => e["kind"]?.GetValue<string>() == "certified_native_projectile_source_windows" && e["to"] is not null), "native type/style dispatch yields certified conditional source windows");
            Equal(true, graph["members"]!.AsArray().OfType<JsonObject>().Any(m => m["name"]!.GetValue<string>().StartsWith("Terraria.Projectile.NewProjectile(", StringComparison.Ordinal)), "native child spawn call is retained with source arguments");
        }
        finally
        {
            if (existed) ContentSamples.ProjectilesByType[id] = original!;
            else ContentSamples.ProjectilesByType.Remove(id);
        }
    }

}
