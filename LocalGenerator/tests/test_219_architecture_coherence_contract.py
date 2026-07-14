from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contract_check_balance_report_helper_has_powerband_and_clamp_taxonomy():
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
    assert "INFINI_BALANCE_MODE=normalize" in report["authority"]["softBalance"]
    assert report["balanceMode"] == "safety"


def _contract_check_generated_items_attach_single_balance_report_debug_block():
    combine = read(ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "combine_gameplay.py")
    assert "attach_balance_report(data, stage)" in combine
    assert 'debug"]["statProfile"' in combine or 'debug\", {})[\"statProfile\"' in combine
    assert "sourceEnvelope" not in read(ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "llm_authoring_pipeline.py")


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_219_architecture_coherence_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_balance_report_helper_has_powerband_and_clamp_taxonomy',
            '_contract_check_generated_items_attach_single_balance_report_debug_block',
        ),
    )
