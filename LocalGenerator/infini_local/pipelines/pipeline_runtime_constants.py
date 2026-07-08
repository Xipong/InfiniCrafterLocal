from __future__ import annotations

import re

from infini_local.core.env_utils import env_bool, env_int, env_str

# AGENT MAP: runtime/prompt constants used by legacy pipeline_support and split
# combine/parent-context modules. Keep gameplay logic out of this module.

PALETTES = {
    "wood": ["brown", "tan", "dark_brown"],
    "wire": ["dark_gray", "yellow"],
    "electric": ["yellow", "cyan", "white"],
    "star": ["gold", "white", "blue"],
    "daybloom": ["yellow", "green", "white"],
    "flower": ["green", "yellow", "pink"],
    "slime": ["green", "cyan"],
    "shadow": ["purple", "black"],
    "fire": ["orange", "red", "yellow"],
    "ice": ["cyan", "white", "blue"],
    "technology": ["dark_gray", "cyan", "blue"],
    "accessory": ["silver", "gold", "blue"],
    "boots": ["brown", "silver", "blue"],
    "wings": ["white", "blue", "gold"],
    "shield": ["gray", "silver", "dark_gray"],
    "emblem": ["gold", "red", "white"],
    "charm": ["gold", "purple", "cyan"],
    "tool": ["brown", "gray", "silver"],
    "axe": ["brown", "steel", "green"],
    "drill": ["gray", "yellow", "blue"],
    "ammo": ["gray", "brass", "red"],
    "armor": ["gray", "silver", "blue"],
    "dirt": ["brown", "tan", "dark_brown"],
    "earth": ["brown", "green", "tan"],
    "stone": ["gray", "dark_gray", "white"],
    "sand": ["tan", "yellow", "white"],
    "block": ["gray", "brown", "tan"],
    "material": ["gray", "tan", "white"],
    "coin": ["gold", "silver", "copper"],
}


BAD_NAME_PATTERNS = [
    re.compile(r"^\s*infini(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*generated(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*combined(?:\s|$|[-_])", re.I),
    re.compile(r"\bhybrid\b", re.I),
]


# =============================================================================
# NAV: CATEGORY_AND_POLICY
# =============================================================================


# DEV-only accessory fallback builder lives in dev_fallback.py.


EFFECT_PRESENTATION = {
    "none": {"color": "white", "trail": "faint", "impact": "small_flash", "sound": "soft"},
    "dust": {"color": "white", "trail": "dust", "impact": "puff", "sound": "soft"},
    "electric": {"color": "cyan_yellow", "trail": "jagged_sparks", "impact": "electric_snap", "sound": "electric"},
    "slime": {"color": "green", "trail": "glob_droplets", "impact": "squish_burst", "sound": "slime"},
    "star": {"color": "white_gold", "trail": "sparkle", "impact": "starburst", "sound": "star"},
    "flame": {"color": "orange_red", "trail": "embers", "impact": "flame_pop", "sound": "fire"},
    "fire": {"color": "orange_red", "trail": "embers", "impact": "flame_pop", "sound": "fire"},
    "frost": {"color": "ice_blue", "trail": "snow_sparks", "impact": "ice_flash", "sound": "ice"},
    "leaf": {"color": "green_yellow", "trail": "leaf_specks", "impact": "petal_puff", "sound": "leaf"},
    "shadow": {"color": "purple_black", "trail": "dark_wisps", "impact": "shadow_flash", "sound": "shadow"},
    "poison": {"color": "toxic_green", "trail": "toxic_bubbles", "impact": "venom_splash", "sound": "poison"},
    "blood": {"color": "deep_red", "trail": "red_sparks", "impact": "cut_splatter", "sound": "cut"},
    "honey": {"color": "amber", "trail": "sticky_drops", "impact": "sticky_pop", "sound": "slime"},
    "sand": {"color": "sand_gold", "trail": "sand_grain", "impact": "sand_puff", "sound": "sand"},
    "heal": {"color": "green_pink", "trail": "soft_sparkle", "impact": "heal_pop", "sound": "heal"},
    "potion": {"color": "green_pink", "trail": "soft_sparkle", "impact": "potion_pop", "sound": "heal"},
    "holy": {"color": "white_gold", "trail": "sparkle", "impact": "soft_flash", "sound": "star"},
    "smoke": {"color": "gray", "trail": "smoke", "impact": "smoke_puff", "sound": "soft"},
    "lunar": {"color": "cyan_violet", "trail": "cosmic_sparkle", "impact": "lunar_burst", "sound": "star"},
    "crystal": {"color": "cyan_pink", "trail": "crystal_shards", "impact": "crystal_chime", "sound": "crystal"},
    "explosion": {"color": "orange_white", "trail": "smoke_embers", "impact": "explosion", "sound": "explosion"},
    "spectral": {"color": "pale_blue", "trail": "ghost_wisp", "impact": "spectral_flash", "sound": "shadow"},
    "mechanical": {"color": "steel_cyan", "trail": "metal_sparks", "impact": "metal_hit", "sound": "mechanical"},
}


LLM_RAW_TOKEN_MODE = env_str("INFINI_LLM_RAW_TOKEN_MODE", "compact").lower()
LLM_AMMO_REP_LIMIT = env_int("INFINI_LLM_AMMO_REP_LIMIT", 3)
# v0.4.51: LLM should see behavior words, not opaque vanilla aiStyle numbers.
# Keep numeric aiStyle internal/debug by default; expose only if explicitly requested.
LLM_INCLUDE_AISTYLE_RAW = env_bool("INFINI_LLM_INCLUDE_AISTYLE", False)
LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST = env_bool("INFINI_LLM_PROJECTILE_BEHAVIOR_DIGEST", True)

# Raw sections are still factual, but they should be compact: keep zeros/False because they
# are meaningful raw values, drop only null/empty strings/empty containers and duplicated
# sourceItem echo that is already present in itemRaw.
LLM_ITEM_RAW_KEYS = [
    "type", "name", "internalName", "sourceMod", "fullName",
    "damage", "damageClass", "damageClassFullName", "knockback", "crit",
    "useStyle", "useTime", "useAnimation", "reuseDelay", "autoReuse", "channel", "noMelee", "noUseGraphic", "useTurn",
    "rare", "rarityDetails", "value", "maxStack", "consumable", "material", "accessory", "defense",
    "headSlot", "bodySlot", "legSlot", "createTile", "createWall",
    "pickPower", "axePower", "hammerPower", "pick", "axe", "hammer",
    "healLife", "healMana", "manaCost", "buffType", "buffTime",
    "ammo", "useAmmo", "shoot", "shootSpeed", "fishingPole", "bait",
]
LLM_PROJECTILE_RAW_KEYS = [
    "source", "inventorySlot", "type", "internalName", "sourceMod", "fullName",
    "itemShootSpeed", "width", "height", "scale", "penetrate", "maxPenetrate", "timeLeft", "extraUpdates",
    "tileCollide", "ignoreWater", "friendly", "hostile", "arrow", "minion", "sentry", "minionSlots",
    "ownerHitCheck", "usesLocalNPCImmunity", "localNPCHitCooldown", "usesIDStaticNPCImmunity", "idStaticNPCHitCooldown",
    "stopsDealingDamageAfterPenetrateHits", "light", "alpha", "netImportant", "damageClass", "damageClassFullName",
    "framesRaw", "setsRaw", "fromGeneratedAttack", "engineMetrics", "unavailable",
]
LLM_AMMO_ITEM_KEYS = [
    "source", "inventorySlot", "type", "name", "internalName", "sourceMod", "fullName", "damage", "damageClass", "damageClassFullName",
    "ammo", "useAmmo", "shoot", "shootSpeed", "knockback", "rare", "value", "maxStack", "consumable", "material",
]


# Runtime validator policy deliberately avoids per-item semantic exception tables.
# Parent tags may still exist as raw/debug/legacy category evidence elsewhere, but combat
# safety below is authored-field and engine-pressure based, not item-family routing.


# =============================================================================
# NAV: LLM_PLAN_AND_REPAIR
# =============================================================================


# JSON object extraction/parsing lives in llm_json_tools.py. server.py re-exports
# the imported helpers for existing tests/tools that call server.parse_first_valid_llm_json.


_RESOLVED_LLM_MODEL: str | None = None


# -----------------------------------------------------------------------------
# Validation / gameplay / visual
# -----------------------------------------------------------------------------


STAGE_PROFILES = [
    {"name": "wood", "minDamage": 5, "maxDamage": 12, "rarity": 0, "value": 50, "useTime": 30, "speed": 6.5, "pierce": 1, "mana": 3, "powerBudget": 0.65},
    {"name": "early", "minDamage": 8, "maxDamage": 18, "rarity": 0, "value": 100, "useTime": 28, "speed": 7.0, "pierce": 1, "mana": 4, "powerBudget": 0.85},
    {"name": "pre_boss", "minDamage": 13, "maxDamage": 26, "rarity": 1, "value": 250, "useTime": 26, "speed": 7.5, "pierce": 1, "mana": 5, "powerBudget": 1.05},
    {"name": "evil_boss", "minDamage": 20, "maxDamage": 38, "rarity": 2, "value": 700, "useTime": 25, "speed": 8.0, "pierce": 2, "mana": 6, "powerBudget": 1.25},
    {"name": "pre_hardmode_late", "minDamage": 32, "maxDamage": 58, "rarity": 3, "value": 1800, "useTime": 24, "speed": 8.5, "pierce": 2, "mana": 7, "powerBudget": 1.55},
    {"name": "hardmode_early", "minDamage": 48, "maxDamage": 82, "rarity": 4, "value": 4500, "useTime": 23, "speed": 9.0, "pierce": 2, "mana": 8, "powerBudget": 1.9},
    {"name": "mech", "minDamage": 70, "maxDamage": 112, "rarity": 5, "value": 9000, "useTime": 22, "speed": 9.5, "pierce": 3, "mana": 9, "powerBudget": 2.25},
    {"name": "plantera", "minDamage": 92, "maxDamage": 145, "rarity": 7, "value": 15000, "useTime": 21, "speed": 10.0, "pierce": 3, "mana": 10, "powerBudget": 2.7},
    {"name": "lunar", "minDamage": 130, "maxDamage": 210, "rarity": 9, "value": 24000, "useTime": 20, "speed": 10.5, "pierce": 4, "mana": 12, "powerBudget": 3.25},
    {"name": "endgame", "minDamage": 170, "maxDamage": 280, "rarity": 10, "value": 40000, "useTime": 18, "speed": 11.5, "pierce": 5, "mana": 14, "powerBudget": 4.0},
]


MOVEMENT_CODE = {
    "straight": 0, "slow_homing": 1, "gravity_arc": 2, "drift": 3, "orbit": 4,
    "boomerang": 5, "bounce": 6, "sine_homing": 7, "phase": 8, "accelerate": 9,
    "spiral": 10, "vortex_orb": 11, "blackhole_pull": 12, "proximity_missile": 13,
    "returning_glaive": 14, "expanding_wave": 15,
    "flail_tether": 16, "yoyo_hover": 17, "whip_lash": 18,
}
MOVEMENT_ALIASES = {
    "rain": "gravity_arc",
    "fall": "gravity_arc",
    "falling": "gravity_arc",
    "falling_projectile": "gravity_arc",
    "projectile_rain": "gravity_arc",
    "starfall": "gravity_arc",
    "skyfall": "gravity_arc",
    "meteor": "gravity_arc",
    "arc": "gravity_arc",
    "lob": "gravity_arc",
    "lobbed": "gravity_arc",
    "grenade_arc": "gravity_arc",
    "homing": "slow_homing",
    "seeking": "slow_homing",
    "guided": "slow_homing",
    "tracking": "slow_homing",
    "return": "returning_glaive",
    "returning": "returning_glaive",
    "returning_throw": "returning_glaive",
    "glaive_return": "returning_glaive",
    "chakram": "boomerang",
    "boomerang_return": "boomerang",
    "wave": "expanding_wave",
    "shockwave": "expanding_wave",
    "ring": "expanding_wave",
    "beam": "phase",
    "laser": "phase",
    "ray": "phase",
    "hitscan": "phase",
    "missile": "proximity_missile",
    "rocket": "proximity_missile",
    "orb": "vortex_orb",
    "flail": "flail_tether",
    "chain_flail": "flail_tether",
    "mace": "flail_tether",
    "anchor": "flail_tether",
    "yoyo": "yoyo_hover",
    "yo_yo": "yoyo_hover",
    "whip": "whip_lash",
    "lash": "whip_lash",
}
DELIVERY_VALUES = {"none", "swing", "thrust", "spear", "shoot", "cast", "throw", "summon", "flail", "yoyo", "whip"}
RUNTIME_FAMILY_VALUES = {"none", "swing", "thrust", "returning", "flail", "yoyo", "whip", "shoot", "cast", "throw", "summon"}
DELIVERY_ALIASES = {
    "slash": "swing", "melee_arc": "swing", "blade_arc": "swing", "sword": "swing", "axe": "swing", "hammer": "swing", "club": "swing",
    "stab": "thrust", "rapier": "thrust", "shortsword": "thrust", "short_sword": "thrust", "held_thrust": "thrust", "spear_thrust": "thrust",
    "polearm": "thrust", "lance": "thrust", "pike": "thrust", "trident": "thrust", "halberd": "thrust", "naginata": "thrust",
    "ranged": "shoot", "bow": "shoot", "repeater": "shoot", "gun": "shoot", "launcher": "shoot", "crossbow": "shoot", "blowgun": "shoot",
    "magic": "cast", "spell": "cast", "staff": "cast", "wand": "cast", "rod": "cast", "book": "cast", "spellbook": "cast",
    "thrown": "throw", "knife": "throw", "dart": "throw", "grenade": "throw",
    "boomerang": "throw", "chakram": "throw", "glaive_throw": "throw", "returning_throw": "throw",
    "flail": "flail", "chain_flail": "flail", "ball_and_chain": "flail", "mace": "flail", "anchor": "flail",
    "yoyo": "yoyo", "yo_yo": "yoyo",
    "whip": "whip", "lash": "whip",
    "minion": "summon", "sentry": "summon", "summon_projectile": "summon",
}
EFFECT_ALIASES = {
    "fire": "flame", "burn": "flame", "ember": "flame", "lava": "flame", "magma": "flame",
    "ice": "frost", "cold": "frost", "snow": "frost", "frostburn": "frost",
    "lightning": "electric", "shock": "electric", "thunder": "electric", "storm": "electric",
    "venom": "poison", "toxic": "poison", "acid": "poison", "ichor": "poison",
    "dark": "shadow", "void": "shadow", "grave": "shadow", "shadowflame": "shadow",
    "nature": "leaf", "plant": "leaf", "spore": "leaf",
    "water": "slime", "goo": "slime", "gel": "slime",
    "radiant": "holy", "light": "holy", "solar": "holy",
    "smog": "smoke", "ash": "smoke",
}
ONHIT_ALIASES = {
    "fire": "burn", "on_fire": "burn", "ignite": "burn",
    "ice": "frostburn", "freeze": "frostburn", "chill": "frostburn",
    "venom": "poison", "toxic": "poison", "acid": "poison",
    "electric": "lightning_arc", "electrified": "lightning_arc", "shock": "lightning_arc", "zap": "lightning_arc",
    "blood": "bleed", "bleeding": "bleed",
    "explode": "burst", "explosion": "burst", "nova": "burst",
    "fragment": "split", "fragments": "split", "shards": "split",
    "star": "starburst", "stars": "starburst", "star_rain": "starfall", "falling_stars": "starfall", "star_wrath": "starfall", "sky_stars": "starfall",
    "life_steal": "lifesteal",
}
EFFECT_CODE = {
    "none": 0, "dust": 0, "electric": 1, "slime": 2, "star": 3, "flame": 4, "frost": 5,
    "leaf": 6, "shadow": 7, "poison": 8, "blood": 9, "honey": 10, "sand": 11, "lunar": 12, "heal": 13, "holy": 14, "smoke": 15,
}
ONHIT_CODE = {
    "none": 0, "burst": 1, "split": 2, "chain": 3, "burn": 4, "frostburn": 5,
    "poison": 6, "shadowflame": 7, "starburst": 8, "bleed": 9, "aura_pulse": 10,
    "spore_cloud": 11, "mini_missiles": 12, "vortex_spawn": 13, "blackhole": 14,
    "radial_beams": 15, "lightning_arc": 16, "lifesteal": 17, "heal": 17, "starfall": 18,
}


LLM_REQUIRED_GENOME_FIELDS = [
    "delivery", "movement", "effect", "onHit",
    "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles",
    "lifetimeTicks", "rangeTiles", "reliability", "selfLockTicks", "missPunish",
]

LLM_OPTIONAL_GENOME_DEFAULTS = {
    "homingStrength": 0.0,
    "extraUpdates": 0,
    "spreadRadians": 0.0,
    "speed": 8.0,
    "splitCount": 0,
    "chainCount": 0,
    "trailLength": 0,
    "burstDustCap": 0,
}

LLM_NUMERIC_GENOME_LIMITS = {
    "useTimeTicks": (10.0, 150.0),
    "shotCount": (1.0, 8.0),
    "pierce": (-1.0, 10.0),
    "aoeRadiusTiles": (0.0, 10.0),
    "homingStrength": (0.0, 1.0),
    "lifetimeTicks": (25.0, 900.0),
    "extraUpdates": (0.0, 3.0),
    "rangeTiles": (4.0, 120.0),
    "reliability": (0.45, 1.25),
    "selfLockTicks": (0.0, 120.0),
    "missPunish": (0.0, 1.0),
    "spreadRadians": (0.0, 0.75),
    "speed": (3.0, 18.0),
    "splitCount": (0.0, 8.0),
    "chainCount": (0.0, 6.0),
    "trailLength": (0.0, 24.0),
    "burstDustCap": (0.0, 40.0),
}


__all__ = [
    "PALETTES",
    "BAD_NAME_PATTERNS",
    "EFFECT_PRESENTATION",
    "LLM_RAW_TOKEN_MODE",
    "LLM_AMMO_REP_LIMIT",
    "LLM_INCLUDE_AISTYLE_RAW",
    "LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST",
    "LLM_ITEM_RAW_KEYS",
    "LLM_PROJECTILE_RAW_KEYS",
    "LLM_AMMO_ITEM_KEYS",
    "STAGE_PROFILES",
    "MOVEMENT_CODE",
    "MOVEMENT_ALIASES",
    "DELIVERY_VALUES",
    "RUNTIME_FAMILY_VALUES",
    "DELIVERY_ALIASES",
    "EFFECT_ALIASES",
    "ONHIT_ALIASES",
    "EFFECT_CODE",
    "ONHIT_CODE",
    "LLM_REQUIRED_GENOME_FIELDS",
    "LLM_OPTIONAL_GENOME_DEFAULTS",
    "LLM_NUMERIC_GENOME_LIMITS",
]
