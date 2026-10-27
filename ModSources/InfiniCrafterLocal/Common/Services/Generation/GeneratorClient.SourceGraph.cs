#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // One parent-local source graph supplements the certified native catalogs.
    // It never runs a hook, allocates gameplay actors, reads mutable mod statics,
    // or turns source statements into generated-item behavior.
    internal static JsonObject CaptureParentSourceGraph(Item item, JsonObject? nativeFacts = null)
    {
        var graph = new ParentSourceGraph();
        graph.Item(item);
        if (nativeFacts is not null) graph.ObservedBuffs(nativeFacts);
        return graph.Finish();
    }

    private sealed class ParentSourceGraph
    {
        private const int NodeLimit = 48, EdgeLimit = 192, DepthLimit = 6, CharacterLimit = 16000;
        private readonly JsonArray nodes = new(), edges = new(), roots = new(), gaps = new();
        private readonly JsonArray members = new(), modules = new();
        private readonly Dictionary<string, int> memberIndices = new(StringComparer.Ordinal);
        private readonly Dictionary<Guid, int> moduleIndices = new();
        private readonly Dictionary<string, int> admitted = new(StringComparer.Ordinal);
        private readonly Dictionary<string, HashSet<FieldInfo>?> focuses = new(StringComparer.Ordinal);
        private readonly Dictionary<MethodBase, HashSet<int>> nativeStatements = new();
        private readonly Queue<(MethodBase Method, int Node, int Depth, HashSet<FieldInfo>? Focus)> pending = new();
        private readonly HashSet<(int Id, string Receiver)> buffs = new();
        private readonly HashSet<int> projectiles = new();
        private readonly HashSet<FieldInfo> watched = new();
        private readonly HashSet<string> reasons = new(StringComparer.Ordinal);
        private readonly Dictionary<MethodBase, ParentSourceMethod?> inspected = new();
        private readonly Dictionary<MethodBase, string> readFailures = new();
        private readonly Dictionary<MethodBase, List<AmmoIl>> nativeSlices = new(), nativeCode = new();
        private readonly Dictionary<MethodBase, Dictionary<int, int>> nativeNext = new();
        private readonly HashSet<MethodBase> nativeProjectileMethods = new();
        private readonly Dictionary<MethodBase, List<(ParentSourceMethod Body, ParentSourceMethod.Value Call)>> callers = new();
        private readonly HashSet<string> edgeKeys = new(StringComparer.Ordinal);
        private readonly List<(Type Type, Type Base)> consumers = new();
        private bool rosterRead;
        private int scanCount;

        private int Module(Module module)
        {
            if (moduleIndices.TryGetValue(module.ModuleVersionId, out int existing)) return existing;
            int id = modules.Count; moduleIndices[module.ModuleVersionId] = id;
            modules.Add(new JsonObject { ["assembly"] = module.Assembly.GetName().Name, ["mvid"] = module.ModuleVersionId.ToString() });
            return id;
        }
        private int Member(MemberInfo member)
        {
            string key = member.Module.ModuleVersionId + ":" + member.MetadataToken + ":" + SourceMember(member);
            if (memberIndices.TryGetValue(key, out int existing)) return existing;
            int id = members.Count; memberIndices[key] = id;
            var row = new JsonObject { ["name"] = SourceMember(member), ["module"] = Module(member.Module) };
            if (member is FieldInfo field) row["type"] = field.FieldType.FullName;
            if (member is MethodInfo method) row["returns"] = method.ReturnType.FullName;
            members.Add(row); return id;
        }
        private JsonObject CompactMethod(JsonObject row, MethodBase method, ParentSourceMethod? body = null)
        {
            row.Remove("method"); row.Remove("signature"); row.Remove("fieldTypes"); row.Remove("sourceModuleVersionId");
            row["method"] = Member(method);
            if (row["sourceMethodSha256"] is JsonNode sha) { row.Remove("sourceMethodSha256"); row["sha256"] = sha; }
            if (row["arguments"] is not null) row["arguments"] = new JsonArray(method.GetParameters().Select(p => (JsonNode?)JsonValue.Create(p.Name)).ToArray());
            if (body is not null && row["values"] is JsonObject values)
                foreach (var value in values)
                    if (body.Values[value.Key].Operand is MemberInfo member) value.Value![1] = new JsonObject { ["member"] = Member(member) };
            return row;
        }
        private void PruneMembers()
        {
            var used = nodes.OfType<JsonObject>().Where(n => n["method"] is JsonValue).Select(n => n["method"]!.GetValue<int>()).ToHashSet();
            foreach (var node in nodes.OfType<JsonObject>())
                if (node["values"] is JsonObject values)
                    foreach (var value in values)
                        if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode id) used.Add(id.GetValue<int>());
            var mapping = used.OrderBy(n => n).Select((old, next) => (old, next)).ToDictionary(pair => pair.old, pair => pair.next);
            var retained = used.OrderBy(n => n).Select(n => members[n]!.DeepClone()).ToArray();
            members.Clear(); foreach (var member in retained) members.Add(member);
            foreach (var node in nodes.OfType<JsonObject>())
            {
                if (node["method"] is JsonValue method) node["method"] = mapping[method.GetValue<int>()];
                if (node["values"] is JsonObject values)
                    foreach (var value in values)
                        if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode id) operand["member"] = mapping[id.GetValue<int>()];
            }
        }

        private static readonly HashSet<string> ItemEvents = new(StringComparer.Ordinal)
        {
            "AltFunctionUse", "CanUseItem", "CanShoot", "UseItem", "UseStyle", "HoldItem", "HoldStyle", "UseAnimation",
            "Shoot", "ModifyShootStats", "OnHitNPC", "ModifyHitNPC", "CanHitNPC", "OnHitPvp", "ModifyHitPvp", "CanHitPvp",
            "UpdateEquip", "UpdateAccessory", "UpdateVanity", "UpdateInventory", "IsArmorSet", "UpdateArmorSet",
            "CanEquipAccessory", "UseItemHitbox", "MeleeEffects", "OnConsumeItem", "ConsumeItem",
        };
        private static readonly HashSet<string> ProjectileEvents = new(StringComparer.Ordinal)
        {
            "PreAI", "AI", "PostAI", "OnHitNPC", "ModifyHitNPC", "OnHitPlayer", "ModifyHitPlayer", "CanHitNPC", "CanHitPlayer",
            "OnKill", "PreKill", "OnSpawn", "OnTileCollide", "Colliding", "CanDamage", "ShouldUpdatePosition",
        };
        private static readonly HashSet<string> BuffEvents = new(StringComparer.Ordinal) { "Update", "ReApply", "SetStaticDefaults" };
        private static readonly HashSet<string> PlayerEvents = new(StringComparer.Ordinal)
        {
            "CanUseItem", "CanShoot", "Shoot", "ModifyShootStats", "OnHitNPCWithItem", "ModifyHitNPCWithItem",
            "OnHitNPCWithProj", "ModifyHitNPCWithProj", "OnHitPvp", "ModifyHitPvp", "OnHitAnything",
        };

        private void Gap(string reason)
        {
            if (reasons.Add(reason) && gaps.Count < 24) gaps.Add(reason);
        }
        private static string MethodKey(MethodBase method) => method.Module.ModuleVersionId + ":" + method.MetadataToken + ":" + SourceMember(method);
        private ParentSourceMethod? Read(MethodBase method)
        {
            if (inspected.TryGetValue(method, out var existing)) return existing;
            if (++scanCount > 1024) { Gap("source_scan_method_limit"); return null; }
            try { return inspected[method] = nativeSlices.TryGetValue(method, out var slice)
                    ? new ParentSourceMethod(method, slice, nativeNext[method]) : new ParentSourceMethod(method); }
            catch (Exception error) when (error is not OutOfMemoryException)
            { inspected[method] = null; readFailures[method] = error is NotSupportedException ? error.Message : error.GetType().Name; return null; }
        }
        private void Edge(int? from, int? to, string kind, int? at = null, JsonNode? context = null, string? unresolved = null)
        {
            if (edges.Count >= EdgeLimit) { Gap("edge_limit"); return; }
            var edge = new JsonObject { ["kind"] = kind };
            if (from is not null) edge["from"] = from;
            if (to is not null) edge["to"] = to;
            if (at is not null) edge["at"] = at;
            if (context is not null) edge["context"] = context;
            if (unresolved is not null) edge["unresolved"] = unresolved;
            if (edgeKeys.Add(edge.ToJsonString())) edges.Add(edge);
        }
        private int? Add(MethodBase method, int depth, HashSet<FieldInfo>? focus = null)
        {
            string key = MethodKey(method);
            if (admitted.TryGetValue(key, out int existing))
            {
                if (focuses[key] is { } prior)
                {
                    int count = prior.Count;
                    if (focus is null) focuses[key] = null;
                    else prior.UnionWith(focus);
                    if (focus is null || prior.Count != count) pending.Enqueue((method, existing, depth, focuses[key]));
                }
                return existing;
            }
            if (depth > DepthLimit) { Gap("helper_depth_limit"); return null; }
            if (nodes.Count >= NodeLimit) { Gap("node_limit"); return null; }
            int id = nodes.Count;
            admitted[key] = id;
            focuses[key] = focus is null ? null : new HashSet<FieldInfo>(focus);
            nodes.Add(new JsonObject { ["id"] = id, ["method"] = SourceMember(method), ["coverage"] = "pending" });
            pending.Enqueue((method, id, depth, focuses[key]));
            return id;
        }
        private static IEnumerable<MethodInfo> Overrides(Type type, Type baseType)
            => type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
                .Where(m => m.IsVirtual && m.DeclaringType != baseType && baseType.IsAssignableFrom(m.DeclaringType)
                    && m.GetBaseDefinition().DeclaringType != typeof(object) && m.GetBaseDefinition().DeclaringType!.IsAssignableFrom(baseType))
                .OrderBy(m => m.MetadataToken);
        private void Hooks(Type type, Type baseType, HashSet<string> events, string owner, string receiver)
        {
            foreach (MethodInfo method in Overrides(type, baseType).Where(m => events.Contains(m.Name)))
            {
                int? node = Add(method, 0);
                if (node is null) continue;
                roots.Add(new JsonObject { ["node"] = node, ["event"] = method.Name, ["owner"] = owner,
                    ["receiver"] = receiver });
            }
        }
        private void Roster<T>(Type baseType) where T : class, ILoadable
        {
            try
            {
                foreach (T prototype in ModContent.GetContent<T>()) consumers.Add((prototype.GetType(), baseType));
            }
            catch { Gap("registered_" + baseType.Name + "_roster_unavailable"); }
        }
        private void ReadRoster()
        {
            if (rosterRead) return;
            rosterRead = true;
            Roster<GlobalNPC>(typeof(GlobalNPC)); Roster<ModPlayer>(typeof(ModPlayer)); Roster<GlobalBuff>(typeof(GlobalBuff));
        }

        internal void Item(Item item)
        {
            if (item.ModItem is not null) Hooks(item.ModItem.GetType(), typeof(ModItem), ItemEvents, "parent_ModItem", "event_signature");
            try { foreach (var global in item.Globals) Hooks(global.GetType(), typeof(GlobalItem), ItemEvents, "attached_GlobalItem", "event_signature"); }
            catch { Gap("attached_GlobalItem_roster_unavailable"); }
            ReadRoster();
            foreach (var owner in consumers.Where(o => o.Base == typeof(ModPlayer)))
                Hooks(owner.Type, owner.Base, PlayerEvents, "registered_ModPlayer_candidate", "event_signature");
            if (item.shoot > ProjectileID.None) Projectile(item.shoot, null, null, "item.shoot_field_candidate");
            if (item.buffType > InfiniTerrariaSentinels.NoBuffType) Buff(item.buffType, "player", null, null);
            if (item.createTile >= TileID.Dirt)
            {
                ModTile? tile = TileLoader.GetTile(item.createTile);
                if (tile is not null) Hooks(tile.GetType(), typeof(ModTile), new HashSet<string>(StringComparer.Ordinal)
                    { "NearbyEffects", "RightClick", "HitWire", "PlaceInWorld", "CanPlace", "KillMultiTile", "FloorVisuals" }, "parent_placed_tile", "placed_tile_conditions_not_evaluated");
                try
                {
                    foreach (var tileGlobal in ModContent.GetContent<GlobalTile>())
                        Hooks(tileGlobal.GetType(), typeof(GlobalTile), new HashSet<string>(StringComparer.Ordinal)
                            { "NearbyEffects", "PlaceInWorld", "HitWire", "CanPlace" }, "registered_GlobalTile_candidate", "placed_tile_conditions_not_evaluated");
                }
                catch { Gap("registered_GlobalTile_roster_unavailable"); }
            }
            if (nodes.Count == 0 && item.ModItem is null) Gap("no_parent_mod_override_observed; native_catalog_coverage_is_separate");
        }

        internal void ObservedBuffs(JsonNode? observation, string receiver = "npc")
        {
            if (observation is JsonObject row)
            {
                string target = row["receiver"]?.GetValue<string>() ?? receiver;
                if (row["buffId"] is JsonValue value && value.TryGetValue<int>(out int id)) Buff(id, target, null, null);
                foreach (var pair in row) ObservedBuffs(pair.Value, pair.Key == "nativeBuffEffectReference" ? "player" : target);
            }
            else if (observation is JsonArray array) foreach (JsonNode? value in array) ObservedBuffs(value, receiver);
        }

        private void Projectile(int id, int? from, int? at, string kind)
        {
            if (id <= 0 || id >= ProjectileLoader.ProjectileCount) { Edge(from, null, kind, at, unresolved: "projectile_identity_not_registered"); return; }
            // A defaults sample is already registered. Do not call SetDefaults to
            // discover a child: arbitrary mod code may have gameplay side effects.
            if (!ContentSamples.ProjectilesByType.TryGetValue(id, out var sample))
            { Edge(from, null, kind, at, JsonValue.Create(id), "registered_projectile_sample_unavailable"); return; }
            if (!projectiles.Add(id)) { Edge(from, null, kind, at, JsonValue.Create(id), "already_visited_projectile_identity"); return; }
            object? nativeStatus = VerifiedSourceHitStatusReference(sample, HitStatusSourceCertificate.Value, typeof(Projectile).Module.ModuleVersionId.ToString());
            if (nativeStatus is not null) ObservedBuffs(JsonSerializer.SerializeToNode(nativeStatus, WireJsonOptions));
            var owners = new List<(Type Type, Type Base)>();
            if (sample.ModProjectile is not null) owners.Add((sample.ModProjectile.GetType(), typeof(ModProjectile)));
            try { foreach (var global in sample.Globals) owners.Add((global.GetType(), typeof(GlobalProjectile))); }
            catch { Gap("child_attached_GlobalProjectile_roster_unavailable"); }
            foreach (var owner in owners.Distinct())
                foreach (var method in Overrides(owner.Type, owner.Base).Where(m => ProjectileEvents.Contains(m.Name)))
                {
                    int? node = Add(method, 0);
                    Edge(from, node, kind, at, new JsonObject { ["projectileId"] = id, ["event"] = method.Name }, node is null ? "graph_limit" : null);
                }
            if (sample.ModProjectile is null) NativeProjectile(sample, from, at);
        }

        private void NativeProjectile(Projectile projectile, int? from, int? at)
        {
            if (!NativeSourceModuleVerified.Value) { Gap("native_projectile_module_certificate_unavailable"); return; }
            foreach (string name in new[] { "VanillaAI", "Kill" })
            {
                MethodInfo? method = typeof(Projectile).GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (method is null) continue;
                try
                {
                    if (!nativeCode.TryGetValue(method, out var code))
                    {
                        nativeCode[method] = code = ReadAmmoIl(method, preserveStructure: true, sourceGraph: true);
                        nativeNext[method] = code.Zip(code.Skip(1), (left, right) => (left.Offset, Next: right.Offset)).ToDictionary(p => p.Offset, p => p.Next);
                    }
                    var selected = new Dictionary<int, AmmoIl>();
                    // Exact type/AI-style equality fallthrough windows. Entry,
                    // missing predecessors and exits stay explicitly unresolved.
                    // No other branch arm is executed, selected or assumed true.
                    for (int n = 0; n + 4 < code.Count; n++)
                    {
                        if (code[n].Op != "ldarg" || !Equals(code[n].Arg, 0)
                            || code[n + 1].Op != "ldfld" || code[n + 1].Arg is not FieldInfo field || field.DeclaringType != typeof(Projectile)
                            || code[n + 2].Op != "const" || code[n + 2].Arg is not int literal
                            || !(field.Name == "type" && literal == projectile.type || field.Name == "aiStyle" && literal == projectile.aiStyle)
                            || code[n + 3].Arg is not int destination || destination <= code[n + 3].Offset) continue;
                        int start = n + 4, end;
                        if (code[n + 3].Op is "bne.un" or "bne.un.s") end = destination;
                        else if (code[n + 3].Op is "beq" or "beq.s")
                        {
                            start = code.FindIndex(i => i.Offset == destination);
                            if (start < 1 || code[start - 1].Op is not ("bne.un" or "bne.un.s" or "br" or "br.s")
                                || code[start - 1].Arg is not int boundary || boundary <= destination) continue;
                            end = boundary;
                        }
                        else continue;
                        var window = code.Skip(n).Take(4).Concat(code.Skip(start).TakeWhile(i => i.Offset < end)).Take(1025).ToArray();
                        if (window.Length > 1024) { Gap("native_projectile_equality_window_bound"); continue; }
                        foreach (var instruction in window) selected[instruction.Offset] = instruction;
                    }
                    if (selected.Count == 0)
                    { Edge(from, null, "native_projectile_source", at, JsonValue.Create(projectile.type), "no_supported_type_or_aiStyle_equality_window_in_" + name); continue; }
                    if (nativeSlices.TryGetValue(method, out var prior)) foreach (var instruction in prior) selected[instruction.Offset] = instruction;
                    if (selected.Count > 4096) { Gap("native_projectile_source_window_limit"); continue; }
                    bool changed = prior is null || prior.Count != selected.Count;
                    nativeSlices[method] = selected.Values.OrderBy(i => i.Offset).ToList();
                    nativeProjectileMethods.Add(method);
                    if (changed) inspected.Remove(method);
                    bool existing = admitted.TryGetValue(MethodKey(method), out int existingNode);
                    int? node = Add(method, 0);
                    if (changed && existing) pending.Enqueue((method, existingNode, 0, null));
                    Edge(from, node, "certified_native_projectile_source_windows", at, new JsonObject
                        { ["projectileId"] = projectile.type, ["aiStyle"] = projectile.aiStyle, ["entryAndOmittedFlow"] = "unresolved" }, node is null ? "graph_limit" : null);
                }
                catch { Gap("native_projectile_source_outside_bound"); }
            }
        }

        private void Buff(int id, string receiver, int? from, int? at)
        {
            if (id <= 0 || id >= BuffLoader.BuffCount) { Edge(from, null, "buff_request", at, unresolved: "buff_identity_not_registered"); return; }
            Edge(from, null, "buff_request", at, new JsonObject { ["buffId"] = id, ["receiver"] = receiver,
                ["admission"] = "AddBuff_request_only; immunity_and_refresh_may_change_outcome" });
            if (!buffs.Add((id, receiver))) return;
            ModBuff? buff = BuffLoader.GetBuff(id);
            if (buff is not null)
                foreach (var method in Overrides(buff.GetType(), typeof(ModBuff)).Where(m => BuffEvents.Contains(m.Name)))
                {
                    if (method.Name != "SetStaticDefaults" && !method.GetParameters().Any(p => p.ParameterType == (receiver == "npc" ? typeof(NPC) : typeof(Player)))) continue;
                    int? node = Add(method, 0);
                    Edge(from, node, "requested_buff_implementation", at, new JsonObject { ["buffId"] = id, ["receiver"] = receiver }, node is null ? "graph_limit" : null);
                }
            else NativeBuff(id, receiver, from);
            if (NativeSourceModuleVerified.Value)
            {
                Type target = receiver == "npc" ? typeof(NPC) : typeof(Player);
                MethodInfo? admission = target.GetMethods(BindingFlags.Instance | BindingFlags.Public).FirstOrDefault(m => m.Name == "AddBuff");
                if (admission is not null)
                    Edge(from, Add(admission, 0, new HashSet<FieldInfo>(target.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                        .Where(f => f.Name is "buffImmune" or "buffType" or "buffTime"))), "native_buff_admission_and_refresh_source", at,
                        new JsonObject { ["buffId"] = id, ["receiver"] = receiver });
            }
            ReadRoster();
            foreach (var owner in consumers.Where(o => o.Base == typeof(GlobalBuff)))
                foreach (var method in Overrides(owner.Type, owner.Base).Where(m => m.Name is "Update" or "ReApply"))
                {
                    if (!method.GetParameters().Any(p => p.ParameterType == (receiver == "npc" ? typeof(NPC) : typeof(Player)))) continue;
                    int? node = Add(method, 0);
                    Edge(from, node, "loaded_GlobalBuff_candidate", at, new JsonObject { ["buffId"] = id, ["receiver"] = receiver }, node is null ? "graph_limit" : null);
                }
            // Read only this buff's registered relationship, never the registry.
            try
            {
                var related = BuffID.Sets.GrantImmunityWith[id];
                if (related is not null && related.Count > 0)
                    Edge(from, null, "loaded_immunity_relationship", at, new JsonObject { ["buffId"] = id,
                        ["grantImmunityWith"] = new JsonArray(related.Select(i => (JsonNode?)JsonValue.Create(i)).ToArray()),
                        ["scope"] = "current_registration; target_immunity_not_observed" });
            }
            catch { Gap("buff_immunity_relationship_unavailable"); }
        }

        private void NativeBuff(int id, string receiver, int? from)
        {
            // Existing certificates remain authoritative. This is additional
            // source syntax for previously unsupported branches/consumers.
            if (BuffEffectSourceCertificate.Value is null) { Gap("native_buff_binary_certificate_unavailable"); return; }
            Type target = receiver == "npc" ? typeof(NPC) : typeof(Player);
            JsonObject known = VerifiedNativeBuffEffectReference(id, receiver, BuffEffectSourceCertificate.Value);
            // Already delivered numeric fragments need not be copied into a
            // second catalog. Their exact native flags still seed loaded-mod
            // consumer discovery, including modifications of vanilla buffs.
            foreach (var field in target.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                if (known.ToJsonString().Contains("\"" + target.FullName + "." + field.Name + "\"", StringComparison.Ordinal)) watched.Add(field);
            if (known["fragments"] is JsonArray knownFragments && knownFragments.Count > 0) return;
            string name = receiver == "npc" ? "UpdateNPC_BuffSetFlags" : "UpdateBuffs";
            MethodInfo? method = target.GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (method is null || Read(method) is not { } body) { Gap("native_buff_dispatch_outside_source_bound"); return; }
            var selected = new HashSet<FieldInfo>();
            var offsets = new HashSet<int>();
            // An identity comparison must actually load target.buffType[slot],
            // not merely contain an unrelated literal with the same integer.
            foreach (var branch in body.Statements.Where(v => v.Op.StartsWith("beq", StringComparison.Ordinal) || v.Op.StartsWith("bne", StringComparison.Ordinal)))
            {
                if (branch.Inputs.Count != 2) continue;
                bool Identity(string input) => body.Definitions(input).Any(v => v.Op == "const" && Equals(v.Operand, id));
                bool Slot(string input) => body.Definitions(input).Any(v => v.Op == "ldelem.i4" && v.Inputs.Count == 2
                    && body.Definitions(v.Inputs[0]).Any(a => a.Operand is FieldInfo f && f.DeclaringType == target && f.Name == "buffType"));
                if (!(Identity(branch.Inputs[0]) && Slot(branch.Inputs[1]) || Identity(branch.Inputs[1]) && Slot(branch.Inputs[0]))) continue;
                var blocks = EqualityBlocks(body, branch);
                foreach (var value in body.Values.Values.Where(v => blocks.Contains(v.Block)))
                {
                    if (value.Operand is FieldInfo field && value.Op is "stfld" or "ldflda") selected.Add(field);
                    if (body.Statements.Contains(value)) offsets.Add(value.At);
                }
            }
            if (offsets.Count == 0) { Gap("native_buff_branch_has_no_resolved_statement_slice"); return; }
            if (!nativeStatements.TryGetValue(method, out var prior)) nativeStatements[method] = prior = new();
            int previousCount = prior.Count; prior.UnionWith(offsets);
            foreach (FieldInfo field in selected) watched.Add(field);
            int? node = Add(method, 0, selected);
            if (node is int updated && previousCount > 0 && previousCount != prior.Count)
                pending.Enqueue((method, updated, 0, focuses[MethodKey(method)]));
            Edge(from, node, "certified_native_buff_source_slice", context: new JsonObject { ["buffId"] = id, ["receiver"] = receiver }, unresolved: node is null ? "graph_limit" : null);
            if (receiver == "npc")
                foreach (string consumer in new[] { "UpdateNPC_BuffApplyDOTs", "GetIncomingStrikeModifiers" })
                {
                    var candidate = typeof(NPC).GetMethod(consumer, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (candidate is not null) Add(candidate, 0, selected);
                }
        }

        private static HashSet<int> EqualityBlocks(ParentSourceMethod body, ParentSourceMethod.Value branch)
        {
            // Preserve only the equality arm's reachable blocks, stopping at the
            // immediate join with its unequal arm. No enclosing gate is erased.
            var block = body.Blocks[branch.Block];
            if (block.Next.Count != 2) return new();
            int equal = branch.Op.StartsWith("beq", StringComparison.Ordinal) ? block.Next[0] : block.Next[1];
            var region = body.ControlledRegion(branch.Block);
            var included = new HashSet<int>(); var pending = new Stack<int>(); pending.Push(equal);
            while (pending.Count > 0)
            {
                int next = pending.Pop();
                if (next == branch.Block || !region.Contains(next) || !included.Add(next)) continue;
                foreach (int successor in body.Blocks[next].Next) pending.Push(successor);
            }
            return included;
        }

        private void Inspect(int node, MethodBase method, int depth, HashSet<FieldInfo>? focus)
        {
            var body = Read(method);
            if (body is null)
            {
                var refused = CompactMethod(MethodSourceIdentitySafe(method), method);
                refused["id"] = node; refused["coverage"] = "unsupported_method_body_or_source_bound";
                refused["reason"] = readFailures.GetValueOrDefault(method, "source_scan_method_limit");
                nodes[node] = refused; Gap("unsupported_method_body_or_source_bound"); return;
            }
            var statements = body.Statements.Where(v => v.Op != "stloc").ToArray();
            if (nativeStatements.TryGetValue(method, out var selectedOffsets)) statements = statements.Where(v => selectedOffsets.Contains(v.At)).ToArray();
            else if (focus is not null)
            {
                if (method is ConstructorInfo constructor && constructor.IsStatic)
                {
                    statements = statements.Where(v => v.Op == "stsfld" && v.Operand is FieldInfo f && focus.Contains(f)).ToArray();
                    var allocations = statements.SelectMany(v => v.Inputs).SelectMany(body.Definitions).Where(v => v.Op == "newobj").Select(v => v.Id).ToHashSet();
                    statements = statements.Concat(body.Statements.Where(v => v.Op == "stfld" && v.Inputs.Count > 0
                        && body.Definitions(v.Inputs[0]).Any(a => allocations.Contains(a.Id)))).ToArray();
                }
                else
                {
                // Keep data and control dependencies of matching field consumers;
                // no unconditional numeric interpretation is attached to slices.
                var matchingBlocks = body.Values.Values.Where(v => v.Operand is FieldInfo f && focus.Contains(f)
                    || v.Operand is MethodBase helper && ReadsFields(helper, focus, new HashSet<MethodBase>(), 0, method.Module.Assembly))
                    .Select(v => v.Block).ToHashSet();
                var reached = new HashSet<int>(matchingBlocks);
                foreach (int block in matchingBlocks) reached.UnionWith(body.ControlledRegion(block));
                statements = statements.Where(v => reached.Contains(v.Block)).ToArray();
                }
            }
            // Bound individual slices too, so one large method cannot erase
            // every other node in the parent graph. Refusal is explicit.
            var selectedStatements = statements;
            var row = CompactMethod(body.Project(selectedStatements), method, body);
            if (row.ToJsonString().Length > 6500) row = CompactMethod(body.Project(selectedStatements, controlLimit: 8), method, body);
            if (row.ToJsonString().Length > 6500) row = CompactMethod(body.Project(selectedStatements, controlLimit: 0), method, body);
            while (row.ToJsonString().Length > 6500 && selectedStatements.Length > 1)
            {
                int Priority(ParentSourceMethod.Value value) => value.Operand is MethodInfo call
                    && (call.DeclaringType == typeof(Projectile) && call.Name is "NewProjectile" or "NewProjectileDirect"
                        || (call.DeclaringType == typeof(NPC) || call.DeclaringType == typeof(Player)) && call.Name == "AddBuff") ? 0
                    : value.Op.StartsWith("stind", StringComparison.Ordinal) || value.Op is "stfld" or "stsfld" or "stobj" or "stelem.ref" ? 1
                    : value.Op == "ret" ? 2 : value.Op is "call" or "callvirt" ? 3 : 4;
                selectedStatements = selectedStatements.OrderBy(Priority).ThenBy(v => v.At)
                    .Take(Math.Max(1, selectedStatements.Length / 2)).OrderBy(v => v.At).ToArray();
                row = CompactMethod(body.Project(selectedStatements, controlLimit: 0), method, body);
            }
            if (row.ToJsonString().Length > 6500)
            {
                row = CompactMethod(MethodSourceIdentitySafe(method), method);
                row["coverage"] = "source_slice_exceeds_method_character_bound";
                Gap("method_character_bound");
            }
            else if (selectedStatements.Length != statements.Length)
            {
                row["omittedStatementCount"] = statements.Length - selectedStatements.Length;
                Gap("method_statement_slice_bound");
            }
            if (row["unresolvedEnclosingBranchCount"] is not null) Gap("control_dependency_slice_bound");
            row["id"] = node;
            nodes[node] = row;
            var selectedValues = row["values"]?.AsObject().Select(pair => pair.Key).ToHashSet() ?? new HashSet<string>();
            foreach (var value in body.Values.Values.Where(v => selectedValues.Contains(v.Id)))
            {
                if (value.Operand is FieldInfo field && (value.Op is "stfld" or "stsfld" or "ldflda" or "ldsflda" || value.Op.StartsWith("ldsfld", StringComparison.Ordinal)))
                {
                    watched.Add(field);
                    if (value.Op == "ldsfld" && field.DeclaringType?.Assembly != typeof(NPC).Assembly && field.DeclaringType?.TypeInitializer is { } initializer)
                        Edge(node, Add(initializer, depth + 1, new HashSet<FieldInfo> { field }), "static_initializer_source; current_static_value_not_read", value.At);
                }
                if (value.Operand is not MethodBase call) continue;
                if (call is MethodInfo info && info.DeclaringType == typeof(Projectile) && info.Name is "NewProjectile" or "NewProjectileDirect")
                    FollowIdentity(body, value, info, "Type", "projectile", node);
                else if (call is MethodInfo addBuff && addBuff.Name == "AddBuff" && (addBuff.DeclaringType == typeof(NPC) || addBuff.DeclaringType == typeof(Player)))
                    FollowIdentity(body, value, addBuff, "type", addBuff.DeclaringType == typeof(NPC) ? "npc" : "player", node);
                else if ((call.DeclaringType?.Assembly == method.DeclaringType?.Assembly && call.DeclaringType?.Assembly != typeof(NPC).Assembly
                    || nativeProjectileMethods.Contains(method) && call.DeclaringType == typeof(Projectile))
                    && !call.ContainsGenericParameters && call.GetMethodBody() is not null)
                {
                    if (nativeProjectileMethods.Contains(method)) nativeProjectileMethods.Add(call);
                    // Virtual targets may be overridden at runtime. Keep the
                    // declared body as a candidate and preserve callsite inputs.
                    if (!callers.TryGetValue(call, out var contexts)) callers[call] = contexts = new();
                    bool newContext = !contexts.Any(c => c.Body.Method == body.Method && c.Call.At == value.At);
                    if (newContext) contexts.Add((body, value));
                    bool alreadyInspected = admitted.TryGetValue(MethodKey(call), out int priorNode);
                    int? destination = Add(call, depth + 1);
                    if (newContext && alreadyInspected && depth < DepthLimit)
                        pending.Enqueue((call, priorNode, depth + 1, focuses[MethodKey(call)]));
                    Edge(node, destination, value.Op == "callvirt" ? "declared_virtual_helper_candidate" : "helper_source",
                        value.At, new JsonArray(value.Inputs.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()));
                }
            }
        }

        private void FollowIdentity(ParentSourceMethod body, ParentSourceMethod.Value call, MethodInfo method, string parameterName, string receiver, int node)
        {
            int parameter = Array.FindIndex(method.GetParameters(), p => string.Equals(p.Name, parameterName, StringComparison.OrdinalIgnoreCase));
            int slot = parameter + (method.IsStatic ? 0 : 1);
            if (parameter < 0 || slot >= call.Inputs.Count) { Edge(node, null, "identity_request", call.At, unresolved: "unsupported_request_signature"); return; }
            bool resolved = false;
            foreach (var definition in IdentityDefinitions(body, call.Inputs[slot], new HashSet<string>(), 0))
            {
                int? id = definition.Op == "const" && definition.Operand is int literal ? literal : null;
                if (definition.Operand is MethodInfo generic && generic.DeclaringType == typeof(ModContent) && generic.IsGenericMethod
                    && generic.GetParameters().Length == 0 && generic.Name == (receiver == "projectile" ? "ProjectileType" : "BuffType"))
                {
                    Type type = generic.GetGenericArguments()[0];
                    if (receiver == "projectile")
                    {
                        for (int candidate = ProjectileID.Count; candidate < ProjectileLoader.ProjectileCount; candidate++)
                            if (ProjectileLoader.GetProjectile(candidate)?.GetType() == type) { id = candidate; break; }
                    }
                    else for (int candidate = BuffID.Count; candidate < BuffLoader.BuffCount; candidate++)
                        if (BuffLoader.GetBuff(candidate)?.GetType() == type) { id = candidate; break; }
                }
                if (id is null) continue;
                resolved = true;
                if (receiver == "projectile") Projectile(id.Value, node, call.At, "conditional_projectile_spawn_candidate");
                else Buff(id.Value, receiver, node, call.At);
            }
            if (!resolved) Edge(node, null, receiver == "projectile" ? "projectile_spawn" : "buff_request", call.At,
                JsonValue.Create(call.Inputs[slot]), "identity_requires_helper_or_runtime_expression; see_source_values");
        }

        private IEnumerable<ParentSourceMethod.Value> IdentityDefinitions(ParentSourceMethod body, string id, HashSet<string> seen, int depth,
            (ParentSourceMethod Body, ParentSourceMethod.Value Call)? binding = null)
        {
            if (depth > DepthLimit || !seen.Add(MethodKey(body.Method) + ":" + id + ":" + binding?.Call.At)) yield break;
            foreach (var value in body.Definitions(id))
            {
                if (value.Op == "ldarg" && value.Operand is int argument)
                {
                    var contexts = binding is { } bound ? new[] { bound }
                        : callers.TryGetValue(body.Method, out var calls) ? calls.ToArray() : Array.Empty<(ParentSourceMethod Body, ParentSourceMethod.Value Call)>();
                    foreach (var context in contexts)
                        if (argument < context.Call.Inputs.Count)
                            foreach (var origin in IdentityDefinitions(context.Body, context.Call.Inputs[argument], seen, depth + 1)) yield return origin;
                }
                else if (value.Operand is MethodInfo helper && value.Op == "call" && helper.DeclaringType != typeof(ModContent)
                    && helper.DeclaringType?.Assembly == body.Method.DeclaringType?.Assembly && helper.DeclaringType?.Assembly != typeof(NPC).Assembly
                    && Read(helper) is { } source)
                {
                    foreach (var ret in source.Statements.Where(v => v.Op == "ret" && v.Inputs.Count == 1))
                        foreach (var origin in IdentityDefinitions(source, ret.Inputs[0], seen, depth + 1, (body, value))) yield return origin;
                }
                else yield return value;
            }
        }

        private void Consumers()
        {
            ReadRoster();
            foreach (var owner in consumers.Where(o => o.Base != typeof(GlobalBuff)).Distinct())
                foreach (MethodInfo method in Overrides(owner.Type, owner.Base))
                {
                    if (admitted.ContainsKey(MethodKey(method))) continue;
                    var body = Read(method);
                    if (body is null) { Gap("consumer_roster_contains_unreadable_source"); continue; }
                    var references = body.Values.Values.Where(v => v.Op is "ldfld" or "ldsfld" or "ldflda" or "ldsflda")
                        .Select(v => v.Operand).OfType<FieldInfo>().Where(watched.Contains).ToHashSet();
                    if (references.Count == 0)
                    {
                        if (!ReadsFields(method, watched, new HashSet<MethodBase>(), 0, method.Module.Assembly)) continue;
                        references.UnionWith(watched);
                    }
                    int? node = Add(method, 0, references);
                    Edge(null, node, "registered_field_consumer_candidate", context: new JsonArray(references.OrderBy(SourceMember).Select(f => (JsonNode?)JsonValue.Create(SourceMember(f))).ToArray()),
                        unresolved: node is null ? "graph_limit" : null);
                }
        }

        private bool ReadsFields(MethodBase method, HashSet<FieldInfo> fields, HashSet<MethodBase> seen, int depth, Assembly assembly)
        {
            if (depth > DepthLimit || method.Module.Assembly != assembly || method.Module.Assembly == typeof(NPC).Assembly
                || !seen.Add(method) || Read(method) is not { } body) return false;
            if (body.Values.Values.Any(v => v.Operand is FieldInfo field && fields.Contains(field)
                && v.Op is "ldfld" or "ldsfld" or "ldflda" or "ldsflda")) return true;
            return body.Values.Values.Select(v => v.Operand).OfType<MethodBase>()
                .Any(helper => ReadsFields(helper, fields, seen, depth + 1, assembly));
        }

        internal JsonObject Finish()
        {
            int previous = -1;
            while (previous != watched.Count || pending.Count > 0)
            {
                while (pending.Count > 0)
                {
                    var next = pending.Dequeue();
                    try { Inspect(next.Node, next.Method, next.Depth, next.Focus); }
                    catch (Exception error) when (error is not OutOfMemoryException)
                    {
                        var failure = CompactMethod(MethodSourceIdentitySafe(next.Method), next.Method);
                        failure["id"] = next.Node; failure["coverage"] = "unsupported_source_projection";
                        nodes[next.Node] = failure; Gap("unsupported_source_projection");
                    }
                }
                previous = watched.Count;
                Consumers();
            }
            var result = new JsonObject
            {
                ["source"] = "parent_reachable_compiled_source_graph", ["version"] = 1,
                ["roots"] = roots, ["nodes"] = nodes, ["members"] = members, ["modules"] = modules, ["edges"] = edges, ["unresolved"] = gaps,
                ["scope"] = "Read-only source, never inherited execution or final stats/DPS. values: [IL opcode, operand, input IDs, block]. {member:N}/node.method reference members[N]; module references modules[N]. blocks: [offset, successors, branch-value ID, required enclosing branch IDs]; targets outside this slice stay unresolved. ldloc/predecessor definitions are alternatives, not independent rolls. Helpers bind caller inputs to argument slots (instance this=0). All statements require control to reach their offsets. Roots, virtual bodies and registered globals/players are dispatch candidates; current immunity registrations are not target admission. Native units/operators are not final stat multipliers. No hooks/helpers/getters/constructors ran. Runtime detours, missing edges and omitted source remain unknown.",
                ["limits"] = new JsonObject { ["nodes"] = NodeLimit, ["edges"] = EdgeLimit, ["helperDepth"] = DepthLimit, ["characters"] = CharacterLimit },
            };
            int removed = 0;
            // Compact metadata identities too: observations reference one exact
            // member, not repeated signatures or a loaded-content registry.
            PruneMembers();
            while (result.ToJsonString().Length > CharacterLimit)
            {
                // Preserve the identity and refusal of a large optional source
                // node before dropping small parent/helper observations.
                var candidate = nodes.OfType<JsonObject>().Where(n => n["values"] is JsonObject)
                    .OrderByDescending(n => members[n["method"]!.GetValue<int>()]!["module"]!.GetValue<int>() == Module(typeof(NPC).Module))
                    .ThenByDescending(n => n.ToJsonString().Length).FirstOrDefault();
                if (candidate is null) break;
                int id = candidate["id"]!.GetValue<int>();
                nodes[id] = new JsonObject { ["id"] = id, ["method"] = candidate["method"]!.DeepClone(),
                    ["sha256"] = candidate["sha256"]?.DeepClone(), ["coverage"] = "source_character_bound" };
                foreach (JsonObject edge in edges.OfType<JsonObject>().Where(e => e["from"]?.GetValue<int>() == id).ToArray()) edges.Remove(edge);
                removed++; PruneMembers();
            }
            while (result.ToJsonString().Length > CharacterLimit && nodes.Count > 0)
            {
                int last = nodes.Count - 1;
                nodes.RemoveAt(last); removed++;
                foreach (JsonObject edge in edges.OfType<JsonObject>().Where(e => e["to"]?.GetValue<int>() == last).ToArray())
                { edge.Remove("to"); edge["unresolved"] = "source_character_bound"; }
                foreach (JsonObject edge in edges.OfType<JsonObject>().Where(e => e["from"]?.GetValue<int>() == last).ToArray()) edges.Remove(edge);
                foreach (JsonObject root in roots.OfType<JsonObject>().Where(r => r["node"]?.GetValue<int>() == last).ToArray())
                { root.Remove("node"); root["unresolved"] = "source_character_bound"; }
                PruneMembers();
            }
            if (removed > 0) { Gap("source_character_bound"); result["omittedNodeCount"] = removed; }
            result["completeness"] = gaps.Count == 0 ? "bounded_source_graph; runtime_dispatch_unknown" : "partial_source_graph";
            return result;
        }
    }

    private static JsonObject MethodSourceIdentitySafe(MethodBase method)
    {
        try { return MethodSourceIdentity(method); }
        catch { return new JsonObject { ["method"] = SourceMember(method), ["sourceModuleVersionId"] = method.Module.ModuleVersionId.ToString() }; }
    }
}
