from __future__ import annotations

import ast
import copy
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.core.vfx_manifest import _compile_manifest, validate_vfx_director_output
from infini_local.pipelines import visual_delivery_gate
from infini_local.pipelines.visual_delivery_gate import visual_delivery_report
from infini_local.qa.live_no_image_fixture import (
    hydrate_no_image_fixture_assets,
    write_no_image_fixture_png,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _vfx_output
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


@pytest.mark.parametrize("output_depth", ["short", "long"])
def test_campaign_fixture_uses_canonical_serving_root(tmp_path, monkeypatch, output_depth):
    from infini_local.core import config_bootstrap
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
    from infini_local.pipelines.combine_pipeline import _cached_payload_report
    from infini_local.services.asset_sync_service import find_asset_file

    output = tmp_path / ("run" if output_depth == "short" else "deep-campaign-" * 12)
    sprites = output / "cache" / "sprites"
    world_recipes = output / "cache" / "world_recipes"
    monkeypatch.setattr(config_bootstrap, "SPRITE_DIR", sprites)
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", sprites)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", world_recipes)

    # Execute the actual campaign fixture owner without argparse, config loading
    # or inference. A helper-only check would miss an OUT-local fixture again.
    harness = Path(__file__).resolve().parents[2] / "toolbox/live-generation/generate_20_items_without_images.py"
    nodes: list[ast.stmt] = [
        node for node in ast.parse(harness.read_text(encoding="utf-8")).body
        if (isinstance(node, ast.ImportFrom) and node.module == "infini_local.core.config_bootstrap")
        or (isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "NO_IMAGE_FIXTURE"
            for target in node.targets
        ))
    ]
    assert sum(isinstance(node, ast.Assign) for node in nodes) == 1
    namespace = {"OUT": output, "write_no_image_fixture_png": write_no_image_fixture_png}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(harness), "exec"), namespace)
    fixture = namespace["NO_IMAGE_FIXTURE"]
    if output_depth == "long":
        assert len(str(fixture.resolve())) > 139

    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    data.update(id="qa-serving-root-control", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION)
    data["vfxManifest"] = _compile_manifest(data, {
        "effectMagnitude": 0.0, "visualBudgetClass": "tiny",
        "motif": {"element": "neutral", "shapeLanguage": "none", "motionLanguage": "none",
                  "paletteRole": "primary", "rhythm": 1.0, "chaos": 0.0}, "slots": [],
    }, "no-image-serving-root")
    for entity in data["runtimeProgram"]["entities"]:
        entity.setdefault("visual", {})["assetMode"] = "baked_sprite"
    before = copy.deepcopy(data)
    delivered = sanitize_recipe_for_delivery(hydrate_no_image_fixture_assets(data, fixture))
    report = _cached_payload_report(delivered)
    assert report.get("runtime", {}).get("ok"), report
    assert report.get("vfx", {}).get("ok"), report
    assert report["ok"], report["errors"]
    assert fixture == sprites / "qa-no-image-fixture.png"
    assert find_asset_file(fixture.name, sprite_dir=sprites, world_recipes_dir=world_recipes) == fixture
    assert delivered["visual"]["spritePath"] == str(fixture.resolve())
    for original, entity in zip(before["runtimeProgram"]["entities"], delivered["runtimeProgram"]["entities"]):
        assert {key: value for key, value in entity.items() if key != "visual"} == {
            key: value for key, value in original.items() if key != "visual"
        }
        assert entity["visual"]["assetMode"] == original["visual"]["assetMode"]
        assert entity["visual"]["spritePath"] == str(fixture.resolve())

    short_reference = copy.deepcopy(delivered)
    short_reference["visual"]["spritePath"] = fixture.name
    for entity in short_reference["runtimeProgram"]["entities"]:
        entity["visual"]["spritePath"] = fixture.name
    assert _cached_payload_report(short_reference)["ok"]

    # An existing absolute outside-root PNG is not an authority. Keep this
    # refusal even though it has the same basename and bytes as the QA fixture.
    outside = write_no_image_fixture_png(output / fixture.name)
    assert outside.read_bytes() == fixture.read_bytes()
    fixture.unlink()
    refused = _cached_payload_report(sanitize_recipe_for_delivery(
        hydrate_no_image_fixture_assets(copy.deepcopy(before), outside)
    ))
    assert not refused["ok"]
    codes = {problem["code"] for problem in refused["visual"]["problems"]}
    assert {"required_entity_sprite_missing", "asset_roster_file_missing"} <= codes

    # A present serving-root file still has to pass the production PNG gate.
    write_no_image_fixture_png(fixture)
    fixture.write_bytes(fixture.read_bytes()[:-1])
    corrupt = _cached_payload_report(delivered)
    assert not corrupt["ok"]
    assert "asset_roster_invalid_png" in {
        problem["code"] for problem in corrupt["visual"]["problems"]
    }


@pytest.fixture(autouse=True)
def isolated_serving_roots(monkeypatch, tmp_path):
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")


def test_no_image_fixture_hydrates_real_delivery_paths_without_backend(tmp_path: Path) -> None:
    fixture_path = write_no_image_fixture_png(tmp_path / "qa-fixture.png")
    # Exercise the decoder used by delivery consumers, not a parallel partial PNG parser.
    with Image.open(fixture_path) as image:
        assert image.format == "PNG"
        assert image.size == (32, 32)
        assert image.mode == "RGBA"
        image.load()
        assert image.getpixel((0, 0)) == (24, 24, 24, 255)
        assert image.getpixel((4, 0)) == (255, 0, 255, 255)
    # Negative control: a matching PNG header/dimensions with a broken IHDR CRC
    # cannot pass merely because its signature looks right.
    damaged = bytearray(fixture_path.read_bytes())
    damaged[24] ^= 1
    with pytest.raises(OSError):
        Image.open(BytesIO(damaged)).load()

    data = build_runtime_fixture("workbench_blade")
    data["visual"] = {}
    non_item = [
        entity
        for entity in data["runtimeProgram"]["entities"]
        if entity["kind"] != "item_body"
    ]
    non_item[0]["visualRole"] = "projectile"
    non_item[0]["visual"] = {"assetMode": "baked_sprite"}
    non_item[1]["visualRole"] = "child"
    non_item[1]["visual"] = {"assetMode": "reuse_item_icon"}

    hydrated = hydrate_no_image_fixture_assets(data, fixture_path)
    report = visual_delivery_report(hydrated, check_backend_config=False)

    assert report["ok"], report
    assert hydrated["visual"]["spriteStatus"] == "qa_no_image_fixture"
    item_body = next(entity for entity in data["runtimeProgram"]["entities"] if entity["kind"] == "item_body")
    assert item_body["visual"]["assetMode"] == "baked_sprite"
    assert item_body["visual"]["spriteStatus"] == "qa_no_image_fixture"
    assert item_body["visual"]["spritePath"] == str(fixture_path.resolve())
    assert non_item[0]["visual"]["spriteStatus"] == "qa_no_image_fixture"
    assert non_item[1]["visual"]["spriteStatus"] == "reused_item_icon"
    assert hydrated["debug"]["noImageQaFixturePath"] == str(fixture_path.resolve())


def test_no_image_fixture_hydrates_canonical_required_asset_plan_roles(tmp_path: Path) -> None:
    fixture_path = write_no_image_fixture_png(tmp_path / "qa-impact-fixture.png")
    data = build_runtime_fixture("workbench_blade")
    data["accessory"] = {"enabled": True}
    entities = data["runtimeProgram"]["entities"]
    required = entities[1]
    unrelated = entities[2]
    required.setdefault("visual", {})["impactSpriteStatus"] = "pending"
    unrelated.setdefault("visual", {})["impactSpriteStatus"] = "pending"
    data["vfxManifest"] = {
        "slots": [{
            "entityId": required["id"],
            "rendererKind": "impactSprite",
            "textureRole": "impact",
        }],
    }

    hydrated = hydrate_no_image_fixture_assets(data, fixture_path)
    required_visual = required["visual"]
    assert required_visual["impactSpriteStatus"] == "qa_no_image_fixture"
    assert required_visual["impactSpritePath"] == str(fixture_path.resolve())
    assert required_visual["impactSpriteUrl"] == ""
    assert required_visual["impactSpriteTechnicalScore"] == 1.0
    assert unrelated["visual"]["impactSpriteStatus"] == "pending"
    assert "impactSpritePath" not in unrelated["visual"]
    visual = hydrated["visual"]
    assert visual["equipOverlayStatus"] == "qa_no_image_fixture"
    assert visual["equipOverlayPath"] == str(fixture_path.resolve())
    assert visual["equipOverlayUrl"] == ""
    assert visual["equipOverlayTechnicalScore"] == 1.0
    assert visual["equipOverlayScore"] == 1.0
    problem_codes = {
        str(problem.get("code") or "")
        for problem in visual_delivery_report(hydrated, check_backend_config=False)["problems"]
    }
    assert "required_equipment_overlay_missing" not in problem_codes
    assert "required_impact_sprite_missing" not in problem_codes


def test_primitive_impact_ring_does_not_require_a_texture_but_impact_sprite_does(tmp_path: Path) -> None:
    fixture = write_no_image_fixture_png(tmp_path / "no-image.png")
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    for row in data["runtimeProgram"]["entities"]:
        if row["kind"] != "item_body":
            row.setdefault("visual", {})["assetMode"] = "baked_sprite"
    authored = _vfx_output(data)
    authored["slots"][0].update(entityId=entity["id"], event="periodic",
                                rendererKind="impactRing", textureRole="impact")
    report = validate_vfx_director_output(authored, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = _compile_manifest(data, report["normalized"], "no_image_impact_probe")

    hydrate_no_image_fixture_assets(data, fixture)
    assert "impactSpritePath" not in entity["visual"]
    ring_report = visual_delivery_report(data, check_backend_config=False)
    assert ring_report["ok"], ring_report["problems"]
    assert not any(slot["role"] == "impact:" + entity["id"] for slot in ring_report["slots"])

    data["vfxManifest"]["slots"][0]["rendererKind"] = "impactSprite"
    sprite_report = visual_delivery_report(data, check_backend_config=False)
    assert "required_impact_sprite_missing" in {problem["code"] for problem in sprite_report["problems"]}
    hydrate_no_image_fixture_assets(data, fixture)
    assert "required_vfx_texture_not_ready" in {
        problem["code"] for problem in visual_delivery_report(data, check_backend_config=False)["problems"]
    }
    # The no-image hydrator deliberately labels QA bytes, not a completed image
    # execution. Supply that result explicitly for this offline delivery fixture.
    entity["visual"]["impactSpriteStatus"] = "generated"
    final_report = visual_delivery_report(data, check_backend_config=False)
    assert final_report["ok"], final_report["problems"]
