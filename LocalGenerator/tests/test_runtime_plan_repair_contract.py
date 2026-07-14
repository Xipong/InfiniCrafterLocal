from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import llm_authoring_pipeline as lap
from infini_local.core.runtime_authoring import runtime_plan_validation_report


def _contract_check_runtime_plan_repair_adds_missing_stats_without_reauthoring_item(monkeypatch):
    data = {
        "name": "Sun-Stabber",
        "tooltip": "Strikes with the warmth of a thousand petals.",
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "thrust", "delivery": "thrust", "movement": "straight", "speed": 12, "useTimeTicks": 13, "pierce": 3}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "aura_pulse", "aoeRadiusTiles": 2, "count": 3}},
            ],
        },
        "visual": {"itemPrompt": "sunflower shortsword", "projectilePrompt": "golden petal thrust"},
        "debug": {},
        "id": "g_test",
        "recipeKey": "r_test",
        "parentA": "Медный короткий меч",
        "parentB": "Подсолнух",
        "sourceMode": "generated",
    }
    before = runtime_plan_validation_report(data)
    assert before["ok"] is False
    assert "combat result lacks set_item_stats" in before["errors"]

    repaired = {"repairPatch": {
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 6, "useTimeTicks": 13, "maxStack": 1, "rarity": 0, "value": 700}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "thrust", "delivery": "thrust", "movement": "straight", "speed": 12, "useTimeTicks": 13, "pierce": 3}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "aura_pulse", "aoeRadiusTiles": 2, "count": 3}},
            ],
        },
    }}

    def fake_llm_chat_json(req, timeout=10):
        assert "runtimePlan.engineCalls validates" in req["messages"][-1]["content"]
        return {"choices": [{"message": {"content": json.dumps(repaired)}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "LLM_RUNTIME_AUTHORING", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm_chat_json)
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)

    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_test")
    after = runtime_plan_validation_report(out)
    assert after["ok"] is True
    assert out["id"] == "g_test"
    assert out["recipeKey"] == "r_test"
    assert out["runtimePlan"]["engineCalls"][0]["fn"] == "set_item_stats"
    assert out["debug"]["runtimeRepairPath"] == "llm_targeted_runtime_contract_repair"



def _contract_check_runtime_plan_repair_triggers_on_compile_level_runtime_family_error(monkeypatch):
    data = {
        "name": "Ambiguous Launcher",
        "tooltip": "A weapon with a readable concept but incomplete execution fields.",
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 8, "useTimeTicks": 20, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"projectileShape": "odd spark", "speed": 10, "useTimeTicks": 20}},
            ],
        },
        "visual": {"itemPrompt": "ambiguous launcher", "projectilePrompt": "odd spark"},
        "debug": {},
        "id": "g_compile_contract",
        "recipeKey": "r_compile_contract",
        "parentA": "Parent A",
        "parentB": "Parent B",
        "sourceMode": "generated",
    }
    before = runtime_plan_validation_report(data)
    assert before["ok"] is False
    assert "primary executable action did not compile: primary_attack_requires_runtimefamily" in before["errors"]
    assert "combat primary action lacks an executable runtimeFamily" in before["errors"]

    repaired = {"repairPatch": {
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 8, "useTimeTicks": 20, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "projectileShape": "odd spark", "speed": 10, "useTimeTicks": 20}},
            ],
        },
    }}

    def fake_llm_chat_json(req, timeout=10):
        assert "primary_attack_requires_runtimefamily" in req["messages"][-1]["content"]
        return {"choices": [{"message": {"content": json.dumps(repaired)}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "LLM_RUNTIME_AUTHORING", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm_chat_json)
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)

    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_compile_contract")
    after = runtime_plan_validation_report(out)
    assert after["ok"] is True
    assert out["id"] == "g_compile_contract"
    assert out["runtimePlan"]["engineCalls"][1]["params"]["runtimeFamily"] == "shoot"
    assert out["debug"]["runtimeRepairPath"] == "llm_targeted_runtime_contract_repair"


def _contract_check_validate_and_repair_preserves_runtime_plan_repair_path(monkeypatch):
    from infini_local.pipelines import combine_validation as cp

    data = {
        "name": "Repair Path Probe",
        "tooltip": "A probe for runtime repair diagnostics.",
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {"resultKind": "weapon"}}]},
        "debug": {},
        "tags": [],
        "visual": {},
        "attack": {},
    }

    def fake_repair_runtime_plan_if_needed(obj, *args, **kwargs):
        obj.setdefault("debug", {})["runtimeRepairPath"] = "llm_runtime_plan_repair"
        return obj

    monkeypatch.setattr(cp, "LLM_RUNTIME_AUTHORING", True)
    monkeypatch.setattr(cp, "repair_runtime_plan_if_needed", fake_repair_runtime_plan_if_needed)
    monkeypatch.setattr(cp, "normalize_runtime_authoring_fields", lambda obj: obj)

    out = cp.validate_and_repair(
        data,
        {"name": "Parent A"},
        {"name": "Parent B"},
        {},
        {},
        "repair_path_probe",
    )

    assert out["debug"]["runtimeRepairPath"] == "llm_runtime_plan_repair"


def _contract_check_runtime_repair_uses_self_contained_authoritative_dossier_without_replaying_history(monkeypatch):
    planner_system = "PLANNER_SYSTEM_SENTINEL_" * 400
    planner_user = "PLANNER_USER_SENTINEL_" * 1000
    planner_assistant = "PLANNER_ASSISTANT_SENTINEL_" * 500
    data = {
        "name": "Retake Probe",
        "tooltip": "Keep this identity.",
        "concept": {"fantasy": "compact repair"},
        "category": "weapon",
        "gameplay": {"kind": "weapon", "damage": 9, "useTime": 24},
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 9, "useTimeTicks": 24, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"speed": 8, "useTimeTicks": 24}},
            ]
        },
        "attack": {"enabled": True, "projectileShape": "needle"},
        "_llmHistory": {
            "kind": "attributed_planner_history_v1",
            "messages": [
                {"role": "system", "name": "item_author_contract", "content": planner_system},
                {"role": "user", "name": "recipe_context", "content": planner_user},
                {"role": "assistant", "name": "item_planner", "content": planner_assistant},
            ],
        },
    }
    validation = {
        "ok": False,
        "errors": [
            "primary executable action did not compile: primary_attack_requires_runtimefamily",
            "combat primary action lacks an executable runtimeFamily",
        ],
    }
    repaired = {
        "repairPatch": {
            "runtimePlan": {
                "engineCalls": [
                    {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 9, "useTimeTicks": 24, "maxStack": 1}},
                    {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 8, "useTimeTicks": 24}},
                ]
            }
        }
    }
    captured = []
    full_payload_builds = []

    def fake_llm_chat_json(req, timeout=10):
        captured.append(req)
        return {"choices": [{"message": {"content": json.dumps(repaired)}}]}

    def fake_author_payload(*args):
        full_payload_builds.append(True)
        return {"engineRuntimeContract": {"legacyLargeContract": "CONTRACT_SENTINEL_" * 1000}}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "build_llm_author_payload", fake_author_payload)
    monkeypatch.setattr(lap, "raw_parent_card_for_llm", lambda item: {"name": item.get("name")})
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm_chat_json)
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)

    assert lap.try_llm_runtime_plan_repair(data, {}, {}, {}, {}, "r_retake", validation, 1) is not None
    dossier_messages = captured[0]["messages"]
    assert [(m["role"], m["name"]) for m in dossier_messages] == [
        ("system", "runtime_repair_contract"),
        ("user", "runtime_validator"),
    ]
    assert "PLANNER_SYSTEM_SENTINEL" not in dossier_messages[0]["content"]
    assert "authoritative current" in dossier_messages[0]["content"].lower()
    dossier = json.loads(dossier_messages[-1]["content"])
    assert dossier["agentHandoff"]["schema"] == "infini.llm-handoff.v1"
    assert dossier["agentHandoff"]["nextSpeaker"] == "runtime_repairer"
    assert dossier["agentHandoff"]["artifactSource"] == "currentItem"
    assert dossier["currentItem"] == {
        "category": data["category"],
        "gameplay": data["gameplay"],
        "runtimePlan": data["runtimePlan"],
        "attack": data["attack"],
    }
    assert dossier["validationReport"] == validation
    assert dossier["parents"] == [{"name": None}, {"name": None}]
    assert dossier["engineRuntimeContract"]["legacyLargeContract"].startswith("CONTRACT_SENTINEL_")
    assert dossier["requiredRepairPatchShape"]["required"] == ["repairPatch"]
    assert "PLANNER_USER_SENTINEL" not in dossier_messages[-1]["content"]
    assert "PLANNER_ASSISTANT_SENTINEL" not in dossier_messages[-1]["content"]
    assert full_payload_builds == [True]

    standalone_data = dict(data)
    standalone_data.pop("_llmHistory")
    assert lap.try_llm_runtime_plan_repair(
        standalone_data,
        {"name": "Parent A"},
        {"name": "Parent B"},
        {},
        {},
        "r_standalone",
        validation,
        1,
    ) is not None
    standalone_messages = captured[1]["messages"]
    assert [(m["role"], m["name"]) for m in standalone_messages] == [
        ("system", "runtime_repair_contract"),
        ("user", "runtime_validator"),
    ]
    standalone = json.loads(standalone_messages[-1]["content"])
    assert standalone["parents"] == [{"name": "Parent A"}, {"name": "Parent B"}]
    assert standalone["engineRuntimeContract"]["legacyLargeContract"].startswith("CONTRACT_SENTINEL_")
    assert "requiredJsonShape" not in standalone
    assert standalone["requiredRepairPatchShape"]["required"] == ["repairPatch"]
    call_schema = standalone["requiredRepairPatchShape"]["properties"]["repairPatch"]["properties"]["runtimePlan"]["properties"]["engineCalls"]["items"]
    assert call_schema["required"] == ["fn", "params"]
    assert call_schema["properties"]["params"]["type"] == "object"
    assert full_payload_builds == [True, True]


def _contract_check_runtime_repair_does_not_mask_malformed_history_with_standalone(monkeypatch):
    data = {
        "name": "Malformed History Probe",
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "runtimePlan": {"engineCalls": []},
        "attack": {"enabled": True},
        "debug": {"planner": "llm_author_first"},
        "_llmHistory": {"kind": "attributed_planner_history_v1", "messages": []},
    }
    calls = []
    standalone_builds = []

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)
    monkeypatch.setattr(
        lap,
        "llm_chat_json",
        lambda *args, **kwargs: calls.append(args) or {"choices": [{"message": {"content": "{}"}}]},
    )
    monkeypatch.setattr(
        lap,
        "build_llm_author_payload",
        lambda *args, **kwargs: standalone_builds.append(True) or {"engineRuntimeContract": {}},
    )

    out = lap.try_llm_runtime_plan_repair(
        data,
        {"name": "Parent A"},
        {"name": "Parent B"},
        {},
        {},
        "r_malformed_history",
        {"ok": False, "errors": ["missing runtimePlan"]},
        1,
    )

    assert out is None
    assert standalone_builds == []
    assert calls == []


def _contract_check_failed_runtime_repairs_return_exact_validator_feedback_and_never_adopt_invalid_candidate(monkeypatch):
    data = {
        "name": "Swift-Strider's Lace",
        "tooltip": "A mobility accessory.",
        "category": "accessory",
        "gameplay": {"kind": "accessory"},
        "runtimePlan": {
            "resultKind": "accessory",
            "engineCalls": [
                {"fn": "accessory_effect", "params": {"archetype": "mobility", "stats": "move"}},
                {"fn": "set_alt_use_mode", "params": {"mode": "mobility", "mobilityMode": "blink_to_cursor", "rangeTiles": 20, "cooldownTicks": 300, "safeTileOnly": True}},
            ],
        },
        "runtimeContract": {"schema": "infini.runtime-contract.v2"},
        "visual": {"itemPrompt": "winged boots"},
        "debug": {},
        "id": "g_accessory_probe",
        "recipeKey": "r_accessory_probe",
        "parentA": "Hermes Boots",
        "parentB": "Aglet",
        "sourceMode": "generated",
    }
    original_calls = json.loads(json.dumps(data["runtimePlan"]["engineCalls"]))
    bad_repairs = [
        {"repairPatch": {"runtimePlan": {"engineCalls": [
            {"fn": "set_item_stats", "params": ["resultKind", "accessory"]},
            {"fn": "accessory_effect", "params": ["archetype", "mobility"]},
        ]}}},
        {"repairPatch": {"runtimePlan": {"engineCalls": [
            {"fn": "set_item_stats", "params": '{"resultKind":"accessory"}'},
            {"fn": "accessory_effect", "params": '{"archetype":"mobility"}'},
        ]}}},
    ]
    captured: list[dict] = []

    def fake_llm_chat_json(req, timeout=10):
        captured.append(req)
        return {"choices": [{"message": {"content": json.dumps(bad_repairs[len(captured) - 1])}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "LLM_RUNTIME_AUTHORING", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm_chat_json)
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)

    with pytest.raises(lap.PlannerUnavailable, match="runtime repair exhausted"):
        lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_accessory_probe")

    assert len(captured) == 2
    second_feedback = json.loads(captured[1]["messages"][-1]["content"])
    assert any("valid dictionary" in error for error in second_feedback["validatorFeedback"]["errors"])
    assert any("engineCalls[].params must be a JSON object" in rule for rule in second_feedback["mustFix"])
    failed_contract = second_feedback["failedCallContracts"][0]
    assert failed_contract["fn"] == "set_item_stats"
    assert failed_contract["paramsSchema"]["type"] == "object"
    accessory_contract = next(contract for contract in second_feedback["failedCallContracts"] if contract["fn"] == "accessory_effect")
    assert "movementSpeed" in accessory_contract["allowedNestedFields"]["stats"]
    assert "jumpSpeed" in accessory_contract["allowedNestedFields"]["stats"]
    assert data["runtimePlan"]["engineCalls"] == original_calls


def _contract_check_valid_later_repair_does_not_inherit_mutations_from_rejected_candidate(monkeypatch):
    data = {
        "name": "Candidate Isolation Blade",
        "category": "weapon",
        "gameplay": {"kind": "weapon", "damage": 12, "useTime": 28},
        "debug": {"planner": "llm_author_first"},
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 12, "useTimeTicks": 28}},
                {"fn": "shoot_projectile", "params": {"speed": 9}},
            ],
        },
    }
    data["_llmHistory"] = {
        "kind": "attributed_planner_history_v1",
        "messages": [
            {"role": "system", "name": "item_author_contract", "content": "planner contract"},
            {"role": "user", "name": "recipe_context", "content": '{"recipe":"candidate isolation"}'},
            {"role": "assistant", "name": "item_planner", "content": json.dumps(data, ensure_ascii=False)},
        ],
    }
    responses = [
        {"repairPatch": {"gameplay": {"damage": 999}, "runtimePlan": {"resultKind": "weapon", "engineCalls": [
            {"fn": "set_item_stats", "params": []},
            {"fn": "shoot_projectile", "params": []},
        ]}}},
        {"repairPatch": {"runtimePlan": {"resultKind": "weapon", "engineCalls": [
            {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 12, "useTimeTicks": 28}},
            {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 9, "shotCount": 1}},
        ]}}},
    ]
    seen_prompts: list[dict] = []

    def fake_llm(req, timeout=10):
        seen_prompts.append(json.loads(req["messages"][-1]["content"]))
        return {"choices": [{"message": {"content": json.dumps(responses[len(seen_prompts) - 1])}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "LLM_RUNTIME_AUTHORING", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm)

    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "candidate_isolation")

    assert seen_prompts[1]["currentItem"]["gameplay"]["damage"] == 999
    assert out["gameplay"]["damage"] == 12
    assert out["debug"]["runtimeRepairPath"] == "llm_targeted_runtime_contract_repair"


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_runtime_plan_repair_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_runtime_plan_repair_adds_missing_stats_without_reauthoring_item',
            '_contract_check_runtime_plan_repair_triggers_on_compile_level_runtime_family_error',
            '_contract_check_validate_and_repair_preserves_runtime_plan_repair_path',
            '_contract_check_runtime_repair_uses_self_contained_authoritative_dossier_without_replaying_history',
            '_contract_check_runtime_repair_does_not_mask_malformed_history_with_standalone',
            '_contract_check_failed_runtime_repairs_return_exact_validator_feedback_and_never_adopt_invalid_candidate',
            '_contract_check_valid_later_repair_does_not_inherit_mutations_from_rejected_candidate',
        ),
    )
