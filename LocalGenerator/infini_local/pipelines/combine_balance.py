from __future__ import annotations

"""Source-numeric balance corridor for the low-level Gameplay Author.

This module deliberately reads no names, tags, categories, tooltip text,
knowledge entries, or semantic classifiers. The corridor is broad numeric
guidance only and never selects mechanics, entity kinds, inputs or assets.
"""

from typing import Any

from infini_local.core.item_identity_tools import item_num


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _numeric_power(item: dict[str, Any]) -> float:
    damage = max(0.0, float(item_num(item, "damage", 0)))
    use_time = max(1.0, float(item_num(item, "useTime", 20)))
    combat = damage * _clamp(20.0 / use_time, 0.25, 4.0)
    tool = max(
        0.0,
        float(item_num(item, "pickPower", 0)),
        float(item_num(item, "axePower", 0)) * 5.0,
        float(item_num(item, "hammerPower", 0)),
    )
    sustain = max(
        float(item_num(item, "defense", 0)) * 5.0,
        float(item_num(item, "healLife", 0)) * 2.0,
        float(item_num(item, "healMana", 0)),
    )
    rarity = max(0.0, float(item_num(item, "rare", 0))) * 7.0
    value = max(0.0, float(item_num(item, "value", 0)))
    value_signal = value ** 0.5 / 7.0 if value else 0.0
    return max(combat, tool, sustain, rarity, value_signal)


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
    scores = [_numeric_power(a), _numeric_power(b)]
    damages = [max(0, int(item_num(a, "damage", 0))), max(0, int(item_num(b, "damage", 0)))]
    fastest_use = min([
        max(1.0, float(item_num(item, "useTime", 20)))
        for item in (a, b) if item_num(item, "damage", 0) > 0
    ] or [20.0])
    combined = max(scores) + min(scores) * 0.28
    max_damage = max(damages)
    suggested_damage = (
        int(_clamp(max(max_damage + 1, max_damage * 1.25 + combined ** 0.5), 1, 2000))
        if max_damage else int(_clamp(combined ** 0.75, 0, 2000))
    )
    power_budget = round(_clamp(0.9 + combined / 55.0, 0.9, 8.0), 2)
    damage_hi = int(_clamp(max(24, suggested_damage * 2.5 + 24), 24, 2000))
    progression_facts = [
        fact for fact in (
            _source_progression_fact(a, "A"),
            _source_progression_fact(b, "B"),
        ) if fact is not None
    ]
    return {
        "authority": "source_numeric_facts_only",
        "gameplayRouter": False,
        "scores": [round(scores[0], 2), round(scores[1], 2)],
        "sourceDamage": damages,
        "sourceFastestUseTime": fastest_use,
        "sourceNumericProgressionFacts": progression_facts,
        "derivedPower": round(combined, 2),
        "derivedDamage": suggested_damage,
        "powerBudget": power_budget,
        "balanceEnvelope": {
            "damage": {"minimum": 0, "suggested": suggested_damage, "maximum": damage_hi},
            "useTimeTicks": {"minimum": 4, "suggested": int(_clamp(fastest_use, 4, 600)), "maximum": 600},
            "lifetimeTicks": {"minimum": 1, "maximum": 36000},
            "entityCount": {"minimum": 1, "maximum": 12},
            "eventSpawnsPerActivation": {"minimum": 0, "maximum": 32},
            "note": "Wide numeric guidance only. The Author chooses every runtime component; deterministic code applies hard safety bounds only.",
        },
    }


__all__ = ["stat_profile_for"]
