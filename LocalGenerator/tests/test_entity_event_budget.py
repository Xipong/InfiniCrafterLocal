"""The Author, compiled wire and frozen Repair share the 16-event native bound."""
from copy import deepcopy

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import (
    build_runtime_repair_scope,
    filter_repair_patch_scope,
)
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def _event_fixture(count: int):
    doc = build_capability_witness("damage_nearby_on_event")
    calls = doc["runtimeProgram"]["calls"]
    original = next(c for c in calls if c["id"] == "witness_call")
    for i in range(1, count):
        extra = deepcopy(original)
        extra["id"] = f"extra_event_{i}"
        calls.append(extra)
    return doc


def test_author_sixteen_actions_compile_without_loss():
    doc = _event_fixture(16)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    target = next(c["target"] for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    events = next(row["events"] for row in wire["runtimeProgram"]["entities"] if row["id"] == target)
    assert len(events) == 16


def test_event_seventeen_is_rejected_early_and_frozen_repair_owns_only_overflow():
    doc = _event_fixture(17)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    overflow = [row for row in report["errors"] if row["code"] == "entity_event_budget"]
    assert len(overflow) == 1
    assert overflow[0]["path"].startswith("$.runtimeProgram.calls[")
    assert "extra_event_16" in overflow[0]["relatedIds"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["deletable"]["callIds"] == ["extra_event_16"]
    assert "witness_call" not in scope["mutable"]["callIds"]
    patch, audit = filter_repair_patch_scope(doc, {"callIdsDelete": ["extra_event_16", "witness_call"]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    assert patch["callIdsDelete"] == ["extra_event_16"]
    fixed = apply_repair_patch(doc, patch)
    assert validate_runtime_program(fixed)["ok"]
    assert doc == before


def test_compiled_wire_overflow_refused_even_without_author_or_receipts():
    wire = compile_runtime_program(_event_fixture(16))
    wire.pop("runtimeContract", None)
    entity = next(row for row in wire["runtimeProgram"]["entities"] if len(row["events"]) == 16)
    tail = deepcopy(entity["events"][-1])
    tail["id"] = "one_too_many"
    entity["events"].append(tail)
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(error["code"] == "entity_event_budget" for error in report["errors"])
