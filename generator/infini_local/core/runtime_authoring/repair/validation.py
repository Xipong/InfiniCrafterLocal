"""Validate a proposed Repair patch against exact authorized scope."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.repair_merge import json_values_equal
from infini_local.core.runtime_authoring.binding_use_policy import action_kind, contact_damage, transaction_key
from infini_local.core.runtime_authoring.capability_registry import BINDING_ACTION_REGISTRY, CAPABILITY_REGISTRY, authored_event
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_SELECTION_FIELD,
    apply_repair_patch,
    strict_repair_shape_report,
)
from infini_local.core.runtime_authoring.repair.choices import _reachability_safe_exclusive_candidates
from infini_local.core.runtime_authoring.repair.facts import (
    _binding_target,
    _body_id,
    _call_target,
    _entity_reference_params,
    _field_permission_map,
    _graph_rows,
    _mapping,
    _program_rows,
    _rows,
    _values,
)
from infini_local.core.runtime_authoring.repair.schema import RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA
from infini_local.core.runtime_authoring.validator import validate_runtime_program


def _scope_error(path: str, message: str, *, actual: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"path": path, "code": "repair_scope_violation", "message": message}
    if actual is not None:
        row["actual"] = actual
    return row


def validate_repair_patch_scope(current: Mapping[str, Any], patch: Mapping[str, Any], scope: Mapping[str, Any]) -> dict[str, Any]:
    shape = strict_repair_shape_report(patch)
    errors: list[dict[str, Any]] = list(shape.get("errors") or [])
    if errors:
        return {"schema": RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA, "ok": False, "errors": errors}

    rows = _graph_rows(current)
    existing = {namespace: {str(row.get("id") or "") for row in values if str(row.get("id") or "")} for namespace, values in rows.items()}
    mutable = _mapping(scope.get("mutable"))
    deletable = _mapping(scope.get("deletable"))
    create = _mapping(scope.get("create"))
    retarget = _mapping(scope.get("retarget"))
    identity = _mapping(scope.get("identityChanges"))
    binding_alternative_map = {
        str(row.get("bindingId") or ""): {
            transaction_key(value, item_body_id=_body_id(rows))
            for value in _values(row.get("allowed"))
            if isinstance(value, Mapping)
        }
        for row in _values(scope.get("bindingAlternatives"))
        if isinstance(row, Mapping) and str(row.get("bindingId") or "")
    }

    patch_binding_rows = [
        row for row in _values(patch.get("bindingsUpsert"))
        if isinstance(row, Mapping)
    ]
    patch_bindings_by_id: dict[str, list[Mapping[str, Any]]] = {}
    for row in patch_binding_rows:
        patch_bindings_by_id.setdefault(str(row.get("id") or ""), []).append(row)

    def serialized_binding_transaction(row: Mapping[str, Any]) -> str:
        return transaction_key(row, item_body_id=_body_id(rows))

    for requirement_index, requirement in enumerate(_values(scope.get("repairRequirements"))):
        if not isinstance(requirement, Mapping):
            continue
        for update_index, update in enumerate(_values(requirement.get("requiredBindingUpdates"))):
            if not isinstance(update, Mapping):
                continue
            binding_id = str(update.get("bindingId") or "")
            allowed_updates = {
                serialized_binding_transaction(row)
                for row in _values(update.get("allowed"))
                if isinstance(row, Mapping)
            }
            candidates = patch_bindings_by_id.get(binding_id, [])
            if len(candidates) != 1 or serialized_binding_transaction(candidates[0]) not in allowed_updates:
                errors.append(_scope_error(
                    f"$.repairRequirements[{requirement_index}].requiredBindingUpdates[{update_index}]",
                    "patch must emit the exact required existing-binding transaction once",
                    actual={"bindingId": binding_id, "candidateCount": len(candidates)},
                ))
        allowed_new_transactions = {
            serialized_binding_transaction(row)
            for row in _values(requirement.get("allowedBindingTransactions"))
            if isinstance(row, Mapping)
        }
        allowed_existing_binding_ids = {
            str(value) for value in _values(requirement.get("allowedExistingBindingIds"))
            if str(value)
        }
        matching_transactions = [
            row for row in patch_binding_rows
            if serialized_binding_transaction(row) in allowed_new_transactions
        ]
        unauthorized_existing = [
            row for row in matching_transactions
            if str(row.get("id") or "") in existing["bindings"]
            and str(row.get("id") or "") not in allowed_existing_binding_ids
        ]
        if unauthorized_existing:
            errors.append(_scope_error(
                f"$.repairRequirements[{requirement_index}].allowedExistingBindingIds",
                "existing binding transaction is outside this requirement's existing binding choices",
                actual={
                    "bindingIds": sorted(str(row.get("id") or "") for row in unauthorized_existing),
                },
            ))
        must_create_exactly_one = bool(requirement.get("mustCreateExactlyOne"))
        if must_create_exactly_one and allowed_new_transactions:
            selected_new = [
                row for row in matching_transactions
                if str(row.get("id") or "") not in existing["bindings"]
            ]
            if len(matching_transactions) != 1 or len(selected_new) != 1:
                errors.append(_scope_error(
                    f"$.repairRequirements[{requirement_index}].allowedBindingTransactions",
                    "patch must emit exactly one listed binding transaction and that transaction must be new",
                    actual={
                        "matchingCount": len(matching_transactions),
                        "newCount": len(selected_new),
                    },
                ))
        elif bool(requirement.get("mustChooseExactlyOne")) and allowed_new_transactions:
            selected = [
                row for row in matching_transactions
                if str(row.get("id") or "") not in existing["bindings"]
                or str(row.get("id") or "") in allowed_existing_binding_ids
            ]
            if len(selected) != 1:
                errors.append(_scope_error(
                    f"$.repairRequirements[{requirement_index}].allowedBindingTransactions",
                    "patch must emit exactly one listed binding transaction",
                    actual={"selectedCount": len(selected)},
                ))

    allowed_param_deletes: set[tuple[str, str]] = set()
    for value in deletable.get("callParamKeys") or []:
        if isinstance(value, Mapping):
            allowed_param_deletes.add((str(value.get("callId") or ""), str(value.get("key") or "")))
    for index, deletion in enumerate(patch.get("callParamKeysDelete") or []):
        if not isinstance(deletion, Mapping):
            continue
        pair = (str(deletion.get("callId") or ""), str(deletion.get("key") or ""))
        if pair not in allowed_param_deletes:
            errors.append(_scope_error(
                f"$.callParamKeysDelete[{index}]",
                "call parameter deletion is outside the exact additional-property error scope",
                actual={"callId": pair[0], "key": pair[1]},
            ))
    allowed_property_deletes: set[tuple[str, str]] = set()
    for value in deletable.get("callPropertyKeys") or []:
        if isinstance(value, Mapping):
            allowed_property_deletes.add((str(value.get("callId") or ""), str(value.get("key") or "")))
    for index, deletion in enumerate(patch.get("callPropertyKeysDelete") or []):
        if not isinstance(deletion, Mapping):
            continue
        pair = (str(deletion.get("callId") or ""), str(deletion.get("key") or ""))
        if pair not in allowed_property_deletes:
            errors.append(_scope_error(
                f"$.callPropertyKeysDelete[{index}]",
                "call property deletion is outside the exact additional-property error scope",
                actual={"callId": pair[0], "key": pair[1]},
            ))

    patch_created_entity_kinds = {
        str(row.get("id") or ""): str(row.get("kind") or "")
        for row in patch.get("entitiesUpsert") or []
        if isinstance(row, Mapping)
        and str(row.get("id") or "") not in existing["entities"]
    }
    specs = (
        ("entities", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete", "entityIds"),
        ("bindings", "bindingsUpsert", "bindingIdsDelete", "bindingIndicesDelete", "bindingIds"),
        ("calls", "callsUpsert", "callIdsDelete", "callIndicesDelete", "callIds"),
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
        create_policy_raw = create.get(namespace)
        create_policy: Mapping[str, Any] = create_policy_raw if isinstance(create_policy_raw, Mapping) else {}
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
                if _binding_target(row, rows) not in set(create_policy.get("allowedTargetIds") or []):
                    errors.append(_scope_error(path + ".action.targetId", "new binding target is outside repair scope", actual=_binding_target(row, rows)))
                if str(row.get("input") or "") not in set(create_policy.get("allowedInputs") or []):
                    errors.append(_scope_error(path + ".input", "new binding input is outside repair scope", actual=row.get("input")))
                if action_kind(row) not in set(create_policy.get("allowedActions") or []):
                    errors.append(_scope_error(path + ".action.kind", "new binding action is outside repair scope", actual=action_kind(row)))
            elif namespace == "calls":
                target_id = _call_target(row, {**rows, "entities": [*rows["entities"], *[{"id": key, "kind": kind} for key, kind in patch_created_entity_kinds.items()]]})
                allowed_target_ids = set(str(value) for value in create_policy.get("allowedTargetIds") or [])
                allowed_target_kinds = set(str(value) for value in create_policy.get("allowedTargetKinds") or [])
                if (
                    target_id not in allowed_target_ids
                    and patch_created_entity_kinds.get(target_id) not in allowed_target_kinds
                ):
                    errors.append(_scope_error(path + ".target", "new call target is outside repair scope", actual=row.get("target")))
                if str(row.get("fn") or "") not in set(create_policy.get("allowedFns") or []):
                    errors.append(_scope_error(path + ".fn", "new call capability is outside the deterministic dependency scope", actual=row.get("fn")))
                required_refs = set(str(value) for value in create_policy.get("requiredReferenceEntityIds") or [])
                if required_refs and not required_refs.intersection(_entity_reference_params(row)):
                    errors.append(_scope_error(path + ".params", "new event call must reference the affected unreachable entity"))

            if row_id in existing[namespace]:
                original_raw = next(
                    (value for value in _program_rows(current)[namespace] if str(value.get("id") or "") == row_id),
                    {},
                )
                original = _mapping(original_raw)
                if namespace == "entities" and row_id not in set(_values(identity.get("entityKindIds"))) and row.get("kind") != original.get("kind"):
                    errors.append(_scope_error(path + ".kind", "entity kind is immutable for this parameter repair", actual=row.get("kind")))
                if namespace == "bindings":
                    original_target = _binding_target(original, rows)
                    allowed_transactions = binding_alternative_map.get(row_id)
                    actual_transaction = transaction_key(row, item_body_id=_body_id(rows))
                    corrected_selectors = copy.deepcopy(dict(original))
                    binding_permissions = _field_permission_map(scope, "bindings").get(row_id, ())
                    if (row_id in set(_values(identity.get("bindingInputIds")))
                            and "input" in binding_permissions):
                        corrected_selectors["input"] = row.get("input")
                    if (row_id in set(_values(identity.get("bindingActionIds")))
                            and "action.kind" in binding_permissions):
                        corrected_selectors["action"] = {
                            **_mapping(original.get("action")),
                            "kind": _mapping(row.get("action")).get("kind"),
                        }
                    corrected_action = BINDING_ACTION_REGISTRY.get(action_kind(corrected_selectors))
                    if ("targetId" not in _mapping(original.get("action"))
                            and "targetId" not in _mapping(row.get("action"))
                            and not original_target and not action_kind(original)
                            and not json_values_equal(corrected_selectors, original)
                            and allowed_transactions is not None and actual_transaction in allowed_transactions
                            and corrected_action is not None and corrected_action.target_kinds == ("item_body",)
                            and _body_id(rows)):
                        # Comparison only: an explicit, scoped selector chooses
                        # the fixed body owner. Keep raw target absence intact.
                        original_target = _binding_target(corrected_selectors, rows)
                    if row_id not in set(_values(identity.get("bindingTargetIds"))) and ("action" in row or "action" in original) and _binding_target(row, rows) != original_target:
                        errors.append(_scope_error(path + ".action.targetId", "binding target is immutable for this parameter repair", actual=_binding_target(row, rows)))
                    if row_id not in set(_values(identity.get("bindingInputIds"))) and row.get("input") != original.get("input"):
                        errors.append(_scope_error(path + ".input", "binding input is immutable for this repair", actual=row.get("input")))
                    if row_id not in set(_values(identity.get("bindingActionIds"))) and _mapping(row.get("action")).get("kind") != _mapping(original.get("action")).get("kind"):
                        errors.append(_scope_error(path + ".action.kind", "binding action is immutable for this repair", actual=action_kind(row)))
                    if allowed_transactions is not None and actual_transaction not in allowed_transactions:
                        errors.append(_scope_error(
                            path,
                            "complete binding use transaction is outside canonical repair alternatives",
                            actual={
                                "input": str(row.get("input") or ""),
                                **{key: copy.deepcopy(row[key]) for key in ("action", "stackCost", "contactDamage", "stackConsumeChancePercent") if key in row},
                            },
                        ))
                if namespace == "calls":
                    if row_id not in set(_values(identity.get("callFnIds"))) and row.get("fn") != original.get("fn"):
                        errors.append(_scope_error(path + ".fn", "capability identity is immutable; repair params or the reported reference instead", actual=row.get("fn")))
                    if row_id not in set(_values(identity.get("callTargetIds"))) and _call_target(row, rows) != _call_target(original, rows):
                        errors.append(_scope_error(path + ".target", "call target is immutable for this parameter repair", actual=row.get("target")))
                    params = _mapping(row.get("params"))
                    original_params = _mapping(original.get("params"))
                    if row_id not in set(_values(identity.get("callEventIds"))) and "when" in original_params and authored_event(params) != authored_event(original_params):
                        errors.append(_scope_error(path + ".params.when", "event binding is immutable unless the reported error concerns the event", actual=params.get("when")))
                    allowed_ref_changes = set(str(value) for value in _values(identity.get("callReferenceParams")))
                    cap = CAPABILITY_REGISTRY.get(str(original.get("fn") or ""))
                    if cap is not None:
                        for param_name, spec in cap.params.items():
                            if spec.reference is None or param_name not in original_params:
                                continue
                            if f"{row_id}:{param_name}" not in allowed_ref_changes and params.get(param_name) != original_params.get(param_name):
                                errors.append(_scope_error(path + f".params.{param_name}", "entity reference is immutable unless that reference is in the repair error", actual=params.get(param_name)))
            # Complete-node provider responses are permitted, but only scoped identity fields may change.
            if namespace == "bindings" and row_id in existing[namespace] and row_id in set(_values(identity.get("bindingTargetIds"))):
                allowed_targets = set(str(value) for value in _values(retarget.get("bindingTargetIds")))
                original = _mapping(next((value for value in _program_rows(current)[namespace] if str(value.get("id") or "") == row_id), {}))
                allowed_targets.add(_binding_target(original, rows))
                if _binding_target(row, rows) not in allowed_targets:
                    errors.append(_scope_error(path + ".action.targetId", "binding retargets outside compatible repair context", actual=_binding_target(row, rows)))
            if namespace == "calls" and row_id in existing[namespace] and row_id in set(_values(identity.get("callTargetIds"))):
                allowed_targets = set(str(value) for value in _values(retarget.get("callTargetIds")))
                original = _mapping(next((value for value in _program_rows(current)[namespace] if str(value.get("id") or "") == row_id), {}))
                allowed_targets.add(_call_target(original, rows))
                if _call_target(row, rows) not in allowed_targets:
                    errors.append(_scope_error(path + ".target", "call retargets outside compatible repair context", actual=row.get("target")))

    transactions = _mapping(scope.get("repairTransactions"))
    primary_transaction = _mapping(transactions.get(PRIMARY_ENTITY_SELECTION_FIELD))
    if patch.get(PRIMARY_ENTITY_SELECTION_FIELD) is not None:
        selected = str(patch.get(PRIMARY_ENTITY_SELECTION_FIELD) or "")
        candidates = set(str(value) for value in primary_transaction.get("candidateEntityIds") or [])
        if not bool(primary_transaction.get("allowed")) or selected not in candidates:
            errors.append(_scope_error(
                "$.primaryEntitySelection",
                "primary entity choice is outside the exact authored-identity transaction",
                actual=selected,
            ))

    raw_event_alternatives = scope.get("eventAlternatives")
    event_transactions = raw_event_alternatives if isinstance(raw_event_alternatives, list) else []
    if event_transactions:
        preview = _mapping(apply_repair_patch(current, patch))
        preview_program = _mapping(preview.get("runtimeProgram"))
        preview_calls = [row for row in _values(preview_program.get("calls")) if isinstance(row, Mapping)]
        preview_bindings = [row for row in _values(preview_program.get("bindings")) if isinstance(row, Mapping)]
        preview_calls_by_id = {
            str(row.get("id") or ""): row
            for row in preview_calls
            if str(row.get("id") or "")
        }
        all_event_call_keys: set[tuple[str, str]] = set()
        selected_event_call_keys: set[tuple[str, str]] = set()
        all_event_binding_inputs: set[str] = set()
        selected_event_binding_inputs: set[str] = set()
        for transaction in event_transactions:
            if not isinstance(transaction, Mapping):
                continue
            call_id = str(transaction.get("callId") or "")
            target_id = str(transaction.get("targetId") or "")
            call = preview_calls_by_id.get(call_id, {})
            raw_params = call.get("params")
            params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
            selected_event = authored_event(params)
            allowed_rows = [row for row in transaction.get("allowed") or [] if isinstance(row, Mapping)]
            alternatives = [
                row for row in allowed_rows
                if str(row.get("event") or "") == selected_event
            ]
            for alternative in allowed_rows:
                is_selected = str(alternative.get("event") or "") == selected_event
                for requirement in alternative.get("requiredCalls") or []:
                    if not isinstance(requirement, Mapping):
                        continue
                    key = (
                        str(requirement.get("fn") or ""),
                        str(requirement.get("targetId") or ""),
                    )
                    all_event_call_keys.add(key)
                    if is_selected:
                        selected_event_call_keys.add(key)
                for requirement in alternative.get("requiredBindings") or []:
                    if not isinstance(requirement, Mapping):
                        continue
                    inputs = {str(value) for value in requirement.get("anyOfInputs") or []}
                    all_event_binding_inputs.update(inputs)
                    if is_selected:
                        selected_event_binding_inputs.update(inputs)

            def alternative_complete(alternative: Mapping[str, Any]) -> bool:
                for requirement in alternative.get("requiredCalls") or []:
                    if not isinstance(requirement, Mapping):
                        return False
                    required_fn = str(requirement.get("fn") or "")
                    required_target = str(requirement.get("targetId") or "")
                    exact_rows = [row for row in requirement.get("exactParams") or [] if isinstance(row, Mapping)]
                    def candidate_satisfies(candidate: Mapping[str, Any]) -> bool:
                        if (
                            str(candidate.get("fn") or "") != required_fn
                            or str(candidate.get("target") or "") != required_target
                        ):
                            return False
                        raw_candidate_params = candidate.get("params")
                        candidate_params: Mapping[str, Any] = (
                            raw_candidate_params if isinstance(raw_candidate_params, Mapping) else {}
                        )
                        return all(
                            candidate_params.get(str(exact.get("param") or "")) == exact.get("value")
                            for exact in exact_rows
                        )

                    if not any(candidate_satisfies(candidate) for candidate in preview_calls):
                        return False
                for requirement in alternative.get("requiredBindings") or []:
                    if not isinstance(requirement, Mapping):
                        return False
                    required_target = str(requirement.get("targetId") or "")
                    allowed_inputs = {str(value) for value in requirement.get("anyOfInputs") or []}
                    allowed_actions = {str(value) for value in requirement.get("anyOfActions") or []}
                    required_contact = requirement.get("requiredContactDamage")
                    if not any(
                        _binding_target(binding, rows) == required_target
                        and str(binding.get("input") or "") in allowed_inputs
                        and (not allowed_actions or action_kind(binding) in allowed_actions)
                        and (
                            required_contact is None
                            or contact_damage(binding) is required_contact
                        )
                        for binding in preview_bindings
                    ):
                        return False
                return True

            if not any(alternative_complete(row) for row in alternatives):
                errors.append(_scope_error(
                    f"$.runtimeProgram.calls[{call_id}].params.when",
                    "event selection must include one complete exact producer alternative in the same repair",
                    actual={"event": selected_event, "targetId": target_id},
                ))

        independent_affected_ids: set[str] = set()
        independent_required_fns: set[str] = set()
        independent_binding_target_ids: set[str] = set()
        raw_requirements = scope.get("repairRequirements")
        for requirement in raw_requirements if isinstance(raw_requirements, list) else []:
            if not isinstance(requirement, Mapping):
                continue
            code = str(requirement.get("code") or "")
            if code == "capability_event_incompatible":
                continue
            affected = {str(value) for value in requirement.get("affectedIds") or []}
            independent_affected_ids.update(affected)
            independent_required_fns.update(
                str(value) for value in requirement.get("requiredOneOfCapabilities") or []
            )
            if code in {"event_not_emitted", "unreachable_entity"}:
                independent_binding_target_ids.update(affected)

        selected_event_new_calls: dict[tuple[str, str], list[tuple[int, str]]] = {}
        for index, row in enumerate(patch.get("callsUpsert") or []):
            if not isinstance(row, Mapping):
                continue
            row_id = str(row.get("id") or "")
            fn = str(row.get("fn") or "")
            key = (fn, str(row.get("target") or ""))
            if (
                key in all_event_call_keys
                and key not in selected_event_call_keys
                and row_id not in independent_affected_ids
                and fn not in independent_required_fns
            ):
                errors.append(_scope_error(
                    f"$.callsUpsert[{index}]",
                    "event producer belongs to an unselected event alternative",
                    actual={"id": row_id, "fn": fn, "targetId": key[1]},
                ))
            if row_id not in existing["calls"] and key in selected_event_call_keys:
                selected_event_new_calls.setdefault(key, []).append((index, row_id))

        current_call_keys = {
            (str(row.get("fn") or ""), str(row.get("target") or ""))
            for row in rows["calls"]
        }
        for key, candidates in selected_event_new_calls.items():
            redundant = candidates if key in current_call_keys else candidates[1:]
            for index, row_id in redundant:
                errors.append(_scope_error(
                    f"$.callsUpsert[{index}]",
                    "selected event alternative requires at most one new producer call per exact fn/target",
                    actual={"id": row_id, "fn": key[0], "targetId": key[1]},
                ))

        selected_event_new_bindings: list[tuple[int, str, str, str]] = []
        for index, row in enumerate(patch.get("bindingsUpsert") or []):
            if not isinstance(row, Mapping):
                continue
            row_id = str(row.get("id") or "")
            input_name = str(row.get("input") or "")
            target_id = _call_target(row, rows)
            independently_required = (
                row_id in independent_affected_ids
                or target_id in independent_binding_target_ids
            )
            if (
                input_name in all_event_binding_inputs
                and input_name not in selected_event_binding_inputs
                and not independently_required
            ):
                errors.append(_scope_error(
                    f"$.bindingsUpsert[{index}]",
                    "event binding belongs to an unselected event alternative",
                    actual={"id": row_id, "input": input_name, "targetId": target_id},
                ))
            if (
                row_id not in existing["bindings"]
                and input_name in selected_event_binding_inputs
                and not independently_required
            ):
                selected_event_new_bindings.append((index, row_id, input_name, target_id))

        current_has_selected_event_binding = any(
            str(row.get("input") or "") in selected_event_binding_inputs
            for row in rows["bindings"]
        )
        redundant_event_bindings = (
            selected_event_new_bindings
            if current_has_selected_event_binding
            else selected_event_new_bindings[1:]
        )
        for index, row_id, input_name, target_id in redundant_event_bindings:
            errors.append(_scope_error(
                f"$.bindingsUpsert[{index}]",
                "selected event alternative requires at most one new binding from its any-of set",
                actual={"id": row_id, "input": input_name, "targetId": target_id},
            ))

    raw_exclusive_groups = transactions.get("exclusiveInputSelections")
    exclusive_rows = raw_exclusive_groups if isinstance(raw_exclusive_groups, list) else []
    exclusive_groups = {
        str(row.get("input") or ""): row
        for row in exclusive_rows
        if isinstance(row, Mapping) and str(row.get("input") or "")
    }
    seen_inputs: set[str] = set()
    preview_rows = rows
    if patch.get("exclusiveInputSelections"):
        preview_patch = copy.deepcopy(dict(patch))
        preview_patch["exclusiveInputSelections"] = []
        preview_rows = _program_rows(apply_repair_patch(current, preview_patch))
    for index, selection in enumerate(patch.get("exclusiveInputSelections") or []):
        if not isinstance(selection, Mapping):
            continue
        input_name = str(selection.get("input") or "")
        keep_id = str(selection.get("keepBindingId") or "")
        group = exclusive_groups.get(input_name) if input_name not in seen_inputs else None
        raw_candidates = group.get("candidateBindingIds") if isinstance(group, Mapping) else []
        candidates = set(str(value) for value in raw_candidates or [])
        if group is not None:
            preview_candidates = [
                str(row.get("id") or "")
                for row in preview_rows.get("bindings", [])
                if str(row.get("input") or "") == input_name and str(row.get("id") or "")
            ]
            if len(preview_candidates) > 1:
                candidates = set(_reachability_safe_exclusive_candidates(
                    preview_rows,
                    input_name=input_name,
                    candidate_ids=preview_candidates,
                ))
        if group is None or keep_id not in candidates:
            errors.append(_scope_error(
                f"$.exclusiveInputSelections[{index}]",
                "exclusive input choice is outside the exact conflicting-binding transaction",
                actual={"input": input_name, "keepBindingId": keep_id},
            ))
        seen_inputs.add(input_name)

    allowed_metadata = set(str(value) for value in _values(scope.get("metadataFields")))
    metadata = _mapping(patch.get("metadataPatch"))
    for key in metadata:
        if key not in allowed_metadata:
            errors.append(_scope_error(f"$.metadataPatch.{key}", f"metadata field '{key}' is valid and immutable in this Repair"))

    preview = apply_repair_patch(current, patch)
    preview_errors = _rows(validate_runtime_program(preview).get("errors"))
    repair_requirements = [
        requirement for requirement in _values(scope.get("repairRequirements"))
        if isinstance(requirement, Mapping)
    ]

    def preview_error_matches_requirement(
        error: Mapping[str, Any],
        requirement: Mapping[str, Any],
    ) -> bool:
        if str(error.get("code") or "") != str(requirement.get("code") or ""):
            return False
        requirement_path = str(requirement.get("errorPath") or "")
        affected_ids = {
            str(value) for value in requirement.get("affectedIds") or []
            if str(value)
        }
        related_ids = {
            str(value) for value in error.get("relatedIds") or []
            if str(value)
        }
        if affected_ids:
            return bool(affected_ids.intersection(related_ids)) or (
                not related_ids and str(error.get("path") or "") == requirement_path
            )
        return str(error.get("path") or "") == requirement_path

    for requirement_index, requirement in enumerate(repair_requirements):
        if not bool(requirement.get("llmRepairable", False)):
            continue
        required_capabilities = {
            str(value) for value in requirement.get("requiredOneOfCapabilities") or []
            if str(value)
        }
        requirement_code = str(requirement.get("code") or "")
        affected_ids = {
            str(value) for value in requirement.get("affectedIds") or []
            if str(value)
        }

        if any(preview_error_matches_requirement(error, requirement) for error in preview_errors):
            errors.append(_scope_error(
                f"$.repairRequirements[{requirement_index}]",
                "patch leaves a reported repair error open after all authorized structural changes",
                actual={
                    "requirementIndex": requirement_index,
                    "code": requirement_code,
                    "affectedIds": sorted(affected_ids),
                    "requiredOneOfCapabilities": sorted(required_capabilities),
                    "exactCapabilityParams": copy.deepcopy(requirement.get("exactCapabilityParams") or []),
                },
            ))

    for preview_error in preview_errors:
        if any(
            preview_error_matches_requirement(preview_error, requirement)
            for requirement in repair_requirements
        ):
            continue
        preview_key = (
            str(preview_error.get("code") or ""),
            str(preview_error.get("path") or ""),
        )
        errors.append(_scope_error(
            "$.repairResult",
            "patch introduces a new runtime validation error outside the reported Repair scope",
            actual={
                "code": preview_key[0],
                "path": preview_key[1],
                "relatedIds": copy.deepcopy(preview_error.get("relatedIds") or []),
            },
        ))

    return {"schema": RUNTIME_REPAIR_SCOPE_REPORT_SCHEMA, "ok": not errors, "errors": errors}
