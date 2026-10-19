"""Explicit native-front-hand movement: real Author/compiler/provenance boundary."""
from copy import deepcopy
from repair_test_helpers import projected_params

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, MOVEMENT_OPCODE
from infini_local.qa.capability_witnesses import build_capability_witness


PARAMS = {"aimMode": "cursor", 'durationSeconds': (13) / 60, "startStretch": "quarter",
          "peakStretch": "full", "hitboxOffsetPx": 11}


def fixture(**params):
    doc = build_capability_witness("move_forward_then_retract")
    calls = doc["runtimeProgram"]["calls"]
    call = next(c for c in calls if c["id"] == "witness_call")
    call.update(fn="move_front_hand", params={**PARAMS, **params})
    next(c for c in calls if c["fn"] == "configure_spawn")["params"].update(
        velocity={'constantSpeedBlocksPerSecond': (0) * 60 / 16}, count=1, spreadRadians=0)
    next(c for c in calls if c["fn"] == "set_projectile_collision")["params"]["tileCollide"] = False
    next(c for c in calls if c["fn"] == "configure_item_use")["params"].pop("handPose")
    calls.append({"id": "singleton", "fn": "set_projectile_concurrency",
                  "target": call["target"], "params": {"maxActive": 1}})
    return doc, call


def entity(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "witness_entity")


def test_explicit_call_compiles_literal_five_params_without_adding_mechanics():
    doc, call = fixture(hitboxOffsetPx=-0.0)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert doc == before
    assert entity(wire)["movement"] == {"name": "move_front_hand", "code": 20, "params": projected_params("move_front_hand", call["params"])}
    assert MOVEMENT_OPCODE["move_forward_then_retract"] == 19 and MOVEMENT_OPCODE["move_front_hand"] == 20
    cap = CAPABILITY_REGISTRY["move_front_hand"]
    assert cap.component_slot == cap.exclusive_group == "movement"
    assert cap.target_kinds == ("owner_attached_projectile",)
    assert set(cap.params) == set(PARAMS)
    assert all(p.required and p.default is None for p in cap.params.values())
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]
    for key, value in call["params"].items():
        rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
                if r.get("callId") == call["id"] and r["authoredPath"].endswith(".params." + key)]
        assert len(rows) == 1 and rows[0]["value"] == cap.params[key].to_wire(value, updates_per_tick=1) and rows[0]["status"] == "delivered"
        assert rows[0]["finalPath"].endswith(".movement.params." + (cap.params[key].wire_name or key))
    assert "controller" not in entity(wire)


@pytest.mark.parametrize("mutation", ["valid", "missing", "wrong_type", "bad_enum", "range", "name", "code", "foreign_driver", "order"])
def test_new_driver_strict_wire_requires_complete_exact_choices_even_without_provenance(mutation):
    doc, _ = fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    movement = entity(wire)["movement"]
    if mutation == "missing": movement["params"].pop("aimMode")
    if mutation == "wrong_type": movement["params"]["durationTicks"] = True
    if mutation == "bad_enum": movement["params"]["peakStretch"] = "FULL"
    if mutation == "range": movement["params"]["hitboxOffsetPx"] = 193
    if mutation == "name": movement["name"] = "move_forward_then_retract"
    if mutation == "code": movement["code"] = 19
    if mutation == "foreign_driver":
        entity(wire)["controller"] = entity(wire).pop("movement")
    if mutation == "order": movement["params"].update(startStretch="full", peakStretch="quarter")
    report = validate_runtime_wire(wire)
    assert report["ok"] == (mutation == "valid"), report["errors"]


@pytest.mark.parametrize("mutation", ["missing", "value", "source", "call", "duplicate", "all", "shared_duration_legacy"])
def test_new_present_leaves_require_unique_exact_receipts_but_old_duration_does_not(mutation):
    doc, _ = fixture()
    wire = compile_runtime_program(doc)
    if mutation == "shared_duration_legacy":
        wire = compile_runtime_program(build_capability_witness("move_forward_then_retract"))
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in receipts if r.get("callId") == "witness_call" and r["authoredPath"].endswith('.params.durationSeconds'))
    if mutation == "shared_duration_legacy":
        assert audit_compiler_receipts(receipts, final_document=wire)["ok"]
        wire.pop("runtimeContract")
        assert validate_runtime_wire(wire)["ok"]
        return
    if mutation == "missing": receipts.remove(row)
    if mutation == "value": row["value"] += 1
    if mutation == "source": row["authoredPath"] = row["authoredPath"].replace("durationSeconds", "hitboxOffsetPx")
    if mutation == "call": row["callId"] = "forged"
    if mutation == "duplicate": receipts.append(deepcopy(row))
    if mutation == "all": receipts.clear()
    audit = audit_compiler_receipts(receipts, final_document=wire)
    assert audit["ok"] == (mutation == "shared_duration_legacy"), audit["violations"]


def test_native_stretch_order_is_validated_not_lexical_enum_order():
    doc, _ = fixture(startStretch="full", peakStretch="quarter")
    report = validate_runtime_program(doc)
    assert not report["ok"] and any(r["code"] == "unordered_param_range" for r in report["errors"])
    for start, peak in (("quarter", "three_quarters"), ("none", "none"), ("full", "full")):
        doc, _ = fixture(startStretch=start, peakStretch=peak)
        assert validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("mutation", ["cap_missing", "cap_two", "count", "spread", "speed", "sampled_speed", "tile", "handPose", "controller", "over_target", "secondary", "hold", "cross_binding"])
def test_front_hand_declared_dependencies_reject_only_conflicting_composition(mutation):
    doc, _ = fixture()
    calls = doc["runtimeProgram"]["calls"]
    def p(fn): return next(c["params"] for c in calls if c["fn"] == fn)
    if mutation == "cap_missing": calls.remove(next(c for c in calls if c["fn"] == "set_projectile_concurrency"))
    if mutation == "cap_two": p("set_projectile_concurrency")["maxActive"] = 2
    if mutation == "count": p("configure_spawn")["count"] = 2
    if mutation == "spread": p("configure_spawn")["spreadRadians"] = 0.1
    if mutation == "speed": p("configure_spawn")["velocity"] = {"constantSpeedBlocksPerSecond": 3.75}
    if mutation == "sampled_speed": p("configure_spawn")["velocity"] = {"disk": {"maxSpeedBlocksPerSecond": 3.75}}
    if mutation == "tile": p("set_projectile_collision")["tileCollide"] = True
    if mutation == "handPose": p("configure_item_use")["handPose"] = "one_handed"
    if mutation == "controller":
        p("configure_item_use")["channel"] = True
        calls.append({"id": "charge", "fn": "charge_then_release", "target": "witness_entity", "params": {'chargeSeconds': (12) / 60, "powerMultiplier": 1}})
    if mutation == "over_target": p("configure_spawn")["position"] = {"above": "cursor", "heightTiles": 3, "activationDelaySeconds": 0}
    if mutation == "secondary": doc["runtimeProgram"]["primaryEntityId"] = "item"
    if mutation == "hold": doc["runtimeProgram"]["bindings"][0]["input"] = "hold"
    if mutation == "cross_binding":
        doc["runtimeProgram"]["bindings"].append({"id": "other_use", "input": "alternate_use", "action": {"kind": "use_item_body"}, "stackCost": 0, "contactDamage": False})
        doc["runtimeProgram"]["bindings"][0]["input"] = "hold"
    report = validate_runtime_program(doc)
    assert not report["ok"], mutation
    assert not any(r["code"].startswith("shape_") for r in report["errors"]), report["errors"]


@pytest.mark.parametrize("mutation", ["params_absent", "cap", "count", "spread", "speed", "tile", "handPose", "controller", "over_target", "secondary", "hold"])
def test_stripped_delivery_retains_new_movement_dependency_guards(mutation):
    doc, _ = fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    body = entity(wire)
    if mutation == "params_absent": body["movement"].pop("params")
    if mutation == "cap": body["spawn"].pop("maxActive")
    if mutation == "count": body["spawn"]["count"] = 2
    if mutation == "spread": body["spawn"]["spreadRadians"] = 0.1
    if mutation == "speed": body["spawn"]["speedPxPerTick"] = 1
    if mutation == "tile": body["collision"]["tileCollide"] = True
    if mutation == "handPose": wire["runtimeProgram"]["itemUse"]["handPose"] = "forward"
    if mutation == "controller": body["controller"] = {"code": 1, "name": "channel_beam", "params": {}}
    if mutation == "over_target": body["spawn"]["overTarget"]["heightTiles"] = 3
    if mutation == "secondary":
        wire["runtimeProgram"].update(primaryEntityId="item", primaryOwner="item_body")
        wire["runtimeProgram"]["bindings"][0]["role"] = "secondary"
    if mutation == "hold": wire["runtimeProgram"]["bindings"][0]["input"] = "hold"
    report = validate_runtime_wire(wire)
    assert not report["ok"], mutation


def test_frozen_dependency_repair_changes_only_exact_spawn_leaf_and_does_not_create_controller():
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    good, _ = fixture()
    broken = deepcopy(good)
    spawn = next(c for c in broken["runtimeProgram"]["calls"] if c["fn"] == "configure_spawn")
    spawn["params"]["velocity"] = {'constantSpeedBlocksPerSecond': (3) * 60 / 16}
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": spawn["id"], "paths": ["params.velocity"]}]
    hostile = deepcopy(spawn)
    hostile["params"].update(velocity={'constantSpeedBlocksPerSecond': (0) * 60 / 16}, aim="facing", count=2)
    patch, audit = filter_repair_patch_scope(broken, {"callsUpsert": [hostile], "note": "zero velocity only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    assert apply_repair_patch(broken, patch) == good
    assert "charge_then_release" not in CAPABILITY_REGISTRY["move_front_hand"].dependencies


@pytest.mark.parametrize("aim_mode", ["initial", "cursor"])
@pytest.mark.parametrize("spawn_aim", ["none", "cursor", "facing", "velocity"])
def test_front_hand_launch_axis_admission_joins_author_compiler_and_bare_wire(aim_mode, spawn_aim):
    doc, _ = fixture(aimMode=aim_mode)
    spawn = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_spawn")
    # Start with a real valid compile; stripping provenance must not conceal the
    # independent wire dependency, nor let the compiler pick a launch axis.
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    spawn["params"]["aim"] = spawn_aim
    entity(wire)["spawn"]["aim"] = spawn_aim
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    bare_report = validate_runtime_wire(wire)
    if spawn_aim == "none":
        index = doc["runtimeProgram"]["calls"].index(spawn)
        assert not report["ok"], report
        assert [(e["path"], e["code"], e["allowed"]) for e in report["errors"]] == [
            (f"$.runtimeProgram.calls[{index}].params.aim", "missing_dependency_param",
             ["cursor", "facing", "velocity"])]
        assert not bare_report["ok"], bare_report
        assert any(e["code"] == "movement_dependency" for e in bare_report["errors"])
        with pytest.raises(ValueError):
            compile_runtime_program(doc)
    else:
        assert report["ok"], report["errors"]
        compiled = compile_runtime_program(doc)
        assert validate_runtime_wire(compiled)["ok"]
        compiled.pop("runtimeContract")
        assert validate_runtime_wire(compiled)["ok"]
        assert bare_report["ok"], bare_report["errors"]
        assert entity(compiled)["spawn"]["aim"] == spawn_aim
        assert entity(compiled)["movement"]["code"] == 20
    assert doc == before


@pytest.mark.parametrize("fn", [name for name, cap in CAPABILITY_REGISTRY.items()
    if cap.category == "movement" and name != "move_front_hand"])
def test_other_movement_drivers_keep_explicit_spawn_aim_none(fn):
    doc = build_capability_witness(fn)
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_spawn")["params"]["aim"] = "none"
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


def test_registry_witness_uses_explicit_minimum_admission_support():
    doc = build_capability_witness("move_front_hand")
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    assert validate_runtime_wire(compile_runtime_program(doc))["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_real_author_packet_explains_center_travel_vs_native_front_hand_without_preset(monkeypatch, mode):
    import json
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, "unrelated", model_name="test-model")
    packet = json.dumps(request, ensure_ascii=False)
    assert "move_front_hand" in packet and "hitboxOffsetPx" in packet
    assert "18px" in packet and "triangular" in packet and "not hand-attached" in packet
    assert "native front hand" in packet and "axis-aligned rectangle" in packet
    assert "only 6px" in packet and "not thrust reach" in packet
    assert "source use/collision geometry" in packet
    assert "no weapon preset" in packet
    assert "quarter" in packet and "three_quarters" in packet
    from prompt_packet_helpers import request_dossier
    catalog = request_dossier(request)["runtimeCapabilityContract"]["catalog"]["capabilities"]
    assert len(catalog) == len(CAPABILITY_REGISTRY)
    assert {card["fn"] for card in catalog} == set(CAPABILITY_REGISTRY)
    hand = next(c for c in catalog if c["fn"] == "move_front_hand")
    launch_axis = [r for r in hand["requires"] if r.get("capability") == "configure_spawn" and r.get("param") == "aim"]
    declared_axis = next(r for r in CAPABILITY_REGISTRY["move_front_hand"].requirements
                         if r.capability == "configure_spawn" and r.param == "aim")
    # Foreground the design decision before the long catalog. Merely exposing a
    # working hand driver did not stop new generations copying center-offset
    # motion from another parent and calling it a held physical weapon.
    priority = " ".join(request_dossier(request)["priorityHeader"])
    for fact in ("continuous hand contact", "move_front_hand", "owner_attached_projectile",
                 "held_body", "handPose", "grip", "do not attach", "collision",
                 "deliberately detached", "not an upgrade recommendation"):
        assert fact in priority
    assert launch_axis == [{"kind": "item_capability_param", "target": "same_target",
        "capability": "configure_spawn", "param": "aim", "anyOf": ["cursor", "facing", "velocity"],
        "message": declared_axis.message}]
    spawn = next(c for c in catalog if c["fn"] == "configure_spawn")
    assert "none" in spawn["params"]["aim"]["enum"]


@pytest.mark.parametrize("key,value", [
    ("aimMode", "initial "), ("aimMode", None), ("aimMode", True),
    ("durationSeconds", 1 / 60), ("durationSeconds", 241 / 60), ("durationSeconds", 0.001), ("durationSeconds", "13"),
    ("startStretch", "threequarters"), ("peakStretch", "quarter "),
    ("hitboxOffsetPx", False), ("hitboxOffsetPx", "11"), ("hitboxOffsetPx", None),
    ("hitboxOffsetPx", -193), ("hitboxOffsetPx", float("nan")), ("hitboxOffsetPx", float("inf")),
])
def test_bad_present_new_parameters_are_red_in_both_author_and_stripped_wire(key, value):
    doc, call = fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    call["params"][key] = value
    entity(wire)["movement"]["params"][key] = value
    assert not validate_runtime_program(doc)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("key", PARAMS)
def test_no_new_required_choice_has_omission_lowering(key):
    doc, call = fixture()
    call["params"].pop(key)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


@pytest.mark.parametrize("aim,offset,duration", [("initial", -192, 2), ("cursor", 192, 240), ("initial", 0, 13)])
def test_independent_non_damage_hand_animation_does_not_select_style_class_visibility_or_metadata(aim, offset, duration):
    doc, _ = fixture(aimMode=aim, hitboxOffsetPx=offset, durationSeconds=duration / 60)
    doc["name"] = "Unrelated equipment-shaped ornament"
    doc["category"] = "equipment"
    calls = doc["runtimeProgram"]["calls"]
    calls.remove(next(c for c in calls if c["fn"] == "set_projectile_damage"))
    next(c for c in calls if c["fn"] == "configure_item_stats")["params"]["damageClass"] = "magic"
    use = next(c for c in calls if c["fn"] == "configure_item_use")["params"]
    use.update(useStyle="hold_up", hideUseGraphic=False, handPose="")
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert "damage" not in entity(wire)
    assert wire["gameplay"]["damageClass"] == "magic"
    assert wire["runtimeProgram"]["itemUse"]["useStyle"] == "hold_up"
    assert wire["runtimeProgram"]["itemUse"]["hideUseGraphic"] is False


def test_missing_singleton_dependency_repair_offers_only_exact_explicit_creation():
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
    doc, _ = fixture()
    doc["runtimeProgram"]["calls"].remove(next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_concurrency"))
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == []
    assert scope["create"]["calls"]["allowedFns"] == ["set_projectile_concurrency"]
    assert scope["create"]["calls"]["allowedTargetIds"] == ["witness_entity"]
    assert any(r["exactCapabilityParams"] == [{"capability": "set_projectile_concurrency", "param": "maxActive", "equals": 1}]
               for r in scope["repairRequirements"])


def test_frozen_wrong_primary_hand_target_offers_only_exact_primary_entity_not_owner_reselection():
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
    doc, _ = fixture()
    doc["runtimeProgram"]["primaryEntityId"] = "item"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["repairTransactions"]["primaryEntitySelection"]["allowed"] is False
    # Existing item primary cannot execute a hand movement. Do not offer every
    # attached entity or silently move the accepted primary selector.
    assert scope["retarget"]["callTargetIds"] == []


def test_frozen_incompatible_singleton_is_not_a_missing_movement_repair_alternative():
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
    doc, call = fixture()
    doc["runtimeProgram"]["calls"].remove(call)
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_concurrency")["params"]["maxActive"] = 2
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert "move_front_hand" not in scope["create"]["calls"]["allowedFns"]


def test_anonymous_nonzero_controller_cannot_compete_for_hand_position_on_delivery():
    doc, _ = fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    entity(wire)["controller"] = {"code": 2, "name": "", "params": {}}
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("aim_mode", ["initial", "cursor"])
@pytest.mark.parametrize("lane", ["hit", "hit_geometry", "periodic"])
@pytest.mark.parametrize("delay", [0, 2])
def test_front_hand_directional_event_compositions_remain_explicit_and_admitted(aim_mode, lane, delay):
    doc, _ = fixture(aimMode=aim_mode)
    fn = "spawn_entity_from_hit_target" if lane == "hit_geometry" else "spawn_entity_on_event"
    event_program = build_capability_witness(fn)["runtimeProgram"]
    doc["runtimeProgram"]["entities"].append(deepcopy(next(
        row for row in event_program["entities"] if row["id"] == "witness_child")))
    child_calls = deepcopy([row for row in event_program["calls"] if row.get("target") == "witness_child"])
    next(row for row in child_calls if row["fn"] == "configure_spawn")["params"]["aim"] = "velocity"
    event = deepcopy(next(row for row in event_program["calls"] if row["fn"] == fn))
    event["id"] = "hand_child_event"
    event["params"].update(when={'everySeconds': (6) / 60} if lane == "periodic" else "on_hit", delaySeconds=(delay) / 60)
    doc["runtimeProgram"]["calls"].extend([*child_calls, event])
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert doc == before
    assert entity(wire)["movement"]["params"]["aimMode"] == aim_mode
    assert entity(wire)["spawn"]["speedPxPerTick"] == 0
    action = entity(wire)["events"][0]
    assert action["delayTicks"] == delay
    assert action["event"] == ("periodic" if lane == "periodic" else "on_hit")
    assert next(row for row in wire["runtimeProgram"]["entities"]
                if row["id"] == "witness_child")["spawn"]["aim"] == "velocity"
