"""Explicit bounded cosmetic geometry, independent of gameplay and legacy presets."""
from __future__ import annotations

import math
from typing import Any

from infini_local.core.vfx_material_contract import _number, rgb_schema

LEGACY_SHAPE_RENDERERS = frozenset({
    "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes", "ghostArc", "impactRing",
})
SHAPE_SEMANTICS = (
    "Bounded cosmetic line/arc/wave/orbit instances, no PNG, Dust, lighting or gameplay. "
    "All dimensions, colors, lifetime opacity and motion are explicit independent controls. "
    "duration is individual world-tick lifetime; repeatEvery is emission cadence, never animation period. "
    "Periodic repeatEvery>=1; event repeatEvery=0 with startTick delay. Item periodic startTick=0. "
    "world attachment freezes event pose; source attachment follows the exact live source generation "
    "and ends on retirement. Expire/kill events require world attachment. "
    "Color, opacity and arc/orbit radius interpolate linearly over lifetime exactly once; "
    "there is no additional automatic fade. Zero dimensions/count/opacity remain silent. "
    "Rotation is relative to source forward; angular speed is per world tick. "
    "Arc starts at rotation and sweeps sweepRadians; full tau is a ring, tail opacity is explicit. "
    "Wave is forward*length*t + normal*amplitude*sin(tau*cycles*t+phase+phaseSpeed*age). "
    "Orbit draws evenly spaced square motes. Each segment/mote consumes shared draw budget."
)


def shape_schema() -> dict[str, Any]:
    number = _number
    common = {
        "kind": {"type": "string", "enum": ["line", "arc", "wave", "orbit"]},
        "attachment": {"type": "string", "enum": ["world", "source"]},
        "offsetForwardPx": number(-128, 128, "Offset along captured/source forward, world pixels."),
        "offsetSidePx": number(-128, 128, "Offset along captured/source normal, world pixels."),
        "rotationRadians": number(-math.tau, math.tau, "Initial radians relative to captured/source forward."),
        "rotationSpeedRadiansPerTick": number(-1, 1, "Radians per world tick, independent of lifetime and cadence."),
        "colorStart": rgb_schema(), "colorEnd": rgb_schema(),
        "opacityStart": number(0, 1, "Initial opacity; interpolated once over individual lifetime."),
        "opacityEnd": number(0, 1, "Final opacity; no additional automatic fade."),
    }
    fields = {
        "lengthPx": number(0, 512, "World-pixel forward length; zero remains invisible."),
        "widthPx": number(0, 128, "World-pixel stroke width, including subpixel; zero remains invisible."),
        "radiusStartPx": number(0, 256, "Initial world-pixel radius, linearly interpolated over lifetime."),
        "radiusEndPx": number(0, 256, "Final world-pixel radius, independent of stroke/mote size."),
        "sweepRadians": number(-math.tau, math.tau, "Signed arc sweep from current rotation; tau gives full ring."),
        "segments": number(1, 64, "Integer geometric tessellation only, not particles/cadence.", integer=True),
        "tailOpacityStart": number(0, 1, "Opacity multiplier at geometric start of arc."),
        "tailOpacityEnd": number(0, 1, "Opacity multiplier at geometric end; interpolated along arc once."),
        "amplitudePx": number(0, 128, "World-pixel sine amplitude, independent of length/width."),
        "cycles": number(0, 8, "Sine cycles along complete wave length."),
        "phaseRadians": number(-math.tau, math.tau, "Initial sine phase in radians."),
        "phaseSpeedRadiansPerTick": number(-1, 1, "Sine phase radians per world tick, independent of rotation."),
        "count": number(0, 64, "Integer evenly spaced square motes; zero stays silent.", integer=True),
        "moteSizePx": number(0, 128, "World-pixel square side, independent of orbit radius/count."),
    }
    kinds = {
        "line": {"lengthPx", "widthPx"},
        "arc": {"radiusStartPx", "radiusEndPx", "sweepRadians", "widthPx", "segments", "tailOpacityStart", "tailOpacityEnd"},
        "wave": {"lengthPx", "amplitudePx", "cycles", "phaseRadians", "phaseSpeedRadiansPerTick", "widthPx", "segments"},
        "orbit": {"count", "radiusStartPx", "radiusEndPx", "moteSizePx"},
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {**common, **fields}, "required": list(common),
        "allOf": [
            {"if": {"properties": {"kind": {"const": kind}}, "required": ["kind"]},
             "then": {"required": sorted(owned), "properties": {name: {"enum": []} for name in sorted(set(fields) - owned)}}}
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
