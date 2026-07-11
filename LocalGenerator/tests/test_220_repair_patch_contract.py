from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.balance_report import build_balance_report
from infini_local.core.runtime_authoring import runtime_plan_validation_report
from infini_local.pipelines import llm_authoring_pipeline as lap


def _enable_runtime_repair(monkeypatch):
    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "LLM_RUNTIME_AUTHORING", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "repair-test-model")
    monkeypatch.setattr(lap, "apply_llm_common_options", lambda req, **kwargs: req)


def _broken_weapon() -> dict:
    return {
        "name": "Original Patch Blade",
        "tooltip": "Original tooltip.",
        "concept": {"fantasy": "original fantasy"},
        "visual": {"itemPrompt": "original sprite"},
        "tags": ["original"],
        "category": "weapon",
        "gameplay": {"kind": "weapon", "damage": 12, "useTime": 28},
        "debug": {},
        "id": "g_patch_original",
        "recipeKey": "r_patch_original",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 12, "useTimeTicks": 28, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"speed": 9, "useTimeTicks": 28}},
            ]
        },
    }


def test_full_json_repair_is_reduced_to_runtime_patch_not_second_author(monkeypatch):
    data = _broken_weapon()
    assert runtime_plan_validation_report(data)["ok"] is False

    full_rewrite = {
        "name": "Rewritten God Blade",
        "tooltip": "rewritten tooltip",
        "concept": {"fantasy": "rewritten fantasy"},
        "visual": {"itemPrompt": "rewritten visual"},
        "tags": ["rewritten"],
        "category": "accessory",
        "gameplay": {"kind": "accessory", "damage": 999, "useTime": 6},
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 12, "useTimeTicks": 28, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 9, "useTimeTicks": 28, "shotCount": 1}},
            ]
        },
        "unexpectedFullRewriteField": {"should": "drop"},
        "debug": {"repairDebugProbe": "kept-as-metadata-only"},
    }

    def fake_llm_chat_json(req, timeout=10):
        content = req["messages"][-1]["content"]
        assert "repairPatch" in content
        assert "Runtime repair is not a second item author" in content
        return {"choices": [{"message": {"content": json.dumps(full_rewrite)}}]}

    _enable_runtime_repair(monkeypatch)
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm_chat_json)
    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_patch_original")

    assert runtime_plan_validation_report(out)["ok"] is True
    assert out["name"] == "Original Patch Blade"
    assert out["tooltip"] == "Original tooltip."
    assert out["concept"]["fantasy"] == "original fantasy"
    assert out["visual"]["itemPrompt"] == "original sprite"
    assert out["tags"] == ["original"]
    assert out["category"] == "weapon"
    assert out["gameplay"]["kind"] == "weapon"
    assert out["gameplay"]["damage"] == 12
    assert "unexpectedFullRewriteField" not in out
    patch_report = json.loads(out["debug"]["runtimePlanRepairPatchContract"])
    assert patch_report["source"] == "full_json_reduced_to_patch"
    assert "runtimePlan" in patch_report["acceptedTopLevel"]
    assert "gameplay" in patch_report["rejectedTopLevel"]
    assert "unexpectedFullRewriteField" in patch_report["rejectedTopLevel"]


def test_explicit_repair_patch_can_adjust_narrow_gameplay_surface(monkeypatch):
    data = _broken_weapon()
    patch_response = {
        "repairPatch": {
            "gameplay": {"damage": 14, "useTime": 26, "evilProse": "drop me"},
            "runtimePlan": {
                "engineCalls": [
                    {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 14, "useTimeTicks": 26, "maxStack": 1}},
                    {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 9, "useTimeTicks": 26, "shotCount": 1}},
                ]
            },
            "visual": {"itemPrompt": "must not adopt"},
        },
        "debug": {"repairDebugProbe": "ok"},
    }

    def fake_llm_chat_json(req, timeout=10):
        return {"choices": [{"message": {"content": json.dumps(patch_response)}}]}

    _enable_runtime_repair(monkeypatch)
    monkeypatch.setattr(lap, "llm_chat_json", fake_llm_chat_json)
    out = lap.repair_runtime_plan_if_needed(data, {}, {}, {}, {}, "r_patch_explicit")
    assert runtime_plan_validation_report(out)["ok"] is True
    assert out["visual"]["itemPrompt"] == "original sprite"
    assert out["gameplay"]["damage"] == 14
    assert out["gameplay"]["useTime"] == 26
    assert "evilProse" not in out["gameplay"]
    patch_report = json.loads(out["debug"]["runtimePlanRepairPatchContract"])
    assert patch_report["source"] == "repairPatch"
    assert "gameplay" in patch_report["acceptedTopLevel"]
    assert "visual" in patch_report["rejectedTopLevel"]
    assert "gameplay.evilProse" in patch_report["rejectedTopLevel"]


def test_balance_report_surfaces_runtime_repair_patch_contract():
    data = {
        "category": "weapon",
        "gameplay": {"kind": "weapon", "damage": 14, "useTime": 26},
        "debug": {
            "runtimeRepairPath": "llm_targeted_runtime_contract_repair",
            "runtimePlanRepairPatchContract": json.dumps({
                "schema": "infini.runtime-repair-patch-contract.v1",
                "source": "repairPatch",
                "acceptedTopLevel": ["runtimePlan", "gameplay"],
                "rejectedTopLevel": ["visual"],
            }),
        },
    }
    report = build_balance_report(data, {"name": "pre_hardmode_late"})
    assert report["repair"]["patchContract"]["source"] == "repairPatch"
    contract_kinds = [row["kind"] for row in report["clamps"]["contract"]]
    assert "runtime_repair_patch_contract" in contract_kinds
