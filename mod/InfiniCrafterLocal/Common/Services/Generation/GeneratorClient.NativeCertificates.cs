#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.IO;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using Mono.Cecil;
using Terraria;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed record NativeMetadata(Mono.Cecil.AssemblyDefinition Assembly, PEReader Pe);
    private static readonly Lazy<NativeMetadata?> NativeMethodMetadata = new(() =>
    {
        try
        {
            string path = typeof(Player).Assembly.Location;
            byte[] image = File.ReadAllBytes(path);
            var assembly = Mono.Cecil.AssemblyDefinition.ReadAssembly(new MemoryStream(image, writable: false));
            if (assembly.MainModule.Mvid != typeof(Player).Module.ModuleVersionId) { assembly.Dispose(); return null; }
            return new NativeMetadata(assembly, new PEReader(new MemoryStream(image, writable: false)));
        }
        catch { return null; }
    });
    private sealed record InspectedNativeMethod(string Shape, string CurrentCertificate);
    private static readonly ConcurrentDictionary<MethodInfo, Lazy<InspectedNativeMethod?>> NativeMethodProofs = new();
    private static readonly ConcurrentDictionary<string, Lazy<Dictionary<string, string>?>> NativeCatalogProofs = new();

    private static InspectedNativeMethod? InspectNativeMethod(MethodInfo method)
        => NativeMethodProofs.GetOrAdd(method, m => new(() =>
        {
            try
            {
                if (m.Module != typeof(Player).Module) return null;
                byte[]? bytes = m.GetMethodBody()?.GetILAsByteArray();
                if (bytes is null) return null;
                var metadata = NativeMethodMetadata.Value;
                if (metadata is null) return null;
                lock (metadata)
                {
                var definition = metadata.Pe.GetMetadataReader().GetMethodDefinition((MethodDefinitionHandle)MetadataTokens.Handle(m.MetadataToken));
                byte[]? diskBytes = metadata.Pe.GetMethodBody(definition.RelativeVirtualAddress).GetILBytes();
                if (diskBytes is null || !bytes.SequenceEqual(diskBytes)) return null;
                if (metadata.Assembly.MainModule.LookupToken(m.MetadataToken) is not Mono.Cecil.MethodDefinition native) return null;
                return new InspectedNativeMethod(NativeSourceFingerprint.Compute(native),
                    Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() + ":" + m.Module.ModuleVersionId);
                }
            }
            catch { return null; }
        })).Value;

    // Only declared dependencies of this catalog are inspected. A changed
    // dependency withholds this catalog, not unrelated live IL capture/gameplay.
    private static Dictionary<string, string>? NativeCatalogProof(string group)
        => NativeCatalogProofs.GetOrAdd(group, g => new(() =>
        {
            try
            {
                var entries = NativeSourceCertificates.Methods.Where(e => e.Group == g).ToArray();
                if (entries.Length == 0) return null;
                var result = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (var expected in entries)
                {
                    Type? owner = typeof(Player).Assembly.GetType(expected.Owner.Replace('/', '+'));
                    var matching = owner?.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                        .Where(m => m.Name == expected.Name).Select(InspectNativeMethod)
                        .Where(p => p?.Shape == expected.Shape).ToArray();
                    if (matching is not { Length: 1 }) return null;
                    string current = matching[0]!.CurrentCertificate;
                    if (result.TryGetValue(current, out string? prior) && prior != expected.AuditedCertificate) return null;
                    result[current] = expected.AuditedCertificate;
                }
                return result;
            }
            catch { return null; }
        })).Value;

    private static bool NativeCatalogVerified(string group) => NativeCatalogProof(group) is not null;
    private static string? AuditedNativeCertificate(string? current, string group)
        => current is not null && NativeCatalogProof(group)?.TryGetValue(current, out string? audited) == true ? audited : null;
    private static JsonObject NativeMethodProvenance(string current, string audited) => new()
    {
        ["observedMethodSha256"] = current.Split(':')[0],
        ["observedModuleVersionId"] = current.Split(':')[1],
        ["auditedMethodSha256"] = audited.Split(':')[0],
        ["auditedModuleVersionId"] = audited.Split(':')[1],
        ["verification"] = "resolved_typed_IL_and_declared_dependencies_equal; not_arbitrary_mod_hooks"
    };
}
