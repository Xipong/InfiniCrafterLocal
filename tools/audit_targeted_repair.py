#!/usr/bin/env python3
"""Audit blocker-scoped conditional Repair against representative v5 failures."""
from __future__ import annotations

import argparse
import ast
import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    REPAIR_ERROR_POLICY,
    VALIDATION_ERROR_CODES,
    apply_repair_patch,
    build_runtime_repair_scope,
    filter_repair_patch_scope,
    validate_runtime_program,
)
from infini_local.pipelines.llm_authoring_pipeline import (
    build_gameplay_repair_dossier,
    build_initial_author_request,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

SCHEMA = "infini.targeted-repair-audit.v1"

PARENT_A = {"name": "Workbench"}
PARENT_B = {"name": "Sword"}
CANONICAL_A = {"facts": ["literal workbench body"]}
CANONICAL_B = {"facts": ["metal blade"]}


def _compact_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _case(name: str, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    current = build_runtime_fixture("workbench_blade")
    mutate(current)
    validation = validate_runtime_program(current)
    if validation.get("ok"):
        raise RuntimeError(f"audit case {name!r} did not create a validation failure")
    dossier = build_gameplay_repair_dossier(
        current,
        PARENT_A,
        PARENT_B,
        CANONICAL_A,
        CANONICAL_B,
        failure_report={"stage": "runtime_program_validation", "errors": validation["errors"]},
    )
    plan = dossier["blockerPlan"]
    broken = dossier["brokenFragments"]
    dependency = dossier["validDependencyFragments"]
    card_names = {
        str(card.get("fn") or "")
        for key in ("blockerCapabilities", "supportingCapabilities", "existingBrokenCapabilityCards")
        for card in dossier.get(key) or []
    }
    subset = set(str(value) for value in dossier["repairScope"].get("capabilitySubset") or [])
    return {
        "name": name,
        "dossierChars": _compact_chars(dossier),
        "errorCodes": [str(row.get("code") or "") for row in validation["errors"]],
        "errorPaths": [str(row.get("path") or "") for row in validation["errors"]],
        "directCapabilities": list(plan.get("directCapabilityNames") or []),
        "supportingCapabilities": list(plan.get("supportingCapabilityNames") or []),
        "existingBrokenCapabilities": list(plan.get("existingBrokenCapabilityNames") or []),
        "capabilitySubsetCount": len(subset),
        "capabilityCardsMatchSubset": card_names == subset,
        "brokenCounts": {key: len(value) for key, value in broken.items()},
        "readOnlyDependencyCounts": {key: len(value) for key, value in dependency.items()},
        "nonRepairableCount": len(dossier["repairScope"].get("nonRepairableErrors") or []),
    }


def _missing_use_style(data: dict[str, Any]) -> None:
    row = next(row for row in data["runtimeProgram"]["calls"] if row["id"] == "item_use")
    row["params"].pop("useStyle", None)


def _missing_item_use(data: dict[str, Any]) -> None:
    data["runtimeProgram"]["calls"] = [
        row for row in data["runtimeProgram"]["calls"] if row["id"] != "item_use"
    ]


def _missing_movement(data: dict[str, Any]) -> None:
    data["runtimeProgram"]["calls"] = [
        row for row in data["runtimeProgram"]["calls"] if row["id"] != "workbench_blade_motion"
    ]


def _channel_dependency(data: dict[str, Any]) -> None:
    row = next(row for row in data["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_motion")
    row["fn"] = "channel_beam"
    row["params"] = {"rangeTiles": 12.0, "widthPx": 12.0, "warmupTicks": 6}




def _empty_patch() -> dict[str, Any]:
    return {
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "bindingsUpsert": [], "bindingIdsDelete": [], "bindingIndicesDelete": [],
        "callsUpsert": [], "callIdsDelete": [], "callIndicesDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "claimIndicesDelete": [],
        "metadataPatch": {}, "note": "audit frozen merge",
    }


def _frozen_merge_probe() -> dict[str, Any]:
    current = build_runtime_fixture("workbench_blade")
    item_use = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_use")
    item_stats = next(row for row in current["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    old_damage = item_stats["params"]["damage"]
    old_hand_pose = item_use["params"]["handPose"]
    item_use["params"].pop("useStyle", None)
    item_use["params"].pop("releaseTiming", None)  # optional, deliberately not reported as required
    validation = validate_runtime_program(current)
    scope = build_runtime_repair_scope(current, validation["errors"])

    fixed = copy.deepcopy(item_use)
    fixed["params"]["useStyle"] = "shoot"
    fixed["params"]["releaseTiming"] = "on_release"
    fixed["params"]["handPose"] = "two_handed"
    rewrite = copy.deepcopy(item_stats)
    rewrite["params"]["damage"] = 999
    patch = _empty_patch()
    patch["callsUpsert"] = [fixed, rewrite]
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    repaired = apply_repair_patch(current, filtered)
    repaired_use = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_use")
    repaired_stats = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "item_stats")
    return {
        "fullValidationOk": bool(validate_runtime_program(repaired).get("ok")),
        "exactRequiredFixApplied": repaired_use["params"].get("useStyle") == "shoot",
        "frozenExistingValuePreserved": repaired_use["params"].get("handPose") == old_hand_pose,
        "independentDamagePreserved": repaired_stats["params"].get("damage") == old_damage,
        "optionalUnreportedAdditionIgnored": "releaseTiming" not in repaired_use["params"],
        "ignoredChangeCount": len(audit.get("ignoredChanges") or []),
        "acceptedPaths": list(audit.get("acceptedPaths") or []),
        "ok": bool(
            validate_runtime_program(repaired).get("ok")
            and repaired_use["params"].get("useStyle") == "shoot"
            and repaired_use["params"].get("handPose") == old_hand_pose
            and repaired_stats["params"].get("damage") == old_damage
            and "releaseTiming" not in repaired_use["params"]
        ),
    }


def _emitted_validator_codes() -> set[str]:
    path = ROOT / "LocalGenerator/infini_local/core/runtime_authoring/validator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "ValidationIssue":
            continue
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            out.add(node.args[1].value)
    return out


def _frozen_callsite_audit() -> dict[str, Any]:
    paths = [
        ROOT / "LocalGenerator/infini_local/core/runtime_authoring/repair_scope.py",
        ROOT / "LocalGenerator/infini_local/pipelines/visual_generation_pipeline.py",
        ROOT / "LocalGenerator/infini_local/core/vfx_manifest.py",
    ]
    total = 0
    explicit_false = 0
    bad: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func.id if isinstance(node.func, ast.Name) else ""
            if fn != "merge_frozen_subtree":
                continue
            total += 1
            keyword = next((row for row in node.keywords if row.arg == "allow_additions"), None)
            if keyword is not None and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                explicit_false += 1
            else:
                bad.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}")
    return {"calls": total, "explicitFalse": explicit_false, "badCallsites": bad, "ok": total > 0 and total == explicit_false}


def render() -> dict[str, Any]:
    _, full_author_payload, _ = build_initial_author_request(
        PARENT_A, PARENT_B, CANONICAL_A, CANONICAL_B, "repair-audit", model_name="audit-model"
    )
    cases = [
        _case("missing_required_parameter", _missing_use_style),
        _case("missing_item_use_capability", _missing_item_use),
        _case("missing_position_driver", _missing_movement),
        _case("existing_dependency_parameter_mismatch", _channel_dependency),
    ]
    full_count = len(CAPABILITY_REGISTRY)
    errors: list[str] = []
    for row in cases:
        if row["capabilitySubsetCount"] >= full_count:
            errors.append(f"{row['name']}: repair received the full capability catalog")
        if not row["capabilityCardsMatchSubset"]:
            errors.append(f"{row['name']}: cards and deterministic subset differ")
        if row["dossierChars"] >= len(full_author_payload):
            errors.append(f"{row['name']}: repair dossier is not smaller than Author payload")
        if row["nonRepairableCount"]:
            errors.append(f"{row['name']}: representative LLM-repairable case became non-repairable")
    movement = next(row for row in cases if row["name"] == "missing_position_driver")
    if "channel_beam" in movement["directCapabilities"] or "charge_then_release" in movement["directCapabilities"]:
        errors.append("missing_position_driver: multi-step/frozen-context alternatives leaked into blocker cards")
    channel = next(row for row in cases if row["name"] == "existing_dependency_parameter_mismatch")
    if channel["directCapabilities"] != ["configure_item_use"]:
        errors.append("existing_dependency_parameter_mismatch: exact existing dependency was not isolated")

    emitted_codes = _emitted_validator_codes()
    policy_coverage = {
        "declaredCodes": len(VALIDATION_ERROR_CODES),
        "emittedCodes": len(emitted_codes),
        "policyCodes": len(REPAIR_ERROR_POLICY),
        "declaredEqualsEmitted": set(VALIDATION_ERROR_CODES) == emitted_codes,
        "declaredEqualsPolicy": set(VALIDATION_ERROR_CODES) == set(REPAIR_ERROR_POLICY),
        "nonRepairableRegistryDefect": REPAIR_ERROR_POLICY.get("unknown_registry_requirement", {}).get("llmRepairable") is False,
    }
    if not all(value for key, value in policy_coverage.items() if key not in {"declaredCodes", "emittedCodes", "policyCodes"}):
        errors.append("validator error inventory and Repair policy are not in exact parity")

    frozen_merge = _frozen_merge_probe()
    if not frozen_merge["ok"]:
        errors.append("frozen merge probe failed")
    frozen_callsites = _frozen_callsite_audit()
    if not frozen_callsites["ok"]:
        errors.append("one or more stage Repair callsites allow arbitrary additions")

    return {
        "schema": SCHEMA,
        "ok": not errors,
        "fullAuthorPayloadChars": len(full_author_payload),
        "fullCapabilityCatalogCount": full_count,
        "policyCoverage": policy_coverage,
        "frozenMerge": frozen_merge,
        "frozenCallsites": frozen_callsites,
        "cases": cases,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="verify the generated audit artifact is current")
    args = parser.parse_args()
    report = render()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    default_target = ROOT / "contracts/targeted_repair_audit.generated.json"
    target = (args.output if args.output and args.output.is_absolute() else ROOT / args.output) if args.output else default_target
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print(f"[FAIL] stale targeted Repair audit: {target.relative_to(ROOT)}")
            return 1
    elif args.output:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if args.json:
        print(text, end="")
    else:
        status = "OK" if report["ok"] else "FAIL"
        print(f"[{status}] Author={report['fullAuthorPayloadChars']} chars; catalog={report['fullCapabilityCatalogCount']}")
        for row in report["cases"]:
            print(
                f"  {row['name']}: {row['dossierChars']} chars, "
                f"capabilities={row['capabilitySubsetCount']}, errors={','.join(row['errorCodes'])}"
            )
        print(
            f"  policy={report['policyCoverage']['policyCodes']}/{report['policyCoverage']['declaredCodes']}; "
            f"frozenMerge={report['frozenMerge']['ok']}; "
            f"frozenCallsites={report['frozenCallsites']['explicitFalse']}/{report['frozenCallsites']['calls']}"
        )
        for error in report["errors"]:
            print("  -", error)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
