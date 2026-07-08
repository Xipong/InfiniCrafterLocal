from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "LocalGenerator"
sys.path.insert(0, str(LOCAL))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_progression_guide_is_human_reference_not_active_prompt_or_helper():
    assert (ROOT / "docs" / "TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md").exists()
    assert not (LOCAL / "data" / "terraria_progression_reference.json").exists()
    assert not (LOCAL / "infini_local" / "core" / "progression_reference.py").exists()

    authoring = read(LOCAL / "infini_local" / "pipelines" / "llm_authoring_pipeline.py")
    combine = read(LOCAL / "infini_local" / "pipelines" / "combine_pipeline.py")
    balance_policy = read(LOCAL / "infini_local" / "core" / "balance_policy.py")
    contracts = read(LOCAL / "infini_local" / "core" / "contract_versions.py")

    for forbidden in [
        "terrariaProgressionReference",
        "progressionIntent",
        "mechanicRisk",
        "balanceReference",
        "compact_progression_reference_for_llm",
        "mechanic_balance_pressure",
        "TERRARIA_PROGRESS_REFERENCE_CONTRACT_VERSION",
    ]:
        assert forbidden not in authoring
        assert forbidden not in combine
        assert forbidden not in contracts

    assert "balanceSingleAuthorityContract" in contracts
    assert "code_owned_balance_envelope_no_active_guide_helper_v0.4.216" in contracts


def test_balance_envelope_is_single_code_owned_layer_with_correct_cost_math():
    from infini_local.pipelines.combine_pipeline import (
        clamp_vanilla_like_weapon_damage,
        vanilla_like_weapon_envelope,
    )

    combine = read(LOCAL / "infini_local" / "pipelines" / "combine_balance.py")
    balance_policy = read(LOCAL / "infini_local" / "core" / "balance_policy.py")
    authoring = read(LOCAL / "infini_local" / "pipelines" / "llm_authoring_pipeline.py")
    prompt_owner = read(LOCAL / "infini_local" / "pipelines" / "llm_authoring_prompt.py")
    authoring_surface = authoring + prompt_owner
    balance_doc = read(ROOT / "docs" / "BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md")

    assert "Single code-owned numeric balance layer" in balance_policy
    assert "Older code divided by cost here" in combine
    assert "pressure_cost = max" in combine
    assert "raise_floor=False" in authoring_surface
    assert "authoredDamageEnvelopeClamp" in authoring_surface
    assert "не должен превращаться" in balance_doc

    assert vanilla_like_weapon_envelope("wood")["max"] >= 24
    assert vanilla_like_weapon_envelope("pre_boss")["max"] >= 60
    assert vanilla_like_weapon_envelope("endgame")["dps"] >= 2700

    stage = {"name": "pre_boss", "sourceFastestUseTime": 20, "powerTransfer": {}}
    # High multishot/cost authored damage must clamp down instead of being excused by cost.
    clamped = clamp_vanilla_like_weapon_damage(
        100,
        10,
        stage,
        use_time=10,
        shot_count=4,
        cost_multiplier=3.0,
        raise_floor=False,
    )
    assert clamped < 100

    # Low authored utility damage stays low when raise_floor=False.
    low = clamp_vanilla_like_weapon_damage(2, 10, stage, use_time=40, shot_count=1, cost_multiplier=1.0, raise_floor=False)
    assert low == 2


def test_non_weapon_parents_do_not_crash_balance_report() -> None:
    from infini_local.pipelines.combine_balance import stat_profile_for
    from infini_local.core.balance_report import build_balance_report

    a = {"name": "Hermes Boots", "damage": 0, "useTime": 0, "value": 1000, "accessory": True}
    b = {"name": "Aglet", "damage": 0, "useTime": 0, "value": 500, "accessory": True}
    stage = stat_profile_for(a, b, set())
    # Finite stage field is required so accessory/tool crafts do not crash later.
    assert stage.get("sourceFastestUseTime") not in (None, float("inf"))
    import math
    assert math.isfinite(float(stage.get("sourceFastestUseTime")))
    report = build_balance_report({"gameplay": {"kind": "accessory", "damage": 0}, "debug": {}}, stage)
    assert int(report["parents"]["fastestUseTime"]) >= 0
