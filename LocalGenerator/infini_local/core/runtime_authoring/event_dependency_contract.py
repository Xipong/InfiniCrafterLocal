from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
)


@dataclass(frozen=True, slots=True)
class EventCallRequirement:
    fn: str
    exact_params: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def create(cls, fn: str, exact_params: Mapping[str, Any] | None = None) -> EventCallRequirement:
        return cls(fn=fn, exact_params=tuple(sorted((exact_params or {}).items())))

    def exact_params_dict(self) -> dict[str, Any]:
        return dict(self.exact_params)


@dataclass(frozen=True, slots=True)
class EventBindingRequirement:
    any_of_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventDependencyAlternative:
    required_calls: tuple[EventCallRequirement, ...] = ()
    required_bindings: tuple[EventBindingRequirement, ...] = ()

    @classmethod
    def required_call(
        cls,
        fn: str,
        exact_params: Mapping[str, Any] | None = None,
    ) -> EventDependencyAlternative:
        return cls(required_calls=(EventCallRequirement.create(fn, exact_params),))

    @classmethod
    def any_binding_input(cls, inputs: Iterable[str]) -> EventDependencyAlternative:
        return cls(required_bindings=(EventBindingRequirement(tuple(inputs)),))


def event_dependency_alternatives(event: str, kind: str) -> tuple[EventDependencyAlternative, ...]:
    """Return finite producer alternatives without selecting or adding one."""

    spec = EVENT_KIND_REGISTRY.get(event)
    if spec is None or kind not in spec.source_kinds:
        return ()
    if event == "on_use":
        return (EventDependencyAlternative.any_binding_input(("primary_use", "alternate_use")),)
    if event in {"on_hit", "on_crit"}:
        required = "enable_item_contact_damage" if kind == "item_body" else "set_projectile_damage"
        return (EventDependencyAlternative.required_call(required),)
    if event == "on_tile_collision":
        return (EventDependencyAlternative.required_call("set_projectile_collision", {"tileCollide": True}),)
    if event in {"on_release", "channel_complete"}:
        return (EventDependencyAlternative.required_call("charge_then_release"),)
    if event == "periodic":
        return (EventDependencyAlternative(),)
    kind_spec = ENTITY_KIND_REGISTRY.get(kind)
    if kind_spec is None:
        return ()
    if event in kind_spec.base_events or spec.always_available_on_projectile and kind_spec.projectile:
        return (EventDependencyAlternative(),)
    return tuple(EventDependencyAlternative.required_call(name) for name in spec.producer_capabilities)


def event_alternative_is_present(
    alternative: EventDependencyAlternative,
    *,
    target_calls: Iterable[Mapping[str, Any]],
    bindings: Iterable[Mapping[str, Any]],
) -> bool:
    call_rows = tuple(target_calls)
    binding_rows = tuple(bindings)

    def call_present(requirement: EventCallRequirement) -> bool:
        expected = requirement.exact_params_dict()
        for call in call_rows:
            if str(call.get("fn") or "") != requirement.fn:
                continue
            raw_params = call.get("params")
            params: Mapping[str, Any] = raw_params if isinstance(raw_params, Mapping) else {}
            if all(params.get(key) == value for key, value in expected.items()):
                return True
        return False

    def binding_present(requirement: EventBindingRequirement) -> bool:
        allowed_inputs = set(requirement.any_of_inputs)
        return any(str(row.get("input") or "") in allowed_inputs for row in binding_rows)

    return (
        all(call_present(requirement) for requirement in alternative.required_calls)
        and all(binding_present(requirement) for requirement in alternative.required_bindings)
    )


def event_dependency_descriptors(alternatives: Iterable[EventDependencyAlternative]) -> tuple[str, ...]:
    allowed: list[str] = []
    for alternative in alternatives:
        for requirement in alternative.required_calls:
            exact = requirement.exact_params_dict()
            suffix = "" if not exact else "(" + ",".join(
                f"{key}={value!r}" for key, value in exact.items()
            ) + ")"
            allowed.append(requirement.fn + suffix)
        for requirement in alternative.required_bindings:
            allowed.append("binding input one of: " + ",".join(requirement.any_of_inputs))
    return tuple(allowed)


__all__ = [
    "EventBindingRequirement",
    "EventCallRequirement",
    "EventDependencyAlternative",
    "event_alternative_is_present",
    "event_dependency_alternatives",
    "event_dependency_descriptors",
]
