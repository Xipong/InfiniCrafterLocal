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
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.qa.runtime_contract_replay import (  # noqa: E402
    default_corpus_path,
    diff_runtime_contract_fingerprints,
    load_corpus,
    replay_cases,
    runtime_contract_fingerprint_manifest,
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
    parser.add_argument(
        "--changed-contracts-from",
        metavar="GIT_REF",
        help=(
            "compare canonical registry fingerprints with the committed manifest at "
            "GIT_REF and replay only affected functions/forms; falls back to all"
        ),
    )
    parser.add_argument(
        "--fingerprints",
        type=Path,
        default=ROOT / ".agent" / "runtime_contract_fingerprints.json",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def _baseline_fingerprints(git_ref: str, path: Path) -> dict[str, Any] | None:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None
    proc = subprocess.run(
        ["git", "show", f"{git_ref}:{relative}"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    corpus = load_corpus(args.corpus)
    cases = corpus["cases"]
    auto_diff: dict[str, Any] | None = None
    auto_functions: list[str] = []
    auto_forms: list[str] = []
    if args.changed_contracts_from:
        baseline = _baseline_fingerprints(
            str(args.changed_contracts_from), args.fingerprints
        )
        if baseline is not None:
            auto_diff = diff_runtime_contract_fingerprints(
                baseline,
                runtime_contract_fingerprint_manifest(),
            )
            if not auto_diff.get("fullReplay"):
                auto_functions = list(auto_diff.get("changedFunctions") or [])
                auto_forms = list(auto_diff.get("changedForms") or [])
        else:
            auto_diff = {
                "fullReplay": True,
                "changedFunctions": [],
                "changedForms": [],
                "reason": "baseline_fingerprint_manifest_unavailable",
            }
    requested_functions = sorted(set(args.functions) | set(auto_functions))
    requested_forms = sorted(set(args.form) | set(auto_forms))
    force_all = bool(auto_diff and auto_diff.get("fullReplay"))
    selected_by_id: dict[str, dict[str, Any]] = {}
    selection: dict[str, Any] = {
        "mode": (
            "all"
            if force_all or (not requested_functions and not requested_forms)
            else "affected"
        ),
        "functions": requested_functions,
        "forms": requested_forms,
        "contractDiff": auto_diff,
    }
    if not force_all and requested_functions:
        for case in select_cases_by_changed_functions(corpus, requested_functions):
            selected_by_id[str(case.get("caseId") or "")] = case
    if not force_all and requested_forms:
        for case in select_cases_by_changed_forms(corpus, requested_forms):
            selected_by_id[str(case.get("caseId") or "")] = case
    selected = (
        sorted(selected_by_id.values(), key=lambda case: str(case.get("caseId") or ""))
        if selected_by_id and not force_all
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
