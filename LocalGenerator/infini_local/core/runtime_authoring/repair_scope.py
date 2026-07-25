from __future__ import annotations

"""Deterministic leaf-local Gameplay Repair scope.

The LLM may return a complete broken node for provider-schema convenience, but
only exact validator-reported fields are mutable.  Every already-valid value is
frozen, out-of-scope rewrites are ignored and audited, and missing dependencies
are represented as tightly constrained create policies.
"""

import copy
import re
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_CAPABILITIES,
    INPUT_KIND_REGISTRY,
)
from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring.program_schema import strict_repair_shape_report


RUNTIME_REPAIR_SCOPE_SCHEMA = "infini.runtime-repair-scope.v5"
RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA = "infini.runtime-repair-scope-report.v5"
RUNTIME_REPAIR_FILTER_REPORT_SCHEMA = "infini.runtime-repair-filter-report.v3"

_NODE_PATH_RE = re.compile(
    r"^\$\.(?:runtimeProgram\.(entities|bindings|calls)|runtimeContract\.(claims))\[(\d+)\]"
)

# Every deterministic validation code has an explicit Repair strategy.  This
# table is intentionally machine-readable: adding a validator error without a
# Repair policy must fail tests instead of silently falling back to a full-item
# retry or an empty patch.
REPAIR_ERROR_POLICY: dict[str, dict[str, Any]] = {
    "ambiguous_global_id": {"strategy": "delete_exact_duplicate", "llmRepairable": True, "allowNodeDelete": True},
    "binding_dependency": {"strategy": "synthesize_exact_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "capability_event_incompatible": {"strategy": "patch_exact_event", "llmRepairable": True, "allowNodeDelete": False},
    "child_depth_budget": {"strategy": "patch_graph_edge_or_count", "llmRepairable": True, "allowNodeDelete": True},
    "duplicate_exclusive_input": {"strategy": "patch_or_delete_conflicting_binding", "llmRepairable": True, "allowNodeDelete": True},
    "duplicate_id": {"strategy": "delete_exact_duplicate", "llmRepairable": True, "allowNodeDelete": True},
    "duplicate_single_component": {"strategy": "patch_or_delete_conflicting_call", "llmRepairable": True, "allowNodeDelete": True},
    "empty_component": {"strategy": "patch_effect_params_or_delete_call", "llmRepairable": True, "allowNodeDelete": True},
    "entity_not_binding_spawnable": {"strategy": "patch_exact_binding_action", "llmRepairable": True, "allowNodeDelete": False},
    "event_not_emitted": {"strategy": "patch_or_synthesize_exact_event_producer", "llmRepairable": True, "allowNodeDelete": False},
    "event_spawn_budget": {"strategy": "patch_spawn_count_or_delete_edge", "llmRepairable": True, "allowNodeDelete": True},
    "exclusive_component_conflict": {"strategy": "patch_or_delete_conflicting_call", "llmRepairable": True, "allowNodeDelete": True},
    "gameplay_claim_without_execution": {"strategy": "patch_or_delete_claim", "llmRepairable": True, "allowNodeDelete": True},
    "illegal_event_cycle": {"strategy": "patch_or_delete_cycle_edge", "llmRepairable": True, "allowNodeDelete": True},
    "inert_component": {"strategy": "patch_effect_params_or_delete_call", "llmRepairable": True, "allowNodeDelete": True},
    "inert_stationary_entity": {"strategy": "synthesize_exact_meaningful_component", "llmRepairable": True, "allowNodeDelete": False},
    "item_body_count": {"strategy": "patch_or_delete_extra_item_body", "llmRepairable": True, "allowNodeDelete": True},
    "missing_capability_dependency": {"strategy": "patch_or_synthesize_exact_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "missing_capability_group": {"strategy": "patch_or_synthesize_one_of_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "missing_claim_backing": {"strategy": "patch_or_delete_claim", "llmRepairable": True, "allowNodeDelete": True},
    "missing_dependency_param": {"strategy": "patch_exact_missing_param", "llmRepairable": True, "allowNodeDelete": False},
    "missing_entity_reference": {"strategy": "retarget_or_create_exact_missing_entity", "llmRepairable": True, "allowNodeDelete": False},
    "missing_entity_role": {"strategy": "synthesize_exact_role_row", "llmRepairable": True, "allowNodeDelete": False},
    "missing_item_capability_param": {"strategy": "patch_or_synthesize_exact_item_dependency", "llmRepairable": True, "allowNodeDelete": False},
    "missing_movement_component": {"strategy": "choose_one_compatible_position_driver", "llmRepairable": True, "allowNodeDelete": False},
    "missing_required_component": {"strategy": "synthesize_exact_required_component", "llmRepairable": True, "allowNodeDelete": False},
    "mixed_entity_role": {"strategy": "patch_exact_row_roles", "llmRepairable": True, "allowNodeDelete": False},
    "primary_entity_count": {"strategy": "choose_exact_single_primary_entity", "llmRepairable": True, "allowNodeDelete": False},
    "self_reference_forbidden": {"strategy": "patch_exact_reference", "llmRepairable": True, "allowNodeDelete": False},
    "unknown_capability": {"strategy": "replace_or_delete_unknown_call", "llmRepairable": True, "allowNodeDelete": True},
    "unknown_registry_requirement": {"strategy": "developer_contract_defect", "llmRepairable": False, "allowNodeDelete": False},
    "unreachable_entity": {"strategy": "bind_reference_or_delete_entity", "llmRepairable": True, "allowNodeDelete": True},
    "unsupported_input_action": {"strategy": "patch_exact_input_or_action", "llmRepairable": True, "allowNodeDelete": False},
    "wrong_binding_target_kind": {"strategy": "retarget_exact_binding", "llmRepairable": True, "allowNodeDelete": False},
    "wrong_reference_target_kind": {"strategy": "patch_exact_reference", "llmRepairable": True, "allowNodeDelete": False},
    "wrong_target_kind": {"strategy": "retarget_exact_call", "llmRepairable": True, "allowNodeDelete": False},
}



def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _program_rows(current: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    program = current.get("runtimeProgram") if isinstance(current.get("runtimeProgram"), Mapping) else {}
    contract = current.get("runtimeContract") if isinstance(current.get("runtimeContract"), Mapping) else {}
    return {
        "entities": _rows(program.get("entities")),
        "bindings": _rows(program.get("bindings")),
        "calls": _rows(program.get("calls")),
        "claims": _rows(contract.get("claims")),
    }


def _id_maps(rows: Mapping[str, list[dict[str, Any]]]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    namespace_by_id: dict[str, str] = {}
    row_by_id: dict[str, dict[str, Any]] = {}
    for namespace, values in rows.items():
        for row in values:
            row_id = str(row.get("id") or "")
            if row_id:
                namespace_by_id.setdefault(row_id, namespace)
                row_by_id.setdefault(row_id, row)
    return namespace_by_id, row_by_id


def _node_from_path(path: str, rows: Mapping[str, list[dict[str, Any]]]) -> tuple[str, int, str] | None:
    match = _NODE_PATH_RE.match(path)
    if not match:
        return None
    namespace = match.group(1) or match.group(2) or ""
    index = int(match.group(3))
    values = rows.get(namespace, [])
    row_id = str(values[index].get("id") or "") if 0 <= index < len(values) else ""
    return namespace, index, row_id


def _capability_names(values: Iterable[Any]) -> set[str]:
    names: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if text in CAPABILITY_REGISTRY:
            names.add(text)
            continue
        token = re.split(r"[.(\s]", text, maxsplit=1)[0]
        if token in CAPABILITY_REGISTRY:
            names.add(token)
    return names




def _decode_constraint_value(raw: str) -> Any:
    text = raw.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if text.lower() == "null":
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text.strip('"\'')


def _capability_constraints(values: Iterable[Any]) -> tuple[set[str], list[dict[str, Any]]]:
    names = _capability_names(values)
    exact: list[dict[str, Any]] = []
    for raw in values:
        text = str(raw or "").strip()
        match = re.fullmatch(r"([A-Za-z0-9_]+)[.(]([A-Za-z0-9_]+)=([^)]*)\)?", text)
        if not match or match.group(1) not in CAPABILITY_REGISTRY:
            continue
        exact.append({
            "capability": match.group(1),
            "param": match.group(2),
            "equals": _decode_constraint_value(match.group(3)),
        })
    return names, exact


def _capability_dependency_closure(names: Iterable[str]) -> set[str]:
    pending = [name for name in names if name in CAPABILITY_REGISTRY]
    out: set[str] = set()
    while pending:
        name = pending.pop()
        if name in out:
            continue
        out.add(name)
        cap = CAPABILITY_REGISTRY[name]
        pending.extend(value for value in cap.dependencies if value in CAPABILITY_REGISTRY)
        for requirement in cap.requirements:
            if requirement.capability in CAPABILITY_REGISTRY:
                pending.append(requirement.capability)
            pending.extend(value for value in requirement.any_of if value in CAPABILITY_REGISTRY)
    return out


def _candidate_capability_viable(
    name: str,
    target_ids: Iterable[str],
    rows: Mapping[str, list[dict[str, Any]]],
) -> bool:
    """Reject blocker alternatives that cannot work with frozen context.

    Repair must not be told to choose a capability whose prerequisite already
    exists with an incompatible frozen value, or which itself still requires a
    second missing alternative from the same component group.  Missing plain
    dependencies remain viable because the blocker plan can explicitly create
    their declared support slice.
    """

    cap = CAPABILITY_REGISTRY.get(name)
    if cap is None:
        return False
    target_ids = tuple(str(value) for value in target_ids if str(value))
    target_kinds = {
        str(row.get("kind") or "")
        for row in rows.get("entities", [])
        if str(row.get("id") or "") in target_ids
    }
    if target_kinds and not target_kinds.intersection(cap.target_kinds):
        return False

    calls = rows.get("calls", [])
    item_ids = {
        str(row.get("id") or "")
        for row in rows.get("entities", [])
        if row.get("kind") == "item_body"
    }
    for requirement in cap.requirements:
        if requirement.kind == "item_capability_param" and requirement.capability:
            matching = [
                row for row in calls
                if str(row.get("fn") or "") == requirement.capability
                and str(row.get("target") or "") in item_ids
            ]
            if matching:
                if not any(
                    isinstance(row.get("params"), Mapping)
                    and row["params"].get(requirement.param) == requirement.equals
                    for row in matching
                ):
                    return False
        elif requirement.kind == "capability_group_present" and requirement.any_of:
            # A candidate which still needs another missing member of the same
            # design-choice group is not a minimal blocker repair.  Keep it only
            # when that group is already present on the target.
            if not any(
                str(row.get("target") or "") in target_ids
                and str(row.get("fn") or "") in requirement.any_of
                for row in calls
            ):
                return False
    return True


def _field_permission_rows(values: Mapping[str, set[str]]) -> list[dict[str, Any]]:
    return [
        {"id": row_id, "paths": sorted(paths)}
        for row_id, paths in sorted(values.items())
        if row_id
    ]


def _field_permission_map(scope: Mapping[str, Any], namespace: str) -> dict[str, tuple[str, ...]]:
    permissions = scope.get("fieldPermissions") if isinstance(scope.get("fieldPermissions"), Mapping) else {}
    rows = permissions.get(namespace) if isinstance(permissions.get(namespace), list) else []
    return {
        str(row.get("id") or ""): tuple(str(value) for value in row.get("paths") or [])
        for row in rows if isinstance(row, Mapping) and str(row.get("id") or "")
    }


def _entity_reference_params(call: Mapping[str, Any]) -> list[str]:
    cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
    params = call.get("params") if isinstance(call.get("params"), Mapping) else {}
    if cap is None:
        return []
    return [str(params.get(name) or "") for name, spec in cap.params.items() if spec.reference is not None and params.get(name)]


def _call_target_kinds(call: Mapping[str, Any], *, param_name: str = "") -> tuple[str, ...]:
    cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
    if cap is None:
        return tuple(ENTITY_KIND_REGISTRY)
    if param_name and param_name in cap.params and cap.params[param_name].reference is not None:
        return cap.params[param_name].reference.target_kinds
    return cap.target_kinds


def _binding_target_kinds(binding: Mapping[str, Any]) -> tuple[str, ...]:
    action = BINDING_ACTION_REGISTRY.get(str(binding.get("action") or ""))
    return action.target_kinds if action is not None else tuple(ENTITY_KIND_REGISTRY)


def _matching_entity_ids(rows: Mapping[str, list[dict[str, Any]]], kinds: Iterable[str]) -> set[str]:
    allowed = set(kinds)
    return {
        str(row.get("id") or "")
        for row in rows["entities"]
        if str(row.get("id") or "") and str(row.get("kind") or "") in allowed
    }



def _strict_scope_string_schema() -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": 48}


def runtime_repair_scope_schema() -> dict[str, Any]:
    id_array = {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 48}, "uniqueItems": True}
    index_array = {"type": "array", "items": {"type": "integer", "minimum": 0}, "uniqueItems": True}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": {"const": RUNTIME_REPAIR_SCOPE_SCHEMA},
            "mutable": {
                "type": "object", "additionalProperties": False,
                "properties": {name: copy.deepcopy(id_array) for name in ("entityIds", "bindingIds", "callIds", "claimIds")},
                "required": ["entityIds", "bindingIds", "callIds", "claimIds"],
            },
            "deletable": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    **{name: copy.deepcopy(id_array) for name in ("entityIds", "bindingIds", "callIds", "claimIds")},
                    **{name: copy.deepcopy(index_array) for name in ("entityIndices", "bindingIndices", "callIndices", "claimIndices")},
                },
                "required": ["entityIds", "bindingIds", "callIds", "claimIds", "entityIndices", "bindingIndices", "callIndices", "claimIndices"],
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
                        },
                        "required": ["allowed", "allowedTargetIds", "allowedInputs", "allowedActions", "requiredTargetIds"],
                    },
                    "calls": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "allowed": {"type": "boolean"}, "allowedTargetIds": copy.deepcopy(id_array),
                            "allowedFns": copy.deepcopy(id_array), "requiredReferenceEntityIds": copy.deepcopy(id_array),
                        },
                        "required": ["allowed", "allowedTargetIds", "allowedFns", "requiredReferenceEntityIds"],
                    },
                    "claims": {
                        "type": "object", "additionalProperties": False,
                        "properties": {"allowed": {"type": "boolean"}}, "required": ["allowed"],
                    },
                },
                "required": ["entities", "bindings", "calls", "claims"],
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
                        "callEventIds", "claimKindIds", "claimBackingIds",
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
                    "callEventIds", "callReferenceParams", "claimKindIds", "claimBackingIds",
                ],
            },
            "metadataFields": copy.deepcopy(id_array),
            "contextIds": {
                "type": "object", "additionalProperties": False,
                "properties": {name: copy.deepcopy(id_array) for name in ("entityIds", "bindingIds", "callIds", "claimIds")},
                "required": ["entityIds", "bindingIds", "callIds", "claimIds"],
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
                    for name in ("entities", "bindings", "calls", "claims")
                },
                "required": ["entities", "bindings", "calls", "claims"],
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
                    },
                    "required": [
                        "errorPath", "code", "message", "affectedIds",
                        "requiredOneOfCapabilities", "exactCapabilityParams",
                        "allowedValues", "repairStrategy", "llmRepairable",
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
        "required": ["schema", "mutable", "deletable", "create", "retarget", "identityChanges", "metadataFields", "contextIds", "fieldPermissions", "repairRequirements", "blockerPlan", "errorPaths", "capabilitySubset", "nonRepairableErrors"],
    }

def _new_scope() -> dict[str, Any]:
    return {
        "schema": RUNTIME_REPAIR_SCOPE_SCHEMA,
        "mutable": {"entityIds": [], "bindingIds": [], "callIds": [], "claimIds": []},
        "deletable": {
            "entityIds": [], "bindingIds": [], "callIds": [], "claimIds": [],
            "entityIndices": [], "bindingIndices": [], "callIndices": [], "claimIndices": [],
        },
        "create": {
            "entities": {"allowed": False, "exactIds": [], "allowedKinds": []},
            "bindings": {
                "allowed": False, "allowedTargetIds": [], "allowedInputs": [],
                "allowedActions": [], "requiredTargetIds": [],
            },
            "calls": {
                "allowed": False, "allowedTargetIds": [], "allowedFns": [],
                "requiredReferenceEntityIds": [],
            },
            "claims": {"allowed": False},
        },
        "retarget": {"entityIds": [], "bindingTargetIds": [], "callTargetIds": []},
        "identityChanges": {
            "entityKindIds": [], "bindingInputIds": [], "bindingActionIds": [],
            "bindingTargetIds": [], "callFnIds": [], "callTargetIds": [],
            "callEventIds": [], "callReferenceParams": [],
            "claimKindIds": [], "claimBackingIds": [],
        },
        "metadataFields": [],
        "contextIds": {"entityIds": [], "bindingIds": [], "callIds": [], "claimIds": []},
        "fieldPermissions": {"entities": [], "bindings": [], "calls": [], "claims": []},
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


def build_runtime_repair_scope(current: Mapping[str, Any], errors: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    error_rows = [dict(row) for row in errors if isinstance(row, Mapping)]
    rows = _program_rows(current)
    error_paths_all = [str(row.get("path") or "$") for row in error_rows]
    namespace_by_id, row_by_id = _id_maps(rows)
    mutable = {name: set() for name in ("entities", "bindings", "calls", "claims")}
    deletable = {name: set() for name in ("entities", "bindings", "calls", "claims")}
    deletable_indices = {name: set() for name in ("entities", "bindings", "calls", "claims")}
    context = {name: set() for name in ("entities", "bindings", "calls", "claims")}
    create_entity_exact: set[str] = set()
    create_entity_kinds: set[str] = set()
    create_binding_targets: set[str] = set()
    create_binding_inputs: set[str] = set()
    create_binding_actions: set[str] = set()
    create_call_targets: set[str] = set()
    create_call_fns: set[str] = set()
    required_reference_entities: set[str] = set()
    allow_create_claim = False
    retarget_binding_ids: set[str] = set()
    retarget_call_ids: set[str] = set()
    entity_kind_change_ids: set[str] = set()
    binding_input_change_ids: set[str] = set()
    binding_action_change_ids: set[str] = set()
    binding_target_change_ids: set[str] = set()
    call_fn_change_ids: set[str] = set()
    call_target_change_ids: set[str] = set()
    call_event_change_ids: set[str] = set()
    call_reference_param_changes: set[str] = set()
    claim_kind_change_ids: set[str] = set()
    claim_backing_change_ids: set[str] = set()
    metadata_fields: set[str] = set()
    field_permissions: dict[str, dict[str, set[str]]] = {
        namespace: {} for namespace in ("entities", "bindings", "calls", "claims")
    }
    repair_requirements: list[dict[str, Any]] = []
    direct_blocker_capabilities: set[str] = set()
    existing_broken_capabilities: set[str] = set()
    non_repairable_errors: list[dict[str, Any]] = []
    error_paths: list[str] = []

    def grant(namespace: str, row_id: str, relative_path: str) -> None:
        if not row_id:
            return
        field_permissions[namespace].setdefault(row_id, set()).add(relative_path.strip("."))

    def mark(namespace: str, row_id: str, *, can_delete: bool = False) -> None:
        if row_id:
            mutable[namespace].add(row_id)
            if can_delete:
                deletable[namespace].add(row_id)

    def context_id(row_id: str) -> None:
        namespace = namespace_by_id.get(row_id)
        if namespace:
            context[namespace].add(row_id)

    def allow_new_call(target_ids: Iterable[str], fns: Iterable[str]) -> None:
        create_call_targets.update(value for value in target_ids if value)
        create_call_fns.update(value for value in fns if value in CAPABILITY_REGISTRY)

    for error in error_rows:
        path = str(error.get("path") or "$")
        code = str(error.get("code") or error.get("kind") or "")
        allowed = error.get("allowed") if isinstance(error.get("allowed"), list) else []
        related = [str(value) for value in error.get("relatedIds") or [] if str(value)]
        required_caps, exact_params = _capability_constraints(allowed)
        policy = REPAIR_ERROR_POLICY.get(code)
        if policy is None and not code.startswith("shape_"):
            non_repairable_errors.append({
                "path": path,
                "code": "missing_repair_error_policy",
                "message": f"validator code {code!r} has no deterministic Repair policy",
                "repairReason": "validator_code_has_no_repair_policy",
                "originalError": copy.deepcopy(error),
            })
            policy = {"strategy": "unmapped_validator_error", "llmRepairable": False, "allowNodeDelete": False}
        if policy is not None and not bool(policy.get("llmRepairable", True)):
            non_repairable_errors.append({
                **copy.deepcopy(error),
                "repairReason": str(policy.get("strategy") or "non_repairable"),
            })
        requirement_row = {
            "errorPath": path,
            "code": code,
            "message": str(error.get("message") or ""),
            "affectedIds": sorted(set(related)),
            "requiredOneOfCapabilities": sorted(required_caps),
            "exactCapabilityParams": exact_params,
            "allowedValues": copy.deepcopy(allowed),
            "repairStrategy": str((policy or {}).get("strategy") or ("patch_exact_schema_path" if code.startswith("shape_") else "unmapped_validator_error")),
            "llmRepairable": bool((policy or {}).get("llmRepairable", code.startswith("shape_"))),
        }
        repair_requirements.append(requirement_row)
        error_paths.append(path)
        node = _node_from_path(path, rows)
        node_namespace = ""
        node_index = -1
        node_id = ""
        node_row: dict[str, Any] = {}
        if node is not None:
            node_namespace, node_index, node_id = node
            node_row = rows.get(node_namespace, [])[node_index] if 0 <= node_index < len(rows.get(node_namespace, [])) else {}
            if node_namespace == "calls":
                existing_fn = str(node_row.get("fn") or "")
                if existing_fn in CAPABILITY_REGISTRY:
                    existing_broken_capabilities.add(existing_fn)
            if node_id:
                root_prefix = (
                    f"$.runtimeProgram.{node_namespace}[{node_index}]"
                    if node_namespace != "claims"
                    else f"$.runtimeContract.claims[{node_index}]"
                )
                if path == root_prefix:
                    # Provider union validation emits a generic shape_one_of at
                    # the row root together with a precise descendant error.
                    # The generic wrapper must not unfreeze the whole row.
                    has_precise_descendant = any(other.startswith(root_prefix + ".") for other in error_paths_all)
                    if code.startswith("shape_") and not (code == "shape_one_of" and has_precise_descendant):
                        grant(node_namespace, node_id, "")
                elif path.startswith(root_prefix + "."):
                    relative = path[len(root_prefix) + 1:]
                    if not (relative == "params" and code in {"empty_component", "inert_component"}):
                        grant(node_namespace, node_id, relative)
            dependency_only_codes = {
                "binding_dependency", "missing_capability_dependency", "missing_capability_group",
                "missing_item_capability_param",
            }
            if node_id:
                if code in dependency_only_codes:
                    context[node_namespace].add(node_id)
                else:
                    mark(
                        node_namespace,
                        node_id,
                        can_delete=bool((policy or {}).get("allowNodeDelete", False)),
                    )
            else:
                deletable_indices[node_namespace].add(node_index)
                if node_namespace == "entities":
                    kind = str(node_row.get("kind") or "")
                    create_entity_kinds.update({kind} if kind in ENTITY_KIND_REGISTRY else ENTITY_KIND_REGISTRY)
                elif node_namespace == "bindings":
                    target = str(node_row.get("target") or "")
                    if target:
                        create_binding_targets.add(target)
                    input_name = str(node_row.get("input") or "")
                    action_name = str(node_row.get("action") or "")
                    if input_name in INPUT_KIND_REGISTRY:
                        create_binding_inputs.add(input_name)
                    if action_name in BINDING_ACTION_REGISTRY:
                        create_binding_actions.add(action_name)
                elif node_namespace == "calls":
                    target = str(node_row.get("target") or "")
                    fn = str(node_row.get("fn") or "")
                    if target:
                        create_call_targets.add(target)
                    if fn in CAPABILITY_REGISTRY:
                        create_call_fns.add(fn)
                elif node_namespace == "claims":
                    allow_create_claim = True

        if node_id:
            if node_namespace == "entities" and path.startswith(f"$.runtimeProgram.entities[{node_index}].kind"):
                entity_kind_change_ids.add(node_id)
            if node_namespace == "bindings":
                if path.startswith(f"$.runtimeProgram.bindings[{node_index}].input"):
                    binding_input_change_ids.add(node_id)
                if path.startswith(f"$.runtimeProgram.bindings[{node_index}].action"):
                    binding_action_change_ids.add(node_id)
                if path.startswith(f"$.runtimeProgram.bindings[{node_index}].target"):
                    binding_target_change_ids.add(node_id)
            if node_namespace == "calls":
                if path.startswith(f"$.runtimeProgram.calls[{node_index}].fn"):
                    call_fn_change_ids.add(node_id)
                if path.startswith(f"$.runtimeProgram.calls[{node_index}].target"):
                    call_target_change_ids.add(node_id)
                param_match = re.search(r"\.params\.([A-Za-z0-9_]+)$", path)
                if param_match:
                    param_name = param_match.group(1)
                    cap = CAPABILITY_REGISTRY.get(str(node_row.get("fn") or ""))
                    if param_name == "event":
                        call_event_change_ids.add(node_id)
                    if cap is not None and param_name in cap.params and cap.params[param_name].reference is not None:
                        call_reference_param_changes.add(f"{node_id}:{param_name}")
            if node_namespace == "claims":
                if path.startswith(f"$.runtimeContract.claims[{node_index}].kind"):
                    claim_kind_change_ids.add(node_id)
                if path.startswith(f"$.runtimeContract.claims[{node_index}].backedBy"):
                    claim_backing_change_ids.add(node_id)

        # Metadata is a separate bounded subtree.
        for field in ("name", "tooltip", "category", "concept"):
            if path.startswith(f"$.{field}"):
                metadata_fields.add(field)
        if path.startswith("$.runtimeContract.parentSynthesis"):
            metadata_fields.add("parentSynthesis")

        if code == "unknown_registry_requirement":
            pass
        elif code in {"mixed_entity_role", "primary_entity_count"}:
            role_row_ids = related or [
                str(row.get("id") or "")
                for namespace in ("bindings", "calls")
                for row in rows[namespace]
                if str(row.get("id") or "")
            ]
            for row_id in role_row_ids:
                namespace = namespace_by_id.get(row_id)
                if namespace in {"bindings", "calls"}:
                    mark(namespace, row_id)
                    grant(namespace, row_id, "role")
        elif code in {"duplicate_id", "ambiguous_global_id"}:
            # IDs are structural identity.  Do not let Repair rename a valid
            # row through a broad upsert; allow dropping the exact offending
            # row by index instead.
            if node_namespace and node_index >= 0:
                deletable_indices[node_namespace].add(node_index)
                if node_id:
                    context[node_namespace].add(node_id)
        elif code == "empty_component" and node_namespace == "calls" and node_id:
            mark("calls", node_id, can_delete=True)
            for descriptor in allowed:
                param_name = str(descriptor).split()[0].strip()
                if param_name:
                    grant("calls", node_id, f"params.{param_name}")
        elif code == "inert_component" and node_namespace == "calls" and node_id:
            mark("calls", node_id, can_delete=True)
            cap = CAPABILITY_REGISTRY.get(str(node_row.get("fn") or ""))
            if cap is not None:
                for param_name in cap.params:
                    grant("calls", node_id, f"params.{param_name}")
        elif code == "duplicate_exclusive_input":
            # Exact validator reports normally include both conflicting ids,
            # but transport/debug fixtures may only preserve the failing path.
            # The path-resolved binding must still be removable/repairable.
            if node_namespace == "bindings" and node_id:
                mark("bindings", node_id, can_delete=True)
                binding_input_change_ids.add(node_id)
                grant("bindings", node_id, "input")
            for row_id in related:
                if namespace_by_id.get(row_id) == "bindings":
                    mark("bindings", row_id, can_delete=True)
                    binding_input_change_ids.add(row_id)
                    grant("bindings", row_id, "input")
        elif code in {"duplicate_single_component", "exclusive_component_conflict"}:
            for row_id in related:
                if namespace_by_id.get(row_id) == "calls":
                    mark("calls", row_id, can_delete=True)
                    call_fn_change_ids.add(row_id)
                    grant("calls", row_id, "fn")
        elif code == "missing_entity_reference":
            missing_ids = [row_id for row_id in related if row_id not in namespace_by_id]
            if node_namespace == "bindings":
                binding_target_change_ids.add(node_id)
                kinds = _binding_target_kinds(node_row)
                create_entity_kinds.update(kinds)
                create_entity_exact.update(missing_ids)
                retarget_binding_ids.update(_matching_entity_ids(rows, kinds))
            elif node_namespace == "calls":
                param_match = re.search(r"\.params\.([A-Za-z0-9_]+)$", path)
                if param_match:
                    call_reference_param_changes.add(f"{node_id}:{param_match.group(1)}")
                else:
                    call_target_change_ids.add(node_id)
                kinds = _call_target_kinds(node_row, param_name=param_match.group(1) if param_match else "")
                create_entity_kinds.update(kinds)
                create_entity_exact.update(missing_ids)
                retarget_call_ids.update(_matching_entity_ids(rows, kinds))
            elif node_namespace == "entities" and not node_id:
                create_entity_kinds.update(ENTITY_KIND_REGISTRY)
        elif code == "item_body_count":
            for row in rows["entities"]:
                if row.get("kind") == "item_body":
                    mark("entities", str(row.get("id") or ""), can_delete=True)
            create_entity_kinds.add("item_body")
        elif code in {"wrong_binding_target_kind", "unsupported_input_action", "entity_not_binding_spawnable"}:
            if node_namespace == "bindings":
                binding_target_change_ids.add(node_id)
                retarget_binding_ids.update(_matching_entity_ids(rows, _binding_target_kinds(node_row)))
                if code == "unsupported_input_action":
                    binding_input_change_ids.add(node_id)
                    binding_action_change_ids.add(node_id)
                    grant("bindings", node_id, "input")
                    grant("bindings", node_id, "action")
                elif code == "entity_not_binding_spawnable":
                    binding_action_change_ids.add(node_id)
                    grant("bindings", node_id, "action")
                if code == "wrong_binding_target_kind":
                    grant("bindings", node_id, "target")
        elif code in {"wrong_target_kind", "wrong_reference_target_kind", "self_reference_forbidden"}:
            if node_namespace == "calls":
                param_match = re.search(r"\.params\.([A-Za-z0-9_]+)$", path)
                if param_match:
                    call_reference_param_changes.add(f"{node_id}:{param_match.group(1)}")
                else:
                    call_target_change_ids.add(node_id)
                retarget_call_ids.update(_matching_entity_ids(rows, _call_target_kinds(node_row, param_name=param_match.group(1) if param_match else "")))
        elif code in {
            "missing_required_component", "missing_movement_component", "inert_stationary_entity",
            "binding_dependency", "event_not_emitted", "missing_item_capability_param",
            "missing_capability_dependency", "missing_capability_group",
        }:
            target_ids = [row_id for row_id in related if namespace_by_id.get(row_id) == "entities"]
            if not target_ids and node_namespace == "calls":
                target_ids = [str(node_row.get("target") or "")]
            if not target_ids and code == "binding_dependency":
                item = next((row for row in rows["entities"] if row.get("kind") == "item_body"), None)
                if item:
                    target_ids = [str(item.get("id") or "")]
            fns = _capability_names(allowed)
            fns = {
                name for name in fns
                if _candidate_capability_viable(name, target_ids, rows)
            }
            if code == "inert_stationary_entity" and not fns:
                affected_kinds = {
                    str(row_by_id.get(row_id, {}).get("kind") or "")
                    for row_id in target_ids
                    if row_id
                }
                fns.update(
                    name
                    for name, cap in CAPABILITY_REGISTRY.items()
                    if cap.meaningful_for_stationary
                    and (not affected_kinds or affected_kinds.intersection(cap.target_kinds))
                )
            # The model-facing requirement must list the same viable blockers
            # for which it receives cards.  Raw validator alternatives can
            # include capabilities that would require changing frozen context
            # or another unresolved design choice, so exposing them here would
            # force the model to guess despite the narrow catalog.
            requirement_row["requiredOneOfCapabilities"] = sorted(fns)
            direct_blocker_capabilities.update(fns)
            for row_id in target_ids:
                context["entities"].add(row_id)
            # Prefer repairing an already-authored producer/dependency over adding
            # a parallel alternative.  Creation is granted only when no candidate
            # capability already exists on the affected target.
            existing_candidates: list[dict[str, Any]] = []
            for call in rows["calls"]:
                if str(call.get("target") or "") in target_ids and str(call.get("fn") or "") in fns:
                    existing_candidates.append(call)
                    call_id = str(call.get("id") or "")
                    existing_broken_capabilities.add(str(call.get("fn") or ""))
                    mark("calls", call_id)
                    for constraint in exact_params:
                        if constraint.get("capability") == call.get("fn"):
                            grant("calls", call_id, f"params.{constraint.get('param')}")
                    if code == "event_not_emitted":
                        for descriptor in allowed:
                            match = re.fullmatch(r"([A-Za-z0-9_]+)\(([A-Za-z0-9_]+)=([^)]*)\)", str(descriptor))
                            if match and match.group(1) == call.get("fn"):
                                grant("calls", call_id, f"params.{match.group(2)}")
            if not existing_candidates:
                allow_new_call(target_ids, fns)
            if code == "event_not_emitted" and any("binding" in str(value) or "primary_use" in str(value) for value in allowed):
                create_binding_targets.update(target_ids)
                create_binding_inputs.update({"primary_use", "alternate_use"})
                create_binding_actions.update(INPUT_KIND_REGISTRY["primary_use"].allowed_actions)
        elif code == "unreachable_entity":
            affected = [row_id for row_id in related if namespace_by_id.get(row_id) == "entities"]
            for row_id in affected:
                mark("entities", row_id, can_delete=True)
                entity = row_by_id.get(row_id, {})
                kind = str(entity.get("kind") or "")
                kind_spec = ENTITY_KIND_REGISTRY.get(kind)
                if kind_spec and kind_spec.spawnable_by_binding:
                    create_binding_targets.add(row_id)
                    create_binding_inputs.update({"primary_use", "alternate_use"})
                    create_binding_actions.add("spawn_entity")
                else:
                    required_reference_entities.add(row_id)
                    create_call_targets.update(str(row.get("id") or "") for row in rows["entities"] if str(row.get("id") or "") != row_id)
                    compatible_links = {
                        name
                        for name in EVENT_CAPABILITIES
                        if any(
                            spec.reference is not None
                            and spec.reference.graph_edge
                            and kind in spec.reference.target_kinds
                            for spec in CAPABILITY_REGISTRY[name].params.values()
                        )
                    }
                    create_call_fns.update(compatible_links)
                    direct_blocker_capabilities.update(compatible_links)
        elif code in {"illegal_event_cycle", "child_depth_budget", "event_spawn_budget"}:
            cycle_entities = set(related)
            for call in rows["calls"]:
                refs = set(_entity_reference_params(call))
                target = str(call.get("target") or "")
                if refs and (not cycle_entities or target in cycle_entities or refs.intersection(cycle_entities)):
                    call_id = str(call.get("id") or "")
                    mark("calls", call_id, can_delete=True)
                    cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
                    if cap is not None:
                        for param_name, spec in cap.params.items():
                            if spec.reference is not None:
                                call_reference_param_changes.add(f"{call_id}:{param_name}")
                                grant("calls", call_id, f"params.{param_name}")
                        if code in {"child_depth_budget", "event_spawn_budget"} and cap.activation_spawn_count_param:
                            grant("calls", call_id, f"params.{cap.activation_spawn_count_param}")
                    if isinstance(call.get("params"), Mapping) and "event" in call["params"]:
                        call_event_change_ids.add(call_id)
                        grant("calls", call_id, "params.event")
        elif code in {"missing_claim_backing", "gameplay_claim_without_execution"}:
            if node_namespace == "claims":
                mark("claims", node_id, can_delete=True)
                grant("claims", node_id, "backedBy")

        # Existing related nodes are useful context unless explicitly mutable.
        for row_id in related:
            context_id(row_id)

    # A mutable node may depend on other valid nodes. Include those as immutable context.
    for binding_id in list(mutable["bindings"]):
        binding = row_by_id.get(binding_id, {})
        context["entities"].add(str(binding.get("target") or ""))
    for call_id in list(mutable["calls"]):
        call = row_by_id.get(call_id, {})
        context["entities"].add(str(call.get("target") or ""))
        context["entities"].update(_entity_reference_params(call))
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if cap is not None:
            existing_broken_capabilities.add(cap.name)

    affected_backing_ids = mutable["entities"] | mutable["bindings"] | mutable["calls"] | deletable["entities"] | deletable["bindings"] | deletable["calls"]
    for claim in rows["claims"]:
        claim_id = str(claim.get("id") or "")
        if affected_backing_ids.intersection(str(value) for value in claim.get("backedBy") or []):
            mark("claims", claim_id)

    # Remove mutable rows from immutable context sets.
    for namespace in context:
        context[namespace].difference_update(mutable[namespace])
        context[namespace].discard("")

    # The Repair prompt distinguishes direct blockers from their technical
    # support dependencies.  It never receives the full full capability catalog.
    direct_blocker_capabilities.update(name for name in create_call_fns if name in CAPABILITY_REGISTRY)
    supporting_capabilities = _capability_dependency_closure(direct_blocker_capabilities) - direct_blocker_capabilities
    if create_call_fns:
        create_call_fns.update(supporting_capabilities)
    capability_subset = direct_blocker_capabilities | supporting_capabilities | existing_broken_capabilities

    # Identity/reference permissions are also represented as exact mutable
    # fields so the conservative merge can retain every unrelated old value.
    for row_id in entity_kind_change_ids:
        grant("entities", row_id, "kind")
    for row_id in binding_input_change_ids:
        grant("bindings", row_id, "input")
    for row_id in binding_action_change_ids:
        grant("bindings", row_id, "action")
    for row_id in binding_target_change_ids:
        grant("bindings", row_id, "target")
    for row_id in call_fn_change_ids:
        grant("calls", row_id, "fn")
    for row_id in call_target_change_ids:
        grant("calls", row_id, "target")
    for row_id in call_event_change_ids:
        grant("calls", row_id, "params.event")
    for encoded in call_reference_param_changes:
        row_id, param_name = encoded.split(":", 1)
        grant("calls", row_id, f"params.{param_name}")
    for row_id in claim_kind_change_ids:
        grant("claims", row_id, "kind")
    for row_id in claim_backing_change_ids:
        grant("claims", row_id, "backedBy")

    scope = _new_scope()
    scope["mutable"] = {
        "entityIds": sorted(mutable["entities"]),
        "bindingIds": sorted(mutable["bindings"]),
        "callIds": sorted(mutable["calls"]),
        "claimIds": sorted(mutable["claims"]),
    }
    scope["deletable"] = {
        "entityIds": sorted(deletable["entities"]),
        "bindingIds": sorted(deletable["bindings"]),
        "callIds": sorted(deletable["calls"]),
        "claimIds": sorted(deletable["claims"]),
        "entityIndices": sorted(deletable_indices["entities"]),
        "bindingIndices": sorted(deletable_indices["bindings"]),
        "callIndices": sorted(deletable_indices["calls"]),
        "claimIndices": sorted(deletable_indices["claims"]),
    }
    scope["create"] = {
        "entities": {
            "allowed": bool(create_entity_exact or create_entity_kinds),
            "exactIds": sorted(create_entity_exact),
            "allowedKinds": sorted(create_entity_kinds),
        },
        "bindings": {
            "allowed": bool(create_binding_targets),
            "allowedTargetIds": sorted(create_binding_targets),
            "allowedInputs": sorted(create_binding_inputs or INPUT_KIND_REGISTRY),
            "allowedActions": sorted(create_binding_actions or BINDING_ACTION_REGISTRY),
            "requiredTargetIds": sorted(create_binding_targets),
        },
        "calls": {
            "allowed": bool(create_call_targets and create_call_fns),
            "allowedTargetIds": sorted(create_call_targets),
            "allowedFns": sorted(name for name in create_call_fns if name in CAPABILITY_REGISTRY),
            "requiredReferenceEntityIds": sorted(required_reference_entities),
        },
        "claims": {"allowed": allow_create_claim},
    }
    scope["retarget"] = {
        "entityIds": sorted(str(row.get("id") or "") for row in rows["entities"] if str(row.get("id") or "")),
        "bindingTargetIds": sorted(retarget_binding_ids),
        "callTargetIds": sorted(retarget_call_ids),
    }
    scope["identityChanges"] = {
        "entityKindIds": sorted(entity_kind_change_ids),
        "bindingInputIds": sorted(binding_input_change_ids),
        "bindingActionIds": sorted(binding_action_change_ids),
        "bindingTargetIds": sorted(binding_target_change_ids),
        "callFnIds": sorted(call_fn_change_ids),
        "callTargetIds": sorted(call_target_change_ids),
        "callEventIds": sorted(call_event_change_ids),
        "callReferenceParams": sorted(call_reference_param_changes),
        "claimKindIds": sorted(claim_kind_change_ids),
        "claimBackingIds": sorted(claim_backing_change_ids),
    }
    scope["metadataFields"] = sorted(metadata_fields)
    scope["contextIds"] = {
        "entityIds": sorted(context["entities"]),
        "bindingIds": sorted(context["bindings"]),
        "callIds": sorted(context["calls"]),
        "claimIds": sorted(context["claims"]),
    }
    scope["fieldPermissions"] = {
        namespace: _field_permission_rows(field_permissions[namespace])
        for namespace in ("entities", "bindings", "calls", "claims")
    }
    scope["repairRequirements"] = repair_requirements
    scope["blockerPlan"] = {
        "directCapabilityNames": sorted(direct_blocker_capabilities),
        "supportingCapabilityNames": sorted(supporting_capabilities),
        "existingBrokenCapabilityNames": sorted(existing_broken_capabilities),
        "requirements": copy.deepcopy(repair_requirements),
    }
    scope["errorPaths"] = error_paths
    scope["capabilitySubset"] = sorted(capability_subset)
    scope["nonRepairableErrors"] = non_repairable_errors
    return scope


def _scope_error(path: str, message: str, *, actual: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"path": path, "code": "repair_scope_violation", "message": message}
    if actual is not None:
        row["actual"] = actual
    return row



def _empty_filtered_patch(note: str) -> dict[str, Any]:
    return {
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "bindingsUpsert": [], "bindingIdsDelete": [], "bindingIndicesDelete": [],
        "callsUpsert": [], "callIdsDelete": [], "callIndicesDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "claimIndicesDelete": [],
        "metadataPatch": {}, "note": note or "deterministically filtered targeted repair",
    }


def _filter_ignored(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {
        "path": path,
        "reason": reason,
        "requested": copy.deepcopy(requested),
        "preserved": copy.deepcopy(preserved),
    }


def _new_row_allowed(namespace: str, row: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[bool, str]:
    if not bool(policy.get("allowed")):
        return False, "creation_not_required"
    if namespace == "entities":
        exact_ids = set(str(value) for value in policy.get("exactIds") or [])
        allowed_kinds = set(str(value) for value in policy.get("allowedKinds") or [])
        row_id = str(row.get("id") or "")
        if exact_ids and row_id not in exact_ids:
            return False, "entity_id_not_missing_reference"
        if str(row.get("kind") or "") not in allowed_kinds:
            return False, "entity_kind_not_compatible"
        return True, ""
    if namespace == "bindings":
        if str(row.get("target") or "") not in set(str(value) for value in policy.get("allowedTargetIds") or []):
            return False, "binding_target_not_required"
        if str(row.get("input") or "") not in set(str(value) for value in policy.get("allowedInputs") or []):
            return False, "binding_input_not_allowed"
        if str(row.get("action") or "") not in set(str(value) for value in policy.get("allowedActions") or []):
            return False, "binding_action_not_allowed"
        return True, ""
    if namespace == "calls":
        if str(row.get("target") or "") not in set(str(value) for value in policy.get("allowedTargetIds") or []):
            return False, "call_target_not_required"
        if str(row.get("fn") or "") not in set(str(value) for value in policy.get("allowedFns") or []):
            return False, "capability_not_in_blocker_closure"
        required_refs = set(str(value) for value in policy.get("requiredReferenceEntityIds") or [])
        if required_refs and not required_refs.intersection(_entity_reference_params(row)):
            return False, "missing_required_affected_entity_reference"
        return True, ""
    if namespace == "claims":
        return bool(policy.get("allowed")), "claim_creation_not_required"
    return False, "unknown_namespace"




def _metadata_permission_paths(scope: Mapping[str, Any], field: str) -> tuple[str, ...]:
    prefix = f"$.{field}" if field != "parentSynthesis" else "$.runtimeContract.parentSynthesis"
    paths: set[str] = set()
    for raw in scope.get("errorPaths") or []:
        path = str(raw or "")
        if path == prefix:
            paths.add("")
        elif path.startswith(prefix + "."):
            paths.add(path[len(prefix) + 1:])
    return tuple(sorted(paths))

def filter_repair_patch_scope(
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze accepted values and retain only useful in-scope repair changes.

    A provider response is fatal only when its strict patch shape is invalid.
    Attempts to rewrite valid values, independent nodes, or unrequested new
    nodes are ignored and audited.  A missing key is accepted only when the
    validator reported that exact path; optional unrequested design fields stay
    absent even if the model includes them in a complete-node response.
    """

    shape = strict_repair_shape_report(patch)
    if not shape.get("ok"):
        return _empty_filtered_patch("invalid repair patch"), {
            "schema": RUNTIME_REPAIR_FILTER_REPORT_SCHEMA,
            "ok": False,
            "errors": copy.deepcopy(shape.get("errors") or []),
            "acceptedPaths": [],
            "ignoredChanges": [],
        }

    rows = _program_rows(current)
    mutable = scope.get("mutable") if isinstance(scope.get("mutable"), Mapping) else {}
    deletable = scope.get("deletable") if isinstance(scope.get("deletable"), Mapping) else {}
    create = scope.get("create") if isinstance(scope.get("create"), Mapping) else {}
    accepted: list[str] = []
    ignored: list[dict[str, Any]] = []
    filtered = _empty_filtered_patch(str(patch.get("note") or "targeted repair"))

    specs = (
        ("entities", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete", "entityIds", "id"),
        ("bindings", "bindingsUpsert", "bindingIdsDelete", "bindingIndicesDelete", "bindingIds", "id"),
        ("calls", "callsUpsert", "callIdsDelete", "callIndicesDelete", "callIds", "id"),
        ("claims", "claimsUpsert", "claimIdsDelete", "claimIndicesDelete", "claimIds", "id"),
    )
    for namespace, upsert_key, delete_key, index_delete_key, scope_key, id_key in specs:
        original_rows = rows[namespace]
        original_by_id = {
            str(row.get(id_key) or ""): row
            for row in original_rows
            if str(row.get(id_key) or "")
        }
        mutable_ids = set(str(value) for value in mutable.get(scope_key) or [])
        deletable_ids = set(str(value) for value in deletable.get(scope_key) or [])
        serialized_index_key = index_delete_key.replace("Delete", "")
        deletable_indices = set(int(value) for value in deletable.get(serialized_index_key) or [])
        permissions = _field_permission_map(scope, namespace)
        create_policy = create.get(namespace) if isinstance(create.get(namespace), Mapping) else {}

        for index, value in enumerate(patch.get(delete_key) or []):
            row_id = str(value)
            path = f"$.{delete_key}[{index}]"
            if row_id in deletable_ids:
                filtered[delete_key].append(row_id)
                accepted.append(path)
            else:
                ignored.append(_filter_ignored(path, row_id, row_id, "valid_node_delete_ignored"))

        for index, value in enumerate(patch.get(index_delete_key) or []):
            numeric = int(value)
            path = f"$.{index_delete_key}[{index}]"
            if numeric in deletable_indices:
                filtered[index_delete_key].append(numeric)
                accepted.append(path)
            else:
                preserved = original_rows[numeric] if 0 <= numeric < len(original_rows) else None
                ignored.append(_filter_ignored(path, numeric, preserved, "valid_index_delete_ignored"))

        for index, candidate in enumerate(patch.get(upsert_key) or []):
            if not isinstance(candidate, Mapping):
                continue
            row_id = str(candidate.get(id_key) or "")
            path = f"$.{upsert_key}[{index}]"
            original = original_by_id.get(row_id)
            if original is not None:
                if row_id not in mutable_ids:
                    if dict(candidate) != dict(original):
                        ignored.append(_filter_ignored(path, candidate, original, "independent_valid_node_frozen"))
                    continue
                merged, row_ignored, row_accepted = merge_frozen_subtree(
                    original,
                    candidate,
                    mutable_paths=permissions.get(row_id, ()),
                    audit_path=path,
                    # A broken component may be returned as a complete object,
                    # but only exact validator-reported leaves may change or be
                    # added. Every other old value remains frozen.
                    allow_additions=False,
                )
                ignored.extend(row_ignored)
                accepted.extend(row_accepted)
                if merged != original:
                    filtered[upsert_key].append(merged)
                continue

            allowed, reason = _new_row_allowed(namespace, candidate, create_policy)
            if allowed:
                filtered[upsert_key].append(copy.deepcopy(dict(candidate)))
                accepted.append(path)
            else:
                ignored.append(_filter_ignored(path, candidate, None, reason))

    allowed_metadata = set(str(value) for value in scope.get("metadataFields") or [])
    metadata = patch.get("metadataPatch") if isinstance(patch.get("metadataPatch"), Mapping) else {}
    contract = current.get("runtimeContract") if isinstance(current.get("runtimeContract"), Mapping) else {}
    for field, candidate in metadata.items():
        path = f"$.metadataPatch.{field}"
        if field not in allowed_metadata:
            preserved = contract.get("parentSynthesis") if field == "parentSynthesis" else current.get(field)
            ignored.append(_filter_ignored(path, candidate, preserved, "valid_metadata_frozen"))
            continue
        preserved = contract.get("parentSynthesis") if field == "parentSynthesis" else current.get(field)
        permissions = _metadata_permission_paths(scope, field)
        if isinstance(preserved, Mapping) and isinstance(candidate, Mapping):
            merged, field_ignored, field_accepted = merge_frozen_subtree(
                preserved,
                candidate,
                mutable_paths=permissions,
                audit_path=path,
                allow_additions=False,
            )
            ignored.extend(field_ignored)
            accepted.extend(field_accepted)
            if merged != preserved:
                filtered["metadataPatch"][field] = merged
        elif permissions:
            filtered["metadataPatch"][field] = copy.deepcopy(candidate)
            accepted.append(path)
        else:
            ignored.append(_filter_ignored(path, candidate, preserved, "valid_metadata_frozen"))

    strict_filtered_scope = validate_repair_patch_scope(current, filtered, scope)
    report = {
        "schema": RUNTIME_REPAIR_FILTER_REPORT_SCHEMA,
        "ok": bool(strict_filtered_scope.get("ok")),
        "errors": copy.deepcopy(strict_filtered_scope.get("errors") or []),
        "acceptedPaths": sorted(set(accepted)),
        "ignoredChanges": ignored,
        "filteredPatch": copy.deepcopy(filtered),
    }
    return filtered, report


def validate_repair_patch_scope(current: Mapping[str, Any], patch: Mapping[str, Any], scope: Mapping[str, Any]) -> dict[str, Any]:
    shape = strict_repair_shape_report(patch)
    errors: list[dict[str, Any]] = list(shape.get("errors") or [])
    if errors:
        return {"schema": RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA, "ok": False, "errors": errors}

    rows = _program_rows(current)
    existing = {namespace: {str(row.get("id") or "") for row in values if str(row.get("id") or "")} for namespace, values in rows.items()}
    mutable = scope.get("mutable") if isinstance(scope.get("mutable"), Mapping) else {}
    deletable = scope.get("deletable") if isinstance(scope.get("deletable"), Mapping) else {}
    create = scope.get("create") if isinstance(scope.get("create"), Mapping) else {}
    retarget = scope.get("retarget") if isinstance(scope.get("retarget"), Mapping) else {}
    identity = scope.get("identityChanges") if isinstance(scope.get("identityChanges"), Mapping) else {}

    specs = (
        ("entities", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete", "entityIds"),
        ("bindings", "bindingsUpsert", "bindingIdsDelete", "bindingIndicesDelete", "bindingIds"),
        ("calls", "callsUpsert", "callIdsDelete", "callIndicesDelete", "callIds"),
        ("claims", "claimsUpsert", "claimIdsDelete", "claimIndicesDelete", "claimIds"),
    )
    for namespace, upsert_key, delete_key, index_delete_key, scope_key in specs:
        mutable_ids = set(str(value) for value in mutable.get(scope_key) or [])
        deletable_ids = set(str(value) for value in deletable.get(scope_key) or [])
        # The serialized scope uses entityIndices/bindingIndices/etc.
        serialized_index_key = index_delete_key.replace("Delete", "")
        allowed_indices = set(int(value) for value in deletable.get(serialized_index_key) or [])
        for index, value in enumerate(patch.get(delete_key) or []):
            row_id = str(value)
            if row_id not in deletable_ids:
                errors.append(_scope_error(f"$.{delete_key}[{index}]", f"{namespace[:-1]} id '{row_id}' is outside repair delete scope", actual=row_id))
        for index, value in enumerate(patch.get(index_delete_key) or []):
            numeric = int(value)
            if numeric not in allowed_indices:
                errors.append(_scope_error(f"$.{index_delete_key}[{index}]", f"{namespace[:-1]} index {numeric} is outside repair delete scope", actual=numeric))
        create_policy = create.get(namespace) if isinstance(create.get(namespace), Mapping) else {}
        for index, row in enumerate(patch.get(upsert_key) or []):
            if not isinstance(row, Mapping):
                continue
            row_id = str(row.get("id") or "")
            path = f"$.{upsert_key}[{index}]"
            if row_id in existing[namespace]:
                if row_id not in mutable_ids:
                    errors.append(_scope_error(path + ".id", f"existing {namespace[:-1]} '{row_id}' is valid and immutable in this Repair", actual=row_id))
            elif not bool(create_policy.get("allowed")):
                errors.append(_scope_error(path + ".id", f"creating a new {namespace[:-1]} is outside repair scope", actual=row_id))
            elif namespace == "entities":
                exact_ids = set(str(value) for value in create_policy.get("exactIds") or [])
                allowed_kinds = set(str(value) for value in create_policy.get("allowedKinds") or [])
                if exact_ids and row_id not in exact_ids:
                    errors.append(_scope_error(path + ".id", "new entity id is not the exact missing reference", actual=row_id))
                if str(row.get("kind") or "") not in allowed_kinds:
                    errors.append(_scope_error(path + ".kind", "new entity kind is outside the inferred target-kind scope", actual=row.get("kind")))
            elif namespace == "bindings":
                if str(row.get("target") or "") not in set(create_policy.get("allowedTargetIds") or []):
                    errors.append(_scope_error(path + ".target", "new binding target is outside repair scope", actual=row.get("target")))
                if str(row.get("input") or "") not in set(create_policy.get("allowedInputs") or []):
                    errors.append(_scope_error(path + ".input", "new binding input is outside repair scope", actual=row.get("input")))
                if str(row.get("action") or "") not in set(create_policy.get("allowedActions") or []):
                    errors.append(_scope_error(path + ".action", "new binding action is outside repair scope", actual=row.get("action")))
            elif namespace == "calls":
                if str(row.get("target") or "") not in set(create_policy.get("allowedTargetIds") or []):
                    errors.append(_scope_error(path + ".target", "new call target is outside repair scope", actual=row.get("target")))
                if str(row.get("fn") or "") not in set(create_policy.get("allowedFns") or []):
                    errors.append(_scope_error(path + ".fn", "new call capability is outside the deterministic dependency scope", actual=row.get("fn")))
                required_refs = set(str(value) for value in create_policy.get("requiredReferenceEntityIds") or [])
                if required_refs and not required_refs.intersection(_entity_reference_params(row)):
                    errors.append(_scope_error(path + ".params", "new event call must reference the affected unreachable entity"))

            if row_id in existing[namespace]:
                original = next((value for value in rows[namespace] if str(value.get("id") or "") == row_id), {})
                if namespace == "entities" and row_id not in set(identity.get("entityKindIds") or []) and row.get("kind") != original.get("kind"):
                    errors.append(_scope_error(path + ".kind", "entity kind is immutable for this parameter repair", actual=row.get("kind")))
                if namespace == "bindings":
                    if row_id not in set(identity.get("bindingTargetIds") or []) and row.get("target") != original.get("target"):
                        errors.append(_scope_error(path + ".target", "binding target is immutable for this parameter repair", actual=row.get("target")))
                    if row_id not in set(identity.get("bindingInputIds") or []) and row.get("input") != original.get("input"):
                        errors.append(_scope_error(path + ".input", "binding input is immutable for this repair", actual=row.get("input")))
                    if row_id not in set(identity.get("bindingActionIds") or []) and row.get("action") != original.get("action"):
                        errors.append(_scope_error(path + ".action", "binding action is immutable for this repair", actual=row.get("action")))
                if namespace == "calls":
                    if row_id not in set(identity.get("callFnIds") or []) and row.get("fn") != original.get("fn"):
                        errors.append(_scope_error(path + ".fn", "capability identity is immutable; repair params or the reported reference instead", actual=row.get("fn")))
                    if row_id not in set(identity.get("callTargetIds") or []) and row.get("target") != original.get("target"):
                        errors.append(_scope_error(path + ".target", "call target is immutable for this parameter repair", actual=row.get("target")))
                    params = row.get("params") if isinstance(row.get("params"), Mapping) else {}
                    original_params = original.get("params") if isinstance(original.get("params"), Mapping) else {}
                    if row_id not in set(identity.get("callEventIds") or []) and "event" in original_params and params.get("event") != original_params.get("event"):
                        errors.append(_scope_error(path + ".params.event", "event binding is immutable unless the reported error concerns the event", actual=params.get("event")))
                    allowed_ref_changes = set(str(value) for value in identity.get("callReferenceParams") or [])
                    cap = CAPABILITY_REGISTRY.get(str(original.get("fn") or ""))
                    if cap is not None:
                        for param_name, spec in cap.params.items():
                            if spec.reference is None or param_name not in original_params:
                                continue
                            if f"{row_id}:{param_name}" not in allowed_ref_changes and params.get(param_name) != original_params.get(param_name):
                                errors.append(_scope_error(path + f".params.{param_name}", "entity reference is immutable unless that reference is in the repair error", actual=params.get(param_name)))
                if namespace == "claims":
                    if row_id not in set(identity.get("claimKindIds") or []) and row.get("kind") != original.get("kind"):
                        errors.append(_scope_error(path + ".kind", "claim kind is immutable for this repair", actual=row.get("kind")))
                    if row_id not in set(identity.get("claimBackingIds") or []) and row.get("backedBy") != original.get("backedBy"):
                        errors.append(_scope_error(path + ".backedBy", "claim backing is immutable unless the backing itself is invalid", actual=row.get("backedBy")))

            # Complete-node provider responses are permitted, but only scoped identity fields may change.
            if namespace == "bindings" and row_id in existing[namespace] and row_id in set(identity.get("bindingTargetIds") or []):
                allowed_targets = set(str(value) for value in retarget.get("bindingTargetIds") or [])
                original = next((value for value in rows[namespace] if str(value.get("id") or "") == row_id), {})
                allowed_targets.add(str(original.get("target") or ""))
                if str(row.get("target") or "") not in allowed_targets:
                    errors.append(_scope_error(path + ".target", "binding retargets outside compatible repair context", actual=row.get("target")))
            if namespace == "calls" and row_id in existing[namespace] and row_id in set(identity.get("callTargetIds") or []):
                allowed_targets = set(str(value) for value in retarget.get("callTargetIds") or [])
                original = next((value for value in rows[namespace] if str(value.get("id") or "") == row_id), {})
                allowed_targets.add(str(original.get("target") or ""))
                if str(row.get("target") or "") not in allowed_targets:
                    errors.append(_scope_error(path + ".target", "call retargets outside compatible repair context", actual=row.get("target")))

    allowed_metadata = set(str(value) for value in scope.get("metadataFields") or [])
    metadata = patch.get("metadataPatch") if isinstance(patch.get("metadataPatch"), Mapping) else {}
    for key in metadata:
        if key not in allowed_metadata:
            errors.append(_scope_error(f"$.metadataPatch.{key}", f"metadata field '{key}' is valid and immutable in this Repair"))

    return {"schema": RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA, "ok": not errors, "errors": errors}



def runtime_repair_fragments(current: Mapping[str, Any], scope: Mapping[str, Any]) -> dict[str, Any]:
    """Project the failed program into a small but sufficient Repair dossier.

    The model receives complete broken nodes plus a local dependency
    neighbourhood around affected entities.  Independent nodes stay in a
    compact immutable index, so Repair can reason about existing ids without
    paying for or rewriting the whole runtime program.
    """

    rows = _program_rows(current)
    mutable = scope.get("mutable") if isinstance(scope.get("mutable"), Mapping) else {}
    context_ids = scope.get("contextIds") if isinstance(scope.get("contextIds"), Mapping) else {}
    create = scope.get("create") if isinstance(scope.get("create"), Mapping) else {}
    key_by_namespace = {"entities": "entityIds", "bindings": "bindingIds", "calls": "callIds", "claims": "claimIds"}

    mutable_sets = {
        namespace: set(str(value) for value in mutable.get(key_by_namespace[namespace]) or [])
        for namespace in rows
    }
    wanted = {
        namespace: set(str(value) for value in context_ids.get(key_by_namespace[namespace]) or [])
        for namespace in rows
    }

    # Seed the local graph with every affected or newly-targeted entity.
    affected_entities = set(wanted["entities"]) | set(mutable_sets["entities"])
    for policy_name in ("calls", "bindings"):
        policy = create.get(policy_name) if isinstance(create.get(policy_name), Mapping) else {}
        affected_entities.update(str(value) for value in policy.get("allowedTargetIds") or [] if str(value))
        affected_entities.update(str(value) for value in policy.get("requiredTargetIds") or [] if str(value))
    call_create = create.get("calls") if isinstance(create.get("calls"), Mapping) else {}
    affected_entities.update(str(value) for value in call_create.get("requiredReferenceEntityIds") or [] if str(value))
    for requirement in scope.get("repairRequirements") or []:
        if not isinstance(requirement, Mapping):
            continue
        for row_id in requirement.get("affectedIds") or []:
            value = str(row_id or "")
            if any(str(row.get("id") or "") == value for row in rows["entities"]):
                affected_entities.add(value)

    # Mutable bindings/calls bring their target and typed references into the
    # same local neighbourhood.
    for binding in rows["bindings"]:
        if str(binding.get("id") or "") in mutable_sets["bindings"]:
            affected_entities.add(str(binding.get("target") or ""))
    for call in rows["calls"]:
        if str(call.get("id") or "") in mutable_sets["calls"]:
            affected_entities.add(str(call.get("target") or ""))
            affected_entities.update(_entity_reference_params(call))
    affected_entities.discard("")

    # Full valid siblings on an affected entity are useful context: they reveal
    # which component slots, event producers and references already exist.  This
    # is still local and normally only a handful of rows, unlike resending the
    # full capability catalog or the whole item.
    for entity in rows["entities"]:
        entity_id = str(entity.get("id") or "")
        if entity_id in affected_entities and entity_id not in mutable_sets["entities"]:
            wanted["entities"].add(entity_id)
    for binding in rows["bindings"]:
        binding_id = str(binding.get("id") or "")
        if binding_id in mutable_sets["bindings"]:
            continue
        if str(binding.get("target") or "") in affected_entities:
            wanted["bindings"].add(binding_id)
    blocker_plan = scope.get("blockerPlan") if isinstance(scope.get("blockerPlan"), Mapping) else {}
    context_capabilities = {
        str(value)
        for key in ("directCapabilityNames", "supportingCapabilityNames", "existingBrokenCapabilityNames")
        for value in blocker_plan.get(key) or []
        if str(value)
    }
    for call in rows["calls"]:
        call_id = str(call.get("id") or "")
        if call_id in mutable_sets["calls"]:
            continue
        refs = set(_entity_reference_params(call))
        is_local = str(call.get("target") or "") in affected_entities or bool(refs.intersection(affected_entities))
        if call_id in wanted["calls"] or (is_local and str(call.get("fn") or "") in context_capabilities):
            wanted["calls"].add(call_id)
            affected_entities.add(str(call.get("target") or ""))
            affected_entities.update(refs)
    affected_entities.discard("")

    # Claims tied to the local graph are sent read-only as well.
    local_backing_ids = (
        affected_entities
        | wanted["bindings"] | wanted["calls"]
        | mutable_sets["bindings"] | mutable_sets["calls"] | mutable_sets["entities"]
    )
    for claim in rows["claims"]:
        claim_id = str(claim.get("id") or "")
        if claim_id in mutable_sets["claims"]:
            continue
        if local_backing_ids.intersection(str(value) for value in claim.get("backedBy") or []):
            wanted["claims"].add(claim_id)

    broken: dict[str, Any] = {}
    dependency: dict[str, Any] = {}
    summaries: dict[str, Any] = {}
    for namespace, values in rows.items():
        broken[namespace] = [
            copy.deepcopy(row) for row in values
            if str(row.get("id") or "") in mutable_sets[namespace]
        ]
        dependency[namespace] = [
            copy.deepcopy(row) for row in values
            if str(row.get("id") or "") in wanted[namespace]
            and str(row.get("id") or "") not in mutable_sets[namespace]
        ]
        if namespace == "entities":
            summaries[namespace] = [
                {"id": row.get("id"), "kind": row.get("kind"), "visualRole": row.get("visualRole")}
                for row in values
            ]
        elif namespace == "bindings":
            summaries[namespace] = [
                {key: row.get(key) for key in ("id", "input", "action", "target")}
                for row in values
            ]
        elif namespace == "calls":
            summaries[namespace] = [
                {key: row.get(key) for key in ("id", "fn", "target")}
                for row in values
            ]
        else:
            summaries[namespace] = [
                {"id": row.get("id"), "kind": row.get("kind"), "backedBy": copy.deepcopy(row.get("backedBy") or [])}
                for row in values
            ]

    deletable = scope.get("deletable") if isinstance(scope.get("deletable"), Mapping) else {}
    broken_by_index: dict[str, list[dict[str, Any]]] = {}
    for namespace in ("entities", "bindings", "calls", "claims"):
        index_key = namespace[:-1] + "Indices" if namespace != "entities" else "entityIndices"
        indices = [int(value) for value in deletable.get(index_key) or []]
        broken_by_index[namespace] = [
            {"index": index, "value": copy.deepcopy(rows[namespace][index])}
            for index in indices if 0 <= index < len(rows[namespace])
        ]
    return {
        "broken": broken,
        "brokenByIndex": broken_by_index,
        "dependencyContext": dependency,
        "immutableIndex": summaries,
    }


__all__ = [
    "RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA",
    "RUNTIME_REPAIR_SCOPE_SCHEMA",
    "REPAIR_ERROR_POLICY",
    "build_runtime_repair_scope",
    "filter_repair_patch_scope",
    "runtime_repair_fragments",
    "runtime_repair_scope_schema",
    "validate_repair_patch_scope",
]
