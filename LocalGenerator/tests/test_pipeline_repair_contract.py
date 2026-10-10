from __future__ import annotations

import ast
import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import infini_local.pipelines.llm_authoring_pipeline as gameplay_stage
import infini_local.pipelines.visual_generation_pipeline as visual_stage
import infini_local.core.runtime_authoring.repair_scope as repair_scope_stage
import infini_local.core.vfx_manifest as vfx_stage
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope, compile_runtime_program, filter_repair_patch_scope, REPAIR_ERROR_POLICY, REPAIR_VALIDATION_ERROR_CODES, runtime_event_inventory, runtime_repair_fragments, runtime_repair_scope_schema, strict_schema_errors, validate_repair_patch_scope, validate_runtime_program, VALIDATION_ERROR_CODES
from infini_local.core.runtime_authoring.capability_registry import EventBindingRequirement, EventDependencyAlternative, RequirementSpec
from infini_local.core.vfx_manifest import VFX_REPAIR_PATCH_SCHEMA, _apply_vfx_repair_patch, _build_vfx_repair_scope, validate_vfx_director_output, vfx_director_surface
from infini_local.pipelines.combine_validation import authored_item_validation_report
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _binding_row, _binding_transaction, _visual_kit, _accepted_visual_data, _vfx_output, _empty_gameplay_patch

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
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, {}, {}, failure_report=report)
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
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"] is ok, audit
    repaired = apply_repair_patch(current, filtered)
    if ok:
        assert repaired["runtimeProgram"]["primaryEntityId"] == selection
        assert validate_runtime_program(repaired)["ok"]
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
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    if scenario == "retarget-conflict":
        assert filtered["exclusiveInputSelections"] == []
        assert any(e["reason"] == "exclusive_input_conflict_already_resolved" for e in audit["ignoredChanges"])
    else:
        assert filtered["exclusiveInputSelections"] == patch["exclusiveInputSelections"]
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    if scenario.startswith("retarget"):
        moved_id = "duplicate_0" if scenario == "retarget-conflict" else original["id"]
        assert next(e for e in repaired["runtimeProgram"]["bindings"] if e["id"] == moved_id)["input"] == "alternate_use"
    else:
        assert all(e["id"] == original["id"] for e in repaired["runtimeProgram"]["bindings"])


@pytest.mark.parametrize("scenario,ok", [("unknown-kind", True), ("wrong-target", True), ("legacy-row", True), ("cross-product", False)])
def test_binding_alternatives_are_atomic(scenario, ok):
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    accepted = copy.deepcopy(binding)
    if scenario == "unknown-kind":
        binding["usePolicy"]["action"]["kind"] = "not_registered"
    elif scenario == "wrong-target":
        binding["usePolicy"]["action"]["targetId"] = "item"
    elif scenario == "legacy-row":
        binding["action"] = binding["usePolicy"]["action"]["kind"]
        binding["target"] = binding["usePolicy"]["action"]["targetId"]
        binding.pop("usePolicy")
        accepted["usePolicy"]["contactDamage"] = False
    errors = validate_runtime_program(current)["errors"] if scenario != "cross-product" else [{"path": "$.runtimeProgram.bindings[0]", "code": "unsupported_input_action", "message": "exact tuple", "relatedIds": [binding["id"]]}]
    assert errors
    if scenario == "unknown-kind":
        assert any(e["path"].endswith(".usePolicy.action.kind") for e in errors)
    if scenario == "legacy-row":
        assert any(e["code"] == "shape_additional_property" for e in errors)
    scope = build_runtime_repair_scope(current, errors)
    alternatives = next(e["allowed"] for e in scope["bindingAlternatives"] if e["bindingId"] == binding["id"])
    if scenario == "unknown-kind":
        assert binding["id"] in scope["identityChanges"]["bindingActionIds"]
    assert {k: v for k, v in accepted.items() if k != "id"} in alternatives
    assert not any(row["input"] == "hold" and row["usePolicy"]["action"]["kind"] == "use_item_body" for row in alternatives)
    if not ok:
        accepted = _binding_row(binding["id"], "hold", "use_item_body", "item")
    patch = dict(_empty_gameplay_patch(), bindingsUpsert=[accepted])
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"] is ok, audit
    if ok:
        assert filtered["bindingsUpsert"] == [accepted]
        assert all(k not in filtered["bindingsUpsert"][0] for k in ("action", "target"))
        assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]
    else:
        assert any(e.get("code") == "repair_scope_violation" or e.get("kind") in {"additional_property", "one_of", "any_of", "exactly_one"} for e in audit["errors"])


@pytest.mark.parametrize("authorized,candidate_author,expected", [(False, None, "gemini"), (True, None, None), (True, "gpt", "gemini")], ids=["omission-frozen", "authorized-omission-deletes", "authorization-not-rewrite"])
def test_metadata_deletion_authorization(authorized, candidate_author, expected):
    candidate = {"literalSynthesis": "s"}
    if candidate_author is not None:
        candidate["author"] = candidate_author
    result, _, accepted = merge_frozen_subtree({"literalSynthesis": "s", "author": "gemini"}, candidate,
        mutable_paths=("literalSynthesis",), audit_path="$", allow_additions=False,
        delete_paths=("author",) if authorized else ())
    assert result.get("author") == expected
    if expected is None:
        assert "author" not in result and "$.author" in accepted


@pytest.mark.parametrize("field", ["name", "concept"])
def test_metadata_scope_changes_only_reported_field(field):
    current = build_runtime_fixture("workbench_blade")
    if field == "name":
        current["name"] = "Workbench"
        error = {"path": "$.name", "code": "uncombined_identity", "message": "authored name"}
        value = "Workbench Blade"
    else:
        current["concept"]["author"] = "gemini-3.5-flash-lite"
        error = {"path": "$.concept.author", "code": "shape_additional_property", "message": "additional property"}
        value = {k: v for k, v in current["concept"].items() if k != "author"}
    scope = build_runtime_repair_scope(current, [error])
    assert scope["nonRepairableErrors"] == [] and scope["metadataFields"] == [field]
    filtered, audit = filter_repair_patch_scope(current, dict(_empty_gameplay_patch(), metadataPatch={field: value}), scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert repaired[field] == value
    assert "tooltip" not in repaired
    assert repaired["runtimeProgram"] == current["runtimeProgram"]
    if field == "concept":
        assert "author" not in repaired["concept"]
        assert repaired["concept"]["literalSynthesis"] == current["concept"]["literalSynthesis"]


@pytest.mark.parametrize("scenario", ["required-pair", "optional-absence"])
def test_missing_call_leaves_freeze_valid_siblings(scenario):
    current = build_runtime_fixture("workbench_blade")
    use = next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_use")
    original = copy.deepcopy(use)
    use["params"].pop("useStyle")
    use["params"].pop("autoReuse" if scenario == "required-pair" else "customHeldSprite")
    report = validate_runtime_program(current)
    assert not report["ok"]
    scope = build_runtime_repair_scope(current, report["errors"])
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    assert scope["repairRequirements"][0]["repairStrategy"]
    assert scope["repairRequirements"][0]["llmRepairable"] is True
    assert not scope["create"]["entities"]["allowed"]
    assert scope["mutable"]["callIds"] == ["item_use"]
    assert scope["blockerPlan"]["existingBrokenCapabilityNames"] == ["configure_item_use"]
    if scenario == "optional-absence":
        assert next(e["paths"] for e in scope["fieldPermissions"]["calls"] if e["id"] == "item_use") == ["params.useStyle"]
    fixed = copy.deepcopy(use)
    fixed["params"].update(useStyle="shoot", autoReuse=True, handPose="two_handed", customHeldSprite="visible")
    fixed["target"] = "nail"
    unrelated = copy.deepcopy(next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_stats"))
    unrelated["params"]["damage"] = 999
    patch = dict(_empty_gameplay_patch(), callsUpsert=[fixed, unrelated])
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    calls = {c["id"]: c for c in repaired["runtimeProgram"]["calls"]}
    assert calls["item_use"]["params"]["useStyle"] == "shoot"
    assert calls["item_use"]["params"]["autoReuse"] is True
    assert calls["item_use"]["params"]["handPose"] == original["params"]["handPose"]
    assert calls["item_use"]["target"] == original["target"]
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
    scope = build_runtime_repair_scope(current, report["errors"])
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
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert filtered[roster_key + "Delete"] == [permission]
    result = apply_repair_patch(current, filtered)
    assert validate_runtime_program(result)["ok"]
    result_call = next(c for c in result["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert key not in (result_call if scenario == "call-property" else result_call["params"])
    if scenario == "call-property":
        dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, {}, {}, failure_report=report)
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
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["mutable"]["bindingIds"] == []
    assert "requiredRolesByTarget" not in scope["create"]["calls"]
    if scenario == "missing-identity":
        assert not scope["create"]["calls"]["allowed"] and scope["create"]["calls"]["allowedTargetIds"] == []
        return
    assert scope["create"]["calls"]["allowedFns"] == ["configure_item_use"]
    assert scope["create"]["calls"]["allowedTargetIds"] == ["item"]
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
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"] is ok, audit
    if ok:
        assert [c["id"] for c in filtered["callsUpsert"]] == ["repair_item_use"]
        assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]
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


@pytest.mark.parametrize("capability,fixture,kind,target,allowed,retain_binding", [
    pytest.param("configure_tool", "configure_tool", "binding_input_present", "item_body", "primary_use", False, id="ambiguous-item-owner"),
    pytest.param("configure_item_stats", "workbench_blade", "binding_action_present", "same_target", "spawn_entity", False, id="foreign-action-target"),
    pytest.param("configure_item_stats", "workbench_blade", "binding_tuple_present", "same_target", "primary_use|spawn_entity|contactDamage=true", True, id="foreign-existing-tuple-target"),
    pytest.param("configure_tile_placement", "configure_tile_placement", "binding_action_reference", "item_body", "spawn_entity", False, id="non-place-action-reference"),
])
def test_requirement_owner_refuses_foreign_binding_choices(monkeypatch, capability, fixture, kind, target, allowed, retain_binding):
    registry = dict(CAPABILITY_REGISTRY)
    registry[capability] = replace(registry[capability], requirements=(RequirementSpec(kind=kind, target=target, any_of=(allowed,), message="Synthetic exact-owner contract."),))
    monkeypatch.setattr(repair_scope_stage, "CAPABILITY_REGISTRY", registry)
    current = build_runtime_fixture(fixture) if fixture == "workbench_blade" else build_capability_witness(fixture)
    program = current["runtimeProgram"]
    if retain_binding:
        program["bindings"][0]["usePolicy"]["contactDamage"] = False
    else:
        program["bindings"] = []
    if kind == "binding_input_present":
        program["entities"].append({**program["entities"][0], "id": "other_item"})
    call_index, call = next((i, c) for i, c in enumerate(program["calls"]) if c["fn"] == capability)
    scope = build_runtime_repair_scope(current, [{"path": f"$.runtimeProgram.calls[{call_index}]", "code": "missing_binding_dependency", "message": "Synthetic exact-owner contract.", "allowed": [f"binding(input={allowed})" if kind == "binding_input_present" else allowed], "relatedIds": [call["id"], "item"]}])
    requirement = scope["repairRequirements"][0]
    assert requirement["allowedBindingTransactions"] == []
    if kind != "binding_action_reference":
        assert requirement["allowedExistingBindingIds"] == []
    if retain_binding:
        assert "requiredBindingUpdates" not in requirement


@pytest.mark.parametrize("scenario,event_ok", [("placement", False), ("missing-contact", False), ("foreign-target-contact", True), ("no-optional-geometry", True)])
def test_item_event_producer_and_exact_contact_repair(scenario, event_ok):
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    binding = program["bindings"][0]
    binding["usePolicy"]["action"] = {"kind": "use_item_body", "targetId": "item"}
    binding["usePolicy"]["contactDamage"] = scenario == "no-optional-geometry"
    event_call = next(c for c in program["calls"] if c["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_use" if scenario == "placement" else "on_hit"
    if scenario == "placement":
        binding["usePolicy"] = {"action": {"kind": "place_item", "targetId": "item", "placementCallId": "place_bench"}, "stackCost": 1, "contactDamage": False}
        program["calls"].append({"id": "place_bench", "fn": "configure_tile_placement", "target": "item", "params": {"tileId": 18, "placeStyle": 0}})
        event_call["params"]["entity"] = "workbench_blade"
    else:
        program["bindings"].append(_binding_row("projectile_root", "alternate_use" if scenario == "foreign-target-contact" else "hold", "spawn_entity", "workbench_blade", contact_damage=scenario == "foreign-target-contact"))
        if scenario == "no-optional-geometry":
            program["calls"] = [c for c in program["calls"] if c["fn"] != "configure_item_contact_hitbox"]
    report = validate_runtime_program(current)
    if not event_ok:
        assert "event_not_emitted" in {e["code"] for e in report["errors"]}
        if scenario == "placement":
            return
        assert [e["code"] for e in report["errors"]] == ["event_not_emitted"]
        scope = build_runtime_repair_scope(current, report["errors"])
        requirement = next(e for e in scope["repairRequirements"] if e["code"] == "event_not_emitted")
        assert binding["id"] in requirement["allowedExistingBindingIds"]
        assert any(e["usePolicy"]["contactDamage"] is True and e["usePolicy"]["action"]["targetId"] == "item" for e in requirement["allowedBindingTransactions"])
        assert any(e["usePolicy"]["action"]["kind"] == "spawn_entity" and e["usePolicy"]["action"]["targetId"] == "workbench_blade" for e in requirement["allowedBindingTransactions"])
        fixed = copy.deepcopy(binding)
        fixed["usePolicy"]["contactDamage"] = True
        filtered, audit = filter_repair_patch_scope(current, dict(_empty_gameplay_patch(), bindingsUpsert=[fixed]), scope)
        assert audit["ok"] and filtered["bindingsUpsert"] == [fixed]
        current = apply_repair_patch(current, filtered)
    assert validate_runtime_program(current)["ok"]
    compiled = compile_runtime_program(current)
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    pairs = {(e["entityId"], e["event"]) for e in runtime_event_inventory(compiled)}
    assert {(item_id, "on_hit"), (item_id, "on_crit")} <= pairs
    assert any(e["event"] == "on_hit" for e in next(e for e in compiled["runtimeProgram"]["entities"] if e["id"] == item_id)["events"])


@pytest.mark.parametrize("scenario", ["missing-binding", "empty-transaction-catalog", "missing-binding-and-call", "missing-contact", "projected-tool"])
def test_tool_primary_binding_requirement_consumes_registry_transactions(scenario):
    card = next(r.card() for r in CAPABILITY_REGISTRY["configure_tool"].requirements if r.kind == "binding_tuple_present")
    assert card == {
        "kind": "binding_tuple_present", "target": "any_entity",
        "anyOf": ["primary_use|use_item_body|contactDamage=true", "primary_use|spawn_entity"],
        "message": "A configured tool requires one explicit primary-use root matching one listed binding transaction. Tool power remains on the item body; the action root is authored explicitly and no ownership is inferred.",
    }
    current = build_runtime_fixture("workbench_blade") if scenario == "projected-tool" else build_capability_witness("configure_tool")
    program = current["runtimeProgram"]
    if scenario == "projected-tool":
        assert program["bindings"][0]["usePolicy"]["action"]["kind"] == "spawn_entity"
        program["bindings"][0]["usePolicy"]["contactDamage"] = False
        program["calls"].append({"id": "projected_tool_power", "fn": "configure_tool", "target": "item", "params": {"pickPower": 225, "axePowerTooltipPercent": 0, "hammerPower": 0, "miningSpeedScale": 0.75}})
        assert validate_runtime_program(current)["ok"]
        return
    if scenario == "missing-contact":
        program["bindings"][0]["usePolicy"]["contactDamage"] = False
    else:
        program["bindings"] = []
    patch = _empty_gameplay_patch()
    if scenario == "missing-binding-and-call":
        item_use = next(c for c in program["calls"] if c["fn"] == "configure_item_use")
        program["calls"].remove(item_use)
        patch["callsUpsert"] = [item_use]
    report = validate_runtime_program(current)
    assert [e["code"] for e in report["errors"]] == (["missing_capability_dependency", "missing_binding_dependency"] if scenario == "missing-binding-and-call" else ["missing_binding_dependency"])
    scope = build_runtime_repair_scope(current, report["errors"])
    if scenario != "missing-contact":
        assert scope["create"]["bindings"] == {
            "allowed": True, "allowedTargetIds": ["item"], "allowedInputs": ["primary_use"],
            "allowedActions": ["use_item_body"], "requiredTargetIds": ["item"],
            "allowedTransactions": [_binding_transaction("primary_use", "use_item_body", "item", contact_damage=True),
                                    _binding_transaction("primary_use", "use_item_body", "item", stack_cost=1, contact_damage=True)],
            "mustChooseExactlyOne": True,
        }
    if scenario == "missing-binding-and-call":
        assert scope["create"]["calls"]["allowedFns"] == ["configure_item_use"]
    if scenario == "empty-transaction-catalog":
        scope["create"]["bindings"]["allowedTransactions"] = []
        patch["bindingsUpsert"] = [_binding_row("must_not_cross_product", "primary_use", "use_item_body", "item")]
        filtered, audit = filter_repair_patch_scope(current, patch, scope)
        assert filtered["bindingsUpsert"] == []
        assert any(e["reason"] == "binding_transaction_not_in_registry_projection" for e in audit["ignoredChanges"])
        return
    if scenario == "missing-contact":
        binding = copy.deepcopy(program["bindings"][0])
        binding["usePolicy"]["contactDamage"] = True
    else:
        binding = _binding_row("repair_tool_primary", "primary_use", "use_item_body", "item", contact_damage=True)
    patch["bindingsUpsert"] = [binding]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"] and filtered["bindingsUpsert"] == [binding]
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


@pytest.mark.parametrize("scenario", ["foreign-error-identity", "foreign-item-owner"])
def test_planned_capability_support_cannot_cross_requirement_owner(scenario):
    current = build_capability_witness("configure_tool")
    program = current["runtimeProgram"]
    program["bindings"] = []
    program["calls"] = [c for c in program["calls"] if c["fn"] != "configure_item_use"]
    if scenario == "foreign-error-identity":
        source_error = next(e for e in validate_runtime_program(current)["errors"] if e["code"] == "missing_binding_dependency")
        foreign_error = {**copy.deepcopy(source_error), "allowed": ["configure_item_use"], "relatedIds": ["foreign_call", "foreign_target"]}
        scope = build_runtime_repair_scope(current, [source_error, foreign_error])
        requirement = scope["repairRequirements"][0]
    else:
        item = next(e for e in program["entities"] if e["kind"] == "item_body")
        program["entities"].append({**item, "id": "other_item"})
        tool = next(c for c in program["calls"] if c["fn"] == "configure_tool")
        program["calls"].append({**copy.deepcopy(tool), "id": "other_tool", "target": "other_item"})
        errors = validate_runtime_program(current)["errors"]
        item_error = next(e for e in errors if e["code"] == "missing_capability_dependency" and e.get("relatedIds") == ["item"])
        foreign_error = next(e for e in errors if e["code"] == "missing_binding_dependency" and "other_tool" in e.get("relatedIds", []))
        scope = build_runtime_repair_scope(current, [item_error, foreign_error])
        requirement = scope["repairRequirements"][1]
        assert requirement["affectedIds"] == ["other_tool"]
    assert requirement["allowedBindingTransactions"] == []


@pytest.mark.parametrize("scenario,repair,ok", [
    pytest.param("tool", "both", False, id="tool-double-choice"),
    pytest.param("tool", "misaligned", False, id="tool-selection-discards-repaired-lane"),
    pytest.param("tool", "single", True, id="tool-selected-single-choice"),
    pytest.param("contact", "both", False, id="contact-double-choice"),
    pytest.param("contact", "single", True, id="contact-selected-single-lane"),
])
def test_requirement_choice_is_single_and_aligned_with_exclusive_selection(scenario, repair, ok):
    current = build_capability_witness("configure_tool") if scenario == "tool" else build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    original = program["bindings"][0]
    original["usePolicy"]["contactDamage"] = False
    duplicate = copy.deepcopy(original)
    duplicate["id"] = "duplicate_tool_primary" if scenario == "tool" else "alternate_body"
    if scenario == "contact":
        original["usePolicy"]["action"] = {"kind": "use_item_body", "targetId": "item"}
        duplicate["usePolicy"]["action"] = copy.deepcopy(original["usePolicy"]["action"])
        duplicate["input"] = "alternate_use"
        program["bindings"].append(_binding_row("projectile_hold", "hold", "spawn_entity", "workbench_blade"))
        event_call = next(c for c in program["calls"] if c["id"] == "shed_nails")
        event_call["target"] = "item"
        event_call["params"]["event"] = "on_hit"
    program["bindings"].append(duplicate)
    report = validate_runtime_program(current)
    assert [e["code"] for e in report["errors"]] == (["duplicate_exclusive_input", "missing_binding_dependency"] if scenario == "tool" else ["event_not_emitted"])
    scope = build_runtime_repair_scope(current, report["errors"])
    requirement = next(e for e in scope["repairRequirements"] if e["code"] == ("missing_binding_dependency" if scenario == "tool" else "event_not_emitted"))
    assert "requiredBindingUpdates" not in requirement
    assert not requirement.get("mustApplyAll", False)
    assert requirement["mustChooseExactlyOne"] is True
    assert not requirement.get("mustCreateExactlyOne", False)
    if scenario == "tool":
        assert requirement["allowedBindingTransactions"] == [_binding_transaction("primary_use", "use_item_body", "item", contact_damage=True)]
        assert requirement["allowedExistingBindingIds"] == [duplicate["id"], original["id"]]
        assert {e["bindingId"] for e in scope["bindingAlternatives"]} == {original["id"], duplicate["id"]}
        assert scope["repairTransactions"]["exclusiveInputSelections"] == [{"input": "primary_use", "candidateBindingIds": [duplicate["id"], original["id"]], "mustKeepExactlyOne": True}]
    else:
        assert len(requirement["allowedBindingTransactions"]) == 2
    fixed_original, fixed_duplicate = copy.deepcopy(original), copy.deepcopy(duplicate)
    fixed_original["usePolicy"]["contactDamage"] = fixed_duplicate["usePolicy"]["contactDamage"] = True
    patch = dict(_empty_gameplay_patch(), bindingsUpsert=[fixed_original, fixed_duplicate] if repair == "both" else [fixed_original if scenario == "tool" else fixed_duplicate])
    if scenario == "tool":
        patch["exclusiveInputSelections"] = [{"input": "primary_use", "keepBindingId": duplicate["id"] if repair == "misaligned" else original["id"]}]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"] is ok, audit
    if ok:
        repaired = apply_repair_patch(current, filtered)
        assert validate_runtime_program(repaired)["ok"]
        if scenario == "tool":
            assert [e["id"] for e in repaired["runtimeProgram"]["bindings"]] == [original["id"]]
    elif repair == "both":
        assert any("exactly one listed binding transaction" in e["message"] for e in audit["errors"])


def test_missing_tool_binding_dependency_with_occupied_primary_exposes_atomic_move_and_create() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    program["entities"] = [row for row in program["entities"] if row["id"] == "item"]
    program["primaryEntityId"] = "item"
    program["calls"] = [
        row for row in program["calls"] if row["id"] in {"item_stats", "item_use"}
    ] + [
        {"id": "place", "fn": "configure_tile_placement", "target": "item", "params": {"tileId": 1, "placeStyle": 0}},
        {"id": "tool", "fn": "configure_tool", "target": "item", "params": {"pickPower": 100, "axePowerTooltipPercent": 0, "hammerPower": 0, "miningSpeedScale": 1.0}},
    ]
    program["bindings"] = [{
        "id": "primary_place",
        "input": "primary_use",
        "usePolicy": {
            "action": {"kind": "place_item", "targetId": "item", "placementCallId": "place"},
            "stackCost": 1,
            "contactDamage": False,
        },
    }]
    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["missing_binding_dependency"]

    scope = build_runtime_repair_scope(current, report["errors"])
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    alternatives = {row["bindingId"]: row["allowed"] for row in scope["bindingAlternatives"]}
    assert alternatives["primary_place"] == [{
        "input": "alternate_use",
        "usePolicy": {
            "action": {"kind": "place_item", "targetId": "item", "placementCallId": "place"},
            "stackCost": 1,
            "contactDamage": False,
        },
    }]
    primary_create = next(
        row for row in scope["create"]["bindings"]["allowedTransactions"]
        if row["input"] == "primary_use" and row["usePolicy"]["action"]["kind"] == "use_item_body"
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
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    by_id = {row["id"]: row for row in repaired["runtimeProgram"]["bindings"]}
    assert by_id["primary_place"]["input"] == "alternate_use"
    assert by_id["tool_primary"]["input"] == "primary_use"


def test_missing_item_body_scope_allows_required_calls_on_same_created_entity(monkeypatch: pytest.MonkeyPatch) -> None:
    current = build_runtime_fixture("workbench_blade")
    original_item = next(
        copy.deepcopy(row) for row in current["runtimeProgram"]["entities"]
        if row["kind"] == "item_body"
    )
    original_item_calls = [
        copy.deepcopy(row) for row in current["runtimeProgram"]["calls"]
        if row["target"] == original_item["id"]
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
    scope = build_runtime_repair_scope(current, report["errors"])
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    assert scope["create"]["calls"]["allowedTargetKinds"] == ["item_body"]
    assert {"configure_item_stats", "configure_item_use"}.issubset(
        scope["create"]["calls"]["allowedFns"]
    )

    new_item_id = "repaired_item_body"
    repaired_item = copy.deepcopy(original_item)
    repaired_item["id"] = new_item_id
    repaired_calls = []
    for row in original_item_calls:
        if row["fn"] not in {"configure_item_stats", "configure_item_use"}:
            continue
        repaired = copy.deepcopy(row)
        repaired["id"] = "repaired_" + row["id"]
        repaired["target"] = new_item_id
        repaired_calls.append(repaired)
    patch = _empty_gameplay_patch()
    patch["entitiesUpsert"] = [repaired_item]
    patch["callsUpsert"] = repaired_calls

    orphan_patch = _empty_gameplay_patch()
    orphan_patch["callsUpsert"] = copy.deepcopy(repaired_calls)
    orphan_filtered, orphan_audit = filter_repair_patch_scope(current, orphan_patch, scope)
    assert not orphan_audit["ok"]
    assert orphan_filtered["callsUpsert"] == []

    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]

    captured_request: dict[str, Any] = {}
    llm_patch = copy.deepcopy(patch)
    llm_patch["realizationReplacement"] = copy.deepcopy(repaired["realization"])

    def repair_transport(request: dict[str, Any], timeout: int) -> dict[str, Any]:
        captured_request.update(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(llm_patch)}}]}

    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(gameplay_stage, "llm_chat_json", repair_transport)
    llm_repaired = gameplay_stage.repair_author_item_after_failure(
        current, {}, {}, {}, {}, "missing-item-body", failure_report=report,
    )
    repair_system = captured_request["messages"][0]["content"]
    assert "create.calls.allowedTargetKinds" in repair_system
    assert "emitted exactly once in entitiesUpsert" in repair_system
    assert validate_runtime_program(llm_repaired)["ok"]


def test_repair_scope_does_not_mask_same_path_error_for_different_related_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = build_runtime_fixture("workbench_blade")
    stats = next(
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] == "item_stats"
    )
    stats["target"] = "missing_original_item"
    source_report = validate_runtime_program(current)
    source_error = next(
        row for row in source_report["errors"]
        if row["code"] == "missing_entity_reference"
        and row["path"].endswith("calls[0].target")
    )
    scope = build_runtime_repair_scope(current, [source_error])
    fixed = copy.deepcopy(stats)
    fixed["target"] = "item"
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]

    monkeypatch.setattr(
        repair_scope_stage,
        "validate_runtime_program",
        lambda _preview: {
            "ok": False,
            "errors": [{
                "code": source_error["code"],
                "path": source_error["path"],
                "message": "different reference failed at the same list position",
                "relatedIds": ["different_call", "different_missing_item"],
            }],
        },
    )

    _filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert not audit["ok"]
    assert any(
        row.get("message") == "patch introduces a new runtime validation error outside the reported Repair scope"
        and row.get("actual", {}).get("relatedIds") == ["different_call", "different_missing_item"]
        for row in audit["errors"]
    )


def test_malformed_vfx_repair_output_fails_closed_as_planner_unavailable() -> None:
    current = build_runtime_fixture("workbench_blade")
    previous = vfx_stage.MalformedVfxDirectorOutput("{", "initial malformed JSON")
    report = validate_vfx_director_output(previous, current)
    scope = _build_vfx_repair_scope(previous, report["errors"])
    malformed_patch = vfx_stage.MalformedVfxDirectorOutput("{", "repair truncated")

    with pytest.raises(PlannerUnavailable, match="VFX Repair patch shape rejected"):
        _apply_vfx_repair_patch(current, previous, malformed_patch, scope)


def test_author_validation_exposes_only_canonical_shape_codes_to_repair() -> None:
    current = build_runtime_fixture("workbench_blade")
    stats = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    stats["params"]["damageClass"] = "none"

    report = authored_item_validation_report(current)

    assert report["ok"] is False
    assert {"shape_one_of", "shape_pattern"}.issubset({row.get("code") for row in report["errors"]})
    assert all(str(row.get("code") or "").startswith("shape_") for row in report["errors"])
    assert all("kind" not in row for row in report["errors"])
    assert any(row.get("kind") == "pattern" for row in report["shape"]["errors"])


def test_shape_failure_still_exposes_graph_semantic_blockers() -> None:
    current = build_runtime_fixture("workbench_blade")
    stats = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    stats["params"]["damageClass"] = "none"
    current["runtimeProgram"]["primaryEntityId"] = "missing_primary"
    binding = current["runtimeProgram"]["bindings"][0]
    duplicate = copy.deepcopy(binding)
    duplicate["id"] = "duplicate_primary_use"
    duplicate["usePolicy"]["action"]["targetId"] = "nail"
    current["runtimeProgram"]["bindings"].append(duplicate)
    current["runtimeProgram"]["bindings"].append(
        _binding_row("wrong_item_spawn", "alternate_use", "spawn_entity", "item")
    )
    current["runtimeProgram"]["entities"].append({"id": "idle_helper", "kind": "temporary_helper"})
    current["runtimeProgram"]["bindings"].append(
        _binding_row("spawn_idle_helper", "hold", "spawn_entity", "idle_helper")
    )
    current["runtimeProgram"]["calls"].append({
        "id": "invalid_placeable",
        "fn": "configure_tile_placement",
        "target": "item",
        "params": {"tileId": -2, "placeStyle": 0},
    })

    report = authored_item_validation_report(current)
    codes = {row.get("code") for row in report["errors"]}

    assert {"shape_one_of", "shape_pattern", "shape_minimum"}.issubset(codes)
    assert {"invalid_primary_entity_reference", "duplicate_exclusive_input"}.issubset(codes)
    # Invalid tile ID is now a strict scalar-domain failure; the old two-sentinel
    # placement shape no longer contributes an empty-component diagnostic.
    assert {"wrong_binding_target_kind", "entity_not_binding_spawnable", "inert_stationary_entity"}.issubset(codes)

    scope = build_runtime_repair_scope(current, report["errors"])
    transaction = scope["repairTransactions"]["primaryEntitySelection"]
    assert transaction["allowed"] is True
    assert transaction["candidateEntityIds"] == ["idle_helper", "item", "nail", "workbench_blade"]
    assert scope["repairTransactions"]["exclusiveInputSelections"] == [{
        "input": "primary_use",
        "candidateBindingIds": ["primary_workbench"],
        "mustKeepExactlyOne": True,
    }]
    call_permissions = {
        row["id"]: set(row["paths"])
        for row in scope["fieldPermissions"]["calls"]
    }
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
    previous["entities"][0]["prompt"] = "KEEP_VALID_ITEM_PROMPT"
    old_silhouette = previous["entities"][1]["silhouette"]
    entity_ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
    item_id = data["runtimeProgram"]["itemEntityId"]
    _kit, errors = visual_stage._validate_kit(previous, entity_ids, item_id)
    scope = visual_stage._build_visual_repair_scope(previous, errors, entity_ids, item_id)
    fixed_row = copy.deepcopy(previous["entities"][1])
    fixed_row["prompt"] = "fixed chained door"
    fixed_row["scale"] = 1.25
    fixed_row["silhouette"] = "SHOULD_BE_FROZEN"
    unrelated_row = copy.deepcopy(previous["entities"][0])
    unrelated_row["prompt"] = "SHOULD_BE_IGNORED"
    patch = {
        "schema": visual_stage.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": None,
        "entitiesUpsert": [fixed_row, unrelated_row], "entityIdsDelete": [], "entityIndicesDelete": [],
        "animationPlan": "SHOULD_BE_IGNORED", "note": "repair one entity row",
    }
    repaired, audit = visual_stage._apply_visual_repair_patch(previous, patch, scope, entity_ids, return_audit=True)
    assert repaired["entities"][0]["prompt"] == "KEEP_VALID_ITEM_PROMPT"
    assert repaired["entities"][1]["scale"] == 1.25
    assert repaired["entities"][1]["silhouette"] == old_silhouette
    assert repaired["animationPlan"] != "SHOULD_BE_IGNORED"
    assert audit["ignoredChanges"]


def test_vfx_repair_freezes_valid_fields_and_accepts_missing_broken_slot_params() -> None:
    data = _accepted_visual_data("door_on_chain")
    previous = _vfx_output(data)
    previous["slots"][0]["duration"] = 999
    del previous["slots"][0]["fadeOut"]
    old_alpha = previous["slots"][0]["alpha"]
    report = validate_vfx_director_output(previous, data)
    assert not report["ok"]
    scope = _build_vfx_repair_scope(previous, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "slot_0", "paths": ["duration", "fadeOut"]}]
    fixed_slot = copy.deepcopy(previous["slots"][0])
    fixed_slot["duration"] = 30
    fixed_slot["fadeOut"] = 0.6
    fixed_slot["alpha"] = 0.1  # already-valid value must remain frozen
    patch = {
        "schema": VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": 0.2,
        "visualBudgetClass": None, "motif": None,
        "slotsUpsert": [fixed_slot], "slotIdsDelete": [], "slotIndicesDelete": [],
        "note": "repair one slot subtree",
    }
    repaired, audit = _apply_vfx_repair_patch(data, previous, patch, scope, return_audit=True)
    assert validate_vfx_director_output(repaired, data)["ok"]
    assert repaired["slots"][0]["fadeOut"] == 0.6
    assert repaired["slots"][0]["alpha"] == old_alpha
    assert repaired["effectMagnitude"] != 0.2
    assert audit["ignoredChanges"]


def test_event_repair_uses_exact_call_target_despite_foreign_related_producer() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    item = next(row for row in program["entities"] if row["kind"] == "item_body")
    other_item = copy.deepcopy(item)
    other_item["id"] = "other_item"
    program["entities"].append(other_item)
    binding = program["bindings"][0]
    binding["usePolicy"]["action"] = {"kind": "use_item_body", "targetId": "other_item"}
    binding["usePolicy"]["contactDamage"] = False
    event_call = next(row for row in program["calls"] if row["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_use"
    call_index = program["calls"].index(event_call)
    scope = build_runtime_repair_scope(current, [{
        "path": f"$.runtimeProgram.calls[{call_index}].params.event",
        "code": "event_not_emitted",
        "message": "Synthetic exact event target contract.",
        "allowed": [
            "binding input one of: primary_use,alternate_use; "
            "action one of: spawn_entity,use_item_body,apply_item_effects",
        ],
        "relatedIds": ["item", "other_item"],
    }])
    requirement = scope["repairRequirements"][0]
    assert requirement["allowedBindingTransactions"]
    assert {
        row["usePolicy"]["action"]["targetId"]
        for row in requirement["allowedBindingTransactions"]
    } == {"item", "workbench_blade"}
    assert all(
        row["usePolicy"]["action"]["kind"] == "spawn_entity"
        or row["usePolicy"]["action"]["targetId"] == "item"
        for row in requirement["allowedBindingTransactions"]
    )


def test_event_repair_preserves_complete_binding_alternatives_without_cross_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        repair_scope_stage,
        "event_dependency_alternatives",
        lambda _event, _kind: (
            EventDependencyAlternative(required_bindings=(EventBindingRequirement(
                ("primary_use",), ("use_item_body",), False,
            ),)),
            EventDependencyAlternative(required_bindings=(EventBindingRequirement(
                ("alternate_use",), ("apply_item_effects",), False,
            ),)),
        ),
    )
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    program["bindings"] = []
    restore = build_capability_witness("restore_resources_on_use")["runtimeProgram"]["calls"]
    program["calls"].append(copy.deepcopy(next(
        row for row in restore if row["fn"] == "restore_resources_on_use"
    )))
    event_call = next(row for row in program["calls"] if row["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_use"
    call_index = program["calls"].index(event_call)
    scope = build_runtime_repair_scope(current, [{
        "path": f"$.runtimeProgram.calls[{call_index}].params.event",
        "code": "event_not_emitted",
        "message": "Synthetic complete event-alternative contract.",
        "allowed": [
            "binding input one of: primary_use; action one of: use_item_body; contactDamage=false",
            "binding input one of: alternate_use; action one of: apply_item_effects; contactDamage=false",
        ],
        "relatedIds": ["item"],
    }])
    requirement = scope["repairRequirements"][0]
    actual = {
        (
            row["input"],
            row["usePolicy"]["action"]["kind"],
            row["usePolicy"]["contactDamage"],
        )
        for row in requirement["allowedBindingTransactions"]
    }
    assert actual == {
        ("primary_use", "use_item_body", False),
        ("alternate_use", "apply_item_effects", False),
    }


def test_binding_choice_is_owned_by_requirement_specific_existing_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = build_capability_witness("configure_tool")
    program = current["runtimeProgram"]
    original = program["bindings"][0]
    original["usePolicy"]["contactDamage"] = False
    duplicate = copy.deepcopy(original)
    duplicate["id"] = "duplicate_tool_primary"
    unrelated = copy.deepcopy(original)
    unrelated["id"] = "unrelated_mutable_binding"
    unrelated["input"] = "equipped"
    program["bindings"].extend([duplicate, unrelated])

    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    requirement = next(
        row for row in scope["repairRequirements"]
        if row["code"] == "missing_binding_dependency"
    )
    assert requirement["allowedExistingBindingIds"] == [
        duplicate["id"], original["id"],
    ]
    unrelated_alternatives = next(
        row["allowed"] for row in scope["bindingAlternatives"]
        if row["bindingId"] == unrelated["id"]
    )
    copied_transaction = copy.deepcopy(requirement["allowedBindingTransactions"][0])
    assert copied_transaction in unrelated_alternatives

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [{"id": unrelated["id"], **copied_transaction}]
    monkeypatch.setattr(
        repair_scope_stage, "validate_runtime_program",
        lambda _preview: {"ok": True, "errors": []},
    )
    audit = validate_repair_patch_scope(current, patch, scope)
    assert not audit["ok"]
    assert any(
        "outside this requirement's existing binding choices" in row["message"]
        for row in audit["errors"]
    )


def test_create_only_binding_choice_rejects_additional_existing_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = build_capability_witness("configure_tool")
    program = current["runtimeProgram"]
    unrelated = copy.deepcopy(program["bindings"][0])
    unrelated["id"] = "unrelated_mutable_binding"
    unrelated["input"] = "equipped"
    unrelated["usePolicy"]["contactDamage"] = False
    program["bindings"] = [unrelated]

    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    requirement = next(
        row for row in scope["repairRequirements"]
        if row["code"] == "missing_binding_dependency"
    )
    assert requirement["mustCreateExactlyOne"] is True
    assert requirement["allowedExistingBindingIds"] == []
    transaction = copy.deepcopy(requirement["allowedBindingTransactions"][0])
    unrelated_alternatives = next(
        row["allowed"] for row in scope["bindingAlternatives"]
        if row["bindingId"] == unrelated["id"]
    )
    assert transaction in unrelated_alternatives

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [
        {"id": unrelated["id"], **copy.deepcopy(transaction)},
        {"id": "created_tool_lane", **copy.deepcopy(transaction)},
    ]
    monkeypatch.setattr(
        repair_scope_stage, "validate_runtime_program",
        lambda _preview: {"ok": True, "errors": []},
    )
    audit = validate_repair_patch_scope(current, patch, scope)
    assert not audit["ok"]
    assert any(
        "exactly one listed binding transaction" in row["message"]
        for row in audit["errors"]
    )


def test_equipment_set_damage_repair_can_fill_its_declared_set_key() -> None:
    current = build_capability_witness("configure_armor")
    armor = next(row for row in current["runtimeProgram"]["calls"] if row["fn"] == "configure_armor")
    armor["params"]["setKey"] = ""
    current["runtimeProgram"]["calls"].append({
        "id": "set_damage", "fn": "add_equipment_damage_bonus", "target": "item",
        "params": {"phase": "matching_armor_set", "damageClass": "magic", "bonusPercent": 15},
    })
    report = validate_runtime_program(current)
    assert any(row["code"] == "missing_set_key" for row in report["errors"])
    scope = build_runtime_repair_scope(current, report["errors"])
    permissions = {row["id"]: row["paths"] for row in scope["fieldPermissions"]["calls"]}
    assert "params.setKey" in permissions.get(armor["id"], [])
    assert "params.phase" not in permissions.get("set_damage", [])
    fixed = copy.deepcopy(armor)
    fixed["params"]["setKey"] = "matching_set"
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_body_armor_set_damage_repair_can_remove_only_invalid_modifier() -> None:
    current = build_capability_witness("configure_armor")
    armor = next(row for row in current["runtimeProgram"]["calls"] if row["fn"] == "configure_armor")
    armor["params"]["slot"] = "body"
    current["runtimeProgram"]["calls"].append({
        "id": "set_damage", "fn": "add_equipment_damage_bonus", "target": "item",
        "params": {"phase": "matching_armor_set", "damageClass": "magic", "bonusPercent": 15},
    })
    report = validate_runtime_program(current)
    assert any(row["code"] == "set_bonus_head_only" for row in report["errors"])
    scope = build_runtime_repair_scope(current, report["errors"])
    assert "set_damage" in scope["deletable"]["callIds"]
    assert armor["id"] not in scope["deletable"]["callIds"]
    patch = _empty_gameplay_patch()
    patch["callIdsDelete"] = ["set_damage"]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    result = apply_repair_patch(current, filtered)
    assert validate_runtime_program(result)["ok"]
    assert next(row for row in result["runtimeProgram"]["calls"] if row["fn"] == "configure_armor")["params"]["slot"] == "body"


def test_binding_dependency_repair_can_delete_the_exact_unwanted_binding() -> None:
    current = build_capability_witness("configure_accessory")
    current["runtimeProgram"]["calls"] = [
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] != "witness_call"
    ]

    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["binding_dependency"]
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["deletable"]["bindingIds"] == ["witness_binding"]
    assert scope["create"]["calls"]["allowedFns"] == [
        "configure_accessory",
        "configure_armor",
    ]

    patch = _empty_gameplay_patch()
    patch["bindingIdsDelete"] = ["witness_binding"]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_accessory_component_requires_one_nonzero_executable_effect() -> None:
    current = build_capability_witness("configure_accessory")
    accessory = next(
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] == "witness_call"
    )
    accessory["params"] = {
        name: (value if name == "lightColor" else 0)
        for name, value in accessory["params"].items()
    }

    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["inert_component"]
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["deletable"]["callIds"] == ["witness_call"]

    fixed = copy.deepcopy(accessory)
    fixed["params"]["defensePoints"] = 1
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_gameplay_scope_can_fix_existing_dependency_parameter() -> None:
    current = build_runtime_fixture("workbench_blade")
    collision = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_collision")
    collision["params"]["tileCollide"] = False
    event_call = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "shed_nails")
    event_call["params"]["event"] = "on_tile_collision"
    report = validate_runtime_program(current)
    assert any(row["code"] == "event_not_emitted" for row in report["errors"])
    scope = build_runtime_repair_scope(current, report["errors"])
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    assert "workbench_blade_collision" in scope["mutable"]["callIds"]
    fixed = copy.deepcopy(collision)
    fixed["params"]["tileCollide"] = True
    fixed["params"]["bounceCount"] = 1
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"]
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_incompatible_event_repair_requires_model_authored_exact_producer_call() -> None:
    current = build_runtime_fixture("door_on_chain")
    calls = current["runtimeProgram"]["calls"]
    damage = next(row for row in calls if row["id"] == "chained_door_damage")
    current["runtimeProgram"]["calls"] = [
        row for row in calls
        if row["id"] != "chained_door_damage"
    ]
    event_call = next(
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] == "door_stun"
    )
    event_call["params"]["event"] = "on_spawn"
    report = validate_runtime_program(current)
    event_error = next(
        row for row in report["errors"]
        if row["code"] == "capability_event_incompatible"
    )
    scope = build_runtime_repair_scope(current, [event_error])

    transaction = scope["eventAlternatives"][0]
    assert transaction["callId"] == "door_stun"
    assert transaction["targetId"] == "chained_door"
    assert {row["event"] for row in transaction["allowed"]} == {"on_hit", "on_crit"}
    assert all(row["requiredCalls"] == [{
        "fn": "set_projectile_damage",
        "targetId": "chained_door",
        "exactParams": [],
    }] for row in transaction["allowed"])
    assert scope["blockerPlan"]["supportingCapabilityNames"] == ["set_projectile_damage"]

    repaired_event = copy.deepcopy(event_call)
    repaired_event["params"]["event"] = "on_hit"
    incomplete = _empty_gameplay_patch()
    incomplete["callsUpsert"] = [repaired_event]
    _, incomplete_audit = filter_repair_patch_scope(current, incomplete, scope)
    assert not incomplete_audit["ok"]
    assert any("complete exact producer alternative" in row["message"] for row in incomplete_audit["errors"])

    complete = copy.deepcopy(incomplete)
    complete["callsUpsert"].append(damage)
    filtered, audit = filter_repair_patch_scope(current, complete, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]


def test_unselected_event_alternative_cannot_smuggle_its_support_call() -> None:
    current = build_capability_witness("damage_area_on_event")
    program = current["runtimeProgram"]
    next(row for row in program["entities"] if row["id"] == "witness_entity")["kind"] = "temporary_helper"
    program["calls"] = [
        row for row in program["calls"]
        if row["id"] != "base_set_projectile_damage"
    ]
    collision = next(
        row for row in program["calls"]
        if row["id"] == "base_set_projectile_collision"
    )
    collision["params"]["tileCollide"] = False
    event_call = next(row for row in program["calls"] if row["id"] == "witness_call")
    event_call["params"]["event"] = "on_spawn"
    event_error = next(
        row for row in validate_runtime_program(current)["errors"]
        if row["code"] == "capability_event_incompatible"
    )
    scope = build_runtime_repair_scope(current, [event_error])

    damage_call = {
        "id": "repair_damage",
        "fn": "set_projectile_damage",
        "target": "witness_entity",
        "params": {
            "damageClass": "generic",
            "damage": 20,
            "knockback": 3.0,
            "ownerHitCheck": False,
        },
    }
    intrinsic_patch = _empty_gameplay_patch()
    intrinsic_patch["callsUpsert"] = [
        {
            **copy.deepcopy(event_call),
            "params": {**event_call["params"], "event": "on_expire"},
        },
        copy.deepcopy(damage_call),
    ]
    _, intrinsic_audit = filter_repair_patch_scope(current, intrinsic_patch, scope)
    assert not intrinsic_audit["ok"]
    assert any(
        "unselected event alternative" in row["message"]
        for row in intrinsic_audit["errors"]
    )

    hit_patch = _empty_gameplay_patch()
    hit_patch["callsUpsert"] = [
        {
            **copy.deepcopy(event_call),
            "params": {**event_call["params"], "event": "on_hit"},
        },
        damage_call,
    ]
    filtered, hit_audit = filter_repair_patch_scope(current, hit_patch, scope)
    assert hit_audit["ok"], hit_audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]

    duplicate_patch = copy.deepcopy(hit_patch)
    duplicate_call = copy.deepcopy(damage_call)
    duplicate_call["id"] = "repair_damage_duplicate"
    duplicate_patch["callsUpsert"].append(duplicate_call)
    _, duplicate_audit = filter_repair_patch_scope(current, duplicate_patch, scope)
    assert not duplicate_audit["ok"]
    assert any(
        "at most one new producer call" in row["message"]
        for row in duplicate_audit["errors"]
    )


def test_event_repair_must_also_close_independent_required_component() -> None:
    current = build_capability_witness("damage_area_on_event")
    program = current["runtimeProgram"]
    event_call = next(row for row in program["calls"] if row["id"] == "witness_call")
    lifetime = next(
        row for row in program["calls"]
        if row["fn"] == "set_projectile_lifetime" and row["target"] == event_call["target"]
    )
    program["calls"] = [row for row in program["calls"] if row["id"] != lifetime["id"]]
    event_call = next(row for row in program["calls"] if row["id"] == "witness_call")
    event_call["params"]["event"] = "on_spawn"

    report = validate_runtime_program(current)
    assert {
        "capability_event_incompatible",
        "missing_required_component",
    }.issubset({row["code"] for row in report["errors"]})
    scope = build_runtime_repair_scope(current, report["errors"])
    repaired_event = copy.deepcopy(event_call)
    repaired_event["params"]["event"] = "on_expire"

    incomplete = _empty_gameplay_patch()
    incomplete["callsUpsert"] = [repaired_event]
    _, incomplete_audit = filter_repair_patch_scope(current, incomplete, scope)
    assert not incomplete_audit["ok"]
    assert any(
        "leaves a reported repair error open" in row["message"]
        for row in incomplete_audit["errors"]
    )

    complete = _empty_gameplay_patch()
    complete["callsUpsert"] = [repaired_event, lifetime]
    filtered, complete_audit = filter_repair_patch_scope(current, complete, scope)
    assert complete_audit["ok"], complete_audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_selected_event_any_of_binding_adds_exactly_one_input_root() -> None:
    current = build_capability_witness("spawn_entity_on_event")
    program = current["runtimeProgram"]
    program["bindings"][0]["input"] = "hold"
    event_call = next(row for row in program["calls"] if row["id"] == "witness_call")
    event_call["target"] = "item"
    event_call["params"]["event"] = "equipped"
    event_error = next(
        row for row in validate_runtime_program(current)["errors"]
        if row["code"] == "capability_event_incompatible"
    )
    scope = build_runtime_repair_scope(current, [event_error])

    repaired_event = {
        **copy.deepcopy(event_call),
        "params": {**event_call["params"], "event": "on_use"},
    }
    primary_binding = _binding_row("repair_primary_use", "primary_use", "use_item_body", "item")
    alternate_binding = _binding_row("repair_alternate_use", "alternate_use", "use_item_body", "item")
    double_patch = _empty_gameplay_patch()
    double_patch["callsUpsert"] = [repaired_event]
    double_patch["bindingsUpsert"] = [primary_binding, alternate_binding]
    _, double_audit = filter_repair_patch_scope(current, double_patch, scope)
    assert not double_audit["ok"]
    assert any(
        "at most one new binding" in row["message"]
        for row in double_audit["errors"]
    )

    single_patch = _empty_gameplay_patch()
    single_patch["callsUpsert"] = [repaired_event]
    single_patch["bindingsUpsert"] = [primary_binding]
    filtered, single_audit = filter_repair_patch_scope(current, single_patch, scope)
    assert single_audit["ok"], single_audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_gameplay_blocker_extraction_sends_only_direct_and_supporting_capabilities() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["calls"] = [row for row in current["runtimeProgram"]["calls"] if row["id"] != "item_use"]
    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    plan = scope["blockerPlan"]
    assert plan["directCapabilityNames"] == ["configure_item_use"]
    assert plan["supportingCapabilityNames"] == []
    assert scope["capabilitySubset"] == ["configure_item_use"]
    assert scope["create"]["calls"]["allowedFns"] == ["configure_item_use"]
    dossier = gameplay_stage.build_gameplay_repair_dossier(
        current, {}, {}, {}, {}, failure_report=report,
    )
    assert "blockerPlan" not in dossier
    assert dossier["repairScope"]["blockerPlan"] == plan

    movement_case = build_runtime_fixture("workbench_blade")
    movement_case["runtimeProgram"]["calls"] = [
        row for row in movement_case["runtimeProgram"]["calls"]
        if row["id"] != "workbench_blade_motion"
    ]
    movement_report = validate_runtime_program(movement_case)
    movement_scope = build_runtime_repair_scope(movement_case, movement_report["errors"])
    assert "configure_item_stats" not in movement_scope["capabilitySubset"]
    movement_allowed = set(next(row for row in movement_report["errors"] if row["code"] == "missing_movement_component")["allowed"])
    direct = set(movement_scope["blockerPlan"]["directCapabilityNames"])
    # Only one-pass viable blockers are exposed. channel_beam would require
    # changing frozen item-use channel state; charge_then_release still needs
    # another movement driver.
    assert direct < movement_allowed
    assert movement_allowed - direct == {"channel_beam", "charge_then_release"}
    movement_requirement = next(
        row for row in movement_scope["repairRequirements"]
        if row["code"] == "missing_movement_component"
    )
    assert set(movement_requirement["requiredOneOfCapabilities"]) == direct
    assert len(movement_scope["capabilitySubset"]) < len(gameplay_stage.CAPABILITY_REGISTRY)
    assert len(movement_scope["capabilitySubset"]) < len(CAPABILITY_REGISTRY)
    assert set(movement_scope["capabilitySubset"]) == (
        set(movement_scope["blockerPlan"]["directCapabilityNames"])
        | set(movement_scope["blockerPlan"]["supportingCapabilityNames"])
        | set(movement_scope["blockerPlan"]["existingBrokenCapabilityNames"])
    )


def test_gameplay_dependency_blocker_prefers_existing_exact_parameter() -> None:
    current = build_runtime_fixture("workbench_blade")
    controller = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_motion")
    controller["fn"] = "channel_beam"
    controller["params"] = {"rangeTiles": 12.0, "widthPx": 12.0, "warmupTicks": 6}
    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["missing_item_capability_param"]
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["blockerPlan"]["directCapabilityNames"] == ["configure_item_use"]
    assert scope["create"]["calls"]["allowed"] is False
    assert scope["mutable"]["callIds"] == ["item_use"]
    permissions = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == "item_use")
    assert permissions["paths"] == ["params.channel"]
    fragments = runtime_repair_fragments(current, scope)
    assert [row["id"] for row in fragments["broken"]["calls"]] == ["item_use"]
    assert [row["id"] for row in fragments["dependencyContext"]["calls"]] == ["workbench_blade_motion"]
    assert all(row["id"] != "item_stats" for row in fragments["dependencyContext"]["calls"])

    incomplete = _empty_gameplay_patch()
    _, incomplete_audit = filter_repair_patch_scope(current, incomplete, scope)
    assert not incomplete_audit["ok"]

    repaired_item_use = copy.deepcopy(next(
        row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_use"
    ))
    repaired_item_use["params"]["channel"] = True
    complete = _empty_gameplay_patch()
    complete["callsUpsert"] = [repaired_item_use]
    filtered, complete_audit = filter_repair_patch_scope(current, complete, scope)
    assert complete_audit["ok"], complete_audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_vfx_root_pair_error_only_thaws_entity_and_event() -> None:
    data = _accepted_visual_data("door_on_chain")
    previous = _vfx_output(data)
    previous["slots"][0]["entityId"] = "missing_entity"
    old_duration = previous["slots"][0]["duration"]
    report = validate_vfx_director_output(previous, data)
    assert not report["ok"]
    scope = _build_vfx_repair_scope(previous, report["errors"])
    permission = next(row for row in scope["fieldPermissions"]["slots"] if row["slotId"] == "slot_0")
    assert permission["paths"] == ["entityId", "event"]

    pair = vfx_director_surface(data)["runtimePairs"][0]
    candidate = copy.deepcopy(previous["slots"][0])
    candidate["entityId"] = pair["entityId"]
    candidate["event"] = pair["event"]
    candidate["duration"] = old_duration + 10
    patch = {
        "schema": VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": None,
        "visualBudgetClass": None, "motif": None,
        "slotsUpsert": [candidate], "slotIdsDelete": [], "slotIndicesDelete": [],
        "note": "retarget only invalid pair",
    }
    repaired, audit = _apply_vfx_repair_patch(data, previous, patch, scope, return_audit=True)
    assert validate_vfx_director_output(repaired, data)["ok"]
    assert repaired["slots"][0]["duration"] == old_duration
    assert any(row["path"].endswith(".duration") for row in audit["ignoredChanges"])


def test_every_validator_error_has_explicit_repair_policy() -> None:
    validator_path = Path(gameplay_stage.__file__).parents[1] / "core" / "runtime_authoring" / "validator.py"
    tree = ast.parse(validator_path.read_text(encoding="utf-8"))
    emitted: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "ValidationIssue":
            continue
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            emitted.add(node.args[1].value)
    assert emitted == set(VALIDATION_ERROR_CODES)
    assert set(REPAIR_VALIDATION_ERROR_CODES) == set(REPAIR_ERROR_POLICY)
    assert REPAIR_ERROR_POLICY["uncombined_identity"]["strategy"] == "patch_exact_name"
    assert REPAIR_ERROR_POLICY["unknown_registry_requirement"]["llmRepairable"] is False


def _bounded_invalid_buff_calls(fields=("durationTicks",)):
    from infini_local.core.runtime_authoring.program_schema import runtime_program_author_schema
    good = build_capability_witness("apply_vanilla_buff_on_use")
    program = good["runtimeProgram"]
    buff = next(row for row in program["calls"] if row["fn"] == "apply_vanilla_buff_on_use")
    support = [row for row in program["calls"] if row is not buff]
    max_calls = runtime_program_author_schema()["properties"]["calls"]["maxItems"]
    program["calls"] = support + [dict(copy.deepcopy(buff), id=f"buff_{index}") for index in range(max_calls - len(support))]
    invalid = copy.deepcopy(good)
    for row in invalid["runtimeProgram"]["calls"]:
        if row["fn"] == "apply_vanilla_buff_on_use":
            row["params"].update({field: 0 for field in fields})
    return invalid, good


@pytest.mark.parametrize("fields", [("durationTicks",), ("buffId", "durationTicks")], ids=["single-leaf", "saturated-multi-leaf"])
@pytest.mark.parametrize("failure_envelope", ["direct", "nested", "orchestration"])
def test_bounded_dossier_preserves_all_canonical_errors_without_broad_permissions(failure_envelope, fields):
    from infini_local.pipelines.combine_pipeline import _failure_report

    current, good = _bounded_invalid_buff_calls(fields)
    assert validate_runtime_program(good)["ok"]
    validation = validate_runtime_program(current)
    broken = [row for row in current["runtimeProgram"]["calls"] if row["fn"] == "apply_vanilla_buff_on_use"]
    assert not validation["ok"]
    assert len(validation["errors"]) == len(broken) * (len(fields) + 1), "complete canonical shape errors must reach every bounded leaf"
    failure = {"errors": validation["errors"]} if failure_envelope == "direct" else {"validation": validation}
    if failure_envelope == "orchestration":
        failure = _failure_report(current, ValueError("bounded authored range rejection"), "gameplay_validation_or_compile")
        assert failure["errors"] == validation["errors"], "the canonical failure envelope must not truncate diagnostics"
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, {}, {}, failure_report=failure)
    assert dossier["exactValidationErrors"] == validation["errors"], "one Repair cannot silently drop later canonical diagnostics"
    broken = [row for row in current["runtimeProgram"]["calls"] if row["fn"] == "apply_vanilla_buff_on_use"]
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == sorted(
        [{"id": row["id"], "paths": ["params." + field for field in fields]} for row in broken], key=lambda row: row["id"])
    candidate = copy.deepcopy(good["runtimeProgram"]["calls"])
    candidate[0]["params"]["damage"] = 100
    filtered, audit = filter_repair_patch_scope(current, {"note": "repair every diagnosed duration", "realizationReplacement": good["realization"], "callsUpsert": candidate}, dossier["repairScope"])
    assert audit["ok"] and audit["ignoredChanges"], audit
    assert apply_repair_patch(current, filtered) == good


@pytest.mark.parametrize("consumer", ["shape", "runtime", "author", "parsed-author", "dossier"])
@pytest.mark.parametrize("damage", ["oversized-list", "extra-members", "deep-container", "cyclic-container", "oversized-text"])
def test_author_input_work_guard_precedes_validation_copy_and_repair(consumer, damage):
    from infini_local.core.runtime_authoring import program_schema

    class UninspectedList(list):
        def __iter__(self):
            raise AssertionError("oversized array must be refused before enumeration")

        def __deepcopy__(self, memo):
            raise AssertionError("oversized array must be refused before copying")

    class UninspectedDict(dict):
        def __iter__(self):
            raise AssertionError("oversized object must be refused before enumeration")

        def items(self):
            raise AssertionError("oversized object must be refused before enumeration")

        def __deepcopy__(self, memo):
            raise AssertionError("oversized object must be refused before copying")

    current = build_runtime_fixture("workbench_blade")
    nodes, depth, width, _ = program_schema._author_schema_work_bounds(program_schema.author_item_response_schema())
    if damage == "oversized-list":
        current["runtimeProgram"]["calls"] = UninspectedList([None] * (nodes + 1))
    elif damage == "extra-members":
        current["runtimeProgram"]["calls"][0]["params"] = UninspectedDict({f"extra_{i}": 0 for i in range(nodes + 1)})
    elif damage == "oversized-text":
        current["realization"]["description"] = "x" * (nodes * width + 1)
    else:
        value = {}
        if damage == "cyclic-container":
            value["cycle"] = value
        else:
            for _ in range(depth + 1):
                value = {"nested": value}
        current["runtimeProgram"]["calls"][0]["params"]["unknown"] = value
    consume = {
        "shape": program_schema.strict_author_shape_report,
        "runtime": validate_runtime_program,
        "author": authored_item_validation_report,
        "parsed-author": gameplay_stage._prepare_parsed_author_item,
        "dossier": lambda value: gameplay_stage.build_gameplay_repair_dossier(
            value, {}, {}, {}, {}, failure_report={"errors": [{"path": "$", "code": "compile_or_wire_rejection", "message": "guard before fragments"}]}),
    }[consumer]
    with pytest.raises(RuntimeError, match="Author input exceeds schema-derived work bounds"):
        consume(current)


def test_maximal_author_schema_shape_keeps_worst_branch_and_report_tail():
    from infini_local.core.runtime_authoring import program_schema

    schema = program_schema.author_item_response_schema()
    program_schema_properties = schema["properties"]["runtimeProgram"]["properties"]
    branches = program_schema_properties["calls"]["items"]["oneOf"]
    worst = max(branches, key=lambda branch: len(branch["properties"]["params"]["properties"]))
    fn = worst["properties"]["fn"]["const"]
    good = build_capability_witness(fn)
    call = next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == fn)
    for key, spec in CAPABILITY_REGISTRY[fn].params.items():
        if key not in call["params"]:
            call["params"][key] = ({child: leaf.enum[0] if leaf.enum else leaf.neutral for child, leaf in spec.properties.items()}
                                   if spec.properties else spec.enum[0] if spec.enum else spec.neutral)
    assert set(call["params"]) == set(worst["properties"]["params"]["properties"])
    program = good["runtimeProgram"]
    for namespace, source in (("calls", call), ("entities", program["entities"][0]), ("bindings", program["bindings"][0])):
        program[namespace] = [dict(copy.deepcopy(source), id=f"max_{namespace}_{index}") for index in range(program_schema_properties[namespace]["maxItems"])]
    concept_schema = schema["properties"]["concept"]["properties"]["plannedPlayerActions"]
    good["concept"]["plannedPlayerActions"] = [{"input": "primary_use", "intent": "bounded sketch"} for _ in range(concept_schema["maxItems"])]
    evaluation_schema = schema["properties"]["realization"]["properties"]["selfEvaluation"]["properties"]
    for section, checks in (("planVsProgram", "actionChecks"), ("programVsReport", "behaviorChecks")):
        rows_schema = evaluation_schema[section]["properties"][checks]
        row = good["realization"]["selfEvaluation"][section][checks][0]
        row["runtimeRefs"] = ["bounded_ref"] * rows_schema["items"]["properties"]["runtimeRefs"]["maxItems"]
        good["realization"]["selfEvaluation"][section][checks] = [copy.deepcopy(row) for _ in range(rows_schema["maxItems"])]
    good = {key: good[key] for key in schema["properties"]}
    # This is a maximal strict-shape control, not a semantically valid graph:
    # repeating singleton components deliberately isolates diagnostic collection.
    assert program_schema.strict_author_shape_report(good)["ok"]
    current = copy.deepcopy(good)
    for row in current["runtimeProgram"]["calls"]:
        row["params"] = {key: "bad" for key in row["params"]}
    for section, checks in (("planVsProgram", "actionChecks"), ("programVsReport", "behaviorChecks")):
        for row in current["realization"]["selfEvaluation"][section][checks]:
            row["runtimeRefs"] = [0] * len(row["runtimeRefs"])
    expected = strict_schema_errors(current, schema, limit=len(json.dumps(current)))
    assert len(expected) > 1024, "do not replace 128 with another guessed prefix"
    report = program_schema.strict_author_shape_report(current)
    assert report["errors"] == expected
    last_check = evaluation_schema["programVsReport"]["properties"]["behaviorChecks"]["maxItems"] - 1
    last_ref = evaluation_schema["programVsReport"]["properties"]["behaviorChecks"]["items"]["properties"]["runtimeRefs"]["maxItems"] - 1
    tail_path = f"$.realization.selfEvaluation.programVsReport.behaviorChecks[{last_check}].runtimeRefs[{last_ref}]"
    assert report["errors"][-1]["path"] == tail_path
    canonical = validate_runtime_program(current)["errors"]
    shape_errors = [row for row in canonical if row["code"].startswith("shape_")]
    assert [(row["path"], row["code"]) for row in shape_errors] == [(row["path"], "shape_" + row["kind"]) for row in expected]
    assert authored_item_validation_report(current)["errors"] == canonical
    assert strict_schema_errors(current, schema) == expected[:128]
    assert strict_schema_errors(current, schema, limit=7) == expected[:7]
    assert strict_schema_errors(current, schema, limit=0) == []


@pytest.mark.parametrize("identity_tail", [False, True], ids=["shape-only", "author-identity-after-shape"])
def test_strict_author_exception_keeps_all_targets_separate_from_display(identity_tail):
    from infini_local.pipelines.combine_pipeline import _failure_report
    from infini_local.pipelines.combine_validation import strict_validate_authored_item

    current, _ = _bounded_invalid_buff_calls(("buffId", "durationTicks"))
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
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, {}, {}, failure_report=failure)
    assert dossier["exactValidationErrors"] == expected
    if identity_tail:
        assert expected[-1]["code"] == "uncombined_identity"
        assert dossier["repairScope"]["metadataFields"] == ["name"]


def test_complete_author_errors_do_not_override_distinct_downstream_provenance():
    current, _ = _bounded_invalid_buff_calls()
    validation = validate_runtime_program(current)
    downstream = [{"path": "$", "code": "compile_or_wire_rejection", "message": "downstream-only defect"}]
    dossier = gameplay_stage.build_gameplay_repair_dossier(current, {}, {}, {}, {}, failure_report={"errors": downstream, "validation": validation})
    assert dossier["exactValidationErrors"] == downstream
    assert dossier["repairScope"]["nonRepairableErrors"]
    assert all(not paths for paths in dossier["repairScope"]["fieldPermissions"].values())


def test_gameplay_repair_dossier_matches_blocker_subset_and_is_not_full_author_prompt() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["calls"] = [
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] != "workbench_blade_motion"
    ]
    validation = validate_runtime_program(current)
    parents = ({"name": "Workbench"}, {"name": "Sword"})
    facts = ({"facts": ["literal workbench"]}, {"facts": ["metal blade"]})
    dossier = gameplay_stage.build_gameplay_repair_dossier(
        current, parents[0], parents[1], facts[0], facts[1],
        failure_report={"stage": "runtime_program_validation", "errors": validation["errors"]},
    )
    repair_rules = " ".join(dossier["rules"])
    assert "Every upsert entry must be a complete schema-valid node" in repair_rules
    assert "id, fn, target, and the complete params object" in repair_rules
    required_shape = dossier["requiredJsonShape"]
    assert not any(key in dossier for key in ("brokenFragments", "brokenFragmentsByIndex", "validDependencyFragments"))
    assert set(dossier["readOnlySourceFragments"]) == {
        "brokenFragments", "brokenFragmentsByIndex", "validDependencyFragments",
    }
    assert "claimsUpsert" not in required_shape
    assert "claimIdsDelete" not in required_shape
    assert set(required_shape["callsUpsert"][0]) == {"id", "fn", "target", "params"}
    card_fns = {
        card["fn"]
        for key in ("blockerCapabilities", "supportingCapabilities", "existingBrokenCapabilityCards")
        for card in dossier[key]
    }
    assert card_fns == set(dossier["repairScope"]["capabilitySubset"])
    assert len(card_fns) == 20
    assert "channel_beam" not in card_fns
    assert "charge_then_release" not in card_fns
    _, author_payload, _ = gameplay_stage.build_initial_author_request(
        parents[0], parents[1], facts[0], facts[1], "repair-audit", model_name="test-model",
    )
    repair_payload = json.dumps(dossier, ensure_ascii=False, separators=(",", ":"))
    assert len(repair_payload) < len(author_payload) / 2
    from infini_local.pipelines.llm_authoring_prompt import realization_execution_truth_for_llm, runtime_units_for_llm
    assert dossier["runtimeExecutionTruth"] == {
        **realization_execution_truth_for_llm(), "units": runtime_units_for_llm(),
    }
    author = json.loads(author_payload)
    assert "selfEvaluation" in author["diagnosticReport"]
    assert "on_expire" in next(row for row in author["runtimeCapabilityContract"]["catalog"]["events"] if row["event"] == "on_expire")["constructionMeaning"]
    assert "interpretation of the exact post-merge program, not an observed run" in repair_rules
    assert "rebuild selfEvaluation.planVsProgram and selfEvaluation.programVsReport" in repair_rules
    assert set(dossier["acceptedItemContext"]) == {"name", "category", "realization", "concept", "runtimeProgram"}
    assert dossier["acceptedItemContext"]["concept"] == current["concept"]
    assert dossier["acceptedItemContext"]["runtimeProgram"] == current["runtimeProgram"]


def test_initial_author_packet_places_unchanged_contract_before_recipe_specific_facts() -> None:
    _, first, _ = gameplay_stage.build_initial_author_request(
        {"name": "Workbench"}, {"name": "Sword"},
        {"name": "Workbench", "facts": ["wood"]},
        {"name": "Sword", "facts": ["blade"]},
        "workbench+sword", model_name="test-model",
    )
    _, second, _ = gameplay_stage.build_initial_author_request(
        {"name": "Lens"}, {"name": "Bird"},
        {"name": "Lens", "facts": ["glass"]},
        {"name": "Bird", "facts": ["feather"]},
        "lens+bird", model_name="test-model",
    )

    common_prefix = 0
    for left, right in zip(first, second):
        if left != right:
            break
        common_prefix += 1
    assert common_prefix > 65_000

    payload = json.loads(first)
    assert list(payload).index("runtimeCapabilityContract") < list(payload).index("recipeKey")
    assert "balanceCorridor" not in payload["runtimeCapabilityContract"]
    assert "primaryEntityOwnership" in payload["runtimeProgramInvariants"]
    assert "primaryEntitySelection" not in payload["runtimeProgramInvariants"]
    assert list(payload)[-2:] == ["balanceCorridor", "sourceWireUnits"]
