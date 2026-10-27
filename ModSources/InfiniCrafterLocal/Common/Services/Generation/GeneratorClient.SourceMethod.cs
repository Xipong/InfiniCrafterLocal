#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // A read-only source decompiler. Values are IL definitions, not runtime
    // values. No instruction, getter, constructor, operator or hook is invoked.
    // CFG joins retain every reaching definition; loops are never unrolled.
    private sealed class ParentSourceMethod
    {
        internal sealed class Value
        {
            internal string Id = "", Op = "";
            internal object? Operand;
            internal List<string> Inputs = new();
            internal int At, Block;
        }
        internal sealed class Block
        {
            internal int Start, Height = -1;
            internal List<int> Next = new();
            internal List<AmmoIl> Code = new();
            internal List<string> Exit = new();
            internal Dictionary<int, HashSet<string>> Incoming = new(), Outgoing = new();
        }
        internal readonly MethodBase Method;
        internal readonly Dictionary<string, Value> Values = new();
        internal readonly List<Value> Statements = new();
        internal readonly Dictionary<int, Block> Blocks = new();
        internal readonly HashSet<int> EscapedLocals = new();
        internal readonly HashSet<int> WrittenArguments = new();
        internal readonly List<string> Unknown = new();
        internal readonly List<AmmoIl> Code;
        private readonly HashSet<int> sliceEntries = new();
        private readonly Dictionary<int, HashSet<int>> reachable = new();
        private Dictionary<int, HashSet<int>>? postdominators;
        private readonly Dictionary<int, HashSet<int>> controlRegions = new();

        internal HashSet<int> Reach(int start)
        {
            if (reachable.TryGetValue(start, out var cached)) return cached;
            var reached = new HashSet<int>(); var pending = new Stack<int>(); pending.Push(start);
            while (pending.Count > 0)
            {
                int next = pending.Pop(); if (!reached.Add(next)) continue;
                foreach (int target in Blocks[next].Next) pending.Push(target);
            }
            return reachable[start] = reached;
        }

        internal HashSet<int> ControlledRegion(int start)
        {
            if (controlRegions.TryGetValue(start, out var cached)) return cached;
            Block block = Blocks[start];
            var region = new HashSet<int> { start };
            if (block.Next.Distinct().Count() < 2) return region;
            if (postdominators is null)
            {
                var all = Blocks.Values.Where(b => b.Height >= 0).Select(b => b.Start).Append(-1).ToHashSet();
                postdominators = all.ToDictionary(b => b, b => b == -1 ? new HashSet<int> { -1 } : new HashSet<int>(all));
                bool changed = true; int passes = 0;
                while (changed)
                {
                    if (++passes > 2048) throw new NotSupportedException("control_dependency_bound");
                    changed = false;
                    foreach (Block current in Blocks.Values.Reverse().Where(b => b.Height >= 0))
                    {
                        var next = current.Next.Count == 0 ? new[] { -1 } : current.Next.ToArray();
                        var common = new HashSet<int>(postdominators[next[0]]);
                        foreach (int successor in next.Skip(1)) common.IntersectWith(postdominators[successor]);
                        common.Add(current.Start);
                        if (!common.SetEquals(postdominators[current.Start])) { postdominators[current.Start] = common; changed = true; }
                    }
                }
            }
            int join = postdominators[start].Where(b => b != start).OrderByDescending(b => postdominators[b].Count).FirstOrDefault(-1);
            var pending = new Stack<int>(block.Next);
            while (pending.Count > 0)
            {
                int next = pending.Pop();
                if (next == join || !region.Add(next)) continue;
                foreach (int successor in Blocks[next].Next) pending.Push(successor);
            }
            return controlRegions[start] = region;
        }

        internal ParentSourceMethod(MethodBase method, List<AmmoIl>? sourceSlice = null, Dictionary<int, int>? sourceNext = null)
        {
            Method = method;
            Code = sourceSlice ?? ReadAmmoIl(method, preserveStructure: true, sourceGraph: true);
            if (Code.Count == 0) throw new NotSupportedException("no_il");
            var leaders = SourceBranchTargets(Code);
            leaders.Add(Code[0].Offset);
            sliceEntries.Add(Code[0].Offset);
            if (sourceNext is not null)
                for (int n = 1; n < Code.Count; n++)
                    if (!sourceNext.TryGetValue(Code[n - 1].Offset, out int next) || next != Code[n].Offset)
                    { leaders.Add(Code[n].Offset); sliceEntries.Add(Code[n].Offset); }
            for (int n = 0; n + 1 < Code.Count; n++)
                if (EndsBlock(Code[n])) leaders.Add(Code[n + 1].Offset);
            // Exception regions are explicitly unsupported. Refuse rather than
            // connect handler entry stacks to normal control flow incorrectly.
            if (method.GetMethodBody()!.ExceptionHandlingClauses.Any(clause => sourceSlice is null || Code.Any(i =>
                i.Offset >= clause.TryOffset && i.Offset < clause.TryOffset + clause.TryLength
                || i.Offset >= clause.HandlerOffset && i.Offset < clause.HandlerOffset + clause.HandlerLength
                || clause.Flags == ExceptionHandlingClauseOptions.Filter && i.Offset >= clause.FilterOffset && i.Offset < clause.HandlerOffset)))
                throw new NotSupportedException("exception_regions");
            Block? current = null;
            foreach (var instruction in Code)
            {
                if (leaders.Contains(instruction.Offset)) Blocks[instruction.Offset] = current = new Block { Start = instruction.Offset };
                current!.Code.Add(instruction);
                if (instruction.Op == "ldloca" && instruction.Arg is int local) EscapedLocals.Add(local);
                if (instruction.Op is "starg" or "ldarga" && instruction.Arg is int argument) WrittenArguments.Add(argument);
            }
            if (Blocks.Count > 2048) throw new NotSupportedException("basic_block_bound");
            var ordered = Blocks.Values.ToArray();
            for (int b = 0; b < ordered.Length; b++)
            {
                Block block = ordered[b];
                AmmoIl last = block.Code[^1];
                if (last.Op == "switch" && last.Arg is int[] targets) block.Next.AddRange(targets);
                else if (IsBranch(last) && last.Arg is int target) block.Next.Add(target);
                if (last.Op is not ("br" or "br.s" or "leave" or "leave.s" or "ret" or "throw" or "rethrow" or "jmp"))
                {
                    if (sourceNext is not null && sourceNext.TryGetValue(last.Offset, out int next)) block.Next.Add(next);
                    else if (sourceNext is null && b + 1 < ordered.Length) block.Next.Add(ordered[b + 1].Start);
                }
                if (sourceSlice is null && block.Next.Any(next => !Blocks.ContainsKey(next))) throw new NotSupportedException("invalid_branch_target");
            }
            if (sourceSlice is not null)
            {
                foreach (int target in ordered.SelectMany(b => b.Next).Distinct().Where(t => !Blocks.ContainsKey(t)).ToArray())
                    Blocks[target] = new Block { Start = target };
                Unknown.Add("source_slice_entry_and_external_CFG_targets_unresolved");
            }
            DetermineHeights();
            foreach (Block block in Blocks.Values.Where(b => b.Height >= 0)) DecodeBlock(block);
            LinkLocals();
            foreach (Block block in ordered.Where(b => b.Height > 0))
                for (int slot = 0; slot < block.Height; slot++)
                {
                    var input = Values[Entry(block.Start, slot)];
                    foreach (Block predecessor in ordered.Where(p => p.Next.Contains(block.Start) && p.Height >= 0))
                        input.Inputs.Add(predecessor.Exit[slot]);
                }
        }

        private static string Entry(int block, int slot) => "in" + block + ":" + slot;
        private static bool IsBranch(AmmoIl i) => i.Op.StartsWith("br", StringComparison.Ordinal)
            || i.Op.StartsWith("beq", StringComparison.Ordinal) || i.Op.StartsWith("bne", StringComparison.Ordinal)
            || i.Op.StartsWith("bge", StringComparison.Ordinal) || i.Op.StartsWith("bgt", StringComparison.Ordinal)
            || i.Op.StartsWith("ble", StringComparison.Ordinal) || i.Op.StartsWith("blt", StringComparison.Ordinal)
            || i.Op.StartsWith("leave", StringComparison.Ordinal);
        private static bool EndsBlock(AmmoIl i) => IsBranch(i) || i.Op is "switch" or "ret" or "throw" or "rethrow" or "jmp";

        private (int Pop, int Push) StackEffect(AmmoIl i)
        {
            if (i.Op == "const") return (0, 1);
            if (i.Op is "call" or "callvirt" or "newobj")
            {
                if (i.Arg is not MethodBase call) throw new NotSupportedException("unresolved_call");
                return (call.GetParameters().Length + (i.Op != "newobj" && !call.IsStatic ? 1 : 0),
                    i.Op == "newobj" || call is MethodInfo info && info.ReturnType != typeof(void) ? 1 : 0);
            }
            if (i.Op == "ret") return (Method is MethodInfo m && m.ReturnType != typeof(void) ? 1 : 0, 0);
            OpCode opcode = AmmoOpcodes.Values.First(op => op.Name == i.Op);
            int pop = opcode.StackBehaviourPop switch
            {
                StackBehaviour.Pop0 => 0,
                StackBehaviour.Pop1 or StackBehaviour.Popi or StackBehaviour.Popref => 1,
                StackBehaviour.Pop1_pop1 or StackBehaviour.Popi_pop1 or StackBehaviour.Popi_popi or StackBehaviour.Popi_popi8
                    or StackBehaviour.Popi_popr4 or StackBehaviour.Popi_popr8 or StackBehaviour.Popref_pop1 or StackBehaviour.Popref_popi => 2,
                StackBehaviour.Popi_popi_popi or StackBehaviour.Popref_popi_pop1 or StackBehaviour.Popref_popi_popi
                    or StackBehaviour.Popref_popi_popi8 or StackBehaviour.Popref_popi_popr4 or StackBehaviour.Popref_popi_popr8
                    or StackBehaviour.Popref_popi_popref => 3,
                _ => throw new NotSupportedException("variable_stack_effect")
            };
            int push = opcode.StackBehaviourPush switch
            {
                StackBehaviour.Push0 => 0,
                StackBehaviour.Push1 or StackBehaviour.Pushi or StackBehaviour.Pushi8 or StackBehaviour.Pushr4
                    or StackBehaviour.Pushr8 or StackBehaviour.Pushref => 1,
                StackBehaviour.Push1_push1 => 2,
                _ => throw new NotSupportedException("variable_stack_effect")
            };
            return (pop, push);
        }

        private void DetermineHeights()
        {
            var queue = new Queue<Block>();
            foreach (int entry in sliceEntries) { Blocks[entry].Height = 0; queue.Enqueue(Blocks[entry]); }
            while (queue.Count > 0)
            {
                Block block = queue.Dequeue();
                int height = block.Height;
                foreach (AmmoIl i in block.Code)
                {
                    var effect = StackEffect(i);
                    if (height < effect.Pop) throw new NotSupportedException("stack_underflow");
                    height += effect.Push - effect.Pop;
                    if (i.Op is "leave" or "leave.s") height = 0;
                    if (height > 128) throw new NotSupportedException("stack_bound");
                }
                foreach (int next in block.Next)
                {
                    Block successor = Blocks[next];
                    if (successor.Height >= 0 && successor.Height != height) throw new NotSupportedException("inconsistent_stack_join");
                    if (successor.Height >= 0) continue;
                    successor.Height = height;
                    queue.Enqueue(successor);
                }
            }
        }

        private void DecodeBlock(Block block)
        {
            var stack = new List<string>();
            for (int slot = 0; slot < block.Height; slot++)
            {
                string id = Entry(block.Start, slot);
                Values[id] = new Value { Id = id, At = block.Start, Block = block.Start, Op = "predecessor_stack_alternatives" };
                stack.Add(id);
            }
            foreach (AmmoIl i in block.Code)
            {
                var effect = StackEffect(i);
                var inputs = stack.Skip(stack.Count - effect.Pop).ToList();
                stack.RemoveRange(stack.Count - effect.Pop, effect.Pop);
                if (i.Op == "dup") { stack.Add(inputs[0]); stack.Add(inputs[0]); continue; }
                var value = new Value { Id = i.Offset.ToString(CultureInfo.InvariantCulture), At = i.Offset, Block = block.Start,
                    Op = i.Op, Operand = i.Arg, Inputs = inputs };
                if (i.Op == "ldarg" && i.Arg is int argument && WrittenArguments.Contains(argument)) value.Op = "written_or_address_exposed_argument";
                Values[value.Id] = value;
                if (effect.Push == 1) stack.Add(value.Id);
                if (effect.Push > 1) throw new NotSupportedException("multiple_stack_results");
                if (i.Op is "stfld" or "stsfld" or "stloc" or "starg" or "stobj" or "initobj" or "cpobj" or "ret" or "throw"
                    || i.Op.StartsWith("stelem", StringComparison.Ordinal) || i.Op.StartsWith("stind", StringComparison.Ordinal)
                    || i.Op is "call" or "callvirt" or "newobj" || EndsBlock(i)) Statements.Add(value);
                if (i.Op is "leave" or "leave.s") stack.Clear();
            }
            block.Exit = stack;
        }

        private static Dictionary<int, HashSet<string>> CopyDefinitions(Dictionary<int, HashSet<string>> values)
            => values.ToDictionary(pair => pair.Key, pair => new HashSet<string>(pair.Value));
        private static bool SameDefinitions(Dictionary<int, HashSet<string>> a, Dictionary<int, HashSet<string>> b)
            => a.Count == b.Count && a.All(pair => b.TryGetValue(pair.Key, out var other) && pair.Value.SetEquals(other));

        private void LinkLocals()
        {
            var entryDefinitions = Method.GetMethodBody()!.LocalVariables.ToDictionary(local => local.LocalIndex,
                local => new HashSet<string> { "local_entry:" + local.LocalIndex });
            foreach (var local in Method.GetMethodBody()!.LocalVariables)
                Values["local_entry:" + local.LocalIndex] = new Value { Id = "local_entry:" + local.LocalIndex,
                    Op = "unresolved_local_entry", Operand = local.LocalType, At = 0, Block = 0 };
            bool changed = true;
            int passes = 0;
            while (changed)
            {
                if (++passes > 512) throw new NotSupportedException("local_dataflow_bound");
                changed = false;
                foreach (Block block in Blocks.Values.Where(b => b.Height >= 0))
                {
                    var incoming = sliceEntries.Contains(block.Start) ? CopyDefinitions(entryDefinitions) : new Dictionary<int, HashSet<string>>();
                    foreach (Block predecessor in Blocks.Values.Where(p => p.Height >= 0 && p.Next.Contains(block.Start)))
                        foreach (var pair in predecessor.Outgoing)
                        {
                            if (!incoming.TryGetValue(pair.Key, out var defs)) incoming[pair.Key] = defs = new HashSet<string>();
                            defs.UnionWith(pair.Value);
                        }
                    var outgoing = CopyDefinitions(incoming);
                    foreach (AmmoIl i in block.Code)
                        if (i.Op == "stloc" && i.Arg is int local) outgoing[local] = new HashSet<string> { i.Offset.ToString(CultureInfo.InvariantCulture) };
                    changed |= !SameDefinitions(outgoing, block.Outgoing);
                    block.Incoming = incoming; block.Outgoing = outgoing;
                }
            }
            foreach (Block block in Blocks.Values.Where(b => b.Height >= 0))
            {
                var definitions = CopyDefinitions(block.Incoming);
                foreach (AmmoIl i in block.Code)
                {
                    string id = i.Offset.ToString(CultureInfo.InvariantCulture);
                    if (i.Op == "ldloc" && i.Arg is int local)
                    {
                        if (EscapedLocals.Contains(local)) Values[id].Op = "address_exposed_local";
                        else if (definitions.TryGetValue(local, out var defs))
                        {
                            if (defs.Count <= 8) Values[id].Inputs.AddRange(defs.OrderBy(s => s, StringComparer.Ordinal));
                            else { Values[id].Op = "unresolved_local_definition_bound"; Unknown.Add("local_" + local + "_has_" + defs.Count + "_reaching_definitions"); }
                        }
                    }
                    if (i.Op == "stloc" && i.Arg is int stored) definitions[stored] = new HashSet<string> { id };
                }
            }
        }

        internal IEnumerable<Value> Definitions(string id)
        {
            var seen = new HashSet<string>();
            var pending = new Stack<string>(); pending.Push(id);
            while (pending.Count > 0 && seen.Count < 256)
            {
                string next = pending.Pop();
                if (!seen.Add(next) || !Values.TryGetValue(next, out var value)) continue;
                if (value.Op is "ldloc" or "stloc" or "predecessor_stack_alternatives")
                    foreach (string input in value.Inputs) pending.Push(input);
                else yield return value;
            }
        }

        internal JsonObject Project(IEnumerable<Value> roots, int controlLimit = 64)
        {
            var selected = new HashSet<string>();
            var opaqueLocals = new HashSet<string>();
            bool ExceedsDependencyBound(Value value)
            {
                if (value.Op is not ("ldloc" or "predecessor_stack_alternatives")) return false;
                var seen = new HashSet<string>(); var pending = new Stack<string>(value.Inputs);
                while (pending.Count > 0)
                {
                    string next = pending.Pop();
                    if (!seen.Add(next) || !Values.TryGetValue(next, out var dependency)) continue;
                    if (seen.Count > 96) return true;
                    foreach (string input in dependency.Inputs) pending.Push(input);
                }
                return false;
            }
            void Include(string id)
            {
                var pending = new Stack<string>(); pending.Push(id);
                while (pending.Count > 0)
                {
                    string next = pending.Pop();
                    if (!selected.Add(next) || !Values.TryGetValue(next, out var value)) continue;
                    if (ExceedsDependencyBound(value)) { opaqueLocals.Add(next); continue; }
                    foreach (string input in value.Inputs) pending.Push(input);
                }
            }
            var rootRows = roots.Distinct().ToArray();
            foreach (var value in rootRows) Include(value.Id);
            // Close the source slice over control dependencies too. Joins retain
            // the guards of ALL definitions, including ternaries and loop bodies.
            var branches = Statements.Where(v => v.Op == "switch" || IsBranch(new AmmoIl(v.At, v.Op, v.Operand))).ToArray();
            var retainedControls = new HashSet<string>();
            var omittedControls = new HashSet<string>();
            int previous;
            do
            {
                previous = selected.Count;
                var selectedBlocks = selected.Select(id => Values[id].Block).ToHashSet();
                foreach (var branch in branches.OrderBy(v => rootRows.Length == 0 ? v.At : rootRows.Min(root => Math.Abs(root.At - v.At))))
                {
                    var region = ControlledRegion(branch.Block);
                    if (selectedBlocks.Any(region.Contains))
                    {
                        if (retainedControls.Count < controlLimit || retainedControls.Contains(branch.Id))
                        { retainedControls.Add(branch.Id); Include(branch.Id); }
                        else omittedControls.Add(branch.Id);
                    }
                }
            } while (selected.Count != previous);
            // A by-ref local cannot be assigned a guessed dominating constant.
            // Keep its possible writes as source evidence alongside the refusal.
            if (selected.Any(id => Values[id].Op == "address_exposed_local"))
                foreach (var write in Statements.Where(v => v.Op.StartsWith("stind", StringComparison.Ordinal) || v.Op is "stobj" or "initobj")) Include(write.Id);
            var values = new JsonObject();
            foreach (var value in Values.Values.Where(v => selected.Contains(v.Id)))
            {
                var row = new JsonArray(JsonValue.Create(opaqueLocals.Contains(value.Id) ? "unresolved_local_or_stack_dependency_bound" : value.Op));
                row.Add(SourceOperand(value.Operand));
                row.Add(new JsonArray((opaqueLocals.Contains(value.Id) ? Enumerable.Empty<string>() : value.Inputs).Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()));
                row.Add(value.Block);
                values[value.Id] = row;
            }
            JsonObject result = MethodSourceIdentity(Method);
            result["signature"] = SourceMember(Method);
            result["static"] = Method.IsStatic;
            result["arguments"] = new JsonArray(Method.GetParameters().Select((p, n) => (JsonNode?)new JsonObject
            {
                ["slot"] = n + (Method.IsStatic ? 0 : 1), ["name"] = p.Name, ["type"] = p.ParameterType.FullName,
            }).ToArray());
            var fieldTypes = new JsonObject();
            foreach (var field in Values.Values.Where(v => selected.Contains(v.Id)).Select(v => v.Operand).OfType<FieldInfo>().Distinct())
                fieldTypes[SourceMember(field)] = field.FieldType.FullName;
            result["fieldTypes"] = fieldTypes;
            result["values"] = values;
            result["statements"] = new JsonArray(rootRows.Select(v => (JsonNode?)JsonValue.Create(v.Id)).ToArray());
            var includedBlocks = selected.Select(id => Values[id].Block).ToHashSet();
            result["blocks"] = new JsonArray(Blocks.Values.Where(b => b.Height >= 0 && includedBlocks.Contains(b.Start)).Select(b => (JsonNode?)new JsonArray(
                JsonValue.Create(b.Start),
                new JsonArray(b.Next.Select(n => (JsonNode?)JsonValue.Create(n)).ToArray()),
                selected.Contains(b.Code[^1].Offset.ToString(CultureInfo.InvariantCulture)) && EndsBlock(b.Code[^1]) ? JsonValue.Create(b.Code[^1].Offset) : null,
                new JsonArray(branches.Where(v => selected.Contains(v.Id) && v.Block != b.Start && ControlledRegion(v.Block).Contains(b.Start))
                    .Select(v => (JsonNode?)JsonValue.Create(v.Id)).ToArray())
            )).ToArray());
            result["coverage"] = "source_slice";
            if (omittedControls.Count > 0) result["unresolvedEnclosingBranchCount"] = omittedControls.Count;
            if (opaqueLocals.Count > 0) result["unresolvedLocalDependencyCount"] = opaqueLocals.Count;
            if (Unknown.Count > 0) result["unresolved"] = new JsonArray(Unknown.Distinct().Select(s => (JsonNode?)JsonValue.Create(s)).ToArray());
            return result;
        }
    }

    private static string SourceMember(MemberInfo member) => member switch
    {
        MethodBase method => (method.DeclaringType?.FullName ?? "") + "." + method.Name
            + (method is MethodInfo info && info.IsGenericMethod ? "<" + string.Join(",", info.GetGenericArguments().Select(t => t.FullName)) + ">" : "")
            + "(" + string.Join(",", method.GetParameters().Select(p => p.ParameterType.FullName)) + ")",
        Type type => type.FullName ?? type.Name,
        _ => member.DeclaringType?.FullName + "." + member.Name,
    };
    private static JsonNode? SourceOperand(object? operand) => operand switch
    {
        null => null,
        MemberInfo member => JsonValue.Create(SourceMember(member)),
        int[] targets => new JsonArray(targets.Select(n => (JsonNode?)JsonValue.Create(n)).ToArray()),
        float value when float.IsFinite(value) => JsonValue.Create(value),
        double value when double.IsFinite(value) => JsonValue.Create(value),
        int value => JsonValue.Create(value),
        long value => JsonValue.Create(value),
        string value => JsonValue.Create(value.Length <= 256 ? value : "unresolved_string_over_character_bound"),
        _ => JsonValue.Create("unsupported_operand"),
    };
}
