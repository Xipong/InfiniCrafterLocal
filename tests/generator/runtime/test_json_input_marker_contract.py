"""Protocol-only JSON framing at the real provider adapter, without inference."""
from __future__ import annotations

import copy

import infini_local.pipelines.transport.http as transport_http
import pytest
from infini_local.pipelines.transport import client as transport
from infini_local.pipelines.transport import provider_wire as llm_provider_wire

MARKER = {"role": "user", "content": "JSON response."}


def test_nous_mapped_repair_json_mode_has_marker_in_input_not_only_system(monkeypatch):
    packet = llm_provider_wire.with_llm_stage({
        "model": "openai/gpt-6.1-sol",
        "messages": [
            {"role": "system", "name": "vfx_repair_contract", "content": "Gameplay is immutable. Return strict JSON only."},
            {"role": "user", "name": "vfx_repair_context", "content": '{"repairScope":{"fieldPermissions":["color"]},"acceptedItemContext":{"exactFact":14}}'},
        ],
        "response_format": {"type": "json_object"}, "max_tokens": 18000,
        "temperature": 0.12, "reasoning": {"effort": "low", "exclude": True},
    }, "vfx_repair")
    original = copy.deepcopy(packet)
    context = {"provider": "openai_compat", "base_url": "https://inference-api.nousresearch.com/v1",
               "model": packet["model"], "api_mode": "chat_completions", "api_key": ""}
    calls = []

    def sender(url, body, timeout=10, headers=None):
        calls.append((url, copy.deepcopy(body)))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(transport_http, "http_json", sender)
    transport._llm_chat_json_exact_context(packet, 1, context)
    assert len(calls) == 1
    url, wire = calls[0]
    assert url == context["base_url"] + "/chat/completions"
    assert wire["messages"] == [*original["messages"], MARKER]
    assert packet == original


def test_nous_explicit_responses_repair_json_mode_keeps_system_outside_input():
    packet = {"model": "openai/gpt-6-luna", "messages": [
        {"role": "system", "content": "Return strict JSON only."},
        {"role": "user", "content": '{"repairScope":{"fieldPermissions":["color"]}}'},
    ], "response_format": {"type": "json_object"}, "reasoning": {"effort": "medium"},
        "temperature": 0.12, "max_tokens": 18000}
    original = copy.deepcopy(packet)
    context = {"provider": "openai_compat", "base_url": "https://inference-api.nousresearch.com/v1"}
    wire = llm_provider_wire._responses_payload_from_chat(packet, "existing_response", context=context)
    assert wire["input"] == [original["messages"][1], MARKER]
    assert wire["instructions"] == original["messages"][0]["content"]
    assert wire["previous_response_id"] == "existing_response"
    assert wire["text"] == {"format": {"type": "json_object"}}
    assert wire["reasoning"] == {"effort": "medium"}
    assert packet == original


@pytest.mark.parametrize('stage,api_mode,format_mode', [
    ('planner', 'chat_completions', 'json_object'),
    ('planner', 'chat_completions', None),
    ('planner', 'responses', 'json_schema'),
    ('vfx_repair', 'chat_completions', 'json_schema'),
    ('vfx_repair', 'responses', 'json_object'),
    ('vfx_repair', 'responses', None),
])
def test_marker_is_protocol_only_for_ordinary_and_repair_packets(monkeypatch, stage, api_mode, format_mode):
    packet = llm_provider_wire.with_llm_stage({"model": "openai/gpt-6-luna", "messages": [
        {"role": "system", "name": "frozen_contract", "content": "JSON result; preserve every accepted fact."},
        {"role": "user", "name": "frozen_context", "content": '{"exactFact":14,"repairScope":{"fieldPermissions":[]}}'},
    ], "max_tokens": 18000, "temperature": 0.12,
        "reasoning": {"effort": "medium", "exclude": True}}, stage)
    if format_mode is not None:
        packet["response_format"] = {"type": format_mode}
        if format_mode == "json_schema":
            packet["response_format"]["json_schema"] = {"name": "frozen_shape", "strict": True, "schema": {"type": "object"}}
    original = copy.deepcopy(packet)
    context = {"provider": "openai_compat", "base_url": "https://inference-api.nousresearch.com/v1",
               "model": packet["model"], "api_mode": api_mode}
    captured = []

    def sender(url, wire, timeout=10, headers=None):
        captured.append(copy.deepcopy(wire))
        if api_mode == "responses":
            return {"status": "completed", "output_text": "{}"}
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(transport_http, "http_json", sender)
    transport._llm_json_single_context(packet, 1, context)
    assert len(captured) == 1
    wire = captured[0]
    system, user = original["messages"]
    if api_mode == "responses":
        expected_input = [{"role": "user", "content": user["content"]}]
        if format_mode == "json_object":
            expected_input.append(MARKER)
        assert wire["instructions"] == system["content"]
        assert wire["input"] == expected_input
    else:
        expected_messages = [system, user]
        if format_mode == "json_object":
            expected_messages.append(MARKER)
        assert wire["messages"] == expected_messages
    assert packet == original


@pytest.mark.parametrize('api_mode,role,content,present', [
    ('chat_completions', 'user', 'Return Json.', True),
    ('chat_completions', 'developer', 'Return (JSON).', True),
    ('chat_completions', 'assistant', 'JSON', True),
    ('chat_completions', 'user', '{"json":14}', True),
    ('chat_completions', 'user', '{"requiredJsonShape":14}', False),
    ('chat_completions', 'user', 'json_schema', False),
    ('chat_completions', 'user', 'notjson', False),
    ('chat_completions', 'system', 'JSON response.', False),
    ('responses', 'user', 'Return Json.', True),
])
def test_marker_checks_word_in_projected_input_content_only(monkeypatch, api_mode, role, content, present):
    packet = {"model": "openai/gpt-6.1-sol", "messages": [
        {"role": "system", "content": "JSON in instructions does not qualify."},
        {"role": "user", "content": '{"frozenFact":14}'},
        {"role": role, "content": content, "name": "json_name_not_content"},
    ], "response_format": {"type": "json_object"}}
    original = copy.deepcopy(packet)
    context = {"provider": "openai_compat", "base_url": "https://inference-api.nousresearch.com/v1", "model": packet["model"]}
    prepared = transport._payload_for_context(packet, context)
    if api_mode == "responses":
        baseline = llm_provider_wire._responses_payload_from_chat(prepared)
        wire = llm_provider_wire._responses_payload_from_chat(prepared, context=context)
        field = "input"
    else:
        captured = []
        monkeypatch.setattr(transport_http, "http_json", lambda url, body, **kwargs:
                            captured.append(copy.deepcopy(body)) or {"choices": [{"message": {"content": "{}"}}]})
        transport._llm_chat_json_exact_context(packet, 1, context)
        wire, baseline, field = captured[0], prepared, "messages"
    if not present:
        baseline[field].append(MARKER)
    assert wire == baseline
    assert packet == original


@pytest.mark.parametrize("api_mode", ["chat_completions", "responses"])
@pytest.mark.parametrize("provider,base_url,model", [
    ("openai_compat", "https://api.openai.com/v1", "gpt-6.1-sol"),
    ("openai_compat", "https://other.example/v1", "openai/gpt-6.1-sol"),
    ("openai_compat", "https://inference-api.nousresearch.com.evil.example/v1", "openai/gpt-6.1-sol"),
    ("openai_compat", "http://inference-api.nousresearch.com/v1", "openai/gpt-6.1-sol"),
    ("openai_compat", "https://inference-api.nousresearch.com/v1", "other/model"),
    ("openrouter", "https://inference-api.nousresearch.com/v1", "openai/gpt-6.1-sol"),
    ("local", "https://inference-api.nousresearch.com/v1", "openai/gpt-6.1-sol"),
])
def test_other_routes_and_models_retain_exact_wire(monkeypatch, api_mode, provider, base_url, model):
    packet = {"model": model, "messages": [{"role": "system", "content": "JSON response."},
              {"role": "user", "content": '{"exactFact":14}'}], "response_format": {"type": "json_object"}}
    original = copy.deepcopy(packet)
    context = {"provider": provider, "base_url": base_url, "model": model, "api_key": "offline-synthetic-key"}
    prepared = transport._payload_for_context(packet, context)
    if api_mode == "responses":
        assert llm_provider_wire._responses_payload_from_chat(prepared, context=context) == llm_provider_wire._responses_payload_from_chat(prepared)
    else:
        captured = []
        monkeypatch.setattr(transport_http, "http_json", lambda url, body, **kwargs:
                            captured.append(copy.deepcopy(body)) or {"choices": [{"message": {"content": "{}"}}]})
        transport._llm_chat_json_exact_context(packet, 1, context)
        assert captured == [prepared]
    assert packet == original


@pytest.mark.parametrize("content,present", [
    ([{"type": "text", "text": "JSON"}], True),
    ([{"type": "input_text", "text": "Json response."}], True),
    ([{"type": "output_text", "text": "json"}], True),
    ([{"type": "image_url", "text": "JSON", "image_url": {"url": "json"}}], False),
    ([{"type": "text", "text": "requiredJsonShape"}], False),
])
def test_input_marker_handles_text_blocks_idempotently(content, present):
    messages = [{"role": "system", "content": "JSON"}, {"role": "user", "content": content}]
    expected = copy.deepcopy(messages)
    if not present:
        expected.append(MARKER)
    llm_provider_wire._ensure_json_input_marker(messages)
    assert messages == expected
    llm_provider_wire._ensure_json_input_marker(messages)
    assert messages == expected


def test_protocol_marker_preserves_the_provider_cache_key_across_recipe_tails(monkeypatch):
    from infini_local.core.llm_prompt_cache import PROMPT_CACHE_METADATA_KEY

    prefix = '{"shared":"frozen",'
    context = {"provider": "openai_compat", "base_url": "https://inference-api.nousresearch.com/v1",
               "model": "openai/gpt-6.1-sol"}
    captured = []
    monkeypatch.setattr(transport_http, "http_json", lambda url, body, **kwargs:
                        captured.append(copy.deepcopy(body)) or {"choices": [{"message": {"content": "{}"}}]})
    for tail in ('"case":"JSON"}', '"case":"one"}'):
        packet = {
            "model": context["model"],
            "messages": [{"role": "system", "content": "Return a structured result."},
                         {"role": "user", "content": prefix + tail}],
            "response_format": {"type": "json_object"},
            PROMPT_CACHE_METADATA_KEY: {"messageIndex": 1, "prefixChars": len(prefix)},
        }
        before = copy.deepcopy(packet)
        transport._llm_chat_json_exact_context(packet, 1, context)
        assert packet == before
        wire = captured[-1]
        assert wire["messages"][:2] == before["messages"]
        assert wire["response_format"] == {"type": "json_object"}

    already_framed, needs_framing = captured
    assert len(already_framed["messages"]) == 2
    assert len(needs_framing["messages"]) == 3
    marker = needs_framing["messages"][-1]
    assert marker["role"] == "user" and "JSON" in marker["content"].upper()
    key = already_framed["prompt_cache_key"]
    assert key and needs_framing["prompt_cache_key"] == key
