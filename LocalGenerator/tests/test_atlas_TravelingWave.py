from copy import deepcopy
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
FN = "move_traveling_wave"
def test_complete_motion_slice():
    doc = build_capability_witness(FN)
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
    assert FN in str(CAPABILITY_REGISTRY[FN].author_prompt_card())
    movement = next(e["movement"] for e in wire["runtimeProgram"]["entities"] if e.get("movement", {}).get("name") == FN)
    assert movement["code"] == 23
    for field in movement["params"]:
        bad = deepcopy(wire)
        p = next(e["movement"]["params"] for e in bad["runtimeProgram"]["entities"] if e.get("movement", {}).get("name") == FN)
        del p[field]
        assert not validate_runtime_wire(bad)["ok"], field
    bad = deepcopy(wire)
    next(e["movement"] for e in bad["runtimeProgram"]["entities"] if e.get("movement", {}).get("name") == FN)["code"] = 0
    assert not validate_runtime_wire(bad)["ok"]
