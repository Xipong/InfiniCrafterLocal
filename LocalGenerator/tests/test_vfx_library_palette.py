"""Exact existing texture selection survives both generation and saved wire."""
import pytest
from infini_local.core import vfx_manifest as vfx
from infini_local.core.vfx_material_contract import LIBRARY_PARTICLE_TEXTURES
from tests.test_vfx_material_admission_contracts import _library_particle
from tests.vfx_material_fixtures import _data


@pytest.mark.parametrize("texture", list(LIBRARY_PARTICLE_TEXTURES))
@pytest.mark.parametrize("blend", ["alpha", "additive"])
def test_palette_selection_is_explicit_and_preserved(texture, blend):
    data = _data()
    raw = _library_particle(data)
    raw["slots"][0]["particle"]["textureId"] = texture
    raw["slots"][0]["blend"] = blend
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    compiled = vfx._compile_manifest(data, raw, "palette")
    assert compiled["slots"][0]["particle"]["textureId"] == texture
    assert compiled["slots"][0]["blend"] == blend
    data["vfxManifest"] = compiled
    assert vfx.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("texture", ["softGlow", "../Star", "flame", "Luminance/Assets/GreyscaleTextures/ShineFlare"])
def test_palette_rejects_unregistered_identity_without_replacing_it(texture):
    data = _data()
    raw = _library_particle(data)
    raw["slots"][0]["particle"]["textureId"] = texture
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    assert raw["slots"][0]["particle"]["textureId"] == texture


@pytest.mark.parametrize("sampling", ["point", "linear"])
def test_library_sampling_survives_snapshot_wire(sampling):
    data = _data()
    raw = _library_particle(data)
    raw["slots"][0]["particle"]["sampling"] = sampling
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "sampling")
    assert data["vfxManifest"]["slots"][0]["particle"]["sampling"] == sampling
    assert vfx.validate_vfx_manifest_wire(data)["ok"]


def test_saved_sampling_omission_is_point_compatibility_not_fresh_fallback():
    data = _data()
    raw = _library_particle(data)
    del raw["slots"][0]["particle"]["sampling"]
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "saved_sampling")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert "sampling" not in data["vfxManifest"]["slots"][0]["particle"]


@pytest.mark.parametrize("sampling", [None, "auto", "nearest", 0])
def test_invalid_sampling_not_normalized_to_point(sampling):
    data = _data()
    raw = _library_particle(data)
    raw["slots"][0]["particle"]["sampling"] = sampling
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "invalid_sampling")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]
