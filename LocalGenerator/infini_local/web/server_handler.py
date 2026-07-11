from __future__ import annotations

import ipaddress
import json
import socket
import time
import traceback
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable
from urllib.parse import urlparse


MAX_JSON_BODY_BYTES = 2 * 1024 * 1024
JSON_BODY_READ_TIMEOUT_SECONDS = 10
_GET_LOOPBACK_REQUIRED_EXACT_ROUTES = {
    "/shutdown",
    "/trace",
    "/trace.json",
    "/trace_clear",
}
_GET_LOOPBACK_REQUIRED_PREFIX_ROUTES = (
    "/sdcpp",
    "/debug/",
    "/visual_doctor",
    "/zimage_doctor",
)
_POST_LOOPBACK_REQUIRED_EXACT_ROUTES = {"/combine"}
_POST_LOOPBACK_REQUIRED_PREFIX_ROUTES = ("/debug/vfx",)


def _is_loopback_host(host: str) -> bool:
    if not host:
        return False

    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    if host.lower() in {"localhost", "localhost.localdomain", "::ffff:127.0.0.1"}:
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_loopback)


def build_handler(
    *,
    app_version: str,
    utility_routes: Callable[[], Any],
    vfx_debug_routes: Callable[[], Any],
    combine_endpoint: Any,
    combine_cache_lookup: Callable[..., Any],
    sanitize_recipe_for_delivery: Callable[..., Any],
    combine: Callable[..., Any],
    trace_event: Callable[..., Any],
    log_event: Callable[..., Any],
    is_client_disconnect: Callable[[BaseException], bool],
    world_scope_missing: type[BaseException],
    visual_delivery_blocked: type[BaseException],
    planner_unavailable: type[BaseException],
    last_combine_failure_summary: Callable[[], dict[str, Any]],
    clear_combine_failure: Callable[[str], None],
    combine_failure_http_response: Callable[..., tuple[int, str, bool, str]],
    combine_failure_payload: Callable[..., dict[str, Any]],
    ascii_reason: Callable[[str], str],
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"InfiniCrafterLocal/{app_version}"

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}")

        def do_GET(self) -> None:
            try:
                request_path = urlparse(self.path).path
                if self._route_requires_loopback(request_path, is_post=False) and not self._is_loopback_client():
                    self.json_error(403, "loopback_only", "This endpoint is only available on loopback")
                    return

                if utility_routes().handle_get(self, self.path):
                    return
                if request_path.startswith("/debug/vfx"):
                    if vfx_debug_routes().handle_get(self, self.path):
                        return
                self.send_error(404)
            except Exception as e:
                if is_client_disconnect(e):
                    log_event("debug", "client disconnected during GET response", {"path": self.path, "error": repr(e)})
                    return
                log_event("error", "GET request failed", {"path": self.path, "error": repr(e), "trace": traceback.format_exc()})
                self.json_error(500, "internal_error", repr(e))

        def do_POST(self) -> None:
            request_path = urlparse(self.path).path
            try:
                if self._route_requires_loopback(request_path, is_post=True) and not self._is_loopback_client():
                    self.json_error(403, "loopback_only", "This endpoint is only available on loopback")
                    return

                length = self._content_length_bytes()
                payload = self._read_json_payload(length)

                if request_path.startswith("/debug/vfx"):
                    if vfx_debug_routes().handle_post(self, self.path, payload):
                        return
                if request_path == "/combine":
                    combine_endpoint.handle_combine_request(
                        payload,
                        app_version=app_version,
                        combine_cache_lookup=combine_cache_lookup,
                        sanitize_recipe_for_delivery=sanitize_recipe_for_delivery,
                        combine=combine,
                        trace_event=trace_event,
                        json=self.json,
                        json_status=self.json_status,
                        last_failure_summary=last_combine_failure_summary,
                        clear_failure_state=clear_combine_failure,
                        cache_lookup_passthrough_errors=(world_scope_missing,),
                    )
                    return
                self.send_error(404)
            except world_scope_missing as e:
                if is_client_disconnect(e):
                    return
                log_event("warn", "craft failed: world scope missing", {"path": self.path, "error": str(e)})
                self.json_error(428, "world_id_required", str(e))
            except visual_delivery_blocked as e:
                if is_client_disconnect(e):
                    return
                self._json_combine_failure("visual delivery blocked", e)
            except planner_unavailable as e:
                if is_client_disconnect(e):
                    return
                self._json_combine_failure("structured combine failure", e)
            except OverflowError as e:
                if is_client_disconnect(e):
                    return
                self.json_error(413, "request_too_large", str(e))
            except TimeoutError as e:
                if is_client_disconnect(e):
                    return
                self.json_error(408, "request_timeout", str(e))
            except ValueError as e:
                if is_client_disconnect(e):
                    return
                self.json_error(400, "invalid_json", str(e))
            except Exception as e:
                if is_client_disconnect(e):
                    log_event("debug", "client disconnected during POST response", {"path": self.path, "error": repr(e)})
                    return
                log_event("error", "request failed", {"path": self.path, "error": repr(e), "trace": traceback.format_exc()})
                self.json_error(500, "internal_error", repr(e))

        def _route_requires_loopback(self, request_path: str, *, is_post: bool) -> bool:
            if is_post:
                return request_path in _POST_LOOPBACK_REQUIRED_EXACT_ROUTES or any(
                    request_path.startswith(prefix) for prefix in _POST_LOOPBACK_REQUIRED_PREFIX_ROUTES
                )
            return (
                request_path in _GET_LOOPBACK_REQUIRED_EXACT_ROUTES
                or any(request_path.startswith(prefix) for prefix in _GET_LOOPBACK_REQUIRED_PREFIX_ROUTES)
            )

        def _is_loopback_client(self) -> bool:
            client_host = ""
            if isinstance(self.client_address, (list, tuple)) and self.client_address:
                client_host = str(self.client_address[0])
            elif isinstance(self.client_address, str):
                client_host = self.client_address
            return _is_loopback_host(client_host)

        def _content_length_bytes(self) -> int:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except (TypeError, ValueError) as e:
                raise ValueError("invalid Content-Length") from e

            if length < 0:
                raise ValueError("negative Content-Length")
            if length > MAX_JSON_BODY_BYTES:
                raise OverflowError(f"content body too large: {length} > {MAX_JSON_BODY_BYTES}")
            return length

        def _read_json_payload(self, length: int) -> dict[str, Any]:
            if length <= 0:
                return {}

            connection = getattr(self, "connection", None)
            previous_timeout: float | None = None
            if connection is not None and hasattr(connection, "gettimeout"):
                previous_timeout = connection.gettimeout()

            if connection is not None and hasattr(connection, "settimeout"):
                connection.settimeout(JSON_BODY_READ_TIMEOUT_SECONDS)

            try:
                body = self.rfile.read(length)
            except socket.timeout as e:
                raise TimeoutError("request body read timeout") from e
            finally:
                if connection is not None and hasattr(connection, "settimeout"):
                    connection.settimeout(previous_timeout)

            body_text = body.decode("utf-8")
            try:
                return json.loads(body_text or "{}")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError("invalid JSON body") from e

        def _json_combine_failure(self, reason: str, error: BaseException) -> None:
            attached = getattr(error, "_infini_failure_snapshot", None)
            failure = dict(attached) if isinstance(attached, dict) else last_combine_failure_summary()
            status, code, retryable, friendly = combine_failure_http_response(error, failure)
            log_event("warn", f"craft failed: {reason}", {
                "path": self.path,
                "httpStatus": status,
                "errorCode": code,
                "error": str(error),
                "lastFailure": failure,
                "failureSnapshotError": getattr(error, "_infini_failure_snapshot_error", ""),
            })
            self.json_status(status, combine_failure_payload(status, code, friendly, failure, retryable=retryable))

        def json(self, obj: Any) -> None:
            self.json_status(200, obj)

        def json_status(self, status: int, obj: Any) -> None:
            data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                if is_client_disconnect(e):
                    log_event("debug", "client disconnected while writing JSON response", {"path": self.path, "status": status, "error": repr(e)})
                    return
                raise

        def json_error(self, status: int, code: str, message: str = "") -> None:
            self.json_status(status, {"ok": False, "error": str(code or "error"), "message": str(message or ""), "version": app_version})

        def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
            try:
                self.json_error(int(code), f"http_{int(code)}", message or explain or "")
            except Exception as e:
                if is_client_disconnect(e):
                    return
                super().send_error(code, ascii_reason(message or explain or "error"), None)

    return Handler


__all__ = ["build_handler", "MAX_JSON_BODY_BYTES", "JSON_BODY_READ_TIMEOUT_SECONDS", "_is_loopback_host"]
