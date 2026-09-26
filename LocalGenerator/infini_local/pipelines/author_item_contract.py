from __future__ import annotations

import copy
from typing import Any, Mapping

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
            "the same entity, contactDamage=false and configure_item_use hides the item graphic, that exact "
            "spawn target owns lifecycle/held representation. Otherwise another entity requires explicitly "
            "authored lifecycle/held ownership. Binding/call rows do not carry role; Lowery derives wire roles "
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
    return {
        # This order is model-facing: non-binding intent, executable mechanics,
        # then the same Author's account and self-evaluation of the result.
        "root": ["name", "category", "concept", "runtimeProgram", "realization"],
        "name": "non-empty string",
        "category": "combat|tool|equipment|placeable|consumable|material|hybrid|generic",
        "concept": {
            "literalSynthesis": "non-empty string",
            "coreMechanic": "non-empty string",
            "parentAContribution": "non-empty string",
            "parentBContribution": "non-empty string",
            "playerExperience": "non-empty string",
            "plannedPlayerActions": [{
                "input": "primary_use|alternate_use|hold|equipped|passive_or_event",
                "intent": "non-binding initial player-facing intent",
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
            "description": "final interpretation of the emitted runtimeProgram, not an observed execution",
            "playerExperience": "what the final executable program lets the player experience",
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
