#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private static int AttackActorArgument(MethodBase method)
    {
        if (!method.IsStatic && method.DeclaringType == typeof(Projectile)) return 0;
        int[] actors = method.GetParameters().Select((p, n) => (p, n)).Where(v => v.p.ParameterType == typeof(Projectile))
            .Select(v => v.n + (method.IsStatic ? 0 : 1)).ToArray();
        return actors.Length == 1 ? actors[0] : -1;
    }

    private static bool AttackCallBindsCapturedActor(ParentSourceMethod caller, IEnumerable<ParentSourceMethod.Value> calls, MethodBase callee)
    {
        int parentActor = AttackActorArgument(caller.Method), childActor = AttackActorArgument(callee);
        if (parentActor < 0 || childActor < 0 || caller.WrittenArguments.Contains(parentActor)) return false;
        var sites = calls.Where(v => Equals(v.Operand, callee)).ToArray();
        // A matching signature is insufficient: the call must actually pass the
        // captured actor, not another projectile from a field/local/array.
        if (caller.Code.Count != AttackCode(caller.Method).Count && !sites.All(site => caller.CompleteCallPrefixes.Contains(site.At))) return false;
        var stability = new AttackIdentitySelection(caller, 0, 0, selectIdentityBranches: false);
        return sites.Length > 0 && sites.All(v => stability.Unmodified(v) && childActor < v.Inputs.Count
            && caller.Values.TryGetValue(v.Inputs[childActor], out var argument)
            && argument.Op == "ldarg" && argument.Operand is int slot && slot == parentActor);
    }

    internal static bool InspectProjectileAttackCallBinding(MethodInfo caller, MethodInfo callee)
    {
        try
        {
            var body = ParentSourceMethod.ForCallPrefixes(caller, AttackCode(caller), new[] { callee });
            return AttackCallBindsCapturedActor(body, body.Statements, callee);
        }
        catch (NotSupportedException) { return false; }
    }

    // A source specialization, not execution: only the captured actor's identity
    // selects CFG edges. The complete unspecialized program remains in the dump.
    private sealed class AttackIdentitySelection
    {
        internal readonly HashSet<int> Reachable = new();
        internal readonly Dictionary<int, int> Selected = new();
        internal readonly JsonObject Receipt;
        private readonly ParentSourceMethod body;
        private readonly int type, style, targetArgument;
        private readonly Dictionary<int, HashSet<int>> selectedReach = new();
        private readonly Dictionary<int, bool> unmodifiedReads = new();
        private readonly ParentSourceMethod.Value[] hazards;
        private int analysisWork;

        private void Work()
        {
            // Actual CFG/dataflow work, not serialized prose length. Refuse the
            // optional proof with an exact reason rather than stall crafting.
            if (++analysisWork > 4_000_000) throw new NotSupportedException("identity_control_flow_work_bound");
        }

        private HashSet<int> CurrentReach(int start)
        {
            if (selectedReach.TryGetValue(start, out var cached)) return cached;
            var reached = new HashSet<int>(); var pending = new Stack<int>(); pending.Push(start);
            while (pending.Count > 0)
            {
                Work(); int block = pending.Pop(); if (!reached.Add(block)) continue;
                foreach (int next in Selected.TryGetValue(block, out int chosen) ? new[] { chosen } : body.Blocks[block].Next.ToArray()) pending.Push(next);
            }
            return selectedReach[start] = reached;
        }

        internal AttackIdentitySelection(ParentSourceMethod body, int type, int style, bool selectIdentityBranches = true)
        {
            this.body = body; this.type = type; this.style = style;
            targetArgument = AttackActorArgument(body.Method);
            hazards = body.Values.Values.Where(IdentityHazard).ToArray();
            Receipt = new JsonObject { ["source"] = "certified_receiver_identity_cfg", ["version"] = 1,
                ["identityPredicates"] = new JsonObject { ["Projectile.type"] = type, ["Projectile.aiStyle"] = style },
                ["scope"] = "Source-only identity specialization; unknown runtime conditions retain all paths. Direct target identity writes/address escapes and uncertified target-passing calls before a read prevent selection. Native detours/global aliases remain outside capture coverage." };
            var edges = new JsonArray();
            // Earlier proven selectors can exclude a mutating foreign-identity
            // arm. Recompute reachability before proving subsequent selectors;
            // unknown runtime arms and any still-reachable hazards remain live.
            bool changed;
            do
            {
                changed = false;
                selectedReach.Clear(); unmodifiedReads.Clear();
                Reachable.Clear(); Reachable.UnionWith(CurrentReach(body.Code[0].Offset));
                var additions = new Dictionary<int, int>();
                if (selectIdentityBranches && targetArgument >= 0 && !body.WrittenArguments.Contains(targetArgument))
                foreach (var branch in body.Statements.Where(v => Reachable.Contains(v.Block) && !Selected.ContainsKey(v.Block) && body.Blocks[v.Block].Next.Count > 1))
                {
                    var values = branch.Inputs.Select(i => Literal(i, new HashSet<string>())).ToArray();
                    if (!values.Any(v => v.Identity) || values.Any(v => v.Number is null)) continue;
                    var next = body.Blocks[branch.Block].Next;
                    int? target = null;
                    if (branch.Op == "switch" && values.Length == 1 && branch.Operand is int[] cases)
                    {
                        int index = values[0].Number!.Value;
                        target = index >= 0 && index < cases.Length ? cases[index] : next[^1];
                    }
                    else if (values.Length == 1 && next.Count == 2 && branch.Op is "brtrue" or "brtrue.s" or "brfalse" or "brfalse.s")
                        target = next[(values[0].Number != 0) == branch.Op.StartsWith("brtrue", StringComparison.Ordinal) ? 0 : 1];
                    else if (values.Length == 2 && next.Count == 2)
                    {
                        bool equal = values[0].Number == values[1].Number;
                        if (branch.Op is "beq" or "beq.s") target = next[equal ? 0 : 1];
                        if (branch.Op is "bne.un" or "bne.un.s") target = next[equal ? 1 : 0];
                        long left = branch.Op.Contains(".un", StringComparison.Ordinal) ? unchecked((uint)values[0].Number!.Value) : values[0].Number!.Value;
                        long right = branch.Op.Contains(".un", StringComparison.Ordinal) ? unchecked((uint)values[1].Number!.Value) : values[1].Number!.Value;
                        if (branch.Op is "bgt" or "bgt.s" or "bgt.un" or "bgt.un.s") target = next[left > right ? 0 : 1];
                        if (branch.Op is "bge" or "bge.s" or "bge.un" or "bge.un.s") target = next[left >= right ? 0 : 1];
                        if (branch.Op is "blt" or "blt.s" or "blt.un" or "blt.un.s") target = next[left < right ? 0 : 1];
                        if (branch.Op is "ble" or "ble.s" or "ble.un" or "ble.un.s") target = next[left <= right ? 0 : 1];
                    }
                    if (target is null) continue;
                    additions[branch.Block] = target.Value;
                    edges.Add(new JsonObject { ["at"] = branch.At, ["block"] = branch.Block, ["op"] = branch.Op, ["successor"] = target.Value });
                }
                foreach (var edge in additions) { Selected[edge.Key] = edge.Value; changed = true; }
            } while (changed);
            Receipt["selectedEdges"] = edges;
        }

        private bool Target(string id, HashSet<string> seen)
        {
            if (!seen.Add(id) || !body.Values.TryGetValue(id, out var value)) return false;
            if (value.Op == "ldarg" && value.Operand is int slot) return slot == targetArgument;
            return value.Op is "ldloc" or "stloc" && value.Inputs.Count == 1 && Target(value.Inputs[0], seen);
        }

        private bool MayTarget(string id, HashSet<string> seen)
        {
            if (!seen.Add(id) || !body.Values.TryGetValue(id, out var value)) return false;
            bool ActorType(Type? candidate) => candidate is not null && candidate.IsAssignableFrom(typeof(Projectile));
            if (value.Op is "ldarg" or "ldarga" or "written_or_address_exposed_argument" && value.Operand is int slot)
            {
                if (slot == targetArgument) return true;
                return slot >= (body.Method.IsStatic ? 0 : 1)
                    && ActorType(body.Method.GetParameters()[slot - (body.Method.IsStatic ? 0 : 1)].ParameterType);
            }
            if (value.Op is "ldloca" or "address_exposed_local")
                return body.Statements.Where(v => v.Op == "stloc" && Equals(v.Operand, value.Operand))
                    .SelectMany(v => v.Inputs).Any(i => MayTarget(i, new(seen)));
            if (value.Op is "ldloc" or "stloc" or "predecessor_stack_alternatives" or "castclass" or "isinst")
                return value.Inputs.Any(i => MayTarget(i, new(seen)));
            // A global/foreign field or call can alias the target even though it
            // cannot prove the exact receiver for an identity comparison.
            return value.Operand is FieldInfo field && ActorType(field.FieldType)
                || value.Operand is MethodInfo call && ActorType(call.ReturnType);
        }

        private static bool BaseEntityValueAccessor(MethodBase method)
        {
            // A nonvirtual Entity accessor can only touch base fields and value
            // types. Reject casts, reference arguments and actor dispatch rather
            // than assuming every property getter/setter is pure.
            if (method.DeclaringType != typeof(Entity) || method.IsVirtual || method.GetMethodBody() is null) return false;
            return AttackCode(method).All(i => i.Op is not ("castclass" or "isinst" or "stsfld")
                && !(i.Arg is FieldInfo f && (f.DeclaringType == typeof(Projectile) || !f.FieldType.IsValueType))
                && !(i.Arg is MethodBase call && (call.IsVirtual || call.GetParameters().Any(p => !p.ParameterType.IsValueType)
                    || !call.IsStatic && call.DeclaringType?.IsValueType != true)));
        }

        private bool IdentityHazard(ParentSourceMethod.Value statement)
        {
            bool hazard = statement.Operand is FieldInfo field && field.DeclaringType == typeof(Projectile)
                && field.Name is "type" or "aiStyle" && statement.Op is "stfld" or "ldflda"
                && statement.Inputs.Count > 0 && MayTarget(statement.Inputs[0], new());
            hazard |= (statement.Operand is MethodBase call && !BaseEntityValueAccessor(call) || statement.Op is "stsfld" or "stfld" or "stobj" || statement.Op.StartsWith("stelem", StringComparison.Ordinal) || statement.Op.StartsWith("stind", StringComparison.Ordinal))
                && statement.Inputs.Skip(statement.Op == "stfld" ? 1 : 0).Any(i => MayTarget(i, new()));
            return hazard;
        }

        internal bool Unmodified(ParentSourceMethod.Value read)
        {
            if (unmodifiedReads.TryGetValue(read.At, out bool cached)) return cached;
            foreach (var statement in hazards)
            {
                Work();
                if (!Reachable.Contains(statement.Block)) continue;
                if (statement.Block == read.Block && statement.At < read.At
                    || statement.Block != read.Block && CurrentReach(statement.Block).Contains(read.Block)
                    || statement.Block == read.Block && body.Blocks[statement.Block].Next.Any(n => CurrentReach(n).Contains(read.Block)))
                    return unmodifiedReads[read.At] = false;
            }
            return unmodifiedReads[read.At] = true;
        }

        private (int? Number, bool Identity) Literal(string id, HashSet<string> seen)
        {
            Work();
            if (seen.Count > 64 || !seen.Add(id) || !body.Values.TryGetValue(id, out var value)) return (null, false);
            if (value.Op == "const" && value.Operand is int number) return (number, false);
            if (value.Op == "ldfld" && value.Operand is FieldInfo field && field.DeclaringType == typeof(Projectile)
                && field.Name is "type" or "aiStyle" && value.Inputs.Count == 1 && Target(value.Inputs[0], new()) && Unmodified(value))
                return (field.Name == "type" ? type : style, true);
            if (value.Op is "ldloc" or "stloc" && value.Inputs.Count == 1) return Literal(value.Inputs[0], seen);
            if (value.Op is "conv.i4" or "conv.u4" && value.Inputs.Count == 1) return Literal(value.Inputs[0], seen);
            if (value.Op is "sub" or "ceq" or "clt" or "clt.un" or "cgt" or "cgt.un" && value.Inputs.Count == 2)
            {
                var left = Literal(value.Inputs[0], new(seen)); var right = Literal(value.Inputs[1], new(seen));
                if (left.Number is not int a || right.Number is not int b) return (null, false);
                long first = value.Op.EndsWith(".un", StringComparison.Ordinal) ? unchecked((uint)a) : a;
                long second = value.Op.EndsWith(".un", StringComparison.Ordinal) ? unchecked((uint)b) : b;
                int result = value.Op switch
                {
                    "ceq" => a == b ? 1 : 0,
                    "clt" or "clt.un" => first < second ? 1 : 0,
                    "cgt" or "cgt.un" => first > second ? 1 : 0,
                    _ => unchecked(a - b),
                };
                return (result, left.Identity || right.Identity);
            }
            return (null, false);
        }
    }
}
