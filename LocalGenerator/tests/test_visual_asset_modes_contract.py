from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
VISUAL = server.visual_generation_pipeline


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
            "impactAssetMode": "particle_vfx",
            "childAssetMode": "none",
            "fieldAssetMode": "none",
        },
    }


def _check_impact_setting_is_allow_gate_not_force_generate(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_IMPACT_IMAGES", True)
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_CHILD_FIELD_IMAGES", True)
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)

    plan = server.build_visual_asset_plan(_base_item())
    impact = next(x for x in plan if x["role"] == "impact")
    child = next(x for x in plan if x["role"] == "child")
    field = next(x for x in plan if x["role"] == "field")

    assert impact["status"] == "skipped_not_authored_baked"
    assert impact["assetMode"] == "particle_vfx"
    assert child["status"] == "skipped_not_authored_baked"
    assert field["status"] == "skipped_not_authored_baked"


def _check_model_can_explicitly_request_baked_extra_asset(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_IMPACT_IMAGES", True)
    data = _base_item()
    data["visualKit"]["impactAssetMode"] = "baked_sprite"

    plan = server.build_visual_asset_plan(data)
    impact = next(x for x in plan if x["role"] == "impact")

    assert impact.get("status") != "skipped_not_authored_baked"
    assert impact["assetMode"] == "baked_sprite"
    assert impact["prompt"] == "tiny metal spark"


def _check_prompt_alone_does_not_request_baked_impact(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_IMPACT_IMAGES", True)
    data = _base_item()
    data["visualKit"].pop("impactAssetMode", None)

    plan = server.build_visual_asset_plan(data)
    impact = next(x for x in plan if x["role"] == "impact")

    assert impact["prompt"] == "tiny metal spark"
    assert impact["status"] == "skipped_not_authored_baked"


def _check_projectile_prompt_alone_no_longer_uses_legacy_baked_fallback(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    data = _base_item()
    data["attack"]["runtimeFamily"] = "cast"
    data["attack"]["projectileSpritePrompt"] = "right-facing violet bolt"
    data["visual"]["projectileImagePrompt"] = "right-facing violet bolt"

    plan = server.build_visual_asset_plan(data)
    projectile = next(x for x in plan if x["role"] == "projectile")

    assert projectile["status"] == "skipped_not_authored_baked"
    assert projectile["assetMode"] == "particle_vfx"
    assert "legacy_baked_sprite" not in str(plan)


def _check_nested_baked_assets_can_request_projectile_sprite(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    data = _base_item()
    data["visualKit"]["bakedAssets"] = {"projectile": {"mode": "baked_sprite", "prompt": "right-facing amber dart"}}

    plan = server.build_visual_asset_plan(data)
    projectile = next(x for x in plan if x["role"] == "projectile")

    assert projectile.get("status") != "skipped_not_authored_baked"
    assert projectile["assetMode"] == "baked_sprite"
    assert projectile["prompt"] == "right-facing amber dart"

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
    '_check_nested_baked_assets_can_request_projectile_sprite'
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
