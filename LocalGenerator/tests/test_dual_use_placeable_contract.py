from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring import (
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


ROOT = Path(__file__).resolve().parents[2]


def _codes(report: dict[str, Any]) -> set[str]:
    return {str(row.get("code")) for row in report.get("errors") or []}


def _changed_paths(left: Any, right: Any, path: str = "$") -> set[str]:
    if type(left) is not type(right):
        return {path}
    if isinstance(left, dict):
        paths: set[str] = set()
        for key in set(left) | set(right):
            if key not in left or key not in right:
                paths.add(f"{path}.{key}")
            else:
                paths.update(_changed_paths(left[key], right[key], f"{path}.{key}"))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return {path}
        paths: set[str] = set()
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            paths.update(_changed_paths(a, b, f"{path}[{index}]"))
        return paths
    return set() if left == right else {path}


def _empty_patch() -> dict[str, Any]:
    return {
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "bindingsUpsert": [], "bindingIdsDelete": [], "bindingIndicesDelete": [],
        "callsUpsert": [], "callIdsDelete": [], "callIndicesDelete": [],
        "callParamKeysDelete": [],
        "metadataPatch": {}, "note": "atomic binding use-policy replay",
    }


def _upgrade_fixture(name: str) -> dict[str, Any]:
    return copy.deepcopy(build_runtime_fixture(name))


def _dual_use_placeable() -> dict[str, Any]:
    authored = _upgrade_fixture("workbench_blade")
    program = authored["runtimeProgram"]
    program["calls"].append({
        "id": "install_tile",
        "fn": "configure_placeable",
        "target": "item",
        "params": {"tileId": 19, "wallId": -1, "placeStyle": 0},
    })
    program["bindings"].append({
        "id": "alternate_install",
        "input": "alternate_use",
        "usePolicy": {
            "action": {
                "kind": "place_item",
                "targetId": "item",
                "placementCallId": "install_tile",
            },
            "stackCost": 1,
            "contactDamage": False,
        },
    })
    authored["realization"]["selfEvaluation"]["planVsProgram"]["actionChecks"].append({
        "plannedIntent": "No corresponding initial action.",
        "implementedBehavior": "Alternate use installs the exact authored tile.",
        "runtimeRefs": ["alternate_install", "install_tile"],
        "result": "added",
        "intentionality": "intentional",
        "reason": "The test adds an explicit placement lane to the executable program.",
    })
    authored["realization"]["selfEvaluation"]["programVsReport"]["behaviorChecks"].append({
        "runtimeRefs": ["alternate_install", "install_tile"],
        "programBehavior": "Alternate use installs the exact authored tile.",
        "reportedBehavior": "Alternate use installs the exact authored tile.",
        "result": "aligned",
        "reason": "The test report names the added placement lane.",
    })
    return authored


def _resource_use_placeable() -> dict[str, Any]:
    authored = _upgrade_fixture("fishing_platform_tool")
    program = authored["runtimeProgram"]
    program["bindings"][0] = {
        "id": "primary_restore",
        "input": "primary_use",
        "usePolicy": {
            "action": {"kind": "apply_item_effects", "targetId": "item"},
            "stackCost": 1,
            "contactDamage": False,
        },
    }
    program["calls"] = [
        row for row in program["calls"]
        if row["id"] not in {"item_contact", "tool_heads"}
    ]
    program["calls"].append({
        "id": "restore_life",
        "fn": "restore_resources_on_use",
        "target": "item",
        "params": {"healLife": 50, "healMana": 0, "usesPotionRules": True},
    })
    stats = next(row for row in program["calls"] if row["id"] == "item_stats")
    stats["params"].update({"damage": 0, "knockback": 0.0, "maxStack": 99})
    authored["realization"] = {
        "description": "Primary use restores life and consumes one stacked item; alternate use places the authored platform.",
        "playerExperience": "The player chooses between a consumable heal and recoverable platform placement.",
        "selfEvaluation": {
            "planVsProgram": {
                "verdict": "changed",
                "summary": "The fixture's original tool lane became an explicit resource-use lane.",
                "actionChecks": [
                    {
                        "plannedIntent": "Use the primary action.",
                        "implementedBehavior": "Primary use restores life and consumes one item.",
                        "runtimeRefs": ["primary_restore", "restore_life"],
                        "result": "changed",
                        "intentionality": "intentional",
                        "reason": "The test explicitly replaces the primary tool behavior.",
                    },
                    {
                        "plannedIntent": "Place the authored platform.",
                        "implementedBehavior": "Alternate use places the authored platform.",
                        "runtimeRefs": ["alternate_place", "platform"],
                        "result": "aligned",
                        "intentionality": "intentional",
                        "reason": "The alternate placement lane remains explicit.",
                    },
                ],
            },
            "programVsReport": {
                "verdict": "aligned",
                "summary": "The report covers both executable use lanes.",
                "behaviorChecks": [
                    {
                        "runtimeRefs": ["primary_restore", "restore_life"],
                        "programBehavior": "Primary use restores life and consumes one item.",
                        "reportedBehavior": "Primary use restores life and consumes one stacked item.",
                        "result": "aligned",
                        "reason": "The final report describes the primary resource-use lane.",
                    },
                    {
                        "runtimeRefs": ["alternate_place", "platform"],
                        "programBehavior": "Alternate use places the authored platform.",
                        "reportedBehavior": "Alternate use places the authored platform.",
                        "result": "aligned",
                        "reason": "The final report describes the alternate placement lane.",
                    },
                ],
            },
        },
    }
    return authored


def test_explicit_resource_use_plus_alternate_placement_is_a_valid_hybrid() -> None:
    authored = _resource_use_placeable()
    report = validate_runtime_program(authored)
    assert report["ok"], report["errors"]


def test_pure_placeable_repairs_alternate_place_to_primary_without_creating_combat() -> None:
    authored = _resource_use_placeable()
    program = authored["runtimeProgram"]
    program["bindings"] = [row for row in program["bindings"] if row["id"] != "primary_restore"]
    program["calls"] = [row for row in program["calls"] if row["id"] != "restore_life"]
    authored["realization"] = {
        "description": "Primary use places the authored platform.",
        "playerExperience": "The item acts as a recoverable placeable platform.",
        "selfEvaluation": {
            "planVsProgram": {
                "verdict": "changed",
                "summary": "The resource-use lane was removed and placement moved to primary use.",
                "actionChecks": [{
                    "plannedIntent": "Place the authored platform.",
                    "implementedBehavior": "Primary use places the authored platform.",
                    "runtimeRefs": ["alternate_place", "platform"],
                    "result": "changed",
                    "intentionality": "intentional",
                    "reason": "The repair test moves the same placement transaction to primary use.",
                }],
            },
            "programVsReport": {
                "verdict": "aligned",
                "summary": "The report covers the only executable use lane.",
                "behaviorChecks": [{
                    "runtimeRefs": ["alternate_place", "platform"],
                    "programBehavior": "Primary use places the authored platform.",
                    "reportedBehavior": "Primary use places the authored platform.",
                    "result": "aligned",
                    "reason": "The final report describes the placement lane.",
                }],
            },
        },
    }

    report = validate_runtime_program(authored)
    assert "dual_use_placeable_input_contract" in _codes(report)
    scope = build_runtime_repair_scope(authored, report["errors"])
    alternatives = next(
        row["allowed"] for row in scope["bindingAlternatives"]
        if row["bindingId"] == "alternate_place"
    )
    assert alternatives[0]["input"] == "primary_use"
    assert scope["create"]["bindings"]["allowedTransactions"] == []

    patch = _empty_patch()
    patch["bindingsUpsert"] = [{"id": "alternate_place", **alternatives[0]}]
    filtered, audit = filter_repair_patch_scope(authored, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(authored, filtered)
    assert validate_runtime_program(repaired)["ok"]


def test_atomic_use_policy_is_the_only_author_and_wire_owner() -> None:
    authored = _dual_use_placeable()
    report = validate_runtime_program(authored)
    assert report["ok"], report["errors"]

    compiled = compile_runtime_program(authored)
    bindings = {
        row["input"]: row for row in compiled["runtimeProgram"]["bindings"]
        if row["input"] in {"primary_use", "alternate_use"}
    }
    assert bindings["primary_use"]["usePolicy"] == {
        "action": {"kind": "spawn_entity", "targetId": "workbench_blade"},
        "stackCost": 0,
        "contactDamage": True,
    }
    assert bindings["alternate_use"]["usePolicy"] == {
        "action": {
            "kind": "place_item",
            "targetId": "item",
            "placement": {"tileId": 19, "wallId": -1, "placeStyle": 0},
        },
        "stackCost": 1,
        "contactDamage": False,
    }
    gameplay = compiled["gameplay"]
    assert "primaryUseConsumeChancePercent" not in gameplay
    assert "alternateUseConsumeChancePercent" not in gameplay
    assert "consumable" not in gameplay
    assert compiled["runtimeProgram"].get("itemContact", {}).get("enabled") is None
    assert validate_runtime_wire(compiled)["ok"]


def test_place_policy_is_structurally_closed_and_legacy_fragments_fail() -> None:
    free_place = _dual_use_placeable()
    free_place["runtimeProgram"]["bindings"][-1]["usePolicy"]["stackCost"] = 0
    assert "place_item_without_stack_cost" in _codes(validate_runtime_program(free_place))

    wrong_contact = _dual_use_placeable()
    wrong_contact["runtimeProgram"]["bindings"][-1]["usePolicy"]["contactDamage"] = True
    assert not validate_runtime_program(wrong_contact)["ok"]

    legacy = _upgrade_fixture("workbench_blade")
    legacy["runtimeProgram"]["bindings"][0]["action"] = "spawn_entity"
    legacy["runtimeProgram"]["bindings"][0]["target"] = "workbench_blade"
    assert not validate_runtime_program(legacy)["ok"]

    legacy_call = _upgrade_fixture("workbench_blade")
    legacy_call["runtimeProgram"]["calls"].append({
        "id": "legacy_cost",
        "fn": "configure_consumption",
        "target": "item",
        "params": {"primaryUseChancePercent": 0, "alternateUseChancePercent": 100},
    })
    assert "unknown_capability" in _codes(validate_runtime_program(legacy_call))


def test_single_policy_leaf_has_single_wire_leaf_blast_radius() -> None:
    baseline = build_runtime_fixture("fishing_platform_tool")
    changed = copy.deepcopy(baseline)
    primary = next(
        row for row in changed["runtimeProgram"]["bindings"]
        if row["input"] == "primary_use"
    )
    primary["usePolicy"]["stackCost"] = 1
    left = compile_runtime_program(baseline)
    right = compile_runtime_program(changed)
    assert _changed_paths(left, right) == {
        "$.runtimeProgram.bindings[1].usePolicy.stackCost",
    }


def test_repair_authorizes_one_complete_use_transaction_not_shadow_calls() -> None:
    current = _upgrade_fixture("workbench_blade")
    current["runtimeProgram"]["calls"].append({
        "id": "placeable_without_binding",
        "fn": "configure_placeable",
        "target": "item",
        "params": {"tileId": 4, "wallId": -1, "placeStyle": 0},
    })
    report = validate_runtime_program(current)
    assert "missing_binding_dependency" in _codes(report)

    scope = build_runtime_repair_scope(current, report["errors"])
    allowed = scope["create"]["bindings"]["allowedTransactions"]
    assert allowed == [{
        "input": "alternate_use",
        "usePolicy": {
            "action": {
                "kind": "place_item",
                "targetId": "item",
                "placementCallId": "placeable_without_binding",
            },
            "stackCost": 1,
            "contactDamage": False,
        },
    }]
    assert "configure_consumption" not in scope["create"]["calls"]["allowedFns"]

    patch = _empty_patch()
    patch["bindingsUpsert"] = [{"id": "bind_alt_place", **allowed[0]}]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]


def test_repair_complete_transaction_changes_only_the_rejected_policy_leaf() -> None:
    current = _dual_use_placeable()
    broken = current["runtimeProgram"]["bindings"][-1]
    broken["usePolicy"]["stackCost"] = 0
    report = validate_runtime_program(current)
    error = next(
        row for row in report["errors"]
        if row["code"] == "place_item_without_stack_cost"
    )
    scope = build_runtime_repair_scope(current, [error])
    alternatives = next(
        row["allowed"] for row in scope["bindingAlternatives"]
        if row["bindingId"] == broken["id"]
    )
    assert len(alternatives) == 1

    patch = _empty_patch()
    patch["bindingsUpsert"] = [{"id": broken["id"], **alternatives[0]}]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert _changed_paths(current, repaired) == {
        "$.runtimeProgram.bindings[1].usePolicy.stackCost",
    }


def test_place_item_is_discoverable_but_not_recommended_by_high_salience_prompt() -> None:
    payload = build_llm_author_payload({}, {}, {}, {}, "prompt-neutrality")
    high_salience = json.dumps({
        "priorityHeader": payload["priorityHeader"],
        "runtimeProgramInvariants": payload["runtimeProgramInvariants"],
        "selfCheck": payload["selfCheck"],
    }, sort_keys=True).lower()
    assert "place_item" not in high_salience
    assert "placeable" not in high_salience
    assert "hybrid placement" not in high_salience

    action_cards = payload["runtimeCapabilityContract"]["catalog"]["bindingActions"]
    place_card = next(row for row in action_cards if row["action"] == "place_item")
    assert place_card["does"] == "Execute the one placement payload referenced by this binding action."
    assert "alternate_use" not in place_card["does"]


def test_csharp_consumes_binding_policy_directly_without_legacy_facades() -> None:
    item_source = (
        ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs"
    ).read_text(encoding="utf-8")
    dto_source = (
        ROOT / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs"
    ).read_text(encoding="utf-8")
    model_source = (
        ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs"
    ).read_text(encoding="utf-8")

    assert "binding.UsePolicy.StackCost" in item_source
    assert "UsePolicy.ContactDamage" in item_source
    assert "BindingUsesItemBodyContact(binding)" in item_source
    assert "binding.UsePolicy.Action.Kind" in item_source
    assert "class RuntimeBindingUsePolicySpec" in dto_source
    assert "PrimaryUseConsumeChancePercent" not in model_source + item_source
    assert "AlternateUseConsumeChancePercent" not in model_source + item_source
    assert "ItemContact.Enabled" not in item_source
