from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring import (
    all_calls,
    compile_runtime_plan_to_genome_patch,
    runtime_plan,
    runtime_plan_provenance_report,
    runtime_plan_quality_report,
    runtime_plan_validation_report,
)
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.item_power_knowledge import apply_item_knowledge
from infini_local.pipelines.pipeline_support import canonicalize


def _safe_case_id(value: object) -> str:
    raw = str(value or "case").strip().lower()
    return re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("_") or "case"


def _nested_has(data: object, path: str) -> bool:
    cur: object = data
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return False
        cur = cur[part]
    return True


def _nested_get(data: object, path: str) -> Any:
    cur: object = data
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _compare_nested(container: object, expected: Mapping[str, Any], prefix: str, mismatches: list[str]) -> None:
    for key, expected_value in expected.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if not isinstance(container, Mapping) or key not in container:
            mismatches.append(f"missing nested key {path}")
            continue
        actual = container[key]
        if isinstance(expected_value, Mapping):
            _compare_nested(actual, expected_value, path, mismatches)
        elif actual != expected_value:
            mismatches.append(f"{path} expected {expected_value!r}, got {actual!r}")


def _authored_stats_from_plan(data: dict[str, Any]) -> dict[str, Any]:
    """Surface set_item_stats params without requiring them to land in genome patch."""
    stats: dict[str, Any] = {}
    for call in all_calls(runtime_plan(data), "set_item_stats"):
        params = call.get("params") if isinstance(call.get("params"), dict) else call
        if not isinstance(params, Mapping):
            continue
        for key, value in params.items():
            if str(key).startswith("_") or value in (None, "", [], {}):
                continue
            stats[str(key)] = value
    return stats


def _mismatches_for_expect(report: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    raw_patch = report.get("patch")
    patch: Mapping[str, Any] = raw_patch if isinstance(raw_patch, Mapping) else {}
    authored_stats = report.get("authoredStats") if isinstance(report.get("authoredStats"), Mapping) else {}
    functions = set(report.get("functions") or [])
    mismatches: list[str] = []

    for fn in expect.get("requiredFunctions") or []:
        if fn not in functions:
            mismatches.append(f"missing function {fn!r}")

    for key, expected in (expect.get("patchEquals") or {}).items():
        actual = _nested_get(patch, key)
        if actual != expected:
            mismatches.append(f"patch[{key!r}] expected {expected!r}, got {actual!r}")

    for key, expected in (expect.get("authoredStatsEquals") or {}).items():
        actual = _nested_get(authored_stats, key)
        if actual != expected:
            mismatches.append(f"authoredStats[{key!r}] expected {expected!r}, got {actual!r}")

    nested = expect.get("patchNestedEquals") or {}
    if isinstance(nested, dict):
        _compare_nested(patch, nested, "patch", mismatches)

    for key in expect.get("patchHasKeys") or []:
        if not _nested_has(patch, key):
            mismatches.append(f"missing patch key {key!r}")

    for key in expect.get("patchNotHasKeys") or []:
        if _nested_has(patch, key):
            mismatches.append(f"unexpected patch key {key!r}={_nested_get(patch, key)!r}")

    raw_rejected = patch.get("rejectedEngineCalls")
    rejected = raw_rejected if isinstance(raw_rejected, list) else []
    min_rejected = expect.get("minRejectedCalls")
    if min_rejected is not None and len(rejected) < int(min_rejected):
        mismatches.append(f"expected at least {min_rejected} rejected calls, got {len(rejected)}")

    rejected_reasons = "\n".join(str(row.get("reason", "")) for row in rejected if isinstance(row, dict))
    for needle in expect.get("rejectedReasonsContain") or []:
        if str(needle) not in rejected_reasons:
            mismatches.append(f"missing rejected reason containing {needle!r}")

    return mismatches


def _mismatches_for_gameplay_expect(report: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    if report.get("error"):
        mismatches.append(f"gameplay seam error: {report['error']}")
        return mismatches

    item = report.get("item") if isinstance(report.get("item"), Mapping) else {}
    attack = item.get("attack") if isinstance(item.get("attack"), Mapping) else {}
    gameplay = item.get("gameplay") if isinstance(item.get("gameplay"), Mapping) else {}
    accessory = item.get("accessory") if isinstance(item.get("accessory"), Mapping) else {}
    armor = item.get("armor") if isinstance(item.get("armor"), Mapping) else {}

    if "categoryEquals" in expect and item.get("category") != expect.get("categoryEquals"):
        mismatches.append(f"category expected {expect.get('categoryEquals')!r}, got {item.get('category')!r}")

    for key, expected in (expect.get("attackEquals") or {}).items():
        actual = attack.get(key)
        if actual != expected:
            mismatches.append(f"attack[{key!r}] expected {expected!r}, got {actual!r}")

    for key, expected in (expect.get("gameplayEquals") or {}).items():
        actual = gameplay.get(key)
        if actual != expected:
            mismatches.append(f"gameplay[{key!r}] expected {expected!r}, got {actual!r}")

    for key, expected in (expect.get("accessoryEquals") or {}).items():
        actual = accessory.get(key)
        if actual != expected:
            mismatches.append(f"accessory[{key!r}] expected {expected!r}, got {actual!r}")

    for key, expected in (expect.get("armorEquals") or {}).items():
        actual = armor.get(key)
        if actual != expected:
            mismatches.append(f"armor[{key!r}] expected {expected!r}, got {actual!r}")

    for key in expect.get("gameplayNotHasKeys") or []:
        if key in gameplay:
            mismatches.append(f"unexpected gameplay key {key!r}={gameplay.get(key)!r}")

    return mismatches


def _default_parents() -> tuple[dict[str, Any], dict[str, Any]]:
    a = {
        "name": "Wooden Sword",
        "internalName": "WoodenSword",
        "sourceMod": "Terraria",
        "damage": 10,
        "damageClass": "melee",
        "useStyle": 1,
        "useTime": 20,
        "useAnimation": 20,
        "rare": 1,
        "value": 100,
        "maxStack": 1,
        "shoot": 0,
        "shootSpeed": 0,
    }
    b = dict(a)
    b.update({"name": "Iron Broadsword", "internalName": "IronBroadsword", "damage": 12})
    return a, b


def build_runtime_proof_report(case: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic runtime proof report for one authored golden case."""
    data = deepcopy(case.get("input") or {})
    patch = compile_runtime_plan_to_genome_patch(data)
    validation = runtime_plan_validation_report(data)
    quality = runtime_plan_quality_report(data)
    provenance = runtime_plan_provenance_report(data, patch)
    authored_stats = _authored_stats_from_plan(data)
    functions = list((quality.get("functions") or []) if isinstance(quality, dict) else [])
    report: dict[str, Any] = {
        "caseId": case.get("caseId"),
        "description": case.get("description", ""),
        "input": data,
        "functions": functions,
        "authoredStats": authored_stats,
        "patch": patch,
        "validation": validation,
        "quality": quality,
        "provenance": provenance,
        "expect": deepcopy(case.get("expect") or {}),
    }
    mismatches = _mismatches_for_expect(report, report["expect"])
    report["mismatches"] = mismatches
    report["ok"] = not mismatches
    return report


def build_gameplay_seam_report(case: dict[str, Any]) -> dict[str, Any]:
    """Run authored runtimePlan through validate/repair + gameplay/attack attachment.

    This is the Python GeneratedItemData seam before visual/asset generation and
    before Terraria. No LLM, HTTP, or image backend.
    """
    plan = deepcopy(case.get("input") or {})
    plan.setdefault("name", str(case.get("caseId") or "golden"))
    plan.setdefault("debug", {})["planner"] = "llm"
    a, b = _default_parents()
    ca = canonicalize(a)
    cb = canonicalize(b)
    key = f"qa_runtime_proof_{_safe_case_id(case.get('caseId'))}"
    report: dict[str, Any] = {
        "caseId": case.get("caseId"),
        "description": case.get("description", ""),
        "expectGameplay": deepcopy(case.get("expectGameplay") or {}),
        "error": None,
        "item": None,
    }
    try:
        data = validate_and_repair(plan, a, b, ca, cb, key)
        data = apply_item_knowledge(data, a, b, ca, cb)
        data = attach_gameplay_and_attack(data, a, b, ca, cb)
        report["item"] = {
            "category": data.get("category"),
            "gameplay": data.get("gameplay") or {},
            "attack": data.get("attack") or {},
            "accessory": data.get("accessory") or {},
            "armor": data.get("armor") or {},
            "debug": {
                "toolMerge": (data.get("debug") or {}).get("toolMerge"),
                "finalCategory": (data.get("debug") or {}).get("finalCategory"),
            },
        }
    except Exception as exc:  # proof must surface seam crashes as failed reports
        report["error"] = f"{type(exc).__name__}: {exc}"
    mismatches = _mismatches_for_gameplay_expect(report, report["expectGameplay"])
    report["mismatches"] = mismatches
    report["ok"] = not mismatches
    return report


def assert_runtime_proof_report(report: dict[str, Any]) -> None:
    mismatches = report.get("mismatches") or []
    assert not mismatches, f"{report.get('caseId')}: " + "; ".join(str(m) for m in mismatches)
    assert report.get("ok") is True


def write_runtime_proof_artifacts(reports: list[dict[str, Any]], out_dir: Path | str) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for report in reports:
        path = out / f"{_safe_case_id(report.get('caseId'))}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


__all__ = [
    "assert_runtime_proof_report",
    "build_gameplay_seam_report",
    "build_runtime_proof_report",
    "write_runtime_proof_artifacts",
]
