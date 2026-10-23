"""Offline routing, deadlines, retries and concurrent request ownership.

Named scenarios cover distinct external behavior, not stage/API/lease products.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler
import time
import copy
from email.message import Message
import io
import json
import threading
import urllib.error
from types import SimpleNamespace

import pytest

from provider_test_support import HttpReply, HttpSender, physical_attempt, loopback_server, write_json_response

from infini_local.pipelines import llm_admission
from infini_local.core import llm_config
from infini_local.pipelines import llm_profiles
from infini_local.pipelines import llm_provider_wire
from provider_test_support import reset_llm_runtime
from infini_local.pipelines import llm_transport as transport

PIN = "ExactVendor/Endpoint-Turbo"
STAGES = ("planner", "visual_director", "vfx_director")


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_provider_json_byte_limit_rejects_overflow_without_truncation(loopback_transport, monkeypatch, method):
    from infini_local.core.http_io import HttpResponseTooLarge
    endpoint, _events = loopback_transport
    body = {"value": "x" * 256}
    encoded = json.dumps(body).encode()
    base, _observed = endpoint([{"body": body}, {"body": body}])
    send = (lambda: transport.http_get_json(base + "/models")) if method == "GET" else (
        lambda: transport.http_json(base + "/chat/completions", {"model": "test"}))
    monkeypatch.setattr(transport, "MAX_PROVIDER_JSON_BYTES", len(encoded))
    assert send() == body
    monkeypatch.setattr(transport, "MAX_PROVIDER_JSON_BYTES", len(encoded) - 1)
    with pytest.raises(HttpResponseTooLarge):
        send()


def packet(stage="planner", *, schema=False):
    response_format = {"type": "json_object"}
    if schema:
        response_format = {"type": "json_schema", "json_schema": {
            "name": "pin_probe", "strict": True,
            "schema": {"type": "object", "properties": {}, "additionalProperties": False},
        }}
    return llm_provider_wire.with_llm_stage({
        "model": "ignored",
        "messages": [
            {"role": "system", "content": f"{stage} instructions"},
            {"role": "user", "content": '{"currentItem":{"name":"Probe"}}'},
        ],
        "max_tokens": 321, "temperature": 0.2, "response_format": response_format,
    }, stage)


def http_error(url, code, body="provider rejected request"):
    return urllib.error.HTTPError(url, code, "synthetic failure", Message(), io.BytesIO(body.encode()))


def schema_error(url):
    body = json.dumps({"error": {"code": "unsupported_response_format", "param": "response_format",
                               "message": "INVALID_ARGUMENT: json_schema response_format is not supported"}})
    error = http_error(url, 400, body)
    error._infini_body = body
    return error


class Wire:
    """Recording offline HTTP double; replies are data, never assertion callbacks."""
    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.calls = []
        self.replies = deque()

    def configure(self, **values):
        for name, value in values.items():
            self.monkeypatch.setattr(llm_config, name, value)
        reset_llm_runtime()

    def __call__(self, url, payload, timeout=10, headers=None):
        self.calls.append((url, copy.deepcopy(payload), dict(headers or {})))
        reply = self.replies.popleft() if self.replies else None
        if isinstance(reply, int):
            raise http_error(url, reply)
        if isinstance(reply, Exception):
            raise reply
        if reply is not None:
            return copy.deepcopy(reply)
        usage = {"input_tokens": 100, "output_tokens": 5,
                 "input_tokens_details": {"cached_tokens": 40}}
        if url.endswith("/responses"):
            return {"id": f"resp_{len(self.calls)}", "status": "completed", "output_text": "{}", "usage": usage}
        return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}], "usage": usage}


@pytest.fixture
def wire(monkeypatch):
    recorder = Wire(monkeypatch)
    recorder.configure(
        LLM_PROVIDER="openrouter", LLM_API_MODE="chat_completions",
        OPENROUTER_BASE_URL="https://primary.example/api/v1", OPENROUTER_MODEL="vendor/model",
        OPENROUTER_API_KEY="synthetic-primary-key", OPENROUTER_PROVIDER=PIN,
        OPENAI_COMPAT_BASE_URL="https://primary.example/v1", OPENAI_COMPAT_MODEL="primary-model",
        OPENAI_COMPAT_API_KEY="synthetic-compat-key", LMSTUDIO_URL="http://primary.local:1234",
        LMSTUDIO_MODEL="primary-local", LLM_POOL_PROFILES=(), LLM_FALLBACK_PROVIDER="",
        LLM_FALLBACK_MODEL="", LLM_FALLBACK_BASE_URL="", LLM_FALLBACK_API_KEY="",
        LLM_FALLBACK_OPENROUTER_PROVIDER="", LLM_FALLBACK_NETWORK_FAILS=2,
    )
    monkeypatch.delenv("INFINI_LLM_REPLAY_RAW", raising=False)
    monkeypatch.setattr(transport, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(transport, "http_json", recorder)
    monkeypatch.setattr(transport, "http_get_json", lambda *_args, **_kwargs: pytest.fail("unexpected model discovery"))
    yield recorder
    reset_llm_runtime()


@pytest.fixture
def loopback_transport(monkeypatch):
    """Actual urllib I/O; replies describe bytes/status, not assertion callbacks."""
    events = []
    recorder = Wire(monkeypatch)
    recorder.configure(
        LLM_PROVIDER="openrouter", LLM_API_MODE="chat_completions",
        OPENROUTER_MODEL="vendor/model", OPENROUTER_API_KEY="synthetic-loopback-key",
        OPENROUTER_PROVIDER=PIN, LLM_POOL_PROFILES=(), LLM_FALLBACK_MODEL="",
        LLM_FALLBACK_NETWORK_FAILS=2,
    )
    monkeypatch.delenv("INFINI_LLM_REPLAY_RAW", raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setattr(transport, "log_event", lambda level, message, data=None:
                        events.append((message, copy.deepcopy(data or {}))))

    @contextmanager
    def endpoint(replies=()):
        observed, remaining = [], deque(replies)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def respond(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                body = json.loads(raw) if raw else None
                observed.append((self.command, self.path, body, self.headers.get("Authorization")))
                reply = remaining.popleft() if remaining else {}
                if self.path.endswith("/models"):
                    default = {"data": [{"id": "vendor/advertised:free"}]}
                elif self.path.endswith("/responses"):
                    default = {"id": "response-loopback", "output_text": "{}", "status": "completed"}
                else:
                    default = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
                write_json_response(self, reply.get("body", default), **{
                    key: value for key, value in reply.items() if key != "body"
                })

            do_POST = do_GET = respond

        with loopback_server(Handler) as server:
            yield f"http://127.0.0.1:{server.server_port}", observed

    with ExitStack() as stack:
        def make_endpoint(replies=()):
            return stack.enter_context(endpoint(replies))
        yield make_endpoint, events
    reset_llm_runtime()


@pytest.mark.parametrize("kind,status", [
    pytest.param("chat_completions", 200, id="same-origin-success"),
    pytest.param("chat_completions", 302, id="chat-redirect-refused"),
    pytest.param("responses", 307, id="responses-redirect-refused"),
    pytest.param("models", 308, id="catalog-redirect-refused"),
])
def test_real_http_redirects_fail_closed_without_forwarding_bearer_or_adopting_foreign_reply(
    loopback_transport, monkeypatch, kind, status,
):
    endpoint, _events = loopback_transport
    foreign_url, foreign = endpoint()
    redirected_path = "/v1/models" if kind == "models" else (
        "/v1/responses" if kind == "responses" else "/v1/chat/completions")
    source_url, observed = endpoint([{"status": status, "headers": {"Location": foreign_url + redirected_path}}])
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", source_url)
    monkeypatch.setattr(llm_config, "LLM_API_MODE", "chat_completions" if kind == "models" else kind)
    if kind == "models":
        monkeypatch.setattr(llm_config, "OPENROUTER_MODEL", "auto")
        resolved = transport.resolve_llm_model()
        assert resolved == ("vendor/advertised:free" if status == 200 else "")
    else:
        with llm_profiles.llm_item_lease("redirect-policy") as lease:
            if status == 200:
                result = transport.llm_chat_json(packet(), timeout=1)
                assert result["choices"][0]["message"]["content"] == "{}"
            else:
                with pytest.raises(urllib.error.HTTPError) as caught:
                    transport.llm_chat_json(packet(), timeout=1)
                assert caught.value.code == status
            assert lease.profile_id == "llm_1" and not lease.failovers
            assert lease.call_count == 1
    assert foreign == []
    assert len(observed) == 1
    method, path, body, auth = observed[0]
    assert method == ("GET" if kind == "models" else "POST")
    assert auth == "Bearer synthetic-loopback-key"
    if body is not None:
        assert body["provider"] == {"only": [PIN], "allow_fallbacks": False}


@pytest.mark.parametrize("phase", ["fast", "body", "headers", "error_body", "retry"])
def test_real_http_deadline_covers_trickle_headers_error_body_and_retry(loopback_transport, monkeypatch, phase):
    endpoint, _events = loopback_transport
    budget = 0.18
    replies = {
        "fast": [{}], "body": [{"trickle": 0.005}], "headers": [{"header_trickle": 0.003}],
        "error_body": [{"status": 400, "body": {"error": {"message": "synthetic message rejection"}}, "trickle": 0.005}],
        "retry": [{"status": 503, "before_headers": 0.11}, {"before_headers": 0.11}],
    }[phase]
    base, observed = endpoint(replies)
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", base)
    started = time.monotonic()
    with llm_profiles.llm_item_lease("whole-call-deadline") as lease:
        if phase == "fast":
            result = transport.llm_chat_json(packet(), timeout=budget)
            assert result["choices"][0]["message"]["content"] == "{}"
        else:
            with pytest.raises(TimeoutError):
                transport.llm_chat_json(packet(), timeout=budget)
        elapsed = time.monotonic() - started
        assert elapsed < budget + 0.15
        assert lease.call_count == 1 and not lease.failovers
    assert len(observed) == 1  # A spent budget must not start another physical request.


@pytest.mark.parametrize("reason", ["pacing", "provider_429"])
def test_deadline_prevents_sending_after_rate_wait(loopback_transport, rate_clock, monkeypatch, reason):
    endpoint, _events = loopback_transport
    base, observed = endpoint()
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(llm_admission, "_remote_rate_key", lambda *_args: "synthetic-rate-key")
    now = rate_clock.now
    llm_admission._LLM_RATE_STATE["synthetic-rate-key"] = {
        "events": [], "lastRequest": now if reason == "pacing" else -1.0e30,
        "blockedUntil": now + 10 if reason == "provider_429" else 0,
    }
    # Spend exactly the logical budget; host scheduling must not decide whether
    # a request was incorrectly admitted after the deadline.
    assert rate_clock.start("expired-admission", lambda: transport.llm_chat_json(packet(), timeout=0.18)) == "waiting"
    assert rate_clock.parked["expired-admission"] == pytest.approx(0.18)
    assert rate_clock.step("expired-admission", now + 0.18) == "done"
    error = rate_clock.results["expired-admission"]
    assert isinstance(error, TimeoutError)
    assert error._infini_transport_debug["physicalAttemptCount"] == 0
    assert error._infini_transport_debug["physicalAttempts"] == []
    assert observed == []
    assert llm_admission._LLM_RATE_STATE["synthetic-rate-key"]["events"] == []
    assert llm_admission._LLM_RATE_STATE["synthetic-rate-key"]["waiters"] == []


@pytest.mark.parametrize("oversized", [False, True])
def test_shared_http_read_returns_exact_bytes_or_refuses_byte_overflow(loopback_transport, oversized):
    from infini_local.core import http_io
    endpoint, _events = loopback_transport
    base, observed = endpoint([{"body": {"value": "loopback"}}])
    deadline = time.monotonic() + 1
    with http_io.urlopen_no_redirect(transport.urlrequest.Request(base), deadline=deadline) as response:
        if oversized:
            with pytest.raises(http_io.HttpResponseTooLarge):
                http_io.read_with_deadline(response, deadline=deadline, max_bytes=3)
        else:
            raw = http_io.read_with_deadline(response, deadline=deadline, max_bytes=100)
            assert raw == json.dumps({"value": "loopback"}).encode()
    assert len(observed) == 1


@pytest.mark.parametrize("outcome", ["recovered", "fatal", "bounded"])
def test_real_http_physical_attempt_timeline_is_bounded_safe_and_survives_failure(loopback_transport, monkeypatch, outcome):
    endpoint, events = loopback_transport
    secret = "synthetic-loopback-key"
    rejection = {"error": {"code": "unsupported_response_format", "param": "response_format",
        "message": "json_schema response_format is not supported: " + secret}}
    escaped = json.dumps(rejection).replace(secret, r"\u0073ynthetic-loopback-key")
    final = {"status": 400, "body": {"error": {"code": "context_length_exceeded", "param": "messages"}}} if outcome == "fatal" else {
        "body": {"choices": [{"message": {"content": "{}"}}],
                 "_debug": {"credential": secret, "promptEcho": "PRIVATE_AUTHOR_PACKET"}}}
    base, observed = endpoint([{"status": 404}, {"status": 400, "raw_body": escaped}, final])
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(llm_config, "LLM_API_MODE", "auto")
    if outcome == "bounded":
        monkeypatch.setattr(transport, "_LLM_MAX_DIAGNOSTIC_ATTEMPTS", 2)
    request = packet(schema=True)
    request["messages"][1]["content"] = "PRIVATE_AUTHOR_PACKET"
    with llm_profiles.llm_item_lease("physical-attribution") as lease:
        if outcome == "fatal":
            with pytest.raises(urllib.error.HTTPError) as caught:
                transport.llm_chat_json(request, timeout=1)
            debug = caught.value._infini_transport_debug
        else:
            result = transport.llm_chat_json(request, timeout=1)
            assert result["choices"][0]["message"]["content"] == "{}"
            debug = result["_debug"]
        assert lease.call_count == 1
    assert len(observed) == debug["physicalAttemptCount"] == 3
    attempts = debug["physicalAttempts"]
    assert len(attempts) == (2 if outcome == "bounded" else 3)
    assert debug["physicalAttemptsDropped"] == (1 if outcome == "bounded" else 0)
    expected_statuses = [404, 400, 400 if outcome == "fatal" else 200]
    assert [row["httpStatus"] for row in attempts] == expected_statuses[:len(attempts)]
    assert len({row["logicalCallId"] for row in attempts}) == 1
    assert all(row["networkStarted"] and row["connectMs"] is None for row in attempts)
    serialized = json.dumps([events, debug])
    assert secret not in serialized and "PRIVATE_AUTHOR_PACKET" not in serialized
    assert r"\u0073ynthetic-loopback-key" not in serialized and "Authorization" not in serialized
    assert all(not {"messages", "body", "headers"} & row.keys() for row in attempts)


def test_real_http_429_timeline_distinguishes_one_send_from_unsent_cooldown(loopback_transport, monkeypatch):
    endpoint, events = loopback_transport
    base, observed = endpoint([{"status": 429, "headers": {"Retry-After": "60"}}])
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(llm_admission, "_remote_rate_key", lambda *_args: "synthetic-rate-key")
    with pytest.raises(TimeoutError) as caught:
        transport.llm_chat_json(packet(), timeout=0.45)
    debug = caught.value._infini_transport_debug
    assert len(observed) == debug["physicalAttemptCount"] == len(debug["physicalAttempts"]) == 1
    assert debug["physicalAttempts"][0]["httpStatus"] == 429
    assert debug["rateWaitReason"] == "provider_cooldown" and debug["rateWaitMsTotal"] > 0
    physical = [data for message, data in events if message == "LLM physical attempt"]
    waits = [data for message, data in events if message == "LLM transport wait"]
    assert len(physical) == len(waits) == 1
    assert waits[0]["networkStarted"] is False and waits[0]["physicalAttemptIndex"] is None
    assert waits[0]["logicalCallId"] == physical[0]["logicalCallId"]


@pytest.mark.parametrize("rejection", ["messages", "endpoint_recovered", "endpoint_failed"])
def test_real_http_responses_learning_does_not_cache_content_failure_or_failed_recovery(loopback_transport, rejection):
    endpoint, _events = loopback_transport
    if rejection == "messages":
        replies = [{"status": 400, "body": {"error": {"code": "context_length_exceeded", "param": "input"}}}, {}]
    else:
        replies = [{"status": 404, "body": {"error": {"message": "Responses endpoint not supported"}}}]
        replies += ([{"status": 400, "body": {"error": {"code": "context_length_exceeded", "param": "messages"}}}] if rejection == "endpoint_failed" else [{}])
        replies.append({})
    base, observed = endpoint(replies)
    context = {"provider": "openrouter", "openrouter_provider": PIN, "model": "vendor/model",
               "base_url": base, "api_mode": "auto", "api_key": "synthetic-loopback-key"}
    if rejection == "endpoint_recovered":
        transport._llm_json_single_context(packet(), 1, context)
    else:
        with pytest.raises(urllib.error.HTTPError):
            transport._llm_json_single_context(packet(), 1, context)
    transport._llm_json_single_context(packet(), 1, context)
    assert [path.rsplit("/", 1)[-1] for _, path, _, _ in observed] == {
        "messages": ["responses", "responses"],
        "endpoint_recovered": ["responses", "completions", "completions"],
        "endpoint_failed": ["responses", "completions", "responses"],
    }[rejection]


@pytest.mark.parametrize("expired", [False, True], ids=["valid-failover-control", "deadline-does-not-switch-lease"])
def test_real_http_failover_keeps_one_budget_and_does_not_escape_after_expiry(loopback_transport, monkeypatch, expired):
    endpoint, events = loopback_transport
    secondary, secondary_calls = endpoint()
    source, source_calls = endpoint([{"status": 503, **({"trickle": 0.005} if expired else {})}])
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", source)
    monkeypatch.setattr(llm_config, "OPENROUTER_PROVIDER", "")
    monkeypatch.setattr(llm_config, "LLM_POOL_PROFILES", ({"id": "llm_2", "enabled": True,
        "provider": "openrouter", "base_url": secondary, "model": "vendor/secondary",
        "api_mode": "chat_completions", "api_key": "synthetic-loopback-key", "openrouter_provider": PIN},))
    with llm_profiles.llm_item_lease("deadline-failover") as lease:
        if expired:
            with pytest.raises(TimeoutError) as caught:
                transport.llm_chat_json(packet(), timeout=0.18)
            assert lease.profile_id == "llm_1" and lease.failovers == []
            debug = caught.value._infini_transport_debug
            assert debug["physicalAttemptCount"] == 1
        else:
            result = transport.llm_chat_json(packet(), timeout=1)
            assert result["_debug"]["physicalAttemptCount"] == 2
            assert lease.profile_id == "llm_2" and len(lease.failovers) == 1
            attempts = [data for message, data in events if message == "LLM physical attempt"]
            assert [row["reason"] for row in attempts] == ["initial", "profile_failover"]
        assert lease.call_count == 1
    assert len(source_calls) == 1 and len(secondary_calls) == (0 if expired else 1)


@pytest.mark.parametrize("failure", [False, True], ids=["subscription-success", "subscription-failure"])
def test_codex_stream_boundary_reports_only_owned_observations_without_generic_http_or_fallback(wire, monkeypatch, failure):
    from infini_local.services import codex_text_backend as codex
    from infini_local.services.codex_auth import CodexError
    wire.configure(LLM_PROVIDER="openai_codex", CODEX_LLM_MODEL="gpt-5.4", LLM_API_MODE="responses",
                   LLM_FALLBACK_PROVIDER="openrouter", LLM_FALLBACK_MODEL="must-not-be-used")
    seen = []
    def generate(prepared, *, timeout):
        seen.append((copy.deepcopy(prepared), timeout))
        if failure:
            raise CodexError("synthetic subscription quota error")
        return {"choices": [{"message": {"content": "{}"}}], "_debug": {"apiMode": "codex_subscription_sse", "provider": "openai_codex"}}
    monkeypatch.setattr(codex, "generate_chat", generate)
    request = packet()
    request["reasoning"] = {"effort": "high", "exclude": True}
    before = copy.deepcopy(request)
    with llm_profiles.llm_item_lease("codex-boundary") as lease:
        if failure:
            with pytest.raises(CodexError) as caught:
                transport.llm_chat_json(request, timeout=1)
            debug = caught.value._infini_transport_debug
        else:
            debug = transport.llm_chat_json(request, timeout=1)["_debug"]
        assert lease.call_count == 1 and lease.profile_id == "llm_1" and lease.failovers == []
    assert len(seen) == 1 and 0 < seen[0][1] <= 1
    assert wire.calls == [] and request == before
    assert debug["effectiveApiMode"] == "codex_subscription_sse"
    assert debug["effectiveResponseFormat"] == "json_object"
    assert debug["effectiveReasoning"] == {"effort": "high"}
    assert debug["physicalAttemptCount"] is None  # Subscription/auth I/O is another owner's observation.
    assert debug["physicalAttempts"] == []


def assert_responses_dossier(body, request):
    assert body["instructions"] == request["messages"][0]["content"]
    assert body["input"] == [request["messages"][1]]
    assert body["text"] == {"format": request["response_format"]}
    assert body["max_output_tokens"] == request["max_tokens"]


@pytest.mark.parametrize("provider,pin,mode", [
    pytest.param("openrouter", PIN, "chat_completions", id="pinned-chat"),
    pytest.param("openrouter", "", "responses", id="automatic-responses"),
    pytest.param("local", PIN, "chat_completions", id="local-ignores-stale-pin"),
    pytest.param("openai_compat", PIN, "auto", id="compat-negotiates-without-router-pin"),
])
def test_profile_routing_wire(wire, provider, pin, mode):
    wire.configure(LLM_PROVIDER=provider, OPENROUTER_PROVIDER=pin, LLM_API_MODE=mode)
    request = packet()
    request["provider"] = {"only": ["WrongVendor"], "allow_fallbacks": True}
    request["reasoning"] = {"effort": "low"}
    before = copy.deepcopy(request)
    result = transport.llm_chat_json(request, timeout=1)
    assert len(wire.calls) == 1
    url, body, headers = wire.calls[0]
    pinned = provider == "openrouter" and bool(pin.strip())
    assert body.get("provider") == ({"only": [PIN], "allow_fallbacks": False} if pinned else None)
    assert request == before
    assert result["choices"][0]["message"]["content"] == "{}"
    assert result["_debug"]["openrouterProvider"] == (PIN if pinned else "")
    assert body["temperature"] == 0.2
    if provider == "openrouter":
        assert headers["Authorization"] == "Bearer synthetic-primary-key"
        assert body["model"] == "vendor/model"
    else:
        assert ("Authorization" in headers) is (provider == "openai_compat")
        assert ("reasoning" in body) is (provider == "openai_compat")
    if url.endswith("/responses"):
        assert_responses_dossier(body, request)
    else:
        expected = {key: value for key, value in request.items() if key not in {llm_provider_wire.LLM_STAGE_KEY, "provider"}}
        expected["model"] = body["model"]
        if pinned:
            expected["provider"] = {"only": [PIN], "allow_fallbacks": False}
        if provider == "local":
            expected.pop("reasoning")
        assert body == expected
        if provider == "openrouter":
            assert url == "https://primary.example/api/v1/chat/completions"


@pytest.mark.parametrize("preferred", [False, True], ids=["round-robin", "explicit-lane"])
def test_profile_selection_persists_for_every_stage(wire, preferred):
    profiles = tuple({"id": f"llm_{index}", "enabled": True, "provider": "openai_compat",
        "base_url": f"https://{label}.example/v1", "api_key": label, "model": f"model-{label}",
        "api_mode": "chat_completions"} for index, label in ((2, "two"), (3, "three")))
    if preferred:
        profiles = ({**profiles[0], "provider": "openrouter", "openrouter_provider": "PreferredVendor/Endpoint"},)
    wire.configure(LLM_PROVIDER="openai_compat", OPENAI_COMPAT_BASE_URL="https://one.example/v1",
                   OPENAI_COMPAT_MODEL="model-one", LLM_POOL_PROFILES=profiles)
    selected = []
    for recipe in ("r1", "r2", "r3", "r4"):
        lease, token = llm_profiles.begin_llm_item_lease(recipe, preferred_profile_id="llm_2" if preferred else "")
        try:
            selected.append(lease.profile_id)
            if preferred:
                assert lease.pool_size == 1 and not lease.legacy_fallback_allowed
                assert lease.initial_profile_id == "llm_2"
            for stage in ("visual_director", "vfx_director"):
                transport.llm_chat_json(packet(stage), timeout=1)
        finally:
            llm_profiles.end_llm_item_lease(lease, token)
    assert selected == (["llm_2"] * 4 if preferred else ["llm_1", "llm_2", "llm_3", "llm_1"])
    assert [url.split("//", 1)[1].split(".", 1)[0] for url, _, _ in wire.calls] == (
        ["two"] * 8 if preferred else ["one", "one", "two", "two", "three", "three", "one", "one"])
    if preferred:
        assert all(body["provider"] == {"only": ["PreferredVendor/Endpoint"], "allow_fallbacks": False} for _, body, _ in wire.calls)
    assert llm_profiles.current_llm_item_lease() is None


def test_responses_chain_keeps_full_authored_stage_dossier(wire):
    wire.configure(LLM_API_MODE="responses")
    with llm_profiles.llm_item_lease("responses-chain") as lease:
        for stage in STAGES:
            request = packet(stage)
            request[llm_provider_wire.LLM_MODEL_OVERRIDE_KEY] = f"override/{stage}"
            before = copy.deepcopy(request)
            result = transport.llm_chat_json(request, timeout=1)
            url, body, _ = wire.calls[-1]
            assert url.endswith("/responses")
            assert body["provider"] == {"only": [PIN], "allow_fallbacks": False}
            assert body["model"] == f"override/{stage}"
            assert_responses_dossier(body, request)
            assert llm_provider_wire.LLM_MODEL_OVERRIDE_KEY not in body and llm_provider_wire.LLM_STAGE_KEY not in body
            assert request == before
            assert result["choices"][0]["message"]["content"] == "{}"
            assert result["_debug"]["apiMode"] == "responses"
            assert result["_debug"]["cachedInputTokens"] == 40
        assert lease.call_count == 3 and lease.failovers == []
        assert result["_debug"]["previousResponseId"] == "resp_2"
    assert [body.get("previous_response_id") for _, body, _ in wire.calls] == [None, "resp_1", "resp_2"]


@pytest.mark.parametrize("mode,lease_mode,failure", [
    pytest.param("chat_completions", "pool", 402, id="quota-cannot-hop-pinned-pool"),
    pytest.param("responses", "legacy_lease", 401, id="auth-cannot-use-fallback"),
    pytest.param("chat_completions", "no_lease", "network", id="network-fails-on-selected-pin"),
    pytest.param("responses", "pool", "envelope", id="malformed-envelope-cannot-hop"),
])
def test_strict_pin_failure_never_crosses_profile_boundary(wire, mode, lease_mode, failure):
    profiles = ({"id": "llm_2", "enabled": True, "provider": "openrouter",
        "base_url": "https://secondary.example/v1", "model": "vendor/secondary",
        "api_mode": mode, "openrouter_provider": "OtherVendor/Secondary"},) if lease_mode == "pool" else ()
    wire.configure(LLM_API_MODE=mode, LLM_POOL_PROFILES=profiles, LLM_FALLBACK_PROVIDER="openrouter",
                   LLM_FALLBACK_MODEL="vendor/fallback", LLM_FALLBACK_BASE_URL="https://fallback.example/v1",
                   LLM_FALLBACK_OPENROUTER_PROVIDER="OtherVendor/Fallback")
    reply = urllib.error.URLError("synthetic connection reset") if failure == "network" else failure
    if failure == "envelope":
        reply = {"status": "failed"} if mode == "responses" else {"choices": []}
    wire.replies.extend([reply, reply])
    lease = token = None
    if lease_mode != "no_lease":
        lease, token = llm_profiles.begin_llm_item_lease("pinned-must-fail-closed")
    try:
        with pytest.raises((urllib.error.URLError, RuntimeError)):
            transport.llm_chat_json(packet(), timeout=1)
        if lease is not None:
            assert lease.profile_id == lease.initial_profile_id == "llm_1"
            assert lease.context["openrouter_provider"] == PIN
            assert lease.failovers == [] and lease.call_count == 1
    finally:
        if lease is not None:
            llm_profiles.end_llm_item_lease(lease, token)
    assert 1 <= len(wire.calls) <= 2
    assert all("primary.example" in url for url, _, _ in wire.calls)
    assert all(body["provider"] == {"only": [PIN], "allow_fallbacks": False} for _, body, _ in wire.calls)
    assert llm_profiles.current_llm_item_lease() is None


@pytest.mark.parametrize("target", ["pool", "legacy"], ids=["pool-adopts-target", "credit-adopts-legacy"])
def test_failover_adopts_target_for_later_stages(wire, target):
    secondary = {"id": "llm_2", "enabled": True, "provider": "openrouter",
        "base_url": "https://secondary.example/v1", "model": "vendor/secondary",
        "api_mode": "chat_completions", "api_key": "synthetic-secondary", "openrouter_provider": "TargetVendor/Endpoint"}
    wire.configure(OPENROUTER_PROVIDER="", LLM_POOL_PROFILES=(secondary,) if target == "pool" else (),
        LLM_FALLBACK_PROVIDER="openrouter", LLM_FALLBACK_MODEL="vendor/secondary",
        LLM_FALLBACK_BASE_URL=secondary["base_url"], LLM_FALLBACK_API_KEY=secondary["api_key"],
        LLM_FALLBACK_OPENROUTER_PROVIDER=secondary["openrouter_provider"])
    wire.replies.append(503 if target == "pool" else 402)
    with llm_profiles.llm_item_lease("failover-item") as lease:
        for stage in ("visual_director", "vfx_director"):
            request = packet(stage)
            request[llm_provider_wire.LLM_MODEL_OVERRIDE_KEY] = "override/main-only"
            result = transport.llm_chat_json(request, timeout=1)
            assert result["choices"][0]["message"]["content"] == "{}"
        assert lease.call_count == 2
    assert [url for url, _, _ in wire.calls] == [
        "https://primary.example/api/v1/chat/completions", *[secondary["base_url"] + "/chat/completions"] * 2]
    assert [body["model"] for _, body, _ in wire.calls] == ["override/main-only", "vendor/secondary", "vendor/secondary"]
    assert [body.get("provider") for _, body, _ in wire.calls] == [None, *[{
        "only": ["TargetVendor/Endpoint"], "allow_fallbacks": False}] * 2]
    assert all(headers["Authorization"] == "Bearer synthetic-secondary" for _, _, headers in wire.calls[1:])
    assert all(llm_provider_wire.LLM_MODEL_OVERRIDE_KEY not in body for _, body, _ in wire.calls)


@pytest.mark.parametrize("stage,mode,attempts", [
    pytest.param("planner", "chat_completions", 1, id="author-single-attempt"),
    pytest.param("visual_director", "responses", 2, id="visual-bounded-content-retry"),
])
def test_content_retry_keeps_selected_pin_model_and_logical_call(wire, stage, mode, attempts):
    wire.configure(LLM_API_MODE=mode, LLM_FALLBACK_NETWORK_FAILS=attempts)
    first = {"id": "resp_partial", "output_text": "{"} if mode == "responses" else {
        "choices": [{"finish_reason": "length", "message": {"content": "{"}}]}
    wire.replies.append(first)
    request = packet(stage)
    request[llm_provider_wire.LLM_MODEL_OVERRIDE_KEY] = f"override/{stage}"
    before = copy.deepcopy(request)
    with llm_profiles.llm_item_lease("length-retry-pin") as lease:
        result = transport.llm_chat_json(request, timeout=1)
        assert lease.call_count == 1 and lease.failovers == [] and len(lease.stages) == 1
        assert lease.context["openrouter_provider"] == PIN
    assert len(wire.calls) == attempts
    assert all(body["provider"] == {"only": [PIN], "allow_fallbacks": False} for _, body, _ in wire.calls)
    assert all(body["model"] == f"override/{stage}" for _, body, _ in wire.calls)
    assert all(llm_provider_wire.LLM_MODEL_OVERRIDE_KEY not in body for _, body, _ in wire.calls)
    assert request == before
    if attempts == 2:
        retry_body = dict(wire.calls[1][1])
        if mode == "responses":
            assert retry_body.pop("previous_response_id") == "resp_partial"
        assert retry_body == wire.calls[0][1]
        assert result["_debug"]["transportRetryCauses"] == ["malformed_json"]
    else:
        assert result["choices"][0]["message"]["content"] == "{"
        assert "transportRetryCount" not in result.get("_debug", {})


@pytest.mark.parametrize("provider,mode,attempts", [
    pytest.param("openrouter", "chat_completions", 1, id="one-attempt-stops"),
    pytest.param("openrouter", "responses", 2, id="transient-retries-same-route"),
])
def test_transient_retry_budget_never_changes_selected_route(wire, provider, mode, attempts):
    wire.configure(LLM_PROVIDER=provider, LLM_API_MODE=mode, LLM_FALLBACK_NETWORK_FAILS=attempts,
                   LLM_FALLBACK_PROVIDER="openai_compat", LLM_FALLBACK_MODEL="paid-fallback" if provider == "openrouter" else "")
    wire.replies.append(503)
    request = packet("vfx_director")
    request[llm_provider_wire.LLM_MODEL_OVERRIDE_KEY] = "override/retry"
    with llm_profiles.llm_item_lease("transient-retry") as lease:
        if attempts == 1:
            with pytest.raises(urllib.error.HTTPError):
                transport.llm_chat_json(request, timeout=1)
        else:
            result = transport.llm_chat_json(request, timeout=1)
            assert result["choices"][0]["message"]["content"] == "{}"
            assert result["_debug"]["transportRetryCount"] == 1
            assert result["_debug"]["transportRetryCauses"] == ["transient_http"]
        assert lease.profile_id == "llm_1" and lease.failovers == [] and lease.call_count == 1
    assert len(wire.calls) == attempts and len({url for url, _, _ in wire.calls}) == 1
    assert all(body.get("provider") == ({"only": [PIN], "allow_fallbacks": False} if provider == "openrouter" else None) for _, body, _ in wire.calls)
    assert all(body["model"] == "override/retry" for _, body, _ in wire.calls)


class RateClock:
    """Explicit thread gates: elapsed quota/deadline time never uses real sleep."""
    def __init__(self):
        self.now = 1000.0
        self.condition = threading.Condition()
        self.parked = {}
        self.releases = set()
        self.results = {}
        self.threads = {}
        self.stopped = False

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        name = threading.current_thread().name
        with self.condition:
            self.parked[name] = float(seconds)
            self.condition.notify_all()
            self.condition.wait_for(lambda: name in self.releases or self.stopped)
            if self.stopped:
                raise RuntimeError("rate test stopped")
            self.releases.remove(name)

    def start(self, name, call):
        def run():
            try:
                result = call()
            except BaseException as error:
                result = error
            with self.condition:
                self.results[name] = result
                self.condition.notify_all()
        worker = threading.Thread(target=run, name=name, daemon=True)
        self.threads[name] = worker
        worker.start()
        return self.observe(name)

    def observe(self, name):
        with self.condition:
            assert self.condition.wait_for(
                lambda: name in self.parked or name in self.results, timeout=2,
            ), f"worker {name} did not reach its gate"
            return "done" if name in self.results else "waiting"

    def step(self, name, now):
        with self.condition:
            assert name in self.parked, (name, self.results)
            assert now >= self.now
            self.now = now
            del self.parked[name]
            self.releases.add(name)
            self.condition.notify_all()
        return self.observe(name)

    def close(self):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()
        for worker in self.threads.values():
            worker.join(timeout=2)
            assert not worker.is_alive(), "rate waiter leaked a thread/lock"


@pytest.fixture
def rate_clock(monkeypatch):
    from infini_local.core import http_io
    clock = RateClock()
    reset_llm_runtime()
    fake_time = SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep, time=lambda: 1_700_000_020.0)
    monkeypatch.setattr(transport, "time", fake_time)
    monkeypatch.setattr(llm_admission, "time", fake_time)
    monkeypatch.setattr(http_io, "time", fake_time)
    monkeypatch.setattr(transport, "log_event", lambda *_args, **_kwargs: None)

    class GateEvent(threading.Event):
        def wait(self, timeout=None):
            if not self.is_set():
                clock.sleep(timeout if timeout is not None else float("inf"))
            return self.is_set()

    # Isolate only this module's waiter primitive; never patch threading globally.
    monkeypatch.setattr(llm_admission, "threading", SimpleNamespace(Event=GateEvent))
    yield clock
    clock.close()
    reset_llm_runtime()


@pytest.mark.parametrize("url,model,cached,policy,wait,second_sent", [
    pytest.param("https://inference-api.nousresearch.com/v1/chat/completions", "openai/gpt-6-luna", 19000,
        "nous_openai_feedback", "pacing", True, id="nous-chat"),
    pytest.param("https://inference-api.nousresearch.com/v1/responses", "openai/gpt-6-luna", 19000,
        "nous_openai_feedback", "pacing", True, id="nous-responses"),
    pytest.param("https://inference-api.nousresearch.com.evil.example/v1/chat/completions", "openai/gpt-6-luna", 19999,
        "unknown_conservative", "token_window", False, id="lookalike-host"),
    pytest.param("https://inference-api.nousresearch.com/v1/chat/completions", "google/gemini", 19999,
        "unknown_conservative", "token_window", False, id="other-model-family"),
])
def test_http_admission_uses_feedback_only_for_exact_nous_route(
    rate_clock, monkeypatch, url, model, cached, policy, wait, second_sent,
):
    clock = rate_clock
    payload = {"model": model, "messages": [{"role": "user", "content": "x" * 80_000}]}
    before = copy.deepcopy(payload)
    sender = HttpSender(monkeypatch, transport, clock, default_body=json.dumps({
        "usage": {"input_tokens": 20000, "input_tokens_details": {"cached_tokens": cached}},
    }).encode())
    observations = []

    def call():
        with physical_attempt(transport, observations):
            return transport.http_json(url, payload, timeout=10)

    assert clock.start("first", call) == "done"
    assert clock.start("second", call) == "waiting"
    if second_sent:
        assert clock.parked["second"] == pytest.approx(5.1), "wire size invented a 60-second quota"
        assert clock.step("second", 1005.1) == "done"
        assert not isinstance(clock.results["second"], Exception)
        assert [sent[1] for sent in sender.sends] == [1000.0, 1005.1]
        assert [sent[2] for sent in sender.sends] == [1010.0, 1010.0]
        assert observations[1]["rateWaitMs"] == 5100
        assert llm_admission._LLM_RATE_STATE[llm_admission._remote_rate_key(url, payload)]["events"] == []
        assert [row["rateAdmissionPolicy"] for row in observations] == [policy] * 2
    else:
        assert clock.step("second", 1010.0) == "done"
        assert isinstance(clock.results["second"], transport.HttpDeadlineExceeded)
        assert len(sender.sends) == 1
        assert observations[1]["rateAdmissionPolicy"] == policy
    assert all(sent[0] == before for sent in sender.sends)
    assert payload == before
    assert observations[1]["rateWaitReason"] == wait


@pytest.mark.parametrize("resource,status", [
    pytest.param("tokens", 200, id="success-quota-feedback"),
    pytest.param("requests", 429, id="429-cooldown-feedback"),
])
def test_http_quota_headers_block_admission_without_retaining_other_headers(rate_clock, monkeypatch, resource, status):
    clock = rate_clock
    url = "https://inference-api.nousresearch.com/v1/chat/completions"
    payload = {"model": "openai/gpt-6-luna", "messages": [{"role": "user", "content": "full authored context"}]}
    headers = Message()
    headers[f"X-RateLimit-Limit-{resource}"] = "100"
    headers[f"X-RateLimit-Remaining-{resource}"] = "0"
    headers[f"X-RateLimit-Reset-{resource}"] = "1m15s"
    headers["Retry-After"] = "75"
    headers["Set-Cookie"] = "session=synthetic-secret-cookie"
    headers["ChatGPT-Account-Id"] = "synthetic-account-id"
    headers["X-RateLimit-Unknown"] = "synthetic-secret-key"
    sends, rows = [], []

    reply = (urllib.error.HTTPError(url, 429, "synthetic quota", headers, io.BytesIO(b'{}'))
             if status == 429 else HttpReply(headers=headers))
    sender = HttpSender(monkeypatch, transport, clock, [reply])
    sends = sender.sends

    def call(timeout):
        with physical_attempt(transport, rows):
            return transport.http_json(url, payload, timeout=timeout)

    assert clock.start("first", lambda: call(100)) == "done"
    if status == 429:
        assert isinstance(clock.results["first"], urllib.error.HTTPError)
        clock.results["first"].close()
    assert "rateLimitHeaders" in rows[0], "actual response quota metadata was discarded"
    assert rows[0]["rateLimitHeaders"] == {
        f"x-ratelimit-limit-{resource}": 100,
        f"x-ratelimit-remaining-{resource}": 0,
        f"x-ratelimit-reset-{resource}": 75.0,
        "retry-after": 75.0,
    }
    assert "synthetic-" not in json.dumps(rows)
    assert clock.start("second", lambda: call(10)) == "waiting"
    assert clock.step("second", 1010.0) == "done"
    assert isinstance(clock.results["second"], transport.HttpDeadlineExceeded)
    assert len(sends) == 1 and rows[1]["networkStarted"] is False
    assert rows[1]["rateWaitReason"] == ("provider_cooldown" if status == 429 else "provider_quota")
    assert clock.start("third", lambda: call(100)) == "waiting"
    assert clock.step("third", 1075.0) == "done"
    assert clock.results["third"] == {}
    assert sends == [(payload, 1000.0, 1100.0), (payload, 1075.0, 1110.0)]


@pytest.mark.parametrize("status", [200, 429])
def test_real_urllib_quota_headers_reach_logical_diagnostics(loopback_transport, monkeypatch, status):
    endpoint, events = loopback_transport
    headers = {"X-RateLimit-Limit-Requests": "10", "X-RateLimit-Remaining-Requests": "0",
               "X-RateLimit-Reset-Requests": "6m0s", "Set-Cookie": "synthetic-secret-cookie",
               "ChatGPT-Account-Id": "synthetic-account-id"}
    base, observed = endpoint([{"status": status, "headers": headers}])
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(llm_config, "LLM_FALLBACK_NETWORK_FAILS", 1)
    if status == 200:
        debug = transport.llm_chat_json(packet(), timeout=1)["_debug"]
    else:
        with pytest.raises(urllib.error.HTTPError) as raised:
            transport.llm_chat_json(packet(), timeout=1)
        debug = raised.value._infini_transport_debug
    assert len(observed) == 1
    row = debug["physicalAttempts"][0]
    assert row["rateAdmissionPolicy"] == "local_exempt"
    assert row["rateLimitHeaders"] == {"x-ratelimit-limit-requests": 10,
                                       "x-ratelimit-remaining-requests": 0,
                                       "x-ratelimit-reset-requests": 360.0}
    assert llm_admission._LLM_RATE_STATE == {}
    assert "synthetic-secret-cookie" not in json.dumps(debug)
    assert "synthetic-account-id" not in json.dumps(events)


def test_http_rate_fifo_reaches_sender_without_changing_wire_or_deadline(rate_clock, monkeypatch):
    clock = rate_clock
    url = "https://provider.example/v1/chat/completions"
    model = "vendor/model"
    llm_admission._reserve_remote_rate_slot(url, {"model": model}, b"{}")
    sends, diagnostics = [], {}

    sender = HttpSender(monkeypatch, transport, clock)
    sends = sender.sends

    def call(name, content):
        request = llm_provider_wire.with_llm_stage({"model": model, "messages": [
            {"role": "user", "content": content}], "response_format": {"type": "json_object"}}, "visual_director")
        state = transport._new_llm_diagnostics(request)
        token = transport._CURRENT_LLM_DIAGNOSTICS.set(state)
        try:
            result = transport._perform_llm_http(url, request, 70, {
                "provider": "openai_compat", "model": model, "profile_id": "offline",
            }, api_mode="chat_completions")
            assert result == {}
        finally:
            diagnostics[name] = transport._llm_diagnostic_summary(state)
            transport._CURRENT_LLM_DIAGNOSTICS.reset(token)

    assert clock.start("older", lambda: call("older", "x" * 64_000)) == "waiting"
    clock.now = 1010.0
    assert clock.start("younger", lambda: call("younger", "small")) == "waiting"
    assert sends == []
    assert clock.step("older", 1060.0) == "done"
    assert clock.results["older"] is None
    assert sends[0][0]["messages"][0]["content"] == "x" * 64_000
    assert sends[0][1:] == (1060.0, 1070.0)
    assert clock.step("younger", 1060.0) == "waiting"
    assert clock.step("younger", 1080.0) == "done"
    assert isinstance(clock.results["younger"], transport.HttpDeadlineExceeded)
    assert len(sends) == 1
    first, second = diagnostics["older"], diagnostics["younger"]
    assert first["physicalAttemptCount"] == 1 and first["rateWaitMsTotal"] == 60_000
    assert first["physicalAttempts"][0]["httpStatus"] == 200
    assert second["physicalAttemptCount"] == 0 and second["physicalAttempts"] == []
    assert second["rateWaitReason"] == "token_window" and second["rateWaitMsTotal"] == 70_000
    assert not llm_admission._LLM_RATE_STATE[llm_admission._remote_rate_key(url, {"model": model})]["waiters"]


def test_concurrent_leases_isolate_profile_and_response_chain(wire, monkeypatch):
    wire.configure(LLM_PROVIDER="openai_compat", LLM_API_MODE="responses", LLM_POOL_PROFILES=({
        "id": "llm_2", "enabled": True, "provider": "openai_compat",
        "base_url": "https://secondary.example/v1", "model": "secondary-model", "api_mode": "responses"},))
    barrier, lock = threading.Barrier(4), threading.Lock()
    calls = []

    def respond(url, body, **_options):
        recipe = json.loads(body["input"][0]["content"])["recipe"]
        with lock:
            calls.append((recipe, url, copy.deepcopy(body)))
        return {"id": f"resp_{recipe}", "status": "completed", "output_text": "{}"}

    def run_item(index):
        recipe = f"item-{index}"
        with llm_profiles.llm_item_lease(recipe):
            barrier.wait(timeout=5)
            request = packet()
            request["messages"][1]["content"] = json.dumps({"recipe": recipe})
            for _ in range(2):
                result = transport.llm_chat_json(request, timeout=1)
                assert result["choices"][0]["message"]["content"] == "{}"
        assert llm_profiles.current_llm_item_lease() is None
        return recipe

    monkeypatch.setattr(transport, "http_json", respond)
    with ThreadPoolExecutor(max_workers=4) as pool:
        recipes = list(pool.map(run_item, range(4)))
    assert len(calls) == 8
    for recipe in recipes:
        owned = [(url, body) for owner, url, body in calls if owner == recipe]
        assert len(owned) == 2 and owned[0][0] == owned[1][0]
        assert [body.get("previous_response_id") for _, body in owned] == [None, f"resp_{recipe}"]
    assert {url for _, url, _ in calls} == {
        "https://primary.example/v1/responses", "https://secondary.example/v1/responses"}
    assert llm_profiles.current_llm_item_lease() is None


@pytest.mark.parametrize("metadata,retained", [
    ({}, True),
    ({"responseFormatType": "json_schema", "responseFormatUsed": True}, True),
    ({"strictSchemaDowngraded": True}, False),
    ({"responseFormatUsed": False}, False),
    ({"responseFormatType": "json_object"}, False),
])
def test_effective_schema_tracks_actual_transport_metadata(metadata, retained):
    response_format = {"type": "json_schema", "json_schema": {"strict": True}}
    actual = llm_provider_wire.effective_response_format({"response_format": response_format}, {"_debug": metadata})
    assert actual is (response_format if retained else None)
    assert llm_provider_wire.effective_response_format({}, {"_debug": metadata}) is None
