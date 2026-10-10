"""Finite test-only projection of the two captured Author corpora.

The archived JSON and its hashes remain evidence of their original contracts.
These rewrites let the same captured choices exercise the current production
compiler and Repair. No runtime, storage loader or provider imports this helper.
"""

from copy import deepcopy
from typing import Any


def without_captured_projectile_alias_delta(compiled: dict[str, Any]) -> dict[str, Any]:
    """Reverse only proven alias/provenance deltas for frozen full-byte oracles.

    This is test-local, not a saved-wire importer. Do not materialize absent
    fields or replace the archived hashes with outputs from the current compiler.
    """
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, validate_runtime_wire

    assert validate_runtime_wire(compiled)["ok"]
    result = deepcopy(compiled)
    checks = result["runtimeContract"]["validation"]["stats"]["registryDrivenChecks"]
    conditional = [(cap.name, name) for cap in CAPABILITY_REGISTRY.values()
                   for name, spec in cap.params.items() if spec.omission_condition is not None]
    assert set(conditional) == {("configure_spawn", "count"), ("configure_spawn", "spreadRadians"),
                                ("set_projectile_collision", "bounceCount")}
    assert len(CAPABILITY_REGISTRY["pull_owner_to_event_target"].requirements) == 1
    # B15 retains the old action-4 receipt owner beside its current alias.
    # It adds exactly one registry inventory requirement, not a gameplay leaf.
    current = CAPABILITY_REGISTRY["damage_nearest_on_event"]
    retained = CAPABILITY_REGISTRY["chain_damage_on_event"]
    assert current.wire_action == retained.name and retained.decision == "internal"
    assert current.requirements == retained.requirements and len(retained.requirements) == 1
    curve_requirements = len(CAPABILITY_REGISTRY["set_projectile_hitbox_curve"].requirements)
    assert curve_requirements == 3
    assert checks["requirements"] == 34 + curve_requirements
    checks["requirements"] -= len(retained.requirements)
    assert checks["requirements"] == 33 + curve_requirements
    checks["requirements"] = 29 + curve_requirements  # Reverse aliases only; retain accepted hitbox requirements.
    removed = set()
    for i, entity in enumerate(result["runtimeProgram"]["entities"]):
        spawn = entity.get("spawn", {})
        if "overTarget" in spawn:
            assert spawn["overTarget"] == {"heightTiles": 0, "delayTicks": 0}
            del spawn["overTarget"]
            removed.update(f"runtimeProgram.entities[{i}].spawn.overTarget.{key}"
                           for key in ("heightTiles", "delayTicks"))
    rows = result["runtimeContract"]["finalWireReceipts"]
    added = [row for row in rows if row["finalPath"] in removed]
    assert len(added) == len(removed) and {row["finalPath"] for row in added} == removed
    for row in added:
        assert row["fn"] == "configure_spawn" and row["status"] == "alias_lowering"
        assert row["authoredPath"].endswith(".params.position")
        assert type(row["value"]) is int and row["value"] == 0
    result["runtimeContract"]["finalWireReceipts"] = [row for row in rows if row["finalPath"] not in removed]
    for row in result["runtimeContract"]["finalWireReceipts"]:
        if not row.get("fn"):
            continue  # Global lowerers keep every byte and all original omissions.
        path = row["authoredPath"]
        if row["fn"] == "configure_spawn" and path.endswith(".params.position.at"):
            assert row["status"] == "delivered"
            row["authoredPath"] = path.removesuffix("position.at") + "placement"
        elif row["fn"] == "set_projectile_collision":
            if path.endswith(".params.updatesPerTick"):
                assert row["status"] == "delivered"
                row["authoredPath"] = path.removesuffix("updatesPerTick") + "extraUpdates"
            elif path.endswith(".params.immunity"):
                assert row["status"] == "alias_lowering" and row["value"] == "local"
                row["authoredPath"] = path.removesuffix("immunity") + "npcImmunityMode"
                row["status"] = "delivered"
            elif path.endswith(".params.immunity.localCooldown"):
                assert row["status"] == "delivered"
                row["authoredPath"] = path.removesuffix("immunity.localCooldown") + "localNpcHitCooldownEngineUnits"
        elif path.endswith(".params.when"):
            assert row["status"] == "delivered" and row["value"] in {"on_hit", "on_expire"}
            row["authoredPath"] = path.removesuffix("when") + "event"
        elif row["fn"] == "damage_area_on_event" and path.endswith(".params.radiusTiles"):
            assert row["status"] == "delivered" and row["value"] == 112
            row["authoredPath"] = path.removesuffix("radiusTiles") + "radiusPx"
    rows = result["runtimeContract"]["finalWireReceipts"]
    # Current event aliases put fn-selected literals before the trigger leaf.
    # Reverse that exact three-row order, not arbitrary receipt sorting.
    for i, original in enumerate(tuple(rows)):
        if not original["finalPath"].endswith(".action") or not original.get("fn"):
            continue
        action, opcode, event = rows[i:i + 3]
        prefix = action["finalPath"].removesuffix("action")
        assert opcode["finalPath"] == prefix + "actionCode" and event["finalPath"] == prefix + "event"
        assert action["status"] == opcode["status"] == "technical_projection"
        assert event["status"] == "delivered"
        assert action["fn"] == opcode["fn"] == event["fn"]
        assert action["callId"] == opcode["callId"] == event["callId"]
        rows[i:i + 3] = [event, action, opcode]
    return result


def project_captured_projectile_call(call: dict[str, Any]) -> None:
    params = call.get("params", {})
    fn = call.get("fn")
    if fn == "configure_spawn" and "placement" in params:
        anchor = params.pop("placement")
        assert anchor in {"item_use_origin", "ground_at_cursor", "cursor"}
        assert "position" not in params
        params["position"] = {"at": "activation_origin" if anchor == "item_use_origin" else anchor}
    elif fn == "set_projectile_collision" and "npcImmunityMode" in params:
        mode = params.pop("npcImmunityMode")
        cooldown = params.pop("localNpcHitCooldownEngineUnits")
        assert mode in {"owner", "local"}
        assert "immunity" not in params and "updatesPerTick" not in params
        # Preserve negative invalid values in the captured diagnostic case.
        # Only -1 is the historical once-per-NPC choice.
        params["immunity"] = (
            "owner_shared" if mode == "owner" else
            "once_per_npc" if cooldown == -1 else {"localCooldown": cooldown}
        )
        params["updatesPerTick"] = params.pop("extraUpdates") + 1
    elif fn in {"apply_status_on_event", "heal_owner_on_event", "damage_area_on_event", "spawn_entity_on_event"}:
        assert params.get("event") in {"on_hit", "on_expire"}
        assert "when" not in params
        params["when"] = params.pop("event")
        if fn == "damage_area_on_event":
            assert params["radiusPx"] == 112
            params["radiusTiles"] = params.pop("radiusPx") / 16
