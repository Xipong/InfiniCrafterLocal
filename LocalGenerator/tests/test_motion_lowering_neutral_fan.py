"""Exact count-one fan omission is not an inferred attack or a blanket zero rule."""
from copy import deepcopy
import re
from typing import Any
import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("fn", ["spawn_on_event", "spawn"])
def test_count_one_fan_omission_is_exact_zero_with_its_own_proof(fn):
    source = build_capability_witness(fn)
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"].update(count=1, spreadRadians=0)
    explicit_wire = compile_runtime_program(source)
    del call["params"]["spreadRadians"]
    frozen = deepcopy(source)
    assert validate_runtime_program(source)["ok"], "count=1 uniquely deactivates the fan"
    wire = compile_runtime_program(source)
    assert source == frozen
    assert wire["runtimeProgram"] == explicit_wire["runtimeProgram"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    omitted = [r for r in rows if r.get("fn") == fn and r["authoredPath"].endswith(".params.spreadRadians")
               and r["callId"] == call["id"]]
    assert len(omitted) == 1 and omitted[0]["status"] == "declared_neutral_omission"
    assert type(omitted[0]["value"]) is int and omitted[0]["value"] == 0
    for authored in (source, None):
        assert audit_compiler_receipts(rows, authored_document=authored, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]
    for count in (2, True):
        changed = deepcopy(wire)
        proof = changed["runtimeContract"]["finalWireReceipts"]
        spread = next(r for r in proof if r.get("fn") == fn and r["callId"] == call["id"]
                      and r["authoredPath"].endswith(".params.spreadRadians"))
        owner_path = spread["finalPath"].rsplit(".", 1)[0]
        count_proof = next(r for r in proof if r.get("fn") == fn and r["callId"] == call["id"]
                           and r["finalPath"] == owner_path + ".count")
        owner: Any = changed
        for key in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\d+", owner_path):
            owner = owner[int(key)] if isinstance(owner, list) else owner[key]
        owner["count"] = count_proof["value"] = count
        report = audit_compiler_receipts(proof, final_document=changed)
        assert not report["ok"]
        assert any("outside its declared inactive consumer branch" in r["reason"] for r in report["violations"]), report


@pytest.mark.parametrize("fn", ["spawn_on_event", "spawn"])
def test_multi_spawn_fan_omission_stays_red_and_explicit_nonzero_is_not_rewritten(fn):
    source = build_capability_witness(fn)
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"].update(count=2)
    call["params"].pop("spreadRadians", None)
    assert not validate_runtime_program(source)["ok"]
    call["params"].update(count=1, spreadRadians=0.5)
    wire = compile_runtime_program(source)
    values = [r["value"] for r in wire["runtimeContract"]["finalWireReceipts"]
              if r.get("fn") == fn and r["callId"] == call["id"] and r["authoredPath"].endswith(".params.spreadRadians")]
    assert values == [0.5]
    assert call["params"]["spreadRadians"] == 0.5


def test_hit_target_spawn_does_not_acquire_another_event_capabilitys_neutral_receipt():
    source = build_capability_witness("spawn_at_hit")
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"]
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)
    assert report["ok"], report
