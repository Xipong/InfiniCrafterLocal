from __future__ import annotations

import json
import socket

import pytest

from infini_local.storage import trace_runtime, trace_tools


def _record(monkeypatch, cache, text):
    monkeypatch.setattr(trace_runtime, "CACHE_DIR", cache)
    monkeypatch.setattr(trace_runtime, "TRACE_FILE", cache / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace_runtime, "PROMPT_TRACE_FILE", cache / "prompt_trace.ndjson")
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(socket.socket, "connect", lambda *args, **kwargs: pytest.fail("trace reader reached network"))
    trace_runtime.trace_event("response", "LLM:visual_director", "exact response", response=text)
    return trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 1)[0]


@pytest.fixture
def exact():
    return ' \r\n {"duplicate":1,"duplicate":2,"escaped":"\\u0410","html":"<script>&"} ' + "ж" * 9000 + " READER_TAIL\r\n "


@pytest.mark.parametrize("sensitive", [False, True])
def test_actual_replay_loads_complete_compacted_trace_without_network(monkeypatch, tmp_path, exact, sensitive):
    from infini_local.pipelines.transport.client import llm_chat_json
    credential = "opaque-credential-for-reader-123456789"
    monkeypatch.setenv("INFINI_LLM_API_KEY", credential)
    text = exact + (credential if sensitive else "")
    row = _record(monkeypatch, tmp_path, text)
    expected = (tmp_path / row["response"]["_traceText"]["path"]).read_bytes()
    assert credential.encode() not in expected
    if sensitive:
        assert b"[REDACTED]" in expected
    else:
        assert expected == exact.encode()
    monkeypatch.setenv("INFINI_LLM_REPLAY_RAW", str(trace_runtime.PROMPT_TRACE_FILE))
    def forbidden(*args, **kwargs):
        pytest.fail("offline replay reached network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = llm_chat_json({"_infini_stage": "visual_director", "_infini_model_override": "offline-model", "messages": []}, timeout=1)
    assert result["choices"][0]["message"]["content"].encode() == expected
    assert result["_debug"]["replay"] is True


@pytest.mark.parametrize("fault", ["missing", "tampered", "outside"])
def test_actual_replay_refuses_broken_receipt_not_preview_or_raw_ndjson(monkeypatch, tmp_path, exact, fault):
    from infini_local.pipelines.transport.client import llm_chat_json
    row = _record(monkeypatch, tmp_path, exact)
    receipt = row["response"]["_traceText"]
    target = tmp_path / receipt["path"]
    if fault == "missing":
        target.unlink()
    elif fault == "tampered":
        target.write_bytes(b"changed")
    else:
        receipt["path"] = "../outside.txt"
        trace_runtime.PROMPT_TRACE_FILE.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setenv("INFINI_LLM_REPLAY_RAW", str(trace_runtime.PROMPT_TRACE_FILE))
    with pytest.raises((ValueError, FileNotFoundError)):
        llm_chat_json({"_infini_stage": "visual_director", "_infini_model_override": "offline-model", "messages": []}, timeout=1)


def test_server_full_detail_route_validates_receipts_and_escapes_html(monkeypatch, tmp_path, exact):
    import html
    from infini_local.web import server_trace_snapshot as snapshots, server_utility_routes as routes
    row = _record(monkeypatch, tmp_path, exact)
    monkeypatch.setattr(snapshots.config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(snapshots, "llm_auth_snapshot", lambda: {})
    monkeypatch.setattr(snapshots, "sdcpp_debug_snapshot", lambda **kwargs: {})
    class Handler:
        def json(self, value):
            self.value = value
        def send_response(self, code):
            self.code = code
        def send_header(self, *args):
            pass
        def end_headers(self):
            pass
    import io
    handler = Handler()
    handler.wfile = io.BytesIO()
    # The ordinary polling snapshot must never touch body files.
    reader = trace_tools.read_transport_artifact
    monkeypatch.setattr(trace_tools, "read_transport_artifact", lambda *args: pytest.fail("poll expanded body"))
    assert routes.handle_get(handler, "/trace.json")
    assert handler.value["promptTrace"][-1]["response"] == row["response"]
    monkeypatch.setattr(trace_tools, "read_transport_artifact", reader)
    assert routes.handle_get(handler, "/trace.json?full=1")
    assert handler.value["promptTrace"][-1]["response"].encode() == exact.encode()
    assert routes.handle_get(handler, "/trace?full=1")
    rendered = handler.wfile.getvalue().decode()
    assert html.escape(exact, quote=True) in rendered
    assert "<script>&" not in rendered
    (tmp_path / row["response"]["_traceText"]["path"]).unlink()
    assert routes.handle_get(handler, "/trace.json?full=1")
    failed = handler.value["promptTrace"][-1]["response"]
    assert "unavailable" in failed and "FileNotFoundError" in failed
    assert failed != exact and failed != row["response"]["preview"]


def test_studio_preview_explicitly_links_full_reader_without_expanding_poll_state(monkeypatch, tmp_path, exact):
    from infini_local.desktop.settings_controller import SettingsController
    _record(monkeypatch, tmp_path, exact)
    gui = SettingsController(tmp_path / "config.env")
    monkeypatch.setattr(trace_tools, "read_transport_artifact", lambda *args: pytest.fail("Studio expanded body"))
    snap = gui._load_local_trace_snapshot(cache=tmp_path)
    gui._render_trace_snapshot(snap)
    assert exact[:420] in gui.trace["prompts"]
    assert "Preview only" in gui.trace["prompts"]
    assert "READER_TAIL" not in gui.trace["prompts"]
    assert "_traceText" not in gui.trace["prompts"]
    assert "full=1" in gui.trace["summary"]


def test_stage_prompt_reference_reuses_existing_message_artifact(monkeypatch, tmp_path, exact):
    _record(monkeypatch, tmp_path, "short")
    monkeypatch.setattr(trace_runtime, "TRACE_MAX_PROMPT_CHARS", 64)
    request = {"messages": [{"role": "system", "content": exact}, {"role": "user", "content": exact}]}
    receipt = trace_runtime.trace_stage_request("visual_director", "r_reuse", request,
        prompt_title="Visual stage request", prompt_payload={"recipeKey": "r_reuse"})
    assert receipt["status"] == "stored"
    assert len(trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 1)[0]["prompt"]["preview"]) == 64
    assert list((tmp_path / "transport_artifacts").glob("*.txt")) == []
    messages = json.dumps(request["messages"], ensure_ascii=False, indent=2)
    rows = trace_tools.read_trace_tail(tmp_path, trace_runtime.PROMPT_TRACE_FILE, 10, full=True)
    assert rows[-1]["prompt"].encode() == messages.encode()
    # Measure body copies, not just receipt declarations.
    files = [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix in {".txt", ".json", ".ndjson"}]
    assert sum(p.read_bytes().count(("ж" * 9000).encode()) for p in files) == 2  # two authored messages, once each
    artifact = tmp_path / receipt["path"]
    artifact.write_bytes(artifact.read_bytes() + b" ")
    broken = trace_tools.read_trace_tail(tmp_path, trace_runtime.PROMPT_TRACE_FILE, 10, full=True)[-1]
    assert "unavailable" in broken["prompt"]
