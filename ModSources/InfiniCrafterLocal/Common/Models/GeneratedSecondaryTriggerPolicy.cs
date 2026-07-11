#nullable enable
using System;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Canonical trigger vocabulary for bounded generated child projectiles.
/// This policy accepts exact contract ids only; it never reads item names, tooltip
/// text, materials or visual prose.
/// </summary>
internal static class GeneratedSecondaryTriggerPolicy
{
    public const string OnHit = "on_hit";
    public const string OnExpire = "on_expire";

    public static string Normalize(string? value)
    {
        string token = (value ?? "").Trim();
        return token switch
        {
            OnHit => OnHit,
            OnExpire => OnExpire,
            _ => "",
        };
    }

    public static string NormalizeForRuntimeFamily(string? value, string? runtimeFamily)
    {
        string trigger = Normalize(value);
        if (trigger == OnExpire && (
            GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.OverheadBarrage)
            || GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.ChargeRelease)
            || GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Sentry)))
            return "";
        return trigger;
    }

    public static bool Is(string? value, string trigger)
        => string.Equals(Normalize(value), trigger, StringComparison.Ordinal);
}
