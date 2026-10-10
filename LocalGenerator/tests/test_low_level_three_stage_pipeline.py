from __future__ import annotations
from contextlib import nullcontext

import copy
import json

import pytest

import infini_local.pipelines.llm_authoring_pipeline as gameplay_stage
import infini_local.pipelines.combine_pipeline as combine_stage
import infini_local.pipelines.visual_generation_pipeline as visual_stage
import infini_local.core.vfx_manifest as vfx_stage
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_program
from infini_local.core.vfx_manifest import VFX_DIRECTOR_SCHEMA, VFX_REPAIR_PATCH_SCHEMA, attach_hybrid_vfx_manifest, vfx_director_surface
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


def _accepted_visual_data(fixture_name: str) -> dict:
    data = compile_runtime_program(build_runtime_fixture(fixture_name))
    runtime = data["runtimeProgram"]
    kit, errors = visual_stage._validate_kit(
        _visual_kit(data), [row["id"] for row in runtime["entities"]], runtime["itemEntityId"],
    )
    assert kit is not None, errors
    # VFX follows Visual in production; a mechanics-only compiler result or an
    # ignored visualKit assignment does not project the actual PNG producers.
    return visual_stage._apply_kit(data, kit)


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
        if isinstance(value, BaseException):
            raise value
        return {"choices": [{"message": {"content": value if isinstance(value, str) else json.dumps(value)}}]}

    for module in (gameplay_stage, visual_stage):
        monkeypatch.setattr(module, "USE_LLM", True)
        monkeypatch.setattr(module, "resolve_llm_model", lambda: "test-model")
        monkeypatch.setattr(module, "llm_chat_json", reply)
    monkeypatch.setattr(visual_stage, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setenv("INFINI_VISUAL_DIRECTOR_TEMPERATURE", "0.5")
    monkeypatch.setenv("INFINI_VISUAL_REPAIR_TEMPERATURE", "0.12")
    monkeypatch.setattr(vfx_stage, "VFX_LLM_DIRECTOR_TEMPERATURE", 0.5)
    monkeypatch.setattr(vfx_stage, "VFX_LLM_REPAIR_TEMPERATURE", 0.12)
    return responses, requests


@pytest.mark.parametrize("fixture_name,repair_needed", [
    pytest.param("workbench_blade", False, id="happy-three-stages"),
    pytest.param("door_on_chain", True, id="conditional-local-visual-and-vfx-repair"),
])
def test_three_stage_wire_and_conditional_repairs(wire_transport, fixture_name, repair_needed):
    responses, requests = wire_transport
    authored = build_runtime_fixture(fixture_name)
    responses.append(authored)
    planned = gameplay_stage.try_llm_plan({"name": "A"}, {"name": "B"}, {}, {}, "a+b")
    assert planned is not None
    assert planned["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] == 1
    compiled = compile_runtime_program(planned)
    compiled["debug"] = copy.deepcopy(planned["debug"])
    responses.append({"schema": visual_stage.VISUAL_KIT_SCHEMA, "item": {}, "entities": [],
                      "animationPlan": "already valid animation"} if repair_needed else _visual_kit(compiled))
    if repair_needed:
        responses.append(_visual_patch(compiled))
    visual = visual_stage.apply_visual_director(compiled, {}, {}, {}, {})
    assert visual["debug"]["llmStageAccounting"]["visualDirectorCalls"] == 1
    assert visual["debug"]["llmStageAccounting"]["visualRepairCalls"] == int(repair_needed)
    if repair_needed:
        assert visual["visualKit"]["animationPlan"] == "already valid animation"
    authored_vfx = _vfx_output(visual)
    responses.append(dict(authored_vfx, effectMagnitude=2.0) if repair_needed else authored_vfx)
    if repair_needed:
        responses.append({"schema": VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": 0.5,
                          "visualBudgetClass": None, "motif": None, "slotsUpsert": [],
                          "slotIdsDelete": [], "slotIndicesDelete": [], "note": "repair only magnitude"})
    final = attach_hybrid_vfx_manifest(visual, "a+b", llm_director=gameplay_stage.call_llm_vfx_director)
    expected_stages = ["planner", "visual_director"] + (["visual_repair"] if repair_needed else [])
    expected_stages += ["vfx_director"] + (["vfx_repair"] if repair_needed else [])
    assert [request["_infini_stage"] for request in requests] == expected_stages
    packet = json.loads(next(request for request in requests if request["_infini_stage"] == "vfx_director")["messages"][1]["content"])
    assert packet["item"]["behaviorChecks"] == visual["realization"]["selfEvaluation"]["programVsReport"]["behaviorChecks"]
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


FORMAT_CASES = [
    pytest.param("gameplay", "recoverable", None, id="author-syntax-only"),
    pytest.param("gameplay", "absent", "recoverable", id="author-cannot-invent-design"),
    pytest.param("gameplay", "rewrite", "recoverable", id="author-cannot-rewrite-damage"),
    pytest.param("gameplay", "budget", "repair budget already consumed", id="syntax-and-semantic-share-one-budget"),
    pytest.param("visual", "recoverable", None, id="visual-syntax-only"),
    pytest.param("visual", "rewrite", "recoverable", id="visual-cannot-rewrite-identity"),
    pytest.param("visual", "absent", "recoverable", id="visual-cannot-invent-design"),
    pytest.param("visual", "empty", "entity-complete visual kit", id="visual-one-repair-no-substitution"),
    pytest.param("vfx", "recoverable", None, id="vfx-conditional-expression-to-strict-json"),
]


@pytest.mark.parametrize("stage,scenario,rejection", FORMAT_CASES)
def test_single_format_repair_preserves_recoverable_design(wire_transport, stage, scenario, rejection):
    responses, requests = wire_transport
    authored = build_runtime_fixture("workbench_blade")
    data = compile_runtime_program(authored)
    kit: dict = {}
    data["debug"] = {"planner": "llm_low_level_runtime_author", "llmStageAccounting": {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 0,
        "visualDirectorCalls": int(stage == "vfx"), "visualRepairCalls": 0,
        "vfxDirectorCalls": 0, "vfxRepairCalls": 0,
    }}
    if stage == "gameplay":
        if scenario == "budget":
            next(c for c in authored["runtimeProgram"]["calls"] if c["id"] == "item_stats")["params"].pop("damage")
        raw = json.dumps(authored)[:-1] + ",}"
        patch = copy.deepcopy(authored)
        if scenario == "absent":
            raw = '{"name":"broken",'
        elif scenario == "rewrite":
            next(c for c in patch["runtimeProgram"]["calls"] if c["id"] == "item_stats")["params"]["damage"] += 1
    elif stage == "visual":
        kit = _visual_kit(data)
        raw = json.dumps(kit)[:-1] + ",}"
        patch = _visual_patch(data)
        patch["animationPlan"] = kit["animationPlan"]
        if scenario == "rewrite":
            patch["itemPatch"]["visualIdentity"] = "replaced concept"
            for row in patch["entitiesUpsert"]:
                if "visualIdentity" in row:
                    row["visualIdentity"] = "replaced concept"
        elif scenario in {"absent", "empty"}:
            raw = '{"schema":'
            if scenario == "empty":
                patch.update(itemPatch=None, entitiesUpsert=[], animationPlan=None)
    else:
        data = visual_stage._apply_kit(data, _visual_kit(data))
        valid = _vfx_output(data)
        raw = json.dumps(valid).replace('"layer": "BeforeProjectiles"', '"layer": "Projectiles" if false else "BeforeProjectiles"', 1)
        patch = {"schema": VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": valid["effectMagnitude"],
                 "visualBudgetClass": valid["visualBudgetClass"], "motif": valid["motif"],
                 "slotsUpsert": valid["slots"], "slotIdsDelete": [], "slotIndicesDelete": [], "note": "strict JSON"}
    responses.extend([raw, patch])
    result = None
    with pytest.raises(PlannerUnavailable, match=rejection) if rejection else nullcontext():
        if stage == "gameplay":
            result = gameplay_stage.try_llm_plan({}, {}, {}, {}, "a+b")
            assert result is not None
            if scenario == "budget":
                combine_stage.compile_and_validate_authored_runtime(result, {}, {}, {}, {}, "a+b",
                    run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs))
        elif stage == "visual":
            result = visual_stage.apply_visual_director(data, {}, {}, {}, {})
        else:
            result = attach_hybrid_vfx_manifest(data, "a+b", llm_director=gameplay_stage.call_llm_vfx_director)
    names = {"gameplay": ["planner", "author_repair"], "visual": ["visual_director", "visual_repair"], "vfx": ["vfx_director", "vfx_repair"]}[stage]
    assert [request["_infini_stage"] for request in requests] == names
    assert not responses  # Any unbounded third request fails the recording transport too.
    context = json.loads(requests[1]["messages"][1]["content"])
    assert context["malformedRawText"] == raw
    if stage == "gameplay":
        assert context["task"].startswith("Repair JSON syntax only")
        assert "multiple" not in context["allowedCallParamsReadOnly"]["spawn_entity_on_event"]
        assert "count" in context["allowedCallParamsReadOnly"]["spawn_entity_on_event"]
        assert "do not invent undeclared params" in requests[1]["messages"][0]["content"]
    else:
        assert context["exactErrors"][0]["message"].startswith("malformed_json:")
        if stage == "vfx":
            assert context["exactErrors"][0]["message"].startswith("malformed_json: JSONDecodeError:")
    if result is not None:
        keys = {"gameplay": ("gameplayAuthorCalls", "gameplayRepairCalls"),
                "visual": ("visualDirectorCalls", "visualRepairCalls"), "vfx": ("vfxDirectorCalls", "vfxRepairCalls")}[stage]
        assert [result["debug"]["llmStageAccounting"][key] for key in keys] == [1, 1]
        if stage == "gameplay":
            assert json.loads(result["_llmHistory"]["messages"][-1]["content"])["runtimeProgram"] == authored["runtimeProgram"]
        elif stage == "visual":
            assert result["visualKit"]["item"]["visualIdentity"] == "literal composition"
            assert result["visualKit"]["animationPlan"] == kit["animationPlan"]
        else:
            assert result["vfxManifest"]["slots"][0]["layer"] == "BeforeProjectiles"
    if stage == "visual" and scenario == "empty":
        assert data["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1


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
        fixed["params"].update(useStyle="shoot", customHeldSprite="visible")
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
        repaired = gameplay_stage.repair_author_item_after_failure(current, {}, {}, {}, {}, "key", failure_report=failure)
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
    assert len(requests[0]["messages"]) == 2
    assert requests[0]["messages"][-1]["name"] == "author_repair_context"
    context = json.loads(requests[0]["messages"][-1]["content"])
    assert list(context)[-1] == "requiredJsonShape"
    assert "callsUpsert" in context["requiredJsonShape"] and "brokenFragments" not in context["requiredJsonShape"]
    assert "readOnlySourceFragments" in context
    if scenario in {"complete-delete", "sparse-delete"}:
        assert all(row["id"] != "bad_primary" for row in repaired["runtimeProgram"]["bindings"])
        assert repaired["debug"]["gameplayRepairRawPatch"] == patch
        if scenario == "sparse-delete":
            assert "Omit unchanged root patch fields" in requests[0]["messages"][0]["content"]
            assert "note and realizationReplacement are required" in requests[0]["messages"][0]["content"]
            assert "requiredRootFields" not in context
    elif scenario == "name-only":
        assert repaired["name"] == "Workbench Blade"
    else:
        prompt = requests[0]["messages"][1]["content"]
        assert '"currentItem"' not in prompt and '"item_use"' in prompt and '"item_stats"' in prompt
        assert context["acceptedItemContext"]["runtimeProgram"] == current["runtimeProgram"]
        calls = {c["id"]: c for c in repaired["runtimeProgram"]["calls"]}
        assert calls["item_use"]["params"]["useStyle"] == "shoot"
        assert calls["item_use"]["params"]["customHeldSprite"] == "hidden"
        assert calls["item_stats"]["params"]["damage"] == 1999
        assert any(row["reason"] == "independent_valid_node_frozen" for row in repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"])


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", [
    "malformed-head", "malformed-tail", "malformed-noop",
    "huge-buff-first", "huge-buff-later", "huge-placeable", "huge-accessory",
    "empty-healing-life", "empty-healing-mana",
])
def test_author_repair_defects_use_one_real_scoped_pipeline(wire_transport, monkeypatch, mode, case):
    from infini_local.core.runtime_authoring import validate_runtime_wire
    from infini_local.qa.capability_witnesses import build_capability_witness

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    responses, requests = wire_transport
    numeric_cases = {
        "huge-buff-first": ("apply_generated_buff_on_use", "miningSpeedMultiplier"),
        "huge-buff-later": ("apply_generated_buff_on_use", "manaRegenBonusPoints"),
        "huge-placeable": ("configure_tile_placement", "tileId"),
        "huge-accessory": ("configure_accessory", "lightStrength"),
    }
    good = build_capability_witness(numeric_cases[case][0] if case in numeric_cases else "restore_resources_on_use")
    if case == "huge-accessory":
        next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")["params"].update(lightStrength=0, lightColor="white")
    if case == "empty-healing-mana":
        next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "restore_resources_on_use")["params"].update(healLife=0, healMana=20)
    current = copy.deepcopy(good)
    calls = current["runtimeProgram"]["calls"]
    patch = {"note": "repair only the exact authored defect", "realizationReplacement": good["realization"]}
    expected_call_permissions = []
    expected_broken_indices = []
    if case.startswith("malformed"):
        malformed_index = len(calls) if case == "malformed-tail" else 0
        calls.insert(malformed_index, None)
        expected_broken_indices = [{"index": malformed_index, "value": None}]
        if case != "malformed-noop":
            patch["callIndicesDelete"] = [malformed_index]
    elif case in numeric_cases:
        fn, param = numeric_cases[case]
        node = next(row for row in calls if row["fn"] == fn)
        node["params"][param] = 10**400
        expected_call_permissions = [{"id": node["id"], "paths": ["params." + param]}]
        patch["callsUpsert"] = [copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == fn))]
    else:
        healing = next(row for row in calls if row["fn"] == "restore_resources_on_use")
        healing["params"].update(healLife=0, healMana=0, usesPotionRules=False)
        expected_call_permissions = [{"id": healing["id"], "paths": ["params.healLife", "params.healMana"]}]
        fixed = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "restore_resources_on_use"))
        fixed["params"]["usesPotionRules"] = True  # Valid frozen control, not an effective healing leaf.
        patch["callsUpsert"] = [fixed]
    if case != "malformed-noop":
        stats = copy.deepcopy(next(row for row in calls if isinstance(row, dict) and row["fn"] == "configure_item_stats"))
        stats["params"]["damage"] = 100
        patch.setdefault("callsUpsert", []).append(stats)
    original = copy.deepcopy(current)
    responses.extend([json.dumps(current, allow_nan=False), json.dumps(patch, allow_nan=False)])
    planned = gameplay_stage.try_llm_plan({}, {}, {}, {}, "scoped-author-repair")
    assert planned is not None
    assert planned["runtimeProgram"] == original["runtimeProgram"]
    before_pass = copy.deepcopy(planned)
    phases = []

    def observe(label, fn, *args, **kwargs):
        phases.append(label)
        return fn(*args, **kwargs)

    match = "leaves a reported repair error open" if case == "malformed-noop" else None
    with pytest.raises(PlannerUnavailable, match=match) if match else nullcontext():
        result = combine_stage.compile_and_validate_authored_runtime(planned, {}, {}, {}, {}, "scoped-author-repair", run_stage=observe)
        assert validate_runtime_wire(result)["ok"]
        expected = compile_runtime_program(good)
        assert result["runtimeProgram"] == expected["runtimeProgram"]
        assert result["gameplay"] == expected["gameplay"]
        audit = result["debug"]["gameplayRepairFilterAudit"]
        assert audit["ok"] and audit["ignoredChanges"]
        assert result["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] == 1
        assert result["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1
        assert phases[-1] == "02r_wire_boundary"
    # The validators attach debug reports in place; authored values stay literal.
    assert {k: v for k, v in planned.items() if k != "debug"} == {k: v for k, v in before_pass.items() if k != "debug"}
    assert current == original
    assert [r["_infini_stage"] for r in requests] == ["planner", "author_repair"]
    assert all(r["response_format"]["type"] == mode for r in requests)
    dossier = json.loads(requests[1]["messages"][1]["content"])
    assert dossier["exactValidationErrors"] == validate_runtime_program(current)["errors"]
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == expected_call_permissions
    assert dossier["readOnlySourceFragments"]["brokenFragmentsByIndex"]["calls"] == expected_broken_indices
    assert not responses


@pytest.mark.parametrize("fields", [("durationTicks",), ("buffId", "durationTicks")], ids=["single-leaf", "saturated-multi-leaf"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_bounded_diagnostic_completeness_reaches_the_single_pipeline_repair(wire_transport, monkeypatch, mode, fields):
    from infini_local.core.runtime_authoring import validate_runtime_wire
    from test_pipeline_repair_contract import _bounded_invalid_buff_calls

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    responses, requests = wire_transport
    current, good = _bounded_invalid_buff_calls(fields)
    assert validate_runtime_program(good)["ok"]
    assert validate_runtime_wire(compile_runtime_program(good))["ok"]
    original = copy.deepcopy(current)
    canonical_errors = validate_runtime_program(current)["errors"]
    broken = [row for row in good["runtimeProgram"]["calls"] if row["fn"] == "apply_vanilla_buff_on_use"]
    candidates = copy.deepcopy(good["runtimeProgram"]["calls"])
    candidates[0]["params"]["damage"] = 100
    patch = {"note": "repair every diagnosed duration", "realizationReplacement": good["realization"], "callsUpsert": candidates}
    responses.extend([json.dumps(current, allow_nan=False), json.dumps(patch, allow_nan=False)])
    planned = gameplay_stage.try_llm_plan({}, {}, {}, {}, "complete-bounded-diagnostics")
    assert planned is not None
    result = combine_stage.compile_and_validate_authored_runtime(planned, {}, {}, {}, {}, "complete-bounded-diagnostics", run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs))
    assert validate_runtime_wire(result)["ok"]
    expected = compile_runtime_program(good)
    assert result["runtimeProgram"] == expected["runtimeProgram"]
    assert result["gameplay"] == expected["gameplay"]
    assert current == original
    assert [r["_infini_stage"] for r in requests] == ["planner", "author_repair"]
    assert all(r["response_format"]["type"] == mode for r in requests)
    assert result["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 1
    dossier = json.loads(requests[1]["messages"][1]["content"])
    assert len(canonical_errors) == len(broken) * (len(fields) + 1)
    assert dossier["exactValidationErrors"] == canonical_errors
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == sorted(
        [{"id": row["id"], "paths": ["params." + field for field in fields]} for row in broken], key=lambda row: row["id"])
    assert result["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert not responses


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("oversized_surface", ["calls", "unknown-root"])
def test_oversized_author_response_refuses_before_format_or_gameplay_repair(wire_transport, monkeypatch, mode, oversized_surface):
    from infini_local.core.runtime_authoring import program_schema

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    responses, requests = wire_transport
    current = build_runtime_fixture("workbench_blade")
    nodes, _, _, _ = program_schema._author_schema_work_bounds(program_schema.author_item_response_schema())
    if oversized_surface == "calls":
        current["runtimeProgram"]["calls"] = [current["runtimeProgram"]["calls"][0]] * (nodes + 1)
    else:
        current["not_pipeline_metadata"] = [None] * (nodes + 1)
    responses.append(json.dumps(current))
    with pytest.raises(PlannerUnavailable, match="Author input exceeds schema-derived work bounds"):
        gameplay_stage.try_llm_plan({}, {}, {}, {}, "oversized-author-input")
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
    assert gameplay_stage.strict_author_item_repair_report(patch)["ok"] is ok


@pytest.mark.parametrize("stage", ["author_repair", "visual_repair", "vfx_repair"])
def test_repair_transport_stage_names(stage):
    from infini_local.pipelines.llm_transport import with_llm_stage
    assert with_llm_stage({"model": "test"}, stage)["_infini_stage"] == stage


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
    recovered = False

    def observe(_label, fn, *args, **kwargs):
        nonlocal recovered
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
        result = combine_stage.compile_and_validate_authored_runtime(current, {}, {}, {}, {}, "a+b", run_stage=observe)
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
