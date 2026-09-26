from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from infini_local.pipelines.visual_delivery_gate import visual_delivery_report
from infini_local.qa.live_no_image_fixture import (
    hydrate_no_image_fixture_assets,
    write_no_image_fixture_png,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


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
    data = build_runtime_fixture("workbench_blade")
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    for row in data["runtimeProgram"]["entities"]:
        if row["kind"] != "item_body":
            row.setdefault("visual", {})["assetMode"] = "baked_sprite"
    data["vfxManifest"] = {"slots": [{
        "entityId": entity["id"], "rendererKind": "impactRing", "textureRole": "impact",
    }]}

    hydrate_no_image_fixture_assets(data, fixture)
    assert "impactSpritePath" not in entity["visual"]
    ring_report = visual_delivery_report(data, check_backend_config=False)
    assert ring_report["ok"], ring_report["problems"]
    assert not any(slot["role"] == "impact:" + entity["id"] for slot in ring_report["slots"])

    data["vfxManifest"]["slots"][0]["rendererKind"] = "impactSprite"
    sprite_report = visual_delivery_report(data, check_backend_config=False)
    assert "required_impact_sprite_missing" in {problem["code"] for problem in sprite_report["problems"]}
    hydrate_no_image_fixture_assets(data, fixture)
    assert visual_delivery_report(data, check_backend_config=False)["ok"]
