"""Offline Gameplay Repair joins for registry-exact front-hand dependencies."""
from copy import deepcopy
import json

import pytest

from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from test_front_hand_movement import fixture


def _call(doc, fn):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)


@pytest.mark.parametrize("max_active,hand_pose", [
    pytest.param(1, None, id="singleton-absent-hand-pose"),
    pytest.param(1, "", id="singleton-empty-hand-pose"),
    pytest.param(2, "", id="incompatible-frozen-singleton"),
])
def test_missing_movement_repair_respects_exact_frozen_support(max_active, hand_pose):
    doc, movement = fixture()
    if hand_pose is not None:
        _call(doc, "configure_item_use")["params"]["handPose"] = hand_pose
    _call(doc, "set_projectile_concurrency")["params"]["maxActive"] = max_active
    doc["runtimeProgram"]["calls"].remove(movement)
    before = json.dumps(doc, sort_keys=True)
    report = validate_runtime_program(doc)
    assert {row["code"] for row in report["errors"]} == {"missing_movement_component"}
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"] == {"entities": [], "bindings": [], "calls": []}
    assert ("move_front_hand" in scope["create"]["calls"]["allowedFns"]) == (max_active == 1)
    inserted = {**deepcopy(movement), "id": "explicit_repair_hand"}
    filtered, audit = filter_repair_patch_scope(doc, {
        "callsUpsert": [inserted], "note": "explicit model-selected movement"}, scope)
    repaired = apply_repair_patch(doc, filtered)
    if max_active == 1:
        assert audit["ok"], audit
        expected = deepcopy(doc)
        expected["runtimeProgram"]["calls"].append(inserted)
        assert repaired == expected
        assert validate_runtime_program(repaired)["ok"]
    else:
        assert not audit["ok"], audit
        assert repaired == doc
        assert {row["code"] for row in validate_runtime_program(repaired)["errors"]} == {"missing_movement_component"}
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("selected_aim", ["cursor", "facing", "velocity"])
def test_aim_none_serialized_repair_offers_exact_axis_choices_and_freezes_siblings(monkeypatch, mode, selected_aim):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.pipelines import llm_authoring_pipeline as stage
    from prompt_packet_helpers import request_dossier
    from repair_test_helpers import repair_with_response
    from test_low_level_three_stage_pipeline import _empty_gameplay_patch
    from test_front_hand_movement import entity

    doc, movement = fixture(aimMode="initial")
    spawn = _call(doc, "configure_spawn")
    spawn["params"]["aim"] = "none"
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    dossier = stage.build_gameplay_repair_dossier(doc, {}, {}, failure_report=report)
    scope = dossier["repairScope"]
    index = doc["runtimeProgram"]["calls"].index(spawn)
    assert scope["fieldPermissions"] == {"entities": [], "bindings": [],
        "calls": [{"id": spawn["id"], "paths": ["params.aim"]}]}
    assert len(scope["repairRequirements"]) == 1
    requirement = scope["repairRequirements"][0]
    assert requirement["errorPath"] == f"$.runtimeProgram.calls[{index}].params.aim"
    assert requirement["allowedValues"] == ["cursor", "facing", "velocity"]
    assert scope["create"]["calls"]["allowedFns"] == []
    assert scope["retarget"]["callTargetIds"] == []
    assert dossier["acceptedItemContext"]["runtimeProgram"] == doc["runtimeProgram"]
    # Omission means leave unchanged, not choose the first offered axis.
    filtered, audit = filter_repair_patch_scope(doc, _empty_gameplay_patch(), scope)
    assert not audit["ok"] and apply_repair_patch(doc, filtered) == doc
    hostile_spawn = deepcopy(spawn)
    hostile_spawn["params"].update(aim=selected_aim, count=2,
        velocity={'constantSpeedBlocksPerSecond': (4) * 60 / 16})
    hostile_movement = deepcopy(movement)
    hostile_movement["params"]["aimMode"] = "cursor"
    hostile_singleton = deepcopy(_call(doc, "set_projectile_concurrency"))
    hostile_singleton["params"]["maxActive"] = 2
    patch = {**_empty_gameplay_patch(), "callsUpsert": [hostile_spawn, hostile_movement, hostile_singleton],
             "realizationReplacement": deepcopy(doc["realization"])}
    repaired, request = repair_with_response(monkeypatch, doc, patch, mode, out_of_scope_response=True)
    packet = request_dossier(request)
    assert packet["repairScope"]["fieldPermissions"] == scope["fieldPermissions"]
    assert packet["repairScope"]["repairRequirements"][0]["allowedValues"] == ["cursor", "facing", "velocity"]
    expected = deepcopy(doc)
    _call(expected, "configure_spawn")["params"]["aim"] = selected_aim
    # Caller diagnostic metadata is separate from frozen authored mechanics.
    assert repaired["runtimeProgram"] == expected["runtimeProgram"]
    assert repaired["name"] == expected["name"] and repaired["category"] == expected["category"]
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    assert entity(wire)["spawn"]["aim"] == selected_aim
    assert entity(wire)["movement"]["code"] == 20
    assert doc == before


def test_launch_axis_diagnostic_tracks_reordered_exact_target_dependency_not_another_entity():
    doc, movement = fixture()
    spawn = _call(doc, "configure_spawn")
    spawn["params"]["aim"] = "none"
    unrelated = deepcopy(spawn)
    unrelated.update(id="other_spawn", target="other_entity")
    unrelated["params"]["aim"] = "cursor"
    doc["runtimeProgram"]["calls"].reverse()
    calls = [unrelated, *doc["runtimeProgram"]["calls"]]
    from infini_local.core.runtime_authoring.validator import _validate_requirement
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    cap = CAPABILITY_REGISTRY["move_front_hand"]
    requirement = next(r for r in cap.requirements if r.capability == "configure_spawn" and r.param == "aim")
    issue = _validate_requirement(requirement, call=movement, call_index=calls.index(movement), cap=cap,
        item_id="item", calls_by_target={movement["target"]: doc["runtimeProgram"]["calls"], "other_entity": [unrelated]},
        entities_by_id={}, bindings=[], primary_entity_id=movement["target"], calls=calls)
    assert issue is not None
    assert issue.path == f"$.runtimeProgram.calls[{calls.index(spawn)}].params.aim"
    assert issue.allowed == ("cursor", "facing", "velocity")


@pytest.mark.parametrize("conflict", ["controller", "over-target-position"])
def test_missing_movement_does_not_offer_hand_against_frozen_owner_conflicts(conflict):
    doc, movement = fixture()
    doc["runtimeProgram"]["calls"].remove(movement)
    if conflict == "controller":
        _call(doc, "configure_item_use")["params"]["channel"] = True
        doc["runtimeProgram"]["calls"].append({
            "id": "accepted_charge", "fn": "charge_then_release", "target": movement["target"],
            "params": {'chargeSeconds': (12) / 60, "damageMultiplier": 1, "knockbackMultiplier": 1, "speedMultiplier": 1}})
    else:
        _call(doc, "configure_spawn")["params"]["position"] = {
            "above": "cursor", "heightTiles": 3, 'activationDelaySeconds': (0) / 60}
    expected_code = "missing_capability_group" if conflict == "controller" else "missing_movement_component"
    report = validate_runtime_program(doc)
    assert {row["code"] for row in report["errors"]} == {expected_code}
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"] == {"entities": [], "bindings": [], "calls": []}
    assert "move_front_hand" not in scope["create"]["calls"]["allowedFns"]
    filtered, audit = filter_repair_patch_scope(doc, {
        "callsUpsert": [movement], "note": "cannot replace frozen owner"}, scope)
    assert not audit["ok"]
    assert apply_repair_patch(doc, filtered) == doc
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("fn,param,value,viable", [
    pytest.param("configure_spawn", "spreadRadians", 0.0, True, id="number-zero-equivalent"),
    pytest.param("set_projectile_concurrency", "maxActive", True, False, id="bool-not-integer-one"),
    pytest.param("configure_spawn", "spreadRadians", False, False, id="bool-not-number-zero"),
    pytest.param("set_projectile_collision", "tileCollide", 0, False, id="integer-not-boolean-false"),
    pytest.param("configure_spawn", "velocity", {"constantSpeedBlocksPerSecond": False}, False, id="structured-bool-not-zero"),
    pytest.param("configure_item_use", "handPose", None, False, id="null-not-allowed-absence"),
    pytest.param("configure_spawn", "aim", "none", False, id="no-launch-axis"),
    pytest.param("configure_spawn", "aim", "facing", True, id="explicit-facing-axis"),
    pytest.param("configure_spawn", "aim", "velocity", True, id="explicit-velocity-axis"),
    pytest.param("configure_spawn", "aim", True, False, id="axis-bool-not-token"),
    pytest.param("configure_spawn", "aim", "cursor ", False, id="axis-token-no-trim"),
])
def test_candidate_frozen_dependency_matches_author_typed_semantics(fn, param, value, viable):
    from infini_local.core.runtime_authoring.repair_scope import _candidate_capability_viable

    doc, movement = fixture()
    _call(doc, fn)["params"][param] = value
    assert validate_runtime_program(doc)["ok"] is viable
    doc["runtimeProgram"]["calls"].remove(movement)
    assert _candidate_capability_viable("move_front_hand", [movement["target"]], doc["runtimeProgram"]) is viable


def test_candidate_cannot_use_dependency_from_another_exact_entity():
    from infini_local.core.runtime_authoring.repair_scope import _candidate_capability_viable

    doc, movement = fixture()
    other = deepcopy(_call(doc, "set_projectile_concurrency"))
    other.update(id="other_singleton", target="other_entity")
    _call(doc, "set_projectile_concurrency")["params"]["maxActive"] = 2
    doc["runtimeProgram"]["entities"].append({
        **deepcopy(next(row for row in doc["runtimeProgram"]["entities"] if row["id"] == movement["target"])),
        "id": "other_entity"})
    doc["runtimeProgram"]["calls"].append(other)
    doc["runtimeProgram"]["calls"].remove(movement)
    assert not _candidate_capability_viable("move_front_hand", [movement["target"]], doc["runtimeProgram"])


@pytest.mark.parametrize("expected", [
    {"constantSpeedBlocksPerSecond": 0},
    [0, {"nested": [False, None, "literal"]}],
])
def test_emitted_json_container_descriptor_keeps_exact_type(expected):
    from infini_local.core.runtime_authoring.repair_scope import _capability_constraints

    encoded = json.dumps(expected, separators=(",", ":"))
    names, constraints = _capability_constraints(["configure_spawn.velocity=" + encoded])
    assert names == {"configure_spawn"}
    assert constraints == [{"capability": "configure_spawn", "param": "velocity", "equals": expected}]
    assert json.loads(json.dumps(constraints))[0]["equals"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("true", True), ("FALSE", False), ("null", None), ("1", 1), ("0.0", 0.0),
    ('""', ""), ("'cursor'", "cursor"), ("cursor", "cursor"),
])
def test_scalar_constraint_legacy_types_are_unchanged(raw, expected):
    from infini_local.core.runtime_authoring.repair_scope import _decode_constraint_value

    actual = _decode_constraint_value(raw)
    assert type(actual) is type(expected) and actual == expected


@pytest.mark.parametrize("raw", [
    '{"constantSpeedBlocksPerSecond":', '[0,]', '{"x":0,"x":1}', '[NaN]', '[1e999]',
])
def test_malformed_container_constraint_stays_literal_not_partial_json(raw):
    from infini_local.core.runtime_authoring.repair_scope import _decode_constraint_value

    assert _decode_constraint_value(raw) == raw


@pytest.mark.parametrize("velocity", [
    '{"constantSpeedBlocksPerSecond":0}', False, {"constantSpeedBlocksPerSecond": False},
    {"constantSpeedBlocksPerSecond": "0"}, {"disk": {"maxSpeedBlocksPerSecond": 0}},
])
def test_zero_velocity_repair_refuses_wrong_types_and_other_projection(velocity):
    doc, _ = fixture()
    spawn = _call(doc, "configure_spawn")
    spawn["params"]["velocity"] = {'constantSpeedBlocksPerSecond': (3) * 60 / 16}
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": spawn["id"], "paths": ["params.velocity"]}]
    candidate = deepcopy(spawn)
    candidate["params"]["velocity"] = velocity
    filtered, audit = filter_repair_patch_scope(doc, {
        "callsUpsert": [candidate], "note": "invalid zero velocity must remain RED"}, scope)
    assert not audit["ok"], audit
    assert not validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]
    assert doc == before


def test_structured_zero_velocity_dossier_and_frozen_repair_join():
    from infini_local.pipelines.llm_authoring_pipeline import build_gameplay_repair_dossier

    good, _ = fixture()
    doc = deepcopy(good)
    spawn = _call(doc, "configure_spawn")
    spawn["params"]["velocity"] = {'constantSpeedBlocksPerSecond': (3) * 60 / 16}
    before = json.dumps(doc, sort_keys=True)
    report = validate_runtime_program(doc)
    assert {row["code"] for row in report["errors"]} == {"missing_item_capability_param"}
    dossier = build_gameplay_repair_dossier(doc, {}, {}, failure_report=report)
    scope = dossier["repairScope"]
    constraint = next(c for r in scope["repairRequirements"] for c in r["exactCapabilityParams"]
                      if c["param"] == "velocity")
    assert constraint == {"capability": "configure_spawn", "param": "velocity",
                          "equals": {"constantSpeedBlocksPerSecond": 0}}
    assert json.loads(json.dumps(dossier))["repairScope"] == scope
    assert scope["fieldPermissions"]["calls"] == [{"id": spawn["id"], "paths": ["params.velocity"]}]
    assert scope["create"]["calls"]["allowedFns"] == []
    assert dossier["acceptedItemContext"]["runtimeProgram"] == doc["runtimeProgram"]
    hostile = deepcopy(spawn)
    hostile["params"].update(velocity={'constantSpeedBlocksPerSecond': (0) * 60 / 16}, aim="facing", count=2)
    singleton = deepcopy(_call(doc, "set_projectile_concurrency"))
    singleton["params"]["maxActive"] = 2
    filtered, audit = filter_repair_patch_scope(doc, {
        "callsUpsert": [hostile, singleton], "note": "explicit zero with hostile siblings"}, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert repaired == good
    assert validate_runtime_program(repaired)["ok"]
    assert json.dumps(doc, sort_keys=True) == before
