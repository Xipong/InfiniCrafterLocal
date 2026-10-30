"""One Author choice delivers one existing native stat, with exact Lowery provenance."""
from collections import Counter
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from test_player_effect_primitives import source


SOURCES = ("configure_accessory", "configure_armor", "apply_generated_buff_on_use")


def stat_source(fn, **params):
    document, call = source(fn, {})
    call["params"].pop("playerEffect")
    call["params"].update(params)
    return document, call


def stat_target(wire, fn):
    return (wire["gameplay"]["generatedBuff"] if fn == "apply_generated_buff_on_use"
            else wire["armor" if fn == "configure_armor" else "accessory"])


@pytest.mark.parametrize("fn", SOURCES)
@pytest.mark.parametrize("rate,units", [(2, 4), (-1.5, -3)])
def test_one_regen_and_treasure_choice_reuses_existing_wire_once(fn, rate, units):
    document, call = stat_source(fn, lifeRegen=rate, regenWhen="stationary",
                                 treasureSense=True, treasureWhen="stationary")
    before = deepcopy(document)
    wire = compile_runtime_program(document)
    assert validate_runtime_wire(wire)["ok"]
    target = stat_target(wire, fn)
    assert target["lifeRegen"] == units
    assert target["lifeRegenCondition"] == "stationary"
    treasure = "oreSenseRadiusTiles" if fn == "apply_generated_buff_on_use" else "treasureSense"
    assert target[treasure] == (1 if fn == "apply_generated_buff_on_use" else True)
    assert target["treasureSenseCondition"] == "stationary"
    assert "playerEffect" not in target
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    own = [row for row in receipts if row.get("callId") == call["id"]]
    counts = Counter(row["finalPath"] for row in own)
    assert counts[next(row["finalPath"] for row in own
                       if row["authoredPath"].endswith(".params.lifeRegen"))] == 1
    assert counts[next(row["finalPath"] for row in own
                       if row["authoredPath"].endswith(".params.treasureSense"))] == 1
    assert audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    bare = deepcopy(wire)
    bare.pop("runtimeContract")
    assert validate_runtime_wire(bare)["ok"]
    assert document == before


@pytest.mark.parametrize("fn", SOURCES)
@pytest.mark.parametrize("field,value", [("lifeRegenHpPerSecond", 2), ("lifeRegen", 2),
                                          ("highlightTreasure", True)])
def test_parallel_nested_stats_are_rejected_instead_of_double_applying(fn, field, value):
    document, call = stat_source(fn, lifeRegen=2, treasureSense=True)
    call["params"]["playerEffect"] = {field: value}
    assert not validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(stat_source(fn, lifeRegen=2)[0])
    target = stat_target(wire, fn)
    target["playerEffect"] = {"lifeRegenUnits": 4} if field != "highlightTreasure" else {field: value}
    wire.pop("runtimeContract")
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fn", SOURCES)
@pytest.mark.parametrize("field,value", [("lifeRegenHpPerSecond", 2), ("oreSenseEnabled", True)])
def test_retired_root_spellings_are_not_a_second_fresh_author_api(fn, field, value):
    document, call = stat_source(fn, lifeRegen=2, treasureSense=True)
    call["params"][field] = value
    assert not validate_runtime_program(document)["ok"]


@pytest.mark.parametrize("fn", SOURCES)
@pytest.mark.parametrize("value", [None, "", "resting", False, 1])
def test_present_invalid_conditions_fail_in_author_and_bare_wire(fn, value):
    document, call = stat_source(fn, lifeRegen=2)
    call["params"]["regenWhen"] = value
    assert not validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(stat_source(fn, lifeRegen=2)[0])
    wire.pop("runtimeContract")
    for key in ("lifeRegenCondition", "treasureSenseCondition"):
        malformed = deepcopy(wire)
        stat_target(malformed, fn)[key] = value
        assert not validate_runtime_wire(malformed)["ok"]


@pytest.mark.parametrize("fn", ("configure_accessory", "apply_generated_buff_on_use"))
def test_a_condition_alone_is_not_an_executable_stat(fn):
    document, _ = stat_source(fn, regenWhen="stationary", treasureWhen="stationary")
    assert not validate_runtime_program(document)["ok"]


@pytest.mark.parametrize("fn", SOURCES)
def test_missing_conditions_preserve_old_wire_and_old_receipt_identity(fn):
    wire = compile_runtime_program(stat_source(fn, lifeRegen=2, treasureSense=True)[0])
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    # Existing same-level historical receipt declarations preserve accepted
    # persisted provenance, while old spellings are rejected for fresh Author.
    for row in receipts:
        if row.get("authoredPath", "").endswith(".params.lifeRegen"):
            row["authoredPath"] += "HpPerSecond"
    assert audit_compiler_receipts(receipts, final_document=wire)["ok"]
    wire.pop("runtimeContract")
    target = stat_target(wire, fn)
    target.pop("lifeRegenCondition")
    target.pop("treasureSenseCondition")
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mode", ("json_object", "json_schema"))
def test_lowery_regen_repair_cannot_change_valid_treasure_or_conditions(monkeypatch, mode):
    from prompt_packet_helpers import request_dossier
    from repair_test_helpers import repair_with_response
    from test_source_unit_guidance import _offline
    getattr(_offline, "__wrapped__")(monkeypatch)
    document, call = stat_source("apply_generated_buff_on_use", lifeRegen=.25,
                                 regenWhen="stationary", treasureSense=True,
                                 treasureWhen="stationary")
    hostile = deepcopy(call)
    hostile["params"].update(lifeRegen=.5, regenWhen="always", treasureSense=False)
    repaired, request = repair_with_response(monkeypatch, document,
        {"note": "repair only the regen half-HP step", "callsUpsert": [hostile]}, mode)
    assert request_dossier(request)["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": call["id"], "paths": ["params.lifeRegen"]}]
    actual = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])
    assert actual["params"] == {**call["params"], "lifeRegen": .5}
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
