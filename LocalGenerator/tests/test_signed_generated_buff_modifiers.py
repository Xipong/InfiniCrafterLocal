"""Negative generated-player modifiers keep their existing unit projections."""
import json
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
from infini_local.storage.world_storage import sanitize_recipe_for_delivery

FN = "generated_buff_on_use"


def document(activation=FN):
    doc = build_capability_witness(activation)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    call["params"].update(lightStrength=0, miningSpeedMultiplier=1, oreSenseEnabled=False,
        moveSpeedBonus=0, jumpSpeedBonus=0, manaRegen=0, lifeRegen=0)
    return doc, call


@pytest.mark.parametrize("leaf,value,wire_leaf,expected", [
    ("combat.defensePoints", -100, "combat.defensePoints", -100),
    ("combat.attackSpeedBonus", -80, "combat.attackSpeedPercent", -80),
    ("combat.critChance", -100, "combat.critChancePoints", -100),
    ("combat.damageBonus", -90, "combat.damagePercent", -90),
    ("moveSpeedBonus", -80, "movementSpeed", -0.8),
    ("jumpSpeedBonus", -30, "jumpBoost", -8),
    ("manaRegen", -100, "manaRegen", -100),
    ("lifeRegen", -50, "lifeRegen", -100),
    ("miningSpeedMultiplier", 0.25, "miningSpeedMultiplier", 0.25),
])
@pytest.mark.parametrize("activation", [FN, "refresh_held_effect", "generated_buff_on_event"])
def test_each_penalty_alone_is_an_effect_in_author_and_saved_wire(leaf, value, wire_leaf, expected, activation):
    doc, call = document(activation)
    if leaf.startswith("combat."):
        call["params"]["combat"] = dict(defensePoints=0, attackSpeedBonus=0,
            critChance=0, damageBonus=0, damageClass="generic")
        call["params"]["combat"][leaf.split(".")[1]] = value
    else:
        call["params"][leaf] = value
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report
    wire = compile_runtime_program(doc)
    assert doc == before
    buff = wire["gameplay"].get("generatedBuff") or wire["runtimeProgram"]["effectGroups"][0]["generatedBuff"]
    for part in wire_leaf.split("."):
        buff = buff[part]
    assert buff == expected
    for source in (doc, None):
        audit = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)
        assert audit["ok"], audit
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    wire = json.loads(json.dumps(sanitize_recipe_for_delivery(wire)))
    assert "runtimeContract" not in wire
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)


@pytest.mark.parametrize("leaf,bad,good", [
    ("combat.defensePoints", -101, -100), ("combat.attackSpeedBonus", -81, -80),
    ("combat.critChance", -101, -100), ("combat.damageBonus", -91, -90),
    ("moveSpeedBonus", -81, -80), ("jumpSpeedBonus", -31, -30),
    ("manaRegen", -101, -100), ("lifeRegen", -50.5, -49.5),
])
def test_signed_leaf_repair_freezes_valid_combat_and_utility_neighbors(leaf, bad, good):
    doc, call = document()
    call["params"]["lightStrength"] = 0.25
    call["params"]["combat"] = dict(defensePoints=0, attackSpeedBonus=0,
        critChance=0, damageBonus=0, damageClass="magic")
    parent = call["params"]["combat"] if leaf.startswith("combat.") else call["params"]
    parent[leaf.split(".")[-1]] = bad
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    paths = next(r["paths"] for r in scope["fieldPermissions"]["calls"] if r["id"] == call["id"])
    assert paths == ["params." + leaf]
    candidate = deepcopy(call)
    parent = candidate["params"]["combat"] if leaf.startswith("combat.") else candidate["params"]
    parent[leaf.split(".")[-1]] = good
    candidate["params"]["lightStrength"] = 1
    candidate["params"]["combat"]["damageClass"] = "melee"
    filtered, audit = filter_repair_patch_scope(doc, {"note": "signed correction", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, filtered)
    actual = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    expected = deepcopy(call)
    parent = expected["params"]["combat"] if leaf.startswith("combat.") else expected["params"]
    parent[leaf.split(".")[-1]] = good
    assert actual == expected
    assert validate_runtime_wire(compile_runtime_program(fixed))["ok"]


def test_neutral_combat_repair_opens_stat_leaves_not_valid_class_selector():
    doc, call = document()
    call["params"]["combat"] = dict(defensePoints=0, attackSpeedBonus=0,
        critChance=0, damageBonus=0, damageClass="magic")
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    paths = next(r["paths"] for r in scope["fieldPermissions"]["calls"] if r["id"] == call["id"])
    assert "params.combat.defensePoints" in paths
    assert "params.combat" not in paths and "params.combat.damageClass" not in paths
    candidate = deepcopy(call)
    candidate["params"]["combat"].update(defensePoints=-10, damageClass="melee")
    filtered, audit = filter_repair_patch_scope(doc, {"note": "one penalty", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, filtered)
    actual = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert actual["params"]["combat"] == {**call["params"]["combat"], "defensePoints": -10}
    assert validate_runtime_wire(compile_runtime_program(fixed))["ok"]


def test_neutral_utility_repair_keeps_accepted_combat_absence_frozen():
    doc, call = document()
    assert "combat" not in call["params"]
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    paths = next(r["paths"] for r in scope["fieldPermissions"]["calls"] if r["id"] == call["id"])
    assert not any(path.startswith("params.combat") for path in paths)
    candidate = deepcopy(call)
    candidate["params"].update(moveSpeedBonus=-10, combat=dict(defensePoints=20,
        attackSpeedBonus=10, critChance=10, damageBonus=10, damageClass="melee"))
    filtered, audit = filter_repair_patch_scope(doc, {"note": "utility penalty", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, filtered)
    actual = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert "combat" not in actual["params"]
    assert actual["params"]["moveSpeedBonus"] == -10
    assert validate_runtime_wire(compile_runtime_program(fixed))["ok"]


def test_existing_positive_upper_bounds_and_exact_steps_are_unchanged():
    cap = CAPABILITY_REGISTRY[FN]
    assert {name: spec.maximum for name, spec in cap.params["combat"].properties.items() if spec.kind != "string"} == {
        "defensePoints": 100, "attackSpeedBonus": 100, "critChance": 100, "damageBonus": 200}
    assert cap.params["moveSpeedBonus"].maximum == 200
    assert cap.params["jumpSpeedBonus"].maximum == 30
    assert cap.params["manaRegen"].maximum == 120
    assert cap.params["lifeRegen"].maximum == 60
    assert cap.params["lifeRegen"].multiple_of == 0.5
