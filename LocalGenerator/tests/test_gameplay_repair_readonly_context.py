"""Exact read-only Gameplay Repair facts must survive the real request builder."""
import copy
import json
import socket

import pytest

from infini_local.core.runtime_authoring import validate_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines import llm_transport as transport
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


class _CapturedBeforeTransport(BaseException):
    pass


def _offline_builder(monkeypatch, format_mode, respond):
    def no_network(*args, **kwargs):
        raise AssertionError("network forbidden in read-only Gameplay Repair regression")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    for name, value in {
        "USE_LLM": True, "resolve_llm_model": lambda: "offline-readonly-context",
        "llm_chat_json": respond, "trace_event": lambda *a, **kw: None,
        "trace_stage_request": lambda *a, **kw: None,
        "llm_reasoning_system_suffix": lambda *a, **kw: "",
    }.items():
        monkeypatch.setattr(author, name, value)


def _capture_request(monkeypatch, item, format_mode):
    captured = []

    def stop(request, **kwargs):
        captured.append(copy.deepcopy(request))
        raise _CapturedBeforeTransport()

    _offline_builder(monkeypatch, format_mode, stop)
    before = json.dumps(item, ensure_ascii=False)
    report = validate_runtime_program(item)
    assert not report["ok"]
    with pytest.raises(_CapturedBeforeTransport):
        author.repair_author_item_after_failure(
            item, {}, {}, {}, {}, "offline-readonly-context", failure_report=report)
    assert json.dumps(item, ensure_ascii=False) == before
    assert len(captured) == 1
    assert captured[0]["response_format"]["type"] == format_mode
    return captured[0], json.loads(captured[0]["messages"][1]["content"])


def _call(item, call_id):
    return next(row for row in item["runtimeProgram"]["calls"] if row["id"] == call_id)


def _broken_held_and_deployed():
    item = build_runtime_fixture("held_and_deployed")
    assert validate_runtime_program(item)["ok"]
    _call(item, "held_lantern_pike_life")["params"]["lifetimeTicks"] = 0
    return item


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("changed_fact", ["independent-runtime-interval", "original-concept"])
def test_changed_source_fact_changes_serialized_repair_not_permissions(monkeypatch, format_mode, changed_fact):
    source = _broken_held_and_deployed()
    variant = copy.deepcopy(source)
    if changed_fact == "independent-runtime-interval":
        assert _call(source, "deployed_targeter")["params"]["intervalTicks"] == 45
        _call(variant, "deployed_targeter")["params"]["intervalTicks"] = 60
        field = "runtimeProgram"
    else:
        variant["concept"]["plannedPlayerActions"][0]["intent"] = (
            "OFFLINE CONTROL: another initial intention, not a runtime choice.")
        field = "concept"
    valid_control = copy.deepcopy(variant)
    _call(valid_control, "held_lantern_pike_life")["params"]["lifetimeTicks"] = 30
    assert validate_runtime_program(valid_control)["ok"]
    assert validate_runtime_program(variant) == validate_runtime_program(source)
    baseline, baseline_dossier = _capture_request(monkeypatch, source, format_mode)
    changed, changed_dossier = _capture_request(monkeypatch, variant, format_mode)
    assert baseline_dossier["repairScope"] == changed_dossier["repairScope"]
    assert baseline["response_format"] == changed["response_format"]
    assert baseline["messages"][0] == changed["messages"][0]
    assert baseline["messages"][1]["content"] != changed["messages"][1]["content"], (
        "different source facts are invisible in the real serialized Repair request")
    for item, dossier in ((source, baseline_dossier), (variant, changed_dossier)):
        assert dossier["acceptedItemContext"]["concept"] == item["concept"]
        assert dossier["acceptedItemContext"]["runtimeProgram"] == item["runtimeProgram"]
        assert "concept" not in dossier and "runtimeProgram" not in dossier
        assert list(dossier)[-1] == "requiredJsonShape"
    # Nothing outside the exact read-only source field should react to this change.
    changed_dossier["acceptedItemContext"][field] = baseline_dossier["acceptedItemContext"][field]
    assert changed_dossier == baseline_dossier


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_binding_index_retains_current_nested_policy_in_serialized_request(monkeypatch, format_mode):
    item = _broken_held_and_deployed()
    _, dossier = _capture_request(monkeypatch, item, format_mode)
    assert dossier["immutableProgramIndex"]["bindings"] == item["runtimeProgram"]["bindings"]
    assert all(row["usePolicy"]["action"]["targetId"] for row in dossier["immutableProgramIndex"]["bindings"])


@pytest.mark.parametrize("policy", ["absent", None, {}, {"action": {"kind": None, "targetId": 0}}])
def test_binding_index_never_falls_back_to_legacy_fields_or_materializes_absences(policy):
    from infini_local.core.runtime_authoring import runtime_repair_fragments

    item = _broken_held_and_deployed()
    binding = item["runtimeProgram"]["bindings"][0]
    binding.update(action="legacy_action_must_not_win", target="legacy_target_must_not_win")
    if policy == "absent":
        binding.pop("usePolicy")
    else:
        binding["usePolicy"] = copy.deepcopy(policy)
    before = copy.deepcopy(item)
    index = runtime_repair_fragments(item, {})["immutableIndex"]["bindings"]
    assert index[0] == {key: value for key, value in binding.items() if key in {"id", "input", "usePolicy"}}
    index[0]["usePolicy"] = {"action": "mutation must stay in projection"}
    assert item == before


def test_serialized_report_instructions_distinguish_source_from_permitted_overlay(monkeypatch):
    _, dossier = _capture_request(monkeypatch, _broken_held_and_deployed(), "json_object")
    rules = " ".join(dossier["rules"])
    for required in (
        "acceptedItemContext.concept", "original non-binding intent",
        "acceptedItemContext.runtimeProgram", "pre-repair source", "including invalid fields",
        "only edits admitted by repairScope", "acceptedItemContext.realization", "not execution evidence",
        "interpretation of the exact post-merge program, not an observed run",
    ):
        assert required in rules
    assert "literal post-repair execution report" not in rules


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_readonly_projection_preserves_exact_values_absences_and_is_detached(monkeypatch, format_mode):
    item = _broken_held_and_deployed()
    _call(item, "item_stats")["params"].pop("manaCost")
    item["concept"]["literalSynthesis"] = "  Источник\r\n雪 \\n без нормализации  "
    before = copy.deepcopy(item)
    _, dossier = _capture_request(monkeypatch, item, format_mode)
    for key in ("concept", "runtimeProgram"):
        assert json.dumps(dossier["acceptedItemContext"][key], ensure_ascii=False) == json.dumps(item[key], ensure_ascii=False)
    projected = author.build_gameplay_repair_dossier(item, {}, {}, {}, {}, failure_report=validate_runtime_program(item))
    projected["acceptedItemContext"]["concept"]["plannedPlayerActions"][0]["intent"] = "only in detached view"
    _call(projected["acceptedItemContext"], "held_lantern_pike_life")["params"]["lifetimeTicks"] = 30
    projected["immutableProgramIndex"]["bindings"][0]["usePolicy"]["action"]["targetId"] = "only in detached index"
    assert item == before


@pytest.mark.parametrize("field", ["concept", "runtimeProgram"])
@pytest.mark.parametrize("value", ["absent", None, {}, [], "", False])
def test_readonly_source_never_invents_values_when_source_is_missing_or_malformed(field, value):
    item = _broken_held_and_deployed()
    if value == "absent":
        item.pop(field)
    else:
        item[field] = copy.deepcopy(value)
    before = copy.deepcopy(item)
    dossier = author.build_gameplay_repair_dossier(item, {}, {}, {}, {}, failure_report={"errors": []})
    context = dossier["acceptedItemContext"]
    assert (field in context) == (field in item)
    if field in item:
        assert json.dumps(context[field]) == json.dumps(item[field])
    assert item == before


def _hostile_patch(item):
    """Handwritten offline response: one legal leaf plus unrelated hostile edits."""
    fixed = copy.deepcopy(_call(item, "held_lantern_pike_life"))
    fixed["params"]["lifetimeTicks"] = 30
    targeter = copy.deepcopy(_call(item, "deployed_targeter"))
    targeter["params"]["intervalTicks"] = 90
    stats = copy.deepcopy(_call(item, "item_stats"))
    stats["params"].update(damage=1999, manaCost=77, knockback=17.0)
    binding = copy.deepcopy(item["runtimeProgram"]["bindings"][0])
    binding["usePolicy"]["stackCost"] = 1
    concept = copy.deepcopy(item["concept"])
    concept["coreMechanic"] = "HOSTILE: unrelated concept rewrite"
    replacement = copy.deepcopy(item["realization"])
    replacement["description"] = "Offline hand-authored report replacement; not model or runtime evidence."
    return {
        "note": "OFFLINE synthetic response, not LLM output",
        "callsUpsert": [fixed, targeter, stats], "bindingsUpsert": [binding],
        "metadataPatch": {"concept": concept, "name": "HOSTILE renamed item"},
        "realizationReplacement": replacement,
    }


def _repair_with_response(monkeypatch, item, patch, format_mode):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_repair_response_schema
    from test_codex_subscription_contract import _encode_nullable_fixture

    requests = []

    def respond(request, **kwargs):
        requests.append(copy.deepcopy(request))
        payload = copy.deepcopy(patch)
        if format_mode == "json_schema":
            payload = _encode_nullable_fixture(payload, author_item_repair_response_schema())
            Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(payload)
        return {"choices": [{"message": {"content": json.dumps(payload)}}],
                "_debug": {"responseFormatType": format_mode}}

    _offline_builder(monkeypatch, format_mode, respond)
    repaired = author.repair_author_item_after_failure(
        item, {}, {}, {}, {}, "offline-readonly-context", failure_report=validate_runtime_program(item))
    assert len(requests) == 1
    return repaired, requests[0]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_visible_independent_facts_grant_no_edits_through_real_repair(monkeypatch, format_mode):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope

    item = _broken_held_and_deployed()
    _call(item, "item_stats")["params"].pop("manaCost")
    before = json.dumps(item, ensure_ascii=False)
    scope = build_runtime_repair_scope(item, validate_runtime_program(item)["errors"])
    assert scope["fieldPermissions"]["calls"] == [
        {"id": "held_lantern_pike_life", "paths": ["params.lifetimeTicks"]}]
    incoming = _hostile_patch(item)
    repaired, request = _repair_with_response(monkeypatch, item, incoming, format_mode)
    dossier = json.loads(request["messages"][1]["content"])
    assert dossier["acceptedItemContext"]["runtimeProgram"] == item["runtimeProgram"]
    assert dossier["repairScope"] == scope
    assert repaired["debug"]["gameplayRepairScope"] == scope
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert audit["ok"] and audit["ignoredChanges"]
    assert any(row["reason"] == "independent_valid_node_frozen" for row in audit["ignoredChanges"])
    expected = copy.deepcopy(item)
    _call(expected, "held_lantern_pike_life")["params"]["lifetimeTicks"] = 30
    expected["realization"] = copy.deepcopy(incoming["realizationReplacement"])
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert "manaCost" not in _call(repaired, "item_stats")["params"]
    assert validate_runtime_program(repaired)["ok"]
    assert json.dumps(item, ensure_ascii=False) == before


@pytest.mark.parametrize("context_key", ["acceptedItemContext", "concept", "runtimeProgram", "immutableProgramIndex"])
def test_readonly_context_is_not_an_output_schema_extension(context_key):
    from infini_local.core.runtime_authoring.program_schema import strict_repair_structure_report

    item = _broken_held_and_deployed()
    patch = {"note": "offline schema control", "realizationReplacement": item["realization"]}
    assert strict_repair_structure_report(patch)["ok"]
    patch[context_key] = {}
    assert not strict_repair_structure_report(patch)["ok"]
