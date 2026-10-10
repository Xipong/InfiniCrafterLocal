#!/usr/bin/env python3
"""Compare canonical Author output with frozen pre-rework sizes and gameplay hashes.

The baseline is data captured before changing the canonical owners. This tool
contains no old Author schema, encoder, importer or alternate compilation API.
"""
from __future__ import annotations

from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import author_item_response_schema, strict_schema_errors
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

BASELINE = ROOT / "LocalGenerator/tests/fixtures/author_notation_baseline.json"


def wire_digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def provider_fixture(value: Any, schema: dict[str, Any]) -> Any:
    """Independent QA encoder of the real strict-provider nullable envelope."""
    for union in ("oneOf", "anyOf"):
        if union in schema:
            branches = [branch for branch in schema[union] if not strict_schema_errors(value, branch)]
            if len(branches) != 1:
                raise ValueError("QA value must select exactly one canonical schema branch")
            return provider_fixture(value, branches[0])
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        if "if" in schema and not strict_schema_errors(value, schema["if"]):
            required.update(schema["then"]["required"])
        return {key: provider_fixture(value[key], child) if key in value else None
                for key, child in schema["properties"].items() if key in value or key not in required}
    if isinstance(value, list):
        return [provider_fixture(row, schema["items"]) for row in value]
    return deepcopy(value)


def chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def measure() -> dict[str, Any]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    schema = author_item_response_schema()
    rows = []
    for name, reference in baseline["compositions"].items():
        document = build_runtime_fixture(name)
        compiled = compile_runtime_program(document)
        for key, expected in reference["wireSha256"].items():
            if wire_digest(compiled[key]) != expected:
                raise ValueError(f"{name}: {key} differs from the frozen gameplay projection")
        proposed = chars(document)
        strict_proposed = chars(provider_fixture(document, schema))
        rows.append({
            "fixture": name,
            "beforeChars": reference["authoredChars"], "afterChars": proposed,
            "savingChars": reference["authoredChars"] - proposed,
            "strictProviderBeforeChars": reference["strictProviderChars"],
            "strictProviderAfterChars": strict_proposed,
            "strictProviderSavingChars": reference["strictProviderChars"] - strict_proposed,
            "gameplayWireMatchesBaseline": True,
        })
    return {
        "schema": "infini.canonical-author-output-measurements.v1",
        "unit": "Unicode characters in compact JSON; not tokens, latency or billed usage",
        "sourceAuthorHead": baseline["sourceAuthorHead"], "foundationHead": baseline["foundationHead"],
        "scope": "native canonical Author v5; flat calls, flat binding variants, exact item-only targets, zero-argument calls and explicit report indices",
        "rows": rows,
        "liveLlmQuality": "notRun",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "contracts/author_notation_measurements.generated.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(measure(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            print("[FAIL] canonical Author measurements are stale")
            return 1
        print("[OK] canonical Author measurements and frozen gameplay hashes reproduce")
    else:
        args.output.write_text(rendered, encoding="utf-8")
        print("[OK] canonical Author measurements written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
