#!/usr/bin/env python3
"""Compare deterministic gameplay semantics with the frozen v20 authorship baseline.

The canonicalizer removes diagnostics and the retired Python-only tool-light aliases.
The v20 baseline freezes the post-audit rule that only explicitly compiled gameplay
semantics survive; no balance, damage, timing, family, child-budget, or executor
field is ignored.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

# The semantic baseline is an offline deterministic contract.  Live GUI/provider
# settings must not alter the result merely because another test imported config.
os.environ["INFINI_USE_LLM"] = "0"
os.environ["INFINI_LLM_RUNTIME_AUTHORING"] = "1"
os.environ["INFINI_LLM_RUNTIME_PLAN_REQUIRED"] = "1"
os.environ["INFINI_LLM_RUNTIME_STRICT_VALIDATION"] = "1"
os.environ["INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK"] = "1"
os.environ["INFINI_BALANCE_MODE"] = "safety"

from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES  # noqa: E402
from infini_local.qa.runtime_proof import build_gameplay_seam_report  # noqa: E402

DEFAULT_BASELINE = ROOT / "contracts" / "golden_runtime_semantics_v20.json"


def canonical_item(item: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(item)
    out.pop("debug", None)
    raw_attack = out.get("attack")
    attack: dict[str, Any] = raw_attack if isinstance(raw_attack, dict) else {}
    attack.pop("runtimeAuthoringProvenance", None)
    attack.pop("genome", None)
    attack.pop("patternSource", None)
    # pullStrength=0 is the neutral default added in v0.4.49; it does not change
    # any frozen v17 case. Non-zero authored pull remains visible to this gate.
    if attack.get("pullStrength") in (0, 0.0, None):
        attack.pop("pullStrength", None)
    if attack.get("pullMode") in ("", "none", None):
        attack.pop("pullMode", None)
    raw_gameplay = out.get("gameplay")
    gameplay: dict[str, Any] = raw_gameplay if isinstance(raw_gameplay, dict) else {}
    # v17 authored tool light into fields absent from the C# Gameplay DTO.  v18
    # routes the same values to the existing held-item executor contract.
    if "runtimeLightStrength" in gameplay and "holdLightStrength" not in gameplay:
        gameplay["holdLightStrength"] = gameplay.pop("runtimeLightStrength")
    if "runtimeLightColorName" in gameplay and "holdLightColorName" not in gameplay:
        gameplay["holdLightColorName"] = gameplay.pop("runtimeLightColorName")
    return out


def build_current() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for case in GOLDEN_RUNTIME_CASES:
        report = build_gameplay_seam_report(case)
        case_id = str(case["caseId"])
        if report.get("error") or not report.get("ok"):
            rows[case_id] = {"error": report.get("error"), "mismatches": report.get("mismatches")}
        else:
            rows[case_id] = canonical_item(report.get("item") or {})
    return rows


def _diff(path: str, expected: Any, actual: Any, out: list[dict[str, Any]]) -> None:
    if type(expected) is not type(actual):
        out.append({"path": path, "expected": expected, "actual": actual})
        return
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}" if path else key
            if key not in expected or key not in actual:
                out.append({"path": child, "expected": expected.get(key, "<missing>"), "actual": actual.get(key, "<missing>")})
            else:
                _diff(child, expected[key], actual[key], out)
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            out.append({"path": path + ".length", "expected": len(expected), "actual": len(actual)})
        for index, (left, right) in enumerate(zip(expected, actual)):
            _diff(f"{path}[{index}]", left, right, out)
    elif expected != actual:
        out.append({"path": path, "expected": expected, "actual": actual})


def build_report(baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = build_current()
    differences: list[dict[str, Any]] = []
    _diff("", baseline.get("cases", {}), current, differences)
    return {
        "schema": "infini.semantic-runtime-diff.v1",
        "baseline": str(baseline_path.relative_to(ROOT) if baseline_path.is_relative_to(ROOT) else baseline_path),
        "caseCount": len(current),
        "ok": not differences,
        "differences": differences[:200],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-current", type=Path)
    args = parser.parse_args()
    if args.write_current:
        payload = {"schema": "infini.golden-runtime-semantics.v1", "cases": build_current()}
        args.write_current.parent.mkdir(parents=True, exist_ok=True)
        args.write_current.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(args.write_current)
        return 0
    report = build_report(args.baseline)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
