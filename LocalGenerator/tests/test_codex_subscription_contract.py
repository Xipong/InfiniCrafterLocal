"""Native Codex account ownership, auth, subscription text/SSE/catalog/image contracts."""
from __future__ import annotations

import base64
import copy
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
import stat
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from infini_local.core import llm_config
from infini_local.pipelines import llm_provider_wire
from infini_local.pipelines import llm_transport as llm, pipeline_visual_config as config
from infini_local.services import codex_auth as auth, codex_catalog as catalog, codex_text_backend as backend
from test_provider_transport_contract import PIN, packet, wire  # noqa: F401 - imported pytest fixture
from provider_test_support import HttpReply, RecordingOpener

CODEX = "https://chatgpt.com/backend-api/codex"


def _assert_structured_outputs_subset(schema):
    """Offline wire gate, independent of the projector (not remote acceptance)."""
    unsupported = {"oneOf", "allOf", "not", "dependentRequired", "dependentSchemas", "if", "then", "else"}
    types = {str: "string", int: "integer", bool: "boolean", float: "number", type(None): "null", list: "array", dict: "object"}

    def visit(node, path=()):
        assert not (unsupported & node.keys()), f"unsupported provider keyword at {path}: {unsupported & node.keys()}"
        if "const" in node:
            assert node.get("type") == types[type(node["const"])], f"untyped provider const at {path}"
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, path
            assert set(node.get("required", [])) == set(node.get("properties", {})), path
        for key in ("properties", "$defs"):
            for name, child in node.get(key, {}).items():
                visit(child, path + (key, name))
        if isinstance(node.get("items"), dict):
            visit(node["items"], path + ("items",))
        for index, child in enumerate(node.get("anyOf", [])):
            visit(child, path + ("anyOf", index))

    visit(schema)


@pytest.mark.parametrize("stage", ["author", "repair"])
def test_subscription_sends_supported_schema_without_mutating_authored_packet(monkeypatch, subscription_sends, stage):
    from infini_local.pipelines import author_item_contract as contract, llm_authoring_pipeline as author

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    if stage == "author":
        request, _, _ = author.build_initial_author_request(
            {"name": "Workbench"}, {"name": "Sword"}, "schema-replay", model_name="gpt-6-sol")
    else:
        request = {"model": "gpt-6-sol", "messages": [{"role": "user", "content": "Repair the exact invalid leaf."}],
                   "response_format": llm_provider_wire.llm_json_response_format(
                       "infini_low_level_runtime_author_repair", schema=contract.author_item_provider_repair_response_schema, strict=True)}
    before = copy.deepcopy(request)
    _response, _credentials, calls = subscription_sends
    backend.generate_chat(request, timeout=3)
    assert len(calls) == 1 and calls[0][0] == CODEX + "/responses"
    sent = calls[0][1]
    _assert_structured_outputs_subset(sent["text"]["format"]["schema"])
    assert sent["model"] == request["model"]
    assert sent["text"]["format"]["type"] == "json_schema"
    assert sent["text"]["format"]["strict"] is True
    assert [row["role"] for row in sent["input"]] == [row["role"] for row in request["messages"] if row["role"] != "system"]
    assert request == before


def _encode_nullable_fixture(value: Any, local: dict[str, Any], *, definitions=None) -> Any:
    """Independent test encoder for valid sparse fixtures; never a production fallback."""
    from jsonschema import Draft202012Validator

    definitions = local.get("$defs", {}) if definitions is None else definitions
    if "$ref" in local:
        assert local["$ref"].startswith("#/$defs/")
        return _encode_nullable_fixture(value, definitions[local["$ref"].removeprefix("#/$defs/")], definitions=definitions)
    for union in ("oneOf", "anyOf"):
        if union in local:
            matches = [branch for branch in local[union]
                       if Draft202012Validator({"$defs": definitions, **branch}).is_valid(value)]
            assert len(matches) == 1
            return _encode_nullable_fixture(value, matches[0], definitions=definitions)
    if isinstance(value, dict):
        required = list(local.get("required", []))
        if "if" in local and Draft202012Validator({"$defs": definitions, **local["if"]}).is_valid(value):
            required += local["then"]["required"]
        return {
            key: (_encode_nullable_fixture(value[key], child, definitions=definitions) if key in value else None)
            for key, child in local["properties"].items()
            if key in value or key not in required
        }
    if isinstance(value, list):
        return [_encode_nullable_fixture(child, local["items"], definitions=definitions) for child in value]
    return copy.deepcopy(value)


def _sparse_event_item(event):
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

    item = build_runtime_fixture("workbench_blade")
    calls = item["runtimeProgram"]["calls"]
    spawn = next(row for row in calls if row["fn"] == "spawn_entity_on_event")
    selected = {"id": "pull_case", "fn": "pull_on_event", "target": spawn["target"],
        "params": {"when": {'everySeconds': (6) / 60} if event == "periodic" else event,
                   "mode": "target_to_entity", "impulseBlocksPerSecond": 3.75, "radiusTiles": 8}}
    calls.append(selected)
    next(row for row in calls if row["fn"] == "configure_item_stats")["params"].pop("manaCost", None)
    return item, selected


@pytest.mark.parametrize("control", ["nullable-valid", "required-null", "unknown-function"])
def test_subscription_author_parse_preserves_nullable_optionals_and_refuses_invalid_authorship(monkeypatch, control):
    from infini_local.pipelines import author_item_contract as contract, llm_authoring_pipeline as author
    from infini_local.core.runtime_authoring.validator import validate_runtime_program

    item, _ = _sparse_event_item("on_hit")
    encoded = _encode_nullable_fixture(item, contract.author_item_response_schema())
    selected = next(row for row in encoded["runtimeProgram"]["calls"] if row["fn"] == "pull_on_event")
    if control == "required-null":
        selected["params"]["impulseBlocksPerSecond"] = None
    elif control == "unknown-function":
        selected["fn"] = "unknown_function"
    before = copy.deepcopy(encoded)
    request = {"model": "gpt-6-sol", "messages": [{"role": "user", "content": "Exact authored item"}],
        "response_format": {"type": "json_schema", "json_schema": {"schema": contract.author_item_provider_response_schema()}}}
    sent = []
    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(author, "resolve_llm_model", lambda: "gpt-6-sol")
    monkeypatch.setattr(author, "build_initial_author_request", lambda *_a, **_kw: (request, "literal task", "literal rules"))
    monkeypatch.setattr(author, "trace_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(author, "trace_stage_request", lambda *_a, **_kw: None)
    monkeypatch.setattr(author, "llm_chat_json", lambda payload, **_kw: sent.append(copy.deepcopy(payload)) or {
        "choices": [{"message": {"content": json.dumps(encoded)}}], "_debug": {"responseFormatType": "json_schema"}})
    parsed = author.try_llm_plan({}, {}, "subscription-parse")
    assert len(sent) == 1 and encoded == before
    report = validate_runtime_program(parsed)
    if control == "nullable-valid":
        assert report["ok"], report["errors"]
        assert parsed["runtimeProgram"] == item["runtimeProgram"]
    else:
        assert not report["ok"], "provider projection must not conceal invalid authored values"
        row = next(row for row in parsed["runtimeProgram"]["calls"] if row["id"] == "pull_case")
        if control == "required-null":
            assert row["params"]["impulseBlocksPerSecond"] is None
        else:
            assert row["fn"] == "unknown_function"


def test_subscription_repair_wire_inverse_precedes_frozen_merge(monkeypatch):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract, llm_authoring_pipeline as author
    from infini_local.core.runtime_authoring.validator import validate_runtime_program

    item, selected = _sparse_event_item("periodic")
    expected = copy.deepcopy(item)
    selected["params"]["when"].pop("everySeconds")
    before = copy.deepcopy(item)
    failure = validate_runtime_program(item)
    assert not failure["ok"]
    corrected = copy.deepcopy(selected)
    corrected["params"].update(when={'everySeconds': (6) / 60}, impulseBlocksPerSecond=7.5)  # hostile valid sibling: must stay frozen at 1
    patch = {"note": "exact missing period", "callsUpsert": [corrected], "realizationReplacement": item["realization"]}
    encoded = _encode_nullable_fixture(patch, contract.author_item_repair_response_schema())
    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(author, "resolve_llm_model", lambda: "gpt-6-sol")
    monkeypatch.setattr(author, "trace_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    requests, premerge = [], []
    def respond(request, **_options):
        requests.append(copy.deepcopy(backend._request_payload(request)))
        assert Draft202012Validator(request["response_format"]["json_schema"]["schema"]).is_valid(encoded)
        return {"choices": [{"message": {"content": json.dumps(encoded)}}], "_debug": {"responseFormatType": "json_schema"}}
    original_filter = author.filter_repair_patch_scope
    def observe(current, delta, scope):
        premerge.append(copy.deepcopy(delta))
        assert scope["fieldPermissions"]["calls"] == [{"id": selected["id"], "paths": ['params.when.everySeconds']}]
        return original_filter(current, delta, scope)
    monkeypatch.setattr(author, "llm_chat_json", respond)
    monkeypatch.setattr(author, "filter_repair_patch_scope", observe)
    repaired = author.repair_author_item_after_failure(item, {}, {}, "provider-offline", failure_report=failure)
    assert len(requests) == len(premerge) == 1
    _assert_structured_outputs_subset(requests[0]["text"]["format"]["schema"])
    assert requests[0]["model"] == "gpt-6-sol" and requests[0]["text"]["format"]["strict"] is True
    assert premerge == [patch]  # no null scaffolding reaches frozen-first Repair
    repaired.pop("debug", None)
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert item == before and validate_runtime_program(repaired)["ok"]


def message(text, *, phase=None, **extra):
    result = {"type": "message", "role": "assistant", "status": "completed",
              "content": [{"type": "output_text", "text": text}], **extra}
    if phase is not None:
        result["phase"] = phase
    return result


def token_response():
    claims = {"exp": int(time.time()) + 3600, "https://api.openai.com/auth": {"chatgpt_account_id": "test-account"}}
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return {"access_token": "test." + body + ".unsigned", "refresh_token": "test-refresh-not-real", "expires_in": 3600}


@pytest.fixture
def subscription(monkeypatch):
    credentials = auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", 9999999999)
    response = {"status": "completed", "output": [message('{"ok":true}')]}
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    monkeypatch.setattr(auth, "post_sse", lambda *_a, **_k: copy.deepcopy(response))
    return response, credentials


@pytest.fixture
def subscription_sends(subscription, monkeypatch):
    response, credentials = subscription
    calls = []

    def post(url, body, **options):
        calls.append((url, copy.deepcopy(body), options))
        return copy.deepcopy(response)

    monkeypatch.setattr(auth, "post_sse", post)
    return response, credentials, calls


@dataclass
class StreamOpener:
    body: bytes
    requests: list = field(default_factory=list)

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return io.BytesIO(self.body)


def test_pkce_authorization_url_has_native_challenge_redirect_and_scope():
    attempt = auth.LoginAttempt()
    params = parse_qs(urlsplit(attempt.authorization_url).query)
    expected = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).decode().rstrip("=")
    assert params["code_challenge"] == [expected] and params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    assert params["scope"] == ["openid profile email offline_access"]
    assert attempt.verifier not in repr(attempt)


@pytest.mark.parametrize("callback,valid", [("valid", True), ("wrong-state", False), ("duplicate-state", False), ("duplicate-code", False)])
def test_pkce_callback_binds_state_and_rejects_duplicates(callback, valid):
    attempt = auth.LoginAttempt()
    suffix = {"valid": f"state={attempt.state}&code=test-code", "wrong-state": "state=wrong&code=x",
        "duplicate-state": f"state={attempt.state}&state=wrong&code=x", "duplicate-code": f"state={attempt.state}&code=x&code=y"}[callback]
    if valid:
        assert attempt.callback_code("/auth/callback?" + suffix) == "test-code"
    else:
        with pytest.raises(auth.CodexError):
            attempt.callback_code("/auth/callback?" + suffix)


@pytest.mark.parametrize("method,status,encoding,diagnostic", [
    pytest.param("post", 429, "plain", "quota reached", id="post-status-and-redaction"),
    pytest.param("get", 403, "twice-unicode", "quota", id="twice-escaped-credential"),
    pytest.param("get", 403, "nested-unicode", "quota", id="nested-escaped-credential"),
    pytest.param("get", 400, "diagnostic-code", "unsupported_parameter", id="non-message-diagnostic"),
])
def test_auth_http_diagnostics_keep_status_not_credentials(monkeypatch, method, status, encoding, diagnostic):
    secret = "test-access-not-real"
    twice = ''.join(r'\\u%04x' % ord(char) for char in secret)
    echoed = secret if encoding == "plain" else twice if encoding == "twice-unicode" else '{"token":"' + ''.join(r'\u%04x' % ord(char) for char in secret) + '"}'
    body = {"error": {"code": "unsupported_parameter", "param": "stream"}} if encoding == "diagnostic-code" else {"error": {"message": diagnostic + " " + echoed}}
    url = CODEX + ("/images/generations" if method == "post" else "/models")
    opener = RecordingOpener(HTTPError(url, status, "denied", {}, HttpReply(json.dumps(body).encode())))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_: opener)
    with pytest.raises(auth.CodexError) as caught:
        if method == "post":
            auth.post_json(url, {}, headers={"Authorization": "Bearer " + secret})
        else:
            auth.get_json(url, headers={"Authorization": "Bearer " + secret})
    error = str(caught.value)
    assert f"HTTP {status}" in error and diagnostic in error
    assert secret not in error.replace('\\', '')
    assert "\\u" not in error
    assert len(opener.requests) == 1
    request, _timeout = opener.requests[0]
    assert request.full_url == url
    if method == "post":
        assert request.get_header("User-agent") == "infinicrafter/1.0"


@pytest.mark.parametrize("output,expected,error", [
    pytest.param([message("I will validate the item first.\n", phase="commentary"),
        {"type": "reasoning", "summary": []}, message('{"item":"Клинок"}', phase="final_answer")],
        '{"item":"Клинок"}', None, id="commentary-not-authored"),
    pytest.param([message('{"status":"working"}', phase="commentary")], None, "text output", id="commentary-only-refused"),
    *[pytest.param([message('{"partial":', phase="final_answer", status=status)], None, "incomplete", id=label)
      for status, label in (("in_progress", "unfinished-final"), ("incomplete", "incomplete-final"))],
    *[pytest.param([{
        "type": "message", "role": "assistant",
        "content": [{"type": "output_text", "text": '{"label":'}, {"type": "output_text", "text": '"Клинок"}'}],
        **({"phase": "final_answer"} if final else {}),
    }], '{"label":"Клинок"}', None, id="final-split-text" if final else "legacy-split-text")
      for final in (False, True)],
    pytest.param([message('', phase="final_answer", content=[
        {"type": "output_text", "text": '{"ok":true}'}, {"type": "refusal", "refusal": "test refusal"},
    ])], None, "refused", id="final-refusal-after-text"),
])
def test_subscription_output_selects_only_completed_final_authored_text(subscription, output, expected, error):
    response, _credentials = subscription
    response["output"] = copy.deepcopy(output)
    before = copy.deepcopy(response)
    request = {"model": "test-model", "messages": [{"role": "user", "content": "test"}]}
    if error:
        with pytest.raises(auth.CodexError, match=error):
            backend.generate_chat(request, timeout=3)
    else:
        text = backend.generate_chat(request, timeout=3)["choices"][0]["message"]["content"]
        assert text == expected
        assert json.loads(text) == json.loads(expected)
    assert response == before


@pytest.mark.parametrize("encoding,commentary", [
    pytest.param("unicode", False, id="legacy-escaped-credential"),
    pytest.param("unicode", True, id="final-escaped-credential"),
    pytest.param("twice-unicode", False, id="twice-escaped-text-credential"),
])
def test_subscription_rejects_encoded_credential_echo(subscription, encoding, commentary):
    response, credentials = subscription
    echo = r'\u0074est-access-not-real' if encoding == "unicode" else ''.join(r'\\u%04x' % ord(char) for char in credentials.access_token)
    response["output"] = ([message("Preparing an answer.", phase="commentary")] if commentary else []) + [message('{"nested":"' + echo + '"}', phase="final_answer" if commentary else None)]
    with pytest.raises(auth.CodexError, match="credential") as caught:
        backend.generate_chat({"model": "test-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
    assert credentials.access_token not in str(caught.value)


@pytest.mark.parametrize("present,value", [
    pytest.param(False, None, id="missing"), pytest.param(True, 168, id="observed-positive"),
    pytest.param(True, 0, id="observed-zero"), pytest.param(True, True, id="bool-is-not-counter"),
])
def test_subscription_cache_instruction_attribution_survives_usage_projection(subscription, present, value, monkeypatch, tmp_path):
    response, credentials = subscription
    response["usage"] = {"input_tokens": 22000, "output_tokens": 120,
        "input_tokens_details": {"cached_tokens": 21000}, "output_tokens_details": {"reasoning_tokens": 100}}
    if present:
        response["usage"]["attribution"] = {"request_fields": {"instructions": {
            "input_tokens": value, "cached_tokens": value, "cache_write_tokens": 0, "output_tokens": 0,
            "metadata": credentials.access_token,
        }}, "items": {credentials.refresh_token: {"input_tokens": 10}}}
    result = backend.generate_chat({"model": "gpt-6.1-sol", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
    diagnostic = llm_provider_wire._usage_fields(result)
    assert diagnostic["reasoningTokens"] == 100
    assert diagnostic["instructionsInputTokens"] == (value if present and type(value) is int and value >= 0 else None)
    assert diagnostic["instructionsCachedInputTokens"] == (value if present and type(value) is int and value >= 0 else None)
    assert diagnostic["instructionsCacheWriteTokens"] == (0 if present else None)
    assert credentials.access_token not in repr(result) and credentials.refresh_token not in repr(result)
    from infini_local.storage import trace_runtime
    monkeypatch.setattr(trace_runtime, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    llm.log_event("info", "LLM usage", diagnostic)
    persisted = json.loads((tmp_path / "events.ndjson").read_text())["payload"]
    assert persisted == diagnostic
    assert credentials.access_token not in repr(persisted) and credentials.refresh_token not in repr(persisted)


@pytest.mark.parametrize("scenario,usage,expected", [
    pytest.param("full", {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
        "input_tokens_details": {"cached_tokens": 100, "cache_write_tokens": 30, "metadata": "test-access-not-real"},
        "output_tokens_details": {"reasoning_tokens": 20, "metadata": "test-refresh-not-real"}},
        {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
         "input_tokens_details": {"cached_tokens": 100, "cache_write_tokens": 30},
         "output_tokens_details": {"reasoning_tokens": 20}}, id="safe-observed-counters"),
    pytest.param("zero", {"input_tokens_details": {"cached_tokens": 0}},
        {"input_tokens_details": {"cached_tokens": 0}}, id="zero-not-missing"),
    pytest.param("metadata", {"input_tokens": True, "input_tokens_details": {"cached_tokens": -1},
        "output_tokens_details": "private", "attribution": {"secret": "test-access-not-real"}},
        {}, id="malformed-counters-and-metadata-removed"),
    pytest.param("missing", {"input_tokens": 7}, {"input_tokens": 7}, id="missing-not-zero"),
])
def test_subscription_usage_is_typed_whitelisted_and_preserved_through_transport(subscription, scenario, usage, expected):
    response, credentials = subscription
    response["usage"] = copy.deepcopy(usage)
    if scenario == "metadata":
        response["id"] = credentials.access_token
    context = {"provider": "openai_codex", "base_url": CODEX, "model": "test-model", "api_mode": "responses", "api_key": ""}
    result = llm._llm_json_single_context(packet(), 3, context)
    assert result["usage"] == expected
    if scenario == "missing":
        assert result["_debug"]["cachedInputTokens"] is None
        assert result["_debug"]["cacheHit"] is None
    for secret in (credentials.access_token, credentials.refresh_token, credentials.account_id):
        assert secret not in repr(result)


@pytest.mark.parametrize("scenario", ["inline-phases", "done-item-phases", "partial-no-completion"])
def test_actual_sse_parser_requires_completion_and_preserves_final_phase(monkeypatch, scenario):
    credentials = auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", 9999999999)
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    items = [message("First I will inspect the schema.\n", phase="commentary"), message('{"ok":true}', phase="final_answer")]
    completion = {"id": "resp-test", "status": "completed", "usage": {"input_tokens_details": {"cached_tokens": 42}}}
    if scenario.startswith("inline"):
        completion["output"] = items
    events = [{"type": "response.output_item.done", "item": item} for item in items]
    if scenario == "partial-no-completion":
        events = [{"type": "response.output_text.delta", "delta": "partial"}]
    if scenario != "partial-no-completion":
        events.append({"type": "response.completed", "response": completion})
    opener = StreamOpener(b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_: opener)
    if scenario == "partial-no-completion":
        with pytest.raises(auth.CodexError, match="before completion"):
            auth.post_sse(backend.RESPONSES_URL, {"stream": True})
    else:
        result = backend.generate_chat({"model": "test-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
        assert result["choices"][0]["message"]["content"] == '{"ok":true}'
        assert result["usage"] == {"input_tokens_details": {"cached_tokens": 42}}
    assert len(opener.requests) == 1
    assert opener.requests[0][0].full_url == backend.RESPONSES_URL
    assert opener.requests[0][0].get_header("Accept") == "text/event-stream"


@pytest.mark.parametrize("scenario,override", [("success", "codex-visual-override"), ("failure", "codex-visual-override")])
def test_subscription_dispatch_strips_foreign_pin_and_never_pays_for_fallback(wire, monkeypatch, subscription, scenario, override):
    response, credentials = subscription
    wire.configure(LLM_PROVIDER="openai_codex", CODEX_LLM_MODEL="test-model", CODEX_VISUAL_REASONING="low",
        OPENAI_COMPAT_BASE_URL="https://api.openai.com/v1", OPENAI_COMPAT_API_KEY="synthetic-paid-key",
        LLM_FALLBACK_PROVIDER="openrouter", LLM_FALLBACK_MODEL="paid-route-not-authorized", LLM_FALLBACK_OPENROUTER_PROVIDER=PIN)
    calls, prepared_calls = [], []
    generate = backend.generate_chat
    monkeypatch.setattr(backend, "generate_chat", lambda payload, timeout: prepared_calls.append(copy.deepcopy(payload)) or generate(payload, timeout=timeout))
    def post(url, body, **options):
        calls.append((url, copy.deepcopy(body), options))
        if scenario == "failure":
            raise auth.CodexError("OpenAI HTTP 429: quota")
        return response
    monkeypatch.setattr(auth, "post_sse", post)
    monkeypatch.setattr(llm, "http_json", lambda *_a, **_k: pytest.fail("paid/legacy HTTP called"))
    request = packet("visual_director")
    request["provider"] = {"only": [PIN], "allow_fallbacks": False}
    request["reasoning"] = {"effort": "high"}
    if override:
        request[llm_provider_wire.LLM_MODEL_OVERRIDE_KEY] = override
    if scenario == "failure":
        with pytest.raises(auth.CodexError, match="429"):
            llm.llm_chat_json(request, timeout=3)
    else:
        result = llm.llm_chat_json(request, timeout=3)
        assert result["choices"][0]["message"]["content"] == '{"ok":true}'
        url, body, options = calls[0]
        assert url == CODEX + "/responses" and body["model"] == (override or "test-model")
        assert body["reasoning"] == {"effort": "low", "summary": "auto"}
        assert body["instructions"] == request["messages"][0]["content"]
        assert body["input"] == [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "JSON response."}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": request["messages"][1]["content"]}]},
        ]
        assert "provider" not in body and llm_provider_wire.LLM_MODEL_OVERRIDE_KEY not in body
    assert len(calls) == len(prepared_calls) == 1
    assert calls[0][0] == CODEX + "/responses"
    assert calls[0][2]["headers"]["Authorization"] == "Bearer " + credentials.access_token
    assert "synthetic-paid-key" not in repr(calls)
    assert "provider" not in prepared_calls[0] and llm_provider_wire.LLM_MODEL_OVERRIDE_KEY not in prepared_calls[0]
    assert prepared_calls[0]["model"] == (override or "test-model")


@pytest.mark.parametrize("scenario", ["literal-stage", "assistant-history", "untranslatable-budget"])
def test_subscription_request_preserves_packet_and_only_supported_wire_options(monkeypatch, subscription_sends, scenario):
    request = {"model": "test-codex-model", "messages": [{"role": "system", "content": "Literal system contract"},
        {"role": "user", "content": "Literal authored item"}], "max_tokens": 2048,
        "response_format": {"type": "json_object"}, "reasoning": {"effort": "low", "exclude": True}, "temperature": 0.38}
    if scenario == "assistant-history":
        request["messages"] = [{"role": "system", "content": "Literal system contract"},
            {"role": "developer", "content": "Literal developer contract"}, {"role": "user", "content": "First request"},
            {"role": "assistant", "content": '{"old":"Клинок"}'}, {"role": "user", "content": "Repair only the invalid field."}]
    if scenario == "untranslatable-budget":
        request["reasoning"] = {"max_tokens": 1500}
        with pytest.raises(auth.CodexError, match="reasoning"):
            backend._request_payload(request)
        return
    response, credentials, calls = subscription_sends
    response["output"] = [message('{"item":"ok"}')]
    response["usage"] = {"input_tokens": 10, "output_tokens": 4}
    before = copy.deepcopy(request)
    result = backend.generate_chat(request, timeout=20)
    assert request == before and result["choices"][0]["message"]["content"] == '{"item":"ok"}'
    assert result["usage"]["output_tokens"] == 4 and len(calls) == 1
    url, body, options = calls[0]
    assert url == CODEX + "/responses" and body["model"] == "test-codex-model"
    assert body["instructions"] == "Literal system contract"
    assert body["input"] == [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "JSON response."}]}] + [{"type": "message", "role": item["role"], "content": [{
        "type": "output_text" if item["role"] == "assistant" else "input_text", "text": item["content"]}]} for item in request["messages"][1:]]
    assert body["reasoning"] == {"effort": "low", "summary": "auto"} and body["text"]["format"] == {"type": "json_object"}
    assert body["stream"] is True and body["store"] is False and body["tools"] == []
    assert "max_output_tokens" not in body and "temperature" not in body
    assert options["headers"]["Authorization"] == "Bearer " + credentials.access_token
    assert options["headers"]["ChatGPT-Account-Id"] == credentials.account_id


@pytest.mark.parametrize("stage,configured,expected", [("visual_director", "high", "low"), ("planner", "high", "high"), ("planner", "max", "max")])
def test_subscription_reasoning_respects_stage_owner_and_catalog_max(wire, monkeypatch, stage, configured, expected):
    wire.configure(LLM_PROVIDER="openai_codex", LLM_REASONING_MODE=configured, CODEX_VISUAL_REASONING="low")
    context = {"provider": "openai_codex", "model": "gpt-6-sol", "base_url": CODEX, "api_mode": "responses", "api_key": ""}
    reasoning = llm_provider_wire.llm_reasoning_payload("gpt-6-sol", context)
    assert reasoning is not None and reasoning["effort"] == configured
    prepared = llm._payload_for_context({"messages": [{"role": "user", "content": "test"}], "reasoning": reasoning, llm_provider_wire.LLM_STAGE_KEY: stage}, context)
    assert prepared["reasoning"]["effort"] == expected
    if configured == "max":
        assert llm_provider_wire.apply_minimum_reasoning_effort({"reasoning": reasoning}, model_name="gpt-6-sol", minimum="medium")["reasoning"]["effort"] == "max"


def test_account_catalog_protocol_discovers_newly_gated_models(monkeypatch, subscription):
    # Offline transport fixture for the observed client-version gate, not a
    # synthesized production model list or an inference entitlement assertion.
    calls = []
    rows = [
        {"slug": "gpt-6-sol", "visibility": "list", "priority": 1},
        {"slug": "gpt-6.1-sol", "visibility": "list", "priority": 0,
         "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}],
         "default_reasoning_level": "low"},
    ]

    def get(url, **options):
        calls.append((url, options))
        version = parse_qs(urlsplit(url).query)["client_version"][0]
        return {"models": rows if tuple(map(int, version.split("."))) >= (0, 161, 0) else rows[:1]}

    monkeypatch.setattr(auth, "get_json", get)
    models = catalog.list_text_models()
    assert [model.slug for model in models] == ["gpt-6.1-sol", "gpt-6-sol"]
    assert models[0].efforts == ("low", "high")
    assert models[0].default_effort == "low"
    assert len(calls) == 1
    assert urlsplit(calls[0][0]).netloc == "chatgpt.com"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-access-not-real"


@pytest.mark.parametrize("scenario", ["visible", "credential-metadata", "empty"])
def test_account_catalog_preserves_declared_models_and_rejects_unsafe_metadata(monkeypatch, subscription, scenario):
    _, credentials = subscription
    if scenario == "visible":
        rows = [{"slug": "hidden-model", "display_name": "Hidden", "visibility": "hide", "priority": 0},
            {"slug": "model-high", "display_name": "High", "visibility": "list", "priority": 10, "supported_in_api": False,
             "default_reasoning_level": "low", "supported_reasoning_levels": [{"effort": "low", "description": "Low"}, {"effort": "high", "description": "High"}]},
            {"slug": "model-first", "display_name": "First", "visibility": "list", "priority": 1, "supported_reasoning_levels": [{"effort": "medium", "description": "Medium"}]},
            {"slug": "model-first", "display_name": "Duplicate", "visibility": "list", "priority": 2}]
    elif scenario == "credential-metadata":
        rows = [{"slug": credentials.access_token, "visibility": "list", "display_name": "unsafe"},
            {"slug": "gpt-safe", "visibility": "list", "display_name": "echo " + credentials.access_token,
             "supported_reasoning_levels": [{"effort": credentials.access_token}, {"effort": "low"}], "default_reasoning_level": credentials.access_token}]
    else:
        rows = [{"slug": "", "visibility": "list"}]
    captured = []
    monkeypatch.setattr(auth, "get_json", lambda url, **options: captured.append((url, options)) or {"models": rows})
    if scenario == "empty":
        with pytest.raises(auth.CodexError):
            catalog.list_text_models()
    else:
        models = catalog.list_text_models()
        assert [item.slug for item in models] == (["model-first", "model-high"] if scenario == "visible" else ["gpt-safe"])
        selected = models[-1]
        assert selected.efforts == (("low", "high") if scenario == "visible" else ("low",))
        assert selected.default_effort == ("low" if scenario == "visible" else "")
        if scenario == "credential-metadata":
            assert selected.label == "gpt-safe" and credentials.access_token not in repr(models)
    assert len(captured) == 1 and captured[0][0] == catalog.MODELS_URL + "?client_version=" + catalog.CLIENT_VERSION
    assert captured[0][1]["headers"]["Authorization"] == "Bearer test-access-not-real"
    assert captured[0][1]["headers"]["ChatGPT-Account-Id"] == credentials.account_id
    assert "api.openai.com" not in captured[0][0]


def test_expired_session_refreshes_once_under_concurrent_requests(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    path = tmp_path / "codex-auth.json"
    fresh = auth.credentials_from_response(token_response())
    auth.save_credentials(replace(fresh, expires_at=1), path)
    calls = []
    def post(url, payload, **kwargs):
        calls.append((url, payload))
        return {**token_response(), "refresh_token": "test-rotated-not-real"}
    monkeypatch.setattr(auth, "post_json", post)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: auth.get_credentials(path), range(4)))
    assert len(calls) == 1
    assert calls[0][0] == "https://auth.openai.com/oauth/token"
    assert calls[0][1]["grant_type"] == "refresh_token"
    assert all(c.refresh_token == "test-rotated-not-real" for c in values)
    assert auth.load_credentials(path) == values[0]


def test_browser_login_exchanges_pkce_once_and_saves_only_after_callback(tmp_path, monkeypatch):
    import threading
    from urllib.request import urlopen
    from urllib.error import HTTPError
    path = tmp_path / "codex-auth.json"
    calls, threads, callback_results = [], [], []
    def post(url, payload, **kwargs):
        calls.append(payload)
        assert payload["grant_type"] == "authorization_code"
        assert payload["code"] == "test-code"
        assert len(payload["code_verifier"]) >= 43
        return token_response()
    monkeypatch.setattr(auth, "post_json", post)
    def visit(url):
        assert not path.exists()
        params = parse_qs(urlsplit(url).query)
        callback = params["redirect_uri"][0]
        def send():
            try:
                urlopen(callback + "?state=wrong&code=test-code", timeout=5)
            except HTTPError as exc:
                callback_results.append(exc.code)
            with urlopen(callback + "?state=" + params["state"][0] + "&code=test-code", timeout=5) as response:
                callback_results.append(response.status)
        thread = threading.Thread(target=send)
        threads.append(thread)
        thread.start()
    auth.login(path=path, on_url=visit, open_browser=False, port=0, timeout=10)
    for thread in threads:
        thread.join(5)
    assert callback_results == [400, 200]
    assert len(calls) == 1
    assert auth.auth_status(path)["authenticated"]


def test_authorization_code_exchange_uses_native_form_encoding(monkeypatch):
    opener = RecordingOpener(HttpReply(b'{"ok": true}'))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: opener)
    assert auth.post_json(auth.TOKEN_URL, {"code": "test+code", "grant_type": "authorization_code"}, form=True) == {"ok": True}
    assert len(opener.requests) == 1
    request, _timeout = opener.requests[0]
    assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
    assert parse_qs(request.data.decode()) == {"code": ["test+code"], "grant_type": ["authorization_code"]}


def test_sse_rejects_late_completion_and_bounds_each_socket_read(monkeypatch):
    import io
    event = b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
    clock = [0.0]
    def advance(seconds):
        clock[0] += seconds
    # Codex and HTTP I/O share this time module. Only reads spend the budget,
    # so scheduler delays cannot expire it before the fake opener is reached.
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(auth.time, "sleep", advance)
    socket_limits, read_lines, opens = [], [], []
    read_delays = iter((0.005, 0.04))
    class Socket:
        def settimeout(self, value):
            socket_limits.append(value)
    class Response(io.BytesIO):
        def __init__(self):
            super().__init__(event)
            from types import SimpleNamespace
            self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=Socket()))
        def readline(self, *args, **kwargs):
            assert len(socket_limits) == len(read_lines) + 1
            # The data line is on time, but the completion delimiter is late.
            time.sleep(next(read_delays))
            line = super().readline(*args, **kwargs)
            read_lines.append(line)
            return line
    class Opener:
        def open(self, request, timeout):
            opens.append(timeout)
            assert clock[0] == 0.0
            return Response()
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    with pytest.raises(auth.CodexError, match="timed out"):
        auth.post_sse("https://chatgpt.com/backend-api/codex/responses", {"stream": True}, timeout=0.02)
    assert opens == pytest.approx([0.02])
    assert read_lines == event.splitlines(keepends=True)
    assert socket_limits == pytest.approx([0.02, 0.015])
    assert all(0 < value <= 0.02 for value in socket_limits)
    assert clock[0] == pytest.approx(0.045)


def test_bounded_catalog_get_uses_only_codex_origin_and_redacts_errors(monkeypatch):
    key = "test-access-not-real"
    url = "https://chatgpt.com/backend-api/codex/models?client_version=0.4.241"
    error_body = json.dumps({"error": {"message": "denied " + key}}).encode()
    opener = RecordingOpener(HttpReply(b'{"models": []}'), HTTPError(url, 403, "denied", {}, HttpReply(error_body)))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: opener)
    headers = {"Authorization": "Bearer " + key}
    assert auth.get_json(url, headers=headers, timeout=3, limit=128) == {"models": []}
    assert opener.requests[0][0].get_method() == "GET"
    with pytest.raises(auth.CodexError, match="HTTP 403") as caught:
        auth.get_json(url, headers=headers, timeout=3, limit=128)
    assert key not in str(caught.value)
    with pytest.raises(auth.CodexError):
        auth.get_json("https://api.openai.com/v1/models", headers=headers)
    assert len(opener.requests) == 2
    assert all(timeout == 3 for _request, timeout in opener.requests)


def test_native_session_roundtrip_is_private_and_status_has_no_secrets(tmp_path):
    path = tmp_path / "codex-auth.json"
    credentials = auth.credentials_from_response(token_response())
    auth.save_credentials(credentials, path)
    loaded = auth.load_credentials(path)
    assert loaded == credentials
    assert credentials.access_token not in repr(credentials)
    status = auth.auth_status(path)
    assert status == {"authenticated": True, "expired": False}
    assert "test-refresh" not in json.dumps(status)
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    auth.logout(path)
    assert auth.auth_status(path) == {"authenticated": False, "expired": False}


@pytest.mark.parametrize("color,remove_bg,mode,background", [
    ("magenta", True, "sprite_keyer", "opaque"),
    ("white", True, "sprite_keyer", "opaque"),
    ("transparent", True, "sprite_keyer", "transparent"),
    ("transparent", False, "sprite_keyer", "transparent"),
    ("cyan", False, "sprite_keyer", "transparent"),
    ("magenta", True, "off", "transparent"),
])
def test_codex_dispatch_writes_verified_png_and_preserves_authored_prompt(tmp_path, monkeypatch, color, remove_bg, mode, background):
    from infini_local.pipelines import pipeline_visual_config as visual_config
    monkeypatch.setattr(visual_config, "BG_COLOR", color)
    monkeypatch.setattr(visual_config, "REMOVE_BG", remove_bg)
    monkeypatch.setattr(visual_config, "BG_REMOVE_MODE", mode)
    assert "openai_codex" in config.SUPPORTED_IMAGE_BACKENDS
    assert config.IMAGE_BACKEND_ALIASES.get("openai_codex", "openai_codex") != "image_api"
    import base64
    import contextlib
    import io
    import time
    from PIL import Image
    from infini_local.pipelines import image_backend_pipeline as backend, visual_sprite_generation as visual
    from infini_local.services import codex_auth as auth
    assert hasattr(backend, "generate_openai_codex"), "Codex is not connected to sprite dispatch"
    stream = io.BytesIO()
    Image.new("RGBA", (64, 64), (15, 120, 240, 255)).save(stream, format="PNG")
    calls, gate = [], []
    credentials = auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", time.time() + 3600)
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    def post(url, payload, **kwargs):
        assert gate == ["entered"]
        calls.append((url, payload, kwargs))
        return {"data": [{"b64_json": base64.b64encode(stream.getvalue()).decode()}]}
    monkeypatch.setattr(auth, "post_json", post)
    monkeypatch.setattr(backend, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 1)
    monkeypatch.setattr(visual, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(visual, "IMAGE_BACKEND_CONFIG_ERROR", "")
    class Gate:
        @contextlib.contextmanager
        def slot(self):
            gate.append("entered")
            yield
            gate.append("exited")
    monkeypatch.setattr(visual, "IMAGE_GENERATION_GATE", Gate())
    for name in ("generate_image_api", "generate_sdcpp"):
        monkeypatch.setattr(visual, name, lambda *a: (_ for _ in ()).throw(AssertionError("unexpected fallback")))
    paths = visual._generate_backend_variants({}, prompt="Literal authored предмет", negative="no text", asset_id="test-item", canvas=32, role="item")
    assert gate == ["entered", "exited"]
    assert len(paths) == 1
    assert Image.open(paths[0]).format == "PNG"
    url, payload, options = calls[0]
    assert url == "https://chatgpt.com/backend-api/codex/images/generations"
    assert payload == {"model": "gpt-image-2", "prompt": "Literal authored предмет\n\nAvoid: no text", "n": 1, "quality": "medium", "size": "1024x1024", "background": background}
    assert options["headers"]["Authorization"] == "Bearer " + credentials.access_token
    assert options["headers"]["ChatGPT-Account-Id"] == credentials.account_id
    assert "response_format" not in payload


def test_codex_auth_error_is_not_retried_or_replaced_by_procedural(monkeypatch):
    from infini_local.pipelines import visual_sprite_generation as visual
    from infini_local.services.codex_auth import CodexError
    calls, fallbacks = [], []
    def fail(*args, **kwargs):
        calls.append(args)
        raise CodexError("OpenAI HTTP 429: quota reached")
    monkeypatch.setattr(visual, "generate_openai_codex", fail)
    monkeypatch.setattr(visual, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(visual, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(visual, "SPRITE_RETRIES", 3)
    monkeypatch.setattr(visual, "VISUAL_ALLOW_PROCEDURAL_FALLBACK", True)
    monkeypatch.setattr(visual, "VISUAL_STRICT_AI_AUTHORSHIP", False)
    monkeypatch.setattr(visual, "normalize_asset_prompt", lambda data, role, prompt, canvas, **kwargs: prompt)
    monkeypatch.setattr(visual.visual_asset_pipeline, "generate_procedural_asset", lambda *a, **kw: fallbacks.append(True))
    data = {"id": "test", "visual": {"imagePrompt": "authored sprite"}}
    visual.maybe_generate_sprite(data)
    assert data["visual"]["spriteStatus"] == "failed"
    assert len(calls) == 1
    assert not fallbacks
    result = visual.generate_visual_asset({}, "entity_shot", "authored shot", "", "shot", 32)
    assert result[3] == "failed"
    assert len(calls) == 2
    assert not fallbacks


@pytest.mark.parametrize("cache_key", [None, "infini-static-prefix", "unicode-кэш", "key\r\nextra: value"])
def test_subscription_cache_affinity_reaches_native_session_header(subscription_sends, monkeypatch, cache_key):
    from urllib.parse import quote
    response, credentials, sent = subscription_sends
    packet = {"model": "test-model", "messages": [{"role": "user", "content": "recipe one"}]}
    if cache_key is not None:
        packet["prompt_cache_key"] = cache_key
    original = copy.deepcopy(packet)
    for content in ("recipe one", "recipe two"):
        packet["messages"][0]["content"] = content
        backend.generate_chat(packet, timeout=3)
    assert len(sent) == 2 and sent[0][1] != sent[1][1]
    for url, body, options in sent:
        assert url == backend.RESPONSES_URL and options["timeout"] == 3
        headers = options["headers"]
        assert headers["Authorization"] == "Bearer " + credentials.access_token
        assert headers["ChatGPT-Account-Id"] == credentials.account_id
        assert headers["originator"] == "infinicrafter"
        assert "thread-id" not in headers  # No fabricated conversation identity.
        if cache_key is None:
            assert "session-id" not in headers and "prompt_cache_key" not in body
        else:
            assert headers["session-id"] == quote(cache_key, safe="")
            assert "\r" not in headers["session-id"] and "\n" not in headers["session-id"]
            assert headers["session-id"].isascii()
            assert body["prompt_cache_key"] == cache_key
    packet["messages"][0]["content"] = original["messages"][0]["content"]
    assert packet == original
