#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Numerics;
using System.Reflection;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed partial class ParentSourceMethod
    {
        // Native identity specialization historically rebuilt the complete
        // method from AttackCode(method), after the same method had already
        // entered the shared source cache. This exact overload is selected only
        // by that MethodInfo + full-code call site. Reuse the immutable decoded
        // facts and keep specialization state outside the shared method.
        internal ParentSourceMethod(MethodInfo method, List<AmmoIl> completeSourceCode)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            ParentSourceMethod shared = ReadCompleteSourceMethod(method);
            if (completeSourceCode.Count != shared.Code.Count
                || completeSourceCode.Count == 0
                || completeSourceCode[0].Offset != shared.Code[0].Offset
                || completeSourceCode[^1].Offset != shared.Code[^1].Offset)
                throw new NotSupportedException("identity_source_not_complete_method");

            Method = shared.Method;
            completeSource = true;
            Values = shared.Values;
            Statements = shared.Statements;
            Blocks = shared.Blocks;
            EscapedLocals = shared.EscapedLocals;
            WrittenArguments = shared.WrittenArguments;
            Unknown = shared.Unknown;
            Code = shared.Code;
            sliceEntries = shared.sliceEntries;
            predecessors = shared.predecessors;
        }

        private sealed class LocalDefinitionLayout
        {
            internal readonly int FirstBit;
            internal readonly string[] Definitions;
            internal readonly int EntryBit;

            internal LocalDefinitionLayout(int firstBit, string[] definitions, bool hasEntry)
            {
                FirstBit = firstBit;
                Definitions = definitions;
                EntryBit = hasEntry ? firstBit : -1;
            }
        }

        private void LinkLocalsBitsets()
        {
            // Dispatcher slices keep the complete method's local metadata, but
            // only locals named by this source region can influence its values.
            // Give each reaching definition one numeric bit and solve only dirty
            // CFG rows. Strings are reconstructed solely at the JSON boundary.
            var referenced = Code.Where(i => i.Op is "ldloc" or "stloc" or "ldloca")
                .Select(i => i.Arg).OfType<int>().ToHashSet();
            if (referenced.Count == 0) return;

            var metadata = Method.GetMethodBody()!.LocalVariables
                .Where(local => referenced.Contains(local.LocalIndex))
                .ToDictionary(local => local.LocalIndex);
            var stores = referenced.ToDictionary(local => local, _ => new List<AmmoIl>());
            foreach (AmmoIl instruction in Code)
                if (instruction.Op == "stloc" && instruction.Arg is int local && stores.TryGetValue(local, out var rows))
                    rows.Add(instruction);

            var layouts = new Dictionary<int, LocalDefinitionLayout>();
            var storeBits = new Dictionary<int, int>();
            int totalBits = 0;
            foreach (int local in referenced.OrderBy(value => value))
            {
                bool hasEntry = metadata.TryGetValue(local, out LocalVariableInfo? info);
                var definitions = new List<string>(stores[local].Count + (hasEntry ? 1 : 0));
                if (hasEntry)
                {
                    string id = "local_entry:" + local;
                    definitions.Add(id);
                    Values[id] = new Value
                    {
                        Id = id,
                        Op = "unresolved_local_entry",
                        Operand = info!.LocalType,
                        At = 0,
                        Block = 0,
                    };
                }
                int firstBit = totalBits;
                foreach (AmmoIl store in stores[local])
                {
                    string id = store.Offset.ToString(CultureInfo.InvariantCulture);
                    storeBits.Add(store.Offset, totalBits + definitions.Count);
                    definitions.Add(id);
                }
                layouts.Add(local, new LocalDefinitionLayout(firstBit, definitions.ToArray(), hasEntry));
                totalBits += definitions.Count;
            }

            // Invalid/opaque local metadata can leave a referenced slot without
            // any representable definition. Preserve address-exposed refusals,
            // but there is no dataflow lattice to solve in that case.
            if (totalBits == 0)
            {
                foreach (AmmoIl instruction in Code)
                    if (instruction.Op == "ldloc" && instruction.Arg is int local && EscapedLocals.Contains(local))
                        Values[instruction.Offset.ToString(CultureInfo.InvariantCulture)].Op = "address_exposed_local";
                return;
            }

            Block[] active = Blocks.Values.Where(block => block.Height >= 0).ToArray();
            var blockIndices = active.Select((block, index) => (block.Start, index))
                .ToDictionary(pair => pair.Start, pair => pair.index);
            int words = (totalBits + 63) >> 6;
            var outgoing = new ulong[checked(active.Length * words)];
            var entry = new ulong[words];
            foreach (LocalDefinitionLayout layout in layouts.Values)
                if (layout.EntryBit >= 0) SetBit(entry, layout.EntryBit);

            var queue = new Queue<int>(active.Length);
            var queued = new bool[active.Length];
            for (int index = 0; index < active.Length; index++)
            {
                queue.Enqueue(index);
                queued[index] = true;
            }
            var incoming = new ulong[words];
            var candidate = new ulong[words];
            long steps = 0;
            long stepBound = Math.Max(512L, active.Length * 512L);
            while (queue.Count > 0)
            {
                if ((steps++ & 255) == 0) currentParentAnalysis?.ThrowIfCancelled();
                if (steps > stepBound) throw new NotSupportedException("local_dataflow_bound");
                int index = queue.Dequeue();
                queued[index] = false;
                Block block = active[index];
                Array.Clear(incoming, 0, words);
                if (sliceEntries.Contains(block.Start)) Or(incoming, entry, 0, words);
                foreach (Block predecessor in predecessors[block.Start])
                    if (predecessor.Height >= 0 && blockIndices.TryGetValue(predecessor.Start, out int predecessorIndex))
                        Or(incoming, outgoing, predecessorIndex * words, words);
                Array.Copy(incoming, candidate, words);
                ApplyLocalTransfers(candidate, block, layouts, storeBits);
                int row = index * words;
                if (SameRow(candidate, outgoing, row, words)) continue;
                Array.Copy(candidate, 0, outgoing, row, words);
                foreach (int successor in block.Next.Distinct())
                    if (blockIndices.TryGetValue(successor, out int successorIndex) && !queued[successorIndex])
                    {
                        queued[successorIndex] = true;
                        queue.Enqueue(successorIndex);
                    }
            }

            // Reconstruct only the small string sets consumed by ldloc rows.
            // This is intentionally a second linear pass: no block retains an
            // Incoming dictionary, and no fixed-point step allocates strings.
            foreach (Block block in active)
            {
                Array.Clear(incoming, 0, words);
                if (sliceEntries.Contains(block.Start)) Or(incoming, entry, 0, words);
                foreach (Block predecessor in predecessors[block.Start])
                    if (predecessor.Height >= 0 && blockIndices.TryGetValue(predecessor.Start, out int predecessorIndex))
                        Or(incoming, outgoing, predecessorIndex * words, words);
                foreach (AmmoIl instruction in block.Code)
                {
                    string id = instruction.Offset.ToString(CultureInfo.InvariantCulture);
                    if (instruction.Op == "ldloc" && instruction.Arg is int local)
                    {
                        if (EscapedLocals.Contains(local)) Values[id].Op = "address_exposed_local";
                        else if (layouts.TryGetValue(local, out LocalDefinitionLayout? layout))
                        {
                            int definitionCount = CountDefinitions(incoming, layout);
                            if (definitionCount <= 8)
                                Values[id].Inputs.AddRange(ReadDefinitions(incoming, layout)
                                    .OrderBy(value => value, StringComparer.Ordinal));
                            else
                            {
                                Values[id].Op = "unresolved_local_definition_bound";
                                Unknown.Add("local_" + local + "_has_" + definitionCount + "_reaching_definitions");
                            }
                        }
                    }
                    if (instruction.Op == "stloc" && instruction.Arg is int stored
                        && layouts.TryGetValue(stored, out LocalDefinitionLayout? storedLayout)
                        && storeBits.TryGetValue(instruction.Offset, out int storeBit))
                    {
                        ClearRange(incoming, storedLayout.FirstBit, storedLayout.Definitions.Length);
                        SetBit(incoming, storeBit);
                    }
                }
            }
        }

        private static void ApplyLocalTransfers(ulong[] state, Block block,
            Dictionary<int, LocalDefinitionLayout> layouts, Dictionary<int, int> storeBits)
        {
            foreach (AmmoIl instruction in block.Code)
                if (instruction.Op == "stloc" && instruction.Arg is int local
                    && layouts.TryGetValue(local, out LocalDefinitionLayout? layout)
                    && storeBits.TryGetValue(instruction.Offset, out int storeBit))
                {
                    ClearRange(state, layout.FirstBit, layout.Definitions.Length);
                    SetBit(state, storeBit);
                }
        }

        private static int CountDefinitions(ulong[] state, LocalDefinitionLayout layout)
        {
            int count = 0;
            VisitDefinitionWords(state, layout, word => count += BitOperations.PopCount(word));
            return count;
        }

        private static List<string> ReadDefinitions(ulong[] state, LocalDefinitionLayout layout)
        {
            var definitions = new List<string>(Math.Min(8, layout.Definitions.Length));
            int start = layout.FirstBit;
            VisitDefinitionWords(state, layout, (word, wordStart) =>
            {
                while (word != 0)
                {
                    int bit = BitOperations.TrailingZeroCount(word);
                    definitions.Add(layout.Definitions[wordStart + bit - start]);
                    word &= word - 1;
                }
            });
            return definitions;
        }

        private static void VisitDefinitionWords(ulong[] state, LocalDefinitionLayout layout, Action<ulong> visit)
            => VisitDefinitionWords(state, layout, (word, _) => visit(word));

        private static void VisitDefinitionWords(ulong[] state, LocalDefinitionLayout layout, Action<ulong, int> visit)
        {
            int start = layout.FirstBit;
            int end = start + layout.Definitions.Length;
            if (end <= start) return;
            for (int wordIndex = start >> 6; wordIndex <= (end - 1) >> 6; wordIndex++)
            {
                ulong word = state[wordIndex];
                int wordStart = wordIndex << 6;
                int lower = Math.Max(start - wordStart, 0);
                int upper = Math.Min(end - wordStart, 64);
                ulong mask = ulong.MaxValue << lower;
                if (upper < 64) mask &= (1UL << upper) - 1;
                visit(word & mask, wordStart);
            }
        }

        private static void SetBit(ulong[] state, int bit)
            => state[bit >> 6] |= 1UL << (bit & 63);

        private static void ClearRange(ulong[] state, int start, int count)
        {
            if (count == 0) return;
            int end = start + count;
            int firstWord = start >> 6;
            int lastWord = (end - 1) >> 6;
            int firstBit = start & 63;
            int lastBit = (end - 1) & 63;
            if (firstWord == lastWord)
            {
                ulong mask = (ulong.MaxValue << firstBit)
                    & (lastBit == 63 ? ulong.MaxValue : (1UL << (lastBit + 1)) - 1);
                state[firstWord] &= ~mask;
                return;
            }
            state[firstWord] &= ~(ulong.MaxValue << firstBit);
            for (int word = firstWord + 1; word < lastWord; word++) state[word] = 0;
            ulong lastMask = lastBit == 63 ? ulong.MaxValue : (1UL << (lastBit + 1)) - 1;
            state[lastWord] &= ~lastMask;
        }

        private static void Or(ulong[] destination, ulong[] source, int sourceOffset, int words)
        {
            for (int word = 0; word < words; word++) destination[word] |= source[sourceOffset + word];
        }

        private static bool SameRow(ulong[] candidate, ulong[] rows, int rowOffset, int words)
        {
            for (int word = 0; word < words; word++)
                if (candidate[word] != rows[rowOffset + word]) return false;
            return true;
        }

        private sealed class PostdominatorFacts
        {
            private readonly int[] nodes;
            private readonly Dictionary<int, int> indices;
            private readonly ulong[] rows;
            private readonly int[] counts;
            private readonly int words;

            internal PostdominatorFacts(int[] nodes, Dictionary<int, int> indices,
                ulong[] rows, int[] counts, int words)
            {
                this.nodes = nodes;
                this.indices = indices;
                this.rows = rows;
                this.counts = counts;
                this.words = words;
            }

            internal int Join(int start)
            {
                int row = indices[start] * words;
                int best = -1;
                int bestCount = -1;
                for (int candidate = 0; candidate < nodes.Length; candidate++)
                {
                    if (nodes[candidate] == start || (rows[row + (candidate >> 6)] & (1UL << (candidate & 63))) == 0)
                        continue;
                    if (counts[candidate] > bestCount)
                    {
                        best = nodes[candidate];
                        bestCount = counts[candidate];
                    }
                }
                return best;
            }
        }

        private PostdominatorFacts SolvePostdominators()
        {
            Block[] active = Blocks.Values.Where(block => block.Height >= 0).ToArray();
            int[] nodes = active.Select(block => block.Start).Append(-1).ToArray();
            var indices = nodes.Select((node, index) => (node, index))
                .ToDictionary(pair => pair.node, pair => pair.index);
            int words = (nodes.Length + 63) >> 6;
            var rows = new ulong[checked(nodes.Length * words)];
            ulong tailMask = (nodes.Length & 63) == 0 ? ulong.MaxValue : (1UL << (nodes.Length & 63)) - 1;
            for (int row = 0; row < active.Length; row++)
            {
                int offset = row * words;
                for (int word = 0; word < words; word++) rows[offset + word] = ulong.MaxValue;
                rows[offset + words - 1] &= tailMask;
            }
            int exitIndex = nodes.Length - 1;
            SetRowBit(rows, exitIndex * words, exitIndex);

            var queue = new Queue<int>(active.Length);
            var queued = new bool[active.Length];
            for (int index = active.Length - 1; index >= 0; index--)
            {
                queue.Enqueue(index);
                queued[index] = true;
            }
            var candidate = new ulong[words];
            long steps = 0;
            long stepBound = Math.Max(2048L, active.Length * 2048L);
            while (queue.Count > 0)
            {
                if ((steps++ & 255) == 0) currentParentAnalysis?.ThrowIfCancelled();
                if (steps > stepBound) throw new NotSupportedException("control_dependency_bound");
                int index = queue.Dequeue();
                queued[index] = false;
                Block block = active[index];
                int firstSuccessor;
                if (block.Next.Count == 0) firstSuccessor = exitIndex;
                else if (!indices.TryGetValue(block.Next[0], out firstSuccessor))
                    throw new NotSupportedException("control_dependency_invalid_successor");
                Array.Copy(rows, firstSuccessor * words, candidate, 0, words);
                for (int successorOffset = 1; successorOffset < block.Next.Count; successorOffset++)
                {
                    if (!indices.TryGetValue(block.Next[successorOffset], out int successor))
                        throw new NotSupportedException("control_dependency_invalid_successor");
                    int successorRow = successor * words;
                    for (int word = 0; word < words; word++) candidate[word] &= rows[successorRow + word];
                }
                SetBit(candidate, index);
                int rowOffset = index * words;
                if (SameRow(candidate, rows, rowOffset, words)) continue;
                Array.Copy(candidate, 0, rows, rowOffset, words);
                foreach (Block predecessor in predecessors[block.Start])
                    if (predecessor.Height >= 0 && indices.TryGetValue(predecessor.Start, out int predecessorIndex)
                        && predecessorIndex < active.Length && !queued[predecessorIndex])
                    {
                        queued[predecessorIndex] = true;
                        queue.Enqueue(predecessorIndex);
                    }
            }

            var counts = new int[nodes.Length];
            for (int row = 0; row < nodes.Length; row++)
            {
                int offset = row * words;
                int count = 0;
                for (int word = 0; word < words; word++) count += BitOperations.PopCount(rows[offset + word]);
                counts[row] = count;
            }
            return new PostdominatorFacts(nodes, indices, rows, counts, words);
        }

        private static void SetRowBit(ulong[] rows, int rowOffset, int bit)
            => rows[rowOffset + (bit >> 6)] |= 1UL << (bit & 63);
    }
}
