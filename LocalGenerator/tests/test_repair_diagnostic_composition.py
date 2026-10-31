"""Independent diagnostic choices share exact permissions without thawing gates."""

import copy

import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("reverse_permissions", [False, True], ids=["scope-order", "reversed-scope-order"])
@pytest.mark.parametrize("reverse_errors", [False, True], ids=["validator-order", "reversed-order"])
@pytest.mark.parametrize("contact_suppressed", [False, True], ids=["repair-contact", "frozen-hitbox"])
def test_component_and_event_repairs_keep_independent_frozen_values(contact_suppressed, reverse_errors, reverse_permissions):
    authored = build_capability_witness("restore_resources_on_use")
    calls = authored["runtimeProgram"]["calls"]
    healing = next(row for row in calls if row["fn"] == "restore_resources_on_use")
    healing["params"].update(healLife=0, healMana=0, usesPotionRules=False)
    item_use = next(row for row in calls if row["fn"] == "item_use")
    item_use["params"]["disableMeleeHitbox"] = contact_suppressed
    binding = authored["runtimeProgram"]["bindings"][0]
    binding["contactDamage"] = False
    event = {
        "id": "body_status", "fn": "apply_status_on_event", "target": "item",
        "params": {"when": "on_hit", "buffId": 20, "duration": 1.0},
    }
    calls.append(event)
    before = copy.deepcopy(authored)
    errors = validate_runtime_program(authored)["errors"]
    assert {row["code"] for row in errors} == {"empty_component", "event_not_emitted"}
    if reverse_errors:
        errors.reverse()
    scope = build_runtime_repair_scope(authored, errors)
    if reverse_permissions:
        for permissions in scope["fieldPermissions"].values():
            permissions.reverse()
            for permission in permissions:
                permission["paths"].reverse()
    # Scope permissions are keyed by identity/path, not traversal order. Sorting
    # (rather than a dict or set) still detects duplicate rows and permissions.
    permissions = [{**row, "paths": sorted(row["paths"])} for row in scope["fieldPermissions"]["calls"]]
    expected_permissions = [
        {"id": event["id"], "paths": ["params.when"]},
        {"id": healing["id"], "paths": ["params.healLife", "params.healMana"]},
    ]
    assert sorted(permissions, key=lambda row: row["id"]) == sorted(expected_permissions, key=lambda row: row["id"])
    assert scope["fieldPermissions"]["bindings"] == ([] if contact_suppressed else [
        {"id": binding["id"], "paths": ["contactDamage"]},
    ])
    assert not scope["create"]["entities"]["allowed"]
    assert not scope["create"]["calls"]["allowed"]
    if contact_suppressed:
        assert not scope["create"]["bindings"]["allowed"]

    fixed_healing = copy.deepcopy(healing)
    fixed_healing["params"].update(healLife=20, usesPotionRules=True)
    fixed_binding = copy.deepcopy(binding)
    fixed_binding.update(contactDamage=True, input="alternate_use")
    hostile_gate = copy.deepcopy(item_use)
    hostile_gate["params"]["disableMeleeHitbox"] = not contact_suppressed
    hostile_event = copy.deepcopy(event)
    hostile_event["params"]["duration"] = 10.0
    patch = {
        "note": "fix independent healing and event diagnostics",
        "callsUpsert": [fixed_healing, hostile_gate, hostile_event],
        "bindingsUpsert": [fixed_binding],
        "callIdsDelete": [event["id"]] if contact_suppressed else [],
    }
    patch_before = copy.deepcopy(patch)
    filtered, audit = filter_repair_patch_scope(authored, patch, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    assert authored == before and patch == patch_before

    expected = copy.deepcopy(authored)
    expected_calls = expected["runtimeProgram"]["calls"]
    next(row for row in expected_calls if row["id"] == healing["id"])["params"]["healLife"] = 20
    if contact_suppressed:
        expected["runtimeProgram"]["calls"] = [row for row in expected_calls if row["id"] != event["id"]]
    else:
        expected["runtimeProgram"]["bindings"][0]["contactDamage"] = True
    repaired = apply_repair_patch(authored, filtered)
    assert repaired == expected
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
