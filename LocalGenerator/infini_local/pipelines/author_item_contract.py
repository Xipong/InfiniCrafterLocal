from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.runtime_authoring import (
    RUNTIME_CONTRACT_SCHEMA,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    apply_repair_patch,
    author_item_repair_schema as _repair_schema,
    author_item_response_schema as _author_schema,
    strict_repair_shape_report,
    validate_runtime_program,
)


def author_item_response_schema() -> dict[str, Any]:
    return copy.deepcopy(_author_schema())


def author_item_prompt_shape_card() -> dict[str, Any]:
    return {
        "root": ["name", "tooltip", "category", "concept", "runtimeContract", "runtimeProgram"],
        "name": "non-empty string",
        "tooltip": "non-empty string",
        "category": "combat|tool|equipment|placeable|consumable|material|hybrid|generic",
        "concept": {
            "literalSynthesis": "non-empty string",
            "coreMechanic": "non-empty string",
            "parentAContribution": "non-empty string",
            "parentBContribution": "non-empty string",
            "playerExperience": "non-empty string",
        },
        "runtimeProgram": {
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
            "schema": RUNTIME_PROGRAM_SCHEMA,
            "primaryEntityId": "exact existing entity id chosen once by the model",
            "entities": [{"id": "stable_id", "kind": "catalog entity kind"}],
            "bindings": [{"id": "stable_id", "input": "primary_use|alternate_use|hold|equipped", "action": "catalog action", "target": "entity_id"}],
            "calls": [{"id": "stable_id", "fn": "catalog capability", "target": "entity_id", "params": {"exactCapabilityParam": "typed value"}}],
        },
        "runtimeContract": {
            "schema": RUNTIME_CONTRACT_SCHEMA,
            "parentSynthesis": {
                "composition": "non-empty string",
                "parentA": {"facts": ["source-backed fact"], "runtimeRoles": ["authored runtime role"]},
                "parentB": {"facts": ["source-backed fact"], "runtimeRoles": ["authored runtime role"]},
            },
            "claims": [{
                "id": "stable_claim_id",
                "kind": "gameplay|physical|parent_synthesis",
                "text": "non-empty claim",
                "backedBy": ["existing call or binding id"],
            }],
        },
        "forbidden": [
            "weapon archetype selector",
            "family-derived movement/attachment/delivery",
            "compiler receipts",
            "visual or VFX gameplay invention",
        ],
    }


def _provider_strict_projection(schema: Any) -> Any:
    """Make optional object properties required+nullable for strict providers.

    The local contract remains sparse where a capability parameter is genuinely
    optional. Provider-only nulls are stripped before local validation; no semantic
    value is invented.
    """
    if isinstance(schema, list):
        return [_provider_strict_projection(value) for value in schema]
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)
    out = {key: _provider_strict_projection(value) for key, value in schema.items()}
    props = out.get("properties")
    if isinstance(props, dict):
        local_required = set(schema.get("required") or [])
        for key, child in list(props.items()):
            if key in local_required or not isinstance(child, dict):
                continue
            props[key] = {"anyOf": [child, {"type": "null"}]}
        out["required"] = list(props)
    return out


def author_item_provider_response_schema() -> dict[str, Any]:
    return _provider_strict_projection(author_item_response_schema())


def author_item_repair_response_schema() -> dict[str, Any]:
    return copy.deepcopy(_repair_schema())


def author_item_repair_prompt_shape_card() -> dict[str, Any]:
    """Expose the repair root cardinality when provider JSON Schema is unavailable."""
    schema = author_item_repair_response_schema()
    properties = schema.get("properties") or {}
    placeholders: dict[str, Any] = {}
    for key, child in properties.items():
        if key == "entitiesUpsert":
            placeholders[key] = [{"id": "stable_entity_id", "kind": "catalog entity kind"}]
            continue
        if key == "bindingsUpsert":
            placeholders[key] = [{
                "id": "stable_binding_id",
                "input": "primary_use|alternate_use|hold|equipped",
                "action": "catalog action",
                "target": "existing entity id",
            }]
            continue
        if key == "callsUpsert":
            placeholders[key] = [{
                "id": "stable_call_id",
                "fn": "catalog capability",
                "target": "existing entity id",
                "params": {"everyRequiredCapabilityParam": "typed value"},
            }]
            continue
        if key == "callParamKeysDelete":
            placeholders[key] = [{
                "callId": "exact call id from repairScope.deletable.callParamKeys",
                "key": "exact invalid parameter key from repairScope.deletable.callParamKeys",
            }]
            continue
        if key == "claimsUpsert":
            placeholders[key] = [{
                "id": "stable_claim_id",
                "kind": "gameplay|physical|parent_synthesis",
                "text": "non-empty claim",
                "backedBy": ["existing binding or call id"],
            }]
            continue
        if key == "primaryEntitySelection":
            placeholders[key] = "entity_id chosen from repairScope.repairTransactions.primaryEntitySelection.candidateEntityIds, or null"
            continue
        if key == "exclusiveInputSelections":
            placeholders[key] = [{"input": "conflicting exclusive input", "keepBindingId": "chosen candidate binding id"}]
            continue
        child_type = child.get("type") if isinstance(child, Mapping) else None
        if child_type == "array":
            placeholders[key] = []
        elif child_type == "object":
            placeholders[key] = {}
        elif child_type == "boolean":
            placeholders[key] = False
        elif child_type in {"integer", "number"}:
            placeholders[key] = 0
        else:
            placeholders[key] = "non-empty repair note"
    return placeholders


def author_item_provider_repair_response_schema(*_: Any, **__: Any) -> dict[str, Any]:
    return _provider_strict_projection(author_item_repair_response_schema())


def author_item_targeted_repair_delta_schema() -> dict[str, Any]:
    return author_item_repair_response_schema()


def author_item_provider_targeted_repair_delta_schema(*_: Any, **__: Any) -> dict[str, Any]:
    return author_item_provider_repair_response_schema()


def _strip_nulls(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_nulls(child) for child in value if child is not None]
    if isinstance(value, dict):
        return {key: _strip_nulls(child) for key, child in value.items() if child is not None}
    return value


def project_provider_nullable_optionals_to_local(value: Any, *_: Any, **__: Any) -> Any:
    return _strip_nulls(copy.deepcopy(value))


def project_provider_author_item_to_local(value: Any, *_: Any, **__: Any) -> Any:
    return project_provider_nullable_optionals_to_local(value)


def normalize_author_item_targeted_repair_delta_text_limits(value: Any) -> Any:
    return copy.deepcopy(value)


def strict_author_item_v3_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "schema": "infini.author-item-low-level-report.v1",
            "ok": False,
            "errors": [{"path": "$", "code": "type", "message": "Author response must be an object."}],
        }
    return validate_runtime_program(value)


def strict_author_item_repair_report(value: Any) -> dict[str, Any]:
    return strict_repair_shape_report(value)


def strict_author_item_targeted_repair_delta_report(value: Any) -> dict[str, Any]:
    return strict_repair_shape_report(value)


def apply_author_item_repair_patch(current: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    return apply_repair_patch(current, patch)


__all__ = [
    "apply_author_item_repair_patch",
    "author_item_prompt_shape_card",
    "author_item_provider_repair_response_schema",
    "author_item_provider_response_schema",
    "author_item_provider_targeted_repair_delta_schema",
    "author_item_repair_prompt_shape_card",
    "author_item_repair_response_schema",
    "author_item_response_schema",
    "author_item_targeted_repair_delta_schema",
    "normalize_author_item_targeted_repair_delta_text_limits",
    "project_provider_author_item_to_local",
    "project_provider_nullable_optionals_to_local",
    "strict_author_item_repair_report",
    "strict_author_item_targeted_repair_delta_report",
    "strict_author_item_v3_report",
]
