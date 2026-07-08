from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_balance_report_helper_has_powerband_and_clamp_taxonomy():
    from infini_local.core.balance_report import build_balance_report

    stage = {
        "name": "pre_hardmode_late",
        "sourceMaxDamage": 40,
        "sourceFastestUseTime": 20,
        "parentGeneratedDepths": [0, 0],
        "powerTransfer": {"weakAnchor": False},
    }
    data = {
        "category": "weapon",
        "gameplay": {"damage": 28, "useTime": 20, "rarity": 3},
        "attack": {"genome": {"shotCount": 3, "pierce": 4, "homingStrength": 0.5}},
        "debug": {
            "authorPreservingValidation": {
                "authoredDamageEnvelopeClamp": {
                    "from": 120,
                    "to": 28,
                    "reason": "code_owned_stage_dps_envelope",
                    "useTime": 20,
                    "shotCount": 3,
                    "costMultiplier": 2.1,
                }
            },
            "runtimeRepairPath": "code_structural_repair_only",
        },
    }
    report = build_balance_report(data, stage)
    assert report["schema"] == "infini.balance-report.v1"
    assert report["powerBand"] == "power_03"
    assert report["sourceBucket"] == "pre_hardmode_late"
    assert report["clamps"]["balance"][0]["kind"] == "authored_damage_soft_envelope"
    assert report["clamps"]["contract"][0]["path"] == "code_structural_repair_only"
    assert report["authority"]["softBalance"] == "Python post-authoring envelope"


def test_generated_items_attach_single_balance_report_debug_block():
    combine = read(ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "combine_gameplay.py")
    assert "attach_balance_report(data, stage)" in combine
    assert 'debug"]["statProfile"' in combine or 'debug\", {})[\"statProfile\"' in combine
    assert "sourceEnvelope" not in read(ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "llm_authoring_pipeline.py")


def test_contract_stamp_records_architecture_coherence_guard():
    from infini_local.core.contract_versions import build_contract_versions

    stamp = build_contract_versions(app_version="0.4.219", recipe_identity_version="r", runtime_api_version="v", visual_pipeline_profile="p")
    assert stamp["architectureCoherenceContract"] == "single_balance_report_clamp_taxonomy_powerband_v0.4.219"


def test_balance_docs_explain_report_and_no_active_guide_helper():
    doc = read(ROOT / "docs" / "BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md")
    assert "balanceReport" in doc
    assert "balanceClamp" in doc
    assert "safetyClamp" in doc
    assert "contractClamp" in doc
    assert "powerBand" in doc
    assert "не активный helper" in doc
