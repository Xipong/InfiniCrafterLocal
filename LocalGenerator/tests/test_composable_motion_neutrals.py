"""Only parent-approved design-neutral side controls may be omitted."""
from copy import deepcopy
import pytest

from test_composable_motion_primitives import base_document, add, compile_ok
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts


CASES = [
    ("set_projectile_aim", {"source": "initial"}, {"turnOwner": False}, "aim"),
    ("attach_projectile", {"anchor": "owner_center"}, {"axisOffsetBlocks": 0, "normalOffsetBlocks": 0}, "attachment"),
    ("set_projectile_return_trigger", {"afterSeconds": 1}, {"onOwnerRelease": False, "onTileCollision": False, "disableTileCollisionOnReturn": False}, "returnTrigger"),
    ("set_projectile_rotation", {"mode": "velocity"}, {"offsetRadians": 0, "radiansPerSecond": 0}, "rotation"),
]


@pytest.mark.parametrize("fn,core,neutrals,member", CASES)
def test_omitted_side_controls_equal_only_their_explicit_neutrals(fn, core, neutrals, member):
    doc = base_document()
    if fn == "attach_projectile":
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision")["params"]["tileCollide"] = False
        add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
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
        if fn == "attach_projectile":
            add(doc, "set_projectile_aim", {"source": "initial", "turnOwner": False})
        add(doc, fn, dict(core, **neutrals))
        doc["runtimeProgram"]["calls"][-1]["params"][name] = None
        assert not validate_runtime_program(doc)["ok"]


def test_optional_return_flags_do_not_make_an_empty_trigger_valid():
    doc = base_document()
    add(doc, "set_projectile_return_trigger", {})
    assert not validate_runtime_program(doc)["ok"]


def test_valid_nonzero_side_control_is_delivered_not_rewritten():
    doc = base_document()
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision")["params"]["tileCollide"] = False
    add(doc, "set_projectile_aim", {"source": "cursor", "turnOwner": True})
    add(doc, "attach_projectile", {"anchor": "owner_center", "axisOffsetBlocks": -2, "normalOffsetBlocks": 1})
    _, entity = compile_ok(doc)
    assert entity["aim"]["turnOwner"] is True
    assert entity["attachment"]["axisOffsetPx"] == -32
    assert entity["attachment"]["normalOffsetPx"] == 16


def test_singleton_new_protocol_choices_are_selected_by_fn_not_authored_params():
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    doc = base_document()
    add(doc, "set_projectile_arrival", {"target": "owner_center", "radiusBlocks": 1})
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    assert CAPABILITY_REGISTRY["set_projectile_arrival"].fixed_wire_literals == {"action": "kill"}
    assert "action" not in CAPABILITY_REGISTRY["set_projectile_arrival"].params
    assert CAPABILITY_REGISTRY["sustain_projectile_mana"].fixed_wire_literals == {"cadence": "held_item_use_time"}
    assert "cadence" not in CAPABILITY_REGISTRY["sustain_projectile_mana"].params
    wire, entity = compile_ok(doc)
    assert entity["arrival"]["action"] == "kill"
    proof = next(r for r in wire["runtimeContract"]["finalWireReceipts"] if r["finalPath"].endswith(".arrival.action"))
    assert proof["status"] == "technical_projection" and proof["authoredPath"].endswith(".fn")


def test_owner_control_disabled_side_effects_are_omittable_but_empty_control_is_red():
    doc = base_document()
    call = add(doc, "set_projectile_owner_control", {"requireHeldItem": True})
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    call["params"] = {}
    assert not validate_runtime_program(doc)["ok"]


def test_owner_control_animation_only_is_an_effect_not_an_empty_capability():
    doc = base_document()
    add(doc, "set_projectile_owner_control", {"animation": "keep_alive"})
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]


def test_valid_absent_side_control_is_frozen_while_repairing_core_choice():
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    doc = base_document()
    call = add(doc, "set_projectile_aim", {"source": "invalid"})
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    proposed = deepcopy(call)
    proposed["params"].update(source="initial", turnOwner=True)
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposed], "note": "repair source only"}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, patch)
    repaired = next(c for c in fixed["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert repaired["params"] == {"source": "initial"}
    assert validate_runtime_program(fixed)["ok"]
