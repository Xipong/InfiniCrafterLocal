from __future__ import annotations

from infini_local.core.runtime_authoring.binding_use_policy import action_kind as binding_action_kind

"""Non-archetypal Author runtime-program acceptance fixtures.

Each fixture is a complete Author response.  The helper intentionally writes every
runtime component explicitly; it never derives movement, attachment, damage, or
lifecycle from the fixture name/category.

These are current synthetic Author examples, not immutable saved-wire captures.
Reach curves do not end a projectile: the three thrust examples retain their
authored lifetimes after retracting rather than the retired bundle's cycle kill.
Door travel explicitly seeks the cursor before returning; no motion is inferred
from its zero-speed spawn or from the word "chain".
"""

from copy import deepcopy
from typing import Any

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, RUNTIME_PROGRAM_API_VERSION, RUNTIME_PROGRAM_SCHEMA


def _item_stats(*, damage: int = 30, damage_class: str = "generic", use_time: float = 0.4) -> dict[str, Any]:
    return {
        "damageClass": damage_class,
        "damage": damage,
        "knockback": 4.0,
        "useTimeSeconds": use_time,
        "useAnimationSeconds": use_time,
        "manaCost": 0,
        "rarity": 2,
        "valueCopper": 7500,
        "maxStack": 1,
        "craftYield": 1,
        "widthPx": 32,
        "heightPx": 32,
        "scale": 1.0,
    }


def _item_use(*, style: str = "shoot", channel: bool = False, hide: bool = False, disable_melee_hitbox: bool = True) -> dict[str, Any]:
    return {
        "useStyle": style,
        "autoReuse": True,
        "useTurn": True,
        "hideUseGraphic": hide,
        "disableMeleeHitbox": disable_melee_hitbox,
        "channel": channel,
        "holdoutOffsetX": 0,
        "holdoutOffsetY": 0,
        "handPose": "one_handed",
        "customHeldSprite": "visible" if channel else "hidden",
    }


def _spawn(*, speed: float = 37.5, count: int = 1, placement: str = "activation_origin", aim: str = "cursor", offset: float = 0) -> dict[str, Any]:
    return {
        "velocity": {"constantSpeedBlocksPerSecond": speed},
        "count": count,
        "spreadRadians": 0.0,
        "offsetBlocks": offset,
        "aim": aim,
        "position": {"at": placement},
    }


def _damage(*, value: int = 30, damage_class: str = "generic", owner_hit_check: bool = False) -> dict[str, Any]:
    return {
        "damageClass": damage_class,
        "damage": value,
        "knockback": 4.0,
        "ownerHitCheck": owner_hit_check,
    }


def _hitbox(width: int = 24, height: int = 24, scale: float = 1.0) -> dict[str, Any]:
    return {"widthPx": width, "heightPx": height, "drawScale": scale, "hitboxScale": 1.0}


def _collision(*, tile: bool = True, bounce: int = 0, pierce: int = 1) -> dict[str, Any]:
    return {
        "tileCollide": tile,
        "ignoreWater": False,
        "bounceCount": bounce,
        "pierce": pierce,
        "updatesPerTick": 1,
        "immunity": {"localCooldown": 10},
    }


class _Builder:
    def __init__(self, fixture_id: str, *, name: str, mechanic: str, category: str = "hybrid", damage: int = 30, channel: bool = False, item_body_contact: bool = False) -> None:
        self.fixture_id = fixture_id
        self.name = name
        self.mechanic = mechanic
        self.category = category
        self.item_body_contact = item_body_contact
        self.entities: list[dict[str, Any]] = [{"id": "item", "kind": "item_body"}]
        self.bindings: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.call("item_stats", "configure_item_stats", "item", _item_stats(damage=damage))
        self.call("item_use", "configure_item_use", "item", _item_use(channel=channel, disable_melee_hitbox=not item_body_contact))
        if item_body_contact:
            self.call("item_contact", "configure_item_contact_hitbox", "item", {"hitboxScale": 1.0, "contactForgivenessPx": 4})

    def entity(self, entity_id: str, kind: str) -> None:
        self.entities.append({"id": entity_id, "kind": kind})

    def bind(
        self,
        binding_id: str,
        input_kind: str,
        action: str,
        target: str,
        *,
        stack_cost: int = 0,
        placement_call_id: str = "",
    ) -> None:
        action_row: dict[str, Any] = {"kind": action, "targetId": target}
        if action == "place_item":
            action_row["placementCallId"] = placement_call_id
        from infini_local.core.runtime_authoring.capability_registry import INPUT_KIND_REGISTRY, BINDING_ACTION_REGISTRY
        if BINDING_ACTION_REGISTRY[action].target_kinds == ("item_body",):
            action_row.pop("targetId")
        if len(INPUT_KIND_REGISTRY[input_kind].allowed_actions) == 1:
            action_row.pop("kind")
        row: dict[str, Any] = {
            "id": binding_id,
            "input": input_kind,
            **{
                "action": action_row,
                "stackCost": stack_cost,
                "contactDamage": (
                    self.item_body_contact
                    and input_kind in {"primary_use", "alternate_use"}
                    and action != "place_item"
                ),
            },
        }
        if not action_row:
            row.pop("action")
        if input_kind not in {"primary_use", "alternate_use"} or action == "place_item":
            row.pop("stackCost")
            row.pop("contactDamage")
        self.bindings.append(row)

    def call(self, call_id: str, fn: str, target: str, params: dict[str, Any]) -> None:
        row = {"id": call_id, "fn": fn, "target": target}
        if CAPABILITY_REGISTRY[fn].target_kinds == ("item_body",):
            row.pop("target")
        if CAPABILITY_REGISTRY[fn].params:
            row["params"] = deepcopy(params)
        self.calls.append(row)

    def projectile(
        self,
        entity_id: str,
        kind: str,
        *,
        speed: float = 37.5,
        lifetime: float = 3,
        damage: int = 30,
        damage_class: str = "generic",
        tile: bool = True,
        pierce: int = 1,
        placement: str = "activation_origin",
        aim: str = "cursor",
        width: int = 24,
        height: int = 24,
    ) -> None:
        self.entity(entity_id, kind)
        self.call(f"{entity_id}_spawn", "configure_spawn", entity_id, _spawn(speed=speed, placement=placement, aim=aim))
        self.call(f"{entity_id}_damage", "set_projectile_damage", entity_id, _damage(value=damage, damage_class=damage_class, owner_hit_check=kind == "owner_attached_projectile"))
        self.call(f"{entity_id}_life", "set_projectile_lifetime", entity_id, {"lifetimeSeconds": lifetime})
        self.call(f"{entity_id}_hitbox", "set_projectile_hitbox", entity_id, _hitbox(width, height))
        self.call(f"{entity_id}_collision", "set_projectile_collision", entity_id, _collision(tile=tile, pierce=pierce))

    def finish(self, *, primary_entity_id: str, composition: str, parent_a: str, parent_b: str) -> dict[str, Any]:
        if primary_entity_id not in {row["id"] for row in self.entities}:
            raise ValueError(f"fixture primary entity {primary_entity_id!r} is absent")
        return {
            "name": self.name,
            "category": self.category,
            "concept": {
                "literalSynthesis": composition,
                "coreMechanic": self.mechanic,
                "parentAContribution": parent_a,
                "parentBContribution": parent_b,
                "playerExperience": "The player directly experiences the explicitly authored entities, inputs and events.",
                "plannedPlayerActions": [
                    {
                        "input": str(row["input"]),
                        "intent": f"Execute the authored {binding_action_kind(row)} action.",
                    }
                    for row in self.bindings
                ] or [{"input": "passive_or_event", "intent": "Execute the authored passive or event-driven behavior."}],
            },
            "realization": {
                "description": f"{composition} {self.mechanic}",
                "playerExperience": "The player directly experiences the explicitly authored entities, inputs and events.",
                "selfEvaluation": "Optional fixture self-check; not observed execution.",
            },
            "runtimeProgram": {
                "apiVersion": RUNTIME_PROGRAM_API_VERSION,
                "schema": RUNTIME_PROGRAM_SCHEMA,
                "primaryEntityId": primary_entity_id,
                "entities": self.entities,
                "bindings": self.bindings,
                "calls": self.calls,
            },
        }


def _workbench_blade() -> dict[str, Any]:
    b = _Builder("workbench_blade", name="Workbench-Backed Blade", mechanic="Thrusts a literal workbench-backed blade and knocks loose nails into targets.", damage=42, item_body_contact=True)
    b.projectile("workbench_blade", "owner_attached_projectile", speed=0, lifetime=28 / 60, damage=42, damage_class="melee", tile=False, pierce=-1, width=64, height=34)
    b.projectile("nail", "child_projectile", speed=48.75, lifetime=2, damage=12, damage_class="ranged", tile=True, pierce=1, width=8, height=8)
    b.call("workbench_blade_aim", "set_projectile_aim", "workbench_blade", {"source": "cursor", "turnOwner": False})
    b.call("workbench_blade_motion", "attach_projectile", "workbench_blade", {"anchor": "owner_center", "axisOffsetBlocks": 1.125, "normalOffsetBlocks": 0, "reachCurve": {"durationSeconds": 0.4, "startOffsetBlocks": 0, "peakOffsetBlocks": 6, "endOffsetBlocks": 0, "peakProgress": 0.5}})
    b.call("workbench_blade_rotation", "set_projectile_rotation", "workbench_blade", {"mode": "axis", "offsetRadians": 1.5707963267948966})
    b.call("nail_motion", "move_straight", "nail", {})
    b.bind("primary_workbench", "primary_use", "spawn_entity", "workbench_blade")
    b.call("shed_nails", "spawn_entity_on_event", "workbench_blade", {"when": "on_hit", "entity": "nail", "count": 5, "spreadRadians": 0.55, "damageMultiplier": 0.35, "delaySeconds": 0, "damageBasis": "authored_child", "knockbackBasis": "authored_child"})
    return b.finish(primary_entity_id="item", composition="A literal workbench is bolted behind a primary contact blade and also participates as a secondary held entity.", parent_a="workbench body", parent_b="blade and nails")


def _umbrella_grenade() -> dict[str, Any]:
    b = _Builder("umbrella_grenade", name="Umbrella Grenadier", mechanic="Primary use braces an umbrella; alternate use lobs a timed explosive canopy weight.", damage=34, channel=True)
    b.projectile("umbrella_guard", "owner_attached_projectile", speed=0, lifetime=32 / 60, damage=18, tile=False, pierce=-1, width=54, height=28)
    b.projectile("grenade_weight", "free_projectile", speed=33.75, lifetime=1.5, damage=34, tile=True, pierce=1, width=18, height=18)
    b.call("umbrella_guard_motion", "seek_projectile", "umbrella_guard", {"target": "cursor", "maxSpeedBlocksPerSecond": 45, "velocityLerpPerUpdate": 0.28, "limitSpeedToDistance": True, "cursorLeashBlocks": 2, "window": {"phase": "outbound"}})
    b.call("umbrella_guard_return", "set_projectile_return_trigger", "umbrella_guard", {"onOwnerRelease": True, "onTileCollision": False, "disableTileCollisionOnReturn": True})
    b.call("umbrella_guard_home", "seek_projectile", "umbrella_guard", {"target": "owner_mounted", "maxSpeedBlocksPerSecond": 45, "velocityLerpPerUpdate": 0.28, "limitSpeedToDistance": True, "window": {"phase": "returning"}})
    b.call("umbrella_guard_arrival", "set_projectile_arrival", "umbrella_guard", {"target": "owner_mounted", "radiusBlocks": 1.25, "window": {"phase": "returning"}})
    b.call("umbrella_guard_rotation", "set_projectile_rotation", "umbrella_guard", {"mode": "spin", "radiansPerSecond": 21})
    b.call("umbrella_guard_control", "set_projectile_owner_control", "umbrella_guard", {"claimHeldProjectile": True})
    b.call("grenade_weight_motion", "accelerate_projectile_vertical", "grenade_weight", {"accelerationYBlocksPerSecondSquared": 56.25})
    b.bind("primary_guard", "primary_use", "spawn_entity", "umbrella_guard")
    b.bind("alternate_grenade", "alternate_use", "spawn_entity", "grenade_weight")
    b.call("grenade_burst", "damage_nearby_on_event", "grenade_weight", {"when": "on_expire", "radiusTiles": 7, "damageMultiplier": 1.4})
    return b.finish(primary_entity_id="umbrella_guard", composition="The umbrella is a literal brace and its weighted tip becomes a grenade.", parent_a="umbrella canopy and shaft", parent_b="grenade charge")


def _door_on_chain() -> dict[str, Any]:
    b = _Builder("door_on_chain", name="Door on a Chain", mechanic="Swings a literal reinforced door from a bounded tether.", damage=48, channel=True)
    b.projectile("chained_door", "owner_attached_projectile", speed=0, lifetime=3, damage=48, damage_class="melee", tile=True, pierce=-1, width=36, height=72)
    b.call("chained_door_motion", "seek_projectile", "chained_door", {"target": "cursor", "maxSpeedBlocksPerSecond": 52.5, "velocityLerpPerUpdate": 0.25, "limitSpeedToDistance": True, "cursorLeashBlocks": 10, "window": {"phase": "outbound"}})
    b.call("chained_door_return", "set_projectile_return_trigger", "chained_door", {"ownerDistanceBlocks": 10, "onOwnerRelease": True, "onTileCollision": False, "disableTileCollisionOnReturn": True})
    b.call("chained_door_home", "seek_projectile", "chained_door", {"target": "owner_mounted", "maxSpeedBlocksPerSecond": 52.5, "velocityLerpPerUpdate": 0.25, "limitSpeedToDistance": False, "window": {"phase": "returning"}})
    b.call("chained_door_arrival", "set_projectile_arrival", "chained_door", {"target": "owner_mounted", "radiusBlocks": 1.25, "window": {"phase": "returning"}})
    b.call("chained_door_rotation", "set_projectile_rotation", "chained_door", {"mode": "spin", "radiansPerSecond": 24})
    b.call("chained_door_control", "set_projectile_owner_control", "chained_door", {"claimHeldProjectile": True})
    b.bind("primary_chain", "primary_use", "spawn_entity", "chained_door")
    b.call("door_stun", "apply_status_on_event", "chained_door", {"when": "on_hit", "buffId": 31, "durationSeconds": 1.5})
    return b.finish(primary_entity_id="chained_door", composition="A full door remains intact and is fastened to a chain.", parent_a="door slab", parent_b="chain tether")


def _returning_potion() -> dict[str, Any]:
    b = _Builder("returning_potion", name="Returning Tonic", mechanic="Throws a potion flask that returns and heals its owner on a hit.", damage=24)
    b.projectile("tonic_flask", "free_projectile", speed=45, lifetime=3, damage=24, damage_class="magic", tile=True, pierce=2, width=18, height=24)
    b.call("tonic_flask_motion", "move_straight", "tonic_flask", {})
    b.call("tonic_flask_return", "set_projectile_return_trigger", "tonic_flask", {"afterSeconds": 0.6, "onOwnerRelease": False, "onTileCollision": False, "disableTileCollisionOnReturn": True})
    b.call("tonic_flask_home", "seek_projectile", "tonic_flask", {"target": "owner_center", "maxSpeedBlocksPerSecond": 56.25, "velocityLerpPerUpdate": 0.2, "limitSpeedToDistance": False, "window": {"phase": "returning"}})
    b.call("tonic_flask_arrival", "set_projectile_arrival", "tonic_flask", {"target": "owner_center", "radiusBlocks": 1.5, "window": {"phase": "returning"}})
    b.bind("primary_tonic", "primary_use", "spawn_entity", "tonic_flask")
    b.call("tonic_heal", "heal_owner_on_event", "tonic_flask", {"when": "on_hit", "damageFraction": 0.18, "maxHeal": 12})
    b.call("tonic_splash", "apply_status_on_event", "tonic_flask", {"when": "on_hit", "buffId": 20, "durationSeconds": 2})
    return b.finish(primary_entity_id="tonic_flask", composition="A sealed potion bottle is thrown whole and returns like a boomerang.", parent_a="potion bottle", parent_b="returning-flight mechanism")


def _fishing_platform_tool() -> dict[str, Any]:
    b = _Builder("fishing_platform_tool", name="Angler's Platform Rod", mechanic="Functions as a tool and places a concrete temporary-looking platform tile.", category="hybrid", damage=8, item_body_contact=True)
    b.bind("primary_tool", "primary_use", "use_item_body", "item")
    b.bind("alternate_place", "alternate_use", "place_item", "item", stack_cost=1, placement_call_id="platform_result")
    b.call("tool_heads", "configure_tool", "item", {"pickPower": 35, "axePowerTooltipPercent": 0, "hammerPower": 20, "miningSpeedMultiplier": 0.9})
    b.call("platform_result", "configure_tile_placement", "item", {"tileId": 19, "placeStyle": 0})
    return b.finish(primary_entity_id="item", composition="A fishing rod carries a fold-out platform panel as a literal placeable result.", parent_a="fishing rod", parent_b="platform tile")


def _shield_and_disc() -> dict[str, Any]:
    b = _Builder("shield_and_disc", name="Shield with Breakaway Disc", mechanic="Primary use holds a contact shield; alternate use launches a returning disc.", damage=32)
    b.projectile("shield_body", "owner_attached_projectile", speed=0, lifetime=40 / 60, damage=16, damage_class="melee", tile=False, pierce=-1, width=44, height=52)
    b.projectile("shield_disc", "free_projectile", speed=52.5, lifetime=2.5, damage=32, damage_class="melee", tile=True, pierce=3, width=28, height=28)
    b.call("shield_body_aim", "set_projectile_aim", "shield_body", {"source": "cursor", "turnOwner": False})
    b.call("shield_body_motion", "attach_projectile", "shield_body", {"anchor": "owner_mounted", "axisOffsetBlocks": 1.125, "normalOffsetBlocks": 0, "reachCurve": {"durationSeconds": 32 / 60, "startOffsetBlocks": 0, "peakOffsetBlocks": 2, "endOffsetBlocks": 0, "peakProgress": 0.5}})
    b.call("shield_body_rotation", "set_projectile_rotation", "shield_body", {"mode": "axis", "offsetRadians": 1.5707963267948966})
    b.call("shield_body_control", "set_projectile_owner_control", "shield_body", {"claimHeldProjectile": True})
    b.call("shield_disc_motion", "move_straight", "shield_disc", {})
    b.call("shield_disc_return", "set_projectile_return_trigger", "shield_disc", {"afterSeconds": 0.5, "onOwnerRelease": False, "onTileCollision": False, "disableTileCollisionOnReturn": True})
    b.call("shield_disc_home", "seek_projectile", "shield_disc", {"target": "owner_center", "maxSpeedBlocksPerSecond": 60, "velocityLerpPerUpdate": 0.2, "limitSpeedToDistance": False, "window": {"phase": "returning"}})
    b.call("shield_disc_arrival", "set_projectile_arrival", "shield_disc", {"target": "owner_center", "radiusBlocks": 1.5, "window": {"phase": "returning"}})
    b.call("shield_disc_rotation", "set_projectile_rotation", "shield_disc", {"mode": "spin", "radiansPerSecond": 21})
    b.bind("primary_shield", "primary_use", "spawn_entity", "shield_body")
    b.bind("alternate_disc", "alternate_use", "spawn_entity", "shield_disc")
    return b.finish(primary_entity_id="shield_body", composition="A shield stays whole while its central plate detaches as a disc.", parent_a="shield body", parent_b="detachable disc")


def _held_and_deployed() -> dict[str, Any]:
    b = _Builder("held_and_deployed", name="Lantern Pike Turret", mechanic="Primary use drives a held lighted body; alternate use deploys an independent targeter.", damage=36)
    b.projectile("held_lantern_pike", "owner_attached_projectile", speed=0, lifetime=0.5, damage=36, tile=False, pierce=-1, width=58, height=24)
    b.call("held_lantern_pike_aim", "set_projectile_aim", "held_lantern_pike", {"source": "cursor", "turnOwner": False})
    b.call("held_lantern_pike_motion", "attach_projectile", "held_lantern_pike", {"anchor": "owner_mounted", "axisOffsetBlocks": 1.125, "normalOffsetBlocks": 0, "reachCurve": {"durationSeconds": 26 / 60, "startOffsetBlocks": 0, "peakOffsetBlocks": 5, "endOffsetBlocks": 0, "peakProgress": 0.5}})
    b.call("held_lantern_pike_rotation", "set_projectile_rotation", "held_lantern_pike", {"mode": "axis", "offsetRadians": 1.5707963267948966})
    b.call("held_lantern_pike_control", "set_projectile_owner_control", "held_lantern_pike", {"claimHeldProjectile": True})
    b.call("held_light", "emit_light_while_active", "held_lantern_pike", {"strength": 0.9, "color": "orange"})
    b.projectile("deployed_lantern", "stationary_projectile", speed=0, lifetime=15, damage=0, tile=True, pierce=-1, placement="ground_at_cursor", aim="none", width=28, height=42)
    b.projectile("lantern_bolt", "child_projectile", speed=41.25, lifetime=2.5, damage=18, damage_class="magic", tile=True, pierce=1, width=12, height=12)
    b.call("lantern_bolt_motion", "seek_projectile", "lantern_bolt", {"target": "nearest_npc", "maxSpeedBlocksPerSecond": 41.25, "velocityLerpPerUpdate": 0.08, "limitSpeedToDistance": False, "searchRangeTiles": 28, "requireLineOfSight": False})
    b.call("deployed_targeter", "target_and_fire", "deployed_lantern", {"shotEntity": "lantern_bolt", "intervalSeconds": 0.75, "rangeTiles": 30, "sameTargetBias": 0.35, "damageBasis": "authored_child", "knockbackBasis": "authored_child", "damageMultiplier": 1.0})
    b.bind("primary_pike", "primary_use", "spawn_entity", "held_lantern_pike")
    b.bind("alternate_deploy", "alternate_use", "spawn_entity", "deployed_lantern")
    return b.finish(primary_entity_id="held_lantern_pike", composition="A lantern is mounted on a pike and can be planted without ceasing to be literal.", parent_a="pike body", parent_b="lantern targeter")


def _equipment_tool_combat() -> dict[str, Any]:
    b = _Builder("equipment_tool_combat", name="Mining Harness Lamp", mechanic="Acts as an accessory, body-owned mining tool, contact weapon and placeable light.", category="hybrid", damage=28, item_body_contact=True)
    b.bind("primary_tool", "primary_use", "use_item_body", "item")
    b.bind("alternate_torch", "alternate_use", "place_item", "item", stack_cost=1, placement_call_id="place_torch")
    b.bind("passive_harness", "equipped", "equip_passive", "item")
    b.call("harness_stats", "configure_accessory", "item", {"defensePoints": 4, "moveSpeedBonusPercent": 8, "genericCritChancePercentagePoints": 2, "damageReductionPercentagePoints": 2, "lightStrength": 0.35, "lightColor": "yellow"})
    b.call("harness_damage", "add_equipment_damage_bonus", "item", {"phase": "equipped", "damageClass": "generic", "bonusPercent": 5})
    b.call("mining_heads", "configure_tool", "item", {"pickPower": 55, "axePowerTooltipPercent": 0, "hammerPower": 0, "miningSpeedMultiplier": 0.85})
    b.call("place_torch", "configure_tile_placement", "item", {"tileId": 4, "placeStyle": 0})

    return b.finish(primary_entity_id="item", composition="A mining harness retains its drill heads and installs its lamp as a literal tile.", parent_a="mining harness/tool", parent_b="placeable lamp")


_FIXTURE_BUILDERS = {
    "workbench_blade": _workbench_blade,
    "umbrella_grenade": _umbrella_grenade,
    "door_on_chain": _door_on_chain,
    "returning_potion": _returning_potion,
    "fishing_platform_tool": _fishing_platform_tool,
    "shield_and_disc": _shield_and_disc,
    "held_and_deployed": _held_and_deployed,
    "equipment_tool_combat": _equipment_tool_combat,
}


def build_runtime_fixture(name: str) -> dict[str, Any]:
    try:
        return deepcopy(_FIXTURE_BUILDERS[name]())
    except KeyError as exc:
        raise KeyError(f"unknown runtime fixture {name!r}; expected one of {sorted(_FIXTURE_BUILDERS)}") from exc


NON_ARCHETYPAL_FIXTURES = tuple(_FIXTURE_BUILDERS)


__all__ = ["NON_ARCHETYPAL_FIXTURES", "build_runtime_fixture"]
