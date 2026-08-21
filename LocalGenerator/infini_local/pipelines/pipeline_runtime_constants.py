from __future__ import annotations

import re

from infini_local.core.env_utils import env_bool, env_int, env_str

# AGENT MAP: pipeline-local palette and LLM prompt contract constants used by
# split combine/parent-context modules. Executor vocabulary/opcodes live in core.

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
]


# =============================================================================
# NAV: CATEGORY_AND_POLICY
# =============================================================================


# DEV-only accessory fallback builder lives in dev_fallback.py.



# Product invariants: the live /combine pipeline has one strict runtime-authoring path.
# Offline deterministic harnesses may disable USE_LLM, but cannot introduce a second genome-repair model role.
LLM_RUNTIME_AUTHORING = True
LLM_RUNTIME_PLAN_REQUIRED = True
LLM_RUNTIME_STRICT_VALIDATION = True
LLM_RUNTIME_MAX_CONCEPT_CANDIDATES = env_int("INFINI_LLM_RUNTIME_MAX_CONCEPT_CANDIDATES", 5, lo=1, hi=16)
LLM_RAW_TOKEN_MODE = env_str("INFINI_LLM_RAW_TOKEN_MODE", "compact").lower()
LLM_AMMO_REP_LIMIT = env_int("INFINI_LLM_AMMO_REP_LIMIT", 3)
# v0.4.52: LLM should see behavior words, not opaque vanilla aiStyle numbers.
# Keep numeric aiStyle internal/debug by default; expose only if explicitly requested.
LLM_INCLUDE_AISTYLE_RAW = env_bool("INFINI_LLM_INCLUDE_AISTYLE", False)
LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST = env_bool("INFINI_LLM_PROJECTILE_BEHAVIOR_DIGEST", True)

# Raw sections are still factual, but they should be compact: keep zeros/False because they
# are meaningful raw values, drop only null/empty strings/empty containers and duplicated
# sourceItem echo that is already present in itemRaw.
LLM_ITEM_RAW_KEYS = [
    "type", "name", "internalName", "sourceMod", "fullName", "tooltipLines",
    "damage", "damageClass", "knockback", "crit",
    "useStyle", "useStyleName", "useTime", "useAnimation", "reuseDelay", "autoReuse", "channel", "noMelee", "noUseGraphic", "useTurn",
    "rare", "rarityDetails", "value", "maxStack", "consumable", "material", "accessory", "defense",
    "headSlot", "bodySlot", "legSlot", "createTile", "createWall",
    "pickPower", "axePower", "hammerPower", "pick", "axe", "hammer",
    "healLife", "healMana", "potion", "manaCost", "buffType", "buffTime",
    "ammo", "ammoCategoryName", "notAmmo", "useAmmo", "shoot", "shootSpeed", "fishingPole", "bait",
]
LLM_PROJECTILE_RAW_KEYS = [
    "source", "inventorySlot", "type", "internalName", "sourceMod", "fullName",
    "itemShootSpeed", "width", "height", "scale", "penetrate", "maxPenetrate", "timeLeft", "extraUpdates",
    "tileCollide", "ignoreWater", "friendly", "hostile", "arrow", "minion", "sentry", "minionSlots",
    "ownerHitCheck", "usesLocalNPCImmunity", "localNPCHitCooldown", "usesIDStaticNPCImmunity", "idStaticNPCHitCooldown",
    "stopsDealingDamageAfterPenetrateHits", "light", "alpha", "netImportant", "damageClass",
    "framesRaw", "setsRaw", "fromGeneratedAttack", "engineMetrics", "unavailable",
]
LLM_AMMO_ITEM_KEYS = [
    "source", "inventorySlot", "type", "name", "internalName", "sourceMod", "fullName", "damage", "damageClass",
    "ammo", "ammoCategoryName", "notAmmo", "useAmmo", "shoot", "shootSpeed", "knockback", "rare", "value", "maxStack", "consumable", "material",
]


# Runtime validator policy deliberately avoids per-item semantic exception tables.
# Parent tags may still exist as raw/debug/legacy category evidence elsewhere, but combat
# safety below is authored-field and engine-pressure based, not item-family routing.


# =============================================================================
# NAV: LLM_PLAN_AND_REPAIR
# =============================================================================


# JSON object extraction/parsing lives in llm_json_tools.py; callers import that
# owner directly.


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




__all__ = [
    "PALETTES",
    "BAD_NAME_PATTERNS",

    "LLM_RAW_TOKEN_MODE",
    "LLM_AMMO_REP_LIMIT",
    "LLM_INCLUDE_AISTYLE_RAW",
    "LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST",
    "LLM_ITEM_RAW_KEYS",
    "LLM_PROJECTILE_RAW_KEYS",
    "LLM_AMMO_ITEM_KEYS",
    "STAGE_PROFILES",

]
