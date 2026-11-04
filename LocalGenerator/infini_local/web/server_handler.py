from __future__ import annotations

from copy import deepcopy
import ipaddress
import socket
import time
import traceback
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from infini_local.core import strict_json
from infini_local.core.config_bootstrap import APP_VERSION
from infini_local.core.errors import PlannerUnavailable
from infini_local.pipelines import combine_pipeline, generation_debug
from infini_local.pipelines.visual.delivery import VisualDeliveryBlocked
from infini_local.services import combine_endpoint
from infini_local.storage.world_recipe_runtime import WorldScopeMissing
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from infini_local.storage.trace_runtime import log_event, trace_event
from infini_local.web import server_utility_routes as utility_routes, vfx_debug_routes
from infini_local.web.http_response_helpers import (
    _ascii_reason, _combine_failure_http_response, _combine_failure_payload, _is_client_disconnect,
)
from infini_local.storage import trace_runtime, trace_tools


class _InvalidJsonRequest(ValueError):
    """A client-controlled request framing or JSON parse failure."""


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
)
_CONTROL_ROUTES = {"/shutdown", "/trace_clear"}
_POST_LOOPBACK_REQUIRED_EXACT_ROUTES = {"/combine", *_CONTROL_ROUTES}
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


class Handler(BaseHTTPRequestHandler):
    server_version = f"InfiniCrafterLocal/{APP_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        if trace_runtime.TRACE_PROMPTS_ENABLED:
            line = trace_tools._redact_diagnostic(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}")
            try:
                print(line)
            except (OSError, ValueError) as error:
                # A detached/closed console must not abort an HTTP response.
                log_event("warn", "HTTP access log console unavailable", {"accessLog": line, "error": repr(error)})

    def do_GET(self) -> None:
        try:
            request_path = urlparse(self.path).path
            if self._route_requires_loopback(request_path, is_post=False) and not self._is_loopback_client():
                self.json_error(403, "loopback_only", "This endpoint is only available on loopback")
                return

            if request_path in _CONTROL_ROUTES:
                self.json_error(405, "method_not_allowed", "Use POST for control endpoints")
                return

            if utility_routes.handle_get(self, self.path):
                return
            if request_path.startswith("/debug/vfx"):
                if vfx_debug_routes.handle_get(self, self.path):
                    return
            self.send_error(404)
        except Exception as e:
            if _is_client_disconnect(e):
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

            if self._route_requires_loopback(request_path, is_post=True) and not self._is_trusted_control_request():
                self.json_error(403, "untrusted_control_origin", "Local mutation requests require a local host and same origin")
                return

            if request_path not in {"/combine", *_CONTROL_ROUTES} and not request_path.startswith("/debug/vfx"):
                self.send_error(404)
                return

            length = self._content_length_bytes()
            payload = self._read_json_payload(length)

            if request_path in _CONTROL_ROUTES:
                utility_routes.handle_post(self, self.path, payload)
                return
            if request_path.startswith("/debug/vfx"):
                if vfx_debug_routes.handle_post(self, self.path, payload):
                    return
            if request_path == "/combine":
                combine_endpoint.handle_combine_request(
                    payload,
                    app_version=APP_VERSION,
                    combine_cache_lookup=combine_pipeline.combine_cache_lookup,
                    sanitize_recipe_for_delivery=sanitize_recipe_for_delivery,
                    combine=combine_pipeline.combine,
                    trace_event=trace_event,
                    json=self.json,
                    json_status=self.json_status,
                    clear_failure_state=generation_debug.clear_combine_failure,
                    cache_lookup_passthrough_errors=(WorldScopeMissing,),
                )
                return
            self.send_error(404)
        except WorldScopeMissing as e:
            if _is_client_disconnect(e):
                return
            log_event("warn", "craft failed: world scope missing", {"path": self.path, "error": str(e)})
            self.json_error(428, "world_id_required", str(e))
        except VisualDeliveryBlocked as e:
            if _is_client_disconnect(e):
                return
            self._json_combine_failure("visual delivery blocked", e)
        except PlannerUnavailable as e:
            if _is_client_disconnect(e):
                return
            self._json_combine_failure("structured combine failure", e)
        except OverflowError as e:
            if _is_client_disconnect(e):
                return
            self.json_error(413, "request_too_large", str(e))
        except TimeoutError as e:
            if _is_client_disconnect(e):
                return
            self.json_error(408, "request_timeout", str(e))
        except _InvalidJsonRequest as e:
            if _is_client_disconnect(e):
                return
            self.json_error(400, "invalid_json", str(e))
        except Exception as e:
            if _is_client_disconnect(e):
                log_event("debug", "client disconnected during POST response", {"path": self.path, "error": repr(e)})
                return
            log_event("error", "request failed", {"path": self.path, "error": repr(e), "trace": traceback.format_exc()})
            self.json_error(500, "internal_error", repr(e))

    def _is_trusted_control_request(self) -> bool:
        # Peer loopback alone cannot distinguish native clients from a hostile
        # web page. Reject rebinding Hosts and cross-origin browser requests.
        host = self.headers.get("Host", "")
        try:
            authority = urlparse("http://" + host)
            if (not _is_loopback_host(authority.hostname or "")
                    or authority.username is not None or authority.password is not None
                    or authority.path or authority.query or authority.fragment
                    or (authority.port or 80) != self.server.server_port):
                return False
        except ValueError:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + host:
            return False
        if self.headers.get("Sec-Fetch-Site", "") not in {"", "same-origin", "none"}:
            return False
        return True

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
        if self.headers.get("Transfer-Encoding") is not None:
            raise _InvalidJsonRequest("Transfer-Encoding is not supported")
        lengths = (self.headers.get_all("Content-Length", []) if hasattr(self.headers, "get_all")
                   else [self.headers["Content-Length"]] if "Content-Length" in self.headers else [])
        if len(lengths) > 1:
            raise _InvalidJsonRequest("multiple Content-Length headers")
        raw_length = lengths[0].strip() if lengths else "0"
        if not raw_length.isascii() or not raw_length.isdecimal():
            raise _InvalidJsonRequest("invalid Content-Length")
        try:
            length = int(raw_length)
        except (TypeError, ValueError) as e:
            raise _InvalidJsonRequest("invalid Content-Length") from e

        if length < 0:
            raise _InvalidJsonRequest("negative Content-Length")
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
            chunks: list[bytes] = []
            remaining = length
            while remaining:
                chunk = self.rfile.read(remaining)
                if not chunk:
                    raise _InvalidJsonRequest(
                        f"request body ended early: expected {length} bytes, received {length - remaining}"
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            body = b"".join(chunks)
        except socket.timeout as e:
            raise TimeoutError("request body read timeout") from e
        finally:
            if connection is not None and hasattr(connection, "settimeout"):
                connection.settimeout(previous_timeout)

        try:
            return strict_json.loads_object(body)
        except (UnicodeError, ValueError, TypeError) as e:
            raise _InvalidJsonRequest("invalid JSON body") from e

    def _json_combine_failure(self, reason: str, error: BaseException) -> None:
        attached = getattr(error, "_infini_failure_snapshot", None)
        failure = deepcopy(attached) if isinstance(attached, dict) else {}
        status, code, retryable, friendly = _combine_failure_http_response(error, failure)
        log_event("warn", f"craft failed: {reason}", {
            "path": self.path,
            "httpStatus": status,
            "errorCode": code,
            "error": str(error),
            "lastFailure": failure,
            "failureSnapshotError": getattr(error, "_infini_failure_snapshot_error", ""),
        })
        self.json_status(status, _combine_failure_payload(status, code, friendly, failure, retryable=retryable))

    def json(self, obj: Any) -> None:
        self.json_status(200, obj)

    def json_status(self, status: int, obj: Any) -> None:
        data = strict_json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            if _is_client_disconnect(e):
                log_event("debug", "client disconnected while writing JSON response", {"path": self.path, "status": status, "error": repr(e)})
                return
            raise

    def json_error(self, status: int, code: str, message: str = "") -> None:
        self.json_status(status, {"ok": False, "error": str(code or "error"), "message": str(message or ""), "version": APP_VERSION})

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        try:
            self.json_error(int(code), f"http_{int(code)}", message or explain or "")
        except Exception as e:
            if _is_client_disconnect(e):
                return
            super().send_error(code, _ascii_reason(message or explain or "error"), None)
