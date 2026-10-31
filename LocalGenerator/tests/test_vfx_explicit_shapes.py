"""Fresh independent geometry controls and immutable legacy presentation admission."""
from __future__ import annotations

import copy
import math
import pytest

import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.repair as vfx_repair
import infini_local.core.vfx.schema as vfx_schema
import infini_local.core.vfx.shapes as vfx_shapes
import infini_local.core.vfx.surface as vfx_surface
import infini_local.core.vfx.validation as vfx_validation
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.schema_validation import strict_schema_errors
from tests.vfx_material_fixtures import _data, _legacy


def shape_slot(data, kind="arc"):
    payload = {
        "kind": kind, "attachment": "world", "offsetForwardPx": 0, "offsetSidePx": 0,
        "rotationFrame": "source", "rotationRadians": 0, "rotationSpeedRadiansPerTick": 0,
        "colorStart": {"r": 17, "g": 93, "b": 241}, "colorEnd": {"r": 0, "g": 30, "b": 255},
        "opacityCurve": "linear", "opacityStart": .8, "opacityEnd": 0,
    }
    payload.update({
        "line": {"lengthPx": 48, "widthPx": .25},
        "arc": {"radiusStartPx": 4, "radiusEndPx": 32, "sweepRadians": math.tau, "widthPx": .5,
                "segments": 20, "tailOpacityStart": 1, "tailOpacityEnd": 1},
        "wave": {"lengthPx": 48, "amplitudePx": 6, "cycles": 1, "phaseRadians": 0,
                 "phaseSpeedRadiansPerTick": -.2, "widthPx": 2, "segments": 16},
        "sector": {"innerRadiusStartPx": 0, "innerRadiusEndPx": 8, "outerRadiusStartPx": 16, "outerRadiusEndPx": 32, "sweepRadians": math.pi, "segments": 16},
        "orbit": {"count": 4, "radiusStartPx": 18, "radiusEndPx": 18, "moteSizePx": 3, "moteOrientation": "world", "moteRotationRadians": 0},
    }[kind])
    return {"id": "explicit_shape", "entityId": data["runtimeProgram"]["itemEntityId"],
            "event": "on_use", "rendererKind": "shape", "anchor": "self", "blend": "additive",
            "layer": "AfterProjectiles", "startTick": 0, "repeatEvery": 0, "duration": 20, "shape": payload}


def authored_shape(data, kind="arc"):
    return {"schema": vfx_contract.VFX_DIRECTOR_SCHEMA, "slots": [shape_slot(data, kind)]}


@pytest.mark.parametrize("kind", ["line", "arc", "wave", "orbit", "sector"])
def test_shape_exact_independent_controls_survive_author_compile_and_wire(kind):
    data = _data()
    raw = authored_shape(data, kind)
    before = copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "shape-test")
    slot = data["vfxManifest"]["slots"][0]
    assert {k: v for k, v in slot.items() if k != "slotSeed"} == raw["slots"][0]
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert raw == before
    assert not vfx_validation.vfx_png_dependencies(data, raw)["dependencies"]


@pytest.mark.parametrize("field", ["alpha", "scale", "density", "spread", "particleSystemId", "color"])
def test_shape_rejects_ambiguous_common_controls(field):
    data = _data()
    raw = authored_shape(data)
    raw["slots"][0][field] = {"particleSystemId": "none", "color": {"r": 0, "g": 0, "b": 0}}.get(field, 1)
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


@pytest.mark.parametrize("kind", ["line", "arc", "wave", "orbit", "sector"])
def test_shape_no_missing_control_inference_and_no_foreign_payload(kind):
    data = _data()
    raw = authored_shape(data, kind)
    for field in list(raw["slots"][0]["shape"]):
        broken = copy.deepcopy(raw)
        del broken["slots"][0]["shape"][field]
        assert not vfx_validation.validate_vfx_director_output(broken, data)["ok"], field
    broken = copy.deepcopy(raw)
    broken["slots"][0]["shape"]["count" if kind != "orbit" else "widthPx"] = 3
    assert not vfx_validation.validate_vfx_director_output(broken, data)["ok"]


def test_legacy_presets_retained_only_in_saved_wire_not_fresh_output():
    data = _data()
    old = _legacy(data)
    for renderer in vfx_shapes.LEGACY_SHAPE_RENDERERS:
        candidate = copy.deepcopy(old)
        candidate["slots"][0]["rendererKind"] = renderer
        assert not vfx_validation.validate_vfx_director_output(candidate, data)["ok"]
        data["vfxManifest"] = vfx_projection._compile_manifest(data, candidate, "unchanged-legacy")
        saved = copy.deepcopy(data["vfxManifest"])
        assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
        assert data["vfxManifest"] == saved
    surface = vfx_surface.vfx_director_surface(data)
    assert not vfx_shapes.LEGACY_SHAPE_RENDERERS.intersection(surface["rendererKind"])
    assert not vfx_shapes.LEGACY_SHAPE_RENDERERS.intersection(surface["rendererSemantics"])


def test_shape_cadence_and_kind_fields_in_repair_schema():
    data = _data()
    raw = authored_shape(data)
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": raw["slots"], "note": "exact geometric leaf"}
    assert not strict_schema_errors(patch, vfx_repair.vfx_repair_schema(data))
    raw["slots"][0]["repeatEvery"] = 2
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


def test_shape_leaf_repair_cannot_change_geometry_composition_or_valid_width():
    data = _data()
    raw = authored_shape(data)
    raw["slots"][0]["shape"]["opacityEnd"] = 2
    before = copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["shape"].update(opacityEnd=0, widthPx=10, radiusEndPx=100)
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "repair opacity only"}
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert vfx_validation.validate_vfx_director_output(repaired, data)["ok"]
    expected = copy.deepcopy(raw)
    expected["slots"][0]["shape"]["opacityEnd"] = 0
    assert repaired == expected
    assert raw == before
    assert any(row["path"].endswith("shape.widthPx") for row in audit["ignoredChanges"])
    assert any(row["path"].endswith("shape.radiusEndPx") for row in audit["ignoredChanges"])


def test_shape_does_not_accept_legacy_phase_clock_on_persisted_wire():
    data = _data()
    data["vfxManifest"] = vfx_projection._compile_manifest(data, authored_shape(data), "no-old-clock")
    data["vfxManifest"]["slots"][0]["phaseOffset"] = 0
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]


def test_director_single_call_keeps_exact_shape_without_image_stage_or_repair():
    data = _data()
    raw = authored_shape(data, "wave")
    calls = []
    def respond(*args, **kwargs):
        calls.append((args, kwargs))
        return copy.deepcopy(raw)
    before_runtime = copy.deepcopy(data["runtimeProgram"])
    final = vfx_stage.attach_vfx_manifest(data, "shape-one-shot", llm_director=respond)
    assert len(calls) == 1
    assert final["runtimeProgram"] == before_runtime
    assert final["vfxManifest"]["slots"][0]["shape"] == raw["slots"][0]["shape"]
    assert final["debug"]["llmStageAccounting"]["vfxDirectorCalls"] == 1
    assert final["debug"]["llmStageAccounting"].get("vfxRepairCalls", 0) == 0


@pytest.mark.parametrize("kind", ["line", "arc", "wave", "orbit", "sector"])
def test_saved_shape_without_new_choices_roundtrips_without_authoring_defaults(kind):
    data = _data()
    raw = authored_shape(data, kind)
    payload = raw["slots"][0]["shape"]
    payload.pop("opacityCurve")
    payload.pop("rotationFrame")
    payload.pop("moteOrientation", None)
    payload.pop("moteRotationRadians", None)
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "saved-explicit-shape")
    before = copy.deepcopy(data["vfxManifest"])
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"] == before


@pytest.mark.parametrize("curve", ["linear", "easeIn", "easeOut", "smoothStep"])
def test_shape_opacity_curve_preserved_independently_of_color_and_radius(curve):
    data = _data()
    raw = authored_shape(data)
    raw["slots"][0]["shape"]["opacityCurve"] = curve
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    raw["slots"][0]["shape"]["opacityCurve"] = "guessed"
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


@pytest.mark.parametrize("period", [1, 2, 3, 4, 5, 6])
def test_shape_can_express_legacy_fast_phase_and_orbit_rates(period):
    data = _data()
    for kind, field in (("wave", "phaseSpeedRadiansPerTick"), ("orbit", "rotationSpeedRadiansPerTick")):
        raw = authored_shape(data, kind)
        raw["slots"][0]["shape"][field] = -math.tau / period
        assert vfx_validation.validate_vfx_director_output(raw, data)["ok"]


@pytest.mark.parametrize("orientation", ["world", "orbit"])
def test_orbit_mote_orientation_is_an_independent_authored_choice(orientation):
    data = _data()
    raw = authored_shape(data, "orbit")
    raw["slots"][0]["shape"].update(moteOrientation=orientation, moteRotationRadians=.75,
                                    rotationSpeedRadiansPerTick=.2)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw


@pytest.mark.parametrize("field,value", [("opacityCurve", "guessed"), ("rotationFrame", "automatic"), ("moteOrientation", "automatic"),
                                         ("moteRotationRadians", 7), ("rotationSpeedRadiansPerTick", 7)])
def test_saved_shape_present_invalid_new_choices_do_not_use_legacy_defaults(field, value):
    data = _data()
    raw = authored_shape(data, "orbit")
    raw["slots"][0]["shape"][field] = value
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "invalid-new-choice")
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("duration", [1, 2])
def test_short_shape_cycle_is_individual_lifetime_without_overlapping_instances(duration):
    data = _data()
    raw = authored_shape(data)
    raw["slots"][0].update(duration=duration)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "short-shape")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("frame", ["world", "source"])
def test_shape_rotation_frame_is_independent_of_attachment_and_offsets(frame):
    data = _data()
    raw = authored_shape(data, "orbit")
    raw["slots"][0]["shape"].update(rotationFrame=frame, attachment="source", offsetForwardPx=13,
                                    rotationSpeedRadiansPerTick=.25, moteOrientation="world")
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw


def test_duration_repair_schema_preserves_renderer_specific_bound():
    from tests.vfx_material_fixtures import _sprite
    data = _data()
    canonical = vfx_schema.vfx_director_schema(data)["properties"]["slots"]["items"]
    for raw, short_allowed in ((authored_shape(data), True), (_sprite(data), False)):
        source = copy.deepcopy(raw["slots"][0])
        source["duration"] = 0
        scoped = vfx_repair._vfx_repair_row_schema(canonical, source, ["duration"], [])
        repaired = {**source, "duration": 2}
        assert (not strict_schema_errors(repaired, scoped)) == short_allowed
        raw["slots"][0] = repaired
        assert vfx_validation.validate_vfx_director_output(raw, data)["ok"] == short_allowed
        repaired["duration"] = 3
        assert not strict_schema_errors(repaired, scoped)


@pytest.mark.parametrize("endpoint", ["Start", "End"])
def test_sector_inner_outer_order_enforced_in_fresh_and_persisted_wire(endpoint):
    data = _data()
    raw = authored_shape(data, "sector")
    raw["slots"][0]["shape"][f"innerRadius{endpoint}Px"] = 80
    result = vfx_validation.validate_vfx_director_output(raw, data)
    assert not result["ok"]
    assert any(e["path"].endswith(f"outerRadius{endpoint}Px") for e in result["errors"])
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "sector-order")
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("changes", [
    {"segments": 2}, {"segments": 65}, {"segments": 3.5},
    {"innerRadiusStartPx": None}, {"outerRadiusEndPx": 257},
    {"radiusStartPx": 5}, {"widthPx": 2}, {"tailOpacityStart": 1},
])
def test_sector_rejects_invalid_or_foreign_geometry(changes):
    data = _data()
    raw = authored_shape(data, "sector")
    raw["slots"][0]["shape"].update(changes)
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


@pytest.mark.parametrize("sweep", [-math.tau, 0, math.tau])
def test_sector_silent_and_full_shapes_remain_authored(sweep):
    data = _data()
    raw = authored_shape(data, "sector")
    raw["slots"][0]["shape"].update(innerRadiusStartPx=0, outerRadiusStartPx=0, innerRadiusEndPx=16, outerRadiusEndPx=16, sweepRadians=sweep, segments=3)
    result = vfx_validation.validate_vfx_director_output(raw, data)
    assert result["ok"], result["errors"]
    assert result["normalized"] == raw


def test_sector_radius_order_repair_is_leaf_local():
    data = _data()
    raw = authored_shape(data, "sector")
    raw["slots"][0]["shape"].update(innerRadiusStartPx=20, outerRadiusStartPx=10)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["shape"].update(outerRadiusStartPx=24, innerRadiusStartPx=0, sweepRadians=math.tau)
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "radius order"}
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert vfx_validation.validate_vfx_director_output(repaired, data)["ok"]
    expected = copy.deepcopy(raw)
    expected["slots"][0]["shape"]["outerRadiusStartPx"] = 24
    assert repaired == expected
    assert any(row["path"].endswith("shape.innerRadiusStartPx") for row in audit["ignoredChanges"])
