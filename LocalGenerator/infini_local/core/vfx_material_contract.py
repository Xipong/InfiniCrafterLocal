from __future__ import annotations

"""Cohesive additive material payload definitions used by the canonical VFX owner."""

import math
from typing import Any

MATERIAL_RENDERERS = ("spriteElement", "texturedPath")
ASSET_ID_PATTERN = r"^[A-Za-z0-9_-]{1,48}$"
CURVES = ("linear", "easeIn", "easeOut", "smoothStep")


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}


def _number(low: float, high: float, description: str, *, integer: bool = False) -> dict[str, Any]:
    return {"type": "integer" if integer else "number", "minimum": low, "maximum": high, "description": description}


def rgb_schema() -> dict[str, Any]:
    """Canonical opaque RGB shape shared by presentation owners; opacity is separate."""
    return {**_object({channel: {"type": "integer", "minimum": 0, "maximum": 255}
                       for channel in ("r", "g", "b")}),
            "description": "Explicit local RGB bytes; no named colors, global color references or alpha. White preserves texture RGB; opacity is separate."}


def _profile(maximum: float | None = None) -> dict[str, Any]:
    knot = rgb_schema() if maximum is None else _number(0, maximum, "Dimensionless multiplier (opacity coefficient for opacityProfile); explicit zero stays zero.")
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


def material_slot_clauses(item_ids: list[str], simple_renderers: list[str], events: list[str], path_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sprite = {"rendererKind": {"const": "spriteElement"}}
    path = {"rendererKind": {"const": "texturedPath"}}
    return [
        _when(sprite, {"required": ["element"], "properties": {"path": {"enum": []}}}),
        _when(path, {"required": ["path"], "properties": {"element": {"enum": []}, "event": {"enum": ["periodic", "on_spawn"]}, "entityId": {"enum": [row["entityId"] for row in path_sources]}}}),
        _when({"rendererKind": {"enum": simple_renderers}}, {"properties": {"element": {"enum": []}, "path": {"enum": []}}}),
        _when({**sprite, "event": {"const": "periodic"}}, {"properties": {"repeatEvery": {"minimum": 1}}}),
        _when({**sprite, "event": {"enum": [event for event in events if event != "periodic"]}}, {"properties": {"repeatEvery": {"const": 0}}}),
        _when({**sprite, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, {"properties": {"startTick": {"const": 0}}}),
        _when({**sprite, "event": {"enum": ["on_expire", "on_kill"]}}, {"properties": {"element": {"properties": {"attachment": {"const": "world"}}}}}),
        *[_when({**path, "entityId": {"const": row["entityId"]}}, {"properties": {"path": {"properties": {"source": {"enum": row["sources"]}}}}}) for row in path_sources],
        _when({**path, "path": {"properties": {"source": {"enum": ["beam", "whip", "ownerLink"]}}, "required": ["source"]}}, {"properties": {"anchor": {"const": "self"}}}),
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
        "offsetForwardPx": _number(-128, 128, "World pixels along captured source forward at emission."),
        "offsetSidePx": _number(-128, 128, "World pixels along captured source normal at emission."),
        "speedMinPxPerTick": _number(0, 24, "Pixels per world tick, uniform speed minimum."),
        "speedMaxPxPerTick": _number(0, 24, "Pixels per world tick, uniform speed maximum >= speedMinPxPerTick."),
        "spreadRadians": _number(0, math.tau, "Radians: full cone around captured forward."),
        "inheritVelocity": _number(0, 1, "Fraction of captured engine velocity, converted to pixels per world tick and added once: Projectile.velocity * (1 + extraUpdates), Player.velocity unchanged. This is not measured anchor displacement; a position-driven controller can use engine velocity as steering. Runtime captures the conversion before source retirement; Terraria Dust velocity is independent."),
        "drag": _number(0, 1, "Velocity retention per world tick (1 keeps velocity; 0 removes it)."),
        "accelerationXPxPerTickSquared": _number(-2, 2, "Pixels per world tick squared, X in selected attachment frame."),
        "accelerationYPxPerTickSquared": _number(-2, 2, "Pixels per world tick squared, Y in selected attachment frame."),
        "rotationRadians": _number(-math.tau, math.tau, "Radians relative to captured forward; never inferred image/PCA axis."),
        "rotationSpeedRadiansPerTick": _number(-1, 1, "Radians per world tick."),
        "widthPx": _number(0, 128, "World pixels along texture X axis, independent of height; zero stays zero."),
        "heightPx": _number(0, 128, "World pixels along texture Y axis, independent of width; zero stays zero."),
        "widthProfile": _profile(4), "heightProfile": _profile(4), "opacityProfile": _profile(1), "colorProfile": _profile(),
    })


def library_particle_schema() -> dict[str, Any]:
    return _object({
        "textureId": {"type": "string", "enum": ["star"], "description": "Exact ParticleLibrary built-in Star texture: opaque grayscale including black texels. Alpha blend includes its black rectangular footprint; additive makes black contribute zero. Choose blend explicitly. Not a motion/weapon preset; no PNG generation."},
        "count": _number(0, 64, "Integer particles per emission; zero is silence; shares existing instance budgets.", integer=True),
        "speedMinPxPerTick": _number(0, 24, "Minimum initial speed in world pixels/world tick."),
        "speedMaxPxPerTick": _number(0, 24, "Maximum initial speed in world pixels per world tick, must be >= speedMinPxPerTick."),
        "spreadRadians": _number(0, math.tau, "Full cone angle around captured source forward, radians."),
        "inheritVelocity": _number(0, 1, "Fraction of captured world-tick engine velocity added once, Projectile.velocity*MaxUpdates or Player.velocity."),
        "drag": _number(0, 1, "Velocity retention per world tick; 1 preserves, 0 removes previous velocity before world acceleration."),
        "accelerationXPxPerTickSquared": _number(-2, 2, "World X acceleration, pixels/world tick squared."),
        "accelerationYPxPerTickSquared": _number(-2, 2, "World Y acceleration, pixels/world tick squared."),
        "widthPx": _number(0, 128, "Full initial width of the library unit quad in world pixels, independent of texture native dimensions; zero stays zero."),
        "heightPx": _number(0, 128, "Full initial height of the library unit quad in world pixels; zero stays zero."),
        "rotationRadians": _number(-math.tau, math.tau, "Initial rotation relative to captured source forward, radians."),
        "rotationSpeedRadiansPerTick": _number(-1, 1, "Spin in radians/world tick."),
        "colorStart": rgb_schema(),
        "colorEnd": rgb_schema(),
        "endScaleMultiplier": _number(0, 4, "Final width/height multiplier, linearly interpolated from 1; zero contracts to nothing."),
        "endOpacity": _number(0, 1, "Final opacity multiplier, linearly interpolated from 1 and multiplied by common alpha once."),
    })


def screen_shake_schema() -> dict[str, Any]:
    return _object({
        "strengthPx": _number(0, 16, "Luminance camera displacement strength in screen pixels before its client screenshake modifier; explicit zero emits no shake."),
        "angularVarianceRadians": _number(0, math.tau, "Random angular variance around the explicitly selected direction, in radians."),
        "directionRadians": _number(-math.tau, math.tau, "Direction angle relative to captured source forward, in radians."),
        "dissipationPxPerFrame": _number(0.01, 16, "Screen-pixel strength removed on each native ModifyScreenPosition visit, not a world-tick lifetime; passed explicitly to Luminance."),
        "taperStartDistancePx": _number(0, 4096, "Distance from resolved event anchor to the viewing player where attenuation begins, in world pixels."),
        "taperEndDistancePx": _number(1, 8192, "World-pixel distance from event anchor to viewer where attenuation reaches zero; must exceed taperStartDistancePx."),
    })


def path_schema() -> dict[str, Any]:
    schema = _object({
        "texture": texture_schema(),
        "source": {"type": "string", "enum": ["anchorHistory", "beam", "whip", "ownerLink"], "description": "anchorHistory reads timestamped anchors; beam/whip read exact accepted collision geometry. ownerLink explicitly draws a cosmetic straight two-point connector from the explicit ownerAnchor to projectile.Center; no collision/damage or inferred grip. Never approximate trajectory/range from item name or sprite. Preserve all collision corners."},
        "historyTicks": _number(0, 32, "World ticks retained: 2..32 for history, 0 for current geometry.", integer=True),
        "minDistancePx": _number(0, 16, "World pixels between accepted history samples; 0 for current geometry."),
        "maxSegmentLengthPx": _number(1, 4096, "World pixels: skip true gaps, never bridge/smooth into invented paths."),
        "widthPx": _number(0, 96, "Authored decorative world pixels, not collision geometry width; zero stays zero."),
        "widthProfile": _profile(4), "opacityProfile": _profile(1), "colorProfile": _profile(),
        "profileDomain": {"type": "string", "enum": ["age", "length"], "description": "age uses each retained history sample age/historyTicks; length uses normalized cumulative geometric length. History can select either; current beam/whip/ownerLink geometry requires length."},
        "uvMode": {"type": "string", "enum": ["stretch", "repeat"]},
        "repeatLengthPx": _number(1, 512, "World pixels per texture repeat along cumulative geometric distance. stretch requires 1."),
        "scrollPxPerTick": _number(-32, 32, "UV pixels per world-clock tick; stretch requires 0."),
    })
    schema["properties"]["ownerAnchor"] = {
        "type": "string", "enum": ["mountedCenter", "frontHand"],
        "description": "Required only for source=ownerLink; forbidden for every other source. mountedCenter reads exact owner.MountedCenter, not a hand. frontHand reads native current composite front hand only while compositeFrontArm.enabled; unavailable/disabled pose refuses and retires the connector, never falls back to center or stale pose. No guessed skin-frame/PNG grip or offsets."
    }
    schema["allOf"] = [
        _when({"source": {"const": "ownerLink"}}, {"required": ["ownerAnchor"]}),
        _when({"source": {"enum": ["anchorHistory", "beam", "whip"]}}, {"properties": {"ownerAnchor": {"enum": []}}}),
        _when({"source": {"const": "anchorHistory"}}, {"properties": {"historyTicks": {"minimum": 2}}}),
        _when({"source": {"enum": ["beam", "whip", "ownerLink"]}}, {"properties": {"historyTicks": {"const": 0}, "minDistancePx": {"const": 0}, "profileDomain": {"const": "length"}}}),
        _when({"uvMode": {"const": "stretch"}}, {"properties": {"repeatLengthPx": {"const": 1}, "scrollPxPerTick": {"const": 0}}}),
    ]
    return schema


# Model spelling only. Persisted material schemas and the renderer retain their
# established keys, units, ranges and clocks. These aliases never touch gameplay.
_VFX_MODEL_FIELDS = {
    "offsetForwardPx": "forwardOffset", "offsetSidePx": "sideOffset",
    "speedMinPxPerTick": "speedMin", "speedMaxPxPerTick": "speedMax",
    "spreadRadians": "coneAngle", "accelerationXPxPerTickSquared": "accelX",
    "accelerationYPxPerTickSquared": "accelY", "rotationRadians": "rotation",
    "rotationSpeedRadiansPerTick": "rotationSpeed", "widthPx": "width",
    "heightPx": "height", "minDistancePx": "minDistance",
    "maxSegmentLengthPx": "maxGap", "repeatLengthPx": "repeatLength",
    "scrollPxPerTick": "scrollSpeed", "strengthPx": "strength",
    "angularVarianceRadians": "angleVariance", "directionRadians": "direction",
    "dissipationPxPerFrame": "dissipationPerCameraVisit",
    "taperStartDistancePx": "fadeStartDistance", "taperEndDistancePx": "fadeEndDistance",
    "endScaleMultiplier": "endScale",
}
_VFX_MATERIAL_FIELDS = frozenset(("element", "particle", "path", "screenShake"))


def _material_names(kind: str) -> dict[str, str]:
    factories = {"element": element_schema, "particle": library_particle_schema,
                 "path": path_schema, "screenShake": screen_shake_schema}
    return {key: alias for key, alias in _VFX_MODEL_FIELDS.items()
            if key in factories[kind]()["properties"]}


def _model_terms(text: str) -> str:
    """Only for contract-authored descriptions, never user artwork or identifiers."""
    import re
    return re.sub(r"\b(" + "|".join(_VFX_MODEL_FIELDS) + r")\b",
                  lambda match: _VFX_MODEL_FIELDS[match.group()], text)


def vfx_model_payload(value: Any, *, to_wire: bool = False) -> Any:
    """Lossless slot-payload spelling adapter; unrelated/unknown data stays literal.

    to_wire decodes fresh model output: long persisted-wire spellings are not
    aliases in that language. Existing candidates use the forward projection.
    """
    import copy
    def material(row: Any, kind: str) -> Any:
        if not isinstance(row, dict):
            return copy.deepcopy(row)
        fields = _material_names(kind)
        names = {alias: key for key, alias in fields.items()} if to_wire else fields
        result: dict[str, Any] = {}
        for key, item in row.items():
            if to_wire and key in fields:
                raise ValueError(f"persisted-wire spelling is not a model field: {key}")
            name = names.get(key, key)
            if name in result:
                raise ValueError(f"ambiguous VFX material field: {name}")
            result[name] = copy.deepcopy(item)
        return result

    def slot(row: Any) -> Any:
        if not isinstance(row, dict):
            return copy.deepcopy(row)
        return {key: material(item, key) if key in _VFX_MATERIAL_FIELDS else copy.deepcopy(item)
                for key, item in row.items()}

    if not isinstance(value, dict):
        return copy.deepcopy(value)
    return {key: [slot(row) for row in item] if key in {"slots", "slotsUpsert"} and isinstance(item, list)
            else copy.deepcopy(item) for key, item in value.items()}


def vfx_model_schema(schema: Any, *, context: str = "") -> Any:
    """Project only slot/material schema paths, including frozen Repair literals."""
    import copy
    if isinstance(schema, list):
        return [vfx_model_schema(row, context=context) for row in schema]
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)
    result = {}
    names = _material_names(context) if context in _VFX_MATERIAL_FIELDS else {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            result[key] = {}
            for name, child in value.items():
                child_context = ("slots" if context == "" and name in {"slots", "slotsUpsert"}
                                 else name if context == "slot" and name in _VFX_MATERIAL_FIELDS
                                 else "literal")
                result[key][names.get(name, name)] = vfx_model_schema(child, context=child_context)
        elif key == "items" and context == "slots":
            result[key] = vfx_model_schema(value, context="slot")
        elif key == "required" and isinstance(value, list) and names:
            result[key] = [names.get(name, name) for name in value]
        elif key == "description" and isinstance(value, str):
            result[key] = _model_terms(value)
        elif key == "const":
            if names and isinstance(value, dict):
                result[key] = {names.get(name, name): copy.deepcopy(item) for name, item in value.items()}
            elif context == "slot" and isinstance(value, dict):
                result[key] = vfx_model_payload({"slots": [value]})["slots"][0]
            elif context == "slots" and isinstance(value, list):
                result[key] = vfx_model_payload({"slots": value})["slots"]
            else:
                result[key] = copy.deepcopy(value)
        else:
            result[key] = vfx_model_schema(value, context=context)
    return result


def vfx_model_context(packet: dict[str, Any]) -> dict[str, Any]:
    """Project only VFX-owned context; preserve accepted gameplay and parent facts."""
    import copy
    import re
    result = copy.deepcopy(packet)
    if "outputSchema" in result:
        result["outputSchema"] = vfx_model_schema(result["outputSchema"])
    for key in ("brokenFragments", "validGeneratedContext"):
        if key in result:
            result[key] = vfx_model_payload(result[key])

    def contract_terms(value: Any) -> Any:
        if isinstance(value, str):
            return _model_terms(value)
        if isinstance(value, list):
            return [contract_terms(row) for row in value]
        if isinstance(value, dict):
            return {key: contract_terms(row) for key, row in value.items()}
        return value

    for key in ("runtimeVocabulary", "runtimeVocabularyReadOnly", "rules"):
        if key in result:
            result[key] = contract_terms(result[key])

    def path(value: str) -> str:
        return re.sub(r"\b(element|particle|path|screenShake)\.([A-Za-z][A-Za-z0-9]*)",
                      lambda m: m[1] + "." + _material_names(m[1]).get(m[2], m[2]), value)

    scope = result.get("repairScope", {})
    for row in scope.get("fieldPermissions", {}).get("slots", []):
        for key in ("paths", "deletePaths"):
            if key in row:
                row[key] = [path(value) for value in row[key]]
    if "errorPaths" in scope:
        scope["errorPaths"] = [path(value) for value in scope["errorPaths"]]
    for error in result.get("exactErrors", []):
        if isinstance(error.get("path"), str):
            error["path"] = path(error["path"])
        if isinstance(error.get("message"), str):
            error["message"] = _model_terms(error["message"])
    return result
