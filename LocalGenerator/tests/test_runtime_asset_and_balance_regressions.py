from __future__ import annotations

import sys
from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LocalGenerator"))
SERVER = ROOT / "LocalGenerator" / "infini_local" / "web" / "server.py"
COMBINE_PIPELINE = ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "combine_pipeline.py"
LLM_PIPELINE = ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "llm_authoring_pipeline.py"
VISUAL_PIPELINE = ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "visual_generation_pipeline.py"
MODEL = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs"


def _check_warn_invalid_generated_assets_do_not_attach_runtime_paths() -> None:
    src = VISUAL_PIPELINE.read_text(encoding="utf-8")
    assert "generated_warn_invalid" in src
    assert "usable_path = bool(path) and status not in {\"failed\", \"prompt_only\", \"placeholder\", \"generated_warn_invalid\"}" in src
    assert "strict_ai_authorship_keep_imperfect_ai_sprite_not_placeholder" in src


def _check_csharp_hydrates_conventional_role_asset_names_for_old_cached_recipes() -> None:
    src = read_text_with_partial_bundles(MODEL)
    assert "SpriteStatusAllowsRuntimePath" in src
    assert "ConventionalAssetFileName(Id, \"_projectile\")" in src
    assert "ConventionalAssetFileName(Id, \"_impact\")" in src
    assert "ConventionalAssetFileName(Id, \"_child\")" in src
    assert "ConventionalAssetFileName(Id, \"_field\")" in src


def _check_low_tier_consumable_projectile_power_is_capped() -> None:
    src = SERVER.read_text(encoding="utf-8") + COMBINE_PIPELINE.read_text(encoding="utf-8")
    assert "is_low_tier_consumable_projectile_item" in src
    assert "+consumable_projectile_cap" in src
    assert "Stackable starter projectiles are consumables, not reusable hardmode weapons" in src


def _check_projectile_prompt_for_linear_family_is_horizontal_side_view() -> None:
    src = VISUAL_PIPELINE.read_text(encoding="utf-8") + COMBINE_PIPELINE.read_text(encoding="utf-8")
    assert "long axis horizontal left-to-right" in src
    assert "tip/nose points right" in src
    assert "not a vertical inventory icon" in src
    assert "weapon_family in {\"bow\", \"crossbow\", \"repeater\", \"gun\", \"shotgun\", \"blowgun\", \"dart\", \"launcher\", \"harpoon\"}" in src


def _check_recursive_generation_has_soft_power_and_variety_nudges() -> None:
    src = LLM_PIPELINE.read_text(encoding="utf-8") + COMBINE_PIPELINE.read_text(encoding="utf-8")
    assert "creativeVariance" in src
    assert "Avoid cloning the strongest generated parent's name/runtimeFamily/onHit" in src
    assert "recursiveDamageSoftCap" in src
    assert "powerBudget prices active behavior/complexity" in src


def _check_server_uses_safe_env_float_for_llm_temperatures() -> None:
    src = LLM_PIPELINE.read_text(encoding="utf-8") + VISUAL_PIPELINE.read_text(encoding="utf-8")
    assert '_env_float("INFINI_LLM_TEMPERATURE", 0.38, 0.0, 1.2)' in src
    assert '_env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", 0.42, 0.0, 1.2)' in src


def _check_potion_merge_preserves_independent_channels_and_buff_pairs() -> None:
    src = COMBINE_PIPELINE.read_text(encoding="utf-8")
    assert "def _bounded_parent_potion_stats" in src
    assert "healLife/healMana are independent" in src
    assert "buffType/buffTime stay paired" in src
    assert "different_parent_buffs_one_item_slot_chose_" in src
    assert "parent_heal = max" not in src
    assert "elif parent_mana" not in src


def _check_planner_contract_uses_engine_calls_for_utility_instead_of_hard_bans() -> None:
    src = LLM_PIPELINE.read_text(encoding="utf-8")
    assert "use a mobility engineCall" in src
    assert "tool_capability" in src
    assert "apply_player_effect_on_use" in src
    assert "Do not describe teleportation" not in src
    assert "Do not promise block digging" not in src
    assert "terrain/contact interaction" not in src


def _check_child_and_starfall_pressure_are_priced_in_balance_cost() -> None:
    from infini_local.pipelines.pipeline_support import behavior_cost_multiplier, estimate_engine_metrics

    base = {"shotCount": 1, "pierce": 0, "aoeRadiusTiles": 0, "lifetimeTicks": 60, "useTimeTicks": 24, "reliability": 1.0}
    no_child = behavior_cost_multiplier({**base, "onHit": "none"})
    starburst = behavior_cost_multiplier({**base, "onHit": "starburst", "splitCount": 4, "maxChildProjectiles": 4})
    starfall = behavior_cost_multiplier({**base, "onHit": "starfall", "splitCount": 4, "maxChildProjectiles": 4})

    assert starburst > no_child * 1.12
    assert starfall > no_child * 1.18
    assert estimate_engine_metrics({**base, "onHit": "starfall", "splitCount": 4}, {})["childProjectilesPerProc"] == 4


def _check_csharp_runtime_surface_contains_starfall_onhit_opcode() -> None:
    src = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    limits = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "InfiniRuntimeLimits.cs").read_text(encoding="utf-8")
    assert "MaxSupportedOnHitCode = 18" in limits
    assert "case 18:" in src
    assert "Starfall" in src
    assert "falling star" in src.lower()


def _check_csharp_swing_runtime_executes_starfall_onhit_opcode() -> None:
    item = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    start = item.index("private static void ApplyGeneratedSwingOnHitEffects")
    end = item.index("private static int SwingDebuffTime", start)
    swing_onhit = item[start:end]
    assert "case 18:" in swing_onhit
    assert "SpawnGeneratedSwingStarfall" in swing_onhit
    assert "18 => \"falling starfall\"" in item

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_warn_invalid_generated_assets_do_not_attach_runtime_paths',
    '_check_csharp_hydrates_conventional_role_asset_names_for_old_cached_recipes',
    '_check_low_tier_consumable_projectile_power_is_capped',
    '_check_projectile_prompt_for_linear_family_is_horizontal_side_view',
    '_check_recursive_generation_has_soft_power_and_variety_nudges',
    '_check_server_uses_safe_env_float_for_llm_temperatures',
    '_check_potion_merge_preserves_independent_channels_and_buff_pairs',
    '_check_planner_contract_uses_engine_calls_for_utility_instead_of_hard_bans',
    '_check_child_and_starfall_pressure_are_priced_in_balance_cost',
    '_check_csharp_runtime_surface_contains_starfall_onhit_opcode',
    '_check_csharp_swing_runtime_executes_starfall_onhit_opcode'
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


def test_runtime_asset_and_balance_regressions_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
