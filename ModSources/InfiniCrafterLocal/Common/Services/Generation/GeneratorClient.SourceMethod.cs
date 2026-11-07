#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Numerics;
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
        }
        internal readonly MethodBase Method;
        private readonly bool completeSource;
        internal readonly Dictionary<string, Value> Values = new();
        internal readonly List<Value> Statements = new();
        internal readonly Dictionary<int, Block> Blocks = new();
        internal readonly HashSet<int> EscapedLocals = new();
        internal readonly HashSet<int> WrittenArguments = new();
        internal readonly List<string> Unknown = new();
        internal readonly List<AmmoIl> Code;
        private readonly HashSet<int> sliceEntries = new();
        private readonly Dictionary<int, List<Block>> predecessors = new();
        private static readonly Dictionary<string, OpCode> OpcodesByName = AmmoOpcodes.Values
            .Where(op => op.Name is not null).ToDictionary(op => op.Name!, StringComparer.Ordinal);
        private readonly Dictionary<int, HashSet<int>> reachable = new();
        // Only the selected immediate postdominator is needed after solving.
        // The dense bit matrix is temporary, not retained by cached methods.
        private Dictionary<int, int>? postdominators;
        private readonly Dictionary<int, HashSet<int>> controlRegions = new();
        private long lazySetMemoBytes;
        private long LazySetMemoBudgetBytes => Math.Min(4L * 1024 * 1024,
            2L * Blocks.Count * (240L + 48L * Blocks.Count));
        internal long LazyMemoReservationBytes => LazySetMemoBudgetBytes + 128L + 64L * Blocks.Count;

        internal readonly HashSet<int> CompleteCallPrefixes = new();

        internal static ParentSourceMethod ForCallPrefixes(MethodBase method, List<AmmoIl> code, IEnumerable<MethodBase> callees)
        {
            // Complete predecessor closure over the original method, not an
            // identity-window slice. Unrelated terminating arms need not be
            // decoded; every normal path into a selected call is retained.
            // Constructor admission rejects any included exception region, so
            // handler/finally side effects can never be silently certified absent.
            var targets = callees.ToHashSet();
            var calls = code.Where(i => i.Arg is MethodBase call && targets.Contains(call)).Select(i => i.Offset).ToArray();
            if (calls.Length == 0) throw new NotSupportedException("call_prefix_missing");
            var predecessors = code.ToDictionary(i => i.Offset, _ => new List<int>());
            var next = code.Zip(code.Skip(1), (a, b) => (a.Offset, b.Offset)).ToDictionary(p => p.Item1, p => p.Item2);
            void Edge(int from, int to)
            {
                if (!predecessors.TryGetValue(to, out var incoming)) throw new NotSupportedException("call_prefix_invalid_target");
                incoming.Add(from);
            }
            foreach (var instruction in code)
            {
                if (instruction.Op == "switch" && instruction.Arg is int[] switches)
                    foreach (int target in switches) Edge(instruction.Offset, target);
                else if (IsBranch(instruction) && instruction.Arg is int target) Edge(instruction.Offset, target);
                if (instruction.Op is not ("br" or "br.s" or "leave" or "leave.s" or "ret" or "throw" or "rethrow" or "jmp")
                    && next.TryGetValue(instruction.Offset, out int following)) Edge(instruction.Offset, following);
            }
            var included = new HashSet<int>(); var pending = new Stack<int>(calls);
            while (pending.Count > 0)
            {
                int offset = pending.Pop(); if (!included.Add(offset)) continue;
                foreach (int predecessor in predecessors[offset]) pending.Push(predecessor);
            }
            var result = new ParentSourceMethod(method, code.Where(i => included.Contains(i.Offset)).ToList(), next);
            result.CompleteCallPrefixes.UnionWith(calls);
            return result;
        }

        private readonly object memoGate = new();
        private HashSet<int> RememberBlockSet(Dictionary<int, HashSet<int>> memo, int start, HashSet<int> result)
        {
            // Budget actual set capacity and dictionary entry overhead. Skipping
            // retention changes neither the returned set nor later computation.
            long cost = 192L + 16L * result.EnsureCapacity(0);
            if (cost <= LazySetMemoBudgetBytes - lazySetMemoBytes)
            {
                memo[start] = result;
                lazySetMemoBytes += cost;
            }
            return result;
        }

        internal HashSet<int> Reach(int start)
        { lock (memoGate) return ReachCore(start); }
        private HashSet<int> ReachCore(int start)
        {
            if (reachable.TryGetValue(start, out var cached)) return cached;
            var reached = new HashSet<int>(); var pending = new Stack<int>(); pending.Push(start);
            while (pending.Count > 0)
            {
                if ((reached.Count & 63) == 0) currentParentAnalysis?.ThrowIfCancelled();
                int next = pending.Pop(); if (!reached.Add(next)) continue;
                foreach (int target in Blocks[next].Next) pending.Push(target);
            }
            return RememberBlockSet(reachable, start, reached);
        }

        internal HashSet<int> ControlledRegion(int start)
        { lock (memoGate) return ControlledRegionCore(start); }
        private HashSet<int> ControlledRegionCore(int start)
        {
            if (controlRegions.TryGetValue(start, out var cached)) return cached;
            Block block = Blocks[start];
            var region = new HashSet<int> { start };
            if (block.Next.Distinct().Count() < 2) return region;
            if (postdominators is null)
            {
                var ordered = Blocks.Values.Where(b => b.Height >= 0).ToArray();
                var starts = ordered.Select(b => b.Start).Append(-1).ToArray();
                var indexes = starts.Select((offset, index) => (offset, index)).ToDictionary(pair => pair.offset, pair => pair.index);
                int exit = ordered.Length, words = (starts.Length + 63) / 64;
                ulong lastWord = starts.Length % 64 == 0 ? ulong.MaxValue : (1UL << (starts.Length % 64)) - 1;
                var solved = new ulong[starts.Length][];
                for (int index = 0; index < exit; index++)
                {
                    solved[index] = new ulong[words];
                    Array.Fill(solved[index], ulong.MaxValue);
                    solved[index][^1] = lastWord;
                }
                solved[exit] = new ulong[words];
                solved[exit][exit >> 6] = 1UL << (exit & 63);
                var successors = ordered.Select(current => current.Next.Count == 0
                    ? new[] { exit } : current.Next.Select(next => indexes[next]).ToArray()).ToArray();
                var common = new ulong[words];
                // Publish memoized control facts only after convergence. A
                // refusal/exception must not make a later projection consume a
                // partially solved CFG (including another row in an export).
                bool changed = true; int passes = 0;
                while (changed)
                {
                    currentParentAnalysis?.ThrowIfCancelled();
                    if (++passes > 2048) throw new NotSupportedException("control_dependency_bound");
                    changed = false;
                    for (int current = exit - 1; current >= 0; current--)
                    {
                        if ((current & 63) == 0) currentParentAnalysis?.ThrowIfCancelled();
                        int[] next = successors[current];
                        Array.Copy(solved[next[0]], common, words);
                        for (int successor = 1; successor < next.Length; successor++)
                            for (int word = 0; word < words; word++) common[word] &= solved[next[successor]][word];
                        common[current >> 6] |= 1UL << (current & 63);
                        if (!common.AsSpan().SequenceEqual(solved[current]))
                        { Array.Copy(common, solved[current], words); changed = true; }
                    }
                }
                var counts = solved.Select(row => row.Sum(word => BitOperations.PopCount(word))).ToArray();
                var joins = new Dictionary<int, int>(ordered.Length);
                for (int current = 0; current < exit; current++)
                {
                    int best = -1, bestCount = -1;
                    for (int word = 0; word < words; word++)
                    {
                        ulong remaining = solved[current][word];
                        while (remaining != 0)
                        {
                            int candidate = word * 64 + BitOperations.TrailingZeroCount(remaining);
                            remaining &= remaining - 1;
                            if (candidate != current && counts[candidate] > bestCount)
                            { best = starts[candidate]; bestCount = counts[candidate]; }
                        }
                    }
                    // A tie can occur in a non-terminating region whose row
                    // stayed universal. Its original insertion order is the
                    // block order above, matching the HashSet solver's tie.
                    joins[starts[current]] = best;
                }
                currentParentAnalysis?.ThrowIfCancelled();
                postdominators = joins;
            }
            int join = postdominators[start];
            var pending = new Stack<int>(block.Next);
            while (pending.Count > 0)
            {
                if ((region.Count & 63) == 0) currentParentAnalysis?.ThrowIfCancelled();
                int next = pending.Pop();
                if (next == join || !region.Add(next)) continue;
                foreach (int successor in Blocks[next].Next) pending.Push(successor);
            }
            return RememberBlockSet(controlRegions, start, region);
        }

        internal ParentSourceMethod(MethodBase method, List<AmmoIl>? sourceSlice = null, Dictionary<int, int>? sourceNext = null, Dictionary<int, int>? selectedSuccessors = null)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            Method = method;
            completeSource = sourceSlice is null && sourceNext is null && selectedSuccessors is null;
            // A full method containing exception regions is unsupported regardless
            // of its instructions. Refuse before decoding potentially huge IL.
            if (sourceSlice is null && method.GetMethodBody()?.ExceptionHandlingClauses.Count > 0)
                throw new NotSupportedException("exception_regions");
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
            if (selectedSuccessors is not null)
                foreach (var (start, successor) in selectedSuccessors)
                {
                    if (!Blocks.TryGetValue(start, out var block) || !block.Next.Contains(successor))
                        throw new NotSupportedException("identity_selection_invalid_successor");
                    block.Next = new List<int> { successor };
                }
            foreach (int start in Blocks.Keys) predecessors[start] = new();
            foreach (Block predecessor in Blocks.Values)
                foreach (int next in predecessor.Next.Distinct()) predecessors[next].Add(predecessor);
            DetermineHeights();
            foreach (Block block in Blocks.Values.Where(b => b.Height >= 0)) DecodeBlock(block);
            LinkLocals();
            foreach (Block block in ordered.Where(b => b.Height > 0))
                for (int slot = 0; slot < block.Height; slot++)
                {
                    var input = Values[Entry(block.Start, slot)];
                    foreach (Block predecessor in predecessors[block.Start].Where(p => p.Height >= 0))
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
            OpCode opcode = OpcodesByName[i.Op];
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
            currentParentAnalysis?.ThrowIfCancelled();
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

        // During the fixed point, definitions are sorted immutable integer sets:
        // IL offsets are nonnegative, and ~localIndex denotes an unknown entry.
        // Most sets are shared singletons. A join allocates only when neither
        // input already contains the exact union; no alternatives are truncated.
        private static int[] UnionDefinitions(int[] left, int[] right)
        {
            if (ReferenceEquals(left, right)) return left;
            int l = 0, r = 0, count = 0;
            while (l < left.Length && r < right.Length)
            {
                int compare = left[l].CompareTo(right[r]);
                if (compare <= 0) l++;
                if (compare >= 0) r++;
                count++;
            }
            count += left.Length - l + right.Length - r;
            if (count == left.Length) return left;
            if (count == right.Length) return right;
            var merged = new int[count]; l = 0; r = 0; int at = 0;
            while (l < left.Length && r < right.Length)
            {
                int compare = left[l].CompareTo(right[r]);
                merged[at++] = compare <= 0 ? left[l] : right[r];
                if (compare <= 0) l++;
                if (compare >= 0) r++;
            }
            Array.Copy(left, l, merged, at, left.Length - l); at += left.Length - l;
            Array.Copy(right, r, merged, at, right.Length - r);
            return merged;
        }

        private static bool SameDefinitions(Dictionary<int, int[]> left, Dictionary<int, int[]> right)
            => left.Count == right.Count && left.All(pair => right.TryGetValue(pair.Key, out var other)
                && (ReferenceEquals(pair.Value, other) || pair.Value.AsSpan().SequenceEqual(other)));

        private void LinkLocals()
        {
            currentParentAnalysis?.ThrowIfCancelled();
            // A dispatcher slice keeps the original method's local metadata,
            // often thousands of slots which never occur in this source region.
            // Those slots cannot feed a decoded value or a local transfer. Keep
            // the exact reaching-definition solver over the referenced domain.
            var referenced = Code.Where(i => i.Op is "ldloc" or "stloc" or "ldloca")
                .Select(i => i.Arg).OfType<int>().ToHashSet();
            if (referenced.Count == 0) return;
            var locals = Method.GetMethodBody()!.LocalVariables.Where(local => referenced.Contains(local.LocalIndex)).ToArray();
            var entryDefinitions = locals.ToDictionary(local => local.LocalIndex,
                local => new[] { ~local.LocalIndex });
            foreach (var local in locals)
                Values["local_entry:" + local.LocalIndex] = new Value { Id = "local_entry:" + local.LocalIndex,
                    Op = "unresolved_local_entry", Operand = local.LocalType, At = 0, Block = 0 };
            var blocks = Blocks.Values.Where(block => block.Height >= 0).ToArray();
            var indexes = blocks.Select((block, index) => (block.Start, index)).ToDictionary(pair => pair.Start, pair => pair.index);
            var previous = blocks.Select(block => predecessors[block.Start].Where(p => p.Height >= 0)
                .Select(p => indexes[p.Start]).ToArray()).ToArray();
            var successors = blocks.Select(block => block.Next.Distinct().Select(next => indexes[next]).ToArray()).ToArray();
            var stores = blocks.Select(block =>
            {
                var last = new Dictionary<int, int[]>();
                foreach (AmmoIl instruction in block.Code)
                    if (instruction.Op == "stloc" && instruction.Arg is int local) last[local] = new[] { instruction.Offset };
                return last;
            }).ToArray();
            var needsIncoming = blocks.Select(block => block.Code.Any(instruction => instruction.Op == "ldloc")).ToArray();
            var incomingStates = new Dictionary<int, int[]>?[blocks.Length];
            var outgoingStates = blocks.Select(_ => new Dictionary<int, int[]>()).ToArray();
            var scheduled = new bool[blocks.Length]; Array.Fill(scheduled, true);
            var followingPass = new bool[blocks.Length];
            bool changed = true; int passes = 0;
            while (changed)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                if (++passes > 512) throw new NotSupportedException("local_dataflow_bound");
                changed = false;
                for (int index = 0; index < blocks.Length; index++)
                {
                    if (!scheduled[index]) continue;
                    scheduled[index] = false;
                    if ((index & 63) == 0) currentParentAnalysis?.ThrowIfCancelled();
                    var incoming = sliceEntries.Contains(blocks[index].Start)
                        ? new Dictionary<int, int[]>(entryDefinitions) : new Dictionary<int, int[]>();
                    foreach (int predecessor in previous[index])
                        foreach (var pair in outgoingStates[predecessor])
                        {
                            if (!incoming.TryGetValue(pair.Key, out var defs)) incoming[pair.Key] = pair.Value;
                            else incoming[pair.Key] = UnionDefinitions(defs, pair.Value);
                        }
                    if (needsIncoming[index]) incomingStates[index] = incoming;
                    var outgoing = stores[index].Count == 0 ? incoming : new Dictionary<int, int[]>(incoming);
                    foreach (var store in stores[index]) outgoing[store.Key] = store.Value;
                    if (SameDefinitions(outgoing, outgoingStates[index])) continue;
                    outgoingStates[index] = outgoing; changed = true;
                    // Preserve the original forward scan's rounds and bound:
                    // later successors run now; backedges run next round. A
                    // block with unchanged predecessors needs no recomputation.
                    foreach (int successor in successors[index])
                        if (successor > index) scheduled[successor] = true;
                        else followingPass[successor] = true;
                }
                (scheduled, followingPass) = (followingPass, scheduled);
            }

            // Bind the observable load inputs directly from temporary states.
            // Cached graphs retain only Value dependencies, not the solved
            // per-block maps or definitions that never feed a decoded load.
            var definitionIds = new Dictionary<int, string>();
            string DefinitionId(int id)
            {
                if (!definitionIds.TryGetValue(id, out string? text))
                {
                    string key = id < 0 ? "local_entry:" + ~id : id.ToString(CultureInfo.InvariantCulture);
                    definitionIds[id] = text = Values[key].Id;
                }
                return text;
            }
            for (int index = 0; index < blocks.Length; index++)
            {
                if ((index & 63) == 0) currentParentAnalysis?.ThrowIfCancelled();
                if (incomingStates[index] is not { } definitions) continue;
                Block block = blocks[index];
                // The fixed point is complete. Blocks with stores own separate
                // incoming/outgoing maps, and replay replaces only their slots.
                foreach (AmmoIl i in block.Code)
                {
                    if (i.Op is not ("ldloc" or "stloc")) continue;
                    string id = DefinitionId(i.Offset);
                    if (i.Op == "ldloc" && i.Arg is int local)
                    {
                        if (EscapedLocals.Contains(local)) Values[id].Op = "address_exposed_local";
                        else if (definitions.TryGetValue(local, out var defs))
                        {
                            if (defs.Length <= 8) Values[id].Inputs.AddRange(defs.Select(DefinitionId).OrderBy(s => s, StringComparer.Ordinal));
                            else { Values[id].Op = "unresolved_local_definition_bound"; Unknown.Add("local_" + local + "_has_" + defs.Length + "_reaching_definitions"); }
                        }
                    }
                    if (i.Op == "stloc" && i.Arg is int stored) definitions[stored] = new[] { i.Offset };
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
            if (pending.Count > 0) yield return new Value { Op = "unresolved_definition_traversal_bound" };
        }

        internal JsonObject Project(IEnumerable<Value> roots, int controlLimit = 64)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            var rootRows = roots.Distinct().ToArray();
            currentParentAnalysis?.ThrowIfCancelled();
            ParentSourceGraphCache? cache = completeSource ? activeParentSourceGraphCache ?? currentParentAnalysis?.SourceCache : null;
            string key = controlLimit.ToString(CultureInfo.InvariantCulture) + ":" + string.Join(",", rootRows.Select(value => value.Id));
            if (cache is not null && cache.TryGetProjection(Method, key, out string? retained))
                return JsonNode.Parse(retained!)!.AsObject();
            JsonObject result = ProjectCore(rootRows, controlLimit);
            currentParentAnalysis?.ThrowIfCancelled();
            cache?.RememberProjection(Method, key, result.ToJsonString());
            return result;
        }

        internal SourceGraphProjection ProjectForGraph(IEnumerable<Value> roots, int controlLimit = 64)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            var rootRows = roots.Distinct().ToArray();
            currentParentAnalysis?.ThrowIfCancelled();
            ParentSourceGraphCache? cache = completeSource ? activeParentSourceGraphCache ?? currentParentAnalysis?.SourceCache : null;
            string key = controlLimit.ToString(CultureInfo.InvariantCulture) + ":" + string.Join(",", rootRows.Select(value => value.Id));
            if (cache is not null && cache.TryGetGraphProjection(Method, key, out var retained)) return retained!;
            JsonObject row = ProjectCore(rootRows, controlLimit);
            var members = new List<MemberInfo>(); var counts = new List<int>();
            var indices = new Dictionary<string, int>(StringComparer.Ordinal);
            int Member(MemberInfo member)
            {
                string identity = member.Module.ModuleVersionId + ":" + member.MetadataToken + ":" + SourceMember(member);
                if (!indices.TryGetValue(identity, out int index))
                { index = members.Count; indices.Add(identity, index); members.Add(member); counts.Add(0); }
                counts[index]++; return index;
            }
            // These are template-local indices, never a graph's member table.
            CompactSourceMethod(row, Method, this, Member);
            var result = new SourceGraphProjection(row.ToJsonString(), members.ToArray(), counts.ToArray());
            currentParentAnalysis?.ThrowIfCancelled();
            cache?.RememberGraphProjection(Method, key, result);
            return result;
        }

        private JsonObject ProjectCore(Value[] rootRows, int controlLimit)
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
            foreach (var value in rootRows) Include(value.Id);
            // Close the source slice over control dependencies too. Joins retain
            // the guards of ALL definitions, including ternaries and loop bodies.
            var branches = Statements.Where(v => v.Op == "switch" || IsBranch(new AmmoIl(v.At, v.Op, v.Operand))).ToArray();
            var orderedBranches = branches.OrderBy(value => rootRows.Length == 0 ? value.At
                : rootRows.Min(root => Math.Abs(root.At - value.At))).ToArray();
            var retainedControls = new HashSet<string>();
            var omittedControls = new HashSet<string>();
            int previous;
            do
            {
                previous = selected.Count;
                var selectedBlocks = selected.Select(id => Values[id].Block).ToHashSet();
                foreach (var branch in orderedBranches)
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

    private static JsonObject CompactSourceMethod(JsonObject row, MethodBase method, ParentSourceMethod? body,
        Func<MemberInfo, int> member)
    {
        row.Remove("method"); row.Remove("signature"); row.Remove("fieldTypes"); row.Remove("sourceModuleVersionId");
        row["method"] = member(method);
        if (row["sourceMethodSha256"] is JsonNode sha) { row.Remove("sourceMethodSha256"); row["sha256"] = sha; }
        if (row["arguments"] is not null) row["arguments"] = new JsonArray(method.GetParameters().Select(p => (JsonNode?)JsonValue.Create(p.Name)).ToArray());
        if (body is not null && row["values"] is JsonObject values)
            foreach (var value in values)
                if (body.Values[value.Key].Operand is MemberInfo sourceMember) value.Value![1] = new JsonObject { ["member"] = member(sourceMember) };
        return row;
    }

    // Rebind a pure source template to the current graph. Counting reference
    // digits gives the exact JSON length without materializing rejected large
    // candidates. Every candidate still registers its members in original order.
    internal sealed class SourceGraphProjection
    {
        internal const int CharacterLimit = 6500;
        private readonly string? json;
        private readonly MemberInfo[] members;
        private readonly int[] uses;
        private readonly int characters;

        internal SourceGraphProjection(string json, MemberInfo[] members, int[] uses)
        {
            this.members = (MemberInfo[])members.Clone(); this.uses = (int[])uses.Clone(); characters = json.Length;
            long minimum = characters;
            for (int index = 0; index < members.Length; index++)
                minimum -= uses[index] * (index.ToString(CultureInfo.InvariantCulture).Length - 1);
            // A candidate too large even with all one-digit indices can never
            // be selected. Retain its exact length and registration effects,
            // not megabytes of JSON that no parent can consume.
            this.json = minimum <= CharacterLimit ? json : null;
        }

        internal long RetainedBytes => (json?.Length ?? 0) * (long)sizeof(char) + members.Length * 128L;
        internal (int[] Members, long Characters) Bind(Func<MemberInfo, int> register)
        {
            int[] mapping = members.Select(register).ToArray();
            long length = characters;
            for (int index = 0; index < mapping.Length; index++)
                length += uses[index] * (mapping[index].ToString(CultureInfo.InvariantCulture).Length
                    - index.ToString(CultureInfo.InvariantCulture).Length);
            return (mapping, length);
        }
        internal JsonObject Materialize(int[] mapping)
        {
            if (json is null) throw new InvalidOperationException("Oversized source projection cannot be materialized.");
            var row = JsonNode.Parse(json)!.AsObject();
            row["method"] = mapping[row["method"]!.GetValue<int>()];
            if (row["values"] is JsonObject values)
                foreach (var value in values)
                    if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode index)
                        operand["member"] = mapping[index.GetValue<int>()];
            return row;
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
