"""Author and stripped delivery reject incomplete/competing independent laws."""
from copy import deepcopy
import pytest

from test_composable_motion_primitives import base_document, add, window, compile_ok
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


@pytest.mark.parametrize("fn,params", [
    ("set_projectile_return_trigger", {"onOwnerRelease": False, "onTileCollision": False, "disableTileCollisionOnReturn": False}),
    ("seek_projectile", {"target": "nearest_npc", "maxSpeedBlocksPerSecond": 30, "velocityLerpPerUpdate": 1, "limitSpeedToDistance": False}),
    ("seek_projectile", {"target": "cursor", "maxSpeedBlocksPerSecond": 30, "minimumSpeedBlocksPerSecond": 60, "velocityLerpPerUpdate": 1, "limitSpeedToDistance": False}),
    ("set_projectile_rotation", {"mode": "velocity", "offsetRadians": 0, "radiansPerSecond": 1}),
    ("set_projectile_lash_geometry", {"clock": "active", "anchor": "owner_center", "reachBlocks": 8, "segments": 12, "sweepStartRadians": -1, "sweepEndRadians": 1, "bendRatio": 0.2, "useOwnerGravity": False, "useOwnerWhipRangeMultiplier": False}),
])
def test_incomplete_selected_modes_are_red(fn, params):
    doc = base_document()
    if fn == "set_projectile_lash_geometry":
        add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, fn, params)
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("target,field,value,wire_field,wire_value", [
    ("nearest_npc", "cursorLeashBlocks", 4, "cursorLeashPx", 64),
    ("owner_center", "cursorLeashBlocks", 4, "cursorLeashPx", 64),
    ("owner_mounted", "cursorLeashBlocks", 4, "cursorLeashPx", 64),
    ("cursor", "searchRangeTiles", 20, "searchRangeTiles", 20),
    ("cursor", "requireLineOfSight", False, "requireLineOfSight", False),
    ("owner_center", "searchRangeTiles", 20, "searchRangeTiles", 20),
    ("owner_mounted", "requireLineOfSight", True, "requireLineOfSight", True),
])
def test_seek_rejects_fields_outside_selected_target_in_author_and_wire(target, field, value, wire_field, wire_value):
    doc = base_document()
    params = {"target": target, "maxSpeedBlocksPerSecond": 30,
              "velocityLerpPerUpdate": 1, "limitSpeedToDistance": False}
    if target == "nearest_npc":
        params.update(searchRangeTiles=20, requireLineOfSight=False)
    call = add(doc, "seek_projectile", params)
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    call["params"][field] = value
    entity["seek"][0][wire_field] = wire_value
    author_before, wire_before = deepcopy(doc), deepcopy(wire)
    report = validate_runtime_program(doc)
    assert any(e["path"].endswith(".params." + field) for e in report["errors"]), report
    report = validate_runtime_wire(wire)
    assert any(e["path"].endswith(".seek[0]." + wire_field) for e in report["errors"]), report
    assert doc == author_before and wire == wire_before


@pytest.mark.parametrize("fn,params", [
    ("set_projectile_return_trigger", {"onOwnerRelease": True, "onTileCollision": False, "disableTileCollisionOnReturn": True}),
    ("set_projectile_owner_control", {"requireHeldItem": True, "requireChannel": True, "requireItemAnimation": False, "claimHeldProjectile": False, "animation": "none", "lifetime": "authored"}),
])
def test_release_and_require_channel_active_inputs_need_explicit_channel(fn, params):
    doc = base_document()
    add(doc, fn, params)
    assert not validate_runtime_program(doc)["ok"]
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    compile_ok(doc)


@pytest.mark.parametrize("gate,producer,leaf", [
    ({"phase": "charging"}, "accumulate_projectile_charge", "phase"),
    ({"phase": "released"}, "accumulate_projectile_charge", "phase"),
    (window("always", "since_release"), "accumulate_projectile_charge", "clock"),
    ({"phase": "returning"}, "set_projectile_return_trigger", "phase"),
    (window("outbound", "since_return"), "set_projectile_return_trigger", "clock"),
])
def test_window_requires_actual_latch_producer_in_author_and_stripped_wire(gate, producer, leaf):
    doc = base_document()
    call = add(doc, "set_projectile_opacity", {"alpha": 10, "window": gate})
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    path = f"$.runtimeProgram.calls[{doc['runtimeProgram']['calls'].index(call)}].params.window.{leaf}"
    assert any(e["path"] == path and e["code"] == "missing_capability_dependency"
               and e["allowed"] == [producer] for e in report["errors"]), report
    assert doc == before
    if producer == "accumulate_projectile_charge":
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
        add(doc, producer, {"durationSeconds": 1})
        member = "charge"
    else:
        add(doc, producer, {"afterSeconds": 1})
        member = "returnTrigger"
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    del entity[member]
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert any(e["path"].endswith(".opacity.window." + leaf)
               and e["code"] == "missing_capability_dependency" for e in report["errors"]), report
    assert wire == before


@pytest.mark.parametrize("name,code,params,member,value", [
    ("move_slow_homing", 1, {"rangeTiles": 10, "homingStrength": 0.1}, "seek",
     [{"target": "cursor", "maxSpeed": 8, "velocityLerpPerUpdate": 1, "limitSpeedToDistance": False}]),
    ("move_gravity_arc", 2, {"gravityPerTick": 0.1}, "verticalAcceleration", {"accelerationYPerUpdate": 0.001}),
    ("move_drift", 3, {"velocityRetention": 0.8}, "velocityRetention", {"multiplierPerUpdate": 0.5}),
    ("move_orbit", 4, {"rangeTiles": 1, "orbitRadiansPerUpdate": 0.1}, "seek",
     [{"target": "cursor", "maxSpeed": 8, "velocityLerpPerUpdate": 1, "limitSpeedToDistance": False}]),
    ("move_sine_homing", 7, {"rangeTiles": 10, "homingStrength": 0.1, "waveAmplitude": 0.1}, "oscillation",
     {"law": "angular_sine", "frequencyRadiansPerUpdate": 0.05, "phaseRadians": 0, "amplitude": 0.1}),
    ("move_boomerang", 5, {"returnAfterTicks": 1, "returnSpeed": 1}, "arrival",
     {"target": "owner_center", "radiusPx": 16, "action": "kill"}),
    ("move_boomerang", 5, {"returnAfterTicks": 1, "returnSpeed": 1}, "returnTrigger",
     {"afterTicks": 1, "onOwnerRelease": False, "onTileCollision": False, "disableTileCollisionOnReturn": False}),
    ("move_proximity_missile", 13, {"rangeTiles": 10, "homingStrength": 0.1, "proximityRadiusPx": 4}, "proximity",
     {"searchRangeTiles": 10, "triggerRadiusPx": 4, "requireLineOfSight": False, "action": "kill"}),
    ("move_phase", 8, {"phaseStrength": 0.1}, "opacity", {"alpha": 20}),
    ("move_returning_glaive", 14, {"returnAfterTicks": 1, "returnSpeed": 1}, "rotation",
     {"mode": "velocity", "offsetRadians": 0, "radiansPerUpdate": 0}),
    ("move_expanding_wave", 15, {"scalePerTick": 0.1, "maxScale": 1}, "visualScaleRate",
     {"deltaPerUpdate": 0.001, "maxScale": 4}),
])
def test_retained_stage_owner_refuses_new_duplicate_without_rewriting_old_wire(name, code, params, member, value):
    wire, entity = compile_ok(base_document())
    wire.pop("runtimeContract")
    entity["movement"] = {"name": name, "code": code, "params": params}
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    entity[member] = value
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert any(e["code"] == "retained_motion_stage_conflict" and ("." + member) in e["path"]
               for e in report["errors"]), report
    assert wire == before


@pytest.mark.parametrize("name,code,params", [
    ("channel_beam", 1, {"rangeTiles": 1, "widthPx": 2, "warmupTicks": 1}),
    ("charge_then_release", 2, {"chargeTicks": 1, "chargeDamageMultiplier": 1, "knockbackMultiplier": 1, "speedMultiplier": 1}),
])
def test_retained_position_controller_refuses_even_nontranslating_new_component(name, code, params):
    wire, entity = compile_ok(base_document())
    wire.pop("runtimeContract")
    entity["controller"] = {"name": name, "code": code, "params": params}
    entity["kind"] = "owner_attached_projectile"
    wire["runtimeProgram"]["itemUse"]["channel"] = True
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    entity["opacity"] = {"alpha": 10}
    report = validate_runtime_wire(wire)
    assert any(e["code"] == "retained_motion_stage_conflict" and e["path"].endswith(".opacity")
               for e in report["errors"]), report


@pytest.mark.parametrize("fn,member,gate", [
    ("set_projectile_turn_modifier", "turnModifier", window("always", "since_release")),
    ("attract_npcs_while_active", "npcAttraction", {"phase": "returning"}),
    ("set_projectile_visual_scale_curve", "visualScaleCurve", {"phase": "released"}),
])
def test_existing_component_windows_also_require_latch_producers(fn, member, gate):
    from infini_local.qa.capability_witnesses import build_capability_witness
    doc = build_capability_witness(fn)
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"]["window"] = gate
    assert not validate_runtime_program(doc)["ok"]
    wire_gate = dict(gate)
    if "clock" in wire_gate:
        wire_gate["startDelayTicks"] = 0
        wire_gate["durationTicks"] = 600
        del wire_gate["startDelaySeconds"], wire_gate["durationSeconds"]
    entity[member]["window"] = wire_gate
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("name,code", [("move_boomerang", 5), ("move_returning_glaive", 14)])
def test_retained_return_driver_is_real_window_producer_without_new_trigger(name, code):
    wire, entity = compile_ok(base_document())
    wire.pop("runtimeContract")
    entity["movement"] = {"name": name, "code": code, "params": {"returnAfterTicks": 1, "returnSpeed": 1}}
    entity["opacity"] = {"alpha": 10, "window": {"phase": "returning"}}
    before = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    assert wire == before


@pytest.mark.parametrize("phase,producer,params", [
    ("returning", "set_projectile_return_trigger", {"afterSeconds": 1}),
    ("released", "accumulate_projectile_charge", {"durationSeconds": 1}),
])
def test_missing_latch_repair_can_add_only_exact_producer_and_freezes_other_window_leaves(phase, producer, params):
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    doc = base_document()
    if producer == "accumulate_projectile_charge":
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    call = add(doc, "set_projectile_opacity", {"alpha": 10, "window": window(phase)})
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    expected_dependencies = [producer, "configure_item_use"] if producer == "accumulate_projectile_charge" else [producer]
    assert scope["create"]["calls"]["allowedFns"] == expected_dependencies
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.window.phase"]}]
    proposed = deepcopy(call)
    proposed["params"]["alpha"] = 200
    proposed["params"]["window"]["durationSeconds"] = 20
    producer_call = {"id": "explicit_latch", "fn": producer, "target": call["target"], "params": params}
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposed, producer_call], "note": "add exact latch"}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, patch)
    repaired = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert repaired == call
    compile_ok(fixed)


def seek_params(phase):
    return {"target": "cursor", "maxSpeedBlocksPerSecond": 30, "velocityLerpPerUpdate": 1,
            "limitSpeedToDistance": False, "window": window(phase)}


@pytest.mark.parametrize("second_phase", ["always", "released", "outbound"])
def test_two_seek_instances_require_distinct_outbound_returning_phases(second_phase):
    doc = base_document()
    add(doc, "seek_projectile", seek_params("outbound"), "first")
    add(doc, "seek_projectile", seek_params(second_phase), "second")
    assert not validate_runtime_program(doc)["ok"]


def test_seek_capacity_and_wire_array_shape_are_strict():
    doc = base_document()
    add(doc, "set_projectile_return_trigger", {"afterSeconds": 1})
    add(doc, "seek_projectile", seek_params("outbound"), "first")
    add(doc, "seek_projectile", seek_params("returning"), "second")
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    for malformed in ([], None, entity["seek"][0], entity["seek"] * 2):
        bad = deepcopy(wire)
        next(e for e in bad["runtimeProgram"]["entities"] if e["id"] == entity["id"])["seek"] = malformed
        assert not validate_runtime_wire(bad)["ok"]
    add(doc, "seek_projectile", seek_params("returning"), "third")
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("phase,accepted", [("charging", True), ("outbound", False), ("released", False)])
def test_attachment_and_velocity_owners_require_disjoint_phases(phase, accepted):
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    add(doc, "accumulate_projectile_charge", {"durationSeconds": 1})
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, "attach_projectile", {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0, "window": window(phase)})
    add(doc, "seek_projectile", seek_params("outbound"))
    assert validate_runtime_program(doc)["ok"] is accepted
    if accepted:
        wire, entity = compile_ok(doc)
        wire.pop("runtimeContract")
        entity["attachment"]["window"]["phase"] = "outbound"
        assert not validate_runtime_wire(wire)["ok"]


def test_attachment_is_single_object_not_an_instruction_array():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision")["params"]["tileCollide"] = False
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    params = {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0}
    add(doc, "attach_projectile", params)
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    entity["attachment"] = [entity["attachment"]]
    assert not validate_runtime_wire(wire)["ok"]
    add(doc, "attach_projectile", dict(params, window=window("returning")), "second_attachment")
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("member,value", [
    ("rotation", {"mode": "spin", "offsetRadians": 0}),
    ("rotation", {"mode": "velocity", "offsetRadians": 0, "radiansPerUpdate": 0.1}),
    ("seek", [{"target": "nearest_npc", "maxSpeed": 8, "velocityLerpPerUpdate": 1, "limitSpeedToDistance": False}]),
    ("armPose", {"durationTicks": 60, "startStretch": "none", "peakStretch": "full", "endStretch": "none", "peakProgress": 0}),
    ("velocityRetention", {"multiplierPerUpdate": 1e-60}),
    ("opacity", {"alpha": True}),
    ("opacity", {"alpha": 0, "window": None}),
    ("opacity", {"alpha": 0, "window": {"phase": "always", "clock": "active", "startDelayTicks": 0, "durationTicks": 1, "extra": 1}}),
])
def test_stripped_wire_checks_present_fields_without_provenance_claim(member, value):
    wire, entity = compile_ok(base_document())
    wire.pop("runtimeContract")
    entity[member] = value
    if member == "armPose":
        entity["aim"] = {"source": "initial", "turnOwner": False}
        wire["runtimeProgram"]["itemUse"].pop("handPose", None)
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("geometry", ["set_projectile_beam_geometry", "set_projectile_lash_geometry"])
@pytest.mark.parametrize("scale,member", [
    ("set_projectile_hitbox_curve", "hitboxCurve"),
    ("set_projectile_visual_scale_curve", "visualScaleCurve"),
    ("add_projectile_visual_scale", "visualScaleRate"),
])
def test_line_geometry_refuses_dynamic_body_owners_in_author_and_stripped_wire(geometry, scale, member):
    from infini_local.qa.capability_witnesses import build_capability_witness
    doc = build_capability_witness(geometry)
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    scale_doc = build_capability_witness(scale)
    _, scale_entity = compile_ok(scale_doc)
    scale_params = next(c["params"] for c in scale_doc["runtimeProgram"]["calls"] if c["fn"] == scale)
    add(doc, scale, scale_params)
    assert not validate_runtime_program(doc)["ok"]
    entity[member] = scale_entity[member]
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == before


def test_nonzero_retention_must_not_collapse_to_zero():
    doc = base_document()
    add(doc, "multiply_projectile_velocity", {"multiplierPerUpdate": 1e-60})
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("bad_phase", [[], {}, None, 1, False])
def test_malformed_window_does_not_crash_cross_component_validation(bad_phase):
    doc = base_document()
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, "attach_projectile", {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0,
        "window": dict(window("outbound"), phase=bad_phase)})
    add(doc, "seek_projectile", seek_params("outbound"))
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("leaf,value", [("durationSeconds", 1e308), ("durationSeconds", float("inf")), ("startDelaySeconds", 10**1000)])
def test_out_of_domain_window_numbers_refuse_without_arithmetic_crash(leaf, value):
    doc = base_document()
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, "attach_projectile", {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0,
        "window": dict(window("outbound"), **{leaf: value})})
    add(doc, "seek_projectile", seek_params("outbound"))
    assert not validate_runtime_program(doc)["ok"]


def test_raw_invalid_binding_input_remains_a_refusal_not_a_motion_validator_crash():
    doc = base_document()
    doc["runtimeProgram"]["bindings"][0]["input"] = []
    assert not validate_runtime_program(doc)["ok"]


def test_axis_rotation_requires_explicit_aim_but_velocity_rotation_does_not():
    doc = base_document()
    add(doc, "set_projectile_rotation", {"mode": "axis", "offsetRadians": 0, "radiansPerSecond": 0})
    assert not validate_runtime_program(doc)["ok"]
    doc["runtimeProgram"]["calls"][-1]["params"]["mode"] = "velocity"
    assert validate_runtime_program(doc)["ok"]


def test_beam_and_lash_cannot_compete_for_collision_geometry():
    doc = base_document()
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, "set_projectile_beam_geometry", {"lengthBlocks": 20, "widthBlocks": 1, "raycastTiles": False})
    from infini_local.qa.capability_witnesses import build_capability_witness
    lash = build_capability_witness("set_projectile_lash_geometry")
    params = next(c["params"] for c in lash["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_lash_geometry")
    add(doc, "set_projectile_lash_geometry", params)
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("fn,bad_leaf,bad_value,fixed_value", [
    ("configure_spawn", "offsetBlocks", -1000, 0),
    ("spawn_entity_on_event", "damageMultiplier", -1, 1),
])
def test_count_one_spread_absence_stays_frozen_during_unrelated_repair(fn, bad_leaf, bad_value, fixed_value):
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    doc = build_capability_witness(fn)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"].update(count=1)
    call["params"].pop("spreadRadians", None)
    call["params"][bad_leaf] = bad_value
    errors = validate_runtime_program(doc)["errors"]
    assert errors
    scope = build_runtime_repair_scope(doc, errors)
    proposed = deepcopy(call)
    proposed["params"].update({bad_leaf: fixed_value, "spreadRadians": 0.5})
    filtered, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposed], "note": "fix unrelated invalid leaf"}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, filtered)
    repaired_call = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert "spreadRadians" not in repaired_call["params"]
    assert validate_runtime_program(fixed)["ok"]


@pytest.mark.parametrize("value", [None, True, "0", -1, 7])
def test_count_one_spread_omission_does_not_repair_invalid_present_values(value):
    from infini_local.qa.capability_witnesses import build_capability_witness
    doc = build_capability_witness("spawn_entity_on_event")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_entity_on_event")
    call["params"].update(count=1, spreadRadians=value)
    assert not validate_runtime_program(doc)["ok"]


def test_count_one_event_fan_omission_respects_radial_child_zero_requirement():
    from infini_local.qa.capability_witnesses import build_capability_witness
    doc = build_capability_witness("spawn_entity_on_event")
    event = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_entity_on_event")
    event["params"].update(count=1)
    event["params"].pop("spreadRadians")
    child = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_spawn" and c["target"] == event["params"]["entity"])
    child["params"]["velocity"] = {"radial": {"minSpeedBlocksPerSecond": 20, "maxSpeedBlocksPerSecond": 30}}
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    event["params"]["spreadRadians"] = 0.5
    assert not validate_runtime_program(doc)["ok"]


def test_overlapping_visual_scale_owners_are_red():
    doc = base_document()
    add(doc, "add_projectile_visual_scale", {"deltaPerSecond": 1, "maxScale": 4})
    # Real existing PR148 curve, not a stand-in for another scale owner.
    from infini_local.qa.capability_witnesses import build_capability_witness
    other = build_capability_witness("set_projectile_visual_scale_curve")
    p = next(c["params"] for c in other["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_visual_scale_curve")
    add(doc, "set_projectile_visual_scale_curve", p)
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("peak", [0, 1, False])
def test_piecewise_peak_progress_is_open_interval(peak):
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"].pop("handPose", None)
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, "set_front_arm_pose", {"durationSeconds": 1, "startStretch": "none", "peakStretch": "full", "endStretch": "none", "peakProgress": peak})
    assert not validate_runtime_program(doc)["ok"]
