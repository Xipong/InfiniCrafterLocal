from __future__ import annotations

"""Opt-in versioned Author admission, compilation and ID-addressed exact Repair."""

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compact_notation import (
    COMPACT_AUTHOR_SCHEMA, CompactAuthorError, _checks, _replace_planned_intent_schema,
    attach_compact_source, compact_author_item_schema, compact_binding_schema, compact_call_schema,
    encode_compact_author, project_compact_author,
)
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import (
    _repair_structure_schema, apply_repair_patch, author_item_repair_schema, author_item_response_schema,
    strict_schema_errors,
)
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


def _digest(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_compact_author(document: Mapping[str, Any]) -> dict[str, Any]:
    try:
        projection = project_compact_author(document)
    except CompactAuthorError as exc:
        return {"schema": "infini.compact-author-validation.v1", "ok": False, "errors": exc.errors}
    report = validate_runtime_program(projection.canonical)
    return {**report, "schema": "infini.compact-author-validation.v1",
            "errors": [projection.source_error(row) for row in report["errors"]]}


def compile_compact_author(document: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_compact_author(document)
    if not report["ok"]:
        raise CompactAuthorError(report["errors"])
    projection = project_compact_author(document)
    compiled = compile_runtime_program(projection.canonical)
    attach_compact_source(compiled, document, projection)
    wire = validate_runtime_wire(compiled)
    if not wire["ok"]:
        raise CompactAuthorError(wire["errors"])
    return compiled


def compact_repair_schema() -> dict[str, Any]:
    schema = author_item_repair_schema()
    properties = schema["properties"]
    properties["callsUpsert"]["items"] = compact_call_schema(item_only=None, with_target=True)
    properties["bindingsUpsert"]["items"] = compact_binding_schema()
    _replace_planned_intent_schema(properties["realizationReplacement"], author_item_response_schema())
    return schema


def build_compact_repair_scope(document: Mapping[str, Any]) -> dict[str, Any]:
    # Scalar-domain failures remain projectable. Missing structure or ambiguous
    # implicit body references are never filled by code to obtain a repair scope.
    projection = project_compact_author(document, check_shape=False, allow_unresolved_reports=True)
    canonical_report = validate_runtime_program(projection.canonical)
    canonical_scope = build_runtime_repair_scope(projection.canonical, canonical_report["errors"])
    return {
        "schema": "infini.compact-author-repair-scope.v1", "authorSchema": COMPACT_AUTHOR_SCHEMA,
        "sourceDigest": _digest(document),
        "errors": [projection.source_error(row) for row in canonical_report["errors"]],
        "canonicalScope": canonical_scope,
        "sourceMap": deepcopy(projection.sources),
        "rules": [
            "Repair is ID-addressed: callsUpsert has an explicit target for projectile-capable calls; item-only calls omit it.",
            "A call target update changes only that call and splits its group when required; it cannot retarget valid siblings.",
            "BindingsUpsert uses the compact flat variant. Missing fields mean no change at the frozen canonical merge boundary.",
            "Concept and its ordering are frozen. Every replacement action check supplies its exact plannedActionIndex; no text matching.",
            "Existing group boundaries and global call order remain, except for explicitly permitted call creation/deletion or target edits.",
        ],
    }


def apply_compact_repair(document: Mapping[str, Any], patch: Mapping[str, Any], scope: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    scope = build_compact_repair_scope(document) if scope is None else scope
    if scope.get("sourceDigest") != _digest(document):
        raise CompactAuthorError([{"path": "$", "code": "stale_compact_repair_scope"}])
    # Do not trust caller-supplied permissions or a caller-supplied source map.
    if scope != build_compact_repair_scope(document):
        raise CompactAuthorError([{"path": "$", "code": "forged_compact_repair_scope"}])
    shape = strict_schema_errors(patch, _repair_structure_schema(compact_repair_schema()))
    if shape:
        raise CompactAuthorError(shape)
    projection = project_compact_author(document, check_shape=False, allow_unresolved_reports=True)
    canonical_patch = deepcopy(dict(patch))
    body_id = next(row["id"] for row in projection.canonical["runtimeProgram"]["entities"] if row["kind"] == "item_body")
    for call in canonical_patch.get("callsUpsert", []):
        cap = CAPABILITY_REGISTRY[call["fn"]]
        if cap.target_kinds == ("item_body",):
            call["target"] = body_id
        if not cap.params:
            call["params"] = {}
    for index, binding in enumerate(patch.get("bindingsUpsert", [])):
        temporary = deepcopy(dict(document))
        temporary["runtimeProgram"]["bindings"] = [deepcopy(binding)]
        canonical_patch["bindingsUpsert"][index] = project_compact_author(temporary, check_shape=False, allow_unresolved_reports=True).canonical["runtimeProgram"]["bindings"][0]
    if "realizationReplacement" in patch:
        temporary = deepcopy(dict(document))
        temporary["realization"] = deepcopy(patch["realizationReplacement"])
        canonical_patch["realizationReplacement"] = project_compact_author(temporary, check_shape=False).canonical["realization"]
        indices = [row["plannedActionIndex"] for row in _checks(temporary)]
    else:
        indices = [row["plannedActionIndex"] for row in _checks(document)]
    filtered, audit = filter_repair_patch_scope(projection.canonical, canonical_patch, scope["canonicalScope"])
    if not audit["ok"]:
        return deepcopy(dict(document)), audit
    merged = apply_repair_patch(projection.canonical, filtered)
    repaired = encode_compact_author(merged, planned_action_indices=indices, preserve_groups_from=document)
    report = validate_compact_author(repaired)
    if not report["ok"]:
        return repaired, {**audit, "ok": False, "remainingErrors": report["errors"]}
    return repaired, audit
