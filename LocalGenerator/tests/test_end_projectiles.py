"""Remote termination is an input action over existing, independently produced entities."""
import json
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


def _call(document):
    return next(row for row in document["runtimeProgram"]["calls"] if row["id"] == "witness_call")


def _event(wire):
    return next(row for entity in wire["runtimeProgram"]["entities"] for row in entity["events"]
                if row["id"] == "witness_call")


def _check(document):
    original = deepcopy(document)
    report = validate_runtime_program(document)
    assert report["ok"], report
    wire = compile_runtime_program(document)
    assert document == original
    report = validate_runtime_wire(wire)
    assert report["ok"], report
    for source in (document, None):
        report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                        authored_document=source, final_document=wire)
        assert report["ok"], report
    delivered = json.loads(json.dumps(sanitize_recipe_for_delivery(wire)))
    assert "runtimeContract" not in delivered
    assert validate_runtime_wire(delivered)["ok"], validate_runtime_wire(delivered)
    return wire


def test_remote_input_preserves_entity_payload_delay_and_exact_provenance():
    document = build_capability_witness("end_projectiles")
    _call(document)["params"]["delay"] = 0.5
    document["runtimeProgram"]["calls"].append({
        "id": "terminal_payload", "fn": "damage_nearby_on_event", "target": "witness_entity",
        "params": {"when": "on_kill", "radius": 3, "maxTargets": 4, "damageMultiplier": 0.75},
    })
    wire = _check(document)
    expected = {"id": "witness_call", "action": "end_projectiles", "actionCode": 12,
                "event": "on_use", "useInput": "alternate_use", "entityId": "witness_entity", "delayTicks": 30}
    assert _event(wire) == expected
    payload = next(row for entity in wire["runtimeProgram"]["entities"] for row in entity["events"]
                   if row["id"] == "terminal_payload")
    assert payload["event"] == "on_kill" and payload["radiusPx"] == 48 and payload["damageMultiplier"] == 0.75
    reordered = deepcopy(document)
    reordered["runtimeProgram"]["calls"].reverse()
    assert _event(_check(reordered)) == expected


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_author_request_roundtrip_delivers_remote_action(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    from repair_test_helpers import provider_roundtrip

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = build_initial_author_request({}, {}, "remote projectile control", model_name="offline")
    document = build_capability_witness("end_projectiles")
    document = {key: document[key] for key in ("name", "category", "runtimeProgram")}
    parsed = provider_roundtrip(document, request["response_format"])
    assert _event(_check(parsed))["entityId"] == "witness_entity"


def test_unscoped_use_and_native_neutral_serialization_remain_readable():
    document = build_capability_witness("end_projectiles")
    _call(document)["params"].update(when="on_use", delay=10)
    wire = _check(document)
    wire.pop("runtimeContract")
    _event(wire).update(count=1, spreadRadians=0.0, damageMultiplier=1.0, periodTicks=0,
                        buffId=-1, durationTicks=0, radiusPx=0, rangeTiles=0.0, mode="", strength=0.0,
                        radiusTiles=0.0, damageFraction=0.0, maxHeal=0, cooldownTicks=0, safeTileOnly=True)
    assert _event(wire)["delayTicks"] == 600
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)


@pytest.mark.parametrize("mutation", ["missing_target", "item_target", "no_producer", "wrong_event", "wrong_source", "invalid_delay"])
def test_unexecutable_control_is_refused_without_changing_the_authored_program(mutation):
    document = build_capability_witness("end_projectiles")
    call = _call(document)
    if mutation == "missing_target":
        call["params"]["entity"] = "absent"
    elif mutation == "item_target":
        call["params"]["entity"] = "item"
    elif mutation == "no_producer":
        document["runtimeProgram"]["bindings"] = [row for row in document["runtimeProgram"]["bindings"]
                                                    if row["input"] == "alternate_use"]
    elif mutation == "wrong_event":
        call["params"]["when"] = "on_kill"
    elif mutation == "wrong_source":
        call["target"] = "witness_entity"
    else:
        call["params"]["delay"] = 10.1
    original = deepcopy(document)
    report = validate_runtime_program(document)
    assert not report["ok"]
    if mutation == "no_producer":
        assert any(row["code"] == "unreachable_entity" for row in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    assert document == original


@pytest.mark.parametrize("mutation", ["wrong_opcode", "wrong_name", "wrong_event", "missing_target", "item_target",
                                      "no_producer", "wrong_source", "delay_type", "delay_bounds", "foreign_damage"])
def test_delivery_without_receipts_still_refuses_invalid_remote_control(mutation):
    wire = compile_runtime_program(build_capability_witness("end_projectiles"))
    wire.pop("runtimeContract")
    event = _event(wire)
    if mutation == "wrong_opcode":
        event["actionCode"] = 1
    elif mutation == "wrong_name":
        event["action"] = "spawn_entity_on_event"
    elif mutation == "wrong_event":
        event["event"] = "on_kill"
        event.pop("useInput")
    elif mutation == "missing_target":
        del event["entityId"]
    elif mutation == "item_target":
        event["entityId"] = "item"
    elif mutation == "no_producer":
        wire["runtimeProgram"]["bindings"] = [row for row in wire["runtimeProgram"]["bindings"]
                                                if row["input"] == "alternate_use"]
    elif mutation == "wrong_source":
        body, projectile = wire["runtimeProgram"]["entities"]
        body["events"].remove(event)
        projectile["events"].append(event)
        event.pop("useInput")
    elif mutation == "delay_type":
        event["delayTicks"] = 0.5
    elif mutation == "delay_bounds":
        event["delayTicks"] = 601
    else:
        event["damageMultiplier"] = 2
    original = deepcopy(wire)
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == original


def test_end_reference_does_not_change_spawn_graph_or_consume_spawn_budget():
    document = build_capability_witness("spawn_on_event")
    _call(document)["id"] = "emit_child"
    document["runtimeProgram"]["bindings"].append({
        "id": "remote", "input": "alternate_use", "action": {"kind": "use_item_body"},
        "stackCost": 0, "contactDamage": False,
    })
    before = validate_runtime_program(document)["stats"]
    document["runtimeProgram"]["calls"].append({
        "id": "witness_call", "fn": "end_projectiles",
        "params": {"when": {"on": "on_use", "useInput": "alternate_use"}, "entity": "witness_child"},
    })
    after = validate_runtime_program(document)["stats"]
    assert (after["eventSpawnBudget"], after["spawnGraphDepth"]) == (before["eventSpawnBudget"], before["spawnGraphDepth"])
    assert _event(_check(document))["entityId"] == "witness_child"


def test_target_repair_preserves_accepted_input_delay_and_producer():
    document = build_capability_witness("end_projectiles")
    call = _call(document)
    call["params"].update(entity="absent", delay=0.5)
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    candidate = deepcopy(call)
    candidate["params"].update(entity="witness_entity", when="on_use", delay=1)
    filtered, audit = filter_repair_patch_scope(document, {"note": "correct reference", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    assert _call(repaired)["params"] == {**call["params"], "entity": "witness_entity"}
    _check(repaired)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_owner"])
def test_reference_receipts_cannot_be_removed_duplicated_or_reassigned(mutation):
    document = build_capability_witness("end_projectiles")
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipt = next(row for row in receipts if row.get("callId") == "witness_call" and row["finalPath"].endswith(".entityId"))
    if mutation == "missing":
        receipts.remove(receipt)
    elif mutation == "duplicate":
        receipts.append(deepcopy(receipt))
    else:
        receipt["callId"] = "base_motion"
    for source in (None, document):
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
