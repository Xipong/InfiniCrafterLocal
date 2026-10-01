"""Bounded offline observers for VFX intermediate ownership, not live image QA."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import threading

import pytest
from PIL import Image, ImageDraw

from infini_local.pipelines import image_backend_pipeline, visual_delivery_gate, visual_sprite_generation
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan

from test_vfx_asset_pipeline import _data, _request, offline_backend  # noqa: F401


def test_same_request_overlap_publishes_each_calls_validated_bytes(offline_backend, monkeypatch):
    data = _data([_request("band", layout="strip")])
    job = next(row for row in build_visual_asset_plan(data) if row["role"] == "vfx:band")
    first_validated = threading.Event()
    second_done = threading.Event()
    validated_bytes = {}
    returned = {}
    errors = {}
    original_backend = visual_sprite_generation.generate_sdcpp
    original_validator = visual_sprite_generation.validate_processed_sprite

    def distinct_pngs(prompt, negative, asset_id, canvas, *, output_dir=None):
        paths = original_backend(prompt, negative, asset_id, canvas, output_dir=output_dir)
        if threading.current_thread().name == "second":
            with Image.open(paths[0]) as source:
                image = source.copy()
            ImageDraw.Draw(image).rectangle((0, 16, 47, 23), fill=(30, 200, 70, 144))
            image.save(paths[0])
        return paths

    def pause_after_real_validation(path, role, **kwargs):
        report = original_validator(path, role, **kwargs)
        if kwargs.get("expected_canvas") == 32:
            name = threading.current_thread().name
            assert report["ok"], report
            validated_bytes[name] = Path(path).read_bytes()
            if name == "first":
                first_validated.set()
                assert second_done.wait(15), "second call did not finish"
        return report

    def call():
        name = threading.current_thread().name
        try:
            returned[name] = visual_sprite_generation.generate_visual_asset(
                copy.deepcopy(data), "vfx:band", job["prompt"], job["negativePrompt"],
                job["assetId"], job["canvas"], processing_role="vfx_strip",
            )
        except BaseException as error:
            errors[name] = error
        finally:
            if name == "second":
                second_done.set()

    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", distinct_pngs)
    monkeypatch.setattr(visual_sprite_generation, "validate_processed_sprite", pause_after_real_validation)
    first = threading.Thread(target=call, name="first")
    second = threading.Thread(target=call, name="second")
    first.start()
    try:
        assert first_validated.wait(15), "first call did not reach its real final PNG validator"
        second.start()
        second.join(15)
        assert not second.is_alive()
    finally:
        second_done.set()
        first.join(15)
    assert not first.is_alive() and not errors, errors
    assert validated_bytes["first"] != validated_bytes["second"]
    for name, result in returned.items():
        assert result[3] == "generated", result
        assert Path(result[0]).read_bytes() == validated_bytes[name], f"{name} published another call's intermediate"
    assert returned["first"][0] != returned["second"][0]
    assert not list(visual_sprite_generation.SPRITE_DIR.glob(".infini_vfx_png_*.part"))
    gate = visual_sprite_generation.IMAGE_GENERATION_GATE
    assert gate._semaphore.acquire(blocking=False)
    gate._semaphore.release()


@pytest.mark.parametrize("configured_seed", [0, 731])
def test_real_adapter_retry_keeps_raw_evidence_unique_and_configured_seeds(offline_backend, monkeypatch, tmp_path, configured_seed):
    """Execute the adapter/request decoder; urlopen returns authored offline bytes."""
    backend = image_backend_pipeline
    # Hydrate ordinary item/entity producers with the same offline fixture seam.
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request("band", layout="strip")]))
    requests = []
    all_raw_paths = []
    fixtures = [b"offline corrupt first-attempt PNG", b"offline corrupt second-attempt PNG"]
    image = Image.new("RGBA", (64, 64), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 16, 63, 23), fill=(210, 100, 20, 144))
    draw.rectangle((48, 16, 63, 23), fill=(30, 90, 210, 144))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    fixtures.append(stream.getvalue())

    class FixtureResponse(io.BytesIO):
        headers = {"Content-Type": "image/png"}

    def offline_urlopen(request, **kwargs):
        requests.append(json.loads(request.data))
        return FixtureResponse(fixtures[(len(requests) - 1) // 2])

    original_adapter = backend.generate_sdcpp

    def real_adapter(prompt, negative, asset_id, canvas, *, output_dir=None):
        paths = original_adapter(prompt, negative, asset_id, canvas, output_dir=output_dir)
        all_raw_paths.append([Path(path) for path in paths])
        return paths

    monkeypatch.setattr(backend, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(backend, "ensure_sdcpp_server", lambda: True)
    monkeypatch.setattr(backend, "_effective_sdcpp_lora_prompt_tags", lambda: "")
    monkeypatch.setattr(backend.urlrequest, "urlopen", offline_urlopen)
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 2)
    monkeypatch.setattr(backend, "SDCPP_SEED", configured_seed)
    monkeypatch.setattr(backend, "SDCPP_SERVER_TXT2IMG_PATHS", ["/sdapi/v1/txt2img"])
    monkeypatch.setattr(backend, "SDCPP_SERVER_PAYLOAD_STYLE", "a1111")
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", real_adapter)
    monkeypatch.setattr(visual_sprite_generation, "SPRITE_RETRIES", 2)
    job = next(row for row in build_visual_asset_plan(data) if row["role"] == "vfx:band")
    result = visual_sprite_generation.generate_visual_asset(
        data, "vfx:band", job["prompt"], job["negativePrompt"], job["assetId"], job["canvas"],
        processing_role="vfx_strip",
    )
    assert result[3] == "generated", data["debug"]
    assert len(requests) == 6 and len(all_raw_paths) == 3
    assert [row["seed"] for row in requests] == [configured_seed, configured_seed + 1] * 3
    attempts = json.loads(data["debug"]["vfx:bandSpriteValidation"])
    assert [row["attempt"] for row in attempts] == [0, 1, 2]
    assert attempts[-1]["validation"]["ok"]
    with Image.open(result[0]) as final:
        assert final.size == (32, 32)
        alpha = final.getchannel("A")
        assert alpha.getbbox() == (0, 8, 32, 12)
        assert alpha.getpixel((0, 8)) == alpha.getpixel((31, 11)) == 144
    flattened = [path for paths in all_raw_paths for path in paths]
    assert len({path.name.casefold() for path in flattened}) == 6, "retry raw filenames alias after the real adapter's 80-character stem projection"
    for index, paths in enumerate(all_raw_paths):
        assert all(path.read_bytes() == fixtures[index] for path in paths)
    data["vfxManifest"]["assets"][0].update(
        spritePath=result[0], spriteUrl=result[1], spriteTechnicalScore=result[2], spriteStatus=result[3],
    )
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert report["ok"], report["problems"]
