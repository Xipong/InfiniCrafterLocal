#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Read bytes and metadata only. Never run UpdateBuffs, NPC updates, ModBuff
    // hooks, tooltips, or copied native code while preparing a parent request.
    private static readonly Lazy<string?> BuffEffectSourceCertificate = new(() =>
    {
        try
        {
            var assembly = typeof(Player).Assembly;
            using var stream = File.OpenRead(assembly.Location);
            string assemblyHash = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
            string key = assemblyHash + ":" + typeof(Player).Module.ModuleVersionId;
            if (!NativeBuffEffectCatalog.Sources.TryGetValue(key, out var source)) return null;
            foreach (var expected in source.Methods)
            {
                Type owner = expected.Owner == "Player" ? typeof(Player) : typeof(NPC);
                MethodInfo? method = owner.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                    .SingleOrDefault(candidate => candidate.Name == expected.Name);
                byte[]? il = method?.GetMethodBody()?.GetILAsByteArray();
                if (il is null || Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant() != expected.Sha256)
                    return null;
            }
            return key;
        }
        catch { return null; }
    });

    internal static JsonObject CaptureNativeBuffEffectReference(int buffId, string receiver)
        => CaptureModBuffEffectReference(buffId, receiver)
            ?? VerifiedNativeBuffEffectReference(buffId, receiver, BuffEffectSourceCertificate.Value);

    private static JsonObject VerifiedNativeBuffEffectReference(int buffId, string receiver, string? certificate)
    {
        string? fullName = null;
        try
        {
            if (buffId > 0 && BuffID.Search.ContainsId(buffId))
            {
                string name = BuffID.Search.GetName(buffId);
                fullName = buffId < BuffID.Count ? "Terraria/" + name : name;
            }
        }
        catch { }
        // Unknown/modded identities remain visible only for this observed parent.
        // Never advertise unknown semantics as an empty/complete effect set.
        // The carrier can be modded while the requested buff is vanilla. Its
        // provenance does not change the certified implementation of that ID.
        // Application/admission and loaded hooks remain outside these fragments.
        string reason = buffId <= 0 || buffId >= BuffID.Count
            ? "buff_identity_outside_native_source_subset"
            : receiver is not ("player" or "npc") ? "unsupported_receiver"
            : certificate is null || !NativeBuffEffectCatalog.Sources.ContainsKey(certificate)
                ? "unknown_native_binary_or_method_certificate"
                : "buff_not_in_supported_source_subset";
        if (reason == "buff_not_in_supported_source_subset"
            && NativeBuffEffectCatalog.Sources.TryGetValue(certificate!, out var source)
            && source.Records.TryGetValue(receiver + ":" + buffId, out string? json)
            && JsonNode.Parse(json) is JsonObject observation)
        {
            observation["source"] = "certified_native_buff_operation_fragments";
            observation["sourceCertificate"] = JsonNode.Parse(source.CertificateJson);
            return observation;
        }
        return new JsonObject
        {
            ["source"] = "parent_observed_buff_identity_semantics_unavailable",
            ["receiver"] = receiver,
            ["buffId"] = buffId,
            ["buffFullName"] = fullName,
            ["completeness"] = "unsupported",
            ["fragments"] = new JsonArray(),
            ["unsupported"] = new JsonArray(JsonValue.Create(reason)),
            ["scope"] = "Observed parent-local identity only; no proved effect values. Modded behavior, native source outside the certified subset, downstream AI and actual admission/immunity remain unknown. No hooks were executed.",
        };
    }
}
