#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_CHECKS = frozenset({
    "pytest",
    "compileall",
    "schema_check",
    "targeted_repair",
    "terraria_standardization",
    "config_registry",
    "contract_parity",
    "delivery_contract",
    "mutation_gate",
    "semantic_runtime_diff",
    "runtime_impact",
    "csharp_contracts",
    "project_hygiene",
    "planner_prompt",
    "ruff",
    "pyright",
    "tml_build",
    "tml_runtime_selftest",
})


def _tail(text: str, limit: int = 1800) -> str:
    clean = text.strip()
    return clean if len(clean) <= limit else "..." + clean[-limit:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-build", action="store_true")
    parser.add_argument("--require-runtime-selftest", action="store_true")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    for line in args.status_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, status, code, duration, log = line.split("\t", 4)
        log_path = ROOT / log if log else None
        output = log_path.read_text(encoding="utf-8", errors="ignore") if log_path and log_path.exists() else ""
        checks.append({
            "name": name,
            "status": status,
            "returnCode": None if code == "" else int(code),
            "durationSeconds": float(duration),
            "log": log,
            "summary": _tail(output),
        })

    names = [str(row["name"]) for row in checks]
    seen: set[str] = set()
    duplicate_checks: list[str] = []
    for name in names:
        if name in seen and name not in duplicate_checks:
            duplicate_checks.append(name)
        seen.add(name)
    duplicate_checks.sort()
    missing_checks = sorted(REQUIRED_CHECKS - seen)
    failed = [row["name"] for row in checks if row["status"] == "failed"]
    optional_unavailable = {
        "tml_build": not args.require_build,
        "tml_runtime_selftest": not args.require_runtime_selftest,
    }
    unavailable_required = [
        row["name"] for row in checks
        if row["status"] == "unavailable" and not optional_unavailable.get(row["name"], False)
    ]
    build = next((row for row in checks if row["name"] == "tml_build"), None)
    runtime_selftest = next((row for row in checks if row["name"] == "tml_runtime_selftest"), None)
    report = {
        "schema": "infini.release-validation.v1",
        "ok": not failed and not unavailable_required and not missing_checks and not duplicate_checks,
        "releaseReady": not failed and not unavailable_required and not missing_checks and not duplicate_checks and bool(
            build and build["status"] == "passed" and runtime_selftest and runtime_selftest["status"] == "passed"
        ),
        "failed": failed,
        "unavailableRequired": unavailable_required,
        "missingChecks": missing_checks,
        "duplicateChecks": duplicate_checks,
        "checks": checks,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
