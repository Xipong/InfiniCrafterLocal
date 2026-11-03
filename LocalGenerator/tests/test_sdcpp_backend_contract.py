from __future__ import annotations

import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.services import sdcpp_backend


def _cfg(**overrides):
    values = dict(
        default_command_template="{exe} --diffusion-model {model} -l {host} --listen-port {port} -W {width} -H {height} --steps {steps} --cfg-scale {cfg} --sampling-method {sampler} {extra}",
        command_mode="safe_args",
        server_exe=r"C:\Games\sdcpp\sd-server.exe",
        model=r"C:\Games\sdcpp\models\z-image.gguf",
        vae=r"C:\Games\sdcpp\models\ae.safetensors",
        llm=r"C:\Games\sdcpp\models\qwen.gguf",
        lora_dir="",
        lora_file="",
        lora_prompt_tags="",
        host="127.0.0.1",
        port=7861,
        width=512,
        height=512,
        steps=8,
        cfg=1.0,
        sampler="euler",
        extra_args="-v --flow-shift 3",
        server_url="http://127.0.0.1:7861",
        health_paths=["/", "/health"],
        zimage_prompt_contract="auto",
        zimage_positive_only=True,
    )
    values.update(overrides)
    return sdcpp_backend.SdcppBackendConfig(**values)


def _check_backend_zimage_payload_clears_negative_channel() -> None:
    payload = sdcpp_backend.server_payload(
        _cfg(),
        "subject",
        "scene, bad",
        512,
        512,
        123,
        "a1111",
        is_zimage=True,
        positive_only=True,
    )

    assert payload["prompt"] == "subject"
    assert payload["negative_prompt"] == ""
    assert payload["zimage_positive_only_prompt"] is True
    assert payload["zimage_prompt_contract"] == "auto"


def _check_backend_extracts_a1111_base64_response(tmp_path: Path) -> None:
    # Minimal valid PNG signature is enough for this contract test; the decoder only writes bytes.
    png = b"\x89PNG\r\n\x1a\n" + b"payload"
    raw = json.dumps({"images": [base64.b64encode(png).decode("ascii")]}).encode("utf-8")
    out = tmp_path / "sprite.png"

    ok = sdcpp_backend.extract_image_from_response(raw, "application/json", out)

    assert ok is True
    assert out.read_bytes() == png


def _check_image_pipeline_derives_sdcpp_lora_tag_from_selected_file_when_prompt_tags_blank() -> None:
    from infini_local.pipelines.images import backends as pipeline

    old_file = pipeline.SDCPP_LORA_FILE
    old_dir = pipeline.SDCPP_LORA_DIR
    old_weight = pipeline.SDCPP_LORA_WEIGHT
    old_tags = pipeline.SDCPP_LORA_PROMPT_TAGS
    try:
        pipeline.SDCPP_LORA_FILE = r"C:\Games\sdcpp\models\pixel_art_style_z_image_turbo.safetensors"
        pipeline.SDCPP_LORA_DIR = r"C:\Games\sdcpp\models"
        pipeline.SDCPP_LORA_WEIGHT = "0.70"
        pipeline.SDCPP_LORA_PROMPT_TAGS = ""

        cfg = pipeline._sdcpp_config()

        assert cfg.lora_file == r"C:\Games\sdcpp\models\pixel_art_style_z_image_turbo.safetensors"
        assert cfg.lora_prompt_tags == "<lora:pixel_art_style_z_image_turbo:0.70>"
    finally:
        pipeline.SDCPP_LORA_FILE = old_file
        pipeline.SDCPP_LORA_DIR = old_dir
        pipeline.SDCPP_LORA_WEIGHT = old_weight
        pipeline.SDCPP_LORA_PROMPT_TAGS = old_tags


def _check_backend_respects_manual_equals_flags_for_dedicated_paths():
    cfg = _cfg(
        vae=r"C:\Games\sdcpp\models\ae.safetensors",
        llm=r"C:\Games\sdcpp\models\Qwen.gguf",
        lora_dir=r"C:\Games\sdcpp\loras",
        extra_args='--vae=manual_ae.safetensors --llm=manual_qwen.gguf --lora-model-dir=manual_loras',
    )
    cmd, shell = sdcpp_backend.build_server_command(cfg)
    rendered = sdcpp_backend.stringify_cmd(cmd)
    assert rendered.count("--vae") == 1
    assert rendered.count("--llm") == 1
    assert rendered.count("--lora-model-dir") == 1
    assert "manual_ae.safetensors" in rendered
    assert "manual_qwen.gguf" in rendered
    assert "manual_loras" in rendered



def _check_backend_does_not_pass_inactive_lora_dir_without_tags() -> None:
    cfg = _cfg(lora_dir=r"C:\Games\sdcpp\loras", lora_prompt_tags="")

    cmd, shell = sdcpp_backend.build_server_command(cfg)
    rendered = sdcpp_backend.stringify_cmd(cmd)

    assert shell is False
    assert "--lora-model-dir" not in rendered


def _check_backend_appends_lora_tags_individually_without_duplicates() -> None:
    prompt = "pixel item <lora:already:0.4>"
    out = sdcpp_backend.append_lora_prompt_tags(prompt, "<lora:already:0.4> <lora:new_style:0.6>")

    assert out.count("<lora:already:0.4>") == 1
    assert out.endswith("<lora:new_style:0.6>")


def _check_extra_args_split_strips_helper_quotes_for_argv_mode() -> None:
    tokens = sdcpp_backend.split_extra_args('--cache-mode dbcache --cache-option "threshold=0.08,warmup=2"')

    assert tokens == ["--cache-mode", "dbcache", "--cache-option", "threshold=0.08,warmup=2"]

def _check_backend_drops_non_finite_lora_multipliers() -> None:
    clean, entries = sdcpp_backend.structured_server_loras(
        "pixel item <lora:bad_nan:nan> <lora:bad_inf:inf>",
    )
    assert clean == "pixel item"
    assert entries == []


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_sdcpp_backend_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")


def test_readiness_observations_keep_acceptance_and_redact_transport(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import socket
    import threading
    from infini_local.pipelines.images import backends
    from infini_local.services.sdcpp_service import SdcppServerState

    reply = {"status": 200, "body": b"{}", "requests": 0}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            reply["requests"] += 1
            self.send_response(reply["status"])
            self.send_header("X-Private-Header", "header-secret")
            self.end_headers()
            self.wfile.write(reply["body"])
        def log_message(self, *_args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{http.server_port}"
    state = SdcppServerState()
    monkeypatch.setattr(backends, "SDCPP_SERVER_STATE", state)
    monkeypatch.setattr(backends, "SDCPP_SERVER_URL", url)
    monkeypatch.setattr(backends, "SDCPP_SERVER_HEALTH_PATHS", ["/health"])
    try:
        initial = backends.sdcpp_debug_snapshot(include_log_tail=False, probe_server=False)
        assert initial["lastProbe"]["outcome"] == "not_probed"
        cases = [
            (200, b'{"status":"ok","secret":"private-body"}', "/health", False, "unrecognized_body", "json_object"),
            (200, b'{"status":"loading"}', "/health", False, "not_ready", "json_status_not_ready"),
            (200, b"sd.cpp", "/health", True, "ready", "text"),
            (200, b'{"status":"loading","product":"sd.cpp"}', "/health", True, "ready", "json_status_not_ready"),
            (200, b"[" * 2000 + b"sd.cpp", "/health", True, "ready", "text"),
            (200, b"{}", "/sdapi/v1/sd-models", False, "unrecognized_body", "json_object"),
            (200, b"[]", "/sdapi/v1/sd-models", True, "ready", "json_array"),
            (404, b"private-body", "/health", False, "http_error", "not_read"),
            (503, b"loading", "/health", False, "http_error", "not_read"),
        ]
        for status, body, path, accepted, outcome, shape in cases:
            reply.update(status=status, body=body)
            monkeypatch.setattr(backends, "SDCPP_SERVER_HEALTH_PATHS", [path])
            assert backends.sdcpp_server_is_alive() is accepted
            requests_before_snapshot = reply["requests"]
            snap = backends.sdcpp_debug_snapshot(include_log_tail=False, probe_server=False)
            assert reply["requests"] == requests_before_snapshot
            probe = json.loads(json.dumps(snap))["lastProbe"]
            assert probe["attempts"] == 1
            assert probe["routes"][0]["httpStatus"] == status
            assert probe["routes"][0]["outcome"] == outcome
            assert probe["routes"][0]["bodyShape"] == shape
            assert all(secret not in json.dumps(probe) for secret in ("private-body", "header-secret"))
            assert probe == state.last_probe  # No extra request from unprobed snapshot.
        reply.update(status=200, body=b"sd.cpp")
        import io
        observed_requests = []
        def accepting_transport(request, *, timeout):
            observed_requests.append((request.full_url, timeout))
            return io.BytesIO(b"sd.cpp")
        with monkeypatch.context() as transport_boundary:
            transport_boundary.setattr(sdcpp_backend.urlrequest, "urlopen", accepting_transport)
            observation = {}
            unusual_url = f"http://127.0.0.1:+{http.server_port}"
            assert sdcpp_backend.server_is_alive(unusual_url, ["/health"], observation=observation)
            assert observed_requests == [(unusual_url + "/health", 2)]
            assert observation["routes"][0]["url"] == ""  # Diagnostic parsing cannot preempt transport.
        reply.update(status=200, body=b"unknown")
        observation = {}
        assert not sdcpp_backend.server_is_alive(url, ["/", "/health", "/other", "/last"], observation=observation)
        assert observation["attempts"] == 4 and len(observation["routes"]) == 3
        assert observation["routes"][-1]["url"].endswith("/[redacted]")
        with socket.socket() as refused:
            refused.bind(("127.0.0.1", 0))  # Reserved but not listening: real TCP refusal.
            observation = {}
            assert not sdcpp_backend.server_is_alive(f"http://127.0.0.1:{refused.getsockname()[1]}", ["/health"], observation=observation)
            assert observation["routes"][0]["outcome"] == "transport_failed"
            assert observation["routes"][0]["errorCategory"] == "transport_error"
            assert observation["routes"][0]["httpStatus"] is None
        def fail_open(*_args, **_kwargs):
            raise OSError("password query-token must never be emitted")
        monkeypatch.setattr(sdcpp_backend.urlrequest, "urlopen", fail_open)
        monkeypatch.setattr(backends, "SDCPP_SERVER_URL", "http://name:password@localhost:1234/private?token=query-token#fragment-secret")
        assert not backends.sdcpp_server_is_alive()
        wire = json.loads(json.dumps(backends.sdcpp_debug_snapshot(include_log_tail=False, probe_server=False)))
        encoded = json.dumps(wire["lastProbe"])
        assert all(secret not in encoded for secret in ("name", "password", "query-token", "private", "fragment-secret", "header-secret"))
        assert wire["lastProbe"]["routes"][0]["url"] == "http://localhost:1234/[redacted]"
    finally:
        http.shutdown()
        http.server_close()
        worker.join(timeout=5)
        assert not worker.is_alive()


def test_probe_publication_ignores_late_older_result_without_lifecycle_wait(monkeypatch):
    import threading
    from infini_local.pipelines.images import backends
    from infini_local.services.sdcpp_service import SdcppServerState

    state = SdcppServerState()
    monkeypatch.setattr(backends, "SDCPP_SERVER_STATE", state)
    entered, release = threading.Event(), threading.Event()
    calls, results = [], []
    def probe(_url, _paths, timeout, *, observation):
        calls.append(timeout)
        if len(calls) == 1:
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test must release older probe")
            observation.update(outcome="not_ready", routes=[], attempts=1)
            return False
        observation.update(outcome="ready", routes=[], attempts=1)
        return True
    monkeypatch.setattr(sdcpp_backend, "server_is_alive", probe)
    worker = threading.Thread(target=lambda: results.append(backends.sdcpp_server_is_alive()))
    worker.start()
    try:
        assert entered.wait(5)
        with state.lock:  # The startup owner's long-held lock must not gate diagnostics.
            assert backends.sdcpp_server_is_alive()
            accepted = dict(state.last_probe)
            release.set()
            worker.join(timeout=5)
            assert not worker.is_alive()
        assert results == [False]
        assert state.last_probe == accepted and accepted["outcome"] == "ready"
        assert calls == [2, 2]
    finally:
        release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
