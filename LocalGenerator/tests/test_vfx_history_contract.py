"""History authoring distinguishes actual positions, poses, sampling and opacity."""

from infini_local.core.vfx import contract as vfx_contract
from infini_local.core.vfx import projection as vfx_projection
from infini_local.core.vfx import surface as vfx_surface
from infini_local.core.vfx import validation as vfx_validation

import copy

import pytest

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.history import history_schema, history_slot_clauses


def trail(draw="stroke"):
    value = {"draw": draw, "source": "center", "historyTicks": 20, "sampleStepTicks": 3,
             "firstSampleAgeTicks": 2, "color": {"r": 31, "g": 142, "b": 255},
             "opacityProfile": {"start": 0.8, "middle": 0.6, "end": 0.1, "curve": "linear"}}
    if draw == "stroke":
        value["widthPx"] = 2.5
    else:
        value.update(texture={"source": "entity", "assetId": "", "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}, scale=1.2, pose="sampled")
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


def test_live_projectile_history_forbids_item_without_exact_use_and_orphan_controls():
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
    from test_low_level_three_stage_pipeline import _accepted_visual_data
    data = _accepted_visual_data("door_on_chain")
    pair = next(p for p in vfx_surface.vfx_director_surface(data)["runtimePairs"]
                if p["entityId"] != data["runtimeProgram"]["itemEntityId"] and p["event"] == "periodic")
    raw = {"schema": vfx_contract.VFX_DIRECTOR_SCHEMA, "slots": [{
        "id": "authored_history", "entityId": pair["entityId"], "event": pair["event"],
        "rendererKind": "historyTrail", "anchor": "self", "blend": "alpha", "layer": "AfterProjectiles",
        "trail": trail(draw),
    }]}
    return data, raw


@pytest.mark.parametrize("draw", ["stroke", "sprites"])
def test_actual_director_compile_wire_preserves_complete_history_design(draw):
    data, raw = history_case(draw)
    before = copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "history-contract-test")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"]["slots"][0]["trail"] == raw["slots"][0]["trail"]
    assert raw == before


def test_history_texture_requires_exact_bound_producer():
    data, raw = history_case("sprites")
    entity_id = raw["slots"][0]["entityId"]
    entity = next(e for e in data["runtimeProgram"]["entities"] if e["id"] == entity_id)
    entity["visual"]["assetMode"] = "no_asset"
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    raw["slots"][0]["trail"]["texture"] = {"source": "asset", "assetId": "missing", "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


def test_history_leaf_repair_keeps_pose_sampling_and_width_frozen():
    import infini_local.core.vfx.contract as vfx_contract
    import infini_local.core.vfx.repair as vfx_repair
    import infini_local.core.vfx.validation as vfx_validation
    data, raw = history_case("sprites")
    raw["slots"][0]["trail"]["opacityProfile"]["middle"] = 2
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["trail"]["opacityProfile"]["middle"] = 0.3
    candidate["trail"].update(pose="current", sampleStepTicks=1, scale=3)
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "repair middle opacity only"}
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert vfx_validation.validate_vfx_director_output(repaired, data)["ok"]
    expected = copy.deepcopy(raw)
    expected["slots"][0]["trail"]["opacityProfile"]["middle"] = 0.3
    assert repaired == expected
    assert any(row["path"].endswith("trail.pose") for row in audit["ignoredChanges"])


def test_history_retains_legacy_fivefold_sprite_multiplier():
    value = trail("sprites")
    value["scale"] = 5
    assert not strict_schema_errors(value, history_schema())
    value["scale"] = 5.01
    assert strict_schema_errors(value, history_schema())


def test_item_history_owns_exact_use_and_player_layers_only():
    schema = {"type": "object", "allOf": history_slot_clauses(["item"], ["historyTrail", "shape"], ["on_use", "periodic"])}
    slot = {"rendererKind": "historyTrail", "entityId": "item", "event": "on_use", "trail": trail(),
            "blend": "alpha", "layer": "BeforePlayer", "anchor": "self"}
    assert not strict_schema_errors(slot, schema)
    assert not strict_schema_errors({**slot, "layer": "AfterPlayer"}, schema)
    for change in ({"event": "periodic"}, {"event": "on_spawn"}, {"layer": "AfterProjectiles"},
                   {"entityId": "projectile"}, {"duration": 12}, {"anchor": "tip"}):
        assert strict_schema_errors({**slot, **change}, schema)
    assert strict_schema_errors({"rendererKind": "shape", "layer": "BeforePlayer"}, schema)

@pytest.mark.parametrize("draw", ["stroke", "sprites"])
def test_held_history_actual_director_wire_and_hidden_refusal(draw):
    data, raw = history_case(draw)
    use = data["runtimeProgram"]["itemUse"]
    use["hideUseGraphic"] = False
    slot = raw["slots"][0]
    slot.update(entityId=data["runtimeProgram"]["itemEntityId"], event="on_use", layer="AfterPlayer")
    if draw == "sprites":
        slot["trail"]["texture"]["source"] = "item"
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "held-history-contract-test")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"]["slots"][0]["trail"] == slot["trail"]
    hidden = copy.deepcopy(data)
    hidden["runtimeProgram"]["itemUse"]["hideUseGraphic"] = True
    assert not vfx_validation.validate_vfx_director_output(raw, hidden)["ok"]
    assert not vfx_validation.validate_vfx_manifest_wire(hidden)["ok"]
