#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Analysis;
using ICSharpCode.Decompiler;
using ICSharpCode.Decompiler.CSharp;
using ICSharpCode.Decompiler.CSharp.OutputVisitor;
using ICSharpCode.Decompiler.CSharp.Syntax;
using ICSharpCode.Decompiler.IL;
using ICSharpCode.Decompiler.Metadata;
using ICSharpCode.Decompiler.TypeSystem;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Source is evidence for the Author, never generated executable C#. The
    // established graph remains in the raw packet, including every refusal.
    // Decompile exact PE bytes rather than loading an assembly or invoking code.
    private const string NativeCSharpVersion = "8.2.0.7535";
    private const string NativeCSharpDecompilerSha256 = "d174072a16aa758a39d160f70ce924103898fae2b8506b48f70d6909e25a1fd0";
    private const string NativeCSharpDecompilerMvid = "bbf1c21f-b23e-4f21-bfdf-386d019c443e";
    private static readonly Lazy<bool> nativeCSharpDecompilerVerified = new(() =>
    {
        var assembly = typeof(CSharpDecompiler).Assembly;
        if (assembly.GetName().Version?.ToString() != NativeCSharpVersion
            || assembly.ManifestModule.ModuleVersionId.ToString() != NativeCSharpDecompilerMvid)
            throw new NotSupportedException("csharp_decompiler_identity_mismatch");
        string path = assembly.Location;
        if (!string.IsNullOrEmpty(path) && (!System.IO.File.Exists(path)
            || CSharpHash(System.IO.File.ReadAllBytes(path)) != NativeCSharpDecompilerSha256))
            throw new NotSupportedException("csharp_decompiler_binary_mismatch");
        return true;
    });
    private const int NativeCSharpPeLimit = 64 * 1024 * 1024, NativeCSharpCodeLimit = 750000;
    private const int NativeCSharpNodeLimit = 200000, NativeCSharpRecordLimit = 120000;
    // A per-method admission ceiling is not a cache-residency ceiling.
    // The former still refuses enormous methods; the latter keeps several
    // independently verified native methods alive across projectile identities.
    // Without separate budgets the same VanillaAI/Kill AST can be decompiled
    // three times inside a single first craft.
    private const int NativeCSharpResidentDocuments = 16;
    private const int NativeCSharpResidentNodes = 650000;
    private const int NativeCSharpResidentCharacters = 4 * NativeCSharpCodeLimit;
    private static readonly object nativeCSharpGate = new();
    private static readonly Dictionary<string, NativeCSharpDocument> nativeCSharpDocuments = new(StringComparer.Ordinal);
    // Only deterministic, verified decompiler bounds are negatively cached.
    // Deadline/cancellation and dependent assembly resolution are retryable.
    private static readonly Dictionary<string, string> nativeCSharpStableRefusals = new(StringComparer.Ordinal);
    private static readonly Queue<string> nativeCSharpRefusalOrder = new();
    private const int NativeCSharpRefusalLimit = 256;
    private static readonly LinkedList<string> nativeCSharpOrder = new();
    private static NativeCSharpModule? nativeCSharpModule;
    private static int nativeCSharpNodes, nativeCSharpCharacters;

    private static bool IsExpensiveNativeCSharpDocument(NativeCSharpDocument document)
        => document.Nodes >= 12000 || document.Characters >= 40000;

    // The cache must never consume an unbounded amount of memory, but the
    // replacement cost is highly asymmetric: a tiny helper takes milliseconds
    // to rebuild, while a dispatcher can take seconds and allocate >500 MB.
    // Evict the oldest *cheap* document before a costly one. If none remain,
    // evict ordinary LRU. Each hit still verifies MVID, metadata, IL and EH.
    private static LinkedListNode<string> NativeCSharpEvictionVictim()
    {
        var oldest = nativeCSharpOrder.First!;
        for (var node = oldest; node is not null; node = node.Next)
            if (!IsExpensiveNativeCSharpDocument(nativeCSharpDocuments[node.Value]))
                return node;
        return oldest;
    }

    private static void NativeCSharpProfileCache(string action, MethodInfo method,
        NativeCSharpDocument? document = null)
    {
        if (!ParentAnalysis.ProfileJobs) return;
        Console.Error.WriteLine(FormattableString.Invariant(
            $"PARENT_ILSPY_CACHE action={action} method={SourceMember(method)} nodes={document?.Nodes ?? 0} characters={document?.Characters ?? 0} resident={nativeCSharpDocuments.Count} retainedNodes={nativeCSharpNodes} retainedChars={nativeCSharpCharacters}"));
    }

    private sealed class NativeCSharpModule : IDisposable
    {
        internal readonly byte[] Bytes;
        internal readonly string Path, Sha256;
        internal readonly Guid Mvid;
        private readonly MemoryStream stream;
        internal readonly PEReader Reader;
        private PEFile? file;
        private NativeCSharpResolver? resolver;
        private DecompilerTypeSystem? typeSystem;
        private bool disposed;
        internal IEnumerable<PEFile> DependencyFiles => resolver?.Files ?? Enumerable.Empty<PEFile>();
        internal IEnumerable<(IAssemblyReference Reference, PEFile? File)> DependencyResolutions
            => resolver?.Resolutions ?? Enumerable.Empty<(IAssemblyReference, PEFile?)>();
        internal bool DependencyResolutionsStable => resolver?.ResolutionsStable == true;

        // Initialized under nativeCSharpGate, and owned by the module rather
        // than its evictable documents. ILSpy's type system has no cancellation
        // overload; the resolver observes the request between dependency reads.
        internal DecompilerTypeSystem GetTypeSystem(CancellationToken cancellation)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            cancellation.ThrowIfCancellationRequested();
            if (typeSystem is not null) return typeSystem;
            _ = nativeCSharpDecompilerVerified.Value;
            var createdResolver = new NativeCSharpResolver(Path, cancellation);
            PEFile? createdFile = null;
            try
            {
                createdFile = new PEFile(Path, new MemoryStream(Bytes, writable: false), PEStreamOptions.PrefetchEntireImage);
                var created = new DecompilerTypeSystem(createdFile, createdResolver,
                    new DecompilerSettings { ThrowOnAssemblyResolveErrors = true });
                cancellation.ThrowIfCancellationRequested();
                file = createdFile; resolver = createdResolver; typeSystem = created;
                return created;
            }
            catch { createdFile?.Dispose(); createdResolver.Dispose(); throw; }
            finally { createdResolver.Cancellation = CancellationToken.None; }
        }

        internal NativeCSharpModule(string path, byte[] bytes, Guid expected)
        {
            if (bytes.Length == 0 || bytes.Length > NativeCSharpPeLimit) throw new NotSupportedException("csharp_pe_size_bound");
            Path = path; Bytes = bytes; Sha256 = CSharpHash(bytes);
            stream = new MemoryStream(bytes, writable: false);
            PEReader? reader = null;
            try
            {
                Reader = reader = new PEReader(stream, PEStreamOptions.LeaveOpen);
                var metadata = Reader.GetMetadataReader();
                Mvid = metadata.GetGuid(metadata.GetModuleDefinition().Mvid);
                if (Mvid != expected) throw new NotSupportedException("csharp_pe_mvid_mismatch");
            }
            catch { reader?.Dispose(); stream.Dispose(); throw; }
        }

        internal unsafe void Verify(MethodInfo method)
        {
            if (method.Module.ModuleVersionId != Mvid) throw new NotSupportedException("csharp_pe_mvid_mismatch");
            var block = Reader.GetMetadata();
            if (method.Module != method.Module.Assembly.ManifestModule
                || !method.Module.Assembly.TryGetRawMetadata(out byte* liveMetadata, out int length)
                || length != block.Length || !new ReadOnlySpan<byte>(liveMetadata, length).SequenceEqual(new ReadOnlySpan<byte>(block.Pointer, block.Length)))
                throw new NotSupportedException("csharp_pe_metadata_mismatch");
            var metadata = Reader.GetMetadataReader();
            var handle = MetadataTokens.Handle(method.MetadataToken);
            if (handle.Kind != HandleKind.MethodDefinition) throw new NotSupportedException("csharp_not_method_definition");
            var definition = metadata.GetMethodDefinition((MethodDefinitionHandle)handle);
            if (metadata.GetString(definition.Name) != method.Name) throw new NotSupportedException("csharp_pe_method_identity_mismatch");
            var liveBody = method.GetMethodBody() ?? throw new NotSupportedException("csharp_method_body_unavailable");
            byte[] live = liveBody.GetILAsByteArray() ?? throw new NotSupportedException("csharp_method_body_unavailable");
            if (definition.RelativeVirtualAddress == 0) throw new NotSupportedException("csharp_pe_il_mismatch");
            var peBody = Reader.GetMethodBody(definition.RelativeVirtualAddress);
            if (!live.AsSpan().SequenceEqual(peBody.GetILBytes()))
                throw new NotSupportedException("csharp_pe_il_mismatch");
            // Method headers and EH sections live outside both the metadata
            // blob and IL stream. The decompiler and reflection must agree on
            // these semantic inputs too, including on document-cache hits.
            int localSignature = peBody.LocalSignature.IsNil ? 0 : MetadataTokens.GetToken(peBody.LocalSignature);
            if (liveBody.LocalSignatureMetadataToken != localSignature)
                throw new NotSupportedException("csharp_pe_local_signature_mismatch");
            if (liveBody.InitLocals != peBody.LocalVariablesInitialized)
                throw new NotSupportedException("csharp_pe_init_locals_mismatch");
            if (liveBody.MaxStackSize != peBody.MaxStack)
                throw new NotSupportedException("csharp_pe_max_stack_mismatch");
            var clauses = liveBody.ExceptionHandlingClauses;
            if (clauses.Count != peBody.ExceptionRegions.Length)
                throw new NotSupportedException("csharp_pe_exception_regions_mismatch");
            for (int index = 0; index < clauses.Count; index++)
            {
                var clause = clauses[index]; var region = peBody.ExceptionRegions[index];
                if ((int)clause.Flags != (int)region.Kind || clause.TryOffset != region.TryOffset
                    || clause.TryLength != region.TryLength || clause.HandlerOffset != region.HandlerOffset
                    || clause.HandlerLength != region.HandlerLength
                    || region.Kind == ExceptionRegionKind.Filter && clause.FilterOffset != region.FilterOffset
                    || region.Kind == ExceptionRegionKind.Catch && clause.CatchType != method.Module.ResolveType(
                        MetadataTokens.GetToken(region.CatchType), method.DeclaringType?.GetGenericArguments(), method.GetGenericArguments()))
                    throw new NotSupportedException("csharp_pe_exception_regions_mismatch");
            }
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            typeSystem = null;
            file?.Dispose(); file = null;
            resolver?.Dispose(); resolver = null;
            Reader.Dispose(); stream.Dispose();
        }
    }

    // UniversalAssemblyResolver and DecompilerTypeSystem are not IDisposable
    // in the pinned ILSpy build. Own every resolved PE explicitly, including
    // files opened before a failed/cancelled type-system initialization.
    private sealed class NativeCSharpResolver : IAssemblyResolver, IDisposable
    {
        private readonly UniversalAssemblyResolver resolver;
        private readonly Dictionary<string, string?> platformAssemblies = new(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<PEFile> files = new();
        internal IEnumerable<PEFile> Files => files;
        private readonly Dictionary<string, (IAssemblyReference Reference, PEFile? File)> resolutions = new(StringComparer.Ordinal);
        internal IEnumerable<(IAssemblyReference Reference, PEFile? File)> Resolutions => resolutions.Values;
        internal bool ResolutionsStable { get; private set; } = true;
        internal CancellationToken Cancellation;

        internal NativeCSharpResolver(string path, CancellationToken cancellation)
        {
            Cancellation = cancellation;
            resolver = new UniversalAssemblyResolver(path, false, ".NETCoreApp,Version=v8.0");
            resolver.AddSearchDirectory(System.IO.Path.GetDirectoryName(path));
            resolver.AddSearchDirectory(RuntimeEnvironment.GetRuntimeDirectory());
            // The host has already selected these exact assets from deps.json,
            // probing paths and RID rules. tML keeps them in nested Libraries;
            // guessing directories also lets a framework copy shadow a package.
            // Read the host's paths only: do not load assemblies or run hooks.
            if (AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") is string paths)
                foreach (string file in paths.Split(System.IO.Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
                {
                    cancellation.ThrowIfCancellationRequested();
                    if (!System.IO.Path.IsPathFullyQualified(file)) continue;
                    string name = System.IO.Path.GetFileNameWithoutExtension(file);
                    if (platformAssemblies.TryGetValue(name, out string? prior))
                    {
                        if (!string.Equals(prior, file, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
                            platformAssemblies[name] = null;
                    }
                    else platformAssemblies.Add(name, file);
                }
        }

        private PEFile? ResolveAssembly(IAssemblyReference reference)
        {
            if (!platformAssemblies.TryGetValue(reference.Name, out string? path)) return resolver.Resolve(reference);
            if (path is null) throw new NotSupportedException("csharp_platform_assembly_binding_ambiguous");
            var stream = System.IO.File.OpenRead(path);
            PEFile? file = null;
            try
            {
                file = new PEFile(path, stream, PEStreamOptions.Default);
                if (!file.IsAssembly || !string.Equals(file.Name, reference.Name, StringComparison.OrdinalIgnoreCase))
                    throw new NotSupportedException("csharp_platform_assembly_identity_mismatch");
                return file;
            }
            catch { file?.Dispose(); stream.Dispose(); throw; }
        }

        private PEFile? ResolveFile(Func<PEFile?> resolve)
        {
            Cancellation.ThrowIfCancellationRequested();
            var result = resolve();
            if (result is not null) files.Add(result);
            Cancellation.ThrowIfCancellationRequested();
            return result;
        }

        public PEFile? Resolve(IAssemblyReference reference)
        {
            PEFile? result;
            try { result = ResolveFile(() => ResolveAssembly(reference)); }
            catch { ResolutionsStable = false; throw; }
            if (resolutions.TryGetValue(reference.FullName, out var prior))
            {
                if (prior.File?.FullName != result?.FullName
                    || prior.Reference.IsWindowsRuntime != reference.IsWindowsRuntime
                    || prior.Reference.IsRetargetable != reference.IsRetargetable)
                    ResolutionsStable = false;
            }
            else if (resolutions.Count < NativeSourcePackDependencyLimit)
                resolutions.Add(reference.FullName, (reference, result));
            else ResolutionsStable = false;
            return result;
        }
        public PEFile? ResolveModule(PEFile mainModule, string name)
        {
            // Assembly-reference pins do not describe multi-module binding.
            // Keep live resolution unchanged, but do not record such a pack.
            ResolutionsStable = false;
            return ResolveFile(() => resolver.ResolveModule(mainModule, name));
        }
        public Task<PEFile?> ResolveAsync(IAssemblyReference reference) => Task.FromResult(Resolve(reference));
        public Task<PEFile?> ResolveModuleAsync(PEFile mainModule, string name) => Task.FromResult(ResolveModule(mainModule, name));
        public void Dispose() { foreach (var resolved in files) resolved.Dispose(); files.Clear(); resolutions.Clear(); }
    }

    private sealed partial class NativeCSharpDocument : IDisposable
    {
        internal readonly MethodInfo Method;
        internal readonly NativeCSharpModule Module;
        internal readonly CSharpDecompiler Decompiler;
        internal readonly SyntaxTree Tree;
        internal readonly MethodDeclaration Declaration;
        internal readonly int Nodes, Characters;
        private CSharpRendered original;
        private bool originalHasLocations;
        internal CSharpRendered Original
        {
            get
            {
                // Most dispatcher/lifecycle consumers need only excerpts. Build
                // the whole-method location map only when its reader asks for it.
                if (!originalHasLocations)
                {
                    original = RenderCSharp(Tree);
                    originalHasLocations = true;
                }
                return original;
            }
        }

        internal NativeCSharpDocument(MethodInfo method, NativeCSharpModule module, CancellationToken cancellation)
            : this(method, module, cancellation, methodAlreadyVerified: false) { }

        internal NativeCSharpDocument(MethodInfo method, NativeCSharpModule module, CancellationToken cancellation, bool methodAlreadyVerified)
        {
            cancellation.ThrowIfCancellationRequested();
            // Direct construction still verifies. The cache owner has already
            // verified every input, including hits, before taking this path.
            if (!methodAlreadyVerified) module.Verify(method);
            if (method.ContainsGenericParameters) throw new NotSupportedException("csharp_open_generic_method_unsupported");
            Method = method; Module = module;
            var settings = new DecompilerSettings { ThrowOnAssemblyResolveErrors = true };
            // Transform state and cancellation belong to this document only.
            Decompiler = new CSharpDecompiler(module.GetTypeSystem(cancellation), settings) { CancellationToken = cancellation };
            Tree = Decompiler.Decompile((MethodDefinitionHandle)MetadataTokens.Handle(method.MetadataToken));
            cancellation.ThrowIfCancellationRequested();
            Nodes = Tree.DescendantsAndSelf.Take(NativeCSharpNodeLimit + 1).Count();
            if (Nodes > NativeCSharpNodeLimit) throw new NotSupportedException("csharp_ast_node_bound");
            Declaration = Tree.Descendants.OfType<MethodDeclaration>().Single();
            if (Tree.DescendantsAndSelf.SelectMany(node => node.Annotations.OfType<ILFunction>()).Distinct().Any(function => function.Warnings.Count > 0))
                throw new NotSupportedException("csharp_decompiler_warnings");
            original = RenderCSharp(Tree, includeLocations: false);
            Characters = original.Code.Length;
            if (Characters > NativeCSharpCodeLimit) throw new NotSupportedException("csharp_method_character_bound");
            cancellation.ThrowIfCancellationRequested();
        }

        // All unmanaged readers belong to Module. Eviction must not dispose
        // them while another locked document borrower still uses that module.
        public void Dispose() { }
    }

    private sealed record CSharpLocation(int Start, int End, int StartLine, int EndLine);
    private sealed record CSharpRendered(string Code, CSharpLocation[] Locations);
    private sealed record CSharpGuard(IfElseStatement Branch, string Field, int Literal, int Offset);
    private sealed record CSharpProgram(JsonObject Row, object[] Path);

    private static string CSharpHash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    // ILSpy AST Clone() is deep. Borrow a branch/method under nativeCSharpGate,
    // temporarily detach only the discarded subtree, clone the closed region,
    // and restore the original parent relation even if cloning fails. This keeps
    // all original IL annotations/tokens and the exact legacy C# rendering.
    private static T CloneCSharpWithoutBody<T>(T source, MethodDeclaration declaration) where T : AstNode
    {
        var original = declaration.Body;
        try
        {
            declaration.Body = BlockStatement.Null;
            return (T)source.Clone();
        }
        finally { declaration.Body = original; }
    }

    private static IfElseStatement CloneCSharpTrueArm(IfElseStatement source)
    {
        var original = source.FalseStatement;
        try
        {
            source.FalseStatement = Statement.Null;
            return (IfElseStatement)source.Clone();
        }
        finally { source.FalseStatement = original; }
    }

    private static CSharpRendered RenderCSharp(AstNode source, bool includeLocations = true)
        => RenderCSharpCore(source, includeLocations, sourceIsOwned: false);

    // The excerpt has already been cloned and will never enter document cache.
    // Let the location writer annotate that private copy instead of cloning it.
    private static CSharpRendered RenderOwnedCSharp(AstNode source)
        => RenderCSharpCore(source, includeLocations: true, sourceIsOwned: true);

    private static CSharpRendered RenderCSharpCore(AstNode source, bool includeLocations, bool sourceIsOwned)
    {
        // Only location assignment needs a clone; the plain writer is read-only.
        // Coordinates are per record, never mutable cached AST state. The empty
        // indentation string avoids whitespace bloat in both identical outputs.
        var node = includeLocations && !sourceIsOwned ? source.Clone() : source;
        using var output = new StringWriter(CultureInfo.InvariantCulture) { NewLine = "\n" };
        var writer = new TextWriterTokenWriter(output) { IndentationString = "" };
        node.AcceptVisitor(new CSharpOutputVisitor(includeLocations ? TokenWriter.WrapInWriterThatSetsLocationsInAST(writer) : writer,
            new DecompilerSettings().CSharpFormattingOptions));
        if (!includeLocations) return new(output.ToString(), Array.Empty<CSharpLocation>());
        var locations = new List<CSharpLocation>();
        foreach (var part in node.DescendantsAndSelf.Where(part => part is not (SyntaxTree or MethodDeclaration or BlockStatement)))
        {
            if (part.StartLocation.Line < 1 || part.EndLocation.Line < part.StartLocation.Line) continue;
            foreach (var instruction in part.Annotations.OfType<ILInstruction>())
                if (instruction.StartILOffset >= 0 && instruction.EndILOffset > instruction.StartILOffset)
                    locations.Add(new(instruction.StartILOffset, instruction.EndILOffset, part.StartLocation.Line, part.EndLocation.Line));
        }
        return new(output.ToString(), locations.Distinct().ToArray());
    }

    private static NativeCSharpModule GetVerifiedNativeCSharpModule(MethodInfo method, CancellationToken cancellation)
    {
        // The immutable module snapshot is tied to the actual loaded Module and
        // MVID. Every requested method separately matches reflection IL, local
        // signature, initialization/stack header and EH, even on a cache hit.
        cancellation.ThrowIfCancellationRequested();
        if (method.Module != typeof(Projectile).Module) throw new NotSupportedException("csharp_non_native_module");
        if (nativeCSharpModule is null)
        {
            string path = method.Module.FullyQualifiedName;
            if (!System.IO.Path.IsPathFullyQualified(path) || !System.IO.File.Exists(path))
                throw new NotSupportedException("csharp_matching_pe_bytes_unavailable");
            var info = new FileInfo(path);
            if (info.Length > NativeCSharpPeLimit) throw new NotSupportedException("csharp_pe_size_bound");
            nativeCSharpModule = new(path, System.IO.File.ReadAllBytes(path), method.Module.ModuleVersionId);
        }
        nativeCSharpModule.Verify(method);
        cancellation.ThrowIfCancellationRequested();
        return nativeCSharpModule;
    }

    private static NativeCSharpDocument GetNativeCSharpDocument(MethodInfo method, CancellationToken cancellation)
    {
        var module = GetVerifiedNativeCSharpModule(method, cancellation);
        string key = method.Module.ModuleVersionId + ":" + method.MetadataToken + ":" + CSharpHash(method.GetMethodBody()!.GetILAsByteArray()!);
        cancellation.ThrowIfCancellationRequested();
        if (nativeCSharpDocuments.TryGetValue(key, out var retained))
        {
            var position = nativeCSharpOrder.Find(key)!;
            nativeCSharpOrder.Remove(position); nativeCSharpOrder.AddLast(position);
            NativeCSharpProfileCache("hit", method, retained);
            return retained;
        }
        if (nativeCSharpStableRefusals.TryGetValue(key, out var stableRefusal))
            throw new NotSupportedException(stableRefusal);
        NativeCSharpDocument created;
        try { created = new NativeCSharpDocument(method, module, cancellation, methodAlreadyVerified: true); }
        catch (NotSupportedException error) when (error.Message is
            "csharp_ast_node_bound" or "csharp_method_character_bound" or
            "csharp_decompiler_warnings" or "csharp_open_generic_method_unsupported")
        {
            cancellation.ThrowIfCancellationRequested();
            if (!nativeCSharpStableRefusals.ContainsKey(key))
            {
                while (nativeCSharpRefusalOrder.Count >= NativeCSharpRefusalLimit)
                    nativeCSharpStableRefusals.Remove(nativeCSharpRefusalOrder.Dequeue());
                nativeCSharpStableRefusals.Add(key, error.Message);
                nativeCSharpRefusalOrder.Enqueue(key);
            }
            throw;
        }
        try { cancellation.ThrowIfCancellationRequested(); }
        catch { created.Dispose(); throw; }
        while (nativeCSharpOrder.Count > 0 && (nativeCSharpDocuments.Count >= NativeCSharpResidentDocuments
            || nativeCSharpNodes + created.Nodes > NativeCSharpResidentNodes
            || nativeCSharpCharacters + created.Characters > NativeCSharpResidentCharacters))
        {
            var victim = NativeCSharpEvictionVictim();
            nativeCSharpOrder.Remove(victim);
            if (!nativeCSharpDocuments.Remove(victim.Value, out var discarded)) continue;
            nativeCSharpNodes -= discarded.Nodes;
            nativeCSharpCharacters -= discarded.Characters;
            NativeCSharpProfileCache("evict", discarded.Method, discarded);
            discarded.Dispose();
        }
        nativeCSharpDocuments.Add(key, created); nativeCSharpOrder.AddLast(key);
        nativeCSharpNodes += created.Nodes; nativeCSharpCharacters += created.Characters;
        NativeCSharpProfileCache("decompile", method, created);
        return created;
    }

    private static void ClearNativeCSharpSourceCache()
    {
        lock (nativeCSharpGate)
        {
            foreach (var document in nativeCSharpDocuments.Values) document.Dispose();
            nativeCSharpDocuments.Clear(); nativeCSharpOrder.Clear(); nativeCSharpNodes = nativeCSharpCharacters = 0;
            nativeCSharpStableRefusals.Clear(); nativeCSharpRefusalOrder.Clear();
            nativeSourcePackReader?.Dispose(); nativeSourcePackReader = null; nativeSourcePackReadAttempted = false;
            nativeCSharpModule?.Dispose(); nativeCSharpModule = null;
        }
    }

    private static IEnumerable<CSharpProgram> CSharpPrograms(JsonNode? value, object[] path)
    {
        if (value is JsonObject row)
        {
            bool program = row["method"] is JsonValue methodName && methodName.TryGetValue<string>(out _)
                && row["sourceMethodSha256"] is JsonValue methodHash && methodHash.TryGetValue<string>(out _)
                && row["sourceModuleVersionId"] is JsonValue moduleId && moduleId.TryGetValue<string>(out _)
                && (row["observations"] is JsonArray || row["coverage"] is JsonValue);
            // A method record owns the complete raw/identitySelected pair. Never
            // publish overlapping replacement paths. Independent predicate-source
            // callees remain separate; their parent cannot swallow their bodies.
            if (program && row["predicateSources"] is not JsonArray { Count: > 0 })
                yield return new(row, path);
            foreach (var pair in row)
            {
                // Author derives draw motifs from the established graph before
                // omitting draw. Presentation stages also consume that graph;
                // this gameplay source view must never take ownership of it.
                if (path.Length == 0 && pair.Key is "draw" or "lifecycle" or "interactionSources") continue;
                if (pair.Key is "sourceMethods" or "nativeCSharpSource" || program && pair.Key == "identitySelected") continue;
                foreach (var child in CSharpPrograms(pair.Value, path.Append((object)pair.Key).ToArray())) yield return child;
            }
        }
        else if (value is JsonArray array)
            for (int index = 0; index < array.Count; index++)
                foreach (var child in CSharpPrograms(array[index], path.Append((object)index).ToArray())) yield return child;
    }

    private static bool CSharpProgramMatches(JsonObject row, MethodInfo method)
        => row["method"] is JsonValue name && name.TryGetValue<string>(out var text) && text == method.DeclaringType!.FullName + "." + method.Name
            && row["sourceModuleVersionId"] is JsonValue module && module.TryGetValue<string>(out var mvid) && mvid == method.Module.ModuleVersionId.ToString()
            && row["sourceMethodSha256"] is JsonValue hash && hash.TryGetValue<string>(out var sha) && sha == CSharpHash(method.GetMethodBody()!.GetILAsByteArray()!)
            && row["metadataToken"] is JsonValue token && token.TryGetValue<int>(out var id) && id == method.MetadataToken;

    private readonly record struct CSharpRowIdentity(string Method, string Mvid, string Sha, int Token);
    private static CSharpRowIdentity? CSharpRowKey(JsonObject row)
        => row["method"] is JsonValue name && name.TryGetValue<string>(out var text)
            && row["sourceModuleVersionId"] is JsonValue module && module.TryGetValue<string>(out var mvid)
            && row["sourceMethodSha256"] is JsonValue hash && hash.TryGetValue<string>(out var sha)
            && row["metadataToken"] is JsonValue token && token.TryGetValue<int>(out var id)
            ? new(text, mvid, sha, id) : null;

    // Attachment-local indexes retain the existing exact tuple and row order.
    // They do not replace the independent native module/certificate checks.
    private sealed class CSharpAttachmentRows
    {
        private readonly ILookup<CSharpRowIdentity?, CSharpProgram> programs;
        private readonly ILookup<CSharpRowIdentity?, JsonObject> calls;
        private readonly HashSet<(string Method, string Mvid)> owners;
        internal CSharpAttachmentRows(CSharpProgram[] programs, JsonArray calls)
        {
            this.programs = programs.ToLookup(program => CSharpRowKey(program.Row));
            this.calls = calls.OfType<JsonObject>().ToLookup(CSharpRowKey);
            owners = this.programs.Select(group => group.Key).OfType<CSharpRowIdentity>()
                .Select(key => (key.Method, key.Mvid)).ToHashSet();
        }
        internal CSharpProgram[] Find(MethodInfo method, out CSharpRowIdentity? key)
        {
            key = null;
            string name = method.DeclaringType!.FullName + "." + method.Name;
            string mvid = method.Module.ModuleVersionId.ToString();
            if (!owners.Contains((name, mvid))) return Array.Empty<CSharpProgram>();
            key = new(name, mvid, CSharpHash(method.GetMethodBody()!.GetILAsByteArray()!), method.MetadataToken);
            return programs[key].ToArray();
        }
        internal HashSet<int> Links(CSharpRowIdentity? key) => CSharpRowLinkOffsets(calls[key]);
    }

    // Derived indexes follow the existing immutable IL decode, rather than
    // retaining old methods after source-cache invalidation.
    private static readonly ConditionalWeakTable<List<AmmoIl>, Dictionary<int, int>> csharpConditionalEnds = new();
    private static Dictionary<int, int> CSharpConditionalEnds(MethodInfo method)
        => csharpConditionalEnds.GetValue(AttackCode(method), static code =>
            code.Zip(code.Skip(1), (instruction, next) => (instruction, next.Offset))
                .Where(pair => pair.instruction.Op.StartsWith('b') && pair.instruction.Op is not ("br" or "br.s" or "break"))
                .ToDictionary(pair => pair.instruction.Offset, pair => pair.Offset));

    private static bool ExactCSharpConditional(ILInstruction instruction, int offset, Dictionary<int, int> ends)
        => ends.TryGetValue(offset, out int end) && instruction.ILRanges.Any(range => range.Start == offset && range.End == end);

    private static CSharpGuard? ReadCSharpGuard(IfElseStatement branch, Dictionary<int, int> ends)
    {
        if (branch.Condition is not BinaryOperatorExpression { Operator: BinaryOperatorType.Equality } comparison) return null;
        bool Field(Expression value, out string name)
        {
            name = "";
            if (value.GetSymbol() is not IField field || field.DeclaringType.FullName != typeof(Projectile).FullName
                || field.Name is not ("type" or "aiStyle")) return false;
            if (value is not IdentifierExpression && value is not MemberReferenceExpression { Target: ThisReferenceExpression or BaseReferenceExpression }) return false;
            name = field.Name; return true;
        }
        string fieldName; int literal;
        if (Field(comparison.Left, out fieldName) && comparison.Right is PrimitiveExpression { Value: int right }) literal = right;
        else if (Field(comparison.Right, out fieldName) && comparison.Left is PrimitiveExpression { Value: int left }) literal = left;
        else return null;
        var control = branch.Annotations.OfType<IfInstruction>().ToArray();
        if (control.Length != 1 || !ExactCSharpConditional(control[0], control[0].StartILOffset, ends)) return null;
        return new(branch, fieldName, literal, control[0].StartILOffset);
    }

    // Strict excerpts only: a leading identity conjunct admits the unchanged
    // full conditional region, never an identity-specialized/pruned branch.
    private static CSharpGuard? ReadCSharpRegionGuard(IfElseStatement branch, Dictionary<int, int> ends)
    {
        var ordinary = ReadCSharpGuard(branch, ends);
        if (ordinary is not null) return ordinary;
        Expression leading = branch.Condition;
        if (leading is not BinaryOperatorExpression { Operator: BinaryOperatorType.ConditionalAnd }) return null;
        while (leading is BinaryOperatorExpression { Operator: BinaryOperatorType.ConditionalAnd } conjunction)
            leading = conjunction.Left;
        if (leading is not BinaryOperatorExpression { Operator: BinaryOperatorType.Equality } comparison) return null;
        var controls = branch.Annotations.OfType<IfInstruction>().ToArray();
        if (controls.Length != 1 || !ExactCSharpConditional(controls[0], controls[0].StartILOffset, ends)) return null;
        int offset = controls[0].StartILOffset;
        var comparisons = comparison.Annotations.OfType<Comp>().ToArray();
        if (comparisons.Length != 1 || !ExactCSharpConditional(comparisons[0], offset, ends)) return null;
        // Reuse the canonical typed receiver/literal check without changing its
        // callers or weakening the specialization reader's equality-only rule.
        var probe = new IfElseStatement { Condition = (Expression)comparison.Clone() };
        probe.AddAnnotation(controls[0]);
        return ReadCSharpGuard(probe, ends) is { } guard
            ? new CSharpGuard(branch, guard.Field, guard.Literal, guard.Offset) : null;
    }

    private static string? CSharpRegionRefusal(Statement body, MethodInfo method)
    {
        // A region is a complete lexical body, never an offset min/max crop.
        // Shared returns can legitimately map to an earlier native ret offset.
        if (body.Ancestors.Any(node => node is TryCatchStatement or UsingStatement or LockStatement)
            || body.DescendantsAndSelf.Any(node => node is GotoStatement or GotoCaseStatement or LabelStatement
            or TryCatchStatement or UsingStatement or LockStatement or LambdaExpression or AnonymousMethodExpression or YieldReturnStatement or YieldBreakStatement
            or UnaryOperatorExpression { Operator: UnaryOperatorType.Await } or LocalFunctionDeclarationStatement)) return "csharp_region_nonlocal_control_unsupported";
        // Other dispatcher branches can contain handlers. Refuse only a selected
        // region intersecting protected/handler/filter IL, including transformed
        // using/foreach syntax; do not reject unrelated EH elsewhere in a method.
        var ranges = body.DescendantsAndSelf.SelectMany(node => node.Annotations.OfType<ILInstruction>())
            .SelectMany(instruction => instruction.ILRanges).Where(range => range.End > range.Start).ToArray();
        foreach (var clause in method.GetMethodBody()!.ExceptionHandlingClauses)
            if (ranges.Any(range => range.Start < clause.TryOffset + clause.TryLength && range.End > clause.TryOffset
                || range.Start < clause.HandlerOffset + clause.HandlerLength && range.End > clause.HandlerOffset
                || clause.Flags == ExceptionHandlingClauseOptions.Filter && range.Start < clause.HandlerOffset && range.End > clause.FilterOffset))
                return "csharp_region_exception_flow_unsupported";
        var declared = body.DescendantsAndSelf.OfType<VariableInitializer>().Select(node => node.GetILVariable())
            .Concat(body.DescendantsAndSelf.OfType<ForeachStatement>().Select(node => node.GetILVariable())).Where(variable => variable is not null).ToHashSet();
        var used = body.DescendantsAndSelf.OfType<IdentifierExpression>().Select(node => node.GetILVariable())
            .Where(variable => variable is not null).ToHashSet();
        if (used.Any(variable => variable!.Kind != VariableKind.Parameter && !declared.Contains(variable)))
            return "csharp_region_external_local_dependency";
        // break/continue must retain their enclosing loop/switch inside the body.
        foreach (var exit in body.DescendantsAndSelf.Where(node => node is BreakStatement or ContinueStatement))
        {
            bool bound = exit.Ancestors.TakeWhile(ancestor => ancestor != body).Any(ancestor => ancestor is ForStatement
                or ForeachStatement or WhileStatement or DoWhileStatement || exit is BreakStatement && ancestor is SwitchStatement);
            if (!bound) return "csharp_region_nonlocal_control_unsupported";
        }
        return null;
    }

    private static bool CSharpControlsContain(AstNode body, int offset, Dictionary<int, int> ends)
        => body.DescendantsAndSelf.OfType<IfElseStatement>().Any(branch => branch.Condition.DescendantsAndSelf.Prepend(branch)
            .SelectMany(node => node.Annotations.OfType<ILInstruction>()).Any(instruction => ExactCSharpConditional(instruction, offset, ends)));

    private static JsonObject[] CSharpIdentityWindows(CSharpProgram[] programs)
        => programs.SelectMany(program => program.Row["identityWindows"] is JsonArray values ? values.OfType<JsonObject>() : Enumerable.Empty<JsonObject>())
            .GroupBy(window => window.ToJsonString(), StringComparer.Ordinal).Select(group => group.First()).ToArray();

    private static HashSet<int> CSharpLinkOffsets(MethodInfo method, JsonArray calls)
        => CSharpRowLinkOffsets(calls.OfType<JsonObject>().Where(call => CSharpProgramMatches(call, method)));
    private static HashSet<int> CSharpRowLinkOffsets(IEnumerable<JsonObject> calls)
    {
        var offsets = new HashSet<int>();
        foreach (var call in calls)
        {
            if (call["at"] is JsonValue at) offsets.Add(at.GetValue<int>());
            if (call["requiredPredicates"] is JsonArray predicates)
                foreach (var predicate in predicates)
                    if (predicate is JsonValue id && id.TryGetValue<string>(out string? name) && name is not null && name.StartsWith('b')
                        && int.TryParse(name.AsSpan(1), NumberStyles.None, CultureInfo.InvariantCulture, out int offset)) offsets.Add(offset);
        }
        return offsets;
    }

    private static JsonArray CSharpGraphPaths(CSharpProgram[] programs)
        => new(programs.Select(program => (JsonNode?)new JsonArray(program.Path
            .Select(part => part is string key ? (JsonNode?)JsonValue.Create(key) : JsonValue.Create((int)part)).ToArray())).ToArray());

    private static JsonObject CSharpProjectionInput(MethodInfo method, CSharpProgram[] programs,
        JsonArray calls, int type, int style, bool capturedReceiverBound)
        => CSharpProjectionInputForLinks(programs, CSharpLinkOffsets(method, calls), type, style, capturedReceiverBound);
    private static JsonObject CSharpProjectionInputForLinks(CSharpProgram[] programs,
        HashSet<int> linkOffsets, int type, int style, bool capturedReceiverBound)
        => new()
        {
            ["type"] = type, ["style"] = style, ["capturedReceiverBound"] = capturedReceiverBound,
            ["mechanicsPolicyVersion"] = 2, // Producer receipt + preserved exception islands.
            ["windows"] = new JsonArray(CSharpIdentityWindows(programs).Select(window => (JsonNode?)window.DeepClone()).ToArray()),
            ["linkOffsets"] = new JsonArray(linkOffsets.Order().Select(offset => (JsonNode?)JsonValue.Create(offset)).ToArray()),
        };

    private static bool CompleteCSharpProjection(JsonObject value, MethodInfo method)
    {
        bool Outcome(string recordName, string refusalName)
        {
            bool hasRecord = value[recordName] is JsonObject;
            bool hasRefusal = value[refusalName] is JsonValue refusal && refusal.TryGetValue<string>(out _);
            if (hasRecord == hasRefusal) return false;
            if (!hasRecord) return value[recordName] is null;
            var record = value[recordName]!.AsObject();
            // Old cached mechanics projections do not carry producer permission.
            // Recompute them rather than manufacturing a receipt on admission.
            if (recordName == "mechanics" && (record["metadataToken"] is not JsonValue token
                || !token.TryGetValue<int>(out int metadataToken) || metadataToken != method.MetadataToken
                || record["identityPruning"] is not JsonObject permission
                || permission["allowed"] is not JsonValue allowed || !allowed.TryGetValue<bool>(out bool canPrune)
                || !permission.ContainsKey("refusal")
                || (canPrune ? permission["refusal"] is not null
                    : permission["refusal"] is not JsonValue reason || !reason.TryGetValue<string>(out _)))) return false;
            return value[refusalName] is null && record.ContainsKey("graphPaths") && record["graphPaths"] is null
                && CSharpProgramMatches(record, method) && record["code"] is JsonValue code && code.TryGetValue<string>(out _)
                && record["coverage"] is JsonValue coverage && coverage.TryGetValue<string>(out _);
        }
        return value.Count == 4 && value.ContainsKey("strict") && value.ContainsKey("strictRefusal")
            && value.ContainsKey("mechanics") && value.ContainsKey("mechanicsRefusal")
            && Outcome("strict", "strictRefusal") && Outcome("mechanics", "mechanicsRefusal");
    }

    private static JsonObject BuildNativeCSharpRecord(NativeCSharpDocument document, CSharpProgram[] programs,
        JsonArray calls, int type, int style, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        return BuildNativeCSharpRecordForLinks(document, programs, CSharpLinkOffsets(document.Method, calls), type, style, cancellation);
    }
    private static JsonObject BuildNativeCSharpRecordForLinks(NativeCSharpDocument document, CSharpProgram[] programs,
        HashSet<int> linkOffsets, int type, int style, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        var method = document.Method;
        var conditionalEnds = CSharpConditionalEnds(method);
        var windows = CSharpIdentityWindows(programs);
        var guards = new List<CSharpGuard>(); var rendered = new List<CSharpRendered>();
        var unresolved = new JsonArray(); string coverage;
        if (windows.Length > 0)
        {
            var candidates = document.Tree.Descendants.OfType<IfElseStatement>().Select(branch => ReadCSharpRegionGuard(branch, conditionalEnds)).OfType<CSharpGuard>()
                .Where(guard => guard.Field == "type" && guard.Literal == type || guard.Field == "aiStyle" && guard.Literal == style).ToArray();
            var selectedTrueArms = candidates.Select(candidate => (AstNode)candidate.Branch.TrueStatement).ToHashSet();
            foreach (var candidate in candidates)
            {
                // A candidate's ancestors never contain its own true statement.
                // Indexed membership replaces quadratic candidate scans.
                if (candidate.Branch.Ancestors.Any(selectedTrueArms.Contains)) continue;
                string? refusal = CSharpRegionRefusal(candidate.Branch.TrueStatement, method);
                if (refusal is not null) { unresolved.Add(refusal + "@" + candidate.Offset); continue; }
                var excerpt = CloneCSharpTrueArm(candidate.Branch);
                refusal = CSharpRegionRefusal(excerpt, method);
                if (refusal is not null) { unresolved.Add(refusal + "@" + candidate.Offset); continue; }
                guards.Add(candidate); rendered.Add(RenderOwnedCSharp(excerpt));
            }
            // Cover every original identity window represented by this graph.
            // Matching one method hash or the first useful guard is insufficient.
            foreach (var window in windows)
            {
                int offset = window["guardOffset"]!.GetValue<int>();
                if (!guards.Any(guard => guard.Offset == offset || CSharpControlsContain(guard.Branch.TrueStatement, offset, conditionalEnds)))
                    throw new NotSupportedException("csharp_region_does_not_cover_all_identity_windows:"
                        + string.Join(",", unresolved.OfType<JsonValue>().Select(value => value.GetValue<string>())));
            }
            if (guards.Count == 0) throw new NotSupportedException("csharp_no_closed_identity_region");
            coverage = "conditional_ast_regions";
            unresolved.Add("conditional_source_excerpts; original_guards_must_be_reached; enclosing_dispatch_and_runtime_hooks_unknown");
            if (guards.Any(guard => guard.Branch.Condition is BinaryOperatorExpression { Operator: BinaryOperatorType.ConditionalAnd }))
                unresolved.Add("entryGuards identify leading identity predicates only; each source body requires its own full condition when its original guard is reached; enclosing flow remains unknown");
        }
        else
        {
            // Whole verified source can retain try/catch/filter/finally even
            // when the independent IL/CFG reader refuses exception regions.
            // Never crop handlers or claim a control-flow/identity proof here.
            if (method.GetMethodBody()!.ExceptionHandlingClauses.Count > 0)
                unresolved.Add("exception_regions_preserved_in_source; control_flow_and_exceptional_execution_not_evaluated");
            rendered.Add(document.Original); coverage = "whole_method";
        }
        string header = "";
        if (coverage == "conditional_ast_regions")
        {
            var signature = CloneCSharpWithoutBody(document.Declaration, document.Declaration);
            header = string.Concat(document.Tree.Children.Where(node => node is UsingDeclaration or UsingAliasDeclaration).Select(node => RenderCSharp(node, includeLocations: false).Code));
            header += "// Source method on " + method.DeclaringType!.FullName + ": " + RenderCSharp(signature, includeLocations: false).Code.Trim().Replace("\r", "").Replace("\n", " ") + "\n";
        }
        string code = header + string.Join("\n", rendered.Select(row => row.Code));
        if (code.Length > NativeCSharpRecordLimit) throw new NotSupportedException("csharp_record_character_bound");
        var locations = new List<CSharpLocation>(); int lineOffset = header.Count(character => character == '\n');
        foreach (var row in rendered)
        {
            locations.AddRange(row.Locations.Select(location => location with { StartLine = location.StartLine + lineOffset, EndLine = location.EndLine + lineOffset }));
            lineOffset += row.Code.Count(character => character == '\n') + 1;
        }
        var mapped = new JsonArray();
        foreach (int offset in linkOffsets.Order())
        {
            var matches = locations.Where(location => location.Start <= offset && offset < location.End)
                .OrderBy(location => location.End - location.Start).ThenBy(location => location.EndLine - location.StartLine).ToArray();
            if (matches.Length == 0) mapped.Add(new JsonObject { ["ilOffset"] = offset, ["unresolved"] = "decompiler_source_location_unavailable" });
            else
            {
                var closest = matches[0];
                mapped.Add(new JsonObject { ["ilOffset"] = offset, ["startLine"] = closest.StartLine, ["endLine"] = closest.EndLine });
            }
        }
        var record = MethodSourceIdentity(method);
        string codeSha256 = SourceAnalysisBuffers.HashUtf8(code, cancellation);
        record["id"] = "csharp:" + record["sourceModuleVersionId"]!.GetValue<string>() + ":" + method.MetadataToken + ":" + codeSha256;
        record["metadataToken"] = method.MetadataToken; record["assemblySha256"] = document.Module.Sha256;
        record["decompiler"] = new JsonObject { ["name"] = "ICSharpCode.Decompiler", ["version"] = NativeCSharpVersion,
            ["assemblySha256"] = NativeCSharpDecompilerSha256, ["settings"] = "csharp_default_no_indentation_v1" };
        record["coverage"] = coverage;
        record["graphPaths"] = CSharpGraphPaths(programs);
        record["code"] = code; record["codeSha256"] = codeSha256;
        record["entryGuards"] = new JsonArray(guards.Select(guard => (JsonNode?)new JsonObject { ["field"] = "Terraria.Projectile." + guard.Field,
            ["operator"] = "==", ["literal"] = guard.Literal, ["ilOffset"] = guard.Offset,
            ["scope"] = "only_if_original_guard_is_reached; enclosing_dispatch_unknown" }).ToArray());
        record["coveredWindows"] = new JsonArray(windows.Select(window => (JsonNode?)window.DeepClone()).ToArray());
        record["locations"] = mapped; record["unresolved"] = unresolved;
        return record;
    }

    // Normalization: an explicit captured-identity source view. This is not a
    // gameplay fallback and never overwrites the complete raw evidence record.
    // Only an exact typed AST guard certified by the IL CFG can lose an arm.
    private static void AttachIdentitySpecializedCSharp(JsonObject record, NativeCSharpDocument document,
        int type, int style, CancellationToken cancellation)
    {
        if (record["coverage"]!.GetValue<string>() != "whole_method") return;
        var method = document.Method;
        if (AttackActorArgument(method) < 0 || method.GetMethodBody()!.ExceptionHandlingClauses.Count != 0) return;
        if (document.Tree.Descendants.Any(node => node is GotoStatement or GotoCaseStatement or LabelStatement
            or LambdaExpression or AnonymousMethodExpression or LocalFunctionDeclarationStatement)) return;
        // Specialization consumes the complete, immutable IL/CFG once; the
        // parent-specific edge proof stays private to AttackIdentitySelection.
        var body = ReadCompleteSourceMethod(method);
        var selection = new AttackIdentitySelection(body, type, style);
        var ends = CSharpConditionalEnds(method);
        var selectedOffsets = selection.Receipt["selectedEdges"]!.AsArray().OfType<JsonObject>()
            .Where(edge => selection.Reachable.Contains(edge["block"]!.GetValue<int>()))
            .Select(edge => edge["at"]!.GetValue<int>()).ToHashSet();
        // With no certified selected edge the old loop could not remove an arm.
        cancellation.ThrowIfCancellationRequested();
        if (selectedOffsets.Count == 0) return;
        var reachableOffsets = body.Blocks.Values.Where(block => selection.Reachable.Contains(block.Start))
            .SelectMany(block => block.Code).Select(instruction => instruction.Offset).Order().ToArray();
        var allOffsets = body.Code.Select(instruction => instruction.Offset).Order().ToArray();
        var tree = (SyntaxTree)document.Tree.Clone();
        var removed = new JsonArray();
        var excludedOffsets = new HashSet<int>();
        PruneOwnedCSharpIdentityBranches(tree, (branch, branchIndex) =>
        {
            var guard = ReadCSharpGuard(branch, ends);
            if (guard is null || !selectedOffsets.Contains(guard.Offset)
                || guard.Literal == (guard.Field == "type" ? type : style)) return false;
            // Keep the exact union of annotated half-open ranges, including
            // holes and shared returns. A reachable instruction still vetoes
            // removal. This changes only the intersection/search algorithm.
            var ranges = document.IdentityRanges(branchIndex, condition: false, cancellation: cancellation);
            if (ranges.IsEmpty || ranges.Intersects(reachableOffsets)) return false;
            ranges.AddOffsets(allOffsets, excludedOffsets, cancellation);
            document.IdentityRanges(branchIndex, condition: true, cancellation: cancellation)
                .AddOffsets(allOffsets, excludedOffsets, cancellation);
            excludedOffsets.Add(guard.Offset);
            removed.Add(guard.Offset);
            return true;
        }, cancellation);
        if (removed.Count == 0) return;
        // Tree is a private, already-mutated copy. Preserve exact IL locations
        // without another full AST clone solely for token writer coordinates.
        var rendered = RenderOwnedCSharp(tree);
        if (rendered.Code.Length >= record["code"]!.GetValue<string>().Length) return;
        var mapped = new JsonArray();
        foreach (var original in record["locations"]!.AsArray().OfType<JsonObject>())
        {
            int offset = original["ilOffset"]!.GetValue<int>();
            var closest = rendered.Locations.Where(location => location.Start <= offset && offset < location.End)
                .OrderBy(location => location.End - location.Start).ThenBy(location => location.EndLine - location.StartLine).FirstOrDefault();
            // Exclusion takes precedence over coarse enclosing-node ranges.
            if (excludedOffsets.Contains(offset)) mapped.Add(new JsonObject { ["ilOffset"] = offset, ["unresolved"] = "excluded_by_identity_proof" });
            else if (closest is null) mapped.Add(new JsonObject { ["ilOffset"] = offset, ["unresolved"] = "decompiler_source_location_unavailable" });
            else mapped.Add(new JsonObject { ["ilOffset"] = offset, ["startLine"] = closest.StartLine, ["endLine"] = closest.EndLine });
        }
        string sha = SourceAnalysisBuffers.HashUtf8(rendered.Code, cancellation);
        record["identitySpecialized"] = new JsonObject
        {
            ["id"] = "csharp-specialized:" + record["id"]!.GetValue<string>() + ":" + sha + ":" + type + ":" + style,
            ["code"] = rendered.Code, ["codeSha256"] = sha, ["coverage"] = "identity_specialized_method", ["locations"] = mapped,
            ["proof"] = new JsonObject
            {
                ["version"] = 1, ["source"] = "certified_receiver_identity_ast", ["originalCodeSha256"] = record["codeSha256"]!.DeepClone(),
                ["identityPredicates"] = selection.Receipt["identityPredicates"]!.DeepClone(), ["scope"] = selection.Receipt["scope"]!.DeepClone(),
                ["selectedEdges"] = selection.Receipt["selectedEdges"]!.DeepClone(), ["removedGuards"] = removed,
            },
            ["sourceMap"] = new JsonObject { ["kind"] = "il_source_locations_v1", ["original"] = record["locations"]!.DeepClone(), ["specialized"] = mapped.DeepClone() },
        };
    }

    private static void AttachNativeCSharpSource(JsonObject attack, IEnumerable<MethodBase> methods, JsonArray calls, int type, int style, ISet<MethodBase> mechanicsBoundReceivers)
    {
        var records = new JsonArray(); var refusals = new JsonArray();
        var mechanics = new JsonArray(); var mechanicsRefusals = new JsonArray();
        bool profilePhases = ParentAnalysis.ProfileJobs;
        long phaseStart = 0, phaseBytes = 0;
        void Mark(MethodInfo method, string phase)
        {
            if (!profilePhases) return;
            long next = System.Diagnostics.Stopwatch.GetTimestamp();
            long bytes = GC.GetAllocatedBytesForCurrentThread();
            if (phaseStart != 0)
                Console.Error.WriteLine(FormattableString.Invariant(
                    $"PARENT_CSHARP type={type} style={style} method={SourceMember(method)} phase={phase} ms={System.Diagnostics.Stopwatch.GetElapsedTime(phaseStart, next).TotalMilliseconds:F3} allocated={bytes - phaseBytes}"));
            phaseStart = next; phaseBytes = bytes;
        }
        var rows = new CSharpAttachmentRows(CSharpPrograms(attack, Array.Empty<object>()).ToArray(), calls);
        foreach (var method in methods.OfType<MethodInfo>().Distinct())
        {
            var owned = rows.Find(method, out var key);
            if (owned.Length == 0) continue;
            Mark(method, "start");
            currentParentAnalysis?.ThrowIfCancelled();
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(currentParentAnalysis?.Cancellation ?? CancellationToken.None);
            timeout.CancelAfter(TimeSpan.FromSeconds(20));
            try
            {
                while (!Monitor.TryEnter(nativeCSharpGate, 50)) timeout.Token.ThrowIfCancellationRequested();
                try
                {
                    var linkOffsets = rows.Links(key);
                    var input = CSharpProjectionInputForLinks(owned, linkOffsets, type, style, mechanicsBoundReceivers.Contains(method));
                    if (TryReadNativeSourceProjection("projectile_method", method, input, timeout.Token, out var cached)
                        && CompleteCSharpProjection(cached, method))
                    {
                        if (cached["strict"] is JsonObject strict)
                        {
                            cached.Remove("strict"); strict["graphPaths"] = CSharpGraphPaths(owned); records.Add(strict);
                        }
                        if (cached["strictRefusal"] is JsonValue strictFailure)
                            refusals.Add(new JsonObject { ["method"] = SourceMember(method), ["unresolved"] = strictFailure.DeepClone() });
                        if (cached["mechanics"] is JsonObject readable)
                        {
                            cached.Remove("mechanics"); readable["graphPaths"] = CSharpGraphPaths(owned); mechanics.Add(readable);
                        }
                        if (cached["mechanicsRefusal"] is JsonValue readableFailure)
                            mechanicsRefusals.Add(new JsonObject { ["method"] = SourceMember(method), ["unresolved"] = readableFailure.DeepClone() });
                        Mark(method, "verified_source_pack");
                        continue;
                    }
                    var document = GetNativeCSharpDocument(method, timeout.Token);
                    Mark(method, "verified_decompile");
                    JsonObject? strictRecord = null;
                    JsonObject? readableRecord = null;
                    string? strictError = null, mechanicsError = null;
                    bool recordable = true;
                    try
                    {
                        var record = BuildNativeCSharpRecordForLinks(document, owned, linkOffsets, type, style, timeout.Token);
                        Mark(method, "strict_record");
                        // A refused optional proof must not erase the full source.
                        try { AttachIdentitySpecializedCSharp(record, document, type, style, timeout.Token); }
                        catch (NotSupportedException) { }
                        Mark(method, "identity_specialization");
                        records.Add(record); strictRecord = record;
                    }
                    catch (NotSupportedException error)
                    { strictError = error.Message; refusals.Add(new JsonObject { ["method"] = SourceMember(method), ["unresolved"] = error.Message }); }
                    try
                    {
                        JsonObject mechanicsRecord;
                        try { mechanicsRecord = BuildMechanicsSourceRecord(document, type, style, timeout.Token, mechanicsBoundReceivers.Contains(method)); }
                        catch (NotSupportedException error) when (error.Message == "mechanics_source_character_bound; strict_source_retained"
                            && strictRecord?["coverage"]?.GetValue<string>() == "conditional_ast_regions")
                        {
                            mechanicsRecord = BuildMechanicsSourceView(document, type, style, timeout.Token, mechanicsBoundReceivers.Contains(method), strictRecord);
                        }
                        mechanicsRecord["graphPaths"] = CSharpGraphPaths(owned);
                        mechanics.Add(mechanicsRecord); readableRecord = mechanicsRecord;
                    }
                    catch (Exception error) when (error is not OutOfMemoryException && error is not OperationCanceledException)
                    {
                        recordable = error is NotSupportedException;
                        mechanicsError = error is NotSupportedException ? error.Message : error.GetType().Name;
                        mechanicsRefusals.Add(new JsonObject { ["method"] = SourceMember(method), ["unresolved"] = mechanicsError });
                    }
                    if (recordable && nativeSourcePackRecorder is not null)
                    {
                        var strictTemplate = strictRecord?.DeepClone().AsObject();
                        var readableTemplate = readableRecord?.DeepClone().AsObject();
                        // Keep this property's position: exact wire byte order
                        // matters, but paths belong to the current source graph.
                        if (strictTemplate is not null) strictTemplate["graphPaths"] = null;
                        if (readableTemplate is not null) readableTemplate["graphPaths"] = null;
                        RecordNativeSourceProjection("projectile_method", method, input, new JsonObject
                        {
                            ["strict"] = strictTemplate, ["strictRefusal"] = strictError,
                            ["mechanics"] = readableTemplate, ["mechanicsRefusal"] = mechanicsError,
                        }, timeout.Token);
                    }
                    Mark(method, "mechanics_source");
                }
                finally { Monitor.Exit(nativeCSharpGate); }
            }
            catch (OperationCanceledException)
            {
                currentParentAnalysis?.ThrowIfCancelled();
                refusals.Add(new JsonObject { ["method"] = SourceMember(method), ["unresolved"] = "csharp_decompilation_time_bound" });
            }
            catch (Exception error) when (error is not OutOfMemoryException)
            {
                refusals.Add(new JsonObject { ["method"] = SourceMember(method), ["unresolved"] = error is NotSupportedException ? error.Message : error.GetType().Name });
            }
        }
        attack["mechanicsSource"] = new JsonObject { ["source"] = "native_mechanics_source", ["version"] = 1,
            ["identity"] = new JsonObject { ["type"] = type, ["aiStyle"] = style }, ["records"] = mechanics,
            ["unresolved"] = mechanicsRefusals, ["strictSourceRefusals"] = refusals.DeepClone(), ["approximation"] = MechanicsIdentityAssumption };
        attack["nativeCSharpSource"] = new JsonObject { ["source"] = "verified_decompiled_native_csharp", ["version"] = 1,
            ["records"] = records, ["unresolved"] = refusals,
            ["scope"] = "Read-only C# reconstructed from MVID/IL-matched native PE bytes. Whole methods retain all branches; region code retains complete closed lexical bodies under original guards. No code, getters, constructors or hooks ran. Runtime detours, callbacks and called implementations remain unknown. This input is never generated-item executable code." };
    }
}
