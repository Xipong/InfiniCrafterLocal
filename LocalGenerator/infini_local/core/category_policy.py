from __future__ import annotations


"""Stable item-hint vocabulary for parent knowledge context.

This module owns static hint-tag vocabularies only. It has no environment reads,
filesystem setup, LLM imports, HTTP imports, or runtime side effects. It is not
prompt keyword routing: gameplay still comes from authored runtimePlan/compiled
specs, and these tags are never injected into LLM-authored result tags in
runtime authoring mode.
"""


ALLOWED_CATEGORIES = {
    "weapon", "accessory", "potion", "consumable", "furniture", "technology", "placeable_station",
    "material", "ammo", "tool", "armor", "summon", "vanity", "mount", "pet", "light_pet", "grappling_hook", "generic",
}
ACCESSORY_HINT_TAGS = {
    "accessory", "boots", "wings", "shield", "emblem", "charm", "ring", "band", "amulet",
    "necklace", "glove", "claw", "balloon", "horseshoe", "anklet", "aglet", "mobility", "defense",
}
TOOL_HINT_TAGS = {"pickaxe", "axe", "hammer", "drill", "chainsaw", "tool", "hook"}
AMMO_HINT_TAGS = {"ammo", "arrow", "bullet", "rocket", "dart"}
ARMOR_HINT_TAGS = {"armor", "helmet", "breastplate", "chestplate", "greaves", "leggings"}

__all__ = [
    "ALLOWED_CATEGORIES",
    "ACCESSORY_HINT_TAGS",
    "TOOL_HINT_TAGS",
    "AMMO_HINT_TAGS",
    "ARMOR_HINT_TAGS",
]
