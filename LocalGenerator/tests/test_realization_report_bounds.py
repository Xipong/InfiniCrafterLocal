"""Finite report bounds preserve authored prose and never change gameplay."""
from __future__ import annotations

from prompt_packet_helpers import request_dossier

import copy
import json

import jsonschema
import pytest

from infini_local.core import llm_config
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.program_schema import (
    apply_repair_patch,
    strict_author_shape_report,
    strict_repair_shape_report,
)
from infini_local.pipelines.author_item_contract import (
    author_item_provider_response_schema,
    author_item_response_schema,
)
from infini_local.pipelines import llm_authoring_pipeline as pipeline
from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture as _runtime_fixture
from infini_local.storage.world_storage import atomic_write_json, sanitize_recipe_for_delivery


def build_runtime_fixture(name):
    item = _runtime_fixture(name)
    item["realization"]["selfEvaluation"] = "Optional self-check, not observed execution."
    return item


@pytest.mark.parametrize("length,accepted", [(80, True), (81, False)])
def test_fresh_item_name_has_80_unicode_character_boundary(length, accepted):
    from infini_local.pipelines.gameplay_stage import authored_item_validation_report

    item = build_runtime_fixture("workbench_blade")
    item["name"] = "🌟" * length
    before = copy.deepcopy(item)
    assert strict_author_shape_report(item)["ok"] is accepted
    assert authored_item_validation_report(item)["ok"] is accepted
    if accepted:
        from infini_local.pipelines.final_normalize import final_normalize
        assert final_normalize(compile_runtime_program(copy.deepcopy(item)))["name"] == before["name"]
    assert item == before


def test_descriptive_contribution_and_behavior_reports_survive_recursive_handoff():
    item = build_runtime_fixture("workbench_blade")
    item["id"] = "descriptive_report_fixture"
    prose = "🌟" * 600
    item["concept"]["parentAContribution"] = prose
    item["concept"]["parentBContribution"] = prose
    item["realization"]["selfEvaluation"] = prose
    before = copy.deepcopy(item)
    assert strict_author_shape_report(item)["ok"]
    compiled = compile_runtime_program(item)
    compiled["generatedParentSummary"] = generated_parent_summary_from_data(compiled)
    delivered = sanitize_recipe_for_delivery(compiled)
    assert "notableEffects" not in delivered["generatedParentSummary"]
    assert delivered["realization"]["selfEvaluation"] == prose
    assert delivered["realization"] == before["realization"]
    assert delivered["concept"] == before["concept"]
    assert item == before


@pytest.mark.parametrize("field,maximum", [("description", 4000), ("playerExperience", 3000)])
def test_expanded_report_boundary_survives_author_repair_and_python_delivery(tmp_path, field, maximum):
    item = build_runtime_fixture("workbench_blade")
    item["id"] = "report_bounds_fixture"
    compiled_before = compile_runtime_program(item)
    item["realization"][field] = ("Ж🌟\r\n" * maximum)[:maximum]
    before = copy.deepcopy(item)
    prepared = pipeline._prepare_parsed_author_item(item)
    report = validate_runtime_program(prepared)
    assert report["ok"], report["errors"]
    assert strict_author_shape_report(prepared)["ok"]
    jsonschema.validate(prepared["realization"], author_item_response_schema()["properties"]["realization"])
    patch = {"note": "Replace only the report", "realizationReplacement": copy.deepcopy(item["realization"])}
    patch_before = copy.deepcopy(patch)
    assert strict_repair_shape_report(patch)["ok"]
    jsonschema.validate(patch["realizationReplacement"], author_item_response_schema()["properties"]["realization"])
    repaired = apply_repair_patch(build_runtime_fixture("workbench_blade"), patch)
    assert repaired["realization"] == before["realization"]
    assert repaired["runtimeProgram"] == before["runtimeProgram"]
    compiled = compile_runtime_program(prepared)
    assert validate_runtime_wire(compiled)["ok"]
    for key in ("runtimeProgram", "gameplay", "accessory", "armor"):
        assert compiled[key] == compiled_before[key]
    assert compiled["realization"] == before["realization"]
    compiled["generatedParentSummary"] = generated_parent_summary_from_data(compiled)
    delivered = sanitize_recipe_for_delivery(compiled)
    path = tmp_path / "report.json"
    atomic_write_json(path, delivered)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["realization"] == before["realization"]
    summary = stored["generatedParentSummary"]
    assert summary[field] == before["realization"][field]
    recursive = raw_parent_card_for_llm({"generatedData": stored})
    assert recursive["raw"]["generatedParent"]["summary"][field] == summary[field]
    assert item == before and patch == patch_before


@pytest.mark.parametrize("mode", ["json_object", "off"])
def test_actual_author_and_repair_packets_disclose_schema_owned_report_bounds(monkeypatch, mode):
    import infini_local.core.runtime_authoring.program_schema as program_schema

    canonical = program_schema.realization_schema

    def changed_report_schema():
        schema = canonical()
        for field in ("description", "playerExperience"):
            schema["properties"][field]["minLength"] = 2
            schema["properties"][field]["maxLength"] += 17
        return schema

    # A changed schema fact must reach the actual consumers: matching copies of
    # hard-coded prompt numbers would pass a plain equality test but fail this.
    monkeypatch.setattr(program_schema, "realization_schema", changed_report_schema)
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-report-test")
    item = build_runtime_fixture("workbench_blade")
    for field in ("description", "playerExperience"):
        item["realization"][field] = "🌟" * canonical()["properties"][field]["maxLength"]
    before = copy.deepcopy(item)
    requests = []

    def respond(request, **kwargs):
        requests.append(copy.deepcopy(request))
        patch = {"note": "Refresh only the report", "realizationReplacement": copy.deepcopy(item["realization"])}
        return {"choices": [{"message": {"content": json.dumps(patch)}}]}

    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    monkeypatch.setattr(pipeline, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "trace_stage_request", lambda *args, **kwargs: None)
    author, _, _ = pipeline.build_initial_author_request({}, {}, "report-card", model_name="offline-report-test")
    result = pipeline.repair_author_item_after_failure(item, {}, {}, "report-card", failure_report={"errors": []})
    repair = requests[0]
    expected_format = {"type": "json_object"} if mode == "json_object" else None
    for request, root in ((author, "realization"), (repair, "realizationReplacement")):
        assert request.get("response_format") == expected_format
        card = request_dossier(request)["requiredJsonShape"][root]
        for field, schema in author_item_response_schema()["properties"]["realization"]["properties"].items():
            if field == "selfEvaluation":
                continue
            text = card[field]
            assert f"minLength={schema['minLength']}" in text, (root, field, text)
            assert f"maxLength={schema['maxLength']}" in text, (root, field, text)
            assert "Unicode code points" in text
            assert "optional advisory" in text
    assert result["runtimeProgram"] == before["runtimeProgram"]
    assert result["realization"] == before["realization"] and item == before


@pytest.mark.parametrize("field,maximum", [("description", 4000), ("playerExperience", 3000)])
@pytest.mark.parametrize("size", [0, 1, 5000])
def test_report_guidance_does_not_reject_empty_or_long_advisory_text(field, maximum, size):
    item = build_runtime_fixture("workbench_blade")
    item["realization"][field] = "я" * size
    patch = {"note": "Optional report", "realizationReplacement": copy.deepcopy(item["realization"])}
    before = copy.deepcopy((item, patch))
    assert validate_runtime_program(item)["ok"]
    assert strict_repair_shape_report(patch)["ok"]
    assert apply_repair_patch(item, patch)["realization"] == item["realization"]
    assert (item, patch) == before


def test_maximal_report_tail_and_runtime_shape_fit_schema_derived_work_guard():
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    import infini_local.core.runtime_authoring.program_schema as program_schema
    from infini_local.qa.capability_witnesses import build_capability_witness

    schema = program_schema.author_item_response_schema()
    runtime = schema["properties"]["runtimeProgram"]["properties"]
    worst = max(runtime["calls"]["items"]["oneOf"], key=lambda branch: len(branch["properties"].get("params", {}).get("properties", {})))
    fn = worst["properties"]["fn"]["const"]
    item = build_capability_witness(fn)
    call = next(row for row in item["runtimeProgram"]["calls"] if row["fn"] == fn)
    for key, spec in CAPABILITY_REGISTRY[fn].params.items():
        if key not in call["params"]:
            call["params"][key] = ({child: leaf.enum[0] if leaf.enum else leaf.neutral for child, leaf in spec.properties.items()}
                                   if spec.properties else spec.enum[0] if spec.enum else spec.neutral)
    for name, source in (("calls", call), ("entities", item["runtimeProgram"]["entities"][0]), ("bindings", item["runtimeProgram"]["bindings"][0])):
        item["runtimeProgram"][name] = [dict(copy.deepcopy(source), id=f"max_{name}_{index}") for index in range(runtime[name]["maxItems"])]
    report_schema = schema["properties"]["realization"]["properties"]
    for field in ("description", "playerExperience"):
        item["realization"][field] = "🌟" * report_schema[field]["maxLength"]
    item["realization"]["selfEvaluation"] = "я" * report_schema["selfEvaluation"]["maxLength"]
    actions = schema["properties"]["concept"]["properties"]["plannedPlayerActions"]
    item["concept"]["plannedPlayerActions"] = [{"input": "primary_use", "intent": "я" * actions["items"]["properties"]["intent"]["maxLength"]} for _ in range(actions["maxItems"])]
    item = {key: item[key] for key in schema["properties"]}
    # Repeated singleton components make this shape-only, not valid gameplay.
    assert program_schema.strict_author_shape_report(item)["ok"]
    provider = author_item_provider_response_schema()
    from test_codex_subscription_contract import _encode_nullable_fixture

    # Provider required+nullable scaffolding is not the sparse local Author shape.
    encoded = _encode_nullable_fixture(copy.deepcopy(item), schema)
    jsonschema.Draft202012Validator(provider).validate(encoded)
    candidate, _ = program_schema.assert_bounded_author_input(encoded, schema=provider, authored_only=False)
    assert candidate == encoded
    item["runtimeProgram"]["calls"][-1]["fn"] = "unknown_operation"
    assert not validate_runtime_program(item)["ok"]
