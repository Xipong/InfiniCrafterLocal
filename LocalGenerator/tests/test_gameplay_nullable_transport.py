"""Provider nullable transport at real Gameplay boundaries; all transport is offline."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.pipelines.author_item_contract import (
    author_item_provider_response_schema,
    project_provider_author_item_to_local,
)

from infini_local.core.runtime_authoring import validate_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as pipeline
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _stats(item):
    return next(row for row in item["runtimeProgram"]["calls"] if isinstance(row, dict) and row["fn"] == "configure_item_stats")


def test_prepare_without_schema_does_not_erase_invalid_nulls_or_shift_indices():
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"].update(manaCost=None, notARegisteredParameter=None)
    item["runtimeProgram"]["calls"].insert(0, None)
    before = copy.deepcopy(item)
    prepared = pipeline._prepare_parsed_author_item(item)
    assert prepared == before
    assert item == before
    assert not validate_runtime_program(prepared)["ok"]


def _response_format():
    return {"type": "json_schema", "json_schema": {"schema": author_item_provider_response_schema()}}


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_projection_only_removes_declared_optional_object_properties(mode):
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"].update(manaCost=None, notARegisteredParameter=None, damage=None)
    item["runtimeProgram"]["calls"].insert(0, None)
    before = copy.deepcopy(item)
    response_format = _response_format() if mode == "json_schema" else ({"type": mode} if mode != "off" else None)
    projected = project_provider_author_item_to_local(item, response_format=response_format)
    params = _stats(projected)["params"]
    assert ("manaCost" not in params) == (mode == "json_schema")
    assert params["notARegisteredParameter"] is None
    assert params["damage"] is None
    assert projected["runtimeProgram"]["calls"][0] is None
    assert len(projected["runtimeProgram"]["calls"]) == len(item["runtimeProgram"]["calls"])
    assert item == before


@pytest.mark.parametrize("mode,actual", [("json_schema", "json_schema"), ("json_object", "json_object"), ("off", ""), ("json_schema", "json_object"), ("json_schema", "")])
def test_try_llm_plan_uses_actual_response_mode_and_preserves_raw(monkeypatch, mode, actual):
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": content}}], "_debug": {"responseFormatType": actual}}

    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    prepared = pipeline.try_llm_plan({}, {}, {}, {}, "nullable-test")
    assert prepared is not None
    assert ("manaCost" not in _stats(prepared)["params"]) == (actual == "json_schema")
    assert validate_runtime_program(prepared)["ok"] == (actual == "json_schema")
    assert prepared["debug"]["llmRawOutput"] == content[:12000]
    assert len(requests) == 1


@pytest.mark.parametrize("source_schema,repair_mode,actual", [
    (True, "json_schema", "json_schema"),
    (False, "json_object", "json_object"),
    (False, "off", ""),
    (False, "json_schema", "json_object"),
])
def test_format_repair_projects_each_response_with_its_own_mode(monkeypatch, source_schema, repair_mode, actual):
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", repair_mode)
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *args, **kwargs: {
        "choices": [{"message": {"content": content}}], "_debug": {"responseFormatType": actual},
    })
    prepared, raw = pipeline._repair_malformed_author_json(
        malformed_raw_text=content[:-1] + ",}", parse_error=ValueError("trailing comma"),
        original_recipe_context="{}", model_name="offline-test",
        source_response_format=_response_format() if source_schema else None,
    )
    assert ("manaCost" not in _stats(prepared)["params"]) == source_schema
    assert raw == content


def test_format_repair_cannot_turn_json_object_null_into_schema_omission(monkeypatch):
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *args, **kwargs: {
        "choices": [{"message": {"content": content}}],
    })
    with pytest.raises(PlannerUnavailable, match="changed recoverable authored fields"):
        pipeline._repair_malformed_author_json(
            malformed_raw_text=content[:-1] + ",}", parse_error=ValueError("trailing comma"),
            original_recipe_context="{}", model_name="offline-test",
        )

@pytest.mark.parametrize("mode,actual", [("json_schema", "json_schema"), ("json_object", "json_object"), ("off", ""), ("json_schema", "json_object")])
@pytest.mark.parametrize("accepted_mana", [None, 7])
def test_repair_transport_omission_preserves_frozen_presence_and_raw(monkeypatch, mode, actual, accepted_mana):
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("workbench_blade")
    stats = _stats(item)
    if accepted_mana is None:
        stats["params"].pop("manaCost", None)
    else:
        stats["params"]["manaCost"] = accepted_mana
    stats["params"]["damage"] = -1
    patch = {"note": "Fix damage only", "realizationReplacement": copy.deepcopy(item["realization"]),
             "callsUpsert": [copy.deepcopy(stats)], "metadataPatch": None}
    patch["callsUpsert"][0]["params"].update(damage=42, manaCost=None)
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *args, **kwargs: {
        "choices": [{"message": {"content": json.dumps(patch)}}], "_debug": {"responseFormatType": actual},
    })
    def repair():
        return pipeline.repair_author_item_after_failure(item, {}, {}, {}, {}, "null-repair", failure_report=validate_runtime_program(item))

    if actual != "json_schema":
        with pytest.raises(PlannerUnavailable):
            repair()
        return
    result = repair()
    assert validate_runtime_program(result)["ok"]
    assert _stats(result)["params"]["damage"] == 42
    assert ("manaCost" in _stats(result)["params"]) == (accepted_mana is not None)
    if accepted_mana is not None:
        assert _stats(result)["params"]["manaCost"] == accepted_mana
    assert result["debug"]["gameplayRepairRawPatch"] == patch

@pytest.mark.parametrize("stage", ["author", "format", "repair"])
@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_serialized_stage_prose_explains_nullable_transport_only_with_schema(monkeypatch, stage, mode):
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    requests = []

    class Captured(BaseException):
        pass

    def capture(request, **kwargs):
        requests.append(request)
        raise Captured()

    monkeypatch.setattr(pipeline, "llm_chat_json", capture)
    with pytest.raises(Captured):
        if stage == "author":
            pipeline.try_llm_plan({}, {}, {}, {}, "prose")
        elif stage == "format":
            pipeline._repair_malformed_author_json(malformed_raw_text="{", parse_error=ValueError(), original_recipe_context="{}", model_name="offline-test")
        else:
            item = build_runtime_fixture("workbench_blade")
            _stats(item)["params"]["damage"] = -1
            pipeline.repair_author_item_after_failure(item, {}, {}, {}, {}, "prose", failure_report=validate_runtime_program(item))
    # Inspect exactly the serialized messages passed to the transport seam.
    system = json.loads(json.dumps(requests[0]))["messages"][0]["content"]
    assert ("nullable transport" in system) == (mode == "json_schema")
    if mode == "json_schema":
        assert "omission" in system
        assert "array elements" in system
        assert "no change" in system

def test_public_repair_filters_frozen_semantics_before_final_validation(monkeypatch):
    from infini_local.pipelines import llm_transport as transport
    from infini_local.pipelines.author_item_contract import strict_author_item_repair_report

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"].update(damage=-1, manaCost=7)
    replacement = copy.deepcopy(_stats(item))
    replacement["params"].update(damage=42, manaCost=-1)
    patch = {"note": "Repair damage", "realizationReplacement": copy.deepcopy(item["realization"]), "callsUpsert": [replacement]}
    assert not strict_author_item_repair_report(patch)["ok"]
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *args, **kwargs: {
        "choices": [{"message": {"content": json.dumps(patch)}}],
    })
    result = pipeline.repair_author_item_after_failure(item, {}, {}, {}, {}, "frozen-range", failure_report=validate_runtime_program(item))
    assert _stats(result)["params"]["damage"] == 42
    assert _stats(result)["params"]["manaCost"] == 7
    assert validate_runtime_program(result)["ok"]

def test_projection_requires_the_actual_declared_nullable_wrapper():
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    response_format = _response_format()
    variants = response_format["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["oneOf"]
    variant = next(row for row in variants if row["properties"]["fn"]["const"] == "configure_item_stats")
    mana = variant["properties"]["params"]["properties"]["manaCost"]
    variant["properties"]["params"]["properties"]["manaCost"] = mana["anyOf"][0]
    projected = project_provider_author_item_to_local(item, response_format=response_format)
    assert _stats(projected)["params"]["manaCost"] is None
    assert not validate_runtime_program(projected)["ok"]


def test_valid_explicit_capabilities_are_unchanged_through_schema_projection():
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, compile_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness

    response_format = _response_format()
    for name in CAPABILITY_REGISTRY:
        item = build_capability_witness(name)
        projected = pipeline._prepare_parsed_author_item(item, response_format=response_format)
        assert projected == item, name
        assert validate_runtime_program(projected)["ok"], name
        assert compile_runtime_program(projected) == compile_runtime_program(item), name


@pytest.mark.parametrize("bad", [None, {}, {"description": "incomplete"}])
def test_repair_keeps_realization_replacement_shape_guard(monkeypatch, bad):
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["damage"] = -1
    replacement = copy.deepcopy(_stats(item))
    replacement["params"]["damage"] = 42
    patch = {"note": "Repair damage", "realizationReplacement": bad, "callsUpsert": [replacement]}
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *args, **kwargs: {
        "choices": [{"message": {"content": json.dumps(patch)}}],
    })
    with pytest.raises(PlannerUnavailable):
        pipeline.repair_author_item_after_failure(item, {}, {}, {}, {}, "report-shape", failure_report=validate_runtime_program(item))

def test_try_llm_plan_carries_schema_mode_into_format_repair(monkeypatch):
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    malformed = content[:-1] + ",}"
    responses = iter([malformed, content])
    stages = []

    def respond(request, **kwargs):
        stages.append(request["_infini_stage"])
        return {"choices": [{"message": {"content": next(responses)}}], "_debug": {"responseFormatType": "json_schema"}}

    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    result = pipeline.try_llm_plan({}, {}, {}, {}, "format-mode")
    assert result is not None
    assert "manaCost" not in _stats(result)["params"]
    assert validate_runtime_program(result)["ok"]
    assert stages == ["planner", "author_repair"]
    assert result["debug"]["llmRawOutput"] == malformed[:12000]
    assert result["debug"]["gameplayFormatRepairRawOutput"] == content[:12000]
