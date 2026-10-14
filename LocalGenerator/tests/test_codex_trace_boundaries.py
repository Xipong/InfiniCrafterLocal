"""Offline synthetic credential and trace-clear boundary regressions."""

import io
import json
import threading
import pytest
from infini_local.services import codex_auth as auth, codex_text_backend as text
from infini_local.storage import trace_runtime as trace, trace_tools


class Response(io.BytesIO):
    status = 200


@pytest.fixture
def recording(monkeypatch, tmp_path):
    assert trace.flush_codex_transport(5)
    monkeypatch.setattr(trace, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace, "PROMPT_TRACE_FILE", tmp_path / "prompt_trace.ndjson")
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    yield tmp_path
    assert trace.flush_codex_transport(5)


@pytest.mark.parametrize("ending", ["complete", "incomplete", "unframed", "malformed_tail", "escaped_malformed_tail", "parts"])
def test_split_stream_credentials_never_reach_artifacts(recording, monkeypatch, ending):
    secret = "vEtAq9QvRu8RsTa7BkFo6PnCx5MdHe4Zy"
    creds = auth.Credentials(secret, "fixture-refresh", "fixture-account", 9999999999)
    monkeypatch.setattr(auth, "get_credentials", lambda: creds)
    fragments = [secret[i : i + 6] for i in range(0, len(secret), 6)]
    events = [{"type": "response.output_text.delta", "delta": f} for f in fragments]
    if ending == "parts":
        events = [
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "output": [
                        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f} for f in fragments]}
                    ],
                },
            }
        ]
    elif ending == "complete":
        events.append({"type": "response.completed", "response": {"status": "completed"}})
    elif ending == "incomplete":
        events.append({"type": "response.incomplete"})
    raw = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
    if ending == "unframed":
        raw = raw[:-1]
    elif ending in {"malformed_tail", "escaped_malformed_tail"}:
        raw = raw[:-4]
        if ending == "escaped_malformed_tail":
            raw = raw.replace(b'"delta":', b'"\\u0064elta":')

    def opened(req, *, deadline, on_open=None):
        if on_open is not None:
            on_open()
        return Response(raw)

    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    with pytest.raises(auth.CodexError):
        text.generate_chat({"model": "fixture", "messages": [{"role": "user", "content": "fixture prompt"}]}, timeout=3)
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    fragments_rows = [r for r in rows if r["event"].startswith("sse_")]
    assert fragments_rows
    reason = "stream_redaction_unverified" if ending in {"malformed_tail", "escaped_malformed_tail"} else "stream_credential_redaction"
    assert all(r["artifact"] == {"status": "refused", "reason": reason} for r in fragments_rows)
    saved = b"".join(p.read_bytes() for p in recording.rglob("*.txt"))
    assert secret.encode() not in saved
    assert not any(f.encode() in saved for f in fragments)


def test_completed_calls_cannot_reappear_after_live_trace_clear(recording, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = trace_tools.persist_transport_artifact

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(trace_tools, "persist_transport_artifact", slow)
    trace.trace_codex_transport({"event": "request", "transportCallId": "finished-before-clear"}, raw=b"{}")
    assert entered.wait(1)
    trace.trace_codex_transport({"event": "call_end", "transportCallId": "finished-before-clear", "outcome": "success"})
    from infini_local.web.server_utility_routes import ServerUtilityRoutes

    route = object.__new__(ServerUtilityRoutes)
    route.app_version = "fixture"
    route.trace_files = tuple(recording / name for name in ["events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"])
    replies = []
    handler = type("Handler", (), {"json": lambda self, response: replies.append(response)})()
    route.trace_clear(handler)
    assert replies[0]["ok"] is True
    assert set(replies[0]["cleared"]) == set(map(str, route.trace_files))
    assert trace.TRACE_FILE.read_text() == ""
    release.set()
    assert trace.flush_codex_transport(5)
    saved = trace.TRACE_FILE.read_text()
    assert "finished-before-clear" not in saved
    assert trace.trace_codex_transport({"event": "request", "transportCallId": "started-after-clear"}, raw=b"{}")
    assert trace.flush_codex_transport(5)
    assert "started-after-clear" in trace.TRACE_FILE.read_text()


def test_sse_fragments_remain_private_until_attempt_boundary(recording):
    secret = "vEtAq9QvRu8RsTa7BkFo6PnCx5MdHe4Zy"
    prefix = secret[:12]
    raw = json.dumps({"type": "response.output_text.delta", "delta": prefix}).encode()
    identity = {"transportCallId": "fixture-boundary", "physicalAttemptIndex": 1}
    assert trace.trace_codex_transport({**identity, "event": "sse_event"}, raw=raw, secrets=(secret,))
    assert trace.flush_codex_transport(5)
    assert not (recording / "transport_artifacts").exists()
    assert trace.trace_codex_transport(
        {**identity, "event": "sse_event"},
        raw=json.dumps({"type": "response.output_text.delta", "delta": secret[12:]}).encode(),
        secrets=(secret,),
    )
    assert trace.trace_codex_transport({**identity, "event": "attempt_end"}, secrets=(secret,))
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert all(r["artifact"]["status"] == "refused" for r in rows if r["event"] == "sse_event")
    assert not (recording / "transport_artifacts").exists()


def test_clear_commit_lock_never_blocks_generation_observation(recording):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        with trace._CODEX_TRACE_COMMIT_LOCK:
            future = pool.submit(trace.trace_codex_transport, {"event": "request", "transportCallId": "during-clear"})
            assert future.result(timeout=1) is True
    assert trace.flush_codex_transport(5)


def test_stream_redaction_failure_refuses_artifacts_without_losing_metadata(recording, monkeypatch):
    def failed(_items):
        raise ValueError("fixture redaction failure")

    monkeypatch.setattr(trace, "_safe_sse_batch", failed)
    identity = {"transportCallId": "fixture-redaction-error", "physicalAttemptIndex": 1}
    assert trace.trace_codex_transport({**identity, "event": "sse_event"}, raw=b'{"type":"response.output_text.delta","delta":"x"}')
    assert trace.trace_codex_transport({**identity, "event": "attempt_end"})
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert rows[0]["artifact"] == {"status": "refused", "reason": "stream_redaction_failed"}
    assert rows[1]["event"] == "attempt_end"
    assert not (recording / "transport_artifacts").exists()


@pytest.mark.parametrize("limit", ["bytes", "events"])
def test_pending_sse_budget_refuses_without_retaining_raw(recording, monkeypatch, limit):
    if limit == "bytes":
        monkeypatch.setattr(trace, "_CODEX_TRACE_MAX_PENDING_BYTES", 1)
    else:
        monkeypatch.setattr(trace, "_CODEX_TRACE_MAX_PENDING_EVENTS", 1)
    identity = {"transportCallId": "fixture-limited", "physicalAttemptIndex": 1}
    for delta in ["first", "second"]:
        trace.trace_codex_transport({**identity, "event": "sse_event"}, raw=json.dumps({"delta": delta}).encode())
    assert trace.flush_codex_transport(5)
    assert not (recording / "transport_artifacts").exists()
    trace.trace_codex_transport({**identity, "event": "attempt_end"})
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert rows[0]["artifact"] == {"status": "refused", "reason": "pending_stream_limit"}
    assert rows[-1]["event"] == "attempt_end"
    assert not (recording / "transport_artifacts").exists()


def test_pending_attempts_are_bounded_without_missing_end_growth(recording, monkeypatch):
    monkeypatch.setattr(trace, "_CODEX_TRACE_MAX_PENDING_ATTEMPTS", 2)
    for index in range(5):
        trace.trace_codex_transport(
            {"transportCallId": str(index), "physicalAttemptIndex": 1, "event": "sse_event"}, raw=json.dumps({"delta": str(index)}).encode()
        )
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert len(rows) == 3
    assert all(row["artifact"]["reason"] == "pending_attempt_limit" for row in rows)
    assert not (recording / "transport_artifacts").exists()
    for index in range(5):
        trace.trace_codex_transport({"transportCallId": str(index), "physicalAttemptIndex": 1, "event": "attempt_end"})
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert {row["transportCallId"] for row in rows if row["event"] == "sse_event"} == {"3", "4"}


def test_call_end_refuses_private_stream_without_attempt_end(recording):
    trace.trace_codex_transport(
        {"transportCallId": "missing-end", "physicalAttemptIndex": 1, "event": "sse_event"}, raw=b'{"delta":"private partial"}'
    )
    trace.trace_codex_transport({"transportCallId": "missing-end", "event": "call_end"})
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert rows[0]["artifact"]["reason"] == "missing_attempt_boundary"
    assert not (recording / "transport_artifacts").exists()


def test_clear_discards_private_batch_and_separates_reused_identity(recording):
    identity = {"transportCallId": "reused-fixture", "physicalAttemptIndex": 1}
    trace.trace_codex_transport({**identity, "event": "sse_event"}, raw=b'{"delta":"before clear"}')
    assert trace.flush_codex_transport(5)
    trace.clear_trace_files([trace.TRACE_FILE])
    assert trace.flush_codex_transport(5)
    clean = b'{"delta":"after clear"}'
    trace.trace_codex_transport({**identity, "event": "sse_event"}, raw=clean)
    trace.trace_codex_transport({**identity, "event": "attempt_end"})
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert len(rows) == 2
    assert (recording / rows[0]["artifact"]["path"]).read_bytes() == clean
    assert len(list((recording / "transport_artifacts").glob("*.txt"))) == 1


def test_credential_split_between_delta_and_terminal_text_is_refused(recording):
    secret = "vEtAq9QvRu8RsTa7BkFo6PnCx5MdHe4Zy"
    identity = {"transportCallId": "cross-field", "physicalAttemptIndex": 1}
    for event in [
        {"type": "response.output_text.delta", "delta": secret[:12]},
        {"type": "response.completed", "response": {"output": [{"content": [{"text": secret[12:]}]}]}},
    ]:
        trace.trace_codex_transport({**identity, "event": "sse_event"}, raw=json.dumps(event).encode(), secrets=(secret,))
    trace.trace_codex_transport({**identity, "event": "attempt_end"})
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    assert all(row["artifact"]["reason"] == "stream_credential_redaction" for row in rows if row["event"] == "sse_event")
    assert not (recording / "transport_artifacts").exists()
