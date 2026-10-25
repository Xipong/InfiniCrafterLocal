"""Independent primitives exercise real Author validation, compilation and wire admission."""
from copy import deepcopy
import pytest

from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


def base_document():
    return build_capability_witness("move_straight")


def add(doc, fn, params, call_id=None):
    target = doc["runtimeProgram"]["primaryEntityId"]
    call = {"id": call_id or fn, "fn": fn, "target": target, "params": params}
    doc["runtimeProgram"]["calls"].append(call)
    return call


def compile_ok(doc):
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    report = validate_runtime_wire(wire)
    assert report["ok"], report["errors"]
    assert doc == before
    return wire, next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == doc["runtimeProgram"]["primaryEntityId"])


@pytest.mark.parametrize("fn,params,member,expected", [
    ("accelerate_projectile_vertical", {"accelerationYBlocksPerSecondSquared": -2}, "verticalAcceleration", {"accelerationYPerUpdate": -2 * 16 / 3600}),
    ("scale_projectile_velocity", {"multiplierPerUpdate": 0}, "velocityScale", [{"multiplierPerUpdate": 0}]),
    ("set_projectile_rotation", {"mode": "spin", "offsetRadians": 0, "radiansPerSecond": -6}, "rotation", {"mode": "spin", "offsetRadians": 0, "radiansPerUpdate": -0.1}),
    ("oscillate_projectile_velocity", {"law": {"angular_sine": {"amplitudeRadiansPerSecond": 6}}, "frequencyRadiansPerSecond": 3, "phaseRadians": 0}, "oscillation", {"law": "angular_sine", "frequencyRadiansPerUpdate": 0.05, "phaseRadians": 0, "amplitude": 0.1}),
    ("add_projectile_visual_scale", {"deltaPerSecond": -0.6, "maxScale": 5}, "visualScaleRate", {"deltaPerUpdate": -0.01, "maxScale": 5}),
])
def test_independent_per_update_law_has_no_compound_obligations(fn, params, member, expected):
    doc = base_document()
    add(doc, fn, params)
    _, entity = compile_ok(doc)
    assert entity[member] == expected
    assert "controller" not in entity
    assert "opacity" not in entity


def window(phase, clock="active"):
    return {"phase": phase, "clock": clock, "startDelaySeconds": 0, "durationSeconds": 10}


def test_independent_outbound_return_seek_and_arrival_do_not_force_channel_or_spin():
    doc = base_document()
    add(doc, "seek_projectile", {"target": "cursor", "maxSpeedBlocksPerSecond": 30,
        "velocityLerpPerUpdate": 0.28, "limitSpeedToDistance": True, "window": window("outbound")}, "out_seek")
    add(doc, "seek_projectile", {"target": "owner_center", "maxSpeedBlocksPerSecond": 60,
        "velocityLerpPerUpdate": 1, "limitSpeedToDistance": False, "window": window("returning", "since_return")}, "back_seek")
    add(doc, "set_projectile_return_trigger", {"afterSeconds": 1, "ownerDistanceBlocks": 30,
        "onOwnerRelease": False, "onTileCollision": False, "disableTileCollisionOnReturn": False})
    add(doc, "set_projectile_arrival", {"target": "owner_center", "radiusBlocks": 1,
        "window": window("returning")})
    wire, entity = compile_ok(doc)
    assert len(entity["seek"]) == 2
    assert [s["maxSpeed"] for s in entity["seek"]] == [8, 16]
    assert entity["returnTrigger"]["afterTicks"] == 60
    assert entity["arrival"]["radiusPx"] == 16
    assert "rotation" not in entity
    assert wire["runtimeProgram"]["itemUse"]["channel"] is False
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert {r["callId"] for r in receipts if ".seek[0]." in r["finalPath"]} == {"out_seek"}
    assert {r["callId"] for r in receipts if ".seek[1]." in r["finalPath"]} == {"back_seek"}


def test_proximity_expiry_without_any_steering():
    doc = base_document()
    add(doc, "set_projectile_proximity_action", {"searchRangeTiles": 20, "triggerRadiusBlocks": 2,
        "requireLineOfSight": False, "action": "expire_then_kill"})
    _, entity = compile_ok(doc)
    assert entity["proximity"] == {"searchRangeTiles": 20, "triggerRadiusPx": 32,
        "requireLineOfSight": False, "action": "expire_then_kill"}
    assert "seek" not in entity


@pytest.mark.parametrize("peak,end", [("full", "full"), ("quarter", "none")])
def test_hand_attachment_pose_and_asymmetric_reach_are_separate(peak, end):
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"].pop("handPose", None)
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision")["params"]["tileCollide"] = False
    add(doc, "attach_projectile", {"anchor": "front_hand", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0})
    add(doc, "set_front_arm_pose", {"durationSeconds": 0.5, "startStretch": "full", "peakStretch": peak,
        "endStretch": end, "peakProgress": 0.3})
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "attach_projectile")["params"]["reachCurve"] = {"durationSeconds": 1, "startOffsetBlocks": -1,
        "peakOffsetBlocks": 4, "endOffsetBlocks": 2, "peakProgress": 0.2}
    _, entity = compile_ok(doc)
    assert entity["attachment"]["anchor"] == "front_hand"
    assert entity["armPose"]["endStretch"] == end
    assert entity["reach"]["peakOffsetPx"] == 64
    assert entity["collision"]["tileCollide"] is False
    assert "ownerControl" not in entity
    assert "maxActive" not in entity["spawn"]


def test_orbit_anchor_phase_and_rate_are_explicit_without_forced_tile_policy():
    doc = base_document()
    add(doc, "orbit_projectile", {"anchor": "owner_mounted", "radiusBlocks": 4, "radiansPerSecond": -6,
        "phaseRadians": 0.2, "identityPhaseRadians": 0})
    _, entity = compile_ok(doc)
    assert entity["orbit"] == {"anchor": "owner_mounted", "radiusPx": 64, "radiansPerUpdate": -0.1,
        "phaseRadians": 0.2, "identityPhaseRadians": 0}
    assert entity["collision"]["tileCollide"] is True


def test_charge_contact_and_owner_liveness_are_independent_of_position():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    add(doc, "accumulate_projectile_charge", {"durationSeconds": 1, "autoReleaseAfterActiveSeconds": 2})
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "accumulate_projectile_charge")["params"]["releaseEffect"] = {"damageMultiplier": 2, "knockbackMultiplier": 0,
        "speedMultiplier": 0.5, "launchSpeedBlocksPerSecond": 30, "pauseLifetimeWhileCharging": False}
    add(doc, "gate_projectile_contact", {"window": window("charging"), "enabled": False})
    add(doc, "set_projectile_owner_control", {"requireHeldItem": True, "requireChannel": False,
        "requireItemAnimation": False, "claimHeldProjectile": False, "animation": "none", "lifetime": "authored"})
    _, entity = compile_ok(doc)
    assert entity["charge"] == {"durationTicks": 60, "autoReleaseAfterActiveTicks": 120}
    assert entity["chargeRelease"]["launchSpeed"] == 8
    assert entity["chargeRelease"]["pauseLifetimeWhileCharging"] is False
    assert entity["contactGate"]["enabled"] is False
    assert "attachment" not in entity
    assert "aim" not in entity


def test_free_beam_geometry_and_ramp_do_not_imply_channel_or_attachment():
    doc = base_document()
    add(doc, "set_projectile_aim", {"source": "velocity", "turnOwner": False})
    add(doc, "set_projectile_beam_geometry", {"lengthBlocks": 20, "widthBlocks": 0.5, "raycastTiles": True})
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_beam_geometry")["params"]["ramp"] = {"warmupSeconds": 0, "initialWidthMultiplier": 1,
        "initialDamageMultiplier": 1, "damageStartProgress": 0}
    wire, entity = compile_ok(doc)
    assert entity["beamGeometry"] == {"lengthPx": 320, "widthPx": 8, "raycastTiles": True}
    assert entity["beamRamp"]["warmupTicks"] == 0
    assert wire["runtimeProgram"]["itemUse"]["channel"] is False
    assert "manaSustain" not in entity
    assert "attachment" not in entity


def test_mana_sustain_is_separate_from_beam_geometry():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    add(doc, "set_projectile_owner_control", {"requireHeldItem": True, "requireChannel": True,
        "requireItemAnimation": False, "claimHeldProjectile": False, "animation": "none", "lifetime": "keep_alive"})
    add(doc, "sustain_projectile_mana", {})
    _, entity = compile_ok(doc)
    assert entity["manaSustain"] == {"cadence": "held_item_use_time"}
    assert "beamGeometry" not in entity


def test_active_lash_has_explicit_geometry_without_animation_bound_lifetime_or_tags():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision")["params"]["tileCollide"] = False
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, "set_projectile_lash_geometry", {"clock": "active", "durationSeconds": 1,
        "anchor": "owner_center", "reachBlocks": 8, "segments": 12,
        "sweepStartRadians": -1, "sweepEndRadians": 1, "bendRatio": 0.2,
        "useOwnerGravity": False, "useOwnerWhipRangeMultiplier": False})
    _, entity = compile_ok(doc)
    assert entity["lashGeometry"]["durationTicks"] == 60
    assert entity["lashGeometry"]["reachPx"] == 128
    assert "ownerControl" not in entity
    assert entity["lifetimeTicks"] == 120


def test_fresh_schema_and_catalog_hide_compound_controllers_but_retain_wire_metadata():
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, MOVEMENT_OPCODE, compact_capability_catalog
    from infini_local.core.runtime_authoring.program_schema import runtime_program_author_schema
    retired = (set(MOVEMENT_OPCODE) - {"move_straight"}) | {"channel_beam", "charge_then_release", "orient_whip_to_owner_gravity"}
    offered = {v["properties"]["fn"]["const"] for v in runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"]}
    assert not retired & offered
    assert not retired & {r["fn"] for r in compact_capability_catalog()}
    assert retired <= CAPABILITY_REGISTRY.keys()
    for fn in retired:
        doc = base_document()
        add(doc, fn, {})
        assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("fn,params", [
    ("seek_projectile", {"target": "cursor", "maxSpeedBlocksPerSecond": 30, "velocityLerpPerUpdate": 0.5, "limitSpeedToDistance": True}),
    ("orbit_projectile", {"anchor": "owner_center", "radiusBlocks": 4, "radiansPerSecond": 0, "phaseRadians": 0, "identityPhaseRadians": 0}),
    ("accelerate_projectile_vertical", {"accelerationYBlocksPerSecondSquared": 1}),
])
def test_new_trajectory_executes_without_retained_movement_slot(fn, params):
    doc = base_document()
    doc["runtimeProgram"]["calls"] = [c for c in doc["runtimeProgram"]["calls"] if c["fn"] != "move_straight"]
    add(doc, fn, params)
    _, entity = compile_ok(doc)
    assert "movement" not in entity


def test_nonspin_rotation_has_exact_zero_technical_lowering_without_authored_rate():
    doc = base_document()
    add(doc, "set_projectile_rotation", {"mode": "velocity", "offsetRadians": 0})
    wire, entity = compile_ok(doc)
    assert entity["rotation"]["radiansPerUpdate"] == 0
    receipt = next(r for r in wire["runtimeContract"]["finalWireReceipts"] if r["finalPath"].endswith(".rotation.radiansPerUpdate"))
    assert receipt["status"] == "declared_neutral_omission"


def test_phase_window_on_existing_turn_modifier_keeps_original_delay_duration():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    add(doc, "accumulate_projectile_charge", {"durationSeconds": 1})
    add(doc, "set_projectile_turn_modifier", {"turnRadiansPerSecond": 3, "startDelaySeconds": 0.2,
        "durationSeconds": 1, "window": window("released", "since_release")})
    _, entity = compile_ok(doc)
    assert entity["turnModifier"]["startDelayTicks"] == 12
    assert entity["turnModifier"]["durationTicks"] == 60
    assert entity["turnModifier"]["window"]["phase"] == "released"


def test_all_new_registry_witnesses_reach_real_compiler_and_stripped_wire():
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    for cap in CAPABILITY_REGISTRY.values():
        if cap.category != "motion_primitive" or not cap.author_visible:
            continue
        doc = build_capability_witness(cap.name)
        wire, _ = compile_ok(doc)
        wire.pop("runtimeContract")
        assert validate_runtime_wire(wire)["ok"], cap.name


def test_oscillation_selected_law_owns_amplitude_units_and_discriminator():
    doc = base_document()
    add(doc, "oscillate_projectile_velocity", {"frequencyRadiansPerSecond": 3, "phaseRadians": 0,
        "law": {"lateral_velocity_sine": {"amplitudeBlocksPerSecond": 30}}})
    _, entity = compile_ok(doc)
    assert entity["oscillation"] == {"law": "lateral_velocity_sine", "frequencyRadiansPerUpdate": 0.05,
        "phaseRadians": 0, "amplitude": 8}
    assert "seek" not in entity


def test_charge_latch_produces_release_event_without_compound_controller():
    from infini_local.core.runtime_authoring.wire_views import runtime_event_inventory
    doc = build_capability_witness("spawn_entity_on_event")
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_entity_on_event")["params"]["when"] = "on_release"
    add(doc, "accumulate_projectile_charge", {"durationSeconds": 1})
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    # Read-only inventory uses actual persisted components, not a compilation
    # or an inverse Author reconstruction.
    wire, entity = compile_ok(base_document())
    wire.pop("runtimeContract")
    entity["charge"] = {"durationTicks": 60}
    assert {"entityId": entity["id"], "event": "on_release"} in runtime_event_inventory(wire)


def test_seek_bound_and_fresh_field_guide_are_registry_owned():
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, runtime_authoring_prompt_field_guide
    import json
    cap = CAPABILITY_REGISTRY["seek_projectile"]
    assert cap.max_per_target == 2
    assert cap.author_prompt_card()["maxPerTarget"] == 2
    guide = json.dumps(runtime_authoring_prompt_field_guide())
    assert "move_front_hand" not in guide
    assert "attach_projectile" in guide and "set_front_arm_pose" in guide


def test_charging_attachment_released_seek_and_existing_modifiers_compose_without_old_driver():
    doc = base_document()
    doc["runtimeProgram"]["calls"] = [c for c in doc["runtimeProgram"]["calls"] if c["fn"] != "move_straight"]
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    add(doc, "accumulate_projectile_charge", {"durationSeconds": 1})
    add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
    add(doc, "attach_projectile", {"anchor": "owner_center", "axisOffsetBlocks": 0, "normalOffsetBlocks": 0,
        "window": window("charging")})
    add(doc, "seek_projectile", {"target": "cursor", "maxSpeedBlocksPerSecond": 30, "velocityLerpPerUpdate": 1,
        "limitSpeedToDistance": False, "window": window("released", "since_release")})
    for fn in ("set_projectile_turn_modifier", "scale_projectile_velocity", "set_projectile_homing_modifier"):
        witness = build_capability_witness(fn)
        params = next(c["params"] for c in witness["runtimeProgram"]["calls"] if c["fn"] == fn)
        add(doc, fn, dict(params, window=window("released", "since_release")))
    _, entity = compile_ok(doc)
    assert "movement" not in entity and "controller" not in entity
    assert all(entity[member]["window"]["phase"] == "released" for member in ("turnModifier", "homingModifier"))
    assert entity["velocityScale"][0]["window"]["phase"] == "released"


def test_phase_only_window_has_no_invented_duration_and_partial_timing_is_red():
    doc = base_document()
    add(doc, "set_projectile_return_trigger", {"afterSeconds": 1})
    call = add(doc, "set_projectile_opacity", {"alpha": 10, "window": {"phase": "returning"}})
    wire, entity = compile_ok(doc)
    assert entity["opacity"]["window"] == {"phase": "returning"}
    for partial in ({"clock": "active"}, {"startDelaySeconds": 0}, {"durationSeconds": 1},
                    {"clock": "active", "durationSeconds": 1}, {"clock": None}):
        call["params"]["window"] = {"phase": "returning", **partial}
        assert not validate_runtime_program(doc)["ok"]
    wire.pop("runtimeContract")
    entity["opacity"]["window"]["clock"] = "active"
    assert not validate_runtime_wire(wire)["ok"]


def test_provider_and_prompt_share_one_window_definition():
    from infini_local.core.runtime_authoring.program_schema import author_item_response_schema, runtime_program_author_schema, author_item_repair_schema
    from infini_local.core.runtime_authoring.capability_registry import compact_capability_catalog, runtime_authoring_prompt_field_guide
    from jsonschema import Draft202012Validator
    for schema in (author_item_response_schema(), runtime_program_author_schema(), author_item_repair_schema()):
        Draft202012Validator.check_schema(schema)
        assert "motionWindow" in schema["$defs"]
    cards = compact_capability_catalog()
    window_cards = [card["params"]["window"] for card in cards if "window" in card["params"]]
    assert window_cards and all(card["typeRef"] == "motionWindow" and "shape" not in card for card in window_cards)
    assert "motionWindow" in runtime_authoring_prompt_field_guide()["types"]


def test_opacity_window_preserves_optional_absence_and_strict_nested_units():
    doc = base_document()
    add(doc, "set_projectile_return_trigger", {"afterSeconds": 1})
    add(doc, "set_projectile_opacity", {"alpha": 120, "window": {
        "phase": "returning", "clock": "since_return", "startDelaySeconds": 0, "durationSeconds": 0.5}})
    _, entity = compile_ok(doc)
    assert entity["opacity"]["window"] == {
        "phase": "returning", "clock": "since_return", "startDelayTicks": 0, "durationTicks": 30}
    for value in (None, {}, {"phase": "returning", "clock": "active", "startDelaySeconds": False, "durationSeconds": 1},
                  {"phase": "returning", "clock": "active", "startDelaySeconds": 0, "durationSeconds": 0},
                  {"phase": "returning", "clock": "active", "startDelaySeconds": 0, "durationSeconds": 1, "oops": 0}):
        bad = deepcopy(doc)
        bad["runtimeProgram"]["calls"][-1]["params"]["window"] = value
        assert not validate_runtime_program(bad)["ok"]


def test_opacity_alone_has_no_wobble_or_movement_obligation():
    doc = base_document()
    add(doc, "set_projectile_opacity", {"alpha": 0})
    wire, entity = compile_ok(doc)
    assert entity["opacity"] == {"alpha": 0}
    assert "oscillation" not in entity
    assert any(r.get("fn") == "set_projectile_opacity" and r["finalPath"].endswith(".opacity.alpha")
               and r["value"] == 0 for r in wire["runtimeContract"]["finalWireReceipts"])


_PACKAGED = [
    ("set_projectile_beam_geometry", "ramp", "set_projectile_beam_ramp", "beamRamp", {"warmupSeconds": 0}),
    ("attach_projectile", "reachCurve", "set_projectile_reach_curve", "reach", {
        "durationSeconds": 1, "startOffsetBlocks": -1, "peakOffsetBlocks": 4,
        "endOffsetBlocks": 2, "peakProgress": 0.2,
        "window": {"phase": "always", "clock": "active", "startDelaySeconds": 0.5, "durationSeconds": 1}}),
    ("accumulate_projectile_charge", "releaseEffect", "apply_projectile_charge_release", "chargeRelease", {
        "launchSpeedBlocksPerSecond": 30}),
]


@pytest.mark.parametrize("parent,property,retired,member,params", _PACKAGED)
def test_optional_motion_property_is_exact_separate_native_component(parent, property, retired, member, params):
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY

    doc = build_capability_witness(parent)
    selected = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == parent)
    absent, entity = compile_ok(doc)
    assert member not in entity
    selected["params"][property] = deepcopy(params)
    wire, entity = compile_ok(doc)
    assert member in entity
    if member == "chargeRelease":
        assert entity[member]["launchSpeed"] == 8
        assert entity[member]["damageMultiplier"] == 1
    if member == "reach":
        assert entity[member]["window"]["startDelayTicks"] == 30
        assert "window" not in entity["attachment"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    nested = [r for r in receipts if "." + member + "." in r["finalPath"]]
    assert nested and {r["fn"] for r in nested} == {parent}
    assert all(".params." + property + "." in r["authoredPath"] for r in nested)
    assert not CAPABILITY_REGISTRY[retired].author_visible
    for source in (None, doc):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
        for corruption in ("missing", "wrong_component", "wrong_call", "duplicate"):
            tampered = deepcopy(receipts)
            index = next(i for i, r in enumerate(tampered) if r == nested[0])
            if corruption == "missing":
                tampered.pop(index)
            elif corruption == "wrong_component":
                tampered[index]["finalPath"] = tampered[index]["finalPath"].replace("." + member + ".", ".damage.")
            elif corruption == "wrong_call":
                tampered[index]["callId"] = "foreign"
            else:
                tampered.append(deepcopy(tampered[index]))
            assert not audit_compiler_receipts(tampered, authored_document=source, final_document=wire)["ok"]
    delivery = deepcopy(wire)
    delivery.pop("runtimeContract")
    assert validate_runtime_wire(delivery)["ok"]
    # Historical standalone component receipts remain valid, while the fresh
    # Author spelling is rejected. Native data itself is byte-for-byte identical.
    legacy = deepcopy(receipts)
    for row in legacy:
        if "." + member + "." in row["finalPath"]:
            row["fn"], row["callId"] = retired, "historical_child"
            row["authoredPath"] = row["authoredPath"].replace(".params." + property + ".", ".params.")
            row["authoredPath"] = __import__("re").sub(r"calls\[\d+\]", "calls[999]", row["authoredPath"])
    assert audit_compiler_receipts(legacy, final_document=wire)["ok"]
    selected["params"].pop(property)
    add(doc, retired, deepcopy(params))
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("parent,property,retired,member,params", _PACKAGED)
@pytest.mark.parametrize("bad", [None, {}, {"unknown": 1}])
def test_nested_property_rejects_null_empty_and_unknown(parent, property, retired, member, params, bad):
    doc = build_capability_witness(parent)
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == parent)["params"][property] = bad
    assert not validate_runtime_program(doc)["ok"]


def test_nested_reach_window_requires_real_release_producer():
    doc = build_capability_witness("attach_projectile")
    attach = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "attach_projectile")
    attach["params"]["reachCurve"] = deepcopy(_PACKAGED[1][4])
    attach["params"]["reachCurve"]["window"] = {"phase": "released"}
    errors = validate_runtime_program(doc)["errors"]
    assert any(e["code"] == "missing_capability_dependency" and ".reachCurve.window.phase" in e["path"] for e in errors)
