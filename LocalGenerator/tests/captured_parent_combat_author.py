"""Test-only replay projection for two fixed archives predating explicit child bases.

Production never accepts old Author syntax. Archived JSON and its delivery hashes
stay unchanged; current replay fixtures state the old independent child choice.
"""
from copy import deepcopy


def captured_parent_combat_author(document):
    projected = deepcopy(document)
    rows = projected.get("runtimeProgram", {}).get("calls", []) + projected.get("callsUpsert", [])
    for row in rows:
        if row.get("fn") not in {"spawn_entity_on_event", "target_and_fire"}:
            continue
        params = row.get("params")
        if not isinstance(params, dict):
            continue
        assert "damageBasis" not in params and "knockbackBasis" not in params
        params.update(damageBasis="authored_child", knockbackBasis="authored_child")
        if row["fn"] == "target_and_fire":
            assert "damageMultiplier" not in params
            params["damageMultiplier"] = 1.0
    return projected
