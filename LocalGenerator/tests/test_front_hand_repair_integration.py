"""Offline frozen Gameplay Repair for independent hand-component choices."""
import json
from copy import deepcopy

import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from test_front_hand_movement import entity, fixture


def _call(doc, fn):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)


@pytest.mark.parametrize("source", ["initial", "cursor", "facing", "velocity"])
def test_missing_axis_repair_creates_only_exact_dependency_not_retired_bundle(source):
    doc, pose = fixture()
    axis = _call(doc, "set_aim")
    doc["runtimeProgram"]["calls"].remove(axis)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert {r["code"] for r in report["errors"]} == {"missing_capability_dependency"}
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"] == {"entities": [], "bindings": [], "calls": []}
    assert scope["create"]["calls"]["allowedFns"] == ["set_aim"]
    assert scope["create"]["calls"]["allowedTargetIds"] == [pose["target"]]
    empty, audit = filter_repair_patch_scope(doc, {"note": "no design selected"}, scope)
    assert not audit["ok"] and apply_repair_patch(doc, empty) == doc
    selected = {**deepcopy(axis), "params": {"source": source, "turnOwner": False}}
    hostile = deepcopy(pose)
    hostile["params"]["endStretch"] = "full"
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [selected, hostile], "note": "explicit axis only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    expected = deepcopy(doc)
    expected["runtimeProgram"]["calls"].append(selected)
    repaired = apply_repair_patch(doc, patch)
    assert repaired == expected
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert doc == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("selected_axis", ["initial", "cursor", "facing", "velocity"])
def test_invalid_axis_serialized_repair_offers_exact_choices_and_freezes_siblings(monkeypatch, mode, selected_axis):
    from infini_local.pipelines.author import request as stage
    from prompt_packet_helpers import request_dossier
    from repair_test_helpers import repair_with_response
    from test_low_level_three_stage_pipeline import _empty_gameplay_patch

    doc, pose = fixture()
    axis = _call(doc, "set_aim")
    axis["params"]["source"] = "none"
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    dossier = stage.build_gameplay_repair_dossier(doc, {}, {}, failure_report=report)
    scope = dossier["repairScope"]
    assert scope["fieldPermissions"] == {"entities": [], "bindings": [],
        "calls": [{"id": axis["id"], "paths": ["params.source"]}]}
    assert scope["create"]["calls"]["allowedFns"] == []
    assert scope["retarget"]["callTargetIds"] == []
    assert dossier["acceptedItemContext"]["runtimeProgram"] == doc["runtimeProgram"]
    filtered, audit = filter_repair_patch_scope(doc, _empty_gameplay_patch(), scope)
    assert not audit["ok"] and apply_repair_patch(doc, filtered) == doc
    hostile_axis = deepcopy(axis)
    hostile_axis["params"].update(source=selected_axis, turnOwner=True)
    hostile_pose = deepcopy(pose)
    hostile_pose["params"]["peakProgress"] = .8
    hostile_attachment = deepcopy(_call(doc, "attach"))
    hostile_attachment["params"]["axisOffsetBlocks"] = 100
    hostile_spawn = deepcopy(_call(doc, "spawn"))
    hostile_spawn["params"].update(aim="facing", count=2, velocity={"speed": 0})
    patch = {**_empty_gameplay_patch(), "callsUpsert": [hostile_axis, hostile_pose, hostile_attachment, hostile_spawn],
             "realizationReplacement": deepcopy(doc["realization"])}
    repaired, request = repair_with_response(monkeypatch, doc, patch, mode, out_of_scope_response=True)
    packet = request_dossier(request)
    assert packet["repairScope"]["fieldPermissions"] == scope["fieldPermissions"]
    card = next(c for c in packet["existingBrokenCapabilityCards"] if c["fn"] == "set_aim")
    assert card["params"]["source"]["enum"] == ["initial", "cursor", "facing", "velocity"]
    expected = deepcopy(doc)
    _call(expected, "set_aim")["params"]["source"] = selected_axis
    assert repaired["runtimeProgram"] == expected["runtimeProgram"]
    assert repaired["name"] == expected["name"] and repaired["category"] == expected["category"]
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    assert entity(wire)["aim"]["source"] == selected_axis
    assert entity(wire)["attachment"]["axisOffsetPx"] == 11
    assert entity(wire)["armPose"]["peakProgress"] == .3
    assert doc == before


def test_reordered_invalid_axis_repair_tracks_exact_call_not_other_entity():
    from test_composable_motion_primitives import add
    doc, _ = fixture()
    axis = _call(doc, "set_aim")
    axis["params"]["source"] = "none"
    doc["runtimeProgram"]["calls"].reverse()
    doc["runtimeProgram"]["entities"].append({"id": "other_entity", "kind": "free_projectile"})
    unrelated = add(doc, "set_aim", {"source": "cursor"}, "other_axis")
    unrelated["target"] = "other_entity"
    report = validate_runtime_program(doc)
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": axis["id"], "paths": ["params.source"]}]
    assert any(r["errorPath"] == f"$.runtimeProgram.calls[{doc['runtimeProgram']['calls'].index(axis)}].params.source"
               for r in scope["repairRequirements"])


@pytest.mark.parametrize("fn", ["move_front_hand", "move_forward_then_retract", "charge_then_release"])
def test_retired_bundle_is_never_a_repair_creation_choice(fn):
    doc, _ = fixture()
    axis = _call(doc, "set_aim")
    doc["runtimeProgram"]["calls"].remove(axis)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert fn not in scope["create"]["calls"]["allowedFns"]
    filtered, audit = filter_repair_patch_scope(doc, {"callsUpsert": [
        {"id": "retired", "fn": fn, "target": axis["target"], "params": {}}], "note": "not a fresh choice"}, scope)
    assert not audit["ok"]
    assert apply_repair_patch(doc, filtered) == doc


@pytest.mark.parametrize("hand_pose,viable", [("", True), ("one_handed", False), (None, False), (False, False)])
def test_candidate_frozen_pose_dependency_uses_typed_hand_pose_semantics(hand_pose, viable):
    from infini_local.core.runtime_authoring.repair.facts import _candidate_capability_viable
    doc, pose = fixture()
    _call(doc, "item_use")["params"]["handPose"] = hand_pose
    assert validate_runtime_program(doc)["ok"] is viable
    doc["runtimeProgram"]["calls"].remove(pose)
    assert _candidate_capability_viable("front_arm_pose", [pose["target"]], doc["runtimeProgram"]) is viable


def test_pose_axis_requirement_cannot_consume_support_from_another_exact_entity():
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    from infini_local.core.runtime_authoring.validator import _validate_requirement
    doc, pose = fixture()
    axis = _call(doc, "set_aim")
    axis["target"] = "other_entity"
    calls = doc["runtimeProgram"]["calls"]
    cap = CAPABILITY_REGISTRY["front_arm_pose"]
    requirement = next(r for r in cap.requirements if r.capability == "set_aim")
    issue = _validate_requirement(requirement, call=pose, call_index=calls.index(pose), cap=cap,
        item_id="item", calls_by_target={pose["target"]: [c for c in calls if c.get("target") == pose["target"]],
                                       "other_entity": [axis]},
        entities_by_id={}, bindings=doc["runtimeProgram"]["bindings"],
        primary_entity_id=pose["target"], calls=calls)
    assert issue is not None and issue.code == "missing_capability_dependency"
    assert issue.path == f"$.runtimeProgram.calls[{calls.index(pose)}]"
    assert issue.allowed == ("set_aim",)


def test_frozen_wrong_primary_pose_target_does_not_offer_owner_reselection():
    doc, _ = fixture()
    doc["runtimeProgram"]["primaryEntityId"] = "item"
    # Isolate the frozen pose-target error: a hidden item with only a spawn
    # binding would independently make the primary selection invalid.
    _call(doc, "item_use")["params"]["hideUseGraphic"] = False
    report = validate_runtime_program(doc)
    assert {row["code"] for row in report["errors"]} == {"wrong_target_kind"}
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["repairTransactions"]["primaryEntitySelection"]["allowed"] is False
    assert scope["retarget"]["callTargetIds"] == []



def test_hidden_item_primary_has_its_own_explicit_reselection_error():
    doc, pose = fixture()
    doc["runtimeProgram"]["primaryEntityId"] = "item"
    _call(doc, "item_use")["params"]["hideUseGraphic"] = True
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert {row["code"] for row in report["errors"]} == {
        "hidden_item_primary_requires_spawn_target", "wrong_target_kind"}
    selection = build_runtime_repair_scope(doc, report["errors"])["repairTransactions"]["primaryEntitySelection"]
    assert selection["allowed"] is True
    assert selection["candidateEntityIds"] == [pose["target"]]
    assert doc == before


def test_bad_attachment_offset_repair_changes_only_exact_leaf_not_other_motion_choices():
    good, _ = fixture(axisOffsetBlocks=0)
    doc = deepcopy(good)
    attachment = _call(doc, "attach")
    attachment["params"]["axisOffsetBlocks"] = None
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"] == {"entities": [], "bindings": [],
        "calls": [{"id": attachment["id"], "paths": ["params.axisOffsetBlocks"]}]}
    hostile = deepcopy(attachment)
    hostile["params"].update(axisOffsetBlocks=0, normalOffsetBlocks=2, anchor="owner_center")
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [hostile], "note": "explicit neutral offset only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(doc, patch)
    assert repaired == good
    wire = compile_runtime_program(repaired)
    assert entity(wire)["attachment"] == {"anchor": "front_hand", "axisOffsetPx": 0, "normalOffsetPx": 0}
    assert validate_runtime_wire(wire)["ok"]
    assert doc == before


def test_competing_item_pose_repair_thaws_only_exact_item_leaf():
    good, _ = fixture()
    _call(good, "item_use")["params"]["handPose"] = ""
    doc = deepcopy(good)
    use = _call(doc, "item_use")
    use["params"]["handPose"] = "one_handed"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"] == {"entities": [], "bindings": [],
        "calls": [{"id": use["id"], "paths": ["params.handPose"]}]}
    hostile = deepcopy(use)
    hostile["params"].update(handPose="", channel=True, hideUseGraphic=True)
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [hostile], "note": "one writer only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(doc, patch)
    assert repaired == good
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("expected", [{"speed": 0}, [0, {"nested": [False, None, "literal"]}]])
def test_emitted_json_container_descriptor_keeps_exact_type(expected):
    from infini_local.core.runtime_authoring.repair.facts import _capability_constraints
    encoded = json.dumps(expected, separators=(",", ":"))
    names, constraints = _capability_constraints(["spawn.velocity=" + encoded])
    assert names == {"spawn"}
    assert constraints == [{"capability": "spawn", "param": "velocity", "equals": expected}]
    assert json.loads(json.dumps(constraints))[0]["equals"] == expected


@pytest.mark.parametrize("raw,expected", [("true", True), ("FALSE", False), ("null", None), ("1", 1), ("0.0", 0.0),
    ('""', ""), ("'cursor'", "cursor"), ("cursor", "cursor")])
def test_scalar_constraint_legacy_types_are_unchanged(raw, expected):
    from infini_local.core.runtime_authoring.repair.facts import _decode_constraint_value
    actual = _decode_constraint_value(raw)
    assert type(actual) is type(expected) and actual == expected


@pytest.mark.parametrize("raw", ['{"speed":', '[0,]', '{"x":0,"x":1}', '[NaN]', '[1e999]'])
def test_malformed_container_constraint_stays_literal_not_partial_json(raw):
    from infini_local.core.runtime_authoring.repair.facts import _decode_constraint_value
    assert _decode_constraint_value(raw) == raw


@pytest.mark.parametrize("value", [False, None, "11", float("inf")])
def test_bad_present_attachment_leaf_cannot_be_accepted_as_neutral_during_repair(value):
    doc, _ = fixture()
    attachment = _call(doc, "attach")
    attachment["params"]["axisOffsetBlocks"] = value
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": attachment["id"], "paths": ["params.axisOffsetBlocks"]}]
    filtered, audit = filter_repair_patch_scope(doc, {"callsUpsert": [deepcopy(attachment)], "note": "not corrected"}, scope)
    assert not audit["ok"]
    assert not validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]
    assert doc == before
