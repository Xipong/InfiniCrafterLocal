"""Production Author -> provider -> compiler/wire and frozen Repair for A11."""
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, compile_runtime_program, validate_runtime_program, validate_runtime_wire,
    build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines import author_item_contract as contract
from infini_local.qa.capability_witnesses import build_capability_witness
from test_codex_subscription_contract import _encode_nullable_fixture
from test_runtime_spawn_distributions import VELOCITIES


FN = "spawn_entity_from_hit_target"


def fixture():
    document = build_capability_witness(FN)
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == FN)
    return document, call


def event_wire(wire, call):
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    return next(row for row in entity["events"] if row["id"] == call["id"])


@pytest.mark.parametrize("velocity", VELOCITIES)
@pytest.mark.parametrize("probability", [0, 0.85, 1])
def test_target_geometry_and_child_velocity_have_exact_provider_inverse_and_native_wire(velocity, probability):
    document, call = fixture()
    call["params"]["geometry"]["beforeProbability"] = probability
    call["params"].update(when="on_crit", damageBasis="live_parent", delayTicks=11)
    spawn = next(row for row in document["runtimeProgram"]["calls"]
                 if row["fn"] == "configure_spawn" and row["target"] == call["params"]["entity"])
    spawn["params"]["velocity"] = deepcopy(velocity)
    local, provider = contract.author_item_response_schema(), contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(document, local)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_author_item_to_local(encoded, response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == document and validate_runtime_program(restored)["ok"]
    wire = compile_runtime_program(restored)
    event = event_wire(wire, call)
    assert event["id"] == call["id"] and event["action"] == "spawn_entity_on_event" and event["actionCode"] == 1
    assert event["hitTargetSpawn"] == call["params"]["geometry"] and event["spreadRadians"] == 0
    assert "geometry" not in event
    assert validate_runtime_wire(wire)["ok"]
    for source in (None, restored):
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("name,value", [
    ("beforeProbability", -0.01), ("beforeProbability", 1.01), ("beforeProbability", True),
    ("hitboxMaxSideFactor", 2.01), ("clearancePx", -1), ("beforePositionJitterRadiusPx", 129),
    ("beforeDirectionJitterRadians", 3.15), ("afterFanSpreadRadians", 6.3),
    ("initialIgnoreCountdownUpdates", -1), ("initialIgnoreCountdownUpdates", 601),
    ("initialIgnoreCountdownUpdates", 1.0), ("initialIgnoreCountdownUpdates", None),
])
def test_geometry_rejects_invalid_values_in_author_and_wire_without_diagnostic_receipts(name, value):
    document, call = fixture()
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    call["params"]["geometry"][name] = value
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)
    event_wire(wire, call)["hitTargetSpawn"][name] = value
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("name", list(CAPABILITY_REGISTRY[FN].params["geometry"].properties))
def test_missing_geometry_leaf_repair_cannot_rewrite_probability_event_or_child(name):
    document, call = fixture()
    original = deepcopy(call["params"]["geometry"])
    del call["params"]["geometry"][name]
    report = validate_runtime_program(document)
    scope = build_runtime_repair_scope(document, report["errors"])
    permission = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"])
    assert permission["paths"] == [f"params.geometry.{name}"]
    candidate = deepcopy(call)
    candidate["params"].update(entity="item", when="on_crit", count=12)
    candidate["params"]["geometry"] = {key: (value if key == name else 0) for key, value in original.items()}
    patch, audit = filter_repair_patch_scope(document, {"note": "fill exact missing leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, patch)
    expected = deepcopy(document)
    next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"]["geometry"][name] = original[name]
    assert repaired == expected
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "old-fn", "swap-equal", "wrong-event", "remove-whole-geometry", "inactive-spread"])
def test_target_geometry_receipts_cannot_be_reassigned_or_silently_removed(mutation):
    document, call = fixture()
    call["params"]["geometry"].update(clearancePx=0, beforePositionJitterRadiusPx=0)
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    geometry = [row for row in receipts if row.get("fn") == FN and ".params.geometry" in row.get("authoredPath", "")]
    leaf = next(row for row in geometry if row["finalPath"].endswith(".clearancePx"))
    if mutation == "drop": receipts.remove(leaf)
    elif mutation == "duplicate": receipts.append(deepcopy(leaf))
    elif mutation == "old-fn": leaf["fn"] = "spawn_entity_on_event"
    elif mutation == "wrong-event": leaf["callId"] = "other_event"
    elif mutation == "swap-equal":
        other = next(row for row in geometry if row["finalPath"].endswith(".beforePositionJitterRadiusPx"))
        leaf["authoredPath"], other["authoredPath"] = other["authoredPath"], leaf["authoredPath"]
    elif mutation == "remove-whole-geometry":
        event_wire(wire, call).pop("hitTargetSpawn")
        receipts[:] = [row for row in receipts if row not in geometry]
    else:
        event_wire(wire, call)["spreadRadians"] = 0.3
        next(row for row in geometry if row["finalPath"].endswith(".spreadRadians"))["value"] = 0.3
    for source in (None, document):
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mutation", ["event", "source-kind", "target-kind", "placement", "aim", "offset", "over-target", "null", "missing", "foreign", "action"])
def test_target_geometry_consumer_and_reference_constraints_are_strict_without_receipts(mutation):
    document, call = fixture()
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    event = event_wire(wire, call)
    child = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["params"]["entity"])
    if mutation == "event": event["event"] = "on_expire"
    elif mutation == "source-kind": next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])["kind"] = "item_body"
    elif mutation == "target-kind": child["kind"] = "stationary_projectile"
    elif mutation == "placement": child["spawn"]["placement"] = "cursor"
    elif mutation == "aim": child["spawn"]["aim"] = "cursor"
    elif mutation == "offset": child["spawn"]["offsetPx"] = 1
    elif mutation == "over-target": child["spawn"]["overTarget"] = {"heightTiles": 2, "delayTicks": 0}
    elif mutation == "null": event["hitTargetSpawn"] = None
    elif mutation == "missing": event["hitTargetSpawn"].pop("beforeProbability")
    elif mutation == "foreign": event["hitTargetSpawn"]["speedMultiplier"] = 0.78
    else: event.update(action="chain_damage_on_event", actionCode=4)
    assert not validate_runtime_wire(wire)["ok"]


def test_retarget_repair_keeps_existing_child_design_frozen_and_compiles_new_complete_child():
    document, call = fixture()
    calls = document["runtimeProgram"]["calls"]
    child_id = call["params"]["entity"]
    child_calls = [deepcopy(row) for row in calls if row["target"] == child_id]
    old_spawn = next(row for row in calls if row["target"] == child_id and row["fn"] == "configure_spawn")
    old_spawn["params"]["aim"] = "cursor"  # Valid independent design, incompatible with this reference.
    calls.append({"id": "keep_original_child", "fn": "spawn_entity_on_event", "target": call["target"],
                  "params": {"when": "on_hit", "entity": child_id, "count": 1, "spreadRadians": 0,
                             "damageBasis": "authored_child", "knockbackBasis": "authored_child", "damageMultiplier": 1, "delayTicks": 0}})
    report = validate_runtime_program(document)
    assert [row["code"] for row in report["errors"]] == ["reference_requirements_unsatisfied"]
    scope = build_runtime_repair_scope(document, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.entity"]}]
    assert "spawn_over_target" not in scope["create"]["calls"]["allowedFns"]
    for row in child_calls:
        row["id"] = "replacement_" + row["id"]
        row["target"] = "replacement_child"
    repaired_call = deepcopy(call); repaired_call["params"].update(entity="replacement_child", count=12)
    hostile = deepcopy(old_spawn); hostile["params"]["aim"] = "velocity"
    patch, audit = filter_repair_patch_scope(document, {"note": "create explicitly compatible child",
        "entitiesUpsert": [{"id": "replacement_child", "kind": "child_projectile"}],
        "callsUpsert": [repaired_call, hostile, *child_calls]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, patch)
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == old_spawn["id"]) == old_spawn
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"]["count"] == 3
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("kind,field", [("RuntimeSpawnVelocitySpec", "HalfAngleRadians"), ("RuntimeHitTargetSpawnSpec", "BeforeProbability"), ("RuntimeHitTargetSpawnSpec", "InitialIgnoreCountdownUpdates")])
def test_numeric_range_audit_reads_real_nullable_setter_and_rejects_storage_mutations(kind, field):
    from infini_local.qa.primitive_loss_audit import nullable_number_rejection_bounds
    root = Path(__file__).resolve().parents[2]
    source = (root / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs").read_bytes()
    assert nullable_number_rejection_bounds(source, kind, field) is not None
    backing = b"_" + field[0].lower().encode() + field[1:].encode()
    # The actual setter must store the admitted value: no hidden normalization.
    mutated = source.replace(backing + b" = number;", backing + b" = 0;") if field != "HalfAngleRadians" else source.replace(backing + b" = angle;", backing + b" = 0;")
    assert nullable_number_rejection_bounds(mutated, kind, field) is None
