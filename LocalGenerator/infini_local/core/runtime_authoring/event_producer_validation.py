"""Item-body event producer projection from the canonical event registry.

The event belongs to the item even when its binding targets a projectile.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.binding_use_policy import (
    action_kind, contact_damage, target_id as binding_target_id,
    wire_action_kind, wire_contact_damage, wire_target_id,
)
from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY, EVENT_KIND_REGISTRY, INPUT_KIND_REGISTRY,
    EventDependencyAlternative, EventCallRequirement, EventBindingRequirement,
    event_dependency_alternatives,
)


def event_alternative_is_present(
    alternative: EventDependencyAlternative,
    *,
    target_id: str,
    target_calls: Iterable[Mapping[str, Any]],
    bindings: Iterable[Mapping[str, Any]],
) -> bool:
    call_rows = tuple(target_calls)
    binding_rows = tuple(bindings)

    def call_present(requirement: EventCallRequirement) -> bool:
        expected = requirement.exact_params_dict()
        for call in call_rows:
            if str(call.get("fn") or "") != requirement.capability:
                continue
            raw_params = call.get("params")
            params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
            if all(params.get(key) == value for key, value in expected.items()):
                return True
        return False

    def binding_present(requirement: EventBindingRequirement) -> bool:
        allowed_inputs = set(requirement.any_of_inputs)
        allowed_actions = set(requirement.any_of_actions)
        return any(
            str(row.get("input") or "") in allowed_inputs
            and (not allowed_actions or action_kind(row) in allowed_actions)
            and binding_target_id(row, item_entity_id=target_id) == target_id
            and (
                requirement.required_contact_damage is None
                or contact_damage(row) is requirement.required_contact_damage
            )
            for row in binding_rows
        )

    return (
        all(call_present(requirement) for requirement in alternative.required_calls)
        and all(binding_present(requirement) for requirement in alternative.required_bindings)
    )



def item_body_producer_bindings(
    event: str,
    *,
    target_id: str,
    target_calls: Iterable[Mapping[str, Any]],
    bindings: Iterable[Mapping[str, Any]],
    contact_suppressed: bool = False,
    wire: bool = False,
) -> tuple[Mapping[str, Any], ...]:
    """Return actual active-use producers from the explicitly selected lifecycle."""
    spec = EVENT_KIND_REGISTRY.get(event)
    if spec is None or "item_body" not in spec.producer_binding_kinds:
        return ()
    calls = tuple(target_calls)
    if spec.producer_binding_contact_damage is True and item_body_contact_suppressed(
        calls, contact_suppressed=contact_suppressed,
    ):
        return ()
    result: list[Mapping[str, Any]] = []
    read_action = wire_action_kind if wire else action_kind
    read_contact = wire_contact_damage if wire else contact_damage
    for alternative in event_dependency_alternatives(event, "item_body"):
        if not all(
            any(
                call.get("fn") == requirement.capability
                and isinstance(call.get("params"), Mapping)
                and all(call["params"].get(key) == value for key, value in requirement.exact_params)
                for call in calls
            ) for requirement in alternative.required_calls
        ):
            continue
        for binding in bindings:
            input_name = str(binding.get("input") or "")
            action_name = read_action(binding)
            input_spec = INPUT_KIND_REGISTRY.get(input_name)
            action_spec = BINDING_ACTION_REGISTRY.get(action_name)
            if (input_spec is None or action_spec is None
                    or action_name not in input_spec.allowed_actions
                    or input_name not in action_spec.allowed_inputs):
                continue
            if alternative.required_bindings and all(
                input_name in requirement.any_of_inputs
                and (not requirement.any_of_actions or action_name in requirement.any_of_actions)
                and (requirement.required_contact_damage is None
                     or read_contact(binding) is requirement.required_contact_damage)
                # Item-targeting actions reference this body; spawn_entity
                # references a projectile, but its use event still belongs here.
                and ("item_body" not in action_spec.target_kinds
                     or (wire_target_id(binding) if wire else binding_target_id(binding, item_entity_id=target_id)) == target_id)
                for requirement in alternative.required_bindings
            ):
                result.append(binding)
    return tuple(result)


def item_body_contact_suppressed(
    target_calls: Iterable[Mapping[str, Any]], *, contact_suppressed: bool = False,
) -> bool:
    """The same frozen engine gates used by validation and wire projection."""
    calls = tuple(target_calls)  # Repair passes a one-shot generator; both gates must see it.
    return (contact_suppressed
            or any(call.get("fn") == "configure_item_use"
                   and isinstance(call.get("params"), Mapping)
                   and call["params"].get("disableMeleeHitbox") is True
                   for call in calls)
            or any(call.get("fn") == "configure_vanilla_ammo_item"
                   and isinstance(call.get("params"), Mapping)
                   and call["params"].get("ammoCategory")
                   for call in calls))


def item_body_event_produced(
    event: str,
    *,
    target_id: str,
    target_calls: Iterable[Mapping[str, Any]],
    bindings: Iterable[Mapping[str, Any]],
) -> bool:
    return bool(item_body_producer_bindings(
        event, target_id=target_id, target_calls=target_calls, bindings=bindings,
    ))
