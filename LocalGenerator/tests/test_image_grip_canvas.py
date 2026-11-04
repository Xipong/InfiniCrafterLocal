"""Preserve explicit final-canvas contacts through real sdcpp pixel delivery."""
from __future__ import annotations
import copy
import pytest
from PIL import Image, ImageDraw
from infini_local.core.images import config
from infini_local.pipelines.images import postprocess as post
from infini_local.pipelines.images import stage


def _data():
    visual = dict(assetMode="baked_sprite", prompt="one copper bar with a blue handle", silhouette="horizontal bar",
                  visualIdentity="copper and blue", imagePrompt="one copper bar with a blue handle",
                  preferredCanvasSize=32, renderSizePx=32, forwardAngleDegrees=0,
                  grip={"normalizedX": .2, "normalizedY": .8})
    return {"id": "frame_contact", "visual": copy.deepcopy(visual),
            "runtimeProgram": {"itemEntityId": "item", "entities": [
                {"id": "item", "kind": "item_body", "visual": {"assetMode": "baked_sprite"}},
                {"id": "body", "kind": "held_body", "visual": copy.deepcopy(visual)}]}}


def _backend(monkeypatch, tmp_path, *, width=128, removable=True):
    monkeypatch.setattr(config, "BG_COLOR", "magenta")
    monkeypatch.setattr(stage, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(stage, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(stage, "SPRITE_RETRIES", 0)
    monkeypatch.setattr(stage, "SPRITE_DIR", tmp_path / "sprites")
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    calls = []
    def generate(prompt, negative, asset_id, canvas, *, output_dir=None):
        raw = Image.new("RGBA", (width, 128), (255, 0, 255, 255) if removable else (240, 240, 240, 255))
        draw = ImageDraw.Draw(raw)
        draw.rectangle((22, 98, 93, 106), fill=(170, 90, 40, 255))
        draw.rectangle((22, 97, 29, 107), fill=(60, 160, 230, 255))
        path = output_dir / (asset_id + "_raw_sdcpp_server_0.png")
        raw.save(path)
        calls.append((prompt, path, path.read_bytes()))
        return [str(path)]
    monkeypatch.setattr(stage, "generate_sdcpp", generate)
    return calls


def _generate(data, entry):
    if entry == "inventory":
        result = stage.maybe_generate_sprite(data)["visual"]
        return result["spritePath"], result["spriteStatus"]
    role, entity_id = ("item", "") if entry == "item" else ("runtime:held_body", "body")
    path, _, _, status = stage.generate_visual_asset(data, role, "one copper bar with blue handle", "", "frame_contact", 32, entity_id=entity_id)
    return path, status


def _blue_pixels(image):
    return [(x, y) for y in range(image.height) for x in range(image.width)
            if (pixel := image.getpixel((x, y)))[3] and pixel[2] > pixel[0] * 2]


@pytest.mark.parametrize("entry", ["inventory", "item", "held_body"])
def test_final_canvas_grip_survives_background_removal_and_publication(tmp_path, monkeypatch, entry):
    calls = _backend(monkeypatch, tmp_path)
    data = _data()
    frozen = copy.deepcopy(data)
    path, status = _generate(data, entry)
    assert path and status in {"generated", "generated_warn_invalid"}
    image = Image.open(path).convert("RGBA")
    # Assert the specific contact, not just any opaque pixel near its coordinate.
    assert min(((x - .2 * image.width) ** 2 + (y - .8 * image.height) ** 2) ** .5 for x, y in _blue_pixels(image)) < 1.5
    assert data["runtimeProgram"] == frozen["runtimeProgram"]
    assert data["visual"]["grip"] == frozen["visual"]["grip"]
    assert len(calls) == 1 and calls[0][1].read_bytes() == calls[0][2]
    prefix = "runtime:held_body" if entry == "held_body" else "item"
    assert data["debug"][prefix + "SpriteFramePolicy"] == "preserve_authored_grip"
    assert image.size == (32, 32) and image.getpixel((0, 0))[3] == 0


def test_absent_grip_retains_existing_bbox_fit(tmp_path, monkeypatch):
    _backend(monkeypatch, tmp_path)
    data = _data()
    del data["runtimeProgram"]["entities"][1]["visual"]["grip"]
    path, status = _generate(data, "held_body")
    assert path and status == "generated"
    image = Image.open(path).convert("RGBA")
    assert min(y for _, y in _blue_pixels(image)) < 20
    assert "grip" not in data["runtimeProgram"]["entities"][1]["visual"]


def test_nonsquare_grip_frame_is_not_padded_or_stretched_into_success(tmp_path, monkeypatch):
    calls = _backend(monkeypatch, tmp_path, width=160)
    data = _data()
    path, status = _generate(data, "held_body")
    assert not path and status == "failed"
    assert "RawSpriteFrameError" in data["debug"]["runtime:held_bodySpriteError"]
    assert calls[0][1].read_bytes() == calls[0][2]
    assert not list((tmp_path / "sprites").glob("*.png"))


def test_grip_frame_does_not_bypass_background_failure(tmp_path, monkeypatch):
    _backend(monkeypatch, tmp_path, removable=False)
    path, status = _generate(_data(), "held_body")
    assert not path and status == "failed"


def test_wrong_provider_contact_is_not_snapped_to_authored_grip(tmp_path, monkeypatch):
    _backend(monkeypatch, tmp_path)
    data = _data()
    data["runtimeProgram"]["entities"][1]["visual"]["grip"] = {"normalizedX": .8, "normalizedY": .2}
    path, status = _generate(data, "held_body")
    assert path and status in {"generated", "generated_warn_invalid"}
    image = Image.open(path).convert("RGBA")
    assert image.getpixel((25, 6))[3] == 0
    assert min(y for _, y in _blue_pixels(image)) >= 23


def test_recoverable_bake_error_keeps_the_same_contact(tmp_path, monkeypatch):
    _backend(monkeypatch, tmp_path)
    def fail_bake(*args, **kwargs):
        raise ValueError("controlled palette-processing failure")
    monkeypatch.setattr(post, "bake_sprite_from_master", fail_bake)
    path, status = _generate(_data(), "held_body")
    assert path and status in {"generated", "generated_warn_invalid"}
    image = Image.open(path).convert("RGBA")
    assert min(((x - .2 * image.width) ** 2 + (y - .8 * image.height) ** 2) ** .5 for x, y in _blue_pixels(image)) < 1.5
