"""Extract rejected fragments and immutable dependency context for Repair requests."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.runtime_authoring.binding_use_policy import target_id as binding_target_id
from infini_local.core.runtime_authoring.repair.facts import _entity_reference_params, _mapping, _program_index_rows, _program_rows, _values


def runtime_repair_fragments(current: Mapping[str, Any], scope: Mapping[str, Any]) -> dict[str, Any]:
    """Project the failed program into a small but sufficient Repair dossier.

    The model receives complete broken nodes plus a local dependency
    neighbourhood around affected entities, plus a compact immutable index.
    The caller separately supplies exact read-only concept/runtimeProgram for
    the complete report; neither projection enlarges the permitted edit scope.
    """

    rows = _program_rows(current)
    mutable = _mapping(scope.get("mutable"))
    context_ids = _mapping(scope.get("contextIds"))
    create = _mapping(scope.get("create"))
    key_by_namespace = {"entities": "entityIds", "bindings": "bindingIds", "calls": "callIds"}

    mutable_sets = {
        namespace: set(str(value) for value in _values(mutable.get(key_by_namespace[namespace])))
        for namespace in rows
    }
    wanted = {
        namespace: set(str(value) for value in _values(context_ids.get(key_by_namespace[namespace])))
        for namespace in rows
    }

    # Seed the local graph with every affected or newly-targeted entity.
    affected_entities = set(wanted["entities"]) | set(mutable_sets["entities"])
    for policy_name in ("calls", "bindings"):
        policy = _mapping(create.get(policy_name))
        affected_entities.update(str(value) for value in _values(policy.get("allowedTargetIds")) if str(value))
        affected_entities.update(str(value) for value in _values(policy.get("requiredTargetIds")) if str(value))
    call_create = _mapping(create.get("calls"))
    affected_entities.update(str(value) for value in _values(call_create.get("requiredReferenceEntityIds")) if str(value))
    for requirement in _values(scope.get("repairRequirements")):
        if not isinstance(requirement, Mapping):
            continue
        for row_id in _values(requirement.get("affectedIds")):
            value = str(row_id or "")
            if any(str(row.get("id") or "") == value for row in rows["entities"]):
                affected_entities.add(value)

    # Mutable bindings/calls bring their target and typed references into the
    # same local neighbourhood.
    for binding in rows["bindings"]:
        if str(binding.get("id") or "") in mutable_sets["bindings"]:
            affected_entities.add(binding_target_id(binding))
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
        if binding_target_id(binding) in affected_entities:
            wanted["bindings"].add(binding_id)
    blocker_plan = _mapping(scope.get("blockerPlan"))
    context_capabilities = {
        str(value)
        for key in ("directCapabilityNames", "supportingCapabilityNames", "existingBrokenCapabilityNames")
        for value in _values(blocker_plan.get(key))
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
                {key: copy.deepcopy(row[key]) for key in ("id", "input", "action", "stackCost", "contactDamage") if key in row}
                for row in values
            ]
        elif namespace == "calls":
            summaries[namespace] = [
                {key: row.get(key) for key in ("id", "fn", "target")}
                for row in values
            ]

    deletable = _mapping(scope.get("deletable"))
    indexed_rows = _program_index_rows(current)
    broken_by_index: dict[str, list[dict[str, Any]]] = {}
    for namespace in ("entities", "bindings", "calls"):
        index_key = namespace[:-1] + "Indices" if namespace != "entities" else "entityIndices"
        indices = [int(value) for value in deletable.get(index_key) or []]
        broken_by_index[namespace] = [
            {"index": index, "value": copy.deepcopy(indexed_rows[namespace][index])}
            for index in indices if 0 <= index < len(indexed_rows[namespace])
        ]
    return {
        "broken": broken,
        "brokenByIndex": broken_by_index,
        "dependencyContext": dependency,
        "immutableIndex": summaries,
    }
