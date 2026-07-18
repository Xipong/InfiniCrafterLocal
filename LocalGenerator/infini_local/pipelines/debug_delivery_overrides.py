from __future__ import annotations

from copy import deepcopy
from typing import Any

from infini_local.core.env_utils import env_bool, env_int


_ENABLED_ENV = "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED"
_MINIMUM_ENV = "INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD"
_ATTACK_CONSUMABLE_KINDS = frozenset({"weapon", "ammo"})
_EXCLUDED_CONSUMABLE_KINDS = frozenset({"potion", "material"})


def _positive_int(value: Any, default: int = 1) -> int:
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return max(1, int(default))


def _is_attacking_consumable(data: dict[str, Any]) -> bool:
    gameplay_candidate = data.get("gameplay")
    gameplay: dict[str, Any] = gameplay_candidate if isinstance(gameplay_candidate, dict) else {}
    if gameplay.get("consumable") is not True:
        return False

    attack_candidate = data.get("attack")
    attack: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}
    kind = str(gameplay.get("kind") or data.get("category") or "").strip().lower()
    if kind in _EXCLUDED_CONSUMABLE_KINDS:
        return False
    ammo_for = str(gameplay.get("ammoFor") or "").strip()
    return attack.get("enabled") is True or kind in _ATTACK_CONSUMABLE_KINDS or bool(ammo_for)


def apply_debug_attack_consumable_minimum_for_delivery(data: dict[str, Any]) -> dict[str, Any]:
    """Overlay a debug-only minimum batch size on the delivered copy.

    The canonical authored recipe is never mutated. This runs after prompt,
    authoring, compiler/provenance validation, and cache persistence.
    """
    if not env_bool(_ENABLED_ENV, False) or not _is_attacking_consumable(data):
        return data

    delivered = deepcopy(data)
    gameplay_candidate = delivered.get("gameplay")
    if not isinstance(gameplay_candidate, dict):
        return delivered

    minimum = env_int(_MINIMUM_ENV, 10, lo=1, hi=999)
    gameplay_candidate["maxStack"] = max(_positive_int(gameplay_candidate.get("maxStack")), minimum)
    gameplay_candidate["craftYield"] = max(_positive_int(gameplay_candidate.get("craftYield")), minimum)
    return delivered


__all__ = ["apply_debug_attack_consumable_minimum_for_delivery"]
