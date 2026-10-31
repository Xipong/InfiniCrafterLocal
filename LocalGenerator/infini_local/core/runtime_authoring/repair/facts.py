"""Read-only graph, dependency and reference facts for targeted Repair."""

from __future__ import annotations

import re
from dataclasses import replace
from itertools import product
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.binding_use_policy import action_kind, canonical_transaction
from infini_local.core.runtime_authoring.binding_use_policy import target_id as binding_target_id
from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    CapabilitySpec,
    compatible_entity_reference_ids,
    referenced_entity_requirement_satisfied,
)
from infini_local.core.runtime_authoring.event_dependencies import event_dependency_alternatives
from infini_local.core.runtime_authoring.event_producer_validation import item_body_contact_suppressed
from infini_local.core.runtime_authoring.validator import _validate_requirement
from infini_local.core.strict_json import loads as strict_json_loads

_NODE_PATH_RE = re.compile(
    r"^\$\.runtimeProgram\.(entities|bindings|calls)\[(\d+)\]"
)


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _conditional_param_dependencies(cap: CapabilitySpec) -> tuple[tuple[str, Any, str], ...]:
    """Exact selector -> required leaf facts, projected from their registry owners."""
    dependencies: list[tuple[str, Any, str]] = []
    for requirement in cap.requirements:
        if requirement.kind == "param_branch_fields":
            dependencies.extend((requirement.param, requirement.equals, name) for name in requirement.any_of)
        if requirement.kind == "conditional_param":
            for encoded in requirement.any_of:
                expected, required = encoded.split(":", 1)
                dependencies.append((requirement.param, expected, required))
    # Some conditional requiredness belongs to the registry's provider shape
    # rather than a semantic RequirementSpec; consume that shape, not event names.
    params_schema = cap.provider_variant_schema()["properties"].get("params", {})
    condition = params_schema.get("if", {})
    for selector, predicate in condition.get("properties", {}).items():
        if selector in condition.get("required", ()) and "const" in predicate:
            dependencies.extend(
                (selector, predicate["const"], required)
                for required in params_schema.get("then", {}).get("required", ())
            )
    return tuple(dependencies)


def _component_repair_paths(
    code: str,
    call: Mapping[str, Any],
    *,
    path: str,
    allowed: Iterable[Any],
) -> set[str]:
    """Causal component leaves; the scope builder owns admission and deletion.

    A neutral component needs only the parameters that can make it effective,
    plus an absent dependency of those parameters. A conflict exposes only its
    diagnosed selector; unrelated effect values remain frozen.
    """
    if code == "empty_component":
        return {
            f"params.{name}"
            for descriptor in allowed
            if (name := str(descriptor).split()[0].strip())
        }
    if code == "duplicate_equipment_damage_selector":
        return {"params.damageClass", "params.phase"}

    cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
    if cap is None:
        return set()
    if code == "inert_component":
        causal_params: set[str] = set()
        for requirement in cap.requirements:
            if requirement.kind == "at_least_one_param_nonzero":
                causal_params.update(requirement.nonzero_params)
            elif requirement.kind == "non_neutral_param":
                def neutral_leaves(name: str, spec: Any, value: Any) -> set[str]:
                    if spec.properties:
                        if not isinstance(value, Mapping):
                            return set()  # A valid omitted composite does not authorize its required selectors.
                        return {leaf for key, child in spec.properties.items()
                                for leaf in neutral_leaves(name + "." + key, child, value.get(key))}
                    return {name} if spec.neutral is not None else set()

                params = _mapping(call.get("params"))
                causal_params.update(
                    leaf for name, spec in cap.params.items()
                    if not requirement.nonzero_params or name in requirement.nonzero_params
                    for leaf in neutral_leaves(name, spec, params.get(name))
                )
        paths = {f"params.{name}" for name in causal_params}
        for requirement in cap.requirements:
            if (
                requirement.kind == "positive_param_requires_param"
                and causal_params.intersection(requirement.nonzero_params)
                and requirement.param not in _mapping(call.get("params"))
            ):
                paths.add(f"params.{requirement.param}")
        return paths
    if code in {"duplicate_single_component", "exclusive_component_conflict"} and ".params." in path:
        param = path.rsplit(".params.", 1)[1]
        if any(req.kind == "capability_absent" and req.param == param for req in cap.requirements):
            return {"params." + param}
    return set()


def _program_rows(current: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    program = _mapping(current.get("runtimeProgram"))
    return {
        "entities": _rows(program.get("entities")),
        "bindings": _rows(program.get("bindings")),
        "calls": _rows(program.get("calls")),
    }


def _graph_rows(current: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    from infini_local.core.runtime_authoring.technical_lowering import (
        _exact_mechanical_view,  # pyright: ignore[reportPrivateUsage] -- private canonical lowering
    )
    return _program_rows(_exact_mechanical_view(current))


def _body_id(rows: Mapping[str, list[dict[str, Any]]]) -> str:
    bodies = [row for row in rows.get("entities", []) if row.get("kind") == "item_body"]
    return str(bodies[0].get("id") or "") if len(bodies) == 1 else ""


def _binding_target(binding: Mapping[str, Any], rows: Mapping[str, list[dict[str, Any]]]) -> str:
    explicit = binding_target_id(binding)
    spec = BINDING_ACTION_REGISTRY.get(action_kind(binding))
    if "targetId" in _mapping(binding.get("action")):
        return explicit
    return _body_id(rows) if spec is not None and spec.target_kinds == ("item_body",) else ""


def _call_target(call: Mapping[str, Any], rows: Mapping[str, list[dict[str, Any]]]) -> str:
    explicit = str(call.get("target") or "")
    cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
    return explicit or (_body_id(rows) if cap is not None and cap.target_kinds == ("item_body",) else "")


def _source_transaction(row: Mapping[str, Any], *, item_body_id: str) -> dict[str, Any]:
    """Project offered alternatives only, never frozen authored presence."""
    return canonical_transaction(row, item_body_id=item_body_id)


def _source_scope_transactions(value: Any, *, item_body_id: str) -> Any:
    if isinstance(value, list):
        return [_source_scope_transactions(row, item_body_id=item_body_id) for row in value]
    if isinstance(value, Mapping):
        result = {key: _source_scope_transactions(row, item_body_id=item_body_id) for key, row in value.items()}
        if "input" in result and isinstance(result.get("action"), Mapping):
            return _source_transaction(result, item_body_id=item_body_id)
        return result
    return value


def _program_index_rows(current: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Source coordinates for diagnostic paths, never a filtered graph view."""
    program = _mapping(current.get("runtimeProgram"))
    return {namespace: _values(program.get(namespace))
            for namespace in ("entities", "bindings", "calls")}


def _ambiguous_row_ids(values: list[dict[str, Any]]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in values:
        row_id = str(row.get("id") or "")
        if row_id and row_id in seen:
            duplicates.add(row_id)
        seen.add(row_id)
    return duplicates


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


def _node_from_path(path: str, rows: Mapping[str, list[Any]]) -> tuple[str, int, str] | None:
    match = _NODE_PATH_RE.match(path)
    if not match:
        return None
    namespace = match.group(1) or ""
    index = int(match.group(2))
    values = rows.get(namespace, [])
    row_id = str(_mapping(values[index]).get("id") or "") if 0 <= index < len(values) else ""
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
    if text.startswith(("{", "[")):
        try:
            return strict_json_loads(text)
        except ValueError:
            return text  # Malformed descriptors never become partial constraints.
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
            if requirement.capability in CAPABILITY_REGISTRY and requirement.kind not in {
                "capability_param_absent", "present_param_forbids_capability", "referenced_entity_capability_params", "referenced_entity_without_capability", "referenced_param_presence_requires_value",
            }:
                pending.append(requirement.capability)
            if requirement.kind == "capability_group_present":
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
    if cap is None or not cap.author_visible:
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
    item_id = _body_id(rows)
    calls_by_target: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        calls_by_target.setdefault(_call_target(call, rows), []).append(call)
    for requirement in cap.requirements:
        if (requirement.kind in {"item_capability_param", "capability_param_absent"}
                or (requirement.kind == "capability_absent" and not requirement.param)):
            # Author owns typed equality, accepted absence and frozen conflicts.
            # Do not invent a looser matcher or guess a candidate selector.
            for target_id in target_ids:
                owner_id = item_id if requirement.target == "item_body" else target_id
                if requirement.kind == "item_capability_param" and not any(
                    row.get("fn") == requirement.capability
                    for row in calls_by_target.get(owner_id, [])
                ):
                    continue  # Missing support may be explicitly created.
                if _validate_requirement(
                    requirement, call={"target": target_id}, call_index=0, cap=cap,
                    item_id=item_id, calls_by_target=calls_by_target,
                    entities_by_id={str(row.get("id") or ""): row for row in rows.get("entities", [])},
                    bindings=rows.get("bindings", []), primary_entity_id="", calls=calls,
                ) is not None:
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
    permissions = _mapping(scope.get("fieldPermissions"))
    rows = _values(permissions.get(namespace))
    return {
        str(row.get("id") or ""): tuple(str(value) for value in _values(row.get("paths")))
        for row in rows if isinstance(row, Mapping) and str(row.get("id") or "")
    }


def _entity_reference_params(call: Mapping[str, Any]) -> list[str]:
    cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
    params = _mapping(call.get("params"))
    if cap is None:
        return []
    return [str(params.get(name) or "") for name, spec in cap.params.items() if spec.reference is not None and params.get(name)]


def _exclusive_reference_dependency_edits(
    rows: Mapping[str, list[dict[str, Any]]],
    source_call: Mapping[str, Any],
    param_name: str,
    primary_entity_id: str,
) -> list[tuple[str, tuple[str, ...]]] | None:
    """Exact dependency leaves, only when no independent consumer owns the child."""
    cap = CAPABILITY_REGISTRY.get(str(source_call.get("fn") or ""))
    source_id = str(source_call.get("id") or "")
    child_id = _mapping(source_call.get("params")).get(param_name)
    if (cap is None or not isinstance(child_id, str) or not source_id
            or child_id == primary_entity_id
            or sum(row.get("id") == source_id for values in rows.values() for row in values) != 1):
        return None
    reference_spec = cap.params.get(param_name)
    reference = reference_spec.reference if reference_spec is not None else None
    entities = [row for row in rows["entities"] if row.get("id") == child_id]
    if (reference is None or reference.namespace != "entity" or not reference.graph_edge
            or (not reference.allow_self and child_id == source_call.get("target"))
            or len(entities) != 1 or entities[0].get("kind") not in reference.target_kinds
            or sum(row.get("id") == child_id for values in rows.values() for row in values) != 1
            or any(_binding_target(binding, rows) == child_id for binding in rows["bindings"])):
        return None
    consumers = []
    for call in rows["calls"]:
        other_cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
        if other_cap is None:
            return None
        for name, spec in other_cap.params.items():
            if (spec.reference is not None and spec.reference.namespace == "entity"
                    and _mapping(call.get("params")).get(name) == child_id):
                consumers.append((str(call.get("id") or ""), name))
    if consumers != [(source_id, param_name)]:
        return None
    child_calls = [row for row in rows["calls"] if row.get("target") == child_id]
    indexed_calls = {child_id: child_calls}
    edits = []
    for requirement in cap.requirements:
        if (requirement.param != param_name or requirement.kind not in {
                "referenced_entity_capability_params", "referenced_entity_without_capability"}
                or referenced_entity_requirement_satisfied(requirement, child_id, indexed_calls)):
            continue
        # Deleting an independently valid capability is not a parameter repair.
        if requirement.kind != "referenced_entity_capability_params":
            return None
        matches = [row for row in child_calls if row.get("fn") == requirement.capability]
        if len(matches) != 1 or not isinstance(requirement.equals, Mapping):
            return None
        call = matches[0]
        call_id = str(call.get("id") or "")
        if not call_id or sum(row.get("id") == call_id for values in rows.values() for row in values) != 1:
            return None
        paths = tuple(
            "params." + name for name, expected in requirement.equals.items()
            if not referenced_entity_requirement_satisfied(
                replace(requirement, equals={name: expected}), child_id, indexed_calls)
        )
        if paths:
            edits.append((call_id, paths))
    return edits or None


def _call_target_kinds(call: Mapping[str, Any], *, param_name: str = "") -> tuple[str, ...]:
    cap = CAPABILITY_REGISTRY.get(str(call.get("fn") or ""))
    if cap is None:
        return tuple(ENTITY_KIND_REGISTRY)
    if param_name and param_name in cap.params:
        reference = cap.params[param_name].reference
        if reference is not None:
            return reference.target_kinds
    return cap.target_kinds


def _compatible_reference_options(
    rows: Mapping[str, list[dict[str, Any]]],
    source_call: Mapping[str, Any],
    cap: CapabilitySpec,
    param_name: str,
) -> tuple[tuple[str, ...], tuple[str, ...], set[str]]:
    """Existing compatible children and the exact support slice of a new child.

    This is used only after exclusive dependency repair has been ruled out.
    It proposes separate model-authored choices without granting edits to an
    existing child or filling any missing component.
    """
    kinds = _call_target_kinds(source_call, param_name=param_name)
    indexed_calls: dict[str, list[dict[str, Any]]] = {}
    for candidate in rows["calls"]:
        indexed_calls.setdefault(str(candidate.get("target") or ""), []).append(candidate)
    candidates = compatible_entity_reference_ids(
        cap, param_name, str(source_call.get("target") or ""),
        {str(row.get("id") or ""): row for row in rows["entities"]}, indexed_calls,
    )
    new_call_fns: set[str] = set()
    for kind in kinds:
        kind_spec = ENTITY_KIND_REGISTRY.get(kind)
        if kind_spec is not None:
            new_call_fns.update(kind_spec.required_components)
            if kind_spec.requires_position_driver:
                new_call_fns.update(candidate.name for candidate in CAPABILITY_REGISTRY.values()
                    if kind in candidate.target_kinds and candidate.position_ownership != "none")
    new_call_fns.update(item.capability for item in cap.requirements
        if item.param == param_name and item.kind == "referenced_entity_capability_params")
    new_call_fns.update(candidate.name for candidate in CAPABILITY_REGISTRY.values()
        if candidate.category == "entity_combat" and set(kinds).intersection(candidate.target_kinds))
    return candidates, kinds, new_call_fns


def _binding_target_kinds(binding: Mapping[str, Any]) -> tuple[str, ...]:
    action_name = action_kind(binding)
    if action_name not in BINDING_ACTION_REGISTRY:
        return tuple(ENTITY_KIND_REGISTRY)
    return BINDING_ACTION_REGISTRY[action_name].target_kinds


def _matching_entity_ids(rows: Mapping[str, list[dict[str, Any]]], kinds: Iterable[str]) -> set[str]:
    allowed = set(kinds)
    return {
        str(row.get("id") or "")
        for row in rows["entities"]
        if str(row.get("id") or "") and str(row.get("kind") or "") in allowed
    }


def _event_producer_options(
    event: str, source_id: str, source_kind: str,
    rows: Mapping[str, list[dict[str, Any]]],
) -> list[tuple[Any, tuple[str, ...]]]:
    """Keep the event source separate from each exact binding action target."""
    spec = EVENT_KIND_REGISTRY.get(event)
    if spec is None:
        return []
    if (source_kind == "item_body" and spec.producer_binding_contact_damage is True
            and item_body_contact_suppressed(
                call for call in rows["calls"] if str(call.get("target") or "") == source_id
            )):
        return []
    options: list[tuple[Any, tuple[str, ...]]] = []
    for dependency in event_dependency_alternatives(event, source_kind):
        if source_kind not in spec.producer_binding_kinds or not dependency.required_bindings:
            options.append((dependency, (source_id,) * len(dependency.required_bindings)))
            continue
        choices: list[list[tuple[Any, str]]] = []
        for requirement in dependency.required_bindings:
            variants: list[tuple[Any, str]] = []
            actions = requirement.any_of_actions or tuple(BINDING_ACTION_REGISTRY)
            for action in actions:
                action_spec = BINDING_ACTION_REGISTRY.get(action)
                if action_spec is None:
                    continue
                inputs = tuple(input_name for input_name in requirement.any_of_inputs
                               if input_name in INPUT_KIND_REGISTRY
                               and action in INPUT_KIND_REGISTRY[input_name].allowed_actions
                               and input_name in action_spec.allowed_inputs)
                if not inputs:
                    continue
                targets = _matching_entity_ids(rows, action_spec.target_kinds)
                if "item_body" in action_spec.target_kinds:
                    targets.intersection_update({source_id})
                for target in sorted(targets):
                    variants.append((replace(requirement, any_of_inputs=inputs,
                                             any_of_actions=(action,)), target))
            choices.append(variants)
        for selection in product(*choices):
            options.append((replace(dependency, required_bindings=tuple(row[0] for row in selection)),
                            tuple(row[1] for row in selection)))
    return options
