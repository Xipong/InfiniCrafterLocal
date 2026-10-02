"""Provider request semantics: reasoning, schema diagnosis, cache identity, JSON."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
import urllib.error

import pytest

from infini_local.core.llm_json_tools import json_object_candidates, parse_first_valid_llm_json, recover_object_with_syntax_only_repairs
from infini_local.core.llm_prompt_cache import json_prefix_chars, with_prompt_cache_prefix
from infini_local.desktop import settings_schema
from infini_local.pipelines import llm_transport as llm
from test_provider_transport_contract import http_error, packet, wire

GOOGLE = "https://generativelanguage.googleapis.com/v1beta/openai"


def cache_packet(suffix='{"recipeKey":"one"}'):
    return {"messages": [{"role": "system", "content": "Shared rules"},
        {"role": "user", "content": '{"catalog":[], ' + suffix}], "response_format": {"type": "json_object"}}


@pytest.mark.parametrize("provider,base,model,mode,effort,source", [
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "auto", "medium", "options", id="google-auto"),
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "xhigh", "high", "options", id="google-xhigh"),
    pytest.param("openai_compat", GOOGLE, "gemma-4-31b-it", "minimal", "minimal", "options", id="google-gemma-minimal"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "google/gemini-3.1-flash-lite", "medium", "medium", "options", id="router-envelope"),
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "medium", "medium", "envelope", id="fallback-to-google"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "google/gemini-3.1-flash-lite", "medium", "medium", "native", id="fallback-to-router"),
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "medium", "medium", "local-intent", id="local-to-remote-intent"),
])
def test_reasoning_control_is_native_to_the_selected_context(monkeypatch, provider, base, model, mode, effort, source):
    context = {"provider": provider, "base_url": base, "model": model}
    local = {"provider": "local", "base_url": "http://127.0.0.1:1234/v1", "model": "local-model"}
    default = local if source == "local-intent" else context
    monkeypatch.setattr(llm, "LLM_REASONING_MODE", mode)
    monkeypatch.setattr(llm, "resolve_llm_model", lambda context=None: (context or default)["model"])
    monkeypatch.setattr(llm, "active_llm_provider", lambda context=None: (context or default)["provider"])
    monkeypatch.setattr(llm, "llm_base_url", lambda context=None: (context or default)["base_url"])
    if source in {"options", "local-intent"}:
        request = llm.apply_llm_common_options({}, model_name=default["model"])
    else:
        request = {"reasoning": {"effort": effort, "exclude": True}} if source == "envelope" else {"reasoning_effort": effort}
    before = copy.deepcopy(request)
    prepared = llm._payload_for_context(request, context)
    if base == GOOGLE:
        assert prepared["reasoning_effort"] == effort and "reasoning" not in prepared
    else:
        assert prepared["reasoning"] == {"effort": effort, "exclude": llm.LLM_REASONING_EXCLUDE}
        assert "reasoning_effort" not in prepared
    assert request == before and all(not key.startswith("_infini_") for key in prepared)
    if source == "local-intent":
        local_payload = llm._payload_for_context(request, local)
        assert "reasoning" not in local_payload and "reasoning_effort" not in local_payload
        assert all(not key.startswith("_infini_") for key in local_payload)


@pytest.mark.parametrize("provider,base,budget,effort,expected,native", [
    pytest.param("openai_compat", GOOGLE, budget, "high", expected, True, id=f"google-high-{budget}")
    for budget, expected in ((4000, 8000), (12000, 24000), (40000, 64000))
] + [
    pytest.param("openai_compat", GOOGLE, 4000, "medium", 4000, True, id="google-medium"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", 4000, "high", 4000, False, id="router-no-headroom"),
] + [
    pytest.param("openai_compat", base, 4000, "high", 4000, False, id=label)
    for label, base in [("spoof-path", "https://proxy.example/generativelanguage.googleapis.com/v1"),
        ("spoof-userinfo", "https://generativelanguage.googleapis.com@proxy.example/v1"),
        ("malformed-port", "https://generativelanguage.googleapis.com:badport/v1")]
])
def test_reasoning_headroom_preserves_answer_budget_only_for_actual_google(monkeypatch, provider, base, budget, effort, expected, native):
    context = {"provider": provider, "base_url": base, "model": "gemini-3.5-flash-lite"}
    monkeypatch.setattr(llm, "resolve_llm_model", lambda context=None: (context or {})["model"])
    monkeypatch.setattr(llm, "active_llm_provider", lambda context=None: (context or {})["provider"])
    monkeypatch.setattr(llm, "llm_base_url", lambda context=None: (context or {})["base_url"])
    request = {"max_tokens": budget, "reasoning_effort": effort}
    prepared = llm._payload_for_context(request, context)
    assert request == {"max_tokens": budget, "reasoning_effort": effort}
    assert prepared["max_tokens"] == expected
    if native:
        assert prepared["reasoning_effort"] == effort
    else:
        assert "reasoning_effort" not in prepared and prepared["reasoning"]["effort"] == effort


@pytest.mark.parametrize("initial,expected", [("off", "medium"), ("high", "high")])
def test_author_reasoning_floor_does_not_lower_explicit_high(monkeypatch, initial, expected):
    monkeypatch.setattr(llm, "active_llm_provider", lambda context=None: "openai_compat")
    monkeypatch.setattr(llm, "llm_base_url", lambda context=None: GOOGLE)
    monkeypatch.setattr(llm, "LLM_REASONING_MODE", initial)
    request = llm.apply_llm_common_options({}, model_name="gemini-3.5-flash-lite") if initial == "off" else {"reasoning_effort": "high"}
    assert llm.apply_minimum_reasoning_effort(request, model_name="gemini-3.5-flash-lite", minimum="medium")["reasoning_effort"] == expected


@pytest.mark.parametrize("failure,format_type,expected", [
    pytest.param(400, "json_schema", True, id="schema-400"),
    pytest.param(400, "json_object", False, id="object-400"),
    pytest.param(400, None, False, id="absent-format-400"),
    *[pytest.param(code, "json_schema", False, id=f"unrelated-{code}") for code in (401, 403, 404, 429, 500, 503)],
    pytest.param("timeout", "json_schema", False, id="transport-timeout"),
])
def test_request_shape_diagnosis_is_pure_and_status_specific(failure, format_type, expected):
    context = {"provider": "openai_compat", "base_url": GOOGLE, "model": "gemini-3.5-flash-lite", "api_mode": "responses", "profile_id": "llm_1", "label": "llm_1"}
    request = packet(schema=format_type == "json_schema")
    if format_type is None:
        request.pop("response_format")
    before = copy.deepcopy(request)
    error = TimeoutError("timed out") if failure == "timeout" else http_error(GOOGLE + "/chat/completions", failure, '{"error":{"code":400,"status":"INVALID_ARGUMENT"}}')
    if isinstance(error, urllib.error.HTTPError):
        error._infini_body = '{"error":{"code":400,"status":"INVALID_ARGUMENT"}}'
    diagnosis = llm.request_shape_rejection_diagnosis(error, request, context)
    assert llm._strict_schema_rejected(error, request) is expected
    assert request == before
    if not expected:
        assert diagnosis is None
    else:
        assert isinstance(diagnosis, dict)
        assert (diagnosis["code"], diagnosis["status"], diagnosis["sentResponseFormat"]) == ("provider_rejected_request_shape", 400, "json_schema")
        assert diagnosis["knownWorkingResponseFormat"] == "json_object" and diagnosis["knownWorkingApiMode"] == "chat_completions"
        assert diagnosis["schemaChars"] > 0 and "INVALID_ARGUMENT" in diagnosis["providerBody"]
        assert "response_format" not in diagnosis and isinstance(diagnosis["knownWorkingResponseFormat"], str)
        for text in ("json_object", "chat_completions", "INFINI_LLM_RESPONSE_FORMAT", "INFINI_LLM_API_MODE", "не получила задание"):
            assert text in diagnosis["hint"]  # Operator copy is the contract on this surface.


@pytest.mark.parametrize("failure,format_type,budget,success", [
    pytest.param(400, "json_schema", 2, True, id="schema-envelope-recovery"),
    pytest.param(400, "json_schema", 2, False, id="persistent-schema-400"),
    pytest.param(429, "json_schema", 2, False, id="429-not-schema"),
    pytest.param(400, "json_object", 1, False, id="one-attempt-no-inner-retry"),
])
def test_transport_schema_recovery_changes_only_envelope_and_is_bounded(wire, monkeypatch, failure, format_type, budget, success):
    wire.configure(LLM_PROVIDER="openai_compat", OPENAI_COMPAT_BASE_URL=GOOGLE, OPENAI_COMPAT_MODEL="gemini-3.5-flash-lite",
                   LLM_API_MODE="chat_completions", LLM_FALLBACK_NETWORK_FAILS=budget)
    events = []
    monkeypatch.setattr(llm, "log_event", lambda level, message, data=None: events.append((level, message, data or {})))
    request = packet(schema=format_type == "json_schema")
    before = copy.deepcopy(request)
    # Pure normalization proof, independently of what the transport sends.
    relaxed = llm._payload_without_strict_schema(request)
    assert relaxed == {**request, "response_format": {"type": "json_object"}}
    assert request == before
    wire.replies.extend([failure] if success else [failure, failure])
    context = llm._primary_llm_context()
    if success:
        result = llm._llm_chat_json_single_context(request, 60, context)
        assert result["choices"][0]["message"]["content"] == "{}"
        assert result["_debug"]["strictSchemaDowngraded"] is True and result["_debug"]["responseFormatType"] == "json_object"
        assert len(wire.calls) == 2
        first, second = wire.calls[0][1], wire.calls[1][1]
        assert first["response_format"]["type"] == "json_schema" and second["response_format"] == {"type": "json_object"}
        assert second == {**first, "response_format": {"type": "json_object"}}
        downgrade = [data for _, message, data in events if "json_object" in message]
        assert downgrade and downgrade[0]["was"] == "json_schema" and downgrade[0]["now"] == "json_object"
        assert "config.env" in downgrade[0]["repairedFor"] and "INFINI_LLM_RESPONSE_FORMAT=json_object" in downgrade[0]["detail"]
        wire.calls.clear()
        again = llm._llm_chat_json_single_context(request, 60, context)
        assert again["_debug"]["strictSchemaDowngraded"] is True
        assert len(wire.calls) == 1 and wire.calls[0][1]["response_format"] == {"type": "json_object"}
    else:
        with pytest.raises(urllib.error.HTTPError) as caught:
            llm._llm_chat_json_single_context(request, 60, context)
        assert caught.value.code == failure
        assert len(wire.calls) == (2 if failure == 400 and format_type == "json_schema" else 1)
        if budget == 1:
            assert wire.calls[0][1]["response_format"] == {"type": "json_object"}
    assert request == before


def test_shape_rejection_reaches_actual_author_failure_with_operator_diagnosis(wire, monkeypatch):
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.core.errors import PlannerUnavailable
    wire.configure(OPENROUTER_PROVIDER="", LLM_PROVIDER="openai_compat", OPENAI_COMPAT_BASE_URL=GOOGLE,
                   OPENAI_COMPAT_MODEL="gemini-3.5-flash-lite", LLM_API_MODE="chat_completions")
    wire.replies.extend([400, 400])
    request = packet(schema=True)
    events, logs = [], []
    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(author, "resolve_llm_model", lambda: "gemini-3.5-flash-lite")
    monkeypatch.setattr(author, "build_initial_author_request", lambda *_a, **_k: (request, "literal task", "literal rules"))
    # Connect the real exact-wire rejection owner to the real Author consumer;
    # schema negotiation (including a second, unrelated rejection) is tested above.
    monkeypatch.setattr(author, "llm_chat_json", lambda payload, timeout: llm._llm_chat_json_exact_context(payload, timeout, llm._primary_llm_context()))
    monkeypatch.setattr(author, "trace_event", lambda *args, **kw: events.append(args))
    monkeypatch.setattr(llm, "log_event", lambda level, message, data=None: logs.append((message, data)))
    with pytest.raises(PlannerUnavailable) as caught:
        author.try_llm_plan({}, {}, {}, {}, "shape-owner")
    cause = caught.value.__cause__
    assert isinstance(cause, urllib.error.HTTPError)
    diagnosis = cause._infini_shape_diagnosis
    assert diagnosis["hint"] in str(caught.value)
    assert any(args[3].get("requestShapeRejection") == diagnosis for args in events)
    assert any(message == "LLM provider rejected the configured request shape" and all(data.get(key) == value for key, value in diagnosis.items()) for message, data in logs)
    assert "request_shape_rejection_diagnosis" in llm.__all__ and callable(llm.request_shape_rejection_diagnosis)


@pytest.mark.parametrize("failure", ["http-400", "malformed-content"])
def test_single_attempt_local_request_has_no_negotiation_or_content_retry(wire, failure):
    wire.configure(LLM_PROVIDER="local", LLM_FALLBACK_NETWORK_FAILS=1, LLM_FALLBACK_MODEL="")
    wire.replies.append(400 if failure == "http-400" else {"choices": [{"finish_reason": "stop", "message": {"content": '{"broken":'}}]})
    request = {"messages": [], "model": "ignored", "response_format": {"type": "json_object"}, "reasoning": {"effort": "low"}}
    if failure == "http-400":
        with pytest.raises(urllib.error.HTTPError) as caught:
            llm.llm_chat_json(request, timeout=1)
        assert caught.value.code == 400
    else:
        result = llm.llm_chat_json(request, timeout=1)
        assert result["choices"][0]["message"]["content"] == '{"broken":'
        assert "transportRetryCount" not in result.get("_debug", {})
    assert len(wire.calls) == 1
    url, body, headers = wire.calls[0]
    assert url == "http://primary.local:1234/v1/chat/completions"
    assert body == {"messages": [], "model": "primary-local", "response_format": {"type": "json_object"}}


@pytest.mark.parametrize("key,default", [
    ("INFINI_LLM_FALLBACK_PROVIDER", None), ("INFINI_LLM_FALLBACK_MODEL", ""),
    ("INFINI_LLM_FALLBACK_BASE_URL", None), ("INFINI_LLM_FALLBACK_API_KEY", None),
    ("INFINI_LLM_FALLBACK_NETWORK_FAILS", "2"),
])
def test_fallback_configuration_fields_have_owned_defaults(key, default):
    assert key in settings_schema.FIELD_ORDER and key in settings_schema.DEFAULTS
    if default is not None:
        assert settings_schema.DEFAULTS[key] == default


@pytest.mark.parametrize("keys,expected", [
    pytest.param(["catalog", "rules"], len('{"catalog":"рецепт","rules":[1],'), id="static-prefix"),
    pytest.param(["catalog", "rules", "recipeKey"], len('{"catalog":"рецепт","rules":[1],"recipeKey":"one"}'), id="whole-packet"),
    pytest.param([], None, id="empty-keys"), pytest.param(["rules"], None, id="noninitial-key"),
    pytest.param(["catalog", "recipeKey"], None, id="gap"), pytest.param(["catalog", "missing"], None, id="missing-key"),
])
def test_cache_prefix_requires_exact_initial_static_keys(keys, expected):
    payload = {"catalog": "рецепт", "rules": [1], "recipeKey": "one"}
    if expected is None:
        with pytest.raises(ValueError):
            json_prefix_chars(payload, keys)
    else:
        assert json_prefix_chars(payload, keys) == expected


@pytest.mark.parametrize("index,chars,valid", [(1, 15, True), (0, 3, False), (1, 0, False), (1, 999, False), (True, 3, False), (1, True, False)])
def test_cache_marker_owns_only_valid_user_boundary(index, chars, valid):
    original = cache_packet()
    if not valid:
        with pytest.raises(ValueError):
            with_prompt_cache_prefix(original, message_index=index, prefix_chars=chars)
    else:
        marked = with_prompt_cache_prefix(original, message_index=index, prefix_chars=chars)
        assert original == cache_packet() and marked["messages"] == original["messages"]
        assert marked["_infini_prompt_cache"] == {"messageIndex": 1, "prefixChars": 15}
        assert "_infini_prompt_cache" not in llm._clean_llm_payload(marked)


@pytest.mark.parametrize("variant,equal", [("recipe", True), ("model", False), ("schema", False), ("reasoning", False), ("role", False), ("process-hash-seed", True)])
def test_cache_identity_is_stable_but_includes_contract_inputs(variant, equal):
    first = with_prompt_cache_prefix(cache_packet(), message_index=1, prefix_chars=15)
    second = copy.deepcopy(first)
    model = "gpt-5.5"
    if variant == "recipe":
        second = with_prompt_cache_prefix(cache_packet('{"recipeKey":"two"}'), message_index=1, prefix_chars=15)
    elif variant == "model":
        model = "gpt-5.4"
    elif variant == "schema":
        second["response_format"] = {"type": "json_schema", "json_schema": {"schema": {"type": "object"}}}
    elif variant == "reasoning":
        second["reasoning"] = {"effort": "high"}
    elif variant == "role":
        second["messages"][0]["role"] = "developer"
    identity = llm._prompt_cache_identity(first, "gpt-5.5")
    assert identity.startswith("infini-") and "recipe" not in identity and "Shared rules" not in identity
    if variant == "process-hash-seed":
        script = "from infini_local.pipelines.llm_transport import _prompt_cache_identity; print(_prompt_cache_identity(" + repr(second) + ", 'gpt-5.5'))"
        child = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True, timeout=30, cwd=Path(__file__).resolve().parents[1])
        assert child.stdout.strip() == identity
    else:
        assert (identity == llm._prompt_cache_identity(second, model)) is equal


@pytest.mark.parametrize("provider,base,model,mode,route", [
    pytest.param("openai_compat", "https://api.openai.com/v1", "gpt-5.6", "responses", "explicit", id="platform-responses"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-5.6", "responses", "explicit", id="router-responses"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "gpt-6-astra", "responses", "explicit", id="future-openai-model"),
    pytest.param("openai_codex", "https://chatgpt.com/backend-api/codex", "gpt-5.4", "responses", "key", id="subscription-adapter"),
    pytest.param("openai_compat", "https://other.example/v1", "gpt-5.6", "responses", "none", id="foreign-responses"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "gpt-5.4", "chat_completions", "key", id="platform-chat"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-5.6", "chat_completions", "explicit", id="router-chat"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "google/gemini-3", "chat_completions", "none", id="non-openai-chat"),
    pytest.param("openai_compat", "https://custom.example/v1", "gpt-5.6", "chat_completions", "none", id="foreign-chat"),
])
def test_cache_wire_fields_are_provider_model_and_api_scoped(wire, monkeypatch, provider, base, model, mode, route):
    from infini_local.services import codex_text_backend as codex
    codex_bodies = []
    monkeypatch.setattr(codex, "generate_chat", lambda prepared, **kw: codex_bodies.append(codex._request_payload(prepared)) or {"choices": [{"message": {"content": "{}"}}], "usage": {}})
    context = {"provider": provider, "base_url": base, "model": model, "api_mode": mode, "api_key": "secret-one"}
    sources = []
    for suffix in ('{"recipeKey":"one"}', '{"recipeKey":"two"}'):
        source = with_prompt_cache_prefix(cache_packet(suffix), message_index=1, prefix_chars=15)
        sources.append(copy.deepcopy(source))
        llm._llm_json_single_context(source, 1, context)
        assert source == sources[-1]
    bodies = codex_bodies if provider == "openai_codex" else [body for _, body, _ in wire.calls]
    assert len(bodies) == 2 and bodies[0] != bodies[1]
    for ordinal, body in enumerate(bodies):
        assert "_infini_prompt_cache" not in str(body) and "secret-one" not in str(body)
        if route == "none":
            assert "prompt_cache_key" not in body and "prompt_cache_options" not in body
        else:
            assert body["prompt_cache_key"] == llm._prompt_cache_identity(sources[ordinal], model)
            assert bodies[0]["prompt_cache_key"] == bodies[1]["prompt_cache_key"]
        content = body["input"][0]["content"] if mode == "responses" else body["messages"][1]["content"]
        if provider == "openai_codex":
            assert body["store"] is False and "prompt_cache_options" not in body
            assert "prompt_cache_breakpoint" not in str(body)
        elif route == "explicit":
            assert body["prompt_cache_options"] == {"mode": "explicit"}
            if mode == "responses":
                assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
        if isinstance(content, list):
            assert ''.join(part["text"] for part in content) == sources[ordinal]["messages"][1]["content"]
        else:
            assert content == sources[ordinal]["messages"][1]["content"]
        if mode == "chat_completions" and route == "none":
            assert body["messages"] == sources[ordinal]["messages"]


@pytest.mark.parametrize("usage,cached,hit,write", [
    pytest.param({"input_tokens": 50}, None, None, None, id="missing-not-zero"),
    pytest.param({"prompt_tokens_details": {"cached_tokens": 0}}, 0, False, None, id="real-zero"),
    pytest.param({"input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 0}}, 20, True, 0, id="positive-hit"),
])
def test_usage_distinguishes_missing_zero_and_real_cache_hit(usage, cached, hit, write):
    result = llm._usage_fields({"usage": usage})
    assert result["cachedInputTokens"] == cached and result["cacheHit"] is hit
    assert result["cacheWriteTokens"] == write


@pytest.mark.parametrize("operation,text,expected", [
    pytest.param("parse", '```json\n{"name":"First"}\n``` trailing {"name":"Second"}', {"name": "First"}, id="fenced-first-object"),
    pytest.param("candidates", '{"a":1}{"b":2}', ['{"a":1}', '{"b":2}'], id="duplicate-objects"),
    pytest.param("parse", 'prefix {"text":"brace } inside string", "ok": true} suffix', {"text": "brace } inside string", "ok": True}, id="string-braces"),
    pytest.param("parse", '<thought>{"name":"Decoy"}</thought>{"name":"Authored"}', {"name": "Authored"}, id="private-thought"),
    pytest.param("candidates", '<thought>{"name":"unfinished-decoy"}', [], id="unfinished-private-thought"),
])
def test_json_extraction_preserves_authored_text_not_private_thought(operation, text, expected):
    result = parse_first_valid_llm_json(text) if operation == "parse" else json_object_candidates(text)
    assert result == expected


@pytest.mark.parametrize("text,expected", [
    pytest.param('{"label":",}", "rows":[{"value":7,},],}', {"label": ",}", "rows": [{"value": 7}]}, id="trailing-comma-not-string"),
    pytest.param('{"calls":[{"damage":12,\n, "kind":"test"}],"attributes":{speed: 2, mode:true, mark:"speed:2"}}', {"calls": [{"damage": 12, "kind": "test"}], "attributes": {"speed": 2, "mode": True, "mark": "speed:2"}}, id="object-comma-and-unquoted-key"),
    pytest.param('{"missing":', None, id="missing-value"),
    pytest.param('{"item":{"damage":20}', {"item": {"damage": 20}}, id="unique-final-brace"),
    pytest.param('{"item":{"damage":20', None, id="missing-inner-brace"),
    pytest.param('{"item":[1,2]', None, id="missing-array-owner-brace"),
    pytest.param('{"damage":42,"damage":43,}', None, id="duplicate-key"),
    pytest.param('{damage:42,"damage":43}', None, id="normalized-duplicate-key"),
    pytest.param('{"mode":recall_home}', None, id="no-invented-enum"),
    pytest.param('{"array":[1,,2]}', None, id="array-middle-hole"),
    pytest.param('{"array":[,1]}', None, id="array-leading-hole"),
    pytest.param('{"array":[,]}', None, id="array-empty-hole"),
    pytest.param('{"array":[1,,]}', None, id="array-trailing-hole"),
    pytest.param('{"missing":,}', None, id="missing-value-comma"),
    pytest.param('{"a":1,,}', {"a": 1}, id="object-extra-trailing-comma"),
])
def test_json_syntax_recovery_never_invents_or_rewrites_values(text, expected):
    assert recover_object_with_syntax_only_repairs(text) == expected


def test_platform_responses_explicit_breakpoint_preserves_exact_content_and_is_stateless(monkeypatch):
    monkeypatch.setattr(llm, "http_json", lambda url, body, **kw: sent.append(body) or {
        "id": "resp-id", "output_text": "{}", "usage": {"input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 12}}})
    sent = []
    ctx = {"provider": "openai_compat", "base_url": "https://api.openai.com/v1", "model": "gpt-5.6", "api_mode": "responses", "api_key": "test"}
    marked = with_prompt_cache_prefix(cache_packet(), message_index=1, prefix_chars=len('{"catalog":[], '))
    with llm.llm_item_lease("first") as lease:
        # Exercise the actual same-profile lease branch, including a pre-existing
        # continuation. A distinct context object would bypass this guard.
        lease.context = ctx
        lease.previous_response_id = "previous-craft-stage"
        result = llm._llm_responses_json_single_context(marked, 1, ctx)
        llm._llm_responses_json_single_context(marked, 1, ctx)
        assert not lease.previous_response_id
    assert len(sent) == 2
    for wire in sent:
        assert "previous_response_id" not in wire
        assert "_infini_prompt_cache" not in str(wire)
        assert wire["prompt_cache_options"] == {"mode": "explicit"}
        blocks = wire["input"][0]["content"]
        assert blocks[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
        assert ''.join(block["text"] for block in blocks) == marked["messages"][1]["content"]
    assert result["_debug"]["cachedInputTokens"] == 0
    assert result["_debug"]["cacheHit"] is False
    assert result["_debug"]["cacheWriteTokens"] == 12


def test_api_presets_explain_working_transport_and_optional_schema():
    from infini_local.desktop import settings_schema

    for name, preset in settings_schema.PRESETS.items():
        provider = preset.get("INFINI_LLM_PROVIDER")
        if provider not in {"openai_compat", "openrouter"}:
            continue
        assert preset.get("INFINI_LLM_RESPONSE_FORMAT") == "json_object", name
        assert preset.get("INFINI_LLM_API_MODE") == "chat_completions", name
    # json_schema must remain a selectable option, only documented as unsupported there.
    choices = settings_schema.OPTION_HELP["INFINI_LLM_RESPONSE_FORMAT"]
    assert set(choices) == {"auto", "json_schema", "json_object", "off"}
    assert "Gemini" in choices["json_schema"]
    assert "json_schema" in settings_schema.FIELD_HELP["INFINI_LLM_RESPONSE_FORMAT"]
    schema_text = Path(settings_schema.__file__).read_text(encoding="utf-8")
    assert "INVALID_ARGUMENT" in schema_text


def test_malformed_content_retry_keeps_one_logical_call_and_combines_attribution(monkeypatch) -> None:
    calls = []

    def fake_single(payload, timeout, context):
        calls.append(payload)
        content = '{"broken":' if len(calls) == 1 else '{"ok":true}'
        result: dict[str, Any] = {
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        }
        if len(calls) == 1:
            result["_debug"] = {
                "transportRetryCount": 1,
                "transportRetryCauses": ["responses_to_chat_fallback"],
            }
        return result

    monkeypatch.setattr(llm, "_llm_json_single_context", fake_single)
    monkeypatch.setattr(llm, "log_event", lambda *_args, **_kwargs: None)
    context = {
        "provider": "openai_compat",
        "base_url": "http://single.local:1234",
        "model": "gemma-4-31b-it",
        "profile_id": "llm_1",
    }
    monkeypatch.setattr(llm, "_primary_llm_context", lambda: context)
    monkeypatch.setattr(llm, "_fallback_llm_context", lambda: None)
    payload = {
        "model": "gemma-4-31b-it",
        "messages": [],
        "response_format": {"type": "json_object"},
    }
    lease = llm.LlmItemLease(
        recipe_key="retry-accounting",
        lease_id="llm_1:1",
        profile_id="llm_1",
        context=context,
        pool_size=1,
    )
    token = llm._CURRENT_LLM_ITEM_LEASE.set(lease)
    try:
        out = llm.llm_chat_json(payload, timeout=1)
    finally:
        llm._CURRENT_LLM_ITEM_LEASE.reset(token)
    assert out["choices"][0]["message"]["content"] == '{"ok":true}'
    assert len(calls) == 2
    assert calls[1] == payload
    assert lease.call_count == 1
    assert len(lease.stages) == 1
    assert out["_debug"]["transportRetryCount"] == 2
    assert out["_debug"]["transportRetryCauses"] == [
        "responses_to_chat_fallback",
        "malformed_json",
    ]


@pytest.mark.parametrize("complete", [False, True], ids=["length-incomplete-minimal-retry", "length-complete-prefix-no-retry"])
def test_google_length_retry_preserves_valid_output_and_reasoning_intent(monkeypatch, complete):
    content = '{"ok":true}\n' + ('}\n' * 128) if complete else "{"
    calls = []
    def single(payload, timeout, context):
        calls.append(copy.deepcopy(payload))
        return {"choices": [{"finish_reason": "length" if len(calls) == 1 else "stop",
            "message": {"content": content if len(calls) == 1 else "{}"}}]}
    monkeypatch.setattr(llm, "_llm_json_single_context", single)
    monkeypatch.setattr(llm, "_is_google_openai_compat_reasoning_model", lambda _model, _context: True)
    monkeypatch.setattr(llm, "log_event", lambda *_a, **_k: None)
    request = {"model": "gemini-3.1-flash-lite", "messages": [],
        "response_format": {"type": "json_object"}, llm._REASONING_INTENT_KEY: {"effort": "minimal" if complete else "low", "exclude": True}}
    before = copy.deepcopy(request)
    result = llm._llm_json_single_context_with_length_retry(request, 1, {"model": request["model"]})
    assert request == before
    assert len(calls) == (1 if complete else 2)
    if complete:
        assert parse_first_valid_llm_json(result["choices"][0]["message"]["content"]) == {"ok": True}
        assert "transportRetryCount" not in result.get("_debug", {})
    else:
        assert result["choices"][0]["finish_reason"] == "stop"
        assert calls[1][llm._REASONING_INTENT_KEY]["effort"] == "minimal"
