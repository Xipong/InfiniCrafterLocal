from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import llm_authoring_pipeline as lap
from infini_local.core.runtime_authoring import runtime_plan_validation_report


def test_runtime_plan_repair_adds_missing_stats_without_reauthoring_item(monkeypatch):
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

    repaired = {
        "name": "Sun-Stabber",
        "tooltip": "Strikes with the warmth of a thousand petals.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 6, "useTimeTicks": 13, "maxStack": 1, "rarity": 0, "value": 700}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "thrust", "delivery": "thrust", "movement": "straight", "speed": 12, "useTimeTicks": 13, "pierce": 3}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "aura_pulse", "aoeRadiusTiles": 2, "count": 3}},
            ],
        },
        "visual": {"itemPrompt": "sunflower shortsword", "projectilePrompt": "golden petal thrust"},
    }

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



def test_runtime_plan_repair_triggers_on_compile_level_runtime_family_error(monkeypatch):
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

    repaired = {
        "name": "Ambiguous Launcher",
        "tooltip": "A weapon with a readable concept but complete execution fields.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 8, "useTimeTicks": 20, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "projectileShape": "odd spark", "speed": 10, "useTimeTicks": 20}},
            ],
        },
        "visual": {"itemPrompt": "ambiguous launcher", "projectilePrompt": "odd spark"},
    }

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


def test_validate_and_repair_preserves_runtime_plan_repair_path(monkeypatch):
    from infini_local.pipelines import combine_pipeline as cp

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
