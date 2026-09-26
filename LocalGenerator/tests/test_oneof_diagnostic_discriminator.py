"""oneOf diagnostics must preserve the exact authored branch for targeted Repair."""

import copy

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    validate_runtime_program,
)
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def test_collision_diagnostics_scope_and_filtered_repair_preserve_authored_fn_and_params():
    current = build_runtime_fixture("workbench_blade")
    calls = current["runtimeProgram"]["calls"]
    index = next(i for i, row in enumerate(calls) if row["id"] == "nail_collision")
    call = calls[index]
    original = copy.deepcopy(call)
    call["params"] = {"tileCollide": True, "pierce": -1, "ignoreWater": True}
    base = f"$.runtimeProgram.calls[{index}]"
    required = set(CAPABILITY_REGISTRY["set_projectile_collision"].provider_variant_schema()["properties"]["params"]["required"])
    missing = required - set(call["params"])
    assert missing

    report = validate_runtime_program(current)
    assert not report["ok"]
    shape_errors = [e for e in report["errors"] if e["code"].startswith("shape_") and e["path"].startswith(base)]
    assert {e["path"] for e in shape_errors} == {base, *(f"{base}.params.{key}" for key in missing)}
    assert all(e["path"] != f"{base}.fn" for e in report["errors"])
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": sorted(f"params.{key}" for key in missing)}]
    assert call["id"] not in scope["identityChanges"]["callFnIds"]
    assert not any(row["callId"] == call["id"] and row["key"] in call["params"]
                   for row in scope["deletable"]["callParamKeys"])

    candidate = copy.deepcopy(original)
    candidate["params"].update(call["params"])
    candidate["params"]["pierce"] = 4  # A valid authored value must remain frozen.
    patch = {"note": "fill exact missing collision fields", "callsUpsert": [candidate],
             "callParamKeysDelete": [{"callId": call["id"], "key": "tileCollide"},
                                     {"callId": call["id"], "key": "pierce"}]}
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit["errors"]
    assert not filtered["callParamKeysDelete"]
    assert filtered["callsUpsert"][0]["fn"] == "set_projectile_collision"
    assert filtered["callsUpsert"][0]["params"]["pierce"] == -1
    assert set(filtered["callsUpsert"][0]["params"]) == required
    replacement = next(row for row in build_runtime_fixture("equipment_tool_combat")["runtimeProgram"]["calls"]
                       if row["fn"] == "configure_accessory")
    replacement["id"] = call["id"]
    replacement["target"] = call["target"]
    foreign_patch, foreign_audit = filter_repair_patch_scope(
        current, {"note": "fill missing and attempt to replace fn", "callsUpsert": [candidate, replacement]}, scope)
    assert foreign_audit["ok"], foreign_audit["errors"]
    assert len(foreign_patch["callsUpsert"]) == 1
    assert foreign_patch["callsUpsert"][0]["fn"] == "set_projectile_collision"
    assert any(row["path"].endswith(".fn") for row in foreign_audit["ignoredChanges"])
    repaired = apply_repair_patch(current, filtered)
    assert repaired["runtimeProgram"]["calls"][index]["params"]["tileCollide"] is True
    assert repaired["runtimeProgram"]["calls"][index]["params"]["pierce"] == -1
    assert validate_runtime_program(repaired)["ok"], validate_runtime_program(repaired)["errors"]
    assert compile_runtime_program(repaired)["runtimeProgram"]["entities"]


def test_missing_binding_action_kind_does_not_unfreeze_contact_damage():
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    replacement = copy.deepcopy(binding)
    del binding["usePolicy"]["action"]["kind"]
    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    permissions = next(row["paths"] for row in scope["fieldPermissions"]["bindings"] if row["id"] == binding["id"])
    assert permissions == ["usePolicy.action.kind"]
    original_contact = binding["usePolicy"]["contactDamage"]
    replacement["usePolicy"]["contactDamage"] = not original_contact
    replacement["usePolicy"]["stackCost"] = 1
    filtered, audit = filter_repair_patch_scope(
        current, {"note": "restore kind but attempt unrelated change", "bindingsUpsert": [replacement]}, scope,
    )
    assert audit["ok"], audit["errors"]
    assert filtered["bindingsUpsert"][0]["usePolicy"]["contactDamage"] is original_contact
    assert filtered["bindingsUpsert"][0]["usePolicy"]["stackCost"] == binding["usePolicy"]["stackCost"]
    assert filtered["bindingsUpsert"][0]["input"] == binding["input"]
    assert filtered["bindingsUpsert"][0]["usePolicy"]["action"]["targetId"] == binding["usePolicy"]["action"]["targetId"]
    assert {"contactDamage", "stackCost"} <= {row["path"].rsplit(".", 1)[-1] for row in audit["ignoredChanges"]}
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert compile_runtime_program(repaired)["runtimeProgram"]["bindings"]

    # A second complete, individually valid binding must not retarget or
    # change input merely because the action discriminator needs repair.
    retargeted = copy.deepcopy(replacement)
    retargeted["input"] = "alternate_use"
    retargeted["usePolicy"]["action"]["targetId"] = "nail"
    retargeted_patch, retargeted_audit = filter_repair_patch_scope(
        current, {"note": "attempt sibling rewrite", "bindingsUpsert": [retargeted]}, scope,
    )
    assert retargeted_audit["ok"], retargeted_audit["errors"]
    frozen = retargeted_patch["bindingsUpsert"][0]
    assert frozen["input"] == binding["input"]
    assert frozen["usePolicy"]["action"]["targetId"] == binding["usePolicy"]["action"]["targetId"]
    assert frozen["usePolicy"]["contactDamage"] is original_contact
    assert frozen["usePolicy"]["stackCost"] == binding["usePolicy"]["stackCost"]
    assert validate_runtime_program(apply_repair_patch(current, retargeted_patch))["ok"]


def test_missing_binding_input_restores_only_missing_leaf():
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    candidate = copy.deepcopy(binding)
    del binding["input"]
    candidate["usePolicy"]["contactDamage"] = not binding["usePolicy"]["contactDamage"]
    candidate["usePolicy"]["stackCost"] = 1
    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    permissions = next(row["paths"] for row in scope["fieldPermissions"]["bindings"] if row["id"] == binding["id"])
    assert permissions == ["input"]
    filtered, audit = filter_repair_patch_scope(current, {"note": "restore discriminator", "bindingsUpsert": [candidate]}, scope)
    assert audit["ok"], audit["errors"]
    fixed = filtered["bindingsUpsert"][0]
    assert fixed["usePolicy"]["contactDamage"] is binding["usePolicy"]["contactDamage"]
    assert fixed["usePolicy"]["stackCost"] == binding["usePolicy"]["stackCost"]
    assert fixed["input"] == "primary_use"
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_atomic_binding_transaction_shortcut_requires_exact_row_and_wire():
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    original = copy.deepcopy(binding)
    other = copy.deepcopy(binding)
    other["id"] = "other_binding"
    other["input"] = "alternate_use"
    current["runtimeProgram"]["bindings"].append(other)
    assert validate_runtime_program(current)["ok"]  # The second row is independently valid.

    # Unlike a missing action.kind leaf, the entire atomic usePolicy is gone.
    # Its legacy siblings are invalid and the exact registry alternative can replace it.
    binding["action"] = original["usePolicy"]["action"]["kind"]
    binding["target"] = original["usePolicy"]["action"]["targetId"]
    del binding["usePolicy"]
    report = validate_runtime_program(current)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"] if e["code"].startswith("shape_")} == {
        "$.runtimeProgram.bindings[0]",
        "$.runtimeProgram.bindings[0].usePolicy",
        "$.runtimeProgram.bindings[0].action",
        "$.runtimeProgram.bindings[0].target",
    }
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["fieldPermissions"]["bindings"] == [{
        "id": binding["id"],
        "paths": ["action", "target", "usePolicy", "usePolicy.action.kind", "usePolicy.action.targetId"],
    }]
    alternatives = next(row["allowed"] for row in scope["bindingAlternatives"]
                        if row["bindingId"] == binding["id"])
    transaction = {"input": original["input"], "usePolicy": copy.deepcopy(original["usePolicy"])}
    transaction["usePolicy"]["contactDamage"] = False
    assert transaction in alternatives
    exact = {"id": binding["id"], **transaction}

    filtered, audit = filter_repair_patch_scope(
        current, {"note": "replace complete usePolicy", "bindingsUpsert": [exact]}, scope)
    assert audit["ok"], audit["errors"]
    assert filtered["bindingsUpsert"] == [exact], filtered
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]

    wrong_input = copy.deepcopy(exact)
    wrong_input["input"] = "alternate_use"
    input_filtered, input_audit = filter_repair_patch_scope(
        current, {"note": "attempt unrelated input", "bindingsUpsert": [wrong_input]}, scope)
    assert not input_audit["ok"], input_audit
    assert input_filtered["bindingsUpsert"] != [wrong_input], input_filtered
    assert any(row["path"] == "$.bindingsUpsert[0].input" and row["reason"] == "frozen_valid_value"
               for row in input_audit["ignoredChanges"]), input_audit

    legacy_sibling = {**copy.deepcopy(exact), "action": binding["action"]}
    sibling_filtered, sibling_audit = filter_repair_patch_scope(
        current, {"note": "attempt legacy sibling", "bindingsUpsert": [legacy_sibling]}, scope)
    assert not sibling_audit["ok"], sibling_audit
    assert sibling_filtered["bindingsUpsert"] != [legacy_sibling], sibling_filtered
    assert any(row["path"] == "$.bindingsUpsert[0].action" and row["kind"] == "additional_property"
               for row in sibling_audit["errors"]), sibling_audit

    wrong_id = {**copy.deepcopy(transaction), "id": other["id"]}
    id_filtered, id_audit = filter_repair_patch_scope(
        current, {"note": "attempt different binding", "bindingsUpsert": [wrong_id]}, scope)
    assert not id_audit["ok"], id_audit
    assert id_filtered["bindingsUpsert"] == [], id_filtered
    assert any(row["path"] == "$.bindingsUpsert[0]" and row["reason"] == "independent_valid_node_frozen"
               for row in id_audit["ignoredChanges"]), id_audit


def test_unknown_binding_action_kind_does_not_unfreeze_valid_siblings():
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    candidate = copy.deepcopy(binding)
    binding["usePolicy"]["action"]["kind"] = "unknown_kind"
    candidate["usePolicy"]["contactDamage"] = not binding["usePolicy"]["contactDamage"]
    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    assert any(row["code"] == "shape_one_of" and row["path"].endswith(".action.kind") for row in report["errors"])
    filtered, audit = filter_repair_patch_scope(current, {"note": "choose action", "bindingsUpsert": [candidate]}, scope)
    assert audit["ok"], audit["errors"]
    assert filtered["bindingsUpsert"][0]["usePolicy"]["contactDamage"] is binding["usePolicy"]["contactDamage"]
    assert filtered["bindingsUpsert"][0]["usePolicy"]["action"]["kind"] == "spawn_entity"
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_every_registry_fn_with_missing_params_reports_own_required_fields_without_foreign_const():
    variants = {fn: cap.provider_variant_schema() for fn, cap in CAPABILITY_REGISTRY.items()}
    union = {"oneOf": list(variants.values())}
    for fn, variant in variants.items():
        required = set(variant["properties"]["params"]["required"])
        if not required:
            continue
        call = {"id": "probe", "fn": fn, "target": "item", "params": {}}
        errors = strict_schema_errors(call, union)
        assert {e["path"] for e in errors if e["kind"] == "required"} == {f"$.params.{key}" for key in required}, fn
        assert all(not (e["path"] == "$.fn" and e["kind"] == "const") for e in errors), fn


def test_oneof_diagnostic_selection_is_independent_of_branch_order():
    branches = [
        {"type": "object", "properties": {"fn": {"const": "alpha"}, "value": {"type": "integer"}}, "required": ["fn", "value"]},
        {"type": "object", "properties": {"fn": {"const": "beta"}, "value": {"type": "integer"}, "other": {"type": "string"}}, "required": ["fn", "value", "other"]},
    ]
    value = {"fn": "beta"}
    expected = [{"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0},
                {"path": "$.value", "kind": "required"}, {"path": "$.other", "kind": "required"}]
    assert strict_schema_errors(value, {"oneOf": branches}) == expected
    assert strict_schema_errors(value, {"oneOf": branches[::-1]}) == expected


@pytest.mark.parametrize("value", [{"fn": "unknown"}, {"value": 1}, {}])
def test_oneof_unknown_or_missing_discriminator_fails_closed_without_branch_permissions(value):
    branches = [{"type": "object", "properties": {"fn": {"const": fn}, "value": {"type": "integer"}},
                 "required": ["fn", "value"]} for fn in ("alpha", "beta")]
    assert strict_schema_errors(value, {"oneOf": branches}) == [
        {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0}]


def test_oneof_nested_discriminators_require_one_exact_branch():
    def branch(input_name, action):
        return {"type": "object", "properties": {
            "input": {"const": input_name}, "policy": {"type": "object", "properties": {
                "action": {"type": "object", "properties": {"kind": {"const": action}}, "required": ["kind"]}}},
            "value": {"type": "integer"}}, "required": ["input", "policy", "value"]}
    branches = [branch("use", "launch"), branch("use", "place"), branch("hold", "launch")]
    errors = strict_schema_errors({"input": "use", "policy": {"action": {"kind": "place"}}}, {"oneOf": branches})
    assert errors == [{"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0},
                      {"path": "$.value", "kind": "required"}]
    assert strict_schema_errors({"input": "use", "policy": {"action": {"kind": "unknown"}}}, {"oneOf": branches}) == [
        {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0},
        {"path": "$.policy.action.kind", "kind": "one_of"}]
    assert strict_schema_errors({"input": "use", "policy": {"action": {}}}, {"oneOf": branches}) == [
        {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0},
        {"path": "$.value", "kind": "required"},
        {"path": "$.policy.action.kind", "kind": "required"}]
    assert strict_schema_errors({"policy": {"action": {"kind": "launch"}}}, {"oneOf": branches}) == [
        {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0},
        {"path": "$.input", "kind": "required"},
        {"path": "$.value", "kind": "required"}]
    assert strict_schema_errors({"input": "unknown", "policy": {"action": {"kind": "launch"}}}, {"oneOf": branches}) == [
        {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 0},
        {"path": "$.input", "kind": "one_of"}]


def test_oneof_valid_and_multi_match_acceptance_semantics_unchanged():
    branch = {"type": "object", "properties": {"fn": {"const": "same"}}, "required": ["fn"]}
    assert strict_schema_errors({"fn": "same"}, {"oneOf": [branch, {"properties": {"fn": {"const": "other"}}}]}) == []
    assert strict_schema_errors({"fn": "same"}, {"oneOf": [branch, copy.deepcopy(branch)]}) == [
        {"path": "$", "kind": "one_of", "expected": "exactly_one", "actual": 2}]
