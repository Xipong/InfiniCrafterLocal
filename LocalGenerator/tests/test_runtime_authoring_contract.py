from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    compile_runtime_plan_to_genome_result,
    infer_attack_pattern_from_runtime,
    normalize_runtime_plan_inplace,
    runtime_plan_quality_report,
)


def _check_runtime_plan_compiler_keeps_current_playable_core() -> None:
    data = {
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 5, "useTimeTicks": 24, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 8.5, "rangeTiles": 45, "lifetimeTicks": 90, "shotCount": 1, "spreadRadians": 0, "pierce": 0, "projectileShape": "thin splinter bolt"}},
                {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 3, "damageMultiplier": 0.25, "spreadRadians": 0.35, "lifetimeTicks": 12, "sameTargetBias": 0.75}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "split", "aoeRadiusTiles": 0}},
                {"fn": "spawn_contact_particles", "params": {"effect": "dust", "amount": 7, "scale": 0.45}},
                {"fn": "leave_trail_or_field", "params": {"trailLength": 4, "visualOnly": True}},
            ],
        }
    }
    normalize_runtime_plan_inplace(data)
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "shoot"
    assert patch["delivery"] == "shoot"
    assert patch["movement"] == "straight"
    assert patch["speed"] == 8.5
    assert patch["splitCount"] == 3
    assert patch["maxChildProjectiles"] == 3
    assert patch["maxChildDepth"] == 1
    assert patch["burstDustCap"] == 7
    assert patch["trailLength"] == 4
    assert infer_attack_pattern_from_runtime(patch, "ranged") == "ranged_projectile"
    assert runtime_plan_quality_report(data)["hasRealChildren"] is True


def _check_runtime_plan_rejects_extra_primary_and_non_visual_field_gameplay() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 4, "useTimeTicks": 22}},
        {"fn": "set_item_stats", "params": {"damage": 6, "craftYield": 3}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "shotCount": 1, "spreadRadians": 0.05, "pierce": 0}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "shotCount": 2, "spreadRadians": 0.25, "pierce": 1}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "throw", "delivery": "throw", "movement": "gravity_arc", "shotCount": 1}},
        {"fn": "leave_trail_or_field", "params": {"trailLength": 5, "fieldRadiusTiles": 4, "fieldLifetimeTicks": 80, "visualOnly": False}},
    ]}}
    result = compile_runtime_plan_to_genome_result(data)
    patch = result["patch"]
    assert patch["useTimeTicks"] == 22
    assert patch["craftYield"] == 3
    assert patch["shotCount"] == 3
    assert patch["spreadRadians"] == 0.25
    assert patch["pierce"] == 1
    assert patch["rejectedPrimaryCalls"][0]["reason"] == "runtime_one_primary_family"
    assert patch["trailLength"] == 5
    assert patch["vfxFieldRadiusTiles"] == 4
    assert patch["vfxFieldLifetimeTicks"] == 80
    assert "fieldRadiusTiles" not in patch
    assert patch["rejectedTrailCalls"][0]["reason"] == "visualOnly_false_not_executable"


def _check_chain_requires_count_and_does_not_create_children_by_accident() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 7, "useTimeTicks": 24}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight"}},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "chain", "count": 2}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["onHit"] == "chain"
    assert patch["chainCount"] == 2
    assert patch["splitCount"] == 0

    bad = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 7, "useTimeTicks": 24}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight"}},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "chain"}},
    ]}}
    patch2 = compile_runtime_plan_to_genome_patch(bad)
    assert patch2["onHit"] == "none"
    assert patch2.get("onHitDemotedReason") == "chain_requires_count_gt_0"


def _check_spear_thrust_delivery_is_distinct_from_sword_swing() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 18, "useTimeTicks": 27}},
        {"fn": "perform_melee_attack", "params": {
            "family": "spear",
            "speed": 8,
            "lifetimeTicks": 25,
            "pierce": -1,
            "projectileShape": "grave-marked spear blade",
            "projectileMotion": "owner-checked spear thrust",
        }},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "thrust"
    assert patch["delivery"] == "thrust"
    assert patch["movement"] == "straight"
    assert infer_attack_pattern_from_runtime(patch, "melee") == "spear_thrust"



def _check_direct_shoot_projectile_gets_only_tiny_unambiguous_runtime_family_repair() -> None:
    spear = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 18, "useTimeTicks": 27}},
        {"fn": "shoot_projectile", "params": {
            "weaponFamily": "spear",
            "movement": "straight",
            "speed": 8,
            "lifetimeTicks": 25,
            "projectileShape": "short grave-marked spear blade",
            "projectileMotion": "owner-checked thrusting lance extension",
        }},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(spear)
    assert patch["runtimeFamily"] == "thrust"
    assert patch["runtimeFamilyRepair"].startswith("light:")
    assert infer_attack_pattern_from_runtime(patch, "melee") == "spear_thrust"

    conflicting = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 18, "useTimeTicks": 27}},
        {"fn": "shoot_projectile", "params": {
            "weaponFamily": "spear",
            "delivery": "cast",
            "movement": "straight",
            "speed": 8,
        }},
    ]}}
    patch2 = compile_runtime_plan_to_genome_patch(conflicting)
    assert patch2["runtimeContractError"] == "primary_attack_requires_runtimeFamily"
    assert "runtimeFamily" not in patch2

    prose_only = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 18, "useTimeTicks": 27}},
        {"fn": "shoot_projectile", "params": {
            "delivery": "swing",
            "movement": "straight",
            "projectileShape": "short grave-marked spear blade",
            "projectileMotion": "owner-checked thrusting lance extension",
        }},
    ]}}
    patch3 = compile_runtime_plan_to_genome_patch(prose_only)
    assert patch3["runtimeFamily"] == "swing"
    assert patch3["runtimeFamilyRepair"] == "light:delivery"
    # The repair intentionally does not read prose fields and therefore does not guess spear/thrust.
    assert infer_attack_pattern_from_runtime(patch3, "melee") == "slash_holdout"


def _check_terraria_family_semantic_calls_compile_without_generic_swing() -> None:
    staff = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 12, "useTimeTicks": 30}},
        {"fn": "cast_magic_weapon", "params": {"family": "beam_staff", "movement": "laser", "effect": "fire", "projectileShape": "ruby beam"}},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "electric", "count": 2}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(staff)
    assert patch["runtimeFamily"] == "cast"
    assert patch["delivery"] == "cast"
    assert patch["movement"] == "phase"
    assert patch["effect"] == "flame"
    assert patch["onHit"] == "lightning_arc"
    assert infer_attack_pattern_from_runtime(patch, "magic") == "laser_beam"

    bow = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 9, "useTimeTicks": 28}},
        {"fn": "fire_ranged_weapon", "params": {"family": "bow", "movement": "straight", "projectileShape": "arrow"}},
    ]}}
    bow_patch = compile_runtime_plan_to_genome_patch(bow)
    assert bow_patch["runtimeFamily"] == "shoot"
    assert bow_patch["delivery"] == "shoot"
    assert bow_patch["weaponFamily"] == "bow"
    assert bow_patch["useStyleCode"] == 5
    assert bow_patch["hideUseGraphic"] is True

    boomerang = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 14, "useTimeTicks": 32}},
        {"fn": "perform_melee_attack", "params": {"family": "boomerang", "projectileShape": "grave chakram"}},
    ]}}
    patch2 = compile_runtime_plan_to_genome_patch(boomerang)
    assert patch2["runtimeFamily"] == "returning"
    assert patch2["delivery"] == "throw"
    assert patch2["movement"] == "boomerang"



def _check_semantic_terraria_weapon_family_calls_compile_to_distinct_runtime_behaviors() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 12, "useTimeTicks": 32}},
        {"fn": "perform_melee_attack", "params": {"family": "flail", "speed": 9, "rangeTiles": 18, "lifetimeTicks": 80, "projectileShape": "grave flail head"}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "flail"
    assert patch["delivery"] == "flail"
    assert patch["movement"] == "flail_tether"
    assert patch["weaponFamily"] == "flail"
    assert infer_attack_pattern_from_runtime(patch, "melee") == "flail_tether"

    yoyo = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 10, "useTimeTicks": 25}},
        {"fn": "perform_melee_attack", "params": {"family": "yoyo", "rangeTiles": 14, "lifetimeTicks": 240, "projectileShape": "bone yoyo"}},
    ]}}
    patch2 = compile_runtime_plan_to_genome_patch(yoyo)
    assert patch2["runtimeFamily"] == "yoyo"
    assert patch2["delivery"] == "yoyo"
    assert patch2["movement"] == "yoyo_hover"
    assert infer_attack_pattern_from_runtime(patch2, "melee") == "yoyo_hover"

    whip = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "summon", "damage": 9, "useTimeTicks": 30}},
        {"fn": "perform_melee_attack", "params": {"family": "whip", "rangeTiles": 12, "lifetimeTicks": 28, "projectileShape": "thorn whip tip"}},
    ]}}
    patch3 = compile_runtime_plan_to_genome_patch(whip)
    assert patch3["runtimeFamily"] == "whip"
    assert patch3["delivery"] == "whip"
    assert patch3["movement"] == "whip_lash"
    assert infer_attack_pattern_from_runtime(patch3, "summon") == "whip_lash"


def _check_compiled_contract_uses_executable_fields_not_legacy_fields() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 10, "useTimeTicks": 28}},
        {"fn": "perform_melee_attack", "params": {"family": "spear", "speed": 8, "lifetimeTicks": 25, "projectileShape": "test spear"}},
    ]}}
    result = compile_runtime_plan_to_genome_result(data)
    compiled = result["compiled"]
    assert compiled["compiler"] == "runtime_plan_to_attack_spec"
    assert "executableFields" in compiled
    assert "legacyFields" not in compiled
    assert compiled["executableFields"]["runtimeFamily"] == "thrust"
    assert compiled["executableFields"]["delivery"] == "thrust"
    assert compiled["executableFields"]["weaponFamily"] == "spear"
    assert compiled["executableFields"]["useStyleCode"] == 5
    assert compiled["executableFields"]["hideUseGraphic"] is True
    assert compiled["executableFields"]["disableItemMeleeHitbox"] is True
    assert compiled["executableFields"]["ownerHitCheck"] is True


def _check_spear_form_does_not_encode_magic_executor() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 24, "useTimeTicks": 31, "manaCost": 8}},
        {"fn": "cast_magic_weapon", "params": {"family": "crystal_spear", "projectileFamily": "spear", "movement": "straight", "speed": 11, "rangeTiles": 42, "lifetimeTicks": 70, "projectileShape": "crystal spear"}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "cast"
    assert patch["delivery"] == "cast"
    assert patch["weaponFamily"] == "magic"
    assert patch["projectileFamily"] == "spear"
    assert infer_attack_pattern_from_runtime(patch, "magic") == "magic_projectile"

    melee_crystal_spear = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 20, "useTimeTicks": 30}},
        {"fn": "perform_melee_attack", "params": {"family": "spear", "effect": "frost", "projectileShape": "crystallized spear thrust"}},
    ]}}
    patch2 = compile_runtime_plan_to_genome_patch(melee_crystal_spear)
    assert patch2["runtimeFamily"] == "thrust"
    assert patch2["weaponFamily"] == "spear"
    assert patch2.get("projectileFamily", "") != "spear"  # no hidden cast/form rewrite

    plain_spear_through_magic_function = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 20, "useTimeTicks": 30}},
        {"fn": "cast_magic_weapon", "params": {"family": "spear", "movement": "slow_homing", "projectileShape": "glowing spear"}},
    ]}}
    patch3 = compile_runtime_plan_to_genome_patch(plain_spear_through_magic_function)
    assert patch3["runtimeFamily"] == "cast"
    assert patch3["weaponFamily"] == "magic"
    assert patch3["projectileFamily"] == "spear"
    assert infer_attack_pattern_from_runtime(patch3, "magic") == "magic_projectile"


def _check_direct_projectile_family_spear_does_not_repair_to_thrust() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 18, "useTimeTicks": 27}},
        {"fn": "shoot_projectile", "params": {
            "projectileFamily": "spear",
            "delivery": "cast",
            "movement": "straight",
            "speed": 9,
            "projectileShape": "magic spear",
        }},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "cast"
    assert patch["runtimeFamilyRepair"] == "light:delivery"
    assert patch["projectileFamily"] == "spear"

    no_executor = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 18, "useTimeTicks": 27}},
        {"fn": "shoot_projectile", "params": {
            "projectileFamily": "spear",
            "movement": "straight",
            "speed": 9,
        }},
    ]}}
    patch2 = compile_runtime_plan_to_genome_patch(no_executor)
    assert patch2["runtimeContractError"] == "primary_attack_requires_runtimeFamily"
    assert "runtimeFamily" not in patch2

    compound_shape_word_is_not_magic = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 18, "useTimeTicks": 27}},
        {"fn": "shoot_projectile", "params": {
            "weaponFamily": "crystal_spear",
            "movement": "straight",
            "speed": 9,
        }},
    ]}}
    patch3 = compile_runtime_plan_to_genome_patch(compound_shape_word_is_not_magic)
    assert patch3["runtimeContractError"] == "primary_attack_requires_runtimeFamily"
    assert "runtimeFamily" not in patch3


def _check_melee_secondary_requires_explicit_secondary_body() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 20, "useTimeTicks": 28}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "swing", "delivery": "swing", "movement": "straight", "speed": 10}},
        {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 2, "damageMultiplier": 0.35}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "swing"
    assert patch["splitCount"] == 0
    assert patch["maxChildProjectiles"] == 0
    assert patch["secondaryDamageMultiplier"] == 0
    assert "secondarySuppressedByMeleeCore" in patch


def _check_melee_secondary_with_authored_body_stays_playable() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 20, "useTimeTicks": 28}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "swing", "delivery": "swing", "movement": "straight", "speed": 10}},
        {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 2, "damageMultiplier": 0.25, "projectileShape": "tiny ember shard", "material": "ember"}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["splitCount"] == 2
    assert patch["maxChildProjectiles"] == 2
    assert patch["secondaryProjectileShape"] == "tiny ember shard"
    assert patch["secondaryMaterial"] == "ember"


def _check_forbidden_world_entity_spawns_are_rejected_not_repaired() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "summon", "damage": 18, "useTimeTicks": 30}},
        {"fn": "summon_boss", "params": {"family": "eye_of_cthulhu"}},
        {"fn": "spawn_temporary_helper_projectile", "params": {"family": "boss", "movement": "orbit", "shotCount": 1}},
        {"fn": "spawn_temporary_helper_projectile", "params": {"family": "drone", "movement": "orbit", "shotCount": 1}},
    ]}}
    normalize_runtime_plan_inplace(data)
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "summon"
    rejected = patch.get("rejectedEngineCalls") or []
    assert len(rejected) == 2
    assert all(x["reason"] == "forbidden_world_entity_spawn" for x in rejected)
    assert patch.get("weaponFamily") == "drone"
    assert {x["fn"] for x in rejected} == {"summon_boss", "spawn_temporary_helper_projectile"}


def _check_state_meter_and_triggered_action_are_preserved_as_contract_only() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 18, "useTimeTicks": 28}},
        {"fn": "cast_magic_weapon", "params": {"family": "staff", "movement": "straight", "speed": 8}},
        {"fn": "state_meter", "params": {"id": "charge", "maxValue": 3, "gainOnHit": 1, "spendOnAltUse": 3}},
        {"fn": "triggered_action", "params": {"trigger": "on_alt_use", "action": "spend_charge", "meterId": "charge", "requiredValue": 3, "spendValue": 3}},
        {"fn": "triggered_action", "params": {"trigger": "on_use", "action": "summon_boss"}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    state = patch.get("runtimeState") or {}
    assert state["executionStatus"] == "preserved_contract_not_gameplay_executor"
    assert state["stateMeters"][0]["id"] == "charge"
    assert state["triggeredActions"][0]["action"] == "spend_charge"
    rejected = patch.get("rejectedEngineCalls") or []
    assert any(x.get("reason") == "forbidden_world_entity_spawn" for x in rejected)


def _check_safe_item_capability_enginecalls_compile_to_gameplay_patch() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "tool", "damage": 0, "useTimeTicks": 32}},
        {"fn": "use_affordance", "params": {"autoReuse": False, "useTurn": True, "channelUse": True, "itemScale": 1.25, "holdoutOffsetX": 14, "holdoutOffsetY": -6, "heldVisibility": "show_projectile", "releaseTiming": "on_release", "handPose": "held_out", "initialOffsetPx": 8}},
        {"fn": "visual_effect_cue", "params": {"event": "hit", "rendererKind": "impactRing", "channel": "impactShape", "lane": "primary", "particleSystemId": "pl:spark", "scale": 1.6, "density": 0.55, "duration": 18, "alpha": 0.8}},
        {"fn": "consumption_behavior", "params": {"consumeChancePercent": 40}},
        {"fn": "ammo_behavior", "params": {"ammoFor": "bullet"}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["autoReuse"] is False
    assert patch["useTurn"] is True
    assert patch["channelUse"] is True
    assert patch["itemScale"] == 1.25
    assert patch["holdoutOffsetX"] == 14
    assert patch["holdoutOffsetY"] == -6
    assert patch["heldVisibility"] == "show_projectile"
    assert patch["releaseTiming"] == "on_release"
    assert patch["handPose"] == "held_out"
    assert patch["initialOffsetPx"] == 8
    assert patch["vfxCueCount"] == 1
    assert patch["vfxCues"][0]["rendererKind"] == "impactRing"
    assert patch["vfxCues"][0]["particleSystemId"] == "pl:spark"
    assert patch["consumeChancePercent"] == 40
    assert patch["ammoFor"] == "bullet"


def _check_overhead_barrage_onhit_is_executable_semantic_child_primitive() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 28, "useTimeTicks": 32}},
        {"fn": "perform_melee_attack", "params": {"family": "broadsword", "movement": "straight", "speed": 8, "rangeTiles": 6, "lifetimeTicks": 30, "shotCount": 1, "spreadRadians": 0, "pierce": 1, "projectileShape": "gold star-edged slash", "effect": "star"}},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "overhead_barrage", "count": 4, "aoeRadiusTiles": 2}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "swing"
    assert patch["onHit"] == "overhead_barrage"
    assert patch["splitCount"] == 4
    assert patch["maxChildProjectiles"] == 4
    assert patch["maxChildDepth"] == 1
    assert "attackPatternTags" not in patch

    data["sourceMode"] = "llm"
    from infini_local.pipelines.combine_genome import llm_authored_weapon_genome
    from infini_local.pipelines.item_power_knowledge import tags_of
    from infini_local.pipelines.combine_balance import stat_profile_for
    a = {"name": "wooden sword", "damage": 7}
    b = {"name": "fallen star"}
    tags = tags_of(a) | tags_of(b)
    genome = llm_authored_weapon_genome(data, a, b, stat_profile_for(a, b, tags))
    assert genome["onHitCode"] == 18
    assert genome["splitCount"] == 4
    assert genome["maxChildProjectiles"] >= 4

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_runtime_plan_compiler_keeps_current_playable_core',
    '_check_runtime_plan_rejects_extra_primary_and_non_visual_field_gameplay',
    '_check_chain_requires_count_and_does_not_create_children_by_accident',
    '_check_spear_thrust_delivery_is_distinct_from_sword_swing',
    '_check_direct_shoot_projectile_gets_only_tiny_unambiguous_runtime_family_repair',
    '_check_terraria_family_semantic_calls_compile_without_generic_swing',
    '_check_semantic_terraria_weapon_family_calls_compile_to_distinct_runtime_behaviors',
    '_check_compiled_contract_uses_executable_fields_not_legacy_fields',
    '_check_spear_form_does_not_encode_magic_executor',
    '_check_direct_projectile_family_spear_does_not_repair_to_thrust',
    '_check_melee_secondary_requires_explicit_secondary_body',
    '_check_melee_secondary_with_authored_body_stays_playable',
    '_check_forbidden_world_entity_spawns_are_rejected_not_repaired',
    '_check_state_meter_and_triggered_action_are_preserved_as_contract_only',
    '_check_safe_item_capability_enginecalls_compile_to_gameplay_patch',
    '_check_overhead_barrage_onhit_is_executable_semantic_child_primitive'
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


def test_runtime_authoring_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
