"""Optional concept limits are visible even without provider JSON Schema."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from prompt_packet_helpers import request_dossier
from infini_local.core import llm_config
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines import llm_authoring_pipeline as author


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_rendered_author_exposes_canonical_concept_text_bounds(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = author.build_initial_author_request({}, {}, "concept-bounds", model_name="offline")
    packet = request_dossier(request)
    shape = packet["requiredJsonShape"]
    schema = contract.author_item_response_schema()
    concept = schema["properties"]["concept"]
    assert "concept" not in schema["required"]
    assert "concept" in shape["optionalAdvisory"]
    assert "concept" not in shape["root"]
    for name, spec in concept["properties"].items():
        if spec.get("type") == "string":
            assert f"minLength={spec['minLength']}, maxLength={spec['maxLength']} Unicode code points" in shape["concept"][name]
    intent = concept["properties"]["plannedPlayerActions"]["items"]["properties"]["intent"]
    assert f"minLength={intent['minLength']}, maxLength={intent['maxLength']} Unicode code points" in shape["concept"]["plannedPlayerActions"][0]["intent"]
    # Inspect serialized messages, not only schema annotations/merged helpers.
    sent_shapes = [json.loads(message["content"])["requiredJsonShape"]
                   for message in request["messages"][1:]
                   if "requiredJsonShape" in json.loads(message["content"])]
    assert sent_shapes == [shape]
    assert "Summarize the mechanic" not in shape["concept"]["coreMechanic"]
    valid = {name: "x" * spec["maxLength"] for name, spec in concept["properties"].items()
             if spec.get("type") == "string"}
    validator = Draft202012Validator(concept)
    assert validator.is_valid(valid)
    valid["coreMechanic"] += "x"
    assert not validator.is_valid(valid), "visibility must not relax the existing bound"


def test_concept_prompt_limits_follow_canonical_schema_not_shadow_constants(monkeypatch):
    schema = copy.deepcopy(contract.author_item_response_schema())
    schema["properties"]["concept"]["properties"]["coreMechanic"]["maxLength"] = 537
    monkeypatch.setattr(contract, "_author_schema", lambda: schema)
    shape = contract.author_item_prompt_shape_card()
    assert "maxLength=537 Unicode code points" in shape["concept"]["coreMechanic"]


@pytest.mark.parametrize("length,valid", [(501, True), (2000, True), (2001, False)])
def test_expanded_core_mechanic_is_bounded_and_does_not_change_gameplay(length, valid):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

    item = build_runtime_fixture("workbench_blade")
    before = compile_runtime_program(item)
    text = "雪" * length
    item["concept"]["coreMechanic"] = text
    assert strict_author_shape_report(item)["ok"] is valid
    assert Draft202012Validator(contract.author_item_response_schema()).is_valid(item) is valid
    if valid:
        encoded = json.dumps(item, ensure_ascii=False)
        assert json.loads(encoded)["concept"]["coreMechanic"] == text
        after = compile_runtime_program(item)
        assert after["runtimeProgram"] == before["runtimeProgram"]
        assert after["gameplay"] == before["gameplay"]
        assert item["concept"]["coreMechanic"] == text


def test_expanded_core_mechanic_bound_reaches_provider_and_repair_metadata():
    spec = contract.author_item_response_schema()["properties"]["concept"]["properties"]["coreMechanic"]
    provider = contract.author_item_provider_response_schema()
    provider_concept = next(branch for branch in provider["properties"]["concept"]["anyOf"]
                            if branch.get("type") == "object")
    repair = contract.author_item_repair_response_schema()
    assert spec == {"type": "string", "minLength": 1, "maxLength": 2000}
    assert provider_concept["properties"]["coreMechanic"] == spec
    assert repair["properties"]["metadataPatch"]["properties"]["concept"]["properties"]["coreMechanic"] == spec
    assert "maxLength=2000 Unicode code points" in contract.author_item_prompt_shape_card()["concept"]["coreMechanic"]
