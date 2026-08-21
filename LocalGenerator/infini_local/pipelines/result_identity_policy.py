from __future__ import annotations

from typing import Any

from infini_local.core.category_policy import ALLOWED_CATEGORIES

from infini_local.pipelines.pipeline_runtime_constants import BAD_NAME_PATTERNS

from infini_local.core.item_identity_tools import (
    item_bool,
    item_num,
    name_of,
)

from infini_local.core.item_signals import VISUAL_SYNONYMS


# AGENT MAP: result identity seam for combine_pipeline.
# Owns deterministic validation of the Author-owned result identity: category
# vocabulary normalization, final-name sanity gate, parent primary-category
# context and visual anchor derivation. It never samples, coerces or routes
# the result category/name: both belong to the LLM Author.


def _ordered_known_tags(tags: set[str], canonical: dict[str, Any]) -> list[str]:
    known = [key for key in canonical if key in tags]
    unknown = sorted(str(tag) for tag in tags if tag not in canonical)
    return known + unknown


def bad_result_name(name: Any, a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> bool:
    n = str(name or "").strip()
    if len(n) < 3 or len(n) > 48:
        return True
    if any(p.search(n) for p in BAD_NAME_PATTERNS):
        return True
    low = n.lower().strip()
    parent_names = {name_of(x).lower().strip() for x in (a or {}, b or {}) if isinstance(x, dict)}
    if low in parent_names:
        return True
    if low in {"item", "generated item", "unknown", "thing", "object"}:
        return True
    return False


def normalize_category(category: Any) -> str:
    c = str(category or "generic").lower().strip()
    aliases = {
        "placeable": "furniture",
        "station": "placeable_station",
        "crafting_station": "placeable_station",
        "device": "technology",
        "trinket": "accessory",
        "acc": "accessory",
        # Do not alias generic consumable to potion. v0.4 runtime has separate
        # stackable generated consumable weapons; potion is only for healing/buff items.
        "consumable_item": "consumable",
        "stack_consumable": "consumable",
        "thrown_stack": "consumable",
    }
    c = aliases.get(c, c)
    return c if c in ALLOWED_CATEGORIES else "generic"


def parent_primary_category(item: dict[str, Any]) -> str:
    """Stable primary role for parent context.

    Important: Terraria Item.material means "can be used in recipes later", not
    "this item is primarily a material". Many weapons/tools are material=true.
    Treat material as a secondary craftability flag unless no stronger role fits.
    """
    damage = int(item_num(item, "damage", 0))
    pick = int(item_num(item, "pickPower", item_num(item, "pick", 0)))
    axe = int(item_num(item, "axePower", item_num(item, "axe", 0)))
    hammer = int(item_num(item, "hammerPower", item_num(item, "hammer", 0)))
    create_tile = int(item_num(item, "createTile", -1))
    create_wall = int(item_num(item, "createWall", -1))

    if item_bool(item, "accessory"):
        return "accessory"
    if item_num(item, "defense", 0) > 0:
        return "armor"
    if pick > 0 or axe > 0 or hammer > 0:
        return "tool"
    if damage > 0:
        return "weapon"
    if item_num(item, "ammo", 0) > 0:
        return "ammo"
    if item_num(item, "healLife", 0) > 0 or item_num(item, "healMana", 0) > 0 or item_num(item, "buffType", 0) > 0:
        return "potion"
    if item_bool(item, "consumable") and item_num(item, "shoot", 0) > 0:
        return "consumable"
    if create_tile >= 0 or create_wall >= 0:
        return "furniture"
    if item_bool(item, "consumable") and not item_bool(item, "material"):
        return "consumable"
    if item_bool(item, "material"):
        return "material"
    return "generic"


def required_anchors_from_tags(tags: set[str]) -> list[str]:
    anchors = []
    for tag in _ordered_known_tags(tags, VISUAL_SYNONYMS):
        anchors.extend(VISUAL_SYNONYMS.get(tag, []))
    return list(dict.fromkeys(anchors))


__all__ = [
    "bad_result_name",
    "normalize_category",
    "parent_primary_category",
    "required_anchors_from_tags",
]
