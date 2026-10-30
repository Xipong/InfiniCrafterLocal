"""Only parent-approved design-neutral side controls may be omitted."""
from copy import deepcopy
import pytest

from test_composable_motion_primitives import base_document, add, compile_ok
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts


CASES = [
    ("set_aim", {"source": "initial"}, {"turnOwner": False}, "aim"),
    ("attach", {"anchor": "owner_center"}, {"axisOffsetBlocks": 0, "normalOffsetBlocks": 0}, "attachment"),
    ("return_when", {"afterSeconds": 1}, {"onOwnerRelease": False, "onTileCollision": False, "passTilesOnReturn": False}, "returnTrigger"),
    ("rotate_sprite", {"mode": "velocity"}, {"offsetRadians": 0, "radiansPerSecond": 0}, "rotation"),
]


@pytest.mark.parametrize("fn,core,neutrals,member", CASES)
def test_omitted_side_controls_equal_only_their_explicit_neutrals(fn, core, neutrals, member):
    doc = base_document()
    if fn == "attach":
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "projectile_collision")["params"]["tileCollide"] = False
        add(doc, "set_aim", {"source": "initial", "turnOwner": False})
    call = add(doc, fn, dict(core))
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    call["params"].update(neutrals)
    _, explicit = compile_ok(doc)
    for name in neutrals:
        call["params"].pop(name)
    before = deepcopy(doc)
    wire, sparse = compile_ok(doc)
    assert sparse == explicit
    assert doc == before
    omitted = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]
               and r["status"] == "declared_neutral_omission"]
    assert len(omitted) == len(neutrals)
    for authored in (doc, None):
        report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=authored, final_document=wire)
        assert report["ok"], report


@pytest.mark.parametrize("fn,core,neutrals,member", CASES)
def test_invalid_present_side_control_never_becomes_a_default(fn, core, neutrals, member):
    for name in neutrals:
        doc = base_document()
        if fn == "attach":
            add(doc, "set_aim", {"source": "initial", "turnOwner": False})
        add(doc, fn, dict(core, **neutrals))
        doc["runtimeProgram"]["calls"][-1]["params"][name] = None
        assert not validate_runtime_program(doc)["ok"]


def test_optional_return_flags_do_not_make_an_empty_trigger_valid():
    doc = base_document()
    add(doc, "return_when", {})
    assert not validate_runtime_program(doc)["ok"]


def test_valid_nonzero_side_control_is_delivered_not_rewritten():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "projectile_collision")["params"]["tileCollide"] = False
    add(doc, "set_aim", {"source": "cursor", "turnOwner": True})
    add(doc, "attach", {"anchor": "owner_center", "axisOffsetBlocks": -2, "normalOffsetBlocks": 1})
    _, entity = compile_ok(doc)
    assert entity["aim"]["turnOwner"] is True
    assert entity["attachment"]["axisOffsetPx"] == -32
    assert entity["attachment"]["normalOffsetPx"] == 16


def test_singleton_new_protocol_choices_are_selected_by_fn_not_authored_params():
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    doc = base_document()
    add(doc, "kill_on_arrival", {"target": "owner_center", "radius": 1})
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    assert CAPABILITY_REGISTRY["kill_on_arrival"].fixed_wire_literals == {"action": "kill"}
    assert "action" not in CAPABILITY_REGISTRY["kill_on_arrival"].params
    assert CAPABILITY_REGISTRY["sustain_mana"].fixed_wire_literals == {"cadence": "held_item_use_time"}
    assert "cadence" not in CAPABILITY_REGISTRY["sustain_mana"].params
    wire, entity = compile_ok(doc)
    assert entity["arrival"]["action"] == "kill"
    proof = next(r for r in wire["runtimeContract"]["finalWireReceipts"] if r["finalPath"].endswith(".arrival.action"))
    assert proof["status"] == "technical_projection" and proof["authoredPath"].endswith(".fn")


def test_owner_control_disabled_side_effects_are_omittable_but_empty_control_is_red():
    doc = base_document()
    call = add(doc, "set_owner_control", {"requireHeldItem": True})
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    call["params"] = {}
    assert not validate_runtime_program(doc)["ok"]


def test_owner_control_animation_only_is_an_effect_not_an_empty_capability():
    doc = base_document()
    add(doc, "set_owner_control", {"animation": "keep_alive"})
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]


def test_valid_absent_side_control_is_frozen_while_repairing_core_choice():
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    doc = base_document()
    call = add(doc, "set_aim", {"source": "invalid"})
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    proposed = deepcopy(call)
    proposed["params"].update(source="initial", turnOwner=True)
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposed], "note": "repair source only"}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, patch)
    repaired = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert repaired["params"] == {"source": "initial"}
    assert validate_runtime_program(fixed)["ok"]


RAMP_NEUTRALS = [
    ("charge", "releaseEffect", "chargeRelease", "launchSpeed", 30,
     {"damageMultiplier": 1, "knockbackMultiplier": 1, "speedMultiplier": 1,
      "pauseLifetimeWhileCharging": False}),
    ("beam_geometry", "ramp", "beamRamp", "warmupSeconds", 1,
     {"initialWidthMultiplier": 1, "initialDamageMultiplier": 1, "damageStartProgress": 0}),
]


def ramp_document(fn, property, neutrals):
    from infini_local.qa.capability_witnesses import build_capability_witness
    doc = build_capability_witness(fn)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"][property] = {"launchSpeed": 30} if property == "releaseEffect" else {"warmupSeconds": 1}
    return doc, call


@pytest.mark.parametrize("fn,property,member,core,value,neutrals", RAMP_NEUTRALS)
def test_ramp_neutrals_have_exact_full_and_stripped_wire_with_complete_provenance(fn, property, member, core, value, neutrals):
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    doc, call = ramp_document(fn, property, neutrals)
    call["params"][property][core] = value
    before = deepcopy(doc)
    wire, sparse = compile_ok(doc)
    call["params"][property].update(neutrals)
    _, explicit = compile_ok(doc)
    assert sparse == explicit
    rows = wire["runtimeContract"]["finalWireReceipts"]
    omitted = [r for r in rows if r.get("callId") == call["id"] and r["status"] == "declared_neutral_omission"]
    assert len(omitted) == len(neutrals)
    assert {r["authoredPath"].rsplit(".", 1)[-1]: r["value"] for r in omitted} == neutrals
    for authored in (before, None):
        assert audit_compiler_receipts(rows, authored_document=authored, final_document=wire)["ok"]
    stripped = deepcopy(wire)
    stripped.pop("runtimeContract")
    assert validate_runtime_wire(stripped)["ok"]
    for proof in omitted:
        incomplete = [r for r in rows if r is not proof]
        for authored in (before, None):
            assert not audit_compiler_receipts(incomplete, authored_document=authored, final_document=wire)["ok"]
        missing = deepcopy(stripped)
        entity = next(e for e in missing["runtimeProgram"]["entities"] if e["id"] == call["target"])
        del entity[member][proof["finalPath"].rsplit(".", 1)[-1]]
        assert not validate_runtime_wire(missing)["ok"], "Wire requires the materialized neutral, not a second fallback"


@pytest.mark.parametrize("fn,property,member,core,value,neutrals", RAMP_NEUTRALS)
def test_ramp_omissions_do_not_supply_core_values_or_missing_dependencies(fn, property, member, core, value, neutrals):
    doc, call = ramp_document(fn, property, neutrals)
    call["params"][property].pop(core, None)
    assert not validate_runtime_program(doc)["ok"]
    call["params"][property][core] = value
    call["fn"] = "apply_projectile_charge_release" if member == "chargeRelease" else "set_projectile_beam_ramp"
    call["params"] = call["params"][property]
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("fn,property,member,core,value,neutrals", RAMP_NEUTRALS)
def test_ramp_invalid_present_neutrals_refused_and_valid_changes_preserved(fn, property, member, core, value, neutrals):
    for name, neutral in neutrals.items():
        for bad in (None, "1", float("nan"), float("inf"), -1, True if type(neutral) is int else 0):
            doc, call = ramp_document(fn, property, neutrals)
            call["params"][property][name] = bad
            assert not validate_runtime_program(doc)["ok"], (name, bad)
        doc, call = ramp_document(fn, property, neutrals)
        chosen = True if type(neutral) is bool else (2 if member == "chargeRelease" else 0.5)
        call["params"][property][name] = chosen
        wire, entity = compile_ok(doc)
        assert entity[member][name] == chosen
        proof = next(r for r in wire["runtimeContract"]["finalWireReceipts"]
                     if r.get("callId") == call["id"] and r["authoredPath"].endswith(".params." + property + "." + name))
        assert proof["status"] == "delivered"


@pytest.mark.parametrize("fn,property,member,core,value,neutrals", RAMP_NEUTRALS)
@pytest.mark.parametrize("explicit", [False, True])
def test_ramp_repair_freezes_neutral_presence_and_values(fn, property, member, core, value, neutrals, explicit):
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    doc, call = ramp_document(fn, property, neutrals)
    if explicit:
        call["params"][property].update(neutrals)
    call["params"][property][core] = -1
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    proposed = deepcopy(call)
    proposed["params"][property][core] = value
    proposed["params"][property].update({name: True if type(neutral) is bool else 0.5
                              for name, neutral in neutrals.items()})
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposed], "note": "repair timing or launch only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    fixed = apply_repair_patch(doc, patch)
    expected = deepcopy(before)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"][property][core] = value
    assert fixed == expected and doc == before
    compile_ok(fixed)
