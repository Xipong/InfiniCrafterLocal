from __future__ import annotations

from typing import Final


# Canonical serialized executor vocabulary. Names and numeric opcodes cross
# Python -> JSON -> C# and therefore have one owner here.
MOVEMENT_CODE: Final[dict[str, int]] = {
    "straight": 0,
    "slow_homing": 1,
    "gravity_arc": 2,
    "drift": 3,
    "orbit": 4,
    "boomerang": 5,
    "bounce": 6,
    "sine_homing": 7,
    "phase": 8,
    "accelerate": 9,
    "spiral": 10,
    "vortex_orb": 11,
    "blackhole_pull": 12,
    "proximity_missile": 13,
    "returning_glaive": 14,
    "expanding_wave": 15,
    "flail_tether": 16,
    "yoyo_hover": 17,
    "whip_lash": 18,
}

EFFECT_CODE: Final[dict[str, int]] = {
    "none": 0,
    "electric": 1,
    "slime": 2,
    "star": 3,
    "flame": 4,
    "frost": 5,
    "leaf": 6,
    "shadow": 7,
    "poison": 8,
    "blood": 9,
    "honey": 10,
    "sand": 11,
    "lunar": 12,
    "heal": 13,
    "holy": 14,
    "smoke": 15,
}

ONHIT_CODE: Final[dict[str, int]] = {
    "none": 0,
    "burst": 1,
    "split": 2,
    "chain": 3,
    "burn": 4,
    "frostburn": 5,
    "poison": 6,
    "shadowflame": 7,
    "starburst": 8,
    "bleed": 9,
    "aura_pulse": 10,
    "spore_cloud": 11,
    "mini_missiles": 12,
    "vortex_spawn": 13,
    "blackhole": 14,
    "radial_beams": 15,
    "lightning_arc": 16,
    "lifesteal": 17,
    "overhead_barrage": 18,
    "slow": 19,
}

MOVEMENTS: Final[frozenset[str]] = frozenset(MOVEMENT_CODE)
EFFECTS: Final[frozenset[str]] = frozenset(EFFECT_CODE)
ONHITS: Final[frozenset[str]] = frozenset(ONHIT_CODE)


__all__ = [
    "EFFECTS",
    "EFFECT_CODE",
    "MOVEMENTS",
    "MOVEMENT_CODE",
    "ONHITS",
    "ONHIT_CODE",
]
