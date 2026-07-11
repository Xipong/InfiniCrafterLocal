from __future__ import annotations

from typing import Any

from infini_local.core.env_utils import env_str

# AGENT MAP: one tiny owner for post-authoring balance behavior.
# Do not put balance formulas here. This module only selects whether existing
# safety/normalization owners may mutate authored values.
BALANCE_MODE_ENV = "INFINI_BALANCE_MODE"
BALANCE_MODE_REPORT = "report"
BALANCE_MODE_SAFETY = "safety"
BALANCE_MODE_NORMALIZE = "normalize"
CANONICAL_BALANCE_MODES = frozenset({
    BALANCE_MODE_REPORT,
    BALANCE_MODE_SAFETY,
    BALANCE_MODE_NORMALIZE,
})
DEFAULT_BALANCE_MODE = BALANCE_MODE_SAFETY


def normalize_balance_mode(value: Any) -> str:
    token = str(value or "").strip().lower()
    return token if token in CANONICAL_BALANCE_MODES else DEFAULT_BALANCE_MODE


def current_balance_mode() -> str:
    return normalize_balance_mode(env_str(BALANCE_MODE_ENV, DEFAULT_BALANCE_MODE))


def should_apply_python_safety(mode: Any = None) -> bool:
    selected = current_balance_mode() if mode is None else normalize_balance_mode(mode)
    return selected in {BALANCE_MODE_SAFETY, BALANCE_MODE_NORMALIZE}


def should_apply_soft_normalization(mode: Any = None) -> bool:
    selected = current_balance_mode() if mode is None else normalize_balance_mode(mode)
    return selected == BALANCE_MODE_NORMALIZE


__all__ = [
    "BALANCE_MODE_ENV",
    "BALANCE_MODE_REPORT",
    "BALANCE_MODE_SAFETY",
    "BALANCE_MODE_NORMALIZE",
    "CANONICAL_BALANCE_MODES",
    "DEFAULT_BALANCE_MODE",
    "normalize_balance_mode",
    "current_balance_mode",
    "should_apply_python_safety",
    "should_apply_soft_normalization",
]
