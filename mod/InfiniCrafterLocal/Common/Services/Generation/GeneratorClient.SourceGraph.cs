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
        var input = CaptureSourceGraphItem(item);
        JsonObject? observations = nativeFacts?.DeepClone().AsObject();
        var graph = new ParentSourceGraph();
        graph.ReadRoster();
        JsonObject Analyze()
        {
            graph.Item(input);
            if (observations is not null) graph.ObservedBuffs(observations);
            return graph.Finish();
        }
        return currentParentAnalysis is { } analysis ? analysis.Defer(Analyze) : Analyze();
    }

    private sealed record SourceGraphItem(Type? ModItem, Type[] Globals, bool GlobalsUnavailable,
        int Shoot, int Buff, Type? Tile, Type[] GlobalTiles, bool TilesUnavailable);

    private static SourceGraphItem CaptureSourceGraphItem(Item item)
    {
        var globals = new List<Type>(); Type[] tiles = Array.Empty<Type>();
        bool globalsUnavailable = false, tilesUnavailable = false;
        try { foreach (var global in item.Globals) globals.Add(global.GetType()); }
        catch { globalsUnavailable = true; }
        Type? tile = null;
        if (item.createTile >= TileID.Dirt)
        {
            tile = TileLoader.GetTile(item.createTile)?.GetType();
            try { tiles = ModContent.GetContent<GlobalTile>().Select(global => global.GetType()).ToArray(); }
            catch { tilesUnavailable = true; }
        }
        return new(item.ModItem?.GetType(), globals.ToArray(), globalsUnavailable, item.shoot, item.buffType,
            tile, tiles, tilesUnavailable);
    }

    // Shared native identity-window recognizer. It selects source syntax only;
    // entry, hooks and any opaque/non-identity predicates remain unresolved.
    private static IEnumerable<(string Field, int Literal, int Guard, AmmoIl[] Code)> ProjectileIdentityWindows(List<AmmoIl> code, int type, int style, Action<string>? gap = null, bool meaningfulBudget = false)
    {
        for (int n = 0; n + 4 < code.Count; n++)
        {
            if (code[n].Op != "ldarg" || !Equals(code[n].Arg, 0)
                || code[n + 1].Op != "ldfld" || code[n + 1].Arg is not FieldInfo field || field.DeclaringType != typeof(Projectile)
                || code[n + 2].Op != "const" || code[n + 2].Arg is not int literal
                || !(field.Name == "type" && literal == type || field.Name == "aiStyle" && literal == style)
                || code[n + 3].Op is not ("bne.un" or "bne.un.s" or "beq" or "beq.s")
                || code[n + 3].Arg is not int destination) continue;
            if (destination <= code[n + 3].Offset)
            { gap?.Invoke("identity_window_nonforward_branch_unsupported"); continue; }
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
            // The broad source graph keeps its raw1024 budget. Narrow attack
            // observation can admit nop-padded windows without removing offsets.
            int rawLimit = meaningfulBudget ? 4096 : 1024;
            var window = code.Skip(n).Take(4).Concat(code.Skip(start).TakeWhile(i => i.Offset < end)).Take(rawLimit + 1).ToArray();
            if (window.Length > rawLimit)
            { gap?.Invoke("identity_window_raw_instruction_bound"); continue; }
            if (meaningfulBudget)
            {
                // Inline AI regions need not be split into a parameterless helper.
                // Bound actual CFG work within the existing raw window limit,
                // rather than refusing a long straight-line source by its length.
                // Branch targets count even when repeated or outside the slice;
                // none are discarded to make a region fit the admission budget.
                var targets = new HashSet<int>();
                int flowWork = window.Count(i => i.Op != "nop");
                foreach (var instruction in window)
                {
                    if (instruction.Op == "switch" && instruction.Arg is int[] arms)
                    { flowWork += 8 + arms.Length; targets.UnionWith(arms); }
                    else if (instruction.Arg is int target && (instruction.Op.StartsWith("b", StringComparison.Ordinal) || instruction.Op.StartsWith("leave", StringComparison.Ordinal)))
                    { flowWork += 8; targets.Add(target); }
                }
                if (targets.Count > 256 || flowWork > 4096)
                { gap?.Invoke("identity_window_control_flow_work_bound"); continue; }
            }
            yield return (field.Name, literal, code[n + 3].Offset, window);
        }
    }

    private sealed partial class ParentSourceGraph
    {
        private const int NodeLimit = 48, EdgeLimit = 192, DepthLimit = 6, CharacterLimit = 40000;
        private const int DiscoveryNodeLimit = 256, DiscoveryEdgeLimit = 1024;
        private const int CatalogCoverageReserve = 320;
        private readonly JsonArray nodes = new(), edges = new(), roots = new(), gaps = new();
        private readonly JsonArray members = new(), modules = new();
        private readonly Dictionary<string, int> memberIndices = new(StringComparer.Ordinal);
        private readonly Dictionary<MemberInfo, int> reflectedMemberIndices = new();
        private readonly Dictionary<Guid, int> moduleIndices = new();
        private readonly Dictionary<string, int> admitted = new(StringComparer.Ordinal);
        private readonly Dictionary<string, HashSet<FieldInfo>?> focuses = new(StringComparer.Ordinal);
        private readonly Dictionary<MethodBase, HashSet<int>> nativeStatements = new();
        private readonly Queue<(MethodBase Method, int Node, int Depth, HashSet<FieldInfo>? Focus)> pending = new();
        private readonly HashSet<(int Id, string Receiver)> buffs = new();
        private readonly HashSet<int> projectiles = new();
        private readonly HashSet<FieldInfo> watched = new(), specificState = new();
        private readonly HashSet<string> reasons = new(StringComparer.Ordinal);
        private readonly Dictionary<MethodBase, ParentSourceMethod?> inspected = new();
        private readonly Dictionary<MethodBase, string> readFailures = new();
        private readonly Dictionary<MethodBase, List<AmmoIl>> nativeCode = new();
        private readonly Dictionary<MethodBase, Dictionary<int, int>> nativeNext = new();
        private readonly HashSet<MethodBase> nativeProjectileMethods = new();
        private readonly Dictionary<string, List<(ParentSourceMethod Body, ParentSourceMethod.Value Call, SourceInvocation Invocation)>> callers = new();
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
            if (reflectedMemberIndices.TryGetValue(member, out int existing)) return existing;
            string key = member.Module.ModuleVersionId + ":" + member.MetadataToken + ":" + SourceMember(member);
            if (memberIndices.TryGetValue(key, out existing)) { reflectedMemberIndices[member] = existing; return existing; }
            int id = members.Count; memberIndices[key] = id; reflectedMemberIndices[member] = id;
            var row = new JsonObject { ["name"] = SourceMember(member), ["module"] = Module(member.Module) };
            if (member is FieldInfo field) row["type"] = field.FieldType.FullName;
            if (member is MethodInfo method) row["returns"] = method.ReturnType.FullName;
            members.Add(row); return id;
        }
        private JsonObject CompactMethod(JsonObject row, MethodBase method, ParentSourceMethod? body = null)
            => CompactSourceMethod(row, method, body, Member);
        private static readonly HashSet<string> ItemEvents = new(StringComparer.Ordinal)
        {
            "AltFunctionUse", "CanUseItem", "CanShoot", "UseItem", "UseStyle", "HoldItem", "HoldStyle", "UseAnimation",
            "ModifyWeaponDamage", "ModifyWeaponKnockback",
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
            "ModifyWeaponDamage", "ModifyWeaponKnockback",
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
            // Only complete method bodies are reusable. Native identity slices
            // and their CFG boundaries are specific to this graph/parent.
            ParentSourceGraphCache? cache = activeParentSourceGraphCache ?? currentParentAnalysis?.SourceCache;
            if (cache is not null && cache.TryGet(method, out object? cached, out string? refusal))
            {
                if (refusal is not null) readFailures[method] = refusal;
                return inspected[method] = (ParentSourceMethod?)cached;
            }
            try
            {
                var body = new ParentSourceMethod(method);
                cache?.Remember(method, body, null, body.Code.Count, body.Blocks.Count);
                return inspected[method] = body;
            }
            catch (Exception error) when (error is not OutOfMemoryException)
            {
                inspected[method] = null;
                string reason = error is NotSupportedException ? error.Message : error.GetType().Name;
                readFailures[method] = reason;
                // Unsupported IL is stable for this exact MethodBase in a dump.
                // Do not retain transient reflection/runtime failures.
                if (error is NotSupportedException) cache?.Remember(method, null, reason, 0, 0);
                return null;
            }
        }
        private void Edge(int? from, int? to, string kind, int? at = null, JsonNode? context = null, string? unresolved = null)
        {
            if (edges.Count >= DiscoveryEdgeLimit) { Gap("discovery_edge_limit"); return; }
            var edge = new JsonObject { ["kind"] = kind };
            if (from is not null) edge["from"] = from;
            if (to is not null) edge["to"] = to;
            if (at is not null) edge["at"] = at;
            if (context is not null) edge["context"] = context;
            if (unresolved is not null) edge["unresolved"] = unresolved;
            if (edgeKeys.Add(edge.ToJsonString())) edges.Add(edge);
        }
        private int? Add(MethodBase method, int depth, HashSet<FieldInfo>? focus = null, SourceInvocation invocation = default)
        {
            string key = InvocationKey(method, invocation);
            if (admitted.TryGetValue(key, out int existing))
            {
                priorities[existing] = Math.Min(priorities[existing], currentPriority);
                RememberPath(existing);
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
            if (nodes.Count >= DiscoveryNodeLimit) { Gap("discovery_node_limit"); return null; }
            string methodKey = MethodKey(method);
            if (!methodInvocations.TryGetValue(methodKey, out var contexts)) methodInvocations[methodKey] = contexts = new();
            if (contexts.Count >= 16 && !contexts.Contains(invocation)) { Gap("invocation_context_limit"); return null; }
            contexts.Add(invocation);
            int id = nodes.Count;
            invocations[id] = invocation;
            methodByNode[id] = method;
            priorities[id] = currentPriority;
            RememberPath(id);
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
                int? node = Add(method, 0, invocation: Captured(type));
                if (node is null) { omittedDiscoveryRoots++; continue; }
                if (baseType == typeof(ModItem) || baseType == typeof(ModProjectile) || baseType == typeof(ModBuff) || baseType == typeof(ModTile))
                    principalNodes.Add(node.Value);
                roots.Add(new JsonObject { ["node"] = node, ["event"] = method.Name, ["owner"] = owner,
                    ["receiver"] = receiver });
            }
        }
        private void Roster<T>(Type baseType) where T : class, ILoadable
        {
            try
            {
                foreach (Type type in SourceSnapshotOnMain(() => ModContent.GetContent<T>().Select(p => p.GetType()).ToArray())) consumers.Add((type, baseType));
            }
            catch { Gap("registered_" + baseType.Name + "_roster_unavailable"); }
        }
        internal void ReadRoster()
        {
            if (rosterRead) return;
            rosterRead = true;
            Roster<GlobalNPC>(typeof(GlobalNPC)); Roster<ModPlayer>(typeof(ModPlayer)); Roster<GlobalBuff>(typeof(GlobalBuff));
        }

        internal void Item(SourceGraphItem item)
        {
            if (item.ModItem is not null) Hooks(item.ModItem, typeof(ModItem), ItemEvents, "parent_ModItem", "event_signature");
            foreach (Type global in item.Globals.OrderBy(t => t.FullName, StringComparer.Ordinal))
                Defer(() => Hooks(global, typeof(GlobalItem), ItemEvents, "attached_GlobalItem", "event_signature"));
            if (item.GlobalsUnavailable) Gap("attached_GlobalItem_roster_unavailable");
            ReadRoster();
            foreach (var owner in consumers.Where(o => o.Base == typeof(ModPlayer)).OrderBy(o => o.Type.FullName, StringComparer.Ordinal))
                Defer(() => Hooks(owner.Type, owner.Base, PlayerEvents, "registered_ModPlayer_candidate", "event_signature"));
            if (item.Shoot > ProjectileID.None) Projectile(item.Shoot, null, null, "item.shoot_field_candidate");
            if (item.Buff > InfiniTerrariaSentinels.NoBuffType) Buff(item.Buff, "player", null, null);
            if (item.Tile is not null) Hooks(item.Tile, typeof(ModTile), new HashSet<string>(StringComparer.Ordinal)
                { "NearbyEffects", "RightClick", "HitWire", "PlaceInWorld", "CanPlace", "KillMultiTile", "FloorVisuals" }, "parent_placed_tile", "placed_tile_conditions_not_evaluated");
            foreach (Type global in item.GlobalTiles.OrderBy(t => t.FullName, StringComparer.Ordinal))
                Defer(() => Hooks(global, typeof(GlobalTile), new HashSet<string>(StringComparer.Ordinal)
                    { "NearbyEffects", "PlaceInWorld", "HitWire", "CanPlace" }, "registered_GlobalTile_candidate", "placed_tile_conditions_not_evaluated"));
            if (item.TilesUnavailable) Gap("registered_GlobalTile_roster_unavailable");
            if (nodes.Count == 0 && item.ModItem is null) Gap("no_parent_mod_override_observed; native_catalog_coverage_is_separate");
        }

        internal void ObservedBuffs(JsonNode? observation, string receiver = "npc")
        {
            if (observation is JsonObject row)
            {
                // Structured source expressions can also have a receiver; only
                // a literal recipient token belongs to a buff observation.
                string target = row["receiver"] is JsonValue recipient && recipient.TryGetValue<string>(out string? observed)
                    ? observed ?? receiver : receiver;
                if (row["buffId"] is JsonValue value && value.TryGetValue<int>(out int id)) Buff(id, target, null, null);
                foreach (var pair in row) ObservedBuffs(pair.Value, pair.Key == "nativeBuffEffectReference" ? "player" : target);
            }
            else if (observation is JsonArray array) foreach (JsonNode? value in array) ObservedBuffs(value, receiver);
        }

        private void Projectile(int id, int? from, int? at, string kind)
        {
            // An already visited identity uses this graph's first snapshot.
            // Keep every callsite edge without another frame-long rendezvous.
            if (projectiles.Contains(id))
            { Edge(from, null, kind, at, JsonValue.Create(id), "already_visited_projectile_identity"); return; }
            var snapshot = SourceSnapshotOnMain(() =>
            {
                bool registered = id > 0 && id < ProjectileLoader.ProjectileCount;
                ContentSamples.ProjectilesByType.TryGetValue(id, out var sample);
                var owners = new List<(Type Type, Type Base)>();
                bool globalsUnavailable = false;
                JsonNode? status = null;
                if (registered && sample is not null)
                {
                    status = JsonSerializer.SerializeToNode(VerifiedSourceHitStatusReference(sample,
                        HitStatusSourceCertificate.Value, typeof(Projectile).Module.ModuleVersionId.ToString()), WireJsonOptions);
                    if (sample.ModProjectile is not null) owners.Add((sample.ModProjectile.GetType(), typeof(ModProjectile)));
                    try { foreach (var global in sample.Globals) owners.Add((global.GetType(), typeof(GlobalProjectile))); }
                    catch { globalsUnavailable = true; }
                }
                return (Registered: registered, Available: sample is not null, Owners: owners.ToArray(),
                    Status: status, GlobalsUnavailable: globalsUnavailable,
                    Vanilla: sample?.ModProjectile is null, Type: sample?.type ?? id, Style: sample?.aiStyle ?? 0);
            });
            if (!snapshot.Registered) { Edge(from, null, kind, at, unresolved: "projectile_identity_not_registered"); return; }
            if (!snapshot.Available) { Edge(from, null, kind, at, JsonValue.Create(id), "registered_projectile_sample_unavailable"); return; }
            if (!projectiles.Add(id)) { Edge(from, null, kind, at, JsonValue.Create(id), "already_visited_projectile_identity"); return; }
            if (snapshot.Status is not null) ObservedBuffs(snapshot.Status);
            if (snapshot.GlobalsUnavailable) Gap("child_attached_GlobalProjectile_roster_unavailable");
            var owners = snapshot.Owners;
            foreach (var owner in owners.Distinct())
                foreach (var method in Overrides(owner.Type, owner.Base).Where(m => ProjectileEvents.Contains(m.Name)))
                {
                    void Admit()
                    {
                        int? node = Add(method, 0, invocation: Captured(owner.Type));
                        if (node is int primary && owner.Base == typeof(ModProjectile)) principalNodes.Add(primary);
                        Edge(from, node, kind, at, new JsonObject { ["projectileId"] = id, ["event"] = method.Name }, node is null ? "graph_limit" : null);
                    }
                    if (owner.Base == typeof(GlobalProjectile)) Defer(Admit);
                    else Admit();
                }
            if (snapshot.Vanilla) NativeProjectile(snapshot.Type, snapshot.Style, from, at);
        }

        private void NativeProjectile(int type, int style, int? from, int? at)
        {
            foreach (string name in new[] { "VanillaAI", "Kill" })
            {
                MethodInfo? method = typeof(Projectile).GetMethod(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (method is null) continue;
                try
                {
                    if (!nativeCode.TryGetValue(method, out var code))
                    {
                        nativeCode[method] = code = AttackCode(method);
                        nativeNext[method] = code.Zip(code.Skip(1), (left, right) => (left.Offset, Next: right.Offset)).ToDictionary(p => p.Offset, p => p.Next);
                    }
                    var selected = new Dictionary<int, AmmoIl>();
                    // Exact type/AI-style equality fallthrough windows. Entry,
                    // missing predecessors and exits stay explicitly unresolved.
                    // No other branch arm is executed, selected or assumed true.
                    bool windowRefused = false;
                    foreach (var window in ProjectileIdentityWindows(code, type, style, reason => { windowRefused = true; Gap(reason); }))
                        foreach (var instruction in window.Code) selected[instruction.Offset] = instruction;
                    if (selected.Count == 0)
                    { Edge(from, null, "native_projectile_source", at, JsonValue.Create(type), windowRefused ? "native_identity_window_refused_in_" + name : "no_supported_type_or_aiStyle_equality_window_in_" + name); continue; }
                    var invocation = new SourceInvocation(typeof(Projectile), typeof(Projectile), type, style);
                    string invocationKey = InvocationKey(method, invocation);
                    nativeInvocationSlices.TryGetValue(invocationKey, out var prior);
                    if (prior is not null) foreach (var instruction in prior) selected[instruction.Offset] = instruction;
                    if (selected.Count > 4096) { Gap("native_projectile_source_window_limit"); continue; }
                    bool changed = prior is null || prior.Count != selected.Count;
                    nativeInvocationSlices[invocationKey] = selected.Values.OrderBy(i => i.Offset).ToList();
                    nativeProjectileMethods.Add(method);
                    if (changed) invocationBodies.Remove(invocationKey);
                    bool existing = admitted.TryGetValue(invocationKey, out int existingNode);
                    int? node = Add(method, 0, invocation: invocation);
                    if (node is int primary) principalNodes.Add(primary);
                    if (changed && existing) pending.Enqueue((method, existingNode, 0, null));
                    Edge(from, node, "certified_native_projectile_source_windows", at, new JsonObject
                        { ["projectileId"] = type, ["aiStyle"] = style, ["entryAndOmittedFlow"] = "unresolved" }, node is null ? "graph_limit" : null);
                }
                catch { Gap("native_projectile_source_outside_bound"); }
            }
        }

        private void Buff(int id, string receiver, int? from, int? at)
        {
            void RequestEdge() => Edge(from, null, "buff_request", at, new JsonObject { ["buffId"] = id, ["receiver"] = receiver,
                ["admission"] = "AddBuff_request_only; immunity_and_refresh_may_change_outcome" });
            if (buffs.Contains((id, receiver))) { RequestEdge(); return; }
            var snapshot = SourceSnapshotOnMain(() =>
            {
                bool registered = id > 0 && id < BuffLoader.BuffCount;
                Type? owner = registered ? BuffLoader.GetBuff(id)?.GetType() : null;
                int[]? related = null; bool unavailable = false;
                try { if (registered) related = BuffID.Sets.GrantImmunityWith[id]?.ToArray(); }
                catch { unavailable = true; }
                return (Registered: registered, Owner: owner, Related: related, Unavailable: unavailable);
            });
            if (!snapshot.Registered) { Edge(from, null, "buff_request", at, unresolved: "buff_identity_not_registered"); return; }
            RequestEdge();
            buffs.Add((id, receiver));
            if (snapshot.Owner is not null)
                foreach (var method in Overrides(snapshot.Owner, typeof(ModBuff)).Where(m => BuffEvents.Contains(m.Name)))
                {
                    if (method.Name != "SetStaticDefaults" && !method.GetParameters().Any(p => p.ParameterType == (receiver == "npc" ? typeof(NPC) : typeof(Player)))) continue;
                    int? node = Add(method, 0, invocation: Captured(snapshot.Owner));
                    if (node is int primary) principalNodes.Add(primary);
                    Edge(from, node, "requested_buff_implementation", at, new JsonObject { ["buffId"] = id, ["receiver"] = receiver }, node is null ? "graph_limit" : null);
                }
            else NativeBuff(id, receiver, from);
            // Read the actual loaded admission method, not a cached source certificate.
            {
                Type target = receiver == "npc" ? typeof(NPC) : typeof(Player);
                MethodInfo? admission = target.GetMethods(BindingFlags.Instance | BindingFlags.Public).FirstOrDefault(m => m.Name == "AddBuff");
                if (admission is not null)
                {
                    int priorPriority = currentPriority;
                    currentPriority = Math.Max(currentPriority, 2);
                    int? admissionNode = Add(admission, 0, new HashSet<FieldInfo>(target.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                        .Where(f => f.Name is "buffImmune" or "buffType" or "buffTime")));
                    currentPriority = priorPriority;
                    Edge(from, admissionNode, "native_buff_admission_and_refresh_source", at,
                        new JsonObject { ["buffId"] = id, ["receiver"] = receiver });
                }
            }
            ReadRoster();
            foreach (var owner in consumers.Where(o => o.Base == typeof(GlobalBuff)))
                foreach (var method in Overrides(owner.Type, owner.Base).Where(m => m.Name is "Update" or "ReApply"))
                {
                    if (!method.GetParameters().Any(p => p.ParameterType == (receiver == "npc" ? typeof(NPC) : typeof(Player)))) continue;
                    Defer(() =>
                    {
                        int? node = Add(method, 0);
                        Edge(from, node, "loaded_GlobalBuff_candidate", at, new JsonObject { ["buffId"] = id, ["receiver"] = receiver }, node is null ? "graph_limit" : null);
                    });
                }
            // Read only this buff's registered relationship, never the registry.
            try
            {
                var related = snapshot.Related;
                if (related is not null && related.Length > 0)
                    Edge(from, null, "loaded_immunity_relationship", at, new JsonObject { ["buffId"] = id,
                        ["grantImmunityWith"] = new JsonArray(related.Select(i => (JsonNode?)JsonValue.Create(i)).ToArray()),
                        ["scope"] = "current_registration; target_immunity_not_observed" });
            }
            catch { Gap("buff_immunity_relationship_unavailable"); }
            if (snapshot.Unavailable) Gap("buff_immunity_relationship_unavailable");
        }

        private void NativeBuff(int id, string receiver, int? from)
        {
            // Existing certificates remain authoritative. This is additional
            // source syntax for previously unsupported branches/consumers.
            if (BuffEffectSourceCertificate.Value is null) { Gap("native_buff_binary_certificate_unavailable"); return; }
            Type target = receiver == "npc" ? typeof(NPC) : typeof(Player);
            JsonObject known = SourceSnapshotOnMain(() => VerifiedNativeBuffEffectReference(id, receiver, BuffEffectSourceCertificate.Value));
            // Already delivered numeric fragments need not be copied into a
            // second catalog. Their exact native flags still seed loaded-mod
            // consumer discovery, including modifications of vanilla buffs.
            string knownJson = known.ToJsonString();
            foreach (var field in target.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                if (knownJson.Contains("\"" + target.FullName + "." + field.Name + "\"", StringComparison.Ordinal))
                { watched.Add(field); if (currentPriority < 2) specificState.Add(field); }
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
            foreach (FieldInfo field in selected) { watched.Add(field); if (currentPriority < 2) specificState.Add(field); }
            int? node = Add(method, 0, selected);
            if (node is int primary) principalNodes.Add(primary);
            if (node is int updated && previousCount > 0 && previousCount != prior.Count)
                pending.Enqueue((method, updated, 0, focuses[MethodKey(method)]));
            Edge(from, node, "certified_native_buff_source_slice", context: new JsonObject { ["buffId"] = id, ["receiver"] = receiver }, unresolved: node is null ? "graph_limit" : null);
            if (receiver == "npc")
                foreach (string consumer in new[] { "UpdateNPC_BuffApplyDOTs", "GetIncomingStrikeModifiers" })
                {
                    var candidate = typeof(NPC).GetMethod(consumer, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (candidate is not null)
                        Edge(from, Add(candidate, 0, selected), "native_buff_field_consumer_source",
                            context: new JsonObject { ["buffId"] = id, ["receiver"] = receiver });
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
            var body = ReadInvocation(method);
            if (body is null)
            {
                var refused = CompactMethod(MethodSourceIdentitySafe(method), method);
                refused["id"] = node; refused["coverage"] = "unsupported_method_body_or_source_bound";
                refused["reason"] = nativeIdentityReceipts.GetValueOrDefault(InvocationKey(method, currentInvocation))?["selectionUnavailable"]?.GetValue<string>()
                    ?? readFailures.GetValueOrDefault(method, "source_scan_method_limit");
                AddInvocation(refused, node);
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
                var matchingValues = body.Values.Values.Where(v => v.Operand is FieldInfo f && focus.Contains(f)
                    || v.Operand is MethodBase && ReferencedCallFields(body, v, focus, new HashSet<(MethodBase, Type?)>(), 0,
                        method.Module.Assembly, currentInvocation.Receiver).Count > 0).ToArray();
                // A compiler may materialize a condition through locals or a
                // stack join before branching on it. Follow forward data and
                // control dependencies, stopping each control arm at its join.
                // Every value, region and controlled block is visited once;
                // alias diamonds cannot multiply traversal work.
                var users = new Dictionary<string, List<ParentSourceMethod.Value>>(StringComparer.Ordinal);
                foreach (var value in body.Values.Values)
                    foreach (string input in value.Inputs)
                    {
                        if (!users.TryGetValue(input, out var list)) users[input] = list = new();
                        list.Add(value);
                    }
                var blockValues = body.Values.Values.GroupBy(value => value.Block)
                    .ToDictionary(group => group.Key, group => group.ToArray());
                var branches = body.Blocks.Values.Where(block => block.Next.Distinct().Count() > 1)
                    .ToDictionary(block => block.Code[^1].Offset.ToString(System.Globalization.CultureInfo.InvariantCulture), block => block.Start);
                var reached = matchingValues.Select(value => value.Block).ToHashSet();
                var visited = new HashSet<string>(StringComparer.Ordinal);
                var controlled = new HashSet<int>();
                var work = new Queue<ParentSourceMethod.Value>();
                void Enqueue(ParentSourceMethod.Value value)
                { if (visited.Add(value.Id)) work.Enqueue(value); }
                foreach (var value in matchingValues) Enqueue(value);
                while (work.Count > 0)
                {
                    currentParentAnalysis?.ThrowIfCancelled();
                    var value = work.Dequeue();
                    if (users.TryGetValue(value.Id, out var dependents))
                        foreach (var dependent in dependents) Enqueue(dependent);
                    if (!branches.TryGetValue(value.Id, out int branchBlock)) continue;
                    foreach (int block in body.ControlledRegion(branchBlock))
                    {
                        if (block == branchBlock || !controlled.Add(block)) continue;
                        reached.Add(block);
                        if (blockValues.TryGetValue(block, out var definitions))
                            foreach (var definition in definitions) Enqueue(definition);
                    }
                }
                statements = statements.Where(v => reached.Contains(v.Block) || visited.Contains(v.Id)).ToArray();
                }
            }
            // Discovery sees the source dependency closure, not a transport-sized
            // projection. Otherwise a large caller can hide every child before
            // the export budget has even selected which evidence to retain.
            // Each invocation has its own certified identity CFG. Keep that
            // CFG's reaching definitions too: mapping them back into the raw
            // dispatcher would reintroduce unrelated actor branches. Only the
            // existing strict selector may remove identity predicates; live
            // conditions and blocked identity reads remain source evidence.
            projections[node] = (body, statements);
            var identity = CompactMethod(MethodSourceIdentitySafe(method), method);
            identity["id"] = node; identity["coverage"] = "pending_export";
            AddInvocation(identity, node);
            nodes[node] = identity;
            foreach (var value in DiscoveryValues(body, statements))
            {
                if (value.Operand is FieldInfo field && (value.Op is "stfld" or "stsfld" or "ldflda" or "ldsflda" || value.Op.StartsWith("ldsfld", StringComparison.Ordinal)))
                {
                    bool modOwned = field.DeclaringType?.Assembly is { } ownerAssembly && ownerAssembly != typeof(NPC).Assembly
                        && ownerAssembly != typeof(Microsoft.Xna.Framework.Vector2).Assembly;
                    // A mutable mod static read can depend on a lifecycle updater,
                    // not just its initializer. Do not expand common engine reads
                    // or let unrelated general hooks promote their own state.
                    if (value.Op != "ldsfld" || currentPriority < 2 && modOwned && !field.IsInitOnly && !field.IsLiteral)
                    {
                        watched.Add(field);
                        // A specific mod-owned state slot is a stronger link
                        // than common engine storage such as Entity.velocity.
                        if (currentPriority < 2 && modOwned) specificState.Add(field);
                    }
                    if (value.Op == "ldsfld" && field.DeclaringType?.Assembly != typeof(NPC).Assembly && field.DeclaringType?.TypeInitializer is { } initializer)
                        Edge(node, Add(initializer, depth + 1, new HashSet<FieldInfo> { field }), "static_initializer_source; current_static_value_not_read", value.At);
                }
                if (value.Operand is not MethodBase call) continue;
                if (call is MethodInfo info && info.DeclaringType == typeof(Projectile) && info.Name is "NewProjectile" or "NewProjectileDirect")
                {
                    if (currentInvocation.NativeIdentityUnbound || nativeIdentityUnavailable.Contains(InvocationKey(method, currentInvocation)))
                        Edge(node, null, "projectile_spawn", value.At, unresolved: "native_actor_identity_unbound; source_only_candidate");
                    else FollowIdentity(body, value, info, "Type", "projectile", node);
                }
                else if (call is MethodInfo addBuff && addBuff.Name == "AddBuff" && (addBuff.DeclaringType == typeof(NPC) || addBuff.DeclaringType == typeof(Player)))
                {
                    if (currentInvocation.NativeIdentityUnbound || nativeIdentityUnavailable.Contains(InvocationKey(method, currentInvocation)))
                        Edge(node, null, "buff_request", value.At, unresolved: "native_actor_identity_unbound; source_only_candidate");
                    else FollowIdentity(body, value, addBuff, "type", addBuff.DeclaringType == typeof(NPC) ? "npc" : "player", node);
                }
                else if (call.DeclaringType?.Assembly == method.DeclaringType?.Assembly && call.DeclaringType?.Assembly != typeof(NPC).Assembly
                    || nativeProjectileMethods.Contains(method) && call.DeclaringType == typeof(Projectile))
                    FollowSourceCall(body, value, call, depth, node);
            }
        }

        private void FollowIdentity(ParentSourceMethod body, ParentSourceMethod.Value call, MethodInfo method, string parameterName, string receiver, int node)
        {
            int parameter = Array.FindIndex(method.GetParameters(), p => string.Equals(p.Name, parameterName, StringComparison.OrdinalIgnoreCase));
            int slot = parameter + (method.IsStatic ? 0 : 1);
            if (parameter < 0 || slot >= call.Inputs.Count) { Edge(node, null, "identity_request", call.At, unresolved: "unsupported_request_signature"); return; }
            bool resolved = false, unknownAlternative = false;
            foreach (var definition in IdentityDefinitions(body, call.Inputs[slot], new HashSet<string>(), 0, currentInvocation))
            {
                int? id = definition.Op == "const" && definition.Operand is int literal ? literal : null;
                if (definition.Operand is MethodInfo generic && generic.DeclaringType == typeof(ModContent) && generic.IsGenericMethod
                    && generic.GetParameters().Length == 0 && generic.Name == (receiver == "projectile" ? "ProjectileType" : "BuffType"))
                {
                    Type type = generic.GetGenericArguments()[0];
                    id = SourceSnapshotOnMain<int?>(() =>
                    {
                        if (receiver == "projectile")
                        {
                            for (int candidate = ProjectileID.Count; candidate < ProjectileLoader.ProjectileCount; candidate++)
                                if (ProjectileLoader.GetProjectile(candidate)?.GetType() == type) return candidate;
                        }
                        else for (int candidate = BuffID.Count; candidate < BuffLoader.BuffCount; candidate++)
                            if (BuffLoader.GetBuff(candidate)?.GetType() == type) return candidate;
                        return null;
                    });
                }
                if (id is null) { unknownAlternative = true; continue; }
                resolved = true;
                if (receiver == "projectile") Projectile(id.Value, node, call.At, "conditional_projectile_spawn_candidate");
                else Buff(id.Value, receiver, node, call.At);
            }
            if (!resolved || unknownAlternative) Edge(node, null, receiver == "projectile" ? "projectile_spawn" : "buff_request", call.At,
                JsonValue.Create(call.Inputs[slot]), "identity_requires_helper_or_runtime_expression; see_source_values");
        }

        private IEnumerable<ParentSourceMethod.Value> IdentityDefinitions(ParentSourceMethod body, string id, HashSet<string> seen, int depth,
            SourceInvocation invocation, (ParentSourceMethod Body, ParentSourceMethod.Value Call, SourceInvocation Invocation)? binding = null)
        {
            string bindingKey = binding is { } caller ? InvocationKey(caller.Body.Method, caller.Invocation) + ":" + caller.Call.At : "root";
            if (depth > DepthLimit || !seen.Add(InvocationKey(body.Method, invocation) + ":" + id + ":" + bindingKey))
            { yield return new ParentSourceMethod.Value { Op = "unresolved_identity_dependency_bound" }; yield break; }
            foreach (var value in body.Definitions(id))
            {
                if (value.Op == "ldarg" && value.Operand is int argument)
                {
                    var contexts = binding is { } bound ? new[] { bound }
                        : callers.TryGetValue(InvocationKey(body.Method, invocation), out var calls) ? calls.ToArray() : Array.Empty<(ParentSourceMethod Body, ParentSourceMethod.Value Call, SourceInvocation Invocation)>();
                    // A root hook argument is runtime data, not an absent arm.
                    // Keep it even when a sibling definition resolves to a literal.
                    if (contexts.Length == 0) yield return value;
                    foreach (var context in contexts)
                        if (argument < context.Call.Inputs.Count)
                            foreach (var origin in IdentityDefinitions(context.Body, context.Call.Inputs[argument], seen, depth + 1, context.Invocation)) yield return origin;
                        else yield return value;
                }
                else if (value.Operand is MethodInfo helper && value.Op == "call" && helper.DeclaringType != typeof(ModContent)
                    && helper.DeclaringType?.Assembly == body.Method.DeclaringType?.Assembly && helper.DeclaringType?.Assembly != typeof(NPC).Assembly
                    && Read(helper) is { } source)
                {
                    foreach (var ret in source.Statements.Where(v => v.Op == "ret" && v.Inputs.Count == 1))
                        foreach (var origin in IdentityDefinitions(source, ret.Inputs[0], seen, depth + 1,
                            invocation with { Receiver = !helper.IsStatic && CallsCapturedThis(body, value) ? invocation.Receiver : null }, (body, value, invocation))) yield return origin;
                }
                else yield return value;
            }
        }

        private void Consumers()
        {
            // With no field to follow, no registered method can contribute a
            // field-consumer edge. Avoid decompiling the whole mod roster.
            if (watched.Count == 0) return;
            ReadRoster();
            foreach (var owner in consumers.Where(o => o.Base != typeof(GlobalBuff)).Distinct())
                foreach (MethodInfo method in Overrides(owner.Type, owner.Base))
                {
                    SourceInvocation invocation = Captured(owner.Type);
                    string key = InvocationKey(method, invocation);
                    if (admitted.ContainsKey(key) && focuses[key] is null) continue;
                    var body = Read(method);
                    if (body is null) { Gap("consumer_roster_contains_unreadable_source"); continue; }
                    // A direct common-field read does not exclude a specific
                    // state read reached through a helper in the same hook.
                    var references = ReferencedFields(method, watched, new HashSet<(MethodBase, Type?)>(), 0,
                        method.Module.Assembly, owner.Type);
                    if (references.Count == 0) continue;
                    void AdmitConsumer()
                    {
                        int? node = Add(method, 0, references, invocation);
                        Edge(null, node, "registered_field_consumer_candidate", context: new JsonArray(references.OrderBy(SourceMember).Select(f => (JsonNode?)JsonValue.Create(SourceMember(f))).ToArray()),
                            unresolved: node is null ? "graph_limit" : null);
                    }
                    if (references.Overlaps(specificState))
                    {
                        int priorPriority = currentPriority;
                        currentPriority = Math.Min(currentPriority, 1);
                        AdmitConsumer();
                        currentPriority = priorPriority;
                    }
                    else if (admitted.ContainsKey(key)) AdmitConsumer();
                    else if (deferredConsumerFocus.TryGetValue(key, out var queued)) queued.UnionWith(references);
                    else
                    {
                        deferredConsumerFocus[key] = references;
                        Defer(AdmitConsumer);
                    }

                }
        }

        private HashSet<FieldInfo> ReferencedFields(MethodBase method, HashSet<FieldInfo> fields,
            HashSet<(MethodBase, Type?)> seen, int depth, Assembly assembly, Type? receiver)
        {
            var references = new HashSet<FieldInfo>();
            if (depth > DepthLimit || method.Module.Assembly != assembly || method.Module.Assembly == typeof(NPC).Assembly
                || !seen.Add((method, receiver)) || Read(method) is not { } body) return references;
            foreach (var value in body.Values.Values)
            {
                if (value.Operand is FieldInfo field && fields.Contains(field)
                    && value.Op is "ldfld" or "ldsfld" or "ldflda" or "ldsflda") references.Add(field);
                else if (value.Operand is MethodBase)
                    references.UnionWith(ReferencedCallFields(body, value, fields, seen, depth + 1, assembly, receiver));
            }
            return references;
        }

        private HashSet<FieldInfo> ReferencedCallFields(ParentSourceMethod body, ParentSourceMethod.Value call,
            HashSet<FieldInfo> fields, HashSet<(MethodBase, Type?)> seen, int depth, Assembly assembly, Type? receiver)
        {
            if (call.Operand is not MethodBase helper || helper.Module.Assembly != assembly
                || helper.Module.Assembly == typeof(NPC).Assembly) return new();
            // Discovery and focused slicing must agree with source-call dispatch.
            // A foreign receiver stays unknown; direct base calls keep their body.
            Type? boundReceiver = !helper.IsStatic && receiver is not null
                && helper.DeclaringType?.IsAssignableFrom(receiver) == true && CallsCapturedThis(body, call) ? receiver : null;
            MethodBase target = call.Op == "callvirt" && helper is MethodInfo { IsVirtual: true } method && boundReceiver is not null
                ? CapturedVirtualTarget(method, boundReceiver) ?? helper : helper;
            return ReferencedFields(target, fields, seen, depth, assembly, boundReceiver);
        }

        internal JsonObject Finish()
        {
            int previous = -1, previousSpecific = -1;
            bool generalDispatch = false;
            // Reach a fixed point over all three sources of work. A late field
            // consumer may itself discover a projectile's general hooks.
            while (pending.Count > 0 || deferred.Count > 0 || previous != watched.Count || previousSpecific != specificState.Count)
            {
                Drain();
                if (previous != watched.Count || previousSpecific != specificState.Count)
                {
                    previous = watched.Count;
                    previousSpecific = specificState.Count;
                    currentPriority = generalDispatch ? 2 : 1;
                    Consumers();
                    continue;
                }
                if (deferred.Count == 0) continue;
                generalDispatch = true;
                currentPriority = 2;
                var next = deferred.Dequeue();
                currentNode = next.Parent;
                next.Admit();
                currentNode = null;
            }
            return SelectExport();
        }

    }

    private static JsonObject MethodSourceIdentitySafe(MethodBase method)
    {
        try { return MethodSourceIdentity(method); }
        catch { return new JsonObject { ["method"] = SourceMember(method), ["sourceModuleVersionId"] = method.Module.ModuleVersionId.ToString() }; }
    }
}
