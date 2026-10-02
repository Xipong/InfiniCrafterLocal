"""Canonical hand-authored material inputs and exact offline Director/Repair packet capture."""
from __future__ import annotations

import json
from typing import Any
from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

def _data(capability: str = "") -> dict[str, Any]:
    return compile_runtime_program(build_capability_witness(capability) if capability else build_runtime_fixture("workbench_blade"))

def _legacy(data: dict[str, Any]) -> dict[str, Any]:
    item_id = data["runtimeProgram"]["itemEntityId"]
    return {
        "schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "visualBudgetClass": "normal",
        "motif": {"element": "metal", "shapeLanguage": "sparks", "motionLanguage": "short wake", "paletteRole": "accent", "rhythm": 1.0, "chaos": 0.2},
        "slots": [{
            "id": "old_slot", "entityId": item_id, "event": "on_use", "rendererKind": "impactRing",
            "backend": "Realtime", "textureRole": "none", "particleRole": "none", "anchor": "self",
            "channel": "impactShape", "lane": "primary", "emissionMode": "burst", "blend": "alpha",
            "layer": "BeforeProjectiles", "particleSystemId": "none", "scale": 1.0,
            "density": 0.4, "duration": 20, "alpha": 0.8, "spread": 0.1, "jitter": 0.1,
            "fadeIn": 0.1, "fadeOut": 0.4, "budgetWeight": 1.0, "signatureWeight": 0.5,
            "visualCost": 0.5, "startTick": 0, "repeatEvery": 0, "spritePrompt": "", "spriteNegativePrompt": "",
        }],
    }

def _profile(start: Any = 1.0, middle: Any = 1.0, end: Any = 0.0, curve: str = "linear") -> dict[str, Any]:
    return {"start": start, "middle": middle, "end": end, "curve": curve}

def _sprite(data: dict[str, Any]) -> dict[str, Any]:
    raw = _legacy(data)
    raw["slots"][0].update({
        "id": "ingredient_element", "rendererKind": "spriteElement", "backend": "Sprite", "emissionMode": "none",
        "scale": 1.0, "density": 0.0, "spread": 0.0, "jitter": 0.0, "fadeIn": 0.0, "fadeOut": 0.0,
        "signatureWeight": 0.0, "visualCost": 0.0,
        "element": {
            "texture": {"source": "item", "assetId": ""}, "attachment": "world", "count": 2,
            "offsetForwardPx": 8.0, "offsetSidePx": -3.0, "speedMinPxPerTick": 1.0, "speedMaxPxPerTick": 2.0,
            "spreadRadians": 0.75, "inheritVelocity": 0.2, "drag": 0.95,
            "accelerationXPxPerTickSquared": 0.0, "accelerationYPxPerTickSquared": 0.05,
            "rotationRadians": 0.0, "rotationSpeedRadiansPerTick": -0.1, "widthPx": 12.0, "heightPx": 5.0,
            "widthProfile": _profile(0.0, 1.0, 2.0, "easeIn"), "heightProfile": _profile(2.0, 1.0, 0.0, "easeOut"),
            "opacityProfile": _profile(0.0, 0.8, 0.0, "smoothStep"), "colorProfile": _profile("white", "effect", "tan"),
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
    slot.update(id="connected_path", entityId=projectile["id"], event="periodic", rendererKind="texturedPath", backend="Primitive", duration=3)
    slot["path"] = {
        "texture": {"source": "item", "assetId": ""}, "source": source,
        "historyTicks": 12 if source == "anchorHistory" else 0, "minDistancePx": 2.0 if source == "anchorHistory" else 0.0,
        "maxSegmentLengthPx": 64.0, "widthPx": 8.0, "widthProfile": _profile(0.0, 2.0, 0.0),
        "opacityProfile": _profile(0.0, 1.0, 0.0), "colorProfile": _profile("gold", "effect", "white"),
        "profileDomain": "age" if source == "anchorHistory" else "length", "uvMode": "repeat",
        "repeatLengthPx": 24.0, "scrollPxPerTick": -2.0,
    }
    return raw
