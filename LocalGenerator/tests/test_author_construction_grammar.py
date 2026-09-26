"""Single-response grammar, distinct from the retained diagnostic self-report."""
import re

from infini_local.pipelines.author_item_contract import (
    author_item_prompt_shape_card, primary_entity_llm_invariant,
)
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request


def test_system_instructs_construction_not_a_private_verification_loop():
    request, _, system = build_initial_author_request({}, {}, {}, {}, "grammar", model_name="test-model")
    assert request["messages"][0]["content"] == system
    assert not re.search(r"\b(verify|review|check)\b|before answering|before returning|reject the draft", system, re.I)
    assert "single" in system.lower() and "JSON" in system
    assert "concept" in system and "selfEvaluation" in system
    assert "diagnostic" in system.lower()


def test_call_grammar_carries_complete_params_and_compatible_reference_obligations():
    shape = author_item_prompt_shape_card()
    call = shape["runtimeProgram"]["calls"][0]
    assert "existing" in call["target"] and "compatible" in call["target"]
    params = str(call["params"])
    assert "non-optional" in params and "conditional" in params
    primary = primary_entity_llm_invariant()
    assert "preEmissionCheck" not in primary
    assert "do not carry role" in primary["primaryRule"]


def test_concept_and_final_diagnostic_fields_remain_the_same_response_shape():
    shape = author_item_prompt_shape_card()
    assert shape["root"] == ["name", "category", "concept", "runtimeProgram", "realization"]
    assert set(shape["concept"]) == {"literalSynthesis", "coreMechanic", "parentAContribution", "parentBContribution", "playerExperience", "plannedPlayerActions"}
    report = shape["realization"]["selfEvaluation"]
    assert set(report) == {"planVsProgram", "programVsReport"}
    assert report["planVsProgram"]["verdict"] == "aligned|changed|uncertain"
    assert report["programVsReport"]["verdict"] == "aligned|mismatch|uncertain"
    for part, rows in (("planVsProgram", "actionChecks"), ("programVsReport", "behaviorChecks")):
        assert {"runtimeRefs", "result", "reason"} <= set(report[part][rows][0])
        assert "uncertain" in report[part][rows][0]["result"]
