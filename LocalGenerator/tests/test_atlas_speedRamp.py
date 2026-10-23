from copy import deepcopy
import pytest
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
FN = "set_projectile_speed_ramp"
def test_complete_motion_slice():
    doc = build_capability_witness(FN)
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
    assert FN in str(CAPABILITY_REGISTRY[FN].author_prompt_card())
    spec = next(e["speedRamp"] for e in wire["runtimeProgram"]["entities"] if "speedRamp" in e)
    for field in list(spec):
        bad = deepcopy(wire)
        value = next(e["speedRamp"] for e in bad["runtimeProgram"]["entities"] if "speedRamp" in e)
        del value[field]
        assert not validate_runtime_wire(bad)["ok"], field
    bad = deepcopy(doc)
    call = next(c for c in bad["runtimeProgram"]["calls"] if c["fn"] == FN)
    call["params"]["durationSeconds"] = 0
    assert not validate_runtime_program(bad)["ok"]
