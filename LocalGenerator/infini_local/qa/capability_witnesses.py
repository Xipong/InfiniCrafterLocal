from __future__ import annotations

"""Automatically generated vertical-slice witnesses for every public capability."""

from copy import deepcopy
from typing import Any

from infini_local.core.runtime_authoring import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    EVENT_CAPABILITIES,
    MOVEMENT_CAPABILITIES,
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
    "handPose": "one_handed", "heldSpriteVisibilityHint": "immediate",
}
_SPAWN = {"speedPxPerUpdate": 8.0, "count": 1, "spreadRadians": 0.0, "offsetPx": 0, "aim": "cursor", "placement": "item_use_origin"}
_DAMAGE = {"damageClass": "generic", "damage": 20, "knockback": 3.0, "ownerHitCheck": False}
_HITBOX = {"widthPx": 16, "heightPx": 16, "drawScale": 1.0, "hitboxScale": 1.0}
_COLLISION = {"tileCollide": True, "ignoreWater": False, "bounceCount": 0, "pierce": 1, "extraUpdates": 0, "npcImmunityMode": "local", "localNpcHitCooldownEngineUnits": 10}


def _value(spec: ParamSpec, name: str) -> Any:
    if spec.enum:
        return deepcopy(spec.enum[0])
    if spec.kind == "boolean":
        return False
    if spec.kind == "integer":
        base = spec.minimum if spec.minimum is not None else 1
        return int(max(spec.multiple_of or 1, base))
    if spec.kind == "number":
        base = spec.minimum if spec.minimum is not None else 0.5
        return float(max(spec.multiple_of or 0.1, base))
    if spec.kind == "string":
        return "witness"
    raise ValueError(f"unsupported parameter kind {spec.kind!r}")


def _params(fn: str) -> dict[str, Any]:
    spec = CAPABILITY_REGISTRY[fn]
    out = {name: _value(param, name) for name, param in spec.params.items() if param.required}
    special: dict[str, dict[str, Any]] = {
        "configure_item_stats": deepcopy(_ITEM_BASE_STATS),
        "configure_item_use": deepcopy(_ITEM_BASE_USE),
        "configure_vanilla_ammo_item": {"ammoCategory": "arrow", "projectileId": 1, "notAmmo": False},
        "restore_resources_on_use": {"healLife": 20, "healMana": 0, "usesPotionRules": False},
        "apply_generated_buff_on_use": {
            "durationTicks": 60, "miningSpeedMultiplier": 1.0, "lightStrength": 0.25,
            "lightColor": "white", "oreSenseEnabled": False, "moveSpeedBonusFactor": 0.0,
            "jumpSpeedBonusPxPerTick": 0.0, "manaRegenBonusPoints": 0, "lifeRegenHpPerSecond": 0,
        },
        "configure_placeable": {"tileId": 4, "wallId": -1, "placeStyle": 0},
        "require_use_condition": {"mode": "grounded"},
        "move_player_on_use": {"mode": "recall_home", "rangeTiles": 0, "cooldownTicks": 60, "safeTileOnly": True},
        "configure_accessory": {"defensePoints": 1},
        "add_equipment_damage_bonus": {"phase": "equipped", "damageClass": "melee", "bonusPercent": 15},
        "configure_armor": {
            "slot": "head", "setKey": "witness_set", "defensePoints": 1,
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
        "move_owner_on_event": {"event": "on_hit", "rangeTiles": 8, "cooldownTicks": 60, "safeTileOnly": True},
    }
    out.update(deepcopy(special.get(fn, {})))
    return out


def _call(call_id: str, fn: str, target: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": call_id, "fn": fn, "target": target, "params": deepcopy(_params(fn) if params is None else params)}


def _binding(
    binding_id: str,
    input_kind: str,
    action_kind: str,
    target: str,
    *,
    placement_call_id: str = "",
    contact_damage: bool = False,
) -> dict[str, Any]:
    action: dict[str, Any] = {"kind": action_kind, "targetId": target}
    if placement_call_id:
        action["placementCallId"] = placement_call_id
    return {
        "id": binding_id,
        "input": input_kind,
        "usePolicy": {
            "action": action,
            "stackCost": 1 if action_kind == "place_item" else 0,
            "contactDamage": contact_damage,
        },
    }


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
            bindings.append(_binding("witness_binding", "primary_use", "use_item_body", "item"))
        else:
            calls.append(_call("item_use", "configure_item_use", "item", _ITEM_BASE_USE))
            if fn == "add_equipment_damage_bonus":
                calls.append(_call("base_equipment", "configure_accessory", "item", {"defensePoints": 1}))
            calls.append(_call("witness_call", fn, "item"))
            action = "use_item_body"
            input_kind = "primary_use"
            if fn == "configure_placeable":
                action = "place_item"
            elif fn in {"configure_accessory", "configure_armor", "add_equipment_damage_bonus"}:
                action = "equip_passive"; input_kind = "equipped"
            elif fn in BINDING_ACTION_REGISTRY["apply_item_effects"].required_item_capabilities_any_of:
                action = "apply_item_effects"
            bindings.append(_binding(
                "witness_binding",
                input_kind,
                action,
                "item",
                placement_call_id="witness_call" if action == "place_item" else "",
                contact_damage=fn in {"configure_item_contact_hitbox", "configure_tool"},
            ))
    else:
        if not any(row["fn"] == "configure_item_use" for row in calls):
            item_use = deepcopy(_ITEM_BASE_USE)
            if fn in {"channel_beam", "charge_then_release"}:
                item_use["channel"] = True
                item_use["heldSpriteVisibilityHint"] = "on_release"
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
        bindings.append(_binding("witness_binding", "primary_use", "spawn_entity", witness_target))

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

    primary_target = "item" if item_target and not projectile_target else witness_target

    return {
        "name": f"Capability Witness {fn}",
        "category": "generic",
        "concept": {
            "literalSynthesis": "A minimal literal test object.",
            "coreMechanic": f"Execute {fn} through its public typed contract.",
            "parentAContribution": "test body",
            "parentBContribution": "test mechanism",
            "playerExperience": "The selected capability runs without inferred archetype behaviour.",
            "plannedPlayerActions": [{
                "input": str(bindings[0]["input"]) if bindings else "passive_or_event",
                "intent": f"Execute {fn} through its public typed contract.",
            }],
        },
        "realization": {
            "description": f"A minimal runtime witness executing {fn}.",
            "playerExperience": "The selected capability runs without inferred archetype behaviour.",
            "selfEvaluation": {
                "planVsProgram": {
                    "verdict": "aligned",
                    "summary": "The witness draft selects the same public capability emitted by the program.",
                    "actionChecks": [{
                        "plannedIntent": f"Execute {fn} through its public typed contract.",
                        "implementedBehavior": f"The runtime program contains the {fn} capability call.",
                        "runtimeRefs": ["witness_call"],
                        "result": "aligned",
                        "intentionality": "intentional",
                        "reason": "The witness directly emits the selected public capability.",
                    }],
                },
                "programVsReport": {
                    "verdict": "aligned",
                    "summary": "The witness report names the exact emitted capability.",
                    "behaviorChecks": [{
                        "runtimeRefs": ["witness_call"],
                        "programBehavior": f"The runtime executes {fn}.",
                        "reportedBehavior": f"The report says that the runtime executes {fn}.",
                        "result": "aligned",
                        "reason": "The report names the exact cited capability.",
                    }],
                },
            },
        },
        "runtimeProgram": {
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
            "schema": RUNTIME_PROGRAM_SCHEMA,
            "primaryEntityId": primary_target,
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
