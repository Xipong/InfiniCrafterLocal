from __future__ import annotations

import copy
import json

import infini_local.core.vfx.contract as vfx_stage_contract
import infini_local.pipelines.author.request as gameplay_stage
import infini_local.pipelines.visual.contract as visual_stage_contract
import infini_local.pipelines.visual.repair as visual_stage_repair
import infini_local.pipelines.visual.repair_scope as visual_stage_repair_scope
import pytest
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.fragments import runtime_repair_fragments
from infini_local.core.runtime_authoring.repair.schema import runtime_repair_scope_schema
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.repair.validation import validate_repair_patch_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_views import runtime_event_inventory
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.contract import VFX_REPAIR_PATCH_SCHEMA
from infini_local.core.vfx.repair import _apply_vfx_repair_patch, _build_vfx_repair_scope
from infini_local.core.vfx.surface import vfx_director_surface
from infini_local.core.vfx.validation import validate_vfx_director_output
from infini_local.pipelines.author.stage import authored_item_validation_report
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from pipeline_test_support import RepairTransaction
from test_low_level_three_stage_pipeline import (
    _accepted_visual_data,
    _binding_row,
    _empty_gameplay_patch,
    _vfx_output,
    _visual_kit,
    wire_transport,
)


@pytest.mark.parametrize("source,selection,ok", [
    pytest.param("invalid", "item", True, id="invalid-primary-select-item"),
    pytest.param("invalid", "workbench_blade", True, id="select-primary-projectile-and-compile-roles"),
    pytest.param("missing", "item", True, id="missing-primary-same-transaction"),
    pytest.param("invalid", "not_an_entity", False, id="outside-roster"),
    pytest.param("invalid", None, False, id="open-primary-noop"),
    pytest.param("unrelated", None, False, id="null-cannot-close-use-style"),
])
def test_primary_identity_transaction(source, selection, ok):
    current = build_runtime_fixture("workbench_blade")
    if source == "invalid":
        current["runtimeProgram"]["primaryEntityId"] = "missing_primary"
    elif source == "missing":
        current["runtimeProgram"].pop("primaryEntityId")
    else:
        next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_use")["params"].pop("useStyle")
    report = validate_runtime_program(current)
    assert not report["ok"]
    if source == "invalid":
        assert "invalid_primary_entity_reference" in {e["code"] for e in report["errors"]}
    elif source == "missing":
        assert next(e for e in report["errors"] if e["path"] == "$.runtimeProgram.primaryEntityId")["code"].startswith("shape_")
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, failure_report=report)
    scope = dossier["repairScope"]
    ids = sorted(e["id"] for e in current["runtimeProgram"]["entities"])
    assert sorted(e["id"] for e in dossier["immutableProgramIndex"]["entities"]) == ids
    if source != "unrelated":
        assert scope["repairTransactions"]["primaryEntitySelection"] == {"allowed": True, "candidateEntityIds": ids, "mustSelectExactlyOne": True}
        assert any("immutableProgramIndex.entities[*].id" in rule for rule in dossier["rules"])
        _, empty_audit = filter_repair_patch_scope(current, _empty_gameplay_patch(), scope)
        assert not empty_audit["ok"]
        assert any("leaves a reported repair error open" in e["message"] for e in empty_audit["errors"])
    patch = dict(_empty_gameplay_patch(), primaryEntitySelection=selection)
    transaction = RepairTransaction(current, report=report, scope=scope)
    repaired, filtered, audit = transaction.apply(patch, accepted=ok)
    if ok:
        assert repaired["runtimeProgram"]["primaryEntityId"] == selection
        assert all("role" not in row for key in ("bindings", "calls") for row in repaired["runtimeProgram"][key])
        compiled = compile_runtime_program(repaired)
        assert all(row["role"] == ("primary" if row["usePolicy"]["action"]["targetId"] == selection else "secondary") for row in compiled["runtimeProgram"]["bindings"])
    elif selection is None:
        assert filtered.get("primaryEntitySelection") is None
        assert "$.primaryEntitySelection" not in audit["acceptedPaths"]
        assert repaired == current


@pytest.mark.parametrize("scenario,duplicates", [
    pytest.param("select", ["foreign-projectile"], id="reject-unreachable-projectile-choice"),
    pytest.param("select", ["unsafe-item-spawn"], id="no-unsafe-keep-fallback"),
    pytest.param("select", ["body-use"], id="retain-projectile-reachability"),
    pytest.param("retarget-conflict", ["same-projectile"], id="ignore-redundant-stale-selection"),
    pytest.param("retarget-original", ["body-use", "body-use"], id="recompute-candidates-after-retarget"),
])
def test_exclusive_input_transaction(scenario, duplicates):
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    original = program["bindings"][0]
    for index, choice in enumerate(duplicates):
        action, target = {"foreign-projectile": ("spawn_entity", "nail"), "unsafe-item-spawn": ("spawn_entity", "item"),
                          "body-use": ("use_item_body", "item"), "same-projectile": ("spawn_entity", "workbench_blade")}[choice]
        program["bindings"].append(_binding_row(f"duplicate_{index}", "primary_use", action, target))
    errors = [e for e in validate_runtime_program(current)["errors"] if e["code"] == "duplicate_exclusive_input"]
    assert errors
    scope = build_runtime_repair_scope(current, errors)
    expected_ids = sorted([original["id"], "duplicate_0"]) if scenario == "retarget-conflict" else [original["id"]]
    assert scope["repairTransactions"]["exclusiveInputSelections"] == [{"input": "primary_use", "candidateBindingIds": expected_ids, "mustKeepExactlyOne": True}]
    patch = _empty_gameplay_patch()
    selected = original["id"]
    if scenario == "retarget-conflict":
        patch["bindingsUpsert"] = [{**program["bindings"][1], "input": "alternate_use"}]
        selected = "not_a_candidate"
    elif scenario == "retarget-original":
        patch["bindingsUpsert"] = [{**original, "input": "alternate_use"}]
        selected = "duplicate_0"
    patch["exclusiveInputSelections"] = [{"input": "primary_use", "keepBindingId": selected}]
    transaction = RepairTransaction(current, errors, scope=scope)
    repaired, filtered, audit = transaction.apply(patch)
    if scenario == "retarget-conflict":
        assert filtered["exclusiveInputSelections"] == []
        assert any(e["reason"] == "exclusive_input_conflict_already_resolved" for e in audit["ignoredChanges"])
    else:
        assert filtered["exclusiveInputSelections"] == patch["exclusiveInputSelections"]
    if scenario.startswith("retarget"):
        moved_id = "duplicate_0" if scenario == "retarget-conflict" else original["id"]
        assert next(e for e in repaired["runtimeProgram"]["bindings"] if e["id"] == moved_id)["input"] == "alternate_use"
    else:
        assert all(e["id"] == original["id"] for e in repaired["runtimeProgram"]["bindings"])


@pytest.mark.parametrize("scenario", ["required-pair", "optional-absence"])
def test_missing_call_leaves_freeze_valid_siblings(scenario):
    current = build_runtime_fixture("workbench_blade")
    use = next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_use")
    original = copy.deepcopy(use)
    use["params"].pop("useStyle")
    use["params"].pop("autoReuse" if scenario == "required-pair" else "customHeldSprite")
    transaction = RepairTransaction(current)
    scope = transaction.scope
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    assert scope["repairRequirements"][0]["repairStrategy"]
    assert scope["repairRequirements"][0]["llmRepairable"] is True
    assert not scope["create"]["entities"]["allowed"]
    assert scope["mutable"]["callIds"] == ["item_use"]
    assert scope["blockerPlan"]["existingBrokenCapabilityNames"] == ["item_use"]
    if scenario == "optional-absence":
        assert next(e["paths"] for e in scope["fieldPermissions"]["calls"] if e["id"] == "item_use") == ["params.useStyle"]
    fixed = copy.deepcopy(use)
    fixed["params"].update(useStyle="shoot", autoReuse=True, handPose="two_handed", customHeldSprite="visible")
    fixed["params"]["channel"] = True  # hostile frozen sibling
    unrelated = copy.deepcopy(next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_stats"))
    unrelated["params"]["damage"] = 999
    patch = dict(_empty_gameplay_patch(), callsUpsert=[fixed, unrelated])
    repaired, filtered, audit = transaction.apply(patch)
    assert audit["ignoredChanges"]
    calls = {c["id"]: c for c in repaired["runtimeProgram"]["calls"]}
    assert calls["item_use"]["params"]["useStyle"] == "shoot"
    assert calls["item_use"]["params"]["autoReuse"] is True
    assert calls["item_use"]["params"]["handPose"] == original["params"]["handPose"]
    assert "target" not in calls["item_use"]
    assert calls["item_stats"]["params"]["damage"] != 999
    if scenario == "required-pair":
        assert calls["item_use"]["params"]["customHeldSprite"] == "hidden"
    else:
        assert "customHeldSprite" not in calls["item_use"]["params"]
        assert any(e["path"].endswith("params.handPose") for e in audit["ignoredChanges"])
        assert any(e["path"].endswith("params.customHeldSprite") and e["reason"] == "addition_not_permitted" for e in audit["ignoredChanges"])


@pytest.mark.parametrize("scenario", ["call-property", "param-extra", "renamed-value", "nested-extra"])
def test_exact_call_key_deletion(scenario):
    current = build_runtime_fixture("workbench_blade")
    call = current["runtimeProgram"]["calls"][0]
    if scenario == "nested-extra":
        scope = build_runtime_repair_scope(current, [{"code": "shape_additional_property", "path": "$.runtimeProgram.calls[0].params.nested.extra", "message": "nested additional property"}])
        assert scope["deletable"]["callParamKeys"] == []
        return
    key = {"call-property": "useStyle", "param-extra": "invalidExtra", "renamed-value": "value"}[scenario]
    container = call if scenario == "call-property" else call["params"]
    container[key] = container.pop("valueCopper") if scenario == "renamed-value" else 7
    report = validate_runtime_program(current)
    assert not report["ok"]
    assert any(e["code"] == "shape_additional_property" and e["path"].endswith('.' + key) for e in report["errors"])
    transaction = RepairTransaction(current, report=report)
    scope = transaction.scope
    roster_key = "callPropertyKeys" if scenario == "call-property" else "callParamKeys"
    permission = {"callId": call["id"], "key": key}
    assert permission in scope["deletable"][roster_key]
    candidate = copy.deepcopy(call)
    target = candidate if scenario == "call-property" else candidate["params"]
    removed = target.pop(key)
    if scenario == "renamed-value":
        target["valueCopper"] = removed
    patch = dict(_empty_gameplay_patch(), callsUpsert=[candidate], primaryEntitySelection=None, exclusiveInputSelections=[])
    if scenario != "param-extra":
        patch[roster_key + "Delete"] = [permission]
    result, filtered, audit = transaction.apply(patch)
    assert filtered[roster_key + "Delete"] == [permission]
    result_call = next(c for c in result["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert key not in (result_call if scenario == "call-property" else result_call["params"])
    if scenario == "call-property":
        dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, failure_report=report)
        assert any("callPropertyKeysDelete" in rule and "note claiming removal" in rule for rule in dossier["rules"])
    else:
        filtered_call = next(c for c in filtered["callsUpsert"] if c["id"] == call["id"])
        assert key not in filtered_call["params"]
        if scenario == "renamed-value":
            assert filtered_call["params"]["valueCopper"] > 0
        outside = dict(_empty_gameplay_patch(), callParamKeysDelete=[{"callId": call["id"], "key": "damage"}])
        rejected, audit = filter_repair_patch_scope(current, outside, scope)
        assert rejected["callParamKeysDelete"] == []
        assert any(e["reason"] == "call_param_delete_outside_exact_error_scope" for e in audit["ignoredChanges"])
        assert any(e["path"] == "$.callParamKeysDelete[0]" for e in validate_repair_patch_scope(current, outside, scope)["errors"])


@pytest.mark.parametrize("scenario,ok", [("exact", True), ("missing-identity", False), ("stale-role", False), ("wrong-capability", False), ("global-collision", False), ("delete-new-param", True)])
def test_missing_dependency_creation(scenario, ok):
    current = build_runtime_fixture("workbench_blade")
    call = next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_use")
    current["runtimeProgram"]["calls"].remove(call)
    report = validate_runtime_program(current)
    assert [e["code"] for e in report["errors"]] == ["binding_dependency"]
    if scenario == "missing-identity":
        report["errors"][0]["relatedIds"] = []
    transaction = RepairTransaction(current, report=report)
    scope = transaction.scope
    assert scope["mutable"]["bindingIds"] == []
    assert "requiredRolesByTarget" not in scope["create"]["calls"]
    if scenario == "missing-identity":
        assert not scope["create"]["calls"]["allowed"] and scope["create"]["calls"]["allowedTargetIds"] == []
        return
    assert scope["create"]["calls"]["allowedFns"] == ["item_use"]
    assert scope["create"]["calls"]["allowedTargetIds"] == ["item"]
    plan = scope["blockerPlan"]
    assert plan["directCapabilityNames"] == ["item_use"]
    assert plan["supportingCapabilityNames"] == []
    assert scope["capabilitySubset"] == ["item_use"]
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, failure_report=report)
    assert "blockerPlan" not in dossier
    assert dossier["repairScope"]["blockerPlan"] == plan
    candidate = copy.deepcopy(call)
    candidate["id"] = "repair_item_use"
    if scenario == "stale-role":
        candidate["role"] = "secondary"
    elif scenario == "wrong-capability":
        candidate = copy.deepcopy(current["runtimeProgram"]["calls"][0])
        candidate["id"] = "wrong_dependency"
    elif scenario == "global-collision":
        candidate["id"] = "item"
    patch = dict(_empty_gameplay_patch(), callsUpsert=[candidate])
    if scenario == "delete-new-param":
        patch["callParamKeysDelete"] = [{"callId": "repair_item_use", "key": "customHeldSprite"}]
    if scenario == "global-collision":
        audit = validate_repair_patch_scope(current, patch, scope)
        assert not audit["ok"]
        assert any(e.get("actual", {}).get("code") == "ambiguous_global_id" for e in audit["errors"])
        return
    repaired, filtered, audit = transaction.apply(patch, accepted=ok)
    if ok:
        assert [c["id"] for c in filtered["callsUpsert"]] == ["repair_item_use"]
        if scenario == "delete-new-param":
            assert filtered["callParamKeysDelete"] == []
            assert any(e["reason"] == "call_param_delete_outside_exact_error_scope" for e in audit["ignoredChanges"])
            assert any(e["path"] == "$.callParamKeysDelete[0]" for e in validate_repair_patch_scope(current, patch, scope)["errors"])
    elif scenario == "stale-role":
        assert any(e.get("kind") == "additional_property" for e in audit["errors"])
    else:
        assert filtered["callsUpsert"] == []
        assert any(e["reason"] == "capability_not_in_blocker_closure" for e in audit["ignoredChanges"])
        assert any("leaves a reported repair error open" in e["message"] for e in audit["errors"])


@pytest.mark.parametrize("scenario,event_ok", [("placement", False), ("missing-contact", False), ("foreign-target-contact", True), ("no-optional-geometry", True)])
def test_item_event_producer_and_exact_contact_repair(scenario, event_ok):
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    binding = program["bindings"][0]
    binding["action"] = {"kind": "use_item_body"}
    binding["contactDamage"] = scenario == "no-optional-geometry"
    event_call = next(c for c in program["calls"] if c["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["when"] = "on_use" if scenario == "placement" else "on_hit"
    if scenario == "placement":
        binding.pop("stackCost"); binding.pop("contactDamage"); binding["action"] = {"kind": "place_item", "placementCallId": "place_bench"}
        program["calls"].append({"id": "place_bench", "fn": "place_tile", "params": {"tileId": 18, "placeStyle": 0}})
        event_call["params"]["entity"] = "workbench_blade"
    else:
        program["bindings"].append(_binding_row("projectile_root", "alternate_use" if scenario == "foreign-target-contact" else "hold", "spawn_entity", "workbench_blade", contact_damage=scenario == "foreign-target-contact"))
        if scenario == "no-optional-geometry":
            program["calls"] = [c for c in program["calls"] if c["fn"] != "item_hitbox"]
    report = validate_runtime_program(current)
    if not event_ok:
        assert "event_not_emitted" in {e["code"] for e in report["errors"]}
        if scenario == "placement":
            return
        assert [e["code"] for e in report["errors"]] == ["event_not_emitted"]
        transaction = RepairTransaction(current, report=report)
        scope = transaction.scope
        requirement = next(e for e in scope["repairRequirements"] if e["code"] == "event_not_emitted")
        assert binding["id"] in requirement["allowedExistingBindingIds"]
        assert any(e["contactDamage"] is True and e["action"] == {"kind": "use_item_body"} for e in requirement["allowedBindingTransactions"])
        assert any(e["action"]["kind"] == "spawn_entity" and e["action"]["targetId"] == "workbench_blade" for e in requirement["allowedBindingTransactions"])
        fixed = copy.deepcopy(binding)
        fixed["contactDamage"] = True
        current, filtered, audit = transaction.apply(dict(_empty_gameplay_patch(), bindingsUpsert=[fixed]))
        assert filtered["bindingsUpsert"] == [fixed]
    assert validate_runtime_program(current)["ok"]
    compiled = compile_runtime_program(current)
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    pairs = {(e["entityId"], e["event"]) for e in runtime_event_inventory(compiled)}
    assert {(item_id, "on_hit"), (item_id, "on_crit")} <= pairs
    assert any(e["event"] == "on_hit" for e in next(e for e in compiled["runtimeProgram"]["entities"] if e["id"] == item_id)["events"])


def test_missing_tool_binding_dependency_with_occupied_primary_exposes_atomic_move_and_create() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    program["entities"] = [row for row in program["entities"] if row["id"] == "item"]
    program["primaryEntityId"] = "item"
    program["calls"] = [
        row for row in program["calls"] if row["id"] in {"item_stats", "item_use"}
    ] + [
        {"id": "place", "fn": "place_tile", "params": {"tileId": 1, "placeStyle": 0}},
        {"id": "tool", "fn": "tool_stats", "params": {"pickPower": 100, "axePower": 0, "hammerPower": 0, "miningSpeedMultiplier": 1.0}},
    ]
    program["bindings"] = [{
        "id": "primary_place",
        "input": "primary_use",
        "action": {"kind": "place_item", "placementCallId": "place"},
    }]
    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["missing_binding_dependency"]

    transaction = RepairTransaction(current, report=report)
    scope = transaction.scope
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    alternatives = {row["bindingId"]: row["allowed"] for row in scope["bindingAlternatives"]}
    assert alternatives["primary_place"] == [{
        "input": "alternate_use",
        "action": {"kind": "place_item", "placementCallId": "place"},
    }]
    primary_create = next(
        row for row in scope["create"]["bindings"]["allowedTransactions"]
        if row["input"] == "primary_use" and row.get("action", {}).get("kind") == "use_item_body"
    )
    requirement = next(row for row in scope["repairRequirements"] if row["code"] == "missing_binding_dependency")
    assert requirement["mustApplyAll"] is True
    assert requirement["requiredBindingUpdates"] == [{
        "bindingId": "primary_place",
        "allowed": alternatives["primary_place"],
    }]

    create_only = _empty_gameplay_patch()
    create_only["bindingsUpsert"] = [{"id": "tool_primary", **primary_create}]
    assert not validate_repair_patch_scope(current, create_only, scope)["ok"]

    move_only = _empty_gameplay_patch()
    move_only["bindingsUpsert"] = [{"id": "primary_place", **alternatives["primary_place"][0]}]
    assert not validate_repair_patch_scope(current, move_only, scope)["ok"]

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [
        {"id": "primary_place", **alternatives["primary_place"][0]},
        {"id": "tool_primary", **primary_create},
    ]
    assert validate_repair_patch_scope(current, patch, scope)["ok"]
    repaired, filtered, audit = transaction.apply(patch)
    by_id = {row["id"]: row for row in repaired["runtimeProgram"]["bindings"]}
    assert by_id["primary_place"]["input"] == "alternate_use"
    assert by_id["tool_primary"]["input"] == "primary_use"


def test_missing_item_body_scope_allows_required_calls_on_same_created_entity(wire_transport) -> None:
    current = build_runtime_fixture("workbench_blade")
    original_item = next(
        copy.deepcopy(row) for row in current["runtimeProgram"]["entities"]
        if row["kind"] == "item_body"
    )
    original_item_calls = [
        copy.deepcopy(row) for row in current["runtimeProgram"]["calls"]
        if CAPABILITY_REGISTRY[row["fn"]].target_kinds == ("item_body",)
    ]
    removed_call_ids = {row["id"] for row in original_item_calls}
    current["runtimeProgram"]["entities"] = [
        row for row in current["runtimeProgram"]["entities"]
        if row["id"] != original_item["id"]
    ]
    current["runtimeProgram"]["calls"] = [
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] not in removed_call_ids
    ]
    current["runtimeProgram"]["primaryEntityId"] = "workbench_blade"

    report = validate_runtime_program(current)
    assert {row["code"] for row in report["errors"]} == {
        "item_body_count",
        "binding_dependency",
    }
    transaction = RepairTransaction(current, report=report)
    scope = transaction.scope
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    assert scope["create"]["calls"]["allowedTargetKinds"] == ["item_body"]
    assert {"item_stats", "item_use"}.issubset(
        scope["create"]["calls"]["allowedFns"]
    )

    new_item_id = "repaired_item_body"
    repaired_item = copy.deepcopy(original_item)
    repaired_item["id"] = new_item_id
    repaired_calls = []
    for row in original_item_calls:
        if row["fn"] not in {"item_stats", "item_use"}:
            continue
        repaired = copy.deepcopy(row)
        repaired["id"] = "repaired_" + row["id"]
        assert "target" not in repaired  # The exact created sole declaration owns body calls.
        repaired_calls.append(repaired)
    patch = _empty_gameplay_patch()
    patch["entitiesUpsert"] = [repaired_item]
    patch["callsUpsert"] = repaired_calls

    orphan_patch = _empty_gameplay_patch()
    orphan_patch["callsUpsert"] = copy.deepcopy(repaired_calls)
    orphan_filtered, orphan_audit = filter_repair_patch_scope(current, orphan_patch, scope)
    assert not orphan_audit["ok"]
    assert orphan_filtered["callsUpsert"] == []

    repaired, filtered, audit = transaction.apply(patch)

    responses, requests = wire_transport
    responses.append({**patch, "realizationReplacement": copy.deepcopy(repaired["realization"])})
    llm_repaired = gameplay_stage.repair_author_item_after_failure(
        current, {}, {}, "missing-item-body", failure_report=report,
    )
    assert len(requests) == 1 and not responses
    repair_system = requests[0]["messages"][0]["content"]
    assert "create.calls.allowedTargetKinds" in repair_system
    assert "emitted exactly once in entitiesUpsert" in repair_system
    assert validate_runtime_program(llm_repaired)["ok"]


def test_malformed_vfx_repair_output_fails_closed_as_planner_unavailable() -> None:
    current = build_runtime_fixture("workbench_blade")
    previous = vfx_stage_contract.MalformedVfxDirectorOutput("{", "initial malformed JSON")
    report = validate_vfx_director_output(previous, current)
    scope = _build_vfx_repair_scope(previous, report["errors"])
    malformed_patch = vfx_stage_contract.MalformedVfxDirectorOutput("{", "repair truncated")

    with pytest.raises(PlannerUnavailable, match="VFX Repair patch shape rejected"):
        _apply_vfx_repair_patch(current, previous, malformed_patch, scope)


@pytest.mark.parametrize("semantic", [
    pytest.param(False, id="shape-only-canonical-codes"),
    pytest.param(True, id="shape-and-graph-blockers-complete-scope"),
])
def test_author_report_preserves_canonical_shape_and_graph_errors(semantic):
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    next(row for row in program["calls"] if row["id"] == "item_stats")["params"]["damageClass"] = "none"
    if semantic:
        program["primaryEntityId"] = "missing_primary"
        duplicate = copy.deepcopy(program["bindings"][0])
        duplicate["id"] = "duplicate_primary_use"
        duplicate["action"]["targetId"] = "nail"
        program["bindings"].extend([duplicate, _binding_row("wrong_item_spawn", "alternate_use", "spawn_entity", "item")])
        program["entities"].append({"id": "idle_helper", "kind": "temporary_helper"})
        program["bindings"].append(_binding_row("spawn_idle_helper", "hold", "spawn_entity", "idle_helper"))
        program["calls"].append({"id": "invalid_placeable", "fn": "place_tile", "params": {"tileId": -2, "placeStyle": 0}})
    report = authored_item_validation_report(current)
    codes = {row.get("code") for row in report["errors"]}
    assert report["ok"] is False
    assert {"shape_one_of", "shape_pattern"} <= codes
    if not semantic:
        assert all(str(row.get("code") or "").startswith("shape_") for row in report["errors"])
        assert all("kind" not in row for row in report["errors"])
        assert any(row.get("kind") == "pattern" for row in report["shape"]["errors"])
    else:
        assert {"shape_minimum", "invalid_primary_entity_reference", "duplicate_exclusive_input",
                "wrong_binding_target_kind", "entity_not_binding_spawnable", "inert_stationary_entity"} <= codes
        scope = build_runtime_repair_scope(current, report["errors"])
        transaction = scope["repairTransactions"]["primaryEntitySelection"]
        assert transaction["allowed"] is True
        assert transaction["candidateEntityIds"] == ["idle_helper", "item", "nail", "workbench_blade"]
        assert scope["repairTransactions"]["exclusiveInputSelections"] == [{"input": "primary_use", "candidateBindingIds": ["primary_workbench"], "mustKeepExactlyOne": True}]
        call_permissions = {row["id"]: set(row["paths"]) for row in scope["fieldPermissions"]["calls"]}
        assert "params.damageClass" in call_permissions["item_stats"]


def test_visual_repair_freezes_valid_fields_and_ignores_scope_escape() -> None:
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    previous = _visual_kit(data)
    # This test targets a distinct baked entity branch, while the shared fixture
    # correctly defaults non-item rows to reuse_item_icon.
    previous["entities"][1].update({
        "assetMode": "baked_sprite", "visualProjectRef": "entity",
        "prompt": "baked chained door", "silhouette": "chained door",
        "visualIdentity": "door on chain",
        "preferredCanvasSize": 64, "renderSizePx": 48, "forwardAngleDegrees": 0,
    })
    previous["entities"][1]["prompt"] = ""
    del previous["entities"][1]["scale"]
    previous["item"]["prompt"] = "KEEP_VALID_ITEM_PROMPT"
    old_silhouette = previous["entities"][1]["silhouette"]
    entity_ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
    item_id = data["runtimeProgram"]["itemEntityId"]
    _kit, errors = visual_stage_contract._validate_kit(previous, entity_ids, item_id)
    scope = visual_stage_repair_scope._build_visual_repair_scope(previous, errors, entity_ids, item_id)
    fixed_row = copy.deepcopy(previous["entities"][1])
    fixed_row["prompt"] = "fixed chained door"
    fixed_row["scale"] = 1.25
    fixed_row["silhouette"] = "SHOULD_BE_FROZEN"
    unrelated_row = copy.deepcopy(previous["entities"][0])
    unrelated_row["scale"] = 4
    patch = {
        "schema": visual_stage_contract.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": None,
        "entitiesUpsert": [fixed_row, unrelated_row], "entityIdsDelete": [], "entityIndicesDelete": [],
        "animationPlan": "SHOULD_BE_IGNORED", "note": "repair one entity row",
    }
    repaired, audit = visual_stage_repair._apply_visual_repair_patch(previous, patch, scope, entity_ids, return_audit=True)
    assert repaired["item"]["prompt"] == "KEEP_VALID_ITEM_PROMPT"
    assert repaired["entities"][0] == previous["entities"][0]
    assert repaired["entities"][1]["scale"] == 1.25
    assert repaired["entities"][1]["silhouette"] == old_silhouette
    assert repaired["animationPlan"] != "SHOULD_BE_IGNORED"
    assert audit["ignoredChanges"]


@pytest.mark.parametrize("scenario,paths", [
    pytest.param("slot-params", ["duration", "startTick"], id="missing-executable-slot-params-frozen-alpha"),
    pytest.param("root-pair", ["entityId", "event"], id="root-pair-frozen-duration"),
])
def test_vfx_exact_slot_closure_freezes_valid_document(scenario, paths):
    data = _accepted_visual_data("door_on_chain")
    previous = _vfx_output(data)
    slot = previous["slots"][0]
    if scenario == "slot-params":
        slot["duration"] = 999
        del slot["startTick"]
        changes = {"duration": 30, "startTick": 2}
        hostile = {"alpha": 0.1}
    else:
        slot["entityId"] = "missing_entity"
        pair = vfx_director_surface(data)["runtimePairs"][0]
        changes = {"entityId": pair["entityId"], "event": pair["event"]}
        hostile = {"duration": slot["duration"] + 10}
    report = validate_vfx_director_output(previous, data)
    assert not report["ok"]
    scope = _build_vfx_repair_scope(previous, report["errors"])
    permission = next(row for row in scope["fieldPermissions"]["slots"] if row["slotId"] == "slot_0")
    assert permission["paths"] == paths
    if scenario == "slot-params":
        assert scope["fieldPermissions"]["slots"] == [{"slotId": "slot_0", "paths": paths}]
    candidate = {**copy.deepcopy(slot), **changes, **hostile}
    patch = {"schema": VFX_REPAIR_PATCH_SCHEMA,
             "slotsUpsert": [candidate],
             "slotIdsDelete": [], "slotIndicesDelete": [], "note": "repair only diagnosed slot leaves"}
    repaired, audit = _apply_vfx_repair_patch(data, previous, patch, scope, return_audit=True)
    expected = copy.deepcopy(previous)
    expected["slots"][0].update(changes)
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_vfx_director_output(repaired, data)["ok"]
    assert audit["ignoredChanges"]
    if scenario == "root-pair":
        assert any(row["path"].endswith(".duration") for row in audit["ignoredChanges"])


@pytest.mark.parametrize("scenario,fixture,code", [
    pytest.param("set-key", "armor", "missing_set_key", id="armor-exact-set-key"),
    pytest.param("body-set", "armor", "set_bonus_head_only", id="body-only-invalid-modifier-delete"),
    pytest.param("unwanted-binding", "accessory", "binding_dependency", id="equipment-exact-binding-delete"),
    pytest.param("inert-accessory", "accessory", "inert_component", id="accessory-nonzero-executable-effect"),
    pytest.param("collision", "workbench_blade", "event_not_emitted", id="event-existing-collision-parameter"),
    pytest.param("channel", "workbench_blade", "missing_item_capability_param", id="charge-existing-channel-parameter"),
])
def test_scoped_dependency_closure_freezes_entire_document(scenario, fixture, code):
    current = build_runtime_fixture(fixture) if fixture == "workbench_blade" else build_capability_witness(fixture)
    program = current["runtimeProgram"]
    calls = program["calls"]
    owner, field, value = {}, "", None
    if scenario in {"set-key", "body-set"}:
        owner = next(row for row in calls if row["fn"] == "armor")
        owner["params"]["setKey" if scenario == "set-key" else "slot"] = "" if scenario == "set-key" else "body"
        calls.append({"id": "set_damage", "fn": "equipment_damage_bonus",
                      "params": {"phase": "matching_armor_set", "damageClass": "magic", "bonusPercent": 15}})
        field, value = "setKey", "matching_set"
    elif scenario == "unwanted-binding":
        calls.remove(next(row for row in calls if row["id"] == "witness_call"))
    elif scenario == "inert-accessory":
        owner = next(row for row in calls if row["id"] == "witness_call")
        owner["params"] = {name: value if name == "lightColor" else 0 for name, value in owner["params"].items()}
        field, value = "defensePoints", 1
    elif scenario == "collision":
        # Attachment deliberately requires tileCollide=false. Author a freely
        # moving body here so enabling collision is an independent valid edit.
        motion = next(row for row in calls if row["id"] == "workbench_blade_motion")
        motion.update(fn="move_straight")
        motion.pop("params")
        assert validate_runtime_program(current)["ok"]
        owner = next(row for row in calls if row["id"] == "workbench_blade_collision")
        owner["params"]["tileCollide"] = False
        next(row for row in calls if row["id"] == "shed_nails")["params"]["when"] = "on_tile_collision"
        field, value = "tileCollide", True
    else:
        # Beam geometry no longer implies a channel policy. An actual charge
        # input producer retains the exact channel dependency being tested.
        calls.append({"id": "workbench_blade_charge", "fn": "charge",
                      "target": "workbench_blade", "params": {"duration": 0.5}})
        owner = next(row for row in calls if row["id"] == "item_use")
        field, value = "channel", True
    report = validate_runtime_program(current)
    codes = [row["code"] for row in report["errors"]]
    assert code in codes
    if scenario in {"unwanted-binding", "inert-accessory", "channel"}:
        assert codes == [code]
    transaction = RepairTransaction(current, report=report)
    scope = transaction.scope
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    expected = copy.deepcopy(current)
    patch = _empty_gameplay_patch()
    if scenario in {"body-set", "unwanted-binding"}:
        collection, deleted = ("calls", "set_damage") if scenario == "body-set" else ("bindings", "witness_binding")
        key = "callIds" if collection == "calls" else "bindingIds"
        assert deleted in scope["deletable"][key]
        if scenario == "body-set":
            assert owner["id"] not in scope["deletable"][key]
        else:
            assert scope["deletable"][key] == [deleted]
            assert scope["create"]["calls"]["allowedFns"] == ["accessory", "armor"]
        patch[key + "Delete"] = [deleted]
        expected["runtimeProgram"][collection] = [row for row in expected["runtimeProgram"][collection] if row["id"] != deleted]
    else:
        permissions = {row["id"]: row["paths"] for row in scope["fieldPermissions"]["calls"]}
        assert "params." + field in permissions[owner["id"]]
        if scenario == "set-key":
            assert "params.phase" not in permissions.get("set_damage", [])
        elif scenario == "inert-accessory":
            assert scope["deletable"]["callIds"] == ["witness_call"]
        elif scenario == "collision":
            assert owner["id"] in scope["mutable"]["callIds"]
        else:
            assert scope["blockerPlan"]["directCapabilityNames"] == ["item_use"]
            assert scope["create"]["calls"]["allowed"] is False
            assert scope["mutable"]["callIds"] == ["item_use"]
            assert permissions[owner["id"]] == ["params.channel"]
            fragments = runtime_repair_fragments(current, scope)
            assert [row["id"] for row in fragments["broken"]["calls"]] == ["item_use"]
            assert [row["id"] for row in fragments["dependencyContext"]["calls"]] == ["workbench_blade_charge"]
            assert all(row["id"] != "item_stats" for row in fragments["dependencyContext"]["calls"])
            _, incomplete_audit = filter_repair_patch_scope(current, _empty_gameplay_patch(), scope)
            assert not incomplete_audit["ok"]
        fixed = copy.deepcopy(owner)
        fixed["params"][field] = value
        next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == owner["id"])["params"][field] = value
        if scenario == "collision":
            fixed["params"]["bounceCount"] = 1

        patch["callsUpsert"] = [fixed]
    result, filtered, audit = transaction.apply(patch)
    assert json.dumps(result, sort_keys=True) == json.dumps(expected, sort_keys=True), "only the authorized closure may change"
    if scenario == "collision":
        assert any(row["path"].endswith(".params.bounceCount") for row in audit["ignoredChanges"])
    assert validate_runtime_program(result)["ok"]
    compile_runtime_program(result)


@pytest.mark.parametrize("scenario,invalid_choice,message", [
    pytest.param("producer", "missing", "complete exact producer alternative", id="producer-required-model-authored-call"),
    pytest.param("alternative", "unselected", "unselected event alternative", id="unselected-alternative-cannot-smuggle-producer"),
    pytest.param("alternative", "duplicate", "at most one new producer call", id="selected-alternative-single-producer-budget"),
    pytest.param("lifetime", "missing", "leaves a reported repair error open", id="independent-required-component-must-close"),
    pytest.param("binding", "duplicate", "at most one new binding", id="selected-any-of-single-input-root-budget"),
])
def test_selected_event_transaction_closes_exact_support(scenario, invalid_choice, message):
    fixture = {"producer": "door_on_chain", "alternative": "damage_nearby_on_event",
               "lifetime": "damage_nearby_on_event", "binding": "spawn_on_event"}[scenario]
    current = build_runtime_fixture(fixture) if fixture == "door_on_chain" else build_capability_witness(fixture)
    program = current["runtimeProgram"]
    event_call = next(row for row in program["calls"] if row["id"] == ("door_stun" if scenario == "producer" else "witness_call"))
    support_calls, support_bindings = [], []
    chosen_event = "on_hit"
    if scenario == "producer":
        damage = next(row for row in program["calls"] if row["id"] == "chained_door_damage")
        program["calls"].remove(damage)
        support_calls = [damage]
    elif scenario == "alternative":
        next(row for row in program["entities"] if row["id"] == "witness_entity")["kind"] = "temporary_helper"
        program["calls"] = [row for row in program["calls"] if row["id"] != "base_projectile_damage"]
        next(row for row in program["calls"] if row["id"] == "base_projectile_collision")["params"]["tileCollide"] = False
        support_calls = [{"id": "repair_damage", "fn": "projectile_damage", "target": "witness_entity",
                          "params": {"damageClass": "generic", "damage": 20, "knockback": 3.0, "ownerHitCheck": False}}]
    elif scenario == "lifetime":
        lifetime = next(row for row in program["calls"] if row["fn"] == "projectile_lifetime" and row["target"] == event_call["target"])
        program["calls"].remove(lifetime)
        support_calls, chosen_event = [lifetime], "on_expire"
    else:
        root = program["bindings"][0]
        program["bindings"][0] = _binding_row(root["id"], "hold", "spawn_entity", root["action"]["targetId"])
        event_call["target"] = "item"
        support_bindings = [_binding_row("repair_primary_use", "primary_use", "use_item_body", "item")]
        chosen_event = "on_use"
    event_call["params"]["when"] = "equipped" if scenario == "binding" else "on_spawn"
    report = validate_runtime_program(current)
    event_error = next(row for row in report["errors"] if row["code"] == "capability_event_incompatible")
    if scenario == "lifetime":
        assert {"capability_event_incompatible", "missing_required_component"} <= {row["code"] for row in report["errors"]}
    transaction = RepairTransaction(current, report["errors"] if scenario == "lifetime" else [event_error])
    scope = transaction.scope
    if scenario == "producer":
        alternative = scope["eventAlternatives"][0]
        assert alternative["callId"] == "door_stun"
        assert alternative["targetId"] == "chained_door"
        assert {row["event"] for row in alternative["allowed"]} == {"on_hit", "on_crit"}
        assert all(row["requiredCalls"] == [{"fn": "projectile_damage", "targetId": "chained_door", "exactParams": []}] for row in alternative["allowed"])
        assert scope["blockerPlan"]["supportingCapabilityNames"] == ["projectile_damage"]
    fixed = copy.deepcopy(event_call)
    fixed["params"]["when"] = chosen_event
    complete = dict(_empty_gameplay_patch(), callsUpsert=[fixed, *support_calls], bindingsUpsert=support_bindings)
    invalid = copy.deepcopy(complete)
    if invalid_choice == "missing":
        invalid["callsUpsert"] = [fixed]
    elif invalid_choice == "unselected":
        invalid["callsUpsert"][0]["params"]["when"] = "on_expire"
    elif scenario == "binding":
        invalid["bindingsUpsert"].append(_binding_row("repair_alternate_use", "alternate_use", "use_item_body", "item"))
    else:
        invalid["callsUpsert"].append({**copy.deepcopy(support_calls[0]), "id": "repair_damage_duplicate"})
    _, refused = filter_repair_patch_scope(current, invalid, scope)
    assert not refused["ok"]
    assert any(message in row["message"] for row in refused["errors"]), refused
    result, filtered, audit = transaction.apply(complete)
    compile_runtime_program(result)


def _bounded_invalid_buff_calls(fields=("duration",)):
    from infini_local.core.runtime_authoring.program_schema import runtime_program_author_schema
    good = build_capability_witness("native_buff_on_use")
    program = good["runtimeProgram"]
    buff = next(row for row in program["calls"] if row["fn"] == "native_buff_on_use")
    support = [row for row in program["calls"] if row is not buff]
    max_calls = runtime_program_author_schema()["properties"]["calls"]["maxItems"]
    program["calls"] = support + [dict(copy.deepcopy(buff), id=f"buff_{index}") for index in range(max_calls - len(support))]
    invalid = copy.deepcopy(good)
    for row in invalid["runtimeProgram"]["calls"]:
        if row["fn"] == "native_buff_on_use":
            row["params"].update({field: 0 for field in fields})
    return invalid, good


@pytest.mark.parametrize("fields,failure_envelope", [
    pytest.param(("buffId", "duration"), "orchestration", id="all-canonical-leaves-reach-single-repair")
])
def test_bounded_dossier_preserves_all_canonical_errors_without_broad_permissions(failure_envelope, fields):
    from infini_local.pipelines.author.stage import _failure_report

    current, good = _bounded_invalid_buff_calls(fields)
    assert validate_runtime_program(good)["ok"]
    validation = validate_runtime_program(current)
    broken = [row for row in current["runtimeProgram"]["calls"] if row["fn"] == "native_buff_on_use"]
    assert not validation["ok"]
    # Unit projection may add a representability diagnostic at an already
    # shape-invalid leaf. Require complete, exact path coverage, not the old
    # fixed diagnostic multiplicity; the canonical lists below stay byte-exact.
    expected_paths = {
        path for index, row in enumerate(current["runtimeProgram"]["calls"])
        if row["fn"] == "native_buff_on_use"
        for path in [f"$.runtimeProgram.calls[{index}]",
                     *(f"$.runtimeProgram.calls[{index}].params.{field}" for field in fields)]
    }
    assert {row["path"] for row in validation["errors"]} == expected_paths
    failure = {"errors": validation["errors"]} if failure_envelope == "direct" else {"validation": validation}
    if failure_envelope == "orchestration":
        failure = _failure_report(current, ValueError("bounded authored range rejection"), "gameplay_validation_or_compile")
        assert failure["errors"] == validation["errors"], "the canonical failure envelope must not truncate diagnostics"
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, failure_report=failure)
    assert dossier["exactValidationErrors"] == validation["errors"], "one Repair cannot silently drop later canonical diagnostics"
    broken = [row for row in current["runtimeProgram"]["calls"] if row["fn"] == "native_buff_on_use"]
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == sorted(
        [{"id": row["id"], "paths": ["params." + field for field in fields]} for row in broken], key=lambda row: row["id"])
    candidate = copy.deepcopy(good["runtimeProgram"]["calls"])
    candidate[0]["params"]["damage"] = 100
    filtered, audit = filter_repair_patch_scope(current, {"note": "repair every diagnosed duration", "realizationReplacement": good["realization"], "callsUpsert": candidate}, dossier["repairScope"])
    assert audit["ok"] and audit["ignoredChanges"], audit
    assert apply_repair_patch(current, filtered) == good


@pytest.mark.parametrize("identity_tail", [False, True], ids=["shape-only", "author-identity-after-shape"])
def test_strict_author_exception_keeps_all_targets_separate_from_display(identity_tail):
    from infini_local.pipelines.author.stage import _failure_report, strict_validate_authored_item

    current, _ = _bounded_invalid_buff_calls(("buffId", "duration"))
    parent_a, parent_b = {"name": "Parent A"}, {"name": "Parent B"}
    if identity_tail:
        current["name"] = parent_a["name"]
    expected = authored_item_validation_report(current, parent_a, parent_b)["errors"]
    assert len(expected) > 128
    with pytest.raises(PlannerUnavailable) as caught:
        strict_validate_authored_item(current, parent_a, parent_b)
    assert caught.value.author_repair_targets == expected
    assert expected[-1]["message"] not in str(caught.value), "only the human display is truncated"
    failure = _failure_report(current, caught.value, "gameplay_validation_or_compile")
    assert failure["errors"] == expected
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, failure_report=failure)
    assert dossier["exactValidationErrors"] == expected
    if identity_tail:
        assert expected[-1]["code"] == "uncombined_identity"
        assert dossier["repairScope"]["metadataFields"] == ["name"]


def test_complete_author_errors_do_not_override_distinct_downstream_provenance():
    current, _ = _bounded_invalid_buff_calls()
    validation = validate_runtime_program(current)
    downstream = [{"path": "$", "code": "compile_or_wire_rejection", "message": "downstream-only defect"}]
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, failure_report={"errors": downstream, "validation": validation})
    assert dossier["exactValidationErrors"] == downstream
    assert dossier["repairScope"]["nonRepairableErrors"]
    assert all(not paths for paths in dossier["repairScope"]["fieldPermissions"].values())
