"""Concise debug notes are requested while legacy advisory shapes remain accepted."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from prompt_packet_helpers import request_dossier
from infini_local.core import llm_config
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines import llm_authoring_pipeline as author


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_rendered_author_requests_concise_notes_but_preserves_legacy_bounds(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = author.build_initial_author_request({}, {}, "concept-bounds", model_name="offline")
    packet = request_dossier(request)
    shape = packet["requiredJsonShape"]
    schema = contract.author_item_response_schema()
    concept = schema["properties"]["concept"]
    assert "concept" not in schema["required"]
    assert {"concept", "realization"} <= shape.keys()
    assert {"concept", "realization"} <= set(shape["root"])
    assert isinstance(shape["concept"], str)
    assert set(shape["realization"]) == {"description", "selfEvaluation"}
    # Inspect serialized messages, not only schema annotations/merged helpers.
    sent_shapes = [json.loads(message["content"])["requiredJsonShape"]
                   for message in request["messages"][1:]
                   if "requiredJsonShape" in json.loads(message["content"])]
    assert sent_shapes == [shape]
    if mode == "json_schema":
        delivered = request["response_format"]["json_schema"]["schema"]
        legacy = contract.author_item_provider_response_schema()
        expected = copy.deepcopy(legacy)
        expected["properties"]["concept"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        report = expected["properties"]["realization"]["anyOf"][0]
        report["properties"].pop("playerExperience")
        report["required"].remove("playerExperience")
        assert delivered == expected, "only advisory roots may differ from the full provider grammar"
        assert set(delivered["properties"]) == set(delivered["required"]) == {"name", "category", "concept", "runtimeProgram", "realization"}
        assert delivered["$defs"] == legacy["$defs"]
        assert delivered["properties"]["runtimeProgram"] == legacy["properties"]["runtimeProgram"]
    valid = {name: "x" * spec["maxLength"] for name, spec in concept["properties"].items()
             if spec.get("type") == "string"}
    validator = Draft202012Validator(concept)
    assert validator.is_valid(valid)
    valid["coreMechanic"] += "x"
    assert not validator.is_valid(valid), "visibility must not relax the existing bound"


def test_changed_legacy_concept_bounds_do_not_impose_structured_report(monkeypatch):
    schema = copy.deepcopy(contract.author_item_response_schema())
    schema["properties"]["concept"]["properties"]["coreMechanic"]["maxLength"] = 537
    monkeypatch.setattr(contract, "_author_schema", lambda: schema)
    shape = contract.author_item_prompt_shape_card()
    assert isinstance(shape["concept"], str)
    assert contract.author_item_response_schema()["properties"]["concept"]["properties"]["coreMechanic"]["maxLength"] == 537


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
    assert isinstance(contract.author_item_prompt_shape_card()["concept"], str)


def test_legacy_advisory_record_still_passes_full_provider_inverse_and_compiler():
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from test_codex_subscription_contract import _encode_nullable_fixture

    source = build_runtime_fixture("workbench_blade")
    before = copy.deepcopy(source)
    local = contract.author_item_response_schema()
    legacy_provider = contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(source, local)
    Draft202012Validator(legacy_provider).validate(encoded)
    restored = author._prepare_parsed_author_item(encoded, response_format={
        "type": "json_schema", "json_schema": {"schema": legacy_provider}})
    assert restored == before and source == before
    compiled, expected = compile_runtime_program(restored), compile_runtime_program(before)
    assert compiled["runtimeProgram"] == expected["runtimeProgram"]
    assert compiled["gameplay"] == expected["gameplay"]
    assert compiled["concept"] == expected["concept"] and compiled["realization"] == expected["realization"]
    generation = contract.author_item_generation_provider_schema()
    assert not Draft202012Validator(generation).is_valid(encoded), "fresh generation keeps a plain concept and separates player description from debug"
