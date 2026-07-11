from __future__ import annotations

import math
from typing import Any

SENTRY_RUNTIME_FAMILY = "sentry"
SENTRY_PLACEMENTS = frozenset({"grounded", "floating"})
SENTRY_INTERVAL_MIN = 12
SENTRY_INTERVAL_MAX = 180
SENTRY_INTERVAL_DEFAULT = 45
SENTRY_RANGE_MIN = 8.0
SENTRY_RANGE_MAX = 60.0
SENTRY_RANGE_DEFAULT = 30.0
SENTRY_LIFETIME_MIN = 120
SENTRY_LIFETIME_MAX = 36000
SENTRY_LIFETIME_DEFAULT = 3600
SENTRY_MAX_SHOTS_PER_VOLLEY = 4
SENTRY_MAX_TOTAL_SHOTS = 48
SENTRY_CHILD_ONHIT = frozenset({"split", "chain", "starburst", "overhead_barrage", "spore_cloud", "mini_missiles", "vortex_spawn", "radial_beams", "lightning_arc"})


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def reject_recursive_sentry_onhit(value: Any) -> None:
    if _token(value) in SENTRY_CHILD_ONHIT:
        raise ValueError("sentry_does_not_support_child_producing_onhit")


def apply_sentry_contract(patch: dict[str, Any]) -> None:
    if _token(patch.get("runtimeFamily")) != SENTRY_RUNTIME_FAMILY:
        return
    if _token(patch.get("secondaryTrigger")):
        raise ValueError("sentry_does_not_support_secondary_projectile_triggers")
    reject_recursive_sentry_onhit(patch.get("onHit"))
    placement = _token(patch.get("sentryPlacement")) or "grounded"
    if placement not in SENTRY_PLACEMENTS:
        raise ValueError("sentryPlacement_must_be_grounded_or_floating")
    interval = max(SENTRY_INTERVAL_MIN, min(SENTRY_INTERVAL_MAX, int(float(patch.get("sentryAttackIntervalTicks") or SENTRY_INTERVAL_DEFAULT))))
    target_range = max(SENTRY_RANGE_MIN, min(SENTRY_RANGE_MAX, float(patch.get("sentryTargetRangeTiles") or SENTRY_RANGE_DEFAULT)))
    lifetime = max(SENTRY_LIFETIME_MIN, min(SENTRY_LIFETIME_MAX, int(float(patch.get("sentryLifetimeTicks") or SENTRY_LIFETIME_DEFAULT))))
    shots = max(1, min(SENTRY_MAX_SHOTS_PER_VOLLEY, int(float(patch.get("shotCount") or 1))))
    max_total = min(SENTRY_MAX_TOTAL_SHOTS, max(1, int(math.ceil(lifetime / interval)) * shots))
    patch.setdefault("damageClass", "summon")
    patch.update({
        "delivery": "summon",
        "channelUse": False,
        "hideUseGraphic": False,
        "disableItemMeleeHitbox": True,
        "ownerHitCheck": False,
        "sentryPlacement": placement,
        "sentryAttackIntervalTicks": interval,
        "sentryTargetRangeTiles": round(target_range, 3),
        "sentryLifetimeTicks": lifetime,
        "shotCount": shots,
        "maxChildProjectiles": max_total,
        "maxChildDepth": 1,
    })


__all__ = [
    "SENTRY_RUNTIME_FAMILY", "SENTRY_PLACEMENTS",
    "SENTRY_INTERVAL_MIN", "SENTRY_INTERVAL_MAX", "SENTRY_INTERVAL_DEFAULT",
    "SENTRY_RANGE_MIN", "SENTRY_RANGE_MAX", "SENTRY_RANGE_DEFAULT",
    "SENTRY_LIFETIME_MIN", "SENTRY_LIFETIME_MAX", "SENTRY_LIFETIME_DEFAULT",
    "SENTRY_MAX_SHOTS_PER_VOLLEY", "SENTRY_MAX_TOTAL_SHOTS", "SENTRY_CHILD_ONHIT",
    "reject_recursive_sentry_onhit", "apply_sentry_contract",
]
