"""Offline test seams shared by provider and desktop contracts.

No model discovery, native Hermes imports, application startup or credentials.
"""
from __future__ import annotations

from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import io
import json
import os
import threading
import time


def reset_llm_runtime():
    """Reset each owner's process state between offline transport scenarios."""
    from infini_local.pipelines.transport import admission as llm_admission
    from infini_local.pipelines.transport import profiles as llm_profiles
    from infini_local.pipelines.transport import client as llm_transport

    with llm_profiles._LLM_POOL_LOCK:
        llm_profiles._LLM_POOL_CURSOR = 0
        llm_profiles._LLM_LEASE_SEQUENCE = 0
        llm_profiles._PROFILE_COOLDOWN_UNTIL.clear()
    llm_transport._RESOLVED_LLM_MODELS.clear()
    llm_transport._RESPONSES_CAPABILITY.clear()
    llm_transport._STRICT_SCHEMA_CAPABILITY.clear()
    with llm_admission._LLM_RATE_LOCK:
        llm_admission._LLM_RATE_STATE.clear()


@contextmanager
def loopback_server(handler):
    """Own a bounded loopback HTTP lifetime, including thread teardown."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True,
    )
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        assert not worker.is_alive(), "loopback HTTP server leaked a worker"


def write_json_response(handler, body, *, status=200, headers=None, raw_body=None,
                        before_headers=0, header_trickle=0, trickle=0):
    """Serve literal JSON/bytes; delay knobs exercise real deadline consumers."""
    encoded = raw_body.encode() if raw_body is not None else json.dumps(body).encode()
    try:
        time.sleep(before_headers)
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            handler.send_header(name, value)
        if header_trickle:
            buffered = b"".join(handler._headers_buffer)
            handler._headers_buffer = []
            for byte in buffered + b"\r\n":
                handler.wfile.write(bytes([byte]))
                handler.wfile.flush()
                time.sleep(header_trickle)
        else:
            handler.end_headers()
        if trickle:
            for byte in encoded:
                handler.wfile.write(bytes([byte]))
                handler.wfile.flush()
                time.sleep(trickle)
        else:
            handler.wfile.write(encoded)
    except (BrokenPipeError, ConnectionResetError):
        pass


class OwnedProcess:
    """Recording subprocess seam: never starts or terminates a real process."""
    def __init__(self, actions=None, *, pid=None):
        self.pid = os.getpid() + 1000 if pid is None else pid
        self.actions = [] if actions is None else actions

    def poll(self):
        return None

    def terminate(self):
        self.actions.append("terminate")

    def kill(self):
        self.actions.append("kill")

    def wait(self, **_kwargs):
        return 0


def deliverable_recipe(tmp_path, monkeypatch, *, manifest_key):
    """Real cache/delivery consumers with an explicitly synthetic image control."""
    from infini_local.core.vfx.projection import _compile_manifest
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.pipelines.visual import delivery as visual
    from infini_local.qa.live_no_image_fixture import (
        hydrate_no_image_fixture_assets, synthetic_no_image_execution_control,
        write_no_image_fixture_png,
    )
    from infini_local.storage import world_recipe_runtime as recipes
    from infini_local.web.vfx_debug_routes import _sample_data

    monkeypatch.setattr(recipes, "WORLD_RECIPES_DIR", tmp_path / "worlds")
    monkeypatch.setattr(visual, "WORLD_RECIPES_DIR", tmp_path / "worlds")
    monkeypatch.setattr(visual, "SPRITE_DIR", tmp_path / "sprites")
    good = _sample_data()
    good["visual"] = {"preferredCanvasSize": 32}
    fixture = write_no_image_fixture_png(tmp_path / "sprites" / "test.png")
    hydrate_no_image_fixture_assets(good, fixture)
    good["vfxManifest"] = _compile_manifest(good, {"slots": []}, manifest_key)
    good = synthetic_no_image_execution_control(good, fixture)
    assert pipeline._cached_payload_report(good)["ok"]
    return good


class HttpReply(io.BytesIO):
    """BytesIO HTTP seam with status/header ownership on each instance."""
    def __init__(self, body=b"{}", *, status=200, headers=None):
        from email.message import Message

        super().__init__(body)
        self.status = status
        self.headers = Message() if headers is None else headers


class HttpSender:
    """Record outgoing JSON, time and deadline; queued replies are data only."""
    def __init__(self, monkeypatch, transport, clock, replies=(), *, default_body=b"{}"):
        from collections import deque

        self.clock = clock
        self.default_body = default_body
        self.replies = deque(replies)
        self.sends = []
        monkeypatch.setattr(transport, "urlopen_no_redirect", self)
        monkeypatch.setattr(transport, "read_with_deadline", lambda response, **kw: response.read())

    def __call__(self, request, *, deadline):
        self.sends.append((json.loads(request.data), self.clock.now, deadline))
        reply = self.replies.popleft() if self.replies else HttpReply(self.default_body)
        if isinstance(reply, Exception):
            raise reply
        return reply


@contextmanager
def physical_attempt(transport, rows):
    """Record actual attempt metadata and always restore the context token."""
    row = {"rateWaitReason": "none"}
    token = transport._CURRENT_LLM_ATTEMPT.set(row)
    try:
        yield row
    finally:
        rows.append(row)
        transport._CURRENT_LLM_ATTEMPT.reset(token)


class RecordingOpener:
    """urllib opener with literal reply/error data and observable outgoing bytes."""
    def __init__(self, *replies):
        from collections import deque

        self.replies = deque(replies)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        return reply


def endpoint_options(*, combine, json, json_status, **overrides):
    """Minimal direct endpoint seam; tests opt into every additional callback."""
    return {
        "app_version": "test", "combine_cache_lookup": lambda _: ("key", None),
        "sanitize_recipe_for_delivery": lambda value: value, "combine": combine,
        "trace_event": lambda *_: None, "json": json, "json_status": json_status,
        **overrides,
    }
