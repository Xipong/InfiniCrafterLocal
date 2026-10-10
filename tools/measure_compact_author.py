#!/usr/bin/env python3
"""Reproduce canonical and strict-provider output sizes on explicit QA fixtures.

This emits data only: no network, model sampling, fixture rewriting or rollout.
The independent nullable encoder is intentionally confined to this QA command.
"""
from __future__ import annotations

from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.core.runtime_authoring.compact_api import compile_compact_author
from infini_local.core.runtime_authoring.compact_notation import compact_author_item_schema, encode_compact_author, project_compact_author
from infini_local.core.runtime_authoring.program_schema import author_item_response_schema, strict_schema_errors
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture


def _provider_fixture(value: Any, schema: dict[str, Any]) -> Any:
    for union in ("oneOf", "anyOf"):
        if union in schema:
            branches = [branch for branch in schema[union] if not strict_schema_errors(value, branch)]
            if len(branches) != 1:
                raise ValueError("QA value does not select exactly one schema branch")
            return _provider_fixture(value, branches[0])
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        if "if" in schema and not strict_schema_errors(value, schema["if"]):
            required.update(schema["then"]["required"])
        return {key: _provider_fixture(value[key], child) if key in value else None
                for key, child in schema["properties"].items() if key in value or key not in required}
    if isinstance(value, list):
        return [_provider_fixture(row, schema["items"]) for row in value]
    return deepcopy(value)


def _chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def measure() -> dict[str, Any]:
    rows = []
    canonical_schema, compact_schema = author_item_response_schema(), compact_author_item_schema()
    for fixture in NON_ARCHETYPAL_FIXTURES:
        canonical = build_runtime_fixture(fixture)
        checks = canonical["realization"]["selfEvaluation"]["planVsProgram"]["actionChecks"]
        # These fixtures explicitly pair row N with row N. No production prose matching.
        compact = encode_compact_author(canonical, planned_action_indices=list(range(len(checks))))
        assert project_compact_author(compact).canonical == canonical
        wire, compact_wire = compile_runtime_program(canonical), compile_compact_author(compact)
        assert all(wire[key] == compact_wire[key] for key in ("runtimeProgram", "gameplay", "accessory", "armor"))
        baseline, proposed = _chars(canonical), _chars(compact)
        strict_baseline = _chars(_provider_fixture(canonical, canonical_schema))
        strict_proposed = _chars(_provider_fixture(compact, compact_schema))
        rows.append({"fixture": fixture, "canonicalBeforeChars": baseline, "compactChars": proposed,
                     "savingChars": baseline - proposed,
                     "strictProviderBeforeChars": strict_baseline, "strictProviderCompactChars": strict_proposed,
                     "strictProviderSavingChars": strict_baseline - strict_proposed})
    tool = {"pickPower": 100, "axePowerTooltipPercent": 0, "hammerPower": 0, "miningSpeedScale": 1}
    resource = {"healLife": 100, "healMana": 0, "usesPotionRules": True}
    return {"schema": "infini.compact-author-output-measurements.v1", "unit": "Unicode characters in compact JSON; not tokens or billed usage",
            "scope": "D1-D6 combined, exact fixture values retained; no additive savings claims or live model quality estimate",
            "rows": rows,
            "newNeutralOmissionsCanonicalOnly": {
                "configure_tool_zero_axe_and_hammer": _chars(tool) - _chars({key: value for key, value in tool.items() if key not in {"axePowerTooltipPercent", "hammerPower"}}),
                "restore_resources_zero_mana": _chars(resource) - _chars({key: value for key, value in resource.items() if key != "healMana"}),
            },
            "liveLlmQuality": "notRun"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(measure(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if args.output is None:
            parser.error("--check requires --output")
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            print("[FAIL] compact Author measurement is stale")
            return 1
        print("[OK] compact Author measurements reproduce exactly")
    elif args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
