from __future__ import annotations

"""Cohesive additive material payload definitions used by the canonical VFX owner."""

import math
from typing import Any

MATERIAL_RENDERERS = ("spriteElement", "texturedPath")
ASSET_ID_PATTERN = r"^[A-Za-z0-9_-]{1,48}$"
CURVES = ("linear", "easeIn", "easeOut", "smoothStep")
COLOR_TOKENS = ("white", "gray", "brown", "tan", "red", "orange", "yellow", "gold", "green", "cyan", "blue", "purple", "pink", "black", "effect")
NEUTRAL_FIELDS = {
    "scale": 1, "density": 0, "spread": 0, "jitter": 0, "fadeIn": 0, "fadeOut": 0,
    "signatureWeight": 0, "visualCost": 0, "budgetWeight": 1,
    "emissionMode": "none", "particleRole": "none", "particleSystemId": "none", "textureRole": "none",
}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}


def _number(low: float, high: float, description: str, *, integer: bool = False) -> dict[str, Any]:
    return {"type": "integer" if integer else "number", "minimum": low, "maximum": high, "description": description}


def _profile(maximum: float | None = None) -> dict[str, Any]:
    knot = {"type": "string", "enum": list(COLOR_TOKENS), "description": "Exact RGB token; effect captures existing effect color, white preserves texture RGB. Opacity is separate."} if maximum is None else _number(0, maximum, "Dimensionless multiplier (opacity coefficient for opacityProfile); explicit zero stays zero.")
    return {
        **_object({"start": dict(knot), "middle": dict(knot), "end": dict(knot), "curve": {"type": "string", "enum": list(CURVES)}}),
        "description": "Knots at normalized profile coordinate 0, 0.5, 1: sprite lifetime age, or path profileDomain age/length. Curve per half interval: linear=t; easeIn=t*t; easeOut=1-(1-t)^2; smoothStep=t*t*(3-2*t). Captured immutably at emission.",
    }


def _asset_id_schema() -> dict[str, Any]:
    # JSON Schema pattern uses search semantics: `$` alone admits a final LF.
    # The explicit forbidden-character assertion also expresses whole-string
    # ASCII identity to standard validators without a nonportable regex \Z.
    return {"type": "string", "minLength": 1, "maxLength": 48,
            "pattern": ASSET_ID_PATTERN, "not": {"pattern": r"[^A-Za-z0-9_-]"}}


def texture_schema() -> dict[str, Any]:
    schema = _object({
        "source": {"type": "string", "enum": ["item", "entity", "impact", "asset"]},
        "assetId": {"type": "string", "maxLength": 48},
    })
    schema["description"] = "Explicit exact item/entity/impact image role or one declared asset ID. No paths/URLs; no cross-entity guesses. impact requires that entity's existing impactSprite producer."
    schema["allOf"] = [
        {"if": {"properties": {"source": {"const": "asset"}}, "required": ["source"]},
         "then": {"properties": {"assetId": _asset_id_schema()}}},
        {"if": {"properties": {"source": {"enum": ["item", "entity", "impact"]}}, "required": ["source"]},
         "then": {"properties": {"assetId": {"const": ""}}}},
    ]
    return schema


def asset_schema() -> dict[str, Any]:
    return _object({
        "id": _asset_id_schema(),
        "prompt": {"type": "string", "minLength": 1, "maxLength": 1400, "pattern": r"[\s\S]*\S[\s\S]*", "description": "One isolated texture ingredient consistent with accepted Visual; no UI/text/atlas. A strip may fill its long axis. No weapon/PCA/silhouette heuristics."},
        "negativePrompt": {"type": "string", "maxLength": 700},
        "canvasSize": {"type": "integer", "enum": [16, 24, 32, 48, 64, 96, 128], "description": "Exact final square pixel canvas; independent of gameplay hitbox."},
        "layout": {"type": "string", "enum": ["cutout", "strip"], "description": "cutout fits an isolated soft-alpha subject; strip preserves the full frame/UV through keying+resize, no crop/recenter/refit/rotation. Either can serve either renderer."},
    })


def _when(values: dict[str, Any], consequent: dict[str, Any]) -> dict[str, Any]:
    return {"if": {"properties": values, "required": list(values)}, "then": consequent}


def material_slot_clauses(item_ids: list[str], legacy_renderers: list[str], events: list[str], channels: list[str], path_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sprite = {"rendererKind": {"const": "spriteElement"}}
    path = {"rendererKind": {"const": "texturedPath"}}
    return [
        _when({"rendererKind": {"enum": list(MATERIAL_RENDERERS)}}, {"properties": {"channel": {"enum": [c for c in channels if c not in {"light", "sound"}]}}}),
        _when(sprite, {"required": ["element"], "properties": {"path": {"enum": []}}}),
        _when(path, {"required": ["path"], "properties": {"element": {"enum": []}, "event": {"enum": ["periodic", "on_spawn"]}, "entityId": {"enum": [row["entityId"] for row in path_sources]}}}),
        _when({"rendererKind": {"enum": legacy_renderers}}, {"properties": {"element": {"enum": []}, "path": {"enum": []}}}),
        _when({**sprite, "event": {"const": "periodic"}}, {"properties": {"repeatEvery": {"minimum": 1}}}),
        _when({**sprite, "event": {"enum": [event for event in events if event != "periodic"]}}, {"properties": {"repeatEvery": {"const": 0}}}),
        _when({**sprite, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, {"properties": {"startTick": {"const": 0}}}),
        _when({**sprite, "event": {"enum": ["on_expire", "on_kill"]}}, {"properties": {"element": {"properties": {"attachment": {"const": "world"}}}}}),
        *[_when({**path, "entityId": {"const": row["entityId"]}}, {"properties": {"path": {"properties": {"source": {"enum": row["sources"]}}}}}) for row in path_sources],
        _when({**path, "path": {"properties": {"source": {"enum": ["beam", "whip"]}}, "required": ["source"]}}, {"properties": {"anchor": {"const": "self"}}}),
    ]


def material_texture_clauses(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _when({"rendererKind": {"const": renderer}, "entityId": {"const": row["entityId"]}},
              {"properties": {payload: {"properties": {"texture": {"properties": {"source": {"enum": row["sources"]}}}}}}})
        for row in rows for renderer, payload in (("spriteElement", "element"), ("texturedPath", "path"))
    ]


def runtime_asset_schema() -> dict[str, Any]:
    schema = asset_schema()
    schema["properties"]["prompt"].update(minLength=0, pattern=r"^$|[\s\S]*\S[\s\S]*")
    metadata = {
        "spritePath": {"type": "string"}, "spriteUrl": {"type": "string"},
        "spriteStatus": {"type": "string", "minLength": 1}, "spriteTechnicalScore": {"type": "number"},
    }
    schema["properties"].update(metadata)
    schema["required"].extend(metadata)
    schema["allOf"] = [_when({"prompt": {"const": ""}}, {"properties": {
        "negativePrompt": {"const": ""}, "spritePath": {"minLength": 1},
        "spriteStatus": {"enum": ["generated", "generated_warn_invalid", "fallback"]},
    }})]
    return schema


def element_schema() -> dict[str, Any]:
    return _object({
        "texture": texture_schema(),
        "attachment": {"type": "string", "enum": ["world", "source"], "description": "world freezes event-time frame; source follows that exact live source generation in its forward/normal frame, ends on retirement. World acceleration uses world X/Y; source acceleration uses local frame."},
        "count": _number(0, 64, "Integer elements per emission; zero is silence. Charged when emitted, never per Draw.", integer=True),
        "offsetForwardPx": _number(-128, 128, "Pixels along captured source forward at emission."),
        "offsetSidePx": _number(-128, 128, "Pixels along captured source normal at emission."),
        "speedMinPxPerTick": _number(0, 24, "Pixels per world tick, uniform speed minimum."),
        "speedMaxPxPerTick": _number(0, 24, "Pixels per world tick, uniform speed maximum >= speedMinPxPerTick."),
        "spreadRadians": _number(0, math.tau, "Radians: full cone around captured forward."),
        "inheritVelocity": _number(0, 1, "Fraction of captured engine velocity, converted to pixels per world tick and added once: Projectile.velocity * (1 + extraUpdates), Player.velocity unchanged. This is not measured anchor displacement; a position-driven controller can use engine velocity as steering. Runtime captures the conversion before source retirement; legacy Dust velocity semantics are unchanged."),
        "drag": _number(0, 1, "Velocity retention per world tick (1 keeps velocity; 0 removes it)."),
        "accelerationXPxPerTickSquared": _number(-2, 2, "Pixels per world tick squared, X in selected attachment frame."),
        "accelerationYPxPerTickSquared": _number(-2, 2, "Pixels per world tick squared, Y in selected attachment frame."),
        "rotationRadians": _number(-math.tau, math.tau, "Radians relative to captured forward; never inferred image/PCA axis."),
        "rotationSpeedRadiansPerTick": _number(-1, 1, "Radians per world tick."),
        "widthPx": _number(0, 128, "Pixels along texture X axis, independent of height; zero stays zero."),
        "heightPx": _number(0, 128, "Pixels along texture Y axis, independent of width; zero stays zero."),
        "widthProfile": _profile(4), "heightProfile": _profile(4), "opacityProfile": _profile(1), "colorProfile": _profile(),
    })


def library_particle_schema() -> dict[str, Any]:
    return _object({
        "textureId": {"type": "string", "enum": ["star"], "description": "Exact ParticleLibrary built-in Star texture: opaque grayscale including black texels. Alpha blend includes its black rectangular footprint; additive makes black contribute zero. Choose blend explicitly. Not a motion/weapon preset; no PNG generation."},
        "count": _number(0, 64, "Integer particles per emission; zero is silence; shares existing instance budgets.", integer=True),
        "speedMinPxPerTick": _number(0, 24, "Minimum initial speed in world pixels/world tick."),
        "speedMaxPxPerTick": _number(0, 24, "Maximum initial speed, must be >= speedMinPxPerTick."),
        "spreadRadians": _number(0, math.tau, "Full cone angle around captured source forward, radians."),
        "inheritVelocity": _number(0, 1, "Fraction of captured world-tick engine velocity added once, Projectile.velocity*MaxUpdates or Player.velocity."),
        "drag": _number(0, 1, "Velocity retention per world tick; 1 preserves, 0 removes previous velocity before world acceleration."),
        "accelerationXPxPerTickSquared": _number(-2, 2, "World X acceleration, pixels/world tick squared."),
        "accelerationYPxPerTickSquared": _number(-2, 2, "World Y acceleration, pixels/world tick squared."),
        "widthPx": _number(0, 128, "Full initial width of the library unit quad in world pixels, independent of texture native dimensions; zero stays zero."),
        "heightPx": _number(0, 128, "Full initial height of the library unit quad in world pixels; zero stays zero."),
        "rotationRadians": _number(-math.tau, math.tau, "Initial rotation relative to captured source forward, radians."),
        "rotationSpeedRadiansPerTick": _number(-1, 1, "Spin in radians/world tick."),
        "colorStart": {"type": "string", "enum": list(COLOR_TOKENS), "description": "Initial opaque RGB token; effect captures accepted effect color; no palette-prose parsing."},
        "colorEnd": {"type": "string", "enum": list(COLOR_TOKENS), "description": "Final RGB token, linearly interpolated over individual lifetime."},
        "endScaleMultiplier": _number(0, 4, "Final width/height multiplier, linearly interpolated from 1; zero contracts to nothing."),
        "endOpacity": _number(0, 1, "Final opacity multiplier, linearly interpolated from 1 and multiplied by common alpha once."),
    })


def screen_shake_schema() -> dict[str, Any]:
    return _object({
        "strengthPx": _number(0, 16, "Luminance camera displacement strength in screen pixels before its client screenshake modifier; explicit zero emits no shake."),
        "angularVarianceRadians": _number(0, math.tau, "Random angular variance around the explicitly selected direction, in radians."),
        "directionRadians": _number(-math.tau, math.tau, "Direction angle relative to captured source forward, in radians."),
        "dissipationPxPerFrame": _number(0.01, 16, "Strength removed on each native ModifyScreenPosition visit, not a world-tick lifetime; passed explicitly to Luminance."),
        "taperStartDistancePx": _number(0, 4096, "Distance from resolved event anchor to the viewing player where attenuation begins, in world pixels."),
        "taperEndDistancePx": _number(1, 8192, "Distance where attenuation reaches zero; must exceed taperStartDistancePx."),
    })


def path_schema() -> dict[str, Any]:
    schema = _object({
        "texture": texture_schema(),
        "source": {"type": "string", "enum": ["anchorHistory", "beam", "whip"], "description": "Actual timestamped anchor history or exact accepted beam/whip collision geometry, read-only. Never approximate trajectory/range from item name or sprite. Preserve all collision corners."},
        "historyTicks": _number(0, 32, "World ticks retained: 2..32 for history, 0 for current geometry.", integer=True),
        "minDistancePx": _number(0, 16, "Pixels between accepted history samples; 0 for current geometry."),
        "maxSegmentLengthPx": _number(1, 4096, "Pixels: skip true gaps, never bridge/smooth into invented paths."),
        "widthPx": _number(0, 96, "Authored decorative pixels, not collision geometry width; zero stays zero."),
        "widthProfile": _profile(4), "opacityProfile": _profile(1), "colorProfile": _profile(),
        "profileDomain": {"type": "string", "enum": ["age", "length"], "description": "age uses each retained history sample age/historyTicks; length uses normalized cumulative geometric length. History can select either; current beam/whip geometry requires length."},
        "uvMode": {"type": "string", "enum": ["stretch", "repeat"]},
        "repeatLengthPx": _number(1, 512, "Pixels per texture repeat along cumulative geometric distance. stretch requires 1."),
        "scrollPxPerTick": _number(-32, 32, "UV pixels per world-clock tick; stretch requires 0."),
    })
    schema["allOf"] = [
        _when({"source": {"const": "anchorHistory"}}, {"properties": {"historyTicks": {"minimum": 2}}}),
        _when({"source": {"enum": ["beam", "whip"]}}, {"properties": {"historyTicks": {"const": 0}, "minDistancePx": {"const": 0}, "profileDomain": {"const": "length"}}}),
        _when({"uvMode": {"const": "stretch"}}, {"properties": {"repeatLengthPx": {"const": 1}, "scrollPxPerTick": {"const": 0}}}),
    ]
    return schema
