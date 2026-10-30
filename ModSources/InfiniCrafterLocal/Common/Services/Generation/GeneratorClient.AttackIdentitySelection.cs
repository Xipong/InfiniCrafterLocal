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
        return sites.Length > 0 && sites.All(v => childActor < v.Inputs.Count
            && caller.Values.TryGetValue(v.Inputs[childActor], out var argument)
            && argument.Op == "ldarg" && argument.Operand is int slot && slot == parentActor);
    }

    internal static bool InspectProjectileAttackCallBinding(MethodInfo caller, MethodInfo callee)
    {
        var body = new ParentSourceMethod(caller);
        return AttackCallBindsCapturedActor(body, body.Statements, callee);
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

        internal AttackIdentitySelection(ParentSourceMethod body, int type, int style)
        {
            this.body = body; this.type = type; this.style = style;
            targetArgument = AttackActorArgument(body.Method);
            Receipt = new JsonObject { ["source"] = "certified_receiver_identity_cfg", ["version"] = 1,
                ["identityPredicates"] = new JsonObject { ["Projectile.type"] = type, ["Projectile.aiStyle"] = style },
                ["scope"] = "Source-only identity specialization; unknown runtime conditions retain all paths. Direct target identity writes/address escapes and uncertified target-passing calls before a read prevent selection. Native detours/global aliases remain outside capture coverage." };
            var edges = new JsonArray();
            if (targetArgument >= 0 && !body.WrittenArguments.Contains(targetArgument))
                foreach (var branch in body.Statements.Where(v => body.Blocks[v.Block].Next.Count > 1))
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
                    }
                    if (target is null) continue;
                    Selected[branch.Block] = target.Value;
                    edges.Add(new JsonObject { ["at"] = branch.At, ["block"] = branch.Block, ["op"] = branch.Op, ["successor"] = target.Value });
                }
            var pending = new Stack<int>(); pending.Push(body.Code[0].Offset);
            while (pending.Count > 0)
            {
                int block = pending.Pop(); if (!Reachable.Add(block)) continue;
                foreach (int next in Selected.TryGetValue(block, out int chosen) ? new[] { chosen } : body.Blocks[block].Next.ToArray())
                    pending.Push(next);
            }
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

        private bool Unmodified(ParentSourceMethod.Value read)
        {
            foreach (var statement in body.Values.Values)
            {
                bool hazard = statement.Operand is FieldInfo field && field.DeclaringType == typeof(Projectile)
                    && field.Name is "type" or "aiStyle" && statement.Op is "stfld" or "ldflda"
                    && statement.Inputs.Count > 0 && MayTarget(statement.Inputs[0], new());
                // Calls receiving the actor may mutate identity; storing the actor
                // into an object/array also escapes it. A local alias alone does not.
                hazard |= (statement.Operand is MethodBase call && !BaseEntityValueAccessor(call) || statement.Op is "stsfld" or "stfld" or "stobj" || statement.Op.StartsWith("stelem", StringComparison.Ordinal) || statement.Op.StartsWith("stind", StringComparison.Ordinal))
                    && statement.Inputs.Skip(statement.Op == "stfld" ? 1 : 0).Any(i => MayTarget(i, new()));
                if (!hazard) continue;
                if (statement.Block == read.Block && statement.At < read.At
                    || statement.Block != read.Block && body.Reach(statement.Block).Contains(read.Block)
                    || statement.Block == read.Block && body.Blocks[statement.Block].Next.Any(n => body.Reach(n).Contains(read.Block))) return false;
            }
            return true;
        }

        private (int? Number, bool Identity) Literal(string id, HashSet<string> seen)
        {
            if (seen.Count > 64 || !seen.Add(id) || !body.Values.TryGetValue(id, out var value)) return (null, false);
            if (value.Op == "const" && value.Operand is int number) return (number, false);
            if (value.Op == "ldfld" && value.Operand is FieldInfo field && field.DeclaringType == typeof(Projectile)
                && field.Name is "type" or "aiStyle" && value.Inputs.Count == 1 && Target(value.Inputs[0], new()) && Unmodified(value))
                return (field.Name == "type" ? type : style, true);
            if (value.Op is "ldloc" or "stloc" && value.Inputs.Count == 1) return Literal(value.Inputs[0], seen);
            if (value.Op is "sub" or "ceq" && value.Inputs.Count == 2)
            {
                var left = Literal(value.Inputs[0], new(seen)); var right = Literal(value.Inputs[1], new(seen));
                return left.Number is int a && right.Number is int b ? (value.Op == "ceq" ? a == b ? 1 : 0 : unchecked(a - b), left.Identity || right.Identity) : (null, false);
            }
            return (null, false);
        }
    }
}
