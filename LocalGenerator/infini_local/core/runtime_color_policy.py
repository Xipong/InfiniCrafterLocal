from __future__ import annotations

from typing import Any

# Exact current runtime/presentation color vocabulary.  Rich image palettes stay in
# visual prompts; these names are only for bounded C# light/dust/tint execution.
CANONICAL_RUNTIME_COLORS = frozenset({
    "white", "gray", "brown", "tan", "red", "orange", "yellow",
    "gold", "green", "cyan", "blue", "purple", "pink",
})

_EFFECT_RUNTIME_COLOR = {
    "none": "white",
    "electric": "cyan",
    "slime": "green",
    "star": "gold",
    "flame": "orange",
    "frost": "blue",
    "leaf": "green",
    "shadow": "purple",
    "poison": "green",
    "blood": "red",
    "honey": "gold",
    "sand": "tan",
    "lunar": "cyan",
    "heal": "pink",
    "holy": "gold",
    "smoke": "gray",
}


def normalize_runtime_color(value: Any, fallback: str = "") -> str:
    token = str(value or "").strip().lower()
    return token if token in CANONICAL_RUNTIME_COLORS else fallback


def runtime_color_for_effect(effect: Any) -> str:
    return _EFFECT_RUNTIME_COLOR.get(str(effect or "none").strip().lower(), "white")


__all__ = ["CANONICAL_RUNTIME_COLORS", "normalize_runtime_color", "runtime_color_for_effect"]
