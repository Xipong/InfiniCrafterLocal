from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace
from infini_local.core.vfx_director_prompt import _vfx_compact_child_for_director
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload
from infini_local.pipelines import visual_generation_pipeline as VISUAL
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt, role_visual_prompt_guard


PARENT_A = {"name": "Wooden Sword", "type": 24, "damage": 7, "useTime": 25, "useAnimation": 25}
PARENT_B = {"name": "Fallen Star", "type": 75, "value": 500}


def _contract_check_active_planner_contract_is_honest_and_compact() -> None:
    payload = build_llm_author_payload(PARENT_A, PARENT_B, {}, {}, "v12_manual_trace")
    functions = payload["engineRuntimeContract"]["availableFunctions"]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    assert "spawn_temporary_helper_projectile" in functions
    assert "summon_combat_entity" not in functions
    assert "persistent Terraria minion or sentry" in functions["spawn_temporary_helper_projectile"]["does"]
    assert "on_hit or on_expire" in text
    lowered = text.lower()
    assert "shotcount" in lowered and "simultaneous" in lowered
    assert "starfury" in lowered
    assert "overhead_barrage" in lowered and "delivery=swing" in lowered
    assert "consumable_weapon" in text
    assert "shoot_projectile" in functions


def _contract_check_only_canonical_temporary_helper_name_is_accepted_and_world_entities_stay_rejected() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "spawn_temporary_helper_projectile", "params": {"family": "drone", "movement": "orbit", "lifetimeTicks": 120}},
        {"fn": "spawn_temporary_helper_projectile", "params": {"family": "boss"}},
        {"fn": "summon_combat_entity", "params": {"family": "minion"}},
    ]}}
    normalize_runtime_plan_inplace(data)
    calls = data["runtimePlan"]["engineCalls"]
    assert len(calls) == 1
    assert calls[0]["_rawFn"] == "spawn_temporary_helper_projectile"
    assert calls[0]["fn"] == "shoot_projectile"
    assert calls[0]["params"]["runtimeFamily"] == "summon"
    rejected = data["runtimePlan"]["_normalization"]["rejectedEngineCalls"]
    assert rejected and rejected[0]["reason"] == "forbidden_world_entity_spawn"
    dropped = data["runtimePlan"]["_normalization"]["droppedCalls"]
    assert any(x.get("fn") == "summon_combat_entity" and x.get("reason") == "unknown_fn" for x in dropped)


def _contract_check_multishot_projectile_prompt_is_one_body_but_explicit_bundle_survives() -> None:
    shotgun = {
        "name": "Sixfold Scattergun",
        "category": "weapon",
        "attack": {"enabled": True, "runtimeFamily": "shoot", "projectileFamily": "pellet", "shotCount": 6},
        "visual": {"palette": ["iron", "amber"]},
    }
    prompt = normalize_asset_prompt(shotgun, "projectile", "six pellets in a wide fan", 32).lower()
    assert "six pellets in a wide fan" in prompt
    assert "one authored projectile texture" not in prompt

    bundle = {
        "name": "Shard Cluster",
        "category": "weapon",
        "attack": {"enabled": True, "runtimeFamily": "shoot", "projectileFamily": "crystal_cluster", "shotCount": 4},
        "visual": {"palette": ["cyan"]},
    }
    bundle_prompt = normalize_asset_prompt(bundle, "projectile", "cluster of six fused crystal shards as one projectile bundle", 32).lower()
    assert "cluster of six fused crystal shards" in bundle_prompt


def _contract_check_child_and_item_role_guards_separate_runtime_multiplicity_and_inventory_scene() -> None:
    child = role_visual_prompt_guard("child", "three ember shards", {"attack": {"splitCount": 3}}).lower()
    assert "child damaging projectile" in child and "runtime spawns" in child

    weapon = {
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon"},
        "attack": {"enabled": True},
    }
    item = role_visual_prompt_guard("item", "silver bow firing a glowing arrow at a target", weapon).lower()
    assert "do not draw its emitted projectile" in item
    assert "attack scene" in item

    armor = {"category": "armor", "runtimePlan": {"resultKind": "armor"}, "armor": {"armorSlot": "head"}}
    armor_prompt = role_visual_prompt_guard("item", "astral armor", armor).lower()
    assert "authored head-slot armor item" in armor_prompt
    assert "helmet" not in armor_prompt
    assert "no character" in armor_prompt

    potion = {"category": "potion", "runtimePlan": {"resultKind": "potion"}}
    potion_prompt = role_visual_prompt_guard("item", "enchanted restorative apple", potion).lower()
    assert "enchanted restorative apple" in potion_prompt
    assert "authored consumable item" in potion_prompt
    assert not any(word in potion_prompt for word in ("bottle", "vial", "flask"))

    furniture = {"category": "furniture", "runtimePlan": {"resultKind": "furniture"}}
    furniture_prompt = role_visual_prompt_guard("item", "cozy alchemy desk in a room", furniture).lower()
    assert "authored placeable furniture item" in furniture_prompt
    assert "no furnished room" in furniture_prompt


def _contract_check_visual_director_rejects_noncanonical_response_keys(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "heldSpritePrompt": "ignored old field",
                "assetModes": {"impact": "baked_sprite"},
                "projectileAssetMode": "particle_vfx",
                "bakedAssets": {"projectile": {"mode": "baked_sprite", "prompt": "one amber bolt"}},
            }
        })}}]},
    )
    data = {
        "id": "visual_canonical_trace",
        "name": "Amber Caster",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon", "engineCalls": [{"fn": "set_item_stats", "params": {"resultKind": "weapon"}}]},
        "attack": {"enabled": True, "runtimeFamily": "cast", "delivery": "cast", "shotCount": 1},
        "visual": {"imagePrompt": "amber wand"},
    }
    out = VISUAL.apply_visual_director(data, {}, {}, {}, {})
    assert out is data
    assert data["debug"]["visualDirectorStatus"] == "visual_director_degraded"
    assert "visualKit" not in data
    error = str(data.get("debug", {}).get("visualDirectorError", ""))
    assert "Extra inputs are not permitted" in error
    assert "assetModes" in error
    assert "heldSpritePrompt" in error
    assert "projectileAssetMode" in error


def _contract_check_vfx_director_receives_compiled_runtime_truth_for_beam_and_children() -> None:
    card = _vfx_compact_child_for_director({
        "name": "Prismatic Thread",
        "attack": {
            "enabled": True,
            "runtimeFamily": "beam",
            "delivery": "cast",
            "movement": "straight",
            "effect": "electric",
            "onHit": "lightning_arc",
            "shotCount": 1,
            "splitCount": 2,
            "secondaryTrigger": "on_hit",
            "channelUse": True,
            "beamWidthPx": 16,
            "beamChargeTicks": 24,
            "immunityCooldown": 10,
        },
        "visualKit": {
            "styleGuide": "prismatic thread pixel art",
            "palette": ["cyan", "violet"],
            "bakedAssets": {"projectile": {"mode": "particle_vfx", "reason": "beam body"}},
            "vfxIntent": "a narrow charged beam with restrained sparks",
        },
    })
    attack = card["attackFacts"]
    assert attack["runtimeFamily"] == "beam"
    assert attack["effect"] == "electric"
    assert attack["onHit"] == "lightning_arc"
    assert attack["secondaryTrigger"] == "on_hit"
    assert attack["beamWidthPx"] == 16
    assert card["visualAssetKit"]["vfxIntent"] == "a narrow charged beam with restrained sparks"


def _contract_check_on_expire_children_are_non_recursive_in_csharp_owner() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    child_policy = (root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs").read_text(encoding="utf-8")
    runtime = (root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    assert "GeneratedSecondaryTriggerPolicy.OnExpire" in source
    assert "childSpec.MaxChildProjectiles = 0" in source
    assert "childSpec.MaxChildDepth = 0" in source
    assert "GeneratedChildSpecPolicy.SanitizeGenericGameplayChild" in runtime
    assert "child.SecondaryTrigger = GeneratedSecondaryTriggerPolicy.OnHit" in child_policy
    assert "child.SplitCount = 0" in child_policy


def _contract_check_generated_ammo_and_authored_throwable_contract_remains_distinct() -> None:
    ammo = compile_runtime_plan_to_genome_patch({"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "ammo", "damageClass": "ranged", "damage": 7, "maxStack": 999, "craftYield": 50, "ammoFor": "arrow"}},
        {"fn": "ammo_behavior", "params": {"ammoFor": "arrow"}},
    ]}})
    throwable = compile_runtime_plan_to_genome_patch({"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "consumable_weapon", "damageClass": "ranged", "damage": 14, "maxStack": 99, "ammoFor": ""}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "throw", "delivery": "throw", "projectileFamily": "poison_dart", "effect": "poison"}},
    ]}})
    assert ammo["kind"] == "ammo" and ammo["ammoFor"] == "arrow"
    assert throwable["kind"] == "consumable_weapon"
    assert throwable["runtimeFamily"] == "throw"
    assert throwable["projectileFamily"] == "poison_dart"


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_v12_pre_livetest_manual_trace_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_active_planner_contract_is_honest_and_compact',
            '_contract_check_only_canonical_temporary_helper_name_is_accepted_and_world_entities_stay_rejected',
            '_contract_check_multishot_projectile_prompt_is_one_body_but_explicit_bundle_survives',
            '_contract_check_child_and_item_role_guards_separate_runtime_multiplicity_and_inventory_scene',
            '_contract_check_visual_director_rejects_noncanonical_response_keys',
            '_contract_check_vfx_director_receives_compiled_runtime_truth_for_beam_and_children',
            '_contract_check_on_expire_children_are_non_recursive_in_csharp_owner',
            '_contract_check_generated_ammo_and_authored_throwable_contract_remains_distinct',
        ),
    )
