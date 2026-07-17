from __future__ import annotations

import copy
import re
from typing import Any

from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
from infini_local.core.runtime_authoring.schema import ENGINE_FN_CATALOG_V2, PLANNER_HIDDEN_ENGINE_FUNCTIONS
from infini_local.core.runtime_contracts import STRUCTURAL_ID_PATTERN


def _namespace_refs(value: Any, prefix: str) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str) and child.startswith("#/$defs/"):
                out[key] = "#/$defs/" + prefix + child.removeprefix("#/$defs/")
            else:
                out[key] = _namespace_refs(child, prefix)
        return out
    if isinstance(value, list):
        return [_namespace_refs(child, prefix) for child in value]
    return value


def _strip_schema_annotations(value: Any) -> Any:
    """Remove schema prose without deleting user fields named like annotations."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"title", "description", "default", "examples"}:
                continue
            if key == "properties" and isinstance(item, dict):
                out[key] = {
                    property_name: _strip_schema_annotations(property_schema)
                    for property_name, property_schema in item.items()
                }
            else:
                out[key] = _strip_schema_annotations(item)
        return out
    if isinstance(value, list):
        return [_strip_schema_annotations(item) for item in value]
    return value


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _json_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    return left == right


def _resolve_local_ref(root: dict[str, Any], ref: str) -> dict[str, Any] | None:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        return None
    resolved = root.get("$defs", {}).get(ref.removeprefix(prefix))
    return resolved if isinstance(resolved, dict) else None


def _strict_schema_errors(
    value: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any],
    path: str,
    limit: int = 64,
) -> list[dict[str, Any]]:
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
        resolved = _resolve_local_ref(root, ref)
        if resolved is None:
            add("unresolved_ref", path, ref)
            return errors
        return _strict_schema_errors(value, resolved, root=root, path=path, limit=limit)

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        branch_errors = [
            _strict_schema_errors(value, branch, root=root, path=path, limit=limit)
            for branch in any_of
            if isinstance(branch, dict)
        ]
        if not any(not branch for branch in branch_errors):
            add("any_of", path)
        return errors

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        branch_errors = [
            _strict_schema_errors(value, branch, root=root, path=path, limit=limit)
            for branch in one_of
            if isinstance(branch, dict)
        ]
        matching = sum(not branch for branch in branch_errors)
        if matching != 1:
            add("one_of", path, "exactly_one_schema", matching)
            if matching == 0 and branch_errors:
                errors.extend(min(branch_errors, key=len)[: max(0, limit - len(errors))])
        return errors

    if "const" in schema and not _json_values_equal(value, schema.get("const")):
        add("const", path, schema.get("const"), value)
    enum = schema.get("enum")
    if isinstance(enum, list) and not any(_json_values_equal(value, candidate) for candidate in enum):
        add("enum", path, enum, value)

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _json_type_matches(value, expected_type):
        add("type", path, expected_type, value)
        return errors

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        pattern = schema.get("pattern")
        if isinstance(min_length, int) and len(value) < min_length:
            add("min_length", path, min_length, len(value))
        if isinstance(max_length, int) and len(value) > max_length:
            add("max_length", path, max_length, len(value))
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            add("pattern", path, pattern, value)

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            add("min_items", path, min_items, len(value))
        if isinstance(max_items, int) and len(value) > max_items:
            add("max_items", path, max_items, len(value))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, child in enumerate(value):
                errors.extend(_strict_schema_errors(child, item_schema, root=root, path=f"{path}[{index}]", limit=max(0, limit - len(errors))))
                if len(errors) >= limit:
                    break

    if isinstance(value, dict):
        properties_candidate = schema.get("properties")
        properties: dict[str, Any] = properties_candidate if isinstance(properties_candidate, dict) else {}
        required_candidate = schema.get("required")
        required: list[Any] = required_candidate if isinstance(required_candidate, list) else []
        for key in required:
            if key not in value:
                add("required", f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    add("additional_property", f"{path}.{key}")
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                errors.extend(_strict_schema_errors(value[key], child_schema, root=root, path=f"{path}.{key}", limit=max(0, limit - len(errors))))
                if len(errors) >= limit:
                    break
    return errors[:limit]


def _engine_call_union() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    definitions: dict[str, Any] = {}
    visible_functions = sorted(set(ENGINE_FN_CATALOG_V2) - set(PLANNER_HIDDEN_ENGINE_FUNCTIONS))
    for fn in visible_functions:
        model = engine_params_model(fn)
        params_schema = copy.deepcopy(model.model_json_schema())
        prefix = fn + "__"
        local_defs = params_schema.pop("$defs", {})
        params_schema = _namespace_refs(params_schema, prefix)
        for name, definition in local_defs.items():
            definitions[prefix + name] = _namespace_refs(definition, prefix)
        variants.append({
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "callId": {"type": "string", "pattern": STRUCTURAL_ID_PATTERN},
                "fn": {"const": fn},
                "params": params_schema,
            },
            "required": ["callId", "fn", "params"],
        })
    return variants, definitions


def author_item_response_schema() -> dict[str, Any]:
    """Project canonical Pydantic engine-call models into the complete AuthorItem-v3 schema."""
    engine_variants, definitions = _engine_call_union()
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": definitions,
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 2, "maxLength": 80},

            "category": {"enum": ["weapon", "ammo", "tool", "accessory", "armor", "potion", "material", "furniture", "generic"]},
            "concept": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fantasy": {"type": "string", "minLength": 2, "maxLength": 500},
                    "mergeLogic": {"type": "string", "minLength": 2, "maxLength": 500},
                    "coreMechanic": {"type": "string", "minLength": 2, "maxLength": 500},
                },
                "required": ["fantasy", "mergeLogic", "coreMechanic"],
            },

            "runtimeContract": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "primaryVerb": {"type": "string", "minLength": 1, "maxLength": 160},
                    "controlStyle": {"enum": ["tap", "hold-to-channel", "passive", "toggle", "automatic", "right-click-alt", "combo", "on-hit-trigger"]},
                    "playerViewTimeline": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "phase": {"type": "string", "minLength": 1, "maxLength": 48},
                                "description": {"type": "string", "minLength": 1, "maxLength": 240},
                            },
                            "required": ["phase", "description"],
                        },
                    },
                },
                "required": ["primaryVerb", "controlStyle"],
            },
            "runtimePlan": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "resultKind": {"enum": ["weapon", "ammo", "consumable_weapon", "tool", "accessory", "armor", "potion", "material", "furniture", "generic"]},
                    "sourceRolePreservation": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"itemA": {"type": "string"}, "itemB": {"type": "string"}},
                        "required": ["itemA", "itemB"],
                    },
                    "engineCalls": {"type": "array", "items": {"oneOf": engine_variants}, "minItems": 1, "maxItems": 16},
                    "runtimeStateIntent": {"type": "string", "maxLength": 500},
                    "visualIntent": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "item": {"type": "string", "maxLength": 500},
                            "projectile": {"type": "string", "maxLength": 500},
                            "impact": {"type": "string", "maxLength": 500},
                            "vfxIntent": {"type": "string", "maxLength": 500},
                            "vfxAvoid": {"type": "string", "maxLength": 500},
                            "topology": {"enum": ["connected", "multipart_touching", "multipart_separated"]},
                            "partCountMin": {"type": "integer", "minimum": 1, "maximum": 8},
                            "partCountMax": {"type": "integer", "minimum": 1, "maximum": 8},
                            "parts": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1, "maxLength": 120},
                                "minItems": 1,
                                "maxItems": 8,
                            },
                            "arrangement": {"type": "string", "minLength": 1, "maxLength": 300},
                            "palette": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1, "maxLength": 48},
                                "maxItems": 8,
                            },
                            "preferredCanvasSize": {"enum": [32, 48, 64]},
                            "projectileCanvasSize": {"enum": [32, 48, 64]},
                            "projectileVisualFamily": {"type": "string", "minLength": 1, "maxLength": 120},
                            "projectileOrientation": {"type": "string", "minLength": 1, "maxLength": 120},
                            "animeReference": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "strength": {"enum": ["subtle", "strong"]},
                                    "source": {"type": "string", "minLength": 1, "maxLength": 120},
                                    "motifs": {
                                        "type": "array",
                                        "items": {"type": "string", "minLength": 1, "maxLength": 120},
                                        "minItems": 1,
                                        "maxItems": 6,
                                    },
                                },
                                "required": ["strength", "source", "motifs"],
                            },
                        },
                        "required": [
                            "item", "projectile", "impact", "vfxIntent", "vfxAvoid",
                        ],
                    },
                    "sourceReading": {"type": "string", "maxLength": 500},
                    "balanceIntent": {"type": "string", "maxLength": 500},
                    "anomalyFlags": {"type": "array", "items": {"type": "string"}, "maxItems": 16},
                },
                "required": ["resultKind", "sourceRolePreservation", "engineCalls", "runtimeStateIntent", "visualIntent", "sourceReading", "balanceIntent", "anomalyFlags"],
            },
        },
        "required": ["name", "category", "concept", "runtimeContract", "runtimePlan"],
    }
    return _strip_schema_annotations(schema)


def author_item_prompt_shape_card() -> dict[str, Any]:
    """Return a compact author card projected from the canonical response schema."""
    schema = author_item_response_schema()
    properties = schema["properties"]

    def enum_or_type(node: dict[str, Any]) -> Any:
        enum = node.get("enum")
        if isinstance(enum, list) and enum:
            if all(isinstance(value, str) for value in enum):
                return "|".join(enum)
            return copy.deepcopy(enum[0])
        return str(node.get("type") or "value")

    def value_card(node: dict[str, Any]) -> Any:
        if node.get("type") == "object":
            child_candidate = node.get("properties")
            child_properties: dict[str, Any] = child_candidate if isinstance(child_candidate, dict) else {}
            required = {str(key) for key in node.get("required") or []}
            out: dict[str, Any] = {}
            for key, child in child_properties.items():
                child_card = value_card(child)
                out[key] = (
                    child_card
                    if key in required or not isinstance(child_card, str)
                    else f"optional {child_card}"
                )
            return out
        if node.get("type") == "array":
            return "array"
        return enum_or_type(node)

    concept_schema = properties["concept"]
    concept_properties = concept_schema["properties"]
    runtime_schema = properties["runtimeContract"]
    runtime_properties = runtime_schema["properties"]
    plan_schema = properties["runtimePlan"]
    plan_properties = plan_schema["properties"]

    card: dict[str, Any] = {
        "name": enum_or_type(properties["name"]),
        "category": enum_or_type(properties["category"]),
        "concept": {
            key: enum_or_type(concept_properties[key])
            for key in concept_schema["required"]
        },
        "runtimeContract": {
            "primaryVerb": enum_or_type(runtime_properties["primaryVerb"]),
            "controlStyle": enum_or_type(runtime_properties["controlStyle"]),
            "playerViewTimeline": "optional array<{phase,description}>; include only relevant phases",
        },
        "runtimePlan": {
            key: (
                "array<{callId,fn,params}> using availableFunctions"
                if key == "engineCalls"
                else value_card(plan_properties[key])
            )
            for key in plan_schema["required"]
        },
    }
    return {key: card[key] for key in schema["required"]}


def _schema_allows_null(schema: dict[str, Any]) -> bool:
    schema_type = schema.get("type")
    if schema_type == "null" or (isinstance(schema_type, list) and "null" in schema_type):
        return True
    if schema.get("const", object()) is None:
        return True
    enum = schema.get("enum")
    if isinstance(enum, list) and None in enum:
        return True
    alternatives = schema.get("anyOf") or schema.get("oneOf")
    return bool(
        isinstance(alternatives, list)
        and any(isinstance(child, dict) and _schema_allows_null(child) for child in alternatives)
    )


def _provider_strict_projection(value: Any) -> Any:
    """Project sparse local JSON Schema into OpenAI strict-output shape.

    Local validation intentionally accepts sparse engine parameter objects. Strict
    providers instead require every declared object property to be present; optional
    values are represented as nullable. Semantic keywords unsupported by provider
    grammars stay owned by the ordinary local boundary after parsing.
    """
    if isinstance(value, list):
        return [_provider_strict_projection(child) for child in value]
    if not isinstance(value, dict):
        return value

    out: dict[str, Any] = {}
    for key, child in value.items():
        if key in {"contains", "minContains", "maxContains", "default"}:
            continue
        projected_key = "anyOf" if key == "oneOf" else key
        out[projected_key] = _provider_strict_projection(child)

    properties_candidate = out.get("properties")
    properties: dict[str, Any] = properties_candidate if isinstance(properties_candidate, dict) else {}
    if out.get("type") == "object" and properties:
        original_required = {str(name) for name in value.get("required") or []}
        for name, child in list(properties.items()):
            if name not in original_required and isinstance(child, dict) and not _schema_allows_null(child):
                properties[name] = {"anyOf": [child, {"type": "null"}]}
        out["required"] = list(properties)
    return out


def author_item_provider_response_schema() -> dict[str, Any]:
    """Strict provider grammar; local sparse validation remains author_item_response_schema."""
    return _provider_strict_projection(author_item_response_schema())


def author_item_repair_response_schema() -> dict[str, Any]:
    """Return the bounded same-author repair patch schema, never a second full AuthorItem."""
    full = author_item_response_schema()
    properties = full["properties"]
    plan = copy.deepcopy(properties["runtimePlan"])
    plan_properties = plan["properties"]
    plan["properties"] = {
        key: copy.deepcopy(plan_properties[key])
        for key in (
            "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
            "balanceIntent", "anomalyFlags",
        )
    }
    plan["required"] = []
    runtime_contract = properties["runtimeContract"]["properties"]
    visual_patch = copy.deepcopy(properties["runtimePlan"]["properties"]["visualIntent"])
    visual_patch["required"] = []
    return {
        "$schema": full["$schema"],
        "$defs": copy.deepcopy(full.get("$defs") or {}),
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": copy.deepcopy(properties["name"]),
            "category": copy.deepcopy(properties["category"]),
            "fantasy": copy.deepcopy(properties["concept"]["properties"]["fantasy"]),
            "mergeLogic": copy.deepcopy(properties["concept"]["properties"]["mergeLogic"]),
            "coreMechanic": copy.deepcopy(properties["concept"]["properties"]["coreMechanic"]),
            "primaryVerb": copy.deepcopy(runtime_contract["primaryVerb"]),
            "controlStyle": copy.deepcopy(runtime_contract["controlStyle"]),
            "playerViewTimeline": copy.deepcopy(runtime_contract["playerViewTimeline"]),
            "sourceRolePreservation": copy.deepcopy(
                properties["runtimePlan"]["properties"]["sourceRolePreservation"]
            ),
            "visualIntent": visual_patch,
            "runtimePlan": plan,
        },
    }


def author_item_provider_repair_response_schema() -> dict[str, Any]:
    return _provider_strict_projection(author_item_repair_response_schema())


def strict_author_item_repair_report(value: Any) -> dict[str, Any]:
    schema = author_item_repair_response_schema()
    errors = _strict_schema_errors(value, schema, root=schema, path="$")
    if isinstance(value, dict) and not value:
        errors.append({"path": "$", "kind": "empty_repair_patch"})
    return {
        "schema": "infini.author-item-v3-scoped-repair-validation.v1",
        "ok": not errors,
        "errors": errors,
    }


def _local_schema_branch(value: Any, schema: dict[str, Any]) -> dict[str, Any]:
    """Select a discriminator branch without attempting semantic validation."""
    alternatives = schema.get("oneOf") or schema.get("anyOf")
    if not isinstance(alternatives, list):
        return schema
    if isinstance(value, dict):
        for candidate in alternatives:
            if not isinstance(candidate, dict):
                continue
            properties = candidate.get("properties")
            if not isinstance(properties, dict):
                continue
            if all(
                not isinstance(rule, dict)
                or "const" not in rule
                or value.get(key) == rule["const"]
                for key, rule in properties.items()
            ):
                return candidate
    return schema


def project_provider_author_item_to_local(value: Any, schema: dict[str, Any] | None = None) -> Any:
    """Decode strict-provider nullable optionals into the canonical sparse object.

    Strict JSON-schema providers require every object property to be present, so
    ``author_item_provider_response_schema`` represents local optional fields as
    nullable.  ``null`` in those provider-only slots means omission, not authored
    gameplay. Required fields, truly nullable local fields, and unknown keys remain
    untouched so the ordinary local strict boundary can reject them.
    """
    local_schema = _local_schema_branch(value, schema or author_item_response_schema())
    if isinstance(value, list):
        item_schema = local_schema.get("items")
        return [
            project_provider_author_item_to_local(child, item_schema if isinstance(item_schema, dict) else {})
            for child in value
        ]
    if not isinstance(value, dict):
        return copy.deepcopy(value)

    properties_candidate = local_schema.get("properties")
    properties: dict[str, Any] = properties_candidate if isinstance(properties_candidate, dict) else {}
    required = {str(key) for key in local_schema.get("required") or []}
    out: dict[str, Any] = {}
    for key, child in value.items():
        child_schema = properties.get(key)
        if not isinstance(child_schema, dict):
            out[key] = copy.deepcopy(child)
            continue
        if child is None and key not in required and not _schema_allows_null(child_schema):
            continue
        out[key] = project_provider_author_item_to_local(child, child_schema)
    return out


def _explicit_physical_throw_movement_errors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    plan = value.get("runtimePlan")
    calls = plan.get("engineCalls") if isinstance(plan, dict) else None
    if not isinstance(calls, list):
        return []
    errors: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or call.get("fn") != "shoot_projectile":
            continue
        params = call.get("params")
        if not isinstance(params, dict):
            continue
        delivery = str(params.get("delivery") or "").strip().lower()
        runtime_family = str(params.get("runtimeFamily") or "").strip().lower()
        if (delivery == "throw" or runtime_family == "throw") and "movement" not in params:
            errors.append({
                "path": f"$.runtimePlan.engineCalls[{index}].params.movement",
                "kind": "required_for_physical_throw",
                "expected": "explicit gravity_arc or explicit straight/other authored movement",
            })
    return errors


def _engine_call_identity_errors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    plan = value.get("runtimePlan")
    calls = plan.get("engineCalls") if isinstance(plan, dict) else None
    if not isinstance(calls, list):
        return []
    first_index_by_id: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        if not isinstance(call, dict):
            continue
        call_id = str(call.get("callId") or "").strip()
        if not call_id:
            continue
        if call_id in first_index_by_id:
            errors.append({
                "path": f"$.runtimePlan.engineCalls[{index}].callId",
                "kind": "duplicate_call_id",
                "callId": call_id,
                "duplicateOf": first_index_by_id[call_id],
            })
        else:
            first_index_by_id[call_id] = index
    return errors


def _visual_intent_errors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    plan = value.get("runtimePlan")
    intent = plan.get("visualIntent") if isinstance(plan, dict) else None
    if not isinstance(intent, dict):
        return []
    minimum = intent.get("partCountMin")
    maximum = intent.get("partCountMax")
    errors: list[dict[str, Any]] = []
    if (minimum is None) != (maximum is None):
        return [{
            "path": "$.runtimePlan.visualIntent",
            "kind": "part_count_range_requires_both_bounds",
        }]
    if isinstance(minimum, int) and isinstance(maximum, int):
        if minimum > maximum:
            errors.append({
                "path": "$.runtimePlan.visualIntent.partCountMin",
                "kind": "part_count_range_inverted",
                "expected": "partCountMin <= partCountMax",
            })
        topology = str(intent.get("topology") or "")
        if topology == "connected" and (minimum != 1 or maximum != 1):
            errors.append({
                "path": "$.runtimePlan.visualIntent",
                "kind": "connected_topology_requires_one_significant_body",
            })
        if topology == "multipart_separated" and maximum < 2:
            errors.append({
                "path": "$.runtimePlan.visualIntent.partCountMax",
                "kind": "separated_topology_requires_multiple_bodies",
            })
    return errors


def strict_author_item_v3_report(value: Any) -> dict[str, Any]:
    schema = author_item_response_schema()
    errors = _strict_schema_errors(value, schema, root=schema, path="$")
    errors.extend(_engine_call_identity_errors(value))
    errors.extend(_explicit_physical_throw_movement_errors(value))
    errors.extend(_visual_intent_errors(value))
    return {
        "schema": "infini.author-item-v3-local-validation.v1",
        "ok": not errors,
        "errors": errors,
    }


__all__ = [
    "author_item_response_schema",
    "author_item_provider_response_schema",
    "author_item_repair_response_schema",
    "author_item_provider_repair_response_schema",
    "author_item_prompt_shape_card",
    "project_provider_author_item_to_local",
    "strict_author_item_v3_report",
    "strict_author_item_repair_report",
]
