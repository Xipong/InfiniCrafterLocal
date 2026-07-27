from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from infini_local.core.runtime_authoring.capability_registry import (
    CONTROLLER_OPCODE,
    EVENT_ACTION_OPCODE,
    MOVEMENT_OPCODE,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_WIRE_SCHEMA,
    VISUAL_ROLE_BY_ENTITY_KIND,
)
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

    def write(self, *, call: Mapping[str, Any], path: str, value: Any, target: MutableMapping[str, Any], key: str) -> None:
        target[key] = copy.deepcopy(value)
        self.receipts.append({
            "callId": str(call.get("id") or ""),
            "fn": str(call.get("fn") or ""),
            "authoredPath": f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].params.{key}",
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
) -> None:
    fn = str(call.get("fn") or "")
    p = _copy_params(call)

    def project(target: dict[str, Any], path_prefix: str, mapping: Mapping[str, str]) -> None:
        for source, destination in mapping.items():
            if source in p:
                ctx.write(call=call, path=f"{path_prefix}.{destination}", value=p[source], target=target, key=destination)

    if fn == "configure_item_stats":
        project(gameplay, "gameplay", {
            "damageClass": "damageClass",
            "damage": "damage",
            "knockback": "knockback",
            "useTimeTicks": "useTime",
            "useAnimationTicks": "useAnimation",
            "manaCost": "manaCost",
            "rarity": "rarity",
            "valueCopper": "value",
            "maxStack": "maxStack",
            "craftYield": "craftYield",
            "widthPx": "width",
            "heightPx": "height",
            "scale": "itemScale",
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
            "channel": "channelUse",
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
    if fn == "enable_item_contact_damage":
        contact = runtime.setdefault("itemContact", {"enabled": True})
        ctx.write_derived(
            call=call,
            path="runtimeProgram.itemContact.enabled",
            value=True,
            target=contact,
            key="enabled",
            source=f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn",
        )
        project(contact, "runtimeProgram.itemContact", {
            "hitboxScale": "hitboxScale",
            "contactForgivenessPx": "contactForgivenessPx",
        })
        return
    if fn == "configure_consumption":
        project(gameplay, "gameplay", {
            "consumable": "consumable",
            "consumeChancePercent": "consumeChancePercent",
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
            "oreSenseRadiusTiles": "oreSenseRadiusTiles",
            "movementSpeed": "movementSpeed",
            "jumpBoost": "jumpBoost",
            "manaRegen": "manaRegen",
            "lifeRegen": "lifeRegen",
        })
        return
    if fn == "configure_tool":
        project(gameplay, "gameplay", {
            "pickPower": "pickPower",
            "axePower": "axePower",
            "hammerPower": "hammerPower",
            "miningSpeedScale": "miningSpeedScale",
        })
        return
    if fn == "configure_placeable":
        project(gameplay, "gameplay", {"tileId": "createTile", "wallId": "createWall", "placeStyle": "placeStyle"})
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
        project(accessory, "accessory", {
            "defense": "defense", "maxLife": "maxLife", "maxMana": "maxMana",
            "lifeRegen": "lifeRegen", "manaRegen": "manaRegen", "movementSpeed": "movementSpeed",
            "genericDamage": "genericDamage", "genericCrit": "genericCrit", "endurance": "endurance",
            "minionSlots": "minionSlots", "sentrySlots": "sentrySlots",
            "lightStrength": "lightStrength", "lightColor": "lightColorName",
        })
        return
    if fn == "configure_armor":
        armor["enabled"] = True
        ctx.write_derived(call=call, path="armor.enabled", value=True, target=armor, key="enabled", source=f"runtimeProgram.calls[{call.get('_sourceIndex', '?')}].fn")
        project(armor, "armor", {
            "slot": "slot", "setKey": "setKey", "defense": "defense", "maxLife": "maxLife", "maxMana": "maxMana",
            "movementSpeed": "movementSpeed", "genericDamage": "genericDamage", "genericCrit": "genericCrit",
            "setBonusText": "setBonusText", "setBonusGenericDamage": "setBonusGenericDamage",
            "setBonusMovementSpeed": "setBonusMovementSpeed", "setBonusLifeRegen": "setBonusLifeRegen",
        })
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
        for key, value in values.items():
            ctx.write(call=call, path=f"{prefix}.{key}", value=value, target=target, key=key)

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
        for key, value in p.items():
            ctx.write(call=call, path=f"{base}.movement.params.{key}", value=value, target=movement_params, key=key)
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
                ctx.write(call=call, path=f"{base}.targeting.{destination}", value=p[source_key], target=targeting, key=destination)
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
        event_row.update(p)
        events.append(event_row)
        event_index = len(events) - 1
        for key, value in event_row.items():
            if key == "id":
                continue
            if key in {"action", "actionCode"}:
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
                "status": "technical_projection" if key == "actionCode" else "delivered",
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
    bindings: list[dict[str, Any]] = []
    for source_index, binding in binding_sources:
        binding["role"] = primary_binding_role(primary_entity_id, str(binding.get("target") or ""))
        final_index = len(bindings)
        bindings.append(binding)
        ctx.receipts.append(primary_binding_role_receipt(
            source_index=source_index,
            final_index=final_index,
            role=binding["role"],
        ))
    entities: list[dict[str, Any]] = []
    entity_index_by_id: dict[str, int] = {}
    for source in authored_entities:
        entity_id = str(source["id"])
        kind = str(source["kind"])
        entity_index_by_id[entity_id] = len(entities)
        entities.append({
            "id": entity_id,
            "kind": kind,
            "visualRole": VISUAL_ROLE_BY_ENTITY_KIND[kind],
            "events": [],
            "visual": {"role": VISUAL_ROLE_BY_ENTITY_KIND[kind]},
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
    for call in calls:
        target = str(call.get("target") or "")
        entity_index = entity_index_by_id[target]
        compiled_entity = entities[entity_index]
        fn = str(call.get("fn") or "")
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
            )
        else:
            _compile_entity_call(ctx, call, entity=compiled_entity, entity_index=entity_index)

    # Canonical ordering makes cache/network fingerprints stable without changing semantics.
    for entity in entities:
        entity["events"] = sorted(entity.get("events") or [], key=lambda row: str(row.get("id") or ""))
    runtime["bindings"] = sorted(runtime["bindings"], key=lambda row: str(row.get("id") or ""))

    lowering_audit = audit_compiler_receipts(ctx.receipts)
    if not lowering_audit["ok"]:
        raise RuntimeError(f"technical lowerer wrote undeclared fields: {lowering_audit['violations'][:8]}")

    contract = _dict(out.get("runtimeContract"))
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
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, Mapping):
            continue
        entity_id = str(entity.get("id") or "")
        rows.append({"entityId": entity_id, "event": "on_spawn"})
        if _dict(entity.get("damage")).get("enabled"):
            rows.extend(({"entityId": entity_id, "event": "on_hit"}, {"entityId": entity_id, "event": "on_crit"}))
        if _dict(entity.get("collision")).get("tileCollide"):
            rows.append({"entityId": entity_id, "event": "on_tile_collision"})
        rows.extend(({"entityId": entity_id, "event": "on_expire"}, {"entityId": entity_id, "event": "on_kill"}))
        for event in entity.get("events") or []:
            if isinstance(event, Mapping):
                rows.append({"entityId": entity_id, "event": str(event.get("event") or "")})
    for binding in runtime.get("bindings") or []:
        if isinstance(binding, Mapping):
            rows.append({"entityId": str(binding.get("target") or ""), "event": "on_use", "input": str(binding.get("input") or "")})
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
