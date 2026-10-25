
"""Actual Author packets keep registry mechanics without contradictory global prose."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def _stationary_periodic_shooter(pool=None):
    doc = build_capability_witness("target_and_fire")
    calls = doc["runtimeProgram"]["calls"]
    controller = next(row for row in calls if row["fn"] == "target_and_fire")
    calls.remove(controller)
    root, child = controller["target"], controller["params"]["shotEntity"]
    calls.append({"id": "periodic_shot", "fn": "spawn_entity_on_event", "target": root, "params": {
        "when": {'everySeconds': (30) / 60}, "entity": child, "count": 1, "spreadRadians": 0.0,
        "damageBasis": "authored_child", "knockbackBasis": "authored_child", "damageMultiplier": 1.0,
        'delaySeconds': (0) / 60,
    }})
    if pool is not None:
        calls.append({"id": "descendant_pool", "fn": "set_descendant_concurrency", "target": root,
                      "params": {"maxActive": pool}})
    return doc, root, child


@pytest.mark.parametrize("pool", [None, 3])
def test_stationary_periodic_shooter_is_admitted_without_targeting_controller(pool):
    doc, root_id, child_id = _stationary_periodic_shooter(pool)
    before = deepcopy(doc)
    assert not any(row["fn"] == "target_and_fire" for row in doc["runtimeProgram"]["calls"])
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert doc == before
    root = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == root_id)
    assert root["kind"] == "stationary_projectile"
    assert "controller" not in root and "targeting" not in root
    assert [(row["event"], row["action"], row["periodTicks"], row["entityId"])
            for row in root["events"]] == [("periodic", "spawn_entity_on_event", 30, child_id)]
    if pool is None:
        assert "descendantMaxActive" not in root["spawn"]
    else:
        assert root["spawn"]["descendantMaxActive"] == pool
    # Concurrency changes runtime occupancy, not the static graph/depth ceilings.
    for row in doc["runtimeProgram"]["calls"]:
        if row["id"] == "periodic_shot":
            row["params"]["entity"] = root_id
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_scoped_repair_explains_stationary_shooting_without_changing_permissions(monkeypatch, mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, _, _ = _stationary_periodic_shooter(pool=3)
    correction = deepcopy(next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "descendant_pool"))
    next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "descendant_pool")["params"]["maxActive"] = 0
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "Correct only invalid concurrent capacity", "realizationReplacement": doc["realization"],
        "callsUpsert": [correction],
    }, mode)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": "descendant_pool", "paths": ["params.maxActive"]}]
    card = next(row for row in dossier["existingBrokenCapabilityCards"] if row["fn"] == "set_descendant_concurrency")
    assert card == CAPABILITY_REGISTRY["set_descendant_concurrency"].prompt_card()
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
