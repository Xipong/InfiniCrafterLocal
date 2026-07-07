from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"


def test_generated_item_data_records_compact_applied_trace() -> None:
    main = read_text_with_partial_bundles(MOD / "Common" / "Models" / "GeneratedItemData.cs")
    debug = (MOD / "Common" / "Models" / "GeneratedItemData.Debug.cs").read_text(encoding="utf-8")

    assert "public sealed partial class GeneratedItemData" in main
    assert "RecordAppliedItemTrace(item, isArmor, isAccessory, actualAmmo);" in main
    assert '"infini.applied-trace.v1"' in debug
    assert "Attack.RuntimeFamily" in debug
    assert "Attack.SplitCount" in debug
    assert "Armor.SetBonusGenericDamage" in debug
    assert "Accessory.Endurance" in debug


def test_csharp_god_file_split_phase1_markers_exist() -> None:
    projectile_net = MOD / "Content" / "Projectiles" / "GeneratedProjectile.NetSync.cs"
    item_debug = MOD / "Common" / "Models" / "GeneratedItemData.Debug.cs"
    normalize = MOD / "Common" / "Models" / "GeneratedItemData.Normalize.cs"
    craft_state = MOD / "Common" / "Players" / "InfiniCraftPlayer.CraftState.cs"
    player = read_text_with_partial_bundles(MOD / "Common" / "Players" / "InfiniCraftPlayer.cs")

    assert projectile_net.exists()
    assert item_debug.exists()
    assert normalize.exists()
    assert not (MOD / "Common" / "Models" / "GeneratedItemData.Compat.cs").exists()
    assert craft_state.exists()
    assert "IsMatchingVisualSyncTarget" in projectile_net.read_text(encoding="utf-8")
    assert "Attack.RuntimeFamily = NormalizeRuntimeFamily(Attack.RuntimeFamily);" in normalize.read_text(encoding="utf-8")
    assert "NormalizeCraftRequestId" in craft_state.read_text(encoding="utf-8")
    assert "public sealed partial class InfiniCraftPlayer" in player
