"""Component provenance authenticates registry-owned instances, not a controller bag."""
from copy import deepcopy
import re

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("fn", [
    "set_aim", "oscillate_velocity", "seek",
    "turn_velocity",
])
def test_component_receipts_admit_real_source_and_source_free_wire(fn):
    source = build_capability_witness(fn)
    before = deepcopy(source)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert report["ok"], report["violations"]
    assert validate_runtime_wire(wire)["ok"]
    assert source == before


@pytest.mark.parametrize("updates", [1, 6])
def test_contextual_neutral_receipts_use_the_same_entity_clock_and_inactive_branch(updates):
    source = build_capability_witness("move_straight")
    calls = source["runtimeProgram"]["calls"]
    collision = next(c for c in calls if c["fn"] == "projectile_collision")
    collision["params"]["updatesPerTick"] = updates
    call = {"id": "rotation", "fn": "rotate_sprite", "target": collision["target"],
            "params": {"mode": "velocity"}}
    calls.append(call)
    wire = compile_runtime_program(source)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    rotation_rows = [r for r in receipts if r.get("callId") == "rotation"]
    omitted = next(r for r in rotation_rows if r["finalPath"].endswith(".radiansPerUpdate"))
    assert omitted["status"] == "declared_neutral_omission"
    assert type(omitted["value"]) is float and omitted["value"] == 0
    for authored in (source, None):
        report = audit_compiler_receipts(receipts, authored_document=authored, final_document=wire)
        assert report["ok"], report["violations"]
    # Absence is a source claim, not a generic permission to relabel an explicit zero.
    explicit = deepcopy(source)
    explicit["runtimeProgram"]["calls"][-1]["params"]["radiansPerSecond"] = 0
    report = audit_compiler_receipts(receipts, authored_document=explicit, final_document=wire)
    assert not report["ok"]
    assert any("explicitly authored" in r["reason"] for r in report["violations"])
    # A saved zero does not prove the inactive branch once the selector is spin.
    changed = deepcopy(wire)
    entity = next(e for e in changed["runtimeProgram"]["entities"] if e["id"] == call["target"])
    entity["rotation"]["mode"] = "spin"
    rows = changed["runtimeContract"]["finalWireReceipts"]
    next(r for r in rows if r.get("callId") == "rotation" and r["finalPath"].endswith(".mode"))["value"] = "spin"
    report = audit_compiler_receipts(rows, final_document=changed)
    assert not report["ok"]
    assert any("inactive consumer branch" in r["reason"] for r in report["violations"])


def two_seek_document():
    source = build_capability_witness("move_straight")
    source["runtimeProgram"]["calls"].append({
        "id": "return_latch", "fn": "return_when",
        "target": source["runtimeProgram"]["primaryEntityId"], "params": {"afterSeconds": 1},
    })
    for phase in ("outbound", "returning"):
        source["runtimeProgram"]["calls"].append({
            "id": phase, "fn": "seek", "target": source["runtimeProgram"]["primaryEntityId"],
            "params": {"target": "owner_center", "maxSpeed": 30,
                       "lerpPerUpdate": 0.5, "limitSpeedToDistance": True,
                       "window": {"phase": phase}},
        })
    return source


@pytest.mark.parametrize("mutation", ["mixed_calls", "same_call_twice", "same_coordinate_twice", "mixed_coordinate", "foreign_fn", "missing_leaf", "duplicate_leaf"])
def test_seek_instance_rejects_equal_value_forged_owner_proofs(mutation):
    source = two_seek_document()
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    selected = [r for r in rows if r.get("fn") == "seek"]
    first = next(r for r in selected if r["callId"] == "outbound" and r["authoredPath"].endswith(".limitSpeedToDistance"))
    second = next(r for r in selected if r["callId"] == "returning" and r["authoredPath"].endswith(".limitSpeedToDistance"))
    if mutation == "mixed_calls":
        first["callId"], second["callId"] = second["callId"], first["callId"]
        first["authoredPath"], second["authoredPath"] = second["authoredPath"], first["authoredPath"]
    elif mutation in {"same_call_twice", "same_coordinate_twice"}:
        source_base = first["authoredPath"].split(".params.")[0]
        for row in selected:
            if row["callId"] == "returning":
                if mutation == "same_call_twice":
                    row["callId"] = "outbound"
                row["authoredPath"] = re.sub(r"runtimeProgram\.calls\[\d+\]", source_base, row["authoredPath"])
    elif mutation == "mixed_coordinate":
        first["authoredPath"] = second["authoredPath"]
    elif mutation == "foreign_fn":
        first["fn"] = "set_aim"
    elif mutation == "missing_leaf":
        rows.remove(first)
    else:
        rows.append(deepcopy(first))
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert not report["ok"], mutation
    assert not validate_runtime_wire(wire)["ok"]


def test_seek_instance_ownership_is_independent_of_wire_or_source_order():
    source = two_seek_document()
    reordered_source = deepcopy(source)
    reordered_source["runtimeProgram"]["calls"].reverse()
    for reordered in (source, reordered_source):
        wire = compile_runtime_program(reordered)
        receipts = wire["runtimeContract"]["finalWireReceipts"]
        for authored in (reordered, None):
            report = audit_compiler_receipts(receipts, authored_document=authored, final_document=wire)
            assert report["ok"], report["violations"]


def test_source_component_target_cannot_be_changed_by_consistent_wire_receipts():
    source = build_capability_witness("seek")
    wire = compile_runtime_program(source)
    source = deepcopy(source)
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "seek")
    call["target"] = next(e["id"] for e in source["runtimeProgram"]["entities"] if e["kind"] == "item_body")
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)
    assert not report["ok"]
    assert any("exact authored target" in r["reason"] for r in report["violations"])


def test_fixed_only_component_cannot_lose_its_whole_receipt_group():
    source = build_capability_witness("sustain_mana")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    rows[:] = [r for r in rows if r.get("fn") != "sustain_mana"]
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert not report["ok"], "the stored component still asserts fn-selected cadence"
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("bad", [None, True, -1, 6, "0"])
def test_contextual_neutral_proof_rejects_missing_or_untyped_wire_clock(bad):
    source = build_capability_witness("move_straight")
    source["runtimeProgram"]["calls"].append({
        "id": "rotation", "fn": "rotate_sprite",
        "target": source["runtimeProgram"]["primaryEntityId"], "params": {"mode": "velocity"},
    })
    wire = compile_runtime_program(source)
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == source["runtimeProgram"]["primaryEntityId"])
    entity["collision"]["extraUpdates"] = bad
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for row in rows:
        if row.get("fn") == "projectile_collision" and row["finalPath"].endswith(".extraUpdates"):
            row["value"] = bad
    report = audit_compiler_receipts(rows, final_document=wire)
    assert not report["ok"]
    assert any("exact declared neutral default/projection" in r["reason"] for r in report["violations"])


def test_contextual_neutral_rejects_a_null_source_call_without_crashing():
    source = build_capability_witness("move_straight")
    source["runtimeProgram"]["calls"].append({
        "id": "rotation", "fn": "rotate_sprite",
        "target": source["runtimeProgram"]["primaryEntityId"], "params": {"mode": "velocity"},
    })
    wire = compile_runtime_program(source)
    source["runtimeProgram"]["calls"][-1] = None
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                     authored_document=source, final_document=wire)
    assert not report["ok"]


@pytest.mark.parametrize("bad", [None, True, 1.5, -1, 256])
def test_component_scalar_cannot_admit_null_wrong_type_or_outside_domain_with_matching_receipt(bad):
    source = build_capability_witness("set_opacity")
    wire = compile_runtime_program(source)
    entity = next(e for e in wire["runtimeProgram"]["entities"] if "opacity" in e)
    entity["opacity"]["alpha"] = bad
    rows = wire["runtimeContract"]["finalWireReceipts"]
    next(r for r in rows if r.get("fn") == "set_opacity")["value"] = bad
    report = audit_compiler_receipts(rows, final_document=wire)
    assert not report["ok"]
    assert not validate_runtime_wire(wire)["ok"]
