
from prompt_packet_helpers import request_dossier, dossier_text
"""Targeting guidance must use the same spawn syntax accepted by Author v5."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from infini_local.core import llm_config
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_targeting_card_uses_current_spawn_position_in_author_and_repair(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = author.build_initial_author_request({}, {}, "targeting-position", model_name="test-model")
    assert dossier_text(request) == user
    cards = json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]
    card = next(row for row in cards if row["fn"] == "target_and_fire")
    assert "position={at:activation_origin} consumes the firing entity origin" in card["does"]
    assert "placement=item_use_origin" not in card["does"]
    assert "aim=velocity consumes the acquired target direction" in card["does"]
    assert "other explicit child aim/position choices remain literal" in card["does"]

    document = build_capability_witness("target_and_fire")
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "target_and_fire")
    del call["params"]['intervalSeconds']
    report = validate_runtime_program(document)
    assert not report["ok"]
    dossier = author.build_gameplay_repair_dossier(document, {}, {}, failure_report=report)
    repair_card = next(row for row in dossier["existingBrokenCapabilityCards"] if row["fn"] == "target_and_fire")
    assert repair_card["does"] == card["does"]


def test_targeting_spawn_example_matches_schema_without_admitting_retired_spelling():
    schema = CAPABILITY_REGISTRY["configure_spawn"].provider_variant_schema()
    call = {
        "id": "child_spawn", "fn": "configure_spawn", "target": "child",
        "params": {
            "velocity": {'constantSpeedBlocksPerSecond': (8) * 60 / 16}, "count": 1,
            "spreadRadians": 0, 'offsetBlocks': (0) / 16, "aim": "velocity",
            "position": {"at": "activation_origin"},
        },
    }
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(call))
    retired = copy.deepcopy(call)
    del retired["params"]["position"]
    retired["params"]["placement"] = "item_use_origin"
    errors = list(validator.iter_errors(retired))
    assert {error.validator for error in errors} == {"additionalProperties", "required"}
