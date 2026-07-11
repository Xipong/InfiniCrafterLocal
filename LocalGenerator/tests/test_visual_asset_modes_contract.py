from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import visual_generation_pipeline
from infini_local.pipelines import visual_asset_plan as ASSET_PLAN
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.pipelines.visual_generation_pipeline import apply_visual_director
import infini_local.pipelines.visual_sprite_generation as SPRITES
VISUAL = visual_generation_pipeline


def _base_item() -> dict:
    return {
        "id": "mode_test",
        "name": "Plain Tin Blade",
        "category": "weapon",
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {"resultKind": "weapon"}}]},
        "attack": {
            "enabled": True,
            "runtimeFamily": "swing",
            "runtimePlanAuthored": True,
            "projectileSpritePrompt": "",
            "impactSpritePrompt": "tiny metal spark",
            "childSpritePrompt": "",
            "fieldSpritePrompt": "",
        },
        "visual": {"imagePrompt": "small tin blade", "impactImagePrompt": "tiny metal spark"},
        "visualKit": {
            "bakedAssets": {
                "impact": {"mode": "particle_vfx"},
                "child": {"mode": "none"},
                "field": {"mode": "none"},
            }
        },
    }


def _check_impact_setting_is_allow_gate_not_force_generate(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_IMPACT_IMAGES", True)
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_CHILD_FIELD_IMAGES", True)
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)

    plan = build_visual_asset_plan(_base_item())
    impact = next(x for x in plan if x["role"] == "impact")
    child = next(x for x in plan if x["role"] == "child")
    field = next(x for x in plan if x["role"] == "field")

    assert impact["status"] == "skipped_not_authored_baked"
    assert impact["assetMode"] == "particle_vfx"
    assert child["status"] == "skipped_not_authored_baked"
    assert field["status"] == "skipped_not_authored_baked"


def _check_model_can_explicitly_request_baked_extra_asset(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_IMPACT_IMAGES", True)
    data = _base_item()
    data["visualKit"]["bakedAssets"]["impact"] = {"mode": "baked_sprite"}

    plan = build_visual_asset_plan(data)
    impact = next(x for x in plan if x["role"] == "impact")

    assert impact.get("status") != "skipped_not_authored_baked"
    assert impact["assetMode"] == "baked_sprite"
    assert impact["prompt"] == "tiny metal spark"


def _check_prompt_alone_does_not_request_baked_impact(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_IMPACT_IMAGES", True)
    data = _base_item()
    data["visualKit"]["bakedAssets"].pop("impact", None)

    plan = build_visual_asset_plan(data)
    impact = next(x for x in plan if x["role"] == "impact")

    assert impact["prompt"] == "tiny metal spark"
    assert impact["status"] == "skipped_not_authored_baked"


def _check_projectile_prompt_alone_no_longer_uses_legacy_baked_fallback(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    data = _base_item()
    data["attack"]["runtimeFamily"] = "cast"
    data["attack"]["projectileSpritePrompt"] = "right-facing violet bolt"
    data["visual"]["projectileImagePrompt"] = "right-facing violet bolt"

    plan = build_visual_asset_plan(data)
    projectile = next(x for x in plan if x["role"] == "projectile")

    assert projectile["status"] == "skipped_not_authored_baked"
    assert projectile["assetMode"] == "particle_vfx"
    assert "legacy_baked_sprite" not in str(plan)


def _check_nested_baked_assets_can_request_projectile_sprite(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    data = _base_item()
    data["visualKit"]["bakedAssets"] = {"projectile": {"mode": "baked_sprite", "prompt": "right-facing amber dart"}}

    plan = build_visual_asset_plan(data)
    projectile = next(x for x in plan if x["role"] == "projectile")

    assert projectile.get("status") != "skipped_not_authored_baked"
    assert projectile["assetMode"] == "baked_sprite"
    assert projectile["prompt"] == "right-facing amber dart"


def _check_item_bodied_projectiles_reuse_item_sprite_unless_distinct(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)

    boomerang = _base_item()
    boomerang["attack"].update({"runtimeFamily": "returning", "delivery": "returning", "hideUseGraphic": True})
    boomerang["visualKit"]["bakedAssets"] = {
        "projectile": {"mode": "baked_sprite", "prompt": "same jade boomerang in flight"}
    }
    reused = next(x for x in build_visual_asset_plan(boomerang) if x["role"] == "projectile")

    transformed = _base_item()
    transformed["attack"].update({"runtimeFamily": "returning", "delivery": "returning", "hideUseGraphic": True})
    transformed["visualKit"]["bakedAssets"] = {
        "projectile": {
            "mode": "baked_sprite",
            "prompt": "boomerang unfolds into a distinct three-bladed flight form",
            "distinctFromItem": True,
        }
    }
    distinct = next(x for x in build_visual_asset_plan(transformed) if x["role"] == "projectile")

    sword_shot = _base_item()
    sword_shot["attack"].update({"runtimeFamily": "shoot", "delivery": "shoot", "weaponFamily": "sword"})
    sword_shot["visualKit"]["bakedAssets"] = {
        "projectile": {"mode": "baked_sprite", "prompt": "generated stalactite shaped like the blade"}
    }
    emitted = next(x for x in build_visual_asset_plan(sword_shot) if x["role"] == "projectile")

    assert reused["status"] == "reuses_item_sprite"
    assert reused["assetMode"] == "reuse_item_sprite"
    assert distinct.get("status") != "reuses_item_sprite"
    assert distinct["assetMode"] == "baked_sprite"
    assert emitted["assetMode"] == "baked_sprite"

    invalid = _base_item()
    invalid["attack"].update({"runtimeFamily": "boomerang", "delivery": "throw"})
    invalid["visualKit"]["bakedAssets"] = {
        "projectile": {"mode": "baked_sprite", "prompt": "same handheld body in flight"}
    }
    invalid_slot = next(x for x in build_visual_asset_plan(invalid) if x["role"] == "projectile")
    assert invalid_slot["assetMode"] != "reuse_item_sprite"
    assert "noncanonical_runtime_family" in invalid.get("debug", {}).get("visualAssetRuntimeGates", "")


def _check_visual_director_preserves_distinct_projectile_contract(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(
        VISUAL,
        "llm_chat_json",
        lambda _req, timeout=None: {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "visualKit": {
                            "bakedAssets": {
                                "projectile": {
                                    "mode": "baked_sprite",
                                    "prompt": "distinct opened three-blade flight body",
                                    "distinctFromItem": True,
                                    "reason": "authored transformation",
                                }
                            }
                        }
                    })
                }
            }]
        },
    )

    data = _base_item()
    data["attack"].update({"runtimeFamily": "returning", "delivery": "returning"})
    result = apply_visual_director(data, {}, {}, {}, {})
    projectile = result["visualKit"]["bakedAssets"]["projectile"]

    assert projectile["distinctFromItem"] is True
    assert projectile["mode"] == "baked_sprite"


def _check_reuse_item_sprite_slot_never_calls_image_backend(monkeypatch) -> None:
    monkeypatch.setattr(SPRITES, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(SPRITES, "maybe_generate_sprite", lambda data: data)
    monkeypatch.setattr(SPRITES, "write_visual_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        SPRITES,
        "build_visual_asset_plan",
        lambda _data: [
            {"role": "item", "status": "generated", "assetMode": "baked_sprite"},
            {
                "role": "projectile",
                "status": "reuses_item_sprite",
                "assetMode": "reuse_item_sprite",
                "prompt": "same boomerang body",
                "assetId": "reuse_projectile",
                "canvas": 32,
            },
        ],
    )

    def forbidden_backend(*_args, **_kwargs):
        raise AssertionError("reuse_item_sprite must not invoke image generation")

    monkeypatch.setattr(SPRITES, "generate_visual_asset", forbidden_backend)
    data = {"id": "reuse_case", "visual": {"spriteStatus": "generated"}, "attack": {"enabled": True}}

    SPRITES.maybe_generate_visual_assets(data)


def _check_anime_reference_opportunity_is_rare_deterministic_and_bounded(monkeypatch) -> None:
    levels = [
        VISUAL.anime_reference_opportunity({"recipeKey": f"anime-reference-{index}"})
        for index in range(2000)
    ]
    assert levels.count("none") >= 1700
    assert 120 <= levels.count("subtle") <= 260
    assert 15 <= levels.count("strong") <= 70
    assert VISUAL.anime_reference_opportunity({"recipeKey": "stable-reference"}) == VISUAL.anime_reference_opportunity({"recipeKey": "stable-reference"})

    strong_key = next(f"anime-reference-{index}" for index in range(2000) if levels[index] == "strong")
    captured = {}

    monkeypatch.setattr(VISUAL, "USE_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(VISUAL, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(VISUAL, "is_llm_planner", lambda _data: True)
    monkeypatch.setattr(VISUAL, "resolve_llm_model", lambda: "strong-test-model")

    def fake_llm(req, timeout=None):
        captured["payload"] = json.loads(req["messages"][1]["content"])
        return {"choices": [{"message": {"content": json.dumps({
            "visualKit": {
                "itemIconPrompt": "an original crescent scythe with a recognizable Soul Eater homage",
                "animeReference": {
                    "strength": "strong",
                    "source": "Soul Eater",
                    "motifs": ["asymmetric crescent blade", "black-red soul stitching"],
                },
            }
        })}}]}

    monkeypatch.setattr(VISUAL, "llm_chat_json", fake_llm)
    data = _base_item()
    data["recipeKey"] = strong_key
    result = apply_visual_director(data, {}, {}, {}, {})

    policy = captured["payload"]["animeReferenceOpportunity"]
    assert policy["maximumStrength"] == "strong"
    assert policy["optional"] is True
    assert "animeReference" in captured["payload"]["requiredJsonShape"]["visualKit"]
    assert result["visualKit"]["animeReference"] == {
        "strength": "strong",
        "source": "Soul Eater",
        "motifs": ["asymmetric crescent blade", "black-red soul stitching"],
    }


# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_impact_setting_is_allow_gate_not_force_generate',
    '_check_model_can_explicitly_request_baked_extra_asset',
    '_check_prompt_alone_does_not_request_baked_impact',
    '_check_projectile_prompt_alone_no_longer_uses_legacy_baked_fallback',
    '_check_nested_baked_assets_can_request_projectile_sprite',
    '_check_item_bodied_projectiles_reuse_item_sprite_unless_distinct',
    '_check_visual_director_preserves_distinct_projectile_contract',
    '_check_reuse_item_sprite_slot_never_calls_image_backend',
    '_check_anime_reference_opportunity_is_rare_deterministic_and_bounded'
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


def test_visual_asset_modes_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
