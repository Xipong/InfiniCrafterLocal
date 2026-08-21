from __future__ import annotations

import ast
import copy
import json
from dataclasses import replace
from pathlib import Path
from collections.abc import Callable
from typing import Any

import pytest

import infini_local.pipelines.llm_authoring_pipeline as gameplay_stage
import infini_local.pipelines.combine_pipeline as combine_stage
import infini_local.pipelines.visual_generation_pipeline as visual_stage
import infini_local.core.runtime_authoring.repair_scope as repair_scope_stage
import infini_local.core.vfx_manifest as vfx_stage
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    REPAIR_ERROR_POLICY,
    REPAIR_VALIDATION_ERROR_CODES,
    runtime_event_inventory,
    runtime_repair_fragments,
    runtime_repair_scope_schema,
    strict_schema_errors,
    validate_repair_patch_scope,
    validate_runtime_program,
    VALIDATION_ERROR_CODES,
)
from infini_local.core.runtime_authoring.capability_registry import (
    EventBindingRequirement,
    EventDependencyAlternative,
    RequirementSpec,
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
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _binding_row(
    binding_id: str,
    input_name: str,
    action_name: str,
    target_id: str,
    *,
    stack_cost: int = 0,
    contact_damage: bool = False,
    placement_call_id: str = "",
) -> dict:
    action = {"kind": action_name, "targetId": target_id}
    if placement_call_id:
        action["placementCallId"] = placement_call_id
    return {
        "id": binding_id,
        "input": input_name,
        "usePolicy": {
            "action": action,
            "stackCost": stack_cost,
            "contactDamage": contact_damage,
        },
    }


def _binding_transaction(
    input_name: str,
    action_name: str,
    target_id: str,
    *,
    stack_cost: int = 0,
    contact_damage: bool = False,
) -> dict:
    row = _binding_row(
        "transaction",
        input_name,
        action_name,
        target_id,
        stack_cost=stack_cost,
        contact_damage=contact_damage,
    )
    row.pop("id")
    return row


def _visual_kit(data: dict) -> dict:
    entities = data["runtimeProgram"]["entities"]
    item_id = data["runtimeProgram"]["itemEntityId"]
    item = {
        "prompt": "literal Terraria item", "negativePrompt": "placeholder",
        "silhouette": "readable", "visualIdentity": "literal composition",
        "palette": ["brown", "steel"], "preferredCanvasSize": 32,
        "inventoryScale": 1.0, "worldScale": 1.0,
    }
    return {
        "schema": visual_stage.VISUAL_KIT_SCHEMA,
        "item": item,
        "entities": [
            ({
                "entityId": row["id"], "assetMode": "baked_sprite", "visualProjectRef": "item",
                "prompt": item["prompt"], "silhouette": item["silhouette"],
                "visualIdentity": item["visualIdentity"], "scale": 1.0,
            } if row["id"] == item_id else {
                "entityId": row["id"], "assetMode": "reuse_item_icon", "visualProjectRef": "item", "scale": 1.0,
            })
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
            "blend": "alpha", "layer": "BeforeProjectiles",
            "particleSystemId": "none", "scale": 1.0,
            "density": 0.4, "duration": 20, "alpha": 0.8, "spread": 0.1,
            "jitter": 0.1, "fadeIn": 0.1, "fadeOut": 0.4, "budgetWeight": 1.0,
            "signatureWeight": 0.4, "visualCost": 0.3, "startTick": 0, "repeatEvery": 0,
            "spritePrompt": "", "spriteNegativePrompt": "",
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


def test_visual_director_contract_preserves_same_physical_object_as_one_visual_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    captured: list[dict[str, Any]] = []

    def transport(request: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        captured.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(_visual_kit(compiled))}}]}

    monkeypatch.setattr(visual_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(visual_stage, "llm_chat_json", transport)

    visual_stage._request_visual_kit(compiled, {}, {}, {}, {})

    assert len(captured) == 1
    system = str(captured[0]["messages"][0]["content"])
    payload = json.loads(str(captured[0]["messages"][1]["content"]))
    rules = "\n".join(str(row) for row in payload["rules"])
    for surface in (system, rules):
        assert "same physical object" in surface
        assert "reuse_item_icon" in surface
        assert "visualProjectRef=item" in surface


def test_malformed_gameplay_author_json_uses_the_single_format_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    authored = build_runtime_fixture("workbench_blade")
    responses = iter([
        '{"name":"broken",',
        json.dumps(authored),
    ])
    requests: list[dict[str, Any]] = []

    def transport(request: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        requests.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": next(responses)}}]}

    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(gameplay_stage, "llm_chat_json", transport)
    planned = gameplay_stage.try_llm_plan(
        {"name": "A"}, {"name": "B"}, {"name": "ignored-ca"}, {"name": "ignored-cb"}, "a+b",
    )

    assert planned is not None
    assert [request["_infini_stage"] for request in requests] == ["planner", "author_repair"]
    repair_context = json.loads(requests[1]["messages"][1]["content"])
    assert repair_context["malformedRawText"] == '{"name":"broken",'
    assert repair_context["task"].startswith("Repair JSON syntax only")
    assert planned["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] == 1
    assert planned["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1
    assert json.loads(planned["_llmHistory"]["messages"][-1]["content"])["runtimeProgram"] == authored["runtimeProgram"]


def test_format_repair_consumes_the_only_gameplay_repair_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid = build_runtime_fixture("workbench_blade")
    next(call for call in invalid["runtimeProgram"]["calls"] if call["id"] == "item_stats")["params"].pop("damage")
    responses = iter(['{"name":"broken",', json.dumps(invalid)])
    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(
        gameplay_stage,
        "llm_chat_json",
        lambda *_args, **_kwargs: {"choices": [{"message": {"content": next(responses)}}]},
    )
    planned = gameplay_stage.try_llm_plan({}, {}, {}, {}, "a+b")
    assert planned is not None
    monkeypatch.setattr(
        combine_stage,
        "repair_author_item_after_failure",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("second Repair must not run")),
    )

    with pytest.raises(PlannerUnavailable, match="repair budget already consumed"):
        combine_stage.compile_and_validate_authored_runtime(
            planned, {}, {}, {}, {}, "a+b",
            run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs),
        )


def test_missing_tool_binding_dependency_with_occupied_primary_exposes_atomic_move_and_create() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    program["entities"] = [row for row in program["entities"] if row["id"] == "item"]
    program["primaryEntityId"] = "item"
    program["calls"] = [
        row for row in program["calls"] if row["id"] in {"item_stats", "item_use"}
    ] + [
        {"id": "place", "fn": "configure_placeable", "target": "item", "params": {"tileId": 1, "wallId": -1, "placeStyle": 0}},
        {"id": "tool", "fn": "configure_tool", "target": "item", "params": {"pickPower": 100, "axePower": 0, "hammerPower": 0, "miningSpeedScale": 1.0}},
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
    current["runtimeContract"]["claims"] = [{
        "id": "claim_tool", "kind": "gameplay", "text": "tool and placement",
        "backedBy": ["tool", "place", "primary_place"],
    }]
    current["realization"]["backedByClaims"] = ["claim_tool"]
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


def test_visual_repair_parent_context_is_raw_packet_not_canonical_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    parent = {
        "name": "Sword Named Parent",
        "internalName": "SwordNamedParent",
        "sourceMod": "Terraria",
        "damage": 20,
        "tags": ["sword", "weapon"],
    }
    canonical = {"class": "weapon", "hardTags": ["sword"], "headNoun": "sword"}
    captured: dict[str, Any] = {}

    monkeypatch.setattr(visual_stage, "resolve_llm_model", lambda: "test-model")

    def fake_chat(request: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        captured.update(copy.deepcopy(request))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(visual_stage, "llm_chat_json", fake_chat)
    visual_stage._request_visual_kit(
        compiled,
        parent,
        parent,
        canonical,
        canonical,
        repair_errors=[{"path": "$.item.prompt", "code": "shape_required"}],
        previous={},
        repair_scope={},
    )
    payload = json.loads(captured["messages"][1]["content"])
    encoded = json.dumps(payload["parentFactsReadOnly"], ensure_ascii=False).casefold()
    assert "canonical" not in encoded
    assert "hardtags" not in encoded
    assert "headnoun" not in encoded
    assert '"tags"' not in encoded
    assert payload["parentFactsReadOnly"]["parentA"] == {"packet": visual_stage.raw_parent_card_for_llm(parent)}


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


def test_malformed_vfx_json_uses_the_single_bounded_vfx_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    visual = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    visual["visualKit"] = _visual_kit(visual)
    visual["debug"] = {"planner": "llm_low_level_runtime_author", "llmStageAccounting": {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 0, "visualDirectorCalls": 1,
        "visualRepairCalls": 0, "vfxDirectorCalls": 0, "vfxRepairCalls": 0,
    }}
    valid = _vfx_output(visual)
    malformed = json.dumps(valid).replace(
        '"layer": "BeforeProjectiles"',
        '"layer": "Projectiles" if false else "BeforeProjectiles"',
        1,
    )
    repair = {
        "schema": VFX_REPAIR_PATCH_SCHEMA,
        "effectMagnitude": valid["effectMagnitude"],
        "visualBudgetClass": valid["visualBudgetClass"],
        "motif": valid["motif"],
        "slotsUpsert": valid["slots"],
        "slotIdsDelete": [],
        "slotIndicesDelete": [],
        "note": "replace the malformed whole response with strict JSON",
    }
    responses = iter([malformed, json.dumps(repair)])
    requests: list[dict[str, Any]] = []

    def transport(request: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        requests.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": next(responses)}}]}

    monkeypatch.setattr(gameplay_stage, "USE_LLM", True)
    monkeypatch.setattr(gameplay_stage, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(gameplay_stage, "llm_chat_json", transport)
    final = attach_hybrid_vfx_manifest(
        visual,
        "malformed-vfx-json",
        llm_director=gameplay_stage.call_llm_vfx_director,
    )

    assert [request["_infini_stage"] for request in requests] == ["vfx_director", "vfx_repair"]
    repair_context = json.loads(requests[1]["messages"][1]["content"])
    assert "Projectiles\" if false else" in repair_context["malformedRawText"]
    assert repair_context["exactErrors"][0]["message"].startswith("malformed_json: JSONDecodeError:")
    assert final["debug"]["llmStageAccounting"]["vfxDirectorCalls"] == 1
    assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert final["vfxManifest"]["slots"][0]["layer"] == "BeforeProjectiles"


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
    current["runtimeProgram"]["bindings"].append(_binding_row("bad_primary", "primary_use", "spawn_entity", "nail"))
    failure = {"stage": "strict_author_validation", "errors": [{"path": "$.runtimeProgram.bindings[1].input", "code": "duplicate_exclusive_input", "message": "duplicate"}]}
    patch = {
        "entitiesUpsert": [], "entityIdsDelete": [], "bindingsUpsert": [],
        "bindingIdsDelete": ["bad_primary"], "callsUpsert": [], "callIdsDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "metadataPatch": {}, "note": "remove only duplicate binding",
        "realizationReplacement": copy.deepcopy(current["realization"]),
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
        "callParamKeysDelete": [], "callPropertyKeysDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "claimIndicesDelete": [],
        "metadataPatch": {}, "note": "targeted repair",
    }


def test_canonical_binding_action_shape_error_exposes_registry_projected_fix() -> None:
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    binding_id = binding["id"]
    accepted_transaction = {
        "input": binding["input"],
        "usePolicy": copy.deepcopy(binding["usePolicy"]),
    }
    binding["usePolicy"]["action"]["kind"] = "not_registered"
    report = validate_runtime_program(current)
    assert any(
        row["path"].endswith(".usePolicy.action.kind") for row in report["errors"]
    )

    scope = build_runtime_repair_scope(current, report["errors"])
    assert binding_id in scope["identityChanges"]["bindingActionIds"]
    alternatives = next(
        row["allowed"] for row in scope["bindingAlternatives"]
        if row["bindingId"] == binding_id
    )
    assert accepted_transaction in alternatives

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [{"id": binding_id, **accepted_transaction}]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_repair_scope_rejects_new_global_id_collision_after_original_errors_close() -> None:
    current = build_runtime_fixture("workbench_blade")
    original_call = next(
        row for row in current["runtimeProgram"]["calls"]
        if row["fn"] == "configure_item_use"
    )
    current["runtimeProgram"]["calls"].remove(original_call)
    report = validate_runtime_program(current)
    assert {row["code"] for row in report["errors"]} == {
        "binding_dependency",
        "missing_claim_backing",
    }
    scope = build_runtime_repair_scope(current, report["errors"])

    colliding_call = copy.deepcopy(original_call)
    colliding_call["id"] = next(
        row["id"] for row in current["runtimeProgram"]["entities"]
        if row["kind"] == "item_body"
    )
    claim = next(
        row for row in current["runtimeContract"]["claims"]
        if original_call["id"] in row["backedBy"]
    )
    colliding_claim = copy.deepcopy(claim)
    colliding_claim["backedBy"] = [colliding_call["id"]]
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [colliding_call]
    patch["claimsUpsert"] = [colliding_claim]

    audit = validate_repair_patch_scope(current, patch, scope)
    assert not audit["ok"]
    assert any(
        row.get("actual", {}).get("code") == "ambiguous_global_id"
        for row in audit["errors"]
    )


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
    current["runtimeContract"]["claims"] = [
        row for row in current["runtimeContract"]["claims"]
        if not removed_call_ids.intersection(row["backedBy"])
    ]
    current["runtimeProgram"]["primaryEntityId"] = "workbench_blade"
    current["realization"]["backedByClaims"] = ["claim_nails"]

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


def test_gameplay_repair_deletes_exact_reported_unknown_call_property() -> None:
    current = build_runtime_fixture("workbench_blade")
    call = current["runtimeProgram"]["calls"][0]
    call["useStyle"] = 1
    report = validate_runtime_program(current)
    errors = [
        row for row in report["errors"]
        if row.get("code") == "shape_additional_property"
        and str(row.get("path") or "").endswith(".useStyle")
    ]
    assert errors

    scope = build_runtime_repair_scope(current, report["errors"])
    assert {"callId": call["id"], "key": "useStyle"} in scope["deletable"]["callPropertyKeys"]
    dossier = gameplay_stage.build_gameplay_repair_dossier(
        current, {}, {}, {}, {}, failure_report=report,
    )
    assert any(
        "callPropertyKeysDelete" in rule and "note claiming removal" in rule
        for rule in dossier["rules"]
    )
    patch = _empty_gameplay_patch()
    patch["callPropertyKeysDelete"] = [{"callId": call["id"], "key": "useStyle"}]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert filtered["callPropertyKeysDelete"] == patch["callPropertyKeysDelete"]
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert "useStyle" not in repaired["runtimeProgram"]["calls"][0]


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
        "fn": "configure_placeable",
        "target": "item",
        "params": {"tileId": -2, "wallId": -1, "placeStyle": 0},
    })

    report = authored_item_validation_report(current)
    codes = {row.get("code") for row in report["errors"]}

    assert {"shape_one_of", "shape_pattern", "shape_minimum"}.issubset(codes)
    assert {"invalid_primary_entity_reference", "duplicate_exclusive_input"}.issubset(codes)
    assert {"wrong_binding_target_kind", "entity_not_binding_spawnable", "inert_stationary_entity", "empty_component"}.issubset(codes)

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


def test_repair_transactions_apply_exact_primary_identity_and_exclusive_input_choices() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["primaryEntityId"] = "missing_primary"
    report = validate_runtime_program(current)
    primary_error = next(row for row in report["errors"] if row["code"] == "invalid_primary_entity_reference")
    scope = build_runtime_repair_scope(current, [primary_error])
    transaction = scope["repairTransactions"]["primaryEntitySelection"]
    assert transaction["candidateEntityIds"] == ["item", "nail", "workbench_blade"]
    assert transaction["mustSelectExactlyOne"] is True

    patch = _empty_gameplay_patch()
    patch["primaryEntitySelection"] = "workbench_blade"
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert repaired["runtimeProgram"]["primaryEntityId"] == "workbench_blade"
    assert all("role" not in row for row in repaired["runtimeProgram"]["bindings"])
    assert all("role" not in row for row in repaired["runtimeProgram"]["calls"])
    compiled = compile_runtime_program(repaired)
    for row in compiled["runtimeProgram"]["bindings"]:
        expected = "primary" if row["usePolicy"]["action"]["targetId"] == "workbench_blade" else "secondary"
        assert row["role"] == expected

    duplicate = build_runtime_fixture("workbench_blade")
    duplicate["runtimeProgram"]["bindings"].append(
        _binding_row("bad_primary", "primary_use", "spawn_entity", "nail")
    )
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


def test_repair_dossier_exposes_one_exact_entity_allowlist_and_empty_patch_cannot_pass() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["primaryEntityId"] = "foreign_item_entity"
    report = validate_runtime_program(current)
    assert not report["ok"]

    dossier = gameplay_stage.build_gameplay_repair_dossier(
        current,
        {"name": "Parent A"},
        {"name": "Parent B"},
        {},
        {},
        failure_report=report,
    )
    scope = dossier["repairScope"]
    exact_entity_ids = sorted(
        str(row["id"])
        for row in current["runtimeProgram"]["entities"]
    )
    assert sorted(
        str(row["id"])
        for row in dossier["immutableProgramIndex"]["entities"]
    ) == exact_entity_ids
    assert scope["repairTransactions"]["primaryEntitySelection"] == {
        "allowed": True,
        "candidateEntityIds": exact_entity_ids,
        "mustSelectExactlyOne": True,
    }
    assert any(
        "immutableProgramIndex.entities[*].id" in rule
        for rule in dossier["rules"]
    )

    empty = _empty_gameplay_patch()
    _, audit = filter_repair_patch_scope(current, empty, scope)
    assert not audit["ok"]
    assert any(
        "leaves a reported repair error open" in row["message"]
        for row in audit["errors"]
    )


def test_binding_retarget_scope_requires_registry_compatible_target_tuple() -> None:
    current = build_runtime_fixture("workbench_blade")
    binding = current["runtimeProgram"]["bindings"][0]
    binding["usePolicy"]["action"]["targetId"] = "item"
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
    assert json.dumps(
        _binding_row(
            "ignored", "primary_use", "spawn_entity", "workbench_blade", contact_damage=True
        )["usePolicy"],
        sort_keys=True,
    ) in {
        json.dumps(row["usePolicy"], sort_keys=True) for row in alternatives["allowed"]
    }

    patch = _empty_gameplay_patch()
    repaired_binding = copy.deepcopy(binding)
    repaired_binding["usePolicy"]["action"]["targetId"] = "workbench_blade"
    patch["bindingsUpsert"] = [repaired_binding]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]


def test_binding_alternative_atomically_replaces_invalid_legacy_siblings() -> None:
    current = build_runtime_fixture("workbench_blade")
    valid_binding = copy.deepcopy(current["runtimeProgram"]["bindings"][0])
    legacy_binding = copy.deepcopy(valid_binding)
    legacy_binding["action"] = valid_binding["usePolicy"]["action"]["kind"]
    legacy_binding["target"] = valid_binding["usePolicy"]["action"]["targetId"]
    legacy_binding.pop("usePolicy")
    current["runtimeProgram"]["bindings"][0] = legacy_binding

    report = validate_runtime_program(current)
    assert not report["ok"]
    assert any(row["code"] == "shape_additional_property" for row in report["errors"])

    scope = build_runtime_repair_scope(current, report["errors"])
    alternatives = next(
        row for row in scope["bindingAlternatives"]
        if row["bindingId"] == valid_binding["id"]
    )
    transaction = {
        "input": valid_binding["input"],
        "usePolicy": copy.deepcopy(valid_binding["usePolicy"]),
    }
    # The legacy row discarded the atomic usePolicy, so Repair may not infer the
    # former body-contact lane. It can only adopt the exact registry alternative.
    transaction["usePolicy"]["contactDamage"] = False
    assert transaction in alternatives["allowed"]

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [{"id": valid_binding["id"], **transaction}]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert filtered["bindingsUpsert"] == patch["bindingsUpsert"]
    assert "action" not in filtered["bindingsUpsert"][0]
    assert "target" not in filtered["bindingsUpsert"][0]

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
        not (row["input"] == "hold" and row["usePolicy"]["action"]["kind"] == "use_item_body")
        for row in alternatives["allowed"]
    )

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [_binding_row(binding["id"], "hold", "use_item_body", "item")]
    _, audit = filter_repair_patch_scope(current, patch, scope)
    assert not audit["ok"]
    assert any(
        row.get("code") == "repair_scope_violation"
        or row.get("kind") in {"additional_property", "one_of", "exactly_one"}
        for row in audit["errors"]
    )


def test_exclusive_reachability_ignores_item_body_and_never_falls_back_to_unsafe_keep() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["bindings"].append(
        _binding_row("bad_item_spawn", "primary_use", "spawn_entity", "item")
    )
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
    assert "tooltip" not in repaired


def test_metadata_repair_deletion_is_limited_to_invalid_additional_properties() -> None:
    original = {"literalSynthesis": "s", "author": "gemini"}
    candidate = {"literalSynthesis": "s"}

    # Without delete authorization the frozen merge preserves the extra key.
    kept, _, _ = merge_frozen_subtree(
        original, candidate, mutable_paths=("literalSynthesis",), audit_path="$",
        allow_additions=False,
    )
    assert kept["author"] == "gemini"

    # With exact delete authorization the omitted key drops.
    dropped, _, accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=("literalSynthesis",), audit_path="$",
        allow_additions=False, delete_paths=("author",),
    )
    assert "author" not in dropped
    assert "$.author" in accepted

    # A candidate that still carries the key keeps normal frozen-merge behaviour.
    rewrite, _, _ = merge_frozen_subtree(
        original, {"literalSynthesis": "s", "author": "gpt"}, mutable_paths=("literalSynthesis",),
        audit_path="$", allow_additions=False, delete_paths=("author",),
    )
    assert rewrite["author"] == "gemini"


def test_metadata_repair_drops_invalid_additional_property() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["concept"]["author"] = "gemini-3.5-flash-lite"
    error = {
        "path": "$.concept.author",
        "code": "shape_additional_property",
        "message": "Strict schema violation: {'path': '$.concept.author', 'kind': 'additional_property'}",
    }
    scope = build_runtime_repair_scope(current, [error])
    assert scope["nonRepairableErrors"] == []
    assert scope["metadataFields"] == ["concept"]

    # The model returns the concept WITHOUT the invalid key; the merge must drop it.
    patch = _empty_gameplay_patch()
    candidate_concept = copy.deepcopy(current["concept"])
    candidate_concept.pop("author")
    patch["metadataPatch"] = {"concept": candidate_concept}
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert "author" not in repaired["concept"]
    assert repaired["concept"]["literalSynthesis"] == current["concept"]["literalSynthesis"]


def test_metadata_repair_accepts_partial_parent_synthesis_and_freezes_the_rest() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeContract"]["parentSynthesis"]["parentA"]["facts"] = [
        f"fact {index}" for index in range(13)
    ]
    scope = build_runtime_repair_scope(current, [{
        "path": "$.runtimeContract.parentSynthesis.parentA.facts",
        "code": "shape_max_items",
        "message": "facts array exceeds 8 items",
    }])
    assert scope["nonRepairableErrors"] == []

    # The model returns only the broken part; composition/parentB stay frozen.
    patch = _empty_gameplay_patch()
    patch["metadataPatch"] = {"parentSynthesis": {"parentA": {
        "facts": ["literal workbench"],
        "runtimeRoles": current["runtimeContract"]["parentSynthesis"]["parentA"]["runtimeRoles"],
    }}}
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    synthesis = repaired["runtimeContract"]["parentSynthesis"]
    assert sorted(synthesis) == ["composition", "parentA", "parentB"]
    assert synthesis["parentA"]["facts"] == ["literal workbench"]
    assert synthesis["composition"] == current["runtimeContract"]["parentSynthesis"]["composition"]
    assert synthesis["parentB"] == current["runtimeContract"]["parentSynthesis"]["parentB"]


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
    authored_patch["realizationReplacement"] = copy.deepcopy(current["realization"])
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
    current["runtimeProgram"]["bindings"].append(
        _binding_row("bad_primary", "primary_use", "spawn_entity", "workbench_blade")
    )
    report = validate_runtime_program(current)
    error = next(row for row in report["errors"] if row["code"] == "duplicate_exclusive_input")
    scope = build_runtime_repair_scope(current, [error])
    assert scope["repairTransactions"]["exclusiveInputSelections"] == [{
        "input": "primary_use",
        "candidateBindingIds": ["bad_primary", "primary_workbench"],
        "mustKeepExactlyOne": True,
    }]

    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [
        _binding_row("bad_primary", "alternate_use", "spawn_entity", "workbench_blade")
    ]
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
        _binding_row("item_primary", "primary_use", "use_item_body", item_id),
        _binding_row("item_place", "primary_use", "use_item_body", item_id),
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


def test_invalid_primary_reference_uses_atomic_exact_entity_selection() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["primaryEntityId"] = "missing_primary"

    report = validate_runtime_program(current)
    codes = {row["code"] for row in report["errors"]}
    assert "invalid_primary_entity_reference" in codes
    scope = build_runtime_repair_scope(current, report["errors"])
    transaction = scope["repairTransactions"]["primaryEntitySelection"]
    assert transaction["allowed"] is True
    assert transaction["candidateEntityIds"] == ["item", "nail", "workbench_blade"]

    outside = _empty_gameplay_patch()
    outside["primaryEntitySelection"] = "not_an_entity"
    _, outside_audit = filter_repair_patch_scope(current, outside, scope)
    assert not outside_audit["ok"]

    patch = _empty_gameplay_patch()
    patch["primaryEntitySelection"] = "item"
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert repaired["runtimeProgram"]["primaryEntityId"] == "item"
    assert validate_runtime_program(repaired)["ok"]


def test_missing_primary_field_uses_same_exact_identity_transaction() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"].pop("primaryEntityId")
    report = validate_runtime_program(current)
    primary_error = next(
        row for row in report["errors"]
        if row["path"] == "$.runtimeProgram.primaryEntityId"
    )
    assert primary_error["code"].startswith("shape_")

    scope = build_runtime_repair_scope(current, [primary_error])
    transaction = scope["repairTransactions"]["primaryEntitySelection"]
    assert transaction["allowed"]
    selected = transaction["candidateEntityIds"][0]
    patch = _empty_gameplay_patch()
    patch["primaryEntitySelection"] = selected
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(current, filtered)
    assert repaired["runtimeProgram"]["primaryEntityId"] == selected
    assert validate_runtime_program(repaired)["ok"]


def test_primary_selection_null_is_a_true_noop() -> None:
    current = build_runtime_fixture("workbench_blade")
    item_use = next(
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] == "item_use"
    )
    del item_use["params"]["useStyle"]
    report = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, report["errors"])
    patch = _empty_gameplay_patch()
    patch["primaryEntitySelection"] = None

    filtered, audit = filter_repair_patch_scope(current, patch, scope)

    assert not audit["ok"]
    assert filtered.get("primaryEntitySelection") is None
    assert "$.primaryEntitySelection" not in audit["acceptedPaths"]
    assert apply_repair_patch(current, filtered) == current


def test_exclusive_input_transaction_preserves_reachability_and_claim_references() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    original = next(row for row in program["bindings"] if row["input"] == "primary_use")
    body_id = next(row["id"] for row in program["entities"] if row["kind"] == "item_body")
    duplicate_id = "duplicate_body_use"
    program["bindings"].append(
        _binding_row(duplicate_id, "primary_use", "use_item_body", body_id)
    )
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


def test_gameplay_filter_removes_accepted_invalid_param_from_complete_repair_call() -> None:
    current = build_runtime_fixture("workbench_blade")
    stats = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    stats["params"]["value"] = stats["params"].pop("valueCopper")
    report = validate_runtime_program(current)
    assert not report["ok"]
    assert any(error["path"].endswith(".params.value") for error in report["errors"])

    scope = build_runtime_repair_scope(current, report["errors"])
    fixed = copy.deepcopy(stats)
    fixed["params"]["valueCopper"] = fixed["params"].pop("value")
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]
    patch["callParamKeysDelete"] = [{"callId": stats["id"], "key": "value"}]
    patch["primaryEntitySelection"] = None
    patch["exclusiveInputSelections"] = []

    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    filtered_stats = next(row for row in filtered["callsUpsert"] if row["id"] == stats["id"])
    assert "value" not in filtered_stats["params"]
    assert filtered_stats["params"]["valueCopper"] > 0
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]


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
    patch["realizationReplacement"] = copy.deepcopy(current["realization"])
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
    # This test targets a distinct baked entity branch, while the shared fixture
    # correctly defaults non-item rows to reuse_item_icon.
    previous["entities"][1].update({
        "assetMode": "baked_sprite", "visualProjectRef": "entity",
        "prompt": "baked chained door", "silhouette": "chained door",
        "visualIdentity": "door on chain",
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
    assert "requiredRolesByTarget" not in scope["create"]["calls"]

    malformed_error = copy.deepcopy(report["errors"][0])
    malformed_error["relatedIds"] = []
    malformed_scope = build_runtime_repair_scope(current, [malformed_error])
    assert malformed_scope["create"]["calls"]["allowed"] is False
    assert malformed_scope["create"]["calls"]["allowedTargetIds"] == []

    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [{
        "id": "repair_item_use", "fn": "configure_item_use", "target": "item",
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

    stale_role = copy.deepcopy(patch)
    stale_role["callsUpsert"][0]["role"] = "secondary"
    _, role_audit = filter_repair_patch_scope(current, stale_role, scope)
    assert not role_audit["ok"]
    assert any(row.get("kind") == "additional_property" for row in role_audit["errors"])

    wrong = copy.deepcopy(patch)
    wrong_call = copy.deepcopy(next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats"))
    wrong_call["id"] = "wrong_dependency"
    wrong["callsUpsert"] = [wrong_call]
    filtered_wrong, wrong_audit = filter_repair_patch_scope(current, wrong, scope)
    assert not wrong_audit["ok"]
    assert not filtered_wrong["callsUpsert"]
    assert any(row.get("reason") == "capability_not_in_blocker_closure" for row in wrong_audit["ignoredChanges"])
    assert any(
        "leaves a reported repair error open" in row["message"]
        for row in wrong_audit["errors"]
    )


def test_tool_requires_primary_use_and_repair_exposes_all_executable_registry_choices() -> None:
    current = build_capability_witness("configure_tool")
    current["runtimeProgram"]["bindings"] = []

    requirement_card = next(
        requirement.card()
        for requirement in CAPABILITY_REGISTRY["configure_tool"].requirements
        if requirement.kind == "binding_tuple_present"
    )
    assert requirement_card == {
        "kind": "binding_tuple_present",
        "target": "any_entity",
        "anyOf": ["primary_use|use_item_body|contactDamage=true", "primary_use|spawn_entity"],
        "message": "A configured tool requires one explicit primary-use root matching one listed binding transaction. Tool power remains on the item body; the action root is authored explicitly and no ownership is inferred.",
    }

    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["missing_binding_dependency"]
    scope = build_runtime_repair_scope(current, report["errors"])
    assert scope["create"]["bindings"] == {
        "allowed": True,
        "allowedTargetIds": ["item"],
        "allowedInputs": ["primary_use"],
        "allowedActions": ["use_item_body"],
        "requiredTargetIds": ["item"],
        "allowedTransactions": [
            _binding_transaction(
                "primary_use", "use_item_body", "item", contact_damage=True
            ),
            _binding_transaction(
                "primary_use",
                "use_item_body",
                "item",
                stack_cost=1,
                contact_damage=True,
            ),
        ],
        "mustChooseExactlyOne": True,
    }

    empty_catalog_scope = copy.deepcopy(scope)
    empty_catalog_scope["create"]["bindings"]["allowedTransactions"] = []
    empty_catalog_patch = _empty_gameplay_patch()
    empty_catalog_patch["bindingsUpsert"] = [
        _binding_row("must_not_cross_product", "primary_use", "use_item_body", "item")
    ]
    empty_filtered, empty_audit = filter_repair_patch_scope(
        current,
        empty_catalog_patch,
        empty_catalog_scope,
    )
    assert empty_filtered["bindingsUpsert"] == []
    assert any(
        row.get("reason") == "binding_transaction_not_in_registry_projection"
        for row in empty_audit["ignoredChanges"]
    )


    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [
        _binding_row("repair_tool_primary", "primary_use", "use_item_body", "item", contact_damage=True)
    ]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


    missing_both = build_capability_witness("configure_tool")
    missing_both["runtimeProgram"]["bindings"] = []
    item_use = next(
        row for row in missing_both["runtimeProgram"]["calls"]
        if row["fn"] == "configure_item_use"
    )
    missing_both["runtimeProgram"]["calls"] = [
        row for row in missing_both["runtimeProgram"]["calls"]
        if row["fn"] != "configure_item_use"
    ]
    report = validate_runtime_program(missing_both)
    assert [row["code"] for row in report["errors"]] == [
        "missing_capability_dependency",
        "missing_binding_dependency",
    ]
    scope = build_runtime_repair_scope(missing_both, report["errors"])
    assert scope["create"]["calls"]["allowedFns"] == ["configure_item_use"]
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [item_use]
    patch["bindingsUpsert"] = [
        _binding_row("repair_tool_primary", "primary_use", "use_item_body", "item", contact_damage=True)
    ]
    filtered, audit = filter_repair_patch_scope(missing_both, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(missing_both, filtered))["ok"]

    wrong_contact = build_capability_witness("configure_tool")
    wrong_binding = wrong_contact["runtimeProgram"]["bindings"][0]
    wrong_binding["usePolicy"]["contactDamage"] = False
    report = validate_runtime_program(wrong_contact)
    assert [row["code"] for row in report["errors"]] == ["missing_binding_dependency"]
    scope = build_runtime_repair_scope(wrong_contact, report["errors"])
    fixed_binding = copy.deepcopy(wrong_binding)
    fixed_binding["usePolicy"]["contactDamage"] = True
    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [fixed_binding]
    filtered, audit = filter_repair_patch_scope(wrong_contact, patch, scope)
    assert audit["ok"], audit
    assert filtered["bindingsUpsert"] == [fixed_binding]
    assert validate_runtime_program(apply_repair_patch(wrong_contact, filtered))["ok"]

    projected_tool = build_runtime_fixture("workbench_blade")
    projected_program = projected_tool["runtimeProgram"]
    projected_primary = projected_program["bindings"][0]
    assert projected_primary["usePolicy"]["action"]["kind"] == "spawn_entity"
    projected_primary["usePolicy"]["contactDamage"] = False
    projected_program["calls"].append({
        "id": "projected_tool_power",
        "fn": "configure_tool",
        "target": "item",
        "params": {
            "pickPower": 225,
            "axePower": 0,
            "hammerPower": 0,
            "miningSpeedScale": 0.75,
        },
    })
    assert validate_runtime_program(projected_tool)["ok"]


def test_tool_dependency_repair_chooses_one_conflicting_existing_primary() -> None:
    current = build_capability_witness("configure_tool")
    original = current["runtimeProgram"]["bindings"][0]
    original["usePolicy"]["contactDamage"] = False
    duplicate = copy.deepcopy(original)
    duplicate["id"] = "duplicate_tool_primary"
    current["runtimeProgram"]["bindings"].append(duplicate)

    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == [
        "duplicate_exclusive_input",
        "missing_binding_dependency",
    ]
    scope = build_runtime_repair_scope(current, report["errors"])
    requirement = next(
        row for row in scope["repairRequirements"]
        if row["code"] == "missing_binding_dependency"
    )
    assert "requiredBindingUpdates" not in requirement
    assert not requirement.get("mustApplyAll", False)
    assert requirement["mustChooseExactlyOne"] is True
    assert not requirement.get("mustCreateExactlyOne", False)
    assert requirement["allowedBindingTransactions"] == [
        _binding_transaction(
            "primary_use", "use_item_body", "item", contact_damage=True,
        ),
    ]
    assert requirement["allowedExistingBindingIds"] == [
        duplicate["id"], original["id"],
    ]
    alternatives = {
        row["bindingId"]: row["allowed"]
        for row in scope["bindingAlternatives"]
    }
    assert set(alternatives) == {original["id"], duplicate["id"]}
    assert scope["repairTransactions"]["exclusiveInputSelections"] == [{
        "input": "primary_use",
        "candidateBindingIds": [duplicate["id"], original["id"]],
        "mustKeepExactlyOne": True,
    }]

    fixed_original = copy.deepcopy(original)
    fixed_original["usePolicy"]["contactDamage"] = True
    fixed_duplicate = copy.deepcopy(duplicate)
    fixed_duplicate["usePolicy"]["contactDamage"] = True

    double_patch = _empty_gameplay_patch()
    double_patch["bindingsUpsert"] = [fixed_original, fixed_duplicate]
    double_patch["exclusiveInputSelections"] = [{
        "input": "primary_use", "keepBindingId": original["id"],
    }]
    _, double_audit = filter_repair_patch_scope(current, double_patch, scope)
    assert not double_audit["ok"]
    assert any(
        "exactly one listed binding transaction" in row["message"]
        for row in double_audit["errors"]
    )

    mismatched_patch = _empty_gameplay_patch()
    mismatched_patch["bindingsUpsert"] = [fixed_original]
    mismatched_patch["exclusiveInputSelections"] = [{
        "input": "primary_use", "keepBindingId": duplicate["id"],
    }]
    _, mismatched_audit = filter_repair_patch_scope(
        current, mismatched_patch, scope,
    )
    assert not mismatched_audit["ok"]

    aligned_patch = _empty_gameplay_patch()
    aligned_patch["bindingsUpsert"] = [fixed_original]
    aligned_patch["exclusiveInputSelections"] = [{
        "input": "primary_use", "keepBindingId": original["id"],
    }]
    filtered, aligned_audit = filter_repair_patch_scope(
        current, aligned_patch, scope,
    )
    assert aligned_audit["ok"], aligned_audit
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert [row["id"] for row in repaired["runtimeProgram"]["bindings"]] == [
        original["id"],
    ]


def test_repair_scope_does_not_merge_capabilities_across_disjoint_error_identity() -> None:
    current = build_capability_witness("configure_tool")
    program = current["runtimeProgram"]
    program["bindings"] = []
    program["calls"] = [
        row for row in program["calls"]
        if row["fn"] != "configure_item_use"
    ]
    source_error = next(
        row for row in validate_runtime_program(current)["errors"]
        if row["code"] == "missing_binding_dependency"
    )
    foreign_error = {
        **copy.deepcopy(source_error),
        "allowed": ["configure_item_use"],
        "relatedIds": ["foreign_call", "foreign_target"],
    }

    scope = build_runtime_repair_scope(current, [source_error, foreign_error])
    requirement = scope["repairRequirements"][0]
    assert requirement["allowedBindingTransactions"] == []


def test_planned_item_capability_support_is_scoped_to_its_owner_target() -> None:
    current = build_capability_witness("configure_tool")
    program = current["runtimeProgram"]
    program["bindings"] = []
    program["calls"] = [
        row for row in program["calls"]
        if row["fn"] != "configure_item_use"
    ]
    item = next(row for row in program["entities"] if row["kind"] == "item_body")
    other_item = copy.deepcopy(item)
    other_item["id"] = "other_item"
    program["entities"].append(other_item)
    tool_call = next(row for row in program["calls"] if row["fn"] == "configure_tool")
    other_tool_call = copy.deepcopy(tool_call)
    other_tool_call["id"] = "other_tool"
    other_tool_call["target"] = "other_item"
    program["calls"].append(other_tool_call)

    errors = validate_runtime_program(current)["errors"]
    item_capability_error = next(
        row for row in errors
        if row["code"] == "missing_capability_dependency"
        and row.get("relatedIds") == ["item"]
    )
    other_binding_error = next(
        row for row in errors
        if row["code"] == "missing_binding_dependency"
        and "other_tool" in row.get("relatedIds", [])
    )
    scope = build_runtime_repair_scope(
        current, [item_capability_error, other_binding_error]
    )
    requirement = scope["repairRequirements"][1]
    assert requirement["affectedIds"] == ["other_tool"]
    assert requirement["allowedBindingTransactions"] == []


def test_binding_input_requirement_fails_closed_for_ambiguous_item_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = dict(CAPABILITY_REGISTRY)
    local_registry["configure_tool"] = replace(
        CAPABILITY_REGISTRY["configure_tool"],
        requirements=(RequirementSpec(
            kind="binding_input_present",
            target="item_body",
            any_of=("primary_use",),
            message="Synthetic exact-owner binding-input contract.",
        ),),
    )
    monkeypatch.setattr(repair_scope_stage, "CAPABILITY_REGISTRY", local_registry)

    current = build_capability_witness("configure_tool")
    program = current["runtimeProgram"]
    program["bindings"] = []
    item = next(row for row in program["entities"] if row["kind"] == "item_body")
    other_item = copy.deepcopy(item)
    other_item["id"] = "other_item"
    program["entities"].append(other_item)
    tool_call_index = next(
        index for index, row in enumerate(program["calls"])
        if row["fn"] == "configure_tool"
    )
    scope = build_runtime_repair_scope(current, [{
        "path": f"$.runtimeProgram.calls[{tool_call_index}]",
        "code": "missing_binding_dependency",
        "message": "Synthetic exact-owner binding-input contract.",
        "allowed": ["binding(input=primary_use)"],
        "relatedIds": ["witness_call", "item"],
    }])
    requirement = scope["repairRequirements"][0]
    assert requirement["allowedBindingTransactions"] == []
    assert requirement["allowedExistingBindingIds"] == []


def test_binding_action_requirement_rejects_foreign_projectile_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = dict(CAPABILITY_REGISTRY)
    local_registry["configure_item_stats"] = replace(
        CAPABILITY_REGISTRY["configure_item_stats"],
        requirements=(RequirementSpec(
            kind="binding_action_present",
            target="same_target",
            any_of=("spawn_entity",),
            message="Synthetic exact-target binding-action contract.",
        ),),
    )
    monkeypatch.setattr(repair_scope_stage, "CAPABILITY_REGISTRY", local_registry)

    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    program["bindings"] = []
    call_index = next(
        index for index, row in enumerate(program["calls"])
        if row["fn"] == "configure_item_stats"
    )
    scope = build_runtime_repair_scope(current, [{
        "path": f"$.runtimeProgram.calls[{call_index}]",
        "code": "missing_binding_dependency",
        "message": "Synthetic exact-target binding-action contract.",
        "allowed": ["spawn_entity"],
        "relatedIds": ["item_stats", "item"],
    }])
    requirement = scope["repairRequirements"][0]
    assert requirement["allowedBindingTransactions"] == []
    assert requirement["allowedExistingBindingIds"] == []


def test_binding_tuple_requirement_rejects_foreign_existing_projectile_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = dict(CAPABILITY_REGISTRY)
    local_registry["configure_item_stats"] = replace(
        CAPABILITY_REGISTRY["configure_item_stats"],
        requirements=(RequirementSpec(
            kind="binding_tuple_present",
            target="same_target",
            any_of=("primary_use|spawn_entity|contactDamage=true",),
            message="Synthetic exact-target binding-tuple contract.",
        ),),
    )
    monkeypatch.setattr(repair_scope_stage, "CAPABILITY_REGISTRY", local_registry)

    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    program["bindings"][0]["usePolicy"]["contactDamage"] = False
    call_index = next(
        index for index, row in enumerate(program["calls"])
        if row["fn"] == "configure_item_stats"
    )
    scope = build_runtime_repair_scope(current, [{
        "path": f"$.runtimeProgram.calls[{call_index}]",
        "code": "missing_binding_dependency",
        "message": "Synthetic exact-target binding-tuple contract.",
        "allowed": ["primary_use|spawn_entity|contactDamage=true"],
        "relatedIds": ["item_stats", "item"],
    }])
    requirement = scope["repairRequirements"][0]
    assert requirement["allowedBindingTransactions"] == []
    assert requirement["allowedExistingBindingIds"] == []
    assert "requiredBindingUpdates" not in requirement


def test_binding_action_reference_rejects_non_place_action_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = dict(CAPABILITY_REGISTRY)
    local_registry["configure_placeable"] = replace(
        CAPABILITY_REGISTRY["configure_placeable"],
        requirements=(RequirementSpec(
            kind="binding_action_reference",
            target="item_body",
            any_of=("spawn_entity",),
            message="Synthetic non-place action-reference contract.",
        ),),
    )
    monkeypatch.setattr(repair_scope_stage, "CAPABILITY_REGISTRY", local_registry)

    current = build_capability_witness("configure_placeable")
    current["runtimeProgram"]["bindings"] = []
    call_index = next(
        index for index, row in enumerate(current["runtimeProgram"]["calls"])
        if row["fn"] == "configure_placeable"
    )
    scope = build_runtime_repair_scope(current, [{
        "path": f"$.runtimeProgram.calls[{call_index}]",
        "code": "missing_binding_dependency",
        "message": "Synthetic non-place action-reference contract.",
        "allowed": ["spawn_entity"],
        "relatedIds": ["witness_call", "item"],
    }])
    requirement = scope["repairRequirements"][0]
    assert requirement["allowedBindingTransactions"] == []


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
    } == {"item"}


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


def test_place_item_binding_does_not_produce_item_on_use_event() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    primary = program["bindings"][0]
    primary["usePolicy"] = {
        "action": {
            "kind": "place_item",
            "targetId": "item",
            "placementCallId": "place_bench",
        },
        "stackCost": 1,
        "contactDamage": False,
    }
    program["calls"].append({
        "id": "place_bench",
        "fn": "configure_placeable",
        "target": "item",
        "params": {"tileId": 18, "wallId": -1, "placeStyle": 0},
    })
    event_call = next(row for row in program["calls"] if row["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_use"
    event_call["params"]["entity"] = "workbench_blade"

    report = validate_runtime_program(current)
    assert "event_not_emitted" in {row["code"] for row in report["errors"]}


def test_item_hit_event_requires_contact_binding_and_repair_updates_exact_policy() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    binding = program["bindings"][0]
    binding["usePolicy"]["action"] = {
        "kind": "use_item_body", "targetId": "item",
    }
    binding["usePolicy"]["contactDamage"] = False
    program["bindings"].append(_binding_row(
        "projectile_hold", "hold", "spawn_entity", "workbench_blade",
    ))
    event_call = next(row for row in program["calls"] if row["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_hit"

    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["event_not_emitted"]
    scope = build_runtime_repair_scope(current, report["errors"])
    requirement = next(
        row for row in scope["repairRequirements"]
        if row["code"] == "event_not_emitted"
    )
    assert requirement["requiredBindingUpdates"] == [{
        "bindingId": binding["id"],
        "allowed": [{
            "input": binding["input"],
            "usePolicy": {
                **copy.deepcopy(binding["usePolicy"]),
                "contactDamage": True,
            },
        }],
    }]
    assert requirement["mustApplyAll"] is True

    fixed_binding = copy.deepcopy(binding)
    fixed_binding["usePolicy"]["contactDamage"] = True
    patch = _empty_gameplay_patch()
    patch["bindingsUpsert"] = [fixed_binding]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert filtered["bindingsUpsert"] == [fixed_binding]
    repaired = apply_repair_patch(current, filtered)
    assert validate_runtime_program(repaired)["ok"]
    compiled = compile_runtime_program(repaired)
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    pairs = {(row["entityId"], row["event"]) for row in runtime_event_inventory(compiled)}
    assert (item_id, "on_hit") in pairs
    assert (item_id, "on_crit") in pairs


def test_item_hit_event_ignores_contact_binding_for_another_target() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    binding = program["bindings"][0]
    binding["usePolicy"]["action"] = {
        "kind": "use_item_body", "targetId": "item",
    }
    binding["usePolicy"]["contactDamage"] = False
    program["bindings"].append(_binding_row(
        "other_target_contact", "alternate_use", "spawn_entity", "workbench_blade",
        contact_damage=True,
    ))
    event_call = next(row for row in program["calls"] if row["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_hit"

    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["event_not_emitted"]
    scope = build_runtime_repair_scope(current, report["errors"])
    requirement = next(
        row for row in scope["repairRequirements"]
        if row["code"] == "event_not_emitted"
    )
    assert requirement["requiredBindingUpdates"] == [{
        "bindingId": binding["id"],
        "allowed": [{
            "input": binding["input"],
            "usePolicy": {
                **copy.deepcopy(binding["usePolicy"]),
                "contactDamage": True,
            },
        }],
    }]


def test_item_hit_event_does_not_require_optional_contact_geometry_call() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    program["calls"] = [
        row for row in program["calls"]
        if row["fn"] != "configure_item_contact_hitbox"
    ]
    for claim in current["runtimeContract"]["claims"]:
        claim["backedBy"] = [
            value for value in claim["backedBy"]
            if value != "item_contact"
        ]
    binding = program["bindings"][0]
    binding["usePolicy"]["action"] = {
        "kind": "use_item_body", "targetId": "item",
    }
    binding["usePolicy"]["contactDamage"] = True
    program["bindings"].append(_binding_row(
        "projectile_hold", "hold", "spawn_entity", "workbench_blade",
    ))
    event_call = next(row for row in program["calls"] if row["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_hit"

    report = validate_runtime_program(current)
    assert report["ok"], report
    compiled = compile_runtime_program(current)
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    pairs = {(row["entityId"], row["event"]) for row in runtime_event_inventory(compiled)}
    assert (item_id, "on_hit") in pairs
    assert (item_id, "on_crit") in pairs


def test_item_hit_event_repair_selects_exactly_one_existing_contact_lane() -> None:
    current = build_runtime_fixture("workbench_blade")
    program = current["runtimeProgram"]
    primary = program["bindings"][0]
    primary["usePolicy"]["action"] = {
        "kind": "use_item_body", "targetId": "item",
    }
    primary["usePolicy"]["contactDamage"] = False
    program["bindings"].append(_binding_row(
        "projectile_hold", "hold", "spawn_entity", "workbench_blade",
    ))
    alternate = _binding_row(
        "alternate_body", "alternate_use", "use_item_body", "item",
        contact_damage=False,
    )
    program["bindings"].append(alternate)
    event_call = next(row for row in program["calls"] if row["id"] == "shed_nails")
    event_call["target"] = "item"
    event_call["params"]["event"] = "on_hit"

    report = validate_runtime_program(current)
    assert [row["code"] for row in report["errors"]] == ["event_not_emitted"]
    scope = build_runtime_repair_scope(current, report["errors"])
    requirement = next(
        row for row in scope["repairRequirements"]
        if row["code"] == "event_not_emitted"
    )
    assert "requiredBindingUpdates" not in requirement
    assert requirement["mustChooseExactlyOne"] is True
    assert not requirement.get("mustCreateExactlyOne", False)
    assert not requirement.get("mustApplyAll", False)
    assert len(requirement["allowedBindingTransactions"]) == 2

    fixed_primary = copy.deepcopy(primary)
    fixed_primary["usePolicy"]["contactDamage"] = True
    fixed_alternate = copy.deepcopy(alternate)
    fixed_alternate["usePolicy"]["contactDamage"] = True

    double_patch = _empty_gameplay_patch()
    double_patch["bindingsUpsert"] = [fixed_primary, fixed_alternate]
    _, double_audit = filter_repair_patch_scope(current, double_patch, scope)
    assert not double_audit["ok"]
    assert any(
        "exactly one listed binding transaction" in row["message"]
        for row in double_audit["errors"]
    )

    single_patch = _empty_gameplay_patch()
    single_patch["bindingsUpsert"] = [fixed_alternate]
    filtered, single_audit = filter_repair_patch_scope(current, single_patch, scope)
    assert single_audit["ok"], single_audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


def test_binding_dependency_repair_can_delete_the_exact_unwanted_binding() -> None:
    current = build_capability_witness("configure_accessory")
    current["runtimeProgram"]["calls"] = [
        row for row in current["runtimeProgram"]["calls"]
        if row["id"] != "witness_call"
    ]
    current["runtimeContract"]["claims"][0]["backedBy"] = ["item_stats"]

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
    fixed["params"]["defense"] = 1
    patch = _empty_gameplay_patch()
    patch["callsUpsert"] = [fixed]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(current, filtered))["ok"]


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


def test_gameplay_scope_create_policy_has_no_parallel_role_authority() -> None:
    current = build_runtime_fixture("workbench_blade")
    current["runtimeProgram"]["calls"] = [
        row for row in current["runtimeProgram"]["calls"] if row["id"] != "item_use"
    ]
    for claim in current["runtimeContract"]["claims"]:
        claim["backedBy"] = [value for value in claim["backedBy"] if value != "item_use"]
    report = validate_runtime_program(current)
    assert any(row["code"] == "binding_dependency" for row in report["errors"])

    scope = build_runtime_repair_scope(current, report["errors"])
    assert "requiredRolesByTarget" not in scope["create"]["calls"]


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
    assert "id, fn, target, and the complete params object" in repair_rules
    required_shape = dossier["requiredJsonShape"]
    assert required_shape["claimsUpsert"][0]["kind"] == "gameplay|physical|parent_synthesis"
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
    author_truth = json.loads(author_payload)["runtimeProgramInvariants"]["realizationExecutionTruth"]
    assert dossier["runtimeExecutionTruth"] == author_truth
    assert "literal post-repair execution report" in repair_rules
    assert "reconcile intentTrace kept/changed/dropped" in repair_rules
    assert dossier["acceptedItemContext"]["claims"] == current["runtimeContract"]["claims"]


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
    assert list(payload)[-1] == "balanceCorridor"


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
    patch["realizationReplacement"] = copy.deepcopy(current["realization"])

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
    payload = json.loads(request["messages"][1]["content"])
    assert any(
        "transparent background" in rule and "opaque background" in rule
        for rule in payload["rules"]
    )
    assert payload["assetModeCatalog"] == [
        {
            "mode": "baked_sprite",
            "runtimeEffect": "Generate and deliver a distinct PNG for this exact runtime entity.",
        },
        {
            "mode": "no_asset",
            "runtimeEffect": "Deliver no PNG and draw no entity body; independent runtime VFX may still draw.",
        },
        {
            "mode": "reuse_item_icon",
            "runtimeEffect": "Deliver no separate PNG; resolve this entity to the item_body generated PNG with identical pixels.",
        },
        {
            "mode": "runtime_geometry",
            "runtimeEffect": "Deliver no PNG; draw the built-in bounded runtime primitive from entity hitbox and light fields.",
        },
    ]
