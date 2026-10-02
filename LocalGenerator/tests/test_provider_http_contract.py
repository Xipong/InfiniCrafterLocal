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
def test_utility_and_debug_dispatch_use_exact_parsed_route(tmp_path, monkeypatch, owner, method, path, accepted):
    from infini_local.services import combine_endpoint

    monkeypatch.setattr(combine_endpoint, "_GENERATION_ACCEPTING", True)
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


def test_health_acknowledges_only_allowlisted_applied_config(tmp_path, monkeypatch):
    from infini_local.web import server

    monkeypatch.setattr(server.combine_endpoint, "_GENERATION_ACCEPTING", True)
    monkeypatch.setattr(server, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(server, "WORLD_RECIPES_DIR", tmp_path / "worlds")
    monkeypatch.setattr(server, "sdcpp_debug_snapshot", lambda **_: {"autostart": False, "command": []})
    monkeypatch.setattr(server, "_multiplayer_connect_info", lambda: {})
    monkeypatch.setattr(server, "llm_auth_snapshot", lambda: {
        "provider": "openrouter", "model": "fixture/model", "openrouterProvider": "Exact/slug",
        "api_key": "SYNTHETIC-SECRET-MUST-NOT-ENTER-PROJECTION",
        "baseUrl": "https://fixture.invalid/?key=SYNTHETIC-URL-SECRET",
    })
    health = server._health_payload()
    assert health["effectiveConfig"] == {
        "cacheDir": str((tmp_path / "cache").resolve()),
        "worldRecipesDir": str((tmp_path / "worlds").resolve()),
        "imageBackend": server.visual_config.IMAGE_BACKEND,
        "llmProvider": "openrouter", "llmModel": "fixture/model",
        "openrouterProvider": "Exact/slug", "sdcppAutostart": False,
    }
    assert "SECRET" not in json.dumps(health["effectiveConfig"])
    assert health["generationActivity"] == {"active": 0, "waiting": 0, "accepting": True}


@pytest.mark.parametrize("phase", ["active", "waiting", "failure"])
def test_safe_shutdown_refuses_admitted_work_and_balances_activity(tmp_path, monkeypatch, phase):
    from infini_local.services import combine_endpoint as endpoint

    monkeypatch.setattr(endpoint, "_GENERATION_ACCEPTING", True, raising=False)
    semaphore = threading.BoundedSemaphore(1)
    monkeypatch.setattr(endpoint, "COMBINE_SEMAPHORE", semaphore)
    monkeypatch.setattr(endpoint, "COMBINE_BUSY_WAIT_SECONDS", 2)
    entered, release = threading.Event(), threading.Event()
    failures = []
    result = Capture()
    if phase == "waiting":
        semaphore.acquire()

    def generate(_):
        entered.set()
        assert release.wait(5)
        if phase == "failure":
            raise ValueError("intentional pipeline failure")
        return {"id": "finished"}

    def run():
        try:
            endpoint.handle_combine_request(
                {}, app_version="test", combine_cache_lookup=lambda _: ("key", None),
                sanitize_recipe_for_delivery=lambda p: p, combine=generate,
                trace_event=lambda _l, _s, msg, _d: entered.set() if "waiting for active craft" in msg else None,
                json=result.json, json_status=result.json_status,
            )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    shutdown = Capture()
    routes = utility_routes(tmp_path)
    try:
        assert entered.wait(5)
        routes.handle_get(shutdown, "/shutdown")
        assert shutdown.code == 409, "safe restart must not discard admitted work"
        assert shutdown.payload["status"] == "generator_busy"
        activity = shutdown.payload["generationActivity"]
        assert activity == {"active": int(phase != "waiting"), "waiting": int(phase == "waiting"), "accepting": True}
    finally:
        release.set()
        if phase == "waiting":
            semaphore.release()
        worker.join(5)
    assert not worker.is_alive()
    assert len(failures) == int(phase == "failure"), failures
    assert endpoint.generation_activity_snapshot() == {"active": 0, "waiting": 0, "accepting": True}
    assert semaphore.acquire(blocking=False)
    semaphore.release()


def test_safe_shutdown_closes_admission_before_acknowledging(tmp_path, monkeypatch):
    from infini_local.services import combine_endpoint as endpoint

    monkeypatch.setattr(endpoint, "_GENERATION_ACCEPTING", True, raising=False)
    shutdown, generated = Capture(), Capture()
    stopped = threading.Event()
    shutdown.server = SimpleNamespace(shutdown=stopped.set)
    routes = utility_routes(tmp_path)
    routes.handle_get(shutdown, "/shutdown")
    assert shutdown.code == 200
    endpoint.handle_combine_request(
        {}, app_version="test", combine_cache_lookup=lambda _: ("key", None),
        sanitize_recipe_for_delivery=lambda p: p, combine=lambda _: {"id": "must_not_start"},
        trace_event=lambda *_: None, json=generated.json, json_status=generated.json_status,
    )
    assert generated.code == 503 and generated.payload["status"] == "generator_shutting_down"
    assert endpoint.generation_activity_snapshot() == {"active": 0, "waiting": 0, "accepting": False}
    assert stopped.wait(2)


@pytest.mark.parametrize("view,recipe_reads,rows", [("recipes", 50, 50), ("health", 100, 100), ("latest", 1, 1), ("contracts", 1, 1)])
def test_debug_views_read_only_selected_recipe_bodies(tmp_path, view, recipe_reads, rows):
    import os

    routes = utility_routes(tmp_path)
    for index in range(200):
        world = tmp_path / f"world_{index % 2}"
        recipes = world / "recipes"
        recipes.mkdir(parents=True, exist_ok=True)
        (world / "manifest.json").write_text(json.dumps({"worldId": str(index % 2)}))
        path = recipes / f"r_{index:024x}.json"
        path.write_text(json.dumps({"name": f"recipe-{index}", "recipeKey": path.stem,
                                   "recipeHealth": {"ok": True, "status": "ready"},
                                   "contractVersions": {"fixture": index}}))
        os.utime(path, (1000 + index, 1000 + index))
    reads = []

    def read(path):
        reads.append(path)
        return world_storage.read_json_file(path)

    routes.read_json_file = read
    handler = Capture()
    route = {"recipes": "/debug/recipes", "health": "/debug/recipe_health",
             "latest": "/debug/latest_recipe", "contracts": "/debug/contracts"}[view]
    routes.handle_get(handler, route)
    if view in {"recipes", "health"}:
        actual = handler.payload[view]
        assert len(actual) == rows
        assert actual[0]["key"] == f"r_{199:024x}"
    elif view == "latest":
        assert handler.payload["name"] == "recipe-199"
    else:
        assert handler.payload["latestRecipeContractVersions"] == {"fixture": 199}
    assert sum(p.parent.name == "recipes" for p in reads) == recipe_reads
    assert sum(p.name == "manifest.json" for p in reads) <= 2


@pytest.mark.parametrize("multi_dev", [False, True], ids=["ordinary-slot", "multidev-profile-slot"])
def test_explicit_force_shutdown_does_not_start_waiting_generation(tmp_path, monkeypatch, multi_dev):
    from infini_local.services import combine_endpoint as endpoint

    entered, stopped = threading.Event(), threading.Event()

    class ObservedSemaphore(threading.BoundedSemaphore):
        def acquire(self, blocking=True, timeout=None):
            acquired = super().acquire(blocking=blocking, timeout=timeout)
            if not blocking and not acquired:
                entered.set()
            return acquired

    held = ObservedSemaphore(1)
    held.acquire()
    monkeypatch.setattr(endpoint, "_GENERATION_ACCEPTING", True)
    monkeypatch.setattr(endpoint, "COMBINE_BUSY_WAIT_SECONDS", 2)
    if multi_dev:
        monkeypatch.setattr(endpoint, "MULTIDEV_PROFILE_SEMAPHORES", {"llm_2": held})
    else:
        monkeypatch.setattr(endpoint, "COMBINE_SEMAPHORE", held)
    result, shutdown, failures, calls = Capture(), Capture(), [], []
    setattr(shutdown, "server", SimpleNamespace(shutdown=stopped.set))

    def run():
        try:
            endpoint.handle_combine_request(
                {"multiDevCraft": multi_dev, "llmProfileId": "llm_2"}, app_version="test",
                combine_cache_lookup=lambda _: ("key", None), sanitize_recipe_for_delivery=lambda p: p,
                combine=lambda _: calls.append("generate") or {"id": "unexpected"},
                trace_event=lambda *_: None, json=result.json, json_status=result.json_status,
            )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        utility_routes(tmp_path).handle_get(shutdown, "/shutdown?force=1")
        assert shutdown.code == 200 and shutdown.payload["forced"] is True
        assert shutdown.payload["generationActivity"] == {"active": 0, "waiting": 1, "accepting": False}
    finally:
        held.release()
        worker.join(5)
    assert not worker.is_alive() and not failures and not calls
    assert result.code == 503
    assert endpoint.generation_activity_snapshot() == {"active": 0, "waiting": 0, "accepting": False}
    assert held.acquire(blocking=False)
    held.release()
    assert stopped.wait(2)


def test_debug_views_skip_unreadable_without_mutating_authority(tmp_path):
    import os

    directory = tmp_path / "world_test" / "recipes"
    directory.mkdir(parents=True)
    good, broken = directory / "valid.json", directory / "newest.json"
    good.write_text(json.dumps({"name": "valid", "recipeKey": "valid"}))
    broken.write_text("{broken")
    os.utime(good, (1000, 1000))
    os.utime(broken, (1001, 1001))
    routes = utility_routes(tmp_path)
    routes.read_json_file = world_storage.read_json_file
    before = {p: p.read_bytes() for p in (good, broken)}
    assert routes.debug_latest_recipe_dump()["name"] == "valid"
    assert [row["key"] for row in routes.debug_recipes()] == ["valid"]
    assert routes.debug_contracts()["latestRecipeContractVersions"] == {}
    assert routes.debug_recipe_health() == []
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize("backend,autostart,alive,configured,local_files,expected", [
    ("sdcpp", False, True, False, False, True),
    ("sdcpp", False, False, False, False, False),
    ("sdcpp", True, False, False, False, False),
    ("sdcpp", True, False, True, True, True),
    ("sdcpp", True, True, True, False, False),
    ("a1111", False, False, False, False, True),
])
def test_visual_doctor_checks_selected_backend_ownership(
    tmp_path, backend, autostart, alive, configured, local_files, expected,
):
    routes = utility_routes(tmp_path)
    routes.health_payload = lambda: {
        "imageBackend": backend, "visualRequireItemSprite": True,
        "visualRequireZImageBackend": False, "pillowAvailable": True,
    }
    local = tmp_path / "local-component"
    if local_files:
        local.write_bytes(b"fixture")
    snapshot = {"autostart": autostart, "serverAlive": alive, "serverConfigured": configured,
                "serverUrl": "http://127.0.0.1:8080", "serverExe": str(local), "model": str(local)}
    calls = []
    routes.sdcpp_debug_snapshot = lambda **_: calls.append("sdcpp") or snapshot
    result = routes.visual_doctor_payload("/visual_doctor.json")
    assert result["ok"] is expected, result["checks"]
    checks = {check["name"]: check for check in result["checks"]}
    if backend != "sdcpp":
        assert not calls and not any(name.startswith("sdcpp_") for name in checks)
    elif not autostart:
        assert not any(name in checks for name in ("sdcpp_serverExe", "sdcpp_model"))
        assert checks["sdcpp_alive"]["ok"] is alive


@pytest.mark.parametrize("mutation", ["append", "replace", "truncate", "unlink"])
def test_asset_response_pins_open_handle_and_bounds_body(tmp_path, monkeypatch, mutation):
    from infini_local.web import server_utility_routes as routes_module

    monkeypatch.setattr(routes_module, "MAX_ASSET_RESPONSE_BYTES", 128)
    path = tmp_path / "mutable.png"
    initial = b"original" * 8
    path.write_bytes(initial)
    handler = Capture()

    def mutate_after_headers():
        if mutation == "append":
            with path.open("ab") as stream:
                stream.write(b"overflow" * 64)
        elif mutation == "replace":
            replacement = tmp_path / "replacement.png"
            replacement.write_bytes(b"replacement" * 64)
            replacement.replace(path)
        elif mutation == "truncate":
            path.write_bytes(initial[:8])
        else:
            path.unlink()

    handler.end_headers = mutate_after_headers
    ServerUtilityRoutes.send_bounded_asset_file(handler, path, "image/png", immutable=True)
    assert handler.code == 200
    assert int(handler.headers["Content-Length"]) == len(initial)
    assert len(handler.wfile.getvalue()) <= len(initial) <= routes_module.MAX_ASSET_RESPONSE_BYTES
    if mutation == "truncate":
        assert handler.wfile.getvalue() == initial[:8]
        assert getattr(handler, "close_connection", False), "short body must close the HTTP connection"
    else:
        assert handler.wfile.getvalue() == initial


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


@pytest.mark.parametrize("move_fails", [False, True], ids=["quarantined", "quarantine-io-refused"])
def test_cache_rejection_retains_quarantine_diagnostics(tmp_path, monkeypatch, move_fails):
    from infini_local.storage import trace_runtime
    from infini_local.web.vfx_debug_routes import _sample_data

    path = world_storage.world_recipe_file(tmp_path, "world", "recipe")
    world_storage.atomic_write_json(path, _sample_data())
    events = []
    monkeypatch.setattr(trace_runtime, "trace_event", lambda *event: events.append(event))
    if move_fails:
        def refuse(*_a, **_k):
            raise PermissionError("quarantine fixture denied")
        monkeypatch.setattr(world_storage, "quarantine_world_recipe_cache", refuse)
    cached = world_storage.read_world_recipe_cache(
        tmp_path, "fixture", "fixture-identity", "recipe", "world",
        validate_payload=lambda _: {"ok": False, "errors": ["fixture:invalid_binding"]},
    )
    assert cached is None
    assert path.exists() is move_fails
    assert len(events) == 1 and events[0][0] == "warn"
    assert events[0][3]["recipeKey"] == "recipe"
    assert ("could not quarantine" in events[0][2]) is move_fails


def test_cache_only_stale_validation_never_quarantines_fresh_writer(tmp_path, monkeypatch):
    """Schedule either an atomic reader or a versioned/CAS reader without sleeps."""
    from copy import deepcopy
    from infini_local.core.vfx_manifest import _compile_manifest
    from infini_local.pipelines import combine_pipeline as pipeline, visual_delivery_gate as visual
    from infini_local.qa.live_no_image_fixture import hydrate_no_image_fixture_assets, write_no_image_fixture_png
    from infini_local.services import combine_endpoint
    from infini_local.storage import world_recipe_runtime as recipes
    from infini_local.web.vfx_debug_routes import _sample_data

    monkeypatch.setattr(recipes, "WORLD_RECIPES_DIR", tmp_path / "worlds")
    monkeypatch.setattr(visual, "WORLD_RECIPES_DIR", tmp_path / "worlds")
    monkeypatch.setattr(visual, "SPRITE_DIR", tmp_path / "sprites")
    good = _sample_data()
    hydrate_no_image_fixture_assets(good, write_no_image_fixture_png(tmp_path / "sprites" / "test.png"))
    good["vfxManifest"] = _compile_manifest(good, {
        "effectMagnitude": 0.0, "visualBudgetClass": "tiny",
        "motif": {"element": "neutral", "shapeLanguage": "none", "motionLanguage": "none",
                  "paletteRole": "primary", "rhythm": 1.0, "chaos": 0.0}, "slots": [],
    }, "cache-race-contract")
    assert pipeline._cached_payload_report(good)["ok"]
    payload = {"worldId": "race", "itemA": {"type": 1}, "itemB": {"type": 2}}
    key, _ = pipeline.combine_cache_lookup(payload)
    path = recipes.world_recipe_file("race", key)
    recipes.cache_put(key, payload["itemA"], payload["itemB"], good, "race")
    assert pipeline.combine_cache_lookup(payload)[1]["id"] == good["id"]
    bad = deepcopy(good)
    bad["runtimeProgram"]["bindings"][0]["id"] = ""
    world_storage.atomic_write_json(path, bad)
    fresh = deepcopy(good)
    fresh["id"] = "fresh_valid_recipe"
    entered, resume, probed, written = (threading.Event() for _ in range(4))
    failures, schedule = [], {}
    original_report = pipeline._cached_payload_report

    def paused_report(data):
        if threading.current_thread().name == "stale-reader":
            entered.set()
            assert resume.wait(5), "reader barrier not released"
        return original_report(data)

    def reader():
        try:
            pipeline.combine_cache_lookup(payload)
        except BaseException as exc:
            failures.append(exc)

    def writer():
        lock = world_storage._storage_lock(path)
        # Arrange a deterministic race for the old/CAS design, or let an atomic
        # read finish first. This controls scheduling, not the correctness oracle.
        immediate = lock.acquire(blocking=False)
        schedule["immediate"] = immediate
        probed.set()
        try:
            recipes.cache_put(key, payload["itemA"], payload["itemB"], fresh, "race")
            written.set()
        except BaseException as exc:
            failures.append(exc)
        finally:
            if immediate:
                lock.release()

    monkeypatch.setattr(pipeline, "_cached_payload_report", paused_report)
    rt = threading.Thread(target=reader, name="stale-reader")
    wt = threading.Thread(target=writer, name="fresh-writer")
    rt.start()
    try:
        assert entered.wait(5)
        wt.start()
        assert probed.wait(5)
        if schedule["immediate"]:
            assert written.wait(5)
    finally:
        resume.set()
        rt.join(5)
        if wt.ident is not None:
            wt.join(5)
    assert not rt.is_alive() and not wt.is_alive()
    assert not failures, failures
    assert written.is_set()
    assert path.exists(), "stale reader removed the committed fresh recipe"
    assert world_storage.read_json_file(path)["id"] == "fresh_valid_recipe"
    handler = Capture()
    combine_endpoint.handle_combine_request(
        {**payload, "cacheOnly": True}, app_version="test",
        combine_cache_lookup=pipeline.combine_cache_lookup,
        sanitize_recipe_for_delivery=recipes.sanitize_recipe_for_delivery,
        combine=lambda _: pytest.fail("cacheOnly must not generate"), trace_event=lambda *_a, **_k: None,
        json=handler.json, json_status=handler.json_status,
    )
    assert handler.code == 200 and handler.payload["id"] == "fresh_valid_recipe"
    assert all(world_storage.read_json_file(p).get("id") != "fresh_valid_recipe"
               for p in (path.parent.parent / "invalid").glob("*.json") if not p.name.endswith(".reason.json"))


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
