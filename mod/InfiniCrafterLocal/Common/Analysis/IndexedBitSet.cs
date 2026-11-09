#nullable enable
using System;
using System.Collections.Generic;

namespace InfiniCrafterLocal.Common.Analysis;

// Build directly into the final compact row. The caller owns the complete,
// dense index map and publishes the returned array only after this call returns.
// No graph, scratch buffers or partially constructed rows are retained here.
internal static class IndexedBitSet
{
    internal static ulong[] Singleton(int start, Dictionary<int, int> indices)
    {
        var words = new ulong[(indices.Count + 63) / 64];
        Add(words, indices[start]);
        return words;
    }

    internal static ulong[] Reach<TNode>(int start, Dictionary<int, int> indices,
        Dictionary<int, TNode> graph, Func<TNode, List<int>> successors)
    {
        var words = new ulong[(indices.Count + 63) / 64];
        var pending = new Stack<int>();
        pending.Push(start);
        while (pending.Count > 0)
        {
            int next = pending.Pop();
            if (!Add(words, indices[next])) continue;
            foreach (int target in successors(graph[next])) pending.Push(target);
        }
        return words;
    }

    internal static ulong[] ControlledRegion<TNode>(int start, int join, Dictionary<int, int> indices,
        Dictionary<int, TNode> graph, Func<TNode, List<int>> successors)
    {
        // The start belongs to its own region even when it is also the join.
        // Successors are pushed in the supplied order, including repeated edges.
        var words = Singleton(start, indices);
        var pending = new Stack<int>(successors(graph[start]));
        while (pending.Count > 0)
        {
            int next = pending.Pop();
            if (next == join || !Add(words, indices[next])) continue;
            foreach (int target in successors(graph[next])) pending.Push(target);
        }
        return words;
    }

    private static bool Add(ulong[] words, int bit)
    {
        ref ulong word = ref words[bit >> 6];
        ulong mask = 1UL << (bit & 63);
        if ((word & mask) != 0) return false;
        word |= mask;
        return true;
    }
}
