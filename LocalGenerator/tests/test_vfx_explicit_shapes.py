"""Fresh independent geometry controls and immutable legacy presentation admission."""
from __future__ import annotations

import copy
import math
import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.schema_validation import strict_schema_errors
from tests.vfx_material_fixtures import _data, _legacy


def shape_slot(data, kind="arc"):
    payload = {
        "kind": kind, "attachment": "world", "offsetForwardPx": 0, "offsetSidePx": 0,
        "rotationRadians": 0, "rotationSpeedRadiansPerTick": 0,
        "colorStart": {"r": 17, "g": 93, "b": 241}, "colorEnd": {"r": 0, "g": 30, "b": 255},
        "opacityStart": .8, "opacityEnd": 0,
    }
    payload.update({
        "line": {"lengthPx": 48, "widthPx": .25},
        "arc": {"radiusStartPx": 4, "radiusEndPx": 32, "sweepRadians": math.tau, "widthPx": .5,
                "segments": 20, "tailOpacityStart": 1, "tailOpacityEnd": 1},
        "wave": {"lengthPx": 48, "amplitudePx": 6, "cycles": 1, "phaseRadians": 0,
                 "phaseSpeedRadiansPerTick": -.2, "widthPx": 2, "segments": 16},
        "orbit": {"count": 4, "radiusStartPx": 18, "radiusEndPx": 18, "moteSizePx": 3},
    }[kind])
    return {"id": "explicit_shape", "entityId": data["runtimeProgram"]["itemEntityId"],
            "event": "on_use", "rendererKind": "shape", "anchor": "self", "blend": "additive",
            "layer": "AfterProjectiles", "startTick": 0, "repeatEvery": 0, "duration": 20, "shape": payload}


def authored_shape(data, kind="arc"):
    return {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": [shape_slot(data, kind)]}


@pytest.mark.parametrize("kind", ["line", "arc", "wave", "orbit"])
def test_shape_exact_independent_controls_survive_author_compile_and_wire(kind):
    data = _data()
    raw = authored_shape(data, kind)
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "shape-test")
    slot = data["vfxManifest"]["slots"][0]
    assert {k: v for k, v in slot.items() if k != "slotSeed"} == raw["slots"][0]
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert raw == before
    assert not vfx.vfx_png_dependencies(data, raw)["dependencies"]


@pytest.mark.parametrize("field", ["alpha", "scale", "density", "spread", "particleSystemId", "color"])
def test_shape_rejects_ambiguous_common_controls(field):
    data = _data()
    raw = authored_shape(data)
    raw["slots"][0][field] = {"particleSystemId": "none", "color": {"r": 0, "g": 0, "b": 0}}.get(field, 1)
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]


@pytest.mark.parametrize("kind", ["line", "arc", "wave", "orbit"])
def test_shape_no_missing_control_inference_and_no_foreign_payload(kind):
    data = _data()
    raw = authored_shape(data, kind)
    for field in list(raw["slots"][0]["shape"]):
        broken = copy.deepcopy(raw)
        del broken["slots"][0]["shape"][field]
        assert not vfx.validate_vfx_director_output(broken, data)["ok"], field
    broken = copy.deepcopy(raw)
    broken["slots"][0]["shape"]["count" if kind != "orbit" else "widthPx"] = 3
    assert not vfx.validate_vfx_director_output(broken, data)["ok"]


def test_legacy_presets_retained_only_in_saved_wire_not_fresh_output():
    data = _data()
    old = _legacy(data)
    for renderer in vfx.LEGACY_SHAPE_RENDERERS:
        candidate = copy.deepcopy(old)
        candidate["slots"][0]["rendererKind"] = renderer
        assert not vfx.validate_vfx_director_output(candidate, data)["ok"]
        data["vfxManifest"] = vfx._compile_manifest(data, candidate, "unchanged-legacy")
        saved = copy.deepcopy(data["vfxManifest"])
        assert vfx.validate_vfx_manifest_wire(data)["ok"]
        assert data["vfxManifest"] == saved
    surface = vfx.vfx_director_surface(data)
    assert not vfx.LEGACY_SHAPE_RENDERERS.intersection(surface["rendererKind"])
    assert not vfx.LEGACY_SHAPE_RENDERERS.intersection(surface["rendererSemantics"])


def test_shape_cadence_and_kind_fields_in_repair_schema():
    data = _data()
    raw = authored_shape(data)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": raw["slots"], "note": "exact geometric leaf"}
    assert not strict_schema_errors(patch, vfx.vfx_repair_schema(data))
    raw["slots"][0]["repeatEvery"] = 2
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]


def test_shape_leaf_repair_cannot_change_geometry_composition_or_valid_width():
    data = _data()
    raw = authored_shape(data)
    raw["slots"][0]["shape"]["opacityEnd"] = 2
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["shape"].update(opacityEnd=0, widthPx=10, radiusEndPx=100)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "repair opacity only"}
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    expected = copy.deepcopy(raw)
    expected["slots"][0]["shape"]["opacityEnd"] = 0
    assert repaired == expected
    assert raw == before
    assert any(row["path"].endswith("shape.widthPx") for row in audit["ignoredChanges"])
    assert any(row["path"].endswith("shape.radiusEndPx") for row in audit["ignoredChanges"])


def test_shape_does_not_accept_legacy_phase_clock_on_persisted_wire():
    data = _data()
    data["vfxManifest"] = vfx._compile_manifest(data, authored_shape(data), "no-old-clock")
    data["vfxManifest"]["slots"][0]["phaseOffset"] = 0
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


def test_director_single_call_keeps_exact_shape_without_image_stage_or_repair():
    data = _data()
    raw = authored_shape(data, "wave")
    calls = []
    def respond(*args, **kwargs):
        calls.append((args, kwargs))
        return copy.deepcopy(raw)
    before_runtime = copy.deepcopy(data["runtimeProgram"])
    final = vfx.attach_vfx_manifest(data, "shape-one-shot", llm_director=respond)
    assert len(calls) == 1
    assert final["runtimeProgram"] == before_runtime
    assert final["vfxManifest"]["slots"][0]["shape"] == raw["slots"][0]["shape"]
    assert final["debug"]["llmStageAccounting"]["vfxDirectorCalls"] == 1
    assert final["debug"]["llmStageAccounting"].get("vfxRepairCalls", 0) == 0
