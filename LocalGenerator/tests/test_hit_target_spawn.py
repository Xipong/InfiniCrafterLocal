"""Production Author -> provider -> compiler/wire and frozen Repair for A11."""
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines.author import item_contract as contract
from infini_local.qa.capability_witnesses import build_capability_witness
from test_codex_subscription_contract import _encode_nullable_fixture
from test_runtime_spawn_distributions import VELOCITIES
from repair_test_helpers import gameplay_repair


FN = "spawn_at_hit"


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
    call["params"].update(when="on_crit", damageBasis="live_parent", delay=(11) / 60)
    spawn = next(row for row in document["runtimeProgram"]["calls"]
                 if row["fn"] == "spawn" and row["target"] == call["params"]["entity"])
    spawn["params"]["velocity"] = deepcopy(velocity)
    local, provider = contract.author_item_response_schema(), contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(document, local)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_author_item_to_local(encoded, response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == document and validate_runtime_program(restored)["ok"]
    wire = compile_runtime_program(restored)
    event = event_wire(wire, call)
    assert event["id"] == call["id"] and event["action"] == "spawn_entity_on_event" and event["actionCode"] == 1
    assert event["hitTargetSpawn"] == {row.wire_path.removeprefix("hitTargetSpawn."): row.value for row in CAPABILITY_REGISTRY[FN].params["geometry"].projected_fields(call["params"]["geometry"], "geometry") if row.wire_path.startswith("hitTargetSpawn.")} and event["spreadRadians"] == 0
    assert "geometry" not in event
    assert validate_runtime_wire(wire)["ok"]
    for source in (None, restored):
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("name,value", [
    ("beforeProbability", -0.01), ("beforeProbability", 1.01), ("beforeProbability", True),
    ("hitboxMaxSideFactor", 2.01), ("clearanceBlocks", -1 / 16), ("beforeJitterRadius", 129 / 16),
    ("beforeAngleJitter", 3.15), ("afterFanSpread", 6.3),
    ("ignoreTargetUpdates", -1), ("ignoreTargetUpdates", 601),
    ("ignoreTargetUpdates", 1.0), ("ignoreTargetUpdates", None),
])
def test_geometry_rejects_invalid_values_in_author_and_wire_without_diagnostic_receipts(name, value):
    document, call = fixture()
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    call["params"]["geometry"][name] = value
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)
    spec = CAPABILITY_REGISTRY[FN].params["geometry"].properties[name]
    event_wire(wire, call)["hitTargetSpawn"][spec.wire_name.rsplit(".", 1)[-1]] = spec.to_wire(value) if type(value) in (int, float) else value
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
    call["params"]["geometry"].update(clearanceBlocks=(0) / 16, beforeJitterRadius=(0) / 16)
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    geometry = [row for row in receipts if row.get("fn") == FN and ".params.geometry" in row.get("authoredPath", "")]
    leaf = next(row for row in geometry if row["finalPath"].endswith(".clearancePx"))
    if mutation == "drop": receipts.remove(leaf)
    elif mutation == "duplicate": receipts.append(deepcopy(leaf))
    elif mutation == "old-fn": leaf["fn"] = "spawn_on_event"
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


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("hostile_edit", [False, True])
def test_sole_hit_reference_repairs_only_conflicting_child_spawn_leaves(monkeypatch, mode, hostile_edit):
    document, call = fixture()
    child_id = call["params"]["entity"]
    spawn = next(row for row in document["runtimeProgram"]["calls"]
                 if row.get("target") == child_id and row["fn"] == "spawn")
    expected = deepcopy(document)
    # Holy Storm's rejected composition: exact hit geometry plus a second
    # independently positioned/facing child. Replacing its only edge orphans it.
    spawn["params"].update(aim="facing", position={"above": "activation_origin", "heightTiles": 12,
                                                  'activationDelay': (0) / 60})
    before = deepcopy(document)
    errors = validate_runtime_program(document)["errors"]
    assert [row["code"] for row in errors] == ["reference_requirements_unsatisfied"]
    candidate = deepcopy(spawn)
    candidate["params"].update(aim="velocity", position={"at": "activation_origin"})
    incoming = [candidate]
    if hostile_edit:
        candidate["params"]["velocity"] = {'speed': (49) * 60 / 16}
        hostile = deepcopy(next(row for row in document["runtimeProgram"]["calls"]
                                if row.get("target") == child_id and row["fn"] == "projectile_damage"))
        hostile["params"]["damage"] = 999
        incoming.append(hostile)
    repaired, dossier = gameplay_repair(monkeypatch, document, {
        "note": "explicit correction of the sole child's exact reference dependency",
        "callsUpsert": incoming, "realizationReplacement": document["realization"],
    }, mode, out_of_scope_response=hostile_edit)
    scope = dossier["repairScope"]
    assert next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == spawn["id"])["paths"] == [
        "params.aim", "params.position"]
    assert not scope["create"]["entities"]["allowed"]
    assert not scope["create"]["calls"]["allowed"]
    assert repaired["runtimeProgram"] == expected["runtimeProgram"]
    assert bool(repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]) is hostile_edit
    assert validate_runtime_program(repaired)["ok"]
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                   authored_document=repaired, final_document=wire)["ok"]
    assert document == before


@pytest.mark.parametrize("consumer", ["second_reference", "binding", "primary"])
def test_independently_used_child_keeps_spawn_frozen(consumer):
    document, call = fixture()
    child_id = call["params"]["entity"]
    child = next(row for row in document["runtimeProgram"]["entities"] if row["id"] == child_id)
    spawn = next(row for row in document["runtimeProgram"]["calls"]
                 if row.get("target") == child_id and row["fn"] == "spawn")
    spawn["params"]["aim"] = "cursor"
    if consumer == "second_reference":
        document["runtimeProgram"]["calls"].append({
            "id": "independent_spawn", "target": call["target"], "fn": "spawn_on_event",
            "params": {"when": "on_hit", "entity": child_id, "count": 1, "spreadRadians": 0,
                       "damageBasis": "authored_child", "knockbackBasis": "authored_child",
                       "damageMultiplier": 1, 'delay': (0) / 60},
        })
    elif consumer == "binding":
        child["kind"] = "free_projectile"
        document["runtimeProgram"]["bindings"].append({
            "id": "independent_use", "input": "alternate_use", "action": {"kind": "spawn_entity", "targetId": child_id},
            "stackCost": 0, "contactDamage": False,
        })
    else:
        document["runtimeProgram"]["primaryEntityId"] = child_id
    before = deepcopy(document)
    report = validate_runtime_program(document)
    assert any(row["code"] == "reference_requirements_unsatisfied" for row in report["errors"])
    scope = build_runtime_repair_scope(document, report["errors"])
    assert spawn["id"] not in scope["mutable"]["callIds"]
    assert all(row["id"] != spawn["id"] for row in scope["fieldPermissions"]["calls"])
    assert scope["create"]["entities"]["allowed"]
    assert document == before


def test_sole_reference_noop_cannot_be_accepted_or_create_a_default():
    document, call = fixture()
    child_id = call["params"]["entity"]
    spawn = next(row for row in document["runtimeProgram"]["calls"]
                 if row.get("target") == child_id and row["fn"] == "spawn")
    spawn["params"]["aim"] = "cursor"
    before = deepcopy(document)
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    filtered, audit = filter_repair_patch_scope(document, {"note": "no correction"}, scope)
    assert not audit["ok"]
    assert not validate_runtime_program(apply_repair_patch(document, filtered))["ok"]
    assert document == before


def test_retarget_repair_keeps_existing_child_design_frozen_and_compiles_new_complete_child():
    document, call = fixture()
    calls = document["runtimeProgram"]["calls"]
    child_id = call["params"]["entity"]
    child_calls = [deepcopy(row) for row in calls if row.get("target") == child_id]
    old_spawn = next(row for row in calls if row.get("target") == child_id and row["fn"] == "spawn")
    old_spawn["params"]["aim"] = "cursor"  # Valid independent design, incompatible with this reference.
    calls.append({"id": "keep_original_child", "fn": "spawn_on_event", "target": call["target"],
                  "params": {"when": "on_hit", "entity": child_id, "count": 1, "spreadRadians": 0,
                             "damageBasis": "authored_child", "knockbackBasis": "authored_child", "damageMultiplier": 1, 'delay': (0) / 60}})
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
