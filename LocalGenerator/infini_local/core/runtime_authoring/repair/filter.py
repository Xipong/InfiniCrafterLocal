"""Apply frozen-first write permissions and audit ignored Repair changes."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.repair_merge import json_path_child, json_path_relative, json_values_equal, merge_frozen_subtree
from infini_local.core.runtime_authoring.binding_use_policy import ACTIVE_USE_INPUTS, action_kind, transaction_key
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_SELECTION_FIELD,
    apply_repair_patch,
    strict_repair_structure_report,
)
from infini_local.core.runtime_authoring.repair.facts import (
    _ambiguous_row_ids,
    _binding_target,
    _body_id,
    _call_target,
    _conditional_param_dependencies,
    _entity_reference_params,
    _field_permission_map,
    _graph_rows,
    _mapping,
    _program_index_rows,
    _program_rows,
    _values,
)
from infini_local.core.runtime_authoring.repair.schema import RUNTIME_REPAIR_FILTER_REPORT_SCHEMA
from infini_local.core.runtime_authoring.repair.validation import validate_repair_patch_scope


def _empty_filtered_patch(note: str) -> dict[str, Any]:
    return {
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "bindingsUpsert": [], "bindingIdsDelete": [], "bindingIndicesDelete": [],
        "callsUpsert": [], "callIdsDelete": [], "callIndicesDelete": [],
        "callParamKeysDelete": [], "callPropertyKeysDelete": [],
        "metadataPatch": {}, "note": note or "deterministically filtered targeted repair",
    }


def _filter_ignored(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {
        "path": path,
        "reason": reason,
        "requested": copy.deepcopy(requested),
        "preserved": copy.deepcopy(preserved),
    }


def _new_row_allowed(
    namespace: str,
    row: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    created_entity_kinds: Mapping[str, str] | None = None,
    source_rows: Mapping[str, list[dict[str, Any]]] | None = None,
) -> tuple[bool, str]:
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
        if _binding_target(row, source_rows or {}) not in set(str(value) for value in policy.get("allowedTargetIds") or []):
            return False, "binding_target_not_required"
        if str(row.get("input") or "") not in set(str(value) for value in policy.get("allowedInputs") or []):
            return False, "binding_input_not_allowed"
        if action_kind(row) not in set(str(value) for value in policy.get("allowedActions") or []):
            return False, "binding_action_not_allowed"
        allowed_transactions = [
            value for value in policy.get("allowedTransactions") or []
            if isinstance(value, Mapping)
        ]
        if not any(transaction_key(row, item_body_id=_body_id(source_rows or {})) ==
                   transaction_key(value, item_body_id=_body_id(source_rows or {}))
                   for value in allowed_transactions):
            return False, "binding_transaction_not_in_registry_projection"
        return True, ""
    if namespace == "calls":
        context_rows = {key: list(value) for key, value in (source_rows or {}).items()}
        context_rows["entities"] = [*context_rows.get("entities", []),
                                    *[{"id": key, "kind": kind} for key, kind in (created_entity_kinds or {}).items()]]
        target_id = _call_target(row, context_rows)
        allowed_target_ids = set(str(value) for value in policy.get("allowedTargetIds") or [])
        allowed_target_kinds = set(str(value) for value in policy.get("allowedTargetKinds") or [])
        created_target_kind = str((created_entity_kinds or {}).get(target_id) or "")
        if target_id not in allowed_target_ids and created_target_kind not in allowed_target_kinds:
            return False, "call_target_not_required"
        if str(row.get("fn") or "") not in set(str(value) for value in policy.get("allowedFns") or []):
            return False, "capability_not_in_blocker_closure"
        required_refs = set(str(value) for value in policy.get("requiredReferenceEntityIds") or [])
        if required_refs and not required_refs.intersection(_entity_reference_params(row)):
            return False, "missing_required_affected_entity_reference"
        return True, ""
    return False, "unknown_namespace"


def _metadata_permission_paths(scope: Mapping[str, Any], field: str) -> tuple[str, ...]:
    prefix = f"$.{field}"
    paths: set[str] = set()
    for raw in scope.get("errorPaths") or []:
        path = str(raw or "")
        relative = json_path_relative(path, prefix)
        if relative is not None:
            paths.add(relative)
    return tuple(sorted(paths))


def _metadata_deletion_paths(scope: Mapping[str, Any], field: str) -> tuple[str, ...]:
    """Exact metadata subtrees the validator declared invalid additional properties.

    Only ``shape_additional_property`` authorizes deletion: the key itself is
    outside the strict schema, so a repair response that omits it must drop the
    broken key instead of preserving an unrepresentable value. Deletion is never
    granted for any other validator code.
    """

    prefix = f"$.{field}"
    paths: set[str] = set()
    for requirement in scope.get("repairRequirements") or []:
        if not isinstance(requirement, Mapping):
            continue
        if str(requirement.get("code") or "") != "shape_additional_property":
            continue
        path = str(requirement.get("errorPath") or "")
        relative = json_path_relative(path, prefix)
        if relative:
            paths.add(relative)
    return tuple(sorted(paths))


def filter_repair_patch_scope(
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze accepted values and retain only useful in-scope repair changes.

    Validate patch structure before filtering and merged values strictly after it.
    Attempts to rewrite valid values, independent nodes, or unrequested new
    nodes are ignored and audited, including wrong numeric ranges or conditional
    values in frozen leaves. Malformed types, union shapes and unknown keys are
    rejected before filtering. A missing key is accepted only when the
    validator reported that exact path, or a registry conditional dependency
    requires it for an authorized explicit selector choice. Optional unrequested
    design fields stay absent even in a complete-node response.
    """

    shape = strict_repair_structure_report(patch)
    if not shape.get("ok"):
        return _empty_filtered_patch("invalid repair patch"), {
            "schema": RUNTIME_REPAIR_FILTER_REPORT_SCHEMA,
            "ok": False,
            "errors": copy.deepcopy(shape.get("errors") or []),
            "acceptedPaths": [],
            "ignoredChanges": [],
        }

    rows = _program_rows(current)
    mutable = _mapping(scope.get("mutable"))
    deletable = _mapping(scope.get("deletable"))
    create_raw = scope.get("create")
    create: Mapping[str, Any] = create_raw if isinstance(create_raw, Mapping) else {}
    accepted: list[str] = []
    ignored: list[dict[str, Any]] = []
    filtered = _empty_filtered_patch(str(patch.get("note") or "targeted repair"))
    if "realizationReplacement" in patch:
        filtered["realizationReplacement"] = copy.deepcopy(patch["realizationReplacement"])
        accepted.append("$.realizationReplacement")
    allowed_param_deletes: set[tuple[str, str]] = set()
    for value in deletable.get("callParamKeys") or []:
        if isinstance(value, Mapping):
            allowed_param_deletes.add((str(value.get("callId") or ""), str(value.get("key") or "")))
    allowed_property_deletes: set[tuple[str, str]] = set()
    for value in deletable.get("callPropertyKeys") or []:
        if isinstance(value, Mapping):
            allowed_property_deletes.add((str(value.get("callId") or ""), str(value.get("key") or "")))
    binding_alternative_map = {
        str(row.get("bindingId") or ""): {
            transaction_key(value, item_body_id=_body_id(rows))
            for value in _values(row.get("allowed"))
            if isinstance(value, Mapping)
        }
        for row in _values(scope.get("bindingAlternatives"))
        if isinstance(row, Mapping) and str(row.get("bindingId") or "")
    }
    accepted_param_deletes: set[tuple[str, str]] = set()

    for index, deletion in enumerate(patch.get("callParamKeysDelete") or []):
        if not isinstance(deletion, Mapping):
            continue
        pair = (str(deletion.get("callId") or ""), str(deletion.get("key") or ""))
        path = f"$.callParamKeysDelete[{index}]"
        if pair in allowed_param_deletes:
            filtered["callParamKeysDelete"].append({"callId": pair[0], "key": pair[1]})
            accepted_param_deletes.add(pair)
            accepted.append(path)
        else:
            ignored.append(_filter_ignored(path, deletion, None, "call_param_delete_outside_exact_error_scope"))

    for index, deletion in enumerate(patch.get("callPropertyKeysDelete") or []):
        if not isinstance(deletion, Mapping):
            continue
        pair = (str(deletion.get("callId") or ""), str(deletion.get("key") or ""))
        path = f"$.callPropertyKeysDelete[{index}]"
        if pair in allowed_property_deletes:
            filtered["callPropertyKeysDelete"].append({"callId": pair[0], "key": pair[1]})
            accepted.append(path)
        else:
            ignored.append(_filter_ignored(path, deletion, None, "call_property_delete_outside_exact_error_scope"))

    existing_entity_ids = {
        str(row.get("id") or "") for row in rows["entities"]
        if str(row.get("id") or "")
    }
    specs = (
        ("entities", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete", "entityIds", "id"),
        ("bindings", "bindingsUpsert", "bindingIdsDelete", "bindingIndicesDelete", "bindingIds", "id"),
        ("calls", "callsUpsert", "callIdsDelete", "callIndicesDelete", "callIds", "id"),
    )
    for namespace, upsert_key, delete_key, index_delete_key, scope_key, id_key in specs:
        original_rows = rows[namespace]
        indexed_rows = _program_index_rows(current)[namespace]
        ambiguous_ids = _ambiguous_row_ids(original_rows)
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
        create_policy_raw = create.get(namespace)
        create_policy: Mapping[str, Any] = create_policy_raw if isinstance(create_policy_raw, Mapping) else {}

        for index, value in enumerate(patch.get(delete_key) or []):
            row_id = str(value)
            path = f"$.{delete_key}[{index}]"
            if row_id in deletable_ids and row_id not in ambiguous_ids:
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
                preserved = indexed_rows[numeric] if 0 <= numeric < len(indexed_rows) else None
                ignored.append(_filter_ignored(path, numeric, preserved, "valid_index_delete_ignored"))

        for index, candidate in enumerate(patch.get(upsert_key) or []):
            if not isinstance(candidate, Mapping):
                continue
            row_id = str(candidate.get(id_key) or "")
            path = f"$.{upsert_key}[{index}]"
            if row_id in ambiguous_ids:
                ignored.append(_filter_ignored(path, candidate, None, "ambiguous_id_requires_index_deletion"))
                continue
            original = original_by_id.get(row_id)
            if original is not None:
                if row_id not in mutable_ids:
                    if not json_values_equal(dict(candidate), dict(original)):
                        ignored.append(_filter_ignored(path, candidate, original, "independent_valid_node_frozen"))
                    continue
                if namespace == "bindings":
                    actual_transaction = transaction_key(candidate, item_body_id=_body_id(rows))
                    allowed_transactions = binding_alternative_map.get(row_id)
                    # An alternative is a complete transaction only when Repair
                    # may replace the atomic usePolicy. A missing/invalid leaf
                    # must still pass through the frozen-subtree merge below.
                    if (allowed_transactions is not None
                            and actual_transaction in allowed_transactions
                            and {""}.intersection(permissions.get(row_id, ()))):
                        replacement = copy.deepcopy(dict(candidate))
                        if not json_values_equal(replacement, original):
                            filtered[upsert_key].append(replacement)
                            accepted.append(path)
                        continue
                row_permissions = set(permissions.get(row_id, ()))
                if namespace == "bindings" and "action" in row_permissions and "action" not in original:
                    # A permitted explicit action closes only its schema-required
                    # independent lanes. No decision is copied out of a foreign wrapper.
                    if action_kind(candidate) != "place_item" and candidate.get("input") in ACTIVE_USE_INPUTS:
                        row_permissions.update(key for key in ("stackCost", "contactDamage") if key not in original)
                row_deletions: list[str] = []
                if namespace == "calls":
                    original_params_raw = original.get("params")
                    candidate_params_raw = candidate.get("params")
                    original_params: Mapping[str, Any] = original_params_raw if isinstance(original_params_raw, Mapping) else {}
                    candidate_params: Mapping[str, Any] = candidate_params_raw if isinstance(candidate_params_raw, Mapping) else {}
                    cap = CAPABILITY_REGISTRY.get(str(original.get("fn") or ""))
                    if cap is not None:
                        for param_name, param_spec in cap.params.items():
                            # A whole invalid union permission permits an explicit
                            # complete model-authored variant, not a union of old/new.
                            # Leaf-only repairs and omitted params never retire branches.
                            if (not param_spec.alternatives or f"params.{param_name}" not in row_permissions
                                    or param_name not in candidate_params
                                    or not isinstance(original_params.get(param_name), Mapping)):
                                continue
                            try:
                                param_spec.selected_variant(candidate_params[param_name])
                            except ValueError:
                                continue
                            if isinstance(candidate_params[param_name], Mapping):
                                row_deletions.extend(
                                    json_path_child(f"params.{param_name}", key)
                                    for key in original_params[param_name]
                                    if key not in candidate_params[param_name]
                                )
                        dependencies = _conditional_param_dependencies(cap)
                        selected_missing = {
                            required for selector, expected, required in dependencies
                            if required not in original_params
                            and f"params.{selector}" in row_permissions
                            and json_values_equal(candidate_params.get(selector, original_params.get(selector)), expected)
                        }
                        for selector, expected, required in dependencies:
                            if (required not in original_params
                                    and f"params.{selector}" in row_permissions
                                    and required not in selected_missing):
                                row_permissions.discard(f"params.{required}")
                    inert_repair = any(
                        requirement.get("code") == "inert_component"
                        and row_id in requirement.get("affectedIds", [])
                        for requirement in _values(scope.get("repairRequirements"))
                        if isinstance(requirement, Mapping)
                    )
                    if cap is not None and inert_repair:
                        effective_params = dict(original_params)
                        effective_params.update({
                            key: value for key, value in candidate_params.items()
                            if f"params.{key}" in row_permissions
                        })
                        for requirement in cap.requirements:
                            if (requirement.kind == "positive_param_requires_param"
                                    and requirement.param not in original_params
                                    and not any(
                                        isinstance(effective_params.get(key), (int, float))
                                        and not isinstance(effective_params.get(key), bool)
                                        and effective_params[key] > 0
                                        for key in requirement.nonzero_params
                                    )):
                                row_permissions.discard(f"params.{requirement.param}")
                    for pair in sorted(allowed_param_deletes):
                        call_id, key = pair
                        if call_id != row_id or key not in original_params or key in candidate_params or pair in accepted_param_deletes:
                            continue
                        filtered["callParamKeysDelete"].append({"callId": call_id, "key": key})
                        accepted_param_deletes.add(pair)
                        accepted.append(json_path_child(path + ".params", key))
                merged, row_ignored, row_accepted = merge_frozen_subtree(
                    original,
                    candidate,
                    mutable_paths=row_permissions,
                    audit_path=path,
                    # A broken component may be returned as a complete object,
                    # but only exact error/dependency leaves may change or be
                    # added. Every other old value remains frozen.
                    allow_additions=False,
                    delete_paths=tuple(row_deletions) + _metadata_deletion_paths(scope, f"runtimeProgram.{namespace}[{next(i for i, row in enumerate(indexed_rows) if isinstance(row, Mapping) and row.get(id_key) == row_id)}]"),
                )
                ignored.extend(row_ignored)
                accepted.extend(row_accepted)
                if namespace == "calls" and isinstance(merged, dict):
                    merged_params_raw = merged.get("params")
                    if isinstance(merged_params_raw, dict):
                        for call_id, key in accepted_param_deletes:
                            if call_id == row_id:
                                merged_params_raw.pop(key, None)
                if not json_values_equal(merged, original):
                    filtered[upsert_key].append(merged)
                continue

            accepted_created_entity_kinds = {
                str(value.get("id") or ""): str(value.get("kind") or "")
                for value in filtered["entitiesUpsert"]
                if isinstance(value, Mapping)
                and str(value.get("id") or "") not in existing_entity_ids
            }
            allowed, reason = _new_row_allowed(
                namespace,
                candidate,
                create_policy,
                created_entity_kinds=accepted_created_entity_kinds,
                source_rows=_graph_rows(current),
            )
            if allowed:
                filtered[upsert_key].append(copy.deepcopy(dict(candidate)))
                accepted.append(path)
            else:
                ignored.append(_filter_ignored(path, candidate, None, reason))

    # Conditional omission dependencies are evaluated after every authorized
    # context edit has been frozen, so call order cannot change permission.
    def effective_rows(namespace: str, upsert_key: str, delete_key: str, index_delete_key: str) -> list[Mapping[str, Any]]:
        replacements = {str(row.get("id") or ""): row for row in filtered[upsert_key]}
        deleted, deleted_indices = set(filtered[delete_key]), set(filtered[index_delete_key])
        originals = _program_index_rows(current)[namespace]
        existing_ids = {str(row.get("id") or "") for row in originals if isinstance(row, Mapping)}
        result = [replacements.get(str(row.get("id") or ""), row) for index, row in enumerate(originals)
                  if isinstance(row, Mapping) and index not in deleted_indices and str(row.get("id") or "") not in deleted]
        result.extend(row for row_id, row in replacements.items() if row_id not in existing_ids)
        return result
    effective_entities = effective_rows("entities", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete")
    effective_calls = effective_rows("calls", "callsUpsert", "callIdsDelete", "callIndicesDelete")
    original_calls = {str(row.get("id") or ""): row for row in rows["calls"]}
    for call in filtered["callsUpsert"]:
        original = original_calls.get(str(call.get("id") or ""))
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if original is None or cap is None or original.get("fn") != call.get("fn"):
            continue
        old_params, params = _mapping(original.get("params")), call.get("params")
        if not isinstance(params, dict):
            continue
        target = original.get("target")
        old_kind = next((str(row.get("kind") or "") for row in rows["entities"] if row.get("id") == target), "")
        old_support = [str(row.get("fn") or "") for row in rows["calls"] if row.get("target") == target]
        new_kind = next((str(row.get("kind") or "") for row in effective_entities if row.get("id") == call.get("target")), "")
        new_support = [str(row.get("fn") or "") for row in effective_calls if row.get("target") == call.get("target")]
        for name, spec in cap.params.items():
            condition = spec.omission_condition
            if (condition is not None and name not in old_params and name in params
                    and condition.allows(old_params, old_kind, old_support)
                    and condition.allows(params, new_kind, new_support)):
                candidate = params.pop(name)
                patch_index = next(i for i, row in enumerate(patch.get("callsUpsert", [])) if row.get("id") == call.get("id"))
                path = f"$.callsUpsert[{patch_index}].params.{name}"
                accepted[:] = [value for value in accepted if value != path]
                ignored.append(_filter_ignored(path, candidate, None, "inactive_omission_stays_frozen"))

    allowed_metadata = set(str(value) for value in _values(scope.get("metadataFields")))
    metadata = _mapping(patch.get("metadataPatch"))
    for field, candidate in metadata.items():
        path = f"$.metadataPatch.{field}"
        if field not in allowed_metadata:
            preserved = current.get(field)
            ignored.append(_filter_ignored(path, candidate, preserved, "valid_metadata_frozen"))
            continue
        preserved = current.get(field)
        permissions = _metadata_permission_paths(scope, field)
        deletions = _metadata_deletion_paths(scope, field)
        if isinstance(preserved, Mapping) and isinstance(candidate, Mapping):
            merged, field_ignored, field_accepted = merge_frozen_subtree(
                preserved,
                candidate,
                mutable_paths=permissions,
                audit_path=path,
                allow_additions=False,
                delete_paths=deletions,
            )
            ignored.extend(field_ignored)
            accepted.extend(field_accepted)
            if not json_values_equal(merged, preserved):
                filtered["metadataPatch"][field] = merged
        elif permissions:
            filtered["metadataPatch"][field] = copy.deepcopy(candidate)
            accepted.append(path)
        else:
            ignored.append(_filter_ignored(path, candidate, preserved, "valid_metadata_frozen"))

    if patch.get(PRIMARY_ENTITY_SELECTION_FIELD) is not None:
        filtered[PRIMARY_ENTITY_SELECTION_FIELD] = copy.deepcopy(patch.get(PRIMARY_ENTITY_SELECTION_FIELD))
        accepted.append("$.primaryEntitySelection")
    if "exclusiveInputSelections" in patch:
        filtered["exclusiveInputSelections"] = []
        preview_patch = copy.deepcopy(filtered)
        preview_patch["exclusiveInputSelections"] = []
        preview = _mapping(apply_repair_patch(current, preview_patch))
        preview_program = _mapping(preview.get("runtimeProgram"))
        preview_bindings = _values(preview_program.get("bindings"))
        for index, selection in enumerate(_values(patch.get("exclusiveInputSelections"))):
            if not isinstance(selection, Mapping):
                continue
            input_name = str(selection.get("input") or "")
            remaining_owners = [
                str(row.get("id") or "")
                for row in preview_bindings
                if isinstance(row, Mapping) and str(row.get("input") or "") == input_name
            ]
            path = f"$.exclusiveInputSelections[{index}]"
            if len(remaining_owners) <= 1:
                ignored.append(_filter_ignored(
                    path,
                    selection,
                    {"remainingBindingIds": remaining_owners},
                    "exclusive_input_conflict_already_resolved",
                ))
                continue
            filtered["exclusiveInputSelections"].append(copy.deepcopy(dict(selection)))
            accepted.append(path)

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
