using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static class SourceIntervalFixture
    {
        private static volatile int observed;

        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void Observe(int value) => observed = value;

        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public static int Branches(int kind, bool active, int value)
        {
            // Keep ordered effects on both arms: Release ILSpy can turn the
            // arithmetic-only fixture into ?: expressions, removing the exact
            // retained false subtree that the clone/move oracle must exercise.
            if (kind == 1)
            {
                if (active) { value += 11; Observe(value); }
                else { Observe(value); value += 12; }
            }
            else if (kind == 2)
            {
                if (active) { value += 21; Observe(value); }
                else if (value > 10) { Observe(value); value += 22; }
                else { value += 23; Observe(value); }
            }
            else if (kind == 3) value += 30;
            else
            {
                if (active) value += 41;
                else value += 42;
            }
            if (kind == 9) value += 90;
            return value;
        }
    }

    // Invoked by the already registered SourcePerformanceDocumentsRendering
    // check. The production helper is reflected; this is not a copied solver.
    private static void SourcePerformanceIntervalPruning()
    {
        var intervalType = CSharpOwner.GetNestedType("CSharpIlIntervalSet", CSharpFlags)!;
        var intersects = intervalType.GetMethod("Intersects", CSharpFlags)!;
        var add = intervalType.GetMethod("AddOffsets", CSharpFlags)!;
        void Compare((int Start, int End)[] ranges, int[] offsets)
        {
            Array.Sort(offsets);
            var interval = SourcePerformanceCreate("CSharpIlIntervalSet", ranges);
            bool expected = offsets.Any(offset => ranges.Any(range => range.Start <= offset && offset < range.End));
            Equal(expected, (bool)intersects.Invoke(interval, new object[] { offsets })!, "interval intersection matches nested Any oracle");
            var actual = new HashSet<int> { 999_999 };
            add.Invoke(interval, new object[] { offsets, actual, CancellationToken.None });
            var selected = offsets.Where(offset => ranges.Any(range => range.Start <= offset && offset < range.End)).ToHashSet();
            selected.Add(999_999);
            Equal(true, actual.SetEquals(selected), "interval union preserves holes, boundaries, existing offsets and duplicates");
        }
        Compare(Array.Empty<(int, int)>(), new[] { 0, 1 });
        Compare(new[] { (0, 2), (3, 4) }, new[] { 2 }); // never close a hole
        Compare(new[] { (0, 2), (2, 4), (1, 3) }, new[] { -1, 0, 2, 3, 4 });
        Compare(new[] { (5, 5), (9, 1), (int.MinValue, int.MinValue + 1), (int.MaxValue - 1, int.MaxValue) },
            new[] { int.MinValue, int.MinValue + 1, 0, int.MaxValue - 1, int.MaxValue });
        var random = new Random(339);
        for (int trial = 0; trial < 1024; trial++)
        {
            var ranges = Enumerable.Range(0, random.Next(80))
                .Select(_ => (Start: random.Next(-20, 600), End: random.Next(-20, 600))).ToArray();
            var offsets = Enumerable.Range(0, random.Next(150)).Select(_ => random.Next(-30, 620)).ToArray();
            Compare(ranges, offsets);
        }

        var method = typeof(SourceIntervalFixture).GetMethod(nameof(SourceIntervalFixture.Branches))!;
        using var module = (IDisposable)SourcePerformanceCreate("NativeCSharpModule", method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)SourcePerformanceCreate("NativeCSharpDocument", method, module, CancellationToken.None);
        var original = (SyntaxTree)CSharpFixtureMember(document, "Tree");
        var originalCode = (string)CSharpFixtureMember(SourcePerformanceRender(original, false), "Code");
        var originalNodes = original.DescendantsAndSelf.ToArray();
        var originalPositions = originalNodes.Select(node => (node.Parent, node.StartLocation, node.EndLocation)).ToArray();
        var originalAnnotations = originalNodes.Select(node => node.Annotations.ToArray()).ToArray();
        Equal(true, original.Descendants.OfType<IfElseStatement>().Any(branch => !branch.FalseStatement.IsNull),
            "fixture includes a real false arm, not only empty replacements");
        Equal(true, original.Descendants.OfType<IfElseStatement>().Any(branch =>
            branch.FalseStatement.DescendantsAndSelf.OfType<IfElseStatement>().Any()),
            "fixture retains a nested false-arm branch for preorder visitation parity");
        var prune = CSharpOwner.GetMethod("PruneOwnedCSharpIdentityBranches", CSharpFlags)!;
        var move = CSharpOwner.GetMethod("ReplaceOwnedCSharpStatement", CSharpFlags)!;
        string Condition(IfElseStatement branch)
            => (string)CSharpFixtureMember(SourcePerformanceRender(branch.Condition, false), "Code");
        void CompareRendering(SyntaxTree expected, SyntaxTree actual)
        {
            var oldRender = SourcePerformanceRender(expected, true);
            var newRender = SourcePerformanceRender(actual, true);
            Equal((string)CSharpFixtureMember(oldRender, "Code"), (string)CSharpFixtureMember(newRender, "Code"),
                "moving a private arm preserves byte-identical C#");
            Equal(true, ((Array)CSharpFixtureMember(oldRender, "Locations")).Cast<object>()
                .SequenceEqual(((Array)CSharpFixtureMember(newRender, "Locations")).Cast<object>()),
                "moving a private arm preserves ordered IL location tuples");
        }
        for (int seed = 0; seed < 32; seed++)
        {
            var expected = (SyntaxTree)original.Clone();
            var actual = (SyntaxTree)original.Clone();
            var oldVisits = new List<string>(); var newVisits = new List<string>();
            var oldDecisions = new Random(seed); var newDecisions = new Random(seed);
            // Exact old preorder snapshot + clone + detached-descendant rule.
            foreach (var branch in expected.Descendants.OfType<IfElseStatement>().ToArray())
            {
                if (!branch.Ancestors.Contains(expected)) continue;
                oldVisits.Add(Condition(branch));
                if (oldDecisions.Next(3) == 0) continue;
                branch.ReplaceWith(branch.FalseStatement.IsNull ? new EmptyStatement() : (Statement)branch.FalseStatement.Clone());
            }
            Func<IfElseStatement, int, bool> remove = (branch, _) =>
            {
                newVisits.Add(Condition(branch));
                return newDecisions.Next(3) != 0;
            };
            prune.Invoke(null, new object[] { actual, remove, CancellationToken.None });
            Equal(true, oldVisits.SequenceEqual(newVisits), "preorder move does not evaluate retained false descendants skipped by the legacy clone");
            CompareRendering(expected, actual);

            // Mechanics uses postorder: its retained children were processed
            // before their parent, so a plain move has the same visitation.
            expected = (SyntaxTree)original.Clone(); actual = (SyntaxTree)original.Clone();
            oldDecisions = new Random(seed); newDecisions = new Random(seed);
            foreach (var node in expected.Descendants.Reverse().ToArray())
                if (node is IfElseStatement branch && branch.Ancestors.Contains(expected))
                {
                    var arm = oldDecisions.Next(2) == 0 ? branch.TrueStatement : branch.FalseStatement;
                    branch.ReplaceWith(arm.IsNull ? new EmptyStatement() : (Statement)arm.Clone());
                }
            foreach (var node in actual.Descendants.Reverse().ToArray())
                if (node is IfElseStatement branch && branch.Ancestors.Contains(actual))
                {
                    var arm = newDecisions.Next(2) == 0 ? branch.TrueStatement : branch.FalseStatement;
                    move.Invoke(null, new object[] { branch, arm });
                }
            CompareRendering(expected, actual);
        }
        Equal(originalCode, (string)CSharpFixtureMember(SourcePerformanceRender(original, false), "Code"), "source AST not changed by private rewrites");
        Equal(true, originalNodes.SequenceEqual(original.DescendantsAndSelf), "source AST retains node identities");
        Equal(true, originalPositions.SequenceEqual(originalNodes.Select(node => (node.Parent, node.StartLocation, node.EndLocation))), "source AST retains parent links and positions");
        Equal(true, originalNodes.Select((node, index) => node.Annotations.SequenceEqual(originalAnnotations[index])).All(value => value), "source AST retains annotations");
        var getRanges = document.GetType().GetMethod("IdentityRanges", CSharpFlags)!;
        var copiedBranches = ((SyntaxTree)original.Clone()).Descendants.OfType<IfElseStatement>().ToArray();
        int[] nativePoints = Enumerable.Range(0, method.GetMethodBody()!.GetILAsByteArray()!.Length + 1).ToArray();
        for (int index = 0; index < copiedBranches.Length; index++)
            foreach (bool condition in new[] { false, true })
            {
                AstNode part = condition ? (AstNode)copiedBranches[index].Condition : copiedBranches[index].TrueStatement;
                var ranges = part.DescendantsAndSelf.SelectMany(node => node.Annotations.OfType<ILInstruction>())
                    .SelectMany(instruction => instruction.ILRanges).ToArray();
                var expected = nativePoints.Where(offset => ranges.Any(range => range.Start <= offset && offset < range.End)).ToHashSet();
                var memo = getRanges.Invoke(document, new object[] { index, condition, CancellationToken.None })!;
                var actual = new HashSet<int>();
                add.Invoke(memo, new object[] { nativePoints, actual, CancellationToken.None });
                Equal(true, actual.SetEquals(expected), "memoized original annotations match every cloned branch/guard range");
            }
        var stored = getRanges.Invoke(document, new object[] { 0, false, CancellationToken.None })!;
        Equal(true, ReferenceEquals(stored, getRanges.Invoke(document, new object[] { 0, false, CancellationToken.None })),
            "same original branch reuses immutable range facts across identities");
        var different = getRanges.Invoke(document, new object[] { 0, true, CancellationToken.None })!;
        Equal(false, ReferenceEquals(stored, different), "guard and true-body range facts are separate");
        Equal(true, (long)CSharpFixtureMember(document, "identityIntervalBytes") <=
            (long)document.GetType().GetField("IdentityIntervalByteLimit", CSharpFlags)!.GetRawConstantValue()!,
            "range memo uses its own bounded accounting");
        using var bounded = (IDisposable)SourcePerformanceCreate("NativeCSharpDocument", method, module, CancellationToken.None);
        getRanges.Invoke(bounded, new object[] { 0, false, CancellationToken.None });
        var retainedMap = (IDictionary)CSharpFixtureMember(bounded, "identityIntervals");
        int retainedBefore = retainedMap.Count;
        long limit = (long)bounded.GetType().GetField("IdentityIntervalByteLimit", CSharpFlags)!.GetRawConstantValue()!;
        bounded.GetType().GetField("identityIntervalBytes", CSharpFlags)!.SetValue(bounded, limit - 1);
        var oversized = getRanges.Invoke(bounded, new object[] { 0, true, CancellationToken.None });
        var retried = getRanges.Invoke(bounded, new object[] { 0, true, CancellationToken.None });
        Equal(false, ReferenceEquals(oversized, retried), "memo budget overflow computes exact ranges without retaining them");
        Equal(retainedBefore, retainedMap.Count, "memo budget pressure does not insert an unaccounted entry");
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
        CSharpSourceRefuses(() => getRanges.Invoke(document, new object[] { 0, false, cancelled.Token }), "canceled");
        Equal(true, ReferenceEquals(stored, getRanges.Invoke(document, new object[] { 0, false, CancellationToken.None })),
            "cancelled borrower cannot remove or replace a valid interval memo");
        CSharpSourceRefuses(() => prune.Invoke(null, new object[] { (SyntaxTree)original.Clone(),
            new Func<IfElseStatement, int, bool>((_, _) => throw new InvalidOperationException("cancel before callback")), cancelled.Token }), "canceled");
    }

    // Invoked after the small-document LRU/lifetime test has released its gate.
    private static void SourcePerformanceWeightedResidency()
    {
        var gate = CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!;
        lock (gate)
        {
            SourcePerformanceClearDocuments();
            try
            {
                var kill = typeof(Projectile).GetMethod("Kill", CSharpFlags, null, Type.EmptyTypes, null)!;
                var expensive = SourcePerformanceGetDocument(kill);
                Equal(true, (bool)CSharpOwner.GetMethod("IsExpensiveNativeCSharpDocument", CSharpFlags)!
                    .Invoke(null, new[] { expensive })!, "native Kill is a costly verified cache entry");
                foreach (var method in SourcePerformanceNativeMethods()) SourcePerformanceGetDocument(method);
                Equal(true, ReferenceEquals(expensive, SourcePerformanceGetDocument(kill)), "tiny helper pressure does not force expensive Kill redecompilation");
                var cache = (IDictionary)CSharpOwner.GetField("nativeCSharpDocuments", CSharpFlags)!.GetValue(null)!;
                int Limit(string name) => (int)CSharpOwner.GetField(name, CSharpFlags)!.GetRawConstantValue()!;
                Equal(true, cache.Count <= Limit("NativeCSharpResidentDocuments"), "resident document ceiling");
                Equal(true, cache.Values.Cast<object>().Sum(document => (int)CSharpFixtureMember(document, "Nodes")) <= Limit("NativeCSharpResidentNodes"), "resident node ceiling");
                Equal(true, cache.Values.Cast<object>().Sum(document => (int)CSharpFixtureMember(document, "Characters")) <= Limit("NativeCSharpResidentCharacters"), "resident character ceiling");
                Equal(true, cache.Values.Cast<object>().All(document => (int)CSharpFixtureMember(document, "Nodes") <= Limit("NativeCSharpNodeLimit")), "per-method node admission is not relaxed");
                Equal(true, cache.Values.Cast<object>().All(document => (int)CSharpFixtureMember(document, "Characters") <= Limit("NativeCSharpCodeLimit")), "per-method character admission is not relaxed");
            }
            finally { SourcePerformanceClearDocuments(); }
        }
    }
}
