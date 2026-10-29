"""Independent hand axis/attachment/pose: Author, compiler and provenance boundary.

The retired bundle's singleton/zero-speed/tile-off/monotone-stretch rules are
not primitive invariants. Their replacements below exercise explicit independent
choices; pose ownership, typed leaves and frozen Repair remain strict.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, MOVEMENT_OPCODE
from infini_local.qa.capability_witnesses import build_capability_witness
from test_composable_motion_primitives import add


PARAMS = {"durationSeconds": 13 / 60, "startStretch": "quarter",
          "peakStretch": "full", "endStretch": "none", "peakProgress": .3}


def fixture(*, source="cursor", axisOffsetBlocks=11 / 16, **pose_params):
    doc = build_capability_witness("move_straight")
    calls = doc["runtimeProgram"]["calls"]
    calls.remove(next(c for c in calls if c["fn"] == "move_straight"))
    next(c for c in calls if c["fn"] == "configure_item_use")["params"].pop("handPose", None)
    # Always-absolute motion cannot execute native tile collision; choose explicitly.
    next(c for c in calls if c["fn"] == "set_projectile_collision")["params"]["tileCollide"] = False
    add(doc, "set_projectile_aim", {"source": source, "turnOwner": False})
    add(doc, "attach_projectile", {"anchor": "front_hand", "axisOffsetBlocks": axisOffsetBlocks,
                                   "normalOffsetBlocks": 0})
    pose = add(doc, "set_front_arm_pose", {**PARAMS, **pose_params}, "hand_pose")
    return doc, pose


def entity(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "witness_entity")


def saved_hand_wire():
    """Immutable already-compiled delivery; never reconstruct retired Author calls."""
    return json.loads((Path(__file__).resolve().parents[2] / "tools/fixtures/front-hand-compiled.json").read_text())


def test_independent_hand_choices_compile_without_adding_bundle_mechanics():
    doc, pose = fixture(axisOffsetBlocks=-0.0)
    before = deepcopy(doc)
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    body = entity(wire)
    assert doc == before
    assert body["aim"] == {"source": "cursor", "turnOwner": False}
    assert body["attachment"] == {"anchor": "front_hand", "axisOffsetPx": -0.0, "normalOffsetPx": 0}
    assert body["armPose"] == {"durationTicks": 13, "startStretch": "quarter", "peakStretch": "full",
                               "endStretch": "none", "peakProgress": .3}
    assert body["collision"]["tileCollide"] is False
    assert body["spawn"]["speedPxPerTick"] == 8
    assert "maxActive" not in body["spawn"]
    assert not {"movement", "controller", "reach", "ownerControl"} & body.keys()
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]
    for key, value in pose["params"].items():
        spec = CAPABILITY_REGISTRY[pose["fn"]].params[key]
        rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
                if r.get("callId") == pose["id"] and r["authoredPath"].endswith(".params." + key)]
        assert len(rows) == 1
        assert rows[0]["value"] == spec.to_wire(value, updates_per_tick=1)
        assert rows[0]["status"] == "delivered"
        assert rows[0]["finalPath"].endswith(".armPose." + (spec.wire_name or key))
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mutation", ["valid", "missing", "null", "wrong_type", "bad_enum", "range", "foreign_leaf"])
def test_independent_pose_strict_wire_checks_present_component_without_provenance(mutation):
    wire = compile_runtime_program(fixture()[0])
    wire.pop("runtimeContract")
    pose = entity(wire)["armPose"]
    if mutation == "missing": pose.pop("endStretch")
    if mutation == "null": entity(wire)["armPose"] = None
    if mutation == "wrong_type": pose["durationTicks"] = True
    if mutation == "bad_enum": pose["peakStretch"] = "FULL"
    if mutation == "range": pose["peakProgress"] = 1
    if mutation == "foreign_leaf": pose["hitboxOffsetPx"] = 11
    report = validate_runtime_wire(wire)
    assert report["ok"] == (mutation == "valid"), report["errors"]


@pytest.mark.parametrize("mutation", ["valid", "missing", "value", "source", "call", "duplicate", "all"])
def test_new_present_leaves_require_unique_exact_receipts(mutation):
    doc, pose = fixture()
    wire = compile_runtime_program(doc)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in receipts if r.get("callId") == pose["id"] and r["authoredPath"].endswith('.params.durationSeconds'))
    if mutation == "missing": receipts.remove(row)
    if mutation == "value": row["value"] += 1
    if mutation == "source": row["authoredPath"] = row["authoredPath"].replace("durationSeconds", "peakProgress")
    if mutation == "call": row["callId"] = "forged"
    if mutation == "duplicate": receipts.append(deepcopy(row))
    if mutation == "all": receipts.clear()
    audit = audit_compiler_receipts(receipts, final_document=wire)
    assert audit["ok"] == (mutation == "valid"), audit["violations"]


@pytest.mark.parametrize("start,peak,end", [("full", "quarter", "none"), ("none", "none", "none"), ("full", "full", "full")])
def test_asymmetric_and_constant_pose_are_authored_not_old_monotone_bundle(start, peak, end):
    doc, _ = fixture(startStretch=start, peakStretch=peak, endStretch=end)
    assert validate_runtime_program(doc)["ok"]
    assert entity(compile_runtime_program(doc))["armPose"]["endStretch"] == end


@pytest.mark.parametrize("mutation", ["count", "spread", "speed", "sampled_speed", "over_target", "cap_two", "charge"])
def test_old_bundle_restrictions_are_independent_explicit_choices(mutation):
    doc, _ = fixture()
    calls = doc["runtimeProgram"]["calls"]
    spawn = next(c["params"] for c in calls if c["fn"] == "configure_spawn")
    if mutation == "count": spawn["count"] = 2
    if mutation == "spread": spawn["spreadRadians"] = .1
    if mutation == "speed": spawn["velocity"] = {"constantSpeedBlocksPerSecond": 3.75}
    if mutation == "sampled_speed": spawn["velocity"] = {"disk": {"maxSpeedBlocksPerSecond": 3.75}}
    if mutation == "over_target": spawn["position"] = {"above": "cursor", "heightTiles": 3, "activationDelaySeconds": 0}
    if mutation == "cap_two": add(doc, "set_projectile_concurrency", {"maxActive": 2})
    if mutation == "charge":
        next(c["params"] for c in calls if c["fn"] == "configure_item_use")["channel"] = True
        add(doc, "accumulate_projectile_charge", {"durationSeconds": .2})
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    assert doc == before


@pytest.mark.parametrize("mutation", ["handPose", "secondary", "hold", "duplicate_pose", "orbit", "tile"])
def test_actual_pose_or_position_ownership_conflicts_are_red(mutation):
    doc, pose = fixture()
    calls = doc["runtimeProgram"]["calls"]
    if mutation == "handPose": next(c["params"] for c in calls if c["fn"] == "configure_item_use")["handPose"] = "one_handed"
    if mutation == "tile": next(c["params"] for c in calls if c["fn"] == "set_projectile_collision")["tileCollide"] = True
    if mutation == "secondary": doc["runtimeProgram"]["primaryEntityId"] = "item"
    if mutation == "hold": doc["runtimeProgram"]["bindings"][0]["input"] = "hold"
    if mutation == "duplicate_pose": calls.append({**deepcopy(pose), "id": "other_pose"})
    if mutation == "orbit": add(doc, "orbit_projectile", {"anchor": "owner_center", "radiusBlocks": 4,
        "radiansPerSecond": 1, "phaseRadians": 0, "identityPhaseRadians": 0})
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(doc)


@pytest.mark.parametrize("source", ["initial", "cursor", "facing", "velocity"])
@pytest.mark.parametrize("spawn_aim", ["none", "cursor", "facing", "velocity"])
def test_axis_owner_is_explicit_and_independent_of_spawn_launch(source, spawn_aim):
    doc, _ = fixture(source=source)
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_spawn")["params"]["aim"] = spawn_aim
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert entity(wire)["aim"]["source"] == source
    assert entity(wire)["spawn"]["aim"] == spawn_aim
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fn,key,value,wire_key", [
    ("set_projectile_aim", "source", "initial ", "source"),
    ("set_projectile_aim", "source", None, "source"),
    ("set_projectile_aim", "turnOwner", 1, "turnOwner"),
    ("set_front_arm_pose", "durationSeconds", 1 / 60, "durationTicks"),
    ("set_front_arm_pose", "durationSeconds", 241 / 60, "durationTicks"),
    ("set_front_arm_pose", "durationSeconds", "13", "durationTicks"),
    ("set_front_arm_pose", "startStretch", "threequarters", "startStretch"),
    ("set_front_arm_pose", "endStretch", None, "endStretch"),
    ("set_front_arm_pose", "peakProgress", False, "peakProgress"),
    ("set_front_arm_pose", "peakProgress", 0, "peakProgress"),
    ("set_front_arm_pose", "peakProgress", 1, "peakProgress"),
    ("attach_projectile", "axisOffsetBlocks", False, "axisOffsetPx"),
    ("attach_projectile", "axisOffsetBlocks", "11", "axisOffsetPx"),
    ("attach_projectile", "axisOffsetBlocks", None, "axisOffsetPx"),
    ("attach_projectile", "axisOffsetBlocks", float("nan"), "axisOffsetPx"),
    ("attach_projectile", "normalOffsetBlocks", float("inf"), "normalOffsetPx"),
])
def test_bad_present_parameters_are_red_in_author_and_stripped_wire(fn, key, value, wire_key):
    doc, _ = fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)["params"][key] = value
    member = {"set_projectile_aim": "aim", "set_front_arm_pose": "armPose", "attach_projectile": "attachment"}[fn]
    # Wire duration uses ticks, not seconds; retain the same intended out-of-range mutation.
    wire_value = (1 if value == 1 / 60 else 241) if key == "durationSeconds" and isinstance(value, float) else value
    entity(wire)[member][wire_key] = wire_value
    assert not validate_runtime_program(doc)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("key", PARAMS)
def test_required_pose_choices_have_no_omission_lowering(key):
    doc, pose = fixture()
    pose["params"].pop(key)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(doc)


@pytest.mark.parametrize("fn", ["move_front_hand", "move_forward_then_retract", "charge_then_release"])
def test_retired_bundle_refused_as_new_author_choice_but_opcode_metadata_retained(fn):
    doc, pose = fixture()
    pose.update(fn=fn, params={})
    assert not CAPABILITY_REGISTRY[fn].author_visible
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(doc)
    assert MOVEMENT_OPCODE["move_front_hand"] == 20
    assert MOVEMENT_OPCODE["move_forward_then_retract"] == 19


@pytest.mark.parametrize("source,offset,duration", [("initial", -12, 2), ("cursor", 12, 240), ("initial", 0, 13)])
def test_non_damage_hand_animation_does_not_select_style_class_visibility_or_metadata(source, offset, duration):
    doc, _ = fixture(source=source, axisOffsetBlocks=offset, durationSeconds=duration / 60)
    doc.update(name="Unrelated equipment-shaped ornament", category="equipment")
    calls = doc["runtimeProgram"]["calls"]
    calls.remove(next(c for c in calls if c["fn"] == "set_projectile_damage"))
    next(c for c in calls if c["fn"] == "configure_item_stats")["params"]["damageClass"] = "magic"
    next(c for c in calls if c["fn"] == "configure_item_use")["params"].update(
        useStyle="hold_up", hideUseGraphic=False, handPose="")
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert "damage" not in entity(wire)
    assert wire["gameplay"]["damageClass"] == "magic"
    assert wire["runtimeProgram"]["itemUse"]["useStyle"] == "hold_up"
    assert wire["runtimeProgram"]["itemUse"]["hideUseGraphic"] is False
    assert entity(wire)["attachment"]["axisOffsetPx"] == offset * 16
    assert doc == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_real_author_packet_offers_separate_hand_choices_not_retired_profiles(monkeypatch, mode):
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    from prompt_packet_helpers import request_dossier
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    request, _, _ = build_initial_author_request({}, {}, "unrelated", model_name="test-model")
    dossier = request_dossier(request)
    catalog = dossier["runtimeCapabilityContract"]["catalog"]["capabilities"]
    assert {c["fn"] for c in catalog} == {name for name, cap in CAPABILITY_REGISTRY.items() if cap.author_visible}
    packet = json.dumps(request, ensure_ascii=False)
    for fn in ("set_projectile_aim", "attach_projectile", "set_front_arm_pose", "reachCurve"):
        assert fn in packet
    offered = {c["fn"] for c in catalog}
    assert not offered.intersection({"move_front_hand", "move_forward_then_retract", "charge_then_release"})
    for fact in ("front_hand", "peakProgress", "endStretch", "normalOffsetBlocks", "grip"):
        assert fact in packet


@pytest.mark.parametrize("source", ["initial", "cursor"])
@pytest.mark.parametrize("lane", ["hit", "hit_geometry", "periodic"])
@pytest.mark.parametrize("delay", [0, 2])
def test_front_hand_directional_event_compositions_remain_explicit_and_admitted(source, lane, delay):
    doc, _ = fixture(source=source)
    fn = "spawn_entity_from_hit_target" if lane == "hit_geometry" else "spawn_entity_on_event"
    event_program = build_capability_witness(fn)["runtimeProgram"]
    doc["runtimeProgram"]["entities"].append(deepcopy(next(
        row for row in event_program["entities"] if row["id"] == "witness_child")))
    child_calls = deepcopy([row for row in event_program["calls"] if row.get("target") == "witness_child"])
    next(row for row in child_calls if row["fn"] == "configure_spawn")["params"]["aim"] = "velocity"
    event = deepcopy(next(row for row in event_program["calls"] if row["fn"] == fn))
    event["id"] = "hand_child_event"
    event["params"].update(when={"everySeconds": 6 / 60} if lane == "periodic" else "on_hit", delaySeconds=delay / 60)
    doc["runtimeProgram"]["calls"].extend([*child_calls, event])
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert doc == before
    assert entity(wire)["aim"]["source"] == source
    action = entity(wire)["events"][0]
    assert action["delayTicks"] == delay
    assert action["event"] == ("periodic" if lane == "periodic" else "on_hit")
    assert next(row for row in wire["runtimeProgram"]["entities"]
                if row["id"] == "witness_child")["spawn"]["aim"] == "velocity"
