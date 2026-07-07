from __future__ import annotations

"""Stable category and item-hint policy for generated-item classification.

This module owns static category vocabulary only. It has no environment reads,
filesystem setup, LLM imports, HTTP imports, or runtime side effects. It is not
prompt keyword routing: gameplay still comes from authored runtimePlan/compiled specs.
"""

ALLOWED_CATEGORIES = {
    "weapon", "accessory", "potion", "consumable", "furniture", "technology", "placeable_station",
    "material", "ammo", "tool", "armor", "summon", "vanity", "mount", "pet", "light_pet", "grappling_hook", "generic",
}
NON_WEAPON_CATEGORIES = ALLOWED_CATEGORIES - {"weapon", "summon"}
COMBAT_CATEGORIES = {"weapon", "summon"}
ACCESSORY_HINT_TAGS = {
    "accessory", "boots", "wings", "shield", "emblem", "charm", "ring", "band", "amulet",
    "necklace", "glove", "claw", "balloon", "horseshoe", "anklet", "aglet", "mobility", "defense",
}
TOOL_HINT_TAGS = {"pickaxe", "axe", "hammer", "drill", "chainsaw", "tool", "hook"}
AMMO_HINT_TAGS = {"ammo", "arrow", "bullet", "rocket", "dart"}
ARMOR_HINT_TAGS = {"armor", "helmet", "breastplate", "chestplate", "greaves", "leggings"}
STRONG_ACCESSORY_TAGS = {"accessory", "boots", "wings", "shield", "emblem", "charm", "ring", "band", "amulet", "glove", "balloon", "horseshoe"}
WEAPON_UPGRADE_TAGS = {"star", "mana", "magic", "fire", "ice", "shadow", "electric", "wire", "slime", "gel", "poison", "toxic", "explosive", "earth", "dirt", "stone", "sand"}
PLACEABLE_HINT_TAGS = {"placeable", "furniture", "chair", "workbench", "bench", "crafting_station", "block", "dirt", "stone", "sand"}

__all__ = [
    "ALLOWED_CATEGORIES",
    "NON_WEAPON_CATEGORIES",
    "COMBAT_CATEGORIES",
    "ACCESSORY_HINT_TAGS",
    "TOOL_HINT_TAGS",
    "AMMO_HINT_TAGS",
    "ARMOR_HINT_TAGS",
    "STRONG_ACCESSORY_TAGS",
    "WEAPON_UPGRADE_TAGS",
    "PLACEABLE_HINT_TAGS",
]
