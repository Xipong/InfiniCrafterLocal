"""Native texture selection reuses material controls without requesting artwork."""
import pytest
from infini_local.core import vfx_manifest as vfx
from infini_local.core.vfx_material_contract import LIBRARY_PARTICLE_TEXTURES
from tests.vfx_material_fixtures import _data, _sprite, _path, _history
from tests.vfx_image_fixtures import offline_backend
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan


@pytest.mark.parametrize("factory,payload", [(_sprite,"element"), (_path,"path"), (_history,"trail")])
@pytest.mark.parametrize("texture_id", list(LIBRARY_PARTICLE_TEXTURES))
def test_native_material_source_has_no_generated_png_dependency(factory, payload, texture_id):
    data = _data()
    before = build_visual_asset_plan(data)
    raw = factory(data)
    raw["slots"][0][payload]["texture"] = {"source": "library", "assetId": texture_id, "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "native_material")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    dependencies = vfx.vfx_png_dependencies(data)
    assert dependencies == {"dependencies": [], "errors": []}
    assert build_visual_asset_plan(data) == before
    assert data["vfxManifest"].get("assets", []) == []


@pytest.mark.parametrize("source,texture_id", [("library", "../star"), ("library", ""), ("library", "fake"), ("asset", "shineFlare")])
def test_library_id_is_not_a_fallback_for_invalid_or_missing_generated_asset(source, texture_id):
    data = _data()
    raw = _sprite(data)
    raw["slots"][0]["element"]["texture"] = {"source": source, "assetId": texture_id, "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]


def test_native_material_requests_zero_vfx_image_calls_and_no_png_delivery_error(offline_backend):
    from tests.vfx_image_fixtures import _data as image_data
    from infini_local.pipelines import visual_sprite_generation, visual_delivery_gate
    calls, _ = offline_backend
    data = image_data([])
    raw = _sprite(data)
    raw["slots"][0]["element"]["texture"] = {"source": "library", "assetId": "shineFlare", "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "native_material_images")
    result = visual_sprite_generation.maybe_generate_visual_assets(data)
    assert all("_vfx_" not in row["id"] for row in calls)
    assert not any(row["role"].startswith("vfx:") for row in build_visual_asset_plan(result))
    report = visual_delivery_gate.visual_delivery_report(result, check_backend_config=False)
    assert not any(row["code"] in {"required_vfx_texture_not_ready", "required_vfx_sprite_missing_or_invalid"} for row in report["problems"])
