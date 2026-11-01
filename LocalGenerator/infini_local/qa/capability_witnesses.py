from __future__ import annotations

"""Automatically generated vertical-slice witnesses for every public capability."""

from copy import deepcopy
from typing import Any

from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    EVENT_CAPABILITIES,
    MOVEMENT_CAPABILITIES,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
)
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.parameter_contract import ParamSpec
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

_ITEM_BASE_STATS = {
    "damageClass": "generic", "damage": 20, "knockback": 3.0,
    "useTimeSeconds": 20 / 60, "useAnimationSeconds": 20 / 60, "manaCost": 0,
    "rarity": 1, "valueCopper": 1000, "maxStack": 1, "craftYield": 1,
    "widthPx": 24, "heightPx": 24, "scale": 1.0,
}
_ITEM_BASE_USE = {
    "useStyle": "shoot", "autoReuse": False, "useTurn": True,
    "hideUseGraphic": False, "disableMeleeHitbox": True, "channel": False,
    "holdoutOffsetX": 0, "holdoutOffsetY": 0,
    "handPose": "one_handed", "customHeldSprite": "hidden",
}
_SPAWN = {"velocity": {"speed": 30.0}, "count": 1, "spreadRadians": 0.0, "offsetBlocks": 0, "aim": "cursor", "position": {"at": "activation_origin"}}
_DAMAGE = {"damageClass": "generic", "damage": 20, "knockback": 3.0, "ownerHitCheck": False}
_HITBOX = {"widthPx": 16, "heightPx": 16, "drawScale": 1.0, "hitboxScale": 1.0}
_COLLISION = {"tileCollide": True, "ignoreWater": False, "bounceCount": 0, "pierce": 1, "updatesPerTick": 1, "immunity": {"localCooldown": 10}}


def _value(spec: ParamSpec, name: str) -> Any:
    if spec.alternatives:
        return _value(spec.alternatives[0], name)
    if spec.kind == "object":
        return {key: _value(child, key) for key, child in spec.properties.items() if child.required}
    if spec.enum:
        return deepcopy(spec.enum[0])
    if spec.kind == "boolean":
        return False
    if spec.wire_kind:
        # Pick an admitted engine endpoint before the canonical QA inverse.
        # Every generated projectile witness explicitly declares N=1 below.
        base = max(1 if spec.projected_kind == "integer" else 0.1, spec.wire_minimum or 0)
        return spec.from_wire(base, updates_per_tick=1)
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
    for requirement in spec.requirements:
        if requirement.kind == "timing_pair_or_window":
            # Keep this canonical witness's already-established finite interval.
            # Dedicated timing tests also exercise the new window-only shape.
            for name in (requirement.param, requirement.other_param):
                out[name] = _value(spec.params[name], name)
    special: dict[str, dict[str, Any]] = {
        "item_stats": deepcopy(_ITEM_BASE_STATS),
        "item_use": deepcopy(_ITEM_BASE_USE),
        "ammo_item": {"ammoCategory": "arrow", "projectileId": 1, "notAmmo": False},
        "restore_resources_on_use": {"healLife": 20, "healMana": 0, "usesPotionRules": False},
        "generated_buff_on_use": {
            "duration": 1, "miningSpeedMultiplier": 1.0, "lightStrength": 0.25,
            "lightColor": "white", "oreSenseEnabled": False, "moveSpeedBonus": 0.0,
            "jumpSpeedBonus": 0.0, "manaRegen": 0, "lifeRegen": 0,
        },
        "place_tile": {"tileId": 4, "placeStyle": 0},
        "place_wall": {"wallId": 1, "placeStyle": 0},
        "placed_sprite": {"placementCallId": "native_placement"},
        "placed_light": {"placementCallId": "native_placement"},
        "placed_vfx": {"placementCallId": "native_placement", "minFrameY": 0, "maxFrameY": 32767},
        "use_condition": {"condition": "grounded"},
        "blink_on_use": {"mode": "blink_to_cursor", "range": 5, "cooldown": 1, "safeTileOnly": True},
        "recall_home_on_use": {"cooldown": 1},
        "accessory": {"defensePoints": 1},
        "equipment_damage_bonus": {"phase": "equipped", "damageClass": "melee", "bonusPercent": 15},
        "armor": {
            "slot": "head", "setKey": "witness_set", "defensePoints": 1,
        },
        "spawn": deepcopy(_SPAWN),
        "projectile_damage": deepcopy(_DAMAGE),
        "projectile_lifetime": {"lifetimeSeconds": 2},
        "projectile_hitbox": deepcopy(_HITBOX),
        "projectile_collision": deepcopy(_COLLISION),
        "move_straight": {},
        "set_owner_control": {"requireHeldItem": True},
        "target_and_fire": {"shotEntity": "witness_shot", "intervalSeconds": 0.5, "range": 20, "sameTargetBias": 0.2, "damageBasis": "authored_child", "knockbackBasis": "authored_child", "damageMultiplier": 1.0},
        "spawn_on_event": {"when": "on_hit", "entity": "witness_child", "count": 1, "spreadRadians": 0.0, "damageMultiplier": 0.5, "delay": 0, "damageBasis": "authored_child", "knockbackBasis": "authored_child"},
        "apply_status_on_event": {"when": "on_hit", "buffId": 20, "duration": 1},
        "npc_effect_on_event": {"when": "on_hit", "duration": 2, "damagePerSecond": 7.5, "defenseDelta": -4},
        "damage_nearby_on_event": {"when": "on_hit", "radius": 8, "maxTargets": 1, "damageMultiplier": 0.5},
        "damage_area_on_event": {"when": "on_hit", "radius": 3, "damageMultiplier": 0.5},
        "damage_nearest_on_event": {"when": "on_hit", "maxTargets": 1, "range": 8, "damageMultiplier": 0.5},
        "pull_on_event": {"when": "on_hit", "mode": "target_to_owner", "impulseBlocksPerSecond": 7.5, "radius": 8},
        "pull_owner_to_event_target": {"when": "on_hit", "impulseBlocksPerSecond": 7.5},
        "heal_owner_on_event": {"when": "on_hit", "damageFraction": 0.1, "maxHeal": 5},
        "move_owner_on_event": {"when": "on_hit", "range": 8, "cooldown": 1, "safeTileOnly": True},
        "spawn_at_hit": {"when": "on_hit", "entity": "witness_child", "count": 3, "damageMultiplier": 0.5, "delay": 0, "damageBasis": "authored_child", "knockbackBasis": "authored_child", "geometry": {"beforeProbability": 0.85, "hitboxMaxSideFactor": 0.6, "clearanceBlocks": 0.625, "beforeJitterRadius": 0.5, "beforeAngleJitter": 0.2, "afterFanSpread": 1.2, "ignoreTargetUpdates": 10}},
        "emit_to_targets_on_event": {"when": "on_hit", "entity": "witness_child", "stepCount": 2,
            "stepRangeTiles": 22.5, "selectionAnchor": "previous_target", "repeatPolicy": "allow_revisits",
            "requireLineOfSight": False, "ignoreTargetUpdates": 10, "delay": 0},
    }
    out.update(deepcopy(special.get(fn, {})))
    return out


def _call(call_id: str, fn: str, target: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {"id": call_id, "fn": fn, "target": target}
    if CAPABILITY_REGISTRY[fn].target_kinds == ("item_body",):
        row.pop("target")
    if CAPABILITY_REGISTRY[fn].params:
        row["params"] = deepcopy(_params(fn) if params is None else params)
    return row


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
    from infini_local.core.runtime_authoring.capability_registry import BINDING_ACTION_REGISTRY, INPUT_KIND_REGISTRY
    if BINDING_ACTION_REGISTRY[action_kind].target_kinds == ("item_body",):
        action.pop("targetId")
    if len(INPUT_KIND_REGISTRY[input_kind].allowed_actions) == 1:
        action.pop("kind")
    row = {
        "id": binding_id,
        "input": input_kind,
        **{
            "action": action,
            "stackCost": 1 if action_kind == "place_item" else 0,
            "contactDamage": contact_damage,
        },
    }

    if not action:
        row.pop("action")
    if input_kind not in {"primary_use", "alternate_use"} or action_kind == "place_item":
        row.pop("stackCost")
        row.pop("contactDamage")
    return row


def build_capability_witness(fn: str) -> dict[str, Any]:
    if fn not in CAPABILITY_REGISTRY or not CAPABILITY_REGISTRY[fn].author_visible:
        raise KeyError(fn)
    if fn in {"weapon_ammo", "end_projectiles"}:
        doc = build_capability_witness("move_straight")
        next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "witness_call")["id"] = "base_motion"
        if fn == "end_projectiles":
            doc["runtimeProgram"]["bindings"].append(_binding("command", "alternate_use", "use_item_body", "item"))
            doc["runtimeProgram"]["calls"].append(_call("witness_call", fn, "item", {
                "when": {"on": "on_use", "useInput": "alternate_use"}, "entity": "witness_entity",
            }))
            doc["runtimeProgram"]["calls"].append(_call("terminal_blast", "damage_nearby_on_event", "witness_entity", {
                "when": "on_kill", "radius": 3, "damageMultiplier": 0.5, "maxTargets": 8,
            }))
        else:
            doc["runtimeProgram"]["calls"].append(_call("witness_call", fn, "item"))
        doc["name"] = f"Capability Witness {fn}"
        doc["concept"]["coreMechanic"] = f"Execute {fn} through its public typed contract."
        doc["realization"]["description"] = f"A minimal runtime witness executing {fn}."
        return doc
    if fn == "generated_buff_on_event":
        doc = build_capability_witness("accessory")
        group = _params("generated_buff_on_use")
        group["effectGroupId"] = "reaction_buff"
        doc["runtimeProgram"]["calls"].extend([
            _call("reaction_effect", "generated_buff_on_use", "item", group),
            _call("witness_reaction", fn, "item", {"when": {"on": "on_hurt", "cooldown": 1}, "effectGroupId": "reaction_buff"}),
        ])
        next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "witness_call")["id"] = "base_equipment"
        doc["runtimeProgram"]["calls"][-1]["id"] = "witness_call"
        doc["name"] = f"Capability Witness {fn}"
        return doc
    cap = CAPABILITY_REGISTRY[fn]
    entities: list[dict[str, Any]] = [{"id": "item", "kind": "item_body"}]
    bindings: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    if fn == "item_stats":
        calls.append(_call("witness_call", fn, "item"))
    else:
        calls.append(_call("item_stats", "item_stats", "item", _ITEM_BASE_STATS))

    item_target = "item_body" in cap.target_kinds
    projectile_target = not item_target or fn in EVENT_CAPABILITIES
    witness_target = "item"

    if item_target and not projectile_target:
        if fn == "item_stats":
            pass
        elif cap.category == "item_inventory":
            calls.append(_call("witness_call", fn, "item"))
        elif fn == "item_use":
            calls.append(_call("witness_call", fn, "item"))
            bindings.append(_binding("witness_binding", "primary_use", "use_item_body", "item"))
        else:
            calls.append(_call("item_use", "item_use", "item", _ITEM_BASE_USE))
            if fn == "equipment_damage_bonus":
                calls.append(_call("base_equipment", "accessory", "item", {"defensePoints": 1}))
            calls.append(_call("witness_call", fn, "item"))
            if fn == "refresh_held_effect":
                effect = _params("generated_buff_on_use")
                effect["effectGroupId"] = _params(fn)["effectGroupId"]
                calls.append(_call("held_utility_effect", "generated_buff_on_use", "item", effect))
            action = "use_item_body"
            input_kind = "primary_use"
            if fn in {"place_tile", "place_wall"} or cap.category == "item_placed_body":
                action = "place_item"
                if cap.category == "item_placed_body":
                    calls.append(_call("native_placement", "place_tile", "item"))
            elif fn in {"accessory", "armor", "equipment_damage_bonus"}:
                action = "equip_passive"; input_kind = "equipped"
            elif fn in BINDING_ACTION_REGISTRY["apply_item_effects"].required_item_capabilities_any_of:
                action = "apply_item_effects"
            bindings.append(_binding(
                "witness_binding",
                input_kind,
                action,
                "item",
                placement_call_id=("native_placement" if cap.category == "item_placed_body" else "witness_call") if action == "place_item" else "",
                contact_damage=fn in {"item_hitbox", "tool_stats"},
            ))
    else:
        if not any(row["fn"] == "item_use" for row in calls):
            item_use = deepcopy(_ITEM_BASE_USE)
            if fn in {"channel_beam", "charge_then_release", "move_flail_tether", "move_yoyo_hover"}:
                item_use["channel"] = True
                item_use["customHeldSprite"] = "visible"
            calls.append(_call("item_use", "item_use", "item", item_use))
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
            "spawn": _SPAWN,
            "projectile_damage": _DAMAGE,
            "projectile_lifetime": {"lifetimeSeconds": 2},
            "projectile_hitbox": _HITBOX,
            "projectile_collision": _COLLISION,
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
        if fn in {"spawn_on_event", "spawn_at_hit", "emit_to_targets_on_event"}:
            entities.append({"id": "witness_child", "kind": "child_projectile"})
            for base_fn, params in base.items():
                child_params = deepcopy(params)
                if fn in {"spawn_at_hit", "emit_to_targets_on_event"} and base_fn == "spawn":
                    child_params.update(position={"at": "activation_origin"}, aim="velocity", offsetBlocks=0)
                calls.append(_call(f"child_{base_fn}", base_fn, "witness_child", child_params))
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

    if fn == "move_front_hand":
        # An explicit test composition, not compiler-created dependencies.
        next(row for row in calls if row["fn"] == "item_use")["params"].pop("handPose", None)
        next(row for row in calls if row["fn"] == "spawn")["params"].update(
            velocity={"speed": 0}, count=1, spreadRadians=0)
        next(row for row in calls if row["fn"] == "projectile_collision")["params"]["tileCollide"] = False
        calls.append(_call("hand_singleton", "projectile_limit", witness_target, {"maxActive": 1}))

    if fn == "orient_whip_to_owner_gravity":
        base_motion = next(row for row in calls if row["id"] == "base_motion")
        base_motion.update(fn="move_whip_lash", params={"range": 8, "segments": 12})

    if cap.category == "motion_primitive":
        pending = [cap]
        while pending:
            selected = pending.pop()
            for requirement in selected.requirements:
                if requirement.kind != "capability_present" or any(row["fn"] == requirement.capability for row in calls):
                    continue
                dependency = CAPABILITY_REGISTRY[requirement.capability]
                calls.append(_call("dep_" + dependency.name, dependency.name, witness_target))
                pending.append(dependency)
        selected_fns = {row["fn"] for row in calls}
        item_use = next(row["params"] for row in calls if row["fn"] == "item_use")
        if selected_fns.intersection({"attach", "lash_geometry"}):
            # This QA composition explicitly chooses a supported tile policy;
            # production never infers it from the selected geometry.
            next(row["params"] for row in calls if row["fn"] == "projectile_collision")["tileCollide"] = False
        if "charge" in selected_fns:
            item_use["channel"] = True
        if "front_arm_pose" in selected_fns:
            item_use.pop("handPose", None)
        if "sustain_mana" in selected_fns:
            item_use["channel"] = True
            next(row["params"] for row in calls if row["fn"] == "set_owner_control").update(
                requireHeldItem=True, requireChannel=True)
        if fn == "return_when":
            next(row["params"] for row in calls if row["id"] == "witness_call")["onTileCollision"] = True

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
            "selfEvaluation": "Optional fixture self-check; not observed execution.",
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
    for fn, spec in CAPABILITY_REGISTRY.items():
        if not spec.author_visible:
            continue
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
