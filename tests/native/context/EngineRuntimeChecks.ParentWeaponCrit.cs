using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int CritSourceExecutions;

    private abstract class CritSourceItemBase : ModItem
    {
        public override void ModifyWeaponCrit(Player player, ref float crit)
        {
            CritSourceExecutions++;
            if (player.wet && player.statLife < player.statLifeMax2) ApplyCritDelta(ref crit);
        }
        private static void ApplyCritDelta(ref float crit) => crit += 23f;
    }
    private sealed class CritSourceItem : CritSourceItemBase { }
    private sealed class CritSourceGlobal : GlobalItem
    {
        public override void ModifyWeaponCrit(Item item, Player player, ref float crit)
        {
            CritSourceExecutions++;
            if (item.damage > 10 && player.wet) crit += 23f;
        }
    }
    private sealed class CritSourcePlayer : ModPlayer
    {
        public override void ModifyWeaponCrit(Item item, ref float crit)
        {
            CritSourceExecutions++;
            if (Player.statLife < Player.statLifeMax2 && item.damage > 10) crit += 23f;
        }
    }

    private static void ParentWeaponCritNativeDispatchIsExplicit()
    {
        MethodBase[] Calls(MethodInfo method) => ((IEnumerable)typeof(GeneratorClient)
            .GetMethod("ReadAmmoIl", BindingFlags.Static | BindingFlags.NonPublic)!
            .Invoke(null, new object[] { method, true, true })!).Cast<object>()
            .Select(row => row.GetType().GetProperty("Arg")!.GetValue(row)).OfType<MethodBase>().ToArray();
        foreach (var (caller, callee, name) in new[] {
            (typeof(Player), typeof(CombinedHooks), "GetWeaponCrit"),
            (typeof(CombinedHooks), typeof(ItemLoader), "ModifyWeaponCrit"),
            (typeof(CombinedHooks), typeof(PlayerLoader), "ModifyWeaponCrit"),
            (typeof(ItemLoader), typeof(ModItem), "ModifyWeaponCrit"),
            (typeof(ItemLoader), typeof(GlobalItem), "ModifyWeaponCrit"),
            (typeof(PlayerLoader), typeof(ModPlayer), "ModifyWeaponCrit"),
        })
        {
            MethodInfo method = caller.GetMethod(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)!;
            Equal(true, Calls(method).Any(target => target.DeclaringType == callee && target.Name == "ModifyWeaponCrit"),
                "native loaded tML dispatch retains " + caller.Name + " -> " + callee.Name);
        }
    }

    private static void ParentModItemCritSourceReachesCapture() => ParentWeaponCritSourceReachesCapture("item");
    private static void ParentGlobalItemCritSourceReachesCapture() => ParentWeaponCritSourceReachesCapture("global");
    private static void ParentModPlayerCritSourceReachesCapture() => ParentWeaponCritSourceReachesCapture("player");

    private static void ParentWeaponCritSourceReachesCapture(string owner)
    {
        using var state = new NativeActorState();
        CritSourceExecutions = 0;
        var cache = (IDictionary)typeof(ModContent).Assembly.GetType("Terraria.ModLoader.ContentCache")!
            .GetField("_cachedContentForAllMods", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        Type[] rosterTypes = { typeof(ModPlayer), typeof(GlobalNPC), typeof(GlobalBuff) };
        var previous = rosterTypes.Select(type => (Type: type, Had: cache.Contains(type), Value: cache[type])).ToArray();
        var globalsField = typeof(Terraria.ModLoader.Core.GlobalTypeLookups<GlobalItem>)
            .GetField("_globalsForType", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? oldGlobals = globalsField.GetValue(null);
        try
        {
            // Install only native owner rosters. The production capture discovers
            // hooks itself; tests never inject an event allowlist or graph root.
            cache[typeof(ModPlayer)] = Array.AsReadOnly(owner == "player" ? new ModPlayer[] { new CritSourcePlayer() } : Array.Empty<ModPlayer>());
            cache[typeof(GlobalNPC)] = Array.AsReadOnly(Array.Empty<GlobalNPC>());
            cache[typeof(GlobalBuff)] = Array.AsReadOnly(Array.Empty<GlobalBuff>());
            var globals = Enumerable.Range(0, ItemLoader.ItemCount).Select(_ => Array.Empty<GlobalItem>()).ToArray();
            if (owner == "global")
            {
                var global = new CritSourceGlobal();
                typeof(GlobalType<GlobalItem>).GetProperty("PerEntityIndex", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)!.SetValue(global, (short)-1);
                globals[ItemID.Wood] = new GlobalItem[] { global };
            }
            globalsField.SetValue(null, globals);
            var item = new Item { type = ItemID.Wood, stack = 1, crit = 4, damage = 17, createTile = -1, createWall = -1 };
            typeof(Item).GetField("_globals", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(item, Array.Empty<GlobalItem>());
            if (owner == "item")
            {
                var host = new CritSourceItem();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, item);
                typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(item, host);
            }
            int attachedCount = 0;
            foreach (var global in item.Globals) attachedCount++;
            Equal(owner == "global" ? 1 : 0, attachedCount, "actual attached GlobalItem enumeration");
            Equal(owner == "player" ? 1 : 0, ModContent.GetContent<ModPlayer>().Count(), "actual registered ModPlayer enumeration");
            // These fixtures are not full installed mod content. Invoke the sole
            // production native-fact capture instead of Prepare, which correctly
            // reconstructs registered defaults and would remove a synthetic host.
            var capture = typeof(GeneratorClient).GetMethod("CaptureParentNativeFacts", BindingFlags.Static | BindingFlags.NonPublic)!;
            object snapshot = capture.Invoke(null, new object?[] { item, null })!;
            var facts = (JsonObject)snapshot.GetType().GetProperty("RuntimeFacts")!.GetValue(snapshot)!;
            JsonObject graph = facts["parentSourceGraph"]!.AsObject();
            string? output = Environment.GetEnvironmentVariable("INFINI_PARENT_CRIT_CAPTURE_DIR");
            if (!string.IsNullOrEmpty(output))
            {
                Directory.CreateDirectory(output);
                File.WriteAllText(Path.Combine(output, owner + ".json"), facts.ToJsonString());
            }
            Equal(4, facts["crit"]!.GetValue<int>(), "base snapshot never becomes conditional 4 + 23");
            Equal(4, item.crit, "source capture never changes base crit");
            Equal(17, item.damage, "source capture never changes native item damage");
            Equal(0, CritSourceExecutions, "source capture never executes crit hooks or helper bodies");
            string expectedOwner = owner == "item" ? "parent_ModItem" : owner == "global" ? "attached_GlobalItem" : "registered_ModPlayer_candidate";
            JsonObject[] roots = graph["roots"]!.AsArray().OfType<JsonObject>().Where(row => row["event"]?.GetValue<string>() == "ModifyWeaponCrit").ToArray();
            Equal(1, roots.Length, "exact admitted ModifyWeaponCrit root: " + expectedOwner);
            Equal(expectedOwner, roots[0]["owner"]!.GetValue<string>(), "crit hook source owner preserved");
            Equal("event_signature", roots[0]["receiver"]!.GetValue<string>(), "runtime event not falsely observed as executed");
            JsonObject node = graph["nodes"]!.AsArray().OfType<JsonObject>().Single(row => row["id"]!.ToJsonString() == roots[0]["node"]!.ToJsonString());
            string declaringType = owner == "item" ? nameof(CritSourceItemBase) : owner == "global" ? nameof(CritSourceGlobal) : nameof(CritSourcePlayer);
            Equal(true, graph["members"]![node["method"]!.GetValue<int>()]!["name"]!.GetValue<string>().Contains(declaringType + ".ModifyWeaponCrit("), "exact inherited or declared hook selected");
            Equal(true, node["sha256"] is JsonValue, "hook retains native IL certificate");
            Equal(true, node["values"] is JsonObject values && values.Count > 0, "crit values and branches retained");
            string source = graph.ToJsonString();
            Equal(true, source.Contains(owner == "player" ? "Terraria.Player.statLife" : "Terraria.Entity.wet", StringComparison.Ordinal), "runtime guard stays source evidence");
            Equal(true, graph["nodes"]!.AsArray().OfType<JsonObject>()
                .SelectMany(row => row["values"]!.AsObject().Select(value => value.Value!.AsArray()))
                .Any(value => value[0]!.GetValue<string>() == "ldc.r4" && value[1]!.ToJsonString() == "23"),
                "literal float hook delta remains separate source");
            Equal("partial_source_graph", graph["completeness"]!.GetValue<string>(), "bounded source retains partial coverage qualification");
            Equal(true, graph["scope"]!.GetValue<string>().Contains("live predicates are never evaluated", StringComparison.Ordinal), "scope never claims the guarded bonus is active");
            if (owner != "item")
            {
                JsonObject guardedValues = node["values"]!.AsObject();
                var write = guardedValues.Single(value => value.Value![0]!.GetValue<string>() == "stind.r4");
                var block = node["blocks"]!.AsArray().Single(row => row![0]!.ToJsonString() == write.Value![3]!.ToJsonString())!;
                Equal(2, block[3]!.AsArray().Count, "crit ref write retains both enclosing runtime guards");
                foreach (JsonNode? branch in block[3]!.AsArray())
                    Equal(true, guardedValues.ContainsKey(branch!.GetValue<string>()), "every required runtime guard resolves inside its source node");
            }
            if (owner == "item")
                Equal(true, source.Contains(".ApplyCritDelta(", StringComparison.Ordinal), "inherited hook retains its reachable helper");
        }
        finally
        {
            globalsField.SetValue(null, oldGlobals);
            foreach (var row in previous) { if (row.Had) cache[row.Type] = row.Value; else cache.Remove(row.Type); }
        }
    }
}
