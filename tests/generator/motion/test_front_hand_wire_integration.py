"""Joined Author/Visual delivery and optional-present native sprite metadata."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.visual_contract_schema import front_hand_sprite_errors
import infini_local.pipelines.visual.contract as visual_contract
import infini_local.pipelines.visual.stage as visual_stage
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from tests.generator.motion.test_front_hand_movement import fixture, entity, saved_hand_wire
from tests.generator.authoring.test_low_level_three_stage_pipeline import _visual_kit, wire_transport


def test_real_author_visual_frozen_grip_repair_survives_strict_delivery(wire_transport):
    from infini_local.pipelines.author import request as llm_authoring_pipeline

    author, _ = fixture()
    responses, requests = wire_transport
    responses.append(author)
    planned = llm_authoring_pipeline.try_llm_plan({}, {}, "offline-hand-join")
    assert planned is not None
    compiled = compile_runtime_program(planned)
    kit = _visual_kit(compiled)
    body = next(r for r in kit["entities"] if r["entityId"] == "witness_entity")
    body.update(assetMode="baked_sprite", visualProjectRef="entity",
                prompt="bronze rigid body with separate handle", silhouette="blade and handle",
                visualIdentity="bronze blade, red handle", preferredCanvasSize=32,
                renderSizePx=41, forwardAngleDegrees=17)
    corrected = dict(body, grip={"normalizedX": .2, "normalizedY": .6})
    responses.extend([kit, {"schema": visual_contract.VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": None, "entitiesUpsert": [corrected], "entityIdsDelete": [],
        "entityIndicesDelete": [], "note": "selected grip only"}])
    projected = visual_stage.apply_visual_director(compiled, {}, {})
    delivered = sanitize_recipe_for_delivery(projected)
    assert not responses
    assert [r["_infini_stage"] for r in requests] == ["planner", "visual_director", "visual_repair"]
    for member in ("aim", "attachment", "armPose", "hitbox", "collision", "spawn"):
        assert entity(delivered)[member] == entity(compiled)[member]
    assert not {"movement", "controller", "reach", "ownerControl"} & entity(delivered).keys()
    assert entity(delivered)["attachment"]["axisOffsetPx"] == 11
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
def test_distinct_optional_grip_is_atomic_strict_and_nonmutating(grip):
    wire = compile_runtime_program(build_capability_witness("move_straight"))
    wire.pop("runtimeContract")
    entity(wire)["visual"].update(assetMode="baked_sprite", grip=grip)
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert report["ok"] == (grip == {"normalizedX": .2, "normalizedY": .6}), report["errors"]
    assert wire == before


@pytest.mark.parametrize("mode", ["reuse_item_icon", "no_asset", "runtime_geometry"])
def test_nonowning_entity_grip_is_rejected_independently_of_movement(mode):
    wire = compile_runtime_program(build_capability_witness("move_straight"))
    wire.pop("runtimeContract")
    entity(wire)["visual"].update(assetMode=mode, grip={"normalizedX": .2, "normalizedY": .6})
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(r["code"] == "nonowning_sprite_presentation" for r in report["errors"])


def test_item_body_entity_does_not_duplicate_root_grip():
    wire = compile_runtime_program(build_capability_witness("move_straight"))
    wire.pop("runtimeContract")
    wire.setdefault("visual", {})["grip"] = {"normalizedX": .2, "normalizedY": .6}
    assert validate_runtime_wire(wire)["ok"]
    wire["runtimeProgram"]["entities"][0]["visual"]["grip"] = deepcopy(wire["visual"]["grip"])
    report = validate_runtime_wire(wire)
    assert not report["ok"] and any(r["code"] == "nonowning_sprite_presentation" for r in report["errors"])


def test_current_optional_grip_and_disabled_plain_spawn_remain_readable():
    for fn in ("move_straight", "target_and_fire"):
        wire = compile_runtime_program(build_capability_witness(fn))
        wire.pop("runtimeContract")
        body = next(e for e in wire["runtimeProgram"]["entities"] if e["kind"] != "item_body")
        if fn == "move_straight":
            body["spawn"]["enabled"] = False  # admission, not executable spawn
        before = deepcopy(wire)
        report = validate_runtime_wire(wire)
        assert report["ok"], report["errors"]
        assert wire == before


def test_captured_bundled_hand_is_refused_without_projection():
    wire = saved_hand_wire()
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["code"] == "unsupported_opcode" and ".movement.code" in e["path"] for e in report["errors"])
    assert wire == before


@pytest.mark.parametrize("code,name", [(19, "move_forward_then_retract"), (20, "move_front_hand")])
def test_retired_hand_code_cannot_hide_inside_an_otherwise_current_definition(code, name):
    wire = compile_runtime_program(fixture()[0])
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    entity(wire)["movement"] = {"code": code, "name": name}
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["code"] == "unsupported_opcode" and ".movement.code" in e["path"] for e in report["errors"])
    assert wire == before
