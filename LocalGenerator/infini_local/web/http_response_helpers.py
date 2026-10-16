from __future__ import annotations

from typing import Any

from infini_local.core.config_bootstrap import APP_VERSION


# AGENT MAP: low-level HTTP/JSON response helpers shared by server route glue.
# Keep route decisions and transport semantics here; do not add generation logic.


def _is_client_disconnect(exc: BaseException) -> bool:
    """Client closed the HTTP socket while we were writing a response.

    Common during GUI health checks/browser refreshes. It is not a generator crash.
    Windows often reports this as WinError 10053/10054.
    """
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) in {10053, 10054}:
        return True
    return False


def _ascii_reason(value: Any, limit: int = 160) -> str:
    # HTTP status reason is latin-1 in BaseHTTPRequestHandler. Never pass repr(e)
    # with localized OS text there; send JSON body instead.
    text = str(value or "error").replace("\r", " ").replace("\n", " ").strip()
    text = text.encode("ascii", "backslashreplace").decode("ascii")
    return text[:limit] or "error"


def _combine_failure_http_response(error: BaseException | str, failure: dict[str, Any]) -> tuple[int, str, bool, str]:
    """Classify a failed /combine into transport-visible HTTP semantics.

    404 is reserved for cache-only misses. Provider request-schema rejections
    are non-retryable 424, not authored-output failures. Authored/LLM output
    failures are 422, visual delivery dependency failures are 424, and generic
    planner availability remains 424; logical/admission deadlines are 504.
    `retryable` means the user may manually craft again; it does not mean C# should cache-poll the same failed attempt.
    """
    from infini_local.storage.failure_state import _transport_debug, summarize_failure
    transport = summarize_failure(failure or {}).get("transportDebug") or _transport_debug(error)
    category = transport.get("failureCategory") if isinstance(transport, dict) else None
    actions = {
        "auth_failed": (424, "llm_auth_failed", False, "LLM authentication or permission failed; check credentials and access before retrying"),
        "model_unavailable": (424, "llm_model_unavailable", False, "Configured LLM model is unavailable; select an accessible model before retrying"),
        "profile_unavailable": (424, "llm_profile_unavailable", False, "Selected LLM profile is disabled or unavailable; enable it or select another lane"),
        "endpoint_unavailable": (424, "llm_endpoint_unavailable", False, "LLM endpoint was not found; check the configured provider URL and API mode"),
        "quota_exhausted": (424, "llm_quota_exhausted", False, "LLM quota is exhausted; check billing or quota before retrying"),
        "rate_limited": (424, "llm_rate_limited", True, "LLM provider rate limited generation; wait before retrying"),
        "admission_timeout": (504, "llm_admission_timeout", True, "Local LLM admission wait exhausted the logical-call deadline; no request was sent for this attempt; wait before retrying"),
        "logical_timeout": (504, "llm_timeout", True, "LLM logical-call deadline was exhausted; this does not establish a provider outage"),
        "transport_unavailable": (424, "llm_transport_unavailable", True, "LLM transport was unavailable; check connectivity before retrying"),
        "request_rejected": (424, "llm_request_rejected", False, "LLM provider rejected the outgoing request; check provider settings or update the generator before retrying"),
    }
    if category in actions:
        return actions[category]
    stage = str((failure or {}).get("stage") or "").lower()
    failure_error = str((failure or {}).get("error") or "")
    message = f"{error} {failure_error}".lower()

    # This provider diagnostic rejects our outgoing schema before any authored
    # output or Repair. Check it before generic "schema"/"json" output heuristics.
    if "http 400:" in message and "invalid schema for response_format" in message:
        return 424, "llm_request_rejected", False, "LLM provider rejected the request schema before generation; update the generator before retrying"

    if stage == "09_visual_delivery_gate" or ("visual" in stage and any(token in message for token in ("asset", "sprite", "delivery"))):
        return 424, "visual_dependency_failed", True, "visual asset generation/delivery did not produce a deliverable item sprite"

    schema_stage = any(token in stage for token in ("schema", "validate", "repair"))
    llm_shape_error = any(token in message for token in (
        "invalid runtime",
        "schema",
        "validation",
        "json",
    ))
    if schema_stage or llm_shape_error:
        return 422, "llm_output_invalid", True, "LLM returned invalid or unsupported authored output"

    if stage == "01_gameplay_author" or "planner unavailable" in message:
        return 424, "planner_unavailable", True, "LLM planner did not return a usable item plan"

    return 424, "combine_failed", True, "combine pipeline failed before a deliverable recipe was committed"


def _combine_failure_player_message(status: int, code: str, message: str, failure: dict[str, Any], *, retryable: bool) -> str:
    # Generation facts only. The native player/world owner alone observes refunds.
    if code in {"llm_auth_failed", "llm_model_unavailable", "llm_profile_unavailable", "llm_endpoint_unavailable", "llm_quota_exhausted", "llm_rate_limited", "llm_admission_timeout", "llm_timeout", "llm_transport_unavailable", "llm_request_rejected"}:
        return "Generation failed: " + message.rstrip(".") + "."
    if code == "llm_output_invalid":
        return "Generation failed: LLM authored output was invalid. Try crafting again."
    if code == "visual_dependency_failed":
        return "Generation failed: required visual asset was not deliverable. Try again."
    if code == "planner_unavailable":
        return "Generation failed: LLM planner did not return a usable item. Try again."
    if code == "generator_busy":
        return "Generator is busy. Try again shortly."
    if status == 428:
        return "Generation failed: world id was missing."
    if retryable:
        return "Generation failed before a recipe was committed. Try crafting again."
    return "Generation failed."


def _combine_failure_payload(status: int, code: str, message: str, failure: dict[str, Any], *, retryable: bool) -> dict[str, Any]:
    player_message = _combine_failure_player_message(status, code, message, failure, retryable=retryable)
    return {
        "ok": False,
        "status": code,
        "error": code,
        "message": str(message or code),
        "playerMessage": player_message,
        "developerHint": "No recipe was committed; do not cache-poll this attempt. Manual regenerate is allowed when retryable=true.",
        "version": APP_VERSION,
        "httpStatus": int(status),
        "retryable": bool(retryable),
        "cacheRecoveryAllowed": False,
        "manualRegenerateAllowed": bool(retryable),
        "lastFailure": failure or {},
    }


__all__ = [
    "_is_client_disconnect",
    "_ascii_reason",
    "_combine_failure_http_response",
    "_combine_failure_payload",
]
