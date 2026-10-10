from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, NoReturn

from infini_local.core.repair_merge import json_path_child
from infini_local.core.schema_validation import strict_schema_errors
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


def _binding_action_schema(action_name: str, *, include_kind: bool = True) -> dict[str, Any]:
    from infini_local.core.runtime_authoring.capability_registry import BINDING_ACTION_REGISTRY, PLACEMENT_CAPABILITIES
    properties: dict[str, Any] = {}
    required: list[str] = []
    if include_kind:
        properties["kind"] = {"const": action_name}
        required.append("kind")
    action_spec = BINDING_ACTION_REGISTRY[action_name]
    if action_spec.target_kinds != ("item_body",):
        properties["targetId"] = {
            **_strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
            "x-infini-reference": {"namespace": "entity", "targetKinds": list(action_spec.target_kinds),
                                  "allowSelf": True, "graphEdge": False},
        }
        required.append("targetId")
    if action_name == "apply_item_effects":
        properties["effectGroupId"] = _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN)
    if action_name == "place_item":
        properties["placementCallId"] = {
            **_strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
            "x-infini-reference": {"namespace": "call", "capabilities": list(PLACEMENT_CAPABILITIES),
                                  "allowSelf": False, "graphEdge": False},
        }
        required.append("placementCallId")
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": required}


def _binding_variant_schema(input_name: str, action_name: str, cost: int | None = None) -> dict[str, Any]:
    active_use = input_name in {"primary_use", "alternate_use"}
    include_kind = len(INPUT_KIND_REGISTRY[input_name].allowed_actions) != 1
    action_shape = _binding_action_schema(action_name, include_kind=include_kind)
    properties: dict[str, Any] = {
        "id": _strict_string(min_len=1, max_len=48, pattern=_ID_PATTERN),
        "input": {"const": input_name},
    }
    required = ["id", "input"]
    if action_shape["properties"]:
        properties["action"] = action_shape
        required.append("action")
    if active_use and action_name != "place_item":
        properties["stackCost"] = {"type": "integer", "const": cost}
        if cost == 1:
            properties["stackConsumeChancePercent"] = {"type": "integer", "minimum": 0, "maximum": 100,
                "description": "Explicit own-stack debit probability after completed use; omission means 100 percent. Never ammo or placement saving."}
        properties["contactDamage"] = {"type": "boolean"}
        required.extend(("stackCost", "contactDamage"))
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": required}


def binding_schema() -> dict[str, Any]:
    return {
        "oneOf": [
            _binding_variant_schema(input_name, action_name, cost)
            for input_name, input_spec in INPUT_KIND_REGISTRY.items()
            for action_name in input_spec.allowed_actions
            for cost in ((0, 1) if input_name in {"primary_use", "alternate_use"} and action_name != "place_item" else (None,))
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
            # Full post-program prose, not a short UI/debug preview. Author,
            # Repair and provider/prompt projections share this finite authority.
            "description": _strict_string(min_len=1, max_len=4000),
            "playerExperience": _strict_string(min_len=1, max_len=3000),
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


def author_item_repair_schema(*, capability_names: Iterable[str] | None = None) -> dict[str, Any]:
    """Canonical patch shape, optionally restricted to request-visible calls.

    None requests the complete local contract. An explicit empty set permits
    only an empty callsUpsert array, never the full catalog. Scope permissions
    and the frozen merge remain separate authorities after parsing.
    """
    variants = capability_provider_union()
    if capability_names is not None:
        requested = set(capability_names)
        registered = {row["properties"]["fn"]["const"] for row in variants}
        if requested - registered:
            raise ValueError(f"Unknown Repair schema capabilities: {sorted(requested - registered)}")
        variants = [row for row in variants if row["properties"]["fn"]["const"] in requested]
    calls_schema = {"type": "array", "items": {"oneOf": variants}, "maxItems": 48} if variants else {
        "type": "array", "maxItems": 0,
        "items": {"type": "object", "additionalProperties": False, "properties": {}, "required": []},
    }
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
            "callsUpsert": calls_schema,
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



def _author_schema_work_bounds(schema: Mapping[str, Any]) -> tuple[int, int, int, int]:
    """Derive input nodes/depth/text width and assertion weight from Author schema.

    Union branches share one input value: size uses the largest branch, while
    assertion weight includes every branch the strict validator may examine.
    A bounded input has at most nodes * weight diagnostics, including missing
    properties, union wrappers and extra keys. This is not a display limit.
    """
    nodes, depth = 1, 0
    weight = 1 + len(schema) + len(schema.get("required", []))
    text_width = max([schema.get("maxLength", 0), *(
        len(value) for value in [schema.get("const"), *schema.get("enum", [])]
        if isinstance(value, str)
    )])
    children = [_author_schema_work_bounds(child) for child in schema.get("properties", {}).values()]
    if children:
        nodes += sum(child[0] for child in children)
        depth = 1 + max(child[1] for child in children)
        text_width = max(text_width, *(len(key) for key in schema["properties"]))
    item = schema.get("items")
    if isinstance(item, Mapping):
        # Author collections must have a declared finite size. Never fall back
        # to a guessed error cap when the contract is extended.
        count = schema["maxItems"]
        child = _author_schema_work_bounds(item)
        nodes += count * child[0]
        depth = max(depth, 1 + child[1])
        children.append(child)
    for key in ("oneOf", "anyOf", "allOf"):
        branches = [_author_schema_work_bounds(branch) for branch in schema.get(key, [])]
        if branches:
            nodes = max(nodes, max(branch[0] for branch in branches))
            depth = max(depth, max(branch[1] for branch in branches))
            children.extend(branches)
    for key in ("if", "then", "else"):
        if isinstance(schema.get(key), Mapping):
            children.append(_author_schema_work_bounds(schema[key]))
    text_width = max([text_width, *(child[2] for child in children)])
    weight += sum(child[3] for child in children)
    return nodes, depth, text_width, weight


def assert_bounded_author_input(
    value: Any, *, schema: Mapping[str, Any] | None = None, authored_only: bool = True,
) -> tuple[Any, int]:
    """Refuse unbounded input before recursive validation, copying or Repair.

    Return the read-only Author projection and its non-truncating diagnostic
    ceiling. Pipeline metadata is outside Author validation; raw provider input
    instead checks the whole object before projection/copying. Work refusal is
    an exception, never a diagnostic prefix advertising incomplete authority.
    """
    schema = schema if schema is not None else author_item_response_schema()
    max_nodes, max_depth, text_width, weight = _author_schema_work_bounds(schema)
    max_text = max_nodes * text_width

    def refuse(error_path: str, dimension: str) -> NoReturn:
        # RuntimeError is not a JSON syntax failure eligible for Format Repair.
        raise RuntimeError(f"Author input exceeds schema-derived work bounds at {error_path} ({dimension})")

    if isinstance(value, Mapping) and len(value) > max_nodes:
        refuse("$", "object members")
    candidate = (
        {key: item for key, item in value.items() if key in schema["properties"]}
        if authored_only and isinstance(value, Mapping) else value
    )
    pending = [(candidate, 0, "$")]
    nodes = text = 0
    while pending:
        current, depth, current_path = pending.pop()
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            refuse(current_path, "nodes/depth")
        if isinstance(current, (dict, list)):
            # Count immediate children before enumerating/allocating their paths.
            if nodes + len(pending) + len(current) > max_nodes:
                refuse(current_path, "container size")
            children = current.items() if isinstance(current, dict) else enumerate(current)
            for key, child in children:
                if isinstance(current, dict):
                    if not isinstance(key, str):
                        refuse(current_path, "non-JSON object key")
                    text += len(key)
                    if text > max_text:
                        refuse(current_path, "text")
                pending.append((child, depth + 1, json_path_child(current_path, key)))
        elif isinstance(current, str):
            text += len(current)
            if text > max_text:
                refuse(current_path, "text")
    return candidate, max_nodes * weight


def strict_author_shape_report(value: Any) -> dict[str, Any]:
    # The provider response is strict, while pipeline metadata (id/debug/parents) is
    # attached after the LLM call. Validate only the authored contract surface here;
    # this is a projection boundary, not permission for unknown authored fields.
    schema = author_item_response_schema()
    candidate, limit = assert_bounded_author_input(value, schema=schema)
    errors = strict_schema_errors(candidate, schema, limit=limit)
    return {"schema": "infini.author-item-shape-report.v1", "ok": not errors, "errors": errors}


def _repair_structure_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project value constraints away, retaining the canonical wire structure.

    String consts identify registered variants; numeric/boolean consts constrain
    values within a variant. Their types remain mandatory even before freezing.
    Conditional requirements are checked on the final merged authored document.
    """
    out = copy.deepcopy(dict(schema))
    for key in ("minimum", "maximum", "multipleOf", "if", "then", "else"):
        out.pop(key, None)
    constant = out.get("const")
    if isinstance(constant, (int, float, bool)):
        out.pop("const")
        out["type"] = "boolean" if isinstance(constant, bool) else ("integer" if isinstance(constant, int) else "number")
    if out.get("type") in {"integer", "number", "boolean"}:
        out.pop("enum", None)
    for key in ("properties", "$defs", "definitions"):
        if isinstance(out.get(key), dict):
            out[key] = {name: _repair_structure_schema(child) for name, child in out[key].items()}
    for key in ("items", "additionalProperties"):
        if isinstance(out.get(key), dict):
            out[key] = _repair_structure_schema(out[key])
    for key in ("oneOf", "anyOf", "allOf"):
        if isinstance(out.get(key), list):
            out[key] = [_repair_structure_schema(child) for child in out[key]]
    # Relaxing numeric constants can make formerly disjoint value branches
    # overlap. Pre-freeze validation requires a registered structure, while the
    # original oneOf still enforces uniqueness on the final merged document.
    if "oneOf" in out:
        structural_union = out.pop("oneOf")
        if "anyOf" in out:
            out.setdefault("allOf", []).append({"anyOf": structural_union})
        else:
            out["anyOf"] = structural_union
    return out


def strict_repair_structure_report(value: Any) -> dict[str, Any]:
    """Pre-filter check only; never substitute for strict merged validation."""
    errors = strict_schema_errors(value, _repair_structure_schema(author_item_repair_schema()))
    return {"schema": "infini.author-item-repair-structure-report.v1", "ok": not errors, "errors": errors}


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
        # Sparse Repair is not a sanitation boundary: retain malformed/ID-less
        # rows, distinct duplicate occurrences and their original ordering.
        result = copy.deepcopy(rows)
        for row in replacements:
            key = str(row.get("id"))
            indices = [index for index, old in enumerate(result)
                       if isinstance(old, dict) and str(old.get("id")) == key]
            if len(indices) > 1:
                raise ValueError(f"ambiguous gameplay repair upsert id: {key!r}")
            if indices:
                result[indices[0]] = copy.deepcopy(row)
            else:
                result.append(copy.deepcopy(row))
        return result

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
        if not isinstance(program, dict):
            return out  # Sparse Repair cannot sanitize an invalid root container.
        original_rows = program.get(list_key)
        operations = any(patch.get(key) for key in (upsert_key, delete_key, index_delete_key))
        if not operations:
            continue
        if not isinstance(original_rows, list):
            raise ValueError(f"gameplay Repair cannot apply row operations to malformed {list_key}")
        current_rows = original_rows
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
    "assert_bounded_author_input",
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
    "strict_repair_structure_report",
    "strict_schema_errors",
]
