"""Offline HTTP ingress, diagnostics/asset routes, and actual provider JSON bytes."""
from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import socket
import threading
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pytest

from infini_local.pipelines import llm_transport as transport
from infini_local.storage import world_storage
from infini_local.web.http_response_helpers import _combine_failure_http_response, _combine_failure_payload
from infini_local.web.server_handler import JSON_BODY_READ_TIMEOUT_SECONDS, MAX_JSON_BODY_BYTES, build_handler
from infini_local.web.server_utility_routes import MAX_ASSET_RESPONSE_BYTES, ServerUtilityRoutes
from infini_local.web.vfx_debug_routes import VfxDebugRoutes


class ReadProbe(io.BytesIO):
    def __init__(self, body=b"", *, forbidden=False, timeout=False):
        super().__init__(body)
        self.forbidden, self.timeout, self.read_calls = forbidden, timeout, 0

    def read(self, size=-1):
        self.read_calls += 1
        if self.forbidden:
            raise AssertionError("unexpected body read")
        if self.timeout:
            raise socket.timeout("simulated read timeout")
        return super().read(size)


@dataclass
class Connection:
    timeout: float | None = None
    set_calls: list = field(default_factory=list)

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value
        self.set_calls.append(value)


@dataclass
class Capture:
    code: int | None = None
    payload: Any = None
    called: int = 0
    headers: dict = field(default_factory=dict)
    wfile: io.BytesIO = field(default_factory=io.BytesIO)

    def json(self, payload):
        self.json_status(200, payload)

    def json_status(self, status, payload):
        self.code, self.payload = status, payload
        self.called += 1

    def json_error(self, status, code, message=""):
        self.json_status(status, {"error": code, "message": str(message)})

    def send_error(self, status, *args, **kwargs):
        self.json_error(status, f"http_{status}")

    def send_response(self, status):
        self.code = status

    def send_header(self, name, value):
        self.headers[str(name)] = str(value)

    def end_headers(self):
        pass


class UtilityProbe:
    def handle_get(self, handler, path):
        route = urlparse(path).path.removeprefix("/")
        if route not in {"get_asset", "health"}:
            return False
        handler.json({"ok": True, "route": route})
        return True

    def handle_post(self, *args):
        return False


class WorldScopeMissing(Exception):
    pass


class VisualDeliveryBlocked(Exception):
    pass


class PlannerUnavailable(Exception):
    pass


def boundary_handler(*, path="/combine", body=b"{}", length=None, address="127.0.0.1", internal_error=False):
    capture = Capture()
    endpoint = SimpleNamespace(handle_combine_request=(
        lambda *_args, **_kw: (_ for _ in ()).throw(ValueError("internal invariant failed"))
        if internal_error else _kw["json"]({"ok": True, "route": "combine"})))
    handler_class = build_handler(
        app_version="test", utility_routes=UtilityProbe,
        vfx_debug_routes=lambda: SimpleNamespace(handle_get=lambda *_: False, handle_post=lambda *_: False),
        combine_endpoint=endpoint, combine_cache_lookup=lambda *_a, **_k: None,
        sanitize_recipe_for_delivery=lambda *_a, **_k: None, combine=lambda *_a, **_k: None,
        trace_event=lambda *_a, **_k: None, log_event=lambda *_a, **_k: None,
        is_client_disconnect=lambda _e: False, world_scope_missing=WorldScopeMissing,
        visual_delivery_blocked=VisualDeliveryBlocked, planner_unavailable=PlannerUnavailable,
        last_combine_failure_summary=lambda: {}, clear_combine_failure=lambda _r: None,
        combine_failure_http_response=lambda _e, _s: (500, "failure", False, "failure"),
        combine_failure_payload=lambda *_a, **_k: {"ok": False, "error": "failure"}, ascii_reason=lambda _m: "error",
    )
    handler = handler_class.__new__(handler_class)
    handler.path, handler.client_address = path, (address, 1234)
    handler.headers = {"Content-Length": str(length if length is not None else len(body))}
    handler.rfile = body if isinstance(body, ReadProbe) else ReadProbe(body)
    handler.wfile, handler.connection = io.BytesIO(), Connection()
    for name in ("json", "json_status", "json_error", "send_error"):
        setattr(handler, name, getattr(capture, name))
    return handler, capture


def utility_routes(root):
    return ServerUtilityRoutes(
        app_version="test", root=root, cache_dir=root, sprite_dir=root, world_recipes_dir=root,
        trace_files=(), trace_dashboard=SimpleNamespace(render_mp_connect_html=lambda _: "<html/>"),
        asset_sync_service=SimpleNamespace(safe_asset_file_from_query=lambda *_a, **_k: None,
            find_asset_file=lambda *_a, **_k: None, asset_content_type=lambda _: "image/png"),
        health_payload=lambda: {"ok": True}, multiplayer_connect_info=lambda: {"host": "127.0.0.1"},
        trace_snapshot=lambda: {}, trace_snapshot_html=lambda: "<html/>", trace_event=lambda *_a, **_k: None,
        sdcpp_start=lambda: True, sdcpp_debug_snapshot=lambda include_log_tail: {"ok": True},
        read_json_file=lambda _: None, last_combine_failure_payload=lambda: {}, cleanup_for_shutdown=lambda _: None,
        build_image_prompt=lambda *_a, **_k: "", maybe_generate_sprite=lambda p: p,
        normalize_asset_prompt=lambda *_a, **_k: "", generate_visual_asset=lambda *_a, **_k: ("", "", 0.0, {}),
        asset_negative_prompt=lambda _: "", alpha_stats=lambda _: {}, image_module=None,
    )


@pytest.mark.parametrize("method,path,address,status,payload,reads", [
    pytest.param("GET", "/get_asset?name=foo.png", "198.51.100.20", 200, {"ok": True, "route": "get_asset"}, 0, id="remote-asset"),
    pytest.param("GET", "/shutdown", "198.51.100.20", 403, "loopback_only", 0, id="remote-control"),
    pytest.param("POST", "/combine", "203.0.113.10", 403, "loopback_only", 0, id="remote-post-no-read"),
    pytest.param("POST", "/missing", "127.0.0.1", 404, None, 0, id="unknown-post-no-read"),
    pytest.param("POST", "/combine", "::ffff:127.0.0.1", 200, {"ok": True, "route": "combine"}, 1, id="mapped-loopback"),
])
def test_ingress_route_authority_precedes_body_read(method, path, address, status, payload, reads):
    body = ReadProbe(b"{}", forbidden=not reads)
    handler, capture = boundary_handler(path=path, body=body, length=2, address=address)
    getattr(handler, "do_" + method)()
    assert capture.code == status
    if isinstance(payload, dict):
        assert capture.payload == payload
    elif payload:
        assert capture.payload["error"] == payload
    assert body.read_calls == reads


@pytest.mark.parametrize("path,required", [("/shutdown", True), ("/shutdownAnything", False),
    ("/sdcpp_start", True), ("/debug/trace", True), ("/visual_doctor", True), ("/health", False)])
def test_control_route_classification_is_exact(path, required):
    handler, _ = boundary_handler()
    assert handler._route_requires_loopback(path, is_post=False) is required


@pytest.mark.parametrize("body,length,status,error,reads,timeout,internal", [
    pytest.param(body, len(body), 400, "invalid_json", 1, False, False, id=label)
    for label, body in [("array", b"[]"), ("null", b"null"), ("nan", b'{"value":NaN}'),
        ("infinity", b'{"value":Infinity}'), ("overflow", b'{"value":1e999}'),
        ("duplicate-key", b'{"value":1,"value":2}'), ("invalid-utf8", b'{"value":"\xff"}')]
] + [
    pytest.param(b"{}", 8, 400, "invalid_json", 2, False, False, id="early-eof"),
    pytest.param(b"", MAX_JSON_BODY_BYTES + 1, 413, "request_too_large", 0, False, False, id="oversized-no-read"),
    pytest.param(b"", -1, 400, "invalid_json", 0, False, False, id="negative-length-no-read"),
    pytest.param(b"", 6, 408, "request_timeout", 1, True, False, id="bounded-timeout"),
    pytest.param(b"{}", 2, 500, "internal_error", 1, False, True, id="internal-value-error-not-json"),
])
def test_post_body_validation_has_bounded_exact_failure(body, length, status, error, reads, timeout, internal):
    stream = ReadProbe(body, forbidden=not reads, timeout=timeout)
    handler, capture = boundary_handler(body=stream, length=length, internal_error=internal)
    handler.do_POST()
    assert capture.code == status
    assert capture.payload["error"] == error
    assert stream.read_calls == reads
    if timeout:
        assert handler.connection.set_calls == [JSON_BODY_READ_TIMEOUT_SECONDS, None]


@pytest.mark.parametrize("owner,method,path,accepted", [
    ("utility", "get", "/shutdown?force=1", True), ("utility", "get", "/shutdownAnything", False),
    ("vfx", "get", "/debug/vfx_matrix?verbose=1", True), ("vfx", "get", "/debug/vfx_matrix_extra", False),
    ("vfx", "post", "/debug/vfx_select?dryRun=1", True), ("vfx", "post", "/debug/vfx_select_extra", False),
])
def test_utility_and_debug_dispatch_use_exact_parsed_route(tmp_path, owner, method, path, accepted):
    routes = utility_routes(tmp_path) if owner == "utility" else VfxDebugRoutes(
        app_version="test", normalize_world_id_from_payload=lambda _: "world",
        read_world_recipe_cache=lambda *_a, **_k: None, write_world_recipe_cache=lambda *_a, **_k: None,
        final_normalize=lambda data: data,
    )
    if method == "post":
        object.__setattr__(routes, "select_manifest", lambda payload: {"payload": payload})
    handler = Capture()
    arguments = (handler, path, {"x": 1}) if method == "post" else (handler, path)
    assert getattr(routes, "handle_" + method)(*arguments) is accepted
    assert handler.called == int(accepted)
    if accepted and owner == "utility":
        assert handler.payload is not None and handler.payload["message"] == "shutdown scheduled"
    elif accepted and method == "get":
        assert handler.payload["ok"] is True and handler.payload["version"] == "test"
        assert handler.payload["schema"] and handler.payload["sampleRuntimeEvents"]
    elif accepted:
        assert handler.payload == {"payload": {"x": 1}}


@pytest.mark.parametrize("kind", ["encoded-traversal", "outside-symlink"])
def test_sprite_path_cannot_escape_serving_root(tmp_path, kind):
    root = tmp_path / "sprites"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"not-a-real-png")
    routes = utility_routes(tmp_path)
    routes.sprite_dir = root
    if kind == "outside-symlink":
        (root / "leak.png").symlink_to(outside)
    handler = Capture()
    routes.sprite_file(handler, "/sprite/leak.png" if kind == "outside-symlink" else "/sprite/%2e%2e%2foutside.png")
    assert handler.code == 404 and handler.wfile.getvalue() == b""


@pytest.mark.parametrize("oversized", [False, True], ids=["streamed-small", "oversize-refused"])
def test_asset_streaming_enforces_server_byte_bound(tmp_path, oversized):
    path = tmp_path / "asset.png"
    if oversized:
        with path.open("wb") as stream:
            stream.truncate(MAX_ASSET_RESPONSE_BYTES + 1)
    else:
        path.write_bytes(b"small-png-payload")
    handler = Capture()
    ServerUtilityRoutes.send_bounded_asset_file(handler, path, "image/png", immutable=True)
    assert handler.code == (413 if oversized else 200)
    assert handler.wfile.getvalue() == (b"" if oversized else b"small-png-payload")
    if not oversized:
        assert handler.headers["Content-Length"] == str(path.stat().st_size)


def test_debug_manifest_never_adopts_forced_authority(monkeypatch) -> None:
    from infini_local.web import vfx_debug_routes as vfx_routes

    attached_meta: list[dict[str, Any]] = []
    written_meta: list[dict[str, Any]] = []

    def attach(data, *_args, **_kwargs):
        attached_meta.append(dict(data.get("recipeMeta") or {}))
        data.setdefault("attack", {})["vfxManifestJson"] = "{}"
        data["vfxManifest"] = {"slots": []}
        return data

    routes = VfxDebugRoutes(
        app_version="test",
        normalize_world_id_from_payload=lambda _payload: "world",
        read_world_recipe_cache=lambda *_args, **_kwargs: {
            "id": "cached",
            "recipeMeta": {"recipeKey": "cached", "vfxForcedRecipeId": "stale-force"},
            "attack": {"enabled": True},
        },
        write_world_recipe_cache=lambda _key, _world, data, **_kwargs: written_meta.append(
            dict(data.get("recipeMeta") or {})
        ),
        final_normalize=lambda data: data,
    )
    monkeypatch.setattr(vfx_routes, "attach_hybrid_vfx_manifest", attach)

    routes.select_manifest({
        "data": {"id": "probe", "recipeMeta": {}, "attack": {"enabled": True}},
        "forceRecipeId": "debug-force",
    })
    routes.reroll_cached_manifest({
        "recipeKey": "cached",
        "forceRecipeId": "debug-force",
        "rerollSalt": "next",
    })

    assert all("vfxForcedRecipeId" not in meta for meta in attached_meta)
    assert all("vfxForcedRecipeId" not in meta for meta in written_meta)


def test_debug_views_consume_authoritative_recipe_files(tmp_path: Path, monkeypatch) -> None:
    from infini_local.pipelines import visual_delivery_gate
    from infini_local.qa.live_no_image_fixture import write_no_image_fixture_png

    # Present transfer-roster paths require actual offline PNG bytes in the
    # serving roots; a generated status alone cannot certify a cache fixture.
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path)
    for name in ("generated-a.png", "generated-b.png", "debug.png"):
        write_no_image_fixture_png(tmp_path / name)
    routes = utility_routes(tmp_path)
    routes.read_json_file = world_storage.read_json_file

    from infini_local.web.vfx_debug_routes import _sample_data
    from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest
    from infini_local.core.runtime_authoring import RUNTIME_PROGRAM_API_VERSION

    recipe_a = _sample_data()
    recipe_a.update({"id": "generated-a", "name": "Generated A", "contractVersions": {"runtimeApiVersion": RUNTIME_PROGRAM_API_VERSION}, "visual": {"spriteStatus": "generated", "spritePath": "generated-a.png"}})
    recipe_a = attach_hybrid_vfx_manifest(recipe_a, "recipe-a")
    recipe_b = _sample_data()
    recipe_b.update({"id": "generated-b", "name": "Generated B", "visual": {"spriteStatus": "generated", "spritePath": "generated-b.png"}})
    recipe_b = attach_hybrid_vfx_manifest(recipe_b, "recipe-b")

    world_storage.write_world_recipe_cache(
        tmp_path,
        "9.9.9",
        "recipe-a",
        "debug-world",
        recipe_a,
        parent_a_name="Wooden Sword",
        parent_b_name="Work Bench",
        world_name="Debug World",
    )
    world_storage.write_world_recipe_cache(
        tmp_path,
        "9.9.9",
        "recipe-b",
        "debug-world",
        recipe_b,
        parent_a_name="Gel",
        parent_b_name="Torch",
        world_name="Debug World",
    )

    root = world_storage.world_recipe_dir(tmp_path, "debug-world")
    assert not (root / "index.json").exists()
    assert not (root / "health.json").exists()

    recipes = routes.debug_recipes()
    assert {row["key"] for row in recipes} == {"recipe-a", "recipe-b"}
    assert next(row for row in recipes if row["key"] == "recipe-a")["a"] == "Wooden Sword"

    health = routes.debug_recipe_health()
    assert {row["key"] for row in health} == {"recipe-a", "recipe-b"}
    assert all(row["status"] == "healthy" for row in health)

    worlds = routes.debug_worlds()
    assert worlds == [
        {
            "dir": "world_debug-world",
            "path": str(root),
            "worldId": "debug-world",
            "worldName": "Debug World",
            "recipeCount": 2,
            "healthCounts": {"healthy": 2},
            "updatedAt": worlds[0]["updatedAt"],
        }
    ]
    assert isinstance(worlds[0]["updatedAt"], float)

    latest_dump = routes.debug_latest_recipe_dump()
    assert latest_dump["ok"] is True
    assert latest_dump["name"] in {"Generated A", "Generated B"}
    assert routes.debug_contracts()["latestRecipeContractVersions"] == {"runtimeApiVersion": RUNTIME_PROGRAM_API_VERSION}


def test_authored_promise_exhaustion_reports_invalid_output() -> None:
    failure = {
        "stage": "01_author_llm_plan",
        "error": "PlannerUnavailable('planner repeated unsupported gameplay promises after 2 re-author attempts: orbiting_companion')",
    }

    status, code, retryable, friendly = _combine_failure_http_response(
        "structured combine failure",
        failure,
    )
    payload = _combine_failure_payload(status, code, friendly, failure, retryable=retryable)

    assert (status, code, retryable) == (422, "llm_output_invalid", True)
    assert "invalid" in payload["playerMessage"].lower()
    assert payload["lastFailure"] == failure


@pytest.mark.parametrize(
    ("mode", "responses_missing", "upstream", "paths"),
    [
        ("chat_completions", False, "ExactVendor/region-1", ["/v1/chat/completions"]),
        ("responses", False, "ExactVendor/region-1", ["/v1/responses"]),
        ("auto", True, "ExactVendor/region-1", ["/v1/responses", "/v1/chat/completions"]),
        ("chat_completions", False, "", ["/v1/chat/completions"]),
    ],
)
def test_actual_serialized_http_preserves_provider_pin(monkeypatch, mode, responses_missing, upstream, paths):
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append((self.path, body))
            missing = responses_missing and self.path == "/v1/responses"
            if missing:
                response = {"error": {"message": "Responses endpoint not supported"}}
            elif self.path == "/v1/responses":
                response = {"id": "local-response", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}]}
            else:
                response = {"choices": [{"message": {"role": "assistant", "content": '{"ok":true}'}, "finish_reason": "stop"}]}
            encoded = json.dumps(response).encode()
            self.send_response(404 if missing else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setattr(transport, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(transport, "_RESPONSES_CAPABILITY", {})
    monkeypatch.setattr(transport, "_STRICT_SCHEMA_CAPABILITY", {})
    monkeypatch.setattr(transport, "_llm_replay_json_response", lambda _payload: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    token = transport._CURRENT_LLM_ITEM_LEASE.set(None)
    thread.start()
    try:
        context = {
            "provider": "openrouter", "openrouter_provider": upstream,
            "base_url": f"http://127.0.0.1:{server.server_port}",
            "model": "owner/model:free", "api_mode": mode, "api_key": "offline-loopback-only",
        }
        payload = {"messages": [{"role": "user", "content": "offline transport fixture"}], "max_tokens": 32}
        result = transport._llm_json_single_context(payload, 3, context)
        assert json.loads(result["choices"][0]["message"]["content"]) == {"ok": True}
        assert [path for path, _ in observed] == paths
        for _, body in observed:
            assert body["model"] == "owner/model:free"
            if upstream:
                assert body["provider"] == {"only": [upstream], "allow_fallbacks": False}
            else:
                assert "provider" not in body
        assert "provider" not in payload  # No mutation of author-owned input.
    finally:
        transport._CURRENT_LLM_ITEM_LEASE.reset(token)
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
