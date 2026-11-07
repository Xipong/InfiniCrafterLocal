"""Unrestricted modifier timing is an explicit Author contract, not recovery."""
from copy import deepcopy

import infini_local.core.runtime_authoring.registry_views as registry_views
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def without_timing(fn="homing"):
    source = build_capability_witness(fn)
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == fn)
    for name in ("window", "startDelay", "duration"):
        call["params"].pop(name, None)
    return source, call


def test_homing_without_time_restriction_is_valid_author_without_mutation():
    source, call = without_timing()
    call["params"].update(range=8, maxTurnRadiansPerSecond=2, requireLineOfSight=True)
    before = deepcopy(source)
    report = validate_runtime_program(source)
    assert report["ok"], report["errors"]
    assert source == before


def test_unrestricted_homing_compiles_to_exact_explicit_always_wire():
    source, call = without_timing()
    before = deepcopy(source)
    explicit = deepcopy(source)
    next(c for c in explicit["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]["window"] = {"phase": "always"}
    expected = compile_runtime_program(explicit)
    actual = compile_runtime_program(source)
    assert actual["runtimeProgram"] == expected["runtimeProgram"]
    assert actual["gameplay"] == expected["gameplay"]
    assert validate_runtime_wire(actual)["ok"]
    assert actual["runtimeContract"]["technicalLoweringAudit"]["ok"]
    proof = [r for r in actual["runtimeContract"]["finalWireReceipts"]
             if r.get("callId") == call["id"] and r.get("status") == "declared_neutral_omission"]
    assert len(proof) == 1
    assert proof[0]["authoredPath"].endswith(".params.window.phase")
    assert proof[0]["value"] == "always"
    assert source == before


def test_neutral_timing_filter_does_not_make_homing_an_empty_effect():
    _, call = without_timing()
    assert CAPABILITY_REGISTRY[call["fn"]].has_non_neutral_effect(call["params"])


def test_shared_window_type_never_inherits_a_use_specific_default(monkeypatch):
    import infini_local.core.runtime_authoring.capability_registry as registry
    cap = registry.CAPABILITY_REGISTRY["homing"]
    reordered = {key: value for key, value in registry.CAPABILITY_REGISTRY.items() if key != cap.name}
    reordered[cap.name] = cap
    monkeypatch.setattr(registry, "CAPABILITY_REGISTRY", reordered)
    shared = registry_views.shared_parameter_schemas()["motionWindow"]
    assert "default" not in shared and "x-infini-neutral" not in shared
