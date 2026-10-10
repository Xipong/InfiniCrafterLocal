"""A12 curve choices reach exact wire/receipts and preserve frozen Repair."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture
from infini_local.qa.capability_library_audit import capability_library_audit
from sentry_contract_checks import without_declared_targeting_neutrals


FN = "set_projectile_hitbox_curve"
PARAMS = {"startScale": .5, "endScale": 4, "startDelayTicks": 5, "durationTicks": 60, "curve": "exponential", "mirrorToSprite": False}


def _call(doc, fn=FN):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)


def _source():
    doc = build_capability_witness(FN)
    _call(doc)["params"] = deepcopy(PARAMS)
    return doc


def _entity(wire):
    return next(row for row in wire["runtimeProgram"]["entities"] if "hitboxCurve" in row)


def _payload(doc):
    return {key: doc[key] for key in ("runtimeProgram", "gameplay", "accessory", "armor")}


@pytest.mark.parametrize("curve", ["linear", "exponential"])
@pytest.mark.parametrize("mirror", [False, True])
def test_explicit_curve_projection_and_provenance(curve, mirror):
    doc = _source()
    _call(doc)["params"].update(curve=curve, mirrorToSprite=mirror)
    frozen = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert _entity(wire)["hitboxCurve"] == _call(doc)["params"]
    assert doc == frozen and validate_runtime_wire(wire)["ok"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert len([row for row in rows if row.get("fn") == FN]) == len(PARAMS)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=wire)["ok"]
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]


@pytest.mark.parametrize("name,value", [
    ("startScale", None), ("startScale", True), ("startScale", "1"), ("startScale", .249), ("startScale", 8.001),
    ("endScale", None), ("endScale", 0), ("endScale", 9), ("endScale", float("inf")), ("endScale", float("nan")),
    ("startDelayTicks", -1), ("startDelayTicks", 21601), ("startDelayTicks", .5), ("startDelayTicks", False),
    ("durationTicks", 0), ("durationTicks", 21601), ("durationTicks", 1.5), ("durationTicks", True),
    ("curve", "smooth"), ("curve", None), ("curve", []), ("mirrorToSprite", 0), ("mirrorToSprite", None),
])
def test_present_invalid_authored_and_wire_values_are_rejected(name, value):
    doc = _source()
    wire = compile_runtime_program(doc)
    _call(doc)["params"][name] = value
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    _entity(wire)["hitboxCurve"][name] = value
    wire.pop("runtimeContract")
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("name", list(PARAMS))
def test_every_present_curve_requires_all_six_explicit_choices(name):
    doc = _source()
    wire = compile_runtime_program(doc)
    del _call(doc)["params"][name]
    assert not validate_runtime_program(doc)["ok"]
    del _entity(wire)["hitboxCurve"][name]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mutation", ["null", "unknown", "item_target", "duplicate", "missing_receipt", "wrong_receipt_entity", "changed_wire"])
def test_no_ambiguous_container_or_provenance_gap(mutation):
    doc = _source()
    wire = compile_runtime_program(doc)
    entity = _entity(wire)
    if mutation == "null":
        entity["hitboxCurve"] = None
    elif mutation == "unknown":
        entity["hitboxCurve"]["nameInference"] = True
    elif mutation == "item_target":
        wire["runtimeProgram"]["entities"][0]["hitboxCurve"] = entity.pop("hitboxCurve")
    elif mutation == "duplicate":
        call = deepcopy(_call(doc)); call["id"] = "second_curve"
        doc["runtimeProgram"]["calls"].append(call)
        assert not validate_runtime_program(doc)["ok"]
        return
    elif mutation == "missing_receipt":
        wire["runtimeContract"]["finalWireReceipts"] = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("fn") != FN]
    elif mutation == "wrong_receipt_entity":
        for row in wire["runtimeContract"]["finalWireReceipts"]:
            if row.get("fn") == FN: row["finalPath"] = row["finalPath"].replace("entities[1]", "entities[0]")
    else:
        entity["hitboxCurve"]["endScale"] = 3
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("name,valid", [("startScale", 1.5), ("endScale", 3), ("startDelayTicks", 0), ("durationTicks", 100)])
def test_repair_changes_only_the_invalid_curve_leaf(name, valid):
    doc = _source()
    _call(doc)["params"][name] = -1
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    fixed = deepcopy(_call(doc)); fixed["params"][name] = valid
    fixed["params"]["mirrorToSprite"] = True
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [fixed], "note": "repair only the invalid curve leaf"}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(before); _call(expected)["params"][name] = valid
    assert repaired == expected
    compile_runtime_program(repaired)


def test_curve_conflicts_with_line_geometry_and_sprite_mirror_has_one_owner():
    for driver in ("channel_beam", "move_whip_lash"):
        doc = build_capability_witness(driver)
        owner = _call(doc, driver)["target"]
        doc["runtimeProgram"]["calls"].append({"id": "new_curve", "fn": FN, "target": owner, "params": deepcopy(PARAMS)})
        report = validate_runtime_program(doc)
        assert not report["ok"] and any(row["code"] == "exclusive_component_conflict" for row in report["errors"])
    doc = build_capability_witness("move_expanding_wave")
    owner = _call(doc, "move_expanding_wave")["target"]
    doc["runtimeProgram"]["calls"].append({"id": "new_curve", "fn": FN, "target": owner, "params": {**PARAMS, "mirrorToSprite": True}})
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    fixed = deepcopy(_call(doc)); fixed["params"].update(mirrorToSprite=False, endScale=7)
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [fixed], "note": "keep independently authored visual growth"}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, patch)
    assert _call(repaired)["params"] == PARAMS
    assert _call(repaired, "move_expanding_wave") == _call(doc, "move_expanding_wave")
    compile_runtime_program(repaired)


@pytest.mark.parametrize("name", NON_ARCHETYPAL_FIXTURES)
def test_no_curve_preserves_frozen_gameplay_payload(name):
    capture = json.loads((Path(__file__).parent / "fixtures/hitbox_curve_legacy_payload_sha256.json").read_text())
    from beam_contract_checks import without_declared_beam_neutrals
    from sentry_contract_checks import without_declared_targeting_neutrals
    from tests.captured_projectile_author import without_captured_projectile_alias_delta
    from captured_parent_combat_author import historical_child_combat_wire
    wire = without_declared_targeting_neutrals(without_declared_beam_neutrals(
        without_captured_projectile_alias_delta(historical_child_combat_wire(compile_runtime_program(build_runtime_fixture(name))))))
    assert all("hitboxCurve" not in entity for entity in wire["runtimeProgram"]["entities"])
    text = json.dumps(_payload(wire), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(text.encode()).hexdigest() == capture["sha256"][name]


def test_full_request_and_numeric_native_range_audit_cover_the_new_owner():
    _, user, _ = build_initial_author_request({}, {}, {}, {}, "curve", model_name="test-model")
    catalog = json.loads(user)["runtimeCapabilityContract"]["catalog"]
    card = next(row for row in catalog["capabilities"] if row["fn"] == FN)
    assert set(card["params"]) == set(PARAMS)
    assert len(card["requires"]) == 3
    audit = capability_library_audit()
    assert audit["ok"]
    rows = [row for row in audit["rangeParity"] if row["capability"] == FN]
    assert {row["param"] for row in rows} == {"startScale", "endScale", "startDelayTicks", "durationTicks"}
    assert all(row["preserved"] for row in rows)
