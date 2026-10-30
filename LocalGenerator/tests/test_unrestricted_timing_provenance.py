"""Conditional neutral windows retain exact leaf provenance and strict wire proof."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY, PROJECTILE_MODIFIER_COMPONENTS,
)
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import (
    _completed_params, audit_compiler_receipts, declared_neutral_omissions,
)
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def unrestricted_source(fn="homing"):
    source = build_capability_witness(fn)
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == fn)
    for name in ("window", "startDelay", "duration"):
        call["params"].pop(name, None)
    return source, call


def test_root_neutral_window_is_a_flat_leaf_receipt_and_exact_private_completion():
    source, call = unrestricted_source()
    params = call["params"]
    before = deepcopy(source)
    assert declared_neutral_omissions(call["fn"], params) == {"window.phase": "always"}
    completed = _completed_params(call["fn"], params)
    assert completed == {**params, "window": {"phase": "always"}}
    assert source == before
    completed["window"]["phase"] = "outbound"
    assert CAPABILITY_REGISTRY[call["fn"]].params["window"].default == {"phase": "always"}


@pytest.mark.parametrize("timing", [
    {"startDelay": 0, "duration": 1},
    {"startDelay": 0}, {"duration": 1},
    {"window": {"phase": "always"}}, {"window": None},
])
def test_timing_presence_does_not_authorize_unrestricted_completion(timing):
    _, call = unrestricted_source()
    params = {**call["params"], **timing}
    assert declared_neutral_omissions(call["fn"], params) == {}
    assert _completed_params(call["fn"], params) == params


@pytest.mark.parametrize("fn", [
    "homing", "turn_velocity",
    "attract_npcs",
])
def test_unrestricted_compilation_is_explicit_always_wire_with_one_omitted_phase(fn):
    source, call = unrestricted_source(fn)
    before = deepcopy(source)
    explicit = deepcopy(source)
    next(c for c in explicit["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]["window"] = {"phase": "always"}
    delivered = compile_runtime_program(explicit)
    wire = compile_runtime_program(source)
    assert source == before
    assert wire["runtimeProgram"] == delivered["runtimeProgram"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    phase = [r for r in rows if r.get("callId") == call["id"] and r["authoredPath"].endswith(".window.phase")]
    assert len(phase) == 1
    assert phase[0]["status"] == "declared_neutral_omission" and phase[0]["value"] == "always"
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert report["ok"], report["violations"]
    assert validate_runtime_wire(wire)["ok"]


def test_audit_authenticates_root_union_default_from_absent_source_and_saved_wire():
    source, call = unrestricted_source()
    explicit = deepcopy(source)
    next(c for c in explicit["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]["window"] = {"phase": "always"}
    wire = compile_runtime_program(explicit)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    phase = next(r for r in rows if r.get("callId") == call["id"] and r["authoredPath"].endswith(".window.phase"))
    phase["status"] = "declared_neutral_omission"
    before = deepcopy((source, wire))
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert report["ok"], report["violations"]
    assert (source, wire) == before


def omitted_phase(wire, call):
    return next(r for r in wire["runtimeContract"]["finalWireReceipts"]
                if r.get("callId") == call["id"] and r["authoredPath"].endswith(".window.phase"))


@pytest.mark.parametrize("attack", [
    "missing", "duplicate", "delivered", "root_path", "foreign_fn", "foreign_target",
    "wrong_phase", "wrong_type", "unknown_wire_leaf", "missing_wire_window",
])
def test_forged_or_incomplete_window_proof_is_rejected_without_mutation(attack):
    source, call = unrestricted_source()
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    phase = omitted_phase(wire, call)
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    component = entity[PROJECTILE_MODIFIER_COMPONENTS[call["fn"]]]
    if attack == "missing":
        rows.remove(phase)
    elif attack == "duplicate":
        rows.append(deepcopy(phase))
    elif attack == "delivered":
        phase["status"] = "delivered"
    elif attack == "root_path":
        phase["authoredPath"] = phase["authoredPath"].removesuffix(".phase")
    elif attack == "foreign_fn":
        phase["fn"] = "turn_velocity"
    elif attack == "foreign_target":
        other = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] != call["target"])
        index = wire["runtimeProgram"]["entities"].index(other)
        phase["finalPath"] = f"runtimeProgram.entities[{index}].homingModifier.window.phase"
        other["homingModifier"] = deepcopy(component)
    elif attack in {"wrong_phase", "wrong_type"}:
        phase["value"] = component["window"]["phase"] = "outbound" if attack == "wrong_phase" else True
    elif attack == "unknown_wire_leaf":
        component["window"]["forged"] = 1
    else:
        del component["window"]
    before = deepcopy((source, wire))
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        # Source-free saved evidence cannot distinguish explicit always from
        # omitted always; it must still reject every inconsistent wire claim.
        if attack == "delivered" and authored is None:
            assert report["ok"], report["violations"]
        else:
            assert not report["ok"], attack
    if attack != "delivered":
        assert not validate_runtime_wire(wire)["ok"], attack
    assert (source, wire) == before


@pytest.mark.parametrize("scalar_fields", [
    {"startDelayTicks": 0}, {"durationTicks": 60},
    {"startDelayTicks": 0, "durationTicks": 60},
    {"startDelayTicks": None, "durationTicks": 60},
])
def test_saved_omission_scope_uses_delivered_siblings_even_without_their_receipts(scalar_fields):
    source, call = unrestricted_source()
    wire = compile_runtime_program(source)
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    entity[PROJECTILE_MODIFIER_COMPONENTS[call["fn"]]].update(scalar_fields)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    report = audit_compiler_receipts(rows, final_document=wire)
    assert not report["ok"]
    assert any("structured" in r["reason"] for r in report["violations"]), report["violations"]


@pytest.mark.parametrize("timing", [
    {"window": {"phase": "always"}},
    {"startDelay": 0, "duration": 1},
    {"startDelay": None, "duration": 1},
])
def test_omission_receipt_cannot_relabel_present_author_timing(timing):
    source, call = unrestricted_source()
    wire = compile_runtime_program(source)
    call["params"].update(timing)
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)
    assert not report["ok"]


@pytest.mark.parametrize("fn", [
    "turn_velocity", "homing", "attract_npcs",
])
def test_full_pair_preserves_absent_window_and_delivered_receipt_presence(fn):
    source = build_capability_witness(fn)
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"].pop("window", None)
    call["params"].update(startDelay=0.5, duration=1)
    before = deepcopy(source)
    wire = compile_runtime_program(source)
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    component = entity[PROJECTILE_MODIFIER_COMPONENTS[fn]]
    assert "window" not in component
    assert component["startDelayTicks"] == 30 and component["durationTicks"] == 60
    rows = wire["runtimeContract"]["finalWireReceipts"]
    own = [r for r in rows if r.get("callId") == call["id"]]
    assert not any(".window" in r["authoredPath"] for r in own)
    assert all(r["status"] == "delivered" for r in own)
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert report["ok"], report["violations"]
    assert source == before


def test_root_omission_cannot_be_spliced_into_an_explicit_timed_window():
    source, call = unrestricted_source()
    call["params"]["window"] = {
        "phase": "always", "clock": "active", "startDelay": 0, "duration": 1,
    }
    wire = compile_runtime_program(source)
    omitted_phase(wire, call)["status"] = "declared_neutral_omission"
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert not report["ok"], "the declared whole-object neutral has no timer leaves"


@pytest.mark.parametrize("window", [
    None, {}, {"phase": "unknown"},
    {"phase": "always", "clock": "active"},
    {"phase": "always", "clock": "active", "startDelayTicks": 0},
    {"phase": "always", "unexpected": True},
])
def test_stripped_wire_never_completes_invalid_or_partial_windows(window):
    source, call = unrestricted_source()
    wire = compile_runtime_program(source)
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    entity[PROJECTILE_MODIFIER_COMPONENTS[call["fn"]]]["window"] = deepcopy(window)
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == before


def test_completion_does_not_create_an_undeclared_structured_parent():
    fn = "sprite_scale_curve"
    _, call = unrestricted_source(fn)
    assert "window" not in _completed_params(fn, call["params"])
    assert not declared_neutral_omissions(fn, call["params"])
