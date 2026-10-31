"""Exact Repair scope grammar and validator-code policy."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.runtime_authoring.capability_registry import BINDING_ACTION_REGISTRY, CAPABILITY_REGISTRY, INPUT_KIND_REGISTRY
from infini_local.core.runtime_authoring.program_schema import PRIMARY_ENTITY_SELECTION_FIELD, binding_schema
from infini_local.core.runtime_authoring.repair.facts import _mapping, _values
from infini_local.core.runtime_authoring.validator import VALIDATION_ERROR_CODES

RUNTIME_REPAIR_SCOPE_SCHEMA = "infini.runtime-repair-scope.v6"


RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA = "infini.runtime-repair-scope-report.v6"


RUNTIME_REPAIR_FILTER_REPORT_SCHEMA = "infini.runtime-repair-filter-report.v3"


# Every deterministic validator code has an explicit Repair strategy. A new
# code without policy must fail closed, never widen to a whole-item retry.
REPAIR_ERROR_POLICY: dict[str, dict[str, Any]] = {
    "unsupported_param_target_kind": {"strategy": "patch_exact_call_param", "llmRepairable": True, "allowNodeDelete": False},
    "unsupported_param_variant_target_kind": {"strategy": "patch_exact_call_param", "llmRepairable": True, "allowNodeDelete": False},
    "unordered_param_range": {"strategy": "patch_exact_call_param", "llmRepairable": True, "allowNodeDelete": False},
    "incompatible_param_variant": {"strategy": "patch_exact_call_param", "llmRepairable": True, "allowNodeDelete": False},
    "consumer_representability": {"strategy": "patch_exact_param", "llmRepairable": True, "allowNodeDelete": False},
    "ambiguous_global_id": {"strategy": "delete_exact_duplicate", "llmRepairable": True, "allowNodeDelete": True},
    "binding_dependency": {"strategy": "synthesize_exact_dependency_or_delete_exact_binding", "llmRepairable": True, "allowNodeDelete": True},
    "missing_effect_group": {"strategy": "retarget_exact_effect_group", "llmRepairable": True, "allowNodeDelete": False},
    "invalid_held_effect_group": {"strategy": "retarget_exact_effect_group", "llmRepairable": True, "allowNodeDelete": False},
    "invalid_reaction_effect_group": {"strategy": "retarget_exact_effect_group", "llmRepairable": True, "allowNodeDelete": False},
    "capability_event_incompatible": {"strategy": "patch_exact_event", "llmRepairable": True, "allowNodeDelete": False},
    "child_depth_budget": {"strategy": "patch_graph_edge_or_count", "llmRepairable": True, "allowNodeDelete": True},
    "dual_use_placeable_input_contract": {"strategy": "replace_complete_use_transaction", "llmRepairable": True, "allowNodeDelete": False},
    "duplicate_exclusive_input": {"strategy": "patch_or_delete_conflicting_binding", "llmRepairable": True, "allowNodeDelete": True},
    "duplicate_id": {"strategy": "delete_exact_duplicate", "llmRepairable": True, "allowNodeDelete": True},
    "duplicate_single_component": {"strategy": "patch_or_delete_conflicting_call", "llmRepairable": True, "allowNodeDelete": True},
    "duplicate_equipment_damage_selector": {"strategy": "patch_selector_or_delete_duplicate", "llmRepairable": True, "allowNodeDelete": True},
    "equipment_scope_conflict": {"strategy": "select_one_equipment_configuration_or_delete_modifier", "llmRepairable": True, "allowNodeDelete": True},
    "empty_component": {"strategy": "patch_effect_params_or_delete_call", "llmRepairable": True, "allowNodeDelete": True},
    "entity_not_binding_spawnable": {"strategy": "patch_exact_binding_action", "llmRepairable": True, "allowNodeDelete": False},
    "event_not_emitted": {"strategy": "patch_or_synthesize_exact_event_producer", "llmRepairable": True, "allowNodeDelete": False},
    "event_spawn_budget": {"strategy": "patch_spawn_count_or_delete_edge", "llmRepairable": True, "allowNodeDelete": True},
    "overlapping_motion_windows": {"strategy": "patch_window_or_delete_conflicting_call", "llmRepairable": True, "allowNodeDelete": True},
    "retained_motion_stage_conflict": {"strategy": "reject_conflicting_saved_wire", "llmRepairable": False, "allowNodeDelete": False},
    "exclusive_component_conflict": {"strategy": "patch_or_delete_conflicting_call", "llmRepairable": True, "allowNodeDelete": True},
    "hidden_item_primary_requires_spawn_target": {"strategy": "select_exact_spawn_target_as_primary", "llmRepairable": True, "allowNodeDelete": False},
    "illegal_event_cycle": {"strategy": "patch_or_delete_cycle_edge", "llmRepairable": True, "allowNodeDelete": True},
    "inert_component": {"strategy": "patch_effect_params_or_delete_call", "llmRepairable": True, "allowNodeDelete": True},
    "inert_stationary_entity": {"strategy": "synthesize_exact_meaningful_component", "llmRepairable": True, "allowNodeDelete": False},
    "item_body_count": {"strategy": "patch_or_delete_extra_item_body", "llmRepairable": True, "allowNodeDelete": True},
    "missing_capability_dependency": {"strategy": "patch_or_synthesize_exact_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "missing_capability_group": {"strategy": "patch_or_synthesize_one_of_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "missing_binding_dependency": {"strategy": "synthesize_exact_binding_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "missing_dependency_param": {"strategy": "patch_exact_missing_param", "llmRepairable": True, "allowNodeDelete": False},
    "missing_entity_reference": {"strategy": "retarget_or_create_exact_missing_entity", "llmRepairable": True, "allowNodeDelete": False},

    "missing_item_capability_param": {"strategy": "patch_or_synthesize_exact_item_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "missing_light_color": {"strategy": "patch_exact_missing_param", "llmRepairable": True, "allowNodeDelete": False},
    "set_bonus_head_only": {"strategy": "patch_exact_param_or_remove_bonus", "llmRepairable": True, "allowNodeDelete": False},
    "missing_movement_component": {"strategy": "choose_one_compatible_position_driver", "llmRepairable": True, "allowNodeDelete": False},
    "missing_set_key": {"strategy": "patch_exact_missing_param", "llmRepairable": True, "allowNodeDelete": False},
    "missing_required_component": {"strategy": "synthesize_exact_required_component", "llmRepairable": True, "allowNodeDelete": False},
    "place_item_without_stack_cost": {"strategy": "replace_complete_use_transaction", "llmRepairable": True, "allowNodeDelete": False},
    "placed_body_placement_reference": {"strategy": "patch_exact_reference_or_delete_presentation", "llmRepairable": True, "allowNodeDelete": True},
    "duplicate_placed_body_reference": {"strategy": "delete_exact_later_presentation_index", "llmRepairable": True, "allowNodeDelete": False},
    "hybrid_placeable_max_stack": {"strategy": "patch_exact_item_param", "llmRepairable": True, "allowNodeDelete": False},
    "invalid_primary_entity_reference": {"strategy": "choose_exact_existing_primary_entity", "llmRepairable": True, "allowNodeDelete": False},
    "self_reference_forbidden": {"strategy": "patch_exact_reference", "llmRepairable": True, "allowNodeDelete": False},
    "unknown_capability": {"strategy": "replace_or_delete_unknown_call", "llmRepairable": True, "allowNodeDelete": True},
    "unknown_registry_requirement": {"strategy": "developer_contract_defect", "llmRepairable": False, "allowNodeDelete": False},
    "unreachable_entity": {"strategy": "bind_reference_or_delete_entity", "llmRepairable": True, "allowNodeDelete": True},
    "uncombined_identity": {"strategy": "patch_exact_name", "llmRepairable": True, "allowNodeDelete": False},
    "unsupported_input_action": {"strategy": "patch_exact_input_or_action", "llmRepairable": True, "allowNodeDelete": False},
    "wrong_binding_target_kind": {"strategy": "retarget_exact_binding", "llmRepairable": True, "allowNodeDelete": False},
    "wrong_reference_target_kind": {"strategy": "patch_exact_reference", "llmRepairable": True, "allowNodeDelete": False},
    "reference_requirements_unsatisfied": {"strategy": "retarget_or_create_compatible_entity_keep_existing_frozen", "llmRepairable": True, "allowNodeDelete": False},
    "wrong_target_kind": {"strategy": "retarget_exact_call", "llmRepairable": True, "allowNodeDelete": False},
}


# Include exact author/combine failures as well as runtime validator codes.
REPAIR_VALIDATION_ERROR_CODES = frozenset((*VALIDATION_ERROR_CODES, "uncombined_identity"))


def _strict_scope_string_schema() -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": 48}


def runtime_repair_scope_schema() -> dict[str, Any]:
    id_array = {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 48}, "uniqueItems": True}
    index_array = {"type": "array", "items": {"type": "integer", "minimum": 0}, "uniqueItems": True}
    transaction_variants: list[dict[str, Any]] = []
    for variant in binding_schema().get("oneOf") or []:
        row = copy.deepcopy(variant)
        row["properties"].pop("id", None)
        row["required"] = [name for name in row["required"] if name != "id"]
        transaction_variants.append(row)
    binding_transaction_array = {
        "type": "array",
        "uniqueItems": True,
        "items": {"oneOf": transaction_variants},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": {"const": RUNTIME_REPAIR_SCOPE_SCHEMA},
            "mutable": {
                "type": "object", "additionalProperties": False,
                "properties": {name: copy.deepcopy(id_array) for name in ("entityIds", "bindingIds", "callIds")},
                "required": ["entityIds", "bindingIds", "callIds"],
            },
            "deletable": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    **{name: copy.deepcopy(id_array) for name in ("entityIds", "bindingIds", "callIds")},
                    **{name: copy.deepcopy(index_array) for name in ("entityIndices", "bindingIndices", "callIndices")},
                    "callParamKeys": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "callId": _strict_scope_string_schema(),
                                "key": {"type": "string", "minLength": 1, "maxLength": 64},
                            },
                            "required": ["callId", "key"],
                        },
                    },
                    "callPropertyKeys": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "callId": _strict_scope_string_schema(),
                                "key": {"type": "string", "minLength": 1, "maxLength": 64},
                            },
                            "required": ["callId", "key"],
                        },
                    },
                },
                "required": ["entityIds", "bindingIds", "callIds", "entityIndices", "bindingIndices", "callIndices", "callParamKeys", "callPropertyKeys"],
            },
            "create": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "entities": {
                        "type": "object", "additionalProperties": False,
                        "properties": {"allowed": {"type": "boolean"}, "exactIds": copy.deepcopy(id_array), "allowedKinds": copy.deepcopy(id_array)},
                        "required": ["allowed", "exactIds", "allowedKinds"],
                    },
                    "bindings": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "allowed": {"type": "boolean"}, "allowedTargetIds": copy.deepcopy(id_array),
                            "allowedInputs": copy.deepcopy(id_array), "allowedActions": copy.deepcopy(id_array),
                            "requiredTargetIds": copy.deepcopy(id_array),
                            "allowedTransactions": copy.deepcopy(binding_transaction_array),
                            "mustChooseExactlyOne": {"type": "boolean"},
                        },
                        "required": [
                            "allowed", "allowedTargetIds", "allowedInputs", "allowedActions",
                            "requiredTargetIds", "allowedTransactions", "mustChooseExactlyOne",
                        ],
                    },
                    "calls": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "allowed": {"type": "boolean"}, "allowedTargetIds": copy.deepcopy(id_array),
                            "allowedTargetKinds": copy.deepcopy(id_array),
                            "allowedFns": copy.deepcopy(id_array), "requiredReferenceEntityIds": copy.deepcopy(id_array),
                        },
                        "required": ["allowed", "allowedTargetIds", "allowedTargetKinds", "allowedFns", "requiredReferenceEntityIds"],
                    },
                },
                "required": ["entities", "bindings", "calls"],
            },
            "retarget": {
                "type": "object", "additionalProperties": False,
                "properties": {name: copy.deepcopy(id_array) for name in ("entityIds", "bindingTargetIds", "callTargetIds")},
                "required": ["entityIds", "bindingTargetIds", "callTargetIds"],
            },
            "identityChanges": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    **{name: copy.deepcopy(id_array) for name in (
                        "entityKindIds", "bindingInputIds", "bindingActionIds",
                        "bindingTargetIds", "callFnIds", "callTargetIds",
                        "callEventIds",
                    )},
                    "callReferenceParams": {
                        "type": "array",
                        "items": {"type": "string", "pattern": r"^[A-Za-z][A-Za-z0-9_]{0,47}:[A-Za-z][A-Za-z0-9_]{0,47}$"},
                        "uniqueItems": True,
                    },
                },
                "required": [
                    "entityKindIds", "bindingInputIds", "bindingActionIds",
                    "bindingTargetIds", "callFnIds", "callTargetIds",
                    "callEventIds", "callReferenceParams",
                ],
            },
            "metadataFields": copy.deepcopy(id_array),
            "bindingAlternatives": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "bindingId": _strict_scope_string_schema(),
                        "allowed": copy.deepcopy(binding_transaction_array),
                    },
                    "required": ["bindingId", "allowed"],
                },
            },
            "eventAlternatives": {
                "type": "array",
                "maxItems": 48,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "callId": _strict_scope_string_schema(),
                        "targetId": _strict_scope_string_schema(),
                        "allowed": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 32,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "event": _strict_scope_string_schema(),
                                    "requiredCalls": {
                                        "type": "array",
                                        "maxItems": 8,
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "fn": {"type": "string", "enum": [cap.name for cap in CAPABILITY_REGISTRY.values()]},
                                                "targetId": _strict_scope_string_schema(),
                                                "exactParams": {
                                                    "type": "array",
                                                    "maxItems": 16,
                                                    "items": {
                                                        "type": "object",
                                                        "additionalProperties": False,
                                                        "properties": {
                                                            "param": _strict_scope_string_schema(),
                                                            "value": {
                                                                "oneOf": [
                                                                    {"type": "string"},
                                                                    {"type": "number"},
                                                                    {"type": "boolean"},
                                                                    {"type": "null"},
                                                                ],
                                                            },
                                                        },
                                                        "required": ["param", "value"],
                                                    },
                                                },
                                            },
                                            "required": ["fn", "targetId", "exactParams"],
                                        },
                                    },
                                    "requiredBindings": {
                                        "type": "array",
                                        "maxItems": 4,
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "targetId": {"type": "string", "minLength": 1},
                                                "anyOfInputs": {
                                                    "type": "array",
                                                    "minItems": 1,
                                                    "maxItems": 8,
                                                    "items": {"type": "string", "enum": list(INPUT_KIND_REGISTRY)},
                                                },
                                                "anyOfActions": {
                                                    "type": "array",
                                                    "maxItems": 5,
                                                    "items": {"type": "string", "enum": list(BINDING_ACTION_REGISTRY)},
                                                },
                                                "requiredContactDamage": {
                                                    "oneOf": [{"type": "boolean"}, {"type": "null"}],
                                                },
                                            },
                                            "required": ["targetId", "anyOfInputs", "anyOfActions", "requiredContactDamage"],
                                        },
                                    },
                                },
                                "required": ["event", "requiredCalls", "requiredBindings"],
                            },
                        },
                        "mustChooseOneCompleteAlternative": {"const": True},
                    },
                    "required": ["callId", "targetId", "allowed", "mustChooseOneCompleteAlternative"],
                },
            },
            "contextIds": {
                "type": "object", "additionalProperties": False,
                "properties": {name: copy.deepcopy(id_array) for name in ("entityIds", "bindingIds", "callIds")},
                "required": ["entityIds", "bindingIds", "callIds"],
            },
            "fieldPermissions": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    name: {
                        "type": "array",
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "id": _strict_scope_string_schema(),
                                "paths": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                            },
                            "required": ["id", "paths"],
                        },
                    }
                    for name in ("entities", "bindings", "calls")
                },
                "required": ["entities", "bindings", "calls"],
            },
            "repairTransactions": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    PRIMARY_ENTITY_SELECTION_FIELD: {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "allowed": {"type": "boolean"},
                            "candidateEntityIds": copy.deepcopy(id_array),
                            "mustSelectExactlyOne": {"type": "boolean"},
                        },
                        "required": ["allowed", "candidateEntityIds", "mustSelectExactlyOne"],
                    },
                    "exclusiveInputSelections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "input": _strict_scope_string_schema(),
                                "candidateBindingIds": copy.deepcopy(id_array),
                                "mustKeepExactlyOne": {"type": "boolean"},
                            },
                            "required": ["input", "candidateBindingIds", "mustKeepExactlyOne"],
                        },
                    },
                },
                "required": [PRIMARY_ENTITY_SELECTION_FIELD, "exclusiveInputSelections"],
            },
            "repairRequirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "errorPath": {"type": "string"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "affectedIds": copy.deepcopy(id_array),
                        "requiredOneOfCapabilities": copy.deepcopy(id_array),
                        "exactCapabilityParams": {"type": "array", "items": {"type": "object"}},
                        "allowedValues": {"type": "array"},
                        "repairStrategy": {"type": "string", "minLength": 1},
                        "llmRepairable": {"type": "boolean"},
                        "allowedBindingTransactions": copy.deepcopy(binding_transaction_array),
                        "allowedExistingBindingIds": copy.deepcopy(id_array),
                        "requiredBindingUpdates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "bindingId": _strict_scope_string_schema(),
                                    "allowed": copy.deepcopy(binding_transaction_array),
                                },
                                "required": ["bindingId", "allowed"],
                            },
                        },
                        "mustChooseExactlyOne": {"type": "boolean"},
                        "mustCreateExactlyOne": {"type": "boolean"},
                        "mustApplyAll": {"type": "boolean"},
                    },
                    "required": [
                        "errorPath", "code", "message", "affectedIds",
                        "requiredOneOfCapabilities", "exactCapabilityParams",
                        "allowedValues", "allowedExistingBindingIds",
                        "repairStrategy", "llmRepairable",
                    ],
                },
            },
            "blockerPlan": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "directCapabilityNames": copy.deepcopy(id_array),
                    "supportingCapabilityNames": copy.deepcopy(id_array),
                    "existingBrokenCapabilityNames": copy.deepcopy(id_array),
                    "requirements": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["directCapabilityNames", "supportingCapabilityNames", "existingBrokenCapabilityNames", "requirements"],
            },
            "errorPaths": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
            "capabilitySubset": copy.deepcopy(id_array),
            "nonRepairableErrors": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["schema", "mutable", "deletable", "create", "retarget", "identityChanges", "metadataFields", "bindingAlternatives", "eventAlternatives", "contextIds", "fieldPermissions", "repairTransactions", "repairRequirements", "blockerPlan", "errorPaths", "capabilitySubset", "nonRepairableErrors"],
    }


def _new_scope() -> dict[str, Any]:
    return {
        "schema": RUNTIME_REPAIR_SCOPE_SCHEMA,
        "mutable": {"entityIds": [], "bindingIds": [], "callIds": []},
        "deletable": {
            "entityIds": [], "bindingIds": [], "callIds": [],
            "entityIndices": [], "bindingIndices": [], "callIndices": [],
            "callParamKeys": [], "callPropertyKeys": [],
        },
        "create": {
            "entities": {"allowed": False, "exactIds": [], "allowedKinds": []},
            "bindings": {
                "allowed": False, "allowedTargetIds": [], "allowedInputs": [],
                "allowedActions": [], "requiredTargetIds": [], "allowedTransactions": [],
                "mustChooseExactlyOne": False,
            },
            "calls": {
                "allowed": False, "allowedTargetIds": [], "allowedTargetKinds": [], "allowedFns": [],
                "requiredReferenceEntityIds": [],
            },
        },
        "retarget": {"entityIds": [], "bindingTargetIds": [], "callTargetIds": []},
        "identityChanges": {
            "entityKindIds": [], "bindingInputIds": [], "bindingActionIds": [],
            "bindingTargetIds": [], "callFnIds": [], "callTargetIds": [],
            "callEventIds": [], "callReferenceParams": [],
        },
        "metadataFields": [],
        "bindingAlternatives": [],
        "eventAlternatives": [],
        "contextIds": {"entityIds": [], "bindingIds": [], "callIds": []},
        "fieldPermissions": {"entities": [], "bindings": [], "calls": []},
        "repairTransactions": {
            PRIMARY_ENTITY_SELECTION_FIELD: {
                "allowed": False,
                "candidateEntityIds": [],
                "mustSelectExactlyOne": True,
            },
            "exclusiveInputSelections": [],
        },
        "repairRequirements": [],
        "blockerPlan": {
            "directCapabilityNames": [],
            "supportingCapabilityNames": [],
            "existingBrokenCapabilityNames": [],
            "requirements": [],
        },
        "errorPaths": [],
        "capabilitySubset": [],
        "nonRepairableErrors": [],
    }


def runtime_repair_schema_capabilities(scope: Mapping[str, Any]) -> list[str]:
    """Project finite request grammar without narrowing an authorized fn edit.

    capabilitySubset describes blocker cards, not every possible replacement
    when fn/the complete call is mutable. Those scopes retain the Author-visible
    capability union; a parameter-only scope can use its exact blocker/support and
    create-policy names. Retained wire metadata is not a fresh patch vocabulary.
    Grammar membership never grants a write permission.
    """
    registered = set(CAPABILITY_REGISTRY)
    author_visible = {name for name, cap in CAPABILITY_REGISTRY.items() if cap.author_visible}
    identity = _mapping(scope.get("identityChanges"))
    permissions = _mapping(scope.get("fieldPermissions"))
    fn_mutable = bool(identity.get("callFnIds")) or any(
        path in {"", "fn"}
        for row in _values(permissions.get("calls")) if isinstance(row, Mapping)
        for path in _values(row.get("paths"))
    )
    if fn_mutable:
        return sorted(author_visible)
    names = set(_values(scope.get("capabilitySubset")))
    blockers = _mapping(scope.get("blockerPlan"))
    for key in ("directCapabilityNames", "supportingCapabilityNames", "existingBrokenCapabilityNames"):
        names.update(_values(blockers.get(key)))
    create = _mapping(_mapping(scope.get("create")).get("calls"))
    if create.get("allowed"):
        names.update(_values(create.get("allowedFns")))
    if names - registered:
        raise ValueError(f"Repair scope references unregistered capabilities: {sorted(names - registered)}")
    return sorted(names & author_visible)
