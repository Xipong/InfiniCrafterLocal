"""Retired opcode slots, scalar bags and receipt spellings are not read adapters."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def current_wire():
    source = build_capability_witness("move_straight")
    wire = compile_runtime_program(source)
    wire.pop("runtimeContract")
    body = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == source["runtimeProgram"]["primaryEntityId"])
    assert validate_runtime_wire(wire)["ok"]
    return wire, body


@pytest.mark.parametrize("code", range(1, 21))
def test_retired_movement_slots_are_refused_even_without_receipts(code):
    wire, body = current_wire()
    body["movement"] = {"name": "move_straight", "code": code, "params": {}}
    report = validate_runtime_wire(wire)
    assert any(row["code"] == "unsupported_opcode" and row["path"].endswith(".movement.code") for row in report["errors"])


@pytest.mark.parametrize("code", [1, 2])
def test_retired_controller_slots_are_not_neutral_placeholders(code):
    wire, body = current_wire()
    body["controller"] = {"name": "", "code": code, "params": {}}
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("code,name", [(3, "damage_area_on_event"), (4, "chain_damage_on_event")])
def test_retired_event_slots_cannot_borrow_old_names(code, name):
    wire, body = current_wire()
    body["events"] = [{"id": "old_event", "event": "on_hit", "actionCode": code, "action": name}]
    report = validate_runtime_wire(wire)
    assert any(row["code"] == "unsupported_opcode" and row["path"].endswith(".actionCode") for row in report["errors"])


@pytest.mark.parametrize("member,value", [("velocityRetention", {"multiplierPerUpdate": 1}), ("speedModifier", {"speedMultiplierPerUpdate": 1}), ("whipUsesOwnerGravity", True)])
def test_retired_components_are_unknown_even_when_neutral(member, value):
    wire, body = current_wire()
    body[member] = value
    assert any(row["code"] == "unknown_final_wire_field" and row["path"].endswith("." + member) for row in validate_runtime_wire(wire)["errors"])


@pytest.mark.parametrize("slot", ["movement", "controller"])
@pytest.mark.parametrize("params", [{}, {"rangeTiles": 0}])
def test_driver_params_have_no_historical_scalar_bag(slot, params):
    wire, body = current_wire()
    body[slot] = {"name": "move_straight" if slot == "movement" else "", "code": 0, "params": params}
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mutation", ["function", "parameter", "both"])
def test_predecessor_receipt_names_are_refused_without_source_or_mutation(mutation):
    source = build_capability_witness("generated_buff_on_use")
    call = next(row for row in source["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    call["params"]["manaRegen"] = 7
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]
    row = next(row for row in rows if row.get("callId") == "witness_call" and row.get("authoredPath", "").endswith(".params.manaRegen"))
    if mutation in {"function", "both"}:
        row["fn"] = "apply_generated_buff_on_use"
    if mutation in {"parameter", "both"}:
        row["authoredPath"] = row["authoredPath"].removesuffix("manaRegen") + "manaRegenBonusPoints"
    before = deepcopy(wire)
    assert not audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == before


@pytest.mark.parametrize("name", sorted(name for name, cap in CAPABILITY_REGISTRY.items() if cap.author_visible))
def test_every_current_authorable_primitive_has_current_proof_and_stripped_wire(name):
    source = build_capability_witness(name)
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
