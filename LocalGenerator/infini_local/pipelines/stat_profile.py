from __future__ import annotations

"""Parent stats, source damage, generated depth, weak anchor signals.

The heavy stat_profile_for/stage_profile_for implementations live in
combine_balance. This module owns small pure summaries used by tests/debug code
and provides the canonical import path for new callers.
"""

from typing import Any

from infini_local.pipelines.combine_balance import stat_profile_for, stage_profile_for


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parent_source_damage(parent: dict[str, Any]) -> int:
    gp = parent.get("gameplay") if isinstance(parent.get("gameplay"), dict) else {}
    return max(_int(parent.get("damage")), _int(gp.get("damage")))


def parent_use_time(parent: dict[str, Any]) -> int:
    gp = parent.get("gameplay") if isinstance(parent.get("gameplay"), dict) else {}
    return max(0, _int(parent.get("useTime") or gp.get("useTime")))


def generated_depth_from_sources(*parents: dict[str, Any]) -> int:
    depths: list[int] = []
    for parent in parents:
        meta = parent.get("recipeMeta") if isinstance(parent.get("recipeMeta"), dict) else {}
        debug = parent.get("debug") if isinstance(parent.get("debug"), dict) else {}
        depth = _int(meta.get("generationDepth") or debug.get("generationDepth"), 0)
        if depth > 0:
            depths.append(depth)
    return (max(depths) + 1) if depths else 1


def weak_anchor_signals(stage: dict[str, Any]) -> dict[str, Any]:
    transfer = stage.get("powerTransfer") if isinstance(stage.get("powerTransfer"), dict) else {}
    return {
        "weakAnchor": bool(transfer.get("weakAnchor")),
        "quality": str(transfer.get("quality") or ""),
        "resultTier": str(transfer.get("resultTier") or stage.get("name") or ""),
    }


def stat_profile_summary(stage: dict[str, Any]) -> dict[str, Any]:
    transfer = stage.get("powerTransfer") if isinstance(stage.get("powerTransfer"), dict) else {}
    return {
        "name": stage.get("name"),
        "powerBudget": _num(stage.get("powerBudget"), 1.0),
        "rarity": _int(stage.get("rarity"), 0),
        "sourceMaxDamage": _int(stage.get("sourceMaxDamage"), 0),
        "sourceFastestUseTime": _int(stage.get("sourceFastestUseTime"), 0),
        "parentGeneratedDepths": list(stage.get("parentGeneratedDepths") or []),
        "powerTransfer": dict(transfer),
        "weakAnchor": weak_anchor_signals(stage),
    }


__all__ = [
    "stat_profile_for",
    "stage_profile_for",
    "parent_source_damage",
    "parent_use_time",
    "generated_depth_from_sources",
    "weak_anchor_signals",
    "stat_profile_summary",
]
