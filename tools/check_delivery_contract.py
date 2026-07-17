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

# This is an offline source/fixture gate. Import its runtime dependencies under a
# finite environment snapshot, then restore the caller exactly; tests import this
# module in-process and must not inherit gate policy.
_GATE_ENV = {
    "INFINI_SKIP_CONFIG_FILE": "1",
    "INFINI_USE_LLM": "0",
    "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK": "1",
    "INFINI_BALANCE_MODE": "safety",
}
_PREVIOUS_GATE_ENV = {key: os.environ.get(key) for key in _GATE_ENV}
os.environ.update(_GATE_ENV)
try:
    from infini_local.core import strict_json  # noqa: E402
    from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION  # noqa: E402
    from infini_local.qa.csharp_delivery_contract import (  # noqa: E402
        CSharpContractParseError,
        load_csharp_contract_graph,
    )
    from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES  # noqa: E402
    from infini_local.qa.runtime_proof import build_gameplay_seam_report  # noqa: E402
    from infini_local.storage.world_storage import sanitize_recipe_for_delivery  # noqa: E402
finally:
    for _key, _value in _PREVIOUS_GATE_ENV.items():
        if _value is None:
            os.environ.pop(_key, None)
        else:
            os.environ[_key] = _value


# This replay intentionally proves that sanitization preserves an old payload;
# it is negative delivery evidence, not a payload the current runtime can load.
EXPECTED_LEGACY_REPLAY_APIS = {"object_debug_payload.json": "v0.4.23"}


def _golden_payloads() -> Iterable[tuple[str, dict[str, Any], list[str]]]:
    for case in GOLDEN_RUNTIME_CASES:
        case_id = str(case.get("caseId") or "unknown")
        report = build_gameplay_seam_report(case)
        item_raw = report.get("item")
        item: dict[str, Any] = item_raw if isinstance(item_raw, dict) else {}
        setup_errors: list[str] = []
        if report.get("error"):
            setup_errors.append(f"gameplay seam failed: {report['error']}")
        # runtime_proof intentionally returns only the executable DTO seam; the
        # production final-normalize stage adds this top-level transport version.
        item = dict(item)
        item["runtimeApiVersion"] = ENGINE_RUNTIME_API_VERSION
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
        runtime_api = str(delivered.get("runtimeApiVersion") or "").strip()
        fixture_name = case_id.removeprefix("replay:") if case_id.startswith("replay:") else ""
        expected_legacy_api = EXPECTED_LEGACY_REPLAY_APIS.get(fixture_name)
        runtime_api_compatible = runtime_api == ENGINE_RUNTIME_API_VERSION
        if expected_legacy_api is not None:
            if runtime_api != expected_legacy_api:
                errors.append(
                    f"negative replay expected runtimeApiVersion={expected_legacy_api}, got {runtime_api or '<missing>'}"
                )
            if runtime_api_compatible:
                errors.append("negative replay no longer proves current-runtime rejection")
        elif not runtime_api_compatible:
            errors.append(
                f"runtimeApiVersion={runtime_api or '<missing>'} is not deliverable to {ENGINE_RUNTIME_API_VERSION}"
            )
        rows.append({
            "caseId": case_id,
            "ok": not errors,
            "deliveryExpected": expected_legacy_api is None,
            "runtimeApiVersion": runtime_api,
            "runtimeApiCompatible": runtime_api_compatible,
            "expectedRuntimeApiRejection": expected_legacy_api is not None,
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
