from __future__ import annotations

import math
from typing import AbstractSet, Any

from infini_local.core.runtime_authoring.schema import INT_FIELDS, NUMERIC_LIMITS
from infini_local.core.runtime_authoring.vocabulary import (
    DELIVERIES,
    normalize_authoring_enum,
    normalize_authoring_token,
)
from infini_local.core.runtime_executor_vocabulary import EFFECTS, MOVEMENTS, ONHITS

ENGINE_RUNTIME_API_VERSION = "v0.4.48"

def _intish(field: str, value: float) -> int | float:
    return int(round(value)) if field in INT_FIELDS or field.endswith("Ticks") else round(value, 3)


def _norm_name(x: Any) -> str:
    return normalize_authoring_token(x)


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


def _enum(value: Any, allowed: AbstractSet[str], fallback: str | None = None) -> str | None:
    field = (
        "movement" if allowed is MOVEMENTS
        else "delivery" if allowed is DELIVERIES
        else "effect" if allowed is EFFECTS
        else "onHit" if allowed is ONHITS
        else "runtimeFamily"
    )
    v = normalize_authoring_enum(value, field)
    if v in allowed:
        return v
    return fallback

__all__ = ["ENGINE_RUNTIME_API_VERSION", "_intish", "_norm_name", "_num", "_clamp", "_enum"]
