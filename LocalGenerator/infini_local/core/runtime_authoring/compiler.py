from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from infini_local.core.runtime_authoring.binding_use_policy import (
    action_kind,
    placement_call_id,
    project_to_wire,
    target_id as binding_target_id,
)
from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY,
    CONTROLLER_OPCODE,
    EVENT_ACTION_OPCODE,
    MOVEMENT_OPCODE,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_WIRE_SCHEMA,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    VISUAL_ROLE_BY_ENTITY_KIND,
    equipment_damage_wire_path,
)
from infini_local.core.runtime_authoring.event_producer_validation import item_body_producer_bindings
from infini_local.core.runtime_authoring.program_schema import authored_primary_entity_id
from infini_local.core.runtime_authoring.technical_lowering import (
    audit_compiler_receipts,
    primary_binding_role,
    primary_binding_role_receipt,
    primary_owner_for_kind,
    primary_owner_receipt,
)
from infini_local.core.runtime_authoring.validator import (
    MAX_CHILD_DEPTH,
    MAX_EVENT_SPAWNS_PER_ACTIVATION,
    MAX_RUNTIME_ENTITIES,
    assert_valid_runtime_program,
)


@dataclass(slots=True)
class _CompileContext:
    receipts: list[dict[str, Any]]

    def write(self, *, call: Mapping[str, Any], path: str, value: Any, target: MutableMapping[str, Any], key: str, authored_param: str | None = None) -> None:
        target[key] = copy.deepcopy(value)
        self.receipts.append({
            "callId": str(call.get("id") or ""),
            "fn": str(call.get("fn") or ""),
            "authoredPath": f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].params.{authored_param or key}",
            "finalPath": path,
            "value": copy.deepcopy(value),
            "status": "delivered",
        })

    def write_derived(self, *, call: Mapping[str, Any], path: str, value: Any, target: MutableMapping[str, Any], key: str, source: str) -> None:
        target[key] = copy.deepcopy(value)
        self.receipts.append({
            "callId": str(call.get("id") or ""),
            "fn": str(call.get("fn") or ""),
            "authoredPath": source,
            "finalPath": path,
            "value": copy.deepcopy(value),
            "status": "technical_projection",
        })


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _copy_params(call: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(_dict(call.get("params")))

def _authored_param_for_wire(fn: str, wire_key: str) -> str:
    """Resolve a fixed DTO slot through the registry, never through Author aliases."""
    params = CAPABILITY_REGISTRY[fn].params
    if wire_key in params:
        return wire_key
    matches = [name for name, spec in params.items()
               if (spec.wire_name or name) == wire_key]
    if len(matches) != 1:
        raise RuntimeError(f"{fn}: wire slot {wire_key!r} has no unique Author parameter")
    return matches[0]


def _compile_item_call(
    ctx: _CompileContext,
    call: Mapping[str, Any],
    *,
    gameplay: dict[str, Any],
    accessory: dict[str, Any],
    armor: dict[str, Any],
    runtime: dict[str, Any],
    item_entity: dict[str, Any],
    entity_index: int,
    equipment_config: str,
) -> None:
    fn = str(call.get("fn") or "")
    p = _copy_params(call)

    def project(target: dict[str, Any], path_prefix: str, mapping: Mapping[str, str]) -> None:
        for wire_key, destination in mapping.items():
            # Prefer the actual DTO field, since older Author spellings need
            # not equal that field (e.g. potionSickness -> potion).
            wire_matches = [name for name, spec in CAPABILITY_REGISTRY[fn].params.items()
                            if spec.wire_name == destination]
            if len(wire_matches) > 1:
                raise RuntimeError(f"{fn}: wire slot {destination!r} is ambiguous")
            source = wire_matches[0] if wire_matches else _authored_param_for_wire(fn, wire_key)
            if source in p:
                spec = CAPABILITY_REGISTRY[fn].params[source]
                ctx.write(call=call, path=f"{path_prefix}.{destination}", value=spec.to_wire(p[source]), target=target, key=destination, authored_param=source)

    def project_equipment(target: dict[str, Any], prefix: str) -> None:
        for source, spec in CAPABILITY_REGISTRY[fn].params.items():
            if source in p:
                destination = spec.wire_name or source
                ctx.write(call=call, path=f"{prefix}.{destination}",
                          value=spec.to_wire(p[source]), target=target,
                          key=destination, authored_param=source)

    if fn == "configure_item_stats":
        project(gameplay, "gameplay", {
            name: spec.wire_name or name
            for name, spec in CAPABILITY_REGISTRY[fn].params.items()
        })
        return
    if fn == "configure_item_use":
        item_use = runtime.setdefault("itemUse", {})
        ctx.write_derived(
            call=call,
            path="runtimeProgram.itemUse.configured",
            value=True,
            target=item_use,
            key="configured",
            source=f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn",
        )
        project(gameplay, "gameplay", {
            "useStyle": "useStyleName",
            "autoReuse": "autoReuse",
            "useTurn": "useTurn",
            "holdoutOffsetX": "holdoutOffsetX",
            "holdoutOffsetY": "holdoutOffsetY",
            "handPose": "handPose",
            "releaseTiming": "releaseTiming",
        })
        project(item_use, "runtimeProgram.itemUse", {
            "useStyle": "useStyle",
            "hideUseGraphic": "hideUseGraphic",
            "disableMeleeHitbox": "disableMeleeHitbox",
            "channel": "channel",
            "handPose": "handPose",
            "releaseTiming": "releaseTiming",
            "holdoutOffsetX": "holdoutOffsetX",
            "holdoutOffsetY": "holdoutOffsetY",
        })
        return
    if fn == "configure_item_contact_hitbox":
        contact = runtime.setdefault("itemContact", {})
        project(contact, "runtimeProgram.itemContact", {
            "hitboxScale": "hitboxScale",
            "contactForgivenessPx": "contactForgivenessPx",
        })
        return
    if fn == "configure_vanilla_ammo_item":
        project(gameplay, "gameplay", {
            "ammoCategory": "ammoCategory",
            "projectileId": "ammoProjectileId",
            "shootSpeedPxPerTick": "ammoShootSpeedPxPerTick",
            "notAmmo": "notAmmo",
        })
        return
    if fn == "restore_resources_on_use":
        project(gameplay, "gameplay", {"healLife": "healLife", "healMana": "healMana", "potionSickness": "potion"})
        return
    if fn == "apply_vanilla_buff_on_use":
        buffs = gameplay.setdefault("extraBuffs", [])
        entry = {"buffCode": p["buffId"], "buffTime": p["durationTicks"]}
        buffs.append(entry)
        base = len(buffs) - 1
        ctx.receipts.extend([
            {
                "callId": str(call.get("id") or ""), "fn": fn,
                "authoredPath": f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].params.buffId",
                "finalPath": f"gameplay.extraBuffs[{base}].buffCode", "value": p["buffId"], "status": "technical_projection",
            },
            {
                "callId": str(call.get("id") or ""), "fn": fn,
                "authoredPath": f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].params.durationTicks",
                "finalPath": f"gameplay.extraBuffs[{base}].buffTime", "value": p["durationTicks"], "status": "technical_projection",
            },
        ])
        return
    if fn == "apply_generated_buff_on_use":
        generated = gameplay.setdefault("generatedBuff", {})
        project(generated, "gameplay.generatedBuff", {
            "durationTicks": "durationTicks",
            "miningSpeedMultiplier": "miningSpeedMultiplier",
            "lightStrength": "emitLightStrength",
            "lightColor": "lightColorName",
            "oreSenseEnabled": "oreSenseRadiusTiles",
            "movementSpeed": "movementSpeed",
            "jumpBoost": "jumpBoost",
            "manaRegen": "manaRegen",
            "lifeRegenHpPerSecond": "lifeRegen",
        })
        return
    if fn == "configure_tool":
        project(gameplay, "gameplay", {
            "pickPower": "pickPower",
            "axePowerTooltipPercent": "axePower",
            "hammerPower": "hammerPower",
            "miningSpeedScale": "miningSpeedScale",
        })
        return

    if fn == "require_use_condition":
        project(gameplay, "gameplay", {"mode": "useConditionMode", "minLife": "useConditionMinLife", "minMana": "useConditionMinMana"})
        return
    if fn == "add_hold_light":
        project(gameplay, "gameplay", {"strength": "holdLightStrength", "color": "holdLightColorName"})
        return
    if fn == "move_player_on_use":
        project(gameplay, "gameplay", {
            "mode": "mobilityMode",
            "rangeTiles": "mobilityRangeTiles",
            "cooldownTicks": "mobilityCooldownTicks",
            "safeTileOnly": "mobilitySafeTileOnly",
        })
        return
    if fn == "configure_accessory":
        accessory["enabled"] = True
        ctx.write_derived(call=call, path="accessory.enabled", value=True, target=accessory, key="enabled", source=f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn")
        project_equipment(accessory, "accessory")
        return
    if fn == "configure_armor":
        armor["enabled"] = True
        ctx.write_derived(call=call, path="armor.enabled", value=True, target=armor, key="enabled", source=f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn")
        project_equipment(armor, "armor")
        return
    if fn == "add_equipment_damage_bonus":
        if equipment_config not in {"armor", "accessory"}:
            raise RuntimeError("validated equipment class modifier has no unique equipment configuration")
        path = equipment_damage_wire_path(
            str(p["phase"]), str(p["damageClass"]), armor=equipment_config == "armor",
        )
        target = armor if equipment_config == "armor" else accessory
        _, key = path.split(".", 1)
        ctx.write(
            call=call, path=path,
            value=CAPABILITY_REGISTRY[fn].params["bonusPercent"].to_wire(p["bonusPercent"]),
            target=target, key=key, authored_param="bonusPercent",
        )
        source = f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].params"
        ctx.receipts[-1]["authoredPaths"] = [
            f"{source}.phase", f"{source}.damageClass", f"{source}.bonusPercent",
        ]
        return
    raise AssertionError(f"unhandled item capability {fn}")


def _compile_entity_call(
    ctx: _CompileContext,
    call: Mapping[str, Any],
    *,
    entity: dict[str, Any],
    entity_index: int,
) -> None:
    fn = str(call.get("fn") or "")
    p = _copy_params(call)
    base = f"runtimeProgram.entities[{entity_index}]"

    def component(name: str) -> dict[str, Any]:
        return entity.setdefault(name, {})

    def project(target: dict[str, Any], prefix: str, values: Mapping[str, Any]) -> None:
        for source, value in values.items():
            spec = CAPABILITY_REGISTRY[fn].params[source]
            destination = spec.wire_name or source
            ctx.write(call=call, path=f"{prefix}.{destination}", value=spec.to_wire(value),
                      target=target, key=destination, authored_param=source)

    if fn == "configure_spawn":
        spawn = component("spawn")
        project(spawn, f"{base}.spawn", p)
        spawn["enabled"] = True
        ctx.write_derived(call=call, path=f"{base}.spawn.enabled", value=True, target=spawn, key="enabled", source=f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn")
        return
    if fn == "set_projectile_damage":
        damage = component("damage")
        project(damage, f"{base}.damage", p)
        damage["enabled"] = True
        ctx.write_derived(call=call, path=f"{base}.damage.enabled", value=True, target=damage, key="enabled", source=f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn")
        return
    if fn == "set_projectile_lifetime":
        ctx.write(call=call, path=f"{base}.lifetimeTicks", value=p["lifetimeTicks"], target=entity, key="lifetimeTicks")
        return
    if fn == "set_projectile_hitbox":
        project(component("hitbox"), f"{base}.hitbox", p)
        return
    if fn == "set_projectile_collision":
        project(component("collision"), f"{base}.collision", p)
        return
    if fn in MOVEMENT_OPCODE:
        movement = component("movement")
        source_fn = f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn"
        ctx.write_derived(call=call, path=f"{base}.movement.name", value=fn, target=movement, key="name", source=source_fn)
        ctx.write_derived(call=call, path=f"{base}.movement.code", value=MOVEMENT_OPCODE[fn], target=movement, key="code", source=source_fn)
        movement_params = movement.setdefault("params", {})
        project(movement_params, f"{base}.movement.params", p)
        return
    if fn in {"channel_beam", "charge_then_release", "target_and_fire"}:
        controller = component("controller")
        source_fn = f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn"
        ctx.write_derived(call=call, path=f"{base}.controller.name", value=fn, target=controller, key="name", source=source_fn)
        ctx.write_derived(call=call, path=f"{base}.controller.code", value=CONTROLLER_OPCODE[fn], target=controller, key="code", source=source_fn)
        if fn == "target_and_fire":
            targeting = component("targeting")
            for source_key, destination in {
                "shotEntity": "shotEntityId",
                "intervalTicks": "intervalTicks",
                "rangeTiles": "rangeTiles",
                "sameTargetBias": "sameTargetBias",
            }.items():
                ctx.write(call=call, path=f"{base}.targeting.{destination}", value=p[source_key], target=targeting, key=destination, authored_param=source_key)
        else:
            controller_params = controller.setdefault("params", {})
            for key, value in p.items():
                ctx.write(call=call, path=f"{base}.controller.params.{key}", value=value, target=controller_params, key=key)
        return
    if fn == "spawn_over_target":
        spawn = component("spawn")
        over_target = spawn.setdefault("overTarget", {})
        project(over_target, f"{base}.spawn.overTarget", p)
        return
    if fn == "emit_light_while_active":
        project(component("light"), f"{base}.light", p)
        return
    if fn in EVENT_ACTION_OPCODE:
        events = entity.setdefault("events", [])
        event_row: dict[str, Any] = {
            "id": str(call.get("id") or ""),
            "event": p.pop("event"),
            "action": fn,
            "actionCode": EVENT_ACTION_OPCODE[fn],
        }
        if fn == "spawn_entity_on_event":
            event_row["entityId"] = p.pop("entity")
        if fn == "move_owner_on_event":
            event_row["mode"] = "blink_to_event_position"  # C# DTO discriminator; not an authored branch
        event_row.update(p)
        events.append(event_row)
        event_index = len(events) - 1
        for key, value in event_row.items():
            if key == "id":
                continue
            if key in {"action", "actionCode"} or (fn == "move_owner_on_event" and key == "mode"):
                authored_path = f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn"
            elif key == "entityId":
                authored_path = f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].params.entity"
            else:
                authored_path = f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].params.{key}"
            ctx.receipts.append({
                "callId": str(call.get("id") or ""),
                "fn": fn,
                "authoredPath": authored_path,
                "finalPath": f"{base}.events[{event_index}].{key}",
                "value": copy.deepcopy(value),
                "status": "technical_projection" if key in {"action", "actionCode"} or (fn == "move_owner_on_event" and key == "mode") else "delivered",
            })
        return
    raise AssertionError(f"unhandled runtime entity capability {fn}")


def compile_runtime_program(document: Mapping[str, Any]) -> dict[str, Any]:
    validation = assert_valid_runtime_program(document)
    out = copy.deepcopy(dict(document))
    authored_program = _dict(out.get("runtimeProgram"))
    authored_entities = [dict(row) for row in authored_program.get("entities", []) if isinstance(row, Mapping)]
    calls = [dict(row) for row in authored_program.get("calls", []) if isinstance(row, Mapping)]
    for index, call in enumerate(calls):
        call["_sourceIndex"] = index

    item_entity = next(row for row in authored_entities if row.get("kind") == "item_body")
    item_entity_id = str(item_entity["id"])
    primary_entity_id = authored_primary_entity_id(authored_program)
    primary_entity_source_index, primary_entity = next(
        (index, row)
        for index, row in enumerate(authored_entities)
        if str(row.get("id") or "") == primary_entity_id
    )
    primary_owner = primary_owner_for_kind(str(primary_entity.get("kind") or ""))
    ctx = _CompileContext(receipts=[])
    ctx.receipts.append(primary_owner_receipt(
        source_index=primary_entity_source_index,
        owner=primary_owner,
    ))
    binding_sources = [
        (index, copy.deepcopy(dict(source)))
        for index, source in enumerate(authored_program.get("bindings") or [])
        if isinstance(source, Mapping)
    ]
    def binding_source_sort_key(pair: tuple[int, dict[str, Any]]) -> str:
        return str(pair[1].get("id") or "")

    binding_sources.sort(key=binding_source_sort_key)
    placement_calls_by_id = {
        str(call["id"]): call
        for call in calls
        if str(call.get("fn") or "") == "configure_placeable"
    }
    bindings: list[dict[str, Any]] = []
    for source_index, authored_binding in binding_sources:
        binding = project_to_wire(
            authored_binding,
            placement_calls_by_id=placement_calls_by_id,
        )
        binding["role"] = primary_binding_role(primary_entity_id, binding_target_id(authored_binding))
        final_index = len(bindings)
        bindings.append(binding)
        ctx.receipts.append(primary_binding_role_receipt(
            source_index=source_index,
            final_index=final_index,
            role=binding["role"],
        ))
        if action_kind(authored_binding) == "place_item":
            call = placement_calls_by_id[placement_call_id(authored_binding)]
            source_call_index = int(call["_sourceIndex"])
            raw_params = call.get("params")
            params = raw_params if isinstance(raw_params, Mapping) else {}
            for key, value in params.items():
                ctx.receipts.append({
                    "callId": str(call["id"]),
                    "fn": "configure_placeable",
                    "authoredPath": f"runtimeProgram.calls[{source_call_index}].params.{key}",
                    "finalPath": f"runtimeProgram.bindings[{final_index}].usePolicy.action.placement.{key}",
                    "value": copy.deepcopy(value),
                    "status": "delivered",
                })
    entities: list[dict[str, Any]] = []
    entity_index_by_id: dict[str, int] = {}
    for source_index, source in enumerate(authored_entities):
        entity_id = str(source["id"])
        kind = str(source["kind"])
        entity_index = len(entities)
        visual_role = VISUAL_ROLE_BY_ENTITY_KIND[kind]
        entity_index_by_id[entity_id] = entity_index
        entities.append({
            "id": entity_id,
            "kind": kind,
            "visualRole": visual_role,
            "events": [],
            "visual": {"role": visual_role},
        })
        for final_path in (
            f"runtimeProgram.entities[{entity_index}].visualRole",
            f"runtimeProgram.entities[{entity_index}].visual.role",
        ):
            ctx.receipts.append({
                "lowererId": "entity_kind_to_visual_role",
                "authoredPaths": [f"runtimeProgram.entities[{source_index}].kind"],
                "finalPath": final_path,
                "value": visual_role,
                "status": "technical_projection",
            })

    runtime: dict[str, Any] = {
        "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        "schema": RUNTIME_WIRE_SCHEMA,
        "itemEntityId": item_entity_id,
        "primaryEntityId": primary_entity_id,
        "primaryOwner": primary_owner,
        "limits": {
            "maxEntityCount": MAX_RUNTIME_ENTITIES,
            "maxChildDepth": MAX_CHILD_DEPTH,
            "maxEventSpawnsPerActivation": MAX_EVENT_SPAWNS_PER_ACTIVATION,
        },
        "entities": entities,
        "bindings": bindings,
    }
    gameplay: dict[str, Any] = {"kind": str(out.get("category") or "generic")}
    accessory: dict[str, Any] = {"enabled": False}
    armor: dict[str, Any] = {"enabled": False}
    equipment_configs = {str(call.get("fn")) for call in calls
                         if call.get("fn") in {"configure_accessory", "configure_armor"}}
    equipment_config = (
        "armor" if equipment_configs == {"configure_armor"} else
        "accessory" if equipment_configs == {"configure_accessory"} else ""
    )
    for call in calls:
        target = str(call.get("target") or "")
        entity_index = entity_index_by_id[target]
        compiled_entity = entities[entity_index]
        fn = str(call.get("fn") or "")
        if fn == "configure_placeable":
            continue
        if target == item_entity_id and fn not in EVENT_ACTION_OPCODE:
            _compile_item_call(
                ctx,
                call,
                gameplay=gameplay,
                accessory=accessory,
                armor=armor,
                runtime=runtime,
                item_entity=compiled_entity,
                entity_index=entity_index,
                equipment_config=equipment_config,
            )
        else:
            _compile_entity_call(ctx, call, entity=compiled_entity, entity_index=entity_index)

    # Canonical ordering makes cache/network fingerprints stable without changing semantics.
    for entity_index, entity in enumerate(entities):
        entity["events"] = sorted(entity.get("events") or [], key=lambda row: str(row.get("id") or ""))
        event_index_by_id = {
            str(event.get("id") or ""): event_index
            for event_index, event in enumerate(entity["events"])
        }
        prefix = f"runtimeProgram.entities[{entity_index}].events["
        for receipt in ctx.receipts:
            final_path = str(receipt.get("finalPath") or "")
            if not final_path.startswith(prefix):
                continue
            event_id = str(receipt.get("callId") or "")
            if event_id not in event_index_by_id:
                raise RuntimeError(f"event receipt references absent event {event_id!r}")
            suffix = final_path[len(prefix):].split("]", 1)[1]
            receipt["finalPath"] = f"{prefix}{event_index_by_id[event_id]}]{suffix}"
    runtime["bindings"] = sorted(runtime["bindings"], key=lambda row: str(row.get("id") or ""))

    lowering_audit = audit_compiler_receipts(
        ctx.receipts,
        authored_document=document,
        final_document={"runtimeProgram": runtime, "gameplay": gameplay, "accessory": accessory, "armor": armor},
    )
    if not lowering_audit["ok"]:
        raise RuntimeError(f"technical lowerer wrote undeclared fields: {lowering_audit['violations'][:8]}")

    # runtimeContract is compiler-owned technical provenance only. The Author no
    # longer emits prose claims or parent synthesis into this namespace.
    contract: dict[str, Any] = {}
    contract["compiledSchema"] = RUNTIME_WIRE_SCHEMA
    contract["runtimeApiVersion"] = RUNTIME_PROGRAM_API_VERSION
    contract["finalWireReceipts"] = ctx.receipts
    contract["validation"] = validation
    contract["technicalLoweringAudit"] = lowering_audit

    out["runtimeProgram"] = runtime
    out["runtimeContract"] = contract
    out["gameplay"] = gameplay
    out["accessory"] = accessory
    out["armor"] = armor
    out.pop("attack", None)
    out.pop("runtimePlan", None)
    out.pop("runtimeCompiled", None)
    out.pop("_authorItemRaw", None)
    return out


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
    bindings = tuple(row for row in runtime.get("bindings") or [] if isinstance(row, Mapping))
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


__all__ = [
    "compile_runtime_program",
    "runtime_event_inventory",
    "runtime_visual_roles",
]
