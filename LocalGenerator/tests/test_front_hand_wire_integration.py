"""Joined Author/Visual delivery and optional-present native sprite metadata."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.visual_contract_schema import front_hand_sprite_errors
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from test_front_hand_movement import fixture, entity
from test_low_level_three_stage_pipeline import _visual_kit, wire_transport


def test_real_author_visual_frozen_grip_repair_survives_strict_delivery(wire_transport):
    from infini_local.pipelines import llm_authoring_pipeline

    author, _ = fixture()
    responses, requests = wire_transport
    responses.append(author)
    planned = llm_authoring_pipeline.try_llm_plan({}, {}, {}, {}, "offline-hand-join")
    assert planned is not None
    compiled = compile_runtime_program(planned)
    kit = _visual_kit(compiled)
    body = next(r for r in kit["entities"] if r["entityId"] == "witness_entity")
    body.update(assetMode="baked_sprite", visualProjectRef="entity",
                prompt="bronze rigid body with separate handle", silhouette="blade and handle",
                visualIdentity="bronze blade, red handle", preferredCanvasSize=32,
                renderSizePx=41, forwardAngleDegrees=17)
    corrected = dict(body, grip={"normalizedX": .2, "normalizedY": .6})
    responses.extend([kit, {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": None, "entitiesUpsert": [corrected], "entityIdsDelete": [],
        "entityIndicesDelete": [], "animationPlan": None, "note": "selected grip only"}])
    projected = visual.apply_visual_director(compiled, {}, {}, {}, {})
    delivered = sanitize_recipe_for_delivery(projected)
    assert not responses
    assert [r["_infini_stage"] for r in requests] == ["planner", "visual_director", "visual_repair"]
    assert entity(delivered)["movement"] == entity(compiled)["movement"]
    assert entity(delivered)["visual"]["grip"] == corrected["grip"]
    assert not front_hand_sprite_errors(delivered)
    report = validate_runtime_wire(delivered)
    assert report["ok"], report["errors"]


@pytest.mark.parametrize("grip", [
    {"normalizedX": .2, "normalizedY": .6}, None,
    {"normalizedX": True, "normalizedY": .6}, {"normalizedX": .2},
    {"normalizedX": float("inf"), "normalizedY": .6},
    {"normalizedX": -.1, "normalizedY": .6},
    {"normalizedX": .2, "normalizedY": .6, "extra": 0},
])
def test_legacy_distinct_optional_grip_is_atomic_strict_and_nonmutating(grip):
    wire = compile_runtime_program(build_capability_witness("move_forward_then_retract"))
    wire.pop("runtimeContract")
    entity(wire)["visual"].update(assetMode="baked_sprite", grip=grip)
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert report["ok"] == (grip == {"normalizedX": .2, "normalizedY": .6}), report["errors"]
    assert wire == before


@pytest.mark.parametrize("mode", ["reuse_item_icon", "no_asset", "runtime_geometry"])
def test_nonowning_entity_grip_is_rejected_even_on_legacy_driver(mode):
    wire = compile_runtime_program(build_capability_witness("move_forward_then_retract"))
    wire.pop("runtimeContract")
    entity(wire)["visual"].update(assetMode=mode, grip={"normalizedX": .2, "normalizedY": .6})
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(r["code"] == "nonowning_sprite_presentation" for r in report["errors"])


def test_item_body_entity_does_not_duplicate_root_grip():
    wire = compile_runtime_program(build_capability_witness("move_forward_then_retract"))
    wire.pop("runtimeContract")
    wire.setdefault("visual", {})["grip"] = {"normalizedX": .2, "normalizedY": .6}
    assert validate_runtime_wire(wire)["ok"]
    wire["runtimeProgram"]["entities"][0]["visual"]["grip"] = deepcopy(wire["visual"]["grip"])
    report = validate_runtime_wire(wire)
    assert not report["ok"] and any(r["code"] == "nonowning_sprite_presentation" for r in report["errors"])


@pytest.mark.parametrize("enabled", [False, None, 1])
def test_new_driver_spawn_dependency_requires_actual_enabled_component(enabled):
    author, _ = fixture()
    wire = compile_runtime_program(author)
    wire.pop("runtimeContract")
    if enabled is None:
        entity(wire)["spawn"].pop("enabled")
    else:
        entity(wire)["spawn"]["enabled"] = enabled
    report = validate_runtime_wire(wire)
    assert not report["ok"], report


def test_old_omitted_grip_controller_bag_and_disabled_spawn_remain_readable():
    for fn in ("move_forward_then_retract", "target_and_fire"):
        wire = compile_runtime_program(build_capability_witness(fn))
        wire.pop("runtimeContract")
        body = next(e for e in wire["runtimeProgram"]["entities"] if e["kind"] != "item_body")
        if fn == "target_and_fire":
            body["controller"].pop("params", None)
        else:
            body["spawn"]["enabled"] = False  # historical admission, not executable spawn
        before = deepcopy(wire)
        report = validate_runtime_wire(wire)
        assert report["ok"], report["errors"]
        assert wire == before
