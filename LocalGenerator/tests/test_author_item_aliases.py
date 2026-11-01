"""Exact item aliases preserve the existing C# wire and frozen Repair choices."""
from copy import deepcopy

import pytest
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from test_registry_receipt_identity import _call


def _source(fn):
    document = build_capability_witness(fn)
    call = _call(document, fn)
    return document, call


@pytest.mark.parametrize("hidden", [False, True])
def test_native_visibility_has_one_exact_receipt(hidden):
    source, call = _source("item_use")
    call["params"]["hideUseGraphic"] = hidden
    wire = compile_runtime_program(source)
    assert wire["runtimeProgram"]["itemUse"]["hideUseGraphic"] is hidden
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    receipt = next(row for row in rows if row["finalPath"] == "runtimeProgram.itemUse.hideUseGraphic")
    receipt["value"] = not hidden
    assert not audit_compiler_receipts(rows, final_document=wire)["ok"]


@pytest.mark.parametrize("layer,inactive", [("tile", "wall"), ("wall", "tile")])
@pytest.mark.parametrize("identifier,style", [(0, 0), (18, 7), (65535, 255)])
def test_placement_layer_has_one_explicit_id_and_exact_inactive_wire_literal(layer, inactive, identifier, style):
    fn = f"place_{layer}"
    source, call = _source(fn)
    call["params"] = {f"{layer}Id": identifier, "placeStyle": style}
    wire = compile_runtime_program(source)
    placement = next(row for row in wire["runtimeProgram"]["bindings"] if row["usePolicy"]["action"]["kind"] == "place_item")["usePolicy"]["action"]["placement"]
    assert placement == {f"{layer}Id": identifier, f"{inactive}Id": -1, "placeStyle": style}
    receipt = next(row for row in wire["runtimeContract"]["finalWireReceipts"] if row.get("fn") == fn and row["finalPath"].endswith(f".{inactive}Id"))
    assert receipt["status"] == "technical_projection" and receipt["authoredPath"].endswith(".fn")
    assert validate_runtime_wire(wire)["ok"]
    receipt["value"] = 0
    assert not audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]


@pytest.mark.parametrize("layer", ["tile", "wall"])
@pytest.mark.parametrize("bad", [-1, 65536, True])
def test_active_placement_id_is_never_disabled_or_guessed(layer, bad):
    source, call = _source(f"place_{layer}")
    call["params"][f"{layer}Id"] = bad
    assert not validate_runtime_program(source)["ok"]


def test_placed_item_sprite_cannot_be_attached_to_a_wall_alias():
    source, _ = _source("placed_sprite")
    placement = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "place_tile")
    placement.update(fn="place_wall", params={"wallId": 1, "placeStyle": 0})
    report = validate_runtime_program(source)
    assert not report["ok"] and any(row["code"] == "placed_body_placement_reference" for row in report["errors"])


@pytest.mark.parametrize("cooldown", [0, 60, 3600])
def test_home_recall_keeps_shared_cooldown_and_only_declared_inactive_blink_fields(cooldown):
    source, call = _source("recall_home_on_use")
    call["params"] = {'cooldown': (cooldown) / 60}
    wire = compile_runtime_program(source)
    assert {key: wire["gameplay"][key] for key in ("mobilityMode", "mobilityRangeTiles", "mobilityCooldownTicks", "mobilitySafeTileOnly")} == {
        "mobilityMode": "recall_home", "mobilityRangeTiles": 0,
        "mobilityCooldownTicks": cooldown, "mobilitySafeTileOnly": False,
    }
    assert validate_runtime_wire(wire)["ok"]
    for key in ("mode", "range", "safeTileOnly"):
        hostile = deepcopy(source)
        next(row for row in hostile["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"][key] = 1
        assert not validate_runtime_program(hostile)["ok"]


SET_FIELDS = {
    "critChance": ("setBonusGenericCrit", 3, 3),
    "moveSpeedBonus": ("setBonusMovementSpeed", 25, 0.25),
    "lifeRegen": ("setBonusLifeRegen", -0.5, -1),
    "manaRegen": ("setBonusManaRegen", 2, 2),
    "minionSlotsBonus": ("setBonusMinionSlots", 1, 1),
    "sentrySlotsBonus": ("setBonusSentrySlots", 2, 2),
    "manaCostReduction": ("setBonusManaCostReduction", 5, 0.05),
    "ammoSaveChancePercent": ("setBonusAmmoSaveChance", 75, 0.75),
    "aggroPoints": ("setBonusAggro", -2, -2),
    "damageReduction": ("setBonusEndurance", 10, 0.10),
    "armorPenetration": ("setBonusArmorPenetration", 4, 4),
}


def test_all_eleven_set_bonuses_keep_their_previous_fields_units_and_receipts():
    source, call = _source("armor")
    call["params"]["setBonuses"] = {name: row[1] for name, row in SET_FIELDS.items()}
    assert set(CAPABILITY_REGISTRY["armor"].params["setBonuses"].properties) == set(SET_FIELDS)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for name, (field, _, expected) in SET_FIELDS.items():
        assert wire["armor"][field] == expected
        receipt = next(row for row in rows if row.get("fn") == "armor" and row["finalPath"] == "armor." + field)
        assert receipt["authoredPath"].endswith(".params.setBonuses." + name)
    assert validate_runtime_wire(wire)["ok"]
    # Retired flat parameter receipts are refused without rewriting wire fields.
    for row in rows:
        if row.get("fn") == "armor" and ".params.setBonuses." in row["authoredPath"]:
            stem, name = row["authoredPath"].split(".params.setBonuses.")
            row["authoredPath"] = stem + ".params.setBonus" + name[0].upper() + name[1:]
    assert not audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]


@pytest.mark.parametrize("slot,key,bonus,valid", [
    ("head", "set", 1, True), ("body", "set", 1, False),
    ("legs", "set", -1, False), ("head", "", -1, False),
    ("body", "", 0, True),
])
def test_grouped_set_bonuses_keep_head_and_set_key_requirements(slot, key, bonus, valid):
    source, call = _source("armor")
    call["params"].update(slot=slot, setKey=key, setBonuses={"aggroPoints": bonus})
    assert validate_runtime_program(source)["ok"] is valid


@pytest.mark.parametrize("condition,expected", [
    ("grounded", {"useConditionMode": "grounded"}),
    ("not_wet", {"useConditionMode": "not_wet"}),
    ({"lifeAtLeast": 0}, {"useConditionMode": "life_above", "useConditionMinLife": 0}),
    ({"lifeAtLeast": 50}, {"useConditionMode": "life_above", "useConditionMinLife": 50}),
    ({"manaAtLeast": 1000}, {"useConditionMode": "mana_above", "useConditionMinMana": 1000}),
])
def test_condition_variants_keep_inclusive_resource_thresholds(condition, expected):
    source, call = _source("use_condition")
    call["params"] = {"input": "primary_use", "condition": condition}
    wire = compile_runtime_program(source)
    assert wire["gameplay"]["useConditions"] == [{"input": "primary_use", **expected}]
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("condition", [{}, {"lifeAtLeast": 1, "manaAtLeast": 1}, {"lifeAtLeast": True}, {"manaAtLeast": -1}, "life_above", ["grounded", "not_wet"]])
def test_condition_never_infers_threshold_or_combines_two_conditions(condition):
    source, call = _source("use_condition")
    call["params"] = {"input": "primary_use", "condition": condition}
    assert not validate_runtime_program(source)["ok"]


def test_armor_repair_preserves_the_other_valid_nested_set_bonus():
    source, call = _source("armor")
    call["params"]["setBonuses"] = {"lifeRegen": 0.25, "minionSlotsBonus": 2}
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.setBonuses.lifeRegen"]}]
    fixed = deepcopy(call)
    fixed["params"]["setBonuses"] = {"lifeRegen": 0.5, "minionSlotsBonus": 20}
    patch, audit = filter_repair_patch_scope(source, {"note": "repair one nested leaf", "callsUpsert": [fixed]}, scope)
    repaired = apply_repair_patch(source, patch)
    actual = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])
    assert actual["params"]["setBonuses"] == {"lifeRegen": 0.5, "minionSlotsBonus": 2}
    assert audit["ignoredChanges"] and validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("params,path", [
    ({"condition": {"lifeAtLeast": True}}, "params.condition.lifeAtLeast"),
    ({"condition": {}}, "params.condition"),
    ({}, "params.condition"),
    ({"condition": "invalid"}, "params.condition"),
])
def test_condition_repair_requires_an_explicit_complete_variant(params, path):
    source, call = _source("use_condition")
    call["params"] = {"input": "primary_use", **params}
    scope = build_runtime_repair_scope(source, validate_runtime_program(source)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [path]}]
    fixed = deepcopy(call)
    fixed["params"] = {"input": "primary_use", "condition": {"lifeAtLeast": 50}}
    patch, audit = filter_repair_patch_scope(source, {"note": "explicit threshold", "callsUpsert": [fixed]}, scope)
    repaired = apply_repair_patch(source, patch)
    assert audit["ok"] and validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    incomplete = deepcopy(call)
    incomplete["params"] = {"input": "primary_use", "condition": {}}
    patch, _ = filter_repair_patch_scope(source, {"note": "no threshold selected", "callsUpsert": [incomplete]}, scope)
    assert not validate_runtime_program(apply_repair_patch(source, patch))["ok"]


def test_unrelated_repair_cannot_change_a_valid_condition_or_threshold():
    source, call = _source("use_condition")
    call["params"] = {"input": "primary_use", "condition": {"lifeAtLeast": 50}}
    stats = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "item_stats")
    stats["params"]["damage"] = True
    scope = build_runtime_repair_scope(source, validate_runtime_program(source)["errors"])
    altered = deepcopy(call)
    altered["params"] = {"input": "primary_use", "condition": {"manaAtLeast": 1}}
    fixed_stats = deepcopy(stats)
    fixed_stats["params"]["damage"] = 10
    patch, audit = filter_repair_patch_scope(source, {"note": "fix damage", "callsUpsert": [fixed_stats, altered]}, scope)
    repaired = apply_repair_patch(source, patch)
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"] == call["params"]
    assert audit["ignoredChanges"] and validate_runtime_wire(compile_runtime_program(repaired))["ok"]

@pytest.mark.parametrize("bad", [True, 1001, 1.0, None])
@pytest.mark.parametrize("source_available", [False, True])
def test_grouped_armor_receipts_refuse_coherent_wrong_json_types(bad, source_available):
    source, call = _source("armor")
    call["params"]["setBonuses"] = {"aggroPoints": 1}
    wire = compile_runtime_program(source)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in receipts if r.get("authoredPath", "").endswith(".setBonuses.aggroPoints"))
    call["params"]["setBonuses"]["aggroPoints"] = bad
    assert not validate_runtime_program(source)["ok"]
    wire["armor"]["setBonusAggro"] = row["value"] = bad
    assert not audit_compiler_receipts(receipts, authored_document=source if source_available else None,
                                       final_document=wire)["ok"]


def test_prior_recall_receipt_is_refused_with_dedicated_current_recall_preserved():
    cap = CAPABILITY_REGISTRY["blink_on_use"]
    assert cap.params["mode"].enum == ("blink_to_cursor",)
    source, call = _source("blink_on_use")
    call["params"]["mode"] = "blink_to_cursor"
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    wire["gameplay"]["mobilityMode"] = "recall_home"
    next(r for r in rows if r.get("callId") == call["id"] and r.get("authoredPath", "").endswith(".params.mode"))["value"] = "recall_home"
    call["params"]["mode"] = "recall_home"
    before = deepcopy(wire)
    assert not audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_program(source)["ok"]
    assert wire == before
