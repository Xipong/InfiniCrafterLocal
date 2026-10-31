"""Explicit bounded cosmetic geometry, independent of gameplay and legacy presets."""
from __future__ import annotations

import math
from typing import Any

from infini_local.core.vfx_material_contract import _number, rgb_schema

LEGACY_SHAPE_RENDERERS = frozenset({
    "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes", "ghostArc", "impactRing",
})
SHAPE_SEMANTICS = (
    "Bounded cosmetic line/arc/wave/orbit/sector instances, no PNG, Dust, lighting or gameplay. "
    "All dimensions, colors, lifetime opacity and motion are explicit independent controls. "
    "duration is individual 1..120 world-tick lifetime; repeatEvery is emission cadence, never animation period. "
    "Periodic repeatEvery>=1; event repeatEvery=0 with startTick delay. Item periodic startTick=0. "
    "world attachment freezes event pose; source attachment follows the exact live source generation "
    "and ends on retirement. Expire/kill events require world attachment. "
    "Color and arc/orbit radius interpolate linearly; opacityCurve eases opacity over the full lifetime exactly once; "
    "there is no additional automatic fade. Zero dimensions/count/opacity remain silent. "
    "rotationFrame selects world +X or source forward for angular motion; offsets stay in source axes. Angular speed is per world tick. "
    "Arc starts at rotation and sweeps sweepRadians; full tau is a ring, tail opacity is explicit. "
    "Sector fills the area between explicit inner/outer radii, linearly interpolated over lifetime; inner<=outer at both endpoints. "
    "Inner zero gives a disk/wedge, positive inner radius a ring/annular sector; equal radii or zero sweep are silent. "
    "Sector starts at rotation and sweeps signed sweepRadians, with no automatic glow, feathering or collision. "
    "Wave is forward*length*t + normal*amplitude*sin(tau*cycles*t+phase+phaseSpeed*age). "
    "Orbit draws evenly spaced square motes; moteOrientation and moteRotationRadians control their "
    "orientation independently of orbital motion. Each segment/mote consumes shared draw budget."
)


def shape_schema(*, persisted_wire: bool = False) -> dict[str, Any]:
    number = _number
    common = {
        "kind": {"type": "string", "enum": ["line", "arc", "wave", "orbit", "sector"]},
        "attachment": {"type": "string", "enum": ["world", "source"]},
        "offsetForwardPx": number(-128, 128, "Offset along captured/source forward, world pixels."),
        "offsetSidePx": number(-128, 128, "Offset along captured/source normal, world pixels."),
        "rotationFrame": {"type": "string", "enum": ["world", "source"], "description": "Angular basis: world +X or captured/live source forward. Offsets remain in source axes independently."},
        "rotationRadians": number(-math.tau, math.tau, "Initial radians relative to the selected rotationFrame."),
        "rotationSpeedRadiansPerTick": number(-math.tau, math.tau, "Radians per world tick, independent of lifetime and cadence."),
        "colorStart": rgb_schema(), "colorEnd": rgb_schema(),
        "opacityCurve": {"type": "string", "enum": ["linear", "easeIn", "easeOut", "smoothStep"], "description": "Easing applied once over complete normalized lifetime to opacity endpoints."},
        "opacityStart": number(0, 1, "Initial opacity; interpolated once over individual lifetime."),
        "opacityEnd": number(0, 1, "Final opacity; no additional automatic fade."),
    }
    fields = {
        "lengthPx": number(0, 512, "World-pixel forward length; zero remains invisible."),
        "widthPx": number(0, 128, "World-pixel stroke width, including subpixel; zero remains invisible."),
        "radiusStartPx": number(0, 256, "Initial world-pixel radius, linearly interpolated over lifetime."),
        "radiusEndPx": number(0, 256, "Final world-pixel radius, independent of stroke/mote size."),
        **{f"{edge}Radius{endpoint}Px": number(0, 256, f"{edge.title()} radius at lifetime {endpoint.lower()}, world pixels; inner must not exceed outer.")
           for edge in ("inner", "outer") for endpoint in ("Start", "End")},
        "sweepRadians": number(-math.tau, math.tau, "Signed arc/sector sweep from current rotation; +/-tau makes a full turn."),
        "segments": number(1, 64, "Integer geometric tessellation only: sector requires 3..64, arc/wave 1..64; not particles/cadence.", integer=True),
        "tailOpacityStart": number(0, 1, "Opacity multiplier at geometric start of arc."),
        "tailOpacityEnd": number(0, 1, "Opacity multiplier at geometric end; interpolated along arc once."),
        "amplitudePx": number(0, 128, "World-pixel sine amplitude, independent of length/width."),
        "cycles": number(0, 8, "Sine cycles along complete wave length."),
        "phaseRadians": number(-math.tau, math.tau, "Initial sine phase in radians."),
        "phaseSpeedRadiansPerTick": number(-math.tau, math.tau, "Sine phase radians per world tick, independent of rotation."),
        "count": number(0, 64, "Integer evenly spaced square motes; zero stays silent.", integer=True),
        "moteOrientation": {"type": "string", "enum": ["world", "orbit"], "description": "world fixes square orientation to world +X; orbit follows current orbit angle. Independent of mote position."},
        "moteRotationRadians": number(-math.tau, math.tau, "Square angle relative to explicitly selected orientation frame."),
        "moteSizePx": number(0, 128, "World-pixel square side, independent of orbit radius/count."),
    }
    kinds = {
        "line": {"lengthPx", "widthPx"},
        "arc": {"radiusStartPx", "radiusEndPx", "sweepRadians", "widthPx", "segments", "tailOpacityStart", "tailOpacityEnd"},
        "wave": {"lengthPx", "amplitudePx", "cycles", "phaseRadians", "phaseSpeedRadiansPerTick", "widthPx", "segments"},
        "sector": {"innerRadiusStartPx", "innerRadiusEndPx", "outerRadiusStartPx", "outerRadiusEndPx", "sweepRadians", "segments"},
        "orbit": {"count", "radiusStartPx", "radiusEndPx", "moteSizePx", "moteOrientation", "moteRotationRadians"},
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {**common, **fields}, "required": [name for name in common if not persisted_wire or name not in {"opacityCurve", "rotationFrame"}],
        "allOf": [
            {"if": {"properties": {"kind": {"const": kind}}, "required": ["kind"]},
             "then": {"required": sorted(owned - ({"moteOrientation", "moteRotationRadians"} if persisted_wire else set())), "properties": {**{name: {"enum": []} for name in sorted(set(fields) - owned)},
                                            **({"segments": {"minimum": 3}} if kind == "sector" else {})}}}
            for kind, owned in kinds.items()
        ],
    }


def shape_slot_clauses(item_ids: list[str], renderers: list[str], events: list[str]) -> list[dict[str, Any]]:
    def when(values: dict[str, Any], then: dict[str, Any]) -> dict[str, Any]:
        return {"if": {"properties": values, "required": list(values)}, "then": then}
    selected = {"rendererKind": {"const": "shape"}}
    return [
        when(selected, {"required": ["shape"], "properties": {"phaseOffset": {"enum": []}}}),
        when({"rendererKind": {"enum": [r for r in renderers if r != "shape"]}}, {"properties": {"shape": {"enum": []}}}),
        when({**selected, "event": {"const": "periodic"}}, {"properties": {"repeatEvery": {"minimum": 1}}}),
        when({**selected, "event": {"enum": [e for e in events if e != "periodic"]}}, {"properties": {"repeatEvery": {"const": 0}}}),
        when({**selected, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, {"properties": {"startTick": {"const": 0}}}),
        when({**selected, "event": {"enum": ["on_expire", "on_kill"]}}, {"properties": {"shape": {"properties": {"attachment": {"const": "world"}}}}}),
    ]


def shape_slot_errors(slot: dict[str, Any], path: str) -> list[dict[str, str]]:
    from infini_local.core.schema_validation import strict_schema_errors
    shape = slot.get("shape")
    if slot.get("rendererKind") != "shape" or not isinstance(shape, dict) or shape.get("kind") != "sector":
        return []
    properties = shape_schema()["properties"]
    errors = []
    for endpoint in ("Start", "End"):
        inner, outer = f"innerRadius{endpoint}Px", f"outerRadius{endpoint}Px"
        if (not strict_schema_errors(shape.get(inner), properties[inner])
                and not strict_schema_errors(shape.get(outer), properties[outer])
                and shape[inner] > shape[outer]):
            errors.append({"path": f"{path}.shape.{outer}", "message": f"must be >= {inner}"})
    return errors
