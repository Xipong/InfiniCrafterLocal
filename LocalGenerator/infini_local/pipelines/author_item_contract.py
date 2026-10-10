from __future__ import annotations

import copy
import json
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring import (
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    apply_repair_patch,
    author_item_repair_schema as _repair_schema,
    author_item_response_schema as _author_schema,
    strict_repair_shape_report,
    validate_runtime_program,
)
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_AUTHOR_PATH,
    PRIMARY_ENTITY_FIELD,
    PRIMARY_ENTITY_SELECTION_FIELD,
    strict_schema_errors,
)


PRIMARY_REPAIR_SYSTEM_RULE = (
    f"Use {PRIMARY_ENTITY_SELECTION_FIELD} whenever its repair transaction is enabled."
)


def primary_entity_llm_invariant() -> dict[str, Any]:
    return {
        "exactlyOnePrimaryEntity": True,
        "authoredField": PRIMARY_ENTITY_AUTHOR_PATH,
        "primaryRule": (
            "Select one existing entity id for lifecycle/held representation, not by damage or mere spawning. "
            "Use the item_body for item-graphic/body-contact representation. When all active bindings spawn "
            "the same entity, all have contactDamage=false and configure_item_use.hideUseGraphic=true, select "
            "that exact spawn target. This selector does not create movement, a controller, damage or a concurrency cap. "
            "A movement/controller that claims held-projectile representation does so only for this primary entity. "
            "Binding/call rows do not carry role; Lowery derives wire roles "
            "by exact target equality with primaryEntityId."
        ),
    }


def author_item_response_schema() -> dict[str, Any]:
    return copy.deepcopy(_author_schema())


def _binding_prompt_shape_card() -> dict[str, Any]:
    """One model-visible binding shape shared by Author and Repair cards."""

    return {
        "id": "stable_binding_id",
        "input": "primary_use|alternate_use|hold|equipped",
        "usePolicy": {
            "action": {
                "kind": "catalog action",
                "targetId": "exact existing entity id compatible with the selected action.targets",
                "placementCallId": "include only for place_item; otherwise omit",
            },
            "stackCost": "exact integer 0 or 1 allowed by the selected input/action",
            "contactDamage": (
                "boolean body-hitbox lane for this active use; independent from action/target, so "
                "spawn_entity + true means item-body contact and projectile spawn on the same use; "
                "must be false for place_item, hold, and equipped"
            ),
        },
    }


def author_item_prompt_shape_card() -> dict[str, Any]:
    report_properties = _author_schema()["properties"]["realization"]["properties"]
    return {
        # This order is model-facing: non-binding intent, executable mechanics,
        # then the same Author's account and self-evaluation of the result.
        "root": ["name", "category", "concept", "runtimeProgram", "realization"],
        "name": "non-empty string",
        "category": "combat|tool|equipment|placeable|consumable|material|hybrid|generic",
        "concept": {
            "literalSynthesis": (
                "non-empty string: preserve the actual parents' concrete appearance/identity, including "
                "deliberately surreal physical combinations. Use only supplied parent identities; "
                "illustrative examples are not additional parents. Literal appearance does not require "
                "inheriting every parent capability."
            ),
            "coreMechanic": (
                "non-empty string: choose one clear core gameplay loop with purposeful mechanics. "
                "Prefer simple, immediately useful play at the supplied progression; add complexity "
                "only when it serves that loop. This is design guidance, not a capability restriction."
            ),
            "parentAContribution": (
                "non-empty string: explain this actual parent's appearance/identity and purposeful "
                "mechanical contribution; copying every parent capability is not required."
            ),
            "parentBContribution": (
                "non-empty string: explain this actual parent's appearance/identity and purposeful "
                "mechanical contribution; copying every parent capability is not required."
            ),
            "playerExperience": "non-empty string: explain practical player value and deliberate costs of the selected mechanics",
            "plannedPlayerActions": [{
                "input": "primary_use|alternate_use|hold|equipped|passive_or_event",
                "intent": (
                    "non-binding initial player-facing intent: include extra control modes only for "
                    "meaningful utility. A parent createTile fact permits placement; it does not require it. "
                    "For alternate placement, identify the placed target's meaningful utility worth "
                    "escrowing the same generated item: accepted placement removes it from inventory "
                    "and makes it unavailable until the tile breaks and returns it. Explicit useful "
                    "placement and multiple purposeful actions remain legal."
                ),
            }],
        },
        "runtimeProgram": {
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
            "schema": RUNTIME_PROGRAM_SCHEMA,
            PRIMARY_ENTITY_FIELD: "exact existing entity id chosen once by the model",
            "entities": [{"id": "stable_id", "kind": "catalog entity kind"}],
            "bindings": [_binding_prompt_shape_card()],
            "calls": [{"id": "stable_id", "fn": "catalog capability", "target": "existing compatible entity id from fn.targets", "params": {"all non-optional and conditional params": "exact card keys and typed values; optional fields only when selected"}}],
        },
        "realization": {
            "description": (
                "final interpretation of the emitted runtimeProgram, not an observed execution; "
                f"string minLength={report_properties['description']['minLength']}, "
                f"maxLength={report_properties['description']['maxLength']} Unicode code points"
            ),
            "playerExperience": (
                "what the final executable program lets the player experience; "
                f"string minLength={report_properties['playerExperience']['minLength']}, "
                f"maxLength={report_properties['playerExperience']['maxLength']} Unicode code points"
            ),
            "selfEvaluation": {
                "planVsProgram": {
                    "verdict": "aligned|changed|uncertain",
                    "summary": "diagnostic comparison of concept with the emitted program",
                    "actionChecks": [{
                        "plannedIntent": "one exact plannedPlayerActions intent, or 'no corresponding initial action' for an added lane",
                        "implementedBehavior": "what runtimeProgram actually implements for it",
                        "runtimeRefs": ["existing entity, binding, or call id"],
                        "result": "aligned|changed|dropped|added|uncertain",
                        "intentionality": "intentional|accidental|uncertain",
                        "reason": "why this action is aligned, changed, dropped, added, or uncertain",
                    }],
                },
                "programVsReport": {
                    "verdict": "aligned|mismatch|uncertain",
                    "summary": "diagnostic comparison of the emitted program with description/playerExperience",
                    "behaviorChecks": [{
                        "runtimeRefs": ["existing entity, binding, or call id"],
                        "programBehavior": "one literal executable behavior lane",
                        "reportedBehavior": "what description/playerExperience says about that lane",
                        "result": "aligned|mismatch|omitted|uncertain",
                        "reason": "why this lane is aligned, mismatched, omitted, or uncertain",
                    }],
                },
            },
        },
        "forbidden": [
            "weapon archetype selector",
            "family-derived movement/attachment/delivery",
            "compiler receipts",
            "gameplay claimed only in prose rather than runtimeProgram",
        ],
    }


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
            (left, right) for left, right in remaining
            if not any(_literal_equal(a, b) for a in domains[left][path] for b in domains[right][path])
        }
        if distinguished:
            selected.append(path)
            remaining -= distinguished
    return selected if not remaining else []


def _union_branch_index(value: Any, branches: list[Mapping[str, Any]], paths: list[tuple[str, ...]] | None = None) -> int | None:
    if paths is None:
        paths = _union_discriminator_paths(branches)
    if not paths and len(branches) == 1:
        # A request-scoped union can contain one capability. Its literal fn
        # still guards nullable decoding; object type alone must not select
        # that branch for an unknown/out-of-scope function.
        paths = list(_required_finite_domains(branches[0]))
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
            # Only proven non-overlapping JSON types; never validate whole rows
            # to choose a different capability because some parameter is invalid.
            matches = _disjoint_union_types(branches) and not strict_schema_errors(value, {"type": branch["type"]})
        if matches:
            candidates.append(index)
    return candidates[0] if len(candidates) == 1 else None


def _disjoint_union_types(branches: list[Mapping[str, Any]]) -> bool:
    types = [branch.get("type") for branch in branches]
    # integer and number overlap; these non-numeric JSON kinds do not.
    return all(isinstance(kind, str) and kind in {"string", "null", "object", "array", "boolean"} for kind in types) and len(set(types)) == len(types)


def _finite_required_cases(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expand only a required finite selector + required-only consequent.

    Partition the original enum before nullable encoding: conditional additions
    stay non-null in the matching case, optional in every other case.
    """
    condition, consequent = schema.get("if"), schema.get("then")
    if (
        schema.get("type") != "object" or "else" in schema
        or not isinstance(condition, Mapping) or set(condition) != {"properties", "required"}
        or not isinstance(consequent, Mapping) or set(consequent) != {"required"}
        or not isinstance(condition["properties"], Mapping) or len(condition["properties"]) != 1
    ):
        raise ValueError("Unproved provider conditional: expected required finite selector and required-only then")
    selector, predicate = next(iter(condition["properties"].items()))
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    child = properties.get(selector)
    additions = consequent["required"]
    if (
        condition["required"] != [selector] or selector not in required
        or not isinstance(predicate, Mapping) or set(predicate) != {"const"}
        or not isinstance(child, Mapping) or "const" in child
        or not isinstance(child.get("enum"), list) or not child["enum"]
        or not isinstance(additions, list) or not additions
        or any(not isinstance(key, str) or key not in properties for key in additions)
        or any(type(value) not in {str, bool, int, float, type(None)} for value in child["enum"])
        or not any(_literal_equal(value, predicate["const"]) for value in child["enum"])
    ):
        raise ValueError("Unproved provider conditional: incomplete finite discriminator or unknown required addition")
    cases = []
    for value in child["enum"]:
        case = copy.deepcopy({key: value for key, value in schema.items() if key not in {"if", "then"}})
        case["properties"][selector]["enum"] = [value]
        if _literal_equal(value, predicate["const"]):
            case["required"] = [*required, *(key for key in additions if key not in required)]
        cases.append(case)
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
            "anyOf" in schema or not isinstance(branches, list) or not branches
            or not all(isinstance(branch, Mapping) for branch in branches)
            or not (_disjoint_union_types(branches) or _union_discriminator_paths(branches))
        ):
            raise ValueError("Unproved provider oneOf: branches need complete disjoint required finite discriminators or types")
        out["anyOf"] = out.pop("oneOf")
    return out


def _provider_strict_projection(schema: Any) -> Any:
    """Lossless provider-only subset + optional-property transport encoding.

    Unsupported/unproved compositions fail closed. Do not recurse through JSON
    literals or owner annotations as if they were schemas.
    """
    if not isinstance(schema, Mapping):
        return copy.deepcopy(schema)
    source = _provider_subset_shape(schema)
    out = copy.deepcopy(source)
    for key in ("properties", "$defs"):
        if isinstance(source.get(key), Mapping):
            out[key] = {name: _provider_strict_projection(child) for name, child in source[key].items()}
    if isinstance(source.get("items"), Mapping):
        out["items"] = _provider_strict_projection(source["items"])
    if isinstance(source.get("anyOf"), list):
        out["anyOf"] = [_provider_strict_projection(branch) for branch in source["anyOf"]]
    if "const" in source:
        try:
            json.dumps(source["const"], allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Unproved provider const: not a finite JSON literal") from exc
    if "const" in source and "type" not in source:
        # Entailed literal type, including number (not integer) for float const.
        literal_type = {str: "string", bool: "boolean", int: "integer", float: "number", type(None): "null", list: "array", dict: "object"}.get(type(source["const"]))
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


def author_item_provider_response_schema() -> dict[str, Any]:
    return _provider_strict_projection(author_item_response_schema())


def author_item_repair_response_schema(*, capability_names: Iterable[str] | None = None) -> dict[str, Any]:
    return copy.deepcopy(_repair_schema(capability_names=capability_names))


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
            placeholders[key] = [_binding_prompt_shape_card()]
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
        if key == "realizationReplacement":
            placeholders[key] = copy.deepcopy(author_item_prompt_shape_card()["realization"])
            continue
        if key == PRIMARY_ENTITY_SELECTION_FIELD:
            placeholders[key] = f"entity_id chosen from repairScope.repairTransactions.{PRIMARY_ENTITY_SELECTION_FIELD}.candidateEntityIds, or null"
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


def author_item_provider_repair_response_schema(
    *_: Any, local_schema: Mapping[str, Any] | None = None, **__: Any,
) -> dict[str, Any]:
    return _provider_strict_projection(
        local_schema if local_schema is not None else author_item_repair_response_schema())


def author_item_targeted_repair_delta_schema() -> dict[str, Any]:
    return author_item_repair_response_schema()


def author_item_provider_targeted_repair_delta_schema(*_: Any, **__: Any) -> dict[str, Any]:
    return author_item_provider_repair_response_schema()


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
                and isinstance(wrapper, list) and len(wrapper) == 2
                and wrapper[1] == {"type": "null"}
                and wrapper[0] == _provider_strict_projection(child_local)
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
    local_schema: Mapping[str, Any] | None = None,
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
    local = local_schema if local_schema is not None else author_item_repair_response_schema()
    return _project_nullable_transport(value, local, provider)


def project_provider_author_item_to_local(
    value: Any, *, response_format: Mapping[str, Any] | None = None,
) -> Any:
    if not isinstance(response_format, Mapping) or response_format.get("type") != "json_schema":
        return copy.deepcopy(value)
    return project_provider_nullable_optionals_to_local(
        value, author_item_response_schema(), response_format=response_format,
    )


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
    "PRIMARY_REPAIR_SYSTEM_RULE",
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
    "primary_entity_llm_invariant",
    "strict_author_item_repair_report",
    "strict_author_item_targeted_repair_delta_report",
    "strict_author_item_v3_report",
]
