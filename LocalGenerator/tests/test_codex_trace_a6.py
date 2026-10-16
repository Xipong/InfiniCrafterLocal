"""Offline A6 regressions; synthetic provider data, never a live model probe."""
import io
import json

import pytest

from infini_local.services import codex_auth as auth, codex_text_backend as text
from infini_local.storage import trace_runtime as trace, trace_tools


class Response(io.BytesIO):
    status = 200


def test_only_end_boundaries_have_terminal_outcomes(monkeypatch):
    events = []
    def opened(req, *, deadline, on_open=None):
        assert on_open is not None
        on_open()
        return Response(b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n')
    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    with auth.generation_observations({}, events.append):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    for row in events:
        if row["event"] in {"attempt_end", "call_end"}:
            assert row["terminal"] is True
            assert row["outcome"] == "success"
        else:
            assert row["terminal"] is False
            assert row["outcome"] == "in_progress"
        assert isinstance(row["observedAt"], float)
    assert [row["event"] for row in events] == ["request", "post_start", "http_response", "sse_event", "attempt_end", "call_end"]


def test_sse_attempt_uses_one_hash_bound_artifact_with_exact_ranges(monkeypatch, tmp_path):
    import hashlib
    assert trace.flush_codex_transport(5)
    monkeypatch.setattr(trace, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    writes = []
    fsyncs = []
    native_fsync = trace_tools.os.fsync
    def fsync(fd):
        fsyncs.append(fd)
        return native_fsync(fd)
    monkeypatch.setattr(trace_tools.os, "fsync", fsync)
    original = trace_tools.persist_transport_artifact
    def persist(*args, **kwargs):
        writes.append(args[1])
        return original(*args, **kwargs)
    monkeypatch.setattr(trace_tools, "persist_transport_artifact", persist)
    identity = {"transportCallId": "a6-fixture", "physicalAttemptIndex": 1}
    raw_events = [json.dumps({"type": "response.output_text.delta", "delta": "я🙂 " + str(i)}, ensure_ascii=False).encode() for i in range(300)]
    for i, raw in enumerate(raw_events):
        trace.trace_codex_transport({**identity, "event": "sse_event", "observedAt": 1000.25 + i, "arrivalMs": i / 2}, raw=raw)
    trace.trace_codex_transport({**identity, "event": "attempt_end", "outcome": "success", "terminal": True})
    assert trace.flush_codex_transport(5)
    assert len(writes) == len(fsyncs) == 1
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    arrivals = [r for r in rows if r["event"] == "sse_event"]
    assert len(arrivals) == len(raw_events)
    assert len({r["artifact"]["path"] for r in arrivals}) == 1
    for i, (row, raw) in enumerate(zip(arrivals, raw_events)):
        artifact = row["artifact"]
        assert trace_tools.read_transport_artifact(tmp_path, artifact) == raw
        assert artifact["rangeSha256"] == hashlib.sha256(raw).hexdigest()
        assert row["observedAt"] == 1000.25 + i
        assert row["arrivalMs"] == i / 2
        assert row["persistedAt"] > row["observedAt"]
    # Existing frozen per-event format stays readable without rewriting evidence.
    legacy = original(tmp_path, b'{"legacy":"exact"}')
    assert trace_tools.read_transport_artifact(tmp_path, legacy) == b'{"legacy":"exact"}'
    corrupted = {**arrivals[0]["artifact"], "rangeSha256": "0" * 64}
    with pytest.raises(ValueError, match="hash"):
        trace_tools.read_transport_artifact(tmp_path, corrupted)


def test_pre_llm_failure_saves_both_exact_inputs_and_recipe_key(monkeypatch, tmp_path):
    import copy
    from infini_local.pipelines import combine_pipeline as pipeline, generation_debug
    assert trace.flush_codex_transport(5)
    monkeypatch.setattr(trace, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(generation_debug, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(generation_debug, "LAST_COMBINE_FAILURE_FILE", tmp_path / "last_combine_failure.json")
    secret = "fixture-failure-secret-never-save"
    monkeypatch.setenv("INFINI_SYNTHETIC_SECRET", secret)
    a = {"name": "A Ж", "accepted": {"zero": 0, "flag": False, "long": "я" * 70000}}
    b = {"name": "B", "accepted": {"tail": "exact B tail", "token": secret}}
    payload = {"itemA": a, "itemB": b, "worldId": "42", "unrelatedConfigSecret": secret}
    before = copy.deepcopy(payload)
    key = "r_exact-source-key"
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "canonicalize", lambda value: value)
    monkeypatch.setattr(pipeline, "recipe_key", lambda *args: key)
    monkeypatch.setattr(pipeline, "cache_get", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "begin_llm_item_lease", lambda *args, **kwargs: ("lease", "token"))
    monkeypatch.setattr(pipeline, "end_llm_item_lease", lambda *args: None)
    def rejected(*args):
        raise ValueError("pre-LLM fixture guard")
    monkeypatch.setattr(pipeline, "try_llm_plan", rejected)
    try:
        with pytest.raises(ValueError) as error:
            pipeline.combine(payload)
        snapshot = error.value._infini_failure_snapshot
        assert snapshot["stage"] == "01_gameplay_author"
        expected = {"itemA": a, "itemB": {**b, "accepted": {"tail": "exact B tail", "token": "[REDACTED]"}}, "recipeKey": key}
        assert snapshot["partialData"] == expected
        persisted = json.loads((tmp_path / "last_combine_failure.json").read_text())
        assert persisted == snapshot
        assert secret not in json.dumps(persisted)
        assert "unrelatedConfigSecret" not in json.dumps(persisted)
        assert payload == before
    finally:
        generation_debug.clear_combine_failure("fixture cleanup")


def test_requests_public_summary_and_preserves_authentic_summary_events(monkeypatch, tmp_path):
    import copy
    assert trace.flush_codex_transport(5)
    monkeypatch.setattr(trace, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(auth, "get_credentials", lambda: auth.Credentials("fixture-access", "fixture-refresh", "fixture-account", 9999999999))
    summary = "Public summary Ж: chose the authored contract."
    raw_events = [
        b'{ "type":"response.reasoning_summary_part.added", "summary_index":0, "part":{"type":"summary_text","text":""} }',
        json.dumps({"type": "response.reasoning_summary_text.delta", "summary_index": 0, "delta": summary}, ensure_ascii=False).encode(),
        json.dumps({"type": "response.reasoning_summary_text.done", "summary_index": 0, "text": summary}, ensure_ascii=False).encode(),
        json.dumps({"type": "response.output_item.done", "item": {"type": "reasoning", "summary": [{"type": "summary_text", "text": summary}]}}).encode(),
        b'{"type":"response.output_text.delta","delta":"{}"}',
        b'{"type":"response.output_item.done","item":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"{}"}]}}',
        b'{"type":"response.completed","response":{"status":"completed","usage":{"output_tokens_details":{"reasoning_tokens":17}}}}',
    ]
    sent = []
    def opened(req, *, deadline, on_open=None):
        assert on_open is not None
        on_open()
        sent.append(json.loads(req.data))
        return Response(b"".join(b"data: " + raw + b"\n\n" for raw in raw_events))
    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    packet = {"model": "fixture", "messages": [{"role": "user", "content": "Exact prompt"}], "reasoning": {"effort": "medium"}, "max_tokens": 1234}
    before = copy.deepcopy(packet)
    result = text.generate_chat(packet, timeout=3)
    assert sent[0]["reasoning"] == {"effort": "medium", "summary": "auto"}
    assert sent[0]["include"] == []  # encrypted reasoning is not requested
    assert "max_output_tokens" not in sent[0]
    assert result["choices"][0]["message"]["content"] == "{}"
    assert result["usage"]["output_tokens_details"]["reasoning_tokens"] == 17
    assert packet == before
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    arrivals = [r for r in rows if r["event"] == "sse_event"]
    assert [trace_tools.read_transport_artifact(tmp_path, r["artifact"]) for r in arrivals] == raw_events
    end = next(r for r in rows if r["event"] == "attempt_end")
    assert end["reasoningSummaryEventCount"] == 3
    assert end["reasoningSummaryReturned"] is True
    assert end["reasoningSummaryDeltaChars"] == len(summary)


@pytest.mark.parametrize("summary", [[], [{"type": "summary_text", "text": "Final-only public summary Ж"}]])
def test_summary_receipt_reports_provider_absence_without_inventing_text(monkeypatch, tmp_path, summary):
    assert trace.flush_codex_transport(5)
    monkeypatch.setattr(trace, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace, "TRACE_PROMPTS_ENABLED", True)
    item = {"type": "reasoning", "encrypted_content": "opaque-fixture-not-readable", "summary": summary}
    event = {"type": "response.completed", "response": {"status": "completed", "output": [item]}}
    raw = json.dumps(event, ensure_ascii=False).encode()
    def opened(req, *, deadline, on_open=None):
        assert on_open is not None
        on_open()
        return Response(b"data: " + raw + b"\n\n")
    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    with auth.generation_credentials(auth.Credentials("fixture-access", "fixture-refresh", "fixture-account", 9999999999), trace.trace_codex_transport):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    assert trace.flush_codex_transport(5)
    rows = [json.loads(line)["payload"] for line in trace.TRACE_FILE.read_text().splitlines()]
    end = next(r for r in rows if r["event"] == "attempt_end")
    assert end["reasoningSummaryReturned"] is bool(summary)
    assert end["reasoningSummaryEventCount"] == end["reasoningSummaryDeltaChars"] == 0
    arrival = next(r for r in rows if r["event"] == "sse_event")
    assert trace_tools.read_transport_artifact(tmp_path, arrival["artifact"]) == raw


def test_batch_receipts_keep_exact_offsets_after_credential_redaction(tmp_path):
    raws = [b'{"echo":"fixture-secret-aaa"}', b'{ "clean":"\\u0410", "dup":1, "dup":2 }']
    receipts = trace_tools.persist_transport_batch(tmp_path, raws, secrets=("fixture-secret-aaa",))
    assert trace_tools.read_transport_artifact(tmp_path, receipts[0]) == b'{"echo":"[REDACTED]"}'
    assert trace_tools.read_transport_artifact(tmp_path, receipts[1]) == raws[1]
    assert receipts[0]["sanitized"] is True and receipts[1]["sanitized"] is False


def test_summary_part_done_counts_readable_text_without_delta(monkeypatch):
    observations = []
    raw = b'{"type":"response.reasoning_summary_part.done","part":{"type":"summary_text","text":"Public final part"}}'
    def opened(req, *, deadline, on_open=None):
        assert on_open is not None
        on_open()
        return Response(b"data: " + raw + b'\n\ndata: {"type":"response.completed","response":{"status":"completed"}}\n\n')
    monkeypatch.setattr(auth, "urlopen_no_redirect", opened)
    with auth.generation_observations({}, observations.append):
        auth.post_sse(text.RESPONSES_URL, {"stream": True}, timeout=3)
    end = next(r for r in observations if r["event"] == "attempt_end")
    assert end["reasoningSummaryEventCount"] == 1
    assert end["reasoningSummaryReturned"] is True
    assert end["reasoningSummaryDeltaChars"] == 0
