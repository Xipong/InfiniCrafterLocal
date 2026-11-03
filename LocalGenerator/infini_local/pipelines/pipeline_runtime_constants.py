from __future__ import annotations

import re

from infini_local.core.env_utils import env_bool

# AGENT MAP: pipeline-local LLM prompt contract constants used by
# split combine/parent-context modules. Executor vocabulary/opcodes live in core.

BAD_NAME_PATTERNS = [
    re.compile(r"^\s*infini(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*generated(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*combined(?:\s|$|[-_])", re.I),
]


# =============================================================================
# NAV: CATEGORY_AND_POLICY
# =============================================================================


# DEV-only accessory fallback builder lives in dev_fallback.py.



# Keep numeric aiStyle internal/debug by default; expose only if explicitly requested.
LLM_INCLUDE_AISTYLE_RAW = env_bool("INFINI_LLM_INCLUDE_AISTYLE", False)

# Raw sections are still factual, but they should be compact: keep zeros/False because they
# are meaningful raw values, drop only null/empty strings/empty containers and duplicated
# sourceItem echo that is already present in itemRaw.
LLM_ITEM_RAW_KEYS = [
    "type", "name", "internalName", "sourceMod", "fullName", "tooltipLines",
    "damage", "damageClass", "knockback", "crit", "armorPenetration", "itemScale",
    "useStyle", "useStyleName", "useTime", "useAnimation", "useLimitPerAnimation", "reuseDelay", "autoReuse", "channel", "noMelee", "noUseGraphic", "useTurn",
    "rare", "rarityDetails", "value", "maxStack", "consumable", "material", "accessory", "defense",
    "headSlot", "bodySlot", "legSlot", "createTile", "createWall", "placeStyle", "nativeTileState",
    "pickPower", "axePower", "hammerPower", "pick", "axe", "hammer",
    "healLife", "healMana", "lifeRegen", "potion", "manaCost", "buffType", "buffTime",
    "ammo", "ammoCategoryName", "notAmmo", "useAmmo", "useAmmoCategoryName", "dropSeedsIfInInventory",
    "shoot", "shootSpeed", "fishingPole", "bait",
]
LLM_PROJECTILE_RAW_KEYS = [
    "source", "inventorySlot", "type", "internalName", "sourceMod", "fullName",
    "armorPenetration", "itemShootSpeed", "width", "height", "scale", "penetrate", "maxPenetrate", "timeLeft", "extraUpdates",
    "tileCollide", "ignoreWater", "friendly", "hostile", "arrow", "minion", "sentry", "minionSlots",
    "ownerHitCheck", "usesLocalNPCImmunity", "localNPCHitCooldown", "usesIDStaticNPCImmunity", "idStaticNPCHitCooldown",
    "stopsDealingDamageAfterPenetrateHits", "light", "alpha", "netImportant", "damageClass",
    "framesRaw", "setsRaw", "fromGeneratedAttack", "engineMetrics", "unavailable", "runtimeDumpProvenance",
]
LLM_AMMO_ITEM_KEYS = [
    "source", "inventorySlot", "type", "name", "internalName", "sourceMod", "fullName", "damage", "damageClass",
    "ammo", "ammoCategoryName", "notAmmo", "useAmmo", "shoot", "shootSpeed", "knockback", "rare", "value", "maxStack", "consumable", "material",
]


__all__ = [
    "BAD_NAME_PATTERNS",

    "LLM_INCLUDE_AISTYLE_RAW",
    "LLM_ITEM_RAW_KEYS",
    "LLM_PROJECTILE_RAW_KEYS",
    "LLM_AMMO_ITEM_KEYS",

]
