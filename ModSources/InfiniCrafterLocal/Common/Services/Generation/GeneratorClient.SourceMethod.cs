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
            // Numeric reaching-definition state. IDs are converted back to the
            // established string contract only when a load is published.
            internal ulong[] DefinitionIncoming = Array.Empty<ulong>();
            internal ulong[] DefinitionOutgoing = Array.Empty<ulong>();
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
        // Postdominators are dense by nature. Store their N x N relation as
        // bits instead of thousands of HashSet<int> objects.
        private ulong[]? postdominatorBits;
        private int[]? postdominatorNodes;
        private Dictionary<int, int>? postdominatorIndices;
        private int postdominatorWords;
        private readonly Dictionary<int, HashSet<int>> controlRegions = new();

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
        internal HashSet<int> Reach(int start)
        { lock (memoGate) return ReachCore(start); }
        private HashSet<int> ReachCore(int start)
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
        { lock (memoGate) return ControlledRegionCore(start); }
        private HashSet<int> ControlledRegionCore(int start)
        {
            if (controlRegions.TryGetValue(start, out var cached)) return cached;
            Block block = Blocks[start];
            var region = new HashSet<int> { start };
            if (block.Next.Distinct().Count() < 2) return region;
            EnsurePostdominators();
            int startIndex = postdominatorIndices![start];
            int row = startIndex * postdominatorWords;
            int join = -1, bestCount = -1;
            // Preserve the old insertion-order tie break: reachable blocks in
            // method order followed by the synthetic exit node.
            for (int candidate = 0; candidate < postdominatorNodes!.Length; candidate++)
            {
                if (candidate == startIndex || !Bit(postdominatorBits!, row, candidate)) continue;
                int count = PopCount(postdominatorBits!, candidate * postdominatorWords, postdominatorWords);
                if (count > bestCount) { bestCount = count; join = postdominatorNodes[candidate]; }
            }
            var pending = new Stack<int>(block.Next);
            while (pending.Count > 0)
            {
                int next = pending.Pop();
                if (next == join || !region.Add(next)) continue;
                foreach (int successor in Blocks[next].Next) pending.Push(successor);
            }
            return controlRegions[start] = region;
        }

        private void EnsurePostdominators()
        {
            if (postdominatorBits is not null) return;
            Block[] active = Blocks.Values.Where(block => block.Height >= 0).ToArray();
            int[] nodes = active.Select(block => block.Start).Append(-1).ToArray();
            var indices = nodes.Select((node, index) => (node, index)).ToDictionary(pair => pair.node, pair => pair.index);
            int words = (nodes.Length + 63) >> 6;
            var solved = new ulong[nodes.Length * words];
            ulong tailMask = nodes.Length % 64 == 0 ? ulong.MaxValue : (1UL << (nodes.Length % 64)) - 1;
            for (int index = 0; index < active.Length; index++)
            {
                int offset = index * words;
                for (int word = 0; word < words; word++) solved[offset + word] = ulong.MaxValue;
                solved[offset + words - 1] &= tailMask;
            }
            int exit = nodes.Length - 1;
            solved[exit * words + (exit >> 6)] |= 1UL << (exit & 63);
            var scratch = new ulong[words];
            bool changed = true; int passes = 0;
            while (changed)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                if (++passes > 2048) throw new NotSupportedException("control_dependency_bound");
                changed = false;
                for (int blockIndex = active.Length - 1; blockIndex >= 0; blockIndex--)
                {
                    Block current = active[blockIndex];
                    int first = current.Next.Count == 0 ? exit : indices[current.Next[0]];
                    Array.Copy(solved, first * words, scratch, 0, words);
                    for (int successorIndex = 1; successorIndex < current.Next.Count; successorIndex++)
                    {
                        int successor = indices[current.Next[successorIndex]] * words;
                        for (int word = 0; word < words; word++) scratch[word] &= solved[successor + word];
                    }
                    scratch[blockIndex >> 6] |= 1UL << (blockIndex & 63);
                    int row = blockIndex * words;
                    bool different = false;
                    for (int word = 0; word < words; word++)
                        if (solved[row + word] != scratch[word]) { different = true; break; }
                    if (!different) continue;
                    Array.Copy(scratch, 0, solved, row, words); changed = true;
                }
            }
            // Publish only a fully converged matrix. Cancellation/refusal never
            // leaves a partially solved relation visible to another projection.
            postdominatorNodes = nodes;
            postdominatorIndices = indices;
            postdominatorWords = words;
            postdominatorBits = solved;
        }

        private static bool Bit(ulong[] bits, int row, int index)
            => (bits[row + (index >> 6)] & (1UL << (index & 63))) != 0;
        private static int PopCount(ulong[] bits, int row, int words)
        {
            int count = 0;
            for (int word = 0; word < words; word++) count += BitOperations.PopCount(bits[row + word]);
            return count;
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

        // Reaching definitions are a monotone bitset problem. String IDs are
        // presentation only; keeping them in the fixed point previously made
        // every join allocate dictionaries/HashSets and repeatedly hash strings.
        private void LinkLocals()
        {
            var referenced = Code.Where(i => i.Op is "ldloc" or "stloc" or "ldloca")
                .Select(i => i.Arg).OfType<int>().ToHashSet();
            var locals = Method.GetMethodBody()!.LocalVariables.Where(local => referenced.Contains(local.LocalIndex)).ToArray();
            if (locals.Length == 0) return;

            var definitionIds = new List<string>();
            var localDefinitions = locals.ToDictionary(local => local.LocalIndex, _ => new List<int>());
            var entryBits = new Dictionary<int, int>();
            int AddDefinition(int local, string id)
            {
                int bit = definitionIds.Count;
                definitionIds.Add(id); localDefinitions[local].Add(bit);
                return bit;
            }
            foreach (var local in locals)
            {
                string id = "local_entry:" + local.LocalIndex;
                entryBits[local.LocalIndex] = AddDefinition(local.LocalIndex, id);
                Values[id] = new Value { Id = id, Op = "unresolved_local_entry", Operand = local.LocalType, At = 0, Block = 0 };
            }
            var storeBits = new Dictionary<int, int>();
            foreach (AmmoIl instruction in Code.Where(i => i.Op == "stloc" && i.Arg is int))
            {
                int local = (int)instruction.Arg!;
                if (localDefinitions.ContainsKey(local))
                    storeBits[instruction.Offset] = AddDefinition(local, instruction.Offset.ToString(CultureInfo.InvariantCulture));
            }

            int words = (definitionIds.Count + 63) >> 6;
            var localMasks = localDefinitions.ToDictionary(pair => pair.Key, pair => new ulong[words]);
            foreach (var pair in localDefinitions)
                foreach (int bit in pair.Value) localMasks[pair.Key][bit >> 6] |= 1UL << (bit & 63);
            var entryState = new ulong[words];
            foreach (int bit in entryBits.Values) entryState[bit >> 6] |= 1UL << (bit & 63);

            Block[] active = Blocks.Values.Where(block => block.Height >= 0).ToArray();
            var blockIndices = active.Select((block, index) => (block.Start, index)).ToDictionary(pair => pair.Start, pair => pair.index);
            var finalStores = new Dictionary<int, (int Local, int Bit)[]>();
            foreach (Block block in active)
            {
                block.DefinitionIncoming = new ulong[words];
                block.DefinitionOutgoing = new ulong[words];
                var stores = new Dictionary<int, int>();
                foreach (AmmoIl instruction in block.Code)
                    if (instruction.Op == "stloc" && instruction.Arg is int local && storeBits.TryGetValue(instruction.Offset, out int storedDefinitionBit))
                        stores[local] = bit;
                finalStores[block.Start] = stores.Select(pair => (pair.Key, pair.Value)).ToArray();
            }

            static void Or(ulong[] target, ulong[] source)
            {
                for (int word = 0; word < target.Length; word++) target[word] |= source[word];
            }
            static bool EqualBits(ulong[] left, ulong[] right)
            {
                for (int word = 0; word < left.Length; word++) if (left[word] != right[word]) return false;
                return true;
            }
            static void ClearLocal(ulong[] state, ulong[] mask)
            {
                for (int word = 0; word < state.Length; word++) state[word] &= ~mask[word];
            }
            static void Set(ulong[] state, int bit) => state[bit >> 6] |= 1UL << (bit & 63);
            static bool Has(ulong[] state, int bit) => (state[bit >> 6] & (1UL << (bit & 63))) != 0;

            var incoming = new ulong[words];
            var outgoing = new ulong[words];
            var queue = new Queue<Block>(active);
            var queued = Enumerable.Repeat(true, active.Length).ToArray();
            long work = 0, workBound = Math.Max(4096L, active.Length * 1024L);
            while (queue.Count > 0)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                if (++work > workBound) throw new NotSupportedException("local_dataflow_bound");
                Block block = queue.Dequeue(); queued[blockIndices[block.Start]] = false;
                Array.Clear(incoming);
                if (sliceEntries.Contains(block.Start)) Or(incoming, entryState);
                foreach (Block predecessor in predecessors[block.Start].Where(p => p.Height >= 0))
                    Or(incoming, predecessor.DefinitionOutgoing);
                if (!EqualBits(incoming, block.DefinitionIncoming)) Array.Copy(incoming, block.DefinitionIncoming, words);
                Array.Copy(incoming, outgoing, words);
                foreach (var store in finalStores[block.Start])
                {
                    ClearLocal(outgoing, localMasks[store.Local]);
                    Set(outgoing, store.Bit);
                }
                if (EqualBits(outgoing, block.DefinitionOutgoing)) continue;
                Array.Copy(outgoing, block.DefinitionOutgoing, words);
                foreach (int successorStart in block.Next)
                {
                    Block successor = Blocks[successorStart];
                    if (successor.Height < 0) continue;
                    int index = blockIndices[successorStart];
                    if (queued[index]) continue;
                    queued[index] = true; queue.Enqueue(successor);
                }
            }

            var state = new ulong[words];
            foreach (Block block in active)
            {
                Array.Copy(block.DefinitionIncoming, state, words);
                foreach (AmmoIl instruction in block.Code)
                {
                    string id = instruction.Offset.ToString(CultureInfo.InvariantCulture);
                    if (instruction.Op == "ldloc" && instruction.Arg is int local)
                    {
                        if (EscapedLocals.Contains(local)) Values[id].Op = "address_exposed_local";
                        else if (localDefinitions.TryGetValue(local, out var bits))
                        {
                            int count = 0;
                            foreach (int definitionBit in bits) if (Has(state, definitionBit)) count++;
                            if (count <= 8)
                            {
                                var ids = bits.Where(definitionBit => Has(state, definitionBit)).Select(definitionBit => definitionIds[definitionBit]).ToList();
                                ids.Sort(StringComparer.Ordinal); Values[id].Inputs.AddRange(ids);
                            }
                            else
                            {
                                Values[id].Op = "unresolved_local_definition_bound";
                                Unknown.Add("local_" + local + "_has_" + count + "_reaching_definitions");
                            }
                        }
                    }
                    if (instruction.Op == "stloc" && instruction.Arg is int stored && storeBits.TryGetValue(instruction.Offset, out int bit))
                    {
                        ClearLocal(state, localMasks[stored]); Set(state, storedDefinitionBit);
                    }
                }
            }
        }

        internal long RetainedBytesEstimate
        {
            get
            {
                long flow = Blocks.Values.Sum(block => (block.DefinitionIncoming.Length + (long)block.DefinitionOutgoing.Length) * sizeof(ulong));
                long postdom = (Blocks.Count + 1L) * (Blocks.Count + 1L + 7L) / 8L;
                return 4096L + Code.Count * 192L + Values.Count * 192L + Blocks.Count * 384L + flow + postdom;
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
