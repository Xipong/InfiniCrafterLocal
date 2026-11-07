"""Current body geometry is required at delivery, not in gameplay drafts."""
from __future__ import annotations

import copy

import pytest
from PIL import Image

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.vfx.projection import _compile_manifest
from infini_local.pipelines.visual import delivery
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.storage import image_store, world_storage
from infini_local.web.vfx_debug_routes import _sample_data


def _body_geometry(source="body_segment"):
    geometry = {
        "schema": "infini.body-geometry.v1", "source": source,
        "widthPx": 0.5, "color": "#13579B", "opacity": 0.4,
    }
    if source == "body_segment":
        geometry.update(lengthPx=37, axis="rotation")
    return geometry


@pytest.fixture
def current_body(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(delivery, "WORLD_RECIPES_DIR", tmp_path / "assets")
    path = tmp_path / "current-body-item.png"
    Image.new("RGBA", (32, 32), (19, 87, 155, 255)).save(path)
    data = _sample_data()
    path = image_store.publish(tmp_path, data, "item", b"current-body-item", path)
    data["visual"] = {
        "spritePath": str(path), "spriteStatus": "generated",
        "renderSizePx": 32, "forwardAngleDegrees": 0,
    }
    item, body = data["runtimeProgram"]["entities"]
    item["visual"] = {"role": "inventory_item", "assetMode": "baked_sprite",
                      "spritePath": str(path), "spriteStatus": "generated"}
    body["visual"] = {
        "role": "projectile", "assetMode": "runtime_geometry", "spriteStatus": "not_required",
        "spritePath": "", "geometry": _body_geometry(),
    }
    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, "current-body")
    assert validate_runtime_wire(data)["ok"]
    report = delivery.visual_delivery_report(data, check_backend_config=False)
    assert report["ok"], report["problems"]
    assert world_storage.is_deliverable_recipe_payload(data)
    return data


@pytest.mark.parametrize("source", ["body_segment", "collision_path"])
def test_current_geometry_delivery_and_cache_preserve_authored_geometry(current_body, tmp_path, source):
    body = current_body["runtimeProgram"]["entities"][1]
    body["visual"]["geometry"] = _body_geometry(source)
    if source == "collision_path":
        body["beamGeometry"] = {"lengthPx": 64, "widthPx": 8, "raycastTiles": False}
        body["aim"] = {"source": "initial", "turnOwner": False}
    before = copy.deepcopy(current_body)
    assert delivery.visual_delivery_report(current_body, check_backend_config=False)["ok"]
    assert world_storage.is_deliverable_recipe_payload(current_body)
    expected = world_storage.sanitize_recipe_for_delivery(current_body)
    world_storage.write_world_recipe_cache(tmp_path / "cache", "test", "body", "world", current_body)
    cached = world_storage.read_world_recipe_cache(tmp_path / "cache", "test", "v5", "body", "world")
    assert cached is not None
    assert cached["runtimeProgram"] == expected["runtimeProgram"]
    assert current_body == before


@pytest.mark.parametrize("missing", ["geometry", "widthPx", "color", "opacity", "lengthPx", "axis"])
def test_missing_authored_body_geometry_blocks_final_delivery_and_cache(current_body, tmp_path, missing):
    body = current_body["runtimeProgram"]["entities"][1]
    if missing == "geometry":
        del body["visual"]["geometry"]
    else:
        del body["visual"]["geometry"][missing]
    before = copy.deepcopy(current_body)
    report = delivery.visual_delivery_report(current_body, check_backend_config=False)
    assert not report["ok"], report
    assert any(problem["code"] in {"required_body_geometry_missing", "invalid_body_geometry"}
               for problem in report["problems"])
    assert not next(slot for slot in report["slots"] if slot["entityId"] == "orb")["usable"]
    assert not world_storage.is_deliverable_recipe_payload(current_body)
    with pytest.raises(ValueError, match="non-deliverable"):
        world_storage.write_world_recipe_cache(tmp_path / "cache", "test", "body", "world", current_body)
    assert not world_storage.world_recipe_file(tmp_path / "cache", "world", "body").exists()
    assert current_body == before


def test_missing_body_geometry_cached_record_is_not_delivered_or_rewritten(current_body, tmp_path):
    cache = tmp_path / "cache"
    world_storage.write_world_recipe_cache(cache, "test", "body", "world", current_body)
    target = world_storage.world_recipe_file(cache, "world", "body")
    retained = world_storage.read_json_file(target)
    assert retained is not None
    del retained["runtimeProgram"]["entities"][1]["visual"]["geometry"]
    world_storage.atomic_write_json(target, retained)
    raw = target.read_bytes()
    with pytest.raises(world_storage.RecipeAssetsUnavailable) as refused:
        world_storage.read_world_recipe_cache(cache, "test", "v5", "body", "world")
    assert "required_body_geometry_missing" in {row["code"] for row in refused.value.report["problems"]}
    assert target.read_bytes() == raw


def test_explicit_no_asset_remains_deliverable_without_geometry(current_body):
    body = current_body["runtimeProgram"]["entities"][1]
    body["visual"] = {"role": "projectile", "assetMode": "no_asset", "spriteStatus": "not_required", "spritePath": ""}
    assert delivery.visual_delivery_report(current_body, check_backend_config=False)["ok"]
    assert world_storage.is_deliverable_recipe_payload(current_body)


@pytest.mark.parametrize("status,accepted", [("generated_warn_invalid", True),
                                            ("fallback", False), ("fallback_after_failed_generation", False)])
def test_current_body_delivery_requires_completed_image_producer(current_body, status, accepted):
    current_body["visual"]["spriteStatus"] = status
    current_body["runtimeProgram"]["entities"][0]["visual"]["spriteStatus"] = status
    report = delivery.visual_delivery_report(current_body, check_backend_config=False)
    assert report["ok"] is accepted, report["problems"]
    assert world_storage.is_deliverable_recipe_payload(current_body) is accepted
    if not accepted:
        assert "required_item_sprite_missing" in {row["code"] for row in report["problems"]}


def test_pre_visual_gameplay_compilation_keeps_geometry_unresolved():
    draft = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    for entity in draft["runtimeProgram"]["entities"]:
        if entity["kind"] != "item_body":
            entity["visual"] = {"role": entity["visualRole"], "assetMode": "runtime_geometry"}
            assert "geometry" not in entity["visual"]
    report = validate_runtime_wire(draft)
    assert report["ok"], report
