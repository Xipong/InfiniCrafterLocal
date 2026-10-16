"""Advisory prose never owns gameplay acceptance or frozen Repair authority."""
from __future__ import annotations

import copy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch, strict_repair_structure_report
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.gameplay_stage import compile_and_validate_authored_runtime
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.mark.parametrize("report", ["absent", None, {}, "author's informal interpretation", {"description": 42},
                                   {"selfEvaluation": {"programVsReport": {"behaviorChecks": []}}}])
def test_advisory_report_shape_does_not_reject_or_repair_gameplay(monkeypatch, report):
    from infini_local.pipelines import gameplay_stage

    baseline = build_runtime_fixture("workbench_blade")
    source = copy.deepcopy(baseline)
    if report == "absent":
        source.pop("realization")
    else:
        source["realization"] = report
    before = copy.deepcopy(source)

    def forbidden(*args, **kwargs):
        raise AssertionError("report-only differences cannot spend Gameplay Repair")

    monkeypatch.setattr(gameplay_stage, "repair_author_item_after_failure", forbidden)
    actual = compile_and_validate_authored_runtime(source, {}, {}, "advisory-only", run_stage=lambda label, fn, *args, **kwargs: fn(*args, **kwargs))
    expected = compile_runtime_program(baseline)
    for field in ("runtimeProgram", "gameplay", "accessory", "armor"):
        assert actual[field] == expected[field]
    if report == "absent":
        assert "realization" not in actual
    else:
        assert actual["realization"] == report
    assert all(source[key] == value for key, value in before.items())


def test_advisory_errors_cannot_hide_invalid_executable_shape():
    source = build_runtime_fixture("workbench_blade")
    source["realization"] = None
    source["runtimeProgram"]["calls"][0]["fn"] = "unknown_operation"
    report = validate_runtime_program(source)
    assert not report["ok"]
    assert report["errors"]
    assert all(row["path"].startswith("$.runtimeProgram") for row in report["errors"])


def test_repair_accepts_optional_unstructured_advisory_without_runtime_edits():
    source = build_runtime_fixture("workbench_blade")
    patch = {"note": "no executable change", "realizationReplacement": "informal updated report"}
    assert strict_repair_structure_report(patch)["ok"]
    actual = apply_repair_patch(source, patch)
    assert actual["runtimeProgram"] == source["runtimeProgram"]
    assert actual["realization"] == patch["realizationReplacement"]


def test_fresh_pipeline_does_not_manufacture_inert_semantic_knowledge():
    from infini_local.pipelines.final_normalize import final_normalize

    source = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    source["name"] = "Literal Workbench Blade"
    before = copy.deepcopy(source)
    result = final_normalize(source)
    assert "itemKnowledge" not in result
    assert "resultKnowledgeCard" not in result["debug"]
    assert result["gameplay"] == before["gameplay"]
    assert result["category"] == before["category"]


def test_parent_summary_keeps_advisory_text_without_verdict_routing_or_duplicate_runtime_ids():
    from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    source = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    source["id"] = "advisory_parent"
    source["realization"] = {"description": "Literal workbench blade.", "playerExperience": "A deliberate close-range tool.",
                             "selfEvaluation": {"programVsReport": {"behaviorChecks": [
                                 {"result": "aligned", "reportedBehavior": "DO NOT PROMOTE SELF-CHECK INTO FACTS"}]}}}
    summary = generated_parent_summary_from_data(source)
    assert summary == {"schema": "infini.generated-parent-summary.v2", "name": source["name"],
                       "identity": "generated:advisory_parent", "description": "Literal workbench blade.",
                       "playerExperience": "A deliberate close-range tool."}
    source["generatedParentSummary"] = summary
    packet = raw_parent_card_for_llm({"name": source["name"], "generatedData": source})
    assert packet["raw"]["generatedParent"]["summary"] == summary
    assert packet["raw"]["generatedParent"]["runtimeProgram"]
