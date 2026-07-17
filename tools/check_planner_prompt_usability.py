#!/usr/bin/env python3
"""Offline planner-prompt usability and catalog-integrity check.

This does not call an LLM.  It verifies that the real author-plan payload stays
short enough for cheap/free API calls while preserving every executable function,
parameter range/enum, and safety note that the runtime compiler accepts.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.pipelines.llm_authoring_pipeline import (  # noqa: E402
    build_initial_author_request,
    build_llm_author_payload,
    build_same_author_repair_request,
)
from infini_local.pipelines.llm_authoring_prompt import PLANNER_PROMPT_LIMIT_CHARS  # noqa: E402
from infini_local.pipelines.author_item_contract import author_item_provider_response_schema  # noqa: E402
from infini_local.pipelines.llm_transport import transport_footprint  # noqa: E402
from infini_local.core.runtime_authoring.schema import (  # noqa: E402
    ENGINE_FN_CATALOG_V2,
    PLANNER_HIDDEN_ENGINE_FUNCTIONS,
    TEMPORARY_HELPER_FAMILIES,
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
        return build_llm_author_payload(a, b, ca, cb, "planner_smoke")


def _sample_authored_item() -> dict[str, object]:
    return {
        "name": "Torchwood Edge",
        "category": "weapon",
        "concept": {
            "fantasy": "A wooden blade carrying a steady torch flame.",
            "mergeLogic": "The torch flame inhabits the wooden sword grain.",
            "coreMechanic": "A direct melee strike emits a short-lived flame projectile.",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "sourceRolePreservation": {"itemA": "Wooden Sword body", "itemB": "Torch flame"},
            "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 12}},
                {"callId": "shot", "fn": "shoot_projectile", "params": {"movement": "straight", "speed": 8}},
            ],
            "visualIntent": {
                "item": "one wooden blade with an embedded torch flame",
                "projectile": "one compact flame body",
                "impact": "small ember burst",
                "vfxIntent": "warm embers",
                "vfxAvoid": "no beam",
                "topology": "connected",
                "parts": ["wooden blade", "embedded flame"],
                "arrangement": "the flame sits inside the blade tip",
            },
        },
        "runtimeContract": {
            "primaryVerb": "swing and release flame",
            "controlStyle": "tap",
            "playerViewTimeline": [],
        },
    }


def _prompt_budgets() -> dict[str, dict[str, int | str]]:
    a, b, ca, cb = _sample_parent_cards()
    initial_req, _, _ = build_initial_author_request(a, b, ca, cb, "planner_smoke")
    explicit_schema_req = copy.deepcopy(initial_req)
    explicit_schema_req["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": "infini_author_item_v3",
            "strict": True,
            "schema": author_item_provider_response_schema(),
        },
    }
    repair_req, _, _, _, _ = build_same_author_repair_request(
        _sample_authored_item(),
        a,
        b,
        {
            "stage": "final_wire",
            "blockingClaims": [{
                "kind": "compiler_provenance_dropped",
                "callId": "shot",
                "authoredParam": "speed",
            }],
        },
    )
    return {
        "authorAutoJsonObject": transport_footprint(initial_req, "author_initial"),
        "explicitJsonSchemaOptIn": transport_footprint(explicit_schema_req, "author_initial"),
        "repairAutoJsonObject": transport_footprint(repair_req, "author_retry"),
    }


def _section_sizes(payload: dict) -> dict[str, int]:
    return {k: len(json.dumps(v, ensure_ascii=False, separators=(",", ":"))) for k, v in payload.items()}


def _contract_section_sizes(contract: dict) -> dict[str, int]:
    return {k: len(json.dumps(v, ensure_ascii=False, separators=(",", ":"))) for k, v in contract.items()}


def _check_catalog_losslessness(functions: dict) -> list[str]:
    problems: list[str] = []
    expected = set(ENGINE_FN_CATALOG_V2) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS)
    actual = set(functions)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        problems.append("missing engine functions: " + ", ".join(missing))
    if extra:
        problems.append("planner exposes unknown functions: " + ", ".join(extra))
    for fn, spec in ENGINE_FN_CATALOG_V2.items():
        if fn in PLANNER_HIDDEN_ENGINE_FUNCTIONS:
            continue
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
    helper_family = str(functions.get("spawn_temporary_helper_projectile", {}).get("params", {}).get("family", ""))
    for family in sorted(TEMPORARY_HELPER_FAMILIES):
        if family not in helper_family:
            problems.append(f"temporary helper family hidden from planner: {family}")
    if "boss/NPC/mob" not in str(functions.get("spawn_temporary_helper_projectile", {}).get("safety", "")):
        problems.append("temporary helper safety note missing from function card")
    for fn in sorted(PLANNER_HIDDEN_ENGINE_FUNCTIONS):
        if fn in functions:
            problems.append(f"preserved-only function leaked into planner: {fn}")
    return problems


def run(limit_chars: int) -> dict:
    payload = _payload(None)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    contract_candidate = payload.get("engineRuntimeContract")
    contract: dict[str, object] = contract_candidate if isinstance(contract_candidate, dict) else {}
    functions_candidate = contract.get("availableFunctions")
    functions: dict[str, object] = functions_candidate if isinstance(functions_candidate, dict) else {}
    problems: list[str] = []
    if len(text) > limit_chars:
        problems.append(f"planner payload too large: {len(text)} > {limit_chars}")
    if contract.get("contractStyle") != "sharp":
        problems.append(f"planner contract style must be sharp, got {contract.get('contractStyle')!r}")
    problems.extend(_check_catalog_losslessness(functions))
    problems.extend(_check_catalog_metadata(functions))
    prompt_budgets = _prompt_budgets()
    required_shape_candidate = payload.get("requiredJsonShape")
    required_shape = required_shape_candidate if isinstance(required_shape_candidate, dict) else {}
    if "runtimePlan" not in required_shape:
        problems.append("requiredJsonShape.runtimePlan missing")
    helper_card_candidate = functions.get("spawn_temporary_helper_projectile")
    helper_card: dict[str, object] = helper_card_candidate if isinstance(helper_card_candidate, dict) else {}
    helper_safety = str(helper_card.get("safety", "")).lower()
    has_no_world_entity_rule = all(token in helper_safety for token in ("boss", "npc", "mob", "enemy"))
    if not has_no_world_entity_rule:
        problems.append("temporary helper world-entity safety is incomplete")
    # Environment values used by old builds must not starve or bloat the planner.
    for style in ("compact", "tiny", "minimal", "full", "verbose", "debug"):
        alt = _payload(style)
        alt_contract = alt.get("engineRuntimeContract") if isinstance(alt.get("engineRuntimeContract"), dict) else {}
        if alt_contract.get("contractStyle") != "sharp":
            problems.append(f"env style {style!r} changed planner style to {alt_contract.get('contractStyle')!r}")
        alt_functions = alt_contract.get("availableFunctions") if isinstance(alt_contract.get("availableFunctions"), dict) else {}
        if set(alt_functions) != (set(ENGINE_FN_CATALOG_V2) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS)):
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
            "hasNoBossRule": has_no_world_entity_rule,
            "note": "Prompt-only readiness check; does not call the LLM.",
        },
        "sectionSizes": _section_sizes(payload),
        "promptBudgets": prompt_budgets,
        "parentCardChars": sum(
            len(json.dumps(payload.get(key), ensure_ascii=False, separators=(",", ":")))
            for key in ("itemA", "itemB")
        ),
        "engineFunctionCardChars": sum(
            len(json.dumps({fn: card}, ensure_ascii=False, separators=(",", ":")))
            for fn, card in functions.items()
        ),
        "contractSectionSizes": _contract_section_sizes(contract),
        "functionCardSizes": {fn: len(json.dumps({fn: card}, ensure_ascii=False, separators=(",", ":"))) for fn, card in functions.items()},
        "hiddenFunctions": sorted(PLANNER_HIDDEN_ENGINE_FUNCTIONS),
        "missingFunctions": sorted((set(ENGINE_FN_CATALOG_V2) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS)) - set(functions)),
        "extraFunctions": sorted(set(functions) - (set(ENGINE_FN_CATALOG_V2) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS))),
        "problems": problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-chars", type=int, default=PLANNER_PROMPT_LIMIT_CHARS)
    args = ap.parse_args()
    result = run(args.limit_chars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
