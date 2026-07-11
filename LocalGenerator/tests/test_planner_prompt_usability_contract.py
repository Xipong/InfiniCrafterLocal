from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring import ENGINE_FN_CATALOG_V2
from infini_local.core.runtime_authoring.schema import PLANNER_HIDDEN_ENGINE_FUNCTIONS
from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload
from infini_local.pipelines.llm_authoring_prompt import planner_prompt_usability_report


PARENT_A = {"name": "Wooden Sword", "type": 24, "damage": 7, "useTime": 25, "useAnimation": 25, "value": 100}
PARENT_B = {"name": "Torch", "type": 8, "createTile": 4, "value": 50}


def _check_real_planner_payload_has_sharp_complete_catalog_for_api_models(monkeypatch) -> None:
    monkeypatch.delenv("INFINI_LLM_ENGINE_CONTRACT_STYLE", raising=False)
    payload = build_llm_author_payload(PARENT_A, PARENT_B, {}, {}, "planner_smoke")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    report = planner_prompt_usability_report(PARENT_A, PARENT_B, {}, {}, "planner_smoke")
    assert report["ok"], report
    assert report["contractStyle"] == "sharp"
    assert len(text) <= 24_000
    functions = payload["engineRuntimeContract"]["availableFunctions"]
    assert set(functions) == set(ENGINE_FN_CATALOG_V2) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS)
    assert not (set(functions) & set(PLANNER_HIDDEN_ENGINE_FUNCTIONS))
    assert functions["apply_player_effect_on_use"]["params"]["healLife"] == "0..500"
    assert functions["shoot_projectile"]["params"]["speed"] == "3..18"
    assert "Low-level primary projectile" in functions["shoot_projectile"]["does"]
    assert "boss/NPC/mob/enemy" in functions["spawn_temporary_helper_projectile"].get("safety", "")
    assert "plannerChecklist" in payload["engineRuntimeContract"]
    assert payload["priorityHeader"][0].startswith("Author one playable result")
    assert any("set_item_stats" in line and "first" in line for line in payload["priorityHeader"])
    assert "runtimePlan" in payload["requiredJsonShape"]
    assert "attack.genome" in payload["authorRules"][-1]
    assert "summon_boss" in text and "hard-rejected" in text
    critical = payload["engineRuntimeContract"]["criticalValueSemantics"]
    assert "-1=infinite hits" in critical["pierce"]
    assert "0 or 1=one target total" in critical["pierce"]
    assert "useAnimation>useTime may repeat" in critical["useTiming"]
    assert "any projectile kill" in critical["expire"]
    assert "at most 48 shots" in critical["sentryBudget"]
    shoot = functions["shoot_projectile"]["params"]
    assert "0 or 1=one target total" in shoot["pierce"]
    assert "steps, not shots" in critical["shots"]
    assert "sentry uses deploy_sentry" in shoot["runtimeFamily"]
    assert "damageMultiplier" not in shoot
    ranged = functions["fire_ranged_weapon"]["params"]
    assert "rocket" not in ranged["ammoFor"]
    assert "0=immediate" in ranged["delayTicks"]
    stats = functions["set_item_stats"]["params"]
    assert "one action/click" in stats["useAnimationTicks"]
    assert "vanilla ammo identity" in stats["ammoFor"]


def _check_legacy_catalog_style_env_cannot_starve_or_bloat_planner(monkeypatch) -> None:
    for style in ["compact", "tiny", "minimal", "full", "verbose", "debug"]:
        monkeypatch.setenv("INFINI_LLM_ENGINE_CONTRACT_STYLE", style)
        payload = build_llm_author_payload(PARENT_A, PARENT_B, {}, {}, "planner_smoke")
        contract = payload["engineRuntimeContract"]
        assert contract["contractStyle"] == "sharp"
        functions = contract["availableFunctions"]
        assert set(functions) == set(ENGINE_FN_CATALOG_V2) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS)
        assert functions["apply_player_effect_on_use"]["params"]["healLife"] == "0..500"
        assert functions["shoot_projectile"]["params"]["movement"].startswith("straight|slow_homing")
        assert "temporary_turret" in functions["spawn_temporary_helper_projectile"]["params"]["family"]
        assert "state_meter" not in functions
        assert "triggered_action" not in functions


def _validated_child(plan: dict) -> dict:
    data = validate_and_repair(plan, PARENT_A, PARENT_B, {}, {}, "planner_smoke")
    return final_normalize(data)


def _check_minimal_llm_weapon_plan_can_become_generated_item_contract() -> None:
    child = _validated_child({
        "name": "Torchbite Blade",
        "tooltip": "A wooden blade that throws a brief ember arc.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 10, "useTimeTicks": 25}},
                {"fn": "perform_melee_attack", "params": {"family": "broadsword", "projectileShape": "short ember slash", "rangeTiles": 12, "lifetimeTicks": 90}},
                {"fn": "spawn_contact_particles", "params": {"effect": "flame", "amount": 8}},
            ],
            "visualIntent": {"item": "wooden sword with a torch ember", "projectile": "short ember slash"},
        },
        "visual": {"itemPrompt": "wooden sword with ember tip"},
    })
    assert child["category"] == "weapon"
    assert child["gameplay"]["damage"] == 10
    genome = child["attack"]["genome"]
    assert genome["runtimePlanAuthored"] is True
    assert genome["runtimeFamily"] == "swing"
    assert genome["effect"] == "flame"


def _check_minimal_llm_accessory_and_extractinator_plans_survive_validation() -> None:
    accessory = _validated_child({
        "name": "Starlit Runners",
        "tooltip": "Boots with a faint star wake.",
        "category": "accessory",
        "runtimePlan": {"resultKind": "accessory", "engineCalls": [
            {"fn": "set_item_stats", "params": {"resultKind": "accessory", "rarity": 2}},
            {"fn": "accessory_effect", "params": {"archetype": "mobility", "movementSpeed": 0.12, "jumpSpeed": 0.8, "lightStrength": 0.25, "lightColorName": "blue"}},
        ]},
    })
    assert accessory["category"] == "accessory"
    assert accessory["attack"]["enabled"] is False
    assert accessory["accessory"]["enabled"] is True
    assert accessory["accessory"]["movementSpeed"] == 0.12

    material = _validated_child({
        "name": "Star Sand",
        "tooltip": "A siftable stellar grit.",
        "category": "material",
        "runtimePlan": {"resultKind": "material", "engineCalls": [
            {"fn": "set_item_stats", "params": {"resultKind": "material", "maxStack": 999, "craftYield": 25}},
            {"fn": "extractinator_output", "params": {"resultType": 75, "stack": 2}},
        ]},
    })
    assert material["category"] == "material"
    assert material["gameplay"]["extractinatorOutputItemType"] == 75
    assert material["gameplay"]["extractinatorOutputStack"] == 2


def _check_forbidden_boss_npc_mob_calls_are_rejected_without_killing_valid_item_parts() -> None:
    child = _validated_child({
        "name": "Refusing Bell",
        "tooltip": "It hums, but refuses to call anything alive.",
        "category": "material",
        "runtimePlan": {"resultKind": "material", "engineCalls": [
            {"fn": "summon_boss", "params": {"type": "Eye of Cthulhu"}},
            {"fn": "set_item_stats", "params": {"resultKind": "material", "maxStack": 1}},
        ]},
    })
    rejected = child["gameplay"].get("rejectedEngineCalls", [])
    assert child["category"] == "material"
    assert child["gameplay"]["maxStack"] == 1
    assert rejected and rejected[0]["reason"] == "forbidden_world_entity_spawn"


def _check_prompt_usability_cli_runs_the_same_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(root / "tools" / "check_planner_prompt_usability.py"), "--limit-chars", "24000"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["report"]["functionCount"] == len(ENGINE_FN_CATALOG_V2) - len(PLANNER_HIDDEN_ENGINE_FUNCTIONS)



def _check_planner_catalog_exposes_safe_terraria_item_capabilities_without_loss(monkeypatch) -> None:
    monkeypatch.delenv("INFINI_LLM_ENGINE_CONTRACT_STYLE", raising=False)
    payload = build_llm_author_payload(PARENT_A, PARENT_B, {}, {}, "planner_smoke")
    functions = payload["engineRuntimeContract"]["availableFunctions"]
    for fn in ["use_affordance", "visual_effect_cue", "consumption_behavior", "ammo_behavior"]:
        assert fn in functions
        assert functions[fn]["does"]
        assert functions[fn]["params"]
    assert functions["visual_effect_cue"]["params"]["rendererKind"].startswith("projectileAfterimage")
    assert functions["consumption_behavior"]["params"]["consumeChancePercent"].startswith("0..100")
    assert functions["ammo_behavior"]["params"]["ammoFor"] == "arrow|bullet|empty"

def _check_placeable_consumable_parent_semantics_are_explicit_without_hiding_raw_flags() -> None:
    chair = {
        "name": "Wooden Chair",
        "internalName": "WoodenChair",
        "type": 34,
        "damage": -1,
        "consumable": True,
        "maxStack": 9999,
        "createTile": 15,
        "createWall": -1,
        "useTime": 10,
        "useAnimation": 14,
    }
    payload = build_llm_author_payload(PARENT_A, chair, {}, {}, "planner_chair_semantics")
    parent = payload["itemB"]
    assert parent["raw"]["item"]["consumable"] is True
    assert parent["raw"]["item"]["createTile"] == 15
    assert parent["semantics"]["consumptionSemantics"] == "consumed_when_placed_as_tile_or_wall"
    assert "does not automatically mean" in parent["semantics"]["note"]
    assert any("placeable" in line.lower() and "consumable" in line.lower() for line in payload["priorityHeader"])
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assert "availableFunctions" in text and "consumed_when_placed_as_tile_or_wall" in text


def _check_planner_prompt_guides_semantic_mechanic_authoring_not_code_repair(monkeypatch) -> None:
    monkeypatch.delenv("INFINI_LLM_ENGINE_CONTRACT_STYLE", raising=False)
    payload = build_llm_author_payload(PARENT_A, {"name": "Fallen Star", "type": 75, "value": 500}, {}, {}, "planner_starfall")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).lower()
    functions = payload["engineRuntimeContract"]["availableFunctions"]

    assert "overhead_barrage" in functions["apply_on_hit_effect"]["params"]["onHit"]
    assert "overhead barrage" in text and "mechanicclaims" in text
    assert "backing=enginecall" in text
    assert "enginecalls/numbers/contracts" in text
    assert "do not infer mechanics from names" in text
    assert "custom_executor for normal/utility enginecalls" in text or "never family=unsupported" in text
    assert "image prompts: item=inventory/held" in text
    assert "same sword/blade/boomerang ok" in text

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_real_planner_payload_has_sharp_complete_catalog_for_api_models',
    '_check_legacy_catalog_style_env_cannot_starve_or_bloat_planner',
    '_check_minimal_llm_weapon_plan_can_become_generated_item_contract',
    '_check_minimal_llm_accessory_and_extractinator_plans_survive_validation',
    '_check_forbidden_boss_npc_mob_calls_are_rejected_without_killing_valid_item_parts',
    '_check_prompt_usability_cli_runs_the_same_contract',
    '_check_planner_catalog_exposes_safe_terraria_item_capabilities_without_loss',
    '_check_placeable_consumable_parent_semantics_are_explicit_without_hiding_raw_flags',
    '_check_planner_prompt_guides_semantic_mechanic_authoring_not_code_repair'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_planner_prompt_usability_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
