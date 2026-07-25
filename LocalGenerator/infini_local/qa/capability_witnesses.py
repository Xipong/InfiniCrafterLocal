from __future__ import annotations

"""Automatically generated vertical-slice witnesses for every public capability."""

from copy import deepcopy
from typing import Any

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    EVENT_CAPABILITIES,
    MOVEMENT_CAPABILITIES,
    RUNTIME_CONTRACT_SCHEMA,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    compile_runtime_program,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.capability_registry import ParamSpec


_ITEM_BASE_STATS = {
    "damageClass": "generic", "damage": 20, "knockback": 3.0,
    "useTimeTicks": 20, "useAnimationTicks": 20, "manaCost": 0,
    "rarity": 1, "valueCopper": 1000, "maxStack": 1, "craftYield": 1,
    "widthPx": 24, "heightPx": 24, "scale": 1.0,
}
_ITEM_BASE_USE = {
    "useStyle": "shoot", "autoReuse": False, "useTurn": True,
    "hideUseGraphic": False, "disableMeleeHitbox": True, "channel": False,
    "holdoutOffsetX": 0, "holdoutOffsetY": 0,
    "handPose": "one_handed", "releaseTiming": "immediate",
}
_SPAWN = {"speedPxPerTick": 8.0, "count": 1, "spreadRadians": 0.0, "offsetPx": 0, "aim": "cursor", "placement": "item_use_origin"}
_DAMAGE = {"damageClass": "generic", "damage": 20, "knockback": 3.0, "ownerHitCheck": False}
_HITBOX = {"widthPx": 16, "heightPx": 16, "drawScale": 1.0, "hitboxScale": 1.0}
_COLLISION = {"tileCollide": True, "ignoreWater": False, "bounceCount": 0, "pierce": 1, "extraUpdates": 0, "npcImmunityMode": "local", "localNpcHitCooldownTicks": 10}


def _value(spec: ParamSpec, name: str) -> Any:
    if spec.enum:
        return deepcopy(spec.enum[0])
    if spec.kind == "boolean":
        return False
    if spec.kind == "integer":
        base = spec.minimum if spec.minimum is not None else 1
        return int(max(1, base))
    if spec.kind == "number":
        base = spec.minimum if spec.minimum is not None else 0.5
        return float(max(0.1, base))
    if spec.kind == "string":
        return "witness"
    raise ValueError(f"unsupported parameter kind {spec.kind!r}")


def _params(fn: str) -> dict[str, Any]:
    spec = CAPABILITY_REGISTRY[fn]
    out = {name: _value(param, name) for name, param in spec.params.items() if param.required}
    special: dict[str, dict[str, Any]] = {
        "configure_item_stats": deepcopy(_ITEM_BASE_STATS),
        "configure_item_use": deepcopy(_ITEM_BASE_USE),
        "configure_consumption": {"consumable": True, "consumeChancePercent": 100},
        "configure_vanilla_ammo_item": {"ammoCategory": "arrow", "projectileId": 1, "notAmmo": False},
        "restore_resources_on_use": {"healLife": 20, "healMana": 0, "potionSickness": False},
        "apply_generated_buff_on_use": {
            "durationTicks": 60, "miningSpeedMultiplier": 1.0, "lightStrength": 0.25,
            "lightColor": "white", "oreSenseRadiusTiles": 0, "movementSpeed": 0.0,
            "jumpBoost": 0.0, "manaRegen": 0, "lifeRegen": 0,
        },
        "configure_placeable": {"tileId": 4, "wallId": -1, "placeStyle": 0},
        "require_use_condition": {"mode": "grounded"},
        "move_player_on_use": {"mode": "recall_home", "rangeTiles": 0, "cooldownTicks": 60, "safeTileOnly": True},
        "configure_armor": {
            "slot": "head", "setKey": "witness_set", "defense": 1, "maxLife": 0,
            "maxMana": 0, "movementSpeed": 0.0, "genericDamage": 0.0, "genericCrit": 0.0,
        },
        "configure_spawn": deepcopy(_SPAWN),
        "set_projectile_damage": deepcopy(_DAMAGE),
        "set_projectile_lifetime": {"lifetimeTicks": 120},
        "set_projectile_hitbox": deepcopy(_HITBOX),
        "set_projectile_collision": deepcopy(_COLLISION),
        "move_straight": {},
        "target_and_fire": {"shotEntity": "witness_shot", "intervalTicks": 30, "rangeTiles": 20, "sameTargetBias": 0.2},
        "spawn_entity_on_event": {"event": "on_hit", "entity": "witness_child", "count": 1, "spreadRadians": 0.0, "damageMultiplier": 0.5, "delayTicks": 0},
        "apply_status_on_event": {"event": "on_hit", "buffId": 20, "durationTicks": 60},
        "damage_area_on_event": {"event": "on_hit", "radiusPx": 48, "damageMultiplier": 0.5},
        "chain_damage_on_event": {"event": "on_hit", "count": 1, "rangeTiles": 8, "damageMultiplier": 0.5},
        "pull_on_event": {"event": "on_hit", "mode": "target_to_owner", "strength": 2.0, "radiusTiles": 8, "periodTicks": 12},
        "heal_owner_on_event": {"event": "on_hit", "damageFraction": 0.1, "maxHeal": 5},
        "move_owner_on_event": {"event": "on_hit", "mode": "blink_to_entity", "rangeTiles": 8, "cooldownTicks": 60, "safeTileOnly": True},
    }
    out.update(deepcopy(special.get(fn, {})))
    return out


def _call(call_id: str, fn: str, target: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": call_id, "fn": fn, "target": target, "params": deepcopy(_params(fn) if params is None else params)}


def build_capability_witness(fn: str) -> dict[str, Any]:
    if fn not in CAPABILITY_REGISTRY:
        raise KeyError(fn)
    cap = CAPABILITY_REGISTRY[fn]
    entities: list[dict[str, Any]] = [{"id": "item", "kind": "item_body"}]
    bindings: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    if fn == "configure_item_stats":
        calls.append(_call("witness_call", fn, "item"))
    else:
        calls.append(_call("item_stats", "configure_item_stats", "item", _ITEM_BASE_STATS))

    item_target = "item_body" in cap.target_kinds
    projectile_target = not item_target or fn in EVENT_CAPABILITIES
    witness_target = "item"

    if item_target and not projectile_target:
        if fn == "configure_item_stats":
            pass
        elif fn == "configure_item_use":
            calls.append(_call("witness_call", fn, "item"))
            bindings.append({"id": "witness_binding", "input": "primary_use", "action": "use_item_body", "target": "item"})
        else:
            calls.append(_call("item_use", "configure_item_use", "item", _ITEM_BASE_USE))
            if fn == "configure_vanilla_ammo_item":
                calls.append(_call("ammo_consumption", "configure_consumption", "item", {"consumable": True, "consumeChancePercent": 100}))
            calls.append(_call("witness_call", fn, "item"))
            action = "use_item_body"
            input_kind = "primary_use"
            if fn == "configure_placeable":
                action = "place_item"
            elif fn in {"configure_accessory", "configure_armor"}:
                action = "equip_passive"; input_kind = "equipped"
            bindings.append({"id": "witness_binding", "input": input_kind, "action": action, "target": "item"})
    else:
        if not any(row["fn"] == "configure_item_use" for row in calls):
            item_use = deepcopy(_ITEM_BASE_USE)
            if fn in {"channel_beam", "charge_then_release"}:
                item_use["channel"] = True
                item_use["releaseTiming"] = "on_release"
            calls.append(_call("item_use", "configure_item_use", "item", item_use))
        if fn == "target_and_fire":
            kind = "stationary_projectile"
        elif cap.target_kinds == ("owner_attached_projectile",):
            kind = "owner_attached_projectile"
        else:
            kind = next((kind for kind in cap.target_kinds if kind != "item_body"), "free_projectile")
            if kind in {"field", "temporary_helper", "stationary_projectile"} and fn not in {"target_and_fire"}:
                kind = "free_projectile"
        witness_target = "witness_entity"
        entities.append({"id": witness_target, "kind": kind})
        bindings.append({"id": "witness_binding", "input": "primary_use", "action": "spawn_entity", "target": witness_target})

        base = {
            "configure_spawn": _SPAWN,
            "set_projectile_damage": _DAMAGE,
            "set_projectile_lifetime": {"lifetimeTicks": 120},
            "set_projectile_hitbox": _HITBOX,
            "set_projectile_collision": _COLLISION,
        }
        for base_fn, params in base.items():
            if fn == base_fn:
                calls.append(_call("witness_call", fn, witness_target))
            else:
                calls.append(_call(f"base_{base_fn}", base_fn, witness_target, params))

        if fn == "target_and_fire":
            entities.append({"id": "witness_shot", "kind": "child_projectile"})
            for base_fn, params in base.items():
                calls.append(_call(f"shot_{base_fn}", base_fn, "witness_shot", params))
            calls.append(_call("shot_motion", "move_straight", "witness_shot", {}))
        if fn == "spawn_entity_on_event":
            entities.append({"id": "witness_child", "kind": "child_projectile"})
            for base_fn, params in base.items():
                calls.append(_call(f"child_{base_fn}", base_fn, "witness_child", params))
            calls.append(_call("child_motion", "move_straight", "witness_child", {}))

        if fn in MOVEMENT_CAPABILITIES or fn in {"channel_beam", "charge_then_release", "target_and_fire"}:
            # Charge/release owns charge positioning but the authored post-release
            # trajectory remains explicit. Channel beam and target/fire own their
            # complete position lifecycle and do not require a movement component.
            if fn == "charge_then_release":
                calls.append(_call("base_motion", "move_straight", witness_target, {}))
            if not any(row["id"] == "witness_call" for row in calls):
                calls.append(_call("witness_call", fn, witness_target))
        else:
            moving = kind in {"owner_attached_projectile", "free_projectile", "child_projectile"}
            if moving:
                calls.append(_call("base_motion", "move_straight", witness_target, {}))
            if not any(row["id"] == "witness_call" for row in calls):
                calls.append(_call("witness_call", fn, witness_target))

    return {
        "name": f"Capability Witness {fn}",
        "tooltip": f"Executable vertical-slice witness for {fn}.",
        "category": "generic",
        "concept": {
            "literalSynthesis": "A minimal literal test object.",
            "coreMechanic": f"Execute {fn} through its public typed contract.",
            "parentAContribution": "test body",
            "parentBContribution": "test mechanism",
            "playerExperience": "The selected capability runs without inferred archetype behaviour.",
        },
        "runtimeContract": {
            "schema": RUNTIME_CONTRACT_SCHEMA,
            "parentSynthesis": {
                "composition": "Minimal vertical-slice witness.",
                "parentA": {"facts": ["test body"], "runtimeRoles": ["literal body"]},
                "parentB": {"facts": ["test mechanism"], "runtimeRoles": ["literal mechanism"]},
            },
            "claims": [{"id": "witness_claim", "kind": "gameplay", "text": f"The runtime executes {fn}.", "backedBy": ["witness_call"]}],
        },
        "runtimeProgram": {
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
            "schema": RUNTIME_PROGRAM_SCHEMA,
            "entities": entities,
            "bindings": bindings,
            "calls": calls,
        },
    }


def capability_vertical_slice_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    ok = True
    for fn in CAPABILITY_REGISTRY:
        authored = build_capability_witness(fn)
        author = validate_runtime_program(authored)
        row: dict[str, Any] = {"fn": fn, "authorValid": bool(author.get("ok")), "authorErrors": author.get("errors") or []}
        if author.get("ok"):
            compiled = compile_runtime_program(authored)
            wire = validate_runtime_wire(compiled)
            row["wireValid"] = bool(wire.get("ok"))
            row["wireErrors"] = wire.get("errors") or []
            row["receiptCount"] = len(compiled["runtimeContract"]["finalWireReceipts"])
        else:
            row["wireValid"] = False
        row["ok"] = bool(row["authorValid"] and row["wireValid"])
        ok = ok and row["ok"]
        rows.append(row)
    return {"schema": "infini.capability-vertical-slice-report.v1", "ok": ok, "capabilityCount": len(rows), "rows": rows}


__all__ = ["build_capability_witness", "capability_vertical_slice_report"]
