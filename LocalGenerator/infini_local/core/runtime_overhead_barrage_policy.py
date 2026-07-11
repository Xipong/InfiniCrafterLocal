from __future__ import annotations

from typing import Any

OVERHEAD_BARRAGE_RUNTIME_FAMILY = "overhead_barrage"


def normalize_overhead_barrage_family(value: Any) -> str:
    """Normalize spelling only; old runtime-family names are intentionally unsupported."""
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def apply_overhead_barrage_contract(patch: dict[str, Any]) -> dict[str, Any]:
    """Fill only fields owned by the finite overhead-barrage executor.

    This is deliberately not a generic trigger/state engine.
    """
    family = normalize_overhead_barrage_family(patch.get("runtimeFamily"))
    if family != OVERHEAD_BARRAGE_RUNTIME_FAMILY:
        return patch
    patch["runtimeFamily"] = OVERHEAD_BARRAGE_RUNTIME_FAMILY
    raw_delay = patch.get("delayTicks")
    raw_shots = patch.get("shotCount")
    patch["delayTicks"] = int(max(0, min(300, float(30 if raw_delay in (None, "") else raw_delay))))
    patch["shotCount"] = int(max(1, min(8, float(3 if raw_shots in (None, "") else raw_shots))))
    patch.setdefault("secondaryDamageMultiplier", 0.55)
    patch.setdefault("secondaryLifetimeTicks", 75)
    patch["maxChildProjectiles"] = int(max(1, min(48, patch["shotCount"])))
    patch["maxChildDepth"] = 1
    patch.setdefault("movement", "phase")
    patch.setdefault("delivery", "shoot")
    patch.setdefault("projectileFamily", "projectile")
    return patch


__all__ = [
    "OVERHEAD_BARRAGE_RUNTIME_FAMILY",
    "apply_overhead_barrage_contract",
    "normalize_overhead_barrage_family",
]
