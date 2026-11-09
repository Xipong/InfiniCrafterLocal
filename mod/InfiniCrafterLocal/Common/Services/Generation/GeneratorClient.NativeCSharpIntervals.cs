#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // An exact union of half-open IL ranges. In particular, this is NOT a
    // min/max crop: gaps between disjoint annotations remain gaps. No native
    // instruction or expression is evaluated. Built from verified source annotations.
    private sealed class CSharpIlIntervalSet
    {
        private readonly (int Start, int End)[] intervals;
        internal bool IsEmpty => intervals.Length == 0;
        internal long RetainedBytes => 64L + intervals.LongLength * 2 * sizeof(int);

        internal CSharpIlIntervalSet(IEnumerable<(int Start, int End)> ranges)
        {
            ArgumentNullException.ThrowIfNull(ranges);
            var ordered = ranges.Where(range => range.End > range.Start)
                .OrderBy(range => range.Start).ThenBy(range => range.End).ToArray();
            if (ordered.Length == 0)
            {
                intervals = Array.Empty<(int, int)>();
                return;
            }
            int count = 0;
            foreach (var range in ordered)
            {
                if (count > 0 && range.Start <= ordered[count - 1].End)
                {
                    var previous = ordered[count - 1];
                    if (range.End > previous.End) ordered[count - 1] = (previous.Start, range.End);
                }
                else ordered[count++] = range;
            }
            if (count != ordered.Length) Array.Resize(ref ordered, count);
            intervals = ordered;
        }

        internal static CSharpIlIntervalSet FromNode(AstNode node, CancellationToken cancellation)
        {
            var ranges = new List<(int Start, int End)>();
            int work = 0;
            foreach (var part in node.DescendantsAndSelf)
            {
                if ((work++ & 255) == 0) cancellation.ThrowIfCancellationRequested();
                foreach (var instruction in part.Annotations.OfType<ILInstruction>())
                    foreach (var range in instruction.ILRanges)
                    {
                        if ((work++ & 255) == 0) cancellation.ThrowIfCancellationRequested();
                        if (range.End > range.Start) ranges.Add((range.Start, range.End));
                    }
            }
            cancellation.ThrowIfCancellationRequested();
            return new CSharpIlIntervalSet(ranges);
        }

        // Both callers build a sorted array once per specialization. Duplicate
        // offsets are harmless; no arithmetic on interval endpoints can overflow.
        private static int LowerBound(int[] sorted, int value)
        {
            int first = 0, last = sorted.Length;
            while (first < last)
            {
                int middle = first + ((last - first) >> 1);
                if (sorted[middle] < value) first = middle + 1;
                else last = middle;
            }
            return first;
        }

        internal bool Intersects(int[] sortedOffsets)
        {
            foreach (var range in intervals)
            {
                int first = LowerBound(sortedOffsets, range.Start);
                if (first < sortedOffsets.Length && sortedOffsets[first] < range.End) return true;
            }
            return false;
        }

        internal void AddOffsets(int[] sortedOffsets, HashSet<int> destination, CancellationToken cancellation)
        {
            int work = 0;
            foreach (var range in intervals)
            {
                cancellation.ThrowIfCancellationRequested();
                for (int index = LowerBound(sortedOffsets, range.Start);
                    index < sortedOffsets.Length && sortedOffsets[index] < range.End; index++)
                {
                    if ((work++ & 255) == 0) cancellation.ThrowIfCancellationRequested();
                    destination.Add(sortedOffsets[index]);
                }
            }
        }
    }

    // Reuse only immutable source ranges; selected edges, excluded instructions
    // and source maps remain request-local. The owning document is already
    // identified and reverified by GetNativeCSharpDocument on every request.
    private sealed partial class NativeCSharpDocument
    {
        private const long IdentityIntervalByteLimit = 2L * 1024 * 1024;
        private readonly object identityIntervalGate = new();
        private IfElseStatement[]? identityBranches;
        private readonly Dictionary<int, CSharpIlIntervalSet> identityIntervals = new();
        private long identityIntervalBytes;

        internal CSharpIlIntervalSet IdentityRanges(int branchIndex, bool condition,
            CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();
            lock (identityIntervalGate)
            {
                cancellation.ThrowIfCancellationRequested();
                if (identityBranches is null)
                {
                    identityBranches = Tree.Descendants.OfType<IfElseStatement>().ToArray();
                    identityIntervalBytes = 32L + identityBranches.LongLength * IntPtr.Size;
                }
                if ((uint)branchIndex >= (uint)identityBranches.Length)
                    throw new InvalidOperationException("CSharp identity branch snapshot does not match its document.");
                int key = checked(branchIndex * 2 + (condition ? 1 : 0));
                if (identityIntervals.TryGetValue(key, out var retained)) return retained;
                var branch = identityBranches[branchIndex];
                var result = CSharpIlIntervalSet.FromNode(condition ? (AstNode)branch.Condition : branch.TrueStatement,
                    cancellation);
                cancellation.ThrowIfCancellationRequested();
                long bytes = 128L + result.RetainedBytes;
                if (identityIntervalBytes + bytes <= IdentityIntervalByteLimit)
                {
                    identityIntervals.Add(key, result);
                    identityIntervalBytes += bytes;
                }
                // Oversized candidates still participate in the exact proof;
                // they are merely not retained. Cancellation never enters memo.
                return result;
            }
        }
    }

    // Only for a private cloned tree. A move, unlike another deep clone, also
    // keeps the node identities of already processed postorder descendants.
    private static void ReplaceOwnedCSharpStatement(Statement original, Statement selected)
    {
        if (selected.IsNull) original.ReplaceWith(new EmptyStatement());
        else
        {
            selected.Remove();
            original.ReplaceWith(selected);
        }
    }

    private static void PruneOwnedCSharpIdentityBranches(SyntaxTree tree,
        Func<IfElseStatement, int, bool> removeTrueArm, CancellationToken cancellation)
    {
        var branches = tree.Descendants.OfType<IfElseStatement>().ToArray();
        for (int index = 0; index < branches.Length; index++)
        {
            cancellation.ThrowIfCancellationRequested();
            var branch = branches[index];
            if (!branch.Ancestors.Contains(tree) || !removeTrueArm(branch, index)) continue;

            // The old preorder loop replaced this branch with a CLONE of its
            // false arm. Every original descendant in its iteration snapshot
            // was then detached and skipped, including descendants of that arm.
            // Moving the arm must preserve that exact visitation rule: do not
            // accidentally apply additional proofs to newly retained children.
            int following = index + 1;
            while (following < branches.Length && branches[following].Ancestors.Contains(branch))
            {
                cancellation.ThrowIfCancellationRequested();
                following++;
            }
            ReplaceOwnedCSharpStatement(branch, branch.FalseStatement);
            index = following - 1;
        }
    }
}
