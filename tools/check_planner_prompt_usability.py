#!/usr/bin/env python3
"""Offline planner-prompt usability and catalog-integrity check.

This does not call an LLM.  It verifies that the real author-plan payload stays
short enough for cheap/free API calls while preserving every executable function,
parameter range/enum, and safety note that the runtime compiler accepts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.web import server  # noqa: E402
from infini_local.core.runtime_authoring import (  # noqa: E402
    ENGINE_FN_CATALOG_V2,
    SAFE_SUMMON_FAMILIES,
)


@contextmanager
def _patched_env(name: str, value: str | None) -> Iterator[None]:
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def _sample_parent_cards() -> tuple[dict, dict, dict, dict]:
    a = {
        "name": "Wooden Sword",
        "type": 24,
        "damage": 7,
        "useTime": 25,
        "useAnimation": 25,
        "knockBack": 5,
        "value": 100,
    }
    b = {
        "name": "Torch",
        "type": 8,
        "createTile": 4,
        "value": 50,
    }
    return a, b, {}, {}


def _payload(style_env: str | None = None) -> dict:
    a, b, ca, cb = _sample_parent_cards()
    with _patched_env("INFINI_LLM_ENGINE_CONTRACT_STYLE", style_env):
        return server.build_llm_author_payload(a, b, ca, cb, "planner_smoke")


def _section_sizes(payload: dict) -> dict[str, int]:
    return {k: len(json.dumps(v, ensure_ascii=False, separators=(",", ":"))) for k, v in payload.items()}


def _contract_section_sizes(contract: dict) -> dict[str, int]:
    return {k: len(json.dumps(v, ensure_ascii=False, separators=(",", ":"))) for k, v in contract.items()}


def _check_catalog_losslessness(functions: dict) -> list[str]:
    problems: list[str] = []
    expected = set(ENGINE_FN_CATALOG_V2)
    actual = set(functions)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        problems.append("missing engine functions: " + ", ".join(missing))
    if extra:
        problems.append("planner exposes unknown functions: " + ", ".join(extra))
    for fn, spec in ENGINE_FN_CATALOG_V2.items():
        card = functions.get(fn)
        if not isinstance(card, dict):
            continue
        if str(card.get("does") or "") != str(spec.get("meaning") or ""):
            problems.append(f"catalog meaning changed/lost for {fn}")
        params = card.get("params") if isinstance(card.get("params"), dict) else {}
        expected_params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
        if set(params) != set(expected_params):
            problems.append(f"catalog params changed for {fn}: expected {sorted(expected_params)}, got {sorted(params)}")
            continue
        for key, value in expected_params.items():
            if str(params.get(key) or "") != str(value or ""):
                problems.append(f"catalog param text changed for {fn}.{key}")
    return problems


def _check_catalog_metadata(functions: dict) -> list[str]:
    problems: list[str] = []
    summon_family = str(functions.get("summon_combat_entity", {}).get("params", {}).get("family", ""))
    for family in sorted(SAFE_SUMMON_FAMILIES):
        if family not in summon_family:
            problems.append(f"safe summon family hidden from planner: {family}")
    if "boss/NPC/mob" not in str(functions.get("summon_combat_entity", {}).get("safety", "")):
        problems.append("summon safety note missing from function card")
    for fn in ("state_meter", "triggered_action"):
        status = str(functions.get(fn, {}).get("runtimeStatus", ""))
        if "preserved intent" not in status:
            problems.append(f"{fn} is not marked as intent-only")
    return problems


def run(limit_chars: int) -> dict:
    payload = _payload(None)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    contract = payload.get("engineRuntimeContract") if isinstance(payload.get("engineRuntimeContract"), dict) else {}
    functions = contract.get("availableFunctions") if isinstance(contract.get("availableFunctions"), dict) else {}
    problems: list[str] = []
    if len(text) > limit_chars:
        problems.append(f"planner payload too large: {len(text)} > {limit_chars}")
    if contract.get("contractStyle") != "sharp":
        problems.append(f"planner contract style must be sharp, got {contract.get('contractStyle')!r}")
    problems.extend(_check_catalog_losslessness(functions))
    problems.extend(_check_catalog_metadata(functions))
    if "runtimePlan" not in payload.get("requiredJsonShape", {}):
        problems.append("requiredJsonShape.runtimePlan missing")
    if "summon_boss" not in text or "hard-rejected" not in text:
        problems.append("boss/NPC/mob safety rule not visible in prompt")
    # Environment values used by old builds must not starve or bloat the planner.
    for style in ("compact", "tiny", "minimal", "full", "verbose", "debug"):
        alt = _payload(style)
        alt_contract = alt.get("engineRuntimeContract") if isinstance(alt.get("engineRuntimeContract"), dict) else {}
        if alt_contract.get("contractStyle") != "sharp":
            problems.append(f"env style {style!r} changed planner style to {alt_contract.get('contractStyle')!r}")
        alt_functions = alt_contract.get("availableFunctions") if isinstance(alt_contract.get("availableFunctions"), dict) else {}
        if set(alt_functions) != set(ENGINE_FN_CATALOG_V2):
            problems.append(f"env style {style!r} changed function set")
    return {
        "ok": not problems,
        "limitChars": limit_chars,
        "report": {
            "ok": not problems,
            "chars": len(text),
            "approxTokens": len(text) // 4,
            "contractStyle": contract.get("contractStyle"),
            "functionCount": len(functions),
            "hasRequiredShape": "requiredJsonShape" in payload,
            "hasRuntimePlanShape": "runtimePlan" in payload.get("requiredJsonShape", {}),
            "hasNoBossRule": "summon_boss" in text and "hard-rejected" in text,
            "note": "Prompt-only readiness check; does not call the LLM.",
        },
        "sectionSizes": _section_sizes(payload),
        "contractSectionSizes": _contract_section_sizes(contract),
        "functionCardSizes": {fn: len(json.dumps({fn: card}, ensure_ascii=False, separators=(",", ":"))) for fn, card in functions.items()},
        "missingFunctions": sorted(set(ENGINE_FN_CATALOG_V2) - set(functions)),
        "extraFunctions": sorted(set(functions) - set(ENGINE_FN_CATALOG_V2)),
        "problems": problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-chars", type=int, default=23000)
    args = ap.parse_args()
    result = run(args.limit_chars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
