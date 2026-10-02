"""Offline profile ownership, bounded retries, and per-profile routing contracts.

Every independent matrix row is a pytest item. Multi-call sequences below are
stateful observations (lease continuity/capability learning), not check dispatchers.
"""
from __future__ import annotations

from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager, nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
import copy
from email.message import Message
import io
import json
import runpy
import threading
import urllib.error

import pytest

from infini_local.core import llm_config
from infini_local.pipelines import llm_transport as transport

PIN = "ExactVendor/Endpoint-Turbo"
STAGES = ("planner", "visual_director", "vfx_director")
MODES = ("chat_completions", "responses", "auto")


def packet(stage="planner", *, schema=False):
    response_format = {"type": "json_object"}
    if schema:
        response_format = {"type": "json_schema", "json_schema": {
            "name": "pin_probe", "strict": True,
            "schema": {"type": "object", "properties": {}, "additionalProperties": False},
        }}
    return transport.with_llm_stage({
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
            self.monkeypatch.setattr(transport, name, value, raising=False)
        transport._reset_llm_pool_runtime_for_tests()

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
    transport._reset_llm_pool_runtime_for_tests()


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
                encoded = reply["raw_body"].encode() if "raw_body" in reply else json.dumps(reply.get("body", default)).encode()
                try:
                    time.sleep(reply.get("before_headers", 0.0))
                    self.send_response(reply.get("status", 200))
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    for name, value in reply.get("headers", {}).items():
                        self.send_header(name, value)
                    if reply.get("header_trickle"):
                        # Every idle gap is below timeout, while the complete header is not.
                        buffered = b"".join(self._headers_buffer)
                        self._headers_buffer = []
                        for octet in buffered + b"\r\n":
                            self.wfile.write(bytes([octet]))
                            self.wfile.flush()
                            time.sleep(reply["header_trickle"])
                    else:
                        self.end_headers()
                    if reply.get("trickle"):
                        for octet in encoded:
                            self.wfile.write(bytes([octet]))
                            self.wfile.flush()
                            time.sleep(reply["trickle"])
                    else:
                        self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_POST = do_GET = respond

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", observed
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    with ExitStack() as stack:
        def make_endpoint(replies=()):
            return stack.enter_context(endpoint(replies))
        yield make_endpoint, events
    transport._reset_llm_pool_runtime_for_tests()


@pytest.mark.parametrize("kind", ["chat_completions", "responses", "models"])
@pytest.mark.parametrize("status", [200, 301, 302, 303, 307, 308])
def test_real_http_redirects_fail_closed_without_forwarding_bearer_or_adopting_foreign_reply(
    loopback_transport, monkeypatch, kind, status,
):
    endpoint, _events = loopback_transport
    foreign_url, foreign = endpoint()
    redirected_path = "/v1/models" if kind == "models" else (
        "/v1/responses" if kind == "responses" else "/v1/chat/completions")
    source_url, observed = endpoint([{"status": status, "headers": {"Location": foreign_url + redirected_path}}])
    monkeypatch.setattr(transport, "OPENROUTER_BASE_URL", source_url)
    monkeypatch.setattr(transport, "LLM_API_MODE", "chat_completions" if kind == "models" else kind)
    if kind == "models":
        monkeypatch.setattr(transport, "OPENROUTER_MODEL", "auto")
        resolved = transport.resolve_llm_model()
        assert resolved == ("vendor/advertised:free" if status == 200 else "")
        assert len(transport._RESOLVED_LLM_MODELS) == (1 if status == 200 else 0)
    else:
        with transport.llm_item_lease("redirect-policy") as lease:
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
    monkeypatch.setattr(transport, "OPENROUTER_BASE_URL", base)
    started = time.monotonic()
    with transport.llm_item_lease("whole-call-deadline") as lease:
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
def test_real_http_deadline_prevents_sending_after_rate_wait(loopback_transport, monkeypatch, reason):
    endpoint, _events = loopback_transport
    base, observed = endpoint()
    monkeypatch.setattr(transport, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(transport, "_remote_rate_key", lambda *_args: "synthetic-rate-key")
    now = time.monotonic()
    transport._LLM_RATE_STATE["synthetic-rate-key"] = {
        "events": [], "lastRequest": now if reason == "pacing" else -1.0e30,
        "blockedUntil": now + 10 if reason == "provider_429" else 0,
    }
    started = time.monotonic()
    with pytest.raises(TimeoutError) as caught:
        transport.llm_chat_json(packet(), timeout=0.18)
    assert caught.value._infini_transport_debug["physicalAttemptCount"] == 0
    assert caught.value._infini_transport_debug["physicalAttempts"] == []
    assert time.monotonic() - started < 0.33
    assert observed == []
    assert transport._LLM_RATE_STATE["synthetic-rate-key"]["events"] == []


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


@pytest.mark.parametrize("outcome", ["success", "failure", "bounded", "escaped_secret", "provider_debug"])
def test_real_http_physical_attempt_timeline_is_bounded_safe_and_survives_failure(
    loopback_transport, monkeypatch, outcome,
):
    endpoint, events = loopback_transport
    secret = "synthetic-loopback-key"
    rejected = {"error": {"code": "unsupported_response_format", "param": "response_format",
                          "message": "json_schema response_format is not supported: " + secret}}
    final = {"status": 400, "body": {"error": {"code": "context_length_exceeded", "param": "messages"}}} if outcome == "failure" else {}
    rejection_reply = {"status": 400, "body": rejected}
    if outcome == "escaped_secret":
        rejection_reply = {"status": 400, "raw_body": json.dumps(rejected).replace("synthetic-loopback-key", r"\u0073ynthetic-loopback-key")}
    if outcome == "provider_debug":
        final = {"body": {"choices": [{"message": {"content": "{}"}}],
                          "_debug": {"providerDebugKey": secret, "promptEcho": "PRIVATE_AUTHOR_PACKET"}}}
    base, observed = endpoint([{"status": 404}, rejection_reply, final])
    monkeypatch.setattr(transport, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(transport, "LLM_API_MODE", "auto")
    if outcome == "bounded":
        monkeypatch.setattr(transport, "_LLM_MAX_DIAGNOSTIC_ATTEMPTS", 2, raising=False)
    request = packet(schema=True)
    request["messages"][1]["content"] = "PRIVATE_AUTHOR_PACKET"
    request["reasoning"] = {"max_tokens": 123, "exclude": True}
    with transport.llm_item_lease("physical-attribution") as lease:
        if outcome == "failure":
            with pytest.raises(urllib.error.HTTPError) as caught:
                transport.llm_chat_json(request, timeout=1)
            debug = caught.value._infini_transport_debug
        else:
            result = transport.llm_chat_json(request, timeout=1)
            debug = result["_debug"]
        assert lease.call_count == 1 and not lease.failovers
    assert len(observed) == 3
    attempts = [data for message, data in events if message == "LLM physical attempt"]
    assert len(attempts) == (2 if outcome == "bounded" else 3)
    assert debug["physicalAttemptCount"] == 3
    assert debug["physicalAttemptsDropped"] == (1 if outcome == "bounded" else 0)
    assert len(debug["physicalAttempts"]) == len(attempts)
    assert len({row["logicalCallId"] for row in attempts}) == 1
    assert [row["physicalAttemptIndex"] for row in attempts] == list(range(1, len(attempts) + 1))
    assert [row["httpStatus"] for row in attempts] == ([404, 400] if outcome == "bounded" else [404, 400, 400 if outcome == "failure" else 200])
    assert [row["effectiveApiMode"] for row in attempts] == (["responses", "chat_completions"] if outcome == "bounded" else ["responses", "chat_completions", "chat_completions"])
    assert attempts[0]["requestedResponseFormat"] == attempts[0]["effectiveResponseFormat"] == "json_schema"
    assert attempts[0]["requestedReasoning"] == {"max_tokens": 123, "exclude": True}
    assert attempts[0]["effectiveReasoning"] == {}
    assert attempts[0]["unsupportedReasoningFields"] == ["exclude", "max_tokens"]
    assert debug["requestedResponseFormat"] == "json_schema"
    assert debug["effectiveResponseFormat"] == "json_object"
    assert debug["requestedApiMode"] == "auto" and debug["effectiveApiMode"] == "chat_completions"
    if outcome != "bounded":
        assert [row["reason"] for row in attempts] == ["initial", "responses_to_chat_fallback", "json_schema_to_json_object_fallback"]
    for row in attempts:
        assert row["rateWaitMs"] >= 0 and row["openMs"] >= 0 and row["readMs"] >= 0
        assert row["connectMs"] is None  # urllib cannot honestly isolate DNS/TCP/TLS here.
        assert 0 <= row["deadlineRemainingMs"] <= 1000
    serialized = json.dumps([events, debug])
    assert secret not in serialized and "PRIVATE_AUTHOR_PACKET" not in serialized
    assert r"\u0073ynthetic-loopback-key" not in serialized
    assert "Authorization" not in serialized and "messages" not in json.dumps(attempts)


def test_real_http_429_timeline_distinguishes_one_send_from_unsent_cooldown(loopback_transport, monkeypatch):
    endpoint, events = loopback_transport
    base, observed = endpoint([{"status": 429, "headers": {"Retry-After": "60"}}])
    monkeypatch.setattr(transport, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(transport, "_remote_rate_key", lambda *_args: "synthetic-rate-key")
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
        assert False in transport._RESPONSES_CAPABILITY.values()
    else:
        with pytest.raises(urllib.error.HTTPError):
            transport._llm_json_single_context(packet(), 1, context)
        assert transport._RESPONSES_CAPABILITY == {}
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
    monkeypatch.setattr(transport, "OPENROUTER_BASE_URL", source)
    monkeypatch.setattr(transport, "OPENROUTER_PROVIDER", "")
    monkeypatch.setattr(transport, "LLM_POOL_PROFILES", ({"id": "llm_2", "enabled": True,
        "provider": "openrouter", "base_url": secondary, "model": "vendor/secondary",
        "api_mode": "chat_completions", "api_key": "synthetic-loopback-key", "openrouter_provider": PIN},))
    with transport.llm_item_lease("deadline-failover") as lease:
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
    with transport.llm_item_lease("codex-boundary") as lease:
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


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("provider,pin", [
    pytest.param("openrouter", PIN, id="strict-pin"),
    pytest.param("openrouter", "", id="automatic"),
    pytest.param("openrouter", "   ", id="whitespace-automatic"),
    pytest.param("local", PIN, id="local-stale-pin"),
    pytest.param("openai_compat", PIN, id="compat-stale-pin"),
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
        context = transport._primary_llm_context()
        assert transport._llm_context_key(context) == transport._llm_context_key({**context, "openrouter_provider": PIN})
        secondary = transport._pool_profile_context({"id": "llm_2", "enabled": True,
            "provider": provider, "model": "other-model", "openrouter_provider": PIN})
        assert secondary is not None and secondary["openrouter_provider"] == ""
    if url.endswith("/responses"):
        assert body["instructions"] == request["messages"][0]["content"]
        assert body["input"] == [request["messages"][1]]
        assert body["max_output_tokens"] == 321
        assert body["text"] == {"format": request["response_format"]}
    else:
        expected = {key: value for key, value in request.items() if key not in {transport.LLM_STAGE_KEY, "provider"}}
        expected["model"] = body["model"]
        if pinned:
            expected["provider"] = {"only": [PIN], "allow_fallbacks": False}
        if provider == "local":
            expected.pop("reasoning")
        assert body == expected
        if provider == "openrouter":
            assert url == "https://primary.example/api/v1/chat/completions"


@pytest.mark.parametrize("configured", [False, True], ids=["blank-defaults", "independent-pins"])
def test_profile_pin_configuration(wire, monkeypatch, configured):
    pins = {2: "DeepInfra/Turbo", 3: "", 4: "GoogleCloud/Preview-Endpoint"}
    env = {"INFINI_OPENROUTER_PROVIDER": PIN,
           "INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER": "FallbackVendor/Exact-Endpoint"}
    for index, pin in pins.items():
        for suffix, value in {"ENABLED": "1", "PROVIDER": "openrouter", "MODEL": f"vendor/pool-{index}",
                              "API_MODE": "chat_completions", "OPENROUTER_PROVIDER": pin}.items():
            monkeypatch.setenv(f"INFINI_LLM_POOL_{index}_{suffix}", value)
        env[f"INFINI_LLM_POOL_{index}_OPENROUTER_PROVIDER"] = pin
    for name, value in env.items():
        if configured:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)
    config = runpy.run_path(llm_config.__file__)
    expected_pins = list(pins.values()) if configured else [""] * 3
    assert config["OPENROUTER_PROVIDER"] == (PIN if configured else "")
    assert config["LLM_FALLBACK_OPENROUTER_PROVIDER"] == ("FallbackVendor/Exact-Endpoint" if configured else "")
    assert [profile["openrouter_provider"] for profile in config["LLM_POOL_PROFILES"]] == expected_pins
    wire.configure(OPENROUTER_PROVIDER=config["OPENROUTER_PROVIDER"], LLM_POOL_PROFILES=config["LLM_POOL_PROFILES"],
                   LLM_FALLBACK_PROVIDER="openrouter", LLM_FALLBACK_MODEL="vendor/fallback",
                   LLM_FALLBACK_OPENROUTER_PROVIDER=config["LLM_FALLBACK_OPENROUTER_PROVIDER"])
    fallback = transport._fallback_llm_context()
    assert fallback is not None and fallback["openrouter_provider"] == config["LLM_FALLBACK_OPENROUTER_PROVIDER"]
    selected = []
    for ordinal in range(4):
        with transport.llm_item_lease(f"pin-pool-{ordinal}") as lease:
            selected.append(lease.profile_id)
            transport.llm_chat_json(packet(), timeout=1)
    assert selected == ["llm_1", "llm_2", "llm_3", "llm_4"]
    assert [body.get("provider") for _, body, _ in wire.calls] == [
        {"only": [pin], "allow_fallbacks": False} if pin else None
        for pin in [config["OPENROUTER_PROVIDER"], *expected_pins]
    ]
    blank = transport._pool_profile_context({"id": "llm_2", "enabled": True, "provider": "openrouter", "model": "vendor/secondary"})
    assert blank is not None and blank["openrouter_provider"] == ""
    monkeypatch.setattr(transport, "LLM_FALLBACK_OPENROUTER_PROVIDER", "")
    blank_fallback = transport._fallback_llm_context()
    assert blank_fallback is not None and blank_fallback["openrouter_provider"] == ""


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
        lease, token = transport.begin_llm_item_lease(recipe, preferred_profile_id="llm_2" if preferred else "")
        try:
            selected.append(lease.profile_id)
            if preferred:
                assert lease.pool_size == 1 and not lease.legacy_fallback_allowed
                assert lease.initial_profile_id == "llm_2"
            for stage in ("visual_director", "vfx_director"):
                transport.llm_chat_json(packet(stage), timeout=1)
        finally:
            transport.end_llm_item_lease(lease, token)
    assert selected == (["llm_2"] * 4 if preferred else ["llm_1", "llm_2", "llm_3", "llm_1"])
    assert [url.split("//", 1)[1].split(".", 1)[0] for url, _, _ in wire.calls] == (
        ["two"] * 8 if preferred else ["one", "one", "two", "two", "three", "three", "one", "one"])
    if preferred:
        assert all(body["provider"] == {"only": ["PreferredVendor/Endpoint"], "allow_fallbacks": False} for _, body, _ in wire.calls)
    assert transport.current_llm_item_lease() is None


@pytest.mark.parametrize("mode", ["responses", "auto"])
@pytest.mark.parametrize("provider", ["openrouter", "openai_compat"])
def test_responses_chain_keeps_full_authored_stage_dossier(wire, mode, provider):
    wire.configure(LLM_API_MODE=mode, LLM_PROVIDER=provider)
    with transport.llm_item_lease("responses-chain") as lease:
        for stage in STAGES:
            request = packet(stage)
            request[transport.LLM_MODEL_OVERRIDE_KEY] = f"override/{stage}"
            before = copy.deepcopy(request)
            result = transport.llm_chat_json(request, timeout=1)
            url, body, _ = wire.calls[-1]
            assert url.endswith("/responses")
            assert body.get("provider") == ({"only": [PIN], "allow_fallbacks": False} if provider == "openrouter" else None)
            assert body["model"] == f"override/{stage}"
            assert body["instructions"] == request["messages"][0]["content"]
            assert body["input"] == [request["messages"][1]]
            assert body["text"] == {"format": request["response_format"]}
            assert body["max_output_tokens"] == 321
            assert transport.LLM_MODEL_OVERRIDE_KEY not in body and transport.LLM_STAGE_KEY not in body
            assert request == before
            assert result["choices"][0]["message"]["content"] == "{}"
            assert result["_debug"]["apiMode"] == "responses"
            assert result["_debug"]["cachedInputTokens"] == 40
        assert lease.call_count == 3 and lease.failovers == []
        assert result["_debug"]["previousResponseId"] == "resp_2"
    assert [body.get("previous_response_id") for _, body, _ in wire.calls] == [None, "resp_1", "resp_2"]


@pytest.mark.parametrize("mode", ["chat_completions", "responses"])
@pytest.mark.parametrize("lease_mode", ["pool", "legacy_lease", "no_lease"])
@pytest.mark.parametrize("failure", [400, 401, 402, 403, 404, 429, 503, "network", "envelope"])
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
        lease, token = transport.begin_llm_item_lease("pinned-must-fail-closed")
    try:
        with pytest.raises((urllib.error.URLError, RuntimeError)):
            transport.llm_chat_json(packet(), timeout=1)
        if lease is not None:
            assert lease.profile_id == lease.initial_profile_id == "llm_1"
            assert lease.context["openrouter_provider"] == PIN
            assert lease.failovers == [] and lease.call_count == 1
    finally:
        if lease is not None:
            transport.end_llm_item_lease(lease, token)
    assert 1 <= len(wire.calls) <= 2
    assert all("primary.example" in url for url, _, _ in wire.calls)
    assert all(body["provider"] == {"only": [PIN], "allow_fallbacks": False} for _, body, _ in wire.calls)
    assert transport.current_llm_item_lease() is None


@pytest.mark.parametrize("provider,mode,target,failure,later_failure,budget", [
    pytest.param("openrouter", mode, "pool", 503, False, 2, id=f"unpinned-enters-pinned-{mode}")
    for mode in ("chat_completions", "responses")
] + [
    pytest.param("openrouter", "chat_completions", "pool", 503, True, 2, id="pinned-target-stops-pool"),
    pytest.param("openrouter", "chat_completions", "legacy", 402, True, 2, id="pinned-legacy-later-stage"),
    pytest.param("openrouter", "chat_completions", "legacy", 402, False, 2, id="pinned-legacy-success"),
    pytest.param("openrouter", "chat_completions", "compat-legacy", 402, False, 2, id="credit-fallback-model-override"),
    pytest.param("openai_compat", "chat_completions", "compat-pool", 503, False, 2, id="chat-profile-failover"),
    pytest.param("openai_compat", "auto", "compat-pool", 503, False, 2, id="responses-no-server-downgrade"),
    pytest.param("local", "chat_completions", "local-legacy", "network", False, 2, id="two-network-failures"),
    pytest.param("local", "chat_completions", "local-pool", "network", False, 1, id="one-attempt-no-pool-failover"),
])
def test_failover_adopts_target_for_later_stages(wire, provider, mode, target, failure, later_failure, budget):
    target_provider = "openrouter" if target in {"pool", "legacy"} else target.split("-")[0]
    target_provider = "openai_compat" if target_provider == "compat" else target_provider
    pin = "TargetVendor/Endpoint" if target_provider == "openrouter" else ""
    secondary = {"id": "llm_2", "enabled": True, "provider": target_provider,
        "base_url": "https://secondary.example/v1", "model": "vendor/secondary",
        "api_mode": mode, "api_key": "fk", "openrouter_provider": pin}
    profiles = (secondary,) if target.endswith("pool") else ()
    if later_failure and target == "pool":
        profiles += ({**secondary, "id": "llm_3", "base_url": "https://third.example/v1", "openrouter_provider": ""},)
    wire.configure(LLM_PROVIDER=provider, OPENROUTER_PROVIDER="", LLM_API_MODE=mode,
        LLM_POOL_PROFILES=profiles, LLM_FALLBACK_NETWORK_FAILS=budget,
        LLM_FALLBACK_PROVIDER=target_provider, LLM_FALLBACK_MODEL="vendor/fallback" if not profiles else "",
        LLM_FALLBACK_BASE_URL="http://fallback.local:1234" if target_provider == "local" else "https://fallback.example/v1",
        LLM_FALLBACK_API_KEY="fk", LLM_FALLBACK_OPENROUTER_PROVIDER=pin)
    reply = urllib.error.URLError("timed out") if failure == "network" else failure
    wire.replies.append(reply)
    if target == "local-legacy" or (later_failure and target == "pool"):
        wire.replies.append(reply)
    if later_failure and target == "legacy":
        wire.replies.extend([{"choices": [{"message": {"content": "{}"}}]}, 402])
    lease_context = nullcontext(None) if target == "local-legacy" else transport.llm_item_lease("failover-item")
    request = packet("visual_director")
    request[transport.LLM_MODEL_OVERRIDE_KEY] = "override/main-only"
    with lease_context as lease:
        if budget == 1 or (later_failure and target == "pool"):
            with pytest.raises(urllib.error.URLError):
                transport.llm_chat_json(request, timeout=1)
        else:
            result = transport.llm_chat_json(request, timeout=1)
            assert result["choices"][0]["message"]["content"] == "{}"
            if lease is not None:
                assert lease.initial_profile_id == "llm_1"
                assert lease.profile_id == ("llm_2" if profiles else "legacy_fallback")
                if later_failure:
                    with pytest.raises(urllib.error.HTTPError):
                        transport.llm_chat_json(packet("planner"), timeout=1)
                else:
                    next_request = packet("planner" if mode == "auto" else "vfx_director")
                    next_request[transport.LLM_MODEL_OVERRIDE_KEY] = "override/main-only"
                    again = transport.llm_chat_json(next_request, timeout=1)
                    assert again["choices"][0]["message"]["content"] == "{}"
                assert lease.profile_id == ("llm_2" if profiles else "legacy_fallback")
                assert lease.snapshot()["initialProfileId"] == "llm_1"
                assert lease.call_count == 2
                if pin:
                    assert lease.context["openrouter_provider"] == pin
                    assert result["_debug"]["openrouterProvider"] == pin
                if profiles:
                    assert lease.failovers == [{"fromProfileId": "llm_1", "toProfileId": "llm_2", "reason": "HTTPError"}]
                    assert transport._PROFILE_COOLDOWN_UNTIL["llm_1"] > 0
                if mode == "auto":
                    assert result["_debug"]["apiMode"] == again["_debug"]["apiMode"] == "responses"
            else:
                assert result["_debug"]["transportRetryCount"] == 2
                assert result["_debug"]["transportRetryCauses"] == ["primary_transport", "primary_transport_fallback"]
    if budget == 1:
        assert len(wire.calls) == 1
    elif later_failure and target == "pool":
        assert [body.get("provider") for _, body, _ in wire.calls] == [None, {"only": [pin], "allow_fallbacks": False}]
        assert lease.initial_profile_id == "llm_1" and lease.profile_id == "llm_2" and len(lease.failovers) == 1
    else:
        assert len(wire.calls) == 3
        suffix = "/responses" if mode == "auto" or mode == "responses" else "/chat/completions"
        source_base = "http://primary.local:1234/v1" if provider == "local" else (
            "https://primary.example/api/v1" if provider == "openrouter" else "https://primary.example/v1")
        target_base = "http://fallback.local:1234/v1" if target_provider == "local" else (
            "https://secondary.example/v1" if profiles else "https://fallback.example/v1")
        assert [url for url, _, _ in wire.calls] == [source_base + suffix,
            (source_base if target == "local-legacy" else target_base) + suffix, target_base + suffix]
        target_model = "vendor/secondary" if profiles else "vendor/fallback"
        assert [body["model"] for _, body, _ in wire.calls] == ["override/main-only",
            "override/main-only" if target == "local-legacy" else target_model, target_model]
        assert wire.calls[-1][2].get("Authorization") == (None if target_provider == "local" else "Bearer fk")
        if pin:
            assert [body.get("provider") for _, body, _ in wire.calls] == [None, *[{"only": [pin], "allow_fallbacks": False}] * 2]
    assert all(transport.LLM_MODEL_OVERRIDE_KEY not in body for _, body, _ in wire.calls)


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("mode", ["chat_completions", "responses"])
@pytest.mark.parametrize("attempts", [1, 2])
def test_content_retry_keeps_selected_pin_model_and_logical_call(wire, stage, mode, attempts):
    wire.configure(LLM_API_MODE=mode, LLM_FALLBACK_NETWORK_FAILS=attempts)
    first = {"id": "resp_partial", "output_text": "{"} if mode == "responses" else {
        "choices": [{"finish_reason": "length", "message": {"content": "{"}}]}
    wire.replies.append(first)
    request = packet(stage)
    request[transport.LLM_MODEL_OVERRIDE_KEY] = f"override/{stage}"
    before = copy.deepcopy(request)
    with transport.llm_item_lease("length-retry-pin") as lease:
        result = transport.llm_chat_json(request, timeout=1)
        assert lease.call_count == 1 and lease.failovers == [] and len(lease.stages) == 1
        assert lease.context["openrouter_provider"] == PIN
    assert len(wire.calls) == attempts
    assert all(body["provider"] == {"only": [PIN], "allow_fallbacks": False} for _, body, _ in wire.calls)
    assert all(body["model"] == f"override/{stage}" for _, body, _ in wire.calls)
    assert all(transport.LLM_MODEL_OVERRIDE_KEY not in body for _, body, _ in wire.calls)
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
    pytest.param("openrouter", mode, attempts, id=f"pin-{mode}-{attempts}")
    for mode in ("chat_completions", "responses") for attempts in (1, 2)
] + [pytest.param("local", "chat_completions", 2, id="local-transient")])
def test_transient_retry_budget_never_changes_selected_route(wire, provider, mode, attempts):
    wire.configure(LLM_PROVIDER=provider, LLM_API_MODE=mode, LLM_FALLBACK_NETWORK_FAILS=attempts,
                   LLM_FALLBACK_PROVIDER="openai_compat", LLM_FALLBACK_MODEL="paid-fallback" if provider == "openrouter" else "")
    wire.replies.append(503)
    request = packet("vfx_director")
    request[transport.LLM_MODEL_OVERRIDE_KEY] = "override/retry"
    with transport.llm_item_lease("transient-retry") as lease:
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


@pytest.mark.parametrize("provider,mode,schema", [
    pytest.param("openrouter", mode, True, id=f"pin-schema-{mode}") for mode in ("responses", "auto")
] + [pytest.param("openai_compat", "auto", False, id="stateless-full-dossier")])
def test_api_negotiation_preserves_authored_request_and_learns_capability(wire, provider, mode, schema):
    wire.configure(LLM_PROVIDER=provider, LLM_API_MODE=mode)
    wire.replies.extend([404, schema_error("https://primary.example/v1/chat/completions")] if schema else [404])
    request = packet("visual_director", schema=schema)
    request["reasoning"] = {"effort": "low"}
    request[transport.LLM_MODEL_OVERRIDE_KEY] = "override/author"
    before = copy.deepcopy(request)
    with transport.llm_item_lease("envelope-negotiation") as lease:
        result = transport.llm_chat_json(request, timeout=1)
        transport.llm_chat_json(request, timeout=1)
        assert lease.call_count == 2 and lease.failovers == []
        if provider == "openrouter":
            assert lease.context["openrouter_provider"] == PIN
    assert [url.rsplit("/", 1)[-1] for url, _, _ in wire.calls] == (["responses", "completions", "completions", "completions"] if schema else ["responses", "completions", "completions"])
    assert all(body.get("provider") == ({"only": [PIN], "allow_fallbacks": False} if provider == "openrouter" else None) for _, body, _ in wire.calls)
    assert all(body["model"] == "override/author" and transport.LLM_MODEL_OVERRIDE_KEY not in body for _, body, _ in wire.calls)
    expected_format = {"type": "json_schema", **request["response_format"]["json_schema"]} if schema else request["response_format"]
    assert wire.calls[0][1]["text"] == {"format": expected_format}
    assert wire.calls[0][1]["reasoning"] == request["reasoning"]
    assert [body["response_format"]["type"] for _, body, _ in wire.calls[1:]] == (["json_schema", "json_object", "json_object"] if schema else ["json_object", "json_object"])
    assert all(body["messages"] == request["messages"] and body["reasoning"] == request["reasoning"] for _, body, _ in wire.calls[1:])
    causes = (["json_schema_to_json_object_fallback"] if schema else []) + ["responses_to_chat_fallback"]
    assert result["_debug"]["transportRetryCauses"] == causes
    assert result["_debug"]["transportRetryCount"] == len(causes)
    assert result["_debug"]["apiMode"] == "chat_completions"
    assert request == before
    footprint = result["_debug"]["transportFootprint"]
    assert set(footprint) == {"mode", "responseMode", "provider", "profile", "systemChars", "systemTokensEstimate",
        "userChars", "userTokensEstimate", "schemaChars", "schemaTokensEstimate", "repairChars", "repairTokensEstimate", "totalChars", "totalTokensEstimate"}
    assert (footprint["mode"], footprint["responseMode"], footprint["provider"], footprint["profile"]) == ("visual_director", "json_schema" if schema else "json_object", provider, "llm_1")
    assert footprint["systemChars"] > 0 and footprint["userChars"] > 0
    assert footprint["systemTokensEstimate"] > 0 and footprint["userTokensEstimate"] > 0
    assert footprint["repairChars"] == 0 and footprint["totalChars"] > footprint["userChars"]
    repair = transport._transport_footprint(packet("author_repair"), "author_repair")
    assert repair["userChars"] == 0 and repair["repairChars"] > 0


@pytest.mark.parametrize("capability", ["responses", "schema", "model"])
def test_capability_learning_is_case_sensitive_and_scoped_to_upstream_pin(wire, monkeypatch, capability):
    wire.configure(LLM_API_MODE="auto" if capability == "responses" else "chat_completions",
                   OPENROUTER_MODEL="auto" if capability == "model" else "vendor/model")
    first = transport._primary_llm_context()
    if capability == "model":
        discovered = []
        monkeypatch.setattr(transport, "http_get_json", lambda url, **kw: discovered.append(url) or {"data": [{"id": f"vendor/advertised-{len(discovered)}:free"}]})
        assert transport.resolve_llm_model(first) == "vendor/advertised-1:free"
    else:
        wire.replies.append(404 if capability == "responses" else schema_error("https://primary.example/v1/chat/completions"))
        transport.llm_chat_json(packet(schema=capability == "schema"), timeout=1)
    monkeypatch.setattr(transport, "OPENROUTER_PROVIDER", "OtherVendor/Exact-Endpoint")
    second = transport._primary_llm_context()
    assert transport._llm_context_key(first) != transport._llm_context_key(second)
    assert transport._llm_context_key(first) != transport._llm_context_key({**first, "openrouter_provider": PIN.lower()})
    if capability == "model":
        assert transport.resolve_llm_model(second) == "vendor/advertised-2:free"
        assert transport.resolve_llm_model(first) == "vendor/advertised-1:free"
        assert len(discovered) == len(transport._RESOLVED_LLM_MODELS) == 2
    else:
        result = transport.llm_chat_json(packet(schema=capability == "schema"), timeout=1)
        if capability == "responses":
            assert result["_debug"]["apiMode"] == "responses"
            assert [url.rsplit("/", 1)[-1] for url, _, _ in wire.calls] == ["responses", "completions", "responses"]
            assert len(transport._RESPONSES_CAPABILITY) == 2
        else:
            assert [body["response_format"]["type"] for _, body, _ in wire.calls] == ["json_schema", "json_object", "json_schema"]
        assert [body["provider"]["only"][0] for _, body, _ in wire.calls] == [PIN, PIN, "OtherVendor/Exact-Endpoint"]


@pytest.mark.parametrize("mode", ["chat_completions", "responses"])
def test_pin_diagnostics_report_routing_not_credentials(wire, monkeypatch, mode):
    wire.configure(LLM_API_MODE=mode, LLM_POOL_PROFILES=({"id": "llm_2", "enabled": True, "provider": "openrouter", "model": "vendor/secondary",
        "api_mode": mode, "openrouter_provider": "SecondaryVendor/Endpoint"},),
        LLM_FALLBACK_PROVIDER="openrouter", LLM_FALLBACK_MODEL="vendor/fallback", LLM_FALLBACK_OPENROUTER_PROVIDER="FallbackVendor/Endpoint")
    events = []
    monkeypatch.setattr(transport, "log_event", lambda level, message, data=None: events.append((message, data or {})))
    view = transport.llm_auth_snapshot()
    assert view["openrouterProvider"] == PIN
    assert [profile["openrouterProvider"] for profile in view["pool"]] == [PIN, "SecondaryVendor/Endpoint"]
    assert view["fallback"]["openrouterProvider"] == "FallbackVendor/Endpoint"
    with transport.llm_item_lease("pin-diagnostics") as lease:
        result = transport.llm_chat_json(packet(), timeout=1)
        snapshot = lease.snapshot()
        assert snapshot["openrouterProvider"] == result["_debug"]["openrouterProvider"] == PIN
    diagnosis = transport.request_shape_rejection_diagnosis(schema_error("https://primary.example/api/v1/chat/completions"), packet(schema=True), transport._primary_llm_context())
    assert diagnosis is not None and diagnosis["openrouterProvider"] == PIN
    # The historical operator-error log contract belongs to Chat Completions.
    wire.configure(LLM_API_MODE="chat_completions")
    wire.replies.append(402)
    with pytest.raises(urllib.error.HTTPError):
        transport.llm_chat_json(packet(), timeout=1)
    errors = [data for message, data in events if message == "LLM HTTP error"]
    assert errors and all(data["openrouterProvider"] == PIN for data in errors)
    for surface in (view, snapshot, result["_debug"], diagnosis, events):
        assert "synthetic-primary-key" not in json.dumps(surface)
        assert '"api_key"' not in json.dumps(surface)


@pytest.mark.parametrize("scenario,model,url,body,calls,expected", [
    pytest.param("tokens", "gemini-3.1-flash-lite", "https://provider.example/v1/chat/completions", b"x" * 20_000, 4, [12.0, 12.0, 36.0], id="gemini-token-window"),
    pytest.param("requests", "gemma-3-27b", "https://provider.example/v1/chat/completions", b"{}", 2, [62.0], id="gemma-request-window"),
    pytest.param("local", "gemini-3.1-flash-lite", "http://127.0.0.1:8085/v1/chat/completions", b"x" * 20_000, 2, [], id="loopback-exempt"),
    pytest.param("429", "gemini-3.1-flash-lite", "https://provider.example/v1/chat/completions", b"{}", 1, [75.0], id="retry-after"),
])
def test_remote_rate_budget_is_shared_token_aware_and_429_safe(wire, monkeypatch, scenario, model, url, body, calls, expected):
    clock, sleeps = [1000.0], []
    def sleep(seconds):
        sleeps.append(round(float(seconds), 3))
        clock[0] += float(seconds)
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(transport.time, "sleep", sleep)
    if scenario == "429":
        headers = Message()
        headers["Retry-After"] = "75"
        transport._mark_remote_rate_limited(url, {"model": model}, urllib.error.HTTPError(url, 429, "rate limited", headers, None))
    for ordinal in range(calls):
        target = "http://localhost:1234/v1/chat/completions" if scenario == "local" and ordinal else url
        transport._reserve_remote_rate_slot(target, {"model": model}, body)
    assert sleeps == expected
    if scenario == "tokens":
        assert sum(count for _, count in transport._LLM_RATE_STATE[next(iter(transport._LLM_RATE_STATE))]["events"]) == 15_000
    if scenario == "local":
        assert transport._LLM_RATE_STATE == {}


def test_concurrent_leases_isolate_profile_sequence_and_response_chain(wire, monkeypatch):
    wire.configure(LLM_PROVIDER="openai_compat", LLM_API_MODE="responses", LLM_POOL_PROFILES=tuple({
        "id": f"llm_{index}", "enabled": True, "provider": "openai_compat",
        "base_url": f"https://{label}.example/v1", "api_key": label,
        "model": f"model-{label}", "api_mode": "responses",
    } for index, label in ((2, "two"), (3, "three"))))
    worker_count = 12
    barrier = threading.Barrier(worker_count)
    call_lock = threading.Lock()
    chains: dict[str, list[str]] = {}
    profile_calls: dict[str, list[str]] = {}

    def fake_http_json(url, payload, timeout=10, headers=None):
        assert url.endswith("/responses")
        recipe = str(json.loads(payload["input"][0]["content"])["recipe"])
        previous = str(payload.get("previous_response_id") or "")
        with call_lock:
            chain = chains.setdefault(recipe, [])
            chain.append(previous)
            ordinal = len(chain)
            profile_calls.setdefault(recipe, []).append(url)
        expected_previous = "" if ordinal == 1 else f"resp_{recipe}_1"
        assert previous == expected_previous
        return {
            "id": f"resp_{recipe}_{ordinal}",
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
        }

    monkeypatch.setattr(transport, "http_json", fake_http_json)

    def run_item(index: int) -> dict[str, object]:
        recipe = f"concurrent_{index}"
        assert transport.current_llm_item_lease() is None
        with transport.llm_item_lease(recipe) as lease:
            assert transport.current_llm_item_lease() is lease
            barrier.wait(timeout=5)
            payload = packet("visual_director")
            payload["messages"][1]["content"] = json.dumps({"recipe": recipe})
            transport.llm_chat_json(payload, timeout=1)
            transport.llm_chat_json(payload, timeout=1)
            inside_snapshot = lease.snapshot()
            result = {
                "recipe": recipe,
                "leaseId": lease.lease_id,
                "profileId": lease.profile_id,
                "callCount": inside_snapshot["callCount"],
                "stages": inside_snapshot["stages"],
            }
        result["cleanAfter"] = transport.current_llm_item_lease() is None
        return result

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(run_item, range(worker_count)))

    lease_ids = [str(row["leaseId"]) for row in results]
    assert len(set(lease_ids)) == worker_count
    assert sorted(int(lease_id.rsplit(":", 1)[1]) for lease_id in lease_ids) == list(range(1, worker_count + 1))
    assert Counter(str(row["profileId"]) for row in results) == Counter({"llm_1": 4, "llm_2": 4, "llm_3": 4})
    assert all(row["callCount"] == 2 and len(row["stages"]) == 2 and row["cleanAfter"] for row in results)
    assert all(chain == ["", f"resp_{recipe}_1"] for recipe, chain in chains.items())
    assert all(len(set(urls)) == 1 for urls in profile_calls.values())
    assert transport.current_llm_item_lease() is None

    try:
        with transport.llm_item_lease("exception_cleanup"):
            raise RuntimeError("synthetic parser failure")
    except RuntimeError as exc:
        assert str(exc) == "synthetic parser failure"
    assert transport.current_llm_item_lease() is None
