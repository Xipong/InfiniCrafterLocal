#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Analysis;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // A read-only source decompiler. Values are IL definitions, not runtime
    // values. No instruction, getter, constructor, operator or hook is invoked.
    // CFG joins retain every reaching definition; loops are never unrolled.
    private sealed partial class ParentSourceMethod
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
        private readonly Dictionary<int, BlockSet> reachable = new();
        private PostdominatorFacts? postdominators;
        private readonly Dictionary<int, BlockSet> controlRegions = new();
        private long reachabilityMemoBytes;
        private int[]? blockSetNodes;
        private Dictionary<int, int>? blockSetIndices;

        // Each possible start block has at most one reachability and one control
        // row. Budget both complete compact tables and their shared index map.
        internal static long ReachabilityMemoByteLimit(int blocks)
            => blocks * 64L + 2L * blocks * (192L + ((blocks + 63L) / 64L) * sizeof(ulong));

        internal sealed class BlockSet : IEnumerable<int>
        {
            private readonly int[] nodes;
            private readonly Dictionary<int, int> indices;
            private readonly ulong[] words;

            internal BlockSet(int[] nodes, Dictionary<int, int> indices, ulong[] words)
            {
                this.nodes = nodes;
                this.indices = indices;
                this.words = words;
            }

            internal bool Contains(int node)
                => indices.TryGetValue(node, out int bit) && (words[bit >> 6] & (1UL << (bit & 63))) != 0;

            public IEnumerator<int> GetEnumerator()
            {
                for (int bit = 0; bit < nodes.Length; bit++)
                    if ((words[bit >> 6] & (1UL << (bit & 63))) != 0) yield return nodes[bit];
            }
            System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() => GetEnumerator();
        }

        private (int[] Nodes, Dictionary<int, int> Indices) ReachabilityLayout()
        {
            if (blockSetNodes is not null) return (blockSetNodes, blockSetIndices!);
            // Keep a new layout local until a complete row can be retained.
            int[] nodes = Blocks.Keys.ToArray();
            var indices = nodes.Select((node, index) => (node, index))
                .ToDictionary(pair => pair.node, pair => pair.index);
            return (nodes, indices);
        }

        private BlockSet RetainReachability(Dictionary<int, BlockSet> memo, int start,
            (int[] Nodes, Dictionary<int, int> Indices) layout, ulong[] words)
        {
            // Called only under memoGate. Construction and failed CFG analysis
            // cannot publish partial sets; every retained row is immutable.
            var retained = new BlockSet(layout.Nodes, layout.Indices, words);
            memo.Add(start, retained);
            if (blockSetNodes is null)
            {
                blockSetNodes = layout.Nodes;
                blockSetIndices = layout.Indices;
                reachabilityMemoBytes = Blocks.Count * 64L;
            }
            reachabilityMemoBytes += 192L + ((Blocks.Count + 63L) / 64L) * sizeof(ulong);
            return retained;
        }

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
        internal BlockSet Reach(int start)
        { lock (memoGate) return ReachCore(start); }
        private BlockSet ReachCore(int start)
        {
            if (reachable.TryGetValue(start, out var cached)) return cached;
            var layout = ReachabilityLayout();
            ulong[] words = IndexedBitSet.Reach(start, layout.Indices, Blocks, static block => block.Next);
            return RetainReachability(reachable, start, layout, words);
        }

        internal BlockSet ControlledRegion(int start)
        { lock (memoGate) return ControlledRegionCore(start); }
        private BlockSet ControlledRegionCore(int start)
        {
            if (controlRegions.TryGetValue(start, out var cached)) return cached;
            Block block = Blocks[start];
            if (block.Next.Distinct().Count() < 2)
            {
                var singleLayout = ReachabilityLayout();
                return RetainReachability(controlRegions, start, singleLayout,
                    IndexedBitSet.Singleton(start, singleLayout.Indices));
            }
            // The solver publishes one immutable compact matrix only after
            // convergence, so a refusal cannot leak partially solved facts.
            postdominators ??= SolvePostdominators();
            int join = postdominators.Join(start);
            var layout = ReachabilityLayout();
            ulong[] words = IndexedBitSet.ControlledRegion(start, join, layout.Indices, Blocks, static block => block.Next);
            return RetainReachability(controlRegions, start, layout, words);
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

        private void LinkLocals() => LinkLocalsBitsets();

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
            var localEvidence = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
            var inspectedLocalReads = new HashSet<string>(StringComparer.Ordinal);
            var localEvidenceUnknown = new HashSet<string>(StringComparer.Ordinal);
            // These are possible source writes, not reaching SSA definitions.
            // In particular a ref call remains opaque and is never evaluated.
            HashSet<int> AddressSlots(string id)
            {
                var result = new HashSet<int>();
                var seen = new HashSet<string>(StringComparer.Ordinal);
                var pending = new Stack<string>(); pending.Push(id);
                while (pending.Count > 0 && seen.Count < 128)
                {
                    string next = pending.Pop();
                    if (!seen.Add(next) || !Values.TryGetValue(next, out var value)) continue;
                    if (value.Op == "ldloca" && value.Operand is int slot) result.Add(slot);
                    else if (value.Op is "ldloc" or "stloc" or "predecessor_stack_alternatives")
                        foreach (string input in value.Inputs) pending.Push(input);
                    else if (value.Op == "ldflda" && value.Inputs.Count > 0) pending.Push(value.Inputs[0]);
                }
                if (pending.Count > 0) localEvidenceUnknown.Add("possible_local_address_bound");
                return result;
            }
            var writesByLocal = new Dictionary<int, List<Value>>();
            foreach (var statement in Statements)
            {
                var slots = new HashSet<int>();
                if (statement.Op == "stloc" && statement.Operand is int slot) slots.Add(slot);
                if (statement.Inputs.Count > 0 && (statement.Op.StartsWith("stind", StringComparison.Ordinal)
                    || statement.Op is "stobj" or "initobj" or "cpobj" or "stfld"))
                    slots.UnionWith(AddressSlots(statement.Inputs[0]));
                if (statement.Op is "call" or "callvirt" or "newobj" && statement.Operand is MethodBase call)
                {
                    var parameters = call.GetParameters();
                    for (int index = 0; index < statement.Inputs.Count; index++)
                    {
                        int parameter = index - (call.IsStatic || statement.Op == "newobj" ? 0 : 1);
                        if (parameter < 0 || parameter < parameters.Length && parameters[parameter].ParameterType.IsByRef)
                            slots.UnionWith(AddressSlots(statement.Inputs[index]));
                    }
                }
                foreach (int local in slots)
                {
                    if (!writesByLocal.TryGetValue(local, out var list)) writesByLocal[local] = list = new();
                    list.Add(statement);
                }
            }
            bool CanPrecede(Value write, Value read)
                => write.Id != read.Id && (write.Block != read.Block ? Reach(write.Block).Contains(read.Block)
                    : write.At < read.At || Blocks[write.Block].Next.Any(next => Reach(next).Contains(write.Block)));
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
                // Follow only the same proved local address. Unrelated ref
                // writes (often rendering temporaries) are not dependencies.
                // Include the writes before closing controls, and keep the read
                // opaque: this is provenance, not a fabricated mutation result.
                foreach (var read in selected.Select(id => Values[id]).Where(value =>
                    value.Op is "address_exposed_local" or "ldloca").ToArray())
                {
                    if (!inspectedLocalReads.Add(read.Id) || read.Operand is not int local) continue;
                    var candidates = writesByLocal.TryGetValue(local, out var writes)
                        ? writes.Where(write => CanPrecede(write, read)).Take(129).ToArray() : Array.Empty<Value>();
                    if (candidates.Length > 128) localEvidenceUnknown.Add("possible_local_write_bound");
                    var evidence = new HashSet<string>(StringComparer.Ordinal);
                    foreach (var write in candidates.Take(128)) { evidence.Add(write.Id); Include(write.Id); }
                    if (evidence.Count > 0) localEvidence[read.Id] = evidence;
                    if (read.Op == "address_exposed_local") localEvidenceUnknown.Add("address_exposed_local_value_unresolved");
                }
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
            if (localEvidence.Count > 0)
            {
                var evidence = new JsonObject();
                foreach (var (read, writes) in localEvidence)
                    evidence[read] = new JsonArray(writes.OrderBy(id => Values[id].At).Select(id => (JsonNode?)JsonValue.Create(id)).ToArray());
                result["possibleLocalWrites"] = evidence;
            }
            if (omittedControls.Count > 0) result["unresolvedEnclosingBranchCount"] = omittedControls.Count;
            if (opaqueLocals.Count > 0) result["unresolvedLocalDependencyCount"] = opaqueLocals.Count;
            if (Unknown.Count > 0 || localEvidenceUnknown.Count > 0)
                result["unresolved"] = new JsonArray(Unknown.Concat(localEvidenceUnknown).Distinct().Select(s => (JsonNode?)JsonValue.Create(s)).ToArray());
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
        internal const int CharacterLimit = 18000;
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
