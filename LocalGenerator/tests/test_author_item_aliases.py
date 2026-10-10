"""Exact item aliases preserve the existing C# wire and frozen Repair choices."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    compile_runtime_program, filter_repair_patch_scope, validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness


def _source(fn):
    document = build_capability_witness(fn)
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == fn)
    return document, call


@pytest.mark.parametrize("value,wire_value", [("hidden", "immediate"), ("visible", "on_release"), ("inherit", "")])
@pytest.mark.parametrize("native_hidden", [False, True])
def test_custom_held_sprite_enum_is_exact_and_native_visibility_independent(value, wire_value, native_hidden):
    source, call = _source("configure_item_use")
    call["params"].update(customHeldSprite=value, hideUseGraphic=native_hidden)
    wire = compile_runtime_program(source)
    assert wire["gameplay"]["releaseTiming"] == wire_value
    assert wire["runtimeProgram"]["itemUse"]["releaseTiming"] == wire_value
    assert wire["runtimeProgram"]["itemUse"]["hideUseGraphic"] is native_hidden
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("bad", ["", "immediate", "on_release", "after_charge", "Visible", None])
def test_old_or_invalid_visibility_tokens_are_not_new_author_values(bad):
    source, call = _source("configure_item_use")
    call["params"]["customHeldSprite"] = bad
    assert not validate_runtime_program(source)["ok"]


@pytest.mark.parametrize("old", ["", "immediate", "on_release", "after_charge"])
def test_persisted_visibility_receipts_keep_their_original_wire_token(old):
    source, call = _source("configure_item_use")
    call["params"]["customHeldSprite"] = "inherit"
    wire = compile_runtime_program(source)
    wire["gameplay"]["releaseTiming"] = old
    wire["runtimeProgram"]["itemUse"]["releaseTiming"] = old
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for row in rows:
        if row.get("fn") == "configure_item_use" and row["authoredPath"].endswith(".customHeldSprite"):
            row["authoredPath"] = row["authoredPath"].removesuffix("customHeldSprite") + "heldSpriteVisibilityHint"
            row["value"] = old
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("layer,inactive", [("tile", "wall"), ("wall", "tile")])
@pytest.mark.parametrize("identifier,style", [(0, 0), (18, 7), (65535, 255)])
def test_placement_layer_has_one_explicit_id_and_exact_inactive_wire_literal(layer, inactive, identifier, style):
    fn = f"configure_{layer}_placement"
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
    source, call = _source(f"configure_{layer}_placement")
    call["params"][f"{layer}Id"] = bad
    assert not validate_runtime_program(source)["ok"]


def test_placed_item_sprite_cannot_be_attached_to_a_wall_alias():
    source, _ = _source("present_placed_item_sprite")
    placement = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_tile_placement")
    placement.update(fn="configure_wall_placement", params={"wallId": 1, "placeStyle": 0})
    report = validate_runtime_program(source)
    assert not report["ok"] and any(row["code"] == "placed_body_placement_reference" for row in report["errors"])


@pytest.mark.parametrize("cooldown", [0, 60, 3600])
def test_home_recall_keeps_shared_cooldown_and_only_declared_inactive_blink_fields(cooldown):
    source, call = _source("recall_home_on_use")
    call["params"] = {"cooldownTicks": cooldown}
    wire = compile_runtime_program(source)
    assert {key: wire["gameplay"][key] for key in ("mobilityMode", "mobilityRangeTiles", "mobilityCooldownTicks", "mobilitySafeTileOnly")} == {
        "mobilityMode": "recall_home", "mobilityRangeTiles": 0,
        "mobilityCooldownTicks": cooldown, "mobilitySafeTileOnly": False,
    }
    assert validate_runtime_wire(wire)["ok"]
    for key in ("mode", "rangeTiles", "safeTileOnly"):
        hostile = deepcopy(source)
        next(row for row in hostile["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"][key] = 1
        assert not validate_runtime_program(hostile)["ok"]


SET_FIELDS = {
    "genericCritChancePercentagePoints": ("setBonusGenericCrit", 3, 3),
    "moveSpeedBonusPercent": ("setBonusMovementSpeed", 25, 0.25),
    "lifeRegenHpPerSecond": ("setBonusLifeRegen", -0.5, -1),
    "manaRegenBonusPoints": ("setBonusManaRegen", 2, 2),
    "minionSlotsBonus": ("setBonusMinionSlots", 1, 1),
    "sentrySlotsBonus": ("setBonusSentrySlots", 2, 2),
    "manaCostReductionPercentagePoints": ("setBonusManaCostReduction", 5, 0.05),
    "ammoSaveChancePercent": ("setBonusAmmoSaveChance", 75, 0.75),
    "aggroPoints": ("setBonusAggro", -2, -2),
    "damageReductionPercentagePoints": ("setBonusEndurance", 10, 0.10),
    "genericArmorPenetrationPoints": ("setBonusArmorPenetration", 4, 4),
}


def test_all_eleven_set_bonuses_keep_their_previous_fields_units_and_receipts():
    source, call = _source("configure_armor")
    call["params"]["setBonuses"] = {name: row[1] for name, row in SET_FIELDS.items()}
    assert set(CAPABILITY_REGISTRY["configure_armor"].params["setBonuses"].properties) == set(SET_FIELDS)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for name, (field, _, expected) in SET_FIELDS.items():
        assert wire["armor"][field] == expected
        receipt = next(row for row in rows if row.get("fn") == "configure_armor" and row["finalPath"] == "armor." + field)
        assert receipt["authoredPath"].endswith(".params.setBonuses." + name)
    assert validate_runtime_wire(wire)["ok"]
    # Source-free old provenance remains inspectable without accepting an old
    # Author document or rewriting any persisted wire field.
    for row in rows:
        if row.get("fn") == "configure_armor" and ".params.setBonuses." in row["authoredPath"]:
            stem, name = row["authoredPath"].split(".params.setBonuses.")
            row["authoredPath"] = stem + ".params.setBonus" + name[0].upper() + name[1:]
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]


@pytest.mark.parametrize("slot,key,bonus,valid", [
    ("head", "set", 1, True), ("body", "set", 1, False),
    ("legs", "set", -1, False), ("head", "", -1, False),
    ("body", "", 0, True),
])
def test_grouped_set_bonuses_keep_head_and_set_key_requirements(slot, key, bonus, valid):
    source, call = _source("configure_armor")
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
    source, call = _source("require_use_condition")
    call["params"] = {"condition": condition}
    wire = compile_runtime_program(source)
    assert {key: value for key, value in wire["gameplay"].items() if key.startswith("useCondition")} == expected
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("condition", [{}, {"lifeAtLeast": 1, "manaAtLeast": 1}, {"lifeAtLeast": True}, {"manaAtLeast": -1}, "life_above", ["grounded", "not_wet"]])
def test_condition_never_infers_threshold_or_combines_two_conditions(condition):
    source, call = _source("require_use_condition")
    call["params"] = {"condition": condition}
    assert not validate_runtime_program(source)["ok"]


def test_armor_repair_preserves_the_other_valid_nested_set_bonus():
    source, call = _source("configure_armor")
    call["params"]["setBonuses"] = {"lifeRegenHpPerSecond": 0.25, "minionSlotsBonus": 2}
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.setBonuses.lifeRegenHpPerSecond"]}]
    fixed = deepcopy(call)
    fixed["params"]["setBonuses"] = {"lifeRegenHpPerSecond": 0.5, "minionSlotsBonus": 20}
    patch, audit = filter_repair_patch_scope(source, {"note": "repair one nested leaf", "callsUpsert": [fixed]}, scope)
    repaired = apply_repair_patch(source, patch)
    actual = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])
    assert actual["params"]["setBonuses"] == {"lifeRegenHpPerSecond": 0.5, "minionSlotsBonus": 2}
    assert audit["ignoredChanges"] and validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("params,path", [
    ({"condition": {"lifeAtLeast": True}}, "params.condition.lifeAtLeast"),
    ({"condition": {}}, "params.condition"),
    ({}, "params.condition"),
    ({"condition": "invalid"}, "params.condition"),
])
def test_condition_repair_requires_an_explicit_complete_variant(params, path):
    source, call = _source("require_use_condition")
    call["params"] = params
    scope = build_runtime_repair_scope(source, validate_runtime_program(source)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [path]}]
    fixed = deepcopy(call)
    fixed["params"] = {"condition": {"lifeAtLeast": 50}}
    patch, audit = filter_repair_patch_scope(source, {"note": "explicit threshold", "callsUpsert": [fixed]}, scope)
    repaired = apply_repair_patch(source, patch)
    assert audit["ok"] and validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    incomplete = deepcopy(call)
    incomplete["params"] = {"condition": {}}
    patch, _ = filter_repair_patch_scope(source, {"note": "no threshold selected", "callsUpsert": [incomplete]}, scope)
    assert not validate_runtime_program(apply_repair_patch(source, patch))["ok"]


def test_unrelated_repair_cannot_change_a_valid_condition_or_threshold():
    source, call = _source("require_use_condition")
    call["params"] = {"condition": {"lifeAtLeast": 50}}
    stats = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    stats["params"]["damage"] = True
    scope = build_runtime_repair_scope(source, validate_runtime_program(source)["errors"])
    altered = deepcopy(call)
    altered["params"] = {"condition": {"manaAtLeast": 1}}
    fixed_stats = deepcopy(stats)
    fixed_stats["params"]["damage"] = 10
    patch, audit = filter_repair_patch_scope(source, {"note": "fix damage", "callsUpsert": [fixed_stats, altered]}, scope)
    repaired = apply_repair_patch(source, patch)
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"] == call["params"]
    assert audit["ignoredChanges"] and validate_runtime_wire(compile_runtime_program(repaired))["ok"]
