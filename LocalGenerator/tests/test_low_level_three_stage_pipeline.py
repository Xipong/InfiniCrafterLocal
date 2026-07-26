from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from collections.abc import Callable

import pytest

import infini_local.pipelines.llm_authoring_pipeline as gameplay_stage
import infini_local.pipelines.visual_generation_pipeline as visual_stage
import infini_local.core.vfx_manifest as vfx_stage
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    REPAIR_ERROR_POLICY,
    REPAIR_VALIDATION_ERROR_CODES,
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
from infini_local.pipelines.combine_validation import authored_item_validation_report
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
    temperatures: list[float] = []
    monkeypatch.setattr(vfx_stage, "VFX_LLM_DIRECTOR_TEMPERATURE", 0.5)
    monkeypatch.setattr(vfx_stage, "VFX_LLM_REPAIR_TEMPERATURE", 0.12)

    def director(*args, **_kwargs):
        nonlocal calls
        calls += 1
        temperatures.append(float(args[3]))
        return next(vfx_responses)

    final = attach_hybrid_vfx_manifest(visual, "door", llm_director=director)
    assert calls == 2
    assert temperatures == [0.5, 0.12]
    assert final["debug"]["llmStageAccounting"]["vfxDirectorCalls"] == 1
    assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert final["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1
    assert final["vfxManifest"]["slots"][0]["id"] == bad_vfx["slots"][0]["id"]


def test_visual_director_and_repair_use_stage_specific_temperatures(monkeypatch: pytest.MonkeyPatch) -> None:
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    temperatures: list[float] = []

    def capture(request: dict, **_kwargs):
        temperatures.append(float(request["temperature"]))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setenv("INFINI_VISUAL_DIRECTOR_TEMPERATURE", "0.5")
    monkeypatch.setenv("INFINI_VISUAL_REPAIR_TEMPERATURE", "0.12")
    monkeypatch.setattr(visual_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(visual_stage, "llm_chat_json", capture)
    visual_stage._request_visual_kit(data, {}, {}, {}, {})
    visual_stage._request_visual_kit(
        data, {}, {}, {}, {}, repair_errors=[], previous={}, repair_scope={},
    )

    assert temperatures == [0.5, 0.12]


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
        "callParamKeysDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "claimIndicesDelete": [],
        "metadataPatch": {}, "note": "targeted repair",
    }


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
    binding = current["runtimeProgram"]["bindings"][0]
    binding["role"] = "primary"
    current["runtimeProgram"]["bindings"].append({
        **binding,
        "id": "duplicate_primary_use",
        "target": "nail",
        "role": "secondary",
    })
    current["runtimeProgram"]["bindings"].append({
        "id": "wrong_item_spawn",
        "input": "alternate_use",
        "action": "spawn_entity",
        "role": "primary",
        "target": "item",
    })
    current["runtimeProgram"]["entities"].append({"id": "idle_helper", "kind": "temporary_helper"})
    current["runtimeProgram"]["bindings"].append({
        "id": "spawn_idle_helper",
        "input": "hold",
        "action": "spawn_entity",
        "role": "secondary",
        "target": "idle_helper",
    })
    current["runtimeProgram"]["calls"].append({
        "id": "invalid_placeable",
        "fn": "configure_placeable",
        "role": "primary",
        "target": "item",
        "params": {"tileId": -2, "wallId": -1, "placeStyle": 0},
    })

    report = authored_item_validation_report(current)
    codes = {row.get("code") for row in report["errors"]}

    assert {"shape_one_of", "shape_pattern", "shape_minimum"}.issubset(codes)
    assert {"mixed_entity_role", "primary_entity_count", "duplicate_exclusive_input"}.issubset(codes)
    assert {"wrong_binding_target_kind", "entity_not_binding_spawnable", "inert_stationary_entity", "empty_component"}.issubset(codes)

    scope = build_runtime_repair_scope(current, report["errors"])
    transaction = scope["repairTransactions"]["entityRoleSelection"]
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


def test_repair_transactions_apply_llm_primary_and_exclusive_input_choices() -> None:
    current = build_runtime_fixture("workbench_blade")
    for namespace in ("bindings", "calls"):
        for row in current["runtimeProgram"][namespace]:
            if row.get("target") == "workbench_blade":
                row["role"] = "primary"
    report = validate_runtime_program(current)
    primary_error = next(row for row in report["errors"] if row["code"] == "primary_entity_count")
    scope = build_runtime_repair_scope(current, [primary_error])
    transaction = scope["repairTransactions"]["entityRoleSelection"]
    assert transaction["candidateEntityIds"] == ["item", "nail", "workbench_blade"]
    assert transaction["mustSelectExactlyOne"] is True

    patch = _empty_gameplay_patch()
    patch["primaryEntitySelection"] = "workbench_blade"
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    for namespace in ("bindings", "calls"):
        for row in repaired["runtimeProgram"][namespace]:
            expected = "primary" if row.get("target") == "workbench_blade" else "secondary"
            assert row["role"] == expected

    duplicate = build_runtime_fixture("workbench_blade")
    duplicate["runtimeProgram"]["bindings"].append({
        "id": "bad_primary", "input": "primary_use", "action": "spawn_entity",
        "role": "secondary", "target": "nail",
    })
    duplicate_report = validate_runtime_program(duplicate)
    duplicate_error = next(row for row in duplicate_report["errors"] if row["code"] == "duplicate_exclusive_input")
    duplicate_scope = build_runtime_repair_scope(duplicate, [duplicate_error])
    exclusive = duplicate_scope["repairTransactions"]["exclusiveInputSelections"]
    assert exclusive == [{
        "input": "primary_use",
        "candidateBindingIds": ["primary_workbench"],
        "mustKeepExactlyOne": True,
    }]

    duplicate_patch = _empty_gameplay_patch()
    duplicate_patch["exclusiveInputSelections"] = [{
        "input": "primary_use", "keepBindingId": "primary_workbench",
    }]
    filtered_duplicate, duplicate_audit = filter_repair_patch_scope(
        duplicate, duplicate_patch, duplicate_scope,
    )
    assert duplicate_audit["ok"], duplicate_audit
    repaired_duplicate = apply_repair_patch(duplicate, filtered_duplicate)
    assert validate_runtime_program(repaired_duplicate)["ok"]
    assert all(
        row["id"] != "bad_primary"
        for row in repaired_duplicate["runtimeProgram"]["bindings"]
    )


def test_binding_retarget_scope_requires_registry_compatible_target_role_tuple() -> None:
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    binding["target"] = "item"
    binding["role"] = "primary"
    report = validate_runtime_program(current)
    errors = [
        row for row in report["errors"]
        if row["code"] in {"wrong_binding_target_kind", "entity_not_binding_spawnable"}
    ]
    assert errors

    scope = build_runtime_repair_scope(current, errors)
    alternatives = next(
        row for row in scope["bindingAlternatives"]
        if row["bindingId"] == binding["id"]
    )
    assert {
        "input": "primary_use",
        "action": "spawn_entity",
        "target": "workbench_blade",
        "role": "secondary",
    } in alternatives["allowed"]
    assert all(
        row["role"] == "secondary"
        for row in alternatives["allowed"]
        if row["target"] == "workbench_blade"
    )

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [{
        **binding,
        "target": "workbench_blade",
        "role": "secondary",
    }]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]


def test_binding_repair_rejects_cross_product_input_action_pair() -> None:
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    error = {
        "path": "$.runtimeProgram.bindings[0]",
        "code": "unsupported_input_action",
        "message": "repair the exact binding tuple",
        "relatedIds": [binding["id"]],
    }
    scope = build_runtime_repair_scope(current, [error])
    alternatives = next(
        row for row in scope["bindingAlternatives"]
        if row["bindingId"] == binding["id"]
    )
    assert all(
        not (row["input"] == "hold" and row["action"] == "use_item_body")
        for row in alternatives["allowed"]
    )

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [{
        **binding,
        "input": "hold",
        "action": "use_item_body",
        "target": "item",
        "role": "primary",
    }]
    _, audit = filter_repair_patch_scope(current, patch, scope)
    assert not audit["ok"]
    assert any(row["code"] == "repair_scope_violation" for row in audit["errors"])


def test_exclusive_reachability_ignores_item_body_and_never_falls_back_to_unsafe_keep() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["bindings"].append({
        "id": "bad_item_spawn",
        "input": "primary_use",
        "action": "spawn_entity",
        "role": "primary",
        "target": "item",
    })
    report = validate_runtime_program(current)
    error = next(row for row in report["errors"] if row["code"] == "duplicate_exclusive_input")

    scope = build_runtime_repair_scope(current, [error])

    assert scope["repairTransactions"]["exclusiveInputSelections"] == [{
        "input": "primary_use",
        "candidateBindingIds": ["primary_workbench"],
        "mustKeepExactlyOne": True,
    }]


def test_uncombined_identity_opens_only_model_authored_name_metadata() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["name"] = "Workbench"
    error = {
        "path": "$.name",
        "code": "uncombined_identity",
        "message": "provide an authored combined identity",
    }
    scope = build_runtime_repair_scope(current, [error])
    assert scope["nonRepairableErrors"] == []
    assert scope["metadataFields"] == ["name"]

    patch = _empty_gameplay_patch()
    patch["metadataPatch"] = {"name": "Workbench Blade"}
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert repaired["name"] == "Workbench Blade"
    assert repaired["tooltip"] == current["tooltip"]


def test_uncombined_identity_closes_through_same_author_repair_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    current = build_runtime_fixture("workbench_blade")
    current["name"] = "Workbench"
    current["debug"] = {"llmStageAccounting": {"gameplayAuthorCalls": 1}}
    failure = {
        "stage": "strict_author_validation",
        "errors": [{
            "path": "$.name", "code": "uncombined_identity",
            "message": "provide an authored combined identity",
        }],
    }
    authored_patch = _empty_gameplay_patch()
    authored_patch["metadataPatch"] = {"name": "Workbench Blade"}
    authored_patch["note"] = "author a combined identity"
    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(
        gameplay_stage,
        "llm_chat_json",
        lambda *_args, **_kwargs: {
            "choices": [{"message": {"content": json.dumps(authored_patch)}}]
        },
    )

    repaired = gameplay_stage.repair_author_item_after_failure(
        current,
        {"name": "Workbench"},
        {"name": "Sword"},
        {"name": "Workbench"},
        {"name": "Sword"},
        "workbench+sword",
        failure_report=failure,
    )

    assert repaired["name"] == "Workbench Blade"
    assert repaired["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1


def test_redundant_exclusive_selection_is_ignored_after_binding_retarget() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["bindings"].append({
        "id": "bad_primary",
        "input": "primary_use",
        "action": "spawn_entity",
        "role": "secondary",
        "target": "workbench_blade",
    })
    report = validate_runtime_program(current)
    error = next(row for row in report["errors"] if row["code"] == "duplicate_exclusive_input")
    scope = build_runtime_repair_scope(current, [error])
    assert scope["repairTransactions"]["exclusiveInputSelections"] == [{
        "input": "primary_use",
        "candidateBindingIds": ["bad_primary", "primary_workbench"],
        "mustKeepExactlyOne": True,
    }]

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [{
        "id": "bad_primary",
        "input": "alternate_use",
        "action": "spawn_entity",
        "role": "secondary",
        "target": "workbench_blade",
    }]
    patch["exclusiveInputSelections"] = [{
        "input": "primary_use",
        "keepBindingId": "not_a_candidate",
    }]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)

    assert audit["ok"], audit
    assert filtered["exclusiveInputSelections"] == []
    assert any(
        row.get("reason") == "exclusive_input_conflict_already_resolved"
        for row in audit["ignoredChanges"]
    )
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    repaired_binding = next(
        row for row in repaired["runtimeProgram"]["bindings"]
        if row["id"] == "bad_primary"
    )
    assert repaired_binding["input"] == "alternate_use"


def test_exclusive_selection_candidates_recompute_after_scoped_retarget() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    original = next(row for row in program["bindings"] if row["input"] == "primary_use")
    item_id = next(row["id"] for row in program["entities"] if row["kind"] == "item_body")
    current["runtimeContract"]["claims"][0]["backedBy"].append(original["id"])
    program["bindings"].extend([
        {
            "id": "item_primary",
            "input": "primary_use",
            "action": "use_item_body",
            "role": "primary",
            "target": item_id,
        },
        {
            "id": "item_place",
            "input": "primary_use",
            "action": "place_item",
            "role": "primary",
            "target": item_id,
        },
    ])
    errors = [
        row for row in validate_runtime_program(current)["errors"]
        if row["code"] == "duplicate_exclusive_input"
    ]
    scope = build_runtime_repair_scope(current, errors)
    transaction = scope["repairTransactions"]["exclusiveInputSelections"][0]
    assert transaction["candidateBindingIds"] == [original["id"]]

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [{**original, "input": "alternate_use"}]
    patch["exclusiveInputSelections"] = [{
        "input": "primary_use",
        "keepBindingId": "item_primary",
    }]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)

    assert audit["ok"], audit
    assert filtered["exclusiveInputSelections"] == [{
        "input": "primary_use",
        "keepBindingId": "item_primary",
    }]
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    repaired_claim = next(
        row for row in repaired["runtimeContract"]["claims"]
        if row["id"] == current["runtimeContract"]["claims"][0]["id"]
    )
    assert original["id"] in repaired_claim["backedBy"]


def test_direct_runtime_id_delete_closes_claim_backing() -> None:
    current = build_runtime_fixture("workbench_blade")
    binding = copy.deepcopy(current["runtimeProgram"]["bindings"][0])
    binding_id = binding["id"]
    claim = current["runtimeContract"]["claims"][0]
    claim["backedBy"].append(binding_id)
    patch = _empty_gameplay_patch()
    patch["bindingIdsDelete"] = [binding_id]

    repaired = apply_repair_patch(current, patch)

    repaired_claim = next(
        row for row in repaired["runtimeContract"]["claims"]
        if row["id"] == claim["id"]
    )
    assert binding_id not in repaired_claim["backedBy"]
    assert repaired_claim["backedBy"]

    replacement_patch = _empty_gameplay_patch()
    replacement_patch["bindingIdsDelete"] = [binding_id]
    replacement_patch["bindingsUpsert"] = [binding]
    replaced = apply_repair_patch(current, replacement_patch)
    replaced_claim = next(
        row for row in replaced["runtimeContract"]["claims"]
        if row["id"] == claim["id"]
    )
    assert binding_id in replaced_claim["backedBy"]


def test_mixed_role_without_primary_count_uses_atomic_entity_selection() -> None:
    current = build_runtime_fixture("workbench_blade")
    valid = validate_runtime_program(current)
    primary_id = valid["stats"]["primaryEntityId"]
    rows = [
        row
        for namespace in ("bindings", "calls")
        for row in current["runtimeProgram"][namespace]
        if row.get("target") == primary_id and row.get("role") == "primary"
    ]
    assert len(rows) >= 2
    rows[0]["role"] = "secondary"

    report = validate_runtime_program(current)
    codes = {row["code"] for row in report["errors"]}
    assert "mixed_entity_role" in codes
    assert "primary_entity_count" not in codes
    scope = build_runtime_repair_scope(current, report["errors"])
    transaction = scope["repairTransactions"]["entityRoleSelection"]
    assert transaction["allowed"] is True
    assert transaction["candidateEntityIds"] == [primary_id]

    patch = _empty_gameplay_patch()
    patch["primaryEntitySelection"] = primary_id
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]


def test_exclusive_input_transaction_preserves_reachability_and_claim_references() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    original = next(row for row in program["bindings"] if row["input"] == "primary_use")
    body_id = next(row["id"] for row in program["entities"] if row["kind"] == "item_body")
    duplicate_id = "duplicate_body_use"
    program["bindings"].append({
        "id": duplicate_id,
        "input": "primary_use",
        "action": "use_item_body",
        "role": "secondary",
        "target": body_id,
    })
    current["runtimeContract"]["claims"][0]["backedBy"].append(duplicate_id)
    error = {
        "path": "$.runtimeProgram.bindings[1].input",
        "code": "duplicate_exclusive_input",
        "message": "duplicate",
        "relatedIds": [original["id"], duplicate_id],
    }

    scope = build_runtime_repair_scope(current, [error])
    selections = scope["repairTransactions"]["exclusiveInputSelections"]
    assert selections == [{
        "input": "primary_use",
        "candidateBindingIds": [original["id"]],
        "mustKeepExactlyOne": True,
    }]

    patch = _empty_gameplay_patch()
    patch["exclusiveInputSelections"] = [{
        "input": "primary_use",
        "keepBindingId": original["id"],
    }]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert duplicate_id not in repaired["runtimeContract"]["claims"][0]["backedBy"]
    assert validate_runtime_program(repaired)["ok"]


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
    assert scope["create"]["calls"]["requiredRolesByTarget"] == [{"targetId": "item", "role": "primary"}]

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

    wrong_role = copy.deepcopy(patch)
    wrong_role["callsUpsert"][0]["role"] = "secondary"
    filtered_role, role_audit = filter_repair_patch_scope(current, wrong_role, scope)
    assert role_audit["ok"]
    assert not filtered_role["callsUpsert"]
    assert any(
        row.get("reason") == "call_role_conflicts_with_target_partition"
        for row in role_audit["ignoredChanges"]
    )

    wrong = copy.deepcopy(patch)
    wrong_call = copy.deepcopy(next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats"))
    wrong_call["id"] = "wrong_dependency"
    wrong["callsUpsert"] = [wrong_call]
    filtered_wrong, wrong_audit = filter_repair_patch_scope(current, wrong, scope)
    assert wrong_audit["ok"]
    assert not filtered_wrong["callsUpsert"]
    assert any(row.get("reason") == "capability_not_in_blocker_closure" for row in wrong_audit["ignoredChanges"])


def test_gameplay_repair_removes_only_exact_invalid_call_param_key() -> None:
    current = build_runtime_fixture("workbench_blade")
    stats = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    stats["params"]["invalidExtra"] = 7
    report = validate_runtime_program(current)
    assert any(
        row["code"] == "shape_additional_property"
        and row["path"].endswith(".params.invalidExtra")
        for row in report["errors"]
    )

    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["deletable"]["callParamKeys"] == [{"callId": "item_stats", "key": "invalidExtra"}]
    candidate = copy.deepcopy(stats)
    del candidate["params"]["invalidExtra"]
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [candidate]

    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert filtered["callParamKeysDelete"] == [{"callId": "item_stats", "key": "invalidExtra"}]
    repaired = apply_repair_patch(current, filtered)
    repaired_stats = next(
        row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_stats"
    )
    assert "invalidExtra" not in repaired_stats["params"]
    assert validate_runtime_program(repaired)["ok"]

    out_of_scope = _empty_gameplay_patch()
    out_of_scope["callParamKeysDelete"] = [{"callId": "item_stats", "key": "damage"}]
    rejected, rejected_audit = filter_repair_patch_scope(current, out_of_scope, scope)
    assert rejected["callParamKeysDelete"] == []
    assert any(
        row.get("reason") == "call_param_delete_outside_exact_error_scope"
        for row in rejected_audit["ignoredChanges"]
    )
    scope_report = validate_repair_patch_scope(current, out_of_scope, scope)
    assert any(row["path"] == "$.callParamKeysDelete[0]" for row in scope_report["errors"])


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


def test_gameplay_scope_does_not_require_role_for_mixed_target_partition() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["calls"] = [
        row for row in current["runtimeProgram"]["calls"] if row["id"] != "item_use"
    ]
    for claim in current["runtimeContract"]["claims"]:
        claim["backedBy"] = [value for value in claim["backedBy"] if value != "item_use"]
    report = validate_runtime_program(current)
    assert any(row["code"] == "binding_dependency" for row in report["errors"])

    secondary = copy.deepcopy(current["runtimeProgram"]["calls"][0])
    secondary["id"] = "existing_secondary_item_call"
    secondary["role"] = "secondary"
    current["runtimeProgram"]["calls"].append(secondary)

    scope = build_runtime_repair_scope(current, report["errors"])
    assert all(
        row["target"] != "item"
        for row in scope["create"]["calls"]["requiredRolesByTarget"]
    )


def test_gameplay_scope_rejects_param_delete_for_new_call() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["calls"] = [
        row for row in current["runtimeProgram"]["calls"] if row["id"] != "item_use"
    ]
    for claim in current["runtimeContract"]["claims"]:
        claim["backedBy"] = [value for value in claim["backedBy"] if value != "item_use"]
    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])

    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [
        {
            "id": "repair_item_use",
            "fn": "configure_item_use",
            "role": "primary",
            "target": "item",
            "params": {
                "useStyle": "shoot",
                "autoReuse": True,
                "useTurn": True,
                "hideUseGraphic": False,
                "disableMeleeHitbox": True,
                "channel": False,
                "holdoutOffsetX": 0,
                "holdoutOffsetY": 0,
                "handPose": "one_handed",
                "releaseTiming": "immediate",
            },
        }
    ]
    patch["callParamKeysDelete"] = [
        {"callId": "repair_item_use", "key": "releaseTiming"}
    ]

    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert [row["id"] for row in filtered["callsUpsert"]] == ["repair_item_use"]
    assert filtered["callParamKeysDelete"] == []
    assert any(
        row.get("reason") == "call_param_delete_outside_exact_error_scope"
        for row in audit["ignoredChanges"]
    )
    scope_report = validate_repair_patch_scope(current, patch, scope)
    assert any(row["path"] == "$.callParamKeysDelete[0]" for row in scope_report["errors"])


def test_gameplay_scope_does_not_widen_nested_call_param_error() -> None:
    current = build_runtime_fixture("workbench_blade")
    nested_error = {
        "code": "shape_additional_property",
        "path": "$.runtimeProgram.calls[0].params.nested.extra",
        "message": "nested additional property",
    }
    scope = build_runtime_repair_scope(current, [nested_error])
    assert scope["deletable"]["callParamKeys"] == []


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
    assert set(REPAIR_VALIDATION_ERROR_CODES) == set(REPAIR_ERROR_POLICY)
    assert REPAIR_ERROR_POLICY["uncombined_identity"]["strategy"] == "patch_exact_name"
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
    repair_rules = " ".join(dossier["rules"])
    assert "Every upsert entry must be a complete schema-valid node" in repair_rules
    assert "id, fn, role, target, and the complete params object" in repair_rules
    required_shape = dossier["requiredJsonShape"]
    assert required_shape["claimsUpsert"][0]["kind"] == "gameplay|physical|parent_synthesis"
    assert set(required_shape["callsUpsert"][0]) == {"id", "fn", "role", "target", "params"}
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
    assert list(payload["runtimeCapabilityContract"])[-1] == "balanceCorridor"


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
