"""Fresh impact artwork is an ordinary explicit asset/material composition."""
from __future__ import annotations

import copy
import infini_local.core.vfx.config as vfx_config
import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.surface as vfx_surface
import infini_local.core.vfx.validation as vfx_validation
from tests.generator.vfx_material_fixtures import _data, _sprite, _asset, _profile


def impact(data, asset_id="impact_a"):
    raw = _sprite(data)
    raw["assets"] = [_asset(asset_id)]
    slot = raw["slots"][0]
    slot.update(id=asset_id, duration=20, alpha=1)
    slot["element"].update(
        texture={"source": "asset", "assetId": asset_id, "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}, attachment="world", count=1,
        offsetForwardPx=0, offsetSidePx=0, speedMinPxPerTick=0, speedMaxPxPerTick=0,
        spreadRadians=0, inheritVelocity=0, drag=1, accelerationXPxPerTickSquared=0,
        accelerationYPxPerTickSquared=0, rotationRadians=0, rotationSpeedRadiansPerTick=0,
        widthPx=32, heightPx=32, widthProfile=_profile(1, 1, 1), heightProfile=_profile(1, 1, 1),
        opacityProfile=_profile(1, .5, 0),
    )
    return raw


def test_explicit_impact_preserves_art_request_and_independent_size_opacity():
    data = _data()
    raw = impact(data)
    original = copy.deepcopy(raw)
    result = vfx_validation.validate_vfx_director_output(raw, data)
    assert result["ok"], result["errors"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "explicit-impact")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    delivered = data["vfxManifest"]["slots"][0]
    assert delivered["element"] == raw["slots"][0]["element"]
    assert len(data["vfxManifest"]["assets"]) == 1
    assert vfx_validation.vfx_png_dependencies(data, raw, require_used=True)["dependencies"][0]["role"] == "vfx:impact_a"
    assert raw == original


def test_twelve_slot_ceiling_can_keep_twelve_distinct_authored_textures(monkeypatch):
    # Explicitly exercise the hard supported slot ceiling, not configured default.
    monkeypatch.setattr(vfx_config, "VFX_LLM_DIRECTOR_MAX_SLOTS", 12)
    data = _data()
    raw = {"schema": vfx_contract.VFX_DIRECTOR_SCHEMA, "slots": [], "assets": []}
    for index in range(12):
        single = impact(data, f"art_{index}")
        raw["slots"].extend(single["slots"])
        raw["assets"].extend(single["assets"])
    result = vfx_validation.validate_vfx_director_output(raw, data)
    assert result["ok"], result["errors"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "maximum-distinct-art")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert len(vfx_validation.vfx_png_dependencies(data, raw, require_used=True)["dependencies"]) == 12


def test_default_slot_budget_admits_sparse_and_twelve_but_not_thirteen(monkeypatch):
    import importlib

    try:
        with monkeypatch.context() as context:
            context.delenv("INFINI_VFX_LLM_DIRECTOR_MAX_SLOTS", raising=False)
            importlib.reload(vfx_config)
            data = _data()
            assert vfx_surface.vfx_director_surface(data)["maxSlots"] == 12
            for count in (0, 3, 12, 13):
                raw = {"schema": vfx_contract.VFX_DIRECTOR_SCHEMA, "slots": [], "assets": []}
                for index in range(count):
                    single = impact(data, f"default_art_{index}")
                    raw["slots"].extend(single["slots"])
                    raw["assets"].extend(single["assets"])
                result = vfx_validation.validate_vfx_director_output(raw, data)
                assert result["ok"] == (count <= 12), result["errors"]
    finally:
        importlib.reload(vfx_config)
