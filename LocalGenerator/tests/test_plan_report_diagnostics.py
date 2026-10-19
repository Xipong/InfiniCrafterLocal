"""Plan comparison formatting never owns gameplay or presentation admission."""
from __future__ import annotations

import copy
import json
import socket

import pytest

from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
import infini_local.core.runtime_authoring.program_schema as program_schema
from infini_local.pipelines import gameplay_stage, llm_authoring_pipeline
from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _fixture(case):
    document = build_runtime_fixture("workbench_blade")
    document["id"] = "advisory-report-control"
    document["realization"]["selfEvaluation"] = {"unexpected diagnostic": case}
    return document


@pytest.mark.parametrize("repair", (False, True))
def test_diagnostic_report_still_obeys_input_work_bounds(repair):
    current = _fixture("cycle")
    advisory = current["realization"]["selfEvaluation"]
    advisory["cycle"] = advisory
    with pytest.raises(RuntimeError, match="schema-derived work bounds"):
        if repair:
            program_schema.strict_repair_shape_report({"note": "repair", "realizationReplacement": current["realization"]})
        else:
            validate_runtime_program(current)


@pytest.mark.parametrize("advisory", [None, "informal self-check", {"unexpected": []}])
def test_repair_advisory_never_opens_frozen_gameplay(advisory):
    baseline = build_runtime_fixture("workbench_blade")
    current = copy.deepcopy(baseline)
    stats = next(row for row in current["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    stats["params"]["damage"] = "invalid"
    scope = build_runtime_repair_scope(current, validate_runtime_program(current)["errors"])
    correction = next(copy.deepcopy(row) for row in baseline["runtimeProgram"]["calls"] if row["id"] == stats["id"])
    correction["params"]["knockback"] = 19
    patch = {"note": "exact damage only", "callsUpsert": [correction], "realizationReplacement": advisory}
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    result = apply_repair_patch(current, filtered)
    assert result["runtimeProgram"] == baseline["runtimeProgram"]
    assert result["realization"] == advisory
    assert validate_runtime_program(result)["ok"]


@pytest.mark.parametrize("format_mode", ("json_object", "json_schema"))
@pytest.mark.parametrize("runtime_repair", (False, True))
def test_serialized_author_and_repair_preserve_diagnostic_report(monkeypatch, format_mode, runtime_repair):
    def denied(*args, **kwargs):
        raise AssertionError("offline test forbids network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', format_mode)
    monkeypatch.setattr(llm_authoring_pipeline, "USE_LLM", True)
    monkeypatch.setattr(llm_authoring_pipeline, "resolve_llm_model", lambda: "offline-test-model")
    monkeypatch.setattr(llm_authoring_pipeline, "trace_stage_request", lambda *args, **kwargs: None)
    current = _fixture("empty-checks")
    before = copy.deepcopy(current)
    responses = [current]
    if runtime_repair:
        stats = next(row for row in current["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
        correction = copy.deepcopy(stats)
        stats["params"]["damage"] = "invalid"
        responses.append({"note": "repair damage", "callsUpsert": [correction], "realizationReplacement": copy.deepcopy(current["realization"])})
    requests = []

    def provider(request, **kwargs):
        requests.append(copy.deepcopy(request))
        assert responses, "report-only defect must never request another Repair"
        return {"choices": [{"message": {"content": json.dumps(responses.pop(0))}}]}

    monkeypatch.setattr(llm_authoring_pipeline, "llm_chat_json", provider)
    planned = llm_authoring_pipeline.try_llm_plan({}, {}, "plan-report-serialization")
    result = gameplay_stage.compile_and_validate_authored_runtime(
        planned, {}, {}, "plan-report-serialization", run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs),
    )
    assert len(requests) == 1 + runtime_repair and not responses
    assert result["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == int(runtime_repair)
    assert result["realization"] == before["realization"]
    if runtime_repair:
        repair_report = result["debug"]["gameplayRepairStructureValidation"]
        assert repair_report["ok"] and not repair_report["shape"]["ok"]
        assert repair_report["shape"]["errors"]
    report = result["debug"]["lowLevelAuthorValidation"]
    assert report["ok"] and not report["shape"]["ok"]
    assert report["shape"]["errors"] and all(program_schema.is_advisory_path(row["path"]) for row in report["shape"]["errors"])
    expected = compile_runtime_program(before)
    for field in ("runtimeProgram", "gameplay", "accessory", "armor"):
        assert result[field] == expected[field]
    assert generated_parent_summary_from_data(result) == generated_parent_summary_from_data(expected)
    assert validate_runtime_wire(result)["ok"]
