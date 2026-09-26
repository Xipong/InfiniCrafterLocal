"""Item-body event producer projection from the canonical event registry.

The event belongs to the item even when its binding targets a projectile.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.binding_use_policy import (
    action_kind, contact_damage, target_id as binding_target_id,
)
from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY, EVENT_KIND_REGISTRY, INPUT_KIND_REGISTRY,
    event_dependency_alternatives,
)


def item_body_producer_bindings(
    event: str,
    *,
    target_id: str,
    target_calls: Iterable[Mapping[str, Any]],
    bindings: Iterable[Mapping[str, Any]],
    contact_suppressed: bool = False,
) -> tuple[Mapping[str, Any], ...]:
    """Return the actual active-use bindings satisfying registry alternatives."""
    spec = EVENT_KIND_REGISTRY.get(event)
    if spec is None or "item_body" not in spec.producer_binding_kinds:
        return ()
    calls = tuple(target_calls)
    if spec.producer_binding_contact_damage is True and item_body_contact_suppressed(
        calls, contact_suppressed=contact_suppressed,
    ):
        return ()
    result: list[Mapping[str, Any]] = []
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
            action_name = action_kind(binding)
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
                     or contact_damage(binding) is requirement.required_contact_damage)
                # Item-targeting actions reference this body; spawn_entity
                # references a projectile, but its use event still belongs here.
                and ("item_body" not in action_spec.target_kinds
                     or binding_target_id(binding) == target_id)
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
