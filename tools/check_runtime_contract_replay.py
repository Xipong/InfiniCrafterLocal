#!/usr/bin/env python3
"""Cheap fail-closed historical runtime-contract replay gate.

Runs the production compiler/final projection without LLM, HTTP, image generation, or
C# execution.  By default every committed case is replayed.  ``--function`` and
``--form function:param.path`` select the exact affected union and fail when the
corpus has no coverage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.qa.runtime_contract_replay import (  # noqa: E402
    default_corpus_path,
    load_corpus,
    replay_cases,
    select_cases_by_changed_forms,
    select_cases_by_changed_functions,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=default_corpus_path())
    parser.add_argument("--function", action="append", default=[], dest="functions")
    parser.add_argument(
        "--form",
        action="append",
        default=[],
        help="exact affected form as function:param.path; repeatable",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--quiet", action="store_true")
    return parser


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    corpus = load_corpus(args.corpus)
    cases = corpus["cases"]
    selected_by_id: dict[str, dict[str, Any]] = {}
    selection: dict[str, Any] = {
        "mode": "all" if not args.functions and not args.form else "affected",
        "functions": sorted(set(args.functions)),
        "forms": sorted(set(args.form)),
    }
    if args.functions:
        for case in select_cases_by_changed_functions(corpus, args.functions):
            selected_by_id[str(case.get("caseId") or "")] = case
    if args.form:
        for case in select_cases_by_changed_forms(corpus, args.form):
            selected_by_id[str(case.get("caseId") or "")] = case
    selected = (
        sorted(selected_by_id.values(), key=lambda case: str(case.get("caseId") or ""))
        if selected_by_id
        else list(cases)
    )
    reports = replay_cases(selected)
    failures = [report for report in reports if not report.get("ok")]
    return {
        "schema": "infini.runtime-contract-replay-gate.v1",
        "ok": not failures,
        "corpusSchema": corpus.get("schema"),
        "corpusCaseCount": len(cases),
        "selectedCaseCount": len(selected),
        "selection": selection,
        "failedCaseCount": len(failures),
        "failures": [
            {
                "caseId": row.get("caseId"),
                "error": row.get("error"),
                "fingerprint": row.get("fingerprint"),
                "expectedFingerprint": row.get("expectedFingerprint"),
            }
            for row in failures
        ],
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        report = build_report(args)
    except Exception as exc:
        report = {
            "schema": "infini.runtime-contract-replay-gate.v1",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if not args.quiet:
        print(text)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
