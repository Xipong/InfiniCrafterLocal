from __future__ import annotations

"""Non-archetypal v5 runtime-program acceptance fixtures.

Each fixture is a complete Author response.  The helper intentionally writes every
runtime component explicitly; it never derives movement, attachment, damage, or
lifecycle from the fixture name/category.
"""

from copy import deepcopy
from typing import Any

from infini_local.core.runtime_authoring import (
    RUNTIME_CONTRACT_SCHEMA,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
)


def _item_stats(*, damage: int = 30, damage_class: str = "generic", use_time: int = 24) -> dict[str, Any]:
    return {
        "damageClass": damage_class,
        "damage": damage,
        "knockback": 4.0,
        "useTimeTicks": use_time,
        "useAnimationTicks": use_time,
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
        "releaseTiming": "on_release" if channel else "immediate",
    }


def _spawn(*, speed: float = 10.0, count: int = 1, placement: str = "item_use_origin", aim: str = "cursor", offset: int = 0) -> dict[str, Any]:
    return {
        "speedPxPerTick": speed,
        "count": count,
        "spreadRadians": 0.0,
        "offsetPx": int(offset),
        "aim": aim,
        "placement": placement,
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
        "extraUpdates": 0,
        "npcImmunityMode": "local",
        "localNpcHitCooldownTicks": 10,
    }


class _Builder:
    def __init__(self, fixture_id: str, *, name: str, tooltip: str, category: str = "hybrid", damage: int = 30, channel: bool = False, item_body_contact: bool = False) -> None:
        self.fixture_id = fixture_id
        self.name = name
        self.tooltip = tooltip
        self.category = category
        self.entities: list[dict[str, Any]] = [{"id": "item", "kind": "item_body"}]
        self.bindings: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.claims: list[dict[str, Any]] = []
        self.call("item_stats", "configure_item_stats", "item", _item_stats(damage=damage))
        self.call("item_use", "configure_item_use", "item", _item_use(channel=channel, disable_melee_hitbox=not item_body_contact))
        if item_body_contact:
            self.call("item_contact", "enable_item_contact_damage", "item", {"hitboxScale": 1.0, "contactForgivenessPx": 4})

    def entity(self, entity_id: str, kind: str) -> None:
        self.entities.append({"id": entity_id, "kind": kind})

    def bind(self, binding_id: str, input_kind: str, action: str, target: str) -> None:
        self.bindings.append({"id": binding_id, "input": input_kind, "action": action, "target": target})

    def call(self, call_id: str, fn: str, target: str, params: dict[str, Any]) -> None:
        self.calls.append({"id": call_id, "fn": fn, "target": target, "params": deepcopy(params)})

    def projectile(
        self,
        entity_id: str,
        kind: str,
        *,
        speed: float = 10.0,
        lifetime: int = 180,
        damage: int = 30,
        damage_class: str = "generic",
        tile: bool = True,
        pierce: int = 1,
        placement: str = "item_use_origin",
        aim: str = "cursor",
        movement: str | None = "move_straight",
        movement_params: dict[str, Any] | None = None,
        width: int = 24,
        height: int = 24,
    ) -> None:
        self.entity(entity_id, kind)
        self.call(f"{entity_id}_spawn", "configure_spawn", entity_id, _spawn(speed=speed, placement=placement, aim=aim))
        self.call(f"{entity_id}_damage", "set_projectile_damage", entity_id, _damage(value=damage, damage_class=damage_class, owner_hit_check=kind == "owner_attached_projectile"))
        self.call(f"{entity_id}_life", "set_projectile_lifetime", entity_id, {"lifetimeTicks": lifetime})
        self.call(f"{entity_id}_hitbox", "set_projectile_hitbox", entity_id, _hitbox(width, height))
        self.call(f"{entity_id}_collision", "set_projectile_collision", entity_id, _collision(tile=tile, pierce=pierce))
        if movement:
            self.call(f"{entity_id}_motion", movement, entity_id, movement_params or {})

    def claim(self, claim_id: str, text: str, *backing: str, kind: str = "gameplay") -> None:
        self.claims.append({"id": claim_id, "kind": kind, "text": text, "backedBy": list(backing)})

    def finish(self, *, primary_entity_id: str, composition: str, parent_a: str, parent_b: str) -> dict[str, Any]:
        if primary_entity_id not in {row["id"] for row in self.entities}:
            raise ValueError(f"fixture primary entity {primary_entity_id!r} is absent")
        return {
            "name": self.name,
            "tooltip": self.tooltip,
            "category": self.category,
            "concept": {
                "literalSynthesis": composition,
                "coreMechanic": self.tooltip,
                "parentAContribution": parent_a,
                "parentBContribution": parent_b,
                "playerExperience": "The player directly experiences the explicitly authored entities, inputs and events.",
            },
            "runtimeContract": {
                "schema": RUNTIME_CONTRACT_SCHEMA,
                "parentSynthesis": {
                    "composition": composition,
                    "parentA": {"facts": [parent_a], "runtimeRoles": ["literal physical component"]},
                    "parentB": {"facts": [parent_b], "runtimeRoles": ["literal mechanical component"]},
                },
                "claims": self.claims,
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
    b = _Builder("workbench_blade", name="Workbench-Backed Blade", tooltip="Thrusts a literal workbench-backed blade and knocks loose nails into targets.", damage=42, item_body_contact=True)
    b.projectile("workbench_blade", "owner_attached_projectile", speed=0, lifetime=28, damage=42, damage_class="melee", tile=False, pierce=-1, movement="move_forward_then_retract", movement_params={"rangeTiles": 6, "durationTicks": 24}, width=64, height=34)
    b.projectile("nail", "child_projectile", speed=13, lifetime=120, damage=12, damage_class="ranged", tile=True, pierce=1, movement="move_straight", width=8, height=8)
    b.bind("primary_workbench", "primary_use", "spawn_entity", "workbench_blade")
    b.call("shed_nails", "spawn_entity_on_event", "workbench_blade", {"event": "on_hit", "entity": "nail", "count": 5, "spreadRadians": 0.55, "damageMultiplier": 0.35, "delayTicks": 0})
    b.claim("claim_literal_bench", "The item body is the primary contact blade; the workbench projectile is an explicit secondary held effect.", "item_stats", "item_use", "item_contact", "primary_workbench", "workbench_blade_motion", kind="parent_synthesis")
    b.claim("claim_nails", "Hits release five independently simulated nails.", "shed_nails")
    return b.finish(primary_entity_id="item", composition="A literal workbench is bolted behind a primary contact blade and also participates as a secondary held entity.", parent_a="workbench body", parent_b="blade and nails")


def _umbrella_grenade() -> dict[str, Any]:
    b = _Builder("umbrella_grenade", name="Umbrella Grenadier", tooltip="Primary use braces an umbrella; alternate use lobs a timed explosive canopy weight.", damage=34)
    b.projectile("umbrella_guard", "owner_attached_projectile", speed=0, lifetime=32, damage=18, tile=False, pierce=-1, movement="move_yoyo_hover", movement_params={"rangeTiles": 2, "returnSpeed": 12}, width=54, height=28)
    b.projectile("grenade_weight", "free_projectile", speed=9, lifetime=90, damage=34, tile=True, pierce=1, movement="move_gravity_arc", movement_params={"gravityPerTick": 0.25}, width=18, height=18)
    b.bind("primary_guard", "primary_use", "spawn_entity", "umbrella_guard")
    b.bind("alternate_grenade", "alternate_use", "spawn_entity", "grenade_weight")
    b.call("grenade_burst", "damage_area_on_event", "grenade_weight", {"event": "on_expire", "radiusPx": 112, "damageMultiplier": 1.4})
    b.claim("claim_guard", "Primary use creates the held umbrella body.", "primary_guard", "umbrella_guard_motion")
    b.claim("claim_burst", "Alternate use creates a separate arcing grenade that bursts on expiry.", "alternate_grenade", "grenade_burst")
    return b.finish(primary_entity_id="umbrella_guard", composition="The umbrella is a literal brace and its weighted tip becomes a grenade.", parent_a="umbrella canopy and shaft", parent_b="grenade charge")


def _door_on_chain() -> dict[str, Any]:
    b = _Builder("door_on_chain", name="Door on a Chain", tooltip="Swings a literal reinforced door from a bounded tether.", damage=48)
    b.projectile("chained_door", "owner_attached_projectile", speed=0, lifetime=180, damage=48, damage_class="melee", tile=True, pierce=-1, movement="move_flail_tether", movement_params={"rangeTiles": 10, "returnSpeed": 14}, width=36, height=72)
    b.bind("primary_chain", "primary_use", "spawn_entity", "chained_door")
    b.call("door_stun", "apply_status_on_event", "chained_door", {"event": "on_hit", "buffId": 31, "durationTicks": 90})
    b.claim("claim_chain", "The door itself is the damaging tethered entity.", "primary_chain", "chained_door_motion", kind="parent_synthesis")
    b.claim("claim_stun", "Door impacts apply the authored status.", "door_stun")
    return b.finish(primary_entity_id="chained_door", composition="A full door remains intact and is fastened to a chain.", parent_a="door slab", parent_b="chain tether")


def _returning_potion() -> dict[str, Any]:
    b = _Builder("returning_potion", name="Returning Tonic", tooltip="Throws a potion flask that returns and heals its owner on a hit.", damage=24)
    b.projectile("tonic_flask", "free_projectile", speed=12, lifetime=180, damage=24, damage_class="magic", tile=True, pierce=2, movement="move_boomerang", movement_params={"returnAfterTicks": 36, "returnSpeed": 15}, width=18, height=24)
    b.bind("primary_tonic", "primary_use", "spawn_entity", "tonic_flask")
    b.call("tonic_heal", "heal_owner_on_event", "tonic_flask", {"event": "on_hit", "damageFraction": 0.18, "maxHeal": 12})
    b.call("tonic_splash", "apply_status_on_event", "tonic_flask", {"event": "on_hit", "buffId": 20, "durationTicks": 120})
    b.claim("claim_return", "The potion is an actual returning projectile.", "primary_tonic", "tonic_flask_motion", kind="parent_synthesis")
    b.claim("claim_heal", "Successful hits heal the owner within a hard cap.", "tonic_heal")
    return b.finish(primary_entity_id="tonic_flask", composition="A sealed potion bottle is thrown whole and returns like a boomerang.", parent_a="potion bottle", parent_b="returning-flight mechanism")


def _fishing_platform_tool() -> dict[str, Any]:
    b = _Builder("fishing_platform_tool", name="Angler's Platform Rod", tooltip="Functions as a tool and places a concrete temporary-looking platform tile.", category="hybrid", damage=8)
    b.bind("primary_place", "primary_use", "place_item", "item")
    b.call("tool_heads", "configure_tool", "item", {"pickPower": 35, "axePower": 0, "hammerPower": 20, "miningSpeedScale": 0.9})
    b.call("platform_result", "configure_placeable", "item", {"tileId": 19, "wallId": -1, "placeStyle": 0})
    b.call("consume_platform", "configure_consumption", "item", {"consumable": True, "consumeChancePercent": 35})
    b.claim("claim_platform", "Use places the explicitly authored platform tile; no fishing-rod family route is involved.", "primary_place", "platform_result")
    b.claim("claim_tool", "The same item has explicit pick and hammer power.", "tool_heads")
    return b.finish(primary_entity_id="item", composition="A fishing rod carries a fold-out platform panel as a literal placeable result.", parent_a="fishing rod", parent_b="platform tile")


def _shield_and_disc() -> dict[str, Any]:
    b = _Builder("shield_and_disc", name="Shield with Breakaway Disc", tooltip="Primary use holds a contact shield; alternate use launches a returning disc.", damage=32)
    b.projectile("shield_body", "owner_attached_projectile", speed=0, lifetime=40, damage=16, damage_class="melee", tile=False, pierce=-1, movement="move_forward_then_retract", movement_params={"rangeTiles": 2, "durationTicks": 32}, width=44, height=52)
    b.projectile("shield_disc", "free_projectile", speed=14, lifetime=150, damage=32, damage_class="melee", tile=True, pierce=3, movement="move_returning_glaive", movement_params={"returnAfterTicks": 30, "returnSpeed": 16}, width=28, height=28)
    b.bind("primary_shield", "primary_use", "spawn_entity", "shield_body")
    b.bind("alternate_disc", "alternate_use", "spawn_entity", "shield_disc")
    b.claim("claim_shield", "Primary use explicitly spawns the held shield body.", "primary_shield", "shield_body_motion")
    b.claim("claim_disc", "Alternate use independently spawns the returning disc.", "alternate_disc", "shield_disc_motion")
    return b.finish(primary_entity_id="shield_body", composition="A shield stays whole while its central plate detaches as a disc.", parent_a="shield body", parent_b="detachable disc")


def _held_and_deployed() -> dict[str, Any]:
    b = _Builder("held_and_deployed", name="Lantern Pike Turret", tooltip="Primary use drives a held lighted body; alternate use deploys an independent targeter.", damage=36)
    b.projectile("held_lantern_pike", "owner_attached_projectile", speed=0, lifetime=30, damage=36, tile=False, pierce=-1, movement="move_forward_then_retract", movement_params={"rangeTiles": 5, "durationTicks": 26}, width=58, height=24)
    b.call("held_light", "emit_light_while_active", "held_lantern_pike", {"strength": 0.9, "color": "orange"})
    b.projectile("deployed_lantern", "stationary_projectile", speed=0, lifetime=900, damage=0, tile=True, pierce=-1, movement=None, placement="ground_at_cursor", aim="none", width=28, height=42)
    b.projectile("lantern_bolt", "child_projectile", speed=11, lifetime=150, damage=18, damage_class="magic", tile=True, pierce=1, movement="move_slow_homing", movement_params={"rangeTiles": 28, "homingStrength": 0.08}, width=12, height=12)
    b.call("deployed_targeter", "target_and_fire", "deployed_lantern", {"shotEntity": "lantern_bolt", "intervalTicks": 45, "rangeTiles": 30, "sameTargetBias": 0.35})
    b.bind("primary_pike", "primary_use", "spawn_entity", "held_lantern_pike")
    b.bind("alternate_deploy", "alternate_use", "spawn_entity", "deployed_lantern")
    b.claim("claim_primary", "Primary use creates only the held pike entity.", "primary_pike", "held_lantern_pike_motion")
    b.claim("claim_alt", "Alternate use independently deploys a targeter that fires the authored bolt entity.", "alternate_deploy", "deployed_targeter")
    return b.finish(primary_entity_id="held_lantern_pike", composition="A lantern is mounted on a pike and can be planted without ceasing to be literal.", parent_a="pike body", parent_b="lantern targeter")


def _equipment_tool_combat() -> dict[str, Any]:
    b = _Builder("equipment_tool_combat", name="Mining Harness Cannon", tooltip="Acts as an accessory, mining tool, placeable light and independent projectile launcher.", category="hybrid", damage=28)
    b.projectile("ore_charge", "free_projectile", speed=10, lifetime=160, damage=28, damage_class="ranged", tile=True, pierce=2, movement="move_proximity_missile", movement_params={"rangeTiles": 24, "homingStrength": 0.06, "proximityRadiusPx": 48}, width=14, height=14)
    b.bind("primary_charge", "primary_use", "spawn_entity", "ore_charge")
    b.bind("passive_harness", "equipped", "equip_passive", "item")
    b.call("harness_stats", "configure_accessory", "item", {"defense": 4, "maxLife": 0, "maxMana": 0, "lifeRegen": 0, "manaRegen": 0, "movementSpeed": 0.08, "genericDamage": 0.05, "genericCrit": 2.0, "endurance": 0.02, "minionSlots": 0, "sentrySlots": 0, "lightStrength": 0.35, "lightColor": "yellow"})
    b.call("mining_heads", "configure_tool", "item", {"pickPower": 55, "axePower": 0, "hammerPower": 0, "miningSpeedScale": 0.85})
    b.call("place_torch", "configure_placeable", "item", {"tileId": 4, "wallId": -1, "placeStyle": 0})
    b.call("charge_burst", "damage_area_on_event", "ore_charge", {"event": "on_hit", "radiusPx": 72, "damageMultiplier": 0.65})
    b.claim("claim_accessory", "Equipping the item applies exact passive modifiers.", "passive_harness", "harness_stats")
    b.claim("claim_mining", "The item has explicit mining power and a concrete placeable result.", "mining_heads", "place_torch")
    b.claim("claim_combat", "Primary use launches the independently configured ore charge.", "primary_charge", "ore_charge_motion", "charge_burst")
    return b.finish(primary_entity_id="item", composition="A mining harness retains its drill heads, lamp and detachable ore charge.", parent_a="mining harness/tool", parent_b="projectile charge and lamp")


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
