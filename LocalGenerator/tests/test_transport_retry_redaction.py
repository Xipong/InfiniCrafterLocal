"""Offline transport/redaction regressions; synthetic credentials only."""
from __future__ import annotations

import copy
from http.client import IncompleteRead
import io
import json
import ssl
from pathlib import Path
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from infini_local.services import codex_auth as auth
from infini_local.storage import trace_tools


CLEAN_PATH = (r"C:\Users\Cosmi\LocalGenerator\cache\image-diagnostics\image-pibcq_5y\attempt-0"
              r"\g_c606cc2b5adac118_trap_returner_dart_raw_openai_codex_0.png")


@pytest.mark.parametrize("alias", ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "INFINI_OPENAI_COMPAT_API_KEY", "INFINI_IMAGE_API_KEY", "INFINI_LLM_2_API_KEY", "INFINI_SYNTHETIC_SECRET", "INFINI_SYNTHETIC_TOKEN"])
def test_real_persisted_sinks_preserve_dart_raw_paths_while_redacting_credentials(monkeypatch, tmp_path, alias):
    opaque = "synthetic-opaque-secret-0123456789"
    refresh = "rt_synthNoRealCredential0123456789"
    monkeypatch.setenv(alias, opaque)
    escaped = "".join(r"\\u%04x" % ord(char) for char in opaque)
    clean = "Exact\r\n  Ж {\"escaped\":\"\\u0410\",\"dup\":1,\"dup\":2} " + CLEAN_PATH
    payload = {"raw": CLEAN_PATH, "clean": clean, "nested": {opaque: [opaque, escaped, refresh]}}
    before = copy.deepcopy(payload)
    trace_tools.log_event(tmp_path, "info", "path " + CLEAN_PATH, payload)
    trace_tools.trace_event(cache_dir=tmp_path, trace_prompts_enabled=True, trace_max_prompt_chars=0,
                            trace_file=tmp_path / "trace.ndjson", prompt_trace_file=tmp_path / "prompts.ndjson",
                            kind="prompt", stage="offline", title="filename", payload=payload,
                            prompt=clean, negative=opaque, response=refresh, error=escaped)
    receipt = trace_tools.persist_stage_request(tmp_path, "offline", "join", {"messages": [
        {"role": "user", "content": clean}, {"role": "user", "content": opaque + " " + refresh + " " + escaped},
    ]})
    assert receipt["status"] == "stored"
    event = json.loads((tmp_path / "events.ndjson").read_bytes())
    trace = json.loads((tmp_path / "prompts.ndjson").read_bytes())
    stage = json.loads((tmp_path / receipt["path"]).read_bytes())
    assert event["payload"]["raw"] == CLEAN_PATH
    assert event["payload"]["clean"].encode() == clean.encode()
    assert event["message"] == "path " + CLEAN_PATH
    assert trace["prompt"].encode() == clean.encode()
    assert stage["messages"][0]["content"].encode() == clean.encode()
    assert trace["negative"] == trace["response"] == trace["error"] == "[REDACTED]"
    assert event["payload"]["nested"] == {"[REDACTED]": ["[REDACTED]"] * 3}
    assert stage["messages"][1]["content"] == "[REDACTED] [REDACTED] [REDACTED]"
    assert payload == before


@pytest.fixture
def codex_image(monkeypatch, tmp_path):
    from infini_local.pipelines import image_backend_pipeline as backend, pipeline_visual_config as config
    from infini_local.pipelines import visual_sprite_generation as generation
    from PIL import Image, ImageDraw
    for name, value in {"INFINI_SPRITE_RETRIES": "1", "INFINI_LLM_FALLBACK_NETWORK_FAILS": "2"}.items():
        monkeypatch.setenv(name, value)
    for name, value in {"IMAGE_BACKEND": "openai_codex", "IMAGE_BACKEND_CONFIG_ERROR": "", "SPRITE_RETRIES": 1,
                        "VISUAL_STRICT_AI_AUTHORSHIP": True, "VISUAL_ALLOW_PROCEDURAL_FALLBACK": False}.items():
        monkeypatch.setattr(generation, name, value)
    monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path / "sprites")
    monkeypatch.setattr(generation, "WORLD_RECIPES_DIR", tmp_path / "world")
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 1)
    for name, value in {"CODEX_IMAGE_MODEL": "gpt-image-2", "CODEX_IMAGE_QUALITY": "medium",
                        "CODEX_IMAGE_SIZE": "1024x1024", "CODEX_IMAGE_TIMEOUT": 5}.items():
        monkeypatch.setattr(config, name, value)
    credentials = auth.Credentials("synthetic-access-only", "synthetic-refresh-only", "synthetic-account", 9999999999)
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    monkeypatch.setattr(generation, "build_retry_prompt_from_validation", lambda *_a, **_k: pytest.fail("transport called semantic Repair"))
    image = Image.new("RGBA", (64, 64), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 55, 55), fill=(210, 100, 20, 255))
    draw.rectangle((28, 8, 35, 55), fill=(210, 130, 50, 255))
    raw = io.BytesIO()
    image.save(raw, format="PNG")
    import base64
    response = json.dumps({"data": [{"b64_json": base64.b64encode(raw.getvalue()).decode()}]}).encode()
    return generation, response


def test_image_503_replays_exact_request_without_touching_valid_gameplay_or_assets(codex_image, monkeypatch, tmp_path):
    generation, response = codex_image
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append((request.full_url, request.data, dict(request.header_items()), timeout))
            if len(requests) == 1:
                raise HTTPError(request.full_url, 503, "busy", Message(), io.BytesIO(b'{"error":{"message":"temporarily unavailable"}}'))
            return io.BytesIO(response)
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_a: Opener())
    accepted = tmp_path / "accepted-item.png"
    import base64
    accepted_bytes = base64.b64decode(json.loads(response)["data"][0]["b64_json"])
    accepted.write_bytes(accepted_bytes)
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from infini_local.core.runtime_authoring import validate_runtime_program
    data = build_runtime_fixture("workbench_blade")
    assert validate_runtime_program(data)["ok"]
    data["visual"] = {"spritePath": str(accepted), "spriteStatus": "generated"}
    before = copy.deepcopy(data)
    path, _url, _score, status = generation.generate_visual_asset(data, "equip_overlay", "one authored round amber object", "no text", "dart", 32)
    assert status == "generated", data.get("debug")
    assert len(requests) == 2
    assert requests[0][:3] == requests[1][:3]
    assert 0 < requests[1][3] <= requests[0][3] <= 5
    assert data["runtimeProgram"] == before["runtimeProgram"] and data["visual"] == before["visual"]
    assert validate_runtime_program(data)["ok"]
    assert accepted.read_bytes() == accepted_bytes
    assert Path(path).is_file()
    assert data["debug"]["equip_overlayFinalPromptAttempt"] == 0
    assert len(json.loads(data["debug"]["equip_overlaySpriteValidation"])) == 1


def test_text_503_has_one_transport_owner_and_one_logical_author_stage(monkeypatch):
    from infini_local.pipelines import llm_transport as llm
    from infini_local.services import codex_text_backend as text
    monkeypatch.setenv("INFINI_LLM_FALLBACK_NETWORK_FAILS", "2")
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "synthetic-codex-model")
    monkeypatch.setattr(llm, "http_json", lambda *_a, **_k: pytest.fail("paid transport called"))
    monkeypatch.setattr(auth, "get_credentials", lambda: auth.Credentials("synthetic-access", "synthetic-refresh", "synthetic-account", 9999999999))
    completion = {"type": "response.completed", "response": {"status": "completed", "output": [{
        "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": '{"valid":true}'}],
    }]}}
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append((request.full_url, request.data, dict(request.header_items()), timeout))
            if len(requests) == 1:
                raise HTTPError(request.full_url, 503, "busy", Message(), io.BytesIO(b'{"error":{"message":"temporary"}}'))
            return io.BytesIO(b"data: " + json.dumps(completion).encode() + b"\n\n")
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_a: Opener())
    packet = llm.with_llm_stage({"model": "synthetic-codex-model", "messages": [
        {"role": "system", "content": "JSON exact authored rules."}, {"role": "user", "content": "Keep exact факт."},
    ], "response_format": {"type": "json_object"}}, "llm")
    before = copy.deepcopy(packet)
    with llm.llm_item_lease("transport-only") as lease:
        result = llm.llm_chat_json(packet, timeout=3)
        assert lease.call_count == 1 and lease.stages == ["llm"] and not lease.failovers
    assert result["choices"][0]["message"]["content"] == '{"valid":true}'
    assert packet == before
    assert len(requests) == 2 and requests[0][:3] == requests[1][:3]
    assert requests[0][0] == text.RESPONSES_URL
    assert 0 < requests[1][3] <= requests[0][3] <= 3


@pytest.mark.parametrize("transport", ["image", "text"])
@pytest.mark.parametrize("fault", ["reset", "incomplete-http-body"])
def test_connection_loss_during_body_retries_same_request_with_fresh_response(monkeypatch, transport, fault):
    from infini_local.services.codex_text_backend import RESPONSES_URL
    url = auth._IMAGE_GENERATION_URL if transport == "image" else RESPONSES_URL
    payload = {"prompt": "unchanged предмет"} if transport == "image" else {"stream": True, "input": ["same authored facts"]}
    requests = []
    event = b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
    class Broken(io.BytesIO):
        def read1(self, *_args):
            if fault == "incomplete-http-body":
                raise IncompleteRead(b"synthetic partial bytes", 100)
            raise ConnectionResetError("synthetic connection reset")
        def readline(self, *_args):
            return self.read1()
    class Opener:
        def open(self, request, timeout):
            requests.append((request.data, dict(request.header_items())))
            if len(requests) == 1:
                return Broken()
            return io.BytesIO(b'{"ok":true}' if transport == "image" else event)
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_args: Opener())
    monkeypatch.setenv("INFINI_SPRITE_RETRIES", "1")
    monkeypatch.setenv("INFINI_LLM_FALLBACK_NETWORK_FAILS", "2")
    result = (auth.post_json if transport == "image" else auth.post_sse)(url, payload, timeout=3)
    assert result == ({"ok": True} if transport == "image" else {"status": "completed", "output": []})
    assert len(requests) == 2 and requests[0] == requests[1]


@pytest.mark.parametrize("transport", ["image", "text"])
def test_incomplete_503_diagnostic_keeps_status_and_same_retry_budget(monkeypatch, transport):
    from infini_local.services.codex_text_backend import RESPONSES_URL
    calls = []
    monkeypatch.setenv("INFINI_SPRITE_RETRIES", "1")
    monkeypatch.setenv("INFINI_LLM_FALLBACK_NETWORK_FAILS", "2")
    class BrokenDiagnostic(io.BytesIO):
        def read1(self, *_args):
            raise IncompleteRead(b"synthetic diagnostic", 100)
    class Opener:
        def open(self, request, timeout):
            calls.append(request.data)
            raise HTTPError(request.full_url, 503, "busy", Message(), BrokenDiagnostic())
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_args: Opener())
    url = auth._IMAGE_GENERATION_URL if transport == "image" else RESPONSES_URL
    with pytest.raises(auth.CodexError, match="HTTP 503"):
        (auth.post_json if transport == "image" else auth.post_sse)(url, {"stream": True}, timeout=3)
    assert len(calls) == 2 and calls[0] == calls[1]


@pytest.mark.parametrize("fault,expected_calls", [
    (503, 2), (URLError("synthetic DNS failure"), 2), (401, 1), (402, 1), (403, 1),
    (429, 1), (400, 1), (404, 1), (302, 1),
    (URLError(ssl.SSLCertVerificationError("synthetic certificate refusal")), 1),
])
def test_image_transport_budget_exhaustion_never_enters_semantic_retry(codex_image, monkeypatch, fault, expected_calls):
    generation, _response = codex_image
    calls = []
    errors = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.data)
            if isinstance(fault, int):
                error = HTTPError(request.full_url, fault, "refused", Message(), io.BytesIO(b'{"error":{"message":"synthetic-access-only"}}'))
                errors.append(error)
                raise error
            raise fault
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_args: Opener())
    data = {"runtimeProgram": {"calls": ["frozen"]}}
    result = generation.generate_visual_asset(data, "equip_overlay", "one authored round object", "", "dart", 32)
    assert result[3] == "failed" and result[0] == ""
    assert len(calls) == expected_calls and all(body == calls[0] for body in calls)
    assert all(error.closed for error in errors)
    assert data["runtimeProgram"] == {"calls": ["frozen"]}
    assert data["debug"]["equip_overlayFinalPromptAttempt"] == 0
    assert "synthetic-access-only" not in data["debug"]["equip_overlaySpriteError"]


@pytest.mark.parametrize("status,budget,expected_calls", [(503, 2, 2), (503, 1, 1), (401, 2, 1), (429, 2, 1), (400, 2, 1)])
def test_text_terminal_failures_do_not_multiply_logical_or_physical_budget(monkeypatch, status, budget, expected_calls):
    from infini_local.pipelines import llm_transport as llm
    monkeypatch.setenv("INFINI_LLM_FALLBACK_NETWORK_FAILS", str(budget))
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "synthetic-codex-model")
    monkeypatch.setattr(llm, "http_json", lambda *_a, **_k: pytest.fail("paid transport called"))
    monkeypatch.setattr(auth, "get_credentials", lambda: auth.Credentials("synthetic-access", "synthetic-refresh", "synthetic-account", 9999999999))
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.data)
            raise HTTPError(request.full_url, status, "busy", Message(), io.BytesIO(b'{"error":{"message":"synthetic-access"}}'))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_args: Opener())
    packet = llm.with_llm_stage({"messages": [{"role": "user", "content": "exact facts"}]}, "visual_director")
    with llm.llm_item_lease("bounded-terminal") as lease:
        with pytest.raises(auth.CodexError, match=f"HTTP {status}") as caught:
            llm.llm_chat_json(packet, timeout=3)
        assert lease.call_count == 1 and lease.stages == ["visual_director"] and not lease.failovers
    assert "synthetic-access" not in str(caught.value)
    assert len(calls) == expected_calls and all(body == calls[0] for body in calls)


@pytest.mark.parametrize("token", ["rt_synthNoRealCredential0123456789", "sk-synthNoRealCredential0123456789", "eyJsynthetic.header.signature"])
@pytest.mark.parametrize("encoding", ["plain", "unicode", "double-unicode"])
def test_standalone_token_patterns_remain_redacted_in_persisted_sink(tmp_path, token, encoding):
    value = token if encoding == "plain" else "".join((r"\u%04x" if encoding == "unicode" else r"\\u%04x") % ord(char) for char in token)
    trace_tools.log_event(tmp_path, "info", "«" + value + "»", {"syntheticSecret": value, "clean": CLEAN_PATH})
    row = json.loads((tmp_path / "events.ndjson").read_bytes())
    assert row["message"] == "«[REDACTED]»"
    assert row["payload"] == {"syntheticSecret": "[REDACTED]", "clean": CLEAN_PATH}


@pytest.mark.parametrize("phase", ["backoff", "body", "error-body"])
def test_image_deadline_is_terminal_before_another_send(codex_image, monkeypatch, phase):
    generation, response = codex_image
    calls = []
    clock = [100.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(auth.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    class Late(io.BytesIO):
        def read1(self, *args):
            clock[0] += 6.0
            return super().read1(*args)
    class Opener:
        def open(self, request, timeout):
            calls.append(request.data)
            if phase == "backoff":
                clock[0] += 4.9
                raise HTTPError(request.full_url, 503, "busy", Message(), io.BytesIO(b'{"error":{"message":"temporary"}}'))
            if phase == "error-body":
                raise HTTPError(request.full_url, 503, "busy", Message(), Late(b'{"error":{"message":"temporary"}}'))
            return Late(response)
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_args: Opener())
    data = {}
    result = generation.generate_visual_asset(data, "equip_overlay", "one authored object", "", "dart", 32)
    assert result[3] == "failed" and result[0] == ""
    assert len(calls) == 1
    assert "HttpDeadlineExceeded" in data["debug"]["equip_overlaySpriteError"]
    assert data["debug"]["equip_overlayFinalPromptAttempt"] == 0
