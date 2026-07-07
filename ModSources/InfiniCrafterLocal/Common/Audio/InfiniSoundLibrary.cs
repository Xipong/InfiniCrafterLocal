#nullable enable
using System;
using Terraria.Audio;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.Audio;

/// <summary>
/// Vanilla SoundID catalog/fallback for generated items.
///
/// v0.4.193 keeps expanding the stock selector with more Terraria-authored item
/// sounds, but keeps the same philosophy as v0.4.189: no fixed external
/// sound pack and no client-side classification of a future huge catalog.
/// The future embedding catalog seam remains explicit-only.
///
/// Notes for the important vanilla roles used here:
/// - Item1: generic swung weapons/tools/consumables.
/// - Item5: bows/repeaters.
/// - Item7: boomerangs.
/// - Item10: harpoon/golem fist/strong launched hit.
/// - Item11: generic guns / magic guns / launchers.
/// - Item12/33/91/157/158: laser / space-gun / zapinator families.
/// - Item20/21/28/43/72/73/84/88/117: distinct magic staff/projectile families.
/// - Item36/38/40/41/61/63/64/98/99/108: shotgun/sniper/handgun/launcher/dart/nail variants.
/// - Item44/46/76/77/78/82/83: summon/sentry staff variants.
/// - Item116/152/169: solar eruption / whips / Zenith.
/// </summary>
public static class InfiniSoundLibrary
{
    public const string ContractVersion = "infini.vanilla-sound-catalog.v6";

    public static readonly string[] KnownProfiles = new[]
    {
        "soft", "swing", "blade", "cut", "heavy", "metal", "mechanical",
        "gun", "shotgun", "sniper", "bow", "launcher", "rocket", "laser",
        "beam", "dart", "nail", "blowpipe", "boomerang", "flail", "whip",
        "magic", "summon", "sentry", "electric", "fire", "ice", "water",
        "star", "lunar", "solar", "nebula", "crystal", "glass", "slime",
        "honey", "heal", "potion", "explosion", "shadow", "poison", "toxic",
        "leaf", "nature", "sand", "earth", "meteor", "bubble", "harp",
        "sickle", "typhoon", "portal", "bee", "bee_swarm", "starfury", "enchanted_sword",
        "nights_edge", "muramasa", "water_bolt", "demon_scythe", "flower_of_fire",
        "space_gun", "last_prism", "phantasm", "vortex_beater", "stardust_dragon",
        "terra", "zenith", "spear", "lance", "dagger", "javelin", "knife", "throwing", "anchor", "flairon", "flamethrower", "rainbow", "coin", "book", "scroll"
    };

    public static SoundStyle ForUse(string profile, string runtimeFamily, string effect, float authoredVolume, float authoredPitch, string catalogId = "", string catalogPath = "", string searchQuery = "", string catalogSource = "")
    {
        string text = Lower($"{profile} {runtimeFamily} {effect}");
        SoundStyle style = InfiniFutureSoundCatalog.TryResolveOneShot(InfiniFutureSoundCatalogRequest.Use(string.IsNullOrWhiteSpace(searchQuery) ? text : searchQuery, runtimeFamily, effect, catalogId, catalogPath, catalogSource), out SoundStyle catalogStyle)
            ? catalogStyle
            : BaseStyle(text, runtimeFamily, effect, impact: false, onHitCode: 0, effectCode: 0);
        return Apply(style, text, authoredVolume, authoredPitch, volumeScale: 1.00f, pitchJitter: 0f, impact: false);
    }

    public static SoundStyle ForImpact(string profile, string effect, int onHitCode, int effectCode, float authoredVolume, float authoredPitch, string catalogId = "", string catalogPath = "", string searchQuery = "", string catalogSource = "")
    {
        string text = Lower($"{profile} {effect}");
        SoundStyle style = InfiniFutureSoundCatalog.TryResolveOneShot(InfiniFutureSoundCatalogRequest.Impact(string.IsNullOrWhiteSpace(searchQuery) ? text : searchQuery, effect, onHitCode, effectCode, catalogId, catalogPath, catalogSource), out SoundStyle catalogStyle)
            ? catalogStyle
            : BaseStyle(text, runtimeFamily: "", effect, impact: true, onHitCode, effectCode);
        return Apply(style, text, authoredVolume, authoredPitch, volumeScale: 1.00f, pitchJitter: 0f, impact: true);
    }

    public static SoundStyle ForVfxCue(string profile, string runtimeFamily, string effect, float authoredVolume, float authoredPitch, int seed, bool impact, string catalogId = "", string catalogPath = "", string searchQuery = "", string catalogSource = "")
    {
        string text = Lower($"{profile} {runtimeFamily} {effect}");
        SoundStyle style = InfiniFutureSoundCatalog.TryResolveOneShot(InfiniFutureSoundCatalogRequest.VfxCue(string.IsNullOrWhiteSpace(searchQuery) ? text : searchQuery, runtimeFamily, effect, impact, catalogId, catalogPath, catalogSource), out SoundStyle catalogStyle)
            ? catalogStyle
            : BaseStyle(text, runtimeFamily, effect, impact, onHitCode: 0, effectCode: 0);
        float jitter = ((seed % 11) - 5) * 0.012f;
        return Apply(style, text, authoredVolume, authoredPitch, volumeScale: impact ? 0.62f : 0.48f, pitchJitter: jitter, impact);
    }

    private static SoundStyle BaseStyle(string text, string runtimeFamily, string effect, bool impact, int onHitCode, int effectCode)
    {
        string t = Lower(text);
        string d = Lower(runtimeFamily);
        string e = Lower(effect);
        bool authored = HasMeaningfulProfile(t);

        if (authored)
        {
            SoundStyle authoredStyle = StyleFromText(t, d, e, impact);
            if (!authoredStyle.Equals(default(SoundStyle)))
                return authoredStyle;
        }

        SoundStyle codeStyle = StyleFromCodes(onHitCode, effectCode);
        if (!codeStyle.Equals(default(SoundStyle)))
            return codeStyle;

        return StyleFromText(t, d, e, impact);
    }

    private static SoundStyle StyleFromText(string text, string runtimeFamily, string effect, bool impact)
    {
        string t = Lower($"{text} {runtimeFamily} {effect}");

        // Very specific/high-identity generated fantasies first. These are still
        // presentation-only: they do not alter delivery/runtime/damage.
        if (HasAny(t, "zenith")) return SoundID.Item169;
        if (HasAny(t, "bee keeper", "bee swarm", "beenade", "bee projectile")) return SoundID.Item97;
        if (HasAny(t, "starfury", "falling star", "starfall", "star wrath")) return impact ? SoundID.Item105 : SoundID.Item9;
        if (HasAny(t, "enchanted sword", "sword beam", "beam sword")) return SoundID.Item60;
        if (HasAny(t, "muramasa")) return SoundID.Item1;
        if (HasAny(t, "night's edge", "nights edge", "night edge", "dark slash")) return SoundID.Item1;
        if (HasAny(t, "solar eruption", "solar whip", "solar flail")) return SoundID.Item116;
        if (HasAny(t, "whip", "lash")) return SoundID.Item152;
        if (HasAny(t, "terra blade", "terrablade", "terra beam")) return SoundID.Item60;
        if (HasAny(t, "star wrath")) return SoundID.Item105;
        if (HasAny(t, "meowmere", "meow", "cat projectile")) return impact ? SoundID.Item57 : SoundID.Item58;

        SoundStyle ranged = StyleFromRangedText(t, impact);
        if (!ranged.Equals(default(SoundStyle))) return ranged;

        SoundStyle magic = StyleFromMagicText(t, impact);
        if (!magic.Equals(default(SoundStyle))) return magic;

        SoundStyle summon = StyleFromSummonText(t, impact);
        if (!summon.Equals(default(SoundStyle))) return summon;

        SoundStyle melee = StyleFromMeleeText(t, impact);
        if (!melee.Equals(default(SoundStyle))) return melee;

        SoundStyle material = StyleFromMaterialOrEffectText(t, impact);
        if (!material.Equals(default(SoundStyle))) return material;

        if (HasAny(t, "boomerang", "returning")) return SoundID.Item7;
        if (HasAny(t, "flail", "chain", "harpoon", "golem fist", "ko cannon", "piranha")) return impact ? SoundID.Item10 : SoundID.Item10;
        if (HasAny(t, "sickle", "scythe")) return SoundID.Item71;
        if (HasAny(t, "cut", "blood", "blade", "slash", "knife", "sword")) return impact ? SoundID.Item10 : SoundID.Item1;
        if (HasAny(t, "leaf", "nature", "wood", "sand", "cloth", "soft")) return impact ? SoundID.Item10 : SoundID.Item1;

        return impact ? SoundID.Item10 : SoundID.Item1;
    }

    private static SoundStyle StyleFromRangedText(string t, bool impact)
    {
        if (HasAny(t, "phantasm", "multi arrow", "arrow volley")) return SoundID.Item102;
        if (HasAny(t, "vortex beater")) return SoundID.Item11;
        if (HasAny(t, "blood rain bow", "hellwing bow")) return SoundID.Item5;
        if (HasAny(t, "shotgun", "boomstick", "quad barrel", "quad-barrel", "onyx blaster")) return SoundID.Item36;
        if (HasAny(t, "tactical shotgun")) return SoundID.Item38;
        if (HasAny(t, "sniper", "sdmg", "s.d.m.g")) return SoundID.Item40;
        if (HasAny(t, "chain gun", "chaingun", "gatligator", "handgun", "phoenix blaster", "revolver", "venus magnum")) return SoundID.Item41;
        if (HasAny(t, "clockwork")) return SoundID.Item31;
        if (HasAny(t, "dart pistol")) return SoundID.Item98;
        if (HasAny(t, "dart rifle")) return SoundID.Item99;
        if (HasAny(t, "nail gun", "nailgun")) return SoundID.Item108;
        if (HasAny(t, "blowpipe")) return SoundID.Item63;
        if (HasAny(t, "blowgun")) return SoundID.Item64;
        if (HasAny(t, "xenopopper")) return impact ? SoundID.Item96 : SoundID.Item95;
        if (HasAny(t, "bees knees", "bee bow", "bee arrow")) return SoundID.Item97;
        if (HasAny(t, "shadowflame bow", "aerial bane")) return SoundID.Item102;
        if (HasAny(t, "pulse bow", "charged blaster")) return SoundID.Item75;
        if (HasAny(t, "grenade launcher")) return impact ? SoundID.Item62 : SoundID.Item61;
        if (HasAny(t, "electrosphere")) return impact ? SoundID.Item94 : SoundID.Item92;
        if (HasAny(t, "rocket", "missile", "launcher")) return impact ? SoundID.Item14 : SoundID.Item42;
        if (HasAny(t, "gun", "firearm", "bullet", "rifle", "pistol", "shot")) return SoundID.Item11;
        if (HasAny(t, "bow", "arrow", "repeater", "crossbow")) return SoundID.Item5;
        return default;
    }

    private static SoundStyle StyleFromMagicText(string t, bool impact)
    {
        if (HasAny(t, "last prism")) return SoundID.Item13;
        if (HasAny(t, "demon scythe", "scythe spell")) return SoundID.Item71;
        if (HasAny(t, "flower of fire", "flower of frost", "flamelash", "cursed flame")) return SoundID.Item20;
        if (HasAny(t, "laser machinegun", "laser machine gun")) return SoundID.Item91;
        if (HasAny(t, "space gun")) return SoundID.Item157;
        if (HasAny(t, "zapinator")) return SoundID.Item158;
        if (HasAny(t, "laser", "heat ray", "laser rifle", "eye beam", "death laser")) return SoundID.Item12;
        if (HasAny(t, "water bolt")) return SoundID.Item21;
        if (HasAny(t, "magic missile", "crystal storm", "sky fracture", "star cannon")) return SoundID.Item9;
        if (HasAny(t, "gem staff", "amber staff", "amethyst staff", "diamond staff", "emerald staff", "ruby staff", "sapphire staff", "topaz staff", "poison staff", "venom staff", "thunder zapper", "spectre staff", "resonance scepter")) return SoundID.Item43;
        if (HasAny(t, "ice rod", "rainbow rod")) return SoundID.Item28;
        if (HasAny(t, "harp")) return SoundID.Item26;
        if (HasAny(t, "aqua scepter", "golden shower", "last prism")) return SoundID.Item13;
        if (HasAny(t, "phaseblade", "phasesaber", "medusa")) return SoundID.Item15;
        if (HasAny(t, "shadowbeam", "shadow beam")) return SoundID.Item72;
        if (HasAny(t, "inferno fork")) return impact ? SoundID.Item74 : SoundID.Item73;
        if (HasAny(t, "staff of earth", "earth staff")) return impact ? SoundID.Item70 : SoundID.Item69;
        if (HasAny(t, "razorblade typhoon", "typhoon")) return SoundID.Item84;
        if (HasAny(t, "bubble gun", "bubble")) return impact ? SoundID.Item54 : SoundID.Item85;
        if (HasAny(t, "meteor staff", "lunar flare", "meteor")) return impact ? SoundID.Item89 : SoundID.Item88;
        if (HasAny(t, "clinger staff")) return SoundID.Item100;
        if (HasAny(t, "crystal vile shard")) return SoundID.Item101;
        if (HasAny(t, "toxic flask")) return impact ? SoundID.Item107 : SoundID.Item106;
        if (HasAny(t, "crystal serpent")) return impact ? SoundID.Item110 : SoundID.Item109;
        if (HasAny(t, "toxikarp")) return SoundID.Item111;
        if (HasAny(t, "blood thorn", "deadly sphere")) return SoundID.Item113;
        if (HasAny(t, "nebula arcanum", "spirit flame")) return SoundID.Item117;
        if (HasAny(t, "phantasmal", "moon bolt")) return SoundID.Item124;
        if (HasAny(t, "magic", "cast", "arcane", "mana", "spell", "staff", "wand", "fireball", "flamelash", "cursed flame", "flower of fire", "flower of frost", "frost staff", "magnet sphere", "nebula blaze", "unholy trident")) return SoundID.Item20;
        return default;
    }

    private static SoundStyle StyleFromSummonText(string t, bool impact)
    {
        if (HasAny(t, "stardust dragon", "dragon staff", "growing minion")) return SoundID.Item44;
        if (HasAny(t, "stardust cell", "cell staff")) return SoundID.Item44;
        if (HasAny(t, "sanguine", "raven", "desert tiger", "xeno staff", "terraprisma")) return SoundID.Item44;
        if (HasAny(t, "hornet staff", "hornet")) return SoundID.Item76;
        if (HasAny(t, "imp staff", "imp")) return SoundID.Item77;
        if (HasAny(t, "queen spider", "frost hydra", "hydra", "sentry")) return SoundID.Item46;
        if (HasAny(t, "lunar portal", "rainbow crystal", "portal sentry")) return SoundID.Item78;
        if (HasAny(t, "optic staff", "nightglow", "optic")) return SoundID.Item82;
        if (HasAny(t, "spider staff", "spider")) return SoundID.Item83;
        if (HasAny(t, "phantasm dragon")) return SoundID.Item119;
        if (HasAny(t, "ice mist")) return SoundID.Item120;
        if (HasAny(t, "lightning orb")) return SoundID.Item121;
        if (HasAny(t, "lightning ritual")) return SoundID.Item123;
        if (HasAny(t, "summon", "minion", "familiar", "spirit", "pirate", "pygmy", "raven", "slime staff", "stardust", "tempest", "vampire frog", "xeno")) return SoundID.Item44;
        return default;
    }

    private static SoundStyle StyleFromMeleeText(string t, bool impact)
    {
        if (HasAny(t, "light disc", "bananarang", "thorn chakram", "combat wrench", "shroomerang", "enchanted boomerang")) return SoundID.Item7;
        if (HasAny(t, "flairon", "anchor", "chain guillotine", "dao of pow", "mace", "blue moon", "sunfury", "ball o hurt")) return SoundID.Item10;
        if (HasAny(t, "vampire knives", "shadowflame knife", "flying knife", "throwing knife", "dagger", "knife")) return impact ? SoundID.Item10 : SoundID.Item1;
        if (HasAny(t, "daybreak", "javelin", "spear", "lance", "trident", "pike", "glaive", "halberd")) return impact ? SoundID.Item10 : SoundID.Item1;
        if (HasAny(t, "katana", "rapier", "saber", "sabre", "shortsword", "broadsword", "greatsword")) return impact ? SoundID.Item10 : SoundID.Item1;
        return default;
    }

    private static SoundStyle StyleFromMaterialOrEffectText(string t, bool impact)
    {
        if (HasAny(t, "electric", "lightning", "spark", "tesla")) return impact ? SoundID.Item94 : SoundID.Item93;
        if (HasAny(t, "explosion", "explode", "bomb", "blast", "grenade")) return impact ? SoundID.Item62 : SoundID.Item14;
        if (HasAny(t, "fire", "flame", "lava", "ember", "molten", "flamethrower", "elf melter")) return SoundID.Item34;
        if (HasAny(t, "frost", "ice", "snow", "cold")) return impact ? SoundID.Item51 : SoundID.Item27;
        if (HasAny(t, "star", "stellar", "lunar", "holy", "cosmic")) return impact ? SoundID.Item105 : SoundID.Item9;
        if (HasAny(t, "slime", "honey", "sticky", "glob", "squish")) return SoundID.Item17;
        if (HasAny(t, "heal", "potion", "mend", "life")) return SoundID.Item4;
        if (HasAny(t, "metal", "mechanical", "gear", "clang", "chain")) return impact ? SoundID.Item37 : SoundID.Item37;
        if (HasAny(t, "crystal", "glass", "chime", "shard")) return impact ? SoundID.Item110 : SoundID.Item43;
        if (HasAny(t, "shadow", "spectral", "ghost", "void", "poison", "venom", "toxic")) return SoundID.Item103;
        if (HasAny(t, "earth", "stone", "rock", "boulder")) return impact ? SoundID.Item70 : SoundID.Item69;
        return default;
    }

    private static SoundStyle StyleFromCodes(int onHitCode, int effectCode)
    {
        return onHitCode switch
        {
            4 => SoundID.Item34,
            5 => SoundID.Item51,
            6 => SoundID.Item17,
            7 => SoundID.Item103,
            8 => SoundID.Item105,
            10 or 14 or 15 => SoundID.Item62,
            16 => SoundID.Item94,
            17 => SoundID.Item4,
            _ => effectCode switch
            {
                1 => SoundID.Item94,
                3 => SoundID.Item105,
                4 => SoundID.Item34,
                5 => SoundID.Item51,
                7 => SoundID.Item103,
                13 => SoundID.Item4,
                14 => SoundID.Item62,
                15 => SoundID.Item51,
                _ => default
            }
        };
    }

    private static SoundStyle Apply(SoundStyle style, string profileText, float authoredVolume, float authoredPitch, float volumeScale, float pitchJitter, bool impact)
    {
        float baseVolume = authoredVolume <= 0f ? 0.85f : authoredVolume;
        float profileVolume = ProfileVolumeScale(profileText, impact);
        float profilePitch = ProfilePitchOffset(profileText, impact);
        return style with
        {
            Volume = Math.Clamp(baseVolume * volumeScale * profileVolume, 0.04f, 1.25f),
            Pitch = Math.Clamp(authoredPitch + profilePitch + pitchJitter, -0.9f, 0.9f),
        };
    }

    private static float ProfileVolumeScale(string text, bool impact)
    {
        string t = Lower(text);
        if (HasAny(t, "explosion", "blast", "rocket", "shotgun", "sniper")) return impact ? 1.12f : 0.94f;
        if (HasAny(t, "heavy", "metal", "mechanical", "clang")) return impact ? 1.04f : 0.90f;
        if (HasAny(t, "soft", "cloth", "leaf", "sand", "heal")) return impact ? 0.72f : 0.70f;
        if (HasAny(t, "crystal", "glass", "chime", "star", "lunar")) return impact ? 0.86f : 0.78f;
        if (HasAny(t, "whip", "laser", "beam")) return impact ? 0.92f : 0.82f;
        return 1.0f;
    }

    private static float ProfilePitchOffset(string text, bool impact)
    {
        string t = Lower(text);
        if (HasAny(t, "crystal", "glass", "chime", "star", "lunar", "electric", "laser", "beam")) return impact ? 0.12f : 0.08f;
        if (HasAny(t, "heavy", "metal", "mechanical", "explosion", "blast", "shotgun", "sniper")) return impact ? -0.10f : -0.06f;
        if (HasAny(t, "slime", "honey", "soft", "leaf", "sand")) return -0.04f;
        if (HasAny(t, "heal", "potion")) return 0.05f;
        return 0f;
    }

    private static bool HasMeaningfulProfile(string text)
    {
        string t = Lower(text);
        foreach (string profile in KnownProfiles)
        {
            if (profile == "soft") continue;
            if (t.Contains(profile, StringComparison.OrdinalIgnoreCase))
                return true;
        }
        return false;
    }

    private static bool HasAny(string text, params string[] needles)
    {
        foreach (string needle in needles)
        {
            if (text.Contains(needle, StringComparison.OrdinalIgnoreCase))
                return true;
        }
        return false;
    }

    private static string Lower(string? value) => (value ?? "").Trim().ToLowerInvariant();
}
