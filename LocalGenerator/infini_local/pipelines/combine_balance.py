from __future__ import annotations

"""Source-numeric balance corridor for the low-level Gameplay Author.

This module deliberately reads no names, tags, categories, tooltip text,
knowledge entries, or semantic classifiers. The corridor is broad numeric
guidance only and never selects mechanics, entity kinds, inputs or assets.
"""

from typing import Any

from infini_local.core.item_identity_tools import item_num
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY


def _source_progression_fact(item: dict[str, Any], parent: str) -> dict[str, Any] | None:
    generated = item.get("generatedData")
    if not isinstance(generated, dict):
        return None
    recipe_meta = generated.get("recipeMeta")
    if not isinstance(recipe_meta, dict):
        return None
    raw = recipe_meta.get("generationDepth")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = int(raw)
    if value < 0 or float(raw) != float(value):
        return None
    return {
        "parent": parent,
        "path": "generatedData.recipeMeta.generationDepth",
        "value": value,
    }


def stat_profile_for(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    damages = [max(0, int(item_num(parent, "damage", 0))) for parent in (a, b)]
    progression_facts = [
        fact for fact in (
            _source_progression_fact(a, "A"),
            _source_progression_fact(b, "B"),
        ) if fact is not None
    ]
    return {
        "authority": "source_numeric_facts_only",
        "gameplayRouter": False,
        "sourceDamage": damages,
        "sourceNumericProgressionFacts": progression_facts,
        "balanceEnvelope": {
            "useTimeSeconds": {
                "minimum": CAPABILITY_REGISTRY["configure_item_stats"].params["useTimeSeconds"].from_wire(4),
                "maximum": CAPABILITY_REGISTRY["configure_item_stats"].params["useTimeSeconds"].from_wire(600),
            },
            "lifetimeSeconds": {
                "minimum": CAPABILITY_REGISTRY["set_projectile_lifetime"].params["lifetimeSeconds"].minimum,
                "maximum": CAPABILITY_REGISTRY["set_projectile_lifetime"].params["lifetimeSeconds"].maximum,
            },
            "entityCount": {"minimum": 1, "maximum": 12},
            "eventSpawnsPerActivation": {"minimum": 0, "maximum": 32},
            "note": "Wide numeric guidance only. The Author chooses every runtime component; deterministic code applies hard safety bounds only.",
        },
    }


__all__ = ["stat_profile_for"]
