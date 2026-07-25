from __future__ import annotations

"""Strict validation for the v5 low-level Gameplay Author response.

Validation reports exact paths and allowed local corrections.  It never chooses
an entity kind, input, movement, delivery path, lifecycle, or weapon family.
"""

import copy
from typing import Any, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import (
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    strict_author_shape_report,
    validate_runtime_program,
)


def _name_of(parent: Mapping[str, Any] | None) -> str:
    if not isinstance(parent, Mapping):
        return ""
    return str(parent.get("name") or parent.get("displayName") or "").strip()


def _identity_errors(data: Mapping[str, Any], a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    name = str(data.get("name") or "").strip()
    if not name:
        errors.append({"path": "$.name", "code": "required_nonempty_string", "message": "Result name is required."})
    elif len(name) > 120:
        errors.append({"path": "$.name", "code": "string_too_long", "message": "Result name must be at most 120 characters."})
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
        *copy.deepcopy(shape.get("errors") or []),
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
        exc = PlannerUnavailable(
            "Gameplay Author low-level runtime rejected: "
            + "; ".join(f"{row.get('path')}: {row.get('message')}" for row in report["errors"][:16])
        )
        setattr(exc, "author_repair_targets", copy.deepcopy(report["errors"][:48]))
        raise exc
    return data


__all__ = ["authored_item_validation_report", "strict_validate_authored_item"]


def _stringish(value: Any, default: str = "") -> str:
    """Presentation-only string coercion retained for Visual pipeline helpers."""
    text = str(value or "").strip()
    return text or default


def validate_and_repair(
    data: dict[str, Any],
    a: dict[str, Any] | None = None,
    b: dict[str, Any] | None = None,
    *_: Any,
    **__: Any,
) -> dict[str, Any]:
    """Compatibility of function *surface* for QA callers, not legacy mechanics.

    This performs only the current strict v5 validation and never edits the
    program.  Conditional repair remains an LLM stage in combine_pipeline.
    """
    return strict_validate_authored_item(data, a, b)


__all__ = [
    "_stringish",
    "authored_item_validation_report",
    "strict_validate_authored_item",
    "validate_and_repair",
]
