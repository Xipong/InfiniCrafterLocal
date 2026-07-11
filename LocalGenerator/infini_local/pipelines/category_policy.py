from __future__ import annotations

"""Pure category/intent debug helpers without prompt keyword routing."""

from typing import Any

from infini_local.core.category_policy import NON_WEAPON_CATEGORIES


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
    "normalize_category_value",
    "category_intent_summary",
    "runtime_kind_is_non_weapon",
]
