#nullable enable
using System;
using System.Collections.Generic;
using Terraria.Audio;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Audio;

/// <summary>
/// Exact built-in Terraria SoundID catalog for generated items.
///
/// The catalog is intentionally broad enough to avoid every generated item sharing
/// a handful of sounds, but it is not a weapon-name classifier. Python/LLM authors
/// a canonical acoustic id; C# resolves that exact id. Names, tooltip text,
/// projectile descriptions, taxonomy prose and search text never select gameplay
/// or built-in audio here.
/// </summary>
public static class InfiniSoundLibrary
{
    public const string ContractVersion = "infini.terraria-sound-catalog.v8";
    public const string BuiltInCatalogSource = "terraria_vanilla";

    private static readonly IReadOnlyDictionary<string, SoundStyle> BuiltInCatalog =
        new Dictionary<string, SoundStyle>(StringComparer.Ordinal)
        {
            // Melee / thrown.
            ["melee_swing"] = SoundID.Item1,
            ["melee_thrust"] = SoundID.Item71,
            ["melee_heavy"] = SoundID.Item37,
            ["melee_energy_slash"] = SoundID.Item60,
            ["melee_prismatic_shred"] = SoundID.Item169,
            ["throw_light"] = SoundID.Item1,
            ["returning_boomerang"] = SoundID.Item7,
            ["flail_chain"] = SoundID.Item10,
            ["yoyo_launch"] = SoundID.Item1,
            ["whip_lash"] = SoundID.Item152,
            ["insect_swarm"] = SoundID.Item97,
            ["creature_meow"] = SoundID.Item58,

            // Ranged.
            ["bow_release"] = SoundID.Item5,
            ["bow_volley"] = SoundID.Item102,
            ["firearm_light"] = SoundID.Item11,
            ["firearm_burst"] = SoundID.Item41,
            ["firearm_clockwork"] = SoundID.Item31,
            ["shotgun_heavy"] = SoundID.Item36,
            ["shotgun_tactical"] = SoundID.Item38,
            ["sniper_heavy"] = SoundID.Item40,
            ["dart_pistol"] = SoundID.Item98,
            ["dart_rifle"] = SoundID.Item99,
            ["nailgun"] = SoundID.Item108,
            ["launcher_rocket"] = SoundID.Item42,
            ["launcher_grenade"] = SoundID.Item14,
            ["flame_stream"] = SoundID.Item34,

            // Energy / magic.
            ["laser_short"] = SoundID.Item12,
            ["laser_heavy"] = SoundID.Item33,
            ["laser_machine"] = SoundID.Item91,
            ["laser_space"] = SoundID.Item157,
            ["laser_zap"] = SoundID.Item158,
            ["magic_bolt"] = SoundID.Item20,
            ["magic_star"] = SoundID.Item9,
            ["magic_gem"] = SoundID.Item43,
            ["magic_water"] = SoundID.Item21,
            ["magic_frost"] = SoundID.Item28,
            ["magic_harp"] = SoundID.Item26,
            ["magic_stream"] = SoundID.Item13,
            ["magic_phase"] = SoundID.Item15,
            ["magic_shadow"] = SoundID.Item72,
            ["magic_inferno"] = SoundID.Item73,
            ["magic_earth"] = SoundID.Item69,
            ["magic_wind_vortex"] = SoundID.Item84,
            ["magic_bubble"] = SoundID.Item85,
            ["magic_meteor"] = SoundID.Item88,
            ["magic_toxic"] = SoundID.Item106,
            ["magic_crystal_burst"] = SoundID.Item109,
            ["magic_void"] = SoundID.Item117,
            ["magic_spectral"] = SoundID.Item124,
            ["magic_electric"] = SoundID.Item93,
            ["magic_cosmic"] = SoundID.Item117,

            // Summon / utility.
            ["summon_general"] = SoundID.Item44,
            ["summon_sentry"] = SoundID.Item46,
            ["summon_insect"] = SoundID.Item76,
            ["summon_fiery"] = SoundID.Item77,
            ["summon_portal"] = SoundID.Item78,
            ["summon_mechanical"] = SoundID.Item82,
            ["summon_skittering"] = SoundID.Item83,
            ["summon_lightning"] = SoundID.Item123,
            ["potion_use"] = SoundID.Item4,

            // Impact roles.
            ["impact_soft"] = SoundID.Item10,
            ["impact_blade"] = SoundID.Item10,
            ["impact_heavy"] = SoundID.Item37,
            ["impact_harpoon"] = SoundID.Item10,
            ["impact_nail"] = SoundID.Item108,
            ["impact_explosion"] = SoundID.Item62,
            ["impact_rocket"] = SoundID.Item14,
            ["impact_electric"] = SoundID.Item94,
            ["impact_fire"] = SoundID.Item34,
            ["impact_frost"] = SoundID.Item51,
            ["impact_star"] = SoundID.Item105,
            ["impact_slime"] = SoundID.Item17,
            ["impact_crystal"] = SoundID.Item110,
            ["impact_shadow"] = SoundID.Item103,
            ["impact_earth"] = SoundID.Item70,
            ["impact_inferno"] = SoundID.Item74,
            ["impact_bubble"] = SoundID.Item54,
            ["impact_meteor"] = SoundID.Item89,
            ["impact_toxic"] = SoundID.Item107,
            ["impact_water"] = SoundID.Item21,
            ["impact_nature"] = SoundID.Item17,
            ["impact_void"] = SoundID.Item113,
            ["impact_heal"] = SoundID.Item4,
            ["impact_creature_meow"] = SoundID.Item57,
            ["impact_laser"] = SoundID.Item33,
            ["impact_magic"] = SoundID.Item20,
            ["impact_summon"] = SoundID.Item44,
            ["impact_wind_vortex"] = SoundID.Item84,
            ["impact_spectral"] = SoundID.Item124,
            ["impact_portal"] = SoundID.Item78,
            ["impact_insect"] = SoundID.Item97,
            ["impact_construct"] = SoundID.Item46,
        };

    public static int BuiltInCatalogCount => BuiltInCatalog.Count;

    public static bool IsBuiltInCatalogId(string? catalogId)
        => !string.IsNullOrWhiteSpace(catalogId) && BuiltInCatalog.ContainsKey(catalogId);

    public static SoundStyle ForUse(
        string runtimeFamily,
        string delivery,
        string effect,
        float authoredVolume,
        float authoredPitch,
        float authoredPitchVariance,
        string catalogId = "",
        string catalogPath = "",
        string catalogSource = "")
    {
        SoundStyle style;
        if (!TryResolveBuiltIn(catalogId, out style) &&
            !InfiniFutureSoundCatalog.TryResolveOneShot(
                InfiniFutureSoundCatalogRequest.Use(
                    runtimeFamily,
                    effect,
                    catalogId,
                    catalogPath,
                    catalogSource),
                out style))
        {
            style = FallbackUse(runtimeFamily, delivery, effect);
        }
        return Apply(style, authoredVolume, authoredPitch, authoredPitchVariance, 1.00f, 0f);
    }

    public static SoundStyle ForImpact(
        string effect,
        int onHitCode,
        int effectCode,
        float authoredVolume,
        float authoredPitch,
        float authoredPitchVariance,
        string catalogId = "",
        string catalogPath = "",
        string catalogSource = "")
    {
        SoundStyle style;
        if (!TryResolveBuiltIn(catalogId, out style) &&
            !InfiniFutureSoundCatalog.TryResolveOneShot(
                InfiniFutureSoundCatalogRequest.Impact(
                    effect,
                    onHitCode,
                    effectCode,
                    catalogId,
                    catalogPath,
                    catalogSource),
                out style))
        {
            style = FallbackImpact(effect, onHitCode, effectCode);
        }
        return Apply(style, authoredVolume, authoredPitch, authoredPitchVariance, 1.00f, 0f);
    }

    public static SoundStyle ForVfxCue(
        string runtimeFamily,
        string effect,
        float authoredVolume,
        float authoredPitch,
        float authoredPitchVariance,
        int seed,
        bool impact,
        string catalogId = "",
        string catalogPath = "",
        string catalogSource = "")
    {
        SoundStyle style;
        if (!TryResolveBuiltIn(catalogId, out style) &&
            !InfiniFutureSoundCatalog.TryResolveOneShot(
                InfiniFutureSoundCatalogRequest.VfxCue(
                    runtimeFamily,
                    effect,
                    impact,
                    catalogId,
                    catalogPath,
                    catalogSource),
                out style))
        {
            style = impact ? FallbackImpact(effect, 0, 0) : FallbackUse(runtimeFamily, "", effect);
        }
        float jitter = ((seed % 11) - 5) * 0.012f;
        return Apply(style, authoredVolume, authoredPitch, authoredPitchVariance, impact ? 0.62f : 0.48f, jitter);
    }

    private static bool TryResolveBuiltIn(string? catalogId, out SoundStyle style)
        => BuiltInCatalog.TryGetValue(catalogId ?? "", out style);

    private static SoundStyle FallbackUse(string runtimeFamily, string delivery, string effect)
    {
        string family = runtimeFamily ?? "";
        string carrier = delivery ?? "";
        string effectName = effect ?? "";
        if (family == "overhead_barrage")
        {
            if (carrier == "swing") return SoundID.Item1;
            if (carrier == "shoot") return SoundID.Item5;
            if (carrier == "throw") return SoundID.Item1;
            if (carrier == "cast") family = "cast";
        }
        if (family == "cast")
        {
            return effectName switch
            {
                "electric" => SoundID.Item93,
                "star" or "holy" => SoundID.Item9,
                "lunar" => SoundID.Item117,
                "flame" => SoundID.Item73,
                "frost" => SoundID.Item28,
                "shadow" => SoundID.Item72,
                "poison" => SoundID.Item106,
                "slime" => SoundID.Item85,
                "sand" => SoundID.Item69,
                _ => SoundID.Item20,
            };
        }

        return family switch
        {
            "thrust" => SoundID.Item71,
            "returning" => SoundID.Item7,
            "flail" => SoundID.Item10,
            "whip" => SoundID.Item152,
            "shoot" => SoundID.Item11,
            "summon" => SoundID.Item44,
            _ => SoundID.Item1,
        };
    }

    private static SoundStyle FallbackImpact(string effect, int onHitCode, int effectCode)
    {
        SoundStyle codeStyle = StyleFromCodes(onHitCode, effectCode);
        if (!codeStyle.Equals(default(SoundStyle)))
            return codeStyle;

        return (effect ?? "") switch
        {
            "electric" => SoundID.Item94,
            "star" or "lunar" or "holy" => SoundID.Item105,
            "flame" => SoundID.Item34,
            "frost" => SoundID.Item51,
            "shadow" => SoundID.Item103,
            "poison" => SoundID.Item107,
            "slime" or "honey" => SoundID.Item17,
            "sand" => SoundID.Item70,
            "leaf" => SoundID.Item17,
            "heal" => SoundID.Item4,
            _ => SoundID.Item10,
        };
    }

    private static SoundStyle StyleFromCodes(int onHitCode, int effectCode)
    {
        return onHitCode switch
        {
            4 => SoundID.Item34,
            5 => SoundID.Item51,
            6 => SoundID.Item107,
            7 => SoundID.Item103,
            8 => SoundID.Item105,
            10 or 14 or 15 => SoundID.Item62,
            16 => SoundID.Item94,
            17 or 18 => SoundID.Item4,
            _ => effectCode switch
            {
                1 => SoundID.Item94,
                3 => SoundID.Item105,
                4 => SoundID.Item34,
                5 => SoundID.Item51,
                7 => SoundID.Item103,
                8 => SoundID.Item107,
                13 => SoundID.Item4,
                14 => SoundID.Item62,
                15 => SoundID.Item51,
                _ => default,
            },
        };
    }

    private static SoundStyle Apply(
        SoundStyle style,
        float authoredVolume,
        float authoredPitch,
        float authoredPitchVariance,
        float volumeScale,
        float pitchJitter)
    {
        float authoredVolumeScale = authoredVolume <= 0f ? 0.85f : Math.Clamp(authoredVolume, 0.05f, 1f);
        float pitch = Math.Clamp(style.Pitch + authoredPitch + pitchJitter, -0.9f, 0.9f);
        float safeVariance = Math.Clamp(Math.Max(style.PitchVariance, authoredPitchVariance), 0f, 0.6f);
        safeVariance = Math.Min(safeVariance, 2f * Math.Max(0f, 0.9f - Math.Abs(pitch)));
        return style with
        {
            Volume = Math.Clamp(style.Volume * authoredVolumeScale * volumeScale, 0.04f, 1f),
            Pitch = pitch,
            PitchVariance = safeVariance,
        };
    }

}
