#nullable enable
using System;
using System.Collections.Generic;

namespace InfiniCrafterLocal.Common.Models;

internal enum GeneratedHeldRenderRole
{
    Generic,
    Ranged,
    Magic,
    Thrust,
    Tethered,
    Swing,
}

// Canonical runtime-family policy shared by DTO normalization, item application,
// projectile execution and presentation. Natural-language aliases never enter here.
internal static class GeneratedRuntimeFamilyPolicy
{
    public const string None = "none";
    public const string Swing = "swing";
    public const string Thrust = "thrust";
    public const string Returning = "returning";
    public const string Flail = "flail";
    public const string Yoyo = "yoyo";
    public const string Whip = "whip";
    public const string Shoot = "shoot";
    public const string Cast = "cast";
    public const string Beam = "beam";
    public const string ChargeRelease = "charge_release";
    public const string OverheadBarrage = "overhead_barrage";
    public const string Throw = "throw";
    public const string Summon = "summon";
    public const string Sentry = "sentry";

    private readonly record struct RuntimeFamilyProfile(
        string Name,
        bool ProjectileOwned,
        bool HeldProjectile,
        bool ItemBodiedProjectile,
        GeneratedHeldRenderRole HeldRenderRole);

    private static readonly Dictionary<string, RuntimeFamilyProfile> Profiles = new(StringComparer.Ordinal)
    {
        [None] = new(None, false, false, false, GeneratedHeldRenderRole.Generic),
        [Swing] = new(Swing, false, false, false, GeneratedHeldRenderRole.Swing),
        [Thrust] = new(Thrust, true, true, true, GeneratedHeldRenderRole.Thrust),
        [Returning] = new(Returning, true, false, true, GeneratedHeldRenderRole.Tethered),
        [Flail] = new(Flail, true, true, false, GeneratedHeldRenderRole.Tethered),
        [Yoyo] = new(Yoyo, true, true, true, GeneratedHeldRenderRole.Tethered),
        [Whip] = new(Whip, true, true, false, GeneratedHeldRenderRole.Tethered),
        [Shoot] = new(Shoot, true, false, false, GeneratedHeldRenderRole.Ranged),
        [Cast] = new(Cast, true, false, false, GeneratedHeldRenderRole.Magic),
        [Beam] = new(Beam, true, true, false, GeneratedHeldRenderRole.Magic),
        [ChargeRelease] = new(ChargeRelease, true, true, false, GeneratedHeldRenderRole.Generic),
        [OverheadBarrage] = new(OverheadBarrage, true, false, false, GeneratedHeldRenderRole.Generic),
        [Throw] = new(Throw, true, false, true, GeneratedHeldRenderRole.Generic),
        [Summon] = new(Summon, true, false, false, GeneratedHeldRenderRole.Magic),
        [Sentry] = new(Sentry, true, false, false, GeneratedHeldRenderRole.Magic),
    };

    private static string Token(string? value)
        => (value ?? "").Trim().ToLowerInvariant();

    private static RuntimeFamilyProfile Profile(string? value)
    {
        string token = Token(value);
        return Profiles.TryGetValue(token, out RuntimeFamilyProfile profile) ? profile : Profiles[None];
    }

    public static bool IsCanonical(string? value) => Profiles.ContainsKey(Token(value));

    public static string Normalize(string? value) => Profile(value).Name;

    public static bool Is(string? value, string family)
        => string.Equals(Profile(value).Name, family, StringComparison.Ordinal);

    public static bool IsProjectileOwned(string? value) => Profile(value).ProjectileOwned;

    public static bool HasCompatibleMovement(AttackSpec? spec)
    {
        if (spec is null) return false;
        string family = Normalize(spec.RuntimeFamily);
        int movement = spec.MovementCode;
        if (family == Returning && movement is not (5 or 14)) return false;
        if (family == Flail && movement != 16) return false;
        if (family == Yoyo && movement != 17) return false;
        if (family == Whip && movement != 18) return false;
        if (movement == 16 && family != Flail) return false;
        if (movement == 17 && family != Yoyo) return false;
        if (movement == 18 && family != Whip) return false;
        return true;
    }

    public static bool HasValidExecutorContract(AttackSpec? spec)
    {
        if (spec is null) return false;
        string family = Normalize(spec.RuntimeFamily);
        string delivery = (spec.Delivery ?? "").Trim().ToLowerInvariant();
        if (family == None || !AcceptsDelivery(family, delivery) || !HasCompatibleMovement(spec))
            return false;
        if (family == ChargeRelease)
            return spec.ChargeTicks > 0 && spec.ChargePowerMultiplier > 0f;
        if (family == Sentry)
            return spec.SentryPlacement is "grounded" or "floating"
                && spec.SentryAttackIntervalTicks > 0
                && spec.SentryLifetimeTicks > 0
                && spec.SentryTargetRangeTiles > 0f;
        return true;
    }

    public static bool UsesHeldProjectile(string? value) => Profile(value).HeldProjectile;

    public static bool UsesItemSpriteAsProjectile(string? value) => Profile(value).ItemBodiedProjectile;

    public static bool UsesProjectileOnlyItemAffordance(string? value, string? delivery)
    {
        string family = Normalize(value);
        string carrier = (delivery ?? "").Trim().ToLowerInvariant().Replace('-', '_').Replace(' ', '_');
        return Profile(family).ProjectileOwned && !KeepsItemBodyDamageLane(family, carrier);
    }

    public static bool KeepsItemBodyDamageLane(string? value, string? delivery)
    {
        string family = Normalize(value);
        string carrier = (delivery ?? "").Trim().ToLowerInvariant().Replace('-', '_').Replace(' ', '_');
        return carrier == "swing" && family is Shoot or OverheadBarrage;
    }

    public static bool AcceptsDelivery(string? value, string? delivery)
    {
        string family = Normalize(value);
        string carrier = (delivery ?? "").Trim().ToLowerInvariant().Replace('-', '_').Replace(' ', '_');
        return family switch
        {
            None => carrier == "none",
            Swing => carrier == "swing",
            Thrust => carrier == "thrust",
            Returning => carrier == "throw",
            Flail => carrier == "flail",
            Yoyo => carrier == "yoyo",
            Whip => carrier == "whip",
            Shoot => carrier is "shoot" or "swing",
            Cast or Beam => carrier == "cast",
            ChargeRelease => carrier is "shoot" or "cast" or "throw",
            OverheadBarrage => carrier is "shoot" or "cast" or "swing",
            Throw => carrier == "throw",
            Summon or Sentry => carrier == "summon",
            _ => false,
        };
    }

    public static GeneratedHeldRenderRole HeldRenderRole(string? value)
        => HeldRenderRole(value, "");

    public static GeneratedHeldRenderRole HeldRenderRole(string? value, string? delivery)
    {
        string family = Normalize(value);
        string carrier = (delivery ?? "").Trim().ToLowerInvariant().Replace('-', '_').Replace(' ', '_');
        if (KeepsItemBodyDamageLane(family, carrier))
            return GeneratedHeldRenderRole.Swing;
        if (family != OverheadBarrage && family != ChargeRelease)
            return Profile(family).HeldRenderRole;
        return carrier switch
        {
            "swing" => GeneratedHeldRenderRole.Swing,
            "cast" => GeneratedHeldRenderRole.Magic,
            "shoot" => GeneratedHeldRenderRole.Ranged,
            _ => GeneratedHeldRenderRole.Generic,
        };
    }
}
