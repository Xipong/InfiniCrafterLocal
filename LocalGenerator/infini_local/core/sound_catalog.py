from __future__ import annotations

from typing import Any

# Canonical, exact authoring vocabulary for Terraria's built-in SoundID palette.
# This is intentionally a sizeable acoustic catalog, not a weapon-name alias table:
# every id describes how the sound feels/acts, and the LLM selects it explicitly.
SOUND_CATALOG_CONTRACT_VERSION = "infini.terraria-sound-catalog.v8"
SOUND_CATALOG_SOURCE = "terraria_vanilla"

USE_SOUND_GROUPS: dict[str, tuple[str, ...]] = {
    "melee_and_thrown": (
        "melee_swing", "melee_thrust", "melee_heavy", "melee_energy_slash",
        "melee_prismatic_shred", "throw_light", "returning_boomerang", "flail_chain",
        "yoyo_launch", "whip_lash", "insect_swarm", "creature_meow",
    ),
    "ranged": (
        "bow_release", "bow_volley", "firearm_light", "firearm_burst",
        "firearm_clockwork", "shotgun_heavy", "shotgun_tactical", "sniper_heavy",
        "dart_pistol", "dart_rifle", "nailgun", "launcher_rocket",
        "launcher_grenade", "flame_stream",
    ),
    "energy_and_magic": (
        "laser_short", "laser_heavy", "laser_machine", "laser_space", "laser_zap",
        "magic_bolt", "magic_star", "magic_gem", "magic_water", "magic_frost",
        "magic_harp", "magic_stream", "magic_phase", "magic_shadow",
        "magic_inferno", "magic_earth", "magic_wind_vortex", "magic_bubble",
        "magic_meteor", "magic_toxic", "magic_crystal_burst", "magic_void",
        "magic_spectral", "magic_electric", "magic_cosmic",
    ),
    "summon_and_utility": (
        "summon_general", "summon_sentry", "summon_insect", "summon_fiery",
        "summon_portal", "summon_mechanical", "summon_skittering", "summon_lightning",
        "potion_use",
    ),
}

IMPACT_SOUND_GROUPS: dict[str, tuple[str, ...]] = {
    "physical": (
        "impact_soft", "impact_blade", "impact_heavy", "impact_harpoon",
        "impact_nail",
    ),
    "elemental": (
        "impact_explosion", "impact_rocket", "impact_electric", "impact_fire",
        "impact_frost", "impact_star", "impact_slime", "impact_crystal",
        "impact_shadow", "impact_earth", "impact_inferno", "impact_bubble",
        "impact_meteor", "impact_toxic", "impact_water", "impact_nature",
        "impact_void",
    ),
    "special": (
        "impact_heal", "impact_creature_meow", "impact_laser", "impact_magic",
        "impact_summon", "impact_wind_vortex", "impact_spectral", "impact_portal",
        "impact_insect", "impact_construct",
    ),
}

USE_SOUND_IDS = frozenset(x for group in USE_SOUND_GROUPS.values() for x in group)
IMPACT_SOUND_IDS = frozenset(x for group in IMPACT_SOUND_GROUPS.values() for x in group)
ALL_SOUND_IDS = USE_SOUND_IDS | IMPACT_SOUND_IDS

_FAMILY_USE_DEFAULT = {
    "swing": "melee_swing",
    "thrust": "melee_thrust",
    "returning": "returning_boomerang",
    "flail": "flail_chain",
    "yoyo": "yoyo_launch",
    "whip": "whip_lash",
    "shoot": "firearm_light",
    "cast": "magic_bolt",
    "beam": "laser_machine",
    "overhead_barrage": "throw_light",
    "throw": "throw_light",
    "summon": "summon_general",
    "sentry": "summon_sentry",
}

_CAST_EFFECT_USE_DEFAULT = {
    "electric": "magic_electric",
    "star": "magic_star",
    "lunar": "magic_cosmic",
    "holy": "magic_star",
    "flame": "magic_inferno",
    "frost": "magic_frost",
    "shadow": "magic_shadow",
    "poison": "magic_toxic",
    "slime": "magic_bubble",
    "sand": "magic_earth",
}

_ONHIT_IMPACT_DEFAULT = {
    "burn": "impact_fire",
    "frostburn": "impact_frost",
    "poison": "impact_toxic",
    "shadowflame": "impact_shadow",
    "bleed": "impact_blade",
    "starburst": "impact_star",
    "overhead_barrage": "impact_magic",
    "burst": "impact_explosion",
    "mini_missiles": "impact_rocket",
    "radial_beams": "impact_laser",
    "lightning_arc": "impact_electric",
    "heal": "impact_heal",
    "lifesteal": "impact_heal",
    "vortex_spawn": "impact_void",
    "blackhole": "impact_void",
    "spore_cloud": "impact_nature",
}

_EFFECT_IMPACT_DEFAULT = {
    "electric": "impact_electric",
    "star": "impact_star",
    "lunar": "impact_star",
    "holy": "impact_star",
    "flame": "impact_fire",
    "frost": "impact_frost",
    "shadow": "impact_shadow",
    "poison": "impact_toxic",
    "slime": "impact_slime",
    "honey": "impact_slime",
    "sand": "impact_earth",
    "leaf": "impact_nature",
    "heal": "impact_heal",
}


def normalize_sound_catalog_id(value: Any, *, impact: bool | None = None) -> str:
    """Normalize spelling only, then require an exact canonical acoustic id.

    No weapon names, prose keywords or fuzzy aliases are accepted here.
    """
    token = str(value or "").strip()
    allowed = IMPACT_SOUND_IDS if impact is True else USE_SOUND_IDS if impact is False else ALL_SOUND_IDS
    return token if token in allowed else ""


def default_use_sound_id(runtime_family: Any, effect: Any = "", delivery: Any = "") -> str:
    family = str(runtime_family or "").strip().lower()
    effect_name = str(effect or "").strip().lower()
    carrier = str(delivery or "").strip().lower().replace("-", "_").replace(" ", "_")
    if family == "charge_release":
        if carrier == "cast":
            return _CAST_EFFECT_USE_DEFAULT.get(effect_name, "magic_phase")
        if carrier == "throw":
            return "throw_light"
        return "bow_release"
    if family == "overhead_barrage":
        if carrier == "swing":
            return "melee_swing"
        if carrier == "shoot":
            return "bow_release"
        if carrier == "cast":
            return _CAST_EFFECT_USE_DEFAULT.get(effect_name, "magic_bolt")
        if carrier == "throw":
            return "throw_light"
    if family == "cast" and effect_name in _CAST_EFFECT_USE_DEFAULT:
        return _CAST_EFFECT_USE_DEFAULT[effect_name]
    return _FAMILY_USE_DEFAULT.get(family, "melee_swing")


def default_impact_sound_id(on_hit: Any, effect: Any = "") -> str:
    on_hit_name = str(on_hit or "").strip().lower()
    effect_name = str(effect or "").strip().lower()
    return _ONHIT_IMPACT_DEFAULT.get(on_hit_name) or _EFFECT_IMPACT_DEFAULT.get(effect_name) or "impact_soft"


def sound_catalog_card_for_llm() -> dict[str, Any]:
    # Pipe-delimited groups keep the full 92-id palette visible without copying the
    # same four audio fields into every attack-function card.  These fields may be
    # added to any primary attack call and are validated exactly by the compiler.
    return {
        "contractVersion": SOUND_CATALOG_CONTRACT_VERSION,
        "catalogSource": SOUND_CATALOG_SOURCE,
        "selectionRule": "Choose the closest acoustic role, not a generic default; exact ids only; no names/prose/taxonomy inference.",
        "placement": "Put audio fields in params of the primary attack call.",
        "authoringFields": {
            "soundUseCatalogId": "use id; attack",
            "soundImpactCatalogId": "impact id; attack",
            "soundVolume": "0.05..1.0 native-volume multiplier",
            "soundPitch": "-0.9..0.9 native-pitch offset",
            "soundPitchVariance": "0..0.6 minimum; native variance preserved",
        },
        "useCatalogIds": {name: "|".join(values) for name, values in USE_SOUND_GROUPS.items()},
        "impactCatalogIds": {name: "|".join(values) for name, values in IMPACT_SOUND_GROUPS.items()},
    }


__all__ = [
    "SOUND_CATALOG_CONTRACT_VERSION", "SOUND_CATALOG_SOURCE",
    "USE_SOUND_GROUPS", "IMPACT_SOUND_GROUPS", "USE_SOUND_IDS", "IMPACT_SOUND_IDS", "ALL_SOUND_IDS",
    "normalize_sound_catalog_id", "default_use_sound_id", "default_impact_sound_id",
    "sound_catalog_card_for_llm",
]
