from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.runtime_authoring.binding_use_policy import (
    ACTIVE_USE_INPUTS,
    action_kind,
    action as binding_action,
    contact_damage,
    placeable_input_contract,
    placement_call_id,
    stack_cost,
    may_retain_stack,
    target_id as binding_target_id,
)
from infini_local.core.runtime_authoring.capability_registry import (
    PROJECTILE_MODIFIER_COMPONENTS,
    authored_event,
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    target_updates_per_tick,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    CapabilitySpec,
    RequirementSpec,
    compatible_entity_reference_ids,
    referenced_entity_requirement_satisfied,
    event_alternative_is_present,
    event_dependency_alternatives,
    event_dependency_descriptors,
)
from infini_local.core.runtime_authoring.event_producer_validation import item_body_event_produced
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_JSON_PATH,
    authored_primary_entity_id,
    is_advisory_path,
    strict_author_shape_report,
)


MAX_RUNTIME_ENTITIES = 12
MAX_RUNTIME_BINDINGS = 8
MAX_RUNTIME_CALLS = 48
MAX_RUNTIME_EVENTS_PER_ENTITY = 16  # Matches InfiniRuntimeLimits.MaxRuntimeEventsPerEntity.
MAX_CHILD_DEPTH = 3
MAX_EVENT_SPAWNS_PER_ACTIVATION = 32

# Finite semantic error inventory. Shape errors are emitted as ``shape_*`` and
# are handled separately by the provider/strict-schema boundary. Every code in
# this set must have an explicit conditional-Repair policy.
VALIDATION_ERROR_CODES = frozenset({
    "unordered_param_range",
    "unsupported_param_variant_target_kind",
    "incompatible_param_variant",
    "ambiguous_global_id",
    "binding_dependency",
    "missing_effect_group",
    "invalid_held_effect_group",
    "invalid_reaction_effect_group",
    "capability_event_incompatible",
    "child_depth_budget",
    "consumer_representability",
    "dual_use_placeable_input_contract",
    "duplicate_exclusive_input",
    "duplicate_id",
    "duplicate_placed_body_reference",
    "duplicate_single_component",
    "duplicate_equipment_damage_selector",
    "equipment_scope_conflict",
    "empty_component",
    "entity_not_binding_spawnable",
    "event_not_emitted",
    "event_spawn_budget",
    "entity_event_budget",
    "exclusive_component_conflict",
    "overlapping_motion_windows",
    "retained_motion_stage_conflict",
    "hidden_item_primary_requires_spawn_target",
    "illegal_event_cycle",
    "inert_component",
    "inert_stationary_entity",
    "item_body_count",
    "missing_capability_dependency",
    "missing_capability_group",
    "missing_binding_dependency",
    "missing_dependency_param",
    "missing_entity_reference",
    "missing_item_capability_param",
    "missing_light_color",
    "set_bonus_head_only",
    "missing_movement_component",
    "missing_set_key",
    "missing_required_component",
    "place_item_without_stack_cost",
    "placed_body_placement_reference",
    "hybrid_placeable_max_stack",
    "invalid_primary_entity_reference",
    "self_reference_forbidden",
    "unknown_capability",
    "unknown_registry_requirement",
    "unreachable_entity",
    "unsupported_input_action",
    "unsupported_param_target_kind",
    "wrong_binding_target_kind",
    "wrong_reference_target_kind",
    "reference_requirements_unsatisfied",
    "wrong_target_kind",
})


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    path: str
    code: str
    message: str
    allowed: tuple[str, ...] = ()
    related_ids: tuple[str, ...] = ()

    def row(self) -> dict[str, Any]:
        out = asdict(self)
        out["allowed"] = list(self.allowed)
        out["relatedIds"] = list(self.related_ids)
        out.pop("related_ids", None)
        return out


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _calls_by_target(program: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for call in _rows(program.get("calls")):
        out.setdefault(str(call.get("target") or ""), []).append(call)
    return out


def _primary_entity_issues(
    entities_by_id: Mapping[str, Mapping[str, Any]],
    program: Mapping[str, Any],
) -> tuple[list[ValidationIssue], str]:
    primary_entity_id = authored_primary_entity_id(program)
    if primary_entity_id in entities_by_id:
        return [], primary_entity_id
    return [ValidationIssue(
        PRIMARY_ENTITY_JSON_PATH,
        "invalid_primary_entity_reference",
        f"primaryEntityId '{primary_entity_id}' must equal one exact authored entity id.",
        tuple(entities_by_id),
        (primary_entity_id,) if primary_entity_id else (),
    )], ""


def _hidden_item_spawn_primary_target(program: Mapping[str, Any], item_id: str) -> str:
    """Return the only explicit lifecycle target when the item body cannot represent use."""
    item_use_calls = [
        row for row in _rows(program.get("calls"))
        if row.get("fn") == "configure_item_use" and str(row.get("target") or "") == item_id
    ]
    if len(item_use_calls) != 1:
        return ""
    params = item_use_calls[0].get("params")
    if not isinstance(params, Mapping) or params.get("hideUseGraphic") is not True:
        return ""
    active_bindings = [
        row for row in _rows(program.get("bindings"))
        if str(row.get("input") or "") in ACTIVE_USE_INPUTS
    ]
    if not active_bindings or any(
        contact_damage(row) or action_kind(row) != "spawn_entity"
        for row in active_bindings
    ):
        return ""
    targets = {binding_target_id(row) for row in active_bindings if binding_target_id(row)}
    return next(iter(targets)) if len(targets) == 1 else ""


def _exclusive_input_issues(bindings: list[dict[str, Any]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    exclusive_inputs: dict[str, tuple[int, str]] = {}
    for index, binding in enumerate(bindings):
        binding_id = str(binding.get("id") or "")
        input_name = str(binding.get("input") or "")
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        if input_spec is None or not input_spec.exclusive:
            continue
        if input_name in exclusive_inputs:
            previous_index, previous_id = exclusive_inputs[input_name]
            issues.append(ValidationIssue(
                f"$.runtimeProgram.bindings[{index}].input",
                "duplicate_exclusive_input",
                f"bindings[{previous_index}] ('{previous_id}') and bindings[{index}] ('{binding_id}') both own exclusive input {input_name}.",
                ("use another input", "sequence through an event", "remove one binding"),
                (previous_id, binding_id),
            ))
        else:
            exclusive_inputs[input_name] = (index, binding_id)
    return issues


def _traversable_runtime_shell(document: Mapping[str, Any]) -> bool:
    """Return whether the single semantic validator can safely traverse row headers.

    Capability parameter shape remains independently owned by the strict schema.
    A malformed leaf must not hide graph/role/input blockers, but malformed list or
    object containers do not provide a trustworthy graph and stay shape-only.
    """

    program = document.get("runtimeProgram")
    if not isinstance(program, Mapping):
        return False
    containers = (
        program.get("entities"),
        program.get("bindings"),
        program.get("calls"),
    )
    return all(
        isinstance(rows, list)
        for rows in containers
    )


def _graph_cycle(edges: Mapping[str, set[str]]) -> tuple[str, ...]:
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def visit(node: str) -> tuple[str, ...]:
        if node in active_set:
            index = active.index(node)
            return tuple((*active[index:], node))
        if node in visited:
            return ()
        visited.add(node)
        active.append(node)
        active_set.add(node)
        for child in edges.get(node, set()):
            cycle = visit(child)
            if cycle:
                return cycle
        active.pop()
        active_set.remove(node)
        return ()

    for node in edges:
        cycle = visit(node)
        if cycle:
            return cycle
    return ()


def _max_depth(edges: Mapping[str, set[str]], roots: Iterable[str]) -> int:
    memo: dict[str, int] = {}

    def depth(node: str) -> int:
        if node in memo:
            return memo[node]
        children = edges.get(node, set())
        value = 0 if not children else 1 + max(depth(child) for child in children)
        memo[node] = value
        return value

    return max((depth(root) for root in roots), default=0)


def _numeric_param(params: Mapping[str, Any], key: str, default: int | float) -> int | float:
    value = params.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Predicate comparison needs no coercion. A valid JSON integer may be
        # outside float range; strict shape owns its structured refusal.
        return value
    return default


def _has_non_neutral_generated_buff(params: Mapping[str, Any]) -> bool:
    # Preserve the existing strict-wire seam; effect facts live in the registry.
    return CAPABILITY_REGISTRY["apply_generated_buff_on_use"].has_non_neutral_effect(params)


def _event_available(
    *,
    event: str,
    target_id: str,
    kind: str,
    calls_by_target: Mapping[str, list[dict[str, Any]]],
    bindings: list[dict[str, Any]],
) -> tuple[bool, tuple[str, ...], str]:
    spec = EVENT_KIND_REGISTRY.get(event)
    if spec is None:
        return False, tuple(EVENT_KIND_REGISTRY), f"unknown event '{event}'"
    if kind not in spec.source_kinds:
        return False, spec.source_kinds, f"{kind} cannot emit {event}"

    target_calls = calls_by_target.get(target_id, [])
    alternatives = event_dependency_alternatives(event, kind)
    if kind in spec.producer_binding_kinds:
        if item_body_event_produced(event, target_id=target_id, target_calls=target_calls, bindings=bindings):
            return True, (), ""
        return False, event_dependency_descriptors(alternatives), f"{event} requires an enabled item-body producer on {target_id}"

    for alternative in alternatives:
        if event_alternative_is_present(
            alternative,
            target_id=target_id,
            target_calls=target_calls,
            bindings=bindings,
        ):
            return True, (), ""
    return False, event_dependency_descriptors(alternatives), f"{event} requires one exact declared producer alternative on {target_id}"


def _validate_requirement(
    requirement: RequirementSpec,
    *,
    call: Mapping[str, Any],
    call_index: int,
    cap: CapabilitySpec,
    item_id: str,
    calls_by_target: Mapping[str, list[dict[str, Any]]],
    entities_by_id: Mapping[str, dict[str, Any]],
    bindings: list[dict[str, Any]],
    primary_entity_id: str,
    calls: list[dict[str, Any]] | None = None,
) -> ValidationIssue | None:
    target_id = str(call.get("target") or "")
    if requirement.when_spawned_by_inputs and not any(
        binding.get("input") in requirement.when_spawned_by_inputs
        and action_kind(binding) == "spawn_entity" and binding_target_id(binding) == target_id
        for binding in bindings
    ):
        return None
    raw_params = call.get("params")
    params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
    target_calls = calls_by_target.get(item_id if requirement.target == "item_body" else target_id, [])
    fns = {str(row.get("fn") or "") for row in target_calls}
    path = f"$.runtimeProgram.calls[{call_index}]"

    def nested_param(name: str, source: Mapping[str, Any] = params) -> Any:
        value: Any = source
        for part in name.split("."):
            value = value.get(part) if isinstance(value, Mapping) else None
        return value

    if requirement.kind == "referenced_param_presence_requires_value":
        referenced_id = params.get(requirement.other_param)
        actual = nested_param(requirement.param)
        if requirement.param not in params and requirement.param in cap.params:
            from infini_local.core.runtime_authoring.technical_lowering import declared_neutral_omissions
            spec = cap.params[requirement.param]
            kind = str(entities_by_id.get(target_id, {}).get("kind") or "")
            if spec.omission_condition is None or spec.omission_condition.allows(params, kind, fns):
                actual = declared_neutral_omissions(cap.name, params).get(requirement.param)
        for row in calls_by_target.get(str(referenced_id), []):
            referenced_params = row.get("params")
            if (row.get("fn") == requirement.capability and isinstance(referenced_params, Mapping)
                    and any(nested_param(name, referenced_params) is not None for name in requirement.any_of)
                    and actual != requirement.equals):
                return ValidationIssue(f"{path}.params.{requirement.param}", "incompatible_param_variant",
                    requirement.message, (str(requirement.equals),), (str(call.get("id") or ""), str(referenced_id)))
        return None

    if requirement.kind == "enabled_trigger":
        if not any(params.get(name) is True or (type(params.get(name)) in (int, float) and params[name] > 0)
                   for name in requirement.any_of):
            return ValidationIssue(path + ".params", "empty_component", requirement.message, requirement.any_of,
                                   (str(call.get("id") or ""),))
        return None
    if requirement.kind == "ordered_params":
        minimum, maximum = nested_param(requirement.param), nested_param(requirement.other_param)
        if not requirement.ordered_values(minimum, maximum):
            return ValidationIssue(f"{path}.params.{requirement.param}", "unordered_param_range",
                requirement.message, related_ids=(str(call.get("id") or ""),))
        return None
    if requirement.kind == "present_param_requires_target_kind":
        if nested_param(requirement.param) is not None and entities_by_id.get(target_id, {}).get("kind") not in requirement.any_of:
            return ValidationIssue(f"{path}.params.{requirement.param.rsplit('.', 1)[0]}",
                "unsupported_param_variant_target_kind", requirement.message,
                related_ids=(str(call.get("id") or ""), target_id))
        return None
    if requirement.kind == "present_param_requires_param_value":
        if nested_param(requirement.param) is None:
            return None
        expected = requirement.any_of or (requirement.equals,)
        actual = nested_param(requirement.other_param)
        if requirement.other_param not in params:
            from infini_local.core.runtime_authoring.technical_lowering import declared_neutral_omissions
            omitted = declared_neutral_omissions(cap.name, params)
            if requirement.other_param in omitted:
                # Compare only an already-declared, context-valid omission;
                # keep the source absent for compiler receipts and frozen Repair.
                condition = cap.params[requirement.other_param].omission_condition
                kind = str(entities_by_id.get(target_id, {}).get("kind") or "")
                target_capabilities = (str(row.get("fn") or "") for row in calls_by_target.get(target_id, ()))
                if condition is None or condition.allows(params, kind, target_capabilities):
                    actual = omitted[requirement.other_param]
        if actual not in expected:
            return ValidationIssue(f"{path}.params.{requirement.other_param}", "incompatible_param_variant",
                requirement.message, tuple(str(value) for value in expected), (str(call.get("id") or ""),))
        return None
    if requirement.kind == "present_params_forbid_item_capability_when_active_spawn":
        selected = any(isinstance(binding.get("input"), str) and binding["input"] in ACTIVE_USE_INPUTS
                       and action_kind(binding) == "spawn_entity" and binding_target_id(binding) == target_id
                       for binding in bindings)
        conflicts = any(row.get("fn") == requirement.capability
                        and nested_param(requirement.other_param, row.get("params", {})) == requirement.equals
                        for row in calls_by_target.get(item_id, []))
        if selected and conflicts and any(nested_param(name) is not None for name in requirement.any_of):
            return ValidationIssue(f"{path}.params.{requirement.param}", "incompatible_param_variant",
                requirement.message, related_ids=(str(call.get("id") or ""), target_id))
        return None
    if requirement.kind == "present_param_forbids_capability":
        if nested_param(requirement.param) is not None and requirement.capability in fns:
            return ValidationIssue(f"{path}.params.{requirement.param.rsplit('.', 1)[0]}", "incompatible_param_variant",
                requirement.message, related_ids=(str(call.get("id") or ""), target_id))
        return None

    if requirement.kind == "param_requires_target_kind":
        if (params.get(requirement.param) == requirement.equals
                and entities_by_id.get(target_id, {}).get("kind") not in requirement.any_of):
            allowed = tuple(str(value) for value in cap.params[requirement.param].enum
                            if value != requirement.equals)
            return ValidationIssue(f"{path}.params.{requirement.param}",
                                   "unsupported_param_target_kind", requirement.message,
                                   allowed, (str(call.get("id") or ""), target_id))
        return None

    if requirement.kind in {"referenced_entity_capability_params", "referenced_entity_without_capability"}:
        referenced_id = params.get(requirement.param)
        if not isinstance(referenced_id, str) or referenced_id not in entities_by_id:
            return None  # Shape/reference ownership emits its exact missing leaf.
        if not referenced_entity_requirement_satisfied(requirement, referenced_id, calls_by_target):
            allowed = compatible_entity_reference_ids(cap, requirement.param, target_id, entities_by_id, calls_by_target)
            return ValidationIssue(f"{path}.params.{requirement.param}", "reference_requirements_unsatisfied",
                                   requirement.message, allowed, (str(call.get("id") or ""), referenced_id))
        return None
    if requirement.kind == "capability_absent":
        if requirement.param and params.get(requirement.param) != requirement.equals:
            return None
        conflicting = [row for row in target_calls if row.get("fn") in requirement.any_of]
        if conflicting:
            return ValidationIssue(path + (".params." + requirement.param if requirement.param else ""),
                                   "exclusive_component_conflict", requirement.message,
                                   requirement.any_of, tuple([str(call.get("id") or ""), *[str(row.get("id") or "") for row in conflicting]]))
        return None

    if requirement.kind in {"executed_tile_placement_reference", "unique_call_reference"}:
        reference = params.get(requirement.param)
        if not isinstance(reference, str):
            return None  # Shape owns missing or malformed leaf diagnostics.
        if requirement.kind == "unique_call_reference":
            same = [row for row in target_calls if row.get("fn") == cap.name
                    and isinstance(row.get("params"), Mapping)
                    and row["params"].get(requirement.param) == reference]
            if same and same[0].get("id") != call.get("id"):
                return ValidationIssue(path, "duplicate_placed_body_reference", requirement.message,
                                       (), (str(call.get("id") or ""),))
            return None
        def valid_placement(row: Mapping[str, Any]) -> bool:
            native = row.get("params")
            return (row.get("fn") == requirement.capability and row.get("target") == target_id
                    and isinstance(native, Mapping) and type(native.get("tileId")) is int
                    and 0 <= native["tileId"] <= 65535
                    and any(action_kind(binding) in requirement.any_of
                            and binding_target_id(binding) == target_id
                            and placement_call_id(binding) == row.get("id")
                            for binding in bindings))
        allowed = tuple(str(row["id"]) for row in target_calls if valid_placement(row))
        if reference not in allowed:
            return ValidationIssue(f"{path}.params.{requirement.param}",
                                   "placed_body_placement_reference", requirement.message,
                                   allowed, (str(call.get("id") or ""), reference))
        return None
    if requirement.kind == "capability_present":
        if requirement.param and nested_param(requirement.param) != requirement.equals:
            return None
        if requirement.capability not in fns:
            return ValidationIssue(path, "missing_capability_dependency", requirement.message, (requirement.capability,), (target_id,))
        return None
    if requirement.kind == "capability_group_present":
        # nonzero_params declares a causal effective-effect group, rather than
        # mere capability-name presence. All alternatives remain registry-owned.
        if requirement.nonzero_params and not any(
            row.get("fn") in requirement.any_of
            and (effect_cap := CAPABILITY_REGISTRY.get(str(row.get("fn") or ""))) is not None
            and isinstance((effect_params := row.get("params")), Mapping)
            and (not cap.effect_groupable or effect_params.get("effectGroupId") == params.get("effectGroupId"))
            and effect_cap.has_non_neutral_effect(effect_params)
            for row in target_calls
        ):
            return ValidationIssue(
                f"{path}.params", "empty_component", requirement.message,
                tuple(f"{name} > 0" for name in requirement.nonzero_params),
            )
        if not fns.intersection(requirement.any_of):
            return ValidationIssue(path, "missing_capability_group", requirement.message, requirement.any_of, (target_id,))
        return None
    if requirement.kind == "primary_target":
        if target_id != primary_entity_id:
            return ValidationIssue(path + ".target", "wrong_target_kind", requirement.message,
                                   (primary_entity_id,), (str(call.get("id") or ""), target_id))
        return None
    if requirement.kind == "capability_param_absent":
        for row in target_calls:
            if row.get("fn") == requirement.capability and nested_param(requirement.param, row.get("params", {})) is not None:
                return ValidationIssue(path, "exclusive_component_conflict", requirement.message,
                                       related_ids=(str(call.get("id") or ""), str(row.get("id") or "")))
        return None
    if requirement.kind == "item_capability_param":
        dependency = next((row for row in target_calls if row.get("fn") == requirement.capability), None)
        raw_dependency_params = (dependency or {}).get("params")
        dependency_params: Mapping[str, Any] = raw_dependency_params if isinstance(raw_dependency_params, Mapping) else {}
        actual = dependency_params.get(requirement.param)
        expected = requirement.equals
        spec = CAPABILITY_REGISTRY[requirement.capability].params[requirement.param]
        if requirement.any_of:
            valid = any(type(actual) is type(value) and actual == value for value in requirement.any_of)
        elif spec.structured and isinstance(expected, Mapping):
            valid = not strict_schema_errors(actual, spec.schema())
            if valid:
                try:
                    updates = target_updates_per_tick(calls or [], target_id) if spec.requires_update_context else None
                    actual_rows = tuple((r.wire_path, r.value) for r in spec.projected_fields(actual, requirement.param, updates_per_tick=updates))
                    expected_rows = tuple((r.wire_path, r.value) for r in spec.projected_fields(expected, requirement.param, updates_per_tick=updates))
                    valid = len(actual_rows) == len(expected_rows) and all(
                        a[0] == b[0] and a[1] == b[1] and type(a[1]) is not bool for a, b in zip(actual_rows, expected_rows))
                except ValueError:
                    valid = False
        elif spec.kind == "number":
            valid = type(actual) in (int, float) and actual == expected
        else:
            valid = type(actual) is type(expected) and actual == expected
        valid = valid or (requirement.allow_absent and requirement.param not in dependency_params)
        if dependency is None or not valid:
            owner_id = item_id if requirement.target == "item_body" else target_id
            if requirement.any_of:
                if dependency is None:
                    return ValidationIssue(path, "missing_capability_dependency", requirement.message,
                                           (requirement.capability,), (owner_id,))
                dependency_index = next((index for index, row in enumerate(calls or []) if row is dependency), call_index)
                return ValidationIssue(f"$.runtimeProgram.calls[{dependency_index}].params.{requirement.param}",
                                       "missing_dependency_param", requirement.message, requirement.any_of,
                                       (str(dependency.get("id") or ""), owner_id))
            encoded = json.dumps(expected, separators=(",", ":"))
            return ValidationIssue(path, "missing_item_capability_param", requirement.message,
                                   (f"{requirement.capability}.{requirement.param}={encoded}",), (owner_id,))
        return None
    if requirement.kind == "at_least_one_param_nonnegative":
        names = requirement.param.split("|")
        if not any(_numeric_param(params, name, -1) >= 0 for name in names):
            return ValidationIssue(f"{path}.params", "empty_component", requirement.message, tuple(f"{name} >= 0" for name in names))
        return None
    if requirement.kind == "conditional_param_values":
        if params.get(requirement.param) == requirement.equals and params.get(requirement.other_param) not in requirement.any_of:
            return ValidationIssue(f"{path}.params.{requirement.other_param}", "incompatible_param_variant", requirement.message, requirement.any_of)
        return None
    if requirement.kind == "param_branch_fields":
        if params.get(requirement.param) != requirement.equals:
            return None
        missing = next((name for name in requirement.any_of if name not in params), None)
        if missing:
            return ValidationIssue(f"{path}.params.{missing}", "missing_dependency_param", requirement.message, (missing,))
        fields = {name for r in cap.requirements if r.kind == "param_branch_fields" for name in r.any_of}
        forbidden = next((name for name in fields if name in params and name not in requirement.any_of), None)
        if forbidden:
            return ValidationIssue(f"{path}.params.{forbidden}", "incompatible_param_variant", requirement.message)
        return None
    if requirement.kind == "timing_pair_or_window":
        pair = (requirement.param, requirement.other_param)
        missing = next((name for name in pair if name not in params), None)
        if missing and any(name in params for name in pair):
            return ValidationIssue(f"{path}.params.{missing}", "missing_dependency_param", requirement.message, (missing,))
        if missing and requirement.any_of[0] not in params:
            return ValidationIssue(f"{path}.params.{requirement.any_of[0]}", "missing_dependency_param", requirement.message, requirement.any_of)
        return None
    if requirement.kind == "conditional_param":
        raw_mode = params.get(requirement.param)
        mode = raw_mode if isinstance(raw_mode, str) else ""
        for encoded in requirement.any_of:
            expected, required_param = encoded.split(":", 1)
            if mode == expected and required_param not in params:
                return ValidationIssue(f"{path}.params.{required_param}", "missing_dependency_param", requirement.message, (required_param,))
        return None
    if requirement.kind == "param_only_when":
        selector = params.get(requirement.other_param)
        if (requirement.param in params and selector in cap.params[requirement.other_param].enum
                and selector != requirement.equals):
            return ValidationIssue(f"{path}.params.{requirement.param}", "incompatible_param_variant",
                                   requirement.message, related_ids=(str(call.get("id") or ""),))
        return None
    if requirement.kind == "conditional_omission":
        condition = cap.params[requirement.param].omission_condition
        kind = str(entities_by_id.get(target_id, {}).get("kind") or "")
        target_capabilities = (str(row.get("fn") or "") for row in calls_by_target.get(target_id, ()))
        if requirement.param not in params and (condition is None or not condition.allows(params, kind, target_capabilities)):
            return ValidationIssue(f"{path}.params.{requirement.param}", "missing_dependency_param", requirement.message, (requirement.param,))
        return None
    if requirement.kind == "binding_input_present":
        required_target = item_id if requirement.target == "item_body" else target_id
        if not any(
            str(binding.get("input") or "") in requirement.any_of
            and binding_target_id(binding) == required_target
            for binding in bindings
        ):
            allowed = tuple(f"binding(input={input_name})" for input_name in requirement.any_of)
            return ValidationIssue(
                path,
                "missing_binding_dependency",
                requirement.message,
                allowed,
                (required_target,) if required_target else (),
            )
        return None
    if requirement.kind == "binding_action_present":
        required_target = item_id if requirement.target == "item_body" else target_id
        group_id = params.get("effectGroupId") if cap.effect_groupable else None
        held = (cap.name == "apply_generated_buff_on_use" and isinstance(group_id, str)
                and any(row.get("fn") in {"refresh_generated_effect_group_while_held", "apply_generated_buff_on_event"}
                        and isinstance(row.get("params"), Mapping)
                        and row["params"].get("effectGroupId") == group_id for row in target_calls))
        if not any(
            action_kind(binding) in requirement.any_of
            and binding_target_id(binding) == required_target
            and (not cap.effect_groupable or binding_action(binding).get("effectGroupId") == group_id)
            for binding in bindings
        ) and not held:
            return ValidationIssue(
                path, "missing_binding_dependency", requirement.message,
                requirement.any_of, (str(call.get("id") or ""), required_target),
            )
        return None
    if requirement.kind == "binding_tuple_present":
        required_target = (
            item_id
            if requirement.target == "item_body"
            else ("" if requirement.target == "any_entity" else target_id)
        )
        allowed_tuples: list[tuple[str, str, bool | None]] = []
        for value in requirement.any_of:
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
            allowed_tuples.append((parts[0], parts[1], required_contact))
        if not any(
            any(
                str(binding.get("input") or "") == input_name
                and action_kind(binding) == required_action
                and (required_contact is None or contact_damage(binding) is required_contact)
                for input_name, required_action, required_contact in allowed_tuples
            )
            and (not required_target or binding_target_id(binding) == required_target)
            for binding in bindings
        ):
            return ValidationIssue(
                path, "missing_binding_dependency", requirement.message,
                requirement.any_of, (str(call.get("id") or ""), required_target),
            )
        return None
    if requirement.kind == "binding_action_reference":
        call_id = str(call.get("id") or "")
        required_target = item_id if requirement.target == "item_body" else target_id
        matching = [
            binding
            for binding in bindings
            if action_kind(binding) in requirement.any_of
            and binding_target_id(binding) == required_target
            and placement_call_id(binding) == call_id
        ]
        if len(matching) != 1:
            return ValidationIssue(
                path,
                "missing_binding_dependency",
                requirement.message,
                tuple(f"binding usePolicy action {name} references call {call_id}" for name in requirement.any_of),
                (call_id, required_target),
            )
        return None
    if requirement.kind == "at_least_one_param_nonzero":
        declared_cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if declared_cap is None or not (
            any(name in params and params[name] != declared_cap.params[name].neutral
                for name in requirement.nonzero_params)
            or any(
                row.get("fn") in requirement.any_of
                and isinstance(row.get("params"), Mapping)
                and row["params"].get("phase") == "equipped"
                and _numeric_param(row["params"], "bonusPercent", 0) != 0
                for row in target_calls
            )
        ):
            return ValidationIssue(
                f"{path}.params",
                "inert_component",
                requirement.message,
                ("set one non-zero effect", "remove the call"),
            )
        return None
    if requirement.kind == "nonneutral_params_require_param":
        declared_cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        has_bonus = declared_cap is not None and any(
            name in params and any(value != leaf.neutral
                                   for _, leaf, value in declared_cap.params[name].leaf_values(params[name], name))
            for name in requirement.nonzero_params
        )
        if has_bonus and not params.get(requirement.param):
            return ValidationIssue(
                f"{path}.params.{requirement.param}", "missing_set_key",
                requirement.message, ("author a non-empty shared setKey", "remove the set bonus"),
            )
        return None
    if requirement.kind == "nonneutral_params_require_exact_param":
        declared_cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        has_bonus = declared_cap is not None and any(
            name in params and any(value != leaf.neutral
                                   for _, leaf, value in declared_cap.params[name].leaf_values(params[name], name))
            for name in requirement.nonzero_params
        )
        if has_bonus and params.get(requirement.param) != requirement.equals:
            return ValidationIssue(
                f"{path}.params.{requirement.param}", "set_bonus_head_only",
                requirement.message, ("author the set bonus on the head piece", "remove the set bonus"),
            )
        return None
    if requirement.kind == "positive_param_requires_param":
        if any(_numeric_param(params, name, 0) > 0 for name in requirement.nonzero_params) and not params.get(requirement.param):
            return ValidationIssue(
                f"{path}.params.{requirement.param}", "missing_light_color",
                requirement.message, ("author lightColor", "remove positive lightStrength"),
            )
        return None
    if requirement.kind == "non_neutral_param":
        if not cap.has_non_neutral_effect(params):
            return ValidationIssue(f"{path}.params", "inert_component", requirement.message, ("set one non-neutral effect", "remove the call"))
        return None
    if requirement.kind == "event_available":
        event = authored_event(params)
        kind = str(entities_by_id.get(target_id, {}).get("kind") or "")
        when = params.get("when")
        selected_bindings = bindings
        if event == "on_use" and isinstance(when, Mapping) and when.get("useInput") in ("primary_use", "alternate_use"):
            selected_bindings = [binding for binding in bindings if binding.get("input") == when["useInput"]]
        ok, allowed, message = _event_available(
            event=event,
            target_id=target_id,
            kind=kind,
            calls_by_target=calls_by_target,
            bindings=selected_bindings,
        )
        if not ok:
            return ValidationIssue(f"{path}.params.{requirement.param}", "event_not_emitted", message, allowed, (target_id,))
        return None
    return ValidationIssue(path, "unknown_registry_requirement", f"Registry requirement kind '{requirement.kind}' has no validator implementation.")


def _validate_runtime_program_semantics(document: Mapping[str, Any]) -> dict[str, Any]:
    """Run the one canonical graph/semantic pass over a traversable shell.

    Every finite requirement evaluator is type-safe: strict shape errors and all
    still-readable graph blockers are aggregated without inferring gameplay.
    """

    from infini_local.core.runtime_authoring.technical_lowering import _exact_mechanical_view  # pyright: ignore[reportPrivateUsage] -- canonical private lowering, not public admission
    literal_program = document.get("runtimeProgram", {})
    document = _exact_mechanical_view(document)
    issues: list[ValidationIssue] = []
    program_raw = document.get("runtimeProgram")
    program: Mapping[str, Any] = program_raw if isinstance(program_raw, Mapping) else {}
    entities = _rows(program.get("entities"))
    bindings = _rows(program.get("bindings"))
    calls = _rows(program.get("calls"))

    entities_by_id: dict[str, dict[str, Any]] = {}
    bindings_by_id: dict[str, dict[str, Any]] = {}
    calls_by_id: dict[str, dict[str, Any]] = {}
    global_ids: dict[str, str] = {}

    def register(row: Mapping[str, Any], *, namespace: str, path: str, target: dict[str, dict[str, Any]]) -> None:
        row_id = str(row.get("id") or "")
        if row_id in target:
            issues.append(ValidationIssue(path, "duplicate_id", f"Duplicate {namespace} id '{row_id}'.", related_ids=(row_id,)))
        else:
            target[row_id] = dict(row)
        if row_id in global_ids:
            issues.append(ValidationIssue(path, "ambiguous_global_id", f"Id '{row_id}' is already used by {global_ids[row_id]}; authored ids are globally unique.", related_ids=(row_id,)))
        else:
            global_ids[row_id] = namespace

    for index, entity in enumerate(entities):
        register(entity, namespace="entity", path=f"$.runtimeProgram.entities[{index}].id", target=entities_by_id)
    for index, binding in enumerate(bindings):
        register(binding, namespace="binding", path=f"$.runtimeProgram.bindings[{index}].id", target=bindings_by_id)
    for index, call in enumerate(calls):
        register(call, namespace="call", path=f"$.runtimeProgram.calls[{index}].id", target=calls_by_id)
    item_entities = [row for row in entities if row.get("kind") == "item_body"]
    if len(item_entities) != 1:
        issues.append(ValidationIssue("$.runtimeProgram.entities", "item_body_count", f"Exactly one item_body is required; found {len(item_entities)}.", ("add one item_body", "remove extras")))
    item_id = str(item_entities[0].get("id") or "") if len(item_entities) == 1 else ""
    body_resolved = len(item_entities) == 1 and isinstance(item_entities[0].get("id"), str) and bool(re.fullmatch(r"[a-z][a-z0-9_]{0,47}", item_id))

    primary_issues, primary_entity_id = _primary_entity_issues(entities_by_id, program)
    issues.extend(primary_issues)

    issues.extend(_exclusive_input_issues(bindings))
    binding_spawn_roots: set[str] = set()
    for index, binding in enumerate(bindings):
        binding_id = str(binding.get("id") or "")
        target_id = binding_target_id(binding)
        input_name = str(binding.get("input") or "")
        action_name = action_kind(binding)
        entity = entities_by_id.get(target_id)
        if not action_name:
            continue  # Shape owns an undecided selector; never invent a target dependency.
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        action_spec = BINDING_ACTION_REGISTRY.get(action_name)
        action_path = f"$.runtimeProgram.bindings[{index}].action"
        if not body_resolved and action_spec is not None and action_spec.target_kinds == ("item_body",):
            continue  # declaration diagnostics own this unresolved dependency
        if entity is None:
            issues.append(ValidationIssue(f"{action_path}.targetId", "missing_entity_reference", f"Binding '{binding_id}' references missing entity '{target_id}'.", tuple(entities_by_id), (binding_id, target_id)))
            continue
        if input_spec is None or action_spec is None:
            continue  # strict schema already reports this case
        if action_name not in input_spec.allowed_actions or input_name not in action_spec.allowed_inputs:
            issues.append(ValidationIssue(
                action_path,
                "unsupported_input_action",
                f"{input_name} cannot run {action_name}.",
                input_spec.allowed_actions,
                (binding_id,),
            ))
        kind = str(entity.get("kind") or "")
        if kind not in action_spec.target_kinds:
            issues.append(ValidationIssue(
                f"{action_path}.targetId",
                "wrong_binding_target_kind",
                f"{action_name} accepts {', '.join(action_spec.target_kinds)}, not {kind}.",
                action_spec.target_kinds,
                (target_id,),
            ))
        if action_name == "spawn_entity":
            kind_spec = ENTITY_KIND_REGISTRY.get(kind)
            if kind_spec is None:
                continue  # strict shape owns unknown entity kinds
            if not kind_spec.spawnable_by_binding:
                issues.append(ValidationIssue(
                    f"{action_path}.targetId",
                    "entity_not_binding_spawnable",
                    f"{kind} must be reached through an event/controller, not a direct binding.",
                    tuple(name for name, row in ENTITY_KIND_REGISTRY.items() if row.spawnable_by_binding),
                    (target_id,),
                ))
            else:
                binding_spawn_roots.add(target_id)

    hidden_item_spawn_target = _hidden_item_spawn_primary_target(program, item_id)
    if (
        primary_entity_id == item_id
        and hidden_item_spawn_target
        and hidden_item_spawn_target in entities_by_id
    ):
        issues.append(ValidationIssue(
            PRIMARY_ENTITY_JSON_PATH,
            "hidden_item_primary_requires_spawn_target",
            "The item use graphic is hidden and no active binding enables item-body contact; "
            f"the sole explicit spawn target '{hidden_item_spawn_target}' must own lifecycle/held representation.",
            (hidden_item_spawn_target,),
            (hidden_item_spawn_target,),
        ))

    calls_by_target = _calls_by_target(program)
    seen_single: set[tuple[str, str, str | None]] = set()
    exclusive_components: dict[tuple[str, str, str | None], tuple[int, str]] = {}
    event_edges: dict[str, set[str]] = {entity_id: set() for entity_id in entities_by_id}
    event_referenced_entities: set[str] = set()
    event_spawn_budget = 0
    input_spawn_budgets = {"primary_use": 0, "alternate_use": 0}
    event_action_counts: dict[str, int] = {}

    for index, call in enumerate(calls):
        call_id = str(call.get("id") or "")
        fn = str(call.get("fn") or "")
        target_id = str(call.get("target") or "")
        raw_params = call.get("params")
        params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
        cap = CAPABILITY_REGISTRY.get(fn)
        entity = entities_by_id.get(target_id)
        if cap is None or not cap.author_visible:
            registered_names = tuple(name for name, spec in CAPABILITY_REGISTRY.items() if spec.author_visible)
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].fn", "unknown_capability", f"Unknown capability '{fn}'.", registered_names, (call_id,)))
            continue
        # A closed params union can hide its undecided selector behind a
        # generic oneOf error. Report the exact leaf so Repair never thaws
        # valid siblings while choosing the branch.
        branch_selectors = {r.param for r in cap.requirements if r.kind == "param_branch_fields"}
        for selector in sorted(branch_selectors):
            spec = cap.params[selector]
            if params.get(selector) not in spec.enum:
                issues.append(ValidationIssue(
                    f"$.runtimeProgram.calls[{index}].params.{selector}",
                    "incompatible_param_variant", "Choose an explicit registered parameter branch.", spec.enum,
                    (call_id,),
                ))
        if not body_resolved and cap.target_kinds == ("item_body",):
            continue  # no writable synthetic target for an implied body reference
        if entity is None:
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].target", "missing_entity_reference", f"Call '{call_id}' references missing entity '{target_id}'.", tuple(entities_by_id), (call_id, target_id)))
            continue
        kind = str(entity.get("kind") or "")
        if kind not in cap.target_kinds:
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].target", "wrong_target_kind", f"{fn} cannot target {kind}.", cap.target_kinds, (call_id, target_id)))
        key = (target_id, fn, params.get("effectGroupId") if cap.effect_groupable and isinstance(params.get("effectGroupId"), str) else None)
        if fn == "require_use_condition":
            selector = params.get("input")
            matching = [row for row in calls[:index] if row.get("fn") == fn
                        and isinstance(row.get("params"), Mapping) and row["params"].get("input") == selector]
            if matching:
                issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}]", "duplicate_single_component", "Each active input may have only one use condition.", related_ids=(call_id,)))
            if isinstance(selector, str) and selector in {"primary_use", "alternate_use"} and not any(row.get("input") == selector for row in bindings):
                issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].params.input", "incompatible_param_variant", "Use condition must select an existing active input.", related_ids=(call_id,)))
        if cap.multiplicity == "single_per_target" and key in seen_single:
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}]", "duplicate_single_component", f"{fn} may appear only once on '{target_id}'.", ("merge into one call", "delete duplicate"), (target_id, call_id)))
        seen_single.add(key)
        if cap.exclusive_group:
            # Multiplicity and exclusivity share the same registry-declared
            # owner: target plus explicit effect identity, never a semantic lane.
            group_key = (target_id, cap.exclusive_group, key[2])
            if group_key in exclusive_components:
                previous_index, previous_id = exclusive_components[group_key]
                issues.append(ValidationIssue(
                    f"$.runtimeProgram.calls[{index}]",
                    "exclusive_component_conflict",
                    f"calls[{previous_index}] ('{previous_id}') and calls[{index}] ('{call_id}') both occupy exclusive component group '{cap.exclusive_group}' on '{target_id}'.",
                    ("keep one", "split behaviour into separate entities"),
                    (previous_id, call_id, target_id),
                ))
            else:
                exclusive_components[group_key] = (index, call_id)

        for param_name, param_spec in cap.params.items():
            if param_name in params:
                for leaf_name, leaf_spec, leaf_value in param_spec.leaf_values(params[param_name], param_name):
                    try:
                        updates = target_updates_per_tick(calls, target_id) if leaf_spec.wire_updates_power else None
                    except ValueError:
                        # The missing/invalid/ambiguous collision clock owns the
                        # diagnostic. Unknown projection context does not prove
                        # another valid authored value is invalid or editable.
                        continue
                    try:
                        consumer_error = leaf_spec.consumer_value_error(leaf_value, updates_per_tick=updates)
                    except ValueError as exc:
                        consumer_error = str(exc)
                    if consumer_error is not None:
                        issues.append(ValidationIssue(
                            f"$.runtimeProgram.calls[{index}].params.{leaf_name}", "consumer_representability", consumer_error,
                            ("author a non-neutral value representable by the declared consumer or exact neutral",),
                        ))
            ref = param_spec.reference
            if ref is None or ref.namespace != "entity" or param_name not in params:
                continue
            referenced_id = str(params.get(param_name) or "")
            referenced = entities_by_id.get(referenced_id) if ref.namespace == "entity" else None
            ref_path = f"$.runtimeProgram.calls[{index}].params.{param_name}"
            if referenced is None:
                issues.append(ValidationIssue(ref_path, "missing_entity_reference", f"{fn}.{param_name} references missing entity '{referenced_id}'.", tuple(entities_by_id), (target_id, referenced_id)))
                continue
            referenced_kind = str(referenced.get("kind") or "")
            if ref.target_kinds and referenced_kind not in ref.target_kinds:
                issues.append(ValidationIssue(ref_path, "wrong_reference_target_kind", f"{fn}.{param_name} cannot reference {referenced_kind}.", ref.target_kinds, (referenced_id,)))
            if not ref.allow_self and referenced_id == target_id:
                issues.append(ValidationIssue(ref_path, "self_reference_forbidden", f"{fn}.{param_name} cannot reference its own target entity.", tuple(entity_id for entity_id in entities_by_id if entity_id != target_id), (target_id,)))
            if ref.graph_edge:
                event_edges.setdefault(target_id, set()).add(referenced_id)
                event_referenced_entities.add(referenced_id)

        if cap.category == "event":
            # One event capability lowers to one native RuntimeEventActionSpec.
            # Report only overflow calls so frozen-first Repair never thaws the first 16.
            if entity is not None:
                event_action_counts[target_id] = event_action_counts.get(target_id, 0) + 1
                if event_action_counts[target_id] > MAX_RUNTIME_EVENTS_PER_ENTITY:
                    issues.append(ValidationIssue(
                        f"$.runtimeProgram.calls[{index}]", "entity_event_budget",
                        f"Entity '{target_id}' has more than {MAX_RUNTIME_EVENTS_PER_ENTITY} event actions; "
                        "the native DTO rejects this program.",
                        (f"at most {MAX_RUNTIME_EVENTS_PER_ENTITY} event calls per entity",),
                        (call_id, target_id),
                    ))
            event = authored_event(params)
            if event not in cap.allowed_events:
                issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].params.when", "capability_event_incompatible", f"{fn} does not accept {event}.", cap.allowed_events, (call_id,)))

        if cap.activation_spawn_count_param:
            raw_spawn_count = params.get(cap.activation_spawn_count_param)
            if isinstance(raw_spawn_count, int) and not isinstance(raw_spawn_count, bool) and raw_spawn_count >= 0:
                when = params.get("when")
                use_input = when.get("useInput") if isinstance(when, Mapping) else None
                # Only these item-use lanes are mutually exclusive per admission.
                # Descendant and other event counts remain conservatively shared.
                if (target_id == item_id and authored_event(params) == "on_use"
                        and isinstance(use_input, str) and use_input in input_spawn_budgets):
                    input_spawn_budgets[use_input] += raw_spawn_count
                else:
                    event_spawn_budget += raw_spawn_count

    seen_equipment_damage: dict[tuple[str, str, str], str] = {}
    for index, call in enumerate(calls):
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if cap is None:
            continue
        if cap.name == "add_equipment_damage_bonus":
            raw_bonus_params = call.get("params")
            bonus_params: Mapping[str, Any] = raw_bonus_params if isinstance(raw_bonus_params, Mapping) else {}
            target_id = str(call.get("target") or "")
            configurations = [row for row in calls_by_target.get(target_id, [])
                              if row.get("fn") in {"configure_accessory", "configure_armor"}]
            if len(configurations) != 1:
                issues.append(ValidationIssue(
                    f"$.runtimeProgram.calls[{index}]", "equipment_scope_conflict",
                    "Select exactly one explicit accessory or armor configuration for this class bonus.",
                    ("configure_accessory", "configure_armor"), (str(call.get("id") or ""), target_id),
                ))
            elif bonus_params.get("phase") == "matching_armor_set":
                config = configurations[0]
                config_index = calls.index(config)
                config_id = str(config.get("id") or "")
                raw_armor_params = config.get("params")
                armor_params: Mapping[str, Any] = raw_armor_params if isinstance(raw_armor_params, Mapping) else {}
                if config.get("fn") != "configure_armor":
                    issues.append(ValidationIssue(
                        f"$.runtimeProgram.calls[{index}].params.phase", "equipment_scope_conflict",
                        "A matching armor set phase cannot target an accessory.",
                        ("equipped",), (str(call.get("id") or ""), target_id),
                    ))
                elif not armor_params.get("setKey"):
                    issues.append(ValidationIssue(
                        f"$.runtimeProgram.calls[{config_index}].params.setKey", "missing_set_key",
                        "Matching armor set damage requires configured armor with a nonempty setKey.",
                        ("author an exact matching setKey",), (config_id, str(call.get("id") or ""), target_id),
                    ))
                elif armor_params.get("slot") != "head":
                    issues.append(ValidationIssue(
                        f"$.runtimeProgram.calls[{config_index}].params.slot", "set_bonus_head_only",
                        "Only the head piece executes a matching three-piece armor set bonus.",
                        ("configure_armor(slot=head)", "remove only the invalid class bonus call"),
                        (config_id, str(call.get("id") or ""), target_id),
                    ))
            selector = (target_id, str(bonus_params.get("phase") or ""), str(bonus_params.get("damageClass") or ""))
            if selector in seen_equipment_damage:
                issues.append(ValidationIssue(
                    f"$.runtimeProgram.calls[{index}]", "duplicate_equipment_damage_selector",
                    "The same equipment phase and damage class may be authored only once.",
                    ("merge the exact modifier into one call",),
                    (seen_equipment_damage[selector], str(call.get("id") or ""), target_id),
                ))
            seen_equipment_damage[selector] = str(call.get("id") or "")
        for requirement in cap.requirements:
            issue = _validate_requirement(
                requirement,
                call=call,
                call_index=index,
                cap=cap,
                item_id=item_id,
                calls_by_target=calls_by_target,
                entities_by_id=entities_by_id,
                bindings=bindings,
                primary_entity_id=primary_entity_id,
                calls=calls,
            )
            if issue is not None:
                issues.append(issue)

    for entity_id, entity in entities_by_id.items():
        kind = str(entity.get("kind") or "")
        kind_spec = ENTITY_KIND_REGISTRY.get(kind)
        if kind_spec is None:
            continue  # strict shape owns unknown entity kinds
        if kind == "item_body" and not body_resolved:
            continue
        target_calls = calls_by_target.get(entity_id, [])
        fns = {str(row.get("fn") or "") for row in target_calls}
        for required in kind_spec.required_components:
            if required not in fns:
                issues.append(ValidationIssue(
                    "$.runtimeProgram.calls",
                    "missing_required_component",
                    f"{kind} '{entity_id}' requires {required}; no semantic default is inserted.",
                    (required,),
                    (entity_id,),
                ))
        if kind == "item_body":
            continue
        reachable = entity_id in binding_spawn_roots or entity_id in event_referenced_entities
        if not reachable:
            issues.append(ValidationIssue("$.runtimeProgram.entities", "unreachable_entity", f"Entity '{entity_id}' is not reached by a binding or typed entity reference.", ("bind it", "reference it", "delete it"), (entity_id,)))
        motion_rows = [{**row, "_path": f"$.runtimeProgram.calls[{calls.index(row)}].params"}
                       for row in target_calls if row.get("fn") in CAPABILITY_REGISTRY]
        active = any(isinstance(binding.get("input"), str) and binding.get("input") in ACTIVE_USE_INPUTS and action_kind(binding) == "spawn_entity"
                     and binding_target_id(binding) == entity_id for binding in bindings)
        item_use = next((row.get("params", {}) for row in calls_by_target.get(item_id, [])
                         if row.get("fn") == "configure_item_use"), {})
        item_use = item_use if isinstance(item_use, Mapping) else {}
        issues.extend(_motion_composition_issues(motion_rows, wire=False, active=active,
                      channel=item_use.get("channel") is True, primary=entity_id == primary_entity_id,
                      hand_pose=item_use.get("handPose"), item_owner_id=item_id))
        position_drivers = [CAPABILITY_REGISTRY[fn] for fn in fns if fn in CAPABILITY_REGISTRY and CAPABILITY_REGISTRY[fn].position_ownership != "none"]
        if kind_spec.requires_position_driver and not position_drivers:
            allowed = tuple(sorted(name for name, row in CAPABILITY_REGISTRY.items() if row.author_visible and kind in row.target_kinds and row.position_ownership != "none"))
            issues.append(ValidationIssue("$.runtimeProgram.calls", "missing_movement_component", f"{kind} '{entity_id}' requires explicit movement/controller; none is inferred.", allowed, (entity_id,)))
        if kind in {"stationary_projectile", "temporary_helper", "field"}:
            meaningful = any(CAPABILITY_REGISTRY[fn].meaningful_for_stationary for fn in fns if fn in CAPABILITY_REGISTRY)
            if not meaningful:
                allowed = tuple(sorted(
                    cap.name
                    for cap in CAPABILITY_REGISTRY.values()
                    if cap.author_visible and kind in cap.target_kinds and cap.meaningful_for_stationary
                ))
                issues.append(ValidationIssue(
                    "$.runtimeProgram.calls",
                    "inert_stationary_entity",
                    f"Stationary entity '{entity_id}' has no executable damage, targeting, event action, or light component.",
                    allowed,
                    (entity_id,),
                ))

    item_calls = calls_by_target.get(item_id, []) if item_id else []
    item_fns = {str(row.get("fn") or "") for row in item_calls}
    effect_groups: dict[str, list[dict[str, Any]]] = {}
    for row in item_calls:
        declared = CAPABILITY_REGISTRY.get(str(row.get("fn") or ""))
        group_id = row.get("params", {}).get("effectGroupId") if isinstance(row.get("params"), Mapping) else None
        if declared is not None and declared.effect_groupable and isinstance(group_id, str):
            effect_groups.setdefault(group_id, []).append(row)
    valid_held_groups = tuple(group_id for group_id, rows in effect_groups.items()
                             if len(rows) == 1 and rows[0].get("fn") == "apply_generated_buff_on_use")
    for row in item_calls:
        if row.get("fn") in {"refresh_generated_effect_group_while_held", "apply_generated_buff_on_event"}:
            group_id = row.get("params", {}).get("effectGroupId") if isinstance(row.get("params"), Mapping) else None
            if isinstance(group_id, str) and group_id not in valid_held_groups:
                issues.append(ValidationIssue(
                    f"$.runtimeProgram.calls[{calls.index(row)}].params.effectGroupId",
                    "invalid_reaction_effect_group" if row.get("fn") == "apply_generated_buff_on_event" else "invalid_held_effect_group",
                    "This consumer requires exactly one named generated utility buff and no heal/native buff/mobility components.",
                    valid_held_groups, (str(row.get("id") or ""),),
                ))
    for index, binding in enumerate(bindings):
        input_name = str(binding.get("input") or "")
        action_name = action_kind(binding)
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        action_spec = BINDING_ACTION_REGISTRY.get(action_name)
        if not body_resolved and action_spec is not None and action_spec.target_kinds == ("item_body",):
            continue
        group_id = binding_action(binding).get("effectGroupId")
        if action_name == "apply_item_effects":
            selected_calls = effect_groups.get(group_id, []) if isinstance(group_id, str) else [
                row for row in item_calls if isinstance(row.get("params"), Mapping) and "effectGroupId" not in row["params"]]
            selected_fns = {str(row.get("fn") or "") for row in selected_calls}
            if isinstance(group_id, str) and group_id not in effect_groups:
                issues.append(ValidationIssue(f"$.runtimeProgram.bindings[{index}].action.effectGroupId",
                    "missing_effect_group", "Binding must select an exact declared effect group.", tuple(effect_groups), (str(binding.get("id") or ""),)))
        else:
            selected_fns = item_fns
        dependencies = (
            ("input", input_spec.required_item_capabilities_any_of if input_spec is not None else ()),
            ("action.kind", action_spec.required_item_capabilities_any_of if action_spec is not None else ()),
        )
        for source, required_any_of in dependencies:
            if required_any_of and not selected_fns.intersection(required_any_of) and not (action_name == "apply_item_effects" and isinstance(group_id, str)):
                issues.append(ValidationIssue(
                    f"$.runtimeProgram.bindings[{index}].{source}",
                    "binding_dependency",
                    f"{source} '{input_name if source == 'input' else action_name}' requires at least one declared item capability.",
                    required_any_of,
                    (item_id,) if item_id else (),
                ))
        if action_name != "place_item":
            continue
        if stack_cost(binding) != 1:
            issues.append(ValidationIssue(
                f"$.runtimeProgram.bindings[{index}].stackCost",
                "place_item_without_stack_cost",
                f"place_item on {input_name} requires stackCost=1 in the same usePolicy.",
                ("1",),
                (str(binding.get("id") or ""),),
            ))
        reusable_active_uses = [
            row for row in bindings
            if str(row.get("input") or "") in {"primary_use", "alternate_use"}
            and action_kind(row) in {"spawn_entity", "use_item_body"}
            and may_retain_stack(row)
        ]
        if reusable_active_uses:
            # Durable hybrid: the item is both a reusable tool/weapon and a placeable.
            # Its inventory stack must stay at one physical unit - placement escrows the
            # whole item and breaking the tile returns it. A larger stack would let one
            # alternate click lock an arbitrary number of weapon instances in the world.
            for call in calls:
                if str(call.get("fn") or "") != "configure_item_stats":
                    continue
                params = call.get("params") if isinstance(call.get("params"), Mapping) else {}
                max_stack = params.get("maxStack")
                if max_stack != 1:
                    issues.append(ValidationIssue(
                        f"$.runtimeProgram.calls[{calls.index(call)}].params.maxStack",
                        "hybrid_placeable_max_stack",
                        "A durable placeable hybrid must hold exactly one unit: set configure_item_stats maxStack to 1.",
                        ("1",),
                        (str(call.get("id") or ""),),
                    ))
        referenced_call_id = placement_call_id(binding)
        referenced_call = calls_by_id.get(referenced_call_id)
        # An invalid binding target is diagnosed at targetId. It does not
        # invalidate an otherwise accepted placement-call identity for Repair.
        if (
            referenced_call is None
            or str(referenced_call.get("fn") or "") not in {"configure_tile_placement", "configure_wall_placement"}
            or (binding_target_id(binding) == item_id
                and str(referenced_call.get("target") or "") != binding_target_id(binding))
        ):
            issues.append(ValidationIssue(
                f"$.runtimeProgram.bindings[{index}].action.placementCallId",
                "missing_binding_dependency",
                "place_item must reference one configure_tile_placement or configure_wall_placement call on the same item target.",
                tuple(
                    str(row.get("id") or "")
                    for row in item_calls
                    if str(row.get("fn") or "") in {"configure_tile_placement", "configure_wall_placement"}
                ),
                (str(binding.get("id") or ""), referenced_call_id),
            ))

    place_bindings = [binding for binding in bindings if action_kind(binding) == "place_item"]
    active_non_place_bindings = [
        binding
        for binding in bindings
        if str(binding.get("input") or "") in ACTIVE_USE_INPUTS
        and action_kind(binding) != "place_item"
    ]
    placeable_roles_valid, placeable_role_message = placeable_input_contract(bindings)
    if place_bindings and not placeable_roles_valid:
        issues.append(ValidationIssue(
            "$.runtimeProgram.bindings",
            "dual_use_placeable_input_contract",
            placeable_role_message,
            ("primary_use", "alternate_use"),
            tuple(
                str(row.get("id") or "")
                for row in (*place_bindings, *active_non_place_bindings)
                if str(row.get("id") or "")
            ),
        ))

    cycle = _graph_cycle(event_edges)
    if cycle:
        issues.append(ValidationIssue("$.runtimeProgram.calls", "illegal_event_cycle", "Runtime entity graph contains a cycle: " + " -> ".join(cycle) + ".", ("remove one edge", "use a non-cyclic bounded child"), cycle))
        depth: int | None = None
    else:
        depth = _max_depth(event_edges, binding_spawn_roots)
        if depth > MAX_CHILD_DEPTH:
            issues.append(ValidationIssue("$.runtimeProgram.calls", "child_depth_budget", f"Runtime graph depth {depth} exceeds {MAX_CHILD_DEPTH}.", (f"depth <= {MAX_CHILD_DEPTH}",)))
    event_spawn_budget += max(input_spawn_budgets.values())
    if event_spawn_budget > MAX_EVENT_SPAWNS_PER_ACTIVATION:
        issues.append(ValidationIssue("$.runtimeProgram.calls", "event_spawn_budget", f"Event spawn count {event_spawn_budget} exceeds {MAX_EVENT_SPAWNS_PER_ACTIVATION}.", (f"sum <= {MAX_EVENT_SPAWNS_PER_ACTIVATION}",)))

    # Archived complete compiled DTOs include these diagnostic counts. New
    # opt-in reference adapters contribute when selected; old programs keep
    # their exact diagnostic bytes as well as their gameplay wire.
    counted_capabilities = [cap for cap in CAPABILITY_REGISTRY.values()
                            if cap.name not in {"present_placed_item_sprite", "add_placed_light", "enable_placed_vfx", "select_targets_and_emit_on_event", "move_front_hand"}
                            or any(call.get("fn") == cap.name for call in calls)]
    stats = {
        "entities": len(entities),
        "bindings": len(bindings),
        "calls": len(calls),
        "eventSpawnBudget": event_spawn_budget,
        "spawnGraphDepth": depth,
        "capabilitiesUsed": sorted({str(row.get("fn")) for row in calls}),
        "primaryEntityId": primary_entity_id,
        "registryDrivenChecks": {
            "typedReferences": sum(1 for cap in counted_capabilities for spec in cap.params.values() if spec.reference is not None),
            "requirements": sum(len(cap.requirements) for cap in counted_capabilities),
            "exclusiveGroups": sorted({cap.exclusive_group for cap in CAPABILITY_REGISTRY.values() if cap.exclusive_group}),
        },
    }
    source_indices = {namespace: [i for i, row in enumerate(literal_program.get(namespace, [])) if isinstance(row, dict)]
                      for namespace in ("entities", "bindings", "calls")}
    def source_path(match: re.Match[str]) -> str:
        namespace, filtered = match.group(1), int(match.group(2))
        indices = source_indices[namespace]
        return f"$.runtimeProgram.{namespace}[{indices[filtered]}]" if filtered < len(indices) else match.group(0)
    errors = [issue.row() for issue in issues]
    for error in errors:
        error["path"] = re.sub(r"\$\.runtimeProgram\.(entities|bindings|calls)\[(\d+)\]", source_path, error["path"])
    return {"schema": "infini.runtime-program-validation.v1", "ok": not issues, "errors": errors, "stats": stats, "warnings": _composition_warnings(document)}


def _composition_warnings(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Observable inactive lanes, never guesses about intended design or repair authority."""
    program = document.get("runtimeProgram", {})
    calls = program.get("calls") if isinstance(program.get("calls"), list) else []
    by_target = _calls_by_target(program)
    warnings = []
    for index, call in enumerate(calls):
        if not isinstance(call, Mapping):
            continue
        params = call.get("params") if isinstance(call.get("params"), Mapping) else {}
        target = call.get("target")
        siblings = by_target.get(str(target), [])
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn")))
        if cap and (cap.category == "movement" or call.get("fn") in {
                "set_projectile_turn_modifier", "set_projectile_speed_modifier", "set_projectile_homing_modifier"}) and any(
                row.get("fn") == "channel_beam" for row in siblings):
            warnings.append({"path": f"$.runtimeProgram.calls[{index}]", "code": "motion_owned_by_beam",
                "message": "channel_beam owns position and velocity; this movement/modifier does not execute while that controller is active.", "relatedIds": [str(call.get("id"))]})
        if params.get("damageBasis") == "live_parent":
            child = params.get("entity") or params.get("shotEntity")
            if child and not any(row.get("fn") == "set_projectile_damage" for row in by_target.get(str(child), [])):
                warnings.append({"path": f"$.runtimeProgram.calls[{index}].params.damageBasis", "code": "inherited_damage_disabled",
                    "message": "live_parent selects damage magnitude but the child has no set_projectile_damage lane; it remains harmless. An explicit damage=0 lane can still receive inherited damage. Harmless children remain valid.",
                    "relatedIds": [str(call.get("id")), str(child)]})
    return warnings


def _motion_windows_overlap(left: Mapping[str, Any], right: Mapping[str, Any], *, wire: bool) -> bool:
    a, b = left.get("window", {}), right.get("window", {})
    if not isinstance(a, Mapping) or not isinstance(b, Mapping):
        return True  # Shape diagnostics own malformed gates.
    selected_phases = (a.get("phase", "always"), b.get("phase", "always"))
    if not all(isinstance(phase, str) for phase in selected_phases):
        return True
    phases = frozenset(selected_phases)
    if phases in (frozenset(("charging", "released")), frozenset(("charging", "outbound")),
                  frozenset(("outbound", "returning"))):
        return False
    if a and b and a.get("clock") == b.get("clock"):
        start, duration = ("startDelayTicks", "durationTicks") if wire else ("startDelaySeconds", "durationSeconds")
        values = (a.get(start), a.get(duration), b.get(start), b.get(duration))
        if all(type(value) in (int, float) and 0 <= value <= 21600 for value in values):
            # Author gates execute after nearest-world-tick projection, not at
            # fractional authored seconds. Overlap is checked in that domain.
            if not wire:
                values = tuple(math.floor(value * 60 + 0.5) for value in values)
            sa, da, sb, db = values
            return sa < sb + db and sb < sa + da
    return True


def _motion_composition_issues(rows: list[dict[str, Any]], *, wire: bool,
                               active: bool, channel: bool, primary: bool,
                               hand_pose: Any = None, item_owner_id: str = "") -> list[ValidationIssue]:
    """Shared mechanical refusal for Author and stripped wire; never writes values."""
    issues: list[ValidationIssue] = []
    if not wire:
        # Only explicitly present packaged components participate. Paths remain
        # rooted in the real Author call for leaf-local Repair.
        nested_rows = []
        for row in rows:
            cap = CAPABILITY_REGISTRY[row["fn"]]
            values = row.get("params", {})
            for parameter, member in cap.nested_components.items():
                if isinstance(values, Mapping) and isinstance(values.get(parameter), Mapping):
                    child = next(fn for fn, component in PROJECTILE_MODIFIER_COMPONENTS.items() if component == member)
                    nested_rows.append({**row, "fn": child, "params": values[parameter],
                                        "_path": row["_path"] + "." + parameter})
        rows = [*rows, *nested_rows]
    fns = {row["fn"] for row in rows}

    def params(row: Mapping[str, Any]) -> Mapping[str, Any]:
        value = row.get("params")
        return value if isinstance(value, Mapping) else {}

    def leaf(row: Mapping[str, Any], name: str) -> Any:
        cap = CAPABILITY_REGISTRY[row["fn"]]
        key = (cap.params[name].wire_name or name) if wire and name in cap.params else name
        value: Any = params(row)
        for part in key.split("."):
            value = value.get(part) if isinstance(value, Mapping) else None
        return value

    def reject(row: Mapping[str, Any], field: str, code: str, message: str,
               allowed: tuple[str, ...] = ()) -> None:
        cap = CAPABILITY_REGISTRY[row["fn"]]
        key = (cap.params[field].wire_name or field) if wire and field in cap.params else field
        path = row["_path"] + ("." + key if key else "")
        issues.append(ValidationIssue(path, code, message, allowed,
                                      (str(row.get("id") or ""),)))

    collision = next((row for row in rows if row["fn"] == "set_projectile_collision"), None)
    always_absolute = any(
        row["fn"] == "set_projectile_lash_geometry" or row["fn"] == "attach_projectile" and (
            "window" not in params(row) or isinstance(params(row)["window"], Mapping)
            and params(row)["window"].get("phase") == "always" and "clock" not in params(row)["window"])
        for row in rows)
    if collision is not None and params(collision).get("tileCollide") is True and always_absolute:
        reject(collision, "tileCollide", "incompatible_param_variant",
               "Always-absolute attachment/lash does not execute native tile collision; choose false or a phase-limited attachment.",
               ("false",))

    for retained in rows:
        retained_cap = CAPABILITY_REGISTRY[retained["fn"]]
        owns_controller_position = retained_cap.category == "controller" and retained_cap.position_ownership != "none"
        for row in rows:
            cap = CAPABILITY_REGISTRY[row["fn"]]
            if cap.category == "motion_primitive" and (owns_controller_position or cap.component_slot in retained_cap.retained_motion_slots):
                reject(row, "", "retained_motion_stage_conflict",
                       f"{retained_cap.name} already owns this native motion stage; a new {cap.component_slot} cannot execute alongside that retained driver, even with a phase window.")

    seeks = [row for row in rows if row["fn"] == "seek_projectile"]
    for fn in fns:
        maximum = CAPABILITY_REGISTRY[fn].max_per_target
        matching = [row for row in rows if row["fn"] == fn]
        if maximum is not None and len(matching) > maximum:
            reject(matching[maximum], "", "duplicate_single_component", f"{fn} permits at most {maximum} instances.")
    if len(seeks) > 1:
        phases = [params(row).get("window", {}).get("phase")
                  if isinstance(params(row).get("window"), Mapping) else None for row in seeks]
        if len(seeks) != 2 or not all(isinstance(phase, str) for phase in phases) or set(phases) != {"outbound", "returning"}:
            reject(seeks[-1], "window", "exclusive_component_conflict",
                   "Two Seek owners require distinct outbound/returning phase gates.")

    for row in rows:
        fn, p = row["fn"], params(row)
        cap = CAPABILITY_REGISTRY[fn]
        window = p.get("window") if "window" in cap.params else None
        if isinstance(window, Mapping):
            needs_charge = window.get("phase") in ("charging", "released") or window.get("clock") == "since_release"
            needs_return = window.get("phase") == "returning" or window.get("clock") == "since_return"
            if needs_charge and not fns.intersection({"accumulate_projectile_charge", "charge_then_release"}):
                reject(row, "window.phase" if window.get("phase") in ("charging", "released") else "window.clock",
                       "missing_capability_dependency", "Charge/release windows require their actual charge latch producer; no release is inferred.",
                       ("accumulate_projectile_charge",))
            if needs_return and not fns.intersection({"set_projectile_return_trigger", "move_boomerang", "move_returning_glaive", "move_flail_tether"}):
                reject(row, "window.phase" if window.get("phase") == "returning" else "window.clock",
                       "missing_capability_dependency", "Return windows require an actual return latch producer; seek and arrival do not produce returning.",
                       ("set_projectile_return_trigger",))
        if cap.category != "motion_primitive":
            continue
        if active and not channel and (fn == "set_projectile_return_trigger" and p.get("onOwnerRelease") is True
                                      or fn == "set_projectile_owner_control" and p.get("requireChannel") is True):
            # The trigger/control choice is valid. Diagnose its exact item
            # dependency, as the registry requirement owner does, rather than
            # thawing the authored selector to make the error disappear.
            path = row["_path"] if wire else row["_path"].removesuffix(".params")
            issues.append(ValidationIssue(path, "missing_item_capability_param",
                "Active owner-channel consumers require configure_item_use.channel=true.",
                ("configure_item_use.channel=true",),
                (str(row.get("id") or ""),) if wire else (item_owner_id,)))
        if fn == "set_projectile_rotation" and p.get("mode") != "spin" and leaf(row, "radiansPerSecond") not in (0, None):
            reject(row, "radiansPerSecond", "incompatible_param_variant", "Non-spin rotation has exact zero angular rate.")
        if fn == "sustain_projectile_mana":
            owner = next((params(other) for other in rows if other["fn"] == "set_projectile_owner_control"), {})
            if owner.get("requireHeldItem") is not True or owner.get("requireChannel") is not True:
                reject(row, "", "missing_capability_dependency", "Mana sustain requires held-item/channel owner control.",
                       ("set_projectile_owner_control",))
        if not wire:
            continue  # The ordinary Author requirement owner already ran.
        for rule in cap.requirements:
            value = leaf(row, rule.param) if rule.param else None
            if rule.kind == "capability_present" and rule.capability not in fns and (not rule.param or value == rule.equals):
                reject(row, "", "missing_capability_dependency", rule.message, (rule.capability,))
            elif rule.kind == "capability_absent" and fns.intersection(rule.any_of) and (not rule.param or value == rule.equals):
                reject(row, "", "exclusive_component_conflict", rule.message, rule.any_of)
            elif rule.kind == "conditional_param":
                for encoded in rule.any_of:
                    choice, required = encoded.split(":", 1)
                    if value == choice and leaf(row, required) is None:
                        reject(row, required, "missing_dependency_param", rule.message, (required,))
            elif (rule.kind == "param_only_when" and value is not None
                  and leaf(row, rule.other_param) in cap.params[rule.other_param].enum
                  and leaf(row, rule.other_param) != rule.equals):
                reject(row, rule.param, "incompatible_param_variant", rule.message)
            elif rule.kind == "ordered_params":
                other = leaf(row, rule.other_param)
                if value is not None and other is not None and not rule.ordered_values(value, other):
                    reject(row, rule.param, "unordered_param_range", rule.message)
            elif rule.kind == "enabled_trigger" and not any(leaf(row, name) is True or
                    type(leaf(row, name)) in (int, float) and leaf(row, name) > 0 for name in rule.any_of):
                reject(row, "", "empty_component", rule.message)
            elif rule.kind == "non_neutral_param" and not cap.has_non_neutral_effect(p):
                reject(row, "", "empty_component", rule.message)
            elif rule.kind == "primary_target" and not primary:
                reject(row, "", "wrong_target_kind", rule.message)
            elif rule.kind == "binding_tuple_present" and not active:
                reject(row, "", "missing_binding_dependency", rule.message)
            elif rule.kind == "item_capability_param":
                actual = channel if rule.param == "channel" else hand_pose
                if ((not rule.when_spawned_by_inputs or active)
                        and not (rule.allow_absent and actual is None)
                        and actual != rule.equals):
                    reject(row, "", "missing_item_capability_param", rule.message)

    for index, left in enumerate(rows):
        lcap = CAPABILITY_REGISTRY[left["fn"]]
        for right in rows[index + 1:]:
            rcap = CAPABILITY_REGISTRY[right["fn"]]
            if lcap.category != "motion_primitive" and rcap.category != "motion_primitive":
                continue  # Saved old driver combinations keep their admission.
            absolute_conflict = (
                lcap.position_ownership == "owns_position_while_active" and
                (rcap.position_ownership in {"owns_position_while_active", "velocity_or_position_controller"} or rcap.category == "motion_modifier") and right["fn"] != "move_straight"
                or rcap.position_ownership == "owns_position_while_active" and
                (lcap.position_ownership in {"owns_position_while_active", "velocity_or_position_controller"} or lcap.category == "motion_modifier") and left["fn"] != "move_straight")
            scale_fns = {"add_projectile_visual_scale", "set_projectile_visual_scale_curve"}
            scale_conflict = (left["fn"] in scale_fns and right["fn"] in scale_fns
                or left["fn"] == "add_projectile_visual_scale" and right["fn"] == "set_projectile_hitbox_curve" and params(right).get("mirrorToSprite") is True
                or right["fn"] == "add_projectile_visual_scale" and left["fn"] == "set_projectile_hitbox_curve" and params(left).get("mirrorToSprite") is True)
            velocity_scale_conflict = left["fn"] == right["fn"] == "scale_projectile_velocity"
            if (absolute_conflict or scale_conflict or velocity_scale_conflict) and _motion_windows_overlap(params(left), params(right), wire=wire):
                mirror = next((row for row in (left, right)
                    if row["fn"] == "set_projectile_hitbox_curve" and params(row).get("mirrorToSprite") is True), None)
                if velocity_scale_conflict:
                    reject(right, "window", "overlapping_motion_windows",
                           "Velocity-scale instances require provably disjoint windows; adjust this window or delete this call.")
                elif scale_conflict and mirror is not None:
                    reject(mirror, "mirrorToSprite", "exclusive_component_conflict",
                           "The explicit sprite mirror conflicts with an independent visual-scale owner.")
                else:
                    reject(right, "", "exclusive_component_conflict", "Overlapping position, velocity-scale or visual-scale owners are not composable.")
    return issues


def validate_runtime_program(document: Mapping[str, Any]) -> dict[str, Any]:
    shape = strict_author_shape_report(document)
    if shape["ok"]:
        return _validate_runtime_program_semantics(document)

    # Intent, realization and self-evaluation are advisory only. Keep raw shape
    # diagnostics for inspection, but never spend Repair on prose or synthesize
    # missing reports. Only executable shape and identity own acceptance.
    raw_shape_errors = [
        row for row in shape.get("errors") or []
        if isinstance(row, Mapping)
        and not is_advisory_path(str(row.get("path") or ""))
    ]
    if not raw_shape_errors and _traversable_runtime_shell(document):
        return _validate_runtime_program_semantics(document)
    shape_issues = [
        ValidationIssue(
            path=str(row.get("path") or "$"),
            code=f"shape_{row.get('kind', 'invalid')}",
            message=f"Strict schema violation: {row}",
        )
        for row in raw_shape_errors
    ]
    semantic_errors: list[dict[str, Any]] = []
    if _traversable_runtime_shell(document):
        semantic_report = _validate_runtime_program_semantics(document)
        semantic_errors = list(semantic_report.get("errors") or [])
    return {
        "schema": "infini.runtime-program-validation.v1",
        "ok": False,
        "errors": [issue.row() for issue in shape_issues] + semantic_errors,
        "stats": {},
    }


def assert_valid_runtime_program(document: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_runtime_program(document)
    if not report["ok"]:
        summary = "; ".join(f"{row['path']}: {row['message']}" for row in report["errors"][:12])
        raise ValueError("runtime program rejected: " + summary)
    return report


__all__ = [
    "MAX_CHILD_DEPTH",
    "MAX_EVENT_SPAWNS_PER_ACTIVATION",
    "MAX_RUNTIME_BINDINGS",
    "MAX_RUNTIME_CALLS",
    "MAX_RUNTIME_EVENTS_PER_ENTITY",
    "MAX_RUNTIME_ENTITIES",
    "ValidationIssue",
    "assert_valid_runtime_program",
    "validate_runtime_program",
]
