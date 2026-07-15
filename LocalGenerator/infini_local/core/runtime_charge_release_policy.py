from __future__ import annotations

from typing import Any

CHARGE_RELEASE_RUNTIME_FAMILY = "charge_release"
CHARGE_TICKS_MIN = 1
CHARGE_TICKS_MAX = 300
CHARGE_POWER_MIN = 1.0
CHARGE_POWER_MAX = 3.0
CHARGE_RELEASE_DELIVERIES = frozenset({"shoot", "cast", "throw"})


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def apply_charge_release_contract(patch: dict[str, Any]) -> None:
    """Apply structural charge-release invariants without inventing charge numbers."""
    if _token(patch.get("runtimeFamily")) != CHARGE_RELEASE_RUNTIME_FAMILY:
        return
    delivery = _token(patch.get("delivery"))
    if delivery not in CHARGE_RELEASE_DELIVERIES:
        raise ValueError("charge_release_requires_delivery_shoot_cast_or_throw")
    if _token(patch.get("ammoFor") or patch.get("ammoKind")):
        raise ValueError("charge_release_does_not_support_vanilla_ammo")
    patch["channelUse"] = True
    patch["hideUseGraphic"] = True
    patch["disableItemMeleeHitbox"] = True
    patch["ownerHitCheck"] = True
    if patch.get("chargeTicks") not in (None, ""):
        patch["chargeTicks"] = max(CHARGE_TICKS_MIN, min(CHARGE_TICKS_MAX, int(float(patch["chargeTicks"]))))
    if patch.get("chargePowerMultiplier") not in (None, ""):
        patch["chargePowerMultiplier"] = round(
            max(CHARGE_POWER_MIN, min(CHARGE_POWER_MAX, float(patch["chargePowerMultiplier"]))),
            3,
        )


__all__ = [
    "CHARGE_RELEASE_RUNTIME_FAMILY",
    "CHARGE_RELEASE_DELIVERIES",
    "CHARGE_TICKS_MIN",
    "CHARGE_TICKS_MAX",
    "CHARGE_POWER_MIN",
    "CHARGE_POWER_MAX",
    "apply_charge_release_contract",
]
