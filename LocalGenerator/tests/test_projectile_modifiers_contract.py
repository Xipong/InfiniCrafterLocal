
from prompt_packet_helpers import request_dossier
"""A13/B15.1 explicit phase modifiers, ownership, provenance and frozen Repair."""
from copy import deepcopy

import pytest
from repair_test_helpers import (
    DELETE, projected_params, edit_fields, frozen_call_repair, frozen_gameplay_repair,
)

from infini_local.core import llm_config
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.capability_registry import PROJECTILE_MODIFIER_COMPONENTS
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from test_low_level_three_stage_pipeline import wire_transport

PARAMS = {
    "set_projectile_turn_modifier": dict(turnRadiansPerSecond=(.04) * 60, startDelaySeconds=(0) / 60, durationSeconds=(90) / 60),
    "set_projectile_speed_modifier": dict(speedMultiplierPerUpdate=1.01, maxSpeedBlocksPerSecond=75, startDelaySeconds=(0) / 60, durationSeconds=(40) / 60),
    "set_projectile_homing_modifier": dict(rangeTiles=40, maxTurnRadiansPerSecond=(.1) * 60, requireLineOfSight=True, startDelaySeconds=(40) / 60, durationSeconds=(50) / 60),
    "attract_npcs_while_active": dict(rangeTiles=10, accelerationBlocksPerSecondSquared=(2) * 3600 / 16, falloff="linear", maxTargets=8, startDelaySeconds=(5) / 60, durationSeconds=(60) / 60),
    "set_projectile_visual_scale_curve": dict(startScale=.5, endScale=4, startDelaySeconds=(5) / 60, durationSeconds=(60) / 60, curve="exponential"),
    "orient_whip_to_owner_gravity": {},
}

def call(doc, fn):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)

def source(fn):
    doc = build_capability_witness(fn)
    if PARAMS[fn]:
        call(doc, fn)["params"] = deepcopy(PARAMS[fn])
    else:
        assert "params" not in call(doc, fn)
    return doc

def entity(wire, fn):
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    return next(row for row in wire["runtimeProgram"]["entities"] if member in row)


@pytest.mark.parametrize("fn,format_mode,repair", [
    ("set_projectile_visual_scale_curve", "json_object", False),
    ("set_projectile_homing_modifier", "json_schema", True),
])
def test_actual_visual_and_repair_packets_preserve_exact_modifier_owner(wire_transport, monkeypatch, fn, format_mode, repair):
    from infini_local.pipelines import visual_generation_pipeline as visual

    data = compile_runtime_program(source(fn))
    frozen = deepcopy(data)
    responses, sent = wire_transport
    responses.append({})
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    kwargs = {"repair_errors": [{"path": "$.item.renderSizePx", "message": "required"}], "previous": {"item": {}}, "repair_scope": {}} if repair else {}
    visual._request_visual_kit(data, {}, {}, **kwargs)
    packet = request_dossier(sent[-1])
    rows = packet["runtimeEntitiesReadOnly" if repair else "runtimeEntities"]
    members = (*PROJECTILE_MODIFIER_COMPONENTS.values(), "whipUsesOwnerGravity")
    for row, accepted in zip(rows, data["runtimeProgram"]["entities"]):
        for member in members:
            assert (member in row) == (member in accepted)
            if member in accepted:
                assert row[member] == accepted[member]
    assert data == frozen

@pytest.mark.parametrize("fn", PARAMS)
def test_complete_vertical_witness_exact_identity_and_source_receipts(fn):
    doc = source(fn); before = deepcopy(doc)
    compiled = compile_runtime_program(doc)
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    assert entity(compiled, fn)[member] == (projected_params(fn, PARAMS[fn]) if fn in PROJECTILE_MODIFIER_COMPONENTS else True)
    assert doc == before and validate_runtime_wire(compiled)["ok"]
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    owned = [row for row in rows if row.get("fn") == fn]
    assert len(owned) == (len(PARAMS[fn]) or 1)
    assert audit_compiler_receipts(rows, final_document=compiled)["ok"]

# Distinct scalar admissions at both Author and unreceipted persisted-wire boundaries.
# Registry numeric tests own the repeated per-field type/bounds matrix.
@pytest.mark.parametrize("fn,leaf,kind,value", [
    ("set_projectile_turn_modifier", "turnRadiansPerSecond", "missing", None),
    ("set_projectile_turn_modifier", "turnRadiansPerSecond", "null", None),
    ("set_projectile_speed_modifier", "maxSpeedBlocksPerSecond", "boolean", True),
    ("set_projectile_speed_modifier", "speedMultiplierPerUpdate", "numeric-text", "1"),
    ("set_projectile_homing_modifier", "rangeTiles", "negative", -22000),
    ("set_projectile_homing_modifier", "requireLineOfSight", "wrong-type", 0),
    ("attract_npcs_while_active", "accelerationBlocksPerSecondSquared", "infinity", float("inf")),
    ("attract_npcs_while_active", "falloff", "unknown", "unknown"),
    ("set_projectile_visual_scale_curve", "endScale", "nan", float("nan")),
    ("set_projectile_visual_scale_curve", "curve", "missing", None),
    ("set_projectile_visual_scale_curve", "durationSeconds", "negative", 0),
])
def test_modifier_leaf_requires_exact_present_author_and_wire_value(fn, leaf, kind, value):
    doc = source(fn)
    compiled = compile_runtime_program(doc)
    authored = call(doc, fn)["params"]
    persisted = entity(compiled, fn)[PROJECTILE_MODIFIER_COMPONENTS[fn]]
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    wire_leaf = CAPABILITY_REGISTRY[fn].params[leaf].wire_name or leaf
    edit_fields(authored, {leaf: DELETE if kind == "missing" else value})
    edit_fields(persisted, {wire_leaf: DELETE if kind == "missing" else value})
    report = validate_runtime_program(doc)
    assert not report["ok"] and any(row["path"].endswith("." + leaf) for row in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("fn,mutation", [
    ("set_projectile_turn_modifier", "null"),
    ("set_projectile_speed_modifier", "unknown"),
    ("set_projectile_homing_modifier", "duplicate"),
    ("attract_npcs_while_active", "receipt_deleted"),
    ("set_projectile_visual_scale_curve", "other_entity"),
    ("orient_whip_to_owner_gravity", "item_target"),
    ("orient_whip_to_owner_gravity", "unknown"),
])
def test_modifier_cannot_be_injected_or_reassigned_without_authority(fn, mutation):
    doc = source(fn); compiled = compile_runtime_program(doc)
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    if mutation == "duplicate":
        second = deepcopy(call(doc, fn)); second["id"] = "duplicate_modifier"
        doc["runtimeProgram"]["calls"].append(second)
        assert not validate_runtime_program(doc)["ok"]
        return
    if mutation == "null": entity(compiled, fn)[member] = None
    elif mutation == "unknown":
        if fn in PROJECTILE_MODIFIER_COMPONENTS: entity(compiled, fn)[member]["familyInference"] = "spiral"
        else: entity(compiled, fn)[member] = False
    elif mutation == "receipt_deleted":
        compiled["runtimeContract"]["finalWireReceipts"] = [r for r in compiled["runtimeContract"]["finalWireReceipts"] if r.get("fn") != fn]
    elif mutation == "other_entity":
        for row in compiled["runtimeContract"]["finalWireReceipts"]:
            if row.get("fn") == fn: row["finalPath"] = row["finalPath"].replace("entities[1]", "entities[0]")
    else: compiled["runtimeProgram"]["entities"][0][member] = entity(compiled, fn).pop(member)
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("fn", PROJECTILE_MODIFIER_COMPONENTS)
def test_frozen_repair_changes_only_invalid_phase_leaf(fn):
    doc = source(fn)
    call(doc, fn)["params"]['durationSeconds'] = (0) / 60
    expected = deepcopy(doc)
    call(expected, fn)["params"]['durationSeconds'] = (100) / 60
    replacement = deepcopy(call(doc, fn))
    replacement["params"].update(durationSeconds=(100) / 60, startDelaySeconds=(21000) / 60)
    repaired, final = frozen_call_repair(doc, [replacement],
        [{"id": replacement["id"], "paths": ['params.durationSeconds']}], expected,
        note="fix invalid duration only")
    assert entity(final, fn)[PROJECTILE_MODIFIER_COMPONENTS[fn]]["durationTicks"] == 100

def test_simultaneous_and_delayed_modifiers_are_independent_of_the_movement_slot():
    doc = source("set_projectile_turn_modifier")
    target = call(doc, "set_projectile_turn_modifier")["target"]
    for index, fn in enumerate(list(PROJECTILE_MODIFIER_COMPONENTS)[1:]):
        doc["runtimeProgram"]["calls"].append(dict(id=f"modifier_{index}", fn=fn, target=target, params=deepcopy(PARAMS[fn])))
    doc["runtimeProgram"]["calls"].append(dict(id="gameplay_curve", fn="set_projectile_hitbox_curve", target=target,
        params=dict(startScale=1, endScale=2, startDelaySeconds=0, durationSeconds=80 / 60, curve="linear", mirrorToSprite=False)))
    compiled = compile_runtime_program(doc)
    final = entity(compiled, "set_projectile_turn_modifier")
    assert final["movement"]["code"] == 0
    for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items(): assert final[member] == projected_params(fn, PARAMS[fn])
    assert final["hitboxCurve"]["endScale"] == 2
    call(doc, "set_projectile_hitbox_curve")["params"]["mirrorToSprite"] = True
    errors = validate_runtime_program(doc)["errors"]
    assert any(row["code"] == "exclusive_component_conflict" and row["path"].endswith("mirrorToSprite") for row in errors)
    scope = build_runtime_repair_scope(doc, errors)
    fix = deepcopy(call(doc, "set_projectile_hitbox_curve")); fix["params"].update(mirrorToSprite=False, endScale=7)
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [fix], "note": "retain the independent visual curve"}, scope)
    repaired = apply_repair_patch(doc, patch)
    assert call(repaired, "set_projectile_hitbox_curve")["params"]["endScale"] == 2
    compile_runtime_program(repaired)

def test_npc_attraction_alone_is_meaningful_on_a_field_without_drag():
    doc = source("attract_npcs_while_active")
    target = call(doc, "attract_npcs_while_active")["target"]
    next(row for row in doc["runtimeProgram"]["entities"] if row["id"] == target)["kind"] = "field"
    doc["runtimeProgram"]["calls"] = [row for row in doc["runtimeProgram"]["calls"] if row["fn"] not in {"move_straight", "set_projectile_damage"}]
    compiled = compile_runtime_program(doc)
    final = entity(compiled, "attract_npcs_while_active")
    assert "movement" not in final and "damage" not in final
    assert final["npcAttraction"] == projected_params("attract_npcs_while_active", PARAMS["attract_npcs_while_active"])

def test_whip_marker_requires_executed_whip_geometry():
    doc = source("orient_whip_to_owner_gravity")
    motion = call(doc, "move_whip_lash")
    motion.update(fn="move_straight", params={})
    assert not validate_runtime_program(doc)["ok"]
    compiled = compile_runtime_program(source("orient_whip_to_owner_gravity"))
    entity(compiled, "orient_whip_to_owner_gravity")["movement"].update(name="move_straight", code=0, params={})
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("driver", ["channel_beam", "move_whip_lash", "move_expanding_wave"])
def test_visual_curve_cannot_be_ignored_by_line_geometry_or_overwritten_by_another_scale_owner(driver):
    doc = build_capability_witness(driver)
    target = call(doc, driver)["target"]
    doc["runtimeProgram"]["calls"].append(dict(id="visual_curve", fn="set_projectile_visual_scale_curve", target=target,
        params=deepcopy(PARAMS["set_projectile_visual_scale_curve"])))
    assert any(row["code"] == "exclusive_component_conflict" for row in validate_runtime_program(doc)["errors"])
    compiled = compile_runtime_program(build_capability_witness(driver))
    next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == target)["visualScaleCurve"] = projected_params("set_projectile_visual_scale_curve", PARAMS["set_projectile_visual_scale_curve"])
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]


@pytest.mark.parametrize("fn,leaf,collapsed,neutral,positive", [
    ("set_projectile_turn_modifier", "turnRadiansPerSecond", 1e-46, 0, 2.4),
    ("set_projectile_speed_modifier", "speedMultiplierPerUpdate", 1.0000000000000002, 1, 1.01),
])
def test_non_neutral_modifier_cannot_collapse_in_the_real_consumer_and_repair_is_leaf_local(fn, leaf, collapsed, neutral, positive):
    doc = source(fn); call(doc, fn)["params"][leaf] = collapsed
    errors = validate_runtime_program(doc)["errors"]
    assert any(row["path"].endswith(".params." + leaf) for row in errors)
    scope = build_runtime_repair_scope(doc, errors)
    correction = deepcopy(call(doc, fn)); correction["params"].update({leaf: positive, 'durationSeconds': (20000) / 60})
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [correction], "note": "retain nonneutral consumer value"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(doc, patch)
    assert call(repaired, fn)["params"]['durationSeconds'] == PARAMS[fn]["durationSeconds"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    for accepted in (neutral, positive):
        control = source(fn); call(control, fn)["params"][leaf] = accepted
        assert validate_runtime_wire(compile_runtime_program(control))["ok"]
    del call(control, fn)["params"][leaf]
    assert not validate_runtime_program(control)["ok"]  # neutral metadata is not omission permission



@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_modifier_phase_repair_freezes_child_launch_and_parent_combat(monkeypatch, format_mode):
    doc = build_capability_witness("spawn_entity_on_event")
    producer = call(doc, "spawn_entity_on_event")
    producer["params"].update(damageBasis="live_parent", knockbackBasis="authored_child")
    child = producer["params"]["entity"]
    spawn = next(row for row in doc["runtimeProgram"]["calls"]
                 if row["fn"] == "configure_spawn" and row["target"] == child)
    spawn["params"]["velocity"] = {"cone": {
        'minSpeedBlocksPerSecond': (4) * 60 / 16, 'maxSpeedBlocksPerSecond': (7) * 60 / 16, "halfAngleRadians": .2}}
    modifier = dict(id="child_turn", fn="set_projectile_turn_modifier", target=child,
                    params=deepcopy(PARAMS["set_projectile_turn_modifier"]))
    doc["runtimeProgram"]["calls"].append(modifier)
    expected = deepcopy(doc)
    expected_wire = compile_runtime_program(expected)
    modifier["params"]['durationSeconds'] = (0) / 60
    correction = deepcopy(modifier)
    correction["params"].update(durationSeconds=(90) / 60, turnRadiansPerSecond=(.2) * 60)
    hostile_producer = deepcopy(producer)
    hostile_producer["params"].update(entity="item", damageBasis="authored_child")
    hostile_spawn = deepcopy(spawn)
    hostile_spawn["params"]["velocity"] = {'constantSpeedBlocksPerSecond': (12) * 60 / 16}
    _, _, wire = frozen_gameplay_repair(monkeypatch, doc,
        {"note": "repair child phase only", "realizationReplacement": doc["realization"],
         "callsUpsert": [correction, hostile_producer, hostile_spawn]}, format_mode,
        {"calls": [{"id": "child_turn", "paths": ['params.durationSeconds']}]}, expected,
        out_of_scope_response=True)
    assert wire == expected_wire
