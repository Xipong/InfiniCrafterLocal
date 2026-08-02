from __future__ import annotations

"""Explicit opt-in DEVELOPER-ONLY deterministic low-level fixture.

This is not a production design fallback.  It exists so offline contract and
HTTP smoke tests can exercise the same v5 entities/bindings/capabilities wire
without reviving the removed weapon-root architecture.
"""

from typing import Any

from infini_local.core.runtime_authoring import (
    RUNTIME_CONTRACT_SCHEMA,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
)


def _parent_name(parent: dict[str, Any], default: str) -> str:
    return str(parent.get("name") or parent.get("displayName") or default).strip()


def deterministic_low_level_plan(
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    del ca, cb
    parent_a = _parent_name(a, "Parent A")
    parent_b = _parent_name(b, "Parent B")
    return {
        "name": f"{parent_a}–{parent_b} Runtime Fixture"[:80],
        "category": "hybrid",
        "concept": {
            "literalSynthesis": f"The physical bodies of {parent_a} and {parent_b} remain visibly combined.",
            "coreMechanic": "Primary use spawns an owner-attached body with explicit forward/retract motion; hits emit three explicit child projectiles.",
            "parentAContribution": f"{parent_a} supplies the main held body.",
            "parentBContribution": f"{parent_b} supplies the emitted fragments.",
            "playerExperience": "A direct short-range strike followed by a small directional fragment burst.",
        },
        "runtimeContract": {
            "schema": RUNTIME_CONTRACT_SCHEMA,
            "parentSynthesis": {
                "composition": f"Literal {parent_a} body carrying visible {parent_b} fragments.",
                "parentA": {"facts": [parent_a], "runtimeRoles": ["held body"]},
                "parentB": {"facts": [parent_b], "runtimeRoles": ["child fragments"]},
            },
            "claims": [
                {
                    "id": "claim_primary_strike",
                    "kind": "gameplay",
                    "text": "Primary use performs a bounded owner-attached strike.",
                    "backedBy": ["bind_primary", "call_move_held", "call_damage_held"],
                },
                {
                    "id": "claim_child_burst",
                    "kind": "gameplay",
                    "text": "A hit emits three child projectiles.",
                    "backedBy": ["call_spawn_shards"],
                },
            ],
        },
        "runtimeProgram": {
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
            "schema": RUNTIME_PROGRAM_SCHEMA,
            "entities": [
                {"id": "item", "kind": "item_body"},
                {"id": "held_body", "kind": "owner_attached_projectile"},
                {"id": "child_shard", "kind": "child_projectile"},
            ],
            "bindings": [
                {"id": "bind_primary", "input": "primary_use", "action": "spawn_entity", "target": "held_body"},
            ],
            "calls": [
                {
                    "id": "call_item_stats", "fn": "configure_item_stats", "target": "item",
                    "params": {"damageClass": "melee", "damage": 42, "knockback": 5.0, "useTimeTicks": 24, "useAnimationTicks": 24, "manaCost": 0, "rarity": 2, "valueCopper": 15000, "maxStack": 1, "craftYield": 1, "widthPx": 40, "heightPx": 40, "scale": 1.0},
                },
                {
                    "id": "call_item_use", "fn": "configure_item_use", "target": "item",
                    "params": {"useStyle": "shoot", "autoReuse": True, "useTurn": True, "hideUseGraphic": True, "disableMeleeHitbox": True, "channel": False, "holdoutOffsetX": 0, "holdoutOffsetY": 0, "handPose": "two_handed", "releaseTiming": "immediate"},
                },
                {
                    "id": "call_spawn_held", "fn": "configure_spawn", "target": "held_body",
                    "params": {"speedPxPerTick": 1.0, "count": 1, "spreadRadians": 0.0, "offsetPx": 18, "aim": "cursor", "placement": "owner_center"},
                },
                {
                    "id": "call_damage_held", "fn": "set_projectile_damage", "target": "held_body",
                    "params": {"damageClass": "melee", "damage": 42, "knockback": 5.0, "ownerHitCheck": True},
                },
                {"id": "call_life_held", "fn": "set_projectile_lifetime", "target": "held_body", "params": {"lifetimeTicks": 30}},
                {"id": "call_hitbox_held", "fn": "set_projectile_hitbox", "target": "held_body", "params": {"widthPx": 64, "heightPx": 32, "drawScale": 1.0, "hitboxScale": 1.0}},
                {"id": "call_collision_held", "fn": "set_projectile_collision", "target": "held_body", "params": {"tileCollide": False, "ignoreWater": False, "bounceCount": 0, "pierce": 3, "extraUpdates": 0, "npcImmunityMode": "local", "localNpcHitCooldownTicks": 10}},
                {"id": "call_move_held", "fn": "move_forward_then_retract", "target": "held_body", "params": {"rangeTiles": 6.0, "durationTicks": 24}},
                {
                    "id": "call_spawn_shards", "fn": "spawn_entity_on_event", "target": "held_body",
                    "params": {"event": "on_hit", "entity": "child_shard", "count": 3, "spreadRadians": 0.75, "damageMultiplier": 0.45, "delayTicks": 0},
                },
                {
                    "id": "call_spawn_child", "fn": "configure_spawn", "target": "child_shard",
                    "params": {"speedPxPerTick": 9.0, "count": 1, "spreadRadians": 0.0, "offsetPx": 0, "aim": "velocity", "placement": "item_use_origin"},
                },
                {
                    "id": "call_damage_child", "fn": "set_projectile_damage", "target": "child_shard",
                    "params": {"damageClass": "ranged", "damage": 18, "knockback": 2.0, "ownerHitCheck": False},
                },
                {"id": "call_life_child", "fn": "set_projectile_lifetime", "target": "child_shard", "params": {"lifetimeTicks": 120}},
                {"id": "call_hitbox_child", "fn": "set_projectile_hitbox", "target": "child_shard", "params": {"widthPx": 10, "heightPx": 10, "drawScale": 0.7, "hitboxScale": 1.0}},
                {"id": "call_collision_child", "fn": "set_projectile_collision", "target": "child_shard", "params": {"tileCollide": True, "ignoreWater": False, "bounceCount": 0, "pierce": 1, "extraUpdates": 0, "npcImmunityMode": "local", "localNpcHitCooldownTicks": -1}},
                {"id": "call_move_child", "fn": "move_gravity_arc", "target": "child_shard", "params": {"gravityPerTick": 0.12}},
            ],
        },
        "id": "dev_" + str(abs(hash(key)))[:16],
        "recipeKey": key,
        "parentA": parent_a,
        "parentB": parent_b,
        "debug": {
            "planner": "deterministic_dev_low_level_fixture",
            "llmStageAccounting": {
                "gameplayAuthorCalls": 0,
                "gameplayRepairCalls": 0,
                "visualDirectorCalls": 0,
                "visualRepairCalls": 0,
                "vfxDirectorCalls": 0,
                "vfxRepairCalls": 0,
            },
        },
    }


__all__ = ["deterministic_low_level_plan"]
