#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED = {
    "multi-entity-program-normalizes",
    "category-cannot-select-equipment-role",
    "duplicate-exclusive-input-rejected",
    "event-cycle-rejected",
    "old-runtime-api-rejected",
    "retired-shape-rejected",
    "strict-vfx-json",
}
EXPECTED_SCHEMA = "infini.tml-runtime-selftest.v2"
EXPECTED_RUNTIME_API = "infini.runtime-program.v5"


def validate(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": "infini.tml-runtime-selftest-check.v1", "ok": False, "path": str(path), "errors": [repr(exc)]}
    if payload.get("schema") != EXPECTED_SCHEMA:
        errors.append(f"unexpected schema {payload.get('schema')!r}")
    if payload.get("runtimeApi") != EXPECTED_RUNTIME_API:
        errors.append(f"unexpected runtimeApi {payload.get('runtimeApi')!r}")
    rows = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    ids = [str(row.get("id") or "") for row in rows if isinstance(row, dict)]
    duplicates = sorted({check_id for check_id in ids if check_id and ids.count(check_id) > 1})
    if duplicates:
        errors.append("duplicate checks: " + ", ".join(duplicates))
    by_id = {str(row.get("id") or ""): row for row in rows if isinstance(row, dict)}
    missing = sorted(REQUIRED - set(by_id))
    if missing:
        errors.append("missing checks: " + ", ".join(missing))
    failed = sorted(check_id for check_id, row in by_id.items() if check_id and row.get("ok") is not True)
    if failed:
        errors.append("failed checks: " + ", ".join(failed))
    if payload.get("ok") is not True:
        errors.append("runtime report ok is not true")
    failures = payload.get("failures")
    if not isinstance(failures, list) or failures:
        errors.append("runtime report failures must be an empty array")
    return {
        "schema": "infini.tml-runtime-selftest-check.v1",
        "ok": not errors,
        "path": str(path),
        "checkCount": len(rows),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    result = validate(args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
