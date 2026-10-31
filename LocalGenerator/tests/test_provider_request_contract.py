"""Provider request semantics: reasoning, schema diagnosis, cache identity, JSON."""
from __future__ import annotations

import copy
import urllib.error

import pytest

from infini_local.core import llm_config
from infini_local.pipelines.transport import profiles as llm_profiles
from infini_local.pipelines.transport import provider_wire as llm_provider_wire
from infini_local.core.llm_json_tools import json_object_candidates, parse_first_valid_llm_json, recover_object_with_syntax_only_repairs
from infini_local.core.llm_prompt_cache import with_prompt_cache_prefix
from infini_local.pipelines.transport import client as llm
from test_provider_transport_contract import schema_error, packet, wire, loopback_transport  # noqa: F401 - imported pytest fixtures

SCHEMA_REJECTION = {"error": {"code": "unsupported_response_format", "param": "response_format",
                              "message": "json_schema response_format is not supported"}}

GOOGLE = "https://generativelanguage.googleapis.com/v1beta/openai"


def cache_packet(suffix='{"recipeKey":"one"}'):
    return {"messages": [{"role": "system", "content": "Shared rules"},
        {"role": "user", "content": '{"catalog":[], ' + suffix}], "response_format": {"type": "json_object"}}


@pytest.fixture
def context_scalars(monkeypatch):
    """Direct legacy scalar seams only; never broaden runtime/native imports."""
    def configure(default):
        monkeypatch.setattr(llm, "resolve_llm_model", lambda context=None: (context or default)["model"])
        monkeypatch.setattr(llm_profiles, "active_llm_provider", lambda context=None: (context or default)["provider"])
        monkeypatch.setattr(llm_profiles, "llm_base_url", lambda context=None: (context or default)["base_url"])
    return configure


@pytest.mark.parametrize("provider,base,model,mode,effort,source", [
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "auto", "medium", "options", id="google-auto"),
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "xhigh", "high", "options", id="google-xhigh"),
    pytest.param("openai_compat", GOOGLE, "gemma-4-31b-it", "minimal", "minimal", "options", id="google-gemma-minimal"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "google/gemini-3.1-flash-lite", "medium", "medium", "options", id="router-envelope"),
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "medium", "medium", "envelope", id="fallback-to-google"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "google/gemini-3.1-flash-lite", "medium", "medium", "native", id="fallback-to-router"),
    pytest.param("openai_compat", GOOGLE, "gemini-3.1-flash-lite", "medium", "medium", "local-intent", id="local-to-remote-intent"),
])
def test_reasoning_control_is_native_to_the_selected_context(wire, monkeypatch, context_scalars, provider, base, model, mode, effort, source):
    context = {"provider": provider, "base_url": base, "model": model,
               "api_mode": "chat_completions", "api_key": "synthetic-reasoning-key"}
    local = {"provider": "local", "base_url": "http://127.0.0.1:1234/v1", "model": "local-model"}
    default = local if source == "local-intent" else context
    monkeypatch.setattr(llm_config, "LLM_REASONING_MODE", mode)
    context_scalars(default)
    if source in {"options", "local-intent"}:
        request = llm_provider_wire.apply_llm_common_options({}, model_name=default["model"])
    else:
        request = {"reasoning": {"effort": effort, "exclude": True}} if source == "envelope" else {"reasoning_effort": effort}
    before = copy.deepcopy(request)
    llm._llm_json_single_context(request, 1, context)
    prepared = wire.calls[-1][1]
    if base == GOOGLE:
        assert prepared["reasoning_effort"] == effort and "reasoning" not in prepared
    else:
        assert prepared["reasoning"] == {"effort": effort, "exclude": llm_config.LLM_REASONING_EXCLUDE}
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
def test_reasoning_headroom_preserves_answer_budget_only_for_actual_google(wire, monkeypatch, context_scalars, provider, base, budget, effort, expected, native):
    context = {"provider": provider, "base_url": base, "model": "gemini-3.5-flash-lite",
               "api_mode": "chat_completions", "api_key": "synthetic-reasoning-key"}
    context_scalars({})
    request = {"max_tokens": budget, "reasoning_effort": effort}
    llm._llm_json_single_context(request, 1, context)
    prepared = wire.calls[-1][1]
    assert request == {"max_tokens": budget, "reasoning_effort": effort}
    assert prepared["max_tokens"] == expected
    if native:
        assert prepared["reasoning_effort"] == effort
    else:
        assert "reasoning_effort" not in prepared and prepared["reasoning"]["effort"] == effort


@pytest.mark.parametrize("initial,expected", [("off", "medium"), ("high", "high")])
def test_author_reasoning_floor_does_not_lower_explicit_high(monkeypatch, initial, expected):
    monkeypatch.setattr(llm_profiles, "active_llm_provider", lambda context=None: "openai_compat")
    monkeypatch.setattr(llm_profiles, "llm_base_url", lambda context=None: GOOGLE)
    monkeypatch.setattr(llm_config, "LLM_REASONING_MODE", initial)
    request = llm_provider_wire.apply_llm_common_options({}, model_name="gemini-3.5-flash-lite") if initial == "off" else {"reasoning_effort": "high"}
    assert llm_provider_wire.apply_minimum_reasoning_effort(request, model_name="gemini-3.5-flash-lite", minimum="medium")["reasoning_effort"] == expected


@pytest.mark.parametrize("cause", ["messages", "unsupported_valid", "unsupported_failed", "unsupported_malformed", "complexity", "model_override", "model_override_whitespace"])
def test_real_http_schema_cache_requires_relevant_rejection_valid_recovery_and_exact_scope(
    loopback_transport, cause,
):
    endpoint, _events = loopback_transport
    rejection = copy.deepcopy(SCHEMA_REJECTION)
    if cause == "messages":
        rejection = {"error": {"code": "context_length_exceeded", "param": "messages",
                               "message": "messages exceed the model context limit"}}
    elif cause == "complexity":
        rejection = {"error": {"code": "invalid_json_schema", "param": "response_format.json_schema.schema",
                               "message": "json_schema exceeds schema complexity limits"}}
    recovery = {}
    if cause == "unsupported_failed":
        recovery = {"status": 400, "body": {"error": {"code": "context_length_exceeded", "param": "messages"}}}
    elif cause == "unsupported_malformed":
        recovery = {"body": {"choices": [{"message": {"content": "{"}}]}}
    replies = [{"status": 400, "body": rejection}]
    if cause != "messages":
        replies.append(recovery)
    replies.extend([{}, {}])
    base, observed = endpoint(replies)
    context = {"provider": "openrouter", "openrouter_provider": "ExactVendor/Endpoint-Turbo",
               "base_url": base, "model": "vendor/model", "api_mode": "chat_completions",
               "api_key": "synthetic-loopback-key"}
    request = packet(schema=True)
    if cause in {"model_override", "model_override_whitespace"}:
        request[llm_provider_wire.LLM_MODEL_OVERRIDE_KEY] = " override/first " if cause == "model_override_whitespace" else "override/first"
    before = copy.deepcopy(request)
    if cause in {"messages", "unsupported_failed"}:
        with pytest.raises(urllib.error.HTTPError):
            llm._llm_chat_json_single_context(request, 1, context)
    else:
        first = llm._llm_chat_json_single_context(request, 1, context)
        assert first["choices"][0]["message"]["content"] == ("{" if cause == "unsupported_malformed" else "{}")
    if cause == "complexity":
        # Same schema can reuse the evidence, another schema must re-negotiate.
        llm._llm_chat_json_single_context(request, 1, context)
    next_request = copy.deepcopy(request)
    next_request["messages"][1]["content"] = "smaller next authored packet"
    if cause == "complexity":
        next_request["response_format"]["json_schema"]["schema"]["properties"] = {"value": {"type": "string"}}
    elif cause in {"model_override", "model_override_whitespace"}:
        next_request[llm_provider_wire.LLM_MODEL_OVERRIDE_KEY] = "override/first" if cause == "model_override_whitespace" else "override/second"
    llm._llm_chat_json_single_context(next_request, 1, context)
    formats = [body["response_format"]["type"] for _, _, body, _ in observed]
    assert formats == {
        "messages": ["json_schema", "json_schema"],
        "unsupported_valid": ["json_schema", "json_object", "json_object"],
        "unsupported_failed": ["json_schema", "json_object", "json_schema"],
        "unsupported_malformed": ["json_schema", "json_object", "json_schema"],
        "complexity": ["json_schema", "json_object", "json_object", "json_schema"],
        "model_override": ["json_schema", "json_object", "json_schema"],
        "model_override_whitespace": ["json_schema", "json_object", "json_object"],
    }[cause]
    assert all(body["provider"] == {"only": [context["openrouter_provider"]], "allow_fallbacks": False}
               for _, _, body, _ in observed)
    if cause != "messages":
        assert observed[1][2] == {**observed[0][2], "response_format": {"type": "json_object"}}
    assert request == before


def test_shape_rejection_reaches_actual_author_failure_with_operator_diagnosis(wire, monkeypatch):
    from infini_local.pipelines.author import request as author
    from infini_local.core.errors import PlannerUnavailable
    wire.configure(OPENROUTER_PROVIDER="", LLM_PROVIDER="openai_compat", OPENAI_COMPAT_BASE_URL=GOOGLE,
                   OPENAI_COMPAT_MODEL="gemini-3.5-flash-lite", LLM_API_MODE="chat_completions")
    wire.replies.extend([schema_error(GOOGLE + "/chat/completions"), 400])
    request = packet(schema=True)
    events, logs = [], []
    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(author, "resolve_llm_model", lambda: "gemini-3.5-flash-lite")
    monkeypatch.setattr(author, "build_initial_author_request", lambda *_a, **_k: (request, "literal task", "literal rules"))
    # Connect the real exact-wire rejection owner to the real Author consumer;
    # schema negotiation (including a second, unrelated rejection) is tested above.
    monkeypatch.setattr(author, "llm_chat_json", lambda payload, timeout: llm._llm_chat_json_exact_context(payload, timeout, llm_profiles._primary_llm_context()))
    monkeypatch.setattr(author, "trace_event", lambda *args, **kw: events.append(args))
    monkeypatch.setattr(llm, "log_event", lambda level, message, data=None: logs.append((message, data)))
    with pytest.raises(PlannerUnavailable) as caught:
        author.try_llm_plan({}, {}, "shape-owner")
    cause = caught.value.__cause__
    assert isinstance(cause, urllib.error.HTTPError)
    diagnosis = cause._infini_shape_diagnosis
    assert diagnosis["hint"] in str(caught.value)
    assert any(args[3].get("requestShapeRejection") == diagnosis for args in events)
    assert any(message == "LLM provider rejected the configured request shape" and all(data.get(key) == value for key, value in diagnosis.items()) for message, data in logs)


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


@pytest.mark.parametrize("provider,base,model,mode,route", [
    pytest.param("openai_compat", "https://api.openai.com/v1", "gpt-5.6", "responses", "explicit", id="platform-responses"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-5.6", "responses", "explicit", id="router-responses"),
    pytest.param("openai_codex", "https://chatgpt.com/backend-api/codex", "gpt-5.4", "responses", "key", id="subscription-adapter"),
    pytest.param("openai_compat", "https://other.example/v1", "gpt-5.6", "responses", "none", id="foreign-responses"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "gpt-5.4", "chat_completions", "key", id="platform-chat"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-5.6", "chat_completions", "explicit", id="router-chat"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "google/gemini-3", "chat_completions", "none", id="non-openai-chat"),
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
            assert isinstance(body["prompt_cache_key"], str) and body["prompt_cache_key"].startswith("infini-")
            assert bodies[0]["prompt_cache_key"] == bodies[1]["prompt_cache_key"]
        content = body["input"][0]["content"] if mode == "responses" else body["messages"][1]["content"]
        if provider == "openai_codex":
            assert body["input"] == [
                {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "JSON response."}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": sources[ordinal]["messages"][1]["content"]}]},
            ]
            content = body["input"][1]["content"]
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
    result = llm_provider_wire._usage_fields({"usage": usage})
    assert result["cachedInputTokens"] == cached and result["cacheHit"] is hit
    assert result["cacheWriteTokens"] == write


@pytest.mark.parametrize("details,expected", [
    pytest.param({"completion_tokens_details": {"reasoning_tokens": 66}}, 66, id="chat-reasoning"),
    pytest.param({"completion_tokens_details": {"reasoning_tokens": 0}}, 0, id="chat-explicit-zero"),
    pytest.param({"output_tokens_details": {"reasoning_tokens": 100}}, 100, id="responses-reasoning"),
    pytest.param({}, None, id="missing-is-unknown"),
    pytest.param({"completion_tokens_details": {"reasoning_tokens": True}}, None, id="bool-not-counter"),
    pytest.param({"output_tokens_details": {"reasoning_tokens": 0},
                  "completion_tokens_details": {"reasoning_tokens": 66}}, 0, id="responses-zero-wins"),
    pytest.param({"output_tokens_details": {"reasoning_tokens": -1},
                  "completion_tokens_details": {"reasoning_tokens": 66}}, None, id="invalid-primary-not-replaced"),
])
def test_usage_reasoning_reads_chat_and_responses_without_rewriting_usage(details, expected):
    response = {"usage": {"prompt_tokens": 120, "completion_tokens": 6,
                          "prompt_tokens_details": {"cached_tokens": 0}, **details}}
    before = copy.deepcopy(response)
    diagnostic = llm_provider_wire._usage_fields(response)
    assert diagnostic["reasoningTokens"] == expected
    assert diagnostic["cachedInputTokens"] == 0 and diagnostic["cacheHit"] is False
    assert response == before


@pytest.mark.parametrize("usage,input_tokens,output_tokens", [
    pytest.param({}, None, None, id="absent-not-free"),
    pytest.param(None, None, None, id="null-usage"),
    pytest.param([], None, None, id="nonobject-usage"),
    pytest.param({"input_tokens": 0, "prompt_tokens": 12, "output_tokens": 0,
                  "completion_tokens": 6}, 0, 0, id="explicit-zero-preserved"),
    pytest.param({"prompt_tokens": 12, "completion_tokens": 6}, 12, 6, id="chat-totals"),
    pytest.param({"input_tokens": 20, "output_tokens": 7}, 20, 7, id="responses-totals"),
    pytest.param({"input_tokens": True, "output_tokens": "6"}, None, None, id="malformed-not-coerced"),
    pytest.param({"prompt_tokens": -1, "completion_tokens": 1.5}, None, None, id="invalid-domain"),
    pytest.param({"input_tokens": None, "prompt_tokens": 12, "output_tokens": {},
                  "completion_tokens": 6}, None, None, id="invalid-primary-not-replaced"),
])
def test_usage_totals_preserve_zero_missing_and_invalid(usage, input_tokens, output_tokens):
    response = {"usage": usage}
    before = copy.deepcopy(response)
    diagnostic = llm_provider_wire._usage_fields(response)
    assert diagnostic["inputTokens"] == input_tokens
    assert diagnostic["outputTokens"] == output_tokens
    assert response == before


@pytest.mark.parametrize("api_mode", ["chat_completions", "responses"])
def test_successful_provider_reply_keeps_raw_usage_and_publishes_actual_counters(wire, api_mode):
    usage = {"prompt_tokens": 120, "completion_tokens": 6,
             "prompt_tokens_details": {"cached_tokens": 0},
             "completion_tokens_details": {"reasoning_tokens": 3}}
    reply = ({"choices": [{"message": {"content": "{}"}}]} if api_mode == "chat_completions"
             else {"id": "usage-fixture", "status": "completed", "output_text": "{}"})
    wire.replies.append({**reply, "usage": usage})
    context = {"provider": "openai_compat", "base_url": "https://inference-api.nousresearch.com/v1",
               "model": "openai/gpt-6.1-sol", "api_mode": api_mode, "api_key": "synthetic-usage-key"}
    source = with_prompt_cache_prefix(cache_packet(), message_index=1, prefix_chars=15)
    before = copy.deepcopy(source)
    result = llm._llm_json_single_context(source, 1, context)
    assert len(wire.calls) == 1
    url, body, _headers = wire.calls[0]
    assert url.endswith("/chat/completions" if api_mode == "chat_completions" else "/responses")
    # Existing provider hint policy stays intact; this change only reads the reply.
    if api_mode == "chat_completions":
        assert body["prompt_cache_key"].startswith("infini-")
    else:
        assert "prompt_cache_key" not in body
    assert "prompt_cache_options" not in body
    assert result["usage"] == usage
    assert result["_debug"]["reasoningTokens"] == 3
    assert result["_debug"]["inputTokens"] == 120
    assert result["_debug"]["outputTokens"] == 6
    assert result["_debug"]["cachedInputTokens"] == 0
    assert result["_debug"]["cacheHit"] is False
    assert result["_debug"]["cacheWriteTokens"] is None
    assert source == before


@pytest.mark.parametrize("operation,text,expected", [
    pytest.param("parse", '```json\n{"name":"First"}\n``` trailing {"name":"Second"}', {"name": "First"}, id="fenced-first-object"),
    pytest.param("candidates", '{"a":1}{"b":2}', ['{"a":1}', '{"b":2}'], id="duplicate-objects"),
    pytest.param("parse", 'prefix {"text":"brace } inside string", "ok": true} suffix', {"text": "brace } inside string", "ok": True}, id="string-braces"),
    pytest.param("parse", '<thought>{"name":"Decoy"}</thought>{"name":"Authored"}', {"name": "Authored"}, id="private-thought"),
    pytest.param("candidates", '<thought>{"name":"unfinished-decoy"}', [], id="unfinished-private-thought"),
    pytest.param("parse", '{"text":"<analysis>literal</analysis>"}', {"text": "<analysis>literal</analysis>"}, id="literal-private-tags"),
    pytest.param("parse", '<analysis>{"decoy":1}</analysis>{"text":"<thought>literal"}', {"text": "<thought>literal"}, id="unfinished-literal-tag"),
    pytest.param("parse", '{"text":"quote \\" <analysis>x</analysis>"}', {"text": 'quote " <analysis>x</analysis>'}, id="escaped-quote-before-tag"),
])
def test_json_extraction_preserves_authored_text_not_private_thought(operation, text, expected):
    result = parse_first_valid_llm_json(text) if operation == "parse" else json_object_candidates(text)
    assert result == expected


@pytest.mark.parametrize("text", [
    '{"damage":1,"damage":2}', '{"damage":NaN}', '{"damage":Infinity}',
    '{"damage":1e999}', '{"child":{"damage":1,"damage":2}}',
])
def test_llm_json_rejects_ambiguous_or_nonfinite_candidates(text):
    with pytest.raises(ValueError):
        parse_first_valid_llm_json(text)
    assert recover_object_with_syntax_only_repairs(text) is None
    assert parse_first_valid_llm_json(text + '{"damage":3}') == {"damage": 3}


@pytest.mark.parametrize("text,expected", [
    pytest.param('{"label":",}", "rows":[{"value":7,},],}', {"label": ",}", "rows": [{"value": 7}]}, id="trailing-comma-not-string"),
    pytest.param('{"calls":[{"damage":12,\n, "kind":"test"}],"attributes":{speed: 2, mode:true, mark:"speed:2"}}', {"calls": [{"damage": 12, "kind": "test"}], "attributes": {"speed": 2, "mode": True, "mark": "speed:2"}}, id="object-comma-and-unquoted-key"),
    pytest.param('{"missing":', None, id="missing-value"),
    pytest.param('{"item":{"damage":20}', {"item": {"damage": 20}}, id="unique-final-brace"),
    pytest.param('{"damage":42,"damage":43,}', None, id="duplicate-key"),
    pytest.param('{"mode":recall_home}', None, id="no-invented-enum"),
    pytest.param('{"array":[1,,2]}', None, id="array-middle-hole"),
])
def test_json_syntax_recovery_never_invents_or_rewrites_values(text, expected):
    assert recover_object_with_syntax_only_repairs(text) == expected


def test_platform_responses_explicit_breakpoint_preserves_exact_content_and_is_stateless(monkeypatch):
    monkeypatch.setattr(llm, "http_json", lambda url, body, **kw: sent.append(body) or {
        "id": "resp-id", "output_text": "{}", "usage": {"input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 12}}})
    sent = []
    ctx = {"provider": "openai_compat", "base_url": "https://api.openai.com/v1", "model": "gpt-5.6", "api_mode": "responses", "api_key": "test"}
    marked = with_prompt_cache_prefix(cache_packet(), message_index=1, prefix_chars=len('{"catalog":[], '))
    with llm_profiles.llm_item_lease("first") as lease:
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


@pytest.mark.parametrize("complete", [False, True], ids=["length-incomplete-minimal-retry", "length-complete-prefix-no-retry"])
def test_google_length_retry_preserves_valid_output_and_reasoning_intent(monkeypatch, complete):
    content = '{"ok":true}\n' + ('}\n' * 128) if complete else "{"
    calls = []
    def single(payload, timeout, context):
        calls.append(copy.deepcopy(payload))
        return {"choices": [{"finish_reason": "length" if len(calls) == 1 else "stop",
            "message": {"content": content if len(calls) == 1 else "{}"}}]}
    monkeypatch.setattr(llm, "_llm_json_single_context", single)
    monkeypatch.setattr(llm_provider_wire, "_is_google_openai_compat_reasoning_model", lambda _model, _context: True)
    monkeypatch.setattr(llm, "log_event", lambda *_a, **_k: None)
    request = {"model": "gemini-3.1-flash-lite", "messages": [],
        "response_format": {"type": "json_object"}, llm_provider_wire._REASONING_INTENT_KEY: {"effort": "minimal" if complete else "low", "exclude": True}}
    before = copy.deepcopy(request)
    result = llm._llm_json_single_context_with_length_retry(request, 1, {"model": request["model"]})
    assert request == before
    assert len(calls) == (1 if complete else 2)
    if complete:
        assert parse_first_valid_llm_json(result["choices"][0]["message"]["content"]) == {"ok": True}
        assert "transportRetryCount" not in result.get("_debug", {})
    else:
        assert result["choices"][0]["finish_reason"] == "stop"
        assert calls[1][llm_provider_wire._REASONING_INTENT_KEY]["effort"] == "minimal"
