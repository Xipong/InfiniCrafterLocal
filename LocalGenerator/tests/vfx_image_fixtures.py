"""Hand-authored offline pixels and compiled asset inputs, shared only by VFX/image contracts."""
from __future__ import annotations

import contextlib
import io
import copy
import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from infini_local.pipelines import sprite_postprocess, visual_asset_manifest, visual_sprite_generation, visual_delivery_gate, pipeline_visual_config
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.core.vfx_manifest import VFX_DIRECTOR_SCHEMA, _compile_manifest
from infini_local.web.vfx_debug_routes import _sample_data

def _request(asset_id: str = "grain", *, layout: str = "cutout", canvas: int = 32) -> dict:
    return {
        "id": asset_id, "prompt": "one isolated amber texture ingredient with soft edges",
        "negativePrompt": "UI, text, atlas, weapon body", "canvasSize": canvas, "layout": layout,
    }

def _profile(value: float) -> dict:
    return {"start": value, "middle": value, "end": value, "curve": "linear"}

def _slot(slot_id: str, asset_id: str, *, renderer: str = "spriteElement") -> dict:
    slot = {
        "id": slot_id, "entityId": "orb", "event": "periodic",
        "rendererKind": renderer, "backend": "Sprite" if renderer == "spriteElement" else "Primitive",
        "textureRole": "none", "particleRole": "none", "anchor": "self", "channel": "motionTrail",
        "lane": "primary", "emissionMode": "none", "blend": "alpha", "layer": "AfterProjectiles",
        "particleSystemId": "none", "scale": 1.0, "density": 0.0,
        "duration": 12 if renderer == "spriteElement" else 3, "alpha": 1.0,
        "spread": 0.0, "jitter": 0.0, "fadeIn": 0.0, "fadeOut": 0.0, "budgetWeight": 1.0,
        "signatureWeight": 0.0, "visualCost": 0.0, "startTick": 0,
        "repeatEvery": 4 if renderer == "spriteElement" else 0,
    }
    texture = {"source": "asset", "assetId": asset_id}
    color = {"start": "white", "middle": "white", "end": "white", "curve": "linear"}
    if renderer == "spriteElement":
        slot["element"] = {
            "texture": texture, "attachment": "world", "count": 1,
            "offsetForwardPx": 0.0, "offsetSidePx": 0.0, "speedMinPxPerTick": 0.0,
            "speedMaxPxPerTick": 0.0, "spreadRadians": 0.0, "inheritVelocity": 0.0, "drag": 1.0,
            "accelerationXPxPerTickSquared": 0.0, "accelerationYPxPerTickSquared": 0.0,
            "rotationRadians": 0.0, "rotationSpeedRadiansPerTick": 0.0, "widthPx": 12.0,
            "heightPx": 8.0, "widthProfile": _profile(1.0), "heightProfile": _profile(1.0),
            "opacityProfile": _profile(1.0), "colorProfile": color,
        }
    else:
        slot["path"] = {
            "texture": texture, "source": "anchorHistory", "historyTicks": 12, "minDistancePx": 1.0,
            "maxSegmentLengthPx": 32.0, "widthPx": 8.0, "widthProfile": _profile(1.0),
            "opacityProfile": _profile(1.0), "colorProfile": color, "profileDomain": "age",
            "uvMode": "repeat", "repeatLengthPx": 16.0, "scrollPxPerTick": 0.0,
        }
    return slot

def _data(requests: list[dict] | None = None) -> dict:
    data = _sample_data()
    data["id"] = "vfx_png_probe"
    requests = [_request()] if requests is None else requests
    authored = {
        "schema": VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "visualBudgetClass": "normal",
        "motif": {"element": "amber", "shapeLanguage": "grain", "motionLanguage": "quiet",
                  "paletteRole": "accent", "rhythm": 1.0, "chaos": 0.0},
        "slots": [_slot("first", requests[0]["id"]), _slot("second", requests[0]["id"], renderer="texturedPath")]
        if requests else [],
    }
    if requests:
        authored["assets"] = copy.deepcopy(requests)
        for index, request in enumerate(requests[1:], start=2):
            authored["slots"].append(_slot(f"extra_{index}", request["id"]))
    data["vfxManifest"] = _compile_manifest(data, authored, "offline_recipe")
    data["visual"] = {"imagePrompt": "offline item fixture", "preferredCanvasSize": 32}
    return data

def _raw_fixture(path: Path, *, layout: str = "cutout", size: int = 64, alpha: int = 144) -> str:
    image = Image.new("RGBA", (size, size), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    if layout == "strip":
        # Off-centre, edge-to-edge band and distinct right-end marker expose UV drift/rotation.
        draw.rectangle((0, size // 4, size - 1, size // 4 + size // 8 - 1), fill=(210, 100, 20, alpha))
        draw.rectangle((size * 3 // 4, size // 4, size - 1, size // 4 + size // 8 - 1), fill=(30, 90, 210, alpha))
    else:
        draw.ellipse((size // 8, size // 4, size // 8 + size // 4, size // 4 + size // 3), fill=(210, 100, 20, alpha))
    image.save(path)
    return str(path)

@pytest.fixture
def offline_backend(monkeypatch, tmp_path):
    calls = []
    events = []
    class FixtureGate(ImageRequestGate):
        @contextlib.contextmanager
        def slot(self):
            with super().slot():
                events.append("enter")
                try:
                    yield
                finally:
                    events.append("exit")

    def configured_sdcpp(prompt, negative, asset_id, canvas, *, output_dir=None):
        calls.append({"id": asset_id, "prompt": prompt, "negative": negative, "canvas": canvas})
        layout = "strip" if "preserve the full authored frame" in prompt else "cutout"
        path = (output_dir if output_dir is not None else tmp_path) / f"{asset_id}_offline_fixture_raw_sdcpp.png"
        return [_raw_fixture(path, layout=layout, alpha=255 if "_vfx_" not in asset_id else 144)]

    for module in (sprite_postprocess, visual_asset_manifest, visual_sprite_generation, visual_delivery_gate):
        monkeypatch.setattr(module, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")
    monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(visual_sprite_generation, "SPRITE_RETRIES", 0)
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", configured_sdcpp)
    monkeypatch.setattr(visual_sprite_generation, "IMAGE_GENERATION_GATE", FixtureGate(1))
    monkeypatch.setattr(pipeline_visual_config, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(pipeline_visual_config, "IMAGE_BACKEND_RAW", "sdcpp")
    monkeypatch.setattr(pipeline_visual_config, "BG_COLOR", "magenta")
    monkeypatch.setattr(pipeline_visual_config, "REMOVE_BG", True)
    return calls, events

def _existing_texture_data(source: str, renderer: str = "spriteElement") -> dict:
    data = _data([])
    slot = _slot("existing", "", renderer=renderer)
    payload = "element" if renderer == "spriteElement" else "path"
    slot[payload]["texture"] = {"source": source, "assetId": ""}
    orb = next(row for row in data["runtimeProgram"]["entities"] if row["id"] == "orb")
    if source == "entity":
        orb["visual"]["assetMode"] = "baked_sprite"
    data["vfxManifest"]["slots"] = [slot]
    if source == "impact":
        producer = {key: copy.deepcopy(value) for key, value in slot.items() if key not in {"element", "path"}}
        producer.update(id="impact_source", rendererKind="impactSprite", backend="Sprite", textureRole="impact")
        data["vfxManifest"]["slots"].append(producer)
        orb["visual"].update(impactPrompt="one isolated impact ingredient", impactNegativePrompt="UI, text, atlas")
    return data

def frozen_value(value):
    """Decode only the explicit nonfinite marker used by offline numeric fixtures."""
    if isinstance(value, dict):
        if set(value) == {"$nonfinite"}:
            return float(value["$nonfinite"])
        return {key: frozen_value(item) for key, item in value.items()}
    return [frozen_value(item) for item in value] if isinstance(value, list) else value

def apply_edits(target, edits):
    """Apply literal JSON-token edits; dots/brackets inside a key stay literal."""
    for operation, path, value in edits:
        parent = target
        for token in path[:-1]:
            parent = parent[token]
        if operation == "delete":
            del parent[path[-1]]
        else:
            parent[path[-1]] = frozen_value(value)
    return target


class HttpCapture:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.code = None
        self.headers = {}

    def send_response(self, code):
        self.code = code

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass

    def send_error(self, code):
        self.code = code
