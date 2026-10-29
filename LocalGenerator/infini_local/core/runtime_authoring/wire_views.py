"""Read-only projections of accepted wire for Visual, VFX, and diagnostics.

These readers do not compile, repair, or accept Author input. Event producer
facts remain in capability_registry and event_producer_validation.
"""
from __future__ import annotations

from typing import Any, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY, ENTITY_KIND_REGISTRY, EVENT_KIND_REGISTRY, PROJECTILE_MODIFIER_COMPONENTS,
)
from infini_local.core.runtime_authoring.event_producer_validation import item_body_producer_bindings


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def runtime_event_inventory(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = _dict(data.get("runtimeProgram"))
    rows: list[dict[str, Any]] = []
    item_entity_id = str(runtime.get("itemEntityId") or "")
    if not item_entity_id:
        item_entity_id = next((
            str(entity.get("id") or "")
            for entity in runtime.get("entities") or []
            if isinstance(entity, Mapping) and str(entity.get("kind") or "") == "item_body"
        ), "")
    # Wire-only caller: feed the shared event predicate its explicit flat view.
    # Never admit or auto-detect an Author wrapper here.
    bindings = tuple({"id": row.get("id"), "input": row.get("input"), **_dict(row.get("usePolicy"))}
                     for row in runtime.get("bindings") or [] if isinstance(row, Mapping))
    contact_suppressed = bool(
        _dict(runtime.get("itemUse")).get("disableMeleeHitbox")
        or _dict(data.get("gameplay")).get("ammoCategory")
    )
    item_producers = {
        name: item_body_producer_bindings(
            name, target_id=item_entity_id, target_calls=(), bindings=bindings,
            contact_suppressed=contact_suppressed,
        )
        for name, spec in EVENT_KIND_REGISTRY.items()
        if "item_body" in spec.producer_binding_kinds
    }
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, Mapping):
            continue
        entity_id = str(entity.get("id") or "")
        entity_kind = str(entity.get("kind") or "")
        kind_spec = ENTITY_KIND_REGISTRY.get(entity_kind)
        for event_name in (kind_spec.base_events if kind_spec is not None else ()):
            rows.append({"entityId": entity_id, "event": event_name})
        for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items():
            if member in entity:
                rows.extend({"entityId": entity_id, "event": event_name}
                            for event_name in CAPABILITY_REGISTRY[fn].emitted_events)
        if entity_kind == "item_body":
            for event_name, producers in item_producers.items():
                if producers and EVENT_KIND_REGISTRY[event_name].producer_binding_contact_damage is True:
                    rows.append({"entityId": entity_id, "event": event_name})
        elif _dict(entity.get("damage")).get("enabled"):
            rows.extend(({"entityId": entity_id, "event": "on_hit"}, {"entityId": entity_id, "event": "on_crit"}))
        if _dict(entity.get("collision")).get("tileCollide"):
            rows.append({"entityId": entity_id, "event": "on_tile_collision"})
        for event in entity.get("events") or []:
            if isinstance(event, Mapping):
                event_name = str(event.get("event") or "")
                if entity_kind == "item_body" and event_name in item_producers and not item_producers[event_name]:
                    continue
                rows.append({"entityId": entity_id, "event": event_name})
    for event_name, producers in item_producers.items():
        if EVENT_KIND_REGISTRY[event_name].producer_binding_contact_damage is None and item_entity_id:
            for binding in producers:
                rows.append({"entityId": item_entity_id, "event": event_name, "input": str(binding.get("input") or "")})
    declared_reactions = {(str(entity.get("id")), str(action.get("event")))
                          for entity in runtime.get("entities", []) if isinstance(entity, Mapping)
                          for action in entity.get("events", []) if isinstance(action, Mapping)
                          and action.get("event") in {"on_hurt", "on_enemy_kill"}}
    rows = [row for row in rows if row["event"] not in {"on_hurt", "on_enemy_kill"}
            or (row["entityId"], row["event"]) in declared_reactions]
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("entityId") or ""), str(row.get("event") or ""), str(row.get("input") or ""))
        unique[key] = row
    return [unique[key] for key in sorted(unique)]


def runtime_visual_roles(data: Mapping[str, Any]) -> list[dict[str, str]]:
    runtime = _dict(data.get("runtimeProgram"))
    out: list[dict[str, str]] = []
    for entity in runtime.get("entities") or []:
        if isinstance(entity, Mapping):
            out.append({
                "entityId": str(entity.get("id") or ""),
                "entityKind": str(entity.get("kind") or ""),
                "visualRole": str(entity.get("visualRole") or ""),
            })
    return out
