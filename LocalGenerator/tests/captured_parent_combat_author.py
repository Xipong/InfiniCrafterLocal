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


def historical_child_combat_wire(document):
    """Remove only asserted equivalent new selectors for archived hash comparison."""
    projected = deepcopy(document)
    for entity in projected.get("runtimeProgram", {}).get("entities", []):
        targeting = entity.get("targeting", {})
        if targeting:
            assert targeting.pop("damageBasis") == "authored_child"
            assert targeting.pop("knockbackBasis") == "authored_child"
            assert targeting.pop("damageMultiplier") == 1.0
        for event in entity.get("events", []):
            if event.get("action") == "spawn_entity_on_event":
                assert event.pop("damageBasis") == "authored_child"
                assert event.pop("knockbackBasis") == "authored_child"
    contract = projected.get("runtimeContract")
    if isinstance(contract, dict):
        kept = []
        for receipt in contract["finalWireReceipts"]:
            fn = receipt.get("fn")
            name = receipt.get("authoredPath", "").rsplit(".params.", 1)[-1]
            if fn in {"spawn_entity_on_event", "target_and_fire"} and name in {"damageBasis", "knockbackBasis"}:
                assert receipt["value"] == "authored_child" and receipt["status"] == "delivered"
            elif fn == "target_and_fire" and name == "damageMultiplier":
                assert receipt["value"] == 1.0 and receipt["status"] == "delivered"
            else:
                kept.append(receipt)
        contract["finalWireReceipts"] = kept
        # This archive hashes diagnostic metadata too. The two new basis-kind
        # requirements are absent from its captured registry inventory.
        contract["validation"]["stats"]["registryDrivenChecks"]["requirements"] -= 2
    return projected
