"""Lossless provider-schema projection and nullable optional transport.

This adapter has no stage-specific default schema or generation dependencies.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from infini_local.core.schema_validation import strict_schema_errors


def provider_nullable_transport_rule(response_format: Mapping[str, Any] | None) -> str:
    if not isinstance(response_format, Mapping) or response_format.get("type") != "json_schema":
        return ""
    return (
        " JSON Schema nullable transport: only when the supplied response schema requires an otherwise "
        "optional object property and explicitly allows null, emit null to represent omission. "
        "This is transport encoding, not an authored value or permission to default invalid values. "
        "Omission retains its meaning in the requested output contract. "
        "Never use this rule for unknown keys, required non-null fields, or array elements. "
        "If no JSON Schema is supplied (json_object/off), omit optional fields instead; explicit null "
        "is not an omission alias."
    )


def _literal_equal(left: Any, right: Any) -> bool:
    # JSON Schema numeric equality includes 1 == 1.0, never true == 1.
    if type(left) in {int, float} and type(right) in {int, float}:
        return left == right
    return type(left) is type(right) and left == right


def _required_finite_domains(schema: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], list[Any]]:
    """Only required property paths can prove complete, disjoint selectors."""
    domain = [schema["const"]] if "const" in schema else schema.get("enum")
    result = {}
    if isinstance(domain, list) and domain and all(type(value) in {str, bool, int, float, type(None)} for value in domain):
        result[prefix] = domain
    if schema.get("type") == "object":
        properties = schema.get("properties") or {}
        for key in schema.get("required") or []:
            child = properties.get(key)
            if isinstance(child, Mapping):
                result.update(_required_finite_domains(child, (*prefix, key)))
    return result


def _union_discriminator_paths(branches: list[Mapping[str, Any]]) -> list[tuple[str, ...]]:
    domains = [_required_finite_domains(branch) for branch in branches]
    common = set.intersection(*(set(domain) for domain in domains)) if domains else set()
    remaining = {(left, right) for left in range(len(branches)) for right in range(left + 1, len(branches))}
    selected = []
    for path in sorted(common):
        distinguished = {
            (left, right)
            for left, right in remaining
            if not any(_literal_equal(a, b) for a in domains[left][path] for b in domains[right][path])
        }
        if distinguished:
            selected.append(path)
            remaining -= distinguished
    return selected if not remaining else []


def _required_object_schemas(schema: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Mapping[str, Any]]:
    """Only an explicit object type and required ancestors prove key presence."""
    if schema.get("type") != "object":
        return {}
    result = {prefix: schema}
    properties = schema.get("properties") or {}
    for key in schema.get("required") or []:
        child = properties.get(key)
        if isinstance(child, Mapping):
            result.update(_required_object_schemas(child, (*prefix, key)))
    return result


def _selector_at_path(path: tuple[str, ...], selector: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(selector))
    for key in reversed(path):
        result = {"type": "object", "properties": {key: result}, "required": [key]}
    return result


def _object_key_selector(schema: Mapping[str, Any]) -> dict[str, Any]:
    # This selects only the explicit structural alternative. No numeric bounds,
    # optional values or unrelated gameplay constraints participate in selection.
    result = {"type": "object", "required": list(schema.get("required") or [])}
    if schema.get("additionalProperties") is False and not schema.get("patternProperties"):
        result.update(properties={key: {} for key in schema.get("properties") or {}}, additionalProperties=False)
    return result


def _union_pair_selectors(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return narrow, disjoint guards only when a pair's separation is proved."""
    kinds = [branch.get("type") for branch in (left, right)]
    known = {"string", "null", "object", "array", "boolean", "integer", "number"}
    if all(isinstance(kind, str) and kind in known for kind in kinds):
        # JSON integer is contained in number; bool is a separate JSON kind.
        domains = [{"integer", "number"} if kind in {"integer", "number"} else {kind} for kind in kinds]
        if domains[0].isdisjoint(domains[1]):
            return {"type": kinds[0]}, {"type": kinds[1]}
    finite = [_required_finite_domains(branch) for branch in (left, right)]
    for path in sorted(finite[0].keys() & finite[1].keys()):
        if not any(_literal_equal(a, b) for a in finite[0][path] for b in finite[1][path]):
            return tuple(_selector_at_path(path, {"enum": domain[path]}) for domain in finite)
    objects = [_required_object_schemas(branch) for branch in (left, right)]
    for path in sorted(objects[0].keys() & objects[1].keys()):
        pair = [objects[0][path], objects[1][path]]
        for required_side, closed_side in (pair, pair[::-1]):
            if (
                closed_side.get("additionalProperties") is False
                and not closed_side.get("patternProperties")
                and set(required_side.get("required") or []) - set(closed_side.get("properties") or {})
            ):
                return tuple(_selector_at_path(path, _object_key_selector(branch)) for branch in pair)
    return None


def _union_branch_index(value: Any, branches: list[Mapping[str, Any]], paths: list[tuple[str, ...]] | None = None) -> int | None:
    if paths is None:
        paths = _union_discriminator_paths(branches)
    if not paths and len(branches) == 1:
        # A request-scoped union can contain one capability. Its literal fn
        # still guards nullable decoding; object type alone must not select
        # that branch for an unknown/out-of-scope function.
        paths = list(_required_finite_domains(branches[0]))
    pairwise = _pairwise_union_selectors(branches) if not paths and len(branches) > 1 else None
    candidates = []
    for index, branch in enumerate(branches):
        if paths:
            domains = _required_finite_domains(branch)
            matches = True
            for path in paths:
                actual = value
                for key in path:
                    if not isinstance(actual, Mapping) or key not in actual:
                        matches = False
                        break
                    actual = actual[key]
                if not matches or not any(_literal_equal(actual, expected) for expected in domains.get(path, [])):
                    matches = False
                    break
        else:
            # Validate only the proven selector guards, never complete rows: an
            # invalid neighbouring parameter must remain available to Repair.
            matches = (
                all(not strict_schema_errors(value, selector) for selector in pairwise[index])
                if pairwise is not None
                else _disjoint_union_types(branches) and not strict_schema_errors(value, {"type": branch["type"]})
            )
        if matches:
            candidates.append(index)
    return candidates[0] if len(candidates) == 1 else None


def _disjoint_union_types(branches: list[Mapping[str, Any]]) -> bool:
    types = [branch.get("type") for branch in branches]
    # integer and number overlap; these non-numeric JSON kinds do not.
    return all(isinstance(kind, str) and kind in {"string", "null", "object", "array", "boolean"} for kind in types) and len(
        set(types)
    ) == len(types)


def _finite_required_cases(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand only a required finite selector + required-only consequent.

    Partition the original enum before nullable encoding: conditional additions
    stay non-null in the matching case, optional in every other case.
    """
    condition, consequent = schema.get("if"), schema.get("then")
    if (
        schema.get("type") != "object"
        or "else" in schema
        or not isinstance(condition, Mapping)
        or set(condition) != {"properties", "required"}
        or not isinstance(consequent, Mapping)
        or set(consequent) != {"required"}
        or not isinstance(condition["properties"], Mapping)
        or len(condition["properties"]) != 1
    ):
        raise ValueError("Unproved provider conditional: expected required finite selector and required-only then")
    selector, predicate = next(iter(condition["properties"].items()))
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    child = properties.get(selector)
    additions = consequent["required"]
    if (
        condition["required"] != [selector]
        or selector not in required
        or not isinstance(predicate, Mapping)
        or set(predicate) != {"const"}
        or not isinstance(child, Mapping)
        or "const" in child
        or not isinstance(child.get("enum"), list)
        or not child["enum"]
        or not isinstance(additions, list)
        or not additions
        or any(not isinstance(key, str) or key not in properties for key in additions)
        or any(type(value) not in {str, bool, int, float, type(None)} for value in child["enum"])
        or not any(_literal_equal(value, predicate["const"]) for value in child["enum"])
    ):
        raise ValueError("Unproved provider conditional: incomplete finite discriminator or unknown required addition")
    # Only requiredness differs across these cases. Share one complete branch
    # per identical required set instead of copying it once per enum literal.
    # Enum values remain explicit, disjoint and in their original order.
    cases_by_required: dict[tuple[str, ...], dict[str, Any]] = {}
    for value in child["enum"]:
        case_required = [*required]
        if _literal_equal(value, predicate["const"]):
            case_required.extend(key for key in additions if key not in case_required)
        signature = tuple(case_required)
        if signature not in cases_by_required:
            case = copy.deepcopy({key: child for key, child in schema.items() if key not in {"if", "then"}})
            case["properties"][selector]["enum"] = []
            case["required"] = case_required
            cases_by_required[signature] = case
        cases_by_required[signature]["properties"][selector]["enum"].append(copy.deepcopy(value))
    cases = list(cases_by_required.values())
    if len(cases) > 1 and not _union_discriminator_paths(cases):
        raise ValueError("Unproved provider conditional: overlapping enum cases")
    return cases


def _provider_subset_shape(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Shallow, exact-equivalence normalization; never alter the local owner."""
    forbidden = {"allOf", "not", "dependentRequired", "dependentSchemas"} & schema.keys()
    if forbidden:
        raise ValueError(f"Unproved provider composition: {sorted(forbidden)}")
    if {"if", "then", "else"} & schema.keys():
        return {"anyOf": _finite_required_cases(schema)}
    out = copy.deepcopy(dict(schema))
    if "oneOf" in schema:
        branches = schema["oneOf"]
        if (
            "anyOf" in schema
            or not isinstance(branches, list)
            or not branches
            or not all(isinstance(branch, Mapping) for branch in branches)
            or not (
                _disjoint_union_types(branches) or _union_discriminator_paths(branches) or _pairwise_union_selectors(branches) is not None
            )
        ):
            raise ValueError(
                "Unproved provider oneOf: every pair needs disjoint types, required finite domains or required keys forbidden by a closed object"
            )
        out["anyOf"] = out.pop("oneOf")
    return out


def _provider_strict_projection(schema: Any, *, omit_annotations: bool = False) -> Any:
    """Lossless provider-only subset + optional-property transport encoding.

    Unsupported/unproved compositions fail closed. Do not recurse through JSON
    literals or owner annotations as if they were schemas.
    """
    if not isinstance(schema, Mapping):
        return copy.deepcopy(schema)
    source = _provider_subset_shape(schema)
    # Gameplay Author/Repair cards already carry these annotations. Other callers
    # (including Visual) keep their original schema guidance unless opted in.
    out = {
        key: copy.deepcopy(child)
        for key, child in source.items()
        if not omit_annotations or (key != "description" and not key.startswith("x-infini-"))
    }
    for key in ("properties", "$defs"):
        if isinstance(source.get(key), Mapping):
            out[key] = {name: _provider_strict_projection(child, omit_annotations=omit_annotations) for name, child in source[key].items()}
    if isinstance(source.get("items"), Mapping):
        out["items"] = _provider_strict_projection(source["items"], omit_annotations=omit_annotations)
    if isinstance(source.get("anyOf"), list):
        out["anyOf"] = [_provider_strict_projection(branch, omit_annotations=omit_annotations) for branch in source["anyOf"]]
    if "const" in source:
        try:
            json.dumps(source["const"], allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Unproved provider const: not a finite JSON literal") from exc
    if "const" in source and "type" not in source:
        # Entailed literal type, including number (not integer) for float const.
        literal_type = {
            str: "string",
            bool: "boolean",
            int: "integer",
            float: "number",
            type(None): "null",
            list: "array",
            dict: "object",
        }.get(type(source["const"]))
        if literal_type is None:
            raise ValueError("Unproved provider const: not a JSON literal")
        out["type"] = literal_type
    props = out.get("properties")
    if isinstance(props, dict):
        local_required = set(source.get("required") or [])
        for key, child in list(props.items()):
            if key not in local_required and isinstance(child, dict):
                props[key] = {"anyOf": [child, {"type": "null"}]}
        out["required"] = list(props)
    return out


def _project_nullable_transport(value: Any, local: Mapping[str, Any], provider: Mapping[str, Any]) -> Any:
    """Invert only declared optional-property wrappers, never authored containers.

    Union selection uses the schema owner's literal discriminators, not validation
    success: an unrelated invalid value must remain available to Repair unchanged.
    Ambiguous/unknown variants are copied intact for the canonical validator.
    """
    local = _provider_subset_shape(local)
    branches, sent_branches = local.get("anyOf"), provider.get("anyOf")
    if isinstance(branches, list):
        if not isinstance(sent_branches, list) or not all(isinstance(branch, Mapping) for branch in sent_branches):
            return copy.deepcopy(value)
        paths = _union_discriminator_paths(branches)
        index = _union_branch_index(value, branches, paths)
        sent_index = _union_branch_index(value, sent_branches, paths)
        if index is None or sent_index is None:
            return copy.deepcopy(value)
        return _project_nullable_transport(value, branches[index], sent_branches[sent_index])
    if isinstance(value, dict):
        local_props = local.get("properties") or {}
        sent_props = provider.get("properties") or {}
        required = local.get("required") or []
        out = {}
        for key, child in value.items():
            child_local = local_props.get(key)
            child_sent = sent_props.get(key)
            if not isinstance(child_local, Mapping) or not isinstance(child_sent, Mapping):
                out[key] = copy.deepcopy(child)
                continue
            wrapper = child_sent.get("anyOf")
            nullable_optional = (
                key not in required
                and key in (provider.get("required") or [])
                and isinstance(wrapper, list)
                and len(wrapper) == 2
                and wrapper[1] == {"type": "null"}
                # Both exact supported projections are lossless; Visual retains
                # annotations while Gameplay Author/Repair omit their duplication.
                and (
                    wrapper[0] == _provider_strict_projection(child_local, omit_annotations=True)
                    or wrapper[0] == _provider_strict_projection(child_local)
                )
            )
            if nullable_optional and isinstance(wrapper, list):
                if child is None:
                    continue
                child_sent = wrapper[0]
            out[key] = _project_nullable_transport(child, child_local, child_sent)
        return out
    if isinstance(value, list):
        local_items, sent_items = local.get("items"), provider.get("items")
        if isinstance(local_items, Mapping) and isinstance(sent_items, Mapping):
            return [_project_nullable_transport(child, local_items, sent_items) for child in value]
    return copy.deepcopy(value)


def project_provider_nullable_optionals_to_local(
    value: Any,
    local_schema: Mapping[str, Any],
    *,
    response_format: Mapping[str, Any] | None = None,
) -> Any:
    # No schema transport means null is an authored value, not omission.
    if not isinstance(response_format, Mapping) or response_format.get("type") != "json_schema":
        return copy.deepcopy(value)
    envelope = response_format.get("json_schema")
    provider = envelope.get("schema") if isinstance(envelope, Mapping) else None
    if not isinstance(provider, Mapping):
        return copy.deepcopy(value)
    local = local_schema
    return _project_nullable_transport(value, local, provider)


def _pairwise_union_selectors(branches: list[Mapping[str, Any]]) -> list[list[dict[str, Any]]] | None:
    """Every pair must be disjoint, possibly by different declared selectors."""
    selectors: list[list[dict[str, Any]]] = [[] for _branch in branches]
    for left in range(len(branches)):
        for right in range(left + 1, len(branches)):
            pair = _union_pair_selectors(branches[left], branches[right])
            if pair is None:
                return None
            selectors[left].append(pair[0])
            selectors[right].append(pair[1])
    return selectors
