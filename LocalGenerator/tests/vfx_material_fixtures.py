"""Canonical hand-authored material inputs and exact offline Director/Repair packet capture."""
from __future__ import annotations

import json
from typing import Any
from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

def _data(capability: str = "") -> dict[str, Any]:
    return compile_runtime_program(build_capability_witness(capability) if capability else build_runtime_fixture("workbench_blade"))

def _legacy(data: dict[str, Any]) -> dict[str, Any]:
    item_id = data["runtimeProgram"]["itemEntityId"]
    return {
        "schema": vfx.VFX_DIRECTOR_SCHEMA,
        "slots": [{
            "color": {"r": 17, "g": 93, "b": 241},
            "id": "old_slot", "entityId": item_id, "event": "on_use", "rendererKind": "impactRing",
            "anchor": "self", "blend": "alpha",
            "layer": "BeforeProjectiles", "particleSystemId": "none", "scale": 1.0,
            "density": 0.4, "duration": 20, "alpha": 0.8, "spread": 0.1,
            "startTick": 0, "repeatEvery": 0,
        }],
    }

def _shape(data: dict[str, Any]) -> dict[str, Any]:
    """Explicit expanding arc: authored dimensions, colors and opacity, no preset."""
    from math import tau
    return {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": [{
        "id": "explicit_shape", "entityId": data["runtimeProgram"]["itemEntityId"],
        "event": "on_use", "rendererKind": "shape", "anchor": "self", "blend": "additive",
        "layer": "AfterProjectiles", "startTick": 0, "repeatEvery": 0, "duration": 20,
        "shape": {"kind": "arc", "attachment": "world", "offsetForwardPx": 0, "offsetSidePx": 0,
            "rotationRadians": 0, "rotationSpeedRadiansPerTick": 0,
            "colorStart": {"r": 17, "g": 93, "b": 241}, "colorEnd": {"r": 0, "g": 30, "b": 255},
            "opacityStart": .8, "opacityEnd": 0, "radiusStartPx": 4, "radiusEndPx": 32,
            "sweepRadians": tau, "widthPx": .5, "segments": 20, "tailOpacityStart": 1, "tailOpacityEnd": 1},
    }]}


def _history(data: dict[str, Any], texture: str = "item") -> dict[str, Any]:
    entity_id = next((row["id"] for row in data["runtimeProgram"].get("entities", []) if row["kind"] != "item_body"), data["runtimeProgram"]["itemEntityId"])
    return {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": [{
        "id": "explicit_history", "entityId": entity_id,
        "event": "periodic", "rendererKind": "historyTrail", "anchor": "self", "blend": "alpha",
        "layer": "AfterProjectiles", "trail": {
            "draw": "sprites", "source": "center", "historyTicks": 20, "sampleStepTicks": 3,
            "firstSampleAgeTicks": 2, "color": {"r": 17, "g": 93, "b": 241},
            "opacityProfile": {"start": .8, "middle": .6, "end": .1, "curve": "linear"},
            "texture": {"source": texture, "assetId": ""}, "scale": 1.2, "pose": "sampled",
        },
    }]}


def _native(data: dict[str, Any], renderer: str = "nativeDust") -> dict[str, Any]:
    slot = {"id": "native_cue", "entityId": data["runtimeProgram"]["itemEntityId"],
            "event": "on_use", "rendererKind": renderer, "anchor": "self",
            "color": {"r": 17, "g": 93, "b": 241}, "startTick": 0, "repeatEvery": 0}
    if renderer == "nativeLight":
        slot["light"] = {"intensity": .6}
    else:
        slot["dust"] = {"type": "Smoke", "count": 3, "size": 1, "speedMinPxPerTick": 1,
                        "speedMaxPxPerTick": 2, "spreadRadians": .5, "inheritVelocity": .2,
                        "nativeAlpha": 100, "noGravity": True}
    return {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": [slot]}


def _profile(start: Any = 1.0, middle: Any = 1.0, end: Any = 0.0, curve: str = "linear") -> dict[str, Any]:
    return {"start": start, "middle": middle, "end": end, "curve": curve}

def _sprite(data: dict[str, Any]) -> dict[str, Any]:
    raw = _legacy(data)
    for field in ("color", "scale", "density", "spread", "particleSystemId", "textureRole"):
        raw["slots"][0].pop(field, None)
    raw["slots"][0].update({
        "id": "ingredient_element", "rendererKind": "spriteElement",
        "element": {
            "texture": {"source": "item", "assetId": ""}, "attachment": "world", "count": 2,
            "offsetForwardPx": 8.0, "offsetSidePx": -3.0, "speedMinPxPerTick": 1.0, "speedMaxPxPerTick": 2.0,
            "spreadRadians": 0.75, "inheritVelocity": 0.2, "drag": 0.95,
            "accelerationXPxPerTickSquared": 0.0, "accelerationYPxPerTickSquared": 0.05,
            "rotationRadians": 0.0, "rotationSpeedRadiansPerTick": -0.1, "widthPx": 12.0, "heightPx": 5.0,
            "widthProfile": _profile(0.0, 1.0, 2.0, "easeIn"), "heightProfile": _profile(2.0, 1.0, 0.0, "easeOut"),
            "opacityProfile": _profile(0.0, 0.8, 0.0, "smoothStep"), "colorProfile": _profile({'r': 255, 'g': 255, 'b': 255}, {'r': 17, 'g': 93, 'b': 241}, {'r': 210, 'g': 180, 'b': 140}),
        },
    })
    return raw

def _sent(data: dict[str, Any], repair: bool, packet: dict[str, Any] | None = None) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []

    def capture(_system: str, user: dict[str, Any], *_args: Any, **kwargs: Any) -> dict[str, Any]:
        sent.append(json.loads(kwargs["messages"][1]["content"]) if repair else json.loads(json.dumps(user)))
        return {}

    packet = vfx._prompt_packet(data, None, None) if packet is None else packet
    if repair:
        vfx._request(capture, packet, repair_errors=[{"path": "$.slots[0].alpha", "message": "invalid"}],
                     previous={"slots": []}, repair_scope={"fieldPermissions": {"slots": []}})
    else:
        vfx._request(capture, packet)
    return sent[0]

def _asset(asset_id: str = "Glow_A-1", layout: str = "cutout") -> dict[str, Any]:
    return {"id": asset_id, "prompt": "one isolated luminous ingredient, no text/UI/atlas", "negativePrompt": "", "canvasSize": 32, "layout": layout}

def _with_asset(data: dict[str, Any]) -> dict[str, Any]:
    raw = _sprite(data)
    raw["assets"] = [_asset()]
    raw["slots"][0]["element"]["texture"] = {"source": "asset", "assetId": "Glow_A-1"}
    return raw

def _path(data: dict[str, Any], source: str = "anchorHistory") -> dict[str, Any]:
    raw = _sprite(data)
    slot = raw["slots"][0]
    slot.pop("element")
    projectile = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    slot.update(id="connected_path", entityId=projectile["id"], event="periodic", rendererKind="texturedPath")
    slot.pop("duration")
    slot.pop("repeatEvery")
    slot["path"] = {
        "texture": {"source": "item", "assetId": ""}, "source": source,
        "historyTicks": 12 if source == "anchorHistory" else 0, "minDistancePx": 2.0 if source == "anchorHistory" else 0.0,
        "maxSegmentLengthPx": 64.0, "widthPx": 8.0, "widthProfile": _profile(0.0, 2.0, 0.0),
        "opacityProfile": _profile(0.0, 1.0, 0.0), "colorProfile": _profile({'r': 255, 'g': 215, 'b': 0}, {'r': 17, 'g': 93, 'b': 241}, {'r': 255, 'g': 255, 'b': 255}),
        "profileDomain": "age" if source == "anchorHistory" else "length", "uvMode": "repeat",
        "repeatLengthPx": 24.0, "scrollPxPerTick": -2.0,
    }
    return raw
