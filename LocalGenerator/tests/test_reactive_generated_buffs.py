"""Equipment reactions select accepted utility groups without inventing use bindings."""
from copy import deepcopy
import json

import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.qa.capability_witnesses import build_capability_witness


def document(event="on_hurt"):
    doc = build_capability_witness("generated_buff_on_event")
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "generated_buff_on_event")["params"]["when"]["on"] = event
    return doc


@pytest.mark.parametrize("event", ["on_hurt", "on_enemy_kill"])
def test_reaction_buff_compiles_exact_group_reference_and_existing_effects(event):
    doc = document(event); before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert doc == before
    assert validate_runtime_wire(wire)["ok"]
    assert {b["usePolicy"]["action"]["kind"] for b in wire["runtimeProgram"]["bindings"]} == {"equip_passive"}
    assert len(wire["runtimeProgram"]["entities"]) == 1
    action = wire["runtimeProgram"]["entities"][0]["events"][0]
    assert action == {"id": "witness_call", "action": "apply_generated_buff_on_event", "actionCode": 9,
                      "event": event, "reactionCooldownTicks": 60, "effectGroupId": "reaction_buff"}
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=wire)["ok"]
    reference = next(r for r in receipts if r.get("callId") == "witness_call" and r.get("finalPath", "").endswith(".effectGroupId"))
    assert reference["authoredPath"].endswith(".params.effectGroupId")
    action["effectGroupId"] = "invented"
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("extra", ["restore_resources_on_use", "native_buff_on_use", "blink_on_use"])
def test_reaction_group_cannot_smuggle_instant_healing_or_other_actions(extra):
    doc = document()
    effect = deepcopy(next(c for c in build_capability_witness(extra)["runtimeProgram"]["calls"] if c["fn"] == extra))
    effect["id"] = "unrelated_effect"; effect["params"]["effectGroupId"] = "reaction_buff"
    doc["runtimeProgram"]["calls"].append(effect)
    assert "invalid_reaction_effect_group" in {e["code"] for e in validate_runtime_program(doc)["errors"]}


def test_reaction_requires_equipment_and_strict_event_cooldown():
    for trigger in ["on_hurt", {"on": "on_hurt", "cooldown": 0}, {"on": "on_hit", "cooldown": 1}]:
        doc = document()
        doc["runtimeProgram"]["calls"][-1]["params"]["when"] = trigger
        assert not validate_runtime_program(doc)["ok"]
    doc = document(); doc["runtimeProgram"]["bindings"] = []
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("mutation", ["missing_group", "wrong_group_type", "wrong_opcode", "wrong_event", "no_cooldown", "foreign_field", "no_equipment"])
def test_stripped_wire_keeps_reaction_admission_without_provenance(mutation):
    wire = compile_runtime_program(document()); wire.pop("runtimeContract")
    action = wire["runtimeProgram"]["entities"][0]["events"][0]
    if mutation == "missing_group": action.pop("effectGroupId")
    elif mutation == "wrong_group_type": action["effectGroupId"] = []
    elif mutation == "wrong_opcode": action["actionCode"] = 3
    elif mutation == "wrong_event": action["event"] = "on_hit"
    elif mutation == "no_cooldown": action.pop("reactionCooldownTicks")
    elif mutation == "foreign_field": action["damageFraction"] = 0.5
    elif mutation == "no_equipment": wire["runtimeProgram"]["bindings"] = []
    assert not validate_runtime_wire(wire)["ok"]


def test_repair_changes_only_broken_selector_and_freezes_buff_definition():
    doc = document(); doc["runtimeProgram"]["calls"][-1]["params"]["effectGroupId"] = "missing"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    corrected = deepcopy(doc["runtimeProgram"]["calls"][-1]); corrected["params"]["effectGroupId"] = "reaction_buff"
    before = deepcopy(doc["runtimeProgram"]["calls"][:-1])
    filtered, audit = filter_repair_patch_scope(doc, {"note": "Exact group reference", "callsUpsert": [corrected]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert repaired["runtimeProgram"]["calls"][:-1] == before
    assert validate_runtime_program(repaired)["ok"], validate_runtime_program(repaired)


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_actual_author_and_repair_packets_expose_complete_reaction_contract(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.pipelines.author import request as author
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = author.build_initial_author_request({}, {}, "reactive-buff", model_name="offline")
    cards = json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]
    card = next(c for c in cards if c["fn"] == "generated_buff_on_event")
    assert set(card["params"]) == {"when", "effectGroupId", "delay"}
    doc = document(); doc["runtimeProgram"]["calls"][-1]["params"]["effectGroupId"] = "missing"
    dossier = author.build_gameplay_repair_dossier(doc, {}, {}, failure_report=validate_runtime_program(doc))
    broken = next(c for c in dossier["existingBrokenCapabilityCards"] if c["fn"] == "generated_buff_on_event")
    assert set(broken["params"]) == set(card["params"])
    assert broken["params"]["when"]["shape"]["properties"]["on"]["enum"] == ["on_hurt", "on_enemy_kill"]
    assert broken["params"]["effectGroupId"]["pattern"] == card["params"]["effectGroupId"]["pattern"]
    assert broken["params"]["effectGroupId"]["required"] is True
    assert request["messages"]  # Built offline at the actual request sender, no provider/auth call.
