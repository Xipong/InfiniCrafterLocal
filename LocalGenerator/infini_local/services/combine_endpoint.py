from __future__ import annotations

import json as json_module
import threading
from typing import Any, Callable

from infini_local.core.env_utils import env_int


# AGENT MAP: service wrapper for /combine request/response behavior.
# Keep endpoint glue thin: validate/shape requests, call the combine pipeline, return
# deliverable data or honest failure. Do not bury gameplay authoring in HTTP glue.
# Generation is intentionally serialized by default. /combine runs LLM + image + VFX
# work synchronously today; unbounded ThreadingHTTPServer requests can otherwise pile up
# and freeze the local service. Set INFINI_COMBINE_CONCURRENCY>1 only for a real worker queue.
COMBINE_CONCURRENCY = env_int("INFINI_COMBINE_CONCURRENCY", 1, lo=1, hi=8)
COMBINE_SEMAPHORE = threading.BoundedSemaphore(COMBINE_CONCURRENCY)
COMBINE_BUSY_WAIT_SECONDS = env_int("INFINI_COMBINE_BUSY_WAIT_SECONDS", 0, lo=0, hi=600)

JsonSender = Callable[[Any], None]
JsonStatusSender = Callable[[int, Any], None]
TraceEvent = Callable[[str, str, str, Any], None]


def handle_combine_request(
    payload: dict[str, Any],
    *,
    app_version: str,
    combine_cache_lookup: Callable[[dict[str, Any]], tuple[str, dict[str, Any] | None]],
    sanitize_recipe_for_delivery: Callable[[Any], Any],
    combine: Callable[[dict[str, Any]], dict[str, Any]],
    trace_event: TraceEvent,
    json: JsonSender,
    json_status: JsonStatusSender,
    cache_lookup_passthrough_errors: tuple[type[BaseException], ...] = (),
) -> None:
    """HTTP-facing /combine orchestration.

    The heavy authored-item pipeline still lives behind `combine(...)`. This module owns
    only endpoint concerns: cache-only behavior, world-cache precheck, and generation
    concurrency throttling.
    """
    cache_only = bool(payload.get("cacheOnly") or payload.get("cacheOnlyIfReady"))
    try:
        cache_key, cached = combine_cache_lookup(payload)
    except Exception as cache_error:
        if cache_lookup_passthrough_errors and isinstance(cache_error, cache_lookup_passthrough_errors):
            raise
        if cache_only:
            json_status(500, {
                "ok": False,
                "status": "cache_lookup_failed",
                "error": "cache_lookup_failed",
                "message": repr(cache_error),
                "playerMessage": "Cache lookup failed. Items were returned; try crafting again.",
                "version": app_version,
                "httpStatus": 500,
                "retryable": True,
                "cacheRecoveryAllowed": False,
            })
            return
        cached = None
        cache_key = ""
    if cached:
        trace_event("step", "HTTP:/combine", "world recipe cache hit before generation lock", {"recipeKey": cache_key, "cacheOnly": cache_only})
        json(sanitize_recipe_for_delivery(cached))
        return
    if cache_only:
        json_status(404, {
            "ok": False,
            "status": "cache_miss",
            "error": "cache_miss",
            "message": "world recipe cache has no completed result for this pair",
            "playerMessage": "No completed cached recipe exists for this pair yet.",
            "version": app_version,
            "httpStatus": 404,
            "retryable": True,
            "cacheRecoveryAllowed": True,
            "recipeKey": cache_key,
        })
        return
    acquired = COMBINE_SEMAPHORE.acquire(blocking=False)
    if not acquired and COMBINE_BUSY_WAIT_SECONDS > 0:
        trace_event("step", "HTTP:/combine", "generator busy; waiting for active craft/cache", {
            "busyWaitSeconds": COMBINE_BUSY_WAIT_SECONDS,
            "combineConcurrency": COMBINE_CONCURRENCY,
            "combineBusyWaitSeconds": COMBINE_BUSY_WAIT_SECONDS,
        })
        acquired = COMBINE_SEMAPHORE.acquire(timeout=COMBINE_BUSY_WAIT_SECONDS)
    if not acquired:
        json_status(409, {
            "ok": False,
            "status": "generator_busy",
            "error": "generator_busy",
            "message": "LocalGenerator is already generating an item; retry shortly.",
            "playerMessage": "Generator is busy. Items were returned; try again shortly.",
            "version": app_version,
            "httpStatus": 409,
            "retryable": True,
            "cacheRecoveryAllowed": False,
            "combineConcurrency": COMBINE_CONCURRENCY,
            "busyWaitSeconds": COMBINE_BUSY_WAIT_SECONDS,
        })
        return
    try:
        data = combine(payload)
    finally:
        COMBINE_SEMAPHORE.release()
    try:
        json_module.dumps(data, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as serialization_error:
        trace_event("error", "HTTP:/combine", "combine returned non-JSON-serializable payload", {"error": repr(serialization_error)})
        json_status(500, {
            "ok": False,
            "status": "combine_response_not_json_serializable",
            "error": "combine_response_not_json_serializable",
            "message": repr(serialization_error),
            "playerMessage": "Generator produced an internal response that cannot be sent to Terraria. Items were returned; check LocalGenerator logs.",
            "version": app_version,
            "httpStatus": 500,
            "retryable": True,
            "cacheRecoveryAllowed": False,
        })
        return
    json(data)
