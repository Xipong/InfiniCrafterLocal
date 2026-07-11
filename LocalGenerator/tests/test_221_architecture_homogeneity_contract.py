from __future__ import annotations

import re
from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "LocalGenerator"
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"


def read(path: Path) -> str:
    return read_text_with_partial_bundles(path)


def test_balance_policy_has_one_source_of_truth_for_power_bands_and_envelopes():
    policy = read(LOCAL / "infini_local" / "core" / "balance_policy.py")
    report = read(LOCAL / "infini_local" / "core" / "balance_report.py")
    combine = read(LOCAL / "infini_local" / "pipelines" / "combine_pipeline.py")
    combine_balance = read(LOCAL / "infini_local" / "pipelines" / "combine_balance.py")

    assert "POWER_BAND_BY_BUCKET" in policy
    assert "VANILLA_LIKE_WEAPON_ENVELOPES" in policy
    assert "def weapon_envelope_for_bucket" in policy
    assert "from infini_local.core.balance_policy import power_band_for_bucket" in report
    assert "from infini_local.core.balance_policy import weapon_envelope_for_bucket" in combine_balance
    assert "VANILLA_LIKE_WEAPON_ENVELOPES: dict" not in combine
    assert "VANILLA_LIKE_WEAPON_ENVELOPES: dict" not in combine_balance
    assert "POWER_BAND_BY_BUCKET: dict" not in report
    assert "terrariaProgressionReference" not in combine


def test_csharp_packet_ids_are_routed_through_one_packet_id_class():
    packets = read(MOD / "Common" / "InfiniNetPacketIds.cs")
    mod = read(MOD / "InfiniCrafterLocal.cs")
    assert "public static class InfiniNetPacketIds" in packets
    assert "CancelServerCraft = 12" in packets
    assert "retired" not in packets
    assert "NotifyGeneratedItem = 2" in packets
    assert "InfiniNetPacketIds.CancelServerCraft" in mod
    assert "InfiniNetPacketIds.NotifyGeneratedAssets" in mod

    for path in MOD.rglob("*.cs"):
        if path.name == "InfiniNetPacketIds.cs":
            continue
        text = read(path)
        assert not re.search(r"public\s+const\s+byte\s+Packet\w+\s*=\s*\d+\s*;", text), path


def test_csharp_runtime_api_and_opcode_limits_have_one_source_of_truth():
    limits = read(MOD / "Common" / "InfiniRuntimeLimits.cs")
    item_data = read(MOD / "Common" / "Models" / "GeneratedItemData.cs")
    projectile = read(MOD / "Content" / "Projectiles" / "GeneratedProjectile.cs")

    assert "public static class InfiniRuntimeLimits" in limits
    assert 'RuntimeApiCurrent = "v0.4.48"' in limits
    assert "MaxSupportedMovementCode = 18" in limits
    assert "private const string RuntimeApiCurrent = InfiniRuntimeLimits.RuntimeApiCurrent" in item_data
    assert "private const int MaxSupportedMovementCode = InfiniRuntimeLimits.MaxSupportedMovementCode" in item_data
    assert "private const int MaxSupportedOnHitCode = InfiniRuntimeLimits.MaxSupportedOnHitCode" in projectile
    assert 'private const string RuntimeApiCurrent = "v0.4.48"' not in item_data
    assert "private const int MaxSupportedMovementCode = 18" not in item_data
    assert "private const int MaxSupportedMovementCode = 18" not in projectile
