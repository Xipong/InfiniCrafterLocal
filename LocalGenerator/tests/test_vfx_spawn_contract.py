"""Shared spawn regions survive all three owners without defaulting or broad Repair."""
import copy
import math

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx_spawn_contract import spawn_schema
from tests.vfx_material_fixtures import _data, _native, _sprite
from tests.test_vfx_material_admission_contracts import _library_particle

REGIONS = [
    {"shape": "point"},
    {"shape": "line", "lengthPx": 512, "rotationRadians": -math.tau, "frame": "world"},
    {"shape": "rectangle", "widthPx": 90, "heightPx": 0, "rotationRadians": .5, "frame": "source"},
    {"shape": "annulus", "innerRadiusPx": 0, "outerRadiusPx": 256},
    {"shape": "annulus", "innerRadiusPx": 16, "outerRadiusPx": 16},
]
OWNERS = [(_sprite, "element"), (_library_particle, "particle"), (_native, "dust")]


@pytest.mark.parametrize("factory,key", OWNERS)
@pytest.mark.parametrize("region", REGIONS)
def test_regions_preserved_through_fresh_and_saved_pipeline(factory, key, region):
    data = _data()
    raw = factory(data)
    raw["slots"][0][key]["spawn"] = copy.deepcopy(region)
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == before
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "spawn-regions")
    report = vfx.validate_vfx_manifest_wire(data)
    assert report["ok"], report["errors"]
    assert data["vfxManifest"]["slots"][0][key]["spawn"] == region
    assert raw == before


@pytest.mark.parametrize("factory,key", OWNERS)
def test_saved_missing_spawn_remains_missing_but_fresh_requires_choice(factory, key):
    data = _data()
    raw = factory(data)
    raw["slots"][0][key].pop("spawn")
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "saved-point")
    before = copy.deepcopy(data["vfxManifest"])
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"] == before


@pytest.mark.parametrize("region", REGIONS)
def test_every_region_requires_its_choices_and_rejects_foreign_controls(region):
    for key in region:
        missing = {name: value for name, value in region.items() if name != key}
        assert strict_schema_errors(missing, spawn_schema()), key
    extra = {**region, "radiusPx": 12}
    assert strict_schema_errors(extra, spawn_schema())
    if region["shape"] == "point":
        assert strict_schema_errors({**region, "frame": "source"}, spawn_schema())


@pytest.mark.parametrize("factory,key", OWNERS)
@pytest.mark.parametrize("region", [None, {"shape": "automatic"},
    {"shape": "line", "lengthPx": -1, "rotationRadians": 0, "frame": "world"},
    {"shape": "annulus", "innerRadiusPx": 30, "outerRadiusPx": 20}])
def test_invalid_spawn_never_uses_historical_point_fallback(factory, key, region):
    data = _data()
    raw = factory(data)
    raw["slots"][0][key]["spawn"] = region
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "invalid-region")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("factory,key", OWNERS)
def test_annulus_repair_only_outer_radius_preserves_region_and_velocity(factory, key):
    data = _data()
    raw = factory(data)
    raw["slots"][0][key]["spawn"] = {"shape": "annulus", "innerRadiusPx": 24, "outerRadiusPx": 10}
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert all(error["path"].endswith("spawn.outerRadiusPx") for error in report["errors"]), report["errors"]
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    fixed = copy.deepcopy(raw["slots"][0])
    fixed[key]["spawn"].update(innerRadiusPx=0, outerRadiusPx=40)
    fixed[key]["speedMaxPxPerTick"] = 24
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [fixed], "note": "outer radius only"}
    result = vfx._apply_vfx_repair_patch(data, raw, patch, scope)
    expected = copy.deepcopy(raw)
    expected["slots"][0][key]["spawn"]["outerRadiusPx"] = 40
    assert result == expected
    assert vfx.validate_vfx_director_output(result, data)["ok"]
