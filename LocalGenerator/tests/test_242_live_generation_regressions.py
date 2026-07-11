from __future__ import annotations

import inspect
import json

import pytest
from pydantic import ValidationError

from infini_local.core.boundary_models import (
    validate_executable_item_boundary,
    validate_visual_kit_boundary,
)
from infini_local.pipelines import combine_pipeline as COMBINE
from infini_local.pipelines import visual_generation_pipeline as VISUAL
from infini_local.pipelines import pipeline_visual_config as VISUAL_CONFIG
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.executable_boundary_projection import project_attack_presentation_fields
from infini_local.pipelines.item_power_knowledge import apply_item_knowledge, canonicalize
from infini_local.pipelines.llm_authoring_pipeline import planner_runtime_promise_gate
from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt


def _wooden_sword() -> dict:
    return {
        "name": "Деревянный меч",
        "internalName": "WoodenSword",
        "sourceMod": "Terraria",
        "damage": 7,
        "damageClass": "melee",
        "useTime": 20,
        "useAnimation": 20,
        "rare": 0,
        "value": 100,
        "maxStack": 1,
        "material": False,
    }


def _workbench() -> dict:
    return {
        "name": "Верстак",
        "internalName": "WorkBench",
        "sourceMod": "Terraria",
        "damage": -1,
        "damageClass": "none",
        "useTime": 10,
        "useAnimation": 14,
        "rare": 0,
        "value": 150,
        "maxStack": 9999,
        "consumable": True,
        "createTile": 18,
    }


def _carpentry_plan(*, weird_twist: str = "Splinters become bounded secondary projectiles.") -> dict:
    return {
        "name": "Carpentry Blade",
        "tooltip": "A rough wooden blade that throws splinters on impact.",
        "concept": {
            "fantasy": "A wooden sword reinforced with the structural essence of a workbench.",
            "mergeLogic": "The sword supplies the attack and the workbench supplies wood and joinery.",
            "weirdTwist": weird_twist,
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "melee",
                        "damage": 12,
                        "useTimeTicks": 24,
                        "useAnimationTicks": 24,
                        "knockback": 6,
                        "maxStack": 1,
                    },
                },
                {
                    "fn": "perform_melee_attack",
                    "params": {
                        "family": "broadsword",
                        "speed": 8,
                        "rangeTiles": 3,
                        "lifetimeTicks": 24,
                        "projectileShape": "wooden broadsword",
                    },
                },
                {
                    "fn": "spawn_secondary_projectiles",
                    "params": {
                        "trigger": "on_hit",
                        "count": 3,
                        "damageMultiplier": 0.35,
                        "projectileShape": "wooden splinter",
                        "material": "wood",
                    },
                },
                {
                    "fn": "spawn_contact_particles",
                    "params": {"effect": "leaf", "amount": 10, "scale": 0.8, "material": "wood"},
                },
            ],
            "visualIntent": {
                "item": "A rough wooden plank sword with a blocky workbench-style guard.",
                "impact": "Wood chips and sawdust.",
                "vfxIntent": "Wood chips and sawdust on impact.",
                "vfxAvoid": "No magical glow or generic steel blade.",
            },
        },
        "visual": {"itemPrompt": "One rough wooden plank broadsword with visible joinery."},
    }


def _compiled_carpentry_item() -> dict:
    a = _wooden_sword()
    b = _workbench()
    ca = canonicalize(a)
    cb = canonicalize(b)
    data = validate_and_repair(_carpentry_plan(), a, b, ca, cb, "wood_workbench_live_regression")
    data = apply_item_knowledge(data, a, b, ca, cb)
    return attach_gameplay_and_attack(data, a, b, ca, cb)


def test_wood_workbench_keeps_visual_intent_out_of_attack_and_grounds_palette() -> None:
    data = _compiled_carpentry_item()

    assert data["visual"]["palette"] == ["brown", "tan", "dark_brown"]
    assert data["visual"]["vfxIntent"] == "Wood chips and sawdust on impact."
    assert data["visual"]["vfxAvoid"] == "No magical glow or generic steel blade."
    assert "vfxIntent" not in data["attack"]
    assert "vfxAvoid" not in data["attack"]

    # Legacy cache payloads are migrated narrowly; arbitrary unknown AttackSpec data
    # remains visible to the strict boundary instead of being silently discarded.
    data["attack"]["vfxIntent"] = "legacy sawdust"
    data["attack"]["vfxMaterialHints"] = ["wood", "sawdust"]
    project_attack_presentation_fields(data, source="test_legacy_cache")
    assert "vfxIntent" not in data["attack"]
    assert "vfxMaterialHints" not in data["attack"]
    assert data["visual"]["vfxIntent"] == "Wood chips and sawdust on impact."
    validate_executable_item_boundary(data)


def test_visual_kit_repairs_singleton_text_lists_without_leaking_invalid_raw_output(monkeypatch) -> None:
    parsed = validate_visual_kit_boundary({
        "qualityNotes": "Keep the wooden material readable.",
        "animationPlan": "short swing then sawdust impact",
        "vfxMaterialHints": "wood",
    })
    assert parsed["qualityNotes"] == ["Keep the wooden material readable."]
    assert parsed["animationPlan"] == ["short swing then sawdust impact"]
    assert parsed["vfxMaterialHints"] == ["wood"]
    with pytest.raises(ValidationError):
        validate_visual_kit_boundary({"qualityNotes": 42})

    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(VISUAL, "anime_reference_opportunity", lambda _data: "none")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "palette": ["brown", "tan", "dark brown"],
                "itemIconPrompt": "one rough wooden plank sword",
                "vfxIntent": "sawdust burst",
                "vfxAvoid": "no magic glow",
                "vfxMaterialHints": "wood",
                "qualityNotes": "Keep the wood grain readable.",
            }
        })}}]},
    )
    data = _compiled_carpentry_item()
    result = VISUAL.apply_visual_director(data, _wooden_sword(), _workbench(), {}, {})
    assert result["visualKit"]["qualityNotes"] == ["Keep the wood grain readable."]
    assert result["debug"]["visualDirectorBoundaryRepairs"] == [
        "vfxMaterialHints:string_to_singleton_list",
        "qualityNotes:string_to_singleton_list",
    ]
    assert result["visual"]["vfxIntent"] == "sawdust burst"
    assert "vfxIntent" not in result["attack"]
    assert "vfxAvoid" not in result["attack"]
    assert "vfxMaterialHints" not in result["attack"]

    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "itemSilhouetteContract": "THIS INVALID RAW CONTRACT MUST NOT LEAK",
                "qualityNotes": 42,
            }
        })}}]},
    )
    invalid_data = _compiled_carpentry_item()
    invalid_result = VISUAL.apply_visual_director(invalid_data, _wooden_sword(), _workbench(), {}, {})
    assert "visualKit" not in invalid_result
    assert "THIS INVALID RAW CONTRACT MUST NOT LEAK" not in json.dumps(invalid_result, ensure_ascii=False)
    assert "visualDirectorError" in invalid_result["debug"]


def test_promise_gate_blocks_fake_platform_and_damaging_field_but_keeps_real_children() -> None:
    platform = _carpentry_plan(
        weird_twist="On hit it creates temporary floating workbench platforms the player can stand on."
    )
    platform_gate = planner_runtime_promise_gate(platform)
    assert platform_gate["ok"] is False
    assert any(row["kind"] == "temporary_platform" for row in platform_gate["blockingClaims"])

    fake_field = _carpentry_plan(
        weird_twist="The splinters linger as a damaging field after the strike."
    )
    field_gate = planner_runtime_promise_gate(fake_field)
    assert field_gate["ok"] is False
    assert any(row["kind"] == "damaging_field" for row in field_gate["blockingClaims"])

    valid = _carpentry_plan(
        weird_twist="On hit it throws three bounded wooden splinter projectiles."
    )
    assert planner_runtime_promise_gate(valid)["ok"] is True


def test_flux2_uses_subject_first_material_grounded_prompt(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL_CONFIG, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(VISUAL_CONFIG, "SDCPP_MODEL", "C:/models/flux-2-klein-4b-Q8_0.gguf")
    monkeypatch.setattr(VISUAL_CONFIG, "ZIMAGE_PROMPT_CONTRACT", "auto")

    data = _compiled_carpentry_item()
    prompt = normalize_asset_prompt(
        data,
        "item",
        "A thick wooden plank blade with a square workbench guard and one small iron nail.",
        48,
    )
    lower = prompt.lower()
    assert lower.startswith("a terraria-like pixel-art item sprite")
    assert "color scheme and materials: brown, tan, dark brown" in lower
    assert "primary authored material: wood" in lower
    assert "main item body visibly made of wood" in lower
    assert "generic polished steel" in lower
    assert "show only the item sprite" in lower
    assert "palette: gray, white" not in lower


def test_strict_preflights_run_before_expensive_image_generation() -> None:
    source = inspect.getsource(COMBINE.combine)
    assert source.index("04c_strict_executable_preflight") < source.index("08_visual_director_asset_pack")
    assert source.index("08c_strict_executable_preflight") < source.index("09_visual_asset_generation")
    assert source.index("11a_project_presentation_out_of_attack") < source.index("11b_strict_executable_boundary")
