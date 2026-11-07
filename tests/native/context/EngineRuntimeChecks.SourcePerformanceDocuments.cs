using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Threading;
using System.Threading.Tasks;
using ICSharpCode.Decompiler;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.Metadata;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static object SourcePerformanceCreate(string name, params object[] args)
        => Activator.CreateInstance(CSharpOwner.GetNestedType(name, CSharpFlags)!, CSharpFlags, null, args, null)!;

    private static object SourcePerformanceRender(AstNode tree, bool locations)
        => CSharpOwner.GetMethod("RenderCSharp", CSharpFlags)!.Invoke(null, new object[] { tree, locations })!;

    private static void SourcePerformanceDocumentsRendering()
    {
        var method = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.Closed))!;
        using var module = (IDisposable)SourcePerformanceCreate("NativeCSharpModule", method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
        CSharpSourceRefuses(() => SourcePerformanceCreate("NativeCSharpDocument", method, module, cancelled.Token), "canceled");
        Equal(true, module.GetType().GetField("typeSystem", CSharpFlags)!.GetValue(module) is null,
            "pre-cancelled document does not allocate a whole-module type system");
        using var document = (IDisposable)SourcePerformanceCreate("NativeCSharpDocument", method, module, CancellationToken.None);
        var shared = CSharpFixtureMember(module, "typeSystem");
        var codeOnly = CSharpFixtureMember(document, "original");
        Equal(0, ((Array)CSharpFixtureMember(codeOnly, "Locations")).Length,
            "character accounting does not eagerly build whole-method locations");
        var original = CSharpFixtureMember(document, "Original");
        Equal((string)CSharpFixtureMember(codeOnly, "Code"), (string)CSharpFixtureMember(original, "Code"),
            "lazy location materialization preserves the already bounded code");
        Equal(true, ReferenceEquals(original, CSharpFixtureMember(document, "Original")),
            "whole-method locations are materialized only once per retained document");
        var tree = (SyntaxTree)CSharpFixtureMember(document, "Tree");
        var nodes = tree.DescendantsAndSelf.ToArray();
        var positions = nodes.Select(node => (node.StartLocation, node.EndLocation, node.Parent)).ToArray();
        var annotations = nodes.Select(node => node.Annotations.ToArray()).ToArray();
        var withLocations = SourcePerformanceRender(tree, true);
        var withoutLocations = SourcePerformanceRender(tree, false);
        Equal((string)CSharpFixtureMember(withLocations, "Code"), (string)CSharpFixtureMember(withoutLocations, "Code"),
            "code-only rendering preserves exact text");
        Equal(0, ((Array)CSharpFixtureMember(withoutLocations, "Locations")).Length, "code-only rendering skips location collection");
        Equal(true, ((Array)CSharpFixtureMember(withLocations, "Locations")).Length > 0, "full rendering retains real IL locations");
        Equal((string)CSharpFixtureMember(withLocations, "Code"), (string)CSharpFixtureMember(original, "Code"), "original text is cached unchanged");
        Equal(true, ((Array)CSharpFixtureMember(withLocations, "Locations")).Cast<object>().SequenceEqual(
            ((Array)CSharpFixtureMember(original, "Locations")).Cast<object>()), "original IL locations are cached unchanged");
        Equal(true, nodes.SequenceEqual(tree.DescendantsAndSelf), "neither rendering path replaces or inserts source nodes");
        Equal(true, positions.SequenceEqual(nodes.Select(node => (node.StartLocation, node.EndLocation, node.Parent))),
            "neither rendering path mutates original coordinates or parents");
        Equal(true, nodes.Select((node, i) => node.Annotations.SequenceEqual(annotations[i])).All(value => value),
            "rendering preserves original annotations");

        // Differential oracles for the old deep-clone-then-drop AST paths.
        var declaration = (MethodDeclaration)CSharpFixtureMember(document, "Declaration");
        var originalSignature = (MethodDeclaration)declaration.Clone();
        originalSignature.Body = BlockStatement.Null;
        var signature = (MethodDeclaration)CSharpOwner.GetMethod("CloneCSharpWithoutBody", CSharpFlags)!
            .MakeGenericMethod(typeof(MethodDeclaration)).Invoke(null, new object[] { declaration, declaration })!;
        Equal((string)CSharpFixtureMember(SourcePerformanceRender(originalSignature, false), "Code"),
            (string)CSharpFixtureMember(SourcePerformanceRender(signature, false), "Code"),
            "signature shell is byte-equal without copying the original body");

        var firstBranch = tree.Descendants.OfType<IfElseStatement>().First();
        var originalExcerpt = (IfElseStatement)firstBranch.Clone();
        originalExcerpt.FalseStatement = Statement.Null;
        var excerpt = (IfElseStatement)CSharpOwner.GetMethod("CloneCSharpTrueArm", CSharpFlags)!
            .Invoke(null, new object[] { firstBranch })!;
        var owned = CSharpOwner.GetMethod("RenderOwnedCSharp", CSharpFlags)!.Invoke(null, new object[] { excerpt })!;
        var baselineExcerpt = SourcePerformanceRender(originalExcerpt, true);
        Equal((string)CSharpFixtureMember(baselineExcerpt, "Code"), (string)CSharpFixtureMember(owned, "Code"),
            "closed excerpt C# remains byte-equal");
        Equal(true, ((Array)CSharpFixtureMember(baselineExcerpt, "Locations")).Cast<object>().SequenceEqual(
            ((Array)CSharpFixtureMember(owned, "Locations")).Cast<object>()), "closed excerpt IL spans remain identical");

        var originalShell = (SyntaxTree)tree.Clone();
        originalShell.Descendants.OfType<MethodDeclaration>().Single().Body = new BlockStatement();
        var shell = (SyntaxTree)CSharpOwner.GetMethod("CloneCSharpWithoutBody", CSharpFlags)!
            .MakeGenericMethod(typeof(SyntaxTree)).Invoke(null, new object[] { tree, declaration })!;
        shell.Descendants.OfType<MethodDeclaration>().Single().Body = new BlockStatement();
        Equal((string)CSharpFixtureMember(SourcePerformanceRender(originalShell, false), "Code"),
            (string)CSharpFixtureMember(SourcePerformanceRender(shell, false), "Code"),
            "mechanics shell renders exactly like the legacy whole-tree clone");

        Equal(true, nodes.SequenceEqual(tree.DescendantsAndSelf), "scoped clones restore the complete shared AST");
        Equal(true, positions.SequenceEqual(nodes.Select(node => (node.StartLocation, node.EndLocation, node.Parent))),
            "scoped clones preserve original locations and parents");
        Equal(true, nodes.Select((node, i) => node.Annotations.SequenceEqual(annotations[i])).All(value => value),
            "scoped clones preserve every original IL annotation");

        // Compare actual old per-document setup against the shared type system,
        // not just two renderers over the same already-decompiled tree.
        using var legacyFile = new PEFile(method.Module.FullyQualifiedName);
        using var resolver = (IDisposable)SourcePerformanceCreate("NativeCSharpResolver", method.Module.FullyQualifiedName, CancellationToken.None);
        var legacy = new CSharpDecompiler(legacyFile, (IAssemblyResolver)resolver, new DecompilerSettings { ThrowOnAssemblyResolveErrors = true });
        var legacyTree = legacy.Decompile((MethodDefinitionHandle)MetadataTokens.Handle(method.MetadataToken));
        var legacyRendered = SourcePerformanceRender(legacyTree, true);
        Equal((string)CSharpFixtureMember(legacyRendered, "Code"), (string)CSharpFixtureMember(original, "Code"), "shared module preserves legacy CSharp bytes");
        Equal(true, ((Array)CSharpFixtureMember(legacyRendered, "Locations")).Cast<object>().SequenceEqual(
            ((Array)CSharpFixtureMember(original, "Locations")).Cast<object>()), "shared module preserves legacy location tuples");

        var literal = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.LiteralSource))!;
        using var second = (IDisposable)SourcePerformanceCreate("NativeCSharpDocument", literal, module, CancellationToken.None);
        Equal(true, ReferenceEquals(shared, CSharpFixtureMember(module, "typeSystem")), "documents share one type system");
        Equal(true, ReferenceEquals(shared, CSharpFixtureMember(CSharpFixtureMember(document, "Decompiler"), "TypeSystem"))
            && ReferenceEquals(shared, CSharpFixtureMember(CSharpFixtureMember(second, "Decompiler"), "TypeSystem")),
            "both actual decompilers borrow the shared type system");
        Equal(false, ReferenceEquals(CSharpFixtureMember(document, "Decompiler"), CSharpFixtureMember(second, "Decompiler")),
            "mutable transforms remain document-local");
        var literalTree = (SyntaxTree)CSharpFixtureMember(second, "Tree");
        Equal((string)CSharpFixtureMember(SourcePerformanceRender(literalTree, true), "Code"),
            (string)CSharpFixtureMember(SourcePerformanceRender(literalTree, false), "Code"), "code-only rendering preserves escaped CRLF literals");
        CSharpSourceRefuses(() => SourcePerformanceCreate("NativeCSharpDocument", literal, module, cancelled.Token), "canceled");
        Equal(true, ReferenceEquals(shared, CSharpFixtureMember(module, "typeSystem")), "cancelled document cannot retire shared state");

        var conditionalEnds = CSharpOwner.GetMethod("CSharpConditionalEnds", CSharpFlags)!;
        var ends = (IDictionary)conditionalEnds.Invoke(null, new object[] { method })!;
        var raw = ((IEnumerable)CSharpOwner.GetMethod("ReadAmmoIl", CSharpFlags)!.Invoke(null,
            new object[] { method, true, true })!).Cast<object>().ToArray();
        var expectedEnds = raw.Zip(raw.Skip(1), (instruction, next) => (instruction, next))
            .Where(pair => ((string)CSharpFixtureMember(pair.instruction, "Op")).StartsWith('b')
                && (string)CSharpFixtureMember(pair.instruction, "Op") is not ("br" or "br.s" or "break"))
            .ToDictionary(pair => (int)CSharpFixtureMember(pair.instruction, "Offset"), pair => (int)CSharpFixtureMember(pair.next, "Offset"));
        Equal(true, expectedEnds.Count > 0, "conditional index oracle includes real branch instructions");
        Equal(expectedEnds.Count, ends.Count, "conditional index preserves the old complete next-offset scan");
        foreach (var pair in expectedEnds) Equal(pair.Value, (int)ends[pair.Key]!, "conditional branch end remains exact");
        Equal(true, ReferenceEquals(ends, conditionalEnds.Invoke(null, new object[] { method })), "same IL decode reuses conditional index");
        CSharpOwner.GetMethod("ClearProjectileAttackCaches", CSharpFlags)!.Invoke(null, null);
        var rebuiltEnds = (IDictionary)conditionalEnds.Invoke(null, new object[] { method })!;
        Equal(false, ReferenceEquals(ends, rebuiltEnds), "source invalidation cannot reuse the retired decode index");
        foreach (var pair in expectedEnds) Equal(pair.Value, (int)rebuiltEnds[pair.Key]!, "rebuilt conditional index retains source offsets");
    }

    private static object SourcePerformanceGetDocument(MethodInfo method, CancellationToken cancellation = default)
        => CSharpOwner.GetMethod("GetNativeCSharpDocument", CSharpFlags)!.Invoke(null, new object[] { method, cancellation })!;

    private static void SourcePerformanceClearDocuments()
        => CSharpOwner.GetMethod("ClearNativeCSharpSourceCache", CSharpFlags)!.Invoke(null, null);

    private static MethodInfo[] SourcePerformanceNativeMethods()
        => typeof(Projectile).GetMethods(CSharpFlags | BindingFlags.DeclaredOnly)
            .Where(method => !method.IsSpecialName && !method.ContainsGenericParameters && method.GetMethodBody() is { } body
                && body.GetILAsByteArray()!.Length < 120 && body.ExceptionHandlingClauses.Count == 0)
            .OrderBy(method => method.MetadataToken).Take(10).ToArray();

    private static void SourcePerformanceDocumentsLruAndLifetime()
    {
        var gate = CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!;
        Task? clear = null;
        PEFile? mainFile = null;
        PEFile[] dependencies = Array.Empty<PEFile>();
        try
        {
            lock (gate)
            {
                SourcePerformanceClearDocuments();
                var methods = SourcePerformanceNativeMethods();
                Equal(10, methods.Length, "native fixture supplies enough small real methods for LRU eviction");
                var documents = methods.Take(8).Select(method => SourcePerformanceGetDocument(method)).ToArray();
                var module = CSharpFixtureMember(documents[0], "Module");
                var typeSystem = CSharpFixtureMember(module, "typeSystem");
                mainFile = (PEFile)CSharpFixtureMember(module, "file");
                dependencies = ((IEnumerable)CSharpFixtureMember(CSharpFixtureMember(module, "resolver"), "files")).Cast<PEFile>().ToArray();
                Equal(true, dependencies.Length > 0, "module owns resolved dependency readers as well as its main PE");
                Equal(true, documents.All(document => ReferenceEquals(module, CSharpFixtureMember(document, "Module"))), "all cached documents share one module");
                Equal(true, ReferenceEquals(documents[0], SourcePerformanceGetDocument(methods[0])), "cache hit returns same document and refreshes recency");
                SourcePerformanceGetDocument(methods[8]);
                var cache = (IDictionary)CSharpOwner.GetField("nativeCSharpDocuments", CSharpFlags)!.GetValue(null)!;
                Equal(8, cache.Count, "document count remains bounded at eight");
                Equal(true, cache.Values.Cast<object>().Contains(documents[0]), "recent hit survives the ninth insertion");
                Equal(false, cache.Values.Cast<object>().Contains(documents[1]), "least recently used rather than oldest-created document is evicted");
                Equal(true, ReferenceEquals(typeSystem, CSharpFixtureMember(module, "typeSystem")), "eviction preserves shared type system");
                Equal(true, mainFile.Reader.GetMetadata().Length > 0, "eviction preserves main PE reader");
                Equal(true, cache.Values.Cast<object>().Sum(document => (int)CSharpFixtureMember(document, "Nodes")) <= 200000, "retained nodes stay within original budget");
                Equal(true, cache.Values.Cast<object>().Sum(document => (int)CSharpFixtureMember(document, "Characters")) <= 1500000, "retained characters stay within original budget");
                Equal(true, cache.Values.Cast<object>().All(document => (int)CSharpFixtureMember(document, "Characters") <= 750000), "individual document bound unchanged");
                using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
                var order = ((IEnumerable)CSharpOwner.GetField("nativeCSharpOrder", CSharpFlags)!.GetValue(null)!).Cast<string>().ToArray();
                CSharpSourceRefuses(() => SourcePerformanceGetDocument(methods[0], cancelled.Token), "canceled");
                CSharpSourceRefuses(() => SourcePerformanceGetDocument(methods[9], cancelled.Token), "canceled");
                Equal(true, order.SequenceEqual(((IEnumerable)CSharpOwner.GetField("nativeCSharpOrder", CSharpFlags)!.GetValue(null)!).Cast<string>()),
                    "cancelled hit and miss leave LRU unchanged");
                using var started = new ManualResetEventSlim();
                clear = Task.Run(() => { started.Set(); SourcePerformanceClearDocuments(); });
                Equal(true, started.Wait(TimeSpan.FromSeconds(5)), "clear task started");
                Equal(false, clear.Wait(50), "cache clear waits for the locked borrower");
                Equal(true, mainFile.Reader.GetMetadata().Length > 0, "locked borrower keeps its reader alive until release");
            }
            Equal(true, clear!.Wait(TimeSpan.FromSeconds(10)), "clear completes after borrower releases gate");
            bool IsDisposed(PEFile file)
            {
                try { file.Reader.GetMetadata(); return false; }
                catch (ObjectDisposedException) { return true; }
            }
            Equal(true, IsDisposed(mainFile!), "clear disposes shared main PE");
            Equal(true, dependencies.All(IsDisposed), "clear disposes every resolved dependency PE");
            Equal(true, CSharpOwner.GetField("nativeCSharpModule", CSharpFlags)!.GetValue(null) is null, "clear drops module ownership");
            Equal(0, (int)CSharpOwner.GetField("nativeCSharpNodes", CSharpFlags)!.GetValue(null)!, "clear resets node accounting");
            Equal(0, (int)CSharpOwner.GetField("nativeCSharpCharacters", CSharpFlags)!.GetValue(null)!, "clear resets character accounting");
        }
        finally { clear?.GetAwaiter().GetResult(); SourcePerformanceClearDocuments(); }
    }

    private static void SourcePerformanceDocumentsVerifyCacheHits()
    {
        var gate = CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!;
        lock (gate)
        {
            SourcePerformanceClearDocuments();
            var field = CSharpOwner.GetField("nativeCSharpModule", CSharpFlags)!;
            object? originalModule = null;
            try
            {
                var method = typeof(Projectile).GetMethods(CSharpFlags | BindingFlags.DeclaredOnly)
                    .Where(candidate => !candidate.IsSpecialName && !candidate.ContainsGenericParameters && candidate.GetMethodBody() is { } body
                        && body.GetILAsByteArray()!.Length < 500 && body.LocalSignatureMetadataToken != 0 && body.ExceptionHandlingClauses.Count == 0)
                    .OrderBy(candidate => candidate.MetadataToken).First();
                var document = SourcePerformanceGetDocument(method);
                originalModule = field.GetValue(null)!;
                byte[] bytes = File.ReadAllBytes(method.Module.FullyQualifiedName);
                using var pe = new PEReader(new MemoryStream(bytes, writable: false));
                int start = CSharpFixtureBodyOffset(pe, method);
                int header = (bytes[start] & 3) == 2 ? 1 : (BitConverter.ToUInt16(bytes, start) >> 12) * 4;
                void Reject(byte[] altered, string reason)
                {
                    using var module = (IDisposable)SourcePerformanceCreate("NativeCSharpModule", method.Module.FullyQualifiedName, altered, method.Module.ModuleVersionId);
                    field.SetValue(null, module);
                    try { CSharpSourceRefuses(() => SourcePerformanceGetDocument(method), reason); }
                    finally { field.SetValue(null, originalModule); }
                    Equal(true, ReferenceEquals(document, SourcePerformanceGetDocument(method)), "failed verification does not replace valid cached document");
                }
                var il = (byte[])bytes.Clone(); il[start + header] ^= 1;
                Reject(il, "csharp_pe_il_mismatch");
                var metadata = (byte[])bytes.Clone();
                int name = metadata.AsSpan().IndexOf(System.Text.Encoding.UTF8.GetBytes(method.Name + "\0"));
                Equal(true, name >= 0, "native method name exists in metadata"); metadata[name] ^= 1;
                Reject(metadata, "csharp_pe_metadata_mismatch");
                Equal(true, header > 1, "cache-hit negative fixture has a real fat method header");
                var stack = (byte[])bytes.Clone(); stack[start + 2] ^= 1; Reject(stack, "csharp_pe_max_stack_mismatch");
                var init = (byte[])bytes.Clone(); init[start] ^= 0x10; Reject(init, "csharp_pe_init_locals_mismatch");
                var locals = (byte[])bytes.Clone(); Array.Clear(locals, start + 8, 4); Reject(locals, "csharp_pe_local_signature_mismatch");
            }
            finally { if (originalModule is not null) field.SetValue(null, originalModule); SourcePerformanceClearDocuments(); }
        }
    }
}
