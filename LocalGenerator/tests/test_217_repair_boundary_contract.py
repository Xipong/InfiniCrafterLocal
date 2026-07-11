from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring import runtime_plan_validation_report
from infini_local.pipelines import llm_authoring_pipeline as lap


def _enable_runtime_repair(monkeypatch):
    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "LLM_RUNTIME_AUTHORING", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)


def test_structural_runtime_shape_repair_is_code_only_for_exact_contract_scalar_types(monkeypatch):
    data = {
        "name": "Crooked Spark Rifle",
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "debug": {"planner": "llm_author_first"},
        "runtimePlan": {
            "engineCalls": [
                {
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "ranged",
                        "damage": "82",
                        "useTimeTicks": "24 ticks",
                        "maxStack": "1",
                    },
                },
                {
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "shoot",
                        "delivery": "shoot",
                        "movement": "straight",
                        "speed": "12.5",
                        "shotCount": "3 shots",
                        "pierce": "2",
                        "homingStrength": "0.35",
                        "rangeTiles": "66 tiles",
                        "lifetimeTicks": "180 ticks",
                    },
                },
            ]
        },
    }

    def forbidden_llm(*args, **kwargs):
        raise AssertionError("exact-shape scalar repair must not call LLM")

    _enable_runtime_repair(monkeypatch)
    monkeypatch.setattr(lap, "llm_chat_json", forbidden_llm)
    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_structural")
    assert runtime_plan_validation_report(out)["ok"] is True
    assert out["debug"]["runtimeRepairPath"] == "code_structural_repair_only"
    assert "runtimeStructuralRepair" in out["debug"]
    calls = out["runtimePlan"]["engineCalls"]
    assert calls[0]["fn"] == "set_item_stats"
    assert calls[0]["params"]["useTimeTicks"] == 24
    assert calls[1]["fn"] == "shoot_projectile"
    assert calls[1]["params"]["shotCount"] == 3
    assert calls[1]["params"]["homingStrength"] == 0.35


def test_dead_or_missing_runtime_plan_gets_one_retry_then_fails_with_debug(monkeypatch):
    data = {
        "name": "Dead Runtime Probe",
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "debug": {"planner": "llm_author_first"},
    }
    calls = {"n": 0}

    def still_dead_llm(req, timeout=10):
        calls["n"] += 1
        return {"choices": [{"message": {"content": json.dumps({"name": "Still Dead", "category": "weapon", "debug": {}})}}]}

    _enable_runtime_repair(monkeypatch)
    monkeypatch.setattr(lap, "llm_chat_json", still_dead_llm)
    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_dead")
    assert calls["n"] == 1
    assert out["debug"]["runtimeRepairKind"] == "dead_missing_runtime_plan_retry_once"
    assert out["debug"]["runtimeRepairAttemptBudget"] == "1"
    assert out["debug"]["runtimeRepairPath"] == "targeted_runtime_repair_failed_then_strict_validation"
    assert "runtimePlan.engineCalls has no accepted executable calls" in out["debug"]["runtimePlanValidationAfterRepair"]


def test_runtime_repair_preserves_identity_fields_even_if_model_returns_full_rewrite(monkeypatch):
    data = {
        "name": "Original Hive Blade",
        "tooltip": "Original tooltip.",
        "concept": {"fantasy": "original fantasy", "mergeLogic": "original merge"},
        "visual": {"itemPrompt": "original sprite"},
        "tags": ["original"],
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "debug": {"planner": "llm_author_first"},
        "id": "g_original",
        "recipeKey": "r_original",
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 8, "useTimeTicks": 20}}]},
    }
    repaired = {
        "name": "Rewritten Name",
        "tooltip": "Rewritten tooltip.",
        "concept": {"fantasy": "rewritten"},
        "visual": {"itemPrompt": "rewritten sprite"},
        "tags": ["rewritten"],
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 8, "useTimeTicks": 20, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 10, "shotCount": 1, "pierce": 0, "lifetimeTicks": 90}},
            ]
        },
    }

    def fake_llm(req, timeout=10):
        return {"choices": [{"message": {"content": json.dumps(repaired)}}]}

    _enable_runtime_repair(monkeypatch)
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm)
    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_original")
    assert runtime_plan_validation_report(out)["ok"] is True
    assert out["name"] == "Original Hive Blade"
    assert out["tooltip"] == "Original tooltip."
    assert out["concept"]["fantasy"] == "original fantasy"
    assert out["visual"]["itemPrompt"] == "original sprite"
    assert out["tags"] == ["original"]
    assert out["id"] == "g_original"
    assert out["recipeKey"] == "r_original"
    assert out["debug"]["runtimeRepairPath"] == "llm_targeted_runtime_contract_repair"
