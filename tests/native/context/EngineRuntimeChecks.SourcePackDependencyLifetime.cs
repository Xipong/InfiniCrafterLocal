using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using ICSharpCode.Decompiler.Metadata;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private sealed record DependencyLifetimeFixture(string Path, string Identity, string Sha256, int Bytes)
    {
        internal JsonObject Pin() => new()
        {
            ["reference"] = Identity, ["assembly"] = Identity, ["sha256"] = Sha256, ["bytes"] = Bytes
        };
    }

    private static DependencyLifetimeFixture DependencyLifetimeInput(Type type)
    {
        string path = type.Assembly.Location;
        using var file = new PEFile(path);
        using var input = File.OpenRead(path);
        return new(path, file.FullName, Convert.ToHexString(SHA256.HashData(input)).ToLowerInvariant(),
            checked((int)new FileInfo(path).Length));
    }

    private static bool DependencyLifetimeClosed(PEFile file)
    {
        try { _ = file.Reader.GetMetadata(); return false; }
        catch (ObjectDisposedException) { return true; }
    }

    private sealed class DependencyLifetimeResolver : IAssemblyResolver, IDisposable
    {
        private readonly Dictionary<string, string> paths;
        internal readonly List<PEFile> Files = new();
        internal readonly List<string> Requests = new();
        internal readonly List<bool> PreviousClosedAtNextResolve = new();
        internal Action? AfterOpen;

        internal DependencyLifetimeResolver(params DependencyLifetimeFixture[] inputs)
            => paths = inputs.ToDictionary(input => input.Identity, input => input.Path, StringComparer.Ordinal);

        public PEFile? Resolve(IAssemblyReference reference)
        {
            Requests.Add(reference.FullName);
            if (Files.Count > 0) PreviousClosedAtNextResolve.Add(DependencyLifetimeClosed(Files[^1]));
            if (!paths.TryGetValue(reference.FullName, out string? path)) return null;
            var file = new PEFile(path, File.OpenRead(path), PEStreamOptions.Default);
            Files.Add(file);
            AfterOpen?.Invoke();
            return file;
        }

        public PEFile? ResolveModule(PEFile mainModule, string moduleName) => throw new NotSupportedException();
        public Task<PEFile?> ResolveAsync(IAssemblyReference reference) => Task.FromResult(Resolve(reference));
        public Task<PEFile?> ResolveModuleAsync(PEFile mainModule, string moduleName) => throw new NotSupportedException();
        public void Dispose() { foreach (PEFile file in Files) file.Dispose(); }
    }

    private static bool DependencyLifetimeMatch(JsonArray pins, IAssemblyResolver resolver, CancellationToken cancellation = default)
        => (bool)typeof(GeneratorClient).GetMethod("NativeSourcePackDependenciesMatchCore", BindingFlags.Static | BindingFlags.NonPublic)!
            .Invoke(null, new object[] { pins, resolver, cancellation })!;

    private static void NativeSourcePackDependenciesReleaseImagesBeforeNextResolve()
    {
        var first = DependencyLifetimeInput(typeof(Uri));
        var second = DependencyLifetimeInput(typeof(Enumerable));
        using var resolver = new DependencyLifetimeResolver(first, second);
        Equal(true, DependencyLifetimeMatch(new JsonArray(first.Pin(), second.Pin()), resolver),
            "real PE images retain exact assembly identities, lengths and independently computed SHA-256 pins");
        Equal(true, resolver.Requests.SequenceEqual(new[] { first.Identity, second.Identity }),
            "dependency resolution preserves manifest order");
        Equal(true, resolver.PreviousClosedAtNextResolve.Single(),
            "the previous verified PE is disposed before resolving the next dependency");
        Equal(true, resolver.Files.All(DependencyLifetimeClosed),
            "the final verified PE is disposed before dependency validation returns");
    }

    private static void NativeSourcePackDependenciesReleaseImagesOnFailureAndCancellation()
    {
        var input = DependencyLifetimeInput(typeof(Uri));
        foreach (string failure in new[] { "hash", "identity", "null-pin", "duplicate" })
        {
            using var resolver = new DependencyLifetimeResolver(input);
            JsonObject pin = input.Pin();
            if (failure == "hash") pin["sha256"] = new string('0', 64);
            if (failure == "identity") pin["assembly"] = "Unexpected, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
            if (failure == "null-pin") { pin["assembly"] = null; pin["sha256"] = null; pin["bytes"] = 0; }
            var pins = new JsonArray(pin);
            if (failure == "duplicate") pins.Add(input.Pin());
            Equal(false, DependencyLifetimeMatch(pins, resolver), "dependency validation rejects " + failure);
            Equal(1, resolver.Requests.Count, "refusal does not resolve a duplicate or any following dependency");
            Equal(true, DependencyLifetimeClosed(resolver.Files.Single()),
                "refused dependency PE is disposed before returning: " + failure);
        }

        // Structural failures still precede resolution, including on the null path.
        foreach (string failure in new[] { "hash-shape", "length-bound", "null-shape" })
        {
            using var resolver = new DependencyLifetimeResolver(input);
            JsonObject pin = input.Pin();
            if (failure == "hash-shape") pin["sha256"] = "invalid";
            if (failure == "length-bound") pin["bytes"] = 64 * 1024 * 1024 + 1;
            if (failure == "null-shape") pin["assembly"] = null;
            Equal(false, DependencyLifetimeMatch(new JsonArray(pin), resolver), "structural refusal remains closed: " + failure);
            Equal(0, resolver.Requests.Count, "invalid pin shape cannot start resolution: " + failure);
        }

        using var cancellation = new CancellationTokenSource();
        using var cancelledResolver = new DependencyLifetimeResolver(input) { AfterOpen = cancellation.Cancel };
        bool cancelled = false;
        try { DependencyLifetimeMatch(new JsonArray(input.Pin()), cancelledResolver, cancellation.Token); }
        catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { cancelled = true; }
        Equal(true, cancelled, "cancellation after resolution still propagates before hashing the image");
        Equal(true, DependencyLifetimeClosed(cancelledResolver.Files.Single()),
            "the current resolved PE is disposed during cancellation unwinding");
    }

    private static void NativeSourcePackResolverRepeatedResolutionSurvivesEarlyRelease()
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var input = DependencyLifetimeInput(typeof(Uri));
        Type resolverType = typeof(GeneratorClient).GetNestedType("NativeCSharpResolver", BindingFlags.NonPublic)!;
        PEFile? first = null, second = null;
        using (var owner = (IDisposable)Activator.CreateInstance(resolverType, flags, binder: null,
            args: new object[] { typeof(Terraria.Projectile).Module.FullyQualifiedName, CancellationToken.None }, culture: null)!)
        {
            var resolver = (IAssemblyResolver)owner;
            var reference = AssemblyNameReference.Parse(input.Identity);
            first = resolver.Resolve(reference)!;
            Equal(true, first is not null, "the actual resolver finds the host-selected framework dependency");
            // The real positive matcher materializes FullName before hashing
            // and releasing the image. RecordResolution can safely reuse that
            // cached identity even after the underlying metadata is disposed.
            Equal(input.Identity, first!.FullName, "materialize the resolved assembly identity as the matcher does");
            Equal(input.Bytes, first.Reader.GetEntireImage().Length, "materialize the actual full-image view");
            first.Dispose();
            Equal(true, DependencyLifetimeClosed(first), "early disposal releases the first real reader");
            second = resolver.Resolve(reference)!;
            Equal(true, second is not null && !ReferenceEquals(first, second), "repeated resolution returns a fresh independently owned PE");
            Equal(input.Identity, second!.FullName, "repeated resolution can compare the cached identity of the disposed prior PE");
            Equal(true, second.Reader.GetMetadata().Length > 0, "the new reader remains usable");
            Equal(true, (bool)resolverType.GetProperty("ResolutionsStable", flags)!.GetValue(owner)!,
                "early release does not change resolution stability or reference flags");
        }
        Equal(true, DependencyLifetimeClosed(first!) && DependencyLifetimeClosed(second!),
            "resolver cleanup safely disposes both previously released and still-owned readers");
    }
}
