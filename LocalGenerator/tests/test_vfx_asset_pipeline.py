"""Offline hand-authored PNG fixtures, not image-model/artistic acceptance.

Only the configured backend adapter is replaced; queue, retries, Pillow keying,
postprocess, manifests, delivery and storage remain production code.
"""
from __future__ import annotations

import contextlib
import copy
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from infini_local.pipelines import sprite_postprocess, visual_asset_manifest, visual_sprite_generation
from infini_local.pipelines import pipeline_visual_config, visual_delivery_gate
from infini_local.services import asset_sync_service
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.core.vfx_manifest import VFX_DIRECTOR_SCHEMA, _compile_manifest
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
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


def test_one_declared_ingredient_shared_by_two_renderers_is_one_plan_job():
    data = _data()
    before = copy.deepcopy(data)
    plan = build_visual_asset_plan(data)
    jobs = [row for row in plan if row["role"].startswith("vfx:")]
    assert len(jobs) == 1
    job_id = jobs[0]["assetId"]
    assert job_id.startswith("infini_vfx_job_")
    assert len(job_id.removeprefix("infini_vfx_job_")) == 64
    assert jobs[0] == {
        "role": "vfx:grain", "assetId": job_id, "vfxAssetId": "grain",
        "assetMode": "baked_sprite", "runtimeGateReason": "authored_vfx_texture_ingredient",
        "prompt": before["vfxManifest"]["assets"][0]["prompt"],
        "negativePrompt": before["vfxManifest"]["assets"][0]["negativePrompt"],
        "canvas": 32, "layout": "cutout", "processingRole": "vfx_cutout", "required": True,
        "status": "pending", "path": "", "url": "", "technicalScore": 0.0,
    }
    assert data == before
    assert "entityId" not in jobs[0]


def test_absent_vfx_requests_do_not_add_jobs_or_wire_fields():
    legacy = _data([])
    before = copy.deepcopy(legacy)
    assert not any(row["role"].startswith("vfx:") for row in build_visual_asset_plan(legacy))
    assert legacy == before
    assert "assets" not in legacy["vfxManifest"]


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

    def configured_sdcpp(prompt, negative, asset_id, canvas):
        calls.append({"id": asset_id, "prompt": prompt, "negative": negative, "canvas": canvas})
        layout = "strip" if "preserve the full authored frame" in prompt else "cutout"
        path = tmp_path / f"{asset_id}_offline_fixture_raw_sdcpp.png"
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


def test_shared_asset_generates_once_through_selected_backend_and_hydrates_manifest(offline_backend):
    calls, events = offline_backend
    data = _data()
    authored = {key: copy.deepcopy(data["vfxManifest"]["assets"][0][key]) for key in ("id", "prompt", "negativePrompt", "canvasSize", "layout")}
    runtime_before = copy.deepcopy(data["runtimeProgram"])
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    vfx_calls = [call for call in calls if "_vfx_" in call["id"]]
    assert len(vfx_calls) == 1
    call = vfx_calls[0]
    assert call["id"].startswith("infini_vfx_job_")
    assert call["canvas"] == 32
    assert call["negative"] == authored["negativePrompt"]
    assert authored["prompt"] in call["prompt"]
    assert events == [value for _ in calls for value in ("enter", "exit")]
    asset = out["vfxManifest"]["assets"][0]
    assert {key: asset[key] for key in authored} == authored
    assert asset["spriteStatus"] == "generated", out["debug"].get("vfx:grainSpriteValidation")
    assert Path(asset["spritePath"]).name.startswith("infini_vfx_png_")
    assert asset["spriteUrl"] == "/sprite/" + Path(asset["spritePath"]).name
    assert 0.0 < asset["spriteTechnicalScore"] <= 1.0
    assert asset_sync_service.is_complete_png_file(asset["spritePath"])
    with Image.open(asset["spritePath"]) as image:
        assert image.size == (32, 32)
        assert image.mode == "RGBA"
        assert sum(image.getchannel("A").histogram()[1:255]) > 0
    after = copy.deepcopy(out["runtimeProgram"])
    for runtime in (runtime_before, after):
        for entity in runtime["entities"]:
            entity.pop("visual", None)
    assert after == runtime_before
    plan = json.loads(out["debug"]["visualAssetPlan"])
    job = next(row for row in plan if row["role"] == "vfx:grain")
    assert job["path"] == asset["spritePath"]
    assert job["status"] == asset["spriteStatus"]


@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath"])
def test_strip_preserves_authored_full_frame_uvs_for_either_renderer(offline_backend, renderer):
    calls, _ = offline_backend
    data = _data([_request("band", layout="strip")])
    data["vfxManifest"]["slots"] = [_slot("literal_use", "band", renderer=renderer)]
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "generated", out["debug"].get("vfx:bandSpriteValidation")
    with Image.open(asset["spritePath"]) as image:
        assert image.size == (32, 32)
        assert image.getchannel("A").getbbox() == (0, 8, 32, 12)
        assert image.getpixel((0, 8))[3] == 144
        assert image.getpixel((31, 11))[3] == 144
        assert image.getpixel((31, 11))[2] > image.getpixel((31, 11))[0]
        assert image.getpixel((0, 8))[0] > image.getpixel((0, 8))[2]
        assert image.getpixel((16, 16)) == (0, 0, 0, 0)
    prompt = next(row["prompt"] for row in calls if "_vfx_" in row["id"])
    assert "preserve the full authored frame" in prompt
    assert "centered" not in prompt
    assert "vfx:band" not in prompt


@pytest.mark.parametrize("layout", ["cutout", "strip"])
def test_backend_error_never_fabricates_a_required_vfx_ingredient(offline_backend, monkeypatch, layout):
    calls, events = offline_backend
    original_backend = visual_sprite_generation.generate_sdcpp

    def fail_requested(prompt, negative, asset_id, canvas):
        if "_vfx_" in asset_id:
            calls.append({"id": asset_id, "prompt": prompt, "canvas": canvas})
            raise RuntimeError("offline fixture: backend generation error")
        return original_backend(prompt, negative, asset_id, canvas)

    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", fail_requested)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ALLOW_PROCEDURAL_FALLBACK", True)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_STRICT_AI_AUTHORSHIP", False)
    out = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout=layout)]))
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "failed"
    assert asset["spritePath"] == asset["spriteUrl"] == ""
    assert asset["spriteTechnicalScore"] == 0.0
    assert len([call for call in calls if "_vfx_" in call["id"]]) == 1
    assert events == [value for _ in calls for value in ("enter", "exit")]


def test_cutout_postprocess_failure_cannot_report_the_raw_image_as_success(offline_backend, monkeypatch):
    original_backend = visual_sprite_generation.generate_sdcpp
    original_master = sprite_postprocess.prepare_sprite_master

    def exact_alpha_fixture(prompt, negative, asset_id, canvas):
        paths = original_backend(prompt, negative, asset_id, canvas)
        if "_vfx_" in asset_id:
            # A valid raw, already-alpha PNG must still not hide a failed processing stage.
            image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((4, 4, canvas - 5, canvas - 5), fill=(200, 110, 10, 128))
            image.save(paths[0])
        return paths

    def broken_master(image, sprite_id, target_size, role="item"):
        if role == "vfx_cutout":
            raise OSError("offline fixture: postprocess write failure")
        return original_master(image, sprite_id, target_size, role)

    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", exact_alpha_fixture)
    monkeypatch.setattr(sprite_postprocess, "prepare_sprite_master", broken_master)
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "failed"
    assert asset["spritePath"] == asset["spriteUrl"] == ""


@pytest.mark.parametrize("layout", ["cutout", "strip"])
@pytest.mark.parametrize("damage", ["missing", "wrong_size", "rgb", "opaque", "empty", "truncated", "not_png"])
def test_delivery_checks_exact_requested_vfx_png_contract(offline_backend, layout, damage):
    out = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout=layout)]))
    asset = out["vfxManifest"]["assets"][0]
    path = Path(asset["spritePath"])
    if damage == "missing":
        path.unlink()
    elif damage == "truncated":
        path.write_bytes(path.read_bytes()[:-1])
    elif damage == "not_png":
        with Image.open(path) as image:
            image.save(path, format="BMP")
    else:
        size = 24 if damage == "wrong_size" else 32
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        if damage != "empty":
            ImageDraw.Draw(image).rectangle((3, 3, size - 4, size - 4), fill=(210, 100, 20, 144))
        if damage == "rgb":
            image = image.convert("RGB")
        if damage == "opaque":
            image.putalpha(255)
        image.save(path, format="PNG")
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["ok"], damage
    assert "required_vfx_sprite_missing_or_invalid" in {problem["code"] for problem in report["problems"]}
    job = next(row for row in report["slots"] if row["role"] == "vfx:grain")
    assert job["required"] is True
    assert job["usable"] is False


def test_delivery_lists_shared_ingredient_once_and_counts_its_file(offline_backend, monkeypatch):
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert report["ok"], report["problems"]
    assert len([row for row in report["slots"] if row["role"] == "vfx:grain"]) == 1
    monkeypatch.setattr(visual_delivery_gate, "MAX_DELIVERABLE_ASSET_FILES", 1)
    bounded = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert "asset_roster_file_limit_exceeded" in {problem["code"] for problem in bounded["problems"]}


@pytest.mark.parametrize("layout", ["cutout", "strip"])
def test_generation_rejects_wrong_final_canvas_before_success(offline_backend, monkeypatch, layout):
    original_bake = sprite_postprocess.bake_sprite_from_master
    def wrong_bake(master, target_size, role="item"):
        image = original_bake(master, target_size, role)
        return image.resize((24, 24)) if role in {"vfx_cutout", "vfx_strip"} else image
    monkeypatch.setattr(sprite_postprocess, "bake_sprite_from_master", wrong_bake)
    out = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout=layout)]))
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "failed"
    assert asset["spritePath"] == asset["spriteUrl"] == ""
    attempts = json.loads(out["debug"]["vfx:grainSpriteValidation"])
    assert "final_canvas_mismatch" in attempts[0]["validation"]["reasons"]



def test_strip_alpha_coverage_can_fill_full_frame_without_silhouette_heuristics(tmp_path):
    path = tmp_path / "offline_full_frame_soft_strip.png"
    Image.new("RGBA", (32, 32), (210, 100, 20, 144)).save(path)
    validation = sprite_postprocess.validate_processed_sprite(str(path), "vfx_strip", expected_canvas=32)
    assert validation["ok"], validation
    assert not sprite_postprocess.sprite_validation_fatal(validation)


@pytest.mark.parametrize("layout", ["cutout", "strip"])
def test_diagnostic_asset_manifest_preserves_identity_layout_and_real_png_hash(offline_backend, layout):
    import hashlib
    out = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout=layout)]))
    asset = out["vfxManifest"]["assets"][0]
    manifest = json.loads(Path(out["visual"]["assetManifestPath"]).read_text(encoding="utf-8"))
    row = next(row for row in manifest["assets"] if row["role"] == "vfx:grain")
    raw = Path(asset["spritePath"]).read_bytes()
    assert row["exists"] is True
    assert row["file"] == Path(asset["spritePath"]).name
    assert row["bytes"] == len(raw)
    assert row["sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["vfxAssetId"] == "grain"
    assert row["layout"] == layout
    assert row["processingRole"] == "vfx_" + layout
    assert row["contract"]["role"] == "vfx_" + layout
    assert row["contract"]["layout"] == layout
    assert row["contract"]["preserveFullFrame"] is (layout == "strip")
    assert row["contract"]["targetSizePx"] == 32



def test_runtime_png_roster_matches_shared_csharp_dto_path_parity_vector():
    fixture = json.loads((Path(__file__).parent / "fixtures/vfx_asset_roster_parity_v1.json").read_text())
    data = fixture["data"]
    assert asset_sync_service.runtime_asset_files(data) == fixture["expectedFiles"]
    asset_sync_service.attach_asset_sync_meta(data)
    assert data["recipeMeta"]["assetFiles"] == fixture["expectedFiles"]
    assert data["recipeMeta"]["assetSync"]["fileCount"] == len(fixture["expectedFiles"])


def test_runtime_png_roster_rejects_over_limit_instead_of_silent_truncation():
    data = {"runtimeProgram": {"entities": [
        {"visual": {"spritePath": f"offline-{index}.png"}} for index in range(33)
    ]}}
    with pytest.raises(ValueError, match="32"):
        asset_sync_service.runtime_asset_files(data)


@pytest.mark.parametrize("damage", ["duplicate", "dangling", "missing", "null", "invalid_id"])
def test_invalid_requests_fail_planning_before_backend_jobs(offline_backend, damage):
    calls, _ = offline_backend
    data = _data()
    if damage == "duplicate":
        data["vfxManifest"]["assets"].append(copy.deepcopy(data["vfxManifest"]["assets"][0]))
    elif damage == "dangling":
        data["vfxManifest"]["slots"][0]["element"]["texture"]["assetId"] = "other"
    elif damage == "missing":
        data["vfxManifest"].pop("assets")
    elif damage == "null":
        data["vfxManifest"]["assets"] = None
    else:
        data["vfxManifest"]["assets"][0]["id"] = "../bad"
    with pytest.raises(ValueError, match="VFX"):
        visual_sprite_generation.maybe_generate_visual_assets(data)
    assert calls == []


def test_unused_new_request_is_rejected_in_canonical_fresh_caption_domain(offline_backend):
    from infini_local.core.vfx_manifest import validate_vfx_director_output
    calls, _ = offline_backend
    data = _data([])
    raw = {
        "schema": VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "visualBudgetClass": "normal",
        "motif": {"element": "amber", "shapeLanguage": "grain", "motionLanguage": "quiet",
                  "paletteRole": "accent", "rhythm": 1.0, "chaos": 0.0},
        "slots": [{**_slot("first", "grain"), "spritePrompt": "", "spriteNegativePrompt": ""}],
        "assets": [_request(), _request("unused")],
    }
    # Runtime wire is a distinct domain and may retain unreferenced compiled rows.
    # Fresh request rejection is owned by this validator, not an asset-side copy.
    report = validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {error["message"] for error in report["errors"]} == {"unused new asset request"}
    assert calls == []


def test_storage_admission_uses_canonical_vfx_references():
    from infini_local.storage import world_storage
    data = _data()
    data["vfxManifest"]["slots"][0]["element"]["texture"]["assetId"] = "dangling"
    assert world_storage.is_deliverable_recipe_payload(data) is False


def test_storage_cache_roundtrip_preserves_assets_refs_pixels_and_runtime(offline_backend, tmp_path):
    from infini_local.storage import world_storage
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(), _request("band", layout="strip")]))
    before = copy.deepcopy(data)
    world_storage.write_world_recipe_cache(tmp_path / "world", "test", "recipe", "world", data)
    assert data == before
    cached = world_storage.read_world_recipe_cache(tmp_path / "world", "test", "v5", "recipe", "world")
    assert cached is not None
    assert cached["vfxManifest"]["assets"] == before["vfxManifest"]["assets"]
    assert cached["vfxManifest"]["slots"] == before["vfxManifest"]["slots"]
    assert cached["runtimeProgram"] == before["runtimeProgram"]
    path = world_storage.world_recipe_file(tmp_path / "world", "world", "recipe")
    stored = path.read_bytes()
    Path(data["vfxManifest"]["assets"][0]["spritePath"]).unlink()
    assert world_storage.is_deliverable_recipe_payload(data) is False
    assert world_storage.read_world_recipe_cache(tmp_path / "world", "test", "v5", "recipe", "world") is None
    invalid = path.parent.parent / "invalid"
    originals = [p for p in invalid.glob("*.json") if not p.name.endswith(".reason.json")]
    assert len(originals) == 1
    assert originals[0].read_bytes() == stored


@pytest.mark.parametrize("ids", [("Glow", "glow"), ("spark", "spark_refit", "spark_retry1")])
def test_case_and_processing_suffix_ids_have_distinct_immutable_png_names(offline_backend, ids):
    calls, _ = offline_backend
    data = _data([_request(asset_id) for asset_id in ids])
    jobs = [row for row in build_visual_asset_plan(data) if row["role"].startswith("vfx:")]
    assert all(row["assetId"].startswith("infini_vfx_job_") for row in jobs)
    assert len({row["assetId"].casefold() for row in jobs}) == len(ids)
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    assets = out["vfxManifest"]["assets"]
    assert [asset["id"] for asset in assets] == list(ids)
    names = [Path(asset["spritePath"]).name for asset in assets]
    assert all(name.startswith("infini_vfx_png_") for name in names)
    assert len({name.casefold() for name in names}) == len(ids)
    assert all(asset["spriteStatus"] == "generated" for asset in assets)
    roster = asset_sync_service.runtime_asset_files(out)
    assert set(names) <= set(roster)
    assert len(roster) == len(ids) + 1
    assert all(name in [Path(asset["spritePath"]).name for asset in assets] for name in roster if name.startswith("infini_vfx_png_"))
    assert len([call for call in calls if call["id"].startswith("infini_vfx_job_")]) == len(ids)


def test_same_authored_asset_id_changed_png_does_not_replace_distributed_file(offline_backend, monkeypatch):
    data = _data()
    first = visual_sprite_generation.maybe_generate_visual_assets(copy.deepcopy(data))
    old_path = Path(first["vfxManifest"]["assets"][0]["spritePath"])
    old_bytes = old_path.read_bytes()
    original = visual_sprite_generation.generate_sdcpp
    def changed_fixture(prompt, negative, asset_id, canvas):
        paths = original(prompt, negative, asset_id, canvas)
        if asset_id.startswith("infini_vfx_job_"):
            with Image.open(paths[0]) as image:
                image.putpixel((14, 23), (50, 210, 90, 144))
                image.save(paths[0])
        return paths
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", changed_fixture)
    second = visual_sprite_generation.maybe_generate_visual_assets(copy.deepcopy(data))
    new_path = Path(second["vfxManifest"]["assets"][0]["spritePath"])
    assert new_path != old_path
    assert new_path.read_bytes() != old_bytes
    assert old_path.read_bytes() == old_bytes
    assert not list(new_path.parent.glob(".infini_vfx_png_*.part"))


@pytest.mark.parametrize("collision", ["item", "ingredient", "different_directory_same_name"])
def test_delivery_rejects_cross_role_or_cross_request_filename_aliasing(offline_backend, tmp_path, collision):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(), _request("band", layout="strip")]))
    first, second = data["vfxManifest"]["assets"]
    if collision == "item":
        first["spritePath"] = data["visual"]["spritePath"]
    elif collision == "ingredient":
        second["spritePath"] = first["spritePath"]
    else:
        source = Path(data["visual"]["spritePath"])
        target = tmp_path / "another_directory" / source.name.upper()
        target.parent.mkdir()
        target.write_bytes(source.read_bytes())
        first["spritePath"] = str(target)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not report["ok"]
    assert "asset_roster_filename_collision" in {problem["code"] for problem in report["problems"]}


@pytest.mark.parametrize("failure", ["wrong_canvas", "backend_exception", "invalid_png"])
def test_strip_retry_keeps_asymmetric_uv_landmarks_and_publishes_only_final_png(offline_backend, monkeypatch, failure):
    calls, _ = offline_backend
    original_backend = visual_sprite_generation.generate_sdcpp
    original_bake = sprite_postprocess.bake_sprite_from_master
    attempts = 0
    bakes = 0
    original_refit = visual_sprite_generation.refit_processed_sprite_to_contract
    def backend_with_first_failure(prompt, negative, asset_id, canvas):
        nonlocal attempts
        if asset_id.startswith("infini_vfx_job_"):
            attempts += 1
            if attempts == 1 and failure == "backend_exception":
                calls.append({"id": asset_id, "prompt": prompt, "canvas": canvas})
                raise RuntimeError("offline first-attempt failure")
        paths = original_backend(prompt, negative, asset_id, canvas)
        if asset_id.startswith("infini_vfx_job_") and attempts == 1 and failure == "invalid_png":
            Path(paths[0]).write_bytes(b"offline corrupt PNG fixture")
        return paths
    def bake_with_first_wrong_canvas(master, target_size, role="item"):
        nonlocal bakes
        image = original_bake(master, target_size, role)
        if role == "vfx_strip":
            bakes += 1
            if bakes == 1 and failure == "wrong_canvas":
                return image.resize((24, 24))
        return image
    def forbidden_refit(*args, **kwargs):
        if args[3] == "vfx_strip":
            raise AssertionError("strip must not enter silhouette refit")
        return original_refit(*args, **kwargs)
    monkeypatch.setattr(visual_sprite_generation, "SPRITE_RETRIES", 1)
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", backend_with_first_failure)
    monkeypatch.setattr(sprite_postprocess, "bake_sprite_from_master", bake_with_first_wrong_canvas)
    monkeypatch.setattr(visual_sprite_generation, "refit_processed_sprite_to_contract", forbidden_refit)
    out = visual_sprite_generation.maybe_generate_visual_assets(_data([_request("band", layout="strip")]))
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "generated"
    assert attempts == 2
    with Image.open(asset["spritePath"]) as image:
        assert image.size == (32, 32)
        assert image.getchannel("A").getbbox() == (0, 8, 32, 12)
        assert image.getpixel((0, 8))[3] == image.getpixel((31, 11))[3] == 144
        assert image.getpixel((31, 11))[2] > image.getpixel((31, 11))[0]
    assert "retry" not in Path(asset["spritePath"]).name
    assert "refit" not in Path(asset["spritePath"]).name
    assert len([name for name in asset_sync_service.runtime_asset_files(out) if name.startswith("infini_vfx_png_")]) == 1


def test_tiny_strip_does_not_enter_silhouette_refit(offline_backend, monkeypatch):
    original_backend = visual_sprite_generation.generate_sdcpp
    original_refit = visual_sprite_generation.refit_processed_sprite_to_contract
    def tiny_uv_fixture(prompt, negative, asset_id, canvas):
        paths = original_backend(prompt, negative, asset_id, canvas)
        if asset_id.startswith("infini_vfx_job_"):
            image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((2, 48, 3, 49), fill=(210, 100, 20, 144))
            image.save(paths[0])
        return paths
    def forbidden_refit(*args, **kwargs):
        if args[3] == "vfx_strip":
            raise AssertionError("strip silhouette refit was called")
        return original_refit(*args, **kwargs)
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", tiny_uv_fixture)
    monkeypatch.setattr(visual_sprite_generation, "refit_processed_sprite_to_contract", forbidden_refit)
    out = visual_sprite_generation.maybe_generate_visual_assets(_data([_request("band", layout="strip")]))
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] in {"generated", "generated_warn_invalid"}, out["debug"]
    with Image.open(asset["spritePath"]) as image:
        assert image.getchannel("A").getbbox() == (1, 24, 2, 25)
        assert image.getpixel((1, 24))[3] == 144



def test_requested_asset_rejects_backend_internal_procedural_substitution(offline_backend, monkeypatch, tmp_path):
    original_backend = visual_sprite_generation.generate_sdcpp
    def backend_fallback_fixture(prompt, negative, asset_id, canvas):
        paths = original_backend(prompt, negative, asset_id, canvas)
        if asset_id.startswith("infini_vfx_job_"):
            path = tmp_path / (asset_id + "_procedural.png")
            path.write_bytes(Path(paths[0]).read_bytes())
            return [str(path)]
        return paths
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", backend_fallback_fixture)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ALLOW_PROCEDURAL_FALLBACK", True)
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "failed"
    assert asset["spritePath"] == asset["spriteUrl"] == ""
    assert asset["spriteTechnicalScore"] == 0.0
    assert not list(tmp_path.glob("infini_vfx_png_*.png"))



@pytest.mark.parametrize("canvas", [16, 24, 32, 48, 64, 96, 128])
@pytest.mark.parametrize("layout", ["cutout", "strip"])
@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath"])
def test_all_authored_canvases_and_layouts_use_either_renderer(offline_backend, canvas, layout, renderer):
    data = _data([_request("ingredient", layout=layout, canvas=canvas)])
    data["vfxManifest"]["slots"] = [_slot("literal", "ingredient", renderer=renderer)]
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] in {"generated", "generated_warn_invalid"}
    with Image.open(asset["spritePath"]) as image:
        assert image.size == (canvas, canvas)
        assert sum(image.getchannel("A").histogram()[1:255]) > 0
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert report["ok"], report["problems"]


@pytest.mark.parametrize("backend_state", ["off", "configuration_error"])
def test_disabled_backend_materializes_all_requested_metadata_without_ready_paths(offline_backend, monkeypatch, backend_state):
    calls, _ = offline_backend
    if backend_state == "off":
        monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND", "off")
        expected_status = "prompt_only"
    else:
        monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND_CONFIG_ERROR", "offline configuration failure fixture")
        expected_status = "backend_config_error"
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    asset = out["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == expected_status
    assert asset["spritePath"] == asset["spriteUrl"] == ""
    assert asset["spriteTechnicalScore"] == 0.0
    assert calls == []
    assert not visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)["ok"]


def test_partial_generation_does_not_hide_failed_requested_ingredient(offline_backend, monkeypatch):
    bad_request = _request("bad", layout="strip")
    bad_request["negativePrompt"] += ", offline partial failure fixture"
    data = _data([_request("good"), bad_request])
    original = visual_sprite_generation.generate_sdcpp
    def partial_backend(prompt, negative, asset_id, canvas):
        # Intermediates are invocation-owned now; target the exact authored request,
        # not the plan's stable ID as a mutable backend filename.
        if negative == bad_request["negativePrompt"]:
            raise RuntimeError("offline partial failure fixture")
        return original(prompt, negative, asset_id, canvas)
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", partial_backend)
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    good, bad = out["vfxManifest"]["assets"]
    assert good["spriteStatus"] == "generated"
    assert asset_sync_service.is_complete_png_file(good["spritePath"])
    assert bad["spriteStatus"] == "failed"
    assert bad["spritePath"] == bad["spriteUrl"] == ""
    assert bad["spriteTechnicalScore"] == 0.0
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["ok"]
    assert any(problem.get("assetId") == "bad" for problem in report["problems"])


def test_ready_asset_cannot_exceed_existing_network_file_limit(offline_backend):
    from PIL.PngImagePlugin import PngInfo
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    path = Path(out["vfxManifest"]["assets"][0]["spritePath"])
    info = PngInfo()
    info.add_text("offline_fixture_padding", "x" * (8 * 1024 * 1024))
    with Image.open(path) as image:
        image.save(path, pnginfo=info)
    assert asset_sync_service.is_complete_png_file(path)
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["ok"]
    job = next(row for row in report["slots"] if row["role"] == "vfx:grain")
    assert "asset_png_byte_limit_exceeded" in job["validation"]["reasons"]


def test_storage_requires_ready_nested_existing_texture_even_without_new_requests():
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.storage import world_storage
    data = _data([])
    slot = _slot("reuse", "")
    slot["element"]["texture"] = {"source": "item", "assetId": ""}
    data["vfxManifest"]["slots"] = [slot]
    assert validate_vfx_manifest_wire(data)["ok"]
    assert world_storage.is_deliverable_recipe_payload(data) is False



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


@pytest.mark.parametrize("source", ["item", "entity", "impact"])
@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath"])
@pytest.mark.parametrize("damage", ["missing", "pending"])
def test_nested_existing_texture_requires_ready_exact_producer(offline_backend, monkeypatch, source, renderer, damage):
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.storage import world_storage
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(visual_delivery_gate, "VISUAL_REQUIRE_ITEM_SPRITE", False)
    data = _existing_texture_data(source, renderer)
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    assert validate_vfx_manifest_wire(out)["ok"]
    assert visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)["ok"]
    orb_visual = next(row for row in out["runtimeProgram"]["entities"] if row["id"] == "orb")["visual"]
    producer = out["visual"] if source == "item" else orb_visual
    prefix = "impactSprite" if source == "impact" else "sprite"
    if damage == "missing":
        Path(producer[prefix + "Path"]).unlink()
    else:
        producer[prefix + "Status"] = "pending"
    assert validate_vfx_manifest_wire(out)["ok"]  # shape is intentionally not an image gate
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["ok"], report
    assert any(problem["code"] == "required_vfx_texture_not_ready" for problem in report["problems"])
    assert world_storage.is_deliverable_recipe_payload(out) is False
    assert "assets" not in out["vfxManifest"]



def test_delivery_rejects_aliasing_unused_overlay_and_requested_ingredient(offline_backend):
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    asset = out["vfxManifest"]["assets"][0]
    out["visual"]["equipOverlayPath"] = asset["spritePath"]
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["equipmentOverlayRequired"]
    assert "asset_roster_filename_collision" in {problem["code"] for problem in report["problems"]}


def test_delivery_counts_whole_canonical_roster_even_for_unneeded_overlay(offline_backend, monkeypatch, tmp_path):
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    overlay = tmp_path / "offline_unneeded_overlay.png"
    _raw_fixture(overlay)
    out["visual"]["equipOverlayPath"] = str(overlay)
    assert len(asset_sync_service.runtime_asset_files(out)) == 3
    monkeypatch.setattr(visual_delivery_gate, "MAX_DELIVERABLE_ASSET_FILES", 2)
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["equipmentOverlayRequired"]
    assert "asset_roster_file_limit_exceeded" in {problem["code"] for problem in report["problems"]}



@pytest.mark.parametrize("status", ["pending", "failed", "fallback", "fallback_after_failed_generation", "prompt_only"])
def test_ready_pixels_do_not_allow_pending_or_fallback_ingredient_admission(offline_backend, tmp_path, status):
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.pipelines.combine_pipeline import _cached_payload_report, _vfx_manifest_report
    from infini_local.storage import world_storage
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    asset = out["vfxManifest"]["assets"][0]
    asset["spriteStatus"] = status
    assert asset_sync_service.is_complete_png_file(asset["spritePath"])
    assert validate_vfx_manifest_wire(out)["ok"]
    assert _vfx_manifest_report(out)["ok"]  # wire helper remains the authority
    assert not visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)["ok"]
    assert not world_storage.is_deliverable_recipe_payload(out)
    assert not _cached_payload_report(out)["ok"]
    root = tmp_path / "world"
    with pytest.raises(ValueError, match="non-deliverable"):
        world_storage.write_world_recipe_cache(root, "test", "recipe", "world", out)
    path = world_storage.world_recipe_file(root, "world", "recipe")
    assert not path.exists()
    world_storage.atomic_write_json(path, out)  # explicit old/incomplete cache fixture
    assert world_storage.read_world_recipe_cache(root, "test", "v5", "recipe", "world") is None
    assert not path.exists()


def test_failed_atomic_publication_never_returns_intermediate_or_changes_old_png(offline_backend, monkeypatch, tmp_path):
    data = _data([_request("band", layout="strip")])
    first = visual_sprite_generation.maybe_generate_visual_assets(copy.deepcopy(data))
    old_path = Path(first["vfxManifest"]["assets"][0]["spritePath"])
    old_bytes = old_path.read_bytes()
    real_replace = visual_sprite_generation.os.replace
    def failed_publication(source, destination):
        if Path(destination).name.startswith("infini_vfx_png_"):
            assert Path(source).suffix == ".part"
            assert asset_sync_service.is_complete_png_file(source)
            raise OSError("offline atomic publication failure fixture")
        return real_replace(source, destination)
    monkeypatch.setattr(visual_sprite_generation.os, "replace", failed_publication)
    second = visual_sprite_generation.maybe_generate_visual_assets(copy.deepcopy(data))
    asset = second["vfxManifest"]["assets"][0]
    assert asset["spriteStatus"] == "failed"
    assert asset["spritePath"] == asset["spriteUrl"] == ""
    assert asset["spriteTechnicalScore"] == 0.0
    assert old_path.read_bytes() == old_bytes
    assert not list(tmp_path.glob(".infini_vfx_png_*.part"))


@pytest.mark.parametrize("field,value", [
    ("id", "Glow"), ("prompt", "one isolated other ingredient"),
    ("negativePrompt", "exact different negative"), ("canvasSize", 48), ("layout", "strip"),
])
def test_processing_digest_uses_each_exact_request_field(field, value):
    from infini_local.pipelines.visual_asset_plan import vfx_asset_job_id
    data = _data()
    first = data["vfxManifest"]["assets"][0]
    second = {**first, field: value}
    assert vfx_asset_job_id(data, first).casefold() != vfx_asset_job_id(data, second).casefold()


def test_both_processing_and_final_png_identity_are_exact_recipe_scoped(offline_backend):
    from infini_local.pipelines.visual_asset_plan import vfx_asset_job_id
    first = _data()
    second = copy.deepcopy(first)
    second["vfxManifest"]["recipeId"] = "Offline_recipe"
    assert vfx_asset_job_id(first, first["vfxManifest"]["assets"][0]) != vfx_asset_job_id(second, second["vfxManifest"]["assets"][0])
    out1 = visual_sprite_generation.maybe_generate_visual_assets(first)
    out2 = visual_sprite_generation.maybe_generate_visual_assets(second)
    asset1, asset2 = out1["vfxManifest"]["assets"][0], out2["vfxManifest"]["assets"][0]
    assert Path(asset1["spritePath"]).read_bytes() == Path(asset2["spritePath"]).read_bytes()
    assert Path(asset1["spritePath"]).name.casefold() != Path(asset2["spritePath"]).name.casefold()



def test_network_stripped_caption_fixture_retains_ready_pngs_refs_and_metadata(offline_backend):
    """Python admission of an ABI transport fixture, not a C# ToNetworkJson claim."""
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.pipelines.combine_pipeline import _cached_payload_report
    from infini_local.storage import world_storage
    full = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(), _request("band", layout="strip")]))
    stripped = copy.deepcopy(full)
    for asset in stripped["vfxManifest"]["assets"]:
        asset["prompt"] = asset["negativePrompt"] = ""
        asset["spritePath"] = Path(asset["spritePath"]).name
    assert validate_vfx_manifest_wire(stripped)["ok"]
    assert visual_delivery_gate.visual_delivery_report(stripped, check_backend_config=False)["ok"]
    assert world_storage.is_deliverable_recipe_payload(stripped)
    assert _cached_payload_report(stripped)["ok"]
    clean = world_storage.sanitize_recipe_for_delivery(stripped)
    assert clean["vfxManifest"]["assets"] == stripped["vfxManifest"]["assets"]
    assert clean["vfxManifest"]["slots"] == full["vfxManifest"]["slots"]
    assert asset_sync_service.runtime_asset_files(clean) == asset_sync_service.runtime_asset_files(full)
    assert full["vfxManifest"]["assets"][0]["prompt"] == _request()["prompt"]
