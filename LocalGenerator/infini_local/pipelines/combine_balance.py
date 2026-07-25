from __future__ import annotations

"""Parent-fact balance corridor for the low-level Gameplay Author.

The corridor exposes broad numeric guidance and never selects an entity kind,
movement, controller, delivery path, or input binding.
"""

from typing import Any

from infini_local.core.item_identity_tools import item_num
from infini_local.pipelines.item_power_knowledge import (
    generation_depth,
    infer_item_card,
    mechanic_signal_power,
    recipe_coherence,
    tags_of,
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def stat_profile_for(a: dict[str, Any], b: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    cards = [infer_item_card(a), infer_item_card(b)]
    scores = [
        max(float(mechanic_signal_power(item).get("score") or 0.0), float(card.get("powerScore") or 0.0))
        for item, card in ((a, cards[0]), (b, cards[1]))
    ]
    damages = [max(0, int(item_num(a, "damage", 0))), max(0, int(item_num(b, "damage", 0)))]
    fastest_use = min([
        max(1.0, float(item_num(item, "useTime", 20)))
        for item in (a, b) if item_num(item, "damage", 0) > 0
    ] or [20.0])
    combined = max(scores) + min(scores) * 0.28
    max_damage = max(damages)
    suggested_damage = int(_clamp(max(max_damage + 1, max_damage * 1.25 + combined ** 0.5), 1, 2000)) if max_damage else int(_clamp(combined ** 0.75, 0, 2000))
    power_budget = round(_clamp(0.9 + combined / 55.0, 0.9, 8.0), 2)
    stage = (
        "wood" if combined < 16 else "early" if combined < 32 else "pre_boss" if combined < 55
        else "pre_hardmode_late" if combined < 85 else "hardmode_early" if combined < 125
        else "mech" if combined < 175 else "plantera" if combined < 235 else "lunar" if combined < 310 else "endgame"
    )
    damage_hi = int(_clamp(max(24, suggested_damage * 2.5 + 24), 24, 2000))
    return {
        "name": stage,
        "authority": "parent_mechanical_facts_only",
        "gameplayRouter": False,
        "scores": [round(scores[0], 2), round(scores[1], 2)],
        "knowledgeTiers": [cards[0].get("tier", "unknown"), cards[1].get("tier", "unknown")],
        "sourceDamage": damages,
        "sourceFastestUseTime": fastest_use,
        "parentGeneratedDepths": [generation_depth(a), generation_depth(b)],
        "recipeCoherence": recipe_coherence(tags, a, b),
        "derivedPower": round(combined, 2),
        "derivedDamage": suggested_damage,
        "powerBudget": power_budget,
        "balanceEnvelope": {
            "damage": {"minimum": 0, "suggested": suggested_damage, "maximum": damage_hi},
            "useTimeTicks": {"minimum": 4, "suggested": int(_clamp(fastest_use, 4, 600)), "maximum": 600},
            "lifetimeTicks": {"minimum": 1, "maximum": 36000},
            "entityCount": {"minimum": 1, "maximum": 12},
            "eventSpawnsPerActivation": {"minimum": 0, "maximum": 32},
            "note": "Wide guidance only. The Author explicitly chooses every runtime component; deterministic code applies hard safety bounds only.",
        },
    }


__all__ = ["stat_profile_for"]
