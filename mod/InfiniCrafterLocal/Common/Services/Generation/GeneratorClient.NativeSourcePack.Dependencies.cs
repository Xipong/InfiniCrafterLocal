#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.Metadata;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private const int NativeSourcePackDependencyLimit = 1024;
    private const long NativeSourcePackDependencyBytes = 512L * 1024 * 1024;

    // Full identities alone do not pin assembly binding: an older reference
    // can resolve to a newer definition. Preserve the requested identity and
    // its exact resolved PE, including unsuccessful resolution attempts.
    // No environment paths are persisted and no assemblies are loaded.
    private static JsonArray NativeSourcePackDependencyPins(NativeCSharpModule module)
    {
        var cancellation = currentParentAnalysis?.Cancellation ?? CancellationToken.None;
        cancellation.ThrowIfCancellationRequested();
        if (!module.DependencyResolutionsStable)
            throw new NotSupportedException("native_source_pack_dependency_resolution_unstable");
        var files = module.DependencyFiles.Take(NativeSourcePackDependencyLimit + 1).ToArray();
        var resolutions = module.DependencyResolutions.Take(NativeSourcePackDependencyLimit + 1).ToArray();
        if (files.Length == 0 || files.Length > NativeSourcePackDependencyLimit
            || resolutions.Length == 0 || resolutions.Length > NativeSourcePackDependencyLimit)
            throw new NotSupportedException("native_source_pack_dependency_count");
        var captured = new Dictionary<string, (string Sha256, int Bytes)>(StringComparer.Ordinal);
        long remaining = NativeSourcePackDependencyBytes;
        foreach (var file in files)
        {
            cancellation.ThrowIfCancellationRequested();
            if (!file.IsAssembly) throw new NotSupportedException("native_source_pack_dependency_netmodule");
            var pin = NativeSourcePackDependencyHash(file, ref remaining, cancellation);
            if (captured.TryGetValue(file.FullName, out var prior) && prior != pin)
                throw new NotSupportedException("native_source_pack_dependency_ambiguous");
            captured[file.FullName] = pin;
        }

        var result = new JsonArray();
        var covered = new HashSet<string>(StringComparer.Ordinal);
        foreach (var (reference, file) in resolutions.OrderBy(value => value.Reference.FullName, StringComparer.Ordinal))
        {
            cancellation.ThrowIfCancellationRequested();
            var parsed = NativeSourcePackDependencyReference(reference.FullName);
            if (parsed.IsWindowsRuntime != reference.IsWindowsRuntime || parsed.IsRetargetable != reference.IsRetargetable)
                throw new NotSupportedException("native_source_pack_dependency_reference_flags");
            if (file is null)
            {
                result.Add(new JsonObject { ["reference"] = reference.FullName, ["assembly"] = null,
                    ["sha256"] = null, ["bytes"] = 0 });
                continue;
            }
            if (!file.IsAssembly || !captured.TryGetValue(file.FullName, out var expected))
                throw new NotSupportedException("native_source_pack_dependency_binding_not_captured");
            covered.Add(file.FullName);
            result.Add(new JsonObject { ["reference"] = reference.FullName, ["assembly"] = file.FullName,
                ["sha256"] = expected.Sha256, ["bytes"] = expected.Bytes });
        }
        if (captured.Keys.Any(identity => !covered.Contains(identity)))
            throw new NotSupportedException("native_source_pack_dependency_binding_not_captured");
        cancellation.ThrowIfCancellationRequested();
        return result;
    }

    private static bool NativeSourcePackDependenciesMatch(NativeCSharpModule module, JsonArray pins, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        if (pins.Count == 0 || pins.Count > NativeSourcePackDependencyLimit) return false;
        try
        {
            using var resolver = new NativeCSharpResolver(module.Path, cancellation);
            var seen = new HashSet<string>(StringComparer.Ordinal);
            long remaining = NativeSourcePackDependencyBytes;
            bool hasResolved = false;
            foreach (var node in pins)
            {
                cancellation.ThrowIfCancellationRequested();
                if (node is not JsonObject pin || pin["reference"] is not JsonValue referenceValue
                    || !referenceValue.TryGetValue<string>(out string? identity) || identity is null || !seen.Add(identity)
                    || pin["bytes"] is not JsonValue lengthValue || !lengthValue.TryGetValue<int>(out int length)) return false;
                var reference = NativeSourcePackDependencyReference(identity);
                if (pin["assembly"] is null)
                {
                    if (pin["sha256"] is not null || length != 0 || resolver.Resolve(reference) is not null) return false;
                    continue;
                }
                if (pin["assembly"] is not JsonValue assemblyValue || !assemblyValue.TryGetValue<string>(out string? assembly)
                    || string.IsNullOrEmpty(assembly) || pin["sha256"] is not JsonValue hashValue
                    || !hashValue.TryGetValue<string>(out string? sha) || sha is null || sha.Length != 64
                    || sha.Any(character => character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f'))
                    || length <= 0 || length > NativeCSharpPeLimit || length > remaining) return false;
                var file = resolver.Resolve(reference);
                if (file is null || !file.IsAssembly || !string.Equals(file.FullName, assembly, StringComparison.Ordinal)) return false;
                var actual = NativeSourcePackDependencyHash(file, ref remaining, cancellation);
                if (actual.Bytes != length || !string.Equals(actual.Sha256, sha, StringComparison.Ordinal)) return false;
                hasResolved = true;
            }
            cancellation.ThrowIfCancellationRequested();
            return hasResolved;
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception error) when (error is not OutOfMemoryException)
        { return false; }
    }

    private static AssemblyNameReference NativeSourcePackDependencyReference(string identity)
    {
        if (string.IsNullOrEmpty(identity) || identity.Length > 2048 || identity.Any(char.IsControl))
            throw new InvalidDataException("native_source_pack_dependency_identity");
        var reference = AssemblyNameReference.Parse(identity);
        if (!string.Equals(reference.FullName, identity, StringComparison.Ordinal) || string.IsNullOrEmpty(reference.Name)
            || reference.Name.IndexOfAny(new[] { '/', '\\', ':' }) >= 0
            || reference.Culture?.IndexOfAny(new[] { '/', '\\', ':' }) >= 0)
            throw new InvalidDataException("native_source_pack_dependency_identity");
        return reference;
    }

    private static unsafe (string Sha256, int Bytes) NativeSourcePackDependencyHash(PEFile file,
        ref long remaining, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        // Bound disk images before requesting the PEReader's complete image.
        // Hash that reader's bytes, not a later re-open of the same pathname.
        var info = new FileInfo(file.FileName);
        if (!info.Exists || info.Length <= 0 || info.Length > NativeCSharpPeLimit || info.Length > remaining)
            throw new InvalidDataException("native_source_pack_dependency_size");
        var image = file.Reader.GetEntireImage();
        if (image.Length <= 0 || image.Length > NativeCSharpPeLimit || image.Length > remaining || image.Length != info.Length)
            throw new InvalidDataException("native_source_pack_dependency_size");
        remaining -= image.Length;
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        for (int offset = 0; offset < image.Length; offset += 65536)
        {
            cancellation.ThrowIfCancellationRequested();
            hash.AppendData(new ReadOnlySpan<byte>(image.Pointer + offset, Math.Min(65536, image.Length - offset)));
        }
        cancellation.ThrowIfCancellationRequested();
        return (Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant(), image.Length);
    }
}
