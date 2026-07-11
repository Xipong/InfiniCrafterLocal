from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch


def _check_player_effect_on_use_compiles_multi_buff_channels() -> None:
    data = {
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "potion"}},
                {"fn": "apply_player_effect_on_use", "params": {"healMana": 20, "buffs": [
                    {"buffType": 9, "buffTime": 18000},
                    {"buffType": 104, "buffTime": 9000},
                ]}},
            ]
        }
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["healMana"] == 20
    assert patch["buffCode"] == 9
    assert len(patch["extraBuffs"]) == 2


def _check_tool_light_and_mobility_calls_are_accepted_without_presets() -> None:
    data = {
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "tool"}},
                {"fn": "tool_capability", "params": {"pickPower": 45}},
                {"fn": "emit_light", "params": {"strength": 0.4, "color": "gold"}},
                {"fn": "mobility_effect", "params": {"mode": "blink_to_cursor", "rangeTiles": 24, "cooldownTicks": 180, "safeTileOnly": True}},
            ]
        }
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["pickPower"] == 45
    assert patch["runtimeLightStrength"] == 0.4
    assert patch["primaryColorName"] == "gold"
    assert patch["mobilityMode"] == "blink_to_cursor"
    assert "rejectedMobilityExecution" not in patch


def _check_generated_utility_buff_call_compiles_to_patch() -> None:
    data = {
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "potion"}},
                {"fn": "apply_player_effect_on_use", "params": {"generatedBuff": {"durationTicks": 1200, "miningSpeedMultiplier": 1.25, "emitLightStrength": 0.4, "lightColorName": "gold", "oreSenseRadiusTiles": 14}}},
            ]
        }
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["generatedBuff"]["durationTicks"] == 1200
    assert patch["generatedBuff"]["miningSpeedMultiplier"] == 1.25
    assert patch["generatedBuff"]["emitLightStrength"] == 0.4
    assert patch["generatedBuff"]["lightColorName"] == "gold"
    assert patch["generatedBuff"]["oreSenseRadiusTiles"] == 14


def _check_alt_hold_extractinator_and_use_condition_calls_compile_to_patch() -> None:
    data = {
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_alt_use_mode", "params": {"mode": "mobility", "mobilityMode": "blink_to_cursor", "rangeTiles": 30, "cooldownTicks": 240, "safeTileOnly": True}},
                {"fn": "hold_item_effect", "params": {"lightStrength": 0.55, "lightColorName": "cyan", "generatedBuff": {"durationTicks": 90, "movementSpeed": 0.12}}},
                {"fn": "extractinator_output", "params": {"resultType": 75, "stack": 3}},
                {"fn": "use_condition", "params": {"mode": "mana_above", "minMana": 40}},
            ]
        }
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["altUseMode"] == "mobility"
    assert patch["altMobilityMode"] == "blink_to_cursor"
    assert patch["altMobilityRangeTiles"] == 30
    assert patch["altMobilityCooldownTicks"] == 240
    assert patch["holdLightStrength"] == 0.55
    assert patch["holdLightColorName"] == "cyan"
    assert patch["holdGeneratedBuff"]["movementSpeed"] == 0.12
    assert patch["extractinatorOutputItemType"] == 75
    assert patch["extractinatorOutputStack"] == 3
    assert patch["useConditionMode"] == "mana_above"
    assert patch["useConditionMinMana"] == 40

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_player_effect_on_use_compiles_multi_buff_channels',
    '_check_tool_light_and_mobility_calls_are_accepted_without_presets',
    '_check_generated_utility_buff_call_compiles_to_patch',
    '_check_alt_hold_extractinator_and_use_condition_calls_compile_to_patch'
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


def test_runtime_enginecall_expansion_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
