#nullable enable
using System;
using System.Reflection;
using System.Linq;
using System.Security.Cryptography;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Offline CFG analysis generates the catalog from certified native IL.
    // It never executes hit hooks or selects generated gameplay at craft time.
    private static readonly Lazy<string?> HitStatusSourceCertificate = new(() =>
    {
        try
        {
            byte[]? il = typeof(Projectile).GetMethod(nameof(Projectile.StatusNPC),
                BindingFlags.Instance | BindingFlags.Public)?.GetMethodBody()?.GetILAsByteArray();
            return il is null ? null : Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant();
        }
        catch { return null; }
    });

    // Live parent requests and offline /infinidump share this one fact owner.
    internal static object? CaptureNativeHitStatusReference(Projectile source)
        => VerifiedSourceHitStatusReference(source, HitStatusSourceCertificate.Value, typeof(Projectile).Module.ModuleVersionId.ToString());

    private static object? VerifiedSourceHitStatusReference(Projectile source, string? certificate, string? moduleVersionId)
    {
        // Do not execute native hit hooks while crafting or extrapolate to a mod
        // projectile, another method build, player/PvP hits, or child projectiles.
        if (source.ModProjectile is not null || certificate is null || moduleVersionId is null
            || !NativeHitStatusCatalog.Sources.TryGetValue(certificate + ":" + moduleVersionId, out var catalog)
            || !catalog.TryGetValue(source.type, out var facts))
            return null;
        return new
        {
            source = "verified_native_StatusNPC_reference",
            fullName = "Terraria/" + ProjectileID.Search.GetName(source.type),
            sourceMethodSha256 = certificate,
            sourceModuleVersionId = moduleVersionId,
            effects = facts.Select(fact => new
            {
                buffId = fact.BuffId,
                buffFullName = "Terraria/" + fact.BuffName,
                durationTicksMin = fact.MinimumTicks,
                durationTicksMax = fact.MaximumTicks,
                durationTicksStep = fact.StepTicks,
                durationDistribution = fact.MinimumTicks == fact.MaximumTicks
                    ? "fixed" : "uniform_integer_steps_inclusive",
                sourceIlOffset = fact.IlOffset,
            }).ToArray(),
            scope = "Proved unconditional vanilla NPC-hit AddBuff requests only, not an exhaustive list of effects. Conditional/player/world/AI-dependent requests and mod hooks are unknown. Target immunity and other loaded mods can change the outcome. Not player/PvP hits or child AI. Read-only source facts, not inherited execution; Author explicitly chooses generated status behavior."
        };
    }
}
