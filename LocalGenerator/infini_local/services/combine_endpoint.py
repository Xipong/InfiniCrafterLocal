from __future__ import annotations

from copy import deepcopy
import threading
from typing import Any, Callable

from infini_local.core import strict_json
from infini_local.core.env_utils import env_int


# AGENT MAP: service wrapper for /combine request/response behavior.
# Keep endpoint glue thin: validate/shape requests, call the combine pipeline, return
# deliverable data or honest failure. Do not bury gameplay authoring in HTTP glue.
# Generation is intentionally serialized by default. /combine runs LLM + image + VFX
# work synchronously today; unbounded ThreadingHTTPServer requests can otherwise pile up
# and freeze the local service. Set INFINI_COMBINE_CONCURRENCY>1 only for a real worker queue.
COMBINE_CONCURRENCY = env_int("INFINI_COMBINE_CONCURRENCY", 1, lo=1, hi=8)
COMBINE_SEMAPHORE = threading.BoundedSemaphore(COMBINE_CONCURRENCY)
MULTIDEV_CONCURRENCY = env_int("INFINI_MULTIDEV_CONCURRENCY", 3, lo=2, hi=3)
MULTIDEV_SEMAPHORE = threading.BoundedSemaphore(MULTIDEV_CONCURRENCY)
MULTIDEV_PROFILE_SEMAPHORES = {
    profile_id: threading.BoundedSemaphore(1)
    for profile_id in ("llm_1", "llm_2", "llm_3")
}
COMBINE_BUSY_WAIT_SECONDS = env_int("INFINI_COMBINE_BUSY_WAIT_SECONDS", 0, lo=0, hi=600)

JsonSender = Callable[[Any], None]
JsonStatusSender = Callable[[int, Any], None]
TraceEvent = Callable[[str, str, str, Any], None]


def _response_json_error(
    value: Any,
    *,
    source: str,
    app_version: str,
    trace_event: TraceEvent,
    json_status: JsonStatusSender,
) -> bool:
    try:
        if not isinstance(value, dict):
            raise TypeError(f"combine response root must be object, got {type(value).__name__}")
        strict_json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return False
    except (TypeError, ValueError, OverflowError) as serialization_error:
        trace_event(
            "error",
            "HTTP:/combine",
            "combine returned invalid strict JSON payload",
            {"source": source, "error": repr(serialization_error)},
        )
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
        return True


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
    last_failure_summary: Callable[[], dict[str, Any]] | None = None,
    clear_failure_state: Callable[[str], None] | None = None,
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
        trace_event("warn", "HTTP:/combine", "world recipe cache lookup failed; continuing with fresh generation", {
            "error": repr(cache_error),
            "cacheRecoveryAllowed": True,
        })
        cached = None
        cache_key = ""
    if cached:
        trace_event("step", "HTTP:/combine", "world recipe cache hit before generation lock", {"recipeKey": cache_key, "cacheOnly": cache_only})
        cached_delivery = sanitize_recipe_for_delivery(cached)
        if _response_json_error(
            cached_delivery,
            source="cache",
            app_version=app_version,
            trace_event=trace_event,
            json_status=json_status,
        ):
            return
        if clear_failure_state is not None:
            try:
                clear_failure_state("endpoint_cache_hit_delivered")
            except Exception as diagnostic_error:
                trace_event("warn", "HTTP:/combine", "could not clear stale failure diagnostics after cache hit", {"error": repr(diagnostic_error), "recipeKey": cache_key})
        json(cached_delivery)
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
    multi_dev = bool(payload.get("multiDevCraft"))
    semaphore = MULTIDEV_SEMAPHORE if multi_dev else COMBINE_SEMAPHORE
    concurrency = MULTIDEV_CONCURRENCY if multi_dev else COMBINE_CONCURRENCY
    profile_id = str(payload.get("llmProfileId") or "").strip().lower() if multi_dev else ""
    profile_semaphore = MULTIDEV_PROFILE_SEMAPHORES.get(profile_id) if multi_dev else None
    profile_acquired = False
    if multi_dev:
        if profile_semaphore is None:
            json_status(422, {
                "ok": False,
                "status": "invalid_multidev_profile",
                "error": "invalid_multidev_profile",
                "message": "Multi-dev craft requires exact llmProfileId llm_1, llm_2, or llm_3.",
                "playerMessage": "Multi-dev LLM profile is invalid. Items were returned.",
                "version": app_version,
                "httpStatus": 422,
                "retryable": False,
                "cacheRecoveryAllowed": False,
                "multiDevCraft": True,
            })
            return
        profile_acquired = profile_semaphore.acquire(blocking=False)
        if not profile_acquired and COMBINE_BUSY_WAIT_SECONDS > 0:
            profile_acquired = profile_semaphore.acquire(timeout=COMBINE_BUSY_WAIT_SECONDS)
        if not profile_acquired:
            json_status(409, {
                "ok": False,
                "status": "multidev_profile_busy",
                "error": "multidev_profile_busy",
                "message": f"Multi-dev profile {profile_id} is already generating an item.",
                "playerMessage": f"{profile_id} is already busy. Items were returned; use another lane or retry.",
                "version": app_version,
                "httpStatus": 409,
                "retryable": True,
                "cacheRecoveryAllowed": False,
                "combineConcurrency": concurrency,
                "multiDevCraft": True,
                "llmProfileId": profile_id,
                "busyWaitSeconds": COMBINE_BUSY_WAIT_SECONDS,
            })
            return
    acquired = semaphore.acquire(blocking=False)
    if not acquired and COMBINE_BUSY_WAIT_SECONDS > 0:
        trace_event("step", "HTTP:/combine", "generator busy; waiting for active craft/cache", {
            "busyWaitSeconds": COMBINE_BUSY_WAIT_SECONDS,
            "combineConcurrency": concurrency,
            "multiDevCraft": multi_dev,
            "combineBusyWaitSeconds": COMBINE_BUSY_WAIT_SECONDS,
        })
        acquired = semaphore.acquire(timeout=COMBINE_BUSY_WAIT_SECONDS)
    if not acquired:
        if profile_acquired and profile_semaphore is not None:
            profile_semaphore.release()
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
            "combineConcurrency": concurrency,
            "multiDevCraft": multi_dev,
            "busyWaitSeconds": COMBINE_BUSY_WAIT_SECONDS,
        })
        return
    try:
        data = combine(payload)
    except Exception as error:
        snapshot_error = ""
        attached = getattr(error, "_infini_failure_snapshot", None)
        snapshot: dict[str, Any] = deepcopy(attached) if isinstance(attached, dict) else {}
        if not snapshot and last_failure_summary is not None:
            try:
                candidate = last_failure_summary()
                if isinstance(candidate, dict):
                    snapshot = deepcopy(candidate)
            except Exception as diagnostic_error:
                snapshot_error = repr(diagnostic_error)
        try:
            setattr(error, "_infini_failure_snapshot", snapshot)
            if snapshot_error:
                setattr(error, "_infini_failure_snapshot_error", snapshot_error)
        except Exception:
            pass
        raise
    finally:
        semaphore.release()
        if profile_acquired and profile_semaphore is not None:
            profile_semaphore.release()
    if _response_json_error(
        data,
        source="fresh",
        app_version=app_version,
        trace_event=trace_event,
        json_status=json_status,
    ):
        return
    json(data)
