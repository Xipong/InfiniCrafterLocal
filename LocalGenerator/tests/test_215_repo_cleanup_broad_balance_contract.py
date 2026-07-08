from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "LocalGenerator"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_repo_docs_are_compact_and_old_gui_prompt_noise_removed():
    assert not (ROOT / "ZIMAGE_GUI_438_PATCH_RU.txt").exists()
    for rel in [
        "README_RU.md",
        "PROJECT_ARCHITECTURE_RU.md",
        "PROJECT_MAP_RU.md",
        "QUICK_START_RU.md",
        "LocalGenerator/README_RU.md",
        "LocalGenerator/PROJECT_ARCHITECTURE_RU.md",
        "LocalGenerator/PROJECT_MAP_RU.md",
        "LocalGenerator/QUICK_START_RU.md",
    ]:
        text = read(ROOT / rel)
        assert "0.4.239" in "\n".join(text.splitlines()[:16])
        limit = 30000 if "ARCHITECTURE" in rel else 12000
        assert len(text) < limit


def test_broad_soft_balance_uplift_is_global_but_still_single_authority():
    from infini_local.pipelines.combine_pipeline import (
        apply_family_locks_to_genome,
        clamp_vanilla_like_weapon_damage,
        vanilla_like_weapon_envelope,
    )

    contracts = read(LOCAL / "infini_local" / "core" / "contract_versions.py")
    pipeline = read(LOCAL / "infini_local" / "pipelines" / "combine_pipeline.py")
    balance_policy = read(LOCAL / "infini_local" / "core" / "balance_policy.py")
    assert "repoCleanupBroadBalanceContract" in contracts
    assert "repo_docs_cleanup_and_broad_soft_balance_uplift_v0.4.216" in contracts
    assert "intentionally sits above a vanilla-like baseline" in balance_policy
    assert "terrariaProgressionReference" not in pipeline

    assert vanilla_like_weapon_envelope("pre_boss")["max"] >= 60
    assert vanilla_like_weapon_envelope("lunar")["dps"] >= 1700

    stage = {"name": "pre_boss", "powerBudget": 3.0, "sourceFastestUseTime": 18, "powerTransfer": {}}
    ordinary = clamp_vanilla_like_weapon_damage(55, 20, stage, use_time=20, shot_count=1, cost_multiplier=1.0, raise_floor=False)
    spammy = clamp_vanilla_like_weapon_damage(120, 20, stage, use_time=8, shot_count=6, cost_multiplier=3.8, raise_floor=False)
    assert ordinary == 55
    assert spammy < 120

    data = {}
    genome = {"shotCount": 8, "pierce": 12, "lifetimeTicks": 700, "aoeRadiusTiles": 9, "rangeTiles": 140, "homingStrength": 1.0}
    clamped = apply_family_locks_to_genome(genome, {}, {}, data, {"powerBudget": 5.0})
    assert clamped["shotCount"] == 6
    assert clamped["pierce"] == 8
    assert clamped["lifetimeTicks"] == 540
    assert clamped["rangeTiles"] == 105.0
    assert clamped["homingStrength"] == 0.68
