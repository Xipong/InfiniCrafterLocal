from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES
from infini_local.qa.runtime_proof import (
    build_gameplay_seam_report,
    build_runtime_proof_report,
    write_runtime_proof_artifacts,
)


DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "agent_reports" / "runtime_proof"


def build_summary(reports: list[dict[str, Any]], *, kind: str = "compiler") -> dict[str, Any]:
    cases = [
        {
            "caseId": report.get("caseId"),
            "ok": bool(report.get("ok")),
            "mismatches": list(report.get("mismatches") or []),
            "functions": list(report.get("functions") or []),
            "error": report.get("error"),
            "kind": kind,
        }
        for report in reports
    ]
    failed = [case for case in cases if not case["ok"]]
    return {
        "ok": not failed,
        "caseCount": len(cases),
        "failedCount": len(failed),
        "cases": cases,
    }


def generate_reports(out_dir: Path, *, include_gameplay: bool = False) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    compiler_reports = [build_runtime_proof_report(case) for case in GOLDEN_RUNTIME_CASES]
    compiler_dir = out_dir / "compiler"
    written = write_runtime_proof_artifacts(compiler_reports, compiler_dir)
    summary = build_summary(compiler_reports, kind="compiler")
    summary["artifactPaths"] = [str(path) for path in written]

    if include_gameplay:
        gameplay_reports = [build_gameplay_seam_report(case) for case in GOLDEN_RUNTIME_CASES]
        gameplay_dir = out_dir / "gameplay_seam"
        gameplay_written = write_runtime_proof_artifacts(gameplay_reports, gameplay_dir)
        gameplay_summary = build_summary(gameplay_reports, kind="gameplay_seam")
        summary["gameplayCaseCount"] = gameplay_summary["caseCount"]
        summary["gameplayFailedCount"] = gameplay_summary["failedCount"]
        summary["gameplayCases"] = gameplay_summary["cases"]
        summary["artifactPaths"].extend(str(path) for path in gameplay_written)
        summary["ok"] = bool(summary["ok"] and gameplay_summary["ok"])

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["summaryPath"] = str(summary_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic runtimePlan golden proof artifacts.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="Output directory for JSON reports.")
    parser.add_argument(
        "--include-gameplay",
        action="store_true",
        help="Also run validate/repair + attach_gameplay_and_attack seam proof for each golden case.",
    )
    args = parser.parse_args(argv)

    summary = generate_reports(args.out, include_gameplay=bool(args.include_gameplay))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
