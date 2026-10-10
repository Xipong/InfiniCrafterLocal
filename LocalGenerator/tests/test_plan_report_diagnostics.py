"""Plan comparison formatting never owns gameplay or presentation admission."""
from __future__ import annotations

import copy
import json
import socket

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring import program_schema
from infini_local.core.vfx_manifest import _prompt_packet
from infini_local.pipelines import combine_pipeline, llm_authoring_pipeline
from infini_local.pipelines.combine_validation import authored_item_validation_report
from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


PLAN_PATH = "$.realization.selfEvaluation.planVsProgram"
CASES = ("missing", "null", "scalar", "empty", "empty-checks", "bad-verdict", "bad-row", "foreign-key")


def _damage_plan(document, case):
    evaluation = document["realization"]["selfEvaluation"]
    if case == "missing":
        del evaluation["planVsProgram"]
    elif case in {"null", "scalar", "empty"}:
        evaluation["planVsProgram"] = {"null": None, "scalar": "unstructured diagnostic", "empty": {}}[case]
    elif case == "empty-checks":
        evaluation["planVsProgram"]["actionChecks"] = []
    elif case == "bad-verdict":
        evaluation["planVsProgram"]["verdict"] = "not-an-enum"
    elif case == "bad-row":
        evaluation["planVsProgram"]["actionChecks"][0]["runtimeRefs"] = [0]
    else:
        evaluation["planVsProgram"]["extra.with.dots"] = "diagnostic only"


def _fixture(case):
    document = build_runtime_fixture("workbench_blade")
    document["id"] = "plan-report-control"
    _damage_plan(document, case)
    return document


@pytest.mark.parametrize("case", CASES)
def test_plan_shape_diagnostics_preserve_source_gameplay_description_and_vfx(case):
    baseline = build_runtime_fixture("workbench_blade")
    baseline["id"] = "plan-report-control"
    current = _fixture(case)
    before = copy.deepcopy(current)
    shape = program_schema.strict_author_shape_report(current)
    assert not shape["ok"] and shape["errors"]
    assert all(program_schema.is_plan_report_diagnostic_path(row["path"]) for row in shape["errors"])
    report = authored_item_validation_report(current)
    assert report["ok"] and report["errors"] == []
    assert report["shape"] == shape
    expected, actual = compile_runtime_program(baseline), compile_runtime_program(current)
    for field in ("runtimeProgram", "gameplay", "accessory", "armor", "runtimeContract"):
        assert actual[field] == expected[field]
    assert actual["realization"] == current["realization"]
    for field in ("description", "playerExperience"):
        assert actual["realization"][field] == expected["realization"][field]
    assert actual["realization"]["selfEvaluation"]["programVsReport"] == baseline["realization"]["selfEvaluation"]["programVsReport"]
    assert generated_parent_summary_from_data(actual) == generated_parent_summary_from_data(expected)
    assert _prompt_packet(actual, {}, {}) == _prompt_packet(expected, {}, {})
    assert validate_runtime_wire(actual)["ok"]
    assert current == before


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("failure", ("runtime-shape", "runtime-reference", "program-report", "description", "experience", "container", "nearby-key"))
def test_plan_diagnostics_cannot_hide_other_rejections(case, failure):
    current = _fixture(case)
    if failure == "runtime-shape":
        current["runtimeProgram"]["calls"][0]["fn"] = "unknown_capability"
    elif failure == "runtime-reference":
        current["runtimeProgram"]["primaryEntityId"] = "missing_entity"
    elif failure == "program-report":
        current["realization"]["selfEvaluation"]["programVsReport"]["behaviorChecks"] = []
    elif failure == "description":
        current["realization"]["description"] = 42
    elif failure == "experience":
        current["realization"]["playerExperience"] = None
    elif failure == "container":
        current["realization"]["selfEvaluation"] = None
    else:
        current["realization"]["selfEvaluation"]["planVsProgramExtra"] = {}
    before = copy.deepcopy(current)
    report = authored_item_validation_report(current)
    assert not report["ok"] and report["errors"]
    assert all(not program_schema.is_plan_report_diagnostic_path(row["path"]) for row in report["errors"])
    assert current == before


@pytest.mark.parametrize("repair", (False, True))
def test_diagnostic_report_still_obeys_input_work_bounds(repair):
    current = _fixture("empty")
    plan = current["realization"]["selfEvaluation"]["planVsProgram"]
    plan["cycle"] = plan
    with pytest.raises(RuntimeError, match="schema-derived work bounds"):
        if repair:
            program_schema.strict_repair_shape_report({"note": "repair", "realizationReplacement": current["realization"]})
        else:
            validate_runtime_program(current)


@pytest.mark.parametrize("case", CASES)
def test_repair_report_diagnostics_preserve_scope_and_frozen_fields(case):
    baseline = build_runtime_fixture("workbench_blade")
    current = copy.deepcopy(baseline)
    stats = next(row for row in current["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    stats["params"]["damage"] = "invalid"
    errors = validate_runtime_program(current)["errors"]
    scope = build_runtime_repair_scope(current, errors)
    replacement = next(copy.deepcopy(row) for row in baseline["runtimeProgram"]["calls"] if row["id"] == stats["id"])
    replacement["params"]["knockback"] = 19  # Valid sibling must stay frozen.
    report_document = copy.deepcopy(baseline)
    _damage_plan(report_document, case)
    patch = {"note": "repair exact damage only", "callsUpsert": [replacement],
             "realizationReplacement": report_document["realization"]}
    before = copy.deepcopy((current, patch, scope))
    for validator in (program_schema.strict_repair_structure_report, program_schema.strict_repair_shape_report):
        report = validator(patch)
        assert report["ok"] and report["errors"] == []
        assert not report["shape"]["ok"] and report["shape"]["errors"]
        assert all(program_schema.is_plan_report_diagnostic_path(row["path"], repair=True) for row in report["shape"]["errors"])
    filtered, audit = filter_repair_patch_scope(current, patch, scope)
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    repaired = apply_repair_patch(current, filtered)
    assert repaired["runtimeProgram"] == baseline["runtimeProgram"]
    assert repaired["realization"] == report_document["realization"]
    assert validate_runtime_program(repaired)["ok"]
    assert (current, patch, scope) == before


@pytest.mark.parametrize("failure", ("program-report", "note", "scope"))
def test_many_repair_diagnostics_cannot_hide_a_later_error(failure):
    baseline = build_runtime_fixture("workbench_blade")
    patch = {"note": "repair", "realizationReplacement": copy.deepcopy(baseline["realization"])}
    evaluation = patch["realizationReplacement"]["selfEvaluation"]
    row = copy.deepcopy(evaluation["planVsProgram"]["actionChecks"][0])
    row["runtimeRefs"] = [0] * 16
    evaluation["planVsProgram"]["actionChecks"] = [copy.deepcopy(row) for _ in range(24)]
    if failure == "program-report":
        evaluation["programVsReport"]["behaviorChecks"] = []
    elif failure == "note":
        patch["note"] = 0
    else:
        patch["callsUpsert"] = [copy.deepcopy(baseline["runtimeProgram"]["calls"][0])]
        patch["callsUpsert"][0]["params"]["damage"] = 999
    shape = program_schema.strict_repair_shape_report(patch)
    assert len(shape["shape"]["errors"]) > 128
    if failure == "scope":
        assert shape["ok"]
        scope = build_runtime_repair_scope(baseline, [])
        filtered, audit = filter_repair_patch_scope(baseline, patch, scope)
        assert audit["ok"] and audit["ignoredChanges"]
        repaired = apply_repair_patch(baseline, filtered)
        assert repaired["runtimeProgram"] == baseline["runtimeProgram"]
    else:
        assert not shape["ok"] and shape["errors"]
        assert all(not program_schema.is_plan_report_diagnostic_path(row["path"], repair=True) for row in shape["errors"])
        with pytest.raises(ValueError, match="invalid gameplay repair patch"):
            apply_repair_patch(baseline, patch)


@pytest.mark.parametrize("format_mode", ("json_object", "json_schema"))
@pytest.mark.parametrize("runtime_repair", (False, True))
def test_serialized_author_and_repair_preserve_diagnostic_report(monkeypatch, format_mode, runtime_repair):
    def denied(*args, **kwargs):
        raise AssertionError("offline test forbids network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", format_mode)
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
    planned = llm_authoring_pipeline.try_llm_plan({}, {}, {}, {}, "plan-report-serialization")
    result = combine_pipeline.compile_and_validate_authored_runtime(
        planned, {}, {}, {}, {}, "plan-report-serialization", run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs),
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
    assert report["shape"]["errors"] and all(program_schema.is_plan_report_diagnostic_path(row["path"]) for row in report["shape"]["errors"])
    expected = compile_runtime_program(before)
    for field in ("runtimeProgram", "gameplay", "accessory", "armor"):
        assert result[field] == expected[field]
    assert generated_parent_summary_from_data(result) == generated_parent_summary_from_data(expected)
    assert _prompt_packet(result, {}, {}) == _prompt_packet(expected, {}, {})
    assert validate_runtime_wire(result)["ok"]
