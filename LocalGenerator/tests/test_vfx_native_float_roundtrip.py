"""Native float serialization may round an admitted endpoint beyond its double spelling."""
from __future__ import annotations

import copy
import math
import struct

import pytest

import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.repair as vfx_repair
import infini_local.core.vfx.validation as vfx_validation
from tests.test_vfx_material_admission_contracts import _library_particle
from tests.test_vfx_sound_selection import _sound
from tests.vfx_material_fixtures import _data


def _single(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _particle():
    data = _data()
    raw = _library_particle(data)
    raw["slots"][0]["particle"]["spreadRadians"] = math.tau
    assert vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "float-endpoint")
    return data, raw


def test_persisted_native_shortest_float_endpoint_remains_admitted_without_mutation():
    data, _ = _particle()
    # The exact System.Text.Json Single spelling observed in the saved item.
    data["vfxManifest"]["slots"][0]["particle"]["spreadRadians"] = 6.2831855
    before = copy.deepcopy(data)
    assert _single(6.2831855) == _single(math.tau)
    report = vfx_validation.validate_vfx_manifest_wire(data)
    assert report["ok"], report["errors"]
    assert data == before


@pytest.mark.parametrize("field,value", [("spreadRadians", 6.2831855), ("rotationRadians", -6.2831855)])
def test_wire_accepts_native_float_endpoint_but_fresh_director_and_repair_remain_strict(field, value):
    data, raw = _particle()
    raw["slots"][0]["particle"][field] = value
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "native-endpoint")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    from infini_local.core.schema_validation import strict_schema_errors
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": raw["slots"], "note": "strict authored range"}
    assert strict_schema_errors(patch, vfx_repair.vfx_repair_schema(data))


@pytest.mark.parametrize("value", [6.283186, -0.000001, True, float("inf"), float("nan"), 10 ** 400])
def test_persisted_gate_still_rejects_next_float_outside_range_and_malformed_numbers(value):
    data, _ = _particle()
    data["vfxManifest"]["slots"][0]["particle"]["spreadRadians"] = value
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("saved_pitch,saved_variance", [
    pytest.param(0.70000005, 0.59999996, id="native-shortest-decimals"),
    pytest.param(_single(0.70000003), _single(0.59999994), id="exact-single-values"),
])
def test_persisted_sound_interval_uses_native_single_operands_and_intermediates_without_mutation(
    sign, saved_pitch, saved_variance,
):
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["sound"] = {"volume": 1, "pitch": sign * 0.70000003, "pitchVariance": 0.59999994}
    authored = copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "single-sound-interval")
    assert data["vfxManifest"]["slots"][0]["sound"] == authored["slots"][0]["sound"]
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    # Native Single storage and its shortest saved spellings preserve the same
    # interval. Merely rounding the operands but summing in double is not enough.
    assert _single(saved_pitch) == _single(0.70000003)
    assert _single(saved_variance) == _single(0.59999994)
    assert abs(_single(saved_pitch)) + _single(saved_variance) / 2 > 1
    assert _single(abs(_single(saved_pitch)) + _single(_single(saved_variance) / 2)) == 1
    data["vfxManifest"]["slots"][0]["sound"].update(pitch=sign * saved_pitch, pitchVariance=saved_variance)
    before = copy.deepcopy(data)
    report = vfx_validation.validate_vfx_manifest_wire(data)
    assert report["ok"], report["errors"]
    assert data == before and raw == authored


@pytest.mark.parametrize("sign", [1, -1])
def test_native_sound_interval_rounding_does_not_relax_fresh_director_or_frozen_repair(sign):
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["sound"] = {"volume": 1, "pitch": sign * 0.70000005, "pitchVariance": 0.6}
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert {e["path"] for e in report["errors"]} == {"$.slots[0].sound.pitchVariance"}
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "explicit_sound", "paths": ["sound.pitchVariance"]}]
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["sound"]["pitchVariance"] = 0.59999996
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "native rounding is not fresh permission"}
    merged, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert audit["ok"] and merged["slots"][0] == candidate
    report = vfx_validation.validate_vfx_director_output(merged, data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.slots[0].sound.pitchVariance"}


@pytest.mark.parametrize("sign", [1, -1])
def test_persisted_sound_interval_rejects_actually_outside_next_single(sign):
    data = _data()
    raw = _sound(data)
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "next-single-sound-interval")
    bits = struct.unpack("<I", struct.pack("<f", 0.70000005))[0]
    next_single = struct.unpack("<f", struct.pack("<I", bits + 1))[0]
    assert _single(0.7000001) == next_single
    assert _single(next_single + _single(_single(0.59999996) / 2)) > 1
    data["vfxManifest"]["slots"][0]["sound"] = {"volume": 1, "pitch": sign * 0.7000001, "pitchVariance": 0.59999996}
    before = copy.deepcopy(data)
    report = vfx_validation.validate_vfx_manifest_wire(data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.vfxManifest.slots[0].sound.pitchVariance"}
    assert data == before


@pytest.mark.parametrize("field,value", [
    ("pitch", True), ("pitch", float("inf")), ("pitch", float("nan")),
    ("pitchVariance", False), ("pitchVariance", float("inf")), ("pitchVariance", float("nan")),
    ("pitchVariance", -0.000001),
])
def test_persisted_sound_interval_still_denies_nonfinite_boolean_and_inverted_controls(field, value):
    data = _data()
    raw = _sound(data)
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "malformed-single-sound")
    data["vfxManifest"]["slots"][0]["sound"][field] = value
    before = copy.deepcopy(data)
    report = vfx_validation.validate_vfx_manifest_wire(data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.vfxManifest.slots[0].sound." + field}
    assert data == before
