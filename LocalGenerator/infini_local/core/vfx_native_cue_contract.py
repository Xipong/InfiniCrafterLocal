"""Explicit native Dust/light emission parameters; no visual preset expansion."""
from __future__ import annotations

import math
from typing import Any

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx_spawn_contract import spawn_schema
from infini_local.core.vfx_material_contract import _number, _object

NATIVE_CUE_RENDERERS = ("nativeDust", "nativeLight")
NATIVE_DUST_TYPES = ("GemDiamond", "TintableDustLighted", "Glass", "Smoke", "Electric")
NATIVE_DUST_SEMANTICS = (
    "Explicit emission into Terraria native Dust, not a custom particle simulation. "
    "The selected native type owns subsequent animation, motion, tint and lifetime. "
    "Count, size, initial velocity, native alpha and gravity flag are independent. "
    "directionFrame selects world +X or captured source forward; angleOffsetRadians offsets the cone center. "
    "Angular distribution random samples uniformly; even spans partial-cone endpoints, or divides a full "
    "circle without duplicating its endpoint. Even distribution with count one uses the cone center. Speed is uniform "
    "between speedMinPxPerTick and speedMaxPxPerTick; source velocity is multiplied "
    "only by inheritVelocity. Identical emission math for item and projectile. "
    "Zero count or size emits nothing. Native alpha is Terraria's 0..255 parameter, "
    "not an opacity multiplier. No inferred Smoke gravity or inherited velocity."
)
NATIVE_LIGHT_SEMANTICS = (
    "One engine-tick native world-light cue: RGB multiplied by explicit intensity "
    "and client light multiplier, identically for item and projectile. Zero intensity "
    "is silent. No sprite, particles or implicit lifetime."
)
NATIVE_CUE_TIMING = (
    "Periodic repeatEvery>=1 is exact emission cadence, never density-derived; "
    "event repeatEvery=0 and startTick is an actual delayed emission from captured "
    "source frame. Projectile periodic startTick is source age gate; item periodic "
    "startTick=0 because there is no item-age clock."
)


def native_dust_schema(*, persisted_wire: bool = False) -> dict[str, Any]:
    schema = {**_object({
        "spawn": spawn_schema(),
        "type": {"type": "string", "enum": list(NATIVE_DUST_TYPES)},
        "count": _number(0, 64, "Integer emissions before shared/client budgets; zero is silent.", integer=True),
        "size": _number(0, 3, "Native Dust size multiplier, independent of velocity/count; zero is silent."),
        "speedMinPxPerTick": _number(0, 24, "Minimum initial speed in world pixels/world tick."),
        "speedMaxPxPerTick": _number(0, 24, "Maximum initial speed, at least speedMinPxPerTick."),
        "angularDistribution": {"type": "string", "enum": ["random", "even"]},
        "directionFrame": {"type": "string", "enum": ["world", "source"]},
        "angleOffsetRadians": _number(-math.tau, math.tau, "Cone center offset from world +X or captured source forward."),
        "spreadRadians": _number(0, math.tau, "Full cone width around selected frame plus offset; tau is full circle."),
        "inheritVelocity": _number(0, 1, "Explicit source-velocity multiplier added to initial velocity."),
        "nativeAlpha": _number(0, 255, "Terraria Dust alpha byte, not opacity; native type controls its use.", integer=True),
        "noGravity": {"type": "boolean", "description": "Exact native Dust noGravity flag; never inferred from type."},
    }), "description": NATIVE_DUST_SEMANTICS}
    if persisted_wire:
        schema["required"] = [name for name in schema["required"] if name not in {"angularDistribution", "directionFrame", "angleOffsetRadians", "spawn"}]
    return schema


def native_light_schema() -> dict[str, Any]:
    return {**_object({"intensity": _number(0, 1.2, "World light RGB multiplier before client option; zero is silent.")}),
            "description": NATIVE_LIGHT_SEMANTICS}


def native_cue_slot_clauses(item_ids: list[str], renderers: list[str], events: list[str]) -> list[dict[str, Any]]:
    def when(values: dict[str, Any], then: dict[str, Any]) -> dict[str, Any]:
        return {"if": {"properties": values, "required": list(values)}, "then": then}
    selected = {"rendererKind": {"enum": list(NATIVE_CUE_RENDERERS)}}
    clauses = []
    for renderer, payload in (("nativeDust", "dust"), ("nativeLight", "light")):
        clauses.extend([
            when({"rendererKind": {"const": renderer}}, {"required": [payload]}),
            when({"rendererKind": {"enum": [r for r in renderers if r != renderer]}},
                 {"properties": {payload: {"enum": []}}}),
        ])
    clauses.extend([
        when(selected, {"required": ["color", "startTick", "repeatEvery"],
                        "properties": {key: {"enum": []} for key in (
                            "scale", "density", "spread", "alpha", "duration", "phaseOffset",
                            "particleSystemId", "blend", "layer", "textureRole")}}),
        when({**selected, "event": {"const": "periodic"}}, {"properties": {"repeatEvery": {"minimum": 1}}}),
        when({**selected, "event": {"enum": [e for e in events if e != "periodic"]}}, {"properties": {"repeatEvery": {"const": 0}}}),
        when({**selected, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, {"properties": {"startTick": {"const": 0}}}),
    ])
    return clauses


def native_cue_errors(slot: Any, path: str = "$", *, persisted_wire: bool = False) -> list[dict[str, Any]]:
    """Payload admission plus relational bounds; never normalize or fill fields.

    The canonical slot owner validates common fields and event compatibility.
    """
    if not isinstance(slot, dict):
        return []  # Canonical slot schema owns the object/type error.
    renderer = slot.get("rendererKind")
    if renderer not in NATIVE_CUE_RENDERERS:
        return []
    key, schema = ("dust", native_dust_schema(persisted_wire=persisted_wire)) if renderer == "nativeDust" else ("light", native_light_schema())
    if persisted_wire:
        schema["x-nativeFloat32Bounds"] = True
    payload = slot.get(key)
    errors = [{"path": str(error.get("path") or path),
               "message": f"schema {error.get('kind')}: expected {error.get('expected')!r}"}
              for error in strict_schema_errors(payload, schema, path=f"{path}.{key}")]
    if renderer == "nativeDust" and isinstance(payload, dict):
        low, high = payload.get("speedMinPxPerTick"), payload.get("speedMaxPxPerTick")
        properties = schema["properties"]
        if (not strict_schema_errors(low, properties["speedMinPxPerTick"])
                and not strict_schema_errors(high, properties["speedMaxPxPerTick"])
                and high < low):
            errors.append({"path": f"{path}.dust.speedMaxPxPerTick", "message": "must be >= speedMinPxPerTick"})
    return errors
