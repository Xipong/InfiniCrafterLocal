"""Finite binding and event-producer alternatives with reachability checks."""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

from infini_local.core.repair_merge import json_path_child
from infini_local.core.runtime_authoring.binding_use_policy import (
    action_kind,
    canonical_transaction,
    contact_damage,
    placement_call_id,
    stack_cost,
)
from infini_local.core.runtime_authoring.binding_use_policy import complete_transaction as transaction
from infini_local.core.runtime_authoring.binding_use_policy import target_id as binding_target_id
from infini_local.core.runtime_authoring.capability_registry import BINDING_ACTION_REGISTRY, CAPABILITY_REGISTRY, INPUT_KIND_REGISTRY
from infini_local.core.runtime_authoring.program_schema import binding_schema
from infini_local.core.runtime_authoring.repair.facts import (
    _binding_target,
    _body_id,
    _candidate_capability_viable,
    _event_producer_options,
    _mapping,
)
from infini_local.core.schema_validation import strict_schema_errors


def _reachable_runtime_entity_ids(rows: Mapping[str, list[dict[str, Any]]]) -> set[str]:
    entity_kind_by_id = {
        str(row.get("id") or ""): str(row.get("kind") or "")
        for row in rows.get("entities", [])
        if str(row.get("id") or "")
    }
    reachable = {
        binding_target_id(row)
        for row in rows.get("bindings", [])
        if action_kind(row) == "spawn_entity" and binding_target_id(row)
        and entity_kind_by_id.get(binding_target_id(row)) != "item_body"
    }
    for call in rows.get("calls", []):
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        raw_params = call.get("params")
        params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
        if cap is None:
            continue
        for param_name, param_spec in cap.params.items():
            reference = param_spec.reference
            if reference is None or not reference.graph_edge or param_name not in params:
                continue
            referenced_id = str(params.get(param_name) or "")
            if referenced_id:
                reachable.add(referenced_id)
    return reachable


def _binding_delete_preserves_reachability(
    rows: Mapping[str, list[dict[str, Any]]],
    binding_id: str,
) -> bool:
    baseline = _reachable_runtime_entity_ids(rows)
    candidate_rows = {name: list(values) for name, values in rows.items()}
    candidate_rows["bindings"] = [
        row for row in rows.get("bindings", [])
        if str(row.get("id") or "") != binding_id
    ]
    return baseline.issubset(_reachable_runtime_entity_ids(candidate_rows))


def _reachability_safe_exclusive_candidates(
    rows: Mapping[str, list[dict[str, Any]]],
    *,
    input_name: str,
    candidate_ids: list[str],
) -> list[str]:
    """Keep choices must not orphan an entity that is reachable before repair."""

    baseline = _reachable_runtime_entity_ids(rows)
    viable: list[str] = []
    for keep_id in candidate_ids:
        candidate_rows = {name: list(values) for name, values in rows.items()}
        candidate_rows["bindings"] = [
            row
            for row in rows.get("bindings", [])
            if str(row.get("input") or "") != input_name or str(row.get("id") or "") == keep_id
        ]
        if baseline.issubset(_reachable_runtime_entity_ids(candidate_rows)):
            viable.append(keep_id)
    return viable


def _complete_binding_transactions(
    rows: Mapping[str, list[dict[str, Any]]],
    *,
    input_name: str,
    action_name: str,
    target_id: str,
) -> list[dict[str, Any]]:
    if action_name == "place_item":
        call_ids = sorted(
            str(call.get("id") or "")
            for call in rows.get("calls", [])
            if str(call.get("fn") or "") in {"place_tile", "place_wall"}
            and str(call.get("target") or "") == target_id
            and str(call.get("id") or "")
        )
        return [
            transaction(
                input_name=input_name,
                action_name=action_name,
                target=target_id,
                stack_cost_value=1,
                contact_damage_value=False,
                placement_call=call_id,
            )
            for call_id in call_ids
        ]
    active = input_name in {"primary_use", "alternate_use"}
    stack_costs = (0, 1) if active else (0,)
    contacts = (False, True) if active else (False,)
    return [
        transaction(
            input_name=input_name,
            action_name=action_name,
            target=target_id,
            stack_cost_value=cost,
            contact_damage_value=contact,
        )
        for cost in stack_costs
        for contact in contacts
    ]


def _binding_repair_alternatives(
    rows: Mapping[str, list[dict[str, Any]]],
    binding: Mapping[str, Any],
    *,
    input_mutable: bool,
    action_mutable: bool,
    target_mutable: bool,
    mutable_paths: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Project complete registry-valid use transactions without choosing one."""

    if input_mutable and not action_mutable and not target_mutable and not action_kind(binding):
        # Omission-only source rows carry no action/target choice to retarget.
        # Comparison candidates may also correct exact diagnosed fixed literals
        # or forbidden keys. Never materialize these corrections into the source
        # or patch: Repair must explicitly supply every required correction.
        permissions = set(mutable_paths)

        def project_fixed_leaves(candidate: dict[str, Any], schema: Mapping[str, Any], prefix: str = "") -> None:
            properties = _mapping(schema.get("properties"))
            for key in list(candidate):
                relative = json_path_child(prefix, key)
                child_schema = _mapping(properties.get(key))
                if relative in permissions:
                    if key not in properties and schema.get("additionalProperties") is False:
                        candidate.pop(key)
                    elif "const" in child_schema:
                        candidate[key] = copy.deepcopy(child_schema["const"])
                if isinstance(candidate.get(key), dict) and child_schema:
                    project_fixed_leaves(candidate[key], child_schema, relative)

        alternatives = []
        for variant in binding_schema()["oneOf"]:
            candidate = {**copy.deepcopy(binding), "input": variant["properties"]["input"]["const"]}
            project_fixed_leaves(candidate, variant)
            if not strict_schema_errors(candidate, variant):
                alternatives.append(canonical_transaction(candidate, item_body_id=_body_id(rows)))
        return sorted({repr(row): row for row in alternatives}.values(), key=repr)
    original_input = str(binding.get("input") or "")
    original_action = action_kind(binding)
    original_target = binding_target_id(binding)
    input_names = sorted(INPUT_KIND_REGISTRY) if input_mutable else [original_input]
    action_names = sorted(BINDING_ACTION_REGISTRY) if action_mutable else [original_action]
    entity_kind_by_id = {
        str(row.get("id") or ""): str(row.get("kind") or "")
        for row in rows.get("entities", [])
        if str(row.get("id") or "")
    }

    alternatives: list[dict[str, Any]] = []
    for input_name in input_names:
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        if input_spec is None:
            continue
        for action_name in action_names:
            action_spec = BINDING_ACTION_REGISTRY.get(action_name)
            if action_spec is None:
                continue
            if action_name not in input_spec.allowed_actions or input_name not in action_spec.allowed_inputs:
                continue
            target_ids = (
                sorted(entity_id for entity_id, kind in entity_kind_by_id.items() if kind in action_spec.target_kinds)
                if target_mutable else [original_target]
            )
            if (not target_mutable and not original_target and action_mutable
                    and "targetId" not in _mapping(binding.get("action"))
                    and action_spec.target_kinds == ("item_body",) and _body_id(rows)):
                # A model-selected body-only action has one technical owner.
                # Preserve source omission; projectile targets remain explicit.
                target_ids = [_body_id(rows)]
            for target_id in target_ids:
                if entity_kind_by_id.get(target_id) not in action_spec.target_kinds:
                    continue
                if action_name != original_action or input_name != original_input:
                    alternatives.extend(_complete_binding_transactions(
                        rows,
                        input_name=input_name,
                        action_name=action_name,
                        target_id=target_id,
                    ))
                    continue
                if action_name == "place_item":
                    alternatives.extend(_complete_binding_transactions(
                        rows,
                        input_name=input_name,
                        action_name=action_name,
                        target_id=target_id,
                    ))
                    continue
                costs = (0, 1) if "stackCost" in mutable_paths else (stack_cost(binding),)
                contacts = (False, True) if "contactDamage" in mutable_paths else (contact_damage(binding),)
                for cost in costs:
                    for contact in contacts:
                        alternatives.append(transaction(
                            input_name=input_name,
                            action_name=action_name,
                            target=target_id,
                            stack_cost_value=cost,
                            contact_damage_value=contact,
                        ))
    group_id = _mapping(binding.get("action")).get("effectGroupId")
    if group_id is not None:
        for row in alternatives:
            if action_kind(row) == "apply_item_effects" and isinstance(row.get("action"), dict):
                row["action"]["effectGroupId"] = copy.deepcopy(group_id)
    return sorted(alternatives, key=lambda row: repr(row))


def _binding_creation_alternatives(
    rows: Mapping[str, list[dict[str, Any]]],
    *,
    owner_item_target_id: str,
    required_inputs: Iterable[str],
    additional_item_capabilities: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Enumerate complete executable transactions; never choose one for Repair."""

    entity_kind_by_id = {
        str(row.get("id") or ""): str(row.get("kind") or "")
        for row in rows.get("entities", [])
        if str(row.get("id") or "")
    }
    if entity_kind_by_id.get(owner_item_target_id) != "item_body":
        return []
    item_capabilities = {
        str(row.get("fn") or "")
        for row in rows.get("calls", [])
        if str(row.get("target") or "") == owner_item_target_id
        and str(row.get("fn") or "")
    }
    item_capabilities.update(str(name) for name in additional_item_capabilities if str(name))

    alternatives: list[dict[str, Any]] = []
    for input_name in sorted(set(str(name) for name in required_inputs if str(name))):
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        if input_spec is None:
            continue
        if input_spec.required_item_capabilities_any_of and not item_capabilities.intersection(input_spec.required_item_capabilities_any_of):
            continue
        for action_name in input_spec.allowed_actions:
            action_spec = BINDING_ACTION_REGISTRY.get(action_name)
            if action_spec is None or input_name not in action_spec.allowed_inputs:
                continue
            if action_spec.required_item_capabilities_any_of and not item_capabilities.intersection(action_spec.required_item_capabilities_any_of):
                continue
            for target_id, target_kind in entity_kind_by_id.items():
                if target_kind in action_spec.target_kinds:
                    alternatives.extend(_complete_binding_transactions(
                        rows,
                        input_name=input_name,
                        action_name=action_name,
                        target_id=target_id,
                    ))
    return sorted(alternatives, key=lambda row: repr(row))


def _missing_event_producer_choices(
    rows: Mapping[str, list[dict[str, Any]]],
    *,
    event_name: str,
    event_target_id: str,
    event_target_kind: str,
    sole_item_entity_id: str,
    planned_item_capabilities_by_target: Mapping[str, set[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[bool]]:
    """Plan complete producers against frozen calls and occupied input lanes.

    Return event alternatives, new bindings, existing binding corrections and
    whether each alternative requires a binding change. These are offered
    choices only; the scope builder remains the sole permission authority.
    """
    structured_alternatives = _event_producer_options(
        event_name, event_target_id, event_target_kind, rows,
    )
    allowed_event_alternatives: list[dict[str, Any]] = []
    event_create_choices: list[dict[str, Any]] = []
    event_existing_choices: list[dict[str, Any]] = []
    binding_change_required_by_alternative: list[bool] = []
    for dependency, binding_targets in structured_alternatives:
        alternative_viable = True
        required_calls: list[dict[str, Any]] = []
        required_bindings: list[dict[str, Any]] = []
        pending_create_choices: list[dict[str, Any]] = []
        pending_existing_choices: list[dict[str, Any]] = []
        missing_binding_count = 0
        for call_requirement in dependency.required_calls:
            if not _candidate_capability_viable(
                call_requirement.capability,
                (event_target_id,),
                rows,
            ):
                alternative_viable = False
                break
            required_calls.append({
                "fn": call_requirement.capability,
                "targetId": event_target_id,
                "exactParams": [
                    {"param": name, "value": copy.deepcopy(value)}
                    for name, value in call_requirement.exact_params
                ],
            })
        if not alternative_viable:
            continue
        for binding_requirement, action_target_id in zip(dependency.required_bindings, binding_targets):
            allowed_inputs = set(binding_requirement.any_of_inputs)
            allowed_actions = set(binding_requirement.any_of_actions)
            if not allowed_actions:
                allowed_actions = {
                    action_name
                    for input_name in allowed_inputs
                    for action_name in INPUT_KIND_REGISTRY[input_name].allowed_actions
                }
            required_contact = binding_requirement.required_contact_damage
            required_bindings.append({
                "targetId": action_target_id,
                "anyOfInputs": sorted(allowed_inputs),
                "anyOfActions": sorted(allowed_actions),
                "requiredContactDamage": required_contact,
            })
            exact_binding_present = any(
                _binding_target(binding, rows) == action_target_id
                and str(binding.get("input") or "") in allowed_inputs
                and action_kind(binding) in allowed_actions
                and (
                    required_contact is None
                    or contact_damage(binding) is required_contact
                )
                for binding in rows["bindings"]
            )
            if exact_binding_present:
                continue
            missing_binding_count += 1
            if required_contact is not None:
                for binding in rows["bindings"]:
                    if (
                        _binding_target(binding, rows) != action_target_id
                        or str(binding.get("input") or "") not in allowed_inputs
                        or action_kind(binding) not in allowed_actions
                        or contact_damage(binding) is required_contact
                    ):
                        continue
                    binding_id = str(binding.get("id") or "")
                    fixed = transaction(
                        input_name=str(binding.get("input") or ""),
                        action_name=action_kind(binding),
                        target=action_target_id,
                        stack_cost_value=stack_cost(binding),
                        contact_damage_value=required_contact,
                        placement_call=placement_call_id(binding),
                    )
                    pending_existing_choices.append({
                        "bindingId": binding_id,
                        "allowed": [fixed],
                    })
            owner_item_target = (
                event_target_id
                if event_target_kind == "item_body"
                else sole_item_entity_id
            )
            projected_rows = (
                _binding_creation_alternatives(
                    rows,
                    owner_item_target_id=owner_item_target,
                    required_inputs=allowed_inputs,
                    additional_item_capabilities=planned_item_capabilities_by_target.get(
                        owner_item_target, set()
                    ),
                )
                if owner_item_target else []
            )
            pending_create_choices.extend(
                projected_row
                for projected_row in projected_rows
                if not pending_existing_choices
                and _binding_target(projected_row, rows) == action_target_id
                and action_kind(projected_row) in allowed_actions
                and not (
                    INPUT_KIND_REGISTRY[str(projected_row.get("input") or "")].exclusive
                    and any(
                        str(existing.get("input") or "")
                        == str(projected_row.get("input") or "")
                        for existing in rows["bindings"]
                    )
                )
                and (
                    required_contact is None
                    or contact_damage(projected_row) is required_contact
                )
            )
            if not pending_existing_choices and not pending_create_choices:
                alternative_viable = False
                break
        if not alternative_viable:
            continue
        allowed_event_alternatives.append({
            "event": event_name,
            "requiredCalls": required_calls,
            "requiredBindings": required_bindings,
        })
        event_create_choices.extend(pending_create_choices)
        event_existing_choices.extend(pending_existing_choices)
        binding_change_required_by_alternative.append(
            bool(required_bindings)
            and missing_binding_count == len(required_bindings)
        )
    return (
        allowed_event_alternatives,
        event_create_choices,
        event_existing_choices,
        binding_change_required_by_alternative,
    )
