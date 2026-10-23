from copy import deepcopy
import pytest
from infini_local.qa.capability_witnesses import build_capability_witness
from repair_test_helpers import frozen_call_repair

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
