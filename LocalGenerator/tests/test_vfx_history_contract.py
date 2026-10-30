"""History authoring distinguishes actual positions, poses, sampling and opacity."""
import copy

import pytest

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx_history_contract import history_schema, history_slot_clauses


def trail(draw="stroke"):
    value = {"draw": draw, "source": "center", "historyTicks": 20, "sampleStepTicks": 3,
             "firstSampleAgeTicks": 2, "color": {"r": 31, "g": 142, "b": 255},
             "opacityProfile": {"start": 0.8, "middle": 0.6, "end": 0.1, "curve": "linear"}}
    if draw == "stroke":
        value["widthPx"] = 2.5
    else:
        value.update(texture={"source": "entity", "assetId": ""}, scale=1.2, pose="sampled")
    return value


def test_independent_history_choices_admit_literal_values():
    for draw in ("stroke", "sprites"):
        value = trail(draw)
        before = copy.deepcopy(value)
        assert not strict_schema_errors(value, history_schema())
        assert value == before


@pytest.mark.parametrize("field", ["source", "historyTicks", "sampleStepTicks", "firstSampleAgeTicks", "color", "opacityProfile", "widthPx"])
def test_missing_stroke_choice_is_not_silently_authored(field):
    value = trail()
    value.pop(field)
    assert strict_schema_errors(value, history_schema())


@pytest.mark.parametrize("change", [
    {"historyTicks": 33}, {"sampleStepTicks": 0}, {"firstSampleAgeTicks": -1},
    {"widthPx": -0.01}, {"widthPx": float("nan")}, {"pose": "current"},
    {"source": "guessed_sprite_nose"}, {"color": {"r": 256, "g": 0, "b": 0}},
])
def test_invalid_or_foreign_fields_fail(change):
    value = {**trail(), **change}
    assert strict_schema_errors(value, history_schema())


def test_zero_opacity_width_scale_remain_literal_not_defaults():
    for draw, field in (("stroke", "widthPx"), ("sprites", "scale")):
        value = trail(draw)
        value[field] = 0
        value["opacityProfile"].update(start=0, middle=0, end=0)
        assert not strict_schema_errors(value, history_schema())
        assert value[field] == 0
        assert value["opacityProfile"]["middle"] == 0


def test_live_history_forbids_item_and_instant_event_and_orphan_controls():
    schema = {"type": "object", "allOf": history_slot_clauses(["item"], ["historyTrail", "shape"], ["periodic", "on_hit"])}
    base = {"rendererKind": "historyTrail", "entityId": "projectile", "event": "periodic",
            "trail": trail(), "blend": "alpha", "layer": "AfterProjectiles", "anchor": "self"}
    assert not strict_schema_errors(base, schema)
    for change in ({"entityId": "item"}, {"event": "on_hit"}, {"duration": 30},
                   {"repeatEvery": 2}, {"startTick": 0}, {"anchor": "tip"}, {"rendererKind": "shape"}):
        assert strict_schema_errors({**base, **change}, schema)


def test_sparse_or_empty_requested_history_is_not_rewritten():
    value = trail()
    value.update(historyTicks=2, firstSampleAgeTicks=31, sampleStepTicks=32)
    assert not strict_schema_errors(value, history_schema())
    assert (value["historyTicks"], value["firstSampleAgeTicks"], value["sampleStepTicks"]) == (2, 31, 32)


def history_case(draw="stroke"):
    from infini_local.core import vfx_manifest as vfx
    from test_low_level_three_stage_pipeline import _accepted_visual_data
    data = _accepted_visual_data("door_on_chain")
    pair = next(p for p in vfx.vfx_director_surface(data)["runtimePairs"]
                if p["entityId"] != data["runtimeProgram"]["itemEntityId"] and p["event"] == "periodic")
    raw = {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": [{
        "id": "authored_history", "entityId": pair["entityId"], "event": pair["event"],
        "rendererKind": "historyTrail", "anchor": "self", "blend": "alpha", "layer": "AfterProjectiles",
        "trail": trail(draw),
    }]}
    return data, raw


@pytest.mark.parametrize("draw", ["stroke", "sprites"])
def test_actual_director_compile_wire_preserves_complete_history_design(draw):
    from infini_local.core import vfx_manifest as vfx
    data, raw = history_case(draw)
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "history-contract-test")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"]["slots"][0]["trail"] == raw["slots"][0]["trail"]
    assert raw == before


def test_history_texture_requires_exact_bound_producer():
    from infini_local.core import vfx_manifest as vfx
    data, raw = history_case("sprites")
    entity_id = raw["slots"][0]["entityId"]
    entity = next(e for e in data["runtimeProgram"]["entities"] if e["id"] == entity_id)
    entity["visual"]["assetMode"] = "no_asset"
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    raw["slots"][0]["trail"]["texture"] = {"source": "asset", "assetId": "missing"}
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]


def test_history_leaf_repair_keeps_pose_sampling_and_width_frozen():
    from infini_local.core import vfx_manifest as vfx
    data, raw = history_case("sprites")
    raw["slots"][0]["trail"]["opacityProfile"]["middle"] = 2
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["trail"]["opacityProfile"]["middle"] = 0.3
    candidate["trail"].update(pose="current", sampleStepTicks=1, scale=3)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "repair middle opacity only"}
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    expected = copy.deepcopy(raw)
    expected["slots"][0]["trail"]["opacityProfile"]["middle"] = 0.3
    assert repaired == expected
    assert any(row["path"].endswith("trail.pose") for row in audit["ignoredChanges"])
