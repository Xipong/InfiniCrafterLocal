"""Finite event producer queries over the canonical capability inventory."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import infini_local.core.runtime_authoring.capability_registry as registry


@dataclass(frozen=True, slots=True)
class EventCallRequirement:
    capability: str
    exact_params: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def create(
        cls,
        capability: str,
        exact_params: Mapping[str, Any] | None = None,
    ) -> EventCallRequirement:
        return cls(
            capability=capability,
            exact_params=tuple(sorted((exact_params or {}).items())),
        )

    def exact_params_dict(self) -> dict[str, Any]:
        return dict(self.exact_params)


@dataclass(frozen=True, slots=True)
class EventBindingRequirement:
    any_of_inputs: tuple[str, ...]
    any_of_actions: tuple[str, ...] = ()
    required_contact_damage: bool | None = None


@dataclass(frozen=True, slots=True)
class EventDependencyAlternative:
    required_calls: tuple[EventCallRequirement, ...] = ()
    required_bindings: tuple[EventBindingRequirement, ...] = ()

    @classmethod
    def required_call(
        cls,
        capability: str,
        exact_params: Mapping[str, Any] | None = None,
    ) -> EventDependencyAlternative:
        return cls(required_calls=(EventCallRequirement.create(capability, exact_params),))

    @classmethod
    def any_binding_input(
        cls,
        inputs: Iterable[str],
        actions: Iterable[str] = (),
        *,
        contact_damage: bool | None = None,
    ) -> EventDependencyAlternative:
        return cls(required_bindings=(EventBindingRequirement(
            tuple(inputs),
            tuple(actions),
            contact_damage,
        ),))


def event_dependency_alternatives(event: str, kind: str) -> tuple[EventDependencyAlternative, ...]:
    """Project finite producer alternatives from registry data without choosing one."""

    event_spec = registry.EVENT_KIND_REGISTRY.get(event)
    kind_spec = registry.ENTITY_KIND_REGISTRY.get(kind)
    if event_spec is None or kind_spec is None or kind not in event_spec.source_kinds:
        return ()
    binding_requirement = (
        EventBindingRequirement(
            event_spec.producer_binding_inputs,
            event_spec.producer_binding_actions,
            event_spec.producer_binding_contact_damage,
        )
        if event_spec.producer_binding_inputs and kind in event_spec.producer_binding_kinds
        else None
    )
    if event in kind_spec.base_events:
        return (EventDependencyAlternative(),)
    alternatives: list[EventDependencyAlternative] = []
    for capability_name in event_spec.producer_capabilities:
        capability = registry.CAPABILITY_REGISTRY.get(capability_name)
        if capability is None or not capability.author_visible or kind not in capability.target_kinds:
            continue
        alternatives.append(EventDependencyAlternative(
            required_calls=(EventCallRequirement.create(
                capability_name,
                event_spec.producer_exact_params.get(capability_name),
            ),),
            required_bindings=((binding_requirement,) if binding_requirement is not None else ()),
        ))
    if not alternatives and binding_requirement is not None:
        alternatives.append(EventDependencyAlternative(required_bindings=(binding_requirement,)))
    return tuple(alternatives)


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
        for row in binding_rows:
            raw_action = row.get("action")
            action: Mapping[str, Any] = raw_action if isinstance(raw_action, Mapping) else {}
            input_name = row.get("input")
            inp = registry.INPUT_KIND_REGISTRY.get(input_name) if isinstance(input_name, str) else None
            action_name = action.get("kind")
            if action_name is None and inp is not None and len(inp.allowed_actions) == 1:
                action_name = inp.allowed_actions[0]
            if (isinstance(input_name, str) and input_name in allowed_inputs
                and (not allowed_actions or isinstance(action_name, str) and action_name in allowed_actions)
                and action.get("targetId") == target_id
                and (requirement.required_contact_damage is None or
                     (row.get("contactDamage") is True) is requirement.required_contact_damage)):
                return True
        return False

    return (
        all(call_present(requirement) for requirement in alternative.required_calls)
        and all(binding_present(requirement) for requirement in alternative.required_bindings)
    )


def event_dependency_descriptors(
    alternatives: Iterable[EventDependencyAlternative],
) -> tuple[str, ...]:
    allowed: list[str] = []
    for alternative in alternatives:
        for requirement in alternative.required_calls:
            exact = requirement.exact_params_dict()
            suffix = "" if not exact else "(" + ",".join(
                f"{key}={value!r}" for key, value in exact.items()
            ) + ")"
            allowed.append(requirement.capability + suffix)
        for requirement in alternative.required_bindings:
            descriptor = "binding input one of: " + ",".join(requirement.any_of_inputs)
            if requirement.any_of_actions:
                descriptor += "; action one of: " + ",".join(requirement.any_of_actions)
            if requirement.required_contact_damage is not None:
                descriptor += "; contactDamage=" + str(requirement.required_contact_damage).lower()
            allowed.append(descriptor)
    return tuple(allowed)
