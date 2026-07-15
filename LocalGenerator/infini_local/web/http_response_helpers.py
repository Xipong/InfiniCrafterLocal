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

    404 is reserved for cache-only misses. Authored/LLM output failures are
    422, visual delivery dependency failures are 424, and generic planner
    availability remains 424. `retryable` means the user may manually craft
    again; it does not mean C# should cache-poll the same failed attempt.
    """
    stage = str((failure or {}).get("stage") or "").lower()
    failure_error = str((failure or {}).get("error") or "")
    message = f"{error} {failure_error}".lower()

    if "09b_visual_delivery_gate" in stage or ("visual" in stage and any(token in message for token in ("asset", "sprite", "delivery"))):
        return 424, "visual_dependency_failed", True, "visual asset generation/delivery did not produce a deliverable item sprite"

    schema_stage = any(token in stage for token in ("schema", "validate", "repair"))
    llm_shape_error = any(token in message for token in (
        "runtimeplan failed",
        "engine-call validation",
        "lacks set_item_stats",
        "invalid runtime",
        "unsupported gameplay promises",
        "schema",
        "validation",
        "json",
    ))
    if schema_stage or llm_shape_error:
        return 422, "llm_output_invalid", True, "LLM returned an invalid/unsupported item plan after repair attempts"

    if "01_author_llm_plan" in stage or "planner unavailable" in message or "llm planner unavailable" in message:
        return 424, "planner_unavailable", True, "LLM planner did not return a usable item plan"

    return 424, "combine_failed", True, "combine pipeline failed before a deliverable recipe was committed"


def _combine_failure_player_message(status: int, code: str, message: str, failure: dict[str, Any], *, retryable: bool) -> str:
    if code == "llm_output_invalid":
        return "Generation failed: LLM item plan was invalid after repair. Items were returned; try crafting again."
    if code == "visual_dependency_failed":
        return "Generation failed: required visual asset was not deliverable. Items were returned; try again."
    if code == "planner_unavailable":
        return "Generation failed: LLM planner did not return a usable item. Items were returned; try again."
    if code == "generator_busy":
        return "Generator is busy. Items were returned; try again shortly."
    if status == 428:
        return "Generation failed: world id was missing. Items were returned."
    if retryable:
        return "Generation failed before a recipe was committed. Items were returned; try crafting again."
    return "Generation failed. Items were returned."


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
