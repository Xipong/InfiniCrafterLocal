"""Repair guidance cannot turn an intentionally finite producer into a pool."""
from copy import deepcopy

from prompt_packet_helpers import request_dossier
from repair_test_helpers import assert_repaired_source, repair_with_response
from test_author_prompt_consistency import _stationary_periodic_shooter


def test_repair_cannot_add_a_replenishable_pool_to_a_valid_finite_producer(monkeypatch):
    good, root, _ = _stationary_periodic_shooter()
    broken = deepcopy(good)
    stats = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "item_stats")
    correction = deepcopy(stats)
    stats["params"]["damage"] = True
    before = deepcopy(broken)
    unwanted_pool = {"id": "invented_pool", "fn": "descendant_limit",
                     "target": root, "params": {"maxActive": 3}}
    repaired, request = repair_with_response(monkeypatch, broken, {
        "note": "Fix damage; try to redesign an already valid producer",
        "callsUpsert": [correction, unwanted_pool],
    }, "json_schema", out_of_scope_response=True)
    dossier = request_dossier(request)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": stats["id"], "paths": ["params.damage"]}]
    assert dossier["acceptedItemContext"]["runtimeProgram"] == broken["runtimeProgram"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    wire = assert_repaired_source(repaired, good)
    assert all("descendantMaxActive" not in row.get("spawn", {}) for row in wire["runtimeProgram"]["entities"])
    assert broken == before
