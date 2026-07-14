from __future__ import annotations

from typing import Any

from infini_local.core.runtime_overhead_barrage_policy import normalize_overhead_barrage_family

# This module is the only owner of permissive LLM-input vocabulary. Aliases are
# accepted at the authoring boundary only; runtimeFamily itself remains strict.
def normalize_authoring_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


MOVEMENT_ALIASES = {
    "rain": "gravity_arc", "fall": "gravity_arc", "falling": "gravity_arc", "falling_projectile": "gravity_arc",
    "projectile_rain": "gravity_arc", "skyfall": "gravity_arc", "meteor": "gravity_arc",
    "arc": "gravity_arc", "lob": "gravity_arc", "lobbed": "gravity_arc", "grenade_arc": "gravity_arc",
    "homing": "slow_homing", "seeking": "slow_homing", "guided": "slow_homing", "tracking": "slow_homing",
    "return": "returning_glaive", "returning": "returning_glaive", "returning_throw": "returning_glaive",
    "glaive_return": "returning_glaive", "chakram": "boomerang", "boomerang_return": "boomerang",
    "wave": "expanding_wave", "shockwave": "expanding_wave", "ring": "expanding_wave",
    "beam": "phase", "laser": "phase", "ray": "phase", "hitscan": "phase",
    "missile": "proximity_missile", "rocket": "proximity_missile", "orb": "vortex_orb",
    "flail": "flail_tether", "chain_flail": "flail_tether", "mace": "flail_tether", "anchor": "flail_tether",
    "yoyo": "yoyo_hover", "yo_yo": "yoyo_hover", "whip": "whip_lash", "lash": "whip_lash",
}

EFFECT_ALIASES = {
    "dust": "smoke",
    "fire": "flame", "burn": "flame", "ember": "flame", "lava": "flame", "magma": "flame",
    "ice": "frost", "cold": "frost", "snow": "frost", "frostburn": "frost",
    "lightning": "electric", "shock": "electric", "thunder": "electric", "storm": "electric",
    "venom": "poison", "toxic": "poison", "acid": "poison", "ichor": "poison",
    "dark": "shadow", "void": "shadow", "grave": "shadow", "shadowflame": "shadow",
    "nature": "leaf", "plant": "leaf", "spore": "leaf", "water": "slime", "goo": "slime", "gel": "slime",
    "radiant": "holy", "light": "holy", "solar": "holy", "smog": "smoke", "ash": "smoke",
}

ONHIT_ALIASES = {
    "fire": "burn", "on_fire": "burn", "ignite": "burn", "ice": "frostburn", "freeze": "frostburn", "chill": "frostburn",
    "venom": "poison", "toxic": "poison", "acid": "poison",
    "electric": "lightning_arc", "electrified": "lightning_arc", "shock": "lightning_arc", "zap": "lightning_arc",
    "blood": "bleed", "bleeding": "bleed", "explode": "burst", "explosion": "burst", "nova": "burst",
    "fragment": "split", "fragments": "split", "shards": "split",
    "star": "starburst", "stars": "starburst",
    "heal": "lifesteal", "lifesteal": "lifesteal", "life_steal": "lifesteal",
    "slow": "slow", "slowed": "slow",
}

DELIVERIES = frozenset({"none", "swing", "thrust", "spear", "shoot", "cast", "throw", "summon", "flail", "yoyo", "whip"})
DELIVERY_ALIASES = {
    "slash": "swing", "melee_arc": "swing", "blade_arc": "swing", "sword": "swing", "axe": "swing", "hammer": "swing", "club": "swing",
    "stab": "thrust", "rapier": "thrust", "shortsword": "thrust", "short_sword": "thrust", "held_thrust": "thrust", "spear_thrust": "thrust",
    "polearm": "thrust", "lance": "thrust", "pike": "thrust", "trident": "thrust", "halberd": "thrust", "naginata": "thrust",
    "ranged": "shoot", "bow": "shoot", "repeater": "shoot", "gun": "shoot", "launcher": "shoot", "crossbow": "shoot", "blowgun": "shoot",
    "magic": "cast", "spell": "cast", "staff": "cast", "wand": "cast", "rod": "cast", "book": "cast", "spellbook": "cast",
    "thrown": "throw", "knife": "throw", "dart": "throw", "grenade": "throw",
    "boomerang": "throw", "chakram": "throw", "glaive_throw": "throw", "returning_throw": "throw",
    "flail": "flail", "chain_flail": "flail", "ball_and_chain": "flail", "mace": "flail", "anchor": "flail",
    "yoyo": "yoyo", "yo_yo": "yoyo", "whip": "whip", "lash": "whip",
    "minion": "summon", "sentry": "summon", "summon_projectile": "summon",
}

_AUTHORING_ALIASES_BY_FIELD = {
    "movement": MOVEMENT_ALIASES,
    "effect": EFFECT_ALIASES,
    "onHit": ONHIT_ALIASES,
    "delivery": DELIVERY_ALIASES,
}


def normalize_authoring_enum(value: Any, field: str) -> str:
    token = normalize_authoring_token(value)
    if field == "runtimeFamily":
        return normalize_overhead_barrage_family(token)
    aliases = _AUTHORING_ALIASES_BY_FIELD.get(field)
    return aliases.get(token, token) if aliases is not None else token


__all__ = [
    "DELIVERIES",
    "normalize_authoring_enum", "normalize_authoring_token",
]
