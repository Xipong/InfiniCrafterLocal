from __future__ import annotations

"""Category/intent helper seam without prompt keyword routing.

Static category sets live in core.category_policy. This compatibility module keeps
the Stage-2 pipelines namespace available for existing imports and pure debug
helpers, but it does not infer gameplay from prompt words.
"""

from typing import Any

from infini_local.core.category_policy import (
    ACCESSORY_HINT_TAGS,
    ALLOWED_CATEGORIES,
    AMMO_HINT_TAGS,
    ARMOR_HINT_TAGS,
    COMBAT_CATEGORIES,
    NON_WEAPON_CATEGORIES,
    PLACEABLE_HINT_TAGS,
    STRONG_ACCESSORY_TAGS,
    TOOL_HINT_TAGS,
    WEAPON_UPGRADE_TAGS,
)


def normalize_category_value(value: Any, default: str = "generic") -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return default
    aliases = {
        "armour": "armor",
        "acc": "accessory",
        "trinket": "accessory",
        "melee_weapon": "weapon",
        "ranged_weapon": "weapon",
        "magic_weapon": "weapon",
        "summon_weapon": "weapon",
    }
    return aliases.get(text, text)


def category_intent_summary(data: dict[str, Any]) -> dict[str, Any]:
    gp = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    runtime = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    calls = runtime.get("engineCalls") if isinstance(runtime.get("engineCalls"), list) else []
    return {
        "authoredCategory": normalize_category_value(data.get("category")),
        "gameplayKind": normalize_category_value(gp.get("kind")),
        "hasRuntimePlan": bool(calls),
        "engineFunctions": [str(c.get("fn") or "") for c in calls if isinstance(c, dict)],
    }


def runtime_kind_is_non_weapon(kind: Any) -> bool:
    return normalize_category_value(kind) in NON_WEAPON_CATEGORIES


__all__ = [
    "ACCESSORY_HINT_TAGS",
    "ALLOWED_CATEGORIES",
    "AMMO_HINT_TAGS",
    "ARMOR_HINT_TAGS",
    "COMBAT_CATEGORIES",
    "NON_WEAPON_CATEGORIES",
    "PLACEABLE_HINT_TAGS",
    "STRONG_ACCESSORY_TAGS",
    "TOOL_HINT_TAGS",
    "WEAPON_UPGRADE_TAGS",
    "normalize_category_value",
    "category_intent_summary",
    "runtime_kind_is_non_weapon",
]
