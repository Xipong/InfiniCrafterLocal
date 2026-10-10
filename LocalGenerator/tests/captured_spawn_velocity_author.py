"""Finite test-only archive projection; production never imports old Author IR."""
from copy import deepcopy


def captured_spawn_velocity_author(document):
    projected = deepcopy(document)
    rows = projected.get("runtimeProgram", {}).get("calls", []) + projected.get("callsUpsert", [])
    for row in rows:
        if row.get("fn") != "configure_spawn" or "speedPxPerUpdate" not in row.get("params", {}):
            continue
        params = row["params"]
        assert "velocity" not in params
        params["velocity"] = {"constantSpeedPxPerUpdate": params.pop("speedPxPerUpdate")}
    return projected


def historical_spawn_velocity_wire(document):
    """Assert the constant projection, then compare its unchanged archived wire."""
    projected = deepcopy(document)
    for entity in projected.get("runtimeProgram", {}).get("entities", []):
        assert "velocityDistribution" not in entity.get("spawn", {})
        assert all("hitTargetSpawn" not in action for action in entity.get("events", []))
    contract = projected.get("runtimeContract")
    if isinstance(contract, dict):
        for receipt in contract["finalWireReceipts"]:
            if receipt.get("fn") == "configure_spawn" and ".params.velocity." in receipt.get("authoredPath", ""):
                assert receipt["authoredPath"].endswith(".params.velocity.constantSpeedPxPerUpdate")
                assert receipt["finalPath"].endswith(".spawn.speedPxPerTick") and receipt["status"] == "delivered"
                receipt["authoredPath"] = receipt["authoredPath"].replace(".params.velocity.constantSpeedPxPerUpdate", ".params.speedPxPerUpdate")
        # Archives include global registry inventory: A11 adds 19 velocity
        # constraints plus 3 target-spawn constraints, the existing spawn
        # event's radial/disk spread guard, and one typed reference.
        checks = contract["validation"]["stats"]["registryDrivenChecks"]
        # Native-shot/sampling exclusivity is a new diagnostic only. It does
        # not alter any of these constant-speed, no-weapon-ammo captures.
        from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
        constraint = [row for row in CAPABILITY_REGISTRY["configure_spawn"].requirements
                      if row.kind == "present_params_forbid_item_capability_when_active_spawn"]
        assert len(constraint) == 1 and constraint[0].equals == "native_shot"
        assert constraint[0].param == "velocity" and constraint[0].capability == "configure_weapon_ammo"
        checks["requirements"] -= 24
        checks["typedReferences"] -= 1
    return projected
