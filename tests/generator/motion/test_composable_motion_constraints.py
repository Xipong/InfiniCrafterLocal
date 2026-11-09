"""Author and stripped delivery reject incomplete/competing independent laws."""
from copy import deepcopy

import pytest
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from tests.generator.motion.test_composable_motion_primitives import add, base_document, compile_ok, window


@pytest.mark.parametrize("fn,params", [
    ("return_when", {"onOwnerRelease": False, "onTileCollision": False, "passTilesOnReturn": False}),
    ("seek", {"target": "nearest_npc", "maxSpeed": 30, "lerpPerUpdate": 1, "limitSpeedToDistance": False}),
    ("seek", {"target": "cursor", "maxSpeed": 30, "minSpeed": 60, "lerpPerUpdate": 1, "limitSpeedToDistance": False}),
    ("rotate_sprite", {"mode": "velocity", "offsetRadians": 0, "radiansPerSecond": 1}),
    ("lash_geometry", {"clock": "active", "anchor": "owner_center", "reach": 8, "segments": 12, "sweepStartRadians": -1, "sweepEndRadians": 1, "bendRatio": 0.2, "useOwnerGravity": False, "useWhipRange": False}),
])
def test_incomplete_selected_modes_are_red(fn, params):
    doc = base_document()
    if fn == "lash_geometry":
        add(doc, "set_aim", {"source": "initial", "turnOwner": False})
    add(doc, fn, params)
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("target,field,value,wire_field,wire_value", [
    ("nearest_npc", "cursorLeashBlocks", 4, "cursorLeashPx", 64),
    ("owner_center", "cursorLeashBlocks", 4, "cursorLeashPx", 64),
    ("owner_mounted", "cursorLeashBlocks", 4, "cursorLeashPx", 64),
    ("cursor", "searchRange", 20, "searchRange", 20),
    ("cursor", "requireLineOfSight", False, "requireLineOfSight", False),
    ("owner_center", "searchRange", 20, "searchRange", 20),
    ("owner_mounted", "requireLineOfSight", True, "requireLineOfSight", True),
])
def test_seek_rejects_fields_outside_selected_target_in_author_and_wire(target, field, value, wire_field, wire_value):
    doc = base_document()
    params = {"target": target, "maxSpeed": 30,
              "lerpPerUpdate": 1, "limitSpeedToDistance": False}
    if target == "nearest_npc":
        params.update(searchRange=20, requireLineOfSight=False)
    call = add(doc, "seek", params)
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
    ("return_when", {"onOwnerRelease": True, "onTileCollision": False, "passTilesOnReturn": True}),
    ("set_owner_control", {"requireHeldItem": True, "requireChannel": True, "requireItemAnimation": False, "claimHeldProjectile": False, "animation": "none", "lifetime": "authored"}),
])
def test_release_and_require_channel_active_inputs_need_explicit_channel(fn, params):
    doc = base_document()
    add(doc, fn, params)
    assert not validate_runtime_program(doc)["ok"]
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "item_use")["params"]["channel"] = True
    compile_ok(doc)


@pytest.mark.parametrize("gate,producer,leaf", [
    ({"phase": "charging"}, "charge", "phase"),
    ({"phase": "released"}, "charge", "phase"),
    (window("always", "since_release"), "charge", "clock"),
    ({"phase": "returning"}, "return_when", "phase"),
    (window("outbound", "since_return"), "return_when", "clock"),
])
def test_window_requires_actual_latch_producer_in_author_and_stripped_wire(gate, producer, leaf):
    doc = base_document()
    call = add(doc, "set_opacity", {"transparencyByte": 10, "window": gate})
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    path = f"$.runtimeProgram.calls[{doc['runtimeProgram']['calls'].index(call)}].params.window.{leaf}"
    assert any(e["path"] == path and e["code"] == "missing_capability_dependency"
               and e["allowed"] == [producer] for e in report["errors"]), report
    assert doc == before
    if producer == "charge":
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "item_use")["params"]["channel"] = True
        add(doc, producer, {"duration": 1})
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






@pytest.mark.parametrize("fn,member,gate", [
    ("turn_velocity", "turnModifier", window("always", "since_release")),
    ("attract_npcs", "npcAttraction", {"phase": "returning"}),
    ("sprite_scale_curve", "visualScaleCurve", {"phase": "released"}),
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
        del wire_gate["startDelay"], wire_gate["duration"]
    entity[member]["window"] = wire_gate
    assert not validate_runtime_wire(wire)["ok"]




@pytest.mark.parametrize("phase,producer,params", [
    ("returning", "return_when", {"afterSeconds": 1}),
    ("released", "charge", {"duration": 1}),
])
def test_missing_latch_repair_can_add_only_exact_producer_and_freezes_other_window_leaves(phase, producer, params):
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
    from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
    doc = base_document()
    if producer == "charge":
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "item_use")["params"]["channel"] = True
    call = add(doc, "set_opacity", {"transparencyByte": 10, "window": window(phase)})
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    expected_dependencies = [producer, "item_use"] if producer == "charge" else [producer]
    assert scope["create"]["calls"]["allowedFns"] == expected_dependencies
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.window.phase"]}]
    proposed = deepcopy(call)
    proposed["params"]["transparencyByte"] = 200
    proposed["params"]["window"]["duration"] = 20
    producer_call = {"id": "explicit_latch", "fn": producer, "target": call["target"], "params": params}
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposed, producer_call], "note": "add exact latch"}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, patch)
    repaired = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert repaired == call
    compile_ok(fixed)


def seek_params(phase):
    return {"target": "cursor", "maxSpeed": 30, "lerpPerUpdate": 1,
            "limitSpeedToDistance": False, "window": window(phase)}


@pytest.mark.parametrize("second_phase", ["always", "released", "outbound"])
def test_two_seek_instances_require_distinct_outbound_returning_phases(second_phase):
    doc = base_document()
    add(doc, "seek", seek_params("outbound"), "first")
    add(doc, "seek", seek_params(second_phase), "second")
    assert not validate_runtime_program(doc)["ok"]


def test_seek_capacity_and_wire_array_shape_are_strict():
    doc = base_document()
    add(doc, "return_when", {"afterSeconds": 1})
    add(doc, "seek", seek_params("outbound"), "first")
    add(doc, "seek", seek_params("returning"), "second")
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    for malformed in ([], None, entity["seek"][0], entity["seek"] * 2):
        bad = deepcopy(wire)
        next(e for e in bad["runtimeProgram"]["entities"] if e["id"] == entity["id"])["seek"] = malformed
        assert not validate_runtime_wire(bad)["ok"]
    add(doc, "seek", seek_params("returning"), "third")
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("phase,accepted", [("charging", True), ("outbound", False), ("released", False)])
def test_attachment_and_velocity_owners_require_disjoint_phases(phase, accepted):
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "item_use")["params"]["channel"] = True
    add(doc, "charge", {"duration": 1})
    add(doc, "set_aim", {"source": "initial", "turnOwner": False})
    add(doc, "attach", {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0, "window": window(phase)})
    add(doc, "seek", seek_params("outbound"))
    assert validate_runtime_program(doc)["ok"] is accepted
    if accepted:
        wire, entity = compile_ok(doc)
        wire.pop("runtimeContract")
        entity["attachment"]["window"]["phase"] = "outbound"
        assert not validate_runtime_wire(wire)["ok"]


def test_attachment_is_single_object_not_an_instruction_array():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "projectile_collision")["params"]["tileCollide"] = False
    add(doc, "set_aim", {"source": "initial", "turnOwner": False})
    params = {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0}
    add(doc, "attach", params)
    wire, entity = compile_ok(doc)
    wire.pop("runtimeContract")
    entity["attachment"] = [entity["attachment"]]
    assert not validate_runtime_wire(wire)["ok"]
    add(doc, "attach", dict(params, window=window("returning")), "second_attachment")
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("member,value", [
    ("rotation", {"mode": "spin", "offsetRadians": 0}),
    ("rotation", {"mode": "velocity", "offsetRadians": 0, "radiansPerUpdate": 0.1}),
    ("seek", [{"target": "nearest_npc", "maxSpeed": 8, "lerpPerUpdate": 1, "limitSpeedToDistance": False}]),
    ("armPose", {"durationTicks": 60, "startStretch": "none", "peakStretch": "full", "endStretch": "none", "peakProgress": 0}),
    ("velocityRetention", {"scalePerUpdate": 1e-60}),
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


@pytest.mark.parametrize("geometry", ["beam_geometry", "lash_geometry"])
@pytest.mark.parametrize("scale,member", [
    ("hitbox_curve", "hitboxCurve"),
    ("sprite_scale_curve", "visualScaleCurve"),
    ("add_sprite_scale", "visualScaleRate"),
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
    add(doc, "scale_velocity", {"scalePerUpdate": 1e-60})
    assert not validate_runtime_program(doc)["ok"]


def _disjoint_attachment_and_seek():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "item_use")["params"]["channel"] = True
    add(doc, "charge", {"duration": 1})
    add(doc, "set_aim", {"source": "initial", "turnOwner": False})
    attachment = add(doc, "attach", {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0,
        "window": window("charging")})
    add(doc, "seek", seek_params("outbound"))
    return doc, attachment


@pytest.mark.parametrize("bad_phase", [[], {}, None, 1, False])
def test_malformed_window_does_not_crash_cross_component_validation(bad_phase):
    doc, attachment = _disjoint_attachment_and_seek()
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    attachment["params"]["window"]["phase"] = bad_phase
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    path = f"$.runtimeProgram.calls[{doc['runtimeProgram']['calls'].index(attachment)}].params.window.phase"
    assert not report["ok"]
    assert any(error["path"] == path and error["code"] == "shape_type" for error in report["errors"]), report
    assert doc == before


@pytest.mark.parametrize("leaf,value,code", [
    ("duration", 1e308, "shape_maximum"),
    ("duration", float("inf"), "shape_type"),
    ("startDelay", 10**1000, "shape_type"),
])
def test_out_of_domain_window_numbers_refuse_without_arithmetic_crash(leaf, value, code):
    doc, attachment = _disjoint_attachment_and_seek()
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    attachment["params"]["window"][leaf] = value
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    path = f"$.runtimeProgram.calls[{doc['runtimeProgram']['calls'].index(attachment)}].params.window.{leaf}"
    assert not report["ok"]
    assert any(error["path"] == path and error["code"] == code for error in report["errors"]), report
    assert doc == before


def test_raw_invalid_binding_input_remains_a_refusal_not_a_motion_validator_crash():
    doc = base_document()
    doc["runtimeProgram"]["bindings"][0]["input"] = []
    assert not validate_runtime_program(doc)["ok"]


def test_axis_rotation_requires_explicit_aim_but_velocity_rotation_does_not():
    doc = base_document()
    add(doc, "rotate_sprite", {"mode": "axis", "offsetRadians": 0, "radiansPerSecond": 0})
    assert not validate_runtime_program(doc)["ok"]
    doc["runtimeProgram"]["calls"][-1]["params"]["mode"] = "velocity"
    assert validate_runtime_program(doc)["ok"]


def test_beam_and_lash_cannot_compete_for_collision_geometry():
    doc = base_document()
    add(doc, "set_aim", {"source": "initial", "turnOwner": False})
    add(doc, "beam_geometry", {"length": 20, "widthBlocks": 1, "raycastTiles": False})
    from infini_local.qa.capability_witnesses import build_capability_witness
    lash = build_capability_witness("lash_geometry")
    params = next(c["params"] for c in lash["runtimeProgram"]["calls"] if c["fn"] == "lash_geometry")
    add(doc, "lash_geometry", params)
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("fn,bad_leaf,bad_value,fixed_value", [
    ("spawn", "offsetBlocks", -1000, 0),
    ("spawn_on_event", "damageMultiplier", -1, 1),
])
def test_count_one_spread_absence_stays_frozen_during_unrelated_repair(fn, bad_leaf, bad_value, fixed_value):
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
    from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
    from infini_local.qa.capability_witnesses import build_capability_witness
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
    doc = build_capability_witness("spawn_on_event")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_on_event")
    call["params"].update(count=1, spreadRadians=value)
    assert not validate_runtime_program(doc)["ok"]


def test_count_one_event_fan_omission_respects_radial_child_zero_requirement():
    from infini_local.qa.capability_witnesses import build_capability_witness
    doc = build_capability_witness("spawn_on_event")
    event = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_on_event")
    event["params"].update(count=1)
    event["params"].pop("spreadRadians")
    child = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn" and c["target"] == event["params"]["entity"])
    child["params"]["velocity"] = {"radial": {"minSpeed": 20, "maxSpeed": 30}}
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    event["params"]["spreadRadians"] = 0.5
    assert not validate_runtime_program(doc)["ok"]


def test_overlapping_visual_scale_owners_are_red():
    doc = base_document()
    add(doc, "add_sprite_scale", {"deltaPerSecond": 1, "maxScale": 4})
    # Real existing PR148 curve, not a stand-in for another scale owner.
    from infini_local.qa.capability_witnesses import build_capability_witness
    other = build_capability_witness("sprite_scale_curve")
    p = next(c["params"] for c in other["runtimeProgram"]["calls"] if c["fn"] == "sprite_scale_curve")
    add(doc, "sprite_scale_curve", p)
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("peak", [0, 1, False])
def test_piecewise_peak_progress_is_open_interval(peak):
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "item_use")["params"].pop("handPose", None)
    add(doc, "set_aim", {"source": "initial", "turnOwner": False})
    add(doc, "front_arm_pose", {"duration": 1, "startStretch": "none", "peakStretch": "full", "endStretch": "none", "peakProgress": peak})
    assert not validate_runtime_program(doc)["ok"]
