using System;
using System.Collections;
using System.Collections.Generic;
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
                AssertParentCritWriteEvidence(graph, node, owner);
                ParentCritWriteEvidenceRejectsMutations(graph, node, owner);
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
    // A fixture-only check of exported evidence, never a call to either hook.
    // Release emits two enclosing branches. Debug materializes the conjunction
    // in a bool local whose phi alternatives carry the first branch's control.
    // Follow that data/control closure rather than counting direct guards.
    private static void AssertParentCritWriteEvidence(JsonObject graph, JsonObject node, string owner)
    {
        Equal(false, node["static"]!.GetValue<bool>(), "crit hook is an instance event");
        Equal(owner == "global" ? "item,player,crit" : "item,crit",
            string.Join(",", node["arguments"]!.AsArray().Select(argument => argument!.GetValue<string>())),
            "crit hook argument slots retain their declared binding");
        JsonObject values = node["values"]!.AsObject();
        var blocks = node["blocks"]!.AsArray().OfType<JsonArray>().ToDictionary(row => row[0]!.GetValue<int>());
        JsonArray Row(string id) => values[id] as JsonArray ?? throw new InvalidOperationException("Missing crit evidence: " + id);
        string[] Inputs(JsonArray row) => row[2]!.AsArray().Select(input => input!.GetValue<string>()).ToArray();
        string Member(JsonArray row) => graph["members"]![row[1]!["member"]!.GetValue<int>()]!["name"]!.GetValue<string>();
        JsonArray write = values.Single(value => value.Value![0]!.GetValue<string>() == "stind.r4").Value!.AsArray();
        Equal(true, values.Count <= 64 && blocks.Count <= 16, "small crit evidence fixture bound");
        bool Reaches(int start, int target)
        {
            var pending = new Stack<int>(); var seen = new HashSet<int>(); pending.Push(start);
            while (pending.Count > 0)
            {
                int next = pending.Pop();
                if (next == target) return true;
                if (!seen.Add(next) || !blocks.TryGetValue(next, out JsonArray? block)) continue;
                foreach (JsonNode? successor in block[1]!.AsArray()) pending.Push(successor!.GetValue<int>());
            }
            return false;
        }
        foreach (int damage in new[] { 9, 10, 11 })
        foreach (int maxLife in new[] { 100, 200 })
        foreach (int life in new[] { maxLife - 1, maxLife, maxLife + 1 })
        foreach (bool wet in new[] { false, true })
        foreach (int initialCrit in new[] { 0, 4, 7 })
        {
            var visiting = new HashSet<string>();
            bool Allows(int blockId)
            {
                if (!blocks.TryGetValue(blockId, out JsonArray? block)) throw new InvalidOperationException("Missing crit block");
                bool allowed = true;
                foreach (JsonNode? guard in block[3]!.AsArray())
                {
                    string id = guard!.GetValue<string>(); JsonArray branch = Row(id);
                    JsonArray branchBlock = blocks[branch[3]!.GetValue<int>()];
                    Equal(id, branchBlock[2]!.ToString(), "guard is its block's retained terminator");
                    int[] next = branchBlock[1]!.AsArray().Select(value => value!.GetValue<int>()).ToArray();
                    Equal(2, next.Length, "conditional guard has both successors");
                    Equal(branch[1]!.GetValue<int>(), next[0], "branch target matches CFG edge");
                    Equal(true, Reaches(next[0], blockId) != Reaches(next[1], blockId), "guard distinguishes this definition/effect block");
                    bool taken = (double)Read(id) != 0;
                    allowed &= Reaches(next[taken ? 0 : 1], blockId);
                }
                return allowed;
            }
            object Read(string id)
            {
                if (!visiting.Add(id)) throw new InvalidOperationException("Cyclic crit evidence");
                try
                {
                    JsonArray row = Row(id); string[] inputs = Inputs(row);
                    string op = row[0]!.GetValue<string>().Replace(".s", "", StringComparison.Ordinal);
                    object Input(int index) => Read(inputs[index]);
                    double Number(int index) => (double)Input(index);
                    switch (op)
                    {
                        case "ldarg":
                            int slot = row[1]!.GetValue<int>();
                            return slot == 0 ? "this" : node["arguments"]![slot - 1]!.GetValue<string>();
                        case "const": return (double)row[1]!.GetValue<int>();
                        case "ldc.r4": return (double)row[1]!.GetValue<float>();
                        case "ldloc": case "stloc":
                            Equal(1, inputs.Length, "fixture local has one retained definition"); return Input(0);
                        case "predecessor_stack_alternatives":
                            string selected = inputs.Where(input => Allows(Row(input)[3]!.GetValue<int>())).Single();
                            Equal(true, Reaches(Row(selected)[3]!.GetValue<int>(), row[3]!.GetValue<int>()), "selected phi input reaches its join");
                            return Read(selected);
                        case "call":
                            Equal("player", owner, "receiver accessor belongs to the ModPlayer fixture");
                            Equal("Terraria.ModLoader.ModPlayer.get_Player()", Member(row), "only the declared ModPlayer receiver accessor is admitted");
                            Equal("this", Input(0), "player accessor is bound to the hook receiver"); return "player";
                        case "ldfld":
                            string member = Member(row);
                            Equal(member == "Terraria.Item.damage" ? "item" : "player", Input(0), "guard field is bound to its event actor");
                            return member switch {
                                "Terraria.Item.damage" => (double)damage,
                                "Terraria.Entity.wet" => wet ? 1d : 0d,
                                "Terraria.Player.statLife" => (double)life,
                                "Terraria.Player.statLifeMax2" => (double)maxLife,
                                _ => throw new InvalidOperationException("Unexpected crit predicate field: " + member),
                            };
                        case "ldind.r4": Equal("crit", Input(0), "delta reads the same crit output"); return (double)initialCrit;
                        case "add": return Number(0) + Number(1);
                        case "cgt": case "bgt": return Number(0) > Number(1) ? 1d : 0d;
                        case "clt": case "blt": return Number(0) < Number(1) ? 1d : 0d;
                        case "bge": return Number(0) >= Number(1) ? 1d : 0d;
                        case "ble": return Number(0) <= Number(1) ? 1d : 0d;
                        case "brtrue": return Number(0) != 0 ? 1d : 0d;
                        case "brfalse": return Number(0) == 0 ? 1d : 0d;
                        default: throw new InvalidOperationException("Unsupported crit evidence row: " + op);
                    }
                }
                finally { visiting.Remove(id); }
            }
            string[] output = Inputs(write);
            Equal("crit", Read(output[0]), "ref write targets the event crit argument");
            Equal(initialCrit + 23d, Read(output[1]), "ref write retains crit + 23, not an unrelated literal");
            Equal(damage > 10 && (owner == "global" ? wet : life < maxLife), Allows(write[3]!.GetValue<int>()),
                $"crit write conjunction for {owner}: damage={damage}, life={life}/{maxLife}, wet={wet}");
        }
    }

    private static void ParentCritWriteEvidenceRejectsMutations(JsonObject graph, JsonObject node, string owner)
    {
        void Reject(string label, Action<JsonObject> mutate)
        {
            JsonObject changed = node.DeepClone().AsObject(); mutate(changed);
            bool rejected = false;
            try { AssertParentCritWriteEvidence(graph, changed, owner); }
            catch (InvalidOperationException) { rejected = true; }
            Equal(true, rejected, "crit evidence rejects " + label);
        }
        JsonObject Values(JsonObject changed) => changed["values"]!.AsObject();
        JsonArray Write(JsonObject changed) => Values(changed).Single(value => value.Value![0]!.GetValue<string>() == "stind.r4").Value!.AsArray();
        JsonArray FirstBranch(JsonObject changed) => Values(changed).First(value =>
            value.Value![0]!.GetValue<string>() is "ble.s" or "ble" or "bge.s" or "bge").Value!.AsArray();
        Reject("missing write guards", changed => changed["blocks"]!.AsArray().Single(block =>
            block![0]!.GetValue<int>() == Write(changed)[3]!.GetValue<int>())![3] = new JsonArray());
        Reject("missing predicate definition", changed => Values(changed).Remove(FirstBranch(changed)[2]![0]!.GetValue<string>()));
        Reject("disconnected predicate inputs with fields still present", changed => {
            JsonArray branch = FirstBranch(changed); branch[2]![0] = branch[2]![1]!.DeepClone();
        });
        Reject("reversed first predicate", changed => {
            JsonArray branch = FirstBranch(changed); branch[0] = owner == "global" ? "bgt.s" : "blt.s";
        });
        Reject("wrong branch target", changed => {
            JsonArray branch = FirstBranch(changed);
            branch[1] = changed["blocks"]!.AsArray().Single(block => block![0]!.GetValue<int>() == branch[3]!.GetValue<int>())![1]![1]!.DeepClone();
        });
        Reject("swapped branch arms", changed => {
            JsonArray branch = FirstBranch(changed);
            JsonArray next = changed["blocks"]!.AsArray().Single(block => block![0]!.GetValue<int>() == branch[3]!.GetValue<int>())![1]!.AsArray();
            int target = next[0]!.GetValue<int>(); next[0] = next[1]!.GetValue<int>(); next[1] = target;
            branch[1] = next[0]!.GetValue<int>();
        });
        Reject("wrong guard actor", changed => {
            JsonArray field = Values(changed).First(value => value.Value![0]!.GetValue<string>() == "ldfld").Value!.AsArray();
            string receiver = field[2]![0]!.GetValue<string>();
            if (owner == "player") receiver = Values(changed)[receiver]![2]![0]!.GetValue<string>();
            Values(changed)[receiver]![1] = owner == "global" ? 2 : 1;
        });
        Reject("wrong crit destination", changed => Values(changed)[Write(changed)[2]![0]!.GetValue<string>()]![1] = 1);
        Reject("wrong delta", changed => Values(changed).Single(value => value.Value![0]!.GetValue<string>() == "ldc.r4").Value![1] = 24f);
        Reject("constant output detached from crit", changed => {
            JsonArray rhs = Values(changed)[Write(changed)[2]![1]!.GetValue<string>()]!.AsArray();
            rhs[0] = "ldc.r4"; rhs[1] = 27f; rhs[2] = new JsonArray();
        });
        if (Values(node).Any(value => value.Value![0]!.GetValue<string>() == "predecessor_stack_alternatives"))
        {
            Reject("disconnected phi controls with predicate rows still present", changed => {
                string firstId = Values(changed).Single(value => ReferenceEquals(value.Value, FirstBranch(changed))).Key;
                foreach (JsonNode? block in changed["blocks"]!.AsArray())
                    block![3] = new JsonArray(block[3]!.AsArray().Where(id => id!.GetValue<string>() != firstId).Select(id => id!.DeepClone()).ToArray());
            });
            Reject("true short-circuit bypass", changed => Values(changed).Single(value =>
                value.Value![0]!.GetValue<string>() == "const" && value.Value![1]!.GetValue<int>() == 0).Value![1] = 1);
        }
    }
}
