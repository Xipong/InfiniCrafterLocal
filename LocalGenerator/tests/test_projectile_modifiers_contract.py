"""A13/B15.1 explicit phase modifiers, ownership, provenance and frozen Repair."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.capability_registry import PROJECTILE_MODIFIER_COMPONENTS
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.capability_library_audit import capability_library_audit
from infini_local.qa.primitive_loss_audit import runtime_component_surface_audit
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from test_low_level_three_stage_pipeline import wire_transport

PARAMS = {
    "set_projectile_turn_modifier": dict(turnRadiansPerUpdate=.04, startDelayTicks=0, durationTicks=90),
    "set_projectile_speed_modifier": dict(speedMultiplierPerUpdate=1.01, maxSpeed=20, startDelayTicks=0, durationTicks=40),
    "set_projectile_homing_modifier": dict(rangeTiles=40, maxTurnRadiansPerUpdate=.1, requireLineOfSight=True, startDelayTicks=40, durationTicks=50),
    "attract_npcs_while_active": dict(rangeTiles=10, strengthPerUpdate=2, falloff="linear", maxTargets=8, startDelayTicks=5, durationTicks=60),
    "set_projectile_visual_scale_curve": dict(startScale=.5, endScale=4, startDelayTicks=5, durationTicks=60, curve="exponential"),
    "orient_whip_to_owner_gravity": {},
}

def call(doc, fn):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == fn)

def source(fn):
    doc = build_capability_witness(fn)
    call(doc, fn)["params"] = deepcopy(PARAMS[fn])
    return doc

def entity(wire, fn):
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    return next(row for row in wire["runtimeProgram"]["entities"] if member in row)


@pytest.mark.parametrize("fn", PARAMS)
@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("repair", [False, True])
def test_actual_visual_and_repair_packets_preserve_exact_modifier_owner(wire_transport, monkeypatch, fn, format_mode, repair):
    from infini_local.pipelines import llm_transport, visual_generation_pipeline as visual

    data = compile_runtime_program(source(fn))
    frozen = deepcopy(data)
    responses, sent = wire_transport
    responses.append({})
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    kwargs = {"repair_errors": [{"path": "$.item.renderSizePx", "message": "required"}], "previous": {"item": {}}, "repair_scope": {}} if repair else {}
    visual._request_visual_kit(data, {}, {}, {}, {}, **kwargs)
    packet = json.loads(sent[-1]["messages"][1]["content"])
    rows = packet["runtimeEntitiesReadOnly" if repair else "runtimeEntities"]
    members = (*PROJECTILE_MODIFIER_COMPONENTS.values(), "whipUsesOwnerGravity")
    for row, accepted in zip(rows, data["runtimeProgram"]["entities"]):
        for member in members:
            assert (member in row) == (member in accepted)
            if member in accepted:
                assert row[member] == accepted[member]
                assert row["modifierMeaningReadOnly"][member] == CAPABILITY_REGISTRY[fn].summary
    formula = packet["spritePresentationReadOnly"]["formulas"]["body"]
    assert "visualScaleCurve is present" in formula
    assert "P=D*E*curveScale(active age) from that explicit visual owner" in formula
    assert "otherwise q_selected * clamp(P, .1, 8)" in formula
    assert packet["spritePresentationReadOnly"]["formulas"]["liveBodyCopy"].startswith("q_selected * clamp(P, .1, 8)")
    assert data == frozen

@pytest.mark.parametrize("fn", PARAMS)
def test_complete_vertical_witness_exact_identity_and_source_receipts(fn):
    doc = source(fn); before = deepcopy(doc)
    compiled = compile_runtime_program(doc)
    member = PROJECTILE_MODIFIER_COMPONENTS.get(fn, "whipUsesOwnerGravity")
    assert entity(compiled, fn)[member] == (PARAMS[fn] if fn in PROJECTILE_MODIFIER_COMPONENTS else True)
    assert doc == before and validate_runtime_wire(compiled)["ok"]
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    owned = [row for row in rows if row.get("fn") == fn]
    assert len(owned) == (len(PARAMS[fn]) or 1)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=compiled)["ok"]
    assert audit_compiler_receipts(rows, final_document=compiled)["ok"]

@pytest.mark.parametrize("fn,leaf", [(fn, key) for fn, values in PARAMS.items() for key in values])
def test_all_new_choices_are_required_in_author_and_persisted_component(fn, leaf):
    doc = source(fn); compiled = compile_runtime_program(doc)
    del call(doc, fn)["params"][leaf]
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(doc)
    del entity(compiled, fn)[PROJECTILE_MODIFIER_COMPONENTS[fn]][leaf]
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("fn,leaf,value", [
    (fn, leaf, value)
    for fn, values in PARAMS.items() for leaf, original in values.items()
    for value in ([None, True, "1", -22000, float("inf"), float("nan")] if type(original) in (int, float)
                  else [None, 0, "unknown"] if isinstance(original, bool) else [None, 1, "unknown"])
])
def test_invalid_present_choice_is_red_at_author_and_wire_boundary(fn, leaf, value):
    doc = source(fn); compiled = compile_runtime_program(doc)
    call(doc, fn)["params"][leaf] = value
    assert not validate_runtime_program(doc)["ok"]
    entity(compiled, fn)[PROJECTILE_MODIFIER_COMPONENTS[fn]][leaf] = value
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

@pytest.mark.parametrize("fn", PARAMS)
@pytest.mark.parametrize("mutation", ["null", "unknown", "duplicate", "receipt_deleted", "other_entity", "item_target"])
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
    doc = source(fn); call(doc, fn)["params"]["durationTicks"] = 0
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    replacement = deepcopy(call(doc, fn)); replacement["params"]["durationTicks"] = 100
    replacement["params"]["startDelayTicks"] = 21000
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [replacement], "note": "fix invalid duration only"}, scope)
    assert audit["ok"]
    repaired = apply_repair_patch(doc, patch)
    call(before, fn)["params"]["durationTicks"] = 100
    assert repaired == before
    compile_runtime_program(repaired)

def test_simultaneous_and_delayed_modifiers_are_independent_of_the_movement_slot():
    doc = source("set_projectile_turn_modifier")
    target = call(doc, "set_projectile_turn_modifier")["target"]
    for index, fn in enumerate(list(PROJECTILE_MODIFIER_COMPONENTS)[1:]):
        doc["runtimeProgram"]["calls"].append(dict(id=f"modifier_{index}", fn=fn, target=target, params=deepcopy(PARAMS[fn])))
    doc["runtimeProgram"]["calls"].append(dict(id="gameplay_curve", fn="set_projectile_hitbox_curve", target=target,
        params=dict(startScale=1, endScale=2, startDelayTicks=0, durationTicks=80, curve="linear", mirrorToSprite=False)))
    compiled = compile_runtime_program(doc)
    final = entity(compiled, "set_projectile_turn_modifier")
    assert final["movement"]["code"] == 0
    for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items(): assert final[member] == PARAMS[fn]
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
    assert final["npcAttraction"] == PARAMS["attract_npcs_while_active"]

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
    next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == target)["visualScaleCurve"] = deepcopy(PARAMS["set_projectile_visual_scale_curve"])
    compiled.pop("runtimeContract")
    assert not validate_runtime_wire(compiled)["ok"]

def test_numeric_bounds_and_complete_dto_fields_are_machine_audited():
    assert runtime_component_surface_audit()["ok"]
    report = capability_library_audit()
    assert report["ok"], report.get("issues")
    dto_path = Path(__file__).parents[2] / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs"
    dto = dto_path.read_bytes().replace(b"[JsonRequired] public float StrengthPerUpdate", b"public float UnexposedPull { get; set; }\n    [JsonRequired] public float StrengthPerUpdate")
    assert not runtime_component_surface_audit(dto)["ok"]

def test_actual_author_request_exposes_every_explicit_choice():
    _, user, _ = build_initial_author_request({"name": "A"}, {"name": "B"}, {}, {}, "modifier-offline", model_name="test-model")
    import json
    payload = json.loads(user)
    cards = {row["fn"]: row for row in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    for fn, params in PARAMS.items(): assert set(cards[fn]["params"]) == set(params)
