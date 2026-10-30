#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Cache source syntax, never an actor/sample or evaluated AI state. Dump can
    // ask about thousands of clones; the very large native dispatcher is decoded
    // once. JSON is cloned on read so callers cannot mutate the cached program.
    private static readonly ConcurrentDictionary<MethodBase, Lazy<List<AmmoIl>>> AttackSourceCode = new();
    private static readonly ConcurrentDictionary<(int Type, int Style), Lazy<string>> AttackSourcePrograms = new();
    private static List<AmmoIl> AttackCode(MethodBase method)
        => AttackSourceCode.GetOrAdd(method, m => new Lazy<List<AmmoIl>>(() => ReadAmmoIl(m, preserveStructure: true, sourceGraph: true))).Value;

    internal static JsonObject CaptureProjectileAttackReference(Projectile projectile)
        => VerifiedProjectileAttackReference(projectile, NativeSourceModuleVerified.Value);

    internal static JsonObject VerifiedProjectileAttackReference(Projectile projectile, bool moduleVerified)
    {
        var refusal = new JsonObject { ["source"] = "read_only_native_attack_source", ["coverage"] = new JsonObject
            { ["unresolved"] = "native_module_certificate_unavailable_or_nonvanilla_identity" } };
        if (!moduleVerified || projectile.ModProjectile is not null || projectile.type <= ProjectileID.None || projectile.type >= ProjectileID.Count) return refusal;
        JsonObject result = JsonNode.Parse(AttackSourcePrograms.GetOrAdd((projectile.type, projectile.aiStyle),
            key => new Lazy<string>(() => BuildProjectileAttackSource(key.Type, key.Style).ToJsonString())).Value)!.AsObject();
        // Literal admission observations are not geometry or guaranteed hits.
        result["admission"] = new JsonObject { ["ownerHitCheck"] = projectile.ownerHitCheck,
            ["ownerHitCheckDistance"] = projectile.ownerHitCheckDistance, ["usesOwnerMeleeHitCD"] = projectile.usesOwnerMeleeHitCD,
            ["scope"] = "current_projectile_fields; native_target_immunity_and_mod_hook_admission_unresolved" };
        return result;
    }

    private static JsonObject BuildProjectileAttackSource(int type, int style)
    {
        var result = new JsonObject { ["source"] = "read_only_native_attack_source", ["version"] = 1,
            ["identityPredicates"] = new JsonObject { ["Projectile.type"] = type, ["Projectile.aiStyle"] = style },
            ["scope"] = "Source statements, not execution, inheritance, final hit/DPS or a gameplay preset. Every observation requires reaching its offset. Predicates retain both successor offsets; alternatives are reaching definitions, not independent rolls. Native hook overrides/detours, enclosing dispatcher flow, hit admission and GPU/texture extent remain unresolved. Fields are live source reads, not captured AI values. Source order is significant.",
            ["units"] = "position/cone length: native world pixels (16 per Terraria block); rotation: radians; localAI/ai timing: AI invocations, not seconds; texture Frame: image coordinates; scale: dimensionless" };
        var certificates = new JsonArray(); var gaps = new JsonArray();
        var certified = new HashSet<MethodBase>();
        void Certify(MethodBase method)
        {
            if (certified.Add(method)) certificates.Add(MethodSourceIdentity(method));
        }
        JsonObject Observe(MethodBase method, string role, List<AmmoIl>? slice = null, bool boundActor = false)
        {
            Certify(method);
            try
            {
                var next = slice is null ? null : AttackCode(method).Zip(AttackCode(method).Skip(1), (a, b) => (a.Offset, b.Offset))
                    .ToDictionary(p => p.Item1, p => p.Item2);
                var body = new ParentSourceMethod(method, slice ?? AttackCode(method), next);
                var observation = new AttackSourceObservation(body, role);
                var program = observation.Finish();
                if (boundActor && slice is null && role is "motion" or "draw")
                {
                    try
                    {
                        var selection = new AttackIdentitySelection(body, type, style);
                        if (selection.Selected.Count > 0)
                        {
                            var specialized = new AttackSourceObservation(new ParentSourceMethod(method, AttackCode(method), selectedSuccessors: selection.Selected), role, selection: selection).Finish();
                            specialized["identitySelection"] = selection.Receipt;
                            program["identitySelected"] = specialized;
                        }
                    }
                    catch (Exception error) when (error is not OutOfMemoryException)
                    {
                        // An optional specialization must never discard the
                        // already captured full connected source/audit program.
                        program["identitySelectionUnavailable"] = error is NotSupportedException ? error.Message : error.GetType().Name;
                    }
                }
                // Referenced native helper identities are certified separately;
                // unselected dust/audio code does not bloat the attack slice.
                foreach (var call in observation.ReferencedMethods.Where(m => m.Module == typeof(Projectile).Module && m.GetMethodBody() is not null)) Certify(call);
                return program;
            }
            catch (Exception error) when (error is not OutOfMemoryException)
            { return new JsonObject { ["method"] = SourceMember(method), ["coverage"] = "unknown", ["unresolved"] = error is NotSupportedException ? error.Message : error.GetType().Name }; }
        }
        MethodInfo? Native(Type owner, string name) => owner.GetMethods(BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)
            .FirstOrDefault(m => m.Name == name);
        foreach (string root in new[] { "VanillaAI", "Colliding" })
        {
            MethodInfo? method = Native(typeof(Projectile), root);
            if (method is null) { gaps.Add(root + "_root_missing"); continue; }
            try
            {
                var code = AttackCode(method);
                var windows = ProjectileIdentityWindows(code, type, style).ToArray();
                if (windows.Length == 0) { gaps.Add(root + "_identity_dispatch_outside_supported_source_shape"); continue; }
                var slice = windows.SelectMany(w => w.Code).GroupBy(i => i.Offset).Select(g => g.First()).OrderBy(i => i.Offset).ToList();
                var dispatch = Observe(method, root == "VanillaAI" ? "dispatch" : "collision", slice);
                dispatch["identityWindows"] = new JsonArray(windows.Select(w => (JsonNode?)new JsonObject
                    { ["field"] = w.Field, ["literal"] = w.Literal, ["guardOffset"] = w.Guard }).ToArray());
                if (root == "Colliding")
                {
                    result["collision"] = dispatch;
                    // Retain the actual predicate implementation, not an invented
                    // analytic cone/AABB formula. Helpers remain source-only.
                    var helpers = new JsonArray();
                    var pending = new Queue<MethodBase>(slice.Select(i => i.Arg).OfType<MethodInfo>()
                        .Where(m => m.DeclaringType == typeof(Utils) && m.Name.Contains("Cone", StringComparison.Ordinal)));
                    var seen = new HashSet<MethodBase>();
                    while (pending.Count > 0 && seen.Count < 4)
                    {
                        MethodBase helper = pending.Dequeue(); if (!seen.Add(helper)) continue;
                        helpers.Add(Observe(helper, "predicate"));
                        foreach (var call in AttackCode(helper).Select(i => i.Arg).OfType<MethodInfo>()
                            .Where(m => m.DeclaringType == typeof(Utils) && m.Name.Contains("Cone", StringComparison.Ordinal))) pending.Enqueue(call);
                    }
                    if (helpers.Count > 0) dispatch["predicateSources"] = helpers;
                }
                else
                {
                    result["motionDispatch"] = dispatch;
                    var helpers = slice.Select(i => i.Arg).OfType<MethodInfo>().Where(m => m.DeclaringType == typeof(Projectile)
                        && m.GetParameters().Length == 0 && m.ReturnType == typeof(void) && m.GetMethodBody() is not null).Distinct().ToArray();
                    var caller = new ParentSourceMethod(method, slice, AttackCode(method).Zip(AttackCode(method).Skip(1), (a, b) => (a.Offset, b.Offset)).ToDictionary(p => p.Item1, p => p.Item2));
                    var programs = helpers.Select(m => Observe(m, "motion", boundActor: AttackCallBindsCapturedActor(caller, caller.Statements, m))).Where(p => p["observations"] is JsonArray a && a.Count > 0).ToArray();
                    if (programs.Length > 0) result["motion"] = new JsonObject { ["programs"] = new JsonArray(programs.Select(p => (JsonNode?)p).ToArray()) };
                    else gaps.Add("motion_helper_or_state_sinks_outside_supported_source_shape");
                }
            }
            catch (Exception error) when (error is not OutOfMemoryException) { gaps.Add(root + ":" + error.GetType().Name); }
        }
        // Draw dispatch is selected only from actual source type comparisons or
        // integer switch selectors. No item name, controller label or ID roster.
        MethodInfo? drawRoot = Native(typeof(Main), "DrawProj_DrawSpecialProjs");
        if (drawRoot is not null)
        {
            try
            {
                var body = new ParentSourceMethod(drawRoot, AttackCode(drawRoot));
                var selected = SelectedProjectileDispatch(body, type, style).ToArray();
                var helpers = selected.Select(v => v.Operand).OfType<MethodInfo>().Where(m => m.DeclaringType == typeof(Main)
                    && m.GetParameters().Any(p => p.ParameterType == typeof(Projectile)) && m.GetMethodBody() is not null).Distinct().ToArray();
                if (helpers.Length > 0)
                {
                    var observation = new AttackSourceObservation(body, "dispatch", selected);
                    var dispatch = observation.Finish(); Certify(drawRoot);
                    foreach (var call in observation.ReferencedMethods.Where(m => m.Module == typeof(Projectile).Module && m.GetMethodBody() is not null)) Certify(call);
                    result["draw"] = new JsonObject { ["dispatch"] = dispatch,
                        ["programs"] = new JsonArray(helpers.Select(m => (JsonNode?)Observe(m, "draw", boundActor: AttackCallBindsCapturedActor(body, selected, m))).ToArray()) };
                }
                else gaps.Add("draw_type_dispatch_outside_supported_source_shape");
            }
            catch (Exception error) when (error is not OutOfMemoryException) { gaps.Add("draw_source:" + error.GetType().Name); }
        }
        if (result["motion"] is not null && Native(typeof(Projectile), "UpdatePosition") is { } integration)
            result["positionIntegration"] = Observe(integration, "motion");
        result["sourceMethods"] = certificates;
        result["coverage"] = new JsonObject { ["proved"] = "bounded_native_source_observations_only", ["unresolved"] = gaps,
            ["boundaries"] = "ProjectileLoader.Colliding/ShouldUpdatePosition and all other hooks remain unevaluated; no source fact is absence of a mechanic; damage may stop before visual lifetime; held-item draw is separate and not inferred from noMelee" };
        return result;
    }

    // This is a syntax recognizer for immutable identity selectors, NOT an IL
    // interpreter. Only constant/type/aiStyle and the switch's integer subtraction
    // are accepted. Opaque state-dependent selectors never choose an arm.
    private static IEnumerable<ParentSourceMethod.Value> SelectedProjectileDispatch(ParentSourceMethod body, int type, int style)
    {
        int? Identity(string id, int depth = 0)
        {
            if (depth > 12) return null;
            var defs = body.Definitions(id).ToArray(); if (defs.Length != 1) return null;
            var value = defs[0];
            if (value.Op == "const" && value.Operand is int literal) return literal;
            if (value.Op == "ldfld" && value.Operand is FieldInfo f && f.DeclaringType == typeof(Projectile))
                return f.Name == "type" ? type : f.Name == "aiStyle" ? style : null;
            if (value.Op == "sub" && value.Inputs.Count == 2 && Identity(value.Inputs[0], depth + 1) is int left && Identity(value.Inputs[1], depth + 1) is int right) return left - right;
            return null;
        }
        bool HasIdentity(string id) => body.Definitions(id).Any(v => v.Operand is FieldInfo f && f.DeclaringType == typeof(Projectile) && f.Name is "type" or "aiStyle"
            || v.Op == "sub" && v.Inputs.Any(HasIdentity));
        var selected = new HashSet<int>();
        foreach (var branch in body.Statements.Where(v => v.Op == "switch" || v.Op.StartsWith("beq", StringComparison.Ordinal) || v.Op.StartsWith("bne", StringComparison.Ordinal)))
        {
            if (!branch.Inputs.Any(HasIdentity)) continue;
            int target;
            if (branch.Op == "switch" && branch.Operand is int[] targets && branch.Inputs.Count == 1 && Identity(branch.Inputs[0]) is int index && index >= 0 && index < targets.Length)
                target = targets[index];
            else if (branch.Inputs.Count == 2 && Identity(branch.Inputs[0]) is int a && Identity(branch.Inputs[1]) is int b && a == b && body.Blocks[branch.Block].Next.Count == 2)
                target = body.Blocks[branch.Block].Next[branch.Op.StartsWith("beq", StringComparison.Ordinal) ? 0 : 1];
            else continue;
            // Dispatch arm starts at a stack-empty basic block; follow only its
            // straight-line body. Unknown nested dispatch remains explicitly out
            // of coverage rather than leaking unrelated source arms.
            if (body.Blocks.TryGetValue(target, out var block)) selected.Add(block.Start);
        }
        return body.Statements.Where(v => selected.Contains(v.Block) && v.Operand is MethodInfo);
    }

    internal static JsonObject InspectProjectileAttackSource(MethodInfo method, string role)
        => new AttackSourceObservation(new ParentSourceMethod(method), role).Finish();

    internal static JsonObject InspectProjectileAttackIdentitySource(MethodInfo method, int type, int style)
    {
        var body = new ParentSourceMethod(method);
        var selection = new AttackIdentitySelection(body, type, style);
        var result = new AttackSourceObservation(new ParentSourceMethod(method, selectedSuccessors: selection.Selected), "motion", selection: selection).Finish();
        result["identitySelection"] = selection.Receipt;
        return result;
    }

    private sealed class AttackSourceObservation
    {
        private readonly ParentSourceMethod body;
        private readonly string role;
        private readonly AttackIdentitySelection? selection;
        private readonly ParentSourceMethod.Value[] roots, branches;
        private readonly JsonObject dependencies = new(), symbols = new();
        internal readonly HashSet<MethodBase> ReferencedMethods = new();
        private string Symbol(MemberInfo member)
        {
            if (member is MethodBase method) ReferencedMethods.Add(method);
            string full = SourceMember(member);
            string name = member.DeclaringType?.Name + "." + member.Name;
            if (symbols[name] is JsonValue existing && existing.GetValue<string>() != full) name += "#" + member.MetadataToken;
            symbols[name] = full;
            return name;
        }
        private readonly JsonArray predicates = new();
        private readonly HashSet<string> visiting = new(), predicateIds = new();
        private int expressionCount;
        internal AttackSourceObservation(ParentSourceMethod body, string role, IEnumerable<ParentSourceMethod.Value>? selected = null, AttackIdentitySelection? selection = null)
        {
            this.body = body; this.role = role; this.selection = selection;
            roots = (selected ?? body.Statements.Where(IsRoot)).Where(v => selection is null || selection.Reachable.Contains(v.Block)).OrderBy(v => v.At).ToArray();
            branches = body.Statements.Where(v => (selection is null || selection.Reachable.Contains(v.Block) && !selection.Selected.ContainsKey(v.Block)) && body.Blocks[v.Block].Next.Distinct().Count() > 1
                && (v.Op == "switch" || v.Op.StartsWith("b", StringComparison.Ordinal))).ToArray();
        }
        private bool IsRoot(ParentSourceMethod.Value value)
        {
            if (role is "collision" or "predicate") return value.Op == "ret" || value.Operand is MethodInfo m && m.ReturnType == typeof(bool);
            if (role == "dispatch") return value.Operand is MethodInfo;
            if (role == "draw") return value.Operand is MethodBase draw && (draw.Name.Contains("Draw", StringComparison.Ordinal)
                || draw.Name == "Frame" || draw.IsConstructor && draw.DeclaringType?.Name == "Color");
            if (value.Op == "stfld" && value.Operand is FieldInfo field && (field.DeclaringType == typeof(Projectile) || field.DeclaringType == typeof(Entity)))
                return field.Name is "position" or "velocity" or "rotation" or "scale" or "timeLeft" or "direction" or "spriteDirection";
            if (value.Operand is MethodInfo call && (call.DeclaringType == typeof(Projectile) || call.DeclaringType == typeof(Entity))
                && (call.Name is "set_Center" or "Kill")) return true;
            if (value.Op.StartsWith("stind", StringComparison.Ordinal) || value.Op.StartsWith("stelem", StringComparison.Ordinal))
                return value.Inputs.Count > 0 && ContainsClock(value.Inputs[0], new HashSet<string>());
            return false;
        }
        private bool ContainsClock(string id, HashSet<string> seen)
            => seen.Count < 128 && seen.Add(id) && body.Values.TryGetValue(id, out var v)
                && (v.Operand is FieldInfo f && f.DeclaringType == typeof(Projectile) && f.Name is "ai" or "localAI" || v.Inputs.Any(i => ContainsClock(i, seen)));
        private JsonArray Required(ParentSourceMethod.Value value)
        {
            var conditions = new JsonArray();
            foreach (var branch in branches.Where(b => b.Block != value.Block && body.ControlledRegion(b.Block).Contains(value.Block)))
            {
                string name = "b" + branch.At; conditions.Add(name);
                if (!predicateIds.Add(name)) continue;
                predicates.Add(new JsonObject { ["id"] = name, ["at"] = branch.At, ["op"] = branch.Op,
                    ["inputs"] = new JsonArray(branch.Inputs.Select(i => (JsonNode?)JsonValue.Create(Expression(i))).ToArray()),
                    ["successors"] = new JsonArray(body.Blocks[branch.Block].Next.Select(n => (JsonNode?)JsonValue.Create(n)).ToArray()) });
            }
            return conditions;
        }
        private string Local(ParentSourceMethod.Value value)
        {
            string name = "l" + value.Operand + "@" + value.At;
            if (dependencies.ContainsKey(name)) return name;
            dependencies[name] = null;
            dependencies[name] = new JsonObject { ["expression"] = value.Inputs.Count == 1 ? Expression(value.Inputs[0]) : value.Op,
                ["at"] = value.At, ["block"] = value.Block, ["requiredPredicates"] = Required(value) };
            return name;
        }
        private string AddressLocal(ParentSourceMethod.Value value)
        {
            string name = "addressed_l" + value.Operand;
            if (dependencies.ContainsKey(name)) return name;
            dependencies[name] = null;
            bool Address(string id) => body.Values.TryGetValue(id, out var v) && v.Op == "ldloca" && Equals(v.Operand, value.Operand);
            var writes = body.Statements.Where(v => selection is null || selection.Reachable.Contains(v.Block)).Where(v => v.Op == "stloc" && Equals(v.Operand, value.Operand)
                || v.Inputs.Count > 0 && v.Inputs.Any(Address)).OrderBy(v => v.At).ToArray();
            dependencies[name] = new JsonObject { ["scope"] = "address_exposed_local; ordered_source_uses_and_stores; alias_effects_and_reaching_value_unresolved",
                ["orderedSourceUses"] = new JsonArray(writes.Select(v => (JsonNode?)new JsonObject { ["at"] = v.At, ["block"] = v.Block,
                    ["expression"] = v.Op == "stloc" ? Local(v) : Operation(v), ["requiredPredicates"] = Required(v) }).ToArray()) };
            return name;
        }
        private string Alternative(string id)
        {
            string expression = Expression(id);
            if (!body.Values.TryGetValue(id, out var value)) return expression;
            var conditions = Required(value);
            // A stack merge after a conditional can have no conditional stloc.
            // Retain the predecessor block/predicates of each actual value;
            // alternatives(.2,.6) alone would erase the source choice.
            return conditions.Count == 0 ? expression : "source_block(" + value.Block
                + ",requires=" + conditions.ToJsonString() + ",value=" + expression + ")";
        }

        private string Expression(string id)
        {
            if (++expressionCount > 12000 || dependencies.Count > 192) throw new NotSupportedException("connected_source_expression_bound");
            if (!body.Values.TryGetValue(id, out var value)) return "unresolved(" + id + ")";
            if (value.Op is "ldloca" or "address_exposed_local") return AddressLocal(value);
            // Local() installs its named dependency before walking connected
            // address uses/predicates. Re-entry references that definition; it
            // is not evidence of a loop in the native instruction stream.
            if (value.Op == "stloc") return Local(value);
            if (!visiting.Add(id)) return "loop_or_alias(" + id + ")";
            try
            {
                if (value.Op is "ldloc" or "predecessor_stack_alternatives")
                {
                    var inputs = value.Inputs.Where(i => selection is null || !body.Values.TryGetValue(i, out var definition) || selection.Reachable.Contains(definition.Block)).ToArray();
                    return inputs.Length == 1 ? Expression(inputs[0]) : "alternatives(" + string.Join(",", inputs.Select(Alternative)) + ")";
                }
                if (value.Op is "ldarg" or "ldarga" or "written_or_address_exposed_argument" && value.Operand is int slot)
                {
                    string argument = !body.Method.IsStatic && slot == 0 ? "this" : body.Method.GetParameters()[slot - (body.Method.IsStatic ? 0 : 1)].Name ?? "arg" + slot;
                    return value.Op == "ldarg" ? argument : "address_or_written(" + argument + ")";
                }
                if (value.Op == "const" || value.Op is "ldc.r4" or "ldc.r8") return SourceOperand(value.Operand)?.ToJsonString() ?? "null";
                return Operation(value);
            }
            finally { visiting.Remove(id); }
        }
        private string Operation(ParentSourceMethod.Value value)
        {
            string[] inputs = value.Inputs.Select(Expression).ToArray();
            if (value.Operand is FieldInfo field) return value.Op + "(" + Symbol(field) + (inputs.Length > 0 ? "," + string.Join(",", inputs) : "") + ")";
            if (value.Operand is MethodBase method) return Symbol(method) + "[" + string.Join(",", inputs) + "]";
            return value.Op + "(" + string.Join(",", inputs) + (value.Operand is null ? "" : ";" + (SourceOperand(value.Operand)?.ToJsonString() ?? "null")) + ")";
        }
        internal JsonObject Finish()
        {
            JsonObject result = MethodSourceIdentity(body.Method);
            var observations = new JsonArray();
            foreach (var value in roots)
            {
                string kind = value.Operand is FieldInfo f ? f.Name == "scale" ? "live_scale" : f.Name == "rotation" ? "rotation" : "state_write"
                    : value.Operand is MethodBase m ? m.Name == "set_Center" ? "center_assignment" : m.Name == "Kill" ? "lifetime_end" : role + "_call" : value.Op == "ret" ? "return" : "clock_or_ai_write";
                var row = new JsonObject { ["kind"] = kind, ["at"] = value.At, ["block"] = value.Block,
                    ["requiredPredicates"] = Required(value) };
                if (value.Operand is MethodBase call)
                {
                    row["call"] = Symbol(call);
                    int skip = call.IsStatic || value.Op == "newobj" ? 0 : 1;
                    if (skip == 1 && value.Inputs.Count > 0) row["receiver"] = Expression(value.Inputs[0]);
                    row["arguments"] = new JsonObject(call.GetParameters().Select((p, n) => new KeyValuePair<string, JsonNode?>(p.Name ?? "arg" + n,
                        n + skip < value.Inputs.Count ? JsonValue.Create(Expression(value.Inputs[n + skip])) : JsonValue.Create("unresolved_signature_input"))));
                }
                else row["expression"] = Operation(value);
                observations.Add(row);
            }
            result["observations"] = observations; result["dependencies"] = dependencies; result["predicates"] = predicates; result["symbols"] = symbols;
            result["coverage"] = "connected_source_slice; opaque_fields_calls_and_address_aliases_are_symbolic";
            if (body.Unknown.Count > 0) result["unresolved"] = new JsonArray(body.Unknown.Distinct().Select(s => (JsonNode?)JsonValue.Create(s)).ToArray());
            // Reject an oversized connected role instead of clipping an equation,
            // its predicates or alternative definitions to make it appear whole.
            if (result.ToJsonString().Length > 32000) throw new NotSupportedException("connected_source_role_character_bound");
            return result;
        }
    }
}
