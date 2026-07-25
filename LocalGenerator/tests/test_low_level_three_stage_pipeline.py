from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from collections.abc import Callable

import pytest

import infini_local.pipelines.llm_authoring_pipeline as gameplay_stage
import infini_local.pipelines.visual_generation_pipeline as visual_stage
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    REPAIR_ERROR_POLICY,
    runtime_repair_fragments,
    runtime_repair_scope_schema,
    strict_schema_errors,
    validate_repair_patch_scope,
    validate_runtime_program,
    VALIDATION_ERROR_CODES,
)
from infini_local.core.vfx_manifest import (
    VFX_DIRECTOR_SCHEMA,
    VFX_REPAIR_PATCH_SCHEMA,
    _apply_vfx_repair_patch,
    _build_vfx_repair_scope,
    attach_hybrid_vfx_manifest,
    validate_vfx_director_output,
    vfx_director_surface,
)
from infini_local.pipelines.combine_pipeline import _assert_stage_topology
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _visual_kit(data: dict) -> dict:
    entities = data["runtimeProgram"]["entities"]
    item_id = data["runtimeProgram"]["itemEntityId"]
    return {
        "schema": visual_stage.VISUAL_KIT_SCHEMA,
        "item": {
            "prompt": "literal Terraria item", "negativePrompt": "placeholder",
            "silhouette": "readable", "visualIdentity": "literal composition",
            "palette": ["brown", "steel"], "preferredCanvasSize": 32,
            "inventoryScale": 1.0, "worldScale": 1.0,
        },
        "entities": [
            {
                "entityId": row["id"], "assetMode": "baked_sprite" if row["id"] == item_id else "reuse_item_icon",
                "prompt": f"literal {row['id']}", "silhouette": "readable", "visualIdentity": row["id"], "scale": 1.0,
            }
            for row in entities
        ],
        "animationPlan": "Follow exact runtime movement.",
    }


def _visual_patch(data: dict) -> dict:
    kit = _visual_kit(data)
    return {
        "schema": visual_stage.VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": kit["item"],
        "entitiesUpsert": kit["entities"],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "animationPlan": None,
        "note": "repair only invalid item and missing entity rows",
    }


def _vfx_output(data: dict) -> dict:
    pair = vfx_director_surface(data)["runtimePairs"][0]
    return {
        "schema": VFX_DIRECTOR_SCHEMA,
        "effectMagnitude": 0.5,
        "visualBudgetClass": "normal",
        "motif": {"element": "metal", "shapeLanguage": "sparks", "motionLanguage": "short wake", "paletteRole": "accent", "rhythm": 1.0, "chaos": 0.2},
        "slots": [{
            "id": "slot_0", "entityId": pair["entityId"], "event": pair["event"],
            "rendererKind": "projectileAfterimage", "backend": "Realtime",
            "textureRole": "entity", "particleRole": "none", "anchor": "self",
            "channel": "motionTrail", "lane": "primary", "emissionMode": "wake",
            "blend": "alpha", "particleSystemId": "none", "scale": 1.0,
            "density": 0.4, "duration": 20, "alpha": 0.8, "spread": 0.1,
            "jitter": 0.1, "fadeIn": 0.1, "fadeOut": 0.4, "budgetWeight": 1.0,
            "signatureWeight": 0.4, "visualCost": 0.3, "startTick": 0, "repeatEvery": 0,
        }],
    }


def test_happy_path_is_one_gameplay_one_visual_one_vfx_zero_repairs(monkeypatch: pytest.MonkeyPatch) -> None:
    authored = build_runtime_fixture("workbench_blade")
    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(gameplay_stage, "llm_chat_json", lambda *_args, **_kwargs: {"choices": [{"message": {"content": json.dumps(authored)}}]})
    planned = gameplay_stage.try_llm_plan({"name": "A"}, {"name": "B"}, {"name": "A"}, {"name": "B"}, "a+b")
    assert planned is not None
    assert planned["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] == 1

    compiled = compile_runtime_program(planned)
    compiled["debug"] = copy.deepcopy(planned["debug"])
    monkeypatch.setattr(visual_stage, "USE_LLM", True)
    monkeypatch.setattr(visual_stage, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(visual_stage, "_request_visual_kit", lambda data, *_args, **_kwargs: _visual_kit(data))
    visual = visual_stage.apply_visual_director(compiled, {}, {}, {}, {})
    assert visual["debug"]["llmStageAccounting"]["visualDirectorCalls"] == 1
    assert visual["debug"]["llmStageAccounting"]["visualRepairCalls"] == 0

    calls = 0
    def director(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _vfx_output(visual)
    final = attach_hybrid_vfx_manifest(visual, "a+b", llm_director=director)
    assert calls == 1
    assert final["debug"]["llmStageAccounting"] == {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 0,
        "visualDirectorCalls": 1, "visualRepairCalls": 0,
        "vfxDirectorCalls": 1, "vfxRepairCalls": 0,
    }
    _assert_stage_topology(final)


def test_visual_and_vfx_repairs_are_conditional_and_local(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    compiled["debug"] = {"planner": "llm_low_level_runtime_author", "llmStageAccounting": {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 0, "visualDirectorCalls": 0,
        "visualRepairCalls": 0, "vfxDirectorCalls": 0, "vfxRepairCalls": 0,
    }}
    monkeypatch.setattr(visual_stage, "USE_LLM", True)
    monkeypatch.setattr(visual_stage, "VISUAL_DIRECTOR_LLM", True)
    responses = iter([
        {"schema": visual_stage.VISUAL_KIT_SCHEMA, "item": {}, "entities": [], "animationPlan": "already valid animation"},
        _visual_patch(compiled),
    ])
    monkeypatch.setattr(visual_stage, "_request_visual_kit", lambda *_args, **_kwargs: next(responses))
    visual = visual_stage.apply_visual_director(compiled, {}, {}, {}, {})
    assert visual["debug"]["llmStageAccounting"]["visualDirectorCalls"] == 1
    assert visual["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1
    assert visual["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] == 1
    assert visual["visualKit"]["animationPlan"] == "already valid animation"

    bad_vfx = _vfx_output(visual)
    bad_vfx["effectMagnitude"] = 2.0
    vfx_patch = {
        "schema": VFX_REPAIR_PATCH_SCHEMA,
        "effectMagnitude": 0.5,
        "visualBudgetClass": None,
        "motif": None,
        "slotsUpsert": [],
        "slotIdsDelete": [],
        "slotIndicesDelete": [],
        "note": "repair only magnitude",
    }
    vfx_responses = iter([bad_vfx, vfx_patch])
    calls = 0

    def director(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return next(vfx_responses)

    final = attach_hybrid_vfx_manifest(visual, "door", llm_director=director)
    assert calls == 2
    assert final["debug"]["llmStageAccounting"]["vfxDirectorCalls"] == 1
    assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert final["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1
    assert final["vfxManifest"]["slots"][0]["id"] == bad_vfx["slots"][0]["id"]


def test_gameplay_repair_runs_only_after_exact_validator_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    current = build_runtime_fixture("workbench_blade")
    current["debug"] = {"llmStageAccounting": {"gameplayAuthorCalls": 1}}
    current["runtimeProgram"]["bindings"].append({"id": "bad_primary", "input": "primary_use", "action": "spawn_entity", "target": "nail"})
    failure = {"stage": "strict_author_validation", "errors": [{"path": "$.runtimeProgram.bindings[1].input", "code": "duplicate_exclusive_input", "message": "duplicate"}]}
    patch = {
        "entitiesUpsert": [], "entityIdsDelete": [], "bindingsUpsert": [],
        "bindingIdsDelete": ["bad_primary"], "callsUpsert": [], "callIdsDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "metadataPatch": {}, "note": "remove only duplicate binding",
    }
    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(gameplay_stage, "llm_chat_json", lambda *_args, **_kwargs: {"choices": [{"message": {"content": json.dumps(patch)}}]})
    repaired = gameplay_stage.repair_author_item_after_failure(current, {}, {}, {}, {}, "key", failure_report=failure)
    assert all(row["id"] != "bad_primary" for row in repaired["runtimeProgram"]["bindings"])
    assert repaired["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1
    assert repaired["debug"]["llmStageAccounting"]["visualDirectorCalls"] == 0


def _empty_gameplay_patch() -> dict:
    return {
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "bindingsUpsert": [], "bindingIdsDelete": [], "bindingIndicesDelete": [],
        "callsUpsert": [], "callIdsDelete": [], "callIndicesDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "claimIndicesDelete": [],
        "metadataPatch": {}, "note": "targeted repair",
    }


def test_gameplay_scope_freezes_old_values_and_accepts_missing_parameters_in_broken_call() -> None:
    current = build_runtime_fixture("workbench_blade")
    item_use = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_use")
    old_hand_pose = item_use["params"]["handPose"]
    old_release_timing = item_use["params"]["releaseTiming"]
    old_target = item_use["target"]
    del item_use["params"]["useStyle"]
    del item_use["params"]["autoReuse"]
    report = validate_runtime_program(current)
    assert not report["ok"]
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["mutable"]["callIds"] == ["item_use"]
    assert scope["blockerPlan"]["existingBrokenCapabilityNames"] == ["configure_item_use"]

    fixed = copy.deepcopy(item_use)
    fixed["params"]["useStyle"] = "shoot"
    fixed["params"]["autoReuse"] = True
    fixed["params"]["handPose"] = "two_handed"  # valid old value must remain frozen
    fixed["target"] = "nail"  # structural rewrite must remain frozen
    unrelated = copy.deepcopy(next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats"))
    unrelated["params"]["damage"] = 999
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed, unrelated]

    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    repaired_use = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_use")
    assert repaired_use["params"]["useStyle"] == "shoot"
    assert repaired_use["params"]["autoReuse"] is True
    assert repaired_use["params"]["releaseTiming"] == "immediate"
    assert repaired_use["params"]["handPose"] == old_hand_pose
    assert repaired_use["target"] == old_target
    repaired_stats = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    assert repaired_stats["params"]["damage"] != 999


def test_gameplay_repair_prompt_omits_full_valid_nodes_but_keeps_read_only_index(monkeypatch: pytest.MonkeyPatch) -> None:
    current = build_runtime_fixture("workbench_blade")
    next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats")["params"]["damage"] = 1999
    item_use = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_use")
    del item_use["params"]["useStyle"]
    failure = {"stage": "strict_author_validation", "errors": validate_runtime_program(current)["errors"]}
    fixed = copy.deepcopy(item_use)
    fixed["params"]["useStyle"] = "shoot"
    fixed["params"]["releaseTiming"] = "on_release"
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]
    captured: dict = {}

    def fake_chat(request, **_kwargs):
        captured.update(request)
        return {"choices": [{"message": {"content": json.dumps(patch)}}]}

    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(gameplay_stage, "llm_chat_json", fake_chat)
    repaired = gameplay_stage.repair_author_item_after_failure(current, {}, {}, {}, {}, "key", failure_report=failure)
    assert validate_runtime_program(repaired)["ok"]
    prompt = captured["messages"][1]["content"]
    assert '"currentItem"' not in prompt
    assert '"item_use"' in prompt
    assert '"item_stats"' in prompt  # compact immutable index
    assert '1999' not in prompt  # full valid item_stats params were not resent


def test_visual_repair_freezes_valid_fields_and_ignores_scope_escape() -> None:
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    previous = _visual_kit(data)
    previous["entities"][1]["prompt"] = ""
    del previous["entities"][1]["scale"]
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
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    previous = _vfx_output(data)
    previous["slots"][0]["duration"] = 999
    del previous["slots"][0]["fadeOut"]
    old_alpha = previous["slots"][0]["alpha"]
    report = validate_vfx_director_output(previous, data)
    assert not report["ok"]
    scope = _build_vfx_repair_scope(previous, report["errors"])
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


def test_gameplay_scope_allows_only_exact_missing_dependency_creation() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["calls"] = [row for row in current["runtimeProgram"]["calls"] if row["id"] != "item_use"]
    for claim in current["runtimeContract"]["claims"]:
        claim["backedBy"] = [row_id for row_id in claim["backedBy"] if row_id != "item_use"]
    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["binding_dependency"]
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["mutable"]["bindingIds"] == []
    assert scope["create"]["calls"]["allowedFns"] == ["configure_item_use"]
    assert scope["create"]["calls"]["allowedTargetIds"] == ["item"]

    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [{
        "id": "repair_item_use", "fn": "configure_item_use", "role": "primary", "target": "item",
        "params": {
            "useStyle": "shoot", "autoReuse": True, "useTurn": True,
            "hideUseGraphic": False, "disableMeleeHitbox": True, "channel": False,
            "holdoutOffsetX": 0, "holdoutOffsetY": 0,
            "handPose": "one_handed", "releaseTiming": "immediate",
        },
    }]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"]
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]

    wrong = copy.deepcopy(patch)
    wrong_call = copy.deepcopy(next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats"))
    wrong_call["id"] = "wrong_dependency"
    wrong["callsUpsert"] = [wrong_call]
    filtered_wrong, wrong_audit = filter_repair_patch_scope(current, wrong, scope)
    assert wrong_audit["ok"]
    assert not filtered_wrong["callsUpsert"]
    assert any(row.get("reason") == "capability_not_in_blocker_closure" for row in wrong_audit["ignoredChanges"])


def test_gameplay_scope_can_fix_existing_dependency_parameter() -> None:
    current = build_runtime_fixture("workbench_blade")
    collision = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_collision")
    collision["params"]["tileCollide"] = False
    event_call = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "shed_nails")
    event_call["params"]["event"] = "on_tile_collision"
    report = validate_runtime_program(current)
    assert any(row["code"] == "event_not_emitted" for row in report["errors"])
    scope = build_runtime_repair_scope(current, report["errors"])
    assert "workbench_blade_collision" in scope["mutable"]["callIds"]
    fixed = copy.deepcopy(collision)
    fixed["params"]["tileCollide"] = True
    fixed["params"]["bounceCount"] = 1
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"]
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


def test_gameplay_required_scalar_does_not_open_entity_creation_or_whole_node_rewrite() -> None:
    current = build_runtime_fixture("workbench_blade")
    item_use = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_use")
    old_hand_pose = item_use["params"]["handPose"]
    del item_use["params"]["useStyle"]
    del item_use["params"]["releaseTiming"]
    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    assert not scope["create"]["entities"]["allowed"]
    permissions = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == "item_use")
    assert permissions["paths"] == ["params.useStyle"]

    candidate = copy.deepcopy(item_use)
    candidate["params"]["useStyle"] = "shoot"
    candidate["params"]["autoReuse"] = True  # existing valid required value stays unchanged
    candidate["params"]["releaseTiming"] = "on_release"  # absent optional field is outside exact repair scope
    candidate["params"]["handPose"] = "two_handed"  # old valid value remains frozen
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [candidate]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    repaired = apply_repair_patch(current, filtered)
    repaired_use = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_use")
    assert validate_runtime_program(repaired)["ok"]
    assert repaired_use["params"]["autoReuse"] is True
    assert "releaseTiming" not in repaired_use["params"]
    assert repaired_use["params"]["handPose"] == old_hand_pose
    assert any(row["path"].endswith("params.handPose") for row in audit["ignoredChanges"])
    assert any(row["path"].endswith("params.releaseTiming") and row["reason"] == "addition_not_permitted" for row in audit["ignoredChanges"])


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


def test_vfx_root_pair_error_only_thaws_entity_and_event() -> None:
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
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
    assert set(REPAIR_ERROR_POLICY) == set(VALIDATION_ERROR_CODES)
    assert REPAIR_ERROR_POLICY["unknown_registry_requirement"]["llmRepairable"] is False


def test_runtime_repair_scope_is_strict_machine_readable_contract() -> None:
    current = build_runtime_fixture("workbench_blade")
    item_use = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_use")
    del item_use["params"]["useStyle"]
    scope = build_runtime_repair_scope(current, validate_runtime_program(current)["errors"])
    assert strict_schema_errors(scope, runtime_repair_scope_schema()) == []
    requirement = scope["repairRequirements"][0]
    assert requirement["repairStrategy"]
    assert requirement["llmRepairable"] is True


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


def test_gameplay_repair_keeps_useful_fix_and_ignores_frozen_rewrite_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    current = build_runtime_fixture("workbench_blade")
    current["debug"] = {"llmStageAccounting": {"gameplayAuthorCalls": 1}}
    item_use = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_use")
    item_stats = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    original_damage = item_stats["params"]["damage"]
    del item_use["params"]["useStyle"]
    failure = {"stage": "strict_author_validation", "errors": validate_runtime_program(current)["errors"]}

    fixed_use = copy.deepcopy(item_use)
    fixed_use["params"]["useStyle"] = "shoot"
    attempted_stats_rewrite = copy.deepcopy(item_stats)
    attempted_stats_rewrite["params"]["damage"] = 999
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed_use, attempted_stats_rewrite]

    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(
        gameplay_stage,
        "llm_chat_json",
        lambda *_args, **_kwargs: {"choices": [{"message": {"content": json.dumps(patch)}}]},
    )
    repaired = gameplay_stage.repair_author_item_after_failure(current, {}, {}, {}, {}, "key", failure_report=failure)
    assert validate_runtime_program(repaired)["ok"]
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_use")["params"]["useStyle"] == "shoot"
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_stats")["params"]["damage"] == original_damage
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert any(row["reason"] == "independent_valid_node_frozen" for row in audit["ignoredChanges"])


def test_nonrepairable_registry_defect_never_calls_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    current = build_runtime_fixture("workbench_blade")
    called = False

    def fake_chat(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("LLM must not be called for a registry/runtime defect")

    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(gameplay_stage, "llm_chat_json", fake_chat)
    failure = {
        "stage": "runtime_program_validation",
        "errors": [{
            "path": "$.runtimeProgram.calls[0]",
            "code": "unknown_registry_requirement",
            "message": "developer defect",
            "allowed": [],
            "relatedIds": [],
        }],
    }
    with pytest.raises(PlannerUnavailable, match="registry/runtime defect"):
        gameplay_stage.repair_author_item_after_failure(current, {}, {}, {}, {}, "key", failure_report=failure)
    assert called is False


def test_repair_transport_stage_names_are_finite_and_enabled() -> None:
    from infini_local.pipelines.llm_transport import with_llm_stage

    for stage in ("author_repair", "visual_repair", "vfx_repair"):
        payload = with_llm_stage({"model": "test"}, stage)
        assert payload["_infini_stage"] == stage


def test_visual_request_uses_real_strict_json_schema_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    captured: dict[str, object] = {}

    def fake_chat(request: dict, **_kwargs):
        captured["request"] = request
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(visual_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(
        visual_stage,
        "apply_llm_common_options",
        lambda request, **_kwargs: request,
    )
    monkeypatch.setattr(visual_stage, "with_llm_stage", lambda request, _stage: request)
    monkeypatch.setattr(visual_stage, "llm_chat_json", fake_chat)

    assert visual_stage._request_visual_kit(compiled, {}, {}, {}, {}) == {}
    request = captured["request"]
    assert isinstance(request, dict)
    response_format = request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["properties"]["entities"]["minItems"] == len(
        compiled["runtimeProgram"]["entities"]
    )
