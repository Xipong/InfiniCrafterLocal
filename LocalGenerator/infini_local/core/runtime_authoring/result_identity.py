from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeResultIdentityProjection:
    """Typed authored result identity projected to the finite Terraria carrier."""

    authored_kind: str
    gameplay_kind: str
    runtime_output_kind: str
    authored_ammo_for: str
    final_ammo_for: str
    unsupported_ammo_for: str


def effective_runtime_result_kind(data: Any) -> str:
    """Canonical authored resultKind: prefer set_item_stats over runtimePlan.

    Parent/economy/placeable gates and runtime validation must share this owner so
    a stats-only or plan-only spelling cannot diverge from final projection.
    """
    if not isinstance(data, dict):
        return ""
    plan = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else data
    if not isinstance(plan, dict):
        return ""
    stats_kind = ""
    calls = plan.get("engineCalls")
    if isinstance(calls, list):
        for raw in calls:
            if not isinstance(raw, dict):
                continue
            fn = str(raw.get("fn") or "").strip().lower()
            if fn != "set_item_stats":
                continue
            params = raw.get("params") if isinstance(raw.get("params"), dict) else raw
            if not isinstance(params, dict):
                continue
            stats_kind = str(params.get("resultKind") or "").strip().lower()
    plan_kind = str(plan.get("resultKind") or "").strip().lower()
    return stats_kind or plan_kind


def project_runtime_result_identity(
    result_kind: Any,
    *,
    ammo_for: Any = "",
    has_root_executor: bool = False,
) -> RuntimeResultIdentityProjection:
    """Project authored resultKind/ammo fields without parent or prose inference."""
    raw_kind = str(result_kind or "generic").strip().lower()
    canonical_kinds = {
        "weapon", "ammo", "consumable_weapon", "tool", "accessory",
        "armor", "potion", "material", "furniture", "generic",
    }
    if raw_kind not in canonical_kinds:
        raise ValueError(f"unsupported_result_kind:{raw_kind}")
    raw_ammo = str(ammo_for or "").strip().lower()
    supported_ammo = raw_ammo in {"arrow", "bullet"}
    canonical_ammo = raw_ammo if supported_ammo else ""
    unsupported_ammo = raw_ammo if raw_ammo and not supported_ammo else ""

    gameplay_kind = "weapon" if raw_kind == "consumable_weapon" else raw_kind
    runtime_output_kind = ""
    final_ammo = raw_ammo
    if raw_kind == "consumable_weapon":
        runtime_output_kind = "consumable_weapon"
        final_ammo = ""
    elif raw_kind == "ammo":
        if not supported_ammo:
            raise ValueError("ammo_result_requires_vanilla_identity")
        if has_root_executor:
            raise ValueError("actual_ammo_cannot_author_generated_root_executor")
        runtime_output_kind = "actual_ammo"
        final_ammo = canonical_ammo

    return RuntimeResultIdentityProjection(
        authored_kind=raw_kind,
        gameplay_kind=gameplay_kind,
        runtime_output_kind=runtime_output_kind,
        authored_ammo_for=raw_ammo,
        final_ammo_for=final_ammo,
        unsupported_ammo_for=unsupported_ammo,
    )


__all__ = [
    "RuntimeResultIdentityProjection",
    "effective_runtime_result_kind",
    "project_runtime_result_identity",
]
