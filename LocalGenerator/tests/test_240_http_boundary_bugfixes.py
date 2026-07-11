from __future__ import annotations

import io
import socket
import types
from pathlib import Path
from typing import Any

from urllib.parse import urlparse

from infini_local.web.server_handler import (
    JSON_BODY_READ_TIMEOUT_SECONDS,
    MAX_JSON_BODY_BYTES,
    build_handler,
)
from infini_local.web.server_utility_routes import ServerUtilityRoutes
from infini_local.web.vfx_debug_routes import VfxDebugRoutes


class _NoReadFile:
    def __init__(self) -> None:
        self.read_calls = 0

    def read(self, _size: int = -1) -> bytes:
        self.read_calls += 1
        raise AssertionError("unexpected body read")


class _BlockingReadFile:
    def __init__(self) -> None:
        self.read_calls = 0

    def read(self, _size: int = -1) -> bytes:
        self.read_calls += 1
        raise socket.timeout("simulated read timeout")


class _FakeConnection:
    def __init__(self) -> None:
        self.timeout: float | None = None
        self.set_calls: list[float | None] = []
        self.get_calls = 0

    def gettimeout(self) -> float | None:
        self.get_calls += 1
        return self.timeout

    def settimeout(self, value: float | None) -> None:
        self.timeout = value
        self.set_calls.append(value)


class _Capture:
    def __init__(self) -> None:
        self.code: int | None = None
        self.payload: Any = None

    def json(self, obj: Any) -> None:
        self.code = 200
        self.payload = obj

    def json_status(self, status: int, obj: Any) -> None:
        self.code = status
        self.payload = obj

    def json_error(self, status: int, code: str, message: str = "") -> None:
        self.code = status
        self.payload = {"error": code, "message": str(message)}

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self.code = int(code)
        self.payload = {"error": f"http_{int(code)}", "message": str(message or explain or "")}


def _make_boundary_handler_class() -> type:
    class _WorldScopeMissing(Exception):
        pass

    class _VisualDeliveryBlocked(Exception):
        pass

    class _PlannerUnavailable(Exception):
        pass

    class _UtilityRoutes:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def handle_get(self, handler: Any, path: str) -> bool:
            self.calls.append(urlparse(path).path)
            request_path = urlparse(path).path
            if request_path == "/get_asset":
                handler.json({"ok": True, "route": "get_asset"})
                return True
            if request_path == "/health":
                handler.json({"ok": True, "route": "health"})
                return True
            return False

        def handle_post(self, _handler: Any, _path: str, _payload: Any) -> bool:
            return False

    class _VfxRoutes:
        def handle_get(self, _handler: Any, _path: str) -> bool:
            return False

        def handle_post(self, _handler: Any, _path: str, _payload: Any) -> bool:
            return False

    class _CombineEndpoint:
        def handle_combine_request(self, _payload: Any, *, json: Any = None, **_kwargs: Any) -> None:
            if json is not None:
                json({"ok": True, "route": "combine"})

    return build_handler(
        app_version="test",
        utility_routes=_UtilityRoutes,
        vfx_debug_routes=_VfxRoutes,
        combine_endpoint=_CombineEndpoint(),
        combine_cache_lookup=lambda *_args, **_kwargs: None,
        sanitize_recipe_for_delivery=lambda *_args, **_kwargs: None,
        combine=lambda *_args, **_kwargs: None,
        trace_event=lambda *_args, **_kwargs: None,
        log_event=lambda *_args, **_kwargs: None,
        is_client_disconnect=lambda _exc: False,
        world_scope_missing=_WorldScopeMissing,
        visual_delivery_blocked=_VisualDeliveryBlocked,
        planner_unavailable=_PlannerUnavailable,
        last_combine_failure_summary=lambda: {},
        clear_combine_failure=lambda _reason: None,
        combine_failure_http_response=lambda _err, _state: (500, "failure", False, "failure"),
        combine_failure_payload=lambda *_args, **_kwargs: {"ok": False, "error": "failure"},
        ascii_reason=lambda _msg: "error",
    )


def _make_handler(
    handler_cls: type,
    *,
    path: str,
    headers: dict[str, str],
    rfile: Any,
    client_address: tuple[str, int],
) -> tuple[Any, _Capture]:
    handler = handler_cls.__new__(handler_cls)
    handler.path = path
    handler.headers = headers
    handler.rfile = rfile
    handler.wfile = io.BytesIO()
    handler.client_address = client_address
    handler.connection = _FakeConnection()

    capture = _Capture()
    handler.json = types.MethodType(_Capture.json, capture)
    handler.json_status = types.MethodType(_Capture.json_status, capture)
    handler.json_error = types.MethodType(_Capture.json_error, capture)
    handler.send_error = types.MethodType(_Capture.send_error, capture)

    return handler, capture


def _build_shutdown_routes(root: Path) -> ServerUtilityRoutes:
    class _TraceDashboard:
        def render_mp_connect_html(self, _info: dict[str, Any]) -> str:
            return "<html/>"

    class _AssetSyncService:
        def safe_asset_file_from_query(self, _query: dict[str, list[str]], *_args: Any, **_kwargs: Any) -> Any:
            return None

        def find_asset_file(self, *_args: Any, **_kwargs: Any) -> Any:
            return None

        def asset_content_type(self, _path: Path) -> str:
            return "image/png"

    return ServerUtilityRoutes(
        app_version="test",
        root=root,
        cache_dir=root,
        sprite_dir=root,
        world_recipes_dir=root,
        trace_files=(),
        trace_dashboard=_TraceDashboard(),
        asset_sync_service=_AssetSyncService(),
        health_payload=lambda: {"ok": True},
        multiplayer_connect_info=lambda: {"host": "127.0.0.1"},
        trace_snapshot=lambda: {},
        trace_snapshot_html=lambda: "<html/>",
        trace_event=lambda *_args, **_kwargs: None,
        sdcpp_start=lambda: True,
        sdcpp_debug_snapshot=lambda include_log_tail: {"ok": True},
        read_json_file=lambda _p: None,
        last_combine_failure_payload=lambda: {},
        cleanup_for_shutdown=lambda _reason: None,
        build_image_prompt=lambda *_args, **_kwargs: "",
        maybe_generate_sprite=lambda _payload: _payload,
        normalize_asset_prompt=lambda *_args, **_kwargs: "",
        generate_visual_asset=lambda *_args, **_kwargs: ("", "", 0.0, {}),
        asset_negative_prompt=lambda _payload: "",
        alpha_stats=lambda _img: {},
        image_module=None,
    )


class _CaptureHandler:
    def __init__(self) -> None:
        self.json_payload = None
        self.called = 0

    def json(self, obj: Any) -> None:
        self.json_payload = obj
        self.called += 1

    def send_error(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - compatibility only
        self.called += 1


def test_get_asset_route_stays_available_to_remote_peer_and_control_routes_stay_loopback_bound() -> None:
    Handler = _make_boundary_handler_class()
    remote_address = ("198.51.100.20", 1234)

    asset_handler, capture = _make_handler(
        Handler,
        path="/get_asset?name=foo.png",
        headers={},
        rfile=io.BytesIO(),
        client_address=remote_address,
    )
    asset_handler.do_GET()
    assert capture.code == 200
    assert capture.payload == {"ok": True, "route": "get_asset"}

    control_handler, control_capture = _make_handler(
        Handler,
        path="/shutdown",
        headers={},
        rfile=io.BytesIO(),
        client_address=remote_address,
    )
    control_handler.do_GET()
    assert control_capture.code == 403
    assert control_capture.payload["error"] == "loopback_only"


def test_ipv4_mapped_loopback_is_still_allowed_for_control_routes() -> None:
    Handler = _make_boundary_handler_class()
    handler, capture = _make_handler(
        Handler,
        path="/combine",
        headers={"Content-Length": "2"},
        rfile=io.BytesIO(b"{}"),
        client_address=("::ffff:127.0.0.1", 1234),
    )
    handler.do_POST()
    assert capture.code == 200
    assert capture.payload == {"ok": True, "route": "combine"}


def test_remote_post_control_route_is_denied_and_body_is_not_read() -> None:
    Handler = _make_boundary_handler_class()
    rfile = _NoReadFile()
    handler, capture = _make_handler(
        Handler,
        path="/combine",
        headers={"Content-Length": "2"},
        rfile=rfile,
        client_address=("203.0.113.10", 1234),
    )
    handler.do_POST()
    assert capture.code == 403
    assert capture.payload["error"] == "loopback_only"
    assert rfile.read_calls == 0


def test_boundary_route_classification_rejects_shutdown_prefix_and_allows_allowed_assets() -> None:
    Handler = _make_boundary_handler_class()
    handler, _ = _make_handler(
        Handler,
        path="/health",
        headers={},
        rfile=io.BytesIO(),
        client_address=("127.0.0.1", 1111),
    )

    assert handler._route_requires_loopback("/shutdown", is_post=False) is True
    assert handler._route_requires_loopback("/shutdownAnything", is_post=False) is False
    assert handler._route_requires_loopback("/sdcpp_start", is_post=False) is True
    assert handler._route_requires_loopback("/debug/trace", is_post=False) is True
    assert handler._route_requires_loopback("/visual_doctor", is_post=False) is True
    assert handler._route_requires_loopback("/health", is_post=False) is False


def test_utility_shutdown_route_match_is_exact_with_query_string_allowed() -> None:
    tmp_path = Path("/tmp/http-boundary-test")
    tmp_path.mkdir(parents=True, exist_ok=True)
    routes = _build_shutdown_routes(tmp_path)

    handler = _CaptureHandler()
    assert routes.handle_get(handler, "/shutdown?force=1") is True
    assert handler.json_payload is not None
    assert handler.json_payload["message"] == "shutdown scheduled"

    handler = _CaptureHandler()
    assert routes.handle_get(handler, "/shutdownAnything") is False
    assert handler.called == 0


def test_post_payload_length_limit_rejects_too_large_body_without_reading() -> None:
    Handler = _make_boundary_handler_class()
    rfile = _NoReadFile()
    handler, capture = _make_handler(
        Handler,
        path="/combine",
        headers={"Content-Length": str(MAX_JSON_BODY_BYTES + 1)},
        rfile=rfile,
        client_address=("127.0.0.1", 1111),
    )

    handler.do_POST()
    assert capture.code == 413
    assert capture.payload["error"] == "request_too_large"
    assert rfile.read_calls == 0


def test_post_negative_content_length_is_rejected() -> None:
    Handler = _make_boundary_handler_class()
    rfile = _NoReadFile()
    handler, capture = _make_handler(
        Handler,
        path="/combine",
        headers={"Content-Length": "-1"},
        rfile=rfile,
        client_address=("127.0.0.1", 1111),
    )

    handler.do_POST()
    assert capture.code == 400
    assert capture.payload["error"] == "invalid_json"
    assert rfile.read_calls == 0


def test_post_body_read_timeout_uses_bounded_timeout_and_returns_408() -> None:
    Handler = _make_boundary_handler_class()
    rfile = _BlockingReadFile()
    handler, capture = _make_handler(
        Handler,
        path="/combine",
        headers={"Content-Length": "6"},
        rfile=rfile,
        client_address=("127.0.0.1", 1111),
    )

    handler.do_POST()
    assert capture.code == 408
    assert capture.payload["error"] == "request_timeout"
    assert rfile.read_calls == 1
    assert handler.connection.set_calls[0] == JSON_BODY_READ_TIMEOUT_SECONDS
    assert handler.connection.set_calls[1] is None


def test_vfx_debug_get_routes_require_an_exact_parsed_path() -> None:
    routes = object.__new__(VfxDebugRoutes)
    object.__setattr__(routes, "recipe_matrix", lambda: {"route": "matrix"})
    handler = _CaptureHandler()

    assert routes.handle_get(handler, "/debug/vfx_matrix_extra") is False
    assert handler.called == 0
    assert routes.handle_get(handler, "/debug/vfx_matrix?verbose=1") is True
    assert handler.json_payload == {"route": "matrix"}


def test_vfx_debug_post_routes_require_an_exact_parsed_path() -> None:
    routes = object.__new__(VfxDebugRoutes)
    object.__setattr__(routes, "select_manifest", lambda payload: {"payload": payload})
    handler = _CaptureHandler()

    assert routes.handle_post(handler, "/debug/vfx_select_extra", {"x": 1}) is False
    assert handler.called == 0
    assert routes.handle_post(handler, "/debug/vfx_select?dryRun=1", {"x": 1}) is True
    assert handler.json_payload == {"payload": {"x": 1}}
