from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"
LOCAL = ROOT / "LocalGenerator"


def read(path: Path) -> str:
    return read_text_with_partial_bundles(path)


def test_generated_tool_mining_speed_and_alt_light_are_executable():
    item = read(MOD / "Content" / "Items" / "GeneratedItem.cs")
    authoring = read(LOCAL / "infini_local" / "core" / "runtime_authoring.py")
    assert "ApplyAuthoredToolMiningSpeed" in item
    assert "gp.MiningSpeedScale" in item
    assert "player.pickSpeed /= scale" in item
    assert "tool_capability" in authoring
    assert "miningSpeedScale" in authoring
    assert "executable held-tool mining speed multiplier" in authoring
    assert "AltLightStrength" in item
    assert "mode == \"light\"" in item
    assert "ApplyGeneratedUtilityBuff(new GeneratedBuffSpec" in item


def test_accessory_authoring_now_covers_runtime_supported_fields():
    authoring = read(LOCAL / "infini_local" / "core" / "runtime_authoring.py")
    model = read(MOD / "Common" / "Models" / "GeneratedItemData.cs")
    item = read(MOD / "Content" / "Items" / "GeneratedItem.cs")
    for field in ["sentrySlots", "manaCostReduction", "ammoSaveChance", "aggro", "endurance", "armorPenetration"]:
        assert field in authoring
    for field in ["SentrySlots", "ManaCostReduction", "AmmoSaveChance", "Aggro", "Endurance", "ArmorPenetration"]:
        assert field in model
    assert "player.maxTurrets += a.SentrySlots" in item
    assert "player.manaCost = Math.Max" in item
    assert "player.endurance += a.Endurance" in item
    assert "GetArmorPenetration" in item


def test_station_manual_ux_and_prefetch_are_bounded_not_autofill():
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


def test_vanilla_like_balance_envelope_and_todo_docs_exist():
    pipeline = read(LOCAL / "infini_local" / "pipelines" / "combine_pipeline.py")
    balance_policy = read(LOCAL / "infini_local" / "core" / "balance_policy.py")
    contracts = read(LOCAL / "infini_local" / "core" / "contract_versions.py")
    assert "VANILLA_LIKE_WEAPON_ENVELOPES" in balance_policy
    assert "clamp_vanilla_like_weapon_damage" in pipeline
    assert "balanceEnvelope" in pipeline
    assert "GAMEPLAY_RUNTIME_REBUILD_CONTRACT_VERSION" in contracts
    assert "gameplayRuntimeRebuildContract" in contracts
    todo = read(ROOT / "docs" / "TODO_ROADMAP_VERY_LATER_RU.md")
    assert "LLM authored" in todo
    assert "runtimeApplied" in todo
    assert "future_disabled" in todo
    balance_doc = read(ROOT / "docs" / "BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md")
    assert "не category-routing" in balance_doc
    assert "VANILLA_LIKE_WEAPON_ENVELOPES" in balance_doc
