"""Syntax recovery needs its actual source grammar, not another design catalog."""
from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.errors import PlannerUnavailable
from infini_local.pipelines.author import item_contract as contract
from infini_local.pipelines.author import request as author
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from prompt_packet_helpers import request_dossier
from test_codex_subscription_contract import _encode_nullable_fixture
from test_gameplay_repair_readonly_context import _offline_builder


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("changed", [False, True])
def test_format_repair_sends_only_recovered_function_grammar_without_design_context(monkeypatch, mode, changed):
    source = build_runtime_fixture("workbench_blade")
    raw = json.dumps(source, ensure_ascii=False)[:-1] + ",}"
    response = copy.deepcopy(source)
    if changed:
        next(row for row in response["runtimeProgram"]["calls"] if row["fn"] == "item_stats")["params"]["damage"] += 1
    calls = {row["fn"] for row in source["runtimeProgram"]["calls"]}
    requests = []

    def respond(request, **_kwargs):
        requests.append(copy.deepcopy(request))
        schema = request.get("response_format", {}).get("json_schema", {}).get("schema")
        if schema:
            encoded = _encode_nullable_fixture(response, contract.author_item_response_schema())
            Draft202012Validator(schema).validate(encoded)
        else:
            encoded = response
        return {"choices": [{"message": {"content": json.dumps(encoded)}}], "_debug": {"responseFormatType": mode}}

    _offline_builder(monkeypatch, mode, respond)
    args: dict[str, Any] = dict(malformed_raw_text=raw, parse_error=ValueError("trailing comma"),
                original_recipe_context=json.dumps({"recipeKey": "format", "parents": {"large": "unrelated design facts"}}),
                model_name="offline-format")
    if changed:
        with pytest.raises(PlannerUnavailable, match="changed recoverable authored fields"):
            author._repair_malformed_author_json(**args)
    else:
        result, _ = author._repair_malformed_author_json(**args)
        assert result == source
    assert len(requests) == 1
    packet = request_dossier(requests[0])
    assert packet["malformedRawText"] == raw
    assert "originalRecipeContext" not in packet
    assert set(packet["allowedCallParamsReadOnly"]) == calls
    assert "coreMechanic" not in json.dumps(packet.get("requiredJsonShape", {}))
    schema = requests[0].get("response_format", {}).get("json_schema", {}).get("schema")
    if schema:
        variants = schema["properties"]["runtimeProgram"]["properties"]["calls"]["items"]
        variants = variants.get("anyOf", [variants])
        assert {row["properties"]["fn"]["const"] for row in variants} == calls


def test_unrecoverable_source_remains_refused_without_inventing_gameplay(monkeypatch):
    response = build_runtime_fixture("workbench_blade")
    _offline_builder(monkeypatch, "json_object", lambda *_a, **_kw: {
        "choices": [{"message": {"content": json.dumps(response)}}]})
    with pytest.raises(PlannerUnavailable, match="cannot prove recoverable authored fields"):
        author._repair_malformed_author_json(malformed_raw_text='{"runtimeProgram":',
            parse_error=ValueError("truncated"), original_recipe_context="{}", model_name="offline-format")


@pytest.mark.parametrize("identity", ["unknown_operation", None, 7])
def test_unknown_source_function_is_preserved_for_semantic_refusal_not_guessed(monkeypatch, identity):
    source = build_runtime_fixture("workbench_blade")
    source["runtimeProgram"]["calls"][0]["fn"] = identity
    requests = []
    def respond(request, **_kwargs):
        requests.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(source)}}]}
    _offline_builder(monkeypatch, "json_object", respond)
    result, _ = author._repair_malformed_author_json(malformed_raw_text=json.dumps(source)[:-1] + ",}",
        parse_error=ValueError("trailing comma"), original_recipe_context="{}", model_name="offline-format")
    assert result == source
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    assert not validate_runtime_program(result)["ok"]
    assert set(request_dossier(requests[0])["allowedCallParamsReadOnly"]) == set(CAPABILITY_REGISTRY)
