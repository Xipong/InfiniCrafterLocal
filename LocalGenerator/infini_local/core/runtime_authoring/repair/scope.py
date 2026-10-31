"""Build exact mutable leaves and create policies from rejected Author fragments."""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping

from infini_local.core.repair_merge import json_path_child, json_path_relative
from infini_local.core.runtime_authoring.binding_use_policy import (
    action_kind,
    contact_damage,
    expected_placeable_input,
    placement_call_id,
    stack_chance_error,
    stack_cost,
)
from infini_local.core.runtime_authoring.binding_use_policy import complete_transaction as transaction
from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_CAPABILITIES,
    INPUT_KIND_REGISTRY,
    authored_event,
)
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_JSON_PATH,
    PRIMARY_ENTITY_SELECTION_FIELD,
    binding_schema,
    primary_entity_repair_transaction,
)
from infini_local.core.runtime_authoring.repair.choices import (
    _binding_creation_alternatives,
    _binding_delete_preserves_reachability,
    _binding_repair_alternatives,
    _complete_binding_transactions,
    _missing_event_producer_choices,
    _reachability_safe_exclusive_candidates,
)
from infini_local.core.runtime_authoring.repair.facts import (
    _ambiguous_row_ids,
    _binding_target,
    _binding_target_kinds,
    _body_id,
    _call_target_kinds,
    _candidate_capability_viable,
    _capability_constraints,
    _capability_dependency_closure,
    _capability_names,
    _compatible_reference_options,
    _component_repair_paths,
    _conditional_param_dependencies,
    _entity_reference_params,
    _event_producer_options,
    _exclusive_reference_dependency_edits,
    _field_permission_rows,
    _graph_rows,
    _id_maps,
    _mapping,
    _matching_entity_ids,
    _node_from_path,
    _program_index_rows,
    _source_scope_transactions,
    _values,
)
from infini_local.core.runtime_authoring.repair.schema import REPAIR_ERROR_POLICY, _new_scope
from infini_local.core.schema_validation import strict_schema_errors


def build_runtime_repair_scope(current: Mapping[str, Any], errors: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    error_rows = [dict(row) for row in errors]
    error_codes = {str(row.get("code") or "") for row in error_rows}
    rows = _graph_rows(current)
    from infini_local.core.runtime_authoring.technical_lowering import (
        _exact_mechanical_view,  # pyright: ignore[reportPrivateUsage] -- private canonical lowering
    )
    indexed_rows = _program_index_rows(_exact_mechanical_view(current))
    ambiguous_ids = {namespace: _ambiguous_row_ids(values) for namespace, values in rows.items()}
    error_paths_all = [str(row.get("path") or "$") for row in error_rows]
    namespace_by_id, row_by_id = _id_maps(rows)
    mutable = {name: set() for name in ("entities", "bindings", "calls")}
    deletable = {name: set() for name in ("entities", "bindings", "calls")}
    deletable_indices = {name: set() for name in ("entities", "bindings", "calls")}
    deletable_call_param_keys: set[tuple[str, str]] = set()
    deletable_call_property_keys: set[tuple[str, str]] = set()
    context = {name: set() for name in ("entities", "bindings", "calls")}
    create_entity_exact: set[str] = set()
    create_entity_kinds: set[str] = set()
    create_binding_targets: set[str] = set()
    create_binding_inputs: set[str] = set()
    create_binding_actions: set[str] = set()
    create_binding_alternatives: list[dict[str, str]] = []

    binding_creation_requests: list[
        tuple[str, tuple[str, ...], tuple[str, ...], bool | None, str]
    ] = []
    create_call_targets: set[str] = set()
    create_call_target_kinds: set[str] = set()
    create_call_fns: set[str] = set()
    required_reference_entities: set[str] = set()
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
    metadata_fields: set[str] = set()
    field_permissions: dict[str, dict[str, set[str]]] = {
        namespace: {} for namespace in ("entities", "bindings", "calls")
    }
    event_alternative_rows: list[dict[str, Any]] = []
    binding_alternative_overrides: dict[str, list[dict[str, str]]] = {}
    event_supporting_capabilities: set[str] = set()
    repair_requirements: list[dict[str, Any]] = []
    direct_blocker_capabilities: set[str] = set()
    existing_broken_capabilities: set[str] = set()
    non_repairable_errors: list[dict[str, Any]] = []
    error_paths: list[str] = []

    def grant(namespace: str, row_id: str, relative_path: str) -> None:
        if not row_id or row_id in ambiguous_ids[namespace]:
            return
        field_permissions[namespace].setdefault(row_id, set()).add(relative_path.strip("."))

    def mark(namespace: str, row_id: str, *, can_delete: bool = False) -> None:
        if row_id and row_id not in ambiguous_ids[namespace]:
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

    def exact_error_identity(row: Mapping[str, Any]) -> tuple[str, str, tuple[str, ...]]:
        return (
            str(row.get("code") or row.get("kind") or ""),
            str(row.get("path") or "$"),
            tuple(sorted(
                str(value) for value in _values(row.get("relatedIds"))
                if str(value)
            )),
        )

    item_entity_ids = {
        str(row.get("id") or "")
        for row in rows["entities"]
        if row.get("kind") == "item_body" and str(row.get("id") or "")
    }
    sole_item_entity_id = (
        next(iter(item_entity_ids))
        if len(item_entity_ids) == 1 else ""
    )

    def request_binding_creation(
        *,
        target_id: str,
        inputs: Iterable[str],
        actions: Iterable[str],
        required_contact: bool | None = None,
        owner_item_target_id: str = "",
    ) -> None:
        normalized_inputs = tuple(sorted({str(value) for value in inputs if str(value)}))
        normalized_actions = tuple(sorted({str(value) for value in actions if str(value)}))
        if not target_id or not normalized_inputs or not normalized_actions:
            return
        binding_creation_requests.append((
            target_id,
            normalized_inputs,
            normalized_actions,
            required_contact,
            owner_item_target_id,
        ))
    planned_item_capabilities_by_target: dict[str, set[str]] = {}
    for candidate_error in error_rows:
        candidate_code = str(candidate_error.get("code") or candidate_error.get("kind") or "")
        if candidate_code not in {"missing_capability_dependency", "missing_capability_group"}:
            continue
        candidate_targets = {
            str(value) for value in _values(candidate_error.get("relatedIds"))
            if str(value) in item_entity_ids
        }
        candidate_node = _node_from_path(str(candidate_error.get("path") or "$"), indexed_rows)
        if candidate_node is not None and candidate_node[0] == "calls":
            candidate_call = _mapping(indexed_rows["calls"][candidate_node[1]])
            candidate_target = str(candidate_call.get("target") or "")
            if candidate_target in item_entity_ids:
                candidate_targets.add(candidate_target)
        for candidate_target in sorted(candidate_targets):
            for capability_name in _capability_names(_values(candidate_error.get("allowed"))):
                if _candidate_capability_viable(
                    capability_name, [candidate_target], rows,
                ):
                    planned_item_capabilities_by_target.setdefault(
                        candidate_target, set()
                    ).add(capability_name)

    for error in error_rows:
        path = str(error.get("path") or "$")
        code = str(error.get("code") or error.get("kind") or "")
        allowed = _values(error.get("allowed"))
        related = [str(value) for value in _values(error.get("relatedIds")) if str(value)]
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
            "allowedExistingBindingIds": [],
            "repairStrategy": str((policy or {}).get("strategy") or ("patch_exact_schema_path" if code.startswith("shape_") else "unmapped_validator_error")),
            "llmRepairable": bool((policy or {}).get("llmRepairable", code.startswith("shape_"))),
        }
        repair_requirements.append(requirement_row)
        error_paths.append(path)
        node = _node_from_path(path, indexed_rows)
        node_namespace = ""
        node_index = -1
        node_id = ""
        node_row: dict[str, Any] = {}
        if node is not None:
            node_namespace, node_index, node_id = node
            node_row = dict(_mapping(indexed_rows[node_namespace][node_index])) if 0 <= node_index < len(indexed_rows[node_namespace]) else {}
            if node_id:
                requirement_row["affectedIds"] = sorted(set(requirement_row["affectedIds"] + [node_id]))
            if node_namespace == "calls":
                existing_fn = str(node_row.get("fn") or "")
                if existing_fn in CAPABILITY_REGISTRY:
                    existing_broken_capabilities.add(existing_fn)
            if node_id:
                root_prefix = f"$.runtimeProgram.{node_namespace}[{node_index}]"
                if path == root_prefix:
                    # Provider union validation emits a generic shape_one_of at
                    # the row root together with a precise descendant error.
                    # The generic wrapper must not unfreeze the whole row.
                    has_precise_descendant = any(json_path_relative(other, root_prefix) for other in error_paths_all)
                    if code.startswith("shape_") and not (code == "shape_one_of" and has_precise_descendant):
                        grant(node_namespace, node_id, "")
                elif (relative := json_path_relative(path, root_prefix)) is not None:
                    has_precise_descendant = any(json_path_relative(other, path) for other in error_paths_all)
                    if not (relative == "params" and code in {"empty_component", "inert_component"}) and not (
                        code == "shape_one_of" and has_precise_descendant
                    ):
                        grant(node_namespace, node_id, relative)
            dependency_only_codes = {
                "binding_dependency", "missing_capability_dependency", "missing_capability_group",
                "missing_binding_dependency", "missing_item_capability_param",
            }
            if node_id:
                if code in dependency_only_codes:
                    context[node_namespace].add(node_id)
                    # A dependency diagnostic may identify a broken reference
                    # leaf on an otherwise frozen binding. Admit that row, not
                    # its siblings; the exact permission still governs merge.
                    if (
                        code == "missing_binding_dependency"
                        and node_namespace == "bindings"
                        and path == f"$.runtimeProgram.bindings[{node_index}].action.placementCallId"
                    ):
                        mark(node_namespace, node_id)
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
                    target = _binding_target(node_row, rows) or str(node_row.get("target") or "")
                    if target:
                        create_binding_targets.add(target)
                    input_name = str(node_row.get("input") or "")
                    action_name = action_kind(node_row) or str(node_row.get("action") or "")
                    if input_name in INPUT_KIND_REGISTRY:
                        create_binding_inputs.add(input_name)
                    if action_name in BINDING_ACTION_REGISTRY:
                        create_binding_actions.add(action_name)
                    request_binding_creation(
                        target_id=target,
                        inputs=(input_name,),
                        actions=(action_name,),
                    )
                elif node_namespace == "calls":
                    target = str(node_row.get("target") or "")
                    fn = str(node_row.get("fn") or "")
                    if target:
                        create_call_targets.add(target)
                    if fn in CAPABILITY_REGISTRY:
                        create_call_fns.add(fn)
        if node_id:
            if node_namespace == "entities" and path.startswith(f"$.runtimeProgram.entities[{node_index}].kind"):
                entity_kind_change_ids.add(node_id)
            if node_namespace == "bindings":
                if path.startswith(f"$.runtimeProgram.bindings[{node_index}].input"):
                    binding_input_change_ids.add(node_id)
                if path == f"$.runtimeProgram.bindings[{node_index}].action" or path.startswith(
                    f"$.runtimeProgram.bindings[{node_index}].action.kind"
                ):
                    binding_action_change_ids.add(node_id)
                    if not isinstance(node_row.get("action"), Mapping):
                        binding_target_change_ids.add(node_id)
                if path.startswith((
                    f"$.runtimeProgram.bindings[{node_index}].action.targetId",
                    f"$.runtimeProgram.bindings[{node_index}].target",
                )):
                    binding_target_change_ids.add(node_id)
            if node_namespace == "calls":
                if path.startswith(f"$.runtimeProgram.calls[{node_index}].fn"):
                    call_fn_change_ids.add(node_id)
                if path.startswith(f"$.runtimeProgram.calls[{node_index}].target"):
                    call_target_change_ids.add(node_id)
                param_match = re.search(r"\.params\.([A-Za-z0-9_]+)$", path)
                if param_match:
                    param_name = param_match.group(1)
                    if code == "hybrid_placeable_max_stack" and param_name == "maxStack":
                        # The durable-hybrid invariant authorizes exactly this leaf so
                        # Repair can set item_stats.maxStack to 1.
                        grant(node_namespace, node_id, f"params.{param_name}")
                        context[node_namespace].add(node_id)
                    cap = CAPABILITY_REGISTRY.get(str(node_row.get("fn") or ""))
                    if (code == "incompatible_param_variant" and cap is not None
                            and param_name in cap.params and not cap.params[param_name].required
                            and any(rule.kind == "param_only_when" and rule.param == param_name
                                    and _mapping(node_row.get("params")).get(rule.other_param) in cap.params[rule.other_param].enum
                                    and _mapping(node_row.get("params")).get(rule.other_param) != rule.equals
                                    for rule in cap.requirements)):
                        # The selected branch is valid; only its inactive optional
                        # leaf may be removed. Do not thaw the selector or siblings.
                        deletable_call_param_keys.add((node_id, param_name))
                    if param_name == "when" and not (
                        code == "shape_one_of" and any(json_path_relative(other, path) for other in error_paths_all)
                    ):
                        call_event_change_ids.add(node_id)
                    if cap is not None and param_name in cap.params and cap.params[param_name].reference is not None:
                        call_reference_param_changes.add(f"{node_id}:{param_name}")
                if code == "shape_additional_property":
                    call_prefix = f"$.runtimeProgram.calls[{node_index}]"
                    for key in node_row:
                        if path == json_path_child(call_prefix, key):
                            deletable_call_property_keys.add((node_id, key))
                    for key in _mapping(node_row.get("params")):
                        if path == json_path_child(call_prefix + ".params", key):
                            deletable_call_param_keys.add((node_id, key))
        # Metadata is a separate bounded subtree.
        for field in ("name", "category", "concept"):
            if json_path_relative(path, f"$.{field}") is not None:
                metadata_fields.add(field)

        if code in {"missing_effect_group", "invalid_held_effect_group", "invalid_reaction_effect_group"}:
            if (code in {"invalid_held_effect_group", "invalid_reaction_effect_group"} and not allowed
                    and node_namespace == "calls" and node_id):
                # No existing utility group can satisfy this optional selector.
                # Only the model may remove the diagnosed call; never invent a buff.
                mark("calls", node_id, can_delete=True)
                requirement_row["repairStrategy"] = "delete_exact_invalid_held_call"
            # The invalid reference leaf is mutable; all candidate definitions
            # remain read-only context. Never synthesize a group or its effects.
            for candidate in rows["calls"]:
                candidate_cap = CAPABILITY_REGISTRY.get(str(candidate.get("fn") or ""))
                if candidate_cap is not None and candidate_cap.effect_groupable:
                    context["calls"].add(str(candidate.get("id") or ""))
        elif code == "unknown_registry_requirement":
            pass
        elif code in {"duplicate_id", "ambiguous_global_id", "duplicate_placed_body_reference"}:
            # IDs are structural identity.  Do not let Repair rename a valid
            # row through a broad upsert; allow dropping the exact offending
            # row by index instead.
            if node_namespace and node_index >= 0:
                deletable_indices[node_namespace].add(node_index)
                if node_id:
                    context[node_namespace].add(node_id)
        elif code in {"empty_component", "inert_component"} and node_namespace == "calls" and node_id:
            mark("calls", node_id, can_delete=True)
            for relative_path in _component_repair_paths(code, node_row, path=path, allowed=allowed):
                grant("calls", node_id, relative_path)
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
        elif code == "set_bonus_head_only" and node_namespace == "calls":
            for row_id in related:
                modifier = row_by_id.get(row_id, {})
                if (
                    row_id != node_id
                    and str(modifier.get("fn") or "") == "equipment_damage_bonus"
                    and str(modifier.get("target") or "") == str(node_row.get("target") or "")
                    and _mapping(modifier.get("params")).get("phase") == "matching_armor_set"
                ):
                    # The invalid bonus can be removed without changing a valid
                    # body/legs item into a head piece or unfreezing its design.
                    mark("calls", row_id, can_delete=True)
        elif code in {"duplicate_equipment_damage_selector", "equipment_scope_conflict"}:
            if node_namespace == "calls" and node_id:
                mark("calls", node_id, can_delete=True)
                for relative_path in _component_repair_paths(code, node_row, path=path, allowed=allowed):
                    grant("calls", node_id, relative_path)
            for row_id in related:
                if row_id != node_id:
                    context_id(row_id)
        elif code == "overlapping_motion_windows":
            if node_namespace == "calls" and node_id:
                mark("calls", node_id, can_delete=True)
                grant("calls", node_id, "params.window")
            for row_id in related:
                if row_id != node_id:
                    context_id(row_id)
        elif code in {"duplicate_single_component", "exclusive_component_conflict"}:
            # A registry conditional conflict may also be resolved by changing
            # the exact selected leaf (for example disabling an explicit visual
            # mirror). Valid curve numbers and the other movement stay frozen.
            causal_paths = _component_repair_paths(code, node_row, path=path, allowed=allowed)
            if node_namespace == "calls" and node_id:
                for relative_path in causal_paths:
                    grant("calls", node_id, relative_path)
            for row_id in related:
                if namespace_by_id.get(row_id) == "calls" and not (row_id == node_id and causal_paths):
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
        elif (code.startswith("shape_") and node_namespace == "entities"
              and path.endswith(".id") and node_row.get("kind") == "item_body"):
            # Invalid declaration identity cannot be addressed by a valid-ID upsert.
            # The model may replace this exact original occurrence explicitly.
            deletable_indices["entities"].add(node_index)
            create_entity_kinds.add("item_body")
        elif code == "item_body_count":
            for row in rows["entities"]:
                if row.get("kind") == "item_body":
                    mark("entities", str(row.get("id") or ""), can_delete=True)
            create_entity_kinds.add("item_body")
            create_call_target_kinds.add("item_body")
            item_body_spec = ENTITY_KIND_REGISTRY.get("item_body")
            if item_body_spec is not None:
                create_call_fns.update(item_body_spec.required_components)
        elif code in {"wrong_binding_target_kind", "unsupported_input_action", "entity_not_binding_spawnable"}:
            if node_namespace == "bindings":
                if code == "unsupported_input_action":
                    binding_input_change_ids.add(node_id)
                    binding_action_change_ids.add(node_id)
                    grant("bindings", node_id, "input")
                    grant("bindings", node_id, "action")
                elif code == "entity_not_binding_spawnable":
                    binding_action_change_ids.add(node_id)
                    binding_target_change_ids.add(node_id)
                    retarget_binding_ids.update(_matching_entity_ids(rows, _binding_target_kinds(node_row)))
                    grant("bindings", node_id, "action")
                else:
                    binding_target_change_ids.add(node_id)
                    retarget_binding_ids.update(_matching_entity_ids(rows, _binding_target_kinds(node_row)))
                    grant("bindings", node_id, "action.targetId")
        elif code == "reference_requirements_unsatisfied" and node_namespace == "calls":
            param_match = re.search(r"\.params\.([A-Za-z0-9_]+)$", path)
            cap = CAPABILITY_REGISTRY.get(str(node_row.get("fn") or ""))
            if param_match and cap is not None:
                param_name = param_match.group(1)
                dependency_edits = _exclusive_reference_dependency_edits(
                    rows, node_row, param_name,
                    str(_mapping(current.get("runtimeProgram")).get("primaryEntityId") or ""),
                )
                if dependency_edits:
                    # The sole incoming edge cannot be replaced without orphaning
                    # this child. Its conflicting dependency leaves are not an
                    # independent accepted use; everything else remains frozen.
                    reference_path = f"params.{param_name}"
                    field_permissions["calls"].get(node_id, set()).discard(reference_path)
                    call_reference_param_changes.discard(f"{node_id}:{param_name}")
                    if not field_permissions["calls"].get(node_id):
                        field_permissions["calls"].pop(node_id, None)
                        mutable["calls"].discard(node_id)
                    context["calls"].add(node_id)
                    requirement_row["repairStrategy"] = "patch_exact_exclusive_reference_dependency"
                    requirement_row["referenceRequirements"] = [item.card() for item in cap.requirements
                        if item.param == param_name and item.kind in {
                            "referenced_entity_capability_params", "referenced_entity_without_capability"}]
                    for dependency_id, paths in dependency_edits:
                        mark("calls", dependency_id)
                        for dependency_path in paths:
                            grant("calls", dependency_id, dependency_path)
                    for row_id in related:
                        context_id(row_id)
                    continue
                candidates, kinds, new_call_fns = _compatible_reference_options(rows, node_row, cap, param_name)
                call_reference_param_changes.add(f"{node_id}:{param_name}")
                retarget_call_ids.update(candidates)
                requirement_row["allowedCompatibleEntityIds"] = list(candidates)
                requirement_row["referenceRequirements"] = [item.card() for item in cap.requirements
                    if item.param == param_name and item.kind in {
                        "referenced_entity_capability_params", "referenced_entity_without_capability"}]
                # A new child is a separate authored choice. No permission is
                # granted to edit the referenced, otherwise-valid existing child.
                create_entity_kinds.update(kinds)
                create_call_target_kinds.update(kinds)
                create_call_fns.update(new_call_fns)
        elif code in {"wrong_target_kind", "wrong_reference_target_kind", "self_reference_forbidden"}:
            if node_namespace == "calls":
                param_match = re.search(r"\.params\.([A-Za-z0-9_]+)$", path)
                if param_match:
                    call_reference_param_changes.add(f"{node_id}:{param_match.group(1)}")
                else:
                    call_target_change_ids.add(node_id)
                candidates = _matching_entity_ids(rows, _call_target_kinds(node_row, param_name=param_match.group(1) if param_match else ""))
                cap = CAPABILITY_REGISTRY.get(str(node_row.get("fn") or ""))
                if not param_match and cap is not None and any(r.kind == "primary_target" for r in cap.requirements):
                    primary = _mapping(current.get("runtimeProgram")).get("primaryEntityId")
                    candidates = [entity_id for entity_id in candidates if entity_id == primary]
                retarget_call_ids.update(candidates)
        elif code == "capability_event_incompatible":
            if node_namespace == "calls":
                cap = CAPABILITY_REGISTRY.get(str(node_row.get("fn") or ""))
                target_id = str(node_row.get("target") or "")
                target_kind = str(row_by_id.get(target_id, {}).get("kind") or "")
                allowed_alternatives: list[dict[str, Any]] = []
                if cap is not None:
                    call_event_change_ids.add(node_id)
                    grant("calls", node_id, "params.when")
                    for event in cap.allowed_events:
                        for dependency, binding_targets in _event_producer_options(
                            event, target_id, target_kind, rows,
                        ):
                            required_calls: list[dict[str, Any]] = []
                            viable = True
                            for raw_requirement in dependency.required_calls:
                                required_fn = raw_requirement.capability
                                if not _candidate_capability_viable(required_fn, [target_id], rows):
                                    viable = False
                                    break
                                exact = raw_requirement.exact_params_dict()
                                required_calls.append({
                                    "fn": required_fn,
                                    "targetId": target_id,
                                    "exactParams": [
                                        {"param": key, "value": value}
                                        for key, value in sorted(exact.items())
                                    ],
                                })
                                event_supporting_capabilities.add(required_fn)
                                existing = next((
                                    call for call in rows["calls"]
                                    if str(call.get("target") or "") == target_id
                                    and str(call.get("fn") or "") == required_fn
                                ), None)
                                if existing is None:
                                    allow_new_call([target_id], [required_fn])
                                else:
                                    existing_id = str(existing.get("id") or "")
                                    raw_params = existing.get("params")
                                    params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
                                    missing_exact = [key for key, value in exact.items() if params.get(key) != value]
                                    if missing_exact:
                                        mark("calls", existing_id)
                                        existing_broken_capabilities.add(required_fn)
                                        for key in missing_exact:
                                            grant("calls", existing_id, f"params.{key}")
                            if not viable:
                                continue
                            required_bindings = [
                                {
                                    "targetId": binding_target,
                                    "anyOfInputs": list(requirement.any_of_inputs),
                                    "anyOfActions": list(requirement.any_of_actions),
                                    "requiredContactDamage": requirement.required_contact_damage,
                                }
                                for requirement, binding_target in zip(dependency.required_bindings, binding_targets)
                            ]
                            for requirement in required_bindings:
                                action_target = requirement["targetId"]
                                allowed_inputs = set(requirement["anyOfInputs"])
                                allowed_actions = set(requirement["anyOfActions"])
                                required_contact = requirement["requiredContactDamage"]
                                if not any(
                                    str(binding.get("input") or "") in allowed_inputs
                                    and (not allowed_actions or action_kind(binding) in allowed_actions)
                                    and _binding_target(binding, rows) == action_target
                                    and (required_contact is None or contact_damage(binding) is required_contact)
                                    for binding in rows["bindings"]
                                ):
                                    contact_updates = [
                                        binding for binding in rows["bindings"]
                                        if required_contact is not None
                                        and _binding_target(binding, rows) == action_target
                                        and str(binding.get("input") or "") in allowed_inputs
                                        and action_kind(binding) in allowed_actions
                                        and contact_damage(binding) is not required_contact
                                    ]
                                    for binding in contact_updates:
                                        binding_id = str(binding.get("id") or "")
                                        fixed = transaction(
                                            input_name=str(binding.get("input") or ""),
                                            action_name=action_kind(binding),
                                            target=action_target,
                                            stack_cost_value=stack_cost(binding),
                                            contact_damage_value=bool(required_contact),
                                            placement_call=placement_call_id(binding),
                                        )
                                        mark("bindings", binding_id)
                                        grant("bindings", binding_id, "contactDamage")
                                        binding_alternative_overrides.setdefault(binding_id, []).append(fixed)
                                    if contact_updates:
                                        continue
                                    owner_item_target = (
                                        target_id if target_kind == "item_body"
                                        else sole_item_entity_id
                                    )
                                    projected = _binding_creation_alternatives(
                                        rows,
                                        owner_item_target_id=owner_item_target,
                                        required_inputs=allowed_inputs,
                                        additional_item_capabilities=planned_item_capabilities_by_target.get(
                                            owner_item_target, set()
                                        ),
                                    ) if owner_item_target else []
                                    if not any(
                                        _binding_target(candidate, rows) == action_target
                                        and action_kind(candidate) in allowed_actions
                                        and (required_contact is None or contact_damage(candidate) is required_contact)
                                        and not (
                                            INPUT_KIND_REGISTRY[str(candidate.get("input") or "")].exclusive
                                            and any(str(existing.get("input") or "") == candidate.get("input")
                                                    for existing in rows["bindings"])
                                        )
                                        for candidate in projected
                                    ):
                                        viable = False
                                        break
                                    create_binding_targets.add(action_target)
                                    create_binding_inputs.update(allowed_inputs)
                                    if allowed_actions:
                                        create_binding_actions.update(allowed_actions)
                                    else:
                                        for input_name in allowed_inputs:
                                            input_spec = INPUT_KIND_REGISTRY.get(input_name)
                                            if input_spec is not None:
                                                create_binding_actions.update(input_spec.allowed_actions)
                                    requested_actions = (
                                        allowed_actions
                                        if allowed_actions
                                        else {
                                            action_name
                                            for input_name in allowed_inputs
                                            for action_name in INPUT_KIND_REGISTRY[input_name].allowed_actions
                                        }
                                    )
                                    request_binding_creation(
                                        target_id=action_target,
                                        inputs=allowed_inputs,
                                        actions=requested_actions,
                                        required_contact=required_contact,
                                        owner_item_target_id=(
                                            target_id if target_kind == "item_body"
                                            else sole_item_entity_id
                                        ),
                                    )
                            if not viable:
                                continue
                            allowed_alternatives.append({
                                "event": event,
                                "requiredCalls": required_calls,
                                "requiredBindings": required_bindings,
                            })
                if allowed_alternatives:
                    requirement_row["allowedValues"] = sorted({
                        option["event"] for option in allowed_alternatives
                    })
                    event_alternative_rows.append({
                        "callId": node_id,
                        "targetId": target_id,
                        "allowed": allowed_alternatives,
                        "mustChooseOneCompleteAlternative": True,
                    })
                elif cap is not None and node_id:
                    # This invalid event has no executable producer under
                    # frozen context; deletion of its own call is leaf-local.
                    mark("calls", node_id, can_delete=True)
                    requirement_row["allowedValues"] = []
        elif code == "place_item_without_stack_cost":
            if node_namespace == "bindings":
                binding_id = str(node_row.get("id") or "")
                target_id = _binding_target(node_row, rows)
                mark("bindings", binding_id)
                grant("bindings", binding_id, "stackCost")
                binding_alternative_overrides[binding_id] = [transaction(
                    input_name=(
                        (expected_placeable_input(node_row, rows["bindings"]) or "")
                        if "dual_use_placeable_input_contract" in error_codes
                        else str(node_row.get("input") or "")
                    ),
                    action_name=action_kind(node_row),
                    target=target_id,
                    stack_cost_value=1,
                    contact_damage_value=False,
                    placement_call=placement_call_id(node_row),
                )]
                context["entities"].add(target_id)
                requirement_row["allowedBindingTransactions"] = binding_alternative_overrides[binding_id]
                requirement_row["allowedExistingBindingIds"] = [binding_id]
                requirement_row["mustChooseExactlyOne"] = True

        elif code == "dual_use_placeable_input_contract":
            related_bindings = [
                row_by_id[row_id]
                for row_id in related
                if namespace_by_id.get(row_id) == "bindings"
            ]
            for binding in related_bindings:
                binding_id = str(binding.get("id") or "")
                action_name = action_kind(binding)
                target_id = _binding_target(binding, rows)
                expected_input = expected_placeable_input(binding, rows["bindings"]) or ""
                if not expected_input:
                    continue
                action_spec = BINDING_ACTION_REGISTRY.get(action_name)
                target_kind = str(row_by_id.get(target_id, {}).get("kind") or "")
                if action_spec is None or target_kind not in action_spec.target_kinds:
                    continue
                mark("bindings", binding_id)
                binding_input_change_ids.add(binding_id)
                grant("bindings", binding_id, "input")
                binding_alternative_overrides[binding_id] = [transaction(
                    input_name=expected_input,
                    action_name=action_name,
                    target=target_id,
                    stack_cost_value=(1 if action_name == "place_item" else stack_cost(binding)),
                    contact_damage_value=(False if action_name == "place_item" else contact_damage(binding)),
                    placement_call=placement_call_id(binding),
                )]
                context["entities"].add(target_id)

        elif code == "missing_binding_dependency" and node_namespace == "calls" and node_id:
            capability = CAPABILITY_REGISTRY.get(str(node_row.get("fn") or ""))
            effect_group_id = _mapping(node_row.get("params")).get("effectGroupId") if capability is not None and capability.effect_groupable else None
            node_target_id = str(node_row.get("target") or "")
            owner_item_target_id = sole_item_entity_id
            selector_choices: list[tuple[str, dict[str, Any]]] = []
            held_selector_covers_group = False
            if isinstance(effect_group_id, str):
                for selector_error in error_rows:
                    selector_code = str(selector_error.get("code") or "")
                    if selector_code not in {"missing_effect_group", "invalid_held_effect_group", "invalid_reaction_effect_group"}:
                        continue
                    if effect_group_id not in _values(selector_error.get("allowed")):
                        continue
                    selector_node = _node_from_path(str(selector_error.get("path") or ""), indexed_rows)
                    if selector_node is None:
                        continue
                    selector_namespace, selector_index, _ = selector_node
                    selector = _mapping(indexed_rows[selector_namespace][selector_index])
                    if (selector_code in {"invalid_held_effect_group", "invalid_reaction_effect_group"} and capability is not None
                            and capability.name == "generated_buff_on_use"
                            and str(selector.get("target") or "") == node_target_id):
                        held_selector_covers_group = True
                    elif (selector_code == "missing_effect_group" and selector_namespace == "bindings"
                            and _binding_target(selector, rows) == node_target_id):
                        fixed = copy.deepcopy(dict(selector))
                        binding_id = str(fixed.pop("id", ""))
                        fixed["action"]["effectGroupId"] = effect_group_id
                        selector_choices.append((binding_id, fixed))
            if held_selector_covers_group:
                pending_groups = set()
                for dependency_error in error_rows:
                    if dependency_error.get("code") != "missing_binding_dependency":
                        continue
                    dependency_node = _node_from_path(str(dependency_error.get("path") or ""), indexed_rows)
                    if dependency_node is None or dependency_node[0] != "calls":
                        continue
                    dependency_call = _mapping(indexed_rows["calls"][dependency_node[1]])
                    dependency_cap = CAPABILITY_REGISTRY.get(str(dependency_call.get("fn") or ""))
                    group = _mapping(dependency_call.get("params")).get("effectGroupId")
                    if (dependency_cap is not None and dependency_cap.effect_groupable
                            and str(dependency_call.get("target") or "") == node_target_id
                            and isinstance(group, str)):
                        pending_groups.add(group)
                if len(pending_groups) == 1:
                    requirement_row["repairStrategy"] = "resolve_existing_effect_group_reference"
                    context["calls"].add(node_id)
                    continue
                # One held selector cannot consume multiple independent groups.
                requirement_row["repairStrategy"] = "retarget_held_selector_or_create_exact_consumer"
                context["calls"].add(node_id)
            authorized_capabilities = {
                capability_name
                for candidate_error in error_rows
                if exact_error_identity(candidate_error) == exact_error_identity(error)
                for capability_name in _capability_names(_values(candidate_error.get("allowed")))
            }
            authorized_capabilities.update(
                planned_item_capabilities_by_target.get(owner_item_target_id, set())
            )
            allowed_rows: list[dict[str, Any]] = []
            required_binding_updates: list[dict[str, Any]] = []
            existing_binding_choices: list[dict[str, Any]] = [
                {"bindingId": binding_id, "allowed": [fixed]}
                for binding_id, fixed in selector_choices
            ]

            def requirement_target_id(
                requirement_target: str,
                *,
                tuple_any_entity: bool = False,
            ) -> str:
                if requirement_target == "item_body":
                    return sole_item_entity_id
                if tuple_any_entity and requirement_target == "any_entity":
                    return ""
                return node_target_id

            def primary_relocation_to_alternate() -> tuple[str, dict[str, Any]] | None:
                existing_primary = next((
                    row for row in rows["bindings"]
                    if str(row.get("input") or "") == "primary_use"
                ), None)
                existing_alternate = next((
                    row for row in rows["bindings"]
                    if str(row.get("input") or "") == "alternate_use"
                ), None)
                if existing_primary is None or existing_alternate is not None:
                    return None
                binding_id = str(existing_primary.get("id") or "")
                action_name = action_kind(existing_primary)
                target_id = _binding_target(existing_primary, rows)
                action_spec = BINDING_ACTION_REGISTRY.get(action_name)
                alternate_spec = INPUT_KIND_REGISTRY.get("alternate_use")
                target_kind = next((
                    str(row.get("kind") or "") for row in rows["entities"]
                    if str(row.get("id") or "") == target_id
                ), "")
                use_policy = existing_primary
                if (
                    not binding_id
                    or not isinstance(use_policy, Mapping)
                    or action_spec is None
                    or alternate_spec is None
                    or action_name not in alternate_spec.allowed_actions
                    or "alternate_use" not in action_spec.allowed_inputs
                    or target_kind not in action_spec.target_kinds
                ):
                    return None
                return binding_id, {
                    "input": "alternate_use",
                    **{key: copy.deepcopy(use_policy[key]) for key in ("action", "stackCost", "contactDamage", "stackConsumeChancePercent") if key in use_policy},
                }

            primary_relocation: tuple[str, dict[str, Any]] | None = None
            if capability is not None:
                for capability_requirement in capability.requirements:
                    if capability_requirement.kind == "binding_action_reference":
                        required_target = requirement_target_id(capability_requirement.target)
                        reference_bindings = []
                        selector_can_repair = False
                        for binding_index, binding in enumerate(indexed_rows["bindings"]):
                            if not isinstance(binding, Mapping):
                                continue
                            target_path = f"$.runtimeProgram.bindings[{binding_index}].action.targetId"
                            kind_path = f"$.runtimeProgram.bindings[{binding_index}].action.kind"
                            if action_kind(binding) not in capability_requirement.any_of:
                                if kind_path in error_paths_all and isinstance(binding.get("action"), Mapping):
                                    for action_name in capability_requirement.any_of:
                                        choice = copy.deepcopy(binding)
                                        choice["action"].update(kind=action_name, placementCallId=node_id)
                                        if target_path in error_paths_all:
                                            choice["action"]["targetId"] = required_target
                                        if (required_target and _binding_target(choice, rows) == required_target
                                                and not strict_schema_errors(choice, binding_schema())):
                                            selector_can_repair = True
                                continue
                            if (_binding_target(binding, rows) == required_target
                                    or (required_target and target_path in error_paths_all)):
                                reference_bindings.append((binding, target_path in error_paths_all))
                        if selector_can_repair:
                            # A model-selected action and explicit call reference
                            # may restore this root; final validation proves exact
                            # one-consumer ownership without creating another lane.
                            requirement_row["repairStrategy"] = "repair_existing_binding_selectors"
                            continue
                        if reference_bindings:
                            # Reuse the authored action root with its exact broken
                            # call reference; adding a second root is not necessary.
                            for binding, target_invalid in reference_bindings:
                                fixed = copy.deepcopy(binding)
                                fixed.pop("id", None)
                                if target_invalid:
                                    fixed["action"]["targetId"] = required_target
                                fixed["action"]["placementCallId"] = node_id
                                existing_binding_choices.append({
                                    "bindingId": str(binding.get("id") or ""),
                                    "allowed": [fixed],
                                })
                            continue
                        occupied = {
                            str(row.get("input") or "") for row in rows["bindings"]
                        }
                        candidate_inputs: tuple[str, ...]
                        if "place_item" not in capability_requirement.any_of:
                            candidate_inputs = ()
                        elif "primary_use" in occupied and "alternate_use" not in occupied:
                            candidate_inputs = ("alternate_use",)
                        elif not occupied.intersection({"primary_use", "alternate_use"}):
                            candidate_inputs = ("primary_use",)
                        else:
                            candidate_inputs = ()
                        for input_name in candidate_inputs:
                            if not required_target:
                                continue
                            allowed_rows.append(transaction(
                                input_name=input_name,
                                action_name="place_item",
                                target=required_target,
                                stack_cost_value=1,
                                contact_damage_value=False,
                                placement_call=node_id,
                            ))
                    elif capability_requirement.kind == "binding_input_present":
                        required_target = requirement_target_id(capability_requirement.target)
                        allowed_rows.extend(
                            row for row in _binding_creation_alternatives(
                                rows,
                                owner_item_target_id=owner_item_target_id,
                                required_inputs=capability_requirement.any_of,
                                additional_item_capabilities=authorized_capabilities,
                            )
                            if _binding_target(row, rows) == required_target
                        )
                    elif capability_requirement.kind == "binding_action_present":
                        required_target = requirement_target_id(capability_requirement.target)
                        consumer_repairs = []
                        for binding_index, existing in enumerate(indexed_rows["bindings"]):
                            if not isinstance(existing, Mapping):
                                continue
                            binding_id = str(existing.get("id") or "")
                            target_path = f"$.runtimeProgram.bindings[{binding_index}].action.targetId"
                            kind_path = f"$.runtimeProgram.bindings[{binding_index}].action.kind"
                            if (not required_target or not binding_id
                                    or binding_id in ambiguous_ids["bindings"]
                                    or not {target_path, kind_path}.intersection(error_paths_all)
                                    or not isinstance(existing.get("action"), Mapping)
                                    or (capability.effect_groupable and
                                        _mapping(existing.get("action")).get("effectGroupId") != effect_group_id)):
                                continue
                            choices = []
                            for action_name in capability_requirement.any_of:
                                fixed = copy.deepcopy(existing)
                                if target_path in error_paths_all:
                                    fixed["action"]["targetId"] = required_target
                                if kind_path in error_paths_all:
                                    fixed["action"]["kind"] = action_name
                                # Co-diagnosed leaves have their own exact grants.
                                # They must not force an existing consumer into a
                                # new lane; only the model patch corrects them.
                                frozen_shape_errors = [
                                    shape_error for shape_error in strict_schema_errors(fixed, binding_schema())
                                    if str(shape_error.get("path") or "$").replace(
                                        "$", f"$.runtimeProgram.bindings[{binding_index}]", 1
                                    ) not in error_paths_all
                                ]
                                if (action_kind(fixed) != action_name
                                        or _binding_target(fixed, rows) != required_target
                                        or frozen_shape_errors):
                                    continue
                                fixed.pop("id")
                                choices.append(fixed)
                            if choices:
                                consumer_repairs.append({"bindingId": binding_id, "allowed": choices})
                        if consumer_repairs:
                            # Exact diagnosed selectors can restore the already
                            # authored consumer. Do not demand a second use lane;
                            # separate leaf permissions own every edit, and final
                            # validation still requires the dependency. Undecided
                            # actions remain model choices, not mandatory consumers.
                            requirement_row["repairStrategy"] = "repair_existing_binding_selectors"
                            context["bindings"].update(row["bindingId"] for row in consumer_repairs)
                            continue
                        existing_primary = next((
                            row for row in rows["bindings"]
                            if str(row.get("input") or "") == "primary_use"
                        ), None)
                        existing_alternate = next((
                            row for row in rows["bindings"]
                            if str(row.get("input") or "") == "alternate_use"
                        ), None)
                        required_inputs: tuple[str, ...] = ()
                        if (
                            existing_primary is not None
                            and (action_kind(existing_primary) in capability_requirement.any_of
                                 or isinstance(effect_group_id, str))
                            and existing_alternate is None
                        ):
                            required_inputs = ("alternate_use",)
                        elif existing_primary is not None and existing_alternate is None:
                            primary_relocation = primary_relocation_to_alternate()
                            if primary_relocation is not None:
                                required_inputs = ("primary_use",)
                        elif existing_primary is None and existing_alternate is None:
                            required_inputs = ("primary_use",)
                        required_target = requirement_target_id(capability_requirement.target)
                        allowed_rows.extend(
                            row for row in _binding_creation_alternatives(
                                rows,
                                owner_item_target_id=owner_item_target_id,
                                required_inputs=required_inputs,
                                additional_item_capabilities=authorized_capabilities,
                            )
                            if action_kind(row) in capability_requirement.any_of
                            and bool(required_target)
                            and _binding_target(row, rows) == required_target
                        )
                        if isinstance(effect_group_id, str):
                            for row in allowed_rows:
                                if action_kind(row) == "apply_item_effects":
                                    row["action"]["effectGroupId"] = effect_group_id
                    elif capability_requirement.kind == "binding_tuple_present":
                        required_patterns: list[tuple[str, str, bool | None]] = []
                        for value in capability_requirement.any_of:
                            parts = value.split("|")
                            if len(parts) not in {2, 3}:
                                continue
                            required_contact: bool | None = None
                            if len(parts) == 3:
                                if parts[2] == "contactDamage=true":
                                    required_contact = True
                                elif parts[2] == "contactDamage=false":
                                    required_contact = False
                                else:
                                    continue
                            required_patterns.append((parts[0], parts[1], required_contact))
                        target_is_any_entity = capability_requirement.target == "any_entity"
                        required_target = requirement_target_id(
                            capability_requirement.target,
                            tuple_any_entity=True,
                        )

                        repaired_policy_pairs: set[tuple[str, str]] = set()
                        for existing in rows["bindings"]:
                            existing_pair = (str(existing.get("input") or ""), action_kind(existing))
                            if (
                                not target_is_any_entity
                                and (
                                    not required_target
                                    or _binding_target(existing, rows) != required_target
                                )
                            ):
                                continue
                            required_contact = next((
                                contact
                                for input_name, action_name, contact in required_patterns
                                if (input_name, action_name) == existing_pair
                                and contact is not None
                                and contact_damage(existing) is not contact
                            ), None)
                            if required_contact is None:
                                continue
                            binding_id = str(existing.get("id") or "")
                            fixed = transaction(
                                input_name=existing_pair[0],
                                action_name=existing_pair[1],
                                target=_binding_target(existing, rows),
                                stack_cost_value=stack_cost(existing),
                                contact_damage_value=required_contact,
                                placement_call=placement_call_id(existing),
                            )
                            mark("bindings", binding_id)
                            grant("bindings", binding_id, "contactDamage")
                            binding_alternative_overrides[binding_id] = [fixed]
                            context["bindings"].add(binding_id)
                            context["entities"].add(_binding_target(existing, rows))
                            existing_binding_choices.append({
                                "bindingId": binding_id,
                                "allowed": [copy.deepcopy(fixed)],
                            })
                            repaired_policy_pairs.add(existing_pair)

                        required_patterns = [
                            pattern for pattern in required_patterns
                            if (pattern[0], pattern[1]) not in repaired_policy_pairs
                        ]
                        required_pairs = {(pattern[0], pattern[1]) for pattern in required_patterns}
                        occupied_inputs = {
                            str(row.get("input") or "")
                            for row in rows["bindings"]
                            if str(row.get("input") or "") in {"primary_use", "alternate_use"}
                        }
                        existing_primary = next((
                            row for row in rows["bindings"]
                            if str(row.get("input") or "") == "primary_use"
                        ), None)
                        current_primary_pair = (
                            ("primary_use", action_kind(existing_primary))
                            if existing_primary is not None else None
                        )
                        if (
                            existing_primary is not None
                            and "alternate_use" not in occupied_inputs
                            and current_primary_pair not in required_pairs
                            and any(pair[0] == "primary_use" for pair in required_pairs)
                        ):
                            primary_relocation = primary_relocation_to_alternate()
                            if primary_relocation is not None:
                                occupied_inputs.discard("primary_use")
                        primary_combat_exists = any(
                            str(row.get("input") or "") == "primary_use"
                            and action_kind(row) in {"spawn_entity", "use_item_body"}
                            for row in rows["bindings"]
                        )
                        required_patterns = [
                            pattern for pattern in required_patterns
                            if pattern[0] not in occupied_inputs
                            and (
                                pattern[1] != "place_item"
                                or (primary_combat_exists and pattern[0] == "alternate_use")
                                or (not occupied_inputs and pattern[0] == "primary_use")
                            )
                        ]
                        allowed_rows.extend(
                            row for row in _binding_creation_alternatives(
                                rows,
                                owner_item_target_id=owner_item_target_id,
                                required_inputs=tuple(sorted({pattern[0] for pattern in required_patterns})),
                                additional_item_capabilities=authorized_capabilities,
                            )
                            if any(
                                row["input"] == input_name
                                and action_kind(row) == required_action
                                and (required_contact is None or contact_damage(row) is required_contact)
                                for input_name, required_action, required_contact in required_patterns
                            )
                            and (
                                target_is_any_entity
                                or (
                                    bool(required_target)
                                    and _binding_target(row, rows) == required_target
                                )
                            )
                        )

            if primary_relocation is not None and any(
                str(row.get("input") or "") == "primary_use" for row in allowed_rows
            ):
                binding_id, relocated = primary_relocation
                mark("bindings", binding_id)
                binding_input_change_ids.add(binding_id)
                binding_alternative_overrides[binding_id] = [relocated]
                context["bindings"].add(binding_id)
                context["entities"].add(_binding_target(relocated, rows))
                required_binding_updates.append({
                    "bindingId": binding_id,
                    "allowed": [copy.deepcopy(relocated)],
                })
            allowed_rows = sorted(
                {repr(row): row for row in allowed_rows}.values(),
                key=repr,
            )
            if len(existing_binding_choices) == 1 and not allowed_rows:
                required_binding_updates.extend(existing_binding_choices)
                existing_binding_choices = []
            existing_choice_rows = sorted(
                {
                    repr(choice["allowed"][0]): copy.deepcopy(choice["allowed"][0])
                    for choice in existing_binding_choices
                }.values(),
                key=repr,
            )
            binding_choice_rows = sorted(
                {repr(row): row for row in [*allowed_rows, *existing_choice_rows]}.values(),
                key=repr,
            )
            create_binding_alternatives.extend(allowed_rows)
            for allowed_row in allowed_rows:
                create_binding_inputs.add(allowed_row["input"])
                create_binding_actions.add(action_kind(allowed_row))
                create_binding_targets.add(_binding_target(allowed_row, rows))
                context["entities"].add(_binding_target(allowed_row, rows))
            requirement_row["allowedBindingTransactions"] = binding_choice_rows
            requirement_row["allowedExistingBindingIds"] = sorted(
                str(choice.get("bindingId") or "")
                for choice in existing_binding_choices
                if str(choice.get("bindingId") or "")
            )
            requirement_row["mustChooseExactlyOne"] = bool(binding_choice_rows) and not held_selector_covers_group
            requirement_row["mustCreateExactlyOne"] = bool(allowed_rows) and not existing_choice_rows and not held_selector_covers_group
            if required_binding_updates:
                requirement_row["requiredBindingUpdates"] = required_binding_updates
                requirement_row["mustApplyAll"] = True

        elif code in {
            "missing_required_component", "missing_movement_component", "inert_stationary_entity",
            "binding_dependency", "event_not_emitted", "missing_item_capability_param",
            "missing_capability_dependency", "missing_capability_group",
        }:
            if (
                code == "binding_dependency"
                and node_namespace == "bindings"
                and node_id
                and _binding_delete_preserves_reachability(rows, node_id)
            ):
                mark("bindings", node_id, can_delete=True)
            if code == "event_not_emitted" and node_namespace == "calls":
                exact_event_target = str(node_row.get("target") or "")
                target_ids = [exact_event_target] if exact_event_target else []
            else:
                target_ids = [row_id for row_id in related if namespace_by_id.get(row_id) == "entities"]
                if not target_ids and node_namespace == "calls":
                    target_ids = [str(node_row.get("target") or "")]
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
            if code == "event_not_emitted" and node_namespace == "calls" and target_ids:
                event_target_id = target_ids[0]
                event_target_kind = str(row_by_id.get(event_target_id, {}).get("kind") or "")
                event_name = authored_event(_mapping(node_row.get("params")))
                (
                    allowed_event_alternatives,
                    event_create_choices,
                    event_existing_choices,
                    binding_change_required_by_alternative,
                ) = _missing_event_producer_choices(
                    rows,
                    event_name=event_name,
                    event_target_id=event_target_id,
                    event_target_kind=event_target_kind,
                    sole_item_entity_id=sole_item_entity_id,
                    planned_item_capabilities_by_target=planned_item_capabilities_by_target,
                )
                if allowed_event_alternatives:
                    event_alternative_rows.append({
                        "callId": node_id,
                        "targetId": event_target_id,
                        "allowed": allowed_event_alternatives,
                        "mustChooseOneCompleteAlternative": True,
                    })
                elif node_id:
                    # Frozen engine gates leave no executable producer. Only
                    # the invalid event call may be removed, not valid gates.
                    mark("calls", node_id, can_delete=True)
                    requirement_row["allowedValues"] = []
                event_create_choices = list({
                    repr(row): row for row in event_create_choices
                }.values())
                event_existing_choices = list({
                    str(row["bindingId"]): row for row in event_existing_choices
                }.values())
                for choice in event_existing_choices:
                    binding_id = str(choice["bindingId"])
                    fixed = copy.deepcopy(choice["allowed"][0])
                    mark("bindings", binding_id)
                    grant("bindings", binding_id, "contactDamage")
                    binding_alternative_overrides.setdefault(binding_id, []).append(fixed)
                    context["bindings"].add(binding_id)
                create_binding_alternatives.extend(event_create_choices)
                for choice in event_create_choices:
                    create_binding_targets.add(_binding_target(choice, rows))
                    create_binding_inputs.add(str(choice.get("input") or ""))
                    create_binding_actions.add(action_kind(choice))
                all_binding_choices = [
                    copy.deepcopy(row) for row in event_create_choices
                ] + [
                    copy.deepcopy(choice["allowed"][0])
                    for choice in event_existing_choices
                ]
                if all_binding_choices:
                    binding_change_is_mandatory = (
                        binding_change_required_by_alternative
                        and all(binding_change_required_by_alternative)
                    )
                    if (
                        binding_change_is_mandatory
                        and len(event_existing_choices) == 1
                        and not event_create_choices
                    ):
                        requirement_row["requiredBindingUpdates"] = event_existing_choices
                        requirement_row["mustApplyAll"] = True
                    else:
                        requirement_row["allowedBindingTransactions"] = all_binding_choices
                        requirement_row["allowedExistingBindingIds"] = sorted(
                            str(choice["bindingId"])
                            for choice in event_existing_choices
                        )
                    if binding_change_is_mandatory and not requirement_row.get("mustApplyAll"):
                        requirement_row["mustChooseExactlyOne"] = True
                        if not event_existing_choices:
                            requirement_row["mustCreateExactlyOne"] = True
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
                    request_binding_creation(
                        target_id=row_id,
                        inputs=("primary_use", "alternate_use"),
                        actions=("spawn_entity",),
                        owner_item_target_id=sole_item_entity_id,
                    )
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
                    if isinstance(call.get("params"), Mapping) and "when" in call["params"]:
                        call_event_change_ids.add(call_id)
                        grant("calls", call_id, "params.when")
        # Existing related nodes are useful context unless explicitly mutable.
        for row_id in related:
            context_id(row_id)

    # A mutable node may depend on other valid nodes. Include those as immutable context.
    for binding_id in list(mutable["bindings"]):
        binding = row_by_id.get(binding_id, {})
        context["entities"].add(_binding_target(binding, rows))
    for call_id in list(mutable["calls"]):
        call = row_by_id.get(call_id, {})
        context["entities"].add(str(call.get("target") or ""))
        context["entities"].update(_entity_reference_params(call))
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if cap is not None:
            existing_broken_capabilities.add(cap.name)

    # Remove mutable rows from immutable context sets.
    for namespace in context:
        context[namespace].difference_update(mutable[namespace])
        context[namespace].discard("")

    # The Repair prompt distinguishes direct blockers from their technical
    # support dependencies.  It never receives the full full capability catalog.
    direct_blocker_capabilities.update(
        name for name in create_call_fns
        if name in CAPABILITY_REGISTRY and name not in event_supporting_capabilities
    )
    registered_capabilities = set(CAPABILITY_REGISTRY)
    direct_blocker_capabilities.intersection_update(registered_capabilities)
    existing_broken_capabilities.intersection_update(registered_capabilities)
    supporting_capabilities = (
        _capability_dependency_closure(direct_blocker_capabilities) - direct_blocker_capabilities
    ) | event_supporting_capabilities
    supporting_capabilities.intersection_update(registered_capabilities)
    if create_call_fns:
        create_call_fns.update(supporting_capabilities)
    capability_subset = direct_blocker_capabilities | supporting_capabilities | existing_broken_capabilities

    # Every binding creation permission is represented by complete executable
    # registry tuples.  The scope never nominates one tuple and never falls back
    # to an unchecked input/action/target cross-product.
    requested_binding_targets = set(create_binding_targets)
    requested_binding_inputs = set(create_binding_inputs)
    requested_binding_actions = set(create_binding_actions)
    for (
        requested_target,
        requested_inputs_for_target,
        requested_actions_for_target,
        requested_contact,
        declared_owner_item_target,
    ) in binding_creation_requests:
        target_kind = str(row_by_id.get(requested_target, {}).get("kind") or "")
        owner_item_target = (
            declared_owner_item_target
            or (requested_target if target_kind == "item_body" else sole_item_entity_id)
        )
        if not owner_item_target:
            continue
        projected_rows = _binding_creation_alternatives(
            rows,
            owner_item_target_id=owner_item_target,
            required_inputs=requested_inputs_for_target,
            additional_item_capabilities=planned_item_capabilities_by_target.get(
                owner_item_target, set()
            ),
        )
        for projected_row in projected_rows:
            if (
                _binding_target(projected_row, rows) != requested_target
                or action_kind(projected_row) not in requested_actions_for_target
                or (
                    requested_contact is not None
                    and contact_damage(projected_row) is not requested_contact
                )
            ):
                continue
            create_binding_alternatives.append(projected_row)
    create_binding_alternatives = sorted(
        {
            repr(row): row
            for row in create_binding_alternatives
            if _binding_target(row, rows) in requested_binding_targets
            and (not requested_binding_inputs or row.get("input") in requested_binding_inputs)
            and (not requested_binding_actions or action_kind(row) in requested_binding_actions)
        }.values(),
        key=repr,
    )
    create_binding_targets = {_binding_target(row, rows) for row in create_binding_alternatives}
    create_binding_inputs = {row["input"] for row in create_binding_alternatives}
    create_binding_actions = {action_kind(row) for row in create_binding_alternatives}

    # Identity/reference permissions are also represented as exact mutable
    # fields so the conservative merge can retain every unrelated old value.
    for row_id in entity_kind_change_ids:
        grant("entities", row_id, "kind")
    for row_id in binding_input_change_ids:
        grant("bindings", row_id, "input")
    for row_id in binding_action_change_ids:
        grant("bindings", row_id, "action.kind")
        binding = row_by_id.get(row_id, {})
        # Expose the required call reference of a possible selected placement
        # branch. The model must supply it; no value is copied into the patch.
        for variant in binding_schema()["oneOf"]:
            action_shape = variant["properties"]["action"]
            if (variant["properties"]["input"]["const"] == binding.get("input")
                    and "placementCallId" in action_shape["required"]
                    and (placement_choices := _complete_binding_transactions(
                        rows, input_name=str(binding.get("input") or ""),
                        action_name=action_shape["properties"]["kind"]["const"],
                        target_id=_body_id(rows)))
                    and not any(
                        _mapping(binding.get("action")).get("placementCallId")
                        == _mapping(choice.get("action")).get("placementCallId")
                        for choice in placement_choices
                    )):
                grant("bindings", row_id, "action.placementCallId")
    for row_id in binding_target_change_ids:
        grant("bindings", row_id, "target")
    for row_id in call_fn_change_ids:
        grant("calls", row_id, "fn")
    for row_id in call_target_change_ids:
        grant("calls", row_id, "target")
    for row_id in call_event_change_ids:
        grant("calls", row_id, "params.when")
    for encoded in call_reference_param_changes:
        row_id, param_name = encoded.split(":", 1)
        grant("calls", row_id, f"params.{param_name}")
    # Expose all exact missing leaves reachable from an authorized selector.
    # The model still chooses the selector; filtering admits only its branch.
    for call in rows["calls"]:
        call_id = str(call.get("id") or "")
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if cap is None:
            continue
        params = _mapping(call.get("params"))
        permissions = field_permissions["calls"].get(call_id, set())
        for selector, _expected, required in _conditional_param_dependencies(cap):
            if f"params.{selector}" in permissions and required not in params:
                grant("calls", call_id, f"params.{required}")
    # A formerly inactive omitted field becomes an explicit decision only when
    # Repair is allowed to change the exact consumer branch that hid it.
    for call in rows["calls"]:
        call_id, target = str(call.get("id") or ""), str(call.get("target") or "")
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if cap is None:
            continue
        params = _mapping(call.get("params"))
        own_permissions = field_permissions["calls"].get(call_id, set())
        for name, spec in cap.params.items():
            condition = spec.omission_condition
            if name in params or condition is None:
                continue
            selector_changes = any(f"params.{selector}" in own_permissions for selector, _ in condition.param_equals)
            kind_changes = bool(condition.target_kinds and target in entity_kind_change_ids)
            support_changes = any(
                row.get("target") == target and row.get("fn") in condition.target_capabilities
                and (str(row.get("id") or "") in call_fn_change_ids
                     or str(row.get("id") or "") in call_target_change_ids
                     or str(row.get("id") or "") in deletable["calls"])
                for row in rows["calls"]
            )
            if selector_changes or kind_changes or support_changes:
                mark("calls", call_id)
                grant("calls", call_id, f"params.{name}")
                context_id(target)
    # Retained opcode/receipt metadata is not a fresh Author/Repair vocabulary.
    create_call_fns.intersection_update(
        name for name, cap in CAPABILITY_REGISTRY.items() if cap.author_visible
    )
    scope = _new_scope()
    scope["mutable"] = {
        "entityIds": sorted(mutable["entities"]),
        "bindingIds": sorted(mutable["bindings"]),
        "callIds": sorted(mutable["calls"]),
    }
    scope["deletable"] = {
        "entityIds": sorted(deletable["entities"]),
        "bindingIds": sorted(deletable["bindings"]),
        "callIds": sorted(deletable["calls"]),
        "entityIndices": sorted(deletable_indices["entities"]),
        "bindingIndices": sorted(deletable_indices["bindings"]),
        "callIndices": sorted(deletable_indices["calls"]),
        "callParamKeys": [
            {"callId": call_id, "key": key}
            for call_id, key in sorted(deletable_call_param_keys)
            if call_id not in ambiguous_ids["calls"]
        ],
        "callPropertyKeys": [
            {"callId": call_id, "key": key}
            for call_id, key in sorted(deletable_call_property_keys)
            if call_id not in ambiguous_ids["calls"]
        ],
    }
    scope["create"] = {
        "entities": {
            "allowed": bool(create_entity_exact or create_entity_kinds),
            "exactIds": sorted(create_entity_exact),
            "allowedKinds": sorted(create_entity_kinds),
        },
        "bindings": {
            "allowed": bool(create_binding_alternatives),
            "allowedTargetIds": sorted(create_binding_targets),
            "allowedInputs": sorted(create_binding_inputs),
            "allowedActions": sorted(create_binding_actions),
            "requiredTargetIds": sorted(create_binding_targets),
            "allowedTransactions": create_binding_alternatives,
            "mustChooseExactlyOne": bool(create_binding_alternatives),
        },
        "calls": {
            "allowed": bool((create_call_targets or create_call_target_kinds) and create_call_fns),
            "allowedTargetIds": sorted(create_call_targets),
            "allowedTargetKinds": sorted(create_call_target_kinds),
            "allowedFns": sorted(create_call_fns.intersection(CAPABILITY_REGISTRY)),
            "requiredReferenceEntityIds": sorted(required_reference_entities),
        },
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
    }
    scope["metadataFields"] = sorted(metadata_fields)

    scope["contextIds"] = {
        "entityIds": sorted(context["entities"]),
        "bindingIds": sorted(context["bindings"]),
        "callIds": sorted(context["calls"]),
    }
    scope["fieldPermissions"] = {
        namespace: _field_permission_rows(field_permissions[namespace])
        for namespace in ("entities", "bindings", "calls")
    }
    error_codes = {str(row.get("code") or row.get("kind") or "") for row in error_rows}
    primary_candidates = sorted(
        str(row.get("id") or "")
        for row in rows["entities"]
        if str(row.get("id") or "")
    )
    primary_shape_error = any(
        str(row.get("path") or "") == PRIMARY_ENTITY_JSON_PATH
        and str(row.get("code") or row.get("kind") or "").startswith("shape_")
        for row in error_rows
    )
    hidden_primary_candidates = sorted({
        str(candidate)
        for error in error_rows
        if str(error.get("code") or error.get("kind") or "") == "hidden_item_primary_requires_spawn_target"
        for candidate in error.get("allowed") or []
        if str(candidate) in primary_candidates
    })
    if hidden_primary_candidates:
        scope["repairTransactions"][PRIMARY_ENTITY_SELECTION_FIELD] = primary_entity_repair_transaction(hidden_primary_candidates)
    elif ("invalid_primary_entity_reference" in error_codes or primary_shape_error) and primary_candidates:
        scope["repairTransactions"][PRIMARY_ENTITY_SELECTION_FIELD] = primary_entity_repair_transaction(primary_candidates)

    binding_alternatives: list[dict[str, Any]] = []
    binding_rows_by_id = {
        str(row.get("id") or ""): row
        for row in rows["bindings"]
        if str(row.get("id") or "")
    }
    for row_id in sorted(
        binding_input_change_ids | binding_action_change_ids | binding_target_change_ids
        | binding_alternative_overrides.keys()
    ):
        binding = binding_rows_by_id.get(row_id)
        if binding is None:
            continue
        binding_choices = binding_alternative_overrides.get(row_id)
        if binding_choices is None:
            binding_choices = _binding_repair_alternatives(
                rows,
                binding,
                input_mutable=row_id in binding_input_change_ids,
                action_mutable=row_id in binding_action_change_ids,
                target_mutable=row_id in binding_target_change_ids,
                mutable_paths=field_permissions["bindings"].get(row_id, set()),
            )
        selector_domains = [error.get("allowed") or [] for error in error_rows
                            if str(error.get("code") or "") == "missing_effect_group"
                            and row_id in (error.get("relatedIds") or [])]
        if selector_domains:
            binding_choices = [{**copy.deepcopy(row), "action": {**copy.deepcopy(_mapping(row.get("action"))), "effectGroupId": group}}
                               for row in binding_choices if action_kind(row) == "apply_item_effects"
                               for group in selector_domains[0]]
        chance = binding.get("stackConsumeChancePercent")
        if (type(chance) is int and 0 <= chance <= 100
                and "stackConsumeChancePercent" not in field_permissions["bindings"].get(row_id, set())):
            for alternative in binding_choices:
                alternative["stackConsumeChancePercent"] = chance
            binding_choices = [alternative for alternative in binding_choices if not stack_chance_error(alternative)]
        elif "stackConsumeChancePercent" in field_permissions["bindings"].get(row_id, set()):
            # Explicit bounded model choices, not a correction/default in source.
            chance_shapes = [variant["properties"]["stackConsumeChancePercent"]
                             for variant in binding_schema()["oneOf"]
                             if "stackConsumeChancePercent" in variant["properties"]]
            chance_values = sorted({value for shape in chance_shapes
                                    for value in range(shape["minimum"], shape["maximum"] + 1)})
            binding_choices = [
                {**copy.deepcopy(alternative), "stackConsumeChancePercent": value}
                for alternative in binding_choices
                for value in chance_values
                if not stack_chance_error({**alternative, "stackConsumeChancePercent": value})
            ]
        group_id = _mapping(binding.get("action")).get("effectGroupId")
        if (isinstance(group_id, str)
                and "action.effectGroupId" not in field_permissions["bindings"].get(row_id, set())):
            for alternative in binding_choices:
                alternative_action = dict(_mapping(alternative.get("action")))
                alternative_action["effectGroupId"] = group_id
                alternative["action"] = alternative_action
            binding_choices = [alternative for alternative in binding_choices
                               if not strict_schema_errors({"id": row_id, **alternative}, binding_schema())]
        binding_alternatives.append({"bindingId": row_id, "allowed": binding_choices})
        retarget_binding_ids.update(_binding_target(row, rows) for row in binding_choices)
    scope["bindingAlternatives"] = binding_alternatives
    scope["eventAlternatives"] = event_alternative_rows
    scope["retarget"]["bindingTargetIds"] = sorted(retarget_binding_ids)

    bindings_by_id = {
        str(row.get("id") or ""): row
        for row in rows["bindings"]
        if str(row.get("id") or "")
    }
    exclusive_inputs: set[str] = set()
    for error in error_rows:
        if str(error.get("code") or error.get("kind") or "") != "duplicate_exclusive_input":
            continue
        related_ids = [str(value) for value in error.get("relatedIds") or [] if str(value)]
        if not related_ids:
            node = _node_from_path(str(error.get("path") or "$"), indexed_rows)
            if node is not None and node[0] == "bindings" and node[2]:
                related_ids = [node[2]]
        exclusive_inputs.update(
            str(bindings_by_id[row_id].get("input") or "")
            for row_id in related_ids
            if row_id in bindings_by_id and str(bindings_by_id[row_id].get("input") or "")
        )
    exclusive_transactions: list[dict[str, Any]] = []
    for input_name in sorted(exclusive_inputs):
        candidate_ids = sorted(
            row_id
            for row_id, row in bindings_by_id.items()
            if str(row.get("input") or "") == input_name
        )
        if len(candidate_ids) <= 1:
            continue
        exclusive_transactions.append({
            "input": input_name,
            "candidateBindingIds": _reachability_safe_exclusive_candidates(
                rows,
                input_name=input_name,
                candidate_ids=candidate_ids,
            ),
            "mustKeepExactlyOne": True,
        })
    scope["repairTransactions"]["exclusiveInputSelections"] = exclusive_transactions
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
    # Only compiler-view transaction alternatives are projected; raw source facts
    # and diagnostic values must never be normalized by a recursive walker.
    for key in ("bindingAlternatives", "repairRequirements", "create", "blockerPlan"):
        scope[key] = _source_scope_transactions(scope[key], item_body_id=_body_id(rows))
    return scope
