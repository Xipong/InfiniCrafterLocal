from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
from infini_local.core.runtime_authoring.function_contract_registry import (
    ENGINE_FUNCTION_CONTRACT_BY_NAME,
)
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"
LOCAL = ROOT / "LocalGenerator"


def read(path: Path) -> str:
    return read_text_with_partial_bundles(path)


def _contract_check_generated_tool_mining_speed_and_alt_light_are_executable():
    item = read(MOD / "Content" / "Items" / "GeneratedItem.cs")
    authoring = read(LOCAL / "infini_local" / "core" / "runtime_authoring" / "__init__.py")
    assert "ApplyAuthoredToolMiningSpeed" in item
    assert "gp.MiningSpeedScale" in item
    assert "player.pickSpeed /= scale" in item
    assert "from infini_local.core.runtime_authoring.function_contract_registry import" in authoring
    tool_contract = ENGINE_FUNCTION_CONTRACT_BY_NAME["tool_capability"]
    mining_speed = next(param for param in tool_contract.params if param.name == "miningSpeedScale")
    assert mining_speed.compiled_fields == ("miningSpeedScale",)
    assert "AltLightStrength" in item
    assert "mode == \"light\"" in item
    assert "ApplyGeneratedUtilityBuff(gp.AltGeneratedBuff, syncNetwork:" in item
    assert "RequestGeneratedAltUseFromServer" in item
    assert "gp.AltGeneratedBuff.EmitLightStrength" in item


def _contract_check_accessory_authoring_now_covers_runtime_supported_fields():
    equipment = read(LOCAL / "infini_local" / "core" / "runtime_authoring" / "equipment.py")
    model = read(MOD / "Common" / "Models" / "GeneratedItemData.cs")
    item = read(MOD / "Content" / "Items" / "GeneratedItem.cs")
    for field in ["sentrySlots", "manaCostReduction", "ammoSaveChance", "aggro", "endurance", "armorPenetration"]:
        assert field in equipment
    for field in ["SentrySlots", "ManaCostReduction", "AmmoSaveChance", "Aggro", "Endurance", "ArmorPenetration"]:
        assert field in model
    assert "player.maxTurrets += a.SentrySlots" in item
    assert "player.manaCost = Math.Max" in item
    assert "player.endurance += a.Endurance" in item
    assert "GetArmorPenetration" in item


def _contract_check_station_manual_ux_and_prefetch_are_bounded_not_autofill():
    ui = read(MOD / "Common" / "UI" / "InfiniCraftStationUISystem.cs")
    player = read(MOD / "Common" / "Players" / "InfiniCraftPlayer.cs")
    config = read(MOD / "Common" / "Config" / "InfiniGameplayQolConfig.cs")
    assert "DrawInputName" in ui
    assert "A+B valid · manual craft only" in ui
    assert "Manual A/B inputs" in ui
    assert "fillButton" not in ui and "swapButton" not in ui
    assert "InventoryAssetPrefetchMaxItems" in config
    assert "GeneratedPrefetchCandidateItems" in player
    assert "player?.armor" in player
    assert "player?.miscEquips" in player
    assert "2 => 30 * 60" in player


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_212_gameplay_runtime_coverage_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_generated_tool_mining_speed_and_alt_light_are_executable',
            '_contract_check_accessory_authoring_now_covers_runtime_supported_fields',
            '_contract_check_station_manual_ux_and_prefetch_are_bounded_not_autofill',
        ),
    )
