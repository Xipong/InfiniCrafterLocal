from __future__ import annotations
from infini_local.pipelines.vfx import request as vfx_transport
from prompt_packet_helpers import request_dossier, dossier_text
from contextlib import nullcontext

import copy
import json

import pytest

import infini_local.pipelines.author.request as gameplay_stage
import infini_local.pipelines.author.stage as combine_stage
import infini_local.pipelines.visual.stage as visual_stage
import infini_local.pipelines.visual.contract as visual_stage_contract
import infini_local.pipelines.visual.stage as visual_stage_stage
import infini_local.pipelines.visual.request as visual_request
import infini_local.core.vfx.config as vfx_stage_config
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import strict_repair_shape_report
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.vfx.contract import VFX_DIRECTOR_SCHEMA, VFX_REPAIR_PATCH_SCHEMA
from infini_local.pipelines.vfx.stage import attach_vfx_manifest
from infini_local.core.vfx.surface import vfx_director_surface
from infini_local.pipelines.combine_pipeline import _assert_stage_topology
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from collections import deque
from contract_checks import assert_pipeline_phase_order, assert_pipeline_terminal_phase, pipeline_phase_count

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
    from infini_local.core.runtime_authoring.capability_registry import INPUT_KIND_REGISTRY, BINDING_ACTION_REGISTRY
    action = {"kind": action_name, "targetId": target_id}
    if placement_call_id:
        action["placementCallId"] = placement_call_id
    spec = BINDING_ACTION_REGISTRY.get(action_name)
    inp = INPUT_KIND_REGISTRY.get(input_name)
    if spec is not None and spec.target_kinds == ("item_body",):
        action.pop("targetId")
    if inp is not None and len(inp.allowed_actions) == 1 and action_name == inp.allowed_actions[0]:
        action.pop("kind")
    row = {"id": binding_id, "input": input_name}
    if action:
        row["action"] = action
    if input_name in {"primary_use", "alternate_use"} and action_name != "place_item":
        row.update(stackCost=stack_cost, contactDamage=contact_damage)
    return row


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
        "renderSizePx": 40, "forwardAngleDegrees": 45,
        "inventoryScale": 1.0, "worldScale": 1.0,
    }
    return {
        "schema": visual_stage_contract.VISUAL_KIT_SCHEMA,
        "item": item,
        "entities": [
            ({
                "entityId": row["id"], "assetMode": "baked_sprite", "visualProjectRef": "item",
                "scale": 1.0,
            } if row["id"] == item_id else {
                "entityId": row["id"], "assetMode": "reuse_item_icon", "visualProjectRef": "item", "scale": 1.0,
            })
            for row in entities
        ],
        "animationPlan": "Follow exact runtime movement.",
    }


def _accepted_visual_data(fixture_name: str) -> dict:
    data = compile_runtime_program(build_runtime_fixture(fixture_name))
    runtime = data["runtimeProgram"]
    kit, errors = visual_stage_contract._validate_kit(
        _visual_kit(data), [row["id"] for row in runtime["entities"]], runtime["itemEntityId"],
    )
    assert kit is not None, errors
    # VFX follows Visual in production; a mechanics-only compiler result or an
    # ignored visualKit assignment does not project the actual PNG producers.
    return visual_stage_stage._apply_kit(data, kit)


def _visual_patch(data: dict) -> dict:
    kit = _visual_kit(data)
    return {
        "schema": visual_stage_contract.VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": kit["item"],
        "entitiesUpsert": kit["entities"],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "note": "repair only invalid item and missing entity rows",
    }


def _vfx_output(data: dict) -> dict:
    pair = vfx_director_surface(data)["runtimePairs"][0]
    return {
        "schema": VFX_DIRECTOR_SCHEMA,
        "slots": [{
            "id": "slot_0", "entityId": pair["entityId"], "event": pair["event"],
            "rendererKind": "libraryParticle", "anchor": "self",
            "blend": "alpha", "layer": "BeforeProjectiles",
            "duration": 20, "alpha": 0.8,
            "startTick": 0, "repeatEvery": 1 if pair["event"] == "periodic" else 0,
            "particle": {
                "spawn": {"shape": "point"}, "textureId": "star", "sampling": "point", "count": 1,
                "speedMinPxPerTick": 0, "speedMaxPxPerTick": 0,
                "spreadRadians": 0, "inheritVelocity": 0, "drag": 1,
                "accelerationXPxPerTickSquared": 0, "accelerationYPxPerTickSquared": 0,
                "widthPx": 4, "heightPx": 4, "rotationRadians": 0,
                "rotationSpeedRadiansPerTick": 0,
                "colorStart": {"r": 17, "g": 93, "b": 241},
                "colorEnd": {"r": 17, "g": 93, "b": 241},
                "endScaleMultiplier": 1, "endOpacity": 0,
            },
        }],
    }


def _empty_gameplay_patch() -> dict:
    return {
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "bindingsUpsert": [], "bindingIdsDelete": [], "bindingIndicesDelete": [],
        "callsUpsert": [], "callIdsDelete": [], "callIndicesDelete": [],
        "callParamKeysDelete": [], "callPropertyKeysDelete": [],
        "metadataPatch": {}, "note": "targeted repair",
    }


# Data cases exercise real stage entry points; only the external transport is inert.
@pytest.fixture
def wire_transport(monkeypatch):
    responses, requests = deque(), []

    def reply(request, **_kwargs):
        requests.append(copy.deepcopy(request))
        assert responses, f"unexpected model call: {request.get('_infini_stage')}"
        value = responses.popleft()
        if request.get("_infini_stage") in {"vfx_director", "vfx_repair"} and isinstance(value, dict):
            # Fixtures are persisted-wire candidates; fake provider speaks the model schema.
            from infini_local.core.vfx.materials import vfx_model_payload
            value = vfx_model_payload(value)
        if isinstance(value, BaseException):
            raise value
        return {"choices": [{"message": {"content": value if isinstance(value, str) else json.dumps(value)}}]}

    for module in (gameplay_stage, visual_stage, vfx_transport):
        monkeypatch.setattr(module, "USE_LLM", True)
    for module in (gameplay_stage, visual_request, vfx_transport):
        monkeypatch.setattr(module, "resolve_llm_model", lambda: "test-model")
        monkeypatch.setattr(module, "llm_chat_json", reply)
    monkeypatch.setattr(visual_stage_stage, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setenv("INFINI_VISUAL_DIRECTOR_TEMPERATURE", "0.5")
    monkeypatch.setenv("INFINI_VISUAL_REPAIR_TEMPERATURE", "0.12")
    monkeypatch.setattr(vfx_stage_config, "VFX_LLM_DIRECTOR_TEMPERATURE", 0.5)
    monkeypatch.setattr(vfx_stage_config, "VFX_LLM_REPAIR_TEMPERATURE", 0.12)
    return responses, requests


@pytest.mark.parametrize("fixture_name,repair_needed", [
    pytest.param("workbench_blade", False, id="happy-three-stages"),
    pytest.param("door_on_chain", True, id="conditional-local-visual-and-vfx-repair"),
])
def test_three_stage_wire_and_conditional_repairs(wire_transport, fixture_name, repair_needed):
    responses, requests = wire_transport
    authored = build_runtime_fixture(fixture_name)
    responses.append(authored)
    planned = gameplay_stage.try_llm_plan({"name": "A"}, {"name": "B"}, "a+b")
    assert planned is not None
    assert planned["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] == 1
    compiled = compile_runtime_program(planned)
    compiled["debug"] = copy.deepcopy(planned["debug"])
    responses.append({"schema": visual_stage_contract.VISUAL_KIT_SCHEMA, "item": {}, "entities": [],
                      "animationPlan": "already valid animation"} if repair_needed else _visual_kit(compiled))
    if repair_needed:
        responses.append(_visual_patch(compiled))
    visual = visual_stage_stage.apply_visual_director(compiled, {}, {})
    assert visual["debug"]["llmStageAccounting"]["visualDirectorCalls"] == 1
    assert visual["debug"]["llmStageAccounting"]["visualRepairCalls"] == int(repair_needed)
    if repair_needed:
        assert visual["visualKit"]["animationPlan"] == "already valid animation"
    authored_vfx = _vfx_output(visual)
    broken_vfx = copy.deepcopy(authored_vfx)
    if repair_needed:
        broken_vfx["slots"][0]["alpha"] = 2
    responses.append(broken_vfx)
    if repair_needed:
        responses.append({"schema": VFX_REPAIR_PATCH_SCHEMA,
                          "slotsUpsert": authored_vfx["slots"],
                          "note": "repair only alpha"})
    final = attach_vfx_manifest(visual, "a+b", llm_director=vfx_transport.call_llm_vfx_director)
    expected_stages = ["planner", "visual_director"] + (["visual_repair"] if repair_needed else [])
    expected_stages += ["vfx_director"] + (["vfx_repair"] if repair_needed else [])
    assert [request["_infini_stage"] for request in requests] == expected_stages
    packet = request_dossier(next(request for request in requests if request["_infini_stage"] == "vfx_director"))
    assert packet["item"]["description"] == visual["realization"]["description"]
    assert packet["item"]["playerExperience"] == visual["realization"]["playerExperience"]
    assert "behaviorChecks" not in packet["item"]
    assert packet["acceptedVisualKit"] == visual["visualKit"]
    mechanics = copy.deepcopy(visual["runtimeProgram"])
    for entity in mechanics["entities"]:
        entity.pop("visual", None)
    assert packet["acceptedRuntimeProgramReadOnly"] == mechanics
    assert final["debug"]["llmStageAccounting"] == {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 0,
        "visualDirectorCalls": 1, "visualRepairCalls": int(repair_needed),
        "vfxDirectorCalls": 1, "vfxRepairCalls": int(repair_needed),
    }
    assert final["vfxManifest"]["slots"][0]["id"] == authored_vfx["slots"][0]["id"]
    assert [r["temperature"] for r in requests if r["_infini_stage"].startswith("visual")] == ([0.5, 0.12] if repair_needed else [0.5])
    assert [r["temperature"] for r in requests if r["_infini_stage"].startswith("vfx")] == ([0.5, 0.12] if repair_needed else [0.5])
    assert not responses
    _assert_stage_topology(final)


@pytest.mark.parametrize("scenario", ["recoverable", "long"])
def test_vfx_conditional_expression_uses_its_single_scoped_repair(wire_transport, monkeypatch, scenario):
    responses, requests = wire_transport
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    data = visual_stage_stage._apply_kit(data, _visual_kit(data))
    valid = _vfx_output(data)
    if scenario == "long":
        monkeypatch.setattr(vfx_stage_config, "VFX_LLM_DIRECTOR_MAX_SLOTS", 12)
        valid["slots"] = [{**copy.deepcopy(valid["slots"][0]), "id": f"slot_{i}"} for i in range(12)]
    raw = json.dumps(valid, indent=2).replace('"layer": "BeforeProjectiles"', '"layer": "Projectiles" if false else "BeforeProjectiles"', 1)
    if scenario == "long":
        assert len(raw) > 12000 and raw.rfind('"endOpacity"') > 12000
    patch = {"schema": VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": valid["slots"],
             "slotIdsDelete": [], "slotIndicesDelete": [], "note": "strict JSON"}
    responses.extend([raw, patch])
    result = attach_vfx_manifest(data, "a+b", llm_director=vfx_transport.call_llm_vfx_director)
    assert [request["_infini_stage"] for request in requests] == ["vfx_director", "vfx_repair"]
    context = request_dossier(requests[1])
    assert context["malformedRawText"] == raw
    assert context["exactErrors"][0]["message"].startswith("malformed_json: JSONDecodeError:")
    assert result["vfxManifest"]["slots"][0]["layer"] == "BeforeProjectiles"
    assert result["debug"]["vfxDirectorRaw"] == valid
    assert result["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert not responses


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "downgraded"])
@pytest.mark.parametrize("rewrite", [False, True], ids=["same-design", "changed-design"])
def test_visual_format_repair_uses_source_transport_semantics(wire_transport, monkeypatch, mode, rewrite):
    responses, requests = wire_transport
    monkeypatch.setattr("infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE",
                        "json_object" if mode == "json_object" else "json_schema")
    reply = visual_request.llm_chat_json

    def with_transport_metadata(request, **kwargs):
        result = reply(request, **kwargs)
        if mode == "downgraded" and request["_infini_stage"] == "visual_director":
            result["_debug"] = {"strictSchemaDowngraded": True, "responseFormatType": "json_object"}
        return result

    monkeypatch.setattr(visual_request, "llm_chat_json", with_transport_metadata)
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    kit = _visual_kit(data)
    # Strict provider optionals encode absence as null. In schema-free replies
    # the same null is an invalid authored value and cannot be silently erased.
    source = copy.deepcopy(kit)
    source["item"]["grip"] = None
    source["animationPlan"] = None
    patch = _visual_patch(data)
    patch["itemPatch"]["grip"] = {"normalizedX": 0.5, "normalizedY": 0.5}
    if rewrite:
        patch["itemPatch"]["visualIdentity"] = "a different visual design"
    raw = json.dumps(source)[:-1] + ",}"
    responses.append(raw)
    if mode != "json_schema":
        responses.append(patch)
    result = visual_stage_stage.apply_visual_director(data, {}, {})
    expected = copy.deepcopy(kit)
    expected.pop("animationPlan")
    if mode != "json_schema":
        expected["item"]["grip"] = patch["itemPatch"]["grip"]
        expected["animationPlan"] = None
    assert result["visualKit"] == expected
    assert result["debug"]["visualDirectorRawText"] == raw
    assert [request["_infini_stage"] for request in requests] == (["visual_director"] if mode == "json_schema" else ["visual_director", "visual_repair"])
    if mode != "json_schema":
        assert not request_dossier(requests[1])["malformedRawText"]
    assert not responses


def test_vfx_repair_receives_every_diagnosis_and_preserves_valid_leaves(wire_transport, monkeypatch):
    from infini_local.core.vfx.materials import vfx_model_context
    from infini_local.core.vfx.validation import validate_vfx_director_output

    responses, requests = wire_transport
    monkeypatch.setattr(vfx_stage_config, "VFX_LLM_DIRECTOR_MAX_SLOTS", 12)
    data = _accepted_visual_data("workbench_blade")
    valid = _vfx_output(data)
    valid["slots"] = [{**copy.deepcopy(valid["slots"][0]), "id": f"slot_{i}"} for i in range(12)]
    assert validate_vfx_director_output(valid, data)["ok"]
    broken = copy.deepcopy(valid)
    for slot in broken["slots"]:
        slot.update(duration=-1, startTick=-1, repeatEvery=-1)
    report = validate_vfx_director_output(broken, data)
    assert len(report["errors"]) > 24
    repaired_slots = copy.deepcopy(valid["slots"])
    for slot in repaired_slots:
        slot["alpha"] = 0.1  # Unrelated valid leaves must remain frozen.
    responses.extend([broken, {"schema": VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": repaired_slots,
                              "note": "Repair timing only; ignore the unrelated alpha rewrite"}])
    result = attach_vfx_manifest(data, "all-vfx-errors", llm_director=vfx_transport.call_llm_vfx_director)
    expected_errors = vfx_model_context({"exactErrors": report["errors"]})["exactErrors"]
    assert request_dossier(requests[1])["exactErrors"] == expected_errors
    assert result["debug"]["vfxDirectorRaw"] == valid
    assert result["debug"]["vfxRepairFilterAudit"]["ignoredChanges"]
    assert result["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert not responses


@pytest.mark.parametrize("scenario", ["complete-delete", "sparse-delete", "name-only", "use-style-frozen", "echo-read-only", "registry-defect"])
def test_author_repair_wire_admission_and_frozen_results(wire_transport, scenario):
    responses, requests = wire_transport
    current = build_runtime_fixture("workbench_blade")
    current["debug"] = {"llmStageAccounting": {"gameplayAuthorCalls": 1}}
    patch = _empty_gameplay_patch()
    if scenario in {"complete-delete", "sparse-delete"}:
        current["runtimeProgram"]["bindings"].append(_binding_row("bad_primary", "primary_use", "spawn_entity", "nail"))
        patch["bindingIdsDelete"] = ["bad_primary"]
        if scenario == "sparse-delete":
            patch = {"bindingIdsDelete": ["bad_primary"], "note": "remove only duplicate binding"}
        failure = {"stage": "strict_author_validation", "errors": [{"path": "$.runtimeProgram.bindings[1].input", "code": "duplicate_exclusive_input", "message": "duplicate"}]}
    elif scenario == "name-only":
        current["name"] = "Workbench"
        patch["metadataPatch"] = {"name": "Workbench Blade"}
        failure = {"errors": [{"path": "$.name", "code": "uncombined_identity", "message": "provide an authored combined identity"}]}
    elif scenario == "registry-defect":
        failure = {"errors": [{"path": "$.runtimeProgram.calls[0]", "code": "unknown_registry_requirement", "message": "developer defect", "allowed": [], "relatedIds": []}]}
    else:
        use = next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_use")
        use["params"].pop("useStyle")
        stats = next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_stats")
        stats["params"]["damage"] = 1999
        fixed = copy.deepcopy(use)
        fixed["params"].update(useStyle="shoot", hideUseGraphic=False)
        frozen_stats = copy.deepcopy(stats)
        frozen_stats["params"]["damage"] = 999
        patch["callsUpsert"] = [fixed, frozen_stats]
        if scenario == "echo-read-only":
            patch["brokenFragments"] = {"calls": [fixed]}
        failure = {"stage": "strict_author_validation", "errors": validate_runtime_program(current)["errors"]}
    patch["realizationReplacement"] = copy.deepcopy(current["realization"])
    if scenario != "registry-defect":
        responses.append(patch)
    match = {"echo-read-only": "additional_property", "registry-defect": "registry/runtime defect"}.get(scenario)
    with pytest.raises(PlannerUnavailable, match=match) if match else nullcontext():
        repaired = gameplay_stage.repair_author_item_after_failure(current, {}, {}, "key", failure_report=failure)
    if scenario == "registry-defect":
        assert requests == []
        return
    assert len(requests) == 1
    assert requests[0]["_infini_stage"] == "author_repair"
    if match:
        return
    assert validate_runtime_program(repaired)["ok"]
    assert repaired["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1
    assert repaired["debug"]["llmStageAccounting"]["visualDirectorCalls"] == 0
    assert [row["role"] for row in requests[0]["messages"]] == ["system", "developer", "user"]
    assert requests[0]["messages"][-1]["name"] == "author_repair_context"
    context = json.loads(requests[0]["messages"][-1]["content"])
    assert "callsUpsert" in context["requiredJsonShape"] and "brokenFragments" not in context["requiredJsonShape"]
    assert "readOnlySourceFragments" in context
    if scenario in {"complete-delete", "sparse-delete"}:
        assert all(row["id"] != "bad_primary" for row in repaired["runtimeProgram"]["bindings"])
        assert repaired["debug"]["gameplayRepairRawPatch"] == patch
        if scenario == "sparse-delete":
            assert "requiredRootFields" not in context
    elif scenario == "name-only":
        assert repaired["name"] == "Workbench Blade"
    else:
        prompt = dossier_text(requests[0])
        assert '"currentItem"' not in prompt and '"item_use"' in prompt and '"item_stats"' in prompt
        assert context["acceptedItemContext"]["runtimeProgram"] == current["runtimeProgram"]
        calls = {c["id"]: c for c in repaired["runtimeProgram"]["calls"]}
        assert calls["item_use"]["params"]["useStyle"] == "shoot"
        assert calls["item_use"]["params"]["hideUseGraphic"] is True
        assert calls["item_stats"]["params"]["damage"] == 1999
        assert any(row["reason"] == "independent_valid_node_frozen" for row in repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"])


# Exact numeric leaves, row positions and healing alternatives belong to
# test_repair_gameplay_contract. Here test only their full-pipeline handoff.
@pytest.mark.parametrize("case,mode", [
    pytest.param("malformed", "json_object", id="object-delete-malformed-row"),
    pytest.param("malformed-noop", "json_schema", id="schema-reject-malformed-noop"),
    pytest.param("huge-number", "json_schema", id="schema-json-integer-overflow"),
    pytest.param("empty-healing", "json_object", id="object-empty-effect"),
])
def test_author_repair_defects_use_one_real_scoped_pipeline(wire_transport, monkeypatch, mode, case):
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.qa.capability_witnesses import build_capability_witness

    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    responses, requests = wire_transport
    fn = "generated_buff_on_use" if case == "huge-number" else "restore_resources_on_use"
    good = build_capability_witness(fn)
    current = copy.deepcopy(good)
    calls = current["runtimeProgram"]["calls"]
    node = next(row for row in calls if row["fn"] == fn)
    patch = {"note": "exact authored defect", "realizationReplacement": good["realization"]}
    permissions = []
    if case.startswith("malformed"):
        calls.insert(0, None)
        if case != "malformed-noop":
            patch["callIndicesDelete"] = [0]
    else:
        patch["callsUpsert"] = [copy.deepcopy(node)]
        if case == "huge-number":
            node["params"]["miningSpeedMultiplier"] = 10**400
            paths = ["params.miningSpeedMultiplier"]
        else:
            node["params"].update(healLife=0, healMana=0, usesPotionRules=False)
            paths = ["params.healLife", "params.healMana"]
        permissions = [{"id": node["id"], "paths": paths}]
    responses.extend([json.dumps(current, allow_nan=False), json.dumps(patch, allow_nan=False)])
    planned = gameplay_stage.try_llm_plan({}, {}, "scoped-author-repair")
    assert planned is not None and planned["runtimeProgram"] == current["runtimeProgram"]
    original = copy.deepcopy(planned)
    match = "leaves a reported repair error open" if case == "malformed-noop" else None
    with pytest.raises(PlannerUnavailable, match=match) if match else nullcontext():
        result = combine_stage.compile_and_validate_authored_runtime(
            planned, {}, {}, "scoped-author-repair", run_stage=lambda _label, fn, *a, **kw: fn(*a, **kw))
        assert validate_runtime_wire(result)["ok"]
        assert result["runtimeProgram"] == compile_runtime_program(good)["runtimeProgram"]
        assert result["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1
    assert {k: v for k, v in planned.items() if k != "debug"} == {k: v for k, v in original.items() if k != "debug"}
    assert [r["_infini_stage"] for r in requests] == ["planner", "author_repair"]
    assert all(r["response_format"]["type"] == mode for r in requests)
    dossier = request_dossier(requests[1])
    assert dossier["exactValidationErrors"] == validate_runtime_program(current)["errors"]
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == permissions
    assert dossier["readOnlySourceFragments"]["brokenFragmentsByIndex"]["calls"] == (
        [{"index": 0, "value": None}] if case.startswith("malformed") else [])
    assert not responses


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_bounded_diagnostic_completeness_reaches_the_single_pipeline_repair(wire_transport, monkeypatch, mode):
    fields = ("buffId", "durationTicks")
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from test_pipeline_repair_contract import _bounded_invalid_buff_calls

    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    responses, requests = wire_transport
    current, good = _bounded_invalid_buff_calls(fields)
    assert validate_runtime_program(good)["ok"]
    assert validate_runtime_wire(compile_runtime_program(good))["ok"]
    original = copy.deepcopy(current)
    canonical_errors = validate_runtime_program(current)["errors"]
    broken = [row for row in good["runtimeProgram"]["calls"] if row["fn"] == "native_buff_on_use"]
    candidates = copy.deepcopy(good["runtimeProgram"]["calls"])
    candidates[0]["params"]["damage"] = 100
    patch = {"note": "repair every diagnosed duration", "realizationReplacement": good["realization"], "callsUpsert": candidates}
    responses.extend([json.dumps(current, allow_nan=False), json.dumps(patch, allow_nan=False)])
    planned = gameplay_stage.try_llm_plan({}, {}, "complete-bounded-diagnostics")
    assert planned is not None
    result = combine_stage.compile_and_validate_authored_runtime(planned, {}, {}, "complete-bounded-diagnostics", run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs))
    assert validate_runtime_wire(result)["ok"]
    expected = compile_runtime_program(good)
    assert result["runtimeProgram"] == expected["runtimeProgram"]
    assert result["gameplay"] == expected["gameplay"]
    assert current == original
    assert [r["_infini_stage"] for r in requests] == ["planner", "author_repair"]
    assert all(r["response_format"]["type"] == mode for r in requests)
    assert result["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1
    dossier = request_dossier(requests[1])
    assert len(canonical_errors) == len(broken) * (len(fields) + 1)
    assert dossier["exactValidationErrors"] == canonical_errors
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == sorted(
        [{"id": row["id"], "paths": ["params." + field for field in fields]} for row in broken], key=lambda row: row["id"])
    assert result["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert not responses


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("oversized_surface", ["calls", "unknown-root"])
def test_oversized_author_response_refuses_before_format_or_gameplay_repair(wire_transport, monkeypatch, mode, oversized_surface):
    import infini_local.core.runtime_authoring.program_schema as program_schema

    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    responses, requests = wire_transport
    current = build_runtime_fixture("workbench_blade")
    nodes, _, _, _ = program_schema._author_schema_work_bounds(program_schema.author_item_response_schema())
    if oversized_surface == "calls":
        current["runtimeProgram"]["calls"] = [current["runtimeProgram"]["calls"][0]] * (nodes + 1)
    else:
        current["not_pipeline_metadata"] = [None] * (nodes + 1)
    responses.append(json.dumps(current))
    with pytest.raises(PlannerUnavailable, match="Author input exceeds schema-derived work bounds"):
        gameplay_stage.try_llm_plan({}, {}, "oversized-author-input")
    assert [request["_infini_stage"] for request in requests] == ["planner"]
    assert requests[0]["response_format"]["type"] == mode
    assert not responses


@pytest.mark.parametrize("patch,ok", [
    pytest.param({"note": "targeted", "callsUpsert": []}, True, id="sparse-valid"),
    pytest.param({"note": "targeted", "callsUpsert": {}}, False, id="wrong-container"),
    pytest.param({"note": "targeted", "extraGameplay": []}, False, id="unknown-root"),
    pytest.param({"callsUpsert": []}, False, id="missing-note"),
])
def test_sparse_patch_shape(patch, ok):
    assert strict_repair_shape_report(patch)["ok"] is ok


@pytest.mark.parametrize("scenario,expected,cutoff", [
    pytest.param("valid", ["author_validation", "runtime_compile", "initial_final_wire"], None, id="validated-before-compile-and-wire"),
    pytest.param("scoped-fix", ["author_validation", "author_recovery", "runtime_compile", "recovered_final_wire"], None, id="one-scoped-recovery-before-recompile"),
    pytest.param("no-op", ["author_validation", "author_recovery"], "author_recovery", id="bad-repair-stops-before-compilation"),
    pytest.param("spent-budget", ["author_validation"], "author_validation", id="spent-budget-stops-before-second-repair"),
])
def test_author_compile_phase_order_and_failure_cutoffs(wire_transport, scenario, expected, cutoff):
    from contract_checks import PIPELINE_PHASE_MARKERS
    responses, requests = wire_transport
    current = build_runtime_fixture("workbench_blade")
    current["debug"] = {"llmStageAccounting": {"gameplayAuthorCalls": 1, "gameplayRepairCalls": int(scenario == "spent-budget")}}
    if scenario != "valid":
        use = next(c for c in current["runtimeProgram"]["calls"] if c["id"] == "item_use")
        use["params"].pop("useStyle")
        if scenario != "spent-budget":
            fixed = copy.deepcopy(use)
            if scenario == "scoped-fix":
                fixed["params"]["useStyle"] = "shoot"
            responses.append(dict(_empty_gameplay_patch(), callsUpsert=[fixed] if scenario == "scoped-fix" else [], realizationReplacement=copy.deepcopy(current["realization"])))
    labels = []
    stage_labels = []
    recovered = False

    def observe(_label, fn, *args, **kwargs):
        nonlocal recovered
        stage_labels.append(_label)
        phases = {combine_stage.strict_validate_authored_item: "author_validation",
                  combine_stage.attach_gameplay_and_runtime_program: "runtime_compile",
                  combine_stage.repair_author_item_after_failure: "author_recovery"}
        if fn is combine_stage.validate_final_runtime_wire_boundary:
            phase = "recovered_final_wire" if recovered else "initial_final_wire"
        else:
            phase = phases.get(fn)
        if phase:
            labels.append(PIPELINE_PHASE_MARKERS[phase][0])
        if phase == "runtime_compile":
            assert_pipeline_phase_order(labels, "author_validation", "runtime_compile")
        if phase == "author_recovery":
            recovered = True
        return fn(*args, **kwargs)

    match = {"no-op": "leaves a reported repair error open", "spent-budget": "repair budget already consumed"}.get(scenario)
    with pytest.raises(PlannerUnavailable, match=match) if match else nullcontext():
        result = combine_stage.compile_and_validate_authored_runtime(current, {}, {}, "a+b", run_stage=observe)
        assert result["runtimeProgram"]["entities"]
    assert_pipeline_phase_order(labels, *expected)
    if cutoff:
        assert_pipeline_terminal_phase(labels, cutoff)
    else:
        assert_pipeline_terminal_phase(labels, expected[-1])
    assert pipeline_phase_count(labels, "author_recovery") == int(scenario in {"scoped-fix", "no-op"})
    assert pipeline_phase_count(labels, "runtime_compile") == int(cutoff is None)
    assert [r["_infini_stage"] for r in requests] == (["author_repair"] if scenario in {"scoped-fix", "no-op"} else [])
    assert not responses

    domain_labels = ["strict_runtime_program", "compile_runtime_program", "wire_boundary"]
    expected_labels = {
        "valid": ["02_" + label for label in domain_labels],
        "scoped-fix": ["02_strict_runtime_program", "02r_conditional_gameplay_repair"]
            + ["02r_" + label for label in domain_labels],
        "no-op": ["02_strict_runtime_program", "02r_conditional_gameplay_repair"],
        "spent-budget": ["02_strict_runtime_program"],
    }
    assert stage_labels == expected_labels[scenario]


@pytest.mark.parametrize("error_type", [RuntimeError, AssertionError, TypeError, ValueError])
@pytest.mark.parametrize("after_repair", [False, True])
def test_compiler_faults_propagate_without_gameplay_repair(monkeypatch, error_type, after_repair):
    good = build_runtime_fixture("workbench_blade")
    current = copy.deepcopy(good)
    if after_repair:
        current["name"] = ""
    repair_calls = []

    def repair(*args, **kwargs):
        repair_calls.append(kwargs["failure_report"])
        return copy.deepcopy(good)

    fault = error_type("compiler invariant failed")

    def broken_compiler(*args, **kwargs):
        raise fault

    monkeypatch.setattr(combine_stage, "compile_runtime_program", broken_compiler)
    monkeypatch.setattr(combine_stage, "repair_author_item_after_failure", repair)
    with pytest.raises(error_type) as caught:
        combine_stage.compile_and_validate_authored_runtime(
            current, {}, {}, "compiler-fault", run_stage=lambda _label, fn, *a, **kw: fn(*a, **kw))
    assert caught.value is fault
    assert len(repair_calls) == int(after_repair)


def test_runtime_wire_admission_once_and_final_gate_still_rejects_mutation(monkeypatch):
    validate = combine_stage.validate_runtime_wire
    calls = []

    def observe(data):
        calls.append(data)
        return validate(data)

    monkeypatch.setattr(combine_stage, "validate_runtime_wire", observe)
    result = combine_stage.compile_and_validate_authored_runtime(
        build_runtime_fixture("workbench_blade"), {}, {}, "single-admission",
        run_stage=lambda _label, fn, *a, **kw: fn(*a, **kw))
    assert len(calls) == 1
    result["runtimeProgram"]["schema"] = "invalid-after-presentation"
    with pytest.raises(PlannerUnavailable, match="runtime wire rejected"):
        combine_stage.validate_final_runtime_wire_boundary(result)
    assert len(calls) == 2


def test_wire_rejection_preserves_exact_repair_targets(monkeypatch):
    validate = combine_stage.validate_runtime_wire
    target = {"path": "$.runtimeProgram.entities[0]", "code": "wire_rejection", "message": "invalid wire leaf"}
    reports = []
    count = 0

    def reject_once(data):
        nonlocal count
        count += 1
        return {"ok": False, "errors": [target]} if count == 1 else validate(data)

    def repair(authored, *args, **kwargs):
        reports.append(kwargs["failure_report"])
        return authored

    monkeypatch.setattr(combine_stage, "validate_runtime_wire", reject_once)
    monkeypatch.setattr(combine_stage, "repair_author_item_after_failure", repair)
    result = combine_stage.compile_and_validate_authored_runtime(
        build_runtime_fixture("workbench_blade"), {}, {}, "wire-rejection",
        run_stage=lambda _label, fn, *a, **kw: fn(*a, **kw))
    assert validate(result)["ok"]
    assert count == 2 and len(reports) == 1
    assert reports[0]["errors"] == [target]


@pytest.mark.parametrize("existing", [None, {}, {
    "gameplayAuthorCalls": 1, "visualRepairCalls": 1, "futureCounter": 7,
}])
def test_stage_accounting_initialization_preserves_spent_budgets_and_debug(existing):
    from infini_local.core.llm_stage_messages import stage_accounting

    debug = {"unrelated": {"retained": True}}
    if existing is not None:
        debug["llmStageAccounting"] = copy.deepcopy(existing)
    data = {"debug": debug}
    original = debug.get("llmStageAccounting")
    counters = stage_accounting(data)
    assert data["debug"] is debug
    assert counters is debug["llmStageAccounting"]
    if original is not None:
        assert counters is original
    expected = {
        "gameplayAuthorCalls": 0, "gameplayRepairCalls": 0,
        "visualDirectorCalls": 0, "visualRepairCalls": 0,
        "vfxDirectorCalls": 0, "vfxRepairCalls": 0,
    }
    expected.update(existing or {})
    assert counters == expected
    counters["vfxRepairCalls"] += 1
    assert stage_accounting(data) is counters
    assert counters == {**expected, "vfxRepairCalls": 1}
    assert debug["unrelated"] == {"retained": True}


def test_stage_accounting_initializes_missing_debug_without_changing_item():
    from infini_local.core.llm_stage_messages import stage_accounting

    data = {"name": "accepted item"}
    counters = stage_accounting(data)
    assert data == {"name": "accepted item", "debug": {"llmStageAccounting": counters}}
    assert len(counters) == 6
    assert all(value == 0 for value in counters.values())
