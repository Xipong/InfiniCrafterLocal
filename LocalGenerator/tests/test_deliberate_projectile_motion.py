"""Movement choices stay explicit; source identity never selects a driver."""
import copy
import json

import pytest

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, compile_runtime_program, validate_runtime_program
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines import llm_transport
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_author_packet_explains_no_hidden_ballistics(monkeypatch, mode):
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    parent = {"id": 39, "name": "Wooden Bow", "shoot": 1, "directProjectileRaw": {"type": 1, "fullName": "Terraria/WoodenArrowFriendly", "aiStyle": 1, "arrow": True}}
    before = copy.deepcopy(parent)
    _, user, _ = build_initial_author_request(parent, {}, {}, {}, "physics-choice", model_name="offline")
    cards = {row["fn"]: row for row in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    meaning = CAPABILITY_REGISTRY["move_straight"].summary
    assert "no gravity" in meaning and "never invokes native projectile AI" in meaning
    assert cards["move_straight"]["does"] == meaning
    guide = json.loads(user)["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["projectileMotion"]
    assert "straight" in guide and "falling" in guide and "intentional" in guide
    assert parent == before


@pytest.mark.parametrize("driver", ["move_straight", "move_gravity_arc"])
def test_both_deliberate_motion_choices_remain_valid(driver):
    document = build_capability_witness(driver)
    before = copy.deepcopy(document)
    assert validate_runtime_program(document)["ok"]
    compile_runtime_program(document)
    assert document == before
