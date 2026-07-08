from __future__ import annotations

import math
from typing import Any

from infini_local.core.runtime_authoring.schema import (
    DELIVERIES,
    DELIVERY_ALIASES,
    EFFECTS,
    EFFECT_ALIASES,
    INT_FIELDS,
    MOVEMENTS,
    MOVEMENT_ALIASES,
    NUMERIC_LIMITS,
    ONHITS,
    ONHIT_ALIASES,
)

ENGINE_RUNTIME_API_VERSION = "v0.4.47"

def _intish(field: str, value: float) -> int | float:
    return int(round(value)) if field in INT_FIELDS or field.endswith("Ticks") else round(value, 3)


def _norm_name(x: Any) -> str:
    return str(x or "").strip().lower().replace("-", "_").replace(" ", "_")


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _clamp(value: Any, field: str, default: float | None = None) -> float | None:
    x = _num(value, default)
    if x is None:
        return None
    lo, hi = NUMERIC_LIMITS[field]
    return max(lo, min(hi, x))


def _enum(value: Any, allowed: set[str], fallback: str | None = None) -> str | None:
    v = _norm_name(value)
    if allowed is MOVEMENTS:
        v = MOVEMENT_ALIASES.get(v, v)
    elif allowed is DELIVERIES:
        v = DELIVERY_ALIASES.get(v, v)
    elif allowed is EFFECTS:
        v = EFFECT_ALIASES.get(v, v)
    elif allowed is ONHITS:
        v = ONHIT_ALIASES.get(v, v)
    if v in allowed:
        return v
    return fallback

__all__ = ["ENGINE_RUNTIME_API_VERSION", "_intish", "_norm_name", "_num", "_clamp", "_enum"]
