"""Finite report bounds preserve authored prose and never change gameplay."""
from __future__ import annotations

import copy
import json

import jsonschema
import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_program,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.program_schema import (
    strict_author_shape_report,
    strict_repair_shape_report,
)
from infini_local.pipelines.author_item_contract import (
    apply_author_item_repair_patch,
    author_item_provider_repair_response_schema,
    author_item_provider_response_schema,
    author_item_response_schema,
    normalize_author_item_targeted_repair_delta_text_limits,
)
from infini_local.pipelines import llm_authoring_pipeline as pipeline
from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.storage.world_storage import atomic_write_json, sanitize_recipe_for_delivery


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
    jsonschema.validate(prepared["realization"], author_item_provider_response_schema()["properties"]["realization"])
    patch = {"note": "Replace only the report", "realizationReplacement": copy.deepcopy(item["realization"])}
    patch_before = copy.deepcopy(patch)
    assert strict_repair_shape_report(patch)["ok"]
    jsonschema.validate(patch["realizationReplacement"], author_item_provider_repair_response_schema()["properties"]["realizationReplacement"])
    normalized = normalize_author_item_targeted_repair_delta_text_limits(patch)
    assert normalized == patch_before
    repaired = apply_author_item_repair_patch(build_runtime_fixture("workbench_blade"), normalized)
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
    # Existing summary whitespace normalization is not a prose length limit.
    assert summary[field] == before["realization"][field].strip()
    recursive = raw_parent_card_for_llm({"generatedData": stored})
    assert recursive["raw"]["generatedParent"]["summary"][field] == summary[field]
    assert item == before and patch == patch_before


@pytest.mark.parametrize("mode", ["json_object", "off"])
def test_actual_author_and_repair_packets_disclose_schema_owned_report_bounds(monkeypatch, mode):
    from infini_local.core.runtime_authoring import program_schema
    from infini_local.pipelines import llm_transport

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
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
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
    author, _, _ = pipeline.build_initial_author_request({}, {}, {}, {}, "report-card", model_name="offline-report-test")
    result = pipeline.repair_author_item_after_failure(item, {}, {}, {}, {}, "report-card", failure_report={"errors": []})
    repair = requests[0]
    expected_format = {"type": "json_object"} if mode == "json_object" else None
    for request, root in ((author, "realization"), (repair, "realizationReplacement")):
        assert request.get("response_format") == expected_format
        card = json.loads(request["messages"][1]["content"])["requiredJsonShape"][root]
        for field, schema in author_item_response_schema()["properties"]["realization"]["properties"].items():
            if field == "selfEvaluation":
                continue
            text = card[field]
            assert f"minLength={schema['minLength']}" in text, (root, field, text)
            assert f"maxLength={schema['maxLength']}" in text, (root, field, text)
            assert "Unicode code points" in text
            assert ("final interpretation" if field == "description" else "executable program") in text
    assert result["runtimeProgram"] == before["runtimeProgram"]
    assert result["realization"] == before["realization"] and item == before


@pytest.mark.parametrize("field,maximum,old_maximum", [("description", 4000, 700), ("playerExperience", 3000, 500)])
@pytest.mark.parametrize("size", [0, 1, "old-bound", "old-plus-one", "maximum-plus-one"])
def test_report_bounds_remain_finite_nonempty_and_preserve_legacy_values(field, maximum, old_maximum, size):
    length = {"old-bound": old_maximum, "old-plus-one": old_maximum + 1, "maximum-plus-one": maximum + 1}.get(size, size)
    item = build_runtime_fixture("workbench_blade")
    item["realization"][field] = "я" * length
    patch = {"note": "Report boundary control", "realizationReplacement": copy.deepcopy(item["realization"])}
    before = copy.deepcopy((item, patch))
    expected_kind = "min_length" if length == 0 else ("max_length" if length > maximum else None)
    author = strict_author_shape_report(item)
    repair = strict_repair_shape_report(patch)
    for report, root in ((author, "realization"), (repair, "realizationReplacement")):
        assert report["ok"] is (expected_kind is None)
        assert report["errors"] == ([] if expected_kind is None else [{
            "path": f"$.{root}.{field}", "kind": expected_kind,
            "expected": 1 if length == 0 else maximum, "actual": length,
        }])
    assert normalize_author_item_targeted_repair_delta_text_limits(patch) == patch
    assert (item, patch) == before


def test_maximal_report_tail_and_runtime_shape_fit_schema_derived_work_guard():
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, program_schema
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
    sections = report_schema["selfEvaluation"]["properties"]
    for section, rows in (("planVsProgram", "actionChecks"), ("programVsReport", "behaviorChecks")):
        properties = sections[section]["properties"]
        item["realization"]["selfEvaluation"][section]["summary"] = "я" * properties["summary"]["maxLength"]
        row = copy.deepcopy(item["realization"]["selfEvaluation"][section][rows][0])
        row_schema = properties[rows]["items"]["properties"]
        for field, child in row_schema.items():
            if field == "runtimeRefs":
                row[field] = ["r" * child["items"]["maxLength"]] * child["maxItems"]
            elif "maxLength" in child:
                row[field] = "я" * child["maxLength"]
        item["realization"]["selfEvaluation"][section][rows] = [copy.deepcopy(row) for _ in range(properties[rows]["maxItems"])]
    actions = schema["properties"]["concept"]["properties"]["plannedPlayerActions"]
    item["concept"]["plannedPlayerActions"] = [{"input": "primary_use", "intent": "я" * actions["items"]["properties"]["intent"]["maxLength"]} for _ in range(actions["maxItems"])]
    item = {key: item[key] for key in schema["properties"]}
    # Repeated singleton components make this shape-only, not valid gameplay.
    assert program_schema.strict_author_shape_report(item)["ok"]
    provider = author_item_provider_response_schema()
    jsonschema.Draft202012Validator(provider).validate(item)
    candidate, _ = program_schema.assert_bounded_author_input(item, schema=provider, authored_only=False)
    assert candidate == item
    item["realization"]["selfEvaluation"]["programVsReport"]["behaviorChecks"][-1]["runtimeRefs"][-1] = 0
    errors = program_schema.strict_author_shape_report(item)["errors"]
    assert len(errors) == 1 and errors[0]["kind"] == "type"
    checks = item["realization"]["selfEvaluation"]["programVsReport"]["behaviorChecks"]
    assert errors[0]["path"] == f"$.realization.selfEvaluation.programVsReport.behaviorChecks[{len(checks) - 1}].runtimeRefs[{len(checks[-1]['runtimeRefs']) - 1}]"
