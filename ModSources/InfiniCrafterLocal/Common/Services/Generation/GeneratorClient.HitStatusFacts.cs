#nullable enable
using System;
using System.Reflection;
using System.Security.Cryptography;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Verified from the official tML v2026.08.3.0 StatusNPC IL. This is an
    // optional source observation, not a type/name -> generated gameplay router.
    private const string HitStatusSourceMethodSha256 = "0409d6e8aeb6c41acc5454f7f818368639b041341d9eafff9dd1336cd42e2cf7";
    private const string InstalledHitStatusSourceMethodSha256 = "ea30212888353eea100edc863b651f8ee1555b4f39891eb2de442ba3339dcb79";
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
        => VerifiedSourceHitStatusReference(source, HitStatusSourceCertificate.Value);

    private static object? VerifiedSourceHitStatusReference(Projectile source, string? certificate)
    {
        // Do not execute native hit hooks while crafting or extrapolate to a mod
        // projectile, another method build, player/PvP hits, or child projectiles.
        if (source.ModProjectile is not null
            || certificate is not (HitStatusSourceMethodSha256 or InstalledHitStatusSourceMethodSha256))
            return null;
        int buffId, minimumTicks, maximumTicks;
        string projectileName, buffName;
        switch (source.type)
        {
            case ProjectileID.GoldenShowerFriendly:
                projectileName = nameof(ProjectileID.GoldenShowerFriendly);
                buffId = BuffID.Ichor; buffName = nameof(BuffID.Ichor);
                minimumTicks = maximumTicks = 600;
                break;
            case ProjectileID.ShadowFlameKnife:
                projectileName = nameof(ProjectileID.ShadowFlameKnife);
                buffId = BuffID.ShadowFlame; buffName = nameof(BuffID.ShadowFlame);
                minimumTicks = 60; maximumTicks = 179; // UnifiedRandom.Next(60, 180)
                break;
            default:
                return null;
        }
        return new
        {
            source = "verified_native_StatusNPC_reference",
            fullName = "Terraria/" + projectileName,
            sourceMethodSha256 = certificate,
            buffId, buffFullName = "Terraria/" + buffName,
            durationTicksMin = minimumTicks, durationTicksMax = maximumTicks,
            durationDistribution = minimumTicks == maximumTicks ? "fixed" : "uniform_integer_inclusive",
            scope = "Vanilla NPC-hit AddBuff request; target immunity and other loaded mods can change the outcome. Not player/PvP hits or child AI. Read-only source facts, not inherited execution; Author explicitly chooses generated status behavior."
        };
    }
}
