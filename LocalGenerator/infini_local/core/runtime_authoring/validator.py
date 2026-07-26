from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    MOVEMENT_CAPABILITIES,
    PROJECTILE_ENTITY_KINDS,
    CapabilitySpec,
    RequirementSpec,
)
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report


MAX_RUNTIME_ENTITIES = 12
MAX_RUNTIME_BINDINGS = 8
MAX_RUNTIME_CALLS = 48
MAX_CHILD_DEPTH = 3
MAX_EVENT_SPAWNS_PER_ACTIVATION = 32

# Finite semantic error inventory. Shape errors are emitted as ``shape_*`` and
# are handled separately by the provider/strict-schema boundary. Every code in
# this set must have an explicit conditional-Repair policy.
VALIDATION_ERROR_CODES = frozenset({
    "ambiguous_global_id",
    "binding_dependency",
    "capability_event_incompatible",
    "child_depth_budget",
    "duplicate_exclusive_input",
    "duplicate_id",
    "duplicate_single_component",
    "empty_component",
    "entity_not_binding_spawnable",
    "event_not_emitted",
    "event_spawn_budget",
    "exclusive_component_conflict",
    "gameplay_claim_without_execution",
    "illegal_event_cycle",
    "inert_component",
    "inert_stationary_entity",
    "item_body_count",
    "missing_capability_dependency",
    "missing_capability_group",
    "missing_claim_backing",
    "missing_dependency_param",
    "missing_entity_reference",
    "missing_entity_role",
    "missing_item_capability_param",
    "missing_movement_component",
    "missing_required_component",
    "mixed_entity_role",
    "primary_entity_count",
    "self_reference_forbidden",
    "unknown_capability",
    "unknown_registry_requirement",
    "unreachable_entity",
    "unsupported_input_action",
    "wrong_binding_target_kind",
    "wrong_reference_target_kind",
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


def _entity_role_issues(
    entities_by_id: Mapping[str, Mapping[str, Any]],
    bindings: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> tuple[list[ValidationIssue], str]:
    issues: list[ValidationIssue] = []
    role_rows_by_target: dict[str, list[tuple[str, str, str]]] = {}
    for namespace, rows in (("bindings", bindings), ("calls", calls)):
        for row in rows:
            target_id = str(row.get("target") or "")
            if target_id not in entities_by_id:
                continue
            role_rows_by_target.setdefault(target_id, []).append(
                (namespace, str(row.get("id") or ""), str(row.get("role") or ""))
            )
    for entity_id in entities_by_id:
        role_rows = role_rows_by_target.get(entity_id, [])
        if not role_rows:
            issues.append(ValidationIssue(
                "$.runtimeProgram",
                "missing_entity_role",
                f"Entity '{entity_id}' has no authored call/binding role rows.",
                ("add an exact call or binding with role primary|secondary",),
                (entity_id,),
            ))
            continue
        roles = {role for _, _, role in role_rows}
        if len(roles) != 1:
            issues.append(ValidationIssue(
                "$.runtimeProgram",
                "mixed_entity_role",
                f"Entity '{entity_id}' mixes authored primary and secondary rows.",
                ("all rows targeting one entity must use one role",),
                tuple(row_id for _, row_id, _ in role_rows if row_id),
            ))
    primary_targets = {
        target_id
        for target_id, role_rows in role_rows_by_target.items()
        if any(role == "primary" for _, _, role in role_rows)
    }
    if len(primary_targets) != 1:
        primary_row_ids = tuple(
            row_id
            for role_rows in role_rows_by_target.values()
            for _, row_id, role in role_rows
            if role == "primary" and row_id
        )
        issues.append(ValidationIssue(
            "$.runtimeProgram",
            "primary_entity_count",
            f"Exactly one explicitly authored primary entity is required; found {len(primary_targets)}.",
            ("mark every row of exactly one target entity primary and all other entity rows secondary",),
            primary_row_ids,
        ))
    primary_entity_id = next(iter(primary_targets)) if len(primary_targets) == 1 else ""
    return issues, primary_entity_id


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
    contract = document.get("runtimeContract")
    if not isinstance(program, Mapping) or not isinstance(contract, Mapping):
        return False
    containers = (
        program.get("entities"),
        program.get("bindings"),
        program.get("calls"),
        contract.get("claims"),
    )
    return all(
        isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
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


def _numeric_param(params: Mapping[str, Any], key: str, default: float) -> float:
    value = params.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _has_non_neutral_generated_buff(params: Mapping[str, Any]) -> bool:
    return any((
        _numeric_param(params, "miningSpeedMultiplier", 1) != 1,
        _numeric_param(params, "lightStrength", 0) > 0,
        _numeric_param(params, "oreSenseRadiusTiles", 0) > 0,
        _numeric_param(params, "movementSpeed", 0) != 0,
        _numeric_param(params, "jumpBoost", 0) > 0,
        _numeric_param(params, "manaRegen", 0) > 0,
        _numeric_param(params, "lifeRegen", 0) > 0,
    ))


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
    fns = {str(row.get("fn") or "") for row in target_calls}
    if event == "on_use":
        active = any(str(row.get("input") or "") in {"primary_use", "alternate_use"} for row in bindings)
        return active, ("add a primary_use or alternate_use binding",), "on_use requires an active item-use binding"
    if event in {"on_hit", "on_crit"}:
        required = "enable_item_contact_damage" if kind == "item_body" else "set_projectile_damage"
        return required in fns, (required,), f"{event} requires explicit damaging contact on the same entity"
    if event == "on_tile_collision":
        collision = next((row for row in target_calls if row.get("fn") == "set_projectile_collision"), None)
        raw_collision_params = (collision or {}).get("params")
        collision_params: Mapping[str, Any] = raw_collision_params if isinstance(raw_collision_params, Mapping) else {}
        tile_collide = collision_params.get("tileCollide") is True
        return tile_collide, ("set_projectile_collision(tileCollide=true)",), "on_tile_collision requires tileCollide=true"
    if event in {"on_release", "channel_complete"}:
        return "charge_then_release" in fns, ("charge_then_release",), f"{event} is emitted only by charge_then_release"
    if event == "periodic":
        return True, (), ""
    kind_spec = ENTITY_KIND_REGISTRY.get(kind)
    if kind_spec is None:
        return False, tuple(ENTITY_KIND_REGISTRY), f"unknown entity kind '{kind}'"
    if event in kind_spec.base_events or spec.always_available_on_projectile and kind_spec.projectile:
        return True, (), ""
    if spec.producer_capabilities:
        producers = tuple(name for name in spec.producer_capabilities if name in fns)
        return bool(producers), spec.producer_capabilities, f"{event} requires one declared producer capability"
    return False, (), f"{event} has no executable producer on {target_id}"


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
) -> ValidationIssue | None:
    target_id = str(call.get("target") or "")
    raw_params = call.get("params")
    params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
    target_calls = calls_by_target.get(item_id if requirement.target == "item_body" else target_id, [])
    fns = {str(row.get("fn") or "") for row in target_calls}
    path = f"$.runtimeProgram.calls[{call_index}]"

    if requirement.kind == "capability_present":
        if requirement.capability not in fns:
            return ValidationIssue(path, "missing_capability_dependency", requirement.message, (requirement.capability,), (target_id,))
        return None
    if requirement.kind == "capability_group_present":
        if not fns.intersection(requirement.any_of):
            return ValidationIssue(path, "missing_capability_group", requirement.message, requirement.any_of, (target_id,))
        return None
    if requirement.kind == "item_capability_param":
        dependency = next((row for row in target_calls if row.get("fn") == requirement.capability), None)
        raw_dependency_params = (dependency or {}).get("params")
        dependency_params: Mapping[str, Any] = raw_dependency_params if isinstance(raw_dependency_params, Mapping) else {}
        actual = dependency_params.get(requirement.param)
        if dependency is None or actual != requirement.equals:
            return ValidationIssue(path, "missing_item_capability_param", requirement.message, (f"{requirement.capability}.{requirement.param}={requirement.equals}",), (item_id,))
        return None
    if requirement.kind == "at_least_one_param_nonnegative":
        names = requirement.param.split("|")
        if not any(_numeric_param(params, name, -1) >= 0 for name in names):
            return ValidationIssue(f"{path}.params", "empty_component", requirement.message, tuple(f"{name} >= 0" for name in names))
        return None
    if requirement.kind == "conditional_param":
        raw_mode = params.get(requirement.param)
        mode = raw_mode if isinstance(raw_mode, str) else ""
        for encoded in requirement.any_of:
            expected, required_param = encoded.split(":", 1)
            if mode == expected and required_param not in params:
                return ValidationIssue(f"{path}.params.{required_param}", "missing_dependency_param", requirement.message, (required_param,))
        return None
    if requirement.kind == "non_neutral_param":
        if not _has_non_neutral_generated_buff(params):
            return ValidationIssue(f"{path}.params", "inert_component", requirement.message, ("set one non-neutral effect", "remove the call"))
        return None
    if requirement.kind == "event_available":
        raw_event = params.get(requirement.param)
        event = raw_event if isinstance(raw_event, str) else ""
        kind = str(entities_by_id.get(target_id, {}).get("kind") or "")
        ok, allowed, message = _event_available(
            event=event,
            target_id=target_id,
            kind=kind,
            calls_by_target=calls_by_target,
            bindings=bindings,
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

    issues: list[ValidationIssue] = []
    program_raw = document.get("runtimeProgram")
    contract_raw = document.get("runtimeContract")
    program: Mapping[str, Any] = program_raw if isinstance(program_raw, Mapping) else {}
    contract: Mapping[str, Any] = contract_raw if isinstance(contract_raw, Mapping) else {}
    entities = _rows(program.get("entities"))
    bindings = _rows(program.get("bindings"))
    calls = _rows(program.get("calls"))
    claims = _rows(contract.get("claims"))

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
    claim_ids: dict[str, dict[str, Any]] = {}
    for index, claim in enumerate(claims):
        register(claim, namespace="claim", path=f"$.runtimeContract.claims[{index}].id", target=claim_ids)

    item_entities = [row for row in entities if row.get("kind") == "item_body"]
    if len(item_entities) != 1:
        issues.append(ValidationIssue("$.runtimeProgram.entities", "item_body_count", f"Exactly one item_body is required; found {len(item_entities)}.", ("add one item_body", "remove extras")))
    item_id = str(item_entities[0].get("id") or "") if len(item_entities) == 1 else ""

    role_issues, primary_entity_id = _entity_role_issues(entities_by_id, bindings, calls)
    issues.extend(role_issues)

    issues.extend(_exclusive_input_issues(bindings))
    binding_spawn_roots: set[str] = set()
    for index, binding in enumerate(bindings):
        binding_id = str(binding.get("id") or "")
        target_id = str(binding.get("target") or "")
        input_name = str(binding.get("input") or "")
        action_name = str(binding.get("action") or "")
        entity = entities_by_id.get(target_id)
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        action_spec = BINDING_ACTION_REGISTRY.get(action_name)
        if entity is None:
            issues.append(ValidationIssue(f"$.runtimeProgram.bindings[{index}].target", "missing_entity_reference", f"Binding '{binding_id}' references missing entity '{target_id}'.", tuple(entities_by_id), (binding_id, target_id)))
            continue
        if input_spec is None or action_spec is None:
            continue  # strict schema already reports this case
        if action_name not in input_spec.allowed_actions or input_name not in action_spec.allowed_inputs:
            issues.append(ValidationIssue(
                f"$.runtimeProgram.bindings[{index}]",
                "unsupported_input_action",
                f"{input_name} cannot run {action_name}.",
                input_spec.allowed_actions,
                (binding_id,),
            ))
        kind = str(entity.get("kind") or "")
        if kind not in action_spec.target_kinds:
            issues.append(ValidationIssue(
                f"$.runtimeProgram.bindings[{index}].target",
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
                    f"$.runtimeProgram.bindings[{index}].target",
                    "entity_not_binding_spawnable",
                    f"{kind} must be reached through an event/controller, not a direct binding.",
                    tuple(name for name, row in ENTITY_KIND_REGISTRY.items() if row.spawnable_by_binding),
                    (target_id,),
                ))
            else:
                binding_spawn_roots.add(target_id)

    calls_by_target = _calls_by_target(program)
    seen_single: set[tuple[str, str]] = set()
    exclusive_components: dict[tuple[str, str], tuple[int, str]] = {}
    event_edges: dict[str, set[str]] = {entity_id: set() for entity_id in entities_by_id}
    event_referenced_entities: set[str] = set()
    event_spawn_budget = 0

    for index, call in enumerate(calls):
        call_id = str(call.get("id") or "")
        fn = str(call.get("fn") or "")
        target_id = str(call.get("target") or "")
        raw_params = call.get("params")
        params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
        cap = CAPABILITY_REGISTRY.get(fn)
        entity = entities_by_id.get(target_id)
        if cap is None:
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].fn", "unknown_capability", f"Unknown capability '{fn}'.", tuple(CAPABILITY_REGISTRY), (call_id,)))
            continue
        if entity is None:
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].target", "missing_entity_reference", f"Call '{call_id}' references missing entity '{target_id}'.", tuple(entities_by_id), (call_id, target_id)))
            continue
        kind = str(entity.get("kind") or "")
        if kind not in cap.target_kinds:
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].target", "wrong_target_kind", f"{fn} cannot target {kind}.", cap.target_kinds, (call_id, target_id)))
        key = (target_id, fn)
        if cap.multiplicity == "single_per_target" and key in seen_single:
            issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}]", "duplicate_single_component", f"{fn} may appear only once on '{target_id}'.", ("merge into one call", "delete duplicate"), (target_id, call_id)))
        seen_single.add(key)
        if cap.exclusive_group:
            group_key = (target_id, cap.exclusive_group)
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
            ref = param_spec.reference
            if ref is None or param_name not in params:
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
            event = str(params.get("event") or "")
            if event not in cap.allowed_events:
                issues.append(ValidationIssue(f"$.runtimeProgram.calls[{index}].params.event", "capability_event_incompatible", f"{fn} does not accept {event}.", cap.allowed_events, (call_id,)))
        if cap.activation_spawn_count_param:
            raw_spawn_count = params.get(cap.activation_spawn_count_param)
            if isinstance(raw_spawn_count, int) and not isinstance(raw_spawn_count, bool) and raw_spawn_count >= 0:
                event_spawn_budget += raw_spawn_count

    for index, call in enumerate(calls):
        cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if cap is None:
            continue
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
            )
            if issue is not None:
                issues.append(issue)

    for entity_id, entity in entities_by_id.items():
        kind = str(entity.get("kind") or "")
        kind_spec = ENTITY_KIND_REGISTRY.get(kind)
        if kind_spec is None:
            continue  # strict shape owns unknown entity kinds
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
        position_drivers = [CAPABILITY_REGISTRY[fn] for fn in fns if fn in CAPABILITY_REGISTRY and CAPABILITY_REGISTRY[fn].position_ownership != "none"]
        if kind_spec.requires_position_driver and not position_drivers:
            allowed = tuple(sorted(name for name, row in CAPABILITY_REGISTRY.items() if kind in row.target_kinds and row.position_ownership != "none"))
            issues.append(ValidationIssue("$.runtimeProgram.calls", "missing_movement_component", f"{kind} '{entity_id}' requires explicit movement/controller; none is inferred.", allowed, (entity_id,)))
        if kind in {"stationary_projectile", "temporary_helper", "field"}:
            meaningful = any(CAPABILITY_REGISTRY[fn].meaningful_for_stationary for fn in fns if fn in CAPABILITY_REGISTRY)
            if not meaningful:
                allowed = tuple(sorted(
                    name
                    for name, cap in CAPABILITY_REGISTRY.items()
                    if kind in cap.target_kinds and cap.meaningful_for_stationary
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
    for index, binding in enumerate(bindings):
        input_name = str(binding.get("input") or "")
        action_name = str(binding.get("action") or "")
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        action_spec = BINDING_ACTION_REGISTRY.get(action_name)
        dependencies = (
            ("input", input_spec.required_item_capabilities_any_of if input_spec is not None else ()),
            ("action", action_spec.required_item_capabilities_any_of if action_spec is not None else ()),
        )
        for source, required_any_of in dependencies:
            if required_any_of and not item_fns.intersection(required_any_of):
                issues.append(ValidationIssue(
                    f"$.runtimeProgram.bindings[{index}].{source}",
                    "binding_dependency",
                    f"{source} '{input_name if source == 'input' else action_name}' requires at least one declared item capability.",
                    required_any_of,
                    (item_id,) if item_id else (),
                ))

    cycle = _graph_cycle(event_edges)
    if cycle:
        issues.append(ValidationIssue("$.runtimeProgram.calls", "illegal_event_cycle", "Runtime entity graph contains a cycle: " + " -> ".join(cycle) + ".", ("remove one edge", "use a non-cyclic bounded child"), cycle))
        depth: int | None = None
    else:
        depth = _max_depth(event_edges, binding_spawn_roots)
        if depth > MAX_CHILD_DEPTH:
            issues.append(ValidationIssue("$.runtimeProgram.calls", "child_depth_budget", f"Runtime graph depth {depth} exceeds {MAX_CHILD_DEPTH}.", (f"depth <= {MAX_CHILD_DEPTH}",)))
    if event_spawn_budget > MAX_EVENT_SPAWNS_PER_ACTIVATION:
        issues.append(ValidationIssue("$.runtimeProgram.calls", "event_spawn_budget", f"Event spawn count {event_spawn_budget} exceeds {MAX_EVENT_SPAWNS_PER_ACTIVATION}.", (f"sum <= {MAX_EVENT_SPAWNS_PER_ACTIVATION}",)))

    backing_ids = set(entities_by_id) | set(bindings_by_id) | set(calls_by_id)
    for index, claim in enumerate(claims):
        raw_backing = claim.get("backedBy")
        backed = [str(value) for value in raw_backing] if isinstance(raw_backing, list) else []
        missing = [value for value in backed if value not in backing_ids]
        if missing:
            issues.append(ValidationIssue(f"$.runtimeContract.claims[{index}].backedBy", "missing_claim_backing", f"Claim '{claim.get('id')}' references missing ids: {', '.join(missing)}.", tuple(sorted(backing_ids)), tuple(missing)))
        if claim.get("kind") == "gameplay" and not any(value in calls_by_id or value in bindings_by_id for value in backed):
            issues.append(ValidationIssue(f"$.runtimeContract.claims[{index}].backedBy", "gameplay_claim_without_execution", f"Gameplay claim '{claim.get('id')}' needs call/binding backing.", tuple(sorted(set(calls_by_id) | set(bindings_by_id)))))

    stats = {
        "entities": len(entities),
        "bindings": len(bindings),
        "calls": len(calls),
        "claims": len(claims),
        "eventSpawnBudget": event_spawn_budget,
        "spawnGraphDepth": depth,
        "capabilitiesUsed": sorted({str(row.get("fn")) for row in calls}),
        "primaryEntityId": primary_entity_id,
        "registryDrivenChecks": {
            "typedReferences": sum(1 for cap in CAPABILITY_REGISTRY.values() for spec in cap.params.values() if spec.reference is not None),
            "requirements": sum(len(cap.requirements) for cap in CAPABILITY_REGISTRY.values()),
            "exclusiveGroups": sorted({cap.exclusive_group for cap in CAPABILITY_REGISTRY.values() if cap.exclusive_group}),
        },
    }
    return {"schema": "infini.runtime-program-validation.v1", "ok": not issues, "errors": [issue.row() for issue in issues], "stats": stats}


def validate_runtime_program(document: Mapping[str, Any]) -> dict[str, Any]:
    shape = strict_author_shape_report(document)
    if shape["ok"]:
        return _validate_runtime_program_semantics(document)

    raw_shape_errors = [
        row for row in shape.get("errors") or []
        if isinstance(row, Mapping)
    ]
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
    "MAX_RUNTIME_ENTITIES",
    "ValidationIssue",
    "assert_valid_runtime_program",
    "validate_runtime_program",
]
