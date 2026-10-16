"""Production Codex transport exercised only with labelled in-memory HTTP/SSE fixtures."""
from __future__ import annotations

import io
import json

import pytest

from infini_local.services import codex_auth as auth, codex_text_backend as text
from infini_local.storage import trace_runtime as trace, trace_tools


def install_opener(monkeypatch, opened):
    def observe_start(req, *, deadline, on_open=None):
        auth.remaining_seconds(deadline)
        if on_open is not None:
            on_open()
        return opened(req, deadline=deadline)
    monkeypatch.setattr(auth, "urlopen_no_redirect", observe_start)


class MemoryResponse(io.BytesIO):
    status = 200


def sse(*events):
    return b"".join(b"data: " + (event if isinstance(event, bytes) else json.dumps(event, ensure_ascii=False).encode()) + b"\n\n" for event in events)


@pytest.fixture
def recording(monkeypatch, tmp_path):
    monkeypatch.setattr(trace, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace, "PROMPT_TRACE_FILE", tmp_path / "prompt_trace.ndjson")
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setenv("INFINI_LLM_FALLBACK_NETWORK_FAILS", "2")
    monkeypatch.setenv("INFINI_SPRITE_RETRIES", "1")
    # These are fixture strings, never loaded from the user's session store.
    monkeypatch.setattr(auth, "get_credentials", lambda: auth.Credentials("fixture-access-secret", "fixture-refresh-secret", "fixture-account-secret", 9999999999))
    # Direct transport seam fixtures inject the same writer as generation backends;
    # auth/control-plane owners do not import storage or register a global writer.
    with auth.generation_credentials(auth.get_credentials(), trace.trace_codex_transport):
        yield tmp_path
    assert trace.flush_codex_transport(5)


def rows(root):
    assert trace.flush_codex_transport(5)
    path = root / "pipeline_trace.ndjson"
    return [row["payload"] for row in map(json.loads, path.read_text().splitlines()) if row["kind"] == "codex_transport"] if path.exists() else []


def test_stalled_failed_trace_writer_cannot_delay_post_or_sse_parsing(recording, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from infini_local.storage import trace_tools
    from infini_local.pipelines import llm_transport as llm
    entered, release = Event(), Event()
    original = trace_tools.append_ndjson
    def stalled(path, record, **kwargs):
        if record.get("kind") == "codex_transport":
            entered.set()
            assert release.wait(3), "fixture writer release missing"
            raise OSError("fixture stalled writer failed")
        return original(path, record, **kwargs)
    calls = []
    def opened(req, *, deadline):
        calls.append(req.data)
        return MemoryResponse(sse({"type": "response.output_text.delta", "delta": "{}"},
            {"type": "response.completed", "response": {"status": "completed"}}))
    monkeypatch.setattr(trace_tools, "append_ndjson", stalled)
    install_opener(monkeypatch, opened)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(llm.llm_chat_json, {"messages": [{"role": "user", "content": "fixture"}]}, timeout=.3)
        try:
            assert entered.wait(1), "real transport writer was not entered"
            result = future.result(timeout=1)
            assert result["choices"][0]["message"]["content"] == "{}"
            assert result["_debug"]["physicalAttemptCount"] == len(calls) == 1
        finally:
            release.set()


def test_clean_process_exit_drains_pending_transport_artifacts(recording):
    import os
    import subprocess
    import sys
    script = """
import atexit, threading
from pathlib import Path
from infini_local.storage import trace_runtime as trace, trace_tools
release, entered = threading.Event(), threading.Event()
original = trace_tools.persist_transport_artifact
def pending(*args, **kwargs):
    entered.set()
    if not release.wait(2): raise OSError('fixture exit gate')
    return original(*args, **kwargs)
trace_tools.persist_transport_artifact = pending
trace.trace_codex_transport({'event':'request','transportCallId':'fixture-exit'}, raw=b'{"fixture":"complete"}')
assert entered.wait(1)
# The exit handler unlocks the already pending sink; the trace owner's handler
# must drain it before interpreter teardown, without a caller flush.
atexit.register(release.set)
"""
    env = {**os.environ, "INFINI_CACHE_DIR": str(recording), "INFINI_TRACE_PROMPTS": "true", "INFINI_SKIP_CONFIG_FILE": "1"}
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    observed = rows(recording)
    assert len(observed) == 1 and observed[0]["transportCallId"] == "fixture-exit"
    assert (recording / observed[0]["artifact"]["path"]).read_bytes() == b'{"fixture":"complete"}'


def test_transport_ndjson_lock_does_not_block_generation_event_logging(recording, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from contextlib import contextmanager
    from infini_local.storage import trace_tools
    from infini_local.pipelines import llm_transport as llm
    entered, release = Event(), Event()
    original = trace_tools._ndjson_process_lock
    @contextmanager
    def stalled(path):
        with original(path):
            if path.name == "pipeline_trace.ndjson":
                entered.set()
                assert release.wait(3), "fixture NDJSON lock release missing"
            yield
    monkeypatch.setattr(trace_tools, "_ndjson_process_lock", stalled)
    def opened(*_a, **_k):
        assert entered.wait(1), "real trace lock was not acquired before HTTP read"
        return MemoryResponse(sse({"type": "response.output_text.delta", "delta": "{}"},
            {"type": "response.completed", "response": {"status": "completed"}}))
    install_opener(monkeypatch, opened)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(llm.llm_chat_json, {"messages": [{"role": "user", "content": "fixture"}]}, timeout=.3)
        try:
            assert entered.wait(1)
            assert future.result(timeout=1)["choices"][0]["message"]["content"] == "{}"
        finally:
            release.set()


def test_artifact_fsync_does_not_block_generation_event_logging(recording, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from infini_local.storage import trace_tools
    from infini_local.pipelines import llm_transport as llm
    entered, release = Event(), Event()
    def stalled_fsync(fd):
        entered.set()
        assert release.wait(3), "fixture fsync release missing"
    monkeypatch.setattr(trace_tools.os, "fsync", stalled_fsync)
    install_opener(monkeypatch, lambda *_a, **_k: MemoryResponse(sse(
        {"type": "response.output_text.delta", "delta": "{}"},
        {"type": "response.completed", "response": {"status": "completed"}})))
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(llm.llm_chat_json, {"messages": [{"role": "user", "content": "fixture"}]}, timeout=.3)
        try:
            assert entered.wait(1)
            assert future.result(timeout=1)["choices"][0]["message"]["content"] == "{}"
        finally:
            release.set()


def test_expired_before_real_opener_reports_zero_physical_posts(recording, monkeypatch):
    from infini_local.core import http_io
    from infini_local.pipelines import llm_transport as llm
    clock = [100.0]
    opened = []
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    class Opener:
        def open(self, req, timeout):
            opened.append(req.data)
            pytest.fail("expired call reached opener")
    def prepare(*handlers):
        clock[0] += 4
        return Opener()
    monkeypatch.setattr(auth, "urlopen_no_redirect", http_io.urlopen_no_redirect)
    monkeypatch.setattr(http_io.urlrequest, "build_opener", prepare)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    with pytest.raises(http_io.HttpDeadlineExceeded) as caught:
        llm.llm_chat_json({"messages": [{"role": "user", "content": "fixture"}]}, timeout=3)
    assert opened == []
    assert caught.value._infini_transport_debug["physicalAttemptCount"] == 0
    assert not any(row["event"] == "post_start" for row in rows(recording))


def test_concurrent_codex_calls_keep_join_and_attempt_state_request_local(recording, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from infini_local.pipelines import llm_transport as llm
    barrier = Barrier(2)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    def opened(req, *, deadline):
        barrier.wait(timeout=5)
        fact = json.loads(req.data)["input"][0]["content"][0]["text"]
        return MemoryResponse(sse({"type": "response.output_text.delta", "delta": fact}, {"type": "response.completed", "response": {"status": "completed"}}))
    install_opener(monkeypatch, opened)
    def call(index):
        with llm.llm_item_lease("fixture-" + str(index)):
            return llm.llm_chat_json({"messages": [{"role": "user", "content": str(index)}]}, timeout=3)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(call, [1, 2]))
    assert {result["choices"][0]["message"]["content"] for result in results} == {"1", "2"}
    identities = {result["_debug"]["logicalCallId"] for result in results}
    assert len(identities) == 2
    for identity in identities:
        observations = [row for row in rows(recording) if row["logicalCallId"] == identity]
        assert len({row["transportCallId"] for row in observations}) == 1
        assert len([row for row in observations if row["event"] == "post_start"]) == 1
        end = next(row for row in observations if row["event"] == "attempt_end")
        assert end["physicalAttemptIndex"] == 1 and end["textDeltaCount"] == 1


def test_observed_codex_zero_send_removes_unknown_scope(recording, monkeypatch):
    from infini_local.core.http_io import HttpDeadlineExceeded
    from infini_local.pipelines import llm_transport as llm
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    remaining = auth.remaining_seconds
    def expired_on_entry(deadline):
        # Only the native generation owner is stopped; no authentication or I/O.
        if auth._GENERATION_OBSERVATIONS.get()[1] is not None:
            raise HttpDeadlineExceeded("fixture stopped before POST")
        return remaining(deadline)
    monkeypatch.setattr(auth, "remaining_seconds", expired_on_entry)
    install_opener(monkeypatch, lambda *_a, **_k: pytest.fail("stopped transport sent POST"))
    with pytest.raises(HttpDeadlineExceeded) as caught:
        llm.llm_chat_json({"messages": [{"role": "user", "content": "fixture"}]}, timeout=3)
    debug = caught.value._infini_transport_debug
    assert debug["physicalAttemptCount"] == 0
    assert debug["physicalAttemptScope"] == "llm_generation_http_post" and debug["physicalAttempts"] == []


def test_malformed_provider_event_type_is_recorded_before_original_parser_rejects_it(recording, monkeypatch):
    raw = b'{"type":{"fixture-key":"fixture-value"},"duplicate":"first","duplicate":"second"}'
    install_opener(monkeypatch, lambda *_a, **_k: MemoryResponse(sse(raw)))
    # Preserve the current parser's error type; tracing must not repair the event.
    with pytest.raises(TypeError):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    arrival = next(row for row in rows(recording) if row["event"] == "sse_event")
    assert arrival["sseEventCount"] == 1
    assert trace_tools.read_transport_artifact(recording, arrival["artifact"]) == raw


@pytest.mark.parametrize("transport", ["text", "image"])
def test_trace_off_still_counts_physical_posts_but_never_traces_auth(recording, monkeypatch, transport):
    from infini_local.pipelines import llm_transport as llm
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", False)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    def opened(req, *, deadline):
        return MemoryResponse(sse({"type": "response.completed", "response": {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}]}}))
    install_opener(monkeypatch, opened)
    if transport == "text":
        result = llm.llm_chat_json({"messages": [{"role": "user", "content": "fixture"}]}, timeout=3)
        assert result["_debug"]["physicalAttemptCount"] == 1
    else:
        install_opener(monkeypatch, lambda *_a, **_k: MemoryResponse(b'{"data":[]}'))
        assert auth.post_json(auth._IMAGE_GENERATION_URL, {"prompt": "fixture"}) == {"data": []}
    assert not list(recording.iterdir())
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    class AuthOpener:
        def open(self, *_a, **_k):
            return MemoryResponse(b'{"fixture":true}')
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_a: AuthOpener())
    assert auth.post_json(auth.TOKEN_URL, {"refresh_token": "fixture-refresh-secret"}) == {"fixture": True}
    assert not list(recording.iterdir())


def test_incomplete_error_body_is_labelled_not_presented_as_complete_empty_response(recording, monkeypatch):
    from email.message import Message
    from http.client import IncompleteRead
    from urllib.error import HTTPError
    class Broken(MemoryResponse):
        def read1(self, *_a):
            raise IncompleteRead(b"fixture partial", 100)
    monkeypatch.setenv("INFINI_LLM_FALLBACK_NETWORK_FAILS", "1")
    def opened(req, *, deadline):
        raise HTTPError(req.full_url, 503, "fixture busy", Message(), Broken())
    install_opener(monkeypatch, opened)
    with pytest.raises(auth.CodexError, match="HTTP 503"):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    body = next(row for row in rows(recording) if row["event"] == "http_error_body")
    assert body["bodyComplete"] is False and body["bodyReadErrorType"] == "IncompleteRead"
    assert "artifact" not in body


def test_backoff_deadline_records_terminal_call_without_inventing_second_post(recording, monkeypatch):
    from email.message import Message
    from urllib.error import HTTPError
    from infini_local.core.http_io import HttpDeadlineExceeded
    clock = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(auth.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    calls = []
    def opened(req, *, deadline):
        calls.append(req.data)
        clock[0] += 2.9
        raise HTTPError(req.full_url, 503, "fixture busy", Message(), MemoryResponse(b'{}'))
    install_opener(monkeypatch, opened)
    with pytest.raises(HttpDeadlineExceeded):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    observations = rows(recording)
    assert len(calls) == len([row for row in observations if row["event"] == "post_start"]) == 1
    terminal = next(row for row in observations if row["event"] == "call_end")
    assert terminal["physicalAttemptCount"] == 1 and terminal["outcome"] == "failure"
    assert terminal["errorType"] == "HttpDeadlineExceeded"


def test_terminal_exception_redacts_refresh_echo_before_caller_logs_it(recording, monkeypatch):
    from email.message import Message
    from urllib.error import HTTPError
    def opened(req, *, deadline):
        raise HTTPError(req.full_url, 429, "fixture denied", Message(), MemoryResponse(b'{"error":{"message":"fixture-refresh-secret"}}'))
    install_opener(monkeypatch, opened)
    with pytest.raises(auth.CodexError) as caught:
        text.generate_chat({"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}]}, timeout=3)
    assert "fixture-refresh-secret" not in str(caught.value)


def test_eof_records_unframed_tail_and_zero_delta_count_without_parsing_it(recording, monkeypatch):
    payload = b'data: {"type":"response.completed","response":{"status":"completed"}}'
    install_opener(monkeypatch, lambda *_a, **_k: MemoryResponse(payload))
    with pytest.raises(auth.CodexError, match="before completion"):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    observations = rows(recording)
    end = next(row for row in observations if row["event"] == "attempt_end")
    assert end["sseEventCount"] == end["textDeltaCount"] == 0
    assert end["firstTextDeltaMs"] is None and end["lastTextDeltaMs"] is None
    tail = next(row for row in observations if row["event"] == "sse_unframed_tail")
    assert tail["accepted"] is False
    assert b"response.completed" in trace_tools.read_transport_artifact(recording, tail["artifact"])
    assert not any(row.get("terminalEventType") for row in observations)


@pytest.mark.parametrize("mode", ["off", "artifact_failure", "writer_failure"])
def test_optional_trace_is_fail_open_and_off_gates_all_transport_persistence(recording, monkeypatch, mode):
    from infini_local.storage import trace_tools
    completion = {"type": "response.completed", "response": {"status": "completed", "output": []}}
    install_opener(monkeypatch, lambda *_a, **_k: MemoryResponse(sse(completion)))
    def failed(*_a, **_k):
        raise OSError("fixture private failure")
    if mode == "off":
        monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", False)
        monkeypatch.setattr(trace_tools, "persist_transport_artifact", lambda *_a, **_k: pytest.fail("OFF artifact write"))
        monkeypatch.setattr(trace_tools, "append_ndjson", lambda *_a, **_k: pytest.fail("OFF event write"))
    elif mode == "artifact_failure":
        monkeypatch.setattr(trace_tools.os, "replace", failed)
    else:
        monkeypatch.setattr(trace_tools, "append_ndjson", failed)
    result = auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    assert result == completion["response"]
    assert trace.flush_codex_transport(5)
    assert not list(recording.rglob(".transport-*"))
    if mode == "off":
        assert not list(recording.iterdir())
    elif mode == "artifact_failure":
        request = next(row for row in rows(recording) if row["event"] == "request")
        assert request["artifact"] == {"status": "refused", "reason": "OSError"}


def test_error_reader_exception_partial_is_preserved_without_claiming_entity_body(recording, monkeypatch):
    from http.client import IncompleteRead
    from email.message import Message
    from urllib.error import HTTPError
    body = json.dumps({"error": {"message": "x" * 70000}}).encode()
    partial = b"reader-owned-opaque-partial-bytes"
    class BrokenTail(MemoryResponse):
        def read1(self, amount: int | None = -1):
            if self.tell() >= 65537:
                raise IncompleteRead(partial, 100)
            return super().read1(amount)
    def opened(req, *, deadline):
        raise HTTPError(req.full_url, 429, "fixture denied", Message(), BrokenTail(body))
    install_opener(monkeypatch, opened)
    with pytest.raises(auth.CodexError, match="HTTP 429: request rejected"):
        text.generate_chat({"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}]}, timeout=3)
    observed = rows(recording)
    error_body = next(row for row in observed if row["event"] == "http_error_body")
    assert error_body["bodyComplete"] is False
    assert trace_tools.read_transport_artifact(recording, error_body["artifact"]) == body[:65537]
    exception_bytes = next(row for row in observed if row["event"] == "reader_exception_partial")
    assert exception_bytes["byteScope"] == "reader_exception_partial_unclassified"
    assert trace_tools.read_transport_artifact(recording, exception_bytes["artifact"]) == partial


@pytest.mark.parametrize("status,expected_posts", [(429, 1), (503, 2)])
def test_slow_oversized_error_drain_does_not_delay_terminal_or_retry(recording, monkeypatch, status, expected_posts):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from email.message import Message
    from urllib.error import HTTPError
    calls, handles = [], []
    entered, release = Event(), Event()
    body = json.dumps({"error": {"message": "x" * 70000}}).encode()
    class SlowTail(MemoryResponse):
        def read1(self, amount: int | None = -1):
            if self.tell() >= 65537:
                entered.set()
                assert release.wait(3), "diagnostic tail release missing"
                raise OSError("fixture late tail unavailable")
            return super().read1(amount)
    def opened(req, *, deadline):
        calls.append(req.data)
        if len(calls) == 1:
            handle = SlowTail(body)
            handles.append(handle)
            raise HTTPError(req.full_url, status, "fixture denied", Message(), handle)
        return MemoryResponse(sse({"type": "response.completed", "response": {"status": "completed", "output": []}}))
    install_opener(monkeypatch, opened)
    with ThreadPoolExecutor(max_workers=1) as pool:
        from contextvars import copy_context
        future = pool.submit(copy_context().run, auth.post_sse, text.RESPONSES_URL, {"stream": True}, timeout=.8)
        try:
            assert entered.wait(1), "diagnostic tail not read"
            if status == 429:
                with pytest.raises(auth.CodexError, match="HTTP 429: request rejected"):
                    future.result(timeout=1)
            else:
                assert future.result(timeout=1) == {"status": "completed", "output": []}
            assert len(calls) == expected_posts
        finally:
            release.set()
    observed = rows(recording)
    error_body = next(row for row in observed if row["event"] == "http_error_body")
    assert error_body["bodyComplete"] is False and error_body["bodyReadErrorType"] == "OSError"
    saved = trace_tools.read_transport_artifact(recording, error_body["artifact"])
    assert saved == body[:65537]
    assert all(handle.closed for handle in handles)


@pytest.mark.parametrize("status,expected_posts", [(429, 1), (503, 2)])
def test_oversized_error_artifact_is_complete_without_changing_legacy_error_projection(recording, monkeypatch, status, expected_posts):
    from email.message import Message
    from urllib.error import HTTPError
    handles, calls = [], []
    body = json.dumps({"error": {"message": "fixture-refresh-secret " + "x" * 70000}}).encode()
    def opened(req, *, deadline):
        calls.append(req.data)
        handle = MemoryResponse(body)
        handles.append(handle)
        raise HTTPError(req.full_url, status, "fixture denied", Message(), handle)
    install_opener(monkeypatch, opened)
    with pytest.raises(auth.CodexError) as caught:
        text.generate_chat({"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}]}, timeout=3)
    assert str(caught.value) == f"OpenAI HTTP {status}: request rejected"
    assert len(calls) == expected_posts
    bodies = [row for row in rows(recording) if row["event"] == "http_error_body"]
    assert len(bodies) == expected_posts
    for row in bodies:
        assert row["bodyComplete"] is True
        saved = trace_tools.read_transport_artifact(recording, row["artifact"])
        assert b"x" * 70000 in saved and b"fixture-refresh-secret" not in saved
    assert all(handle.closed for handle in handles)


@pytest.mark.parametrize("status,expected_posts", [(429, 1), (503, 2)])
def test_http_failure_persists_sanitized_full_body_and_actual_retry_identity(recording, monkeypatch, status, expected_posts):
    from email.message import Message
    from urllib.error import HTTPError
    calls = []
    body = json.dumps({"error": {"message": "fixture-refresh-secret " + "x" * 50000}, "fixture-account-secret": "fixture-access-secret"}).encode()
    def opened(req, *, deadline):
        calls.append(req.data)
        raise HTTPError(req.full_url, status, "fixture denied", Message(), MemoryResponse(body))
    install_opener(monkeypatch, opened)
    with pytest.raises(auth.CodexError, match=f"HTTP {status}"):
        text.generate_chat({"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}]}, timeout=3)
    assert len(calls) == expected_posts
    observations = rows(recording)
    ends = [row for row in observations if row["event"] == "attempt_end"]
    assert [row["physicalAttemptIndex"] for row in ends] == list(range(1, expected_posts + 1))
    assert [row["terminal"] for row in ends] == ([False, True] if status == 503 else [True])
    bodies = [row for row in observations if row["event"] == "http_error_body"]
    assert len(bodies) == expected_posts
    for row in bodies:
        saved = trace_tools.read_transport_artifact(recording, row["artifact"])
        assert b"fixture-" not in saved and b"x" * 50000 in saved
        assert row["httpStatus"] == status


@pytest.mark.parametrize("scenario", ["incomplete", "malformed", "eof", "late"])
def test_failed_stream_observations_never_invent_completion(recording, monkeypatch, scenario):
    clock = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    class Late(MemoryResponse):
        def readline(self, *args):
            line = super().readline(*args)
            if line == b"\n":
                clock[0] += 4
            return line
    payload = sse({"type": "response.output_text.delta", "delta": "partial"})
    if scenario == "incomplete":
        payload += sse({"type": "response.incomplete", "response": {"usage": {"output_tokens": 1}}})
    if scenario == "malformed":
        payload += sse(b'{"type":broken')
    if scenario == "late":
        payload = sse({"type": "response.completed", "response": {"status": "completed"}})
    install_opener(monkeypatch, lambda *_a, **_k: (Late if scenario == "late" else MemoryResponse)(payload))
    with pytest.raises(auth.CodexError):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    observations = rows(recording)
    end = next(row for row in observations if row["event"] == "attempt_end")
    assert end["outcome"] == "failure" and end["terminal"] is True
    assert len([row for row in observations if row["event"] == "post_start"]) == 1
    assert not any(row["event"] == "sse_event" and row.get("eventType") == "response.completed" for row in observations)
    if scenario == "late":
        late = next(row for row in observations if row["event"] == "sse_late_read")
        assert late["arrivalMs"] >= 3000 and late["accepted"] is False
        assert b"response.completed" in trace_tools.read_transport_artifact(recording, late["artifact"])
    elif scenario == "incomplete":
        assert end["terminalEventType"] == "response.incomplete"
    elif scenario == "malformed":
        assert end["sseEventCount"] == 2


def test_image_http_body_redacts_session_echoes_without_changing_png(recording, monkeypatch):
    import base64
    from PIL import Image
    from infini_local.services import codex_image_backend as image
    buffer = io.BytesIO()
    Image.new("RGBA", (2, 3), (10, 20, 30, 255)).save(buffer, format="PNG")
    body = {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}], "fixture-refresh-secret": {"metadata": json.dumps({"echo": "fixture-refresh-secret"})}}
    seen = []
    def opened(req, *, deadline):
        seen.append(req.data)
        return MemoryResponse(json.dumps(body).encode())
    install_opener(monkeypatch, opened)
    target = recording / "fixture.png"
    image.generate_image("authored Ж prompt", "avoid text", target, model="fixture-model", quality="low", size="auto", timeout=3)
    assert target.read_bytes() == buffer.getvalue()
    observations = rows(recording)
    body_row = next(row for row in observations if row["event"] == "http_body")
    saved = trace_tools.read_transport_artifact(recording, body_row["artifact"])
    assert b"fixture-refresh-secret" not in saved
    request = next(row for row in observations if row["event"] == "request")
    assert trace_tools.read_transport_artifact(recording, request["artifact"]) == seen[0]
    assert json.loads(seen[0])["prompt"] == "authored Ж prompt\n\nAvoid: avoid text"


@pytest.mark.parametrize("prefix", ["", "\\q", "\\u2"])
@pytest.mark.parametrize("suffix", ["", "\\", "\\u2", "\\q"])
@pytest.mark.parametrize("nested", [False, True])
def test_partial_escaped_credential_is_redacted_before_artifact_or_event_persistence(recording, monkeypatch, nested, suffix, prefix):
    from infini_local.storage import trace_tools
    secret = 'fixture/opaque"secret\\value'
    incomplete = '{"error":{"message":"' + prefix + json.dumps(secret)[1:-1] + "x" * 70000 + suffix
    raw = (json.dumps({"echo": incomplete}) if nested else incomplete).encode()
    receipt = trace_tools.persist_transport_artifact(recording, raw, secrets=(secret,))
    assert receipt["status"] == "stored" and receipt["sanitized"] is True
    saved = (recording / receipt["path"]).read_text()
    encoded = json.dumps(secret)[1:-1]
    assert secret not in saved and encoded not in saved
    assert "[REDACTED]" in saved and "x" * 70000 in saved
    if not nested:
        assert not saved.endswith('"'), "redaction fabricated a completed JSON string"
    monkeypatch.setenv("INFINI_SYNTHETIC_SECRET", secret)
    trace_tools.log_event(recording, "info", "fixture partial metadata", {"echo": incomplete})
    event = json.loads((recording / "events.ndjson").read_text())
    assert encoded not in event["payload"]["echo"]


def test_transport_artifacts_redact_all_json_members_and_nested_escaped_strings(recording, monkeypatch):
    from infini_local.storage import trace_tools
    secret = 'fixture/opaque"secret\\value'
    monkeypatch.setenv("INFINI_SYNTHETIC_SECRET", secret)
    inner = '{' + json.dumps(secret) + ':' + json.dumps(secret) + ',"dup":' + json.dumps(secret) + ',"dup":"clean"}'
    nested = inner
    for _ in range(6):
        nested = json.dumps(nested)
    raw = ('{"echo":' + nested + ',"dup":' + json.dumps(secret) + ',"dup":"clean"}').encode()
    receipt = trace_tools.persist_transport_artifact(recording, raw)
    assert receipt["status"] == "stored"
    saved = (recording / receipt["path"]).read_text()
    def all_members(value):
        if isinstance(value, str):
            assert secret not in value
            try:
                decoded = json.loads(value, object_pairs_hook=lambda pairs: pairs)
            except ValueError:
                return
            all_members(decoded)
        elif isinstance(value, (tuple, list)):
            for child in value:
                all_members(child)
    all_members(json.loads(saved, object_pairs_hook=lambda pairs: pairs))
    assert receipt["sanitized"] is True
    trace_tools.log_event(recording, "info", "fixture nested metadata", {"echo": raw.decode()})
    all_members(json.loads((recording / "events.ndjson").read_bytes())["payload"]["echo"])
    clean = b'{ "dup":1, "dup":2, "escaped":"\\u0410", "path":"raw/path" }'
    receipt = trace_tools.persist_transport_artifact(recording, clean)
    assert (recording / receipt["path"]).read_bytes() == clean and receipt["sanitized"] is False


def test_llm_logical_summary_counts_actual_codex_retry_posts(recording, monkeypatch):
    from email.message import Message
    from urllib.error import HTTPError
    from infini_local.pipelines import llm_transport as llm
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "fixture-model")
    calls = []
    def opened(req, *, deadline):
        calls.append(req.data)
        if len(calls) == 1:
            raise HTTPError(req.full_url, 503, "fixture busy", Message(), MemoryResponse(b'{"error":{"message":"fixture busy"}}'))
        return MemoryResponse(sse({"type": "response.completed", "response": {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}]}}))
    install_opener(monkeypatch, opened)
    with llm.llm_item_lease("fixture-join") as lease:
        result = llm.llm_chat_json(llm.with_llm_stage({"messages": [{"role": "user", "content": "fact"}]}, "planner"), timeout=3)
        debug = result["_debug"]
        assert debug["physicalAttemptCount"] == len(calls) == 2
        assert debug["physicalAttemptScope"] == "llm_generation_http_post"
        assert [row["httpStatus"] for row in debug["physicalAttempts"]] == [503, 200]
        assert [row["physicalAttemptIndex"] for row in debug["physicalAttempts"]] == [1, 2]
        assert [row["terminal"] for row in debug["physicalAttempts"]] == [False, True]
        assert lease.call_count == 1
        for row in rows(recording):
            assert row["logicalCallId"] == debug["logicalCallId"]
            assert row["leaseId"] == lease.lease_id and row["stage"] == "planner"
    assert calls[0] == calls[1]


def test_sse_records_authentic_terminal_before_parser_reconstructs_output(recording, monkeypatch):
    events = [{"type": "response.output_text.delta", "delta": "first Ж"},
              {"type": "response.output_text.delta", "delta": " last"},
              {"type": "response.completed", "response": {"id": "fixture-response", "status": "completed", "usage": {"input_tokens": 8}}}]
    install_opener(monkeypatch, lambda *_a, **_k: MemoryResponse(sse(*events)))
    result = auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    assert result["output"][0]["content"][0]["text"] == "first Ж last"
    observations = rows(recording)
    arrivals = [row for row in observations if row["event"] == "sse_event"]
    assert [row["eventType"] for row in arrivals] == [event["type"] for event in events]
    assert [row["sseEventCount"] for row in arrivals] == [1, 2, 3]
    terminal = arrivals[-1]
    assert json.loads(trace_tools.read_transport_artifact(recording, terminal["artifact"])) == events[-1]
    assert "output" not in json.loads(trace_tools.read_transport_artifact(recording, terminal["artifact"]))["response"]
    end = next(row for row in observations if row["event"] == "attempt_end")
    assert end["sseEventCount"] == 3 and end["textDeltaCount"] == 2
    assert 0 <= end["firstTextDeltaMs"] <= end["lastTextDeltaMs"] <= end["elapsedMs"]
    assert end["terminalEventType"] == "response.completed"


def test_effective_wire_and_actual_post_are_traced_without_headers(recording, monkeypatch):
    seen = []
    def opened(req, *, deadline):
        seen.append(req.data)
        return MemoryResponse(sse({"type": "response.completed", "response": {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}]}}))
    install_opener(monkeypatch, opened)
    packet = {"model": "fixture-model", "messages": [{"role": "system", "content": "Exact\r\n  Ж rules."}, {"role": "user", "content": "fixture fact"}], "response_format": {"type": "json_object"}, "max_tokens": 30}
    result = text.generate_chat(packet, timeout=3)
    assert result["choices"][0]["message"]["content"] == "{}"
    observations = rows(recording)
    request = next(row for row in observations if row["event"] == "request")
    assert trace_tools.read_transport_artifact(recording, request["artifact"]) == seen[0]
    assert json.loads(seen[0])["instructions"] == packet["messages"][0]["content"]
    assert "max_output_tokens" not in json.loads(seen[0])
    start = next(row for row in observations if row["event"] == "post_start")
    response = next(row for row in observations if row["event"] == "http_response")
    end = next(row for row in observations if row["event"] == "attempt_end")
    assert start["physicalAttemptIndex"] == end["physicalAttemptIndex"] == 1
    assert start["transportCallId"] == request["transportCallId"] == end["transportCallId"]
    assert response["httpStatus"] == end["httpStatus"] == 200
    assert end["networkStarted"] is True and end["outcome"] == "success" and end["terminal"] is True
    assert end["openMs"] >= 0 and end["readMs"] >= 0 and end["elapsedMs"] >= 0
    persisted = b"".join(path.read_bytes() for path in recording.rglob("*") if path.is_file())
    for forbidden in (b"Authorization", b"ChatGPT-Account", b"fixture-access-secret", b"fixture-refresh-secret", b"fixture-account-secret"):
        assert forbidden not in persisted
