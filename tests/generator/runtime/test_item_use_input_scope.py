"""Explicit input scopes survive Author -> wire without changing event multiplicity."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def _document(scope="both"):
    doc = build_capability_witness("spawn_on_event")
    runtime = doc["runtimeProgram"]
    call = next(c for c in runtime["calls"] if c["id"] == "witness_call")
    call["target"] = "item"
    call["params"]["when"] = "on_use" if scope is None else {"on": "on_use", "useInput": scope}
    call["params"]["delay"] = 0.5
    alternate = deepcopy(runtime["bindings"][0])
    alternate.update(id="alternate", input="alternate_use")
    runtime["bindings"].append(alternate)
    return doc


def _event(wire):
    body = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "item")
    assert len(body["events"]) == 1  # both must not lower to duplicate event actions
    return body["events"][0]


@pytest.mark.parametrize("scope", ["primary_use", "alternate_use", "both", None])
def test_use_event_scope_projects_once_with_exact_provenance(scope):
    doc = _document(scope)
    wire = compile_runtime_program(doc)
    event = _event(wire)
    assert event["event"] == "on_use"
    assert event["delayTicks"] == 30
    assert event.get("useInput") == scope
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=wire)["ok"]
    scoped = [r for r in receipts if r["finalPath"].endswith(".useInput")]
    assert len(scoped) == (scope is not None)
    if scoped:
        assert scoped[0]["authoredPath"].endswith(".params.when.useInput")
        assert scoped[0]["value"] == scope
        event["useInput"] = "primary_use" if scope != "primary_use" else "alternate_use"
        assert not audit_compiler_receipts(receipts, authored_document=doc, final_document=wire)["ok"]


@pytest.mark.parametrize("scope", ["primary_use", "alternate_use", "both", None])
def test_mana_scope_and_legacy_default_keep_declared_receipts(scope):
    doc = _document()
    stats = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "item_stats")
    stats["params"]["manaCost"] = 17
    if scope is not None:
        stats["params"]["manaCostInput"] = scope
    wire = compile_runtime_program(doc)
    assert wire["gameplay"]["manaCost"] == 17
    assert wire["gameplay"]["manaCostInput"] == (scope or "both")
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipt, = [r for r in receipts if r["finalPath"] == "gameplay.manaCostInput"]
    assert receipt["status"] == ("delivered" if scope else "declared_neutral_omission")
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("when", [
    {"on": "on_use", "useInput": "hold"},
    {"on": "on_use"},
    {"on": "on_hit", "useInput": "primary_use"},
    {"on": "on_use", "useInput": None},
])
def test_malformed_input_scope_never_becomes_both(when):
    doc = _document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")["params"]["when"] = when
    assert not validate_runtime_program(doc)["ok"]


def test_scoped_use_event_cannot_be_attached_to_projectile():
    doc = _document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")["target"] = "witness_entity"
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("mutation", ["invalid_event_scope", "wrong_event", "wrong_owner", "invalid_mana_scope"])
def test_delivered_wire_rejects_scopes_outside_contract_without_receipts(mutation):
    wire = compile_runtime_program(_document())
    wire.pop("runtimeContract")
    event = _event(wire)
    if mutation == "invalid_event_scope":
        event["useInput"] = "all"
    elif mutation == "wrong_event":
        event["event"] = "on_hit"
    elif mutation == "wrong_owner":
        body = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "item")
        projectile = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "witness_entity")
        projectile["events"] = body.pop("events")
    else:
        wire["gameplay"]["manaCostInput"] = None
    result = validate_runtime_wire(wire)
    assert not result["ok"]
    assert any(e["code"] == "invalid_use_input_scope" for e in result["errors"])


def test_scoped_event_requires_its_selected_input_but_both_accepts_either():
    doc = _document("alternate_use")
    doc["runtimeProgram"]["bindings"].pop()
    assert not validate_runtime_program(doc)["ok"]
    next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")["params"]["when"]["useInput"] = "both"
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    _event(wire)["useInput"] = "alternate_use"
    assert any(e["code"] == "event_not_produced" for e in validate_runtime_wire(wire)["errors"])
