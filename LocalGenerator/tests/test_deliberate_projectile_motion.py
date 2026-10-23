"""Movement choices stay explicit; source identity never selects a driver."""

import copy
import json

import pytest

from infini_local.core import llm_config
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_author_packet_explains_no_hidden_ballistics(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    parent = {"id": 39, "name": "Wooden Bow", "shoot": 1, "directProjectileRaw": {"type": 1, "fullName": "Terraria/WoodenArrowFriendly", "aiStyle": 1, "arrow": True}}
    before = copy.deepcopy(parent)
    _, user, _ = build_initial_author_request(parent, {}, "physics-choice", model_name="offline")
    cards = {row["fn"]: row for row in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    meaning = CAPABILITY_REGISTRY["move_straight"].summary
    assert "no gravity" in meaning and "never invokes native projectile AI" in meaning
    assert cards["move_straight"]["does"] == meaning
    guide = json.loads(user)["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["projectileMotion"]
    assert "move_straight" in guide and "falling" in guide
    assert "accelerate_projectile_vertical" in guide and "deliberate" in guide
    assert "move_gravity_arc" not in cards
    assert parent == before


@pytest.mark.parametrize("falling", [False, True])
def test_both_deliberate_motion_choices_remain_valid(falling):
    document = build_capability_witness("move_straight")
    if falling:
        document["runtimeProgram"]["calls"].append({"id": "explicit_gravity", "fn": "accelerate_projectile_vertical",
            "target": document["runtimeProgram"]["primaryEntityId"],
            "params": {"accelerationYBlocksPerSecondSquared": 12}})
    before = copy.deepcopy(document)
    assert validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(document)
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
