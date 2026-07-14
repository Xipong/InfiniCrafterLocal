from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES
from infini_local.qa.runtime_proof import (
    assert_runtime_proof_report,
    build_gameplay_seam_report,
    build_runtime_proof_report,
    write_runtime_proof_artifacts,
)


def _contract_check_golden_runtime_cases_cover_core_gameplay_shapes() -> None:
    case_ids = {case["caseId"] for case in GOLDEN_RUNTIME_CASES}
    assert len(GOLDEN_RUNTIME_CASES) >= 6
    assert {
        "melee_swing_onhit",
        "ranged_straight_shot",
        "magic_cast_aura",
        "accessory_runtime",
        "tool_mining_light",
        "forbidden_world_entity",
        "armor_runtime",
    }.issubset(case_ids)

    for case in GOLDEN_RUNTIME_CASES:
        assert case["caseId"]
        assert case["description"]
        assert isinstance(case["input"].get("runtimePlan", {}).get("engineCalls"), list)
        assert case["expect"].get("requiredFunctions")
        assert case.get("expectGameplay"), f"{case['caseId']} missing expectGameplay"


def _contract_check_golden_runtime_proof_reports_match_expected_envelopes() -> None:
    reports = [build_runtime_proof_report(case) for case in GOLDEN_RUNTIME_CASES]
    for report in reports:
        assert_runtime_proof_report(report)
        assert "validation" in report
        assert "provenance" in report
        assert "patch" in report
        assert "functions" in report
        assert isinstance(report["mismatches"], list)

    by_id = {report["caseId"]: report for report in reports}
    forbidden = by_id["forbidden_world_entity"]
    assert forbidden["ok"] is True
    assert forbidden["mismatches"] == []
    assert forbidden["patch"].get("runtimeFamily") == "summon"
    assert forbidden["patch"].get("weaponFamily") == "minion"
    rejected = forbidden["patch"].get("rejectedEngineCalls") or []
    assert rejected
    assert all("forbidden_world_entity" in str(row.get("reason", "")) for row in rejected)
    assert "bossNpcType" not in forbidden["patch"]
    assert "worldEntitySpawn" not in forbidden["patch"]


def _contract_check_golden_gameplay_seam_reports_match_expected_generated_item_fields() -> None:
    reports = [build_gameplay_seam_report(case) for case in GOLDEN_RUNTIME_CASES]
    for report in reports:
        assert_runtime_proof_report(report)
        assert report.get("error") is None
        item = report.get("item") or {}
        assert "gameplay" in item
        assert "attack" in item

    by_id = {report["caseId"]: report for report in reports}
    tool = by_id["tool_mining_light"]["item"]["gameplay"]
    assert tool["pickPower"] == 65
    assert tool["axePower"] == 12
    assert tool["holdLightStrength"] == 0.85
    assert "runtimeLightStrength" not in tool
    assert "runtimeLightColorName" not in tool
    armor = by_id["armor_runtime"]["item"]
    assert armor["category"] == "armor"
    assert armor["armor"]["slot"] == "body"
    assert armor["gameplay"]["damage"] == 0
    magic = by_id["magic_cast_aura"]["item"]["gameplay"]
    assert magic["manaCost"] == 8
    forbidden = by_id["forbidden_world_entity"]["item"]
    assert forbidden["attack"]["weaponFamily"] == "minion"
    assert "bossNpcType" not in (forbidden.get("gameplay") or {})


def _contract_check_golden_runtime_proof_artifact_writer_outputs_stable_json(tmp_path) -> None:
    reports = [build_runtime_proof_report(case) for case in GOLDEN_RUNTIME_CASES[:2]]
    written = write_runtime_proof_artifacts(reports, tmp_path)
    assert len(written) == 2
    for path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["caseId"]
        assert "patch" in payload
        assert "authoredStats" in payload
        assert "validation" in payload
        assert "provenance" in payload
        assert "mismatches" in payload


def _contract_check_generate_golden_runtime_proof_cli_writes_summary(tmp_path) -> None:
    out = tmp_path / "runtime_proof"
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "generate_golden_runtime_proof.py"), "--out", str(out), "--include-gameplay"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    summary_path = out / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["caseCount"] == len(GOLDEN_RUNTIME_CASES)
    assert summary["failedCount"] == 0
    assert summary.get("gameplayCaseCount") == len(GOLDEN_RUNTIME_CASES)
    assert summary.get("gameplayFailedCount") == 0
    assert len(summary["artifactPaths"]) >= len(GOLDEN_RUNTIME_CASES)


def _contract_check_live_semantic_gate_fails_on_partial_or_unsupported_heavy_rows() -> None:
    from infini_local.qa.runtime_proof import summarize_semantic_sample_rows

    rows = [
        {"caseId": "ok", "ok": True, "runtimeFamily": "shoot", "movement": "straight", "onHit": "burn", "executionStatus": "executable", "unsupportedPromises": []},
        {"caseId": "weak", "ok": True, "runtimeFamily": "", "movement": "", "onHit": "none", "executionStatus": "partial", "unsupportedPromises": ["unsupported:charge_release"]},
    ]

    summary = summarize_semantic_sample_rows(rows)

    assert summary["ok"] is False
    assert summary["failedCount"] == 0
    assert summary["semanticGate"]["ok"] is False
    assert any("partial" in reason or "unsupported" in reason for reason in summary["semanticGate"]["reasons"])


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_239_golden_runtime_proof_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_golden_runtime_cases_cover_core_gameplay_shapes',
            '_contract_check_golden_runtime_proof_reports_match_expected_envelopes',
            '_contract_check_golden_gameplay_seam_reports_match_expected_generated_item_fields',
            '_contract_check_golden_runtime_proof_artifact_writer_outputs_stable_json',
            '_contract_check_generate_golden_runtime_proof_cli_writes_summary',
            '_contract_check_live_semantic_gate_fails_on_partial_or_unsupported_heavy_rows',
        ),
    )
