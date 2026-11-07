using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp.Syntax;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private sealed class SourceAstCloneProbe : ICloneable
    {
        internal int Clones;
        public object Clone() { Clones++; return new SourceAstCloneProbe(); }
    }

    [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
    private static string SourceAstReuseFixture(Projectile actor, int value)
    {
        if (actor.type == 643) { actor.rotation = value; actor.ai[0]++; }
        else { actor.velocity.X = value; actor.ai[1]++; }
        return "line1\r\nline2\"\\";
    }

    private static object SourceAstInvoke(string method, params object[] args)
        => CSharpOwner.GetMethod(method, CSharpFlags)!.Invoke(null, args)!;

    private static void SourceAstEqualRendering(AstNode legacy, AstNode owned, string purpose)
    {
        var expected = SourcePerformanceRender(legacy, true);
        var actual = SourceAstInvoke("RenderOwnedCSharp", owned, true);
        Equal((string)CSharpFixtureMember(expected, "Code"), (string)CSharpFixtureMember(actual, "Code"), purpose + " exact source bytes");
        Equal(true, ((Array)CSharpFixtureMember(expected, "Locations")).Cast<object>().SequenceEqual(
            ((Array)CSharpFixtureMember(actual, "Locations")).Cast<object>()), purpose + " exact IL/location tuples");
    }

    private static void SourceAstReusePreservesTextAndEvidence()
    {
        var method = typeof(EngineRuntimeChecks).GetMethod(nameof(SourceAstReuseFixture), CSharpFlags)!;
        using var module = (IDisposable)SourcePerformanceCreate("NativeCSharpModule", method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)SourcePerformanceCreate("NativeCSharpDocument", method, module, CancellationToken.None);
        var tree = (SyntaxTree)CSharpFixtureMember(document, "Tree");
        var declaration = (MethodDeclaration)CSharpFixtureMember(document, "Declaration");
        var branch = tree.Descendants.OfType<IfElseStatement>().Single(candidate => !candidate.FalseStatement.IsNull);
        var bodyProbe = new SourceAstCloneProbe(); declaration.Body.AddAnnotation(bodyProbe);
        var rootProbe = new SourceAstCloneProbe(); declaration.AddAnnotation(rootProbe);
        var immutableAnnotation = new object(); declaration.AddAnnotation(immutableAnnotation);
        var falseProbe = new SourceAstCloneProbe(); branch.FalseStatement.AddAnnotation(falseProbe);
        var branchProbe = new SourceAstCloneProbe(); branch.AddAnnotation(branchProbe);
        var nodes = tree.DescendantsAndSelf.ToArray();
        var positions = nodes.Select(node => (node.StartLocation, node.EndLocation, node.Parent, node.Role)).ToArray();
        var annotations = nodes.Select(node => node.Annotations.ToArray()).ToArray();

        var signature = (MethodDeclaration)SourceAstInvoke("CloneCSharpSignature", declaration);
        Equal(0, bodyProbe.Clones, "signature never visits the discarded method body");
        Equal(1, rootProbe.Clones, "signature preserves root annotation clone semantics");
        Equal(true, signature.Body.IsNull, "signature excludes its body");
        Equal(true, signature.Annotations.Contains(immutableAnnotation), "noncloneable root annotations remain shared as in AstNode.Clone");
        Equal(false, ReferenceEquals(rootProbe, signature.Annotations.OfType<SourceAstCloneProbe>().Single()),
            "cloneable root annotations belong to the private signature");
        var oldSignature = (MethodDeclaration)declaration.Clone(); oldSignature.Body = BlockStatement.Null;
        SourceAstEqualRendering(oldSignature, signature, "signature");

        falseProbe.Clones = 0; branchProbe.Clones = 0;
        var selected = (IfElseStatement)SourceAstInvoke("CloneCSharpTrueBranch", branch);
        Equal(0, falseProbe.Clones, "selected branch never visits the discarded else subtree");
        Equal(1, branchProbe.Clones, "selected branch preserves root annotation clone semantics");
        Equal(true, selected.FalseStatement.IsNull, "selected branch excludes its else subtree");
        Equal(true, selected.Children.Zip(branch.Children.Where(child => child != branch.FalseStatement),
            (copy, original) => copy.Role == original.Role && !ReferenceEquals(copy, original)).All(value => value),
            "retained branch children preserve roles and private ownership");
        var oldSelected = (IfElseStatement)branch.Clone(); oldSelected.FalseStatement = Statement.Null;
        SourceAstEqualRendering(oldSelected, selected, "selected branch");

        bodyProbe.Clones = 0;
        var shell = (SyntaxTree)SourceAstInvoke("CloneCSharpMethodShell", tree, declaration);
        Equal(0, bodyProbe.Clones, "conditional mechanics shell skips the whole discarded body");
        var oldShell = (SyntaxTree)tree.Clone(); oldShell.Descendants.OfType<MethodDeclaration>().Single().Body = new BlockStatement();
        SourceAstEqualRendering(oldShell, shell, "mechanics method shell");
        Equal(tree.FileName, shell.FileName, "mechanics shell preserves source filename metadata");
        var privateTree = (SyntaxTree)tree.Clone();
        SourceAstEqualRendering(tree, privateTree, "owned whole-method renderer");
        Equal(true, ((Array)CSharpFixtureMember(SourceAstInvoke("RenderOwnedCSharp", privateTree, true), "Locations")).Length > 0,
            "owned renderer still produces real IL evidence");
        Equal(true, nodes.SequenceEqual(tree.DescendantsAndSelf), "owned rendering leaves cached node identity and order unchanged");
        Equal(true, positions.SequenceEqual(nodes.Select(node => (node.StartLocation, node.EndLocation, node.Parent, node.Role))),
            "owned rendering never changes cached AST coordinates, parents or roles");
        Equal(true, nodes.Select((node, i) => node.Annotations.SequenceEqual(annotations[i])).All(value => value),
            "selective copies leave every original annotation attached to its source node");

        // The pinned reader currently emits a direct member. A future nested
        // declaration must retain the complete syntax and metadata as before.
        var nestedTree = new SyntaxTree { FileName = "nested-fixture.cs" };
        var container = new TypeDeclaration { Name = "Nested" }; nestedTree.Members.Add(container);
        var nestedMethod = (MethodDeclaration)declaration.Clone(); container.Members.Add(nestedMethod);
        var nestedLegacy = (SyntaxTree)nestedTree.Clone(); nestedLegacy.Descendants.OfType<MethodDeclaration>().Single().Body = new BlockStatement();
        SourceAstEqualRendering(nestedLegacy, (SyntaxTree)SourceAstInvoke("CloneCSharpMethodShell", nestedTree, nestedMethod),
            "nested method shell fallback");
    }

    private static void SourceAstReuseKeepsCompleteProof()
    {
        var method = typeof(EngineRuntimeChecks).GetMethod(nameof(SourceAstReuseFixture), CSharpFlags)!;
        using var cache = (IDisposable)SourcePerformanceCreate("ParentSourceGraphCache", false);
        using var scope = (IDisposable)cache.GetType().GetMethod("Enter", CSharpFlags)!.Invoke(cache, null)!;
        var complete = SourceAstInvoke("ReadCompleteSourceMethod", method);
        var raw = SourceAstInvoke("AttackCode", method);
        var legacy = SourcePerformanceCreate("ParentSourceMethod", method, raw, null!, null!);
        var oldSelection = SourcePerformanceCreate("AttackIdentitySelection", legacy, 643, 123, true);
        var selection = SourcePerformanceCreate("AttackIdentitySelection", complete, 643, 123, true, true);
        Equal(((JsonObject)CSharpFixtureMember(oldSelection, "Receipt")).ToJsonString(),
            ((JsonObject)CSharpFixtureMember(selection, "Receipt")).ToJsonString(), "complete method preserves the identity proof receipt");
        Equal((int)CSharpFixtureMember(oldSelection, "analysisWork"), (int)CSharpFixtureMember(selection, "analysisWork"),
            "explicit connectedness requirement preserves the legacy proof work bound");
        Equal(false, ((IEnumerable)CSharpFixtureMember(complete, "Unknown")).Cast<string>()
            .Contains("source_slice_entry_and_external_CFG_targets_unresolved"), "borrowing complete IR cannot mark shared state as a slice");
        using var module = (IDisposable)SourcePerformanceCreate("NativeCSharpModule", method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)SourcePerformanceCreate("NativeCSharpDocument", method, module, CancellationToken.None);
        var record = CSharpFixtureRecord(method, false);
        var before = cache.GetType().GetMethod("Snapshot", CSharpFlags)!.Invoke(cache, null)!;
        SourceAstInvoke("AttachIdentitySpecializedCSharp", record, document, 643, 123, CancellationToken.None);
        var after = cache.GetType().GetMethod("Snapshot", CSharpFlags)!.Invoke(cache, null)!;
        Equal((long)CSharpFixtureMember(before, "Hits") + 1, (long)CSharpFixtureMember(after, "Hits"),
            "CSharp specialization borrows the already built complete source method");
        Equal(true, ReferenceEquals(complete, SourceAstInvoke("ReadCompleteSourceMethod", method)), "specialization keeps the same cached IR");

        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("SourceAstDisconnectedFixture"), AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("fixture").DefineType("Source", TypeAttributes.Public);
        var builder = type.DefineMethod("Disconnected", MethodAttributes.Public | MethodAttributes.Static, typeof(void), new[] { typeof(Projectile) });
        var il = builder.GetILGenerator();
        il.Emit(OpCodes.Ret); il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Stfld, typeof(Projectile).GetField(nameof(Projectile.damage))!); il.Emit(OpCodes.Ret);
        var disconnected = type.CreateType()!.GetMethod("Disconnected")!;
        var disconnectedComplete = SourceAstInvoke("ReadCompleteSourceMethod", disconnected);
        var disconnectedLegacy = SourcePerformanceCreate("ParentSourceMethod", disconnected, SourceAstInvoke("AttackCode", disconnected), null!, null!);
        CSharpSourceRefuses(() => SourcePerformanceCreate("AttackIdentitySelection", disconnectedLegacy, 643, 123, true),
            "identity_selection_disconnected_source_components");
        CSharpSourceRefuses(() => SourcePerformanceCreate("AttackIdentitySelection", disconnectedComplete, 643, 123, true, true),
            "identity_selection_disconnected_source_components");
    }

    private static void SourceAstStableRefusalsAreBoundedAndVerified()
    {
        var gate = CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!;
        lock (gate)
        {
            SourcePerformanceClearDocuments();
            try
            {
                var refusals = (IDictionary)CSharpOwner.GetField("nativeCSharpRefusals", CSharpFlags)!.GetValue(null)!;
                var order = (LinkedList<string>)CSharpOwner.GetField("nativeCSharpRefusalOrder", CSharpFlags)!.GetValue(null)!;
                var moduleField = CSharpOwner.GetField("nativeCSharpModule", CSharpFlags)!;
                var method = SourcePerformanceNativeMethods()[0];
                var bytes = File.ReadAllBytes(method.Module.FullyQualifiedName);
                var module = SourcePerformanceCreate("NativeCSharpModule", method.Module.FullyQualifiedName, bytes, method.Module.ModuleVersionId);
                moduleField.SetValue(null, module);
                string key = (string)SourceAstInvoke("NativeCSharpDocumentKey", method, module);
                Equal(true, key.Contains((string)CSharpFixtureMember(module, "Sha256"), StringComparison.Ordinal), "stable refusal key includes exact PE bytes");
                Equal(true, key.Contains("8.2.0.7535", StringComparison.Ordinal), "stable refusal key includes pinned reader version");
                SourceAstInvoke("RememberNativeCSharpRefusal", key, "csharp_ast_node_bound", CancellationToken.None);
                CSharpSourceRefuses(() => SourcePerformanceGetDocument(method), "csharp_ast_node_bound");
                Equal(true, module.GetType().GetField("typeSystem", CSharpFlags)!.GetValue(module) is null,
                    "stable refusal avoids repeated decompilation and type-system construction");
                using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
                CSharpSourceRefuses(() => SourcePerformanceGetDocument(method, cancelled.Token), "canceled");
                CSharpSourceRefuses(() => SourceAstInvoke("RememberNativeCSharpRefusal", "cancelled", "csharp_ast_node_bound", cancelled.Token), "canceled");
                Equal(false, refusals.Contains("cancelled"), "cancellation cannot install a stable failure");
                foreach (string reason in new[] { "csharp_decompilation_time_bound", "csharp_decompiler_warnings", "csharp_open_generic_method_unsupported",
                    "csharp_pe_il_mismatch", "dependency_resolution_failure" })
                    SourceAstInvoke("RememberNativeCSharpRefusal", reason, reason, CancellationToken.None);
                Equal(1, refusals.Count, "transient, verification and nonwhitelisted failures are never cached");

                var altered = (byte[])bytes.Clone();
                using var pe = new System.Reflection.PortableExecutable.PEReader(new MemoryStream(altered, writable: false));
                int bodyOffset = CSharpFixtureBodyOffset(pe, method);
                int headerSize = (altered[bodyOffset] & 3) == 2 ? 1 : (BitConverter.ToUInt16(altered, bodyOffset) >> 12) * 4;
                altered[bodyOffset + headerSize] ^= 1;
                using (var invalid = (IDisposable)SourcePerformanceCreate("NativeCSharpModule", method.Module.FullyQualifiedName, altered, method.Module.ModuleVersionId))
                {
                    moduleField.SetValue(null, invalid);
                    string invalidKey = (string)SourceAstInvoke("NativeCSharpDocumentKey", method, invalid);
                    SourceAstInvoke("RememberNativeCSharpRefusal", invalidKey, "csharp_method_character_bound", CancellationToken.None);
                    try { CSharpSourceRefuses(() => SourcePerformanceGetDocument(method), "csharp_pe_il_mismatch"); }
                    finally { moduleField.SetValue(null, module); }
                }
                // Keep only the real method sentinel before filling the bound.
                refusals.Clear(); order.Clear();
                SourceAstInvoke("RememberNativeCSharpRefusal", key, "csharp_ast_node_bound", CancellationToken.None);
                for (int index = 0; index < 63; index++)
                    SourceAstInvoke("RememberNativeCSharpRefusal", "fixture:" + index, "csharp_method_character_bound", CancellationToken.None);
                CSharpSourceRefuses(() => SourcePerformanceGetDocument(method), "csharp_ast_node_bound");
                SourceAstInvoke("RememberNativeCSharpRefusal", "fixture:63", "csharp_method_character_bound", CancellationToken.None);
                Equal(64, refusals.Count, "stable refusal cache is independently bounded");
                Equal(64, order.Count, "stable refusal LRU has one node per entry");
                Equal(true, refusals.Contains(key), "cache hit refreshes the stable refusal lifetime");
                Equal(false, refusals.Contains("fixture:0"), "stable refusals evict the least recently used entry");
                SourcePerformanceClearDocuments();
                Equal(0, refusals.Count, "module invalidation clears stable refusals");
                Equal(0, order.Count, "module invalidation clears stable refusal order");
                Equal(true, SourcePerformanceGetDocument(method) is not null, "cleared refusal cannot suppress a valid fresh document");
            }
            finally { SourcePerformanceClearDocuments(); }
        }
    }
}
