from __future__ import annotations

import json
import time
import traceback
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable


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
                if utility_routes().handle_get(self, self.path):
                    return
                if self.path.startswith("/debug/vfx"):
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
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body or "{}")
                if self.path.startswith("/debug/vfx"):
                    if vfx_debug_routes().handle_post(self, self.path, payload):
                        return
                if self.path.startswith("/combine"):
                    combine_endpoint.handle_combine_request(
                        payload,
                        app_version=app_version,
                        combine_cache_lookup=combine_cache_lookup,
                        sanitize_recipe_for_delivery=sanitize_recipe_for_delivery,
                        combine=combine,
                        trace_event=trace_event,
                        json=self.json,
                        json_status=self.json_status,
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
            except Exception as e:
                if is_client_disconnect(e):
                    log_event("debug", "client disconnected during POST response", {"path": self.path, "error": repr(e)})
                    return
                log_event("error", "request failed", {"path": self.path, "error": repr(e), "trace": traceback.format_exc()})
                self.json_error(500, "internal_error", repr(e))

        def _json_combine_failure(self, reason: str, error: BaseException) -> None:
            failure = last_combine_failure_summary()
            status, code, retryable, friendly = combine_failure_http_response(error, failure)
            log_event("warn", f"craft failed: {reason}", {
                "path": self.path,
                "httpStatus": status,
                "errorCode": code,
                "error": str(error),
                "lastFailure": failure,
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


__all__ = ["build_handler"]
