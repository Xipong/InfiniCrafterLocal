"""Repair operates on the single Author source with its declared omissions."""
from __future__ import annotations

import copy

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch,
    build_runtime_repair_scope,
    filter_repair_patch_scope,
    runtime_repair_fragments,
    validate_runtime_program,
)
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.mark.parametrize("declaration", ["missing", "ambiguous"])
def test_item_declaration_repair_resolves_implicit_targets_without_rewriting_calls(declaration):
    source = build_runtime_fixture("workbench_blade")
    program = source["runtimeProgram"]
    program["primaryEntityId"] = "workbench_blade"
    body = next(row for row in program["entities"] if row["kind"] == "item_body")
    if declaration == "missing":
        program["entities"].remove(body)
        patch = {"note": "declare the missing body", "entitiesUpsert": [copy.deepcopy(body)]}
    else:
        duplicate = {**copy.deepcopy(body), "id": "ambiguous_body"}
        program["entities"].append(duplicate)
        patch = {"note": "remove the exact extra body", "entityIdsDelete": [duplicate["id"]]}
    frozen_calls = copy.deepcopy(program["calls"])
    frozen_bindings = copy.deepcopy(program["bindings"])
    report = validate_runtime_program(source)
    assert not report["ok"]
    assert "item_body_count" in {row["code"] for row in report["errors"]}
    assert not any(row["path"].endswith((".target", ".action.targetId")) for row in report["errors"])
    scope = build_runtime_repair_scope(source, report["errors"])
    filtered, audit = filter_repair_patch_scope(source, patch, scope)
    assert audit["ok"], audit
    assert filtered["callsUpsert"] == filtered["bindingsUpsert"] == []
    repaired = apply_repair_patch(source, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert repaired["runtimeProgram"]["calls"] == frozen_calls
    assert repaired["runtimeProgram"]["bindings"] == frozen_bindings


def test_no_argument_call_retarget_does_not_materialize_params():
    source = build_capability_witness("move_straight")
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "move_straight")
    assert "params" not in call
    good = copy.deepcopy(call)
    del call["target"]
    report = validate_runtime_program(source)
    assert not report["ok"]
    scope = build_runtime_repair_scope(source, report["errors"])
    filtered, audit = filter_repair_patch_scope(source, {"note": "restore exact target", "callsUpsert": [good]}, scope)
    assert audit["ok"], audit
    assert filtered["callsUpsert"] == [good]
    assert "params" not in filtered["callsUpsert"][0]
    assert validate_runtime_program(apply_repair_patch(source, filtered))["ok"]


@pytest.mark.parametrize("fn,extra_key,extra_value", [
    ("configure_item_stats", "target", "arbitrary_item"),
    ("move_straight", "params", {}),
])
def test_exact_forbidden_call_property_can_be_removed_without_expanding_source(fn, extra_key, extra_value):
    source = build_capability_witness(fn)
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == fn)
    good = copy.deepcopy(call)
    assert extra_key not in good
    call[extra_key] = copy.deepcopy(extra_value)
    report = validate_runtime_program(source)
    assert not report["ok"]
    scope = build_runtime_repair_scope(source, report["errors"])
    filtered, audit = filter_repair_patch_scope(source, {"note": "remove forbidden field", "callsUpsert": [good]}, scope)
    assert audit["ok"], audit
    assert filtered["callsUpsert"] == [good]
    assert any(path.endswith("." + extra_key) for path in audit["acceptedPaths"])
    assert validate_runtime_program(apply_repair_patch(source, filtered))["ok"]


def test_equipped_input_repair_preserves_all_singleton_omissions():
    source = build_capability_witness("configure_accessory")
    binding = next(row for row in source["runtimeProgram"]["bindings"] if row["input"] == "equipped")
    good = copy.deepcopy(binding)
    assert set(good) == {"id", "input"}
    del binding["input"]
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    assert scope["fieldPermissions"]["bindings"] == [{"id": binding["id"], "paths": ["input"]}]
    filtered, audit = filter_repair_patch_scope(source, {"note": "restore equipped input", "bindingsUpsert": [good]}, scope)
    assert audit["ok"], audit
    assert filtered["bindingsUpsert"] == [good]
    repaired = apply_repair_patch(source, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert next(row for row in repaired["runtimeProgram"]["bindings"] if row["id"] == good["id"]) == good


def test_item_only_dependency_context_retains_exact_source_omissions():
    source = build_runtime_fixture("workbench_blade")
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_item_use")
    del call["params"]["useStyle"]
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    fragments = runtime_repair_fragments(source, scope)
    assert fragments["broken"]["calls"] == [call]
    item_index = next(row for row in fragments["immutableIndex"]["calls"] if row["id"] == call["id"])
    assert item_index == {"id": call["id"], "fn": call["fn"]}
    assert "item" in {row["id"] for row in fragments["dependencyContext"]["entities"]}
