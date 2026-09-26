from __future__ import annotations

import copy
import math
import re
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    ENTITY_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    capability_provider_union,
)
_ID_PATTERN = r"^[a-z][a-z0-9_]{0,47}$"
PRIMARY_ENTITY_FIELD = "primaryEntityId"
PRIMARY_ENTITY_AUTHOR_PATH = f"runtimeProgram.{PRIMARY_ENTITY_FIELD}"
PRIMARY_ENTITY_JSON_PATH = f"$.{PRIMARY_ENTITY_AUTHOR_PATH}"
PRIMARY_ENTITY_SELECTION_FIELD = "primaryEntitySelection"
PRIMARY_ENTITY_SELECTION_JSON_PATH = f"$.{PRIMARY_ENTITY_SELECTION_FIELD}"


def authored_primary_entity_id(program: Mapping[str, Any]) -> str:
    return str(program.get(PRIMARY_ENTITY_FIELD) or "")


def primary_entity_repair_transaction(entity_ids: Iterable[str]) -> dict[str, Any]:
    candidates = sorted({str(entity_id) for entity_id in entity_ids if str(entity_id)})
    if not candidates:
        return {}
    return {
        "allowed": True,
        "candidateEntityIds": candidates,
        "mustSelectExactlyOne": True,
    }


def _strict_string(*, min_len: int = 0, max_len: int = 256, pattern: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "string", "minLength": min_len, "maxLength": max_len}
    if pattern:
        out["pattern"] = pattern
    return out


def entity_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
            "kind": {"type": "string", "enum": list(ENTITY_KIND_REGISTRY)},
        },
        "required": ["id", "kind"],
    }


def _binding_action_schema(action_name: str) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "kind": {"const": action_name},
        "targetId": {
            **_strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
            "x-infini-reference": {
                "namespace": "entity",
                "targetKinds": list(ENTITY_KIND_REGISTRY),
                "allowSelf": True,
                "graphEdge": False,
            },
        },
    }
    required = ["kind", "targetId"]
    if action_name == "place_item":
        properties["placementCallId"] = {
            **_strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
            "x-infini-reference": {
                "namespace": "call",
                "capabilities": ["configure_placeable"],
                "allowSelf": False,
                "graphEdge": False,
            },
        }
        required.append("placementCallId")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _binding_variant_schema(input_name: str, action_name: str) -> dict[str, Any]:
    active_use = input_name in {"primary_use", "alternate_use"}
    may_contact = active_use and action_name != "place_item"
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
            "input": {"const": input_name},
            "usePolicy": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": _binding_action_schema(action_name),
                    "stackCost": (
                        {"const": 1}
                        if action_name == "place_item"
                        else ({"type": "integer", "enum": [0, 1]} if active_use else {"const": 0})
                    ),
                    "contactDamage": (
                        {"type": "boolean"} if may_contact else {"const": False}
                    ),
                },
                "required": ["action", "stackCost", "contactDamage"],
            },
        },
        "required": ["id", "input", "usePolicy"],
    }


def binding_schema() -> dict[str, Any]:
    return {
        "oneOf": [
            _binding_variant_schema(input_name, action_name)
            for input_name, input_spec in INPUT_KIND_REGISTRY.items()
            for action_name in input_spec.allowed_actions
        ],
    }


def runtime_program_author_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "apiVersion": {"const": RUNTIME_PROGRAM_API_VERSION},
            "schema": {"const": RUNTIME_PROGRAM_SCHEMA},
            PRIMARY_ENTITY_FIELD: {
                **_strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
                "description": "The exact model-authored primary entity id. Technical row roles are lowered from exact target equality.",
                "x-infini-reference": {"namespace": "entity", "targetKinds": list(ENTITY_KIND_REGISTRY), "allowSelf": True, "graphEdge": False},
            },
            "entities": {
                "type": "array",
                "items": entity_schema(),
                "minItems": 1,
                "maxItems": 12,
            },
            "bindings": {
                "type": "array",
                "items": binding_schema(),
                "minItems": 0,
                "maxItems": 8,
            },
            "calls": {
                "type": "array",
                "items": {"oneOf": capability_provider_union()},
                "minItems": 1,
                "maxItems": 48,
            },
        },
        "required": ["apiVersion", "schema", PRIMARY_ENTITY_FIELD, "entities", "bindings", "calls"],
    }


def realization_schema() -> dict[str, Any]:
    runtime_refs = {
        "type": "array",
        "items": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
        "minItems": 1,
        "maxItems": 16,
    }
    deviation = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "plannedIntent": _strict_string(min_len=1, max_len=280),
            "implementedBehavior": _strict_string(min_len=1, max_len=280),
            "runtimeRefs": copy.deepcopy(runtime_refs),
            "result": {"type": "string", "enum": ["aligned", "changed", "dropped", "added", "uncertain"]},
            "intentionality": {"type": "string", "enum": ["intentional", "accidental", "uncertain"]},
            "reason": _strict_string(min_len=1, max_len=400),
        },
        "required": ["plannedIntent", "implementedBehavior", "runtimeRefs", "result", "intentionality", "reason"],
    }
    mismatch = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "runtimeRefs": copy.deepcopy(runtime_refs),
            "programBehavior": _strict_string(min_len=1, max_len=280),
            "reportedBehavior": _strict_string(min_len=1, max_len=280),
            "result": {"type": "string", "enum": ["aligned", "mismatch", "omitted", "uncertain"]},
            "reason": _strict_string(min_len=1, max_len=400),
        },
        "required": ["runtimeRefs", "programBehavior", "reportedBehavior", "result", "reason"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "description": _strict_string(min_len=1, max_len=700),
            "playerExperience": _strict_string(min_len=1, max_len=500),
            # Deliberately last: the same Author independently compares the
            # non-binding draft with the program, then the program with its report.
            "selfEvaluation": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "planVsProgram": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "verdict": {"type": "string", "enum": ["aligned", "changed", "uncertain"]},
                            "summary": _strict_string(min_len=1, max_len=500),
                            "actionChecks": {"type": "array", "items": deviation, "minItems": 1, "maxItems": 24},
                        },
                        "required": ["verdict", "summary", "actionChecks"],
                    },
                    "programVsReport": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "verdict": {"type": "string", "enum": ["aligned", "mismatch", "uncertain"]},
                            "summary": _strict_string(min_len=1, max_len=500),
                            "behaviorChecks": {"type": "array", "items": mismatch, "minItems": 1, "maxItems": 24},
                        },
                        "required": ["verdict", "summary", "behaviorChecks"],
                    },
                },
                "required": ["planVsProgram", "programVsReport"],
            },
        },
        "required": ["description", "playerExperience", "selfEvaluation"],
    }


def author_item_response_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": _strict_string(min_len=1, max_len=80),
            "category": {
                "type": "string",
                "enum": ["combat", "tool", "equipment", "placeable", "consumable", "material", "hybrid", "generic"],
                "description": "UI/equipment result category only; never routes runtime execution.",
            },
            "concept": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "literalSynthesis": _strict_string(min_len=1, max_len=500),
                    "coreMechanic": _strict_string(min_len=1, max_len=500),
                    "parentAContribution": _strict_string(min_len=1, max_len=280),
                    "parentBContribution": _strict_string(min_len=1, max_len=280),
                    "playerExperience": _strict_string(min_len=1, max_len=500),
                    "plannedPlayerActions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "description": "Non-binding initial gameplay sketch. It never routes execution or rejects a craft when the final program changes.",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "input": {
                                    "type": "string",
                                    "enum": ["primary_use", "alternate_use", "hold", "equipped", "passive_or_event"],
                                },
                                "intent": _strict_string(min_len=1, max_len=280),
                            },
                            "required": ["input", "intent"],
                        },
                    },
                },
                "required": [
                    "literalSynthesis", "coreMechanic", "parentAContribution", "parentBContribution", "playerExperience",
                ],
            },
            "runtimeProgram": runtime_program_author_schema(),
            # Deliberately last: this is the same Author's post-program account
            # of what the accepted executable draft actually realizes.
            "realization": realization_schema(),
        },
        "required": ["name", "category", "concept", "runtimeProgram", "realization"],
    }


def author_item_repair_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entitiesUpsert": {"type": "array", "items": entity_schema(), "maxItems": 12},
            "entityIdsDelete": {"type": "array", "items": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN), "maxItems": 12},
            "entityIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 11}, "maxItems": 12},
            "bindingsUpsert": {"type": "array", "items": binding_schema(), "maxItems": 8},
            "bindingIdsDelete": {"type": "array", "items": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN), "maxItems": 8},
            "bindingIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 7}, "maxItems": 8},
            "callsUpsert": {"type": "array", "items": {"oneOf": capability_provider_union()}, "maxItems": 48},
            "callIdsDelete": {"type": "array", "items": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN), "maxItems": 48},
            "callIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 47}, "maxItems": 48},
            "callParamKeysDelete": {
                "type": "array",
                "maxItems": 48,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "callId": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
                        "key": _strict_string(min_len=1, max_len=64),
                    },
                    "required": ["callId", "key"],
                },
            },
            "callPropertyKeysDelete": {
                "type": "array",
                "maxItems": 48,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "callId": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
                        "key": _strict_string(min_len=1, max_len=64),
                    },
                    "required": ["callId", "key"],
                },
            },
            PRIMARY_ENTITY_SELECTION_FIELD: {
                "oneOf": [
                    _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
                    {"type": "null"},
                ],
            },
            "exclusiveInputSelections": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "input": {"type": "string", "enum": list(INPUT_KIND_REGISTRY)},
                        "keepBindingId": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
                    },
                    "required": ["input", "keepBindingId"],
                },
            },
            "metadataPatch": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": _strict_string(min_len=1, max_len=80),
                    "category": {"type": "string", "enum": ["combat", "tool", "equipment", "placeable", "consumable", "material", "hybrid", "generic"]},
                    "concept": author_item_response_schema()["properties"]["concept"],
                },
            },
            "realizationReplacement": realization_schema(),
            "note": _strict_string(min_len=1, max_len=500),
        },
        "required": ["note"],
    }


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    if expected == "null":
        return value is None
    return False


def _resolve_ref(root: Mapping[str, Any], ref: str) -> Mapping[str, Any] | None:
    if not ref.startswith("#/$defs/"):
        return None
    defs = root.get("$defs")
    if not isinstance(defs, Mapping):
        return None
    value = defs.get(ref.removeprefix("#/$defs/"))
    return value if isinstance(value, Mapping) else None


def strict_schema_errors(value: Any, schema: Mapping[str, Any], *, path: str = "$", root: Mapping[str, Any] | None = None, limit: int = 128) -> list[dict[str, Any]]:
    root_schema = root or schema
    errors: list[dict[str, Any]] = []

    def add(kind: str, error_path: str, expected: Any = None, actual: Any = None) -> None:
        if len(errors) >= limit:
            return
        row: dict[str, Any] = {"path": error_path, "kind": kind}
        if expected is not None:
            row["expected"] = expected
        if actual is not None:
            row["actual"] = actual if isinstance(actual, (str, int, float, bool)) else type(actual).__name__
        errors.append(row)

    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = _resolve_ref(root_schema, ref)
        if resolved is None:
            add("unresolved_ref", path, ref)
            return errors
        return strict_schema_errors(value, resolved, path=path, root=root_schema, limit=limit)

    if "const" in schema and value != schema.get("const"):
        add("const", path, schema.get("const"), value)
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        add("enum", path, enum, value)

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        branch_results = [strict_schema_errors(value, branch, path=path, root=root_schema, limit=limit) for branch in one_of if isinstance(branch, Mapping)]
        matches = [branch for branch in branch_results if not branch]
        if len(matches) != 1:
            add("one_of", path, "exactly_one", len(matches))
            if not matches and branch_results:
                errors.extend(min(branch_results, key=len)[: max(0, limit - len(errors))])
        return errors[:limit]

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        branch_results = [strict_schema_errors(value, branch, path=path, root=root_schema, limit=limit) for branch in any_of if isinstance(branch, Mapping)]
        if not any(not branch for branch in branch_results):
            add("any_of", path)
        return errors[:limit]

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _type_matches(value, expected_type):
        add("type", path, expected_type, value)
        return errors[:limit]

    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            add("min_length", path, schema["minLength"], len(value))
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            add("max_length", path, schema["maxLength"], len(value))
        if isinstance(schema.get("pattern"), str) and re.fullmatch(str(schema["pattern"]), value) is None:
            add("pattern", path, schema["pattern"], value)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            add("finite", path, "finite number", value)
        if schema.get("minimum") is not None and value < schema["minimum"]:
            add("minimum", path, schema["minimum"], value)
        if schema.get("maximum") is not None and value > schema["maximum"]:
            add("maximum", path, schema["maximum"], value)
        step = schema.get("multipleOf")
        if isinstance(step, (int, float)) and step > 0 and math.isfinite(float(value)):
            # The only authored fractional step is an exact binary half; check
            # the quotient without rounding or approximating engine quantities.
            if value % step != 0:
                add("multiple_of", path, step, value)

    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            add("min_items", path, schema["minItems"], len(value))
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            add("max_items", path, schema["maxItems"], len(value))
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, child in enumerate(value):
                errors.extend(strict_schema_errors(child, item_schema, path=f"{path}[{index}]", root=root_schema, limit=max(0, limit - len(errors))))
                if len(errors) >= limit:
                    break

    if isinstance(value, dict):
        condition = schema.get("if")
        if isinstance(condition, Mapping) and not strict_schema_errors(value, condition, path=path, root=root_schema, limit=limit):
            consequent = schema.get("then")
            if isinstance(consequent, Mapping):
                errors.extend(strict_schema_errors(value, consequent, path=path, root=root_schema, limit=max(0, limit - len(errors))))
        raw_properties = schema.get("properties")
        properties: Mapping[str, Any] = raw_properties if isinstance(raw_properties, Mapping) else {}
        raw_required = schema.get("required")
        required: list[Any] = raw_required if isinstance(raw_required, list) else []
        for key in required:
            if key not in value:
                add("required", f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    add("additional_property", f"{path}.{key}")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, Mapping):
                errors.extend(strict_schema_errors(child, child_schema, path=f"{path}.{key}", root=root_schema, limit=max(0, limit - len(errors))))
                if len(errors) >= limit:
                    break
    return errors[:limit]


def strict_author_shape_report(value: Any) -> dict[str, Any]:
    # The provider response is strict, while pipeline metadata (id/debug/parents) is
    # attached after the LLM call. Validate only the authored contract surface here;
    # this is a projection boundary, not permission for unknown authored fields.
    if not isinstance(value, Mapping):
        candidate: Any = value
    else:
        allowed = set(author_item_response_schema()["properties"])
        candidate = {key: copy.deepcopy(item) for key, item in value.items() if key in allowed}
    errors = strict_schema_errors(candidate, author_item_response_schema())
    return {"schema": "infini.author-item-shape-report.v1", "ok": not errors, "errors": errors}


def strict_repair_shape_report(value: Any) -> dict[str, Any]:
    errors = strict_schema_errors(value, author_item_repair_schema())
    return {"schema": "infini.author-item-repair-shape-report.v1", "ok": not errors, "errors": errors}


def apply_repair_patch(current: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    report = strict_repair_shape_report(patch)
    if not report["ok"]:
        raise ValueError(f"invalid gameplay repair patch: {report['errors'][:8]}")
    out = copy.deepcopy(dict(current))
    program = out.setdefault("runtimeProgram", {})

    def upsert(rows: list[Any], replacements: list[Any]) -> list[Any]:
        by_id = {str(row.get("id")): copy.deepcopy(row) for row in rows if isinstance(row, dict) and row.get("id")}
        order = [str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")]
        for row in replacements:
            key = str(row.get("id"))
            if key not in by_id:
                order.append(key)
            by_id[key] = copy.deepcopy(row)
        return [by_id[key] for key in order if key in by_id]

    def delete(rows: list[Any], ids: list[Any]) -> list[Any]:
        doomed = {str(value) for value in ids}
        return [row for row in rows if not isinstance(row, dict) or str(row.get("id")) not in doomed]

    def delete_indices(rows: list[Any], indices: list[Any]) -> list[Any]:
        doomed = {int(value) for value in indices if isinstance(value, int) and not isinstance(value, bool)}
        return [row for index, row in enumerate(rows) if index not in doomed]

    for list_key, upsert_key, delete_key, index_delete_key in (
        ("entities", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete"),
        ("bindings", "bindingsUpsert", "bindingIdsDelete", "bindingIndicesDelete"),
        ("calls", "callsUpsert", "callIdsDelete", "callIndicesDelete"),
    ):
        current_rows = list(program.get(list_key) or []) if isinstance(program, dict) else []
        current_rows = delete_indices(current_rows, list(patch.get(index_delete_key) or []))
        current_rows = delete(current_rows, list(patch.get(delete_key) or []))
        program[list_key] = upsert(current_rows, list(patch.get(upsert_key) or []))

    calls_by_id = {
        str(row.get("id") or ""): row
        for row in program.get("calls") or []
        if isinstance(row, dict) and str(row.get("id") or "")
    }
    for deletion in patch.get("callPropertyKeysDelete") or []:
        if not isinstance(deletion, Mapping):
            continue
        call = calls_by_id.get(str(deletion.get("callId") or ""))
        key = str(deletion.get("key") or "")
        if call is not None and key:
            call.pop(key, None)
    for deletion in patch.get("callParamKeysDelete") or []:
        if not isinstance(deletion, Mapping):
            continue
        call = calls_by_id.get(str(deletion.get("callId") or ""))
        key = str(deletion.get("key") or "")
        if call is not None and key and isinstance(call.get("params"), dict):
            call["params"].pop(key, None)

    selected_primary = str(patch.get(PRIMARY_ENTITY_SELECTION_FIELD) or "").strip()
    if selected_primary:
        program[PRIMARY_ENTITY_FIELD] = selected_primary

    for selection in patch.get("exclusiveInputSelections") or []:
        if not isinstance(selection, Mapping):
            continue
        input_name = str(selection.get("input") or "")
        keep_id = str(selection.get("keepBindingId") or "")
        before_bindings = list(program.get("bindings") or [])
        program["bindings"] = [
            row for row in before_bindings
            if not isinstance(row, Mapping)
            or str(row.get("input") or "") != input_name
            or str(row.get("id") or "") == keep_id
        ]

    metadata = patch.get("metadataPatch")
    if isinstance(metadata, Mapping):
        for key in ("name", "category", "concept"):
            if key in metadata:
                out[key] = copy.deepcopy(metadata[key])
    if "realizationReplacement" in patch:
        out["realization"] = copy.deepcopy(patch["realizationReplacement"])
    return out


__all__ = [
    "PRIMARY_ENTITY_AUTHOR_PATH",
    "PRIMARY_ENTITY_FIELD",
    "PRIMARY_ENTITY_JSON_PATH",
    "PRIMARY_ENTITY_SELECTION_FIELD",
    "PRIMARY_ENTITY_SELECTION_JSON_PATH",
    "apply_repair_patch",
    "authored_primary_entity_id",
    "author_item_repair_schema",
    "author_item_response_schema",
    "binding_schema",
    "entity_schema",
    "realization_schema",
    "runtime_program_author_schema",
    "primary_entity_repair_transaction",
    "strict_author_shape_report",
    "strict_repair_shape_report",
    "strict_schema_errors",
]
