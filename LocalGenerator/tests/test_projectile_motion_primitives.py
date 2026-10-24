"""Motion Author -> strict wire/receipts and frozen Repair contracts."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from repair_test_helpers import frozen_call_repair


@pytest.mark.parametrize("fn,member,opcode", [
    ("set_projectile_vector_acceleration", "vectorAcceleration", None),
    ("set_projectile_speed_ramp", "speedRamp", None),
    ("move_spring_tether", "movement", 21),
    ("move_elliptic_orbit", "movement", 22),
    ("move_traveling_wave", "movement", 23),
])
def test_motion_vertical_slice_keeps_required_fields_and_exact_owner(fn, member, opcode):
    doc = build_capability_witness(fn)
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    bare_wire = deepcopy(wire)
    bare_wire.pop("runtimeContract")
    assert validate_runtime_wire(bare_wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
    assert CAPABILITY_REGISTRY[fn].author_prompt_card()["fn"] == fn
    entity = next(e for e in wire["runtimeProgram"]["entities"] if member in e)
    component = entity[member]
    if opcode is not None:
        assert component["code"] == opcode
        component = component["params"]
    for field in component:
        bad = deepcopy(wire)
        bad.pop("runtimeContract")
        bad_entity = next(e for e in bad["runtimeProgram"]["entities"] if e["id"] == entity["id"])
        target = bad_entity[member]["params"] if opcode is not None else bad_entity[member]
        del target[field]
        assert not validate_runtime_wire(bad)["ok"], field
    if opcode is not None:
        bad = deepcopy(wire)
        next(e for e in bad["runtimeProgram"]["entities"] if e["id"] == entity["id"])["movement"]["code"] = 0
        assert not validate_runtime_wire(bad)["ok"]
    else:
        bad = deepcopy(doc)
        next(c for c in bad["runtimeProgram"]["calls"] if c["fn"] == fn)["params"]["durationSeconds"] = 0
        assert not validate_runtime_program(bad)["ok"]


@pytest.mark.parametrize("fn", ["move_spring_tether", "move_elliptic_orbit", "move_traveling_wave"])
def test_movement_repair_freezes_all_other_authored_choices(fn):
    doc=build_capability_witness(fn)
    call=next(c for c in doc["runtimeProgram"]["calls"] if c["fn"]==fn)
    field=next(iter(call["params"]))
    valid=call["params"][field]
    call["params"][field]=None
    expected=deepcopy(doc)
    next(c for c in expected["runtimeProgram"]["calls"] if c["fn"]==fn)["params"][field]=valid
    replacement=deepcopy(call)
    replacement["params"][field]=valid
    for sibling in replacement["params"]:
        if sibling!=field: replacement["params"][sibling]=999999
    repaired,wire=frozen_call_repair(doc,[replacement],[{"id":call["id"],"paths":["params."+field]}],expected,note="repair only invalid movement leaf")
    assert repaired==expected

@pytest.mark.parametrize("fn", ["move_elliptic_orbit", "move_traveling_wave"])
def test_oriented_motion_refuses_missing_axis_at_both_boundaries(fn):
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    doc=build_capability_witness(fn)
    wire=compile_runtime_program(doc)
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"]=="configure_spawn")["params"]["aim"]="none"
    assert not validate_runtime_program(doc)["ok"]
    next(e for e in wire["runtimeProgram"]["entities"] if e.get("movement",{}).get("name")==fn)["spawn"]["aim"]="none"
    assert not validate_runtime_wire(wire)["ok"]
