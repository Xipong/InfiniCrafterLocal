from __future__ import annotations

from typing import Any, Final

# Canonical executable trigger vocabulary for real secondary projectiles.
# This is deliberately tiny. New triggers require a complete Python -> DTO -> C#
# vertical slice; do not add authoring aliases or infer triggers from prose.
SECONDARY_TRIGGER_ON_HIT: Final = "on_hit"
SECONDARY_TRIGGER_ON_EXPIRE: Final = "on_expire"
CANONICAL_SECONDARY_TRIGGERS: Final[frozenset[str]] = frozenset({
    SECONDARY_TRIGGER_ON_HIT,
    SECONDARY_TRIGGER_ON_EXPIRE,
})


def normalize_secondary_trigger(value: Any, default: str = SECONDARY_TRIGGER_ON_HIT) -> str:
    if value is None:
        return default
    token = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not token:
        return ""
    return token if token in CANONICAL_SECONDARY_TRIGGERS else ""


__all__ = [
    "CANONICAL_SECONDARY_TRIGGERS",
    "SECONDARY_TRIGGER_ON_EXPIRE",
    "SECONDARY_TRIGGER_ON_HIT",
    "normalize_secondary_trigger",
]
