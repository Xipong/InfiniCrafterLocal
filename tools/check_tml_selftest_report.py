#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED = {
    "dust-zero-remains-disabled",
    "sentry-shot-not-root",
    "charge-shot-not-holdout",
    "strict-generated-item-json",
    "strict-vfx-json",
}


def validate(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": "infini.tml-runtime-selftest-check.v1", "ok": False, "path": str(path), "errors": [repr(exc)]}
    if payload.get("schema") != "infini.tml-runtime-selftest.v1":
        errors.append(f"unexpected schema {payload.get('schema')!r}")
    rows = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    by_id = {str(row.get("id")): row for row in rows if isinstance(row, dict)}
    missing = sorted(REQUIRED - set(by_id))
    if missing:
        errors.append("missing checks: " + ", ".join(missing))
    failed = sorted(check_id for check_id, row in by_id.items() if not bool(row.get("ok")))
    if failed:
        errors.append("failed checks: " + ", ".join(failed))
    if payload.get("ok") is not True:
        errors.append("runtime report ok is not true")
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
