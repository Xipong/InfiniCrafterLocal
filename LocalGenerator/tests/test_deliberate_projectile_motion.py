"""Movement choices stay explicit; source identity never selects a driver."""

import copy
import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.llm_authoring_pipeline import try_llm_plan
from infini_local.qa.capability_witnesses import build_capability_witness
from test_low_level_three_stage_pipeline import wire_transport  # noqa: F401


@pytest.mark.parametrize("falling", [False, True])
def test_native_arrow_parent_does_not_override_either_authored_motion_choice(wire_transport, falling):
    document = build_capability_witness("move_straight")
    if falling:
        document["runtimeProgram"]["calls"].append({"id": "explicit_gravity", "fn": "accelerate_y",
            "target": document["runtimeProgram"]["primaryEntityId"],
            "params": {"accelY": 12}})
    before = copy.deepcopy(document)
    parent = {"id": 39, "name": "Wooden Bow", "shoot": 1,
              "directProjectileRaw": {"type": 1, "fullName": "Terraria/WoodenArrowFriendly", "aiStyle": 1, "arrow": True}}
    parent_before = copy.deepcopy(parent)
    responses, _ = wire_transport
    responses.append(document)
    accepted = try_llm_plan(parent, {}, "physics-choice")
    assert accepted is not None and not responses
    assert accepted["runtimeProgram"] == before["runtimeProgram"]
    assert parent == parent_before
    assert validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(accepted)
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == document["runtimeProgram"]["primaryEntityId"])
    assert entity["movement"] == {"name": "move_straight", "code": 0, "params": {}}
    assert ("verticalAcceleration" in entity) is falling
    assert "controller" not in entity
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    assert validate_runtime_wire(wire)["ok"]
    for source in (document, None):
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                      authored_document=source, final_document=wire)["ok"]
    assert document == before
