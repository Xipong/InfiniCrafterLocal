#!/usr/bin/env python3
"""Deterministic v5 fixture snapshot without preserving the retired weapon IR."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import (
    NON_ARCHETYPAL_FIXTURES,
    build_runtime_fixture,
)


def build_current() -> dict[str, dict[str, Any]]:
    current: dict[str, dict[str, Any]] = {}
    for name in NON_ARCHETYPAL_FIXTURES:
        compiled = compile_runtime_program(build_runtime_fixture(name))
        report = validate_runtime_wire(compiled)
        runtime = compiled["runtimeProgram"]
        encoded = json.dumps(
            runtime,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        current[name] = {
            "ok": report["ok"],
            "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "entityKinds": sorted({entity["kind"] for entity in runtime["entities"]}),
            "entityCount": len(runtime["entities"]),
            "bindingCount": len(runtime["bindings"]),
            "hasFamilyAuthority": any(
                key in encoded for key in ("runtimeFamily", "weaponFamily")
            ),
        }
    return current


def build_report() -> dict[str, Any]:
    cases = build_current()
    return {
        "schema": "infini.low-level-semantic-proof.v1",
        "ok": all(
            bool(row["ok"]) and not bool(row["hasFamilyAuthority"])
            for row in cases.values()
        ),
        "baselinePolicy": (
            "v5 fixtures prove explicit entities/inputs/events; "
            "old weapon-IR zero-diff is intentionally retired"
        ),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--write-current", type=Path)
    args = parser.parse_args()
    report = build_report()
    target = args.out or args.write_current
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
