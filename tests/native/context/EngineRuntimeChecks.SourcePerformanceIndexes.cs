using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata.Ecma335;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;
using ICSharpCode.Decompiler.TypeSystem;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private sealed class SourceCallIndexFixture : Projectile
    {
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void RepeatedOverloads(int value, float other, string receiver)
        {
            damage = Math.Abs(value);
            damage += Math.Abs(value + 1);
            damage += Math.Abs(value + 2);
            rotation = Math.Abs(other);
            damage += receiver.Trim().Length;
        }
    }

    private static (int Offset, string Op, object? Arg)[] SourceIndexCode(MethodInfo method)
        => ((IEnumerable)CSharpOwner.GetMethod("AttackCode", CSharpFlags)!.Invoke(null, new object[] { method })!)
            .Cast<object>().Select(row => ((int)CSharpFixtureMember(row, "Offset"), (string)CSharpFixtureMember(row, "Op"),
                row.GetType().GetProperty("Arg")!.GetValue(row))).ToArray();

    // Independent pre-index oracle: scan every instruction for every invocation,
    // retaining the original exact predicate and unknown-diagnostic policy.
    private static HashSet<int> SourceIndexScanOracle(IEnumerable<InvocationExpression> invocations,
        (int Offset, string Op, object? Arg)[] code, JsonArray unknowns, bool includeAmbiguous)
    {
        var offsets = new HashSet<int>();
        foreach (var invocation in invocations)
        {
            if (invocation.GetSymbol() is not IMethod symbol) continue;
            int token = MetadataTokens.GetToken(symbol.MetadataToken);
            var ranges = invocation.DescendantsAndSelf.SelectMany(node => node.Annotations.OfType<ILInstruction>())
                .SelectMany(instruction => instruction.ILRanges).Where(range => range.End > range.Start).ToArray();
            var matches = code.Where(instruction => instruction.Op is "call" or "callvirt"
                && instruction.Arg is MethodBase called && called.MetadataToken == token
                && called.DeclaringType?.FullName == symbol.DeclaringType.FullName && called.Name == symbol.Name
                && ranges.Any(range => range.Start <= instruction.Offset && instruction.Offset < range.End)).ToArray();
            if (matches.Length == 1) offsets.Add(matches[0].Offset);
            else if (!unknowns.Any(value => value?.GetValue<string>() == "some_call_offsets_not_uniquely_mapped"))
                unknowns.Add("some_call_offsets_not_uniquely_mapped");
            if (includeAmbiguous) foreach (var match in matches) offsets.Add(match.Offset);
        }
        return offsets;
    }

    private static InvocationExpression SourceIndexRanges(InvocationExpression original, params (int Start, int End)[] ranges)
    {
        var invocation = (InvocationExpression)original.Clone();
        foreach (var node in invocation.DescendantsAndSelf) node.RemoveAnnotations<ILInstruction>();
        foreach (var range in ranges)
        {
            var annotation = new Nop();
            annotation.AddILRange(new ICSharpCode.Decompiler.Util.Interval(range.Start, range.End));
            invocation.AddAnnotation(annotation);
        }
        return invocation;
    }

    private static void MechanicsCallIndexMatchesScanningOracle()
    {
        var methods = new[] {
            typeof(SourceCallIndexFixture).GetMethod(nameof(SourceCallIndexFixture.RepeatedOverloads))!,
            typeof(MechanicsSourceFixture).GetMethod(nameof(MechanicsSourceFixture.ChildCalls))!,
            typeof(MechanicsSourceFixture).GetMethod(nameof(MechanicsSourceFixture.LocalChildTypes))!,
            typeof(MechanicsSourceFixture).GetMethod(nameof(MechanicsSourceFixture.ConditionalRegion))!,
            typeof(Projectile).GetMethod("Colliding", CSharpFlags)!,
            typeof(Projectile).GetMethod("VanillaAI", CSharpFlags)!,
            typeof(Projectile).GetMethod("Kill", CSharpFlags, null, Type.EmptyTypes, null)!
        };
        int compared = 0, lifecycleCompared = 0;
        foreach (var method in methods)
        {
            object Create(Type type, params object?[] values) => Activator.CreateInstance(type, CSharpFlags, null, values, null)!;
            using var module = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!, method.Module.FullyQualifiedName,
                File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
            using var document = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!, method, module, CancellationToken.None);
            var tree = (SyntaxTree)CSharpFixtureMember(document, "Tree");
            var render = CSharpOwner.GetMethod("RenderCSharp", CSharpFlags)!;
            var located = render.Invoke(null, new object[] { tree, true })!;
            var codeOnly = render.Invoke(null, new object[] { tree, false })!;
            Equal((string)CSharpFixtureMember(located, "Code"), (string)CSharpFixtureMember(codeOnly, "Code"), method.Name + " code-only rendering preserves bytes");
            Equal(0, ((Array)CSharpFixtureMember(codeOnly, "Locations")).Length, "code-only render skips locations");
            var index = Create(CSharpOwner.GetNestedType("NativeSourceCallIndex", CSharpFlags)!, method);
            var code = SourceIndexCode(method);
            var invocations = tree.Descendants.OfType<InvocationExpression>().ToArray();
            Equal(true, invocations.Length > 0, method.Name + " contains invocations");
            HashSet<int> Check(InvocationExpression[] calls, bool ambiguous)
            {
                var expectedGaps = new JsonArray("existing_diagnostic");
                var actualGaps = new JsonArray("existing_diagnostic");
                var expected = SourceIndexScanOracle(calls, code, expectedGaps, ambiguous);
                var actual = (HashSet<int>)CSharpOwner.GetMethod("MechanicsCallOffsets", CSharpFlags)!
                    .Invoke(null, new object[] { calls, index, actualGaps, ambiguous })!;
                Equal(true, expected.SetEquals(actual), method.Name + " exact call offsets");
                Equal(expectedGaps.ToJsonString(), actualGaps.ToJsonString(), method.Name + " unchanged diagnostics");
                compared++;
                return actual;
            }
            foreach (bool ambiguous in new[] { false, true })
            {
                foreach (var invocation in invocations) Check(new[] { invocation }, ambiguous);
                Check(invocations.Concat(invocations).ToArray(), ambiguous);
            }
            foreach (var invocation in invocations.Where(invocation => invocation.GetSymbol() is IMethod symbol
                && symbol.DeclaringType.FullName == typeof(Projectile).FullName && symbol.Name is "NewProjectile" or "NewProjectileDirect"))
            {
                var symbol = (IMethod)invocation.GetSymbol()!;
                int token = MetadataTokens.GetToken(symbol.MetadataToken);
                var ranges = invocation.DescendantsAndSelf.SelectMany(node => node.Annotations.OfType<ILInstruction>())
                    .SelectMany(instruction => instruction.ILRanges).Where(range => range.End > range.Start).ToArray();
                var expected = code.Where(instruction => instruction.Arg is MethodInfo called && called.MetadataToken == token
                    && called.DeclaringType == typeof(Projectile) && called.Name == symbol.Name
                    && called.GetParameters().Length == symbol.Parameters.Count && instruction.Op is "call" or "callvirt"
                    && ranges.Any(range => range.Start <= instruction.Offset && instruction.Offset < range.End)).Select(row => row.Offset).ToHashSet();
                var actual = (HashSet<int>)index.GetType().GetMethod("Match", CSharpFlags)!.Invoke(index, new object[] { invocation, symbol, true })!;
                Equal(true, expected.SetEquals(actual), method.Name + " exact lifecycle signature and offsets");
                lifecycleCompared++;
            }
            if (method.DeclaringType != typeof(SourceCallIndexFixture)) continue;
            var integer = invocations.First(invocation => invocation.GetSymbol() is IMethod symbol
                && symbol.Name == "Abs" && symbol.Parameters.Single().Type.FullName == "System.Int32");
            var floating = invocations.First(invocation => invocation.GetSymbol() is IMethod symbol
                && symbol.Name == "Abs" && symbol.Parameters.Single().Type.FullName == "System.Single");
            var sites = code.Where(row => row.Arg is MethodBase called && called.DeclaringType == typeof(Math)
                && called.Name == "Abs" && called.GetParameters().Single().ParameterType == typeof(int)).Select(row => row.Offset).ToArray();
            Equal(3, sites.Length, "repeated int overload native call sites");
            var disjoint = SourceIndexRanges(integer, (sites[0], sites[0] + 1), (sites[2], sites[2] + 1));
            Equal(0, Check(new[] { disjoint }, false).Count, "ambiguous removed call cannot be excluded");
            var retained = Check(new[] { disjoint, disjoint }, true);
            Equal(true, retained.SetEquals(new[] { sites[0], sites[2] }), "disjoint holes never admit middle call");
            var overlap = SourceIndexRanges(integer, (sites[0], sites[0] + 1), (sites[0], sites[0] + 1));
            Equal(1, Check(new[] { overlap }, false).Count, "overlapping annotations count a call once");
            Equal(0, Check(new[] { SourceIndexRanges(integer, (sites[0] - 1, sites[0])) }, true).Count, "range end is exclusive");
            Equal(0, Check(new[] { SourceIndexRanges(integer, (sites[0], sites[0])) }, true).Count, "empty ranges do not map");
            Equal(0, Check(new[] { SourceIndexRanges(floating, (sites[0], sites[2] + 1)) }, true).Count, "same name does not match another overload");
            Equal(0, Check(new[] { new InvocationExpression(new IdentifierExpression("Abs")) }, true).Count, "unbound syntax cannot prove a call");
            // Retained ambiguity must still veto removal, not just emit a warning.
            var removed = Check(new[] { overlap }, false);
            removed.ExceptWith(retained);
            Equal(0, removed.Count, "possibly retained calls cannot become excluded offsets");
        }
        Equal(true, lifecycleCompared > 0, "native lifecycle spawn mappings exercised");
        Console.WriteLine("mechanics call index oracle comparisons: " + compared + "; lifecycle: " + lifecycleCompared);
    }
}
