"""Gameplay acceptance: strict Author -> compile -> wire, with one scoped Repair.

This is the stage entrypoint used by combine. Request construction stays in
llm_authoring_pipeline; canonical shape/validation/compilation stays in
core.runtime_authoring. No design choices or new wire are introduced here.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Callable, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION, RUNTIME_PROGRAM_SCHEMA
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import ITEM_NAME_MAX_LENGTH, strict_author_shape_report
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.llm_authoring_pipeline import repair_author_item_after_failure


class _RepairableGameplayRejection(PlannerUnavailable):
    """An explicit Author/wire validation rejection, never a compiler bug."""


def _name_of(parent: Mapping[str, Any] | None) -> str:
    if not isinstance(parent, Mapping):
        return ""
    return str(parent.get("name") or parent.get("displayName") or "").strip()


def _identity_errors(data: Mapping[str, Any], a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    name = str(data.get("name") or "").strip()
    if not name:
        errors.append({"path": "$.name", "code": "required_nonempty_string", "message": "Result name is required."})
    elif len(name) > ITEM_NAME_MAX_LENGTH:
        errors.append({"path": "$.name", "code": "string_too_long", "message": f"Result name must be at most {ITEM_NAME_MAX_LENGTH} characters."})
    parent_names = {value.casefold() for value in (_name_of(a), _name_of(b)) if value}
    if len(parent_names) == 2 and name.casefold() in parent_names:
        errors.append({
            "path": "$.name",
            "code": "uncombined_identity",
            "message": "Result name exactly repeats one parent despite two distinct parents; provide an authored combined identity.",
        })
    return errors


def authored_item_validation_report(
    data: Mapping[str, Any],
    a: Mapping[str, Any] | None = None,
    b: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    shape = strict_author_shape_report(data)
    runtime = validate_runtime_program(data)
    identity = _identity_errors(data, a, b)
    errors = [
        # validate_runtime_program is the canonical Repair-facing boundary. It
        # already converts strict-schema kinds to finite ``shape_*`` codes.
        # Keep the raw shape report below for diagnostics, but never mix its
        # kind-only rows into author_repair_targets.
        *copy.deepcopy(runtime.get("errors") or []),
        *identity,
    ]
    program = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), Mapping) else {}
    if program.get("apiVersion") != RUNTIME_PROGRAM_API_VERSION:
        errors.append({
            "path": "$.runtimeProgram.apiVersion",
            "code": "unsupported_api_version",
            "message": f"Expected exact API version {RUNTIME_PROGRAM_API_VERSION}.",
        })
    if program.get("schema") != RUNTIME_PROGRAM_SCHEMA:
        errors.append({
            "path": "$.runtimeProgram.schema",
            "code": "unsupported_author_schema",
            "message": f"Expected exact author schema {RUNTIME_PROGRAM_SCHEMA}.",
        })
    # Deduplicate because the shape and semantic validator can intentionally
    # report the same boundary problem at different levels.
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in errors:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("path") or "$"), str(row.get("code") or "invalid"), str(row.get("message") or ""))
        unique[key] = row
    final_errors = list(unique.values())
    return {
        "schema": "infini.low-level-author-validation.v1",
        "ok": not final_errors,
        "errors": final_errors,
        "shape": shape,
        "runtime": runtime,
    }


def strict_validate_authored_item(
    data: dict[str, Any],
    a: dict[str, Any] | None = None,
    b: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = authored_item_validation_report(data, a, b)
    data.setdefault("debug", {})["lowLevelAuthorValidation"] = copy.deepcopy(report)
    if not report["ok"]:
        exc = _RepairableGameplayRejection(
            "Gameplay Author low-level runtime rejected: "
            + "; ".join(f"{row.get('path')}: {row.get('message')}" for row in report["errors"][:16])
        )
        # Human-readable exception text is a preview; Repair authority is the
        # complete same-pass canonical report, including later identity errors.
        setattr(exc, "author_repair_targets", copy.deepcopy(report["errors"]))
        raise exc
    return data


def attach_gameplay_and_runtime_program(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
) -> dict[str, Any]:
    compiled = compile_runtime_program(data)
    compiled["runtimeApiVersion"] = RUNTIME_PROGRAM_API_VERSION
    compiled.setdefault("schemaVersion", 5)
    compiled.setdefault("parentA", str(a.get("name") or a.get("displayName") or ""))
    compiled.setdefault("parentB", str(b.get("name") or b.get("displayName") or ""))
    compiled.setdefault("debug", {})["gameplayCompiler"] = "explicit_low_level_runtime_program_v5"
    compiled["debug"]["gameplayDesignAuthorship"] = "gameplay_author"
    compiled["debug"]["deterministicRole"] = "validate_compile_execute_only"
    return compiled


def validate_final_runtime_wire_boundary(data: dict[str, Any]) -> dict[str, Any]:
    report = validate_runtime_wire(data)
    debug = data.setdefault("debug", {})
    debug["finalRuntimeProgramWireGate"] = bounded_json_dumps(report, max_chars=12000)
    if not report.get("ok"):
        exc = _RepairableGameplayRejection(
            "final low-level runtime wire rejected: "
            + "; ".join(f"{row.get('path')}: {row.get('message')}" for row in report.get("errors", [])[:12])
        )
        exc.author_repair_targets = copy.deepcopy(report.get("errors") or [])
        raise exc
    return report


def _failure_report(item: Mapping[str, Any], exc: BaseException, stage: str) -> dict[str, Any]:
    validation = validate_runtime_program(item)
    errors = copy.deepcopy(validation.get("errors") or [])
    targets = getattr(exc, "author_repair_targets", None)
    if isinstance(targets, list):
        errors = [copy.deepcopy(row) for row in targets if isinstance(row, Mapping)] or errors
    if not errors:
        errors = [{"path": "$", "code": "compile_or_wire_rejection", "message": str(exc)[:1800]}]
    return {
        "schema": "infini.low-level-gameplay-failure.v1",
        "stage": stage,
        "errorType": type(exc).__name__,
        "error": str(exc)[:2000],
        "errors": errors,
        "validation": validation,
    }


def compile_and_validate_authored_runtime(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    key: str,
    *,
    run_stage: Callable[..., Any],
) -> dict[str, Any]:
    """Validate/compile once, then use one conditional Gameplay Repair if rejected."""

    def domain_pass(item: dict[str, Any], prefix: str) -> dict[str, Any]:
        item = run_stage(prefix + "_strict_runtime_program", strict_validate_authored_item, item, a, b)
        item = run_stage(prefix + "_compile_runtime_program", attach_gameplay_and_runtime_program, item, a, b)
        run_stage(prefix + "_wire_boundary", validate_final_runtime_wire_boundary, item)
        return item

    authored = copy.deepcopy(data)
    try:
        return domain_pass(data, "02")
    except _RepairableGameplayRejection as exc:
        report = _failure_report(authored, exc, "gameplay_validation_or_compile")
    accounting = ((authored.get("debug") or {}).get("llmStageAccounting") or {})
    if int(accounting.get("gameplayRepairCalls", 0) or 0) >= 1:
        raise PlannerUnavailable(
            "Gameplay format Repair output failed validation and the single gameplay repair budget already consumed: "
            + json.dumps(report["errors"][:12], ensure_ascii=False)
        )
    repaired = run_stage(
        "02r_conditional_gameplay_repair",
        repair_author_item_after_failure,
        authored,
        a,
        b,
        key,
        failure_report=report,
    )
    try:
        return domain_pass(repaired, "02r")
    except _RepairableGameplayRejection as exc:
        second = _failure_report(repaired, exc, "gameplay_repair_validation_or_compile")
        raise PlannerUnavailable("Gameplay Repair did not produce an executable low-level program: " + json.dumps(second["errors"][:12], ensure_ascii=False)) from exc
