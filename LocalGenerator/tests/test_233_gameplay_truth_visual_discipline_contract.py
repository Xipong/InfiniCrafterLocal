from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import visual_asset_plan as ASSET_PLAN
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch
from infini_local.services.visual_asset_pipeline import strip_conflicting_sprite_prompt_bits


def _contract_check_incompatible_second_primary_cannot_override_first_executor() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 18, "useTimeTicks": 24}},
                {"fn": "perform_melee_attack", "params": {"family": "broadsword", "speed": 12, "rangeTiles": 4}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 10, "rangeTiles": 12, "lifetimeTicks": 40}},
            ]
        },
    }

    patch = compile_runtime_plan_to_genome_patch(data)

    assert patch["runtimeFamily"] == "swing"
    assert patch["delivery"] == "swing"
    assert patch["disableItemMeleeHitbox"] is False
    assert patch["rejectedRootExecutorCalls"][0]["reason"] == "runtime_one_root_executor"
    assert "recoveredPrimaryConflictAsSecondary" not in patch
    assert patch.get("splitCount", 0) == 0
    assert patch.get("maxChildProjectiles", 0) == 0


def _contract_check_parent_flaming_tag_does_not_author_burn() -> None:
    data = {
        "category": "weapon",
        "itemKnowledge": {
            "parents": [
                {"name": "Подожженная стрела", "tags": ["ammo", "flaming", "ranged"]},
                {"name": "Факел", "tags": ["torch", "material"]},
            ]
        },
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "consumable_weapon", "damageClass": "ranged", "damage": 12, "useTimeTicks": 20, "consumable": True}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "throw", "delivery": "throw", "movement": "gravity_arc", "speed": 8, "rangeTiles": 40, "lifetimeTicks": 300}},
                {"fn": "emit_light", "params": {"strength": 0.8, "lightColorName": "orange"}},
            ]
        },
    }

    patch = compile_runtime_plan_to_genome_patch(data)

    assert patch["onHit"] == "none"
    assert "parentMechanicPreserved" not in patch
    assert "debuffTime" not in patch
    assert patch["runtimeLightStrength"] == 0.8
    assert patch["primaryColorName"] == "orange"


def _contract_check_melee_swing_runtime_gates_wasted_projectile_baked_asset(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    data = {
        "id": "bench_blade",
        "category": "weapon",
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {"resultKind": "weapon"}}]},
        "attack": {"enabled": True, "runtimeFamily": "swing", "delivery": "swing", "disableItemMeleeHitbox": False},
        "visual": {"imagePrompt": "heavy wooden bench blade", "projectileImagePrompt": "spinning table plank"},
        "visualKit": {
            "projectileSpritePrompt": "spinning table plank",
            "bakedAssets": {"projectile": {"mode": "baked_sprite", "distinctFromItem": True}},
        },
    }

    plan = build_visual_asset_plan(data)
    projectile = next(x for x in plan if x["role"] == "projectile")

    assert projectile["status"] == "skipped_not_authored_baked"
    assert projectile["assetMode"] == "particle_vfx"
    assert "distinctFromItem" not in data["visualKit"]["bakedAssets"]["projectile"]
    assert "melee_swing_uses_item_sprite_no_projectile_asset" in data["debug"]["visualAssetRuntimeGates"]


def _contract_check_field_baked_asset_requires_compiled_field_runtime(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_CHILD_FIELD_IMAGES", True)
    data = {
        "id": "lantern_dart",
        "category": "weapon",
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {"resultKind": "weapon"}}]},
        "attack": {"enabled": True, "runtimeFamily": "throw", "delivery": "throw"},
        "visual": {"imagePrompt": "small vial", "fieldImagePrompt": "anchored flame"},
        "visualKit": {
            "fieldSpritePrompt": "anchored flame",
            "bakedAssets": {"field": {"mode": "baked_sprite"}},
        },
    }

    plan = build_visual_asset_plan(data)
    field = next(x for x in plan if x["role"] == "field")

    assert field["status"] == "skipped_runtime_unused"
    assert field["assetMode"] == "none"
    assert "no_compiled_field_runtime_or_vfx_slot" in data["debug"]["visualAssetRuntimeGates"]


def _contract_check_zimage_prompt_sanitizer_strips_sprite_resolution_tokens() -> None:
    cleaned = strip_conflicting_sprite_prompt_bits(
        "glowing purple wooden splinter, sharp, dark trail, 16x16 pixel art, 24x24 resolution"
    ).lower()

    assert "16x16" not in cleaned
    assert "24x24" not in cleaned
    assert "resolution" not in cleaned
    assert "pixel art" in cleaned


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_233_gameplay_truth_visual_discipline_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_incompatible_second_primary_cannot_override_first_executor',
            '_contract_check_parent_flaming_tag_does_not_author_burn',
            '_contract_check_melee_swing_runtime_gates_wasted_projectile_baked_asset',
            '_contract_check_field_baked_asset_requires_compiled_field_runtime',
            '_contract_check_zimage_prompt_sanitizer_strips_sprite_resolution_tokens',
        ),
    )
