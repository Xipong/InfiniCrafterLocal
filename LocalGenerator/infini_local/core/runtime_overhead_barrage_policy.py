from __future__ import annotations

from typing import Any

OVERHEAD_BARRAGE_RUNTIME_FAMILY = "overhead_barrage"


def normalize_overhead_barrage_family(value: Any) -> str:
    """Normalize spelling only; old runtime-family names are intentionally unsupported."""
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def apply_overhead_barrage_contract(patch: dict[str, Any]) -> dict[str, Any]:
    """Apply only bounded executor invariants to explicitly authored barrage fields."""
    family = normalize_overhead_barrage_family(patch.get("runtimeFamily"))
    if family != OVERHEAD_BARRAGE_RUNTIME_FAMILY:
        return patch
    patch["runtimeFamily"] = OVERHEAD_BARRAGE_RUNTIME_FAMILY
    if patch.get("delayTicks") not in (None, ""):
        patch["delayTicks"] = int(max(0, min(300, float(patch["delayTicks"]))))
    if patch.get("shotCount") not in (None, ""):
        patch["shotCount"] = int(max(1, min(8, float(patch["shotCount"]))))
        patch["maxChildProjectiles"] = int(max(1, min(48, patch["shotCount"])))
        patch["maxChildDepth"] = 1
    if patch.get("secondaryDamageMultiplier") not in (None, ""):
        patch["secondaryDamageMultiplier"] = round(
            max(0.0, min(1.0, float(patch["secondaryDamageMultiplier"]))),
            3,
        )
    if patch.get("secondaryLifetimeTicks") not in (None, ""):
        patch["secondaryLifetimeTicks"] = int(
            max(5, min(180, float(patch["secondaryLifetimeTicks"])))
        )
    return patch


__all__ = [
    "OVERHEAD_BARRAGE_RUNTIME_FAMILY",
    "apply_overhead_barrage_contract",
    "normalize_overhead_barrage_family",
]
