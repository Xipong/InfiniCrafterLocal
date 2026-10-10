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
    result = historical_author_binding_wire(compiled)
    checks = result["runtimeContract"]["validation"]["stats"]["registryDrivenChecks"]
    conditional = [(cap.name, name) for cap in CAPABILITY_REGISTRY.values()
                   for name, spec in cap.params.items() if spec.omission_condition is not None]
    assert set(conditional) == {("configure_spawn", "count"), ("configure_spawn", "spreadRadians"),
                                ("set_projectile_collision", "bounceCount")}
    assert len(CAPABILITY_REGISTRY["pull_owner_to_event_target"].requirements) == 1
    added_modifier_caps = ("set_projectile_hitbox_curve", "set_projectile_turn_modifier", "set_projectile_speed_modifier",
                           "set_projectile_homing_modifier", "set_projectile_visual_scale_curve", "orient_whip_to_owner_gravity")
    added_requirements = sum(len(CAPABILITY_REGISTRY[fn].requirements) for fn in added_modifier_caps)
    assert added_requirements == 9
    assert checks["requirements"] == 35 + added_requirements
    checks["requirements"] -= 4  # Three branch proofs and the explicit owner-pull event.
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


def project_captured_author_notation(document: dict[str, Any]) -> dict[str, Any]:
    """Exact v4->v5 notation projection for archived tests only; never admission."""
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
    from infini_local.core.runtime_authoring.capability_registry import INPUT_KIND_REGISTRY, BINDING_ACTION_REGISTRY
    projected = deepcopy(document)
    program = projected.get("runtimeProgram", {})
    if "schema" in program:
        assert program["schema"] in {"infini.runtime-program.authoring.v4", "infini.runtime-program.authoring.v5"}
        program["schema"] = "infini.runtime-program.authoring.v5"
    for row in program.get("calls", []) + projected.get("callsUpsert", []):
        if not isinstance(row, dict):
            continue
        cap = CAPABILITY_REGISTRY.get(row.get("fn"))
        if cap is None:
            continue
        if cap.target_kinds == ("item_body",):
            row.pop("target", None)
        if not cap.params and row.get("params") == {}:
            del row["params"]
    for row in program.get("bindings", []) + projected.get("bindingsUpsert", []):
        if not isinstance(row, dict):
            continue
        if "usePolicy" in row:
            assert isinstance(row["usePolicy"], dict)
            row.update(row.pop("usePolicy"))
        action = row.get("action")
        inp = INPUT_KIND_REGISTRY.get(row.get("input"))
        spec = BINDING_ACTION_REGISTRY.get(action.get("kind")) if isinstance(action, dict) else None
        if spec is None or inp is None:
            continue  # Preserve historically invalid selectors, not guess them.
        if spec.target_kinds == ("item_body",):
            action.pop("targetId", None)
        if len(inp.allowed_actions) == 1:
            assert action.get("kind") == inp.allowed_actions[0]
            del action["kind"]
        if not action:
            row.pop("action")
        if row["input"] not in {"primary_use", "alternate_use"} or spec.name == "place_item":
            for key, value in (("stackCost", 1 if spec.name == "place_item" else 0), ("contactDamage", False)):
                if key in row:
                    if type(row[key]) is type(value) and row[key] == value:
                        del row[key]
    return projected


def historical_author_binding_wire(compiled: dict[str, Any]) -> dict[str, Any]:
    """Reverse only authenticated v5 notation provenance for frozen v4 oracles."""
    import re
    result = deepcopy(compiled)
    contract = result["runtimeContract"]
    rows = contract["finalWireReceipts"]
    new = [r for r in rows if r.get("lowererId") == "author_binding_lanes"]
    assert new
    for row in new:
        assert row["status"] == "technical_projection" and row["authoredPaths"]
        path = row["finalPath"]
        value = result
        for key, index in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path):
            value = value[int(index)] if index else value[key]
        assert type(value) is type(row["value"]) and value == row["value"]
    contract["finalWireReceipts"] = [r for r in rows if r not in new]
    for row in contract["finalWireReceipts"]:
        if row.get("lowererId") == "primary_entity_to_binding_role":
            match = re.fullmatch(r"runtimeProgram.bindings\[(\d+)\].role", row["finalPath"])
            assert match and row["authoredPaths"][0] == "runtimeProgram.primaryEntityId"
            source = next(path for path in row["authoredPaths"] if path.startswith("runtimeProgram.bindings["))
            prefix = source.split("]", 1)[0] + "]"
            row["authoredPaths"] = ["runtimeProgram.primaryEntityId", prefix + ".usePolicy.action.targetId"]
    manifest = contract["technicalLoweringAudit"]["lowerers"]
    assert sum(row["id"] == "author_binding_lanes" for row in manifest) == 1
    manifest[:] = [row for row in manifest if row["id"] != "author_binding_lanes"]
    role = next(row for row in manifest if row["id"] == "primary_entity_to_binding_role")
    assert role["inputs"] == ["runtimeProgram.primaryEntityId", "runtimeProgram.bindings[].action.targetId", "runtimeProgram.bindings[].id", "runtimeProgram.bindings[].input", "runtimeProgram.bindings[].action.kind", "runtimeProgram.entities[].id", "runtimeProgram.entities[].kind"]
    role["inputs"] = ["runtimeProgram.primaryEntityId", "runtimeProgram.bindings[].usePolicy.action.targetId"]
    return result
