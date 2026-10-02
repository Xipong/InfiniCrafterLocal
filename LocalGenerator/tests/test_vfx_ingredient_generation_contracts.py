"""Offline canonical vfx ingredient generation contracts; no live services."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from infini_local.pipelines import sprite_postprocess, visual_sprite_generation
from infini_local.pipelines import visual_delivery_gate
from infini_local.services import asset_sync_service
from infini_local.core.vfx_manifest import VFX_DIRECTOR_SCHEMA
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from tests.vfx_image_fixtures import _data, _request, _slot, _raw_fixture, offline_backend


def test_absent_vfx_requests_do_not_add_jobs_or_wire_fields():
    legacy = _data([])
    before = copy.deepcopy(legacy)
    assert not any(row["role"].startswith("vfx:") for row in build_visual_asset_plan(legacy))
    assert legacy == before
    assert "assets" not in legacy["vfxManifest"]


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


def test_strip_alpha_coverage_can_fill_full_frame_without_silhouette_heuristics(tmp_path):
    path = tmp_path / "offline_full_frame_soft_strip.png"
    Image.new("RGBA", (32, 32), (210, 100, 20, 144)).save(path)
    validation = sprite_postprocess.validate_processed_sprite(str(path), "vfx_strip", expected_canvas=32)
    assert validation["ok"], validation
    assert not sprite_postprocess.sprite_validation_fatal(validation)


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
    def changed_fixture(prompt, negative, asset_id, canvas, *, output_dir=None):
        paths = original(prompt, negative, asset_id, canvas, output_dir=output_dir)
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
    def backend_with_first_failure(prompt, negative, asset_id, canvas, *, output_dir=None):
        nonlocal attempts
        if asset_id.startswith("infini_vfx_job_"):
            attempts += 1
            if attempts == 1 and failure == "backend_exception":
                calls.append({"id": asset_id, "prompt": prompt, "canvas": canvas})
                raise RuntimeError("offline first-attempt failure")
        paths = original_backend(prompt, negative, asset_id, canvas, output_dir=output_dir)
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
    def tiny_uv_fixture(prompt, negative, asset_id, canvas, *, output_dir=None):
        paths = original_backend(prompt, negative, asset_id, canvas, output_dir=output_dir)
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

INGREDIENT_CASES = [("grain", 32, "cutout", "shared")] + [
    ("band" if layout == "strip" else "ingredient", canvas, layout, renderer)
    for canvas in (16, 24, 32, 48, 64, 96, 128) for layout in ("cutout", "strip")
    for renderer in ("spriteElement", "texturedPath")
]

@pytest.mark.parametrize("asset_id,canvas,layout,renderer", INGREDIENT_CASES,
                         ids=[f"{name}-{canvas}-{layout}-{renderer}" for name, canvas, layout, renderer in INGREDIENT_CASES])
def test_ingredient_plan_pixels_and_delivery(offline_backend, monkeypatch, asset_id, canvas, layout, renderer):
    import hashlib
    calls, events = offline_backend
    data = _data([_request(asset_id, layout=layout, canvas=canvas)])
    if renderer != "shared":
        data["vfxManifest"]["slots"] = [_slot("literal_use", asset_id, renderer=renderer)]
    before = copy.deepcopy(data)
    role = "vfx:" + asset_id
    jobs = [row for row in build_visual_asset_plan(data) if row["role"].startswith("vfx:")]
    assert len(jobs) == 1
    job_id = jobs[0]["assetId"]
    assert job_id.startswith("infini_vfx_job_") and len(job_id.removeprefix("infini_vfx_job_")) == 64
    authored = {key: before["vfxManifest"]["assets"][0][key] for key in ("id", "prompt", "negativePrompt", "canvasSize", "layout")}
    assert jobs[0] == {
        "role": role, "assetId": job_id, "vfxAssetId": asset_id,
        "assetMode": "baked_sprite", "runtimeGateReason": "authored_vfx_texture_ingredient",
        "prompt": authored["prompt"], "negativePrompt": authored["negativePrompt"],
        "canvas": canvas, "layout": layout, "processingRole": "vfx_" + layout,
        "required": True, "status": "pending", "path": "", "url": "", "technicalScore": 0.0,
    }
    assert data == before and "entityId" not in jobs[0]
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    asset = out["vfxManifest"]["assets"][0]
    vfx_calls = [row for row in calls if "_vfx_" in row["id"]]
    assert len(vfx_calls) == 1
    call = vfx_calls[0]
    assert call["id"].startswith("infini_vfx_job_")
    assert call["canvas"] == canvas and call["negative"] == authored["negativePrompt"]
    assert authored["prompt"] in call["prompt"]
    assert events == [event for _ in calls for event in ("enter", "exit")]
    assert {key: asset[key] for key in authored} == authored
    assert asset["spriteStatus"] in {"generated", "generated_warn_invalid"}
    if renderer == "shared" or (layout == "strip" and canvas == 32):
        assert asset["spriteStatus"] == "generated"
    path = Path(asset["spritePath"])
    assert path.name.startswith("infini_vfx_png_")
    assert asset["spriteUrl"] == "/sprite/" + path.name
    assert 0.0 < asset["spriteTechnicalScore"] <= 1.0
    assert asset_sync_service.is_complete_png_file(path)
    with Image.open(path) as image:
        assert image.size == (canvas, canvas) and image.mode == "RGBA"
        assert sum(image.getchannel("A").histogram()[1:255]) > 0
        if layout == "strip" and canvas == 32:
            assert image.getchannel("A").getbbox() == (0, 8, 32, 12)
            assert image.getpixel((0, 8))[3] == image.getpixel((31, 11))[3] == 144
            assert image.getpixel((31, 11))[2] > image.getpixel((31, 11))[0]
            assert image.getpixel((0, 8))[0] > image.getpixel((0, 8))[2]
            assert image.getpixel((16, 16)) == (0, 0, 0, 0)
    if layout == "strip":
        assert "preserve the full authored frame" in call["prompt"]
        assert "centered" not in call["prompt"] and role not in call["prompt"]
    after = copy.deepcopy(out["runtimeProgram"])
    gameplay = copy.deepcopy(before["runtimeProgram"])
    for program in (gameplay, after):
        for entity in program["entities"]:
            entity.pop("visual", None)
    assert after == gameplay
    job = next(row for row in json.loads(out["debug"]["visualAssetPlan"]) if row["role"] == role)
    assert job["path"] == asset["spritePath"] and job["status"] == asset["spriteStatus"]
    metadata = json.loads(Path(out["visual"]["assetManifestPath"]).read_text())
    row = next(row for row in metadata["assets"] if row["role"] == role)
    raw = path.read_bytes()
    assert row["exists"] is True and row["file"] == path.name and row["bytes"] == len(raw)
    assert row["sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["vfxAssetId"] == asset_id and row["layout"] == layout and row["processingRole"] == "vfx_" + layout
    assert row["contract"]["role"] == "vfx_" + layout and row["contract"]["layout"] == layout
    assert row["contract"]["preserveFullFrame"] is (layout == "strip")
    assert row["contract"]["targetSizePx"] == canvas
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert report["ok"], report["problems"]
    assert len([row for row in report["slots"] if row["role"] == role]) == 1
    if renderer == "shared":
        monkeypatch.setattr(visual_delivery_gate, "MAX_DELIVERABLE_ASSET_FILES", 1)
        assert "asset_roster_file_limit_exceeded" in {row["code"] for row in visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)["problems"]}

INGREDIENT_FAILURES = [(fault, layout) for fault in ("backend_error", "wrong_canvas") for layout in ("cutout", "strip")] + [
    ("native_alpha_postprocess_io", "cutout"), ("provider_procedural", "cutout"),
    ("backend_off", "cutout"), ("backend_configuration", "cutout"), ("partial_backend", "strip"),
    ("atomic_publication", "strip"),
]

@pytest.mark.parametrize("fault,layout", INGREDIENT_FAILURES, ids=[fault + "-" + layout for fault, layout in INGREDIENT_FAILURES])
def test_required_ingredient_failure_projection(offline_backend, monkeypatch, tmp_path, fault, layout):
    calls, events = offline_backend
    request = _request("band" if fault == "atomic_publication" else "bad" if fault == "partial_backend" else "grain", layout=layout)
    if fault == "partial_backend": request["negativePrompt"] += ", offline partial failure fixture"
    data = _data([_request("good"), request] if fault == "partial_backend" else [request])
    old_path = None
    if fault == "atomic_publication":
        first = visual_sprite_generation.maybe_generate_visual_assets(copy.deepcopy(data))
        old_path = Path(first["vfxManifest"]["assets"][0]["spritePath"]); old_bytes = old_path.read_bytes()
        calls.clear(); events.clear()
    backend = visual_sprite_generation.generate_sdcpp
    def backend_boundary(prompt, negative, asset_id, canvas, *, output_dir=None):
        selected = "_vfx_" in asset_id and (fault != "partial_backend" or negative == request["negativePrompt"])
        if selected and fault in {"backend_error", "partial_backend"}:
            calls.append({"id": asset_id, "prompt": prompt, "canvas": canvas})
            raise RuntimeError("offline requested backend failure")
        paths = backend(prompt, negative, asset_id, canvas, output_dir=output_dir)
        if selected and fault == "native_alpha_postprocess_io":
            image = Image.new("RGBA", (canvas, canvas))
            ImageDraw.Draw(image).rectangle((4, 4, canvas - 5, canvas - 5), fill=(200, 110, 10, 128)); image.save(paths[0])
        if selected and fault == "provider_procedural":
            path = output_dir / (asset_id + "_procedural.png"); path.write_bytes(Path(paths[0]).read_bytes()); return [str(path)]
        return paths
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", backend_boundary)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ALLOW_PROCEDURAL_FALLBACK", True)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_STRICT_AI_AUTHORSHIP", False)
    if fault in {"native_alpha_postprocess_io", "wrong_canvas", "atomic_publication"}:
        owner, name = (visual_sprite_generation.os, "replace") if fault == "atomic_publication" else (sprite_postprocess, "prepare_sprite_master" if fault == "native_alpha_postprocess_io" else "bake_sprite_from_master")
        original = getattr(owner, name)
        def stage_boundary(*args, **kwargs):
            role = kwargs.get("role", args[3] if name == "prepare_sprite_master" and len(args) > 3 else args[2] if name == "bake_sprite_from_master" and len(args) > 2 else "item")
            if name == "replace" and Path(args[1]).name.startswith("infini_vfx_png_"):
                assert Path(args[0]).suffix == ".part" and asset_sync_service.is_complete_png_file(args[0])
                raise OSError("offline atomic publication failure")
            if fault == "native_alpha_postprocess_io" and role == "vfx_cutout":
                raise OSError("offline postprocess write failure")
            result = original(*args, **kwargs)
            return result.resize((24, 24)) if fault == "wrong_canvas" and role in {"vfx_cutout", "vfx_strip"} else result
        monkeypatch.setattr(owner, name, stage_boundary)
    if fault == "backend_off": monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND", "off")
    if fault == "backend_configuration": monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND_CONFIG_ERROR", "offline configuration failure fixture")
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    assets = out["vfxManifest"]["assets"]
    asset = assets[-1]
    expected = "prompt_only" if fault == "backend_off" else "backend_config_error" if fault == "backend_configuration" else "failed"
    assert asset["spriteStatus"] == expected
    assert asset["spritePath"] == asset["spriteUrl"] == "" and asset["spriteTechnicalScore"] == 0.0
    assert events == [event for _ in calls for event in ("enter", "exit")]
    if fault in {"backend_off", "backend_configuration"}:
        assert calls == []
    else:
        vfx_calls = [call for call in calls if "_vfx_" in call["id"]]
        assert len(vfx_calls) == (2 if fault == "partial_backend" else 1)
    if fault == "wrong_canvas":
        attempts = json.loads(out["debug"]["vfx:" + request["id"] + "SpriteValidation"])
        assert "final_canvas_mismatch" in attempts[0]["validation"]["reasons"]
    if fault == "provider_procedural": assert not list(tmp_path.glob("infini_vfx_png_*.png"))
    if fault == "partial_backend":
        assert assets[0]["spriteStatus"] == "generated" and asset_sync_service.is_complete_png_file(assets[0]["spritePath"])
    if old_path:
        assert old_path.read_bytes() == old_bytes
        assert not list(tmp_path.glob(".infini_vfx_png_*.part"))
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["ok"]
    if fault == "partial_backend": assert any(problem.get("assetId") == "bad" for problem in report["problems"])
