#!/usr/bin/env python3
"""Validate sanitized Python delivery payloads against the source C# DTO graph."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

# This is an offline source/fixture gate.  Do not inherit GUI/provider settings
# from an earlier in-process config import and accidentally enter live authoring.
os.environ["INFINI_SKIP_CONFIG_FILE"] = "1"
os.environ["INFINI_USE_LLM"] = "0"
os.environ["INFINI_LLM_RUNTIME_AUTHORING"] = "1"
os.environ["INFINI_LLM_RUNTIME_PLAN_REQUIRED"] = "1"
os.environ["INFINI_LLM_RUNTIME_STRICT_VALIDATION"] = "1"
os.environ["INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK"] = "1"
os.environ["INFINI_BALANCE_MODE"] = "safety"

from infini_local.core import strict_json  # noqa: E402
from infini_local.qa.csharp_delivery_contract import (  # noqa: E402
    CSharpContractParseError,
    load_csharp_contract_graph,
)
from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES  # noqa: E402
from infini_local.qa.runtime_proof import build_gameplay_seam_report  # noqa: E402
from infini_local.storage.world_storage import sanitize_recipe_for_delivery  # noqa: E402


def _golden_payloads() -> Iterable[tuple[str, dict[str, Any], list[str]]]:
    for case in GOLDEN_RUNTIME_CASES:
        case_id = str(case.get("caseId") or "unknown")
        report = build_gameplay_seam_report(case)
        item_raw = report.get("item")
        item: dict[str, Any] = item_raw if isinstance(item_raw, dict) else {}
        setup_errors: list[str] = []
        if report.get("error"):
            setup_errors.append(f"gameplay seam failed: {report['error']}")
        yield f"golden:{case_id}", item, setup_errors


def _replay_payloads() -> Iterable[tuple[str, dict[str, Any], list[str]]]:
    fixture_root = ROOT / "LocalGenerator" / "tests" / "fixtures" / "combine_payload"
    for path in sorted(fixture_root.glob("*.json")):
        setup_errors: list[str] = []
        try:
            raw = strict_json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raw = {}
            setup_errors.append(f"fixture read failed: {exc!r}")
        payload: dict[str, Any] = raw if isinstance(raw, dict) else {}
        if not isinstance(raw, dict):
            setup_errors.append("fixture root must be an object")
        yield f"replay:{path.name}", payload, setup_errors


def build_report() -> dict[str, Any]:
    try:
        graph = load_csharp_contract_graph()
    except CSharpContractParseError as exc:
        return {
            "schema": "infini.csharp-delivery-contract.v1",
            "ok": False,
            "errors": [str(exc)],
            "payloads": [],
        }

    reachable = graph.reachable_summary()
    rows: list[dict[str, Any]] = []
    for case_id, raw_payload, setup_errors in [*_golden_payloads(), *_replay_payloads()]:
        errors = list(setup_errors)
        try:
            delivered = sanitize_recipe_for_delivery(raw_payload)
        except Exception as exc:  # release gate: preserve exact sanitizer failure evidence
            delivered = {}
            errors.append(f"sanitize_recipe_for_delivery failed: {exc!r}")
        if not errors:
            errors.extend(graph.validate(delivered))
        if not errors:
            try:
                strict_json.dumps(delivered, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError, OverflowError) as exc:
                errors.append(f"strict JSON serialization failed: {exc!r}")
        rows.append({
            "caseId": case_id,
            "ok": not errors,
            "topLevelFieldCount": len(delivered),
            "errors": errors,
        })

    graph_errors = list(reachable.get("unresolvedTypes") or [])
    errors = [*graph_errors]
    errors.extend(
        f"{row['caseId']}: {error}"
        for row in rows
        for error in row["errors"]
    )
    return {
        "schema": "infini.csharp-delivery-contract.v1",
        "ok": not errors,
        "rootType": "GeneratedItemData",
        "sourceFileCount": len(graph.source_paths),
        "parsedClassCount": len(graph.classes),
        "reachable": reachable,
        "payloadCount": len(rows),
        "payloads": rows,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    report = build_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    if not args.quiet:
        print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
