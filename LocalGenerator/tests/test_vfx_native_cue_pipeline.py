"""Explicit native emission survives pipeline boundaries without artistic defaults."""
from __future__ import annotations

import copy
import pytest
from infini_local.core import vfx_manifest as vfx
from tests.vfx_material_fixtures import _data
from tests.test_vfx_native_cue_contract import dust


def cue(data, renderer="nativeDust"):
    return {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": [{
        "id": "native_cue", "entityId": data["runtimeProgram"]["itemEntityId"],
        "event": "on_use", "rendererKind": renderer, "anchor": "self",
        "startTick": 3, "repeatEvery": 0, "color": {"r": 10, "g": 40, "b": 80},
        **({"dust": dust()} if renderer == "nativeDust" else {"light": {"intensity": .75}}),
    }]}


@pytest.mark.parametrize("renderer", ["nativeDust", "nativeLight"])
def test_native_cue_identity_and_no_png_or_accompanying_renderer(renderer):
    data = _data()
    raw = cue(data, renderer)
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "native-cue")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    delivered = data["vfxManifest"]["slots"][0]
    assert {k: v for k, v in delivered.items() if k != "slotSeed"} == raw["slots"][0]
    assert vfx.vfx_png_dependencies(data, raw)["dependencies"] == []
    assert raw == before


def test_native_dust_repair_only_invalid_speed_bound():
    data = _data()
    raw = cue(data)
    raw["slots"][0]["dust"]["speedMaxPxPerTick"] = 1
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    fixed = copy.deepcopy(raw["slots"][0])
    fixed["dust"].update(speedMaxPxPerTick=3, nativeAlpha=0, noGravity=True, count=64)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [fixed], "note": "maximum speed only"}
    result = vfx._apply_vfx_repair_patch(data, raw, patch, scope)
    expected = copy.deepcopy(raw)
    expected["slots"][0]["dust"]["speedMaxPxPerTick"] = 3
    assert result == expected
    assert vfx.validate_vfx_director_output(result, data)["ok"]


def test_persisted_native_cue_accepts_exact_float32_boundary_rounding():
    import math
    import struct
    data = _data()
    raw = cue(data)
    raw["slots"][0]["dust"]["spreadRadians"] = math.tau
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "native-float-boundary")
    data["vfxManifest"]["slots"][0]["dust"]["spreadRadians"] = struct.unpack("f", struct.pack("f", math.tau))[0]
    report = vfx.validate_vfx_manifest_wire(data)
    assert report["ok"], report["errors"]
