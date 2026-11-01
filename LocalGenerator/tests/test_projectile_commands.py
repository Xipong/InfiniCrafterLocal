"""Owned-projectile commands preserve explicit targeting and terminal composition."""
import json
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


def command(doc):
    return next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "end_projectiles")


def event(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e["kind"] == "item_body")["events"][0]


def check(doc):
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert doc == before
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)["errors"]
    for source in (doc, None):
        report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                        authored_document=source, final_document=wire)
        assert report["ok"], report["violations"]
    stripped = json.loads(json.dumps(sanitize_recipe_for_delivery(wire)))
    assert "runtimeContract" not in stripped
    assert validate_runtime_wire(stripped)["ok"], validate_runtime_wire(stripped)["errors"]
    return wire


@pytest.mark.parametrize("scope", ["primary_use", "alternate_use", "both", None])
def test_command_scope_roundtrips_once_without_authoring_a_spawn_or_explosion(scope):
    doc = build_capability_witness("end_projectiles")
    command(doc)["params"]["when"] = "on_use" if scope is None else {"on": "on_use", "useInput": scope}
    wire = check(doc)
    expected = {"id": "witness_call", "action": "end_projectiles", "actionCode": 12,
                "event": "on_use", "entityId": "witness_entity", "delayTicks": 0}
    if scope is not None:
        expected["useInput"] = scope
    assert event(wire) == expected
    alternate = next(b for b in wire["runtimeProgram"]["bindings"] if b["input"] == "alternate_use")
    assert alternate["usePolicy"]["action"] == {"kind": "use_item_body", "targetId": "item"}
    assert alternate["usePolicy"]["contactDamage"] is False
    projectile = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "witness_entity")
    assert [(e["event"], e["action"]) for e in projectile["events"]] == [("on_kill", "damage_nearby_on_event")]
    doc["runtimeProgram"]["calls"] = [c for c in doc["runtimeProgram"]["calls"] if c["id"] != "terminal_blast"]
    assert event(check(doc)) == expected  # The command does not require or invent a terminal effect.


@pytest.mark.parametrize("edits", [
    {"entity": "missing"}, {"entity": "item"}, {"entity": None},
    {"when": "on_kill"}, {"when": {"on": "on_use", "useInput": "hold"}},
    {"delay": 0}, {"count": 1}, {"range": 10},
])
def test_invalid_author_selection_or_unowned_parameters_are_refused(edits):
    doc = build_capability_witness("end_projectiles")
    command(doc)["params"].update(edits)
    before = deepcopy(doc)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert doc == before


def test_command_reference_never_makes_an_unspawned_entity_reachable():
    doc = build_capability_witness("end_projectiles")
    doc["runtimeProgram"]["bindings"] = [b for b in doc["runtimeProgram"]["bindings"] if b["input"] == "alternate_use"]
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(e["code"] == "unreachable_entity" for e in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


def test_command_can_select_a_child_reached_by_an_existing_event_spawn():
    doc = build_capability_witness("spawn_on_event")
    doc["runtimeProgram"]["bindings"].append({"id": "command", "input": "alternate_use",
        "action": {"kind": "use_item_body"}, "stackCost": 0, "contactDamage": False})
    doc["runtimeProgram"]["calls"].append({"id": "end_child", "fn": "end_projectiles", "params": {
        "when": {"on": "on_use", "useInput": "alternate_use"}, "entity": "witness_child"}})
    wire = check(doc)
    assert event(wire)["entityId"] == "witness_child"


@pytest.mark.parametrize("mutation", ["missing_entity", "item_reference", "unreachable", "disabled_spawn",
    "projectile_source", "wrong_event", "wrong_action", "wrong_opcode", "delay", "other_action_field"])
def test_delivery_without_receipts_still_refuses_wrong_command_semantics(mutation):
    wire = compile_runtime_program(build_capability_witness("end_projectiles"))
    wire.pop("runtimeContract")
    e = event(wire)
    projectile = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == "witness_entity")
    if mutation == "missing_entity":
        e.pop("entityId")
    elif mutation == "item_reference":
        e["entityId"] = "item"
    elif mutation == "unreachable":
        wire["runtimeProgram"]["bindings"] = [b for b in wire["runtimeProgram"]["bindings"] if b["input"] == "alternate_use"]
    elif mutation == "disabled_spawn":
        projectile["spawn"]["enabled"] = False
    elif mutation == "projectile_source":
        next(row for row in wire["runtimeProgram"]["entities"] if row["kind"] == "item_body")["events"].remove(e)
        projectile["events"].append(e)
    else:
        key, value = {"wrong_event": ("event", "on_kill"), "wrong_action": ("action", "spawn_entity_on_event"),
                      "wrong_opcode": ("actionCode", 1), "delay": ("delayTicks", 1),
                      "other_action_field": ("count", 2)}[mutation]
        e[key] = value
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == before


def test_reference_repair_cannot_change_command_input_or_valid_terminal_effect():
    doc = build_capability_witness("end_projectiles")
    command(doc)["params"]["entity"] = "missing"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    candidate = deepcopy(command(doc))
    candidate["params"].update(entity="witness_entity", when="on_use")
    filtered, audit = filter_repair_patch_scope(doc, {"note": "repair only the entity reference", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    expected = deepcopy(doc)
    command(expected)["params"]["entity"] = "witness_entity"
    assert repaired == expected
    check(repaired)


def test_command_receipts_reject_duplicate_or_forged_reference():
    wire = check(build_capability_witness("end_projectiles"))
    receipt = next(r for r in wire["runtimeContract"]["finalWireReceipts"]
                   if r.get("fn") == "end_projectiles" and r["finalPath"].endswith(".entityId"))
    for duplicate in (True, False):
        mutated = deepcopy(wire)
        rows = mutated["runtimeContract"]["finalWireReceipts"]
        if duplicate:
            rows.append(deepcopy(receipt))
        else:
            next(r for r in rows if r == receipt)["authoredPath"] = receipt["authoredPath"].replace(".entity", ".when")
        assert not audit_compiler_receipts(rows, final_document=mutated)["ok"]


def test_actual_provider_packet_offers_only_the_two_authored_command_parameters(monkeypatch):
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier
    from test_source_unit_guidance import _serialized_chat_request

    monkeypatch.setattr("infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE", "json_schema")
    request, _, _ = build_initial_author_request({}, {}, "owned-command", model_name="offline-test")
    packet = _serialized_chat_request(monkeypatch, request)
    variants = packet["response_format"]["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
    schema, = [row for row in variants if row["properties"]["fn"]["const"] == "end_projectiles"]
    assert set(schema["properties"]["params"]["properties"]) == {"when", "entity"}
    assert set(schema["properties"]["params"]["required"]) == {"when", "entity"}
    cards = request_dossier(packet, declaration=request)["runtimeCapabilityContract"]["catalog"]["capabilities"]
    card, = [row for row in cards if row["fn"] == "end_projectiles"]
    assert card["params"]["entity"]["reference"] == CAPABILITY_REGISTRY["end_projectiles"].params["entity"].reference.card()
    assert card["params"]["entity"]["reference"]["graphEdge"] is False
