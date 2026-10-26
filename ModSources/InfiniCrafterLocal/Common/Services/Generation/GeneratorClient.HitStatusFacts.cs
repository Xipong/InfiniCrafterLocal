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
        => VerifiedNativeStatusReference(source.type, source.ModProjectile is null, "projectile",
            "", certificate, moduleVersionId);

    private static readonly Lazy<string?> ContactHitStatusCertificate = new(() => NativeAttackCertificate(typeof(Player), "StatusToNPC"));
    internal static object? CaptureNativeContactHitStatusReference(Item item)
    {
        string[]? certificate = ContactHitStatusCertificate.Value?.Split(':');
        return certificate is { Length: 2 } ? VerifiedNativeStatusReference(item.type, item.ModItem is null, "contact",
            "", certificate[0], certificate[1]) : null;
    }

    private static object? VerifiedNativeStatusReference(int type, bool vanilla, string sourceKind, string fullName,
        string? certificate, string? moduleVersionId)
    {
        // Capture never executes hooks. Method identity, module, source kind and
        // vanilla host must agree: item contact cannot borrow projectile facts.
        string key = certificate + ":" + moduleVersionId;
        if (!vanilla || certificate is null || moduleVersionId is null
            || !NativeHitStatusCatalog.SourceKinds.TryGetValue(key, out string? kind) || kind != sourceKind
            || !NativeHitStatusCatalog.Sources.TryGetValue(key, out var catalog)
            || !catalog.TryGetValue(type, out var facts))
            return null;
        NativeHitStatusCatalog.RandomSources.TryGetValue(key, out var randomCatalog);
        NativeHitStatusCatalog.Choice[] choices = randomCatalog is not null && randomCatalog.TryGetValue(type, out var observed)
            ? observed : Array.Empty<NativeHitStatusCatalog.Choice>();
        object Effect(NativeHitStatusCatalog.Fact fact) => new
        {
            buffId = fact.BuffId,
            buffFullName = "Terraria/" + fact.BuffName,
            durationTicksMin = fact.MinimumTicks,
            durationTicksMax = fact.MaximumTicks,
            durationTicksStep = fact.StepTicks,
            durationDistribution = fact.MinimumTicks == fact.MaximumTicks ? "fixed" : "uniform_integer_steps_inclusive",
            sourceIlOffset = fact.IlOffset,
            // Same per-request identity, but NPC receiver semantics; never reuse
            // Player.UpdateBuffs operations for an applied NPC status.
            buffEffectReference = CaptureNativeBuffEffectReference(fact.BuffId, "npc"),
        };
        return new
        {
            source = sourceKind == "contact" ? "verified_native_StatusToNPC_reference" : "verified_native_StatusNPC_reference",
            sourceKind,
            fullName = fullName.Length > 0 ? fullName : "Terraria/" + (sourceKind == "contact" ? ItemID.Search.GetName(type) : ProjectileID.Search.GetName(type)),
            sourceMethodSha256 = certificate,
            sourceModuleVersionId = moduleVersionId,
            effects = facts.Select(Effect).ToArray(),
            randomOutcomes = choices.Select(choice => new
            {
                sourceRandomCallIlOffset = choice.SourceRandomCallIlOffset,
                randomMinimumInclusive = choice.RandomMinimumInclusive,
                randomMaximumExclusive = choice.RandomMaximumExclusive,
                alternatives = choice.Alternatives.Select(alternative => new
                {
                    randomValues = alternative.RandomValues,
                    probabilityNumerator = alternative.ProbabilityNumerator,
                    probabilityDenominator = alternative.ProbabilityDenominator,
                    effects = alternative.Effects.Select(Effect).ToArray(),
                }).ToArray(),
            }).ToArray(),
            scope = (sourceKind == "contact" ? "Native item-contact StatusToNPC only. " : "Native projectile StatusNPC only. ") + "Proved vanilla NPC-hit AddBuff requests, not an exhaustive list. effects are unconditional; each randomOutcomes choice has mutually exclusive alternatives, exactly one per hit, including empty alternatives. Do not combine alternatives as simultaneous effects or independent rolls. Requests depending on player/world/AI state or more than one branching random call, and mod hooks, remain unknown. Target immunity and other loaded mods can change the outcome. Not player/PvP hits or child AI. Read-only source facts, not inherited execution; Author explicitly chooses generated status behavior."
        };
    }
}
