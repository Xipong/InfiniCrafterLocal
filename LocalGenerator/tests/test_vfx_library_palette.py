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
