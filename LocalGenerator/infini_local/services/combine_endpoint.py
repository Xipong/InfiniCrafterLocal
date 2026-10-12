from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
import math
import threading
import time
import uuid
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

_GENERATION_STATE_LOCK = threading.RLock()
_GENERATION_ACTIVE = 0
_GENERATION_WAITING = 0
_GENERATION_ACCEPTING = True
_GENERATION_REQUESTS: dict[str, _GenerationAdmission] = {}
_GENERATION_MAX_ROWS = 32
_CURRENT_GENERATION: ContextVar["_GenerationAdmission | None"] = ContextVar("infini_generation_admission", default=None)
_GENERATION_WAIT_REASONS = frozenset({"none", "generation_slot", "profile_slot", "rate_queue", "provider_cooldown", "provider_quota", "token_window", "pacing", "retry_backoff"})
_GENERATION_STAGES = frozenset({
    "admission", "00_prepare", "00_llm_lease", "01_gameplay_author", "01_dev_only_low_level_fixture",
    "02_strict_runtime_program", "02_parent_power_context", "02_compile_runtime_program", "02_wire_boundary",
    "02r_conditional_gameplay_repair", "02r_strict_runtime_program", "02r_parent_power_context", "02r_compile_runtime_program", "02r_wire_boundary",
    "03_result_knowledge_card", "04_visual_technical_init", "05_visual_director", "06_vfx_director",
    "07_visual_asset_runtime_gates", "08_visual_asset_generation", "09_visual_delivery_gate",
    "10_generated_parent_summary", "11_final_normalize", "12_final_runtime_wire_gate", "13_stage_accounting",
})


def _elapsed_seconds(now: float, started: float) -> float:
    value = now - started
    return round(max(0.0, min(value, 10**9)), 3) if math.isfinite(value) else 0.0


def generation_activity_snapshot() -> dict[str, Any]:
    """Detached bounded live projection; no payload, prompt, world or credential identity."""
    with _GENERATION_STATE_LOCK:
        now = time.monotonic()
        rows = [{"requestId": row.request_id, "profileId": row.profile_id,
                 "stage": row.stage, "startedMonotonicSeconds": row.started,
                 "elapsedSeconds": _elapsed_seconds(now, row.started),
                 "stageElapsedSeconds": _elapsed_seconds(now, row.stage_started),
                 "waitReason": row.wait_reason, "networkStarted": row.network_started,
                 "active": row.active} for row in _GENERATION_REQUESTS.values()]
        return {"active": _GENERATION_ACTIVE, "waiting": _GENERATION_WAITING,
                "accepting": _GENERATION_ACCEPTING, "requests": rows,
                "requestsOmitted": max(0, _GENERATION_ACTIVE + _GENERATION_WAITING - len(rows))}


def update_generation_activity(*, profile_id: str | None = None, wait_reason: str | None = None,
                               network_started: bool | None = None) -> None:
    row = _CURRENT_GENERATION.get()
    if row is None:
        return
    with _GENERATION_STATE_LOCK:
        if profile_id is not None:
            row.profile_id = profile_id if profile_id in {"llm_1", "llm_2", "llm_3"} else None
        if wait_reason in _GENERATION_WAIT_REASONS:
            row.wait_reason = wait_reason
        row.network_started = network_started if type(network_started) is bool else None


@contextmanager
def generation_stage(stage: str | None):
    row = _CURRENT_GENERATION.get()
    if row is None:
        yield
        return
    with _GENERATION_STATE_LOCK:
        row.stage = stage if stage in _GENERATION_STAGES else None
        row.stage_started = time.monotonic()
        row.wait_reason, row.network_started = "none", None
    try:
        yield
    finally:
        with _GENERATION_STATE_LOCK:
            # Flat pipeline stages are observations, not progress estimates.
            # Between entered stages the current stage/network boundary is unknown.
            row.stage, row.stage_started = None, time.monotonic()
            row.wait_reason, row.network_started = "none", None


def request_shutdown(*, force: bool = False) -> tuple[bool, dict[str, Any]]:
    """Atomically close new admission, or refuse while admitted work exists."""
    global _GENERATION_ACCEPTING
    with _GENERATION_STATE_LOCK:
        if not force and (_GENERATION_ACTIVE or _GENERATION_WAITING):
            return False, generation_activity_snapshot()
        _GENERATION_ACCEPTING = False
        return True, generation_activity_snapshot()


class _GenerationAdmission:
    """Request-scoped counter ownership, including waits and exceptional exits."""

    def __init__(self, profile_id: str = "") -> None:
        self.admitted = False
        self.active = False
        self.request_id = uuid.uuid4().hex
        self.profile_id = profile_id if profile_id in {"llm_1", "llm_2", "llm_3"} else None
        self.started = self.stage_started = time.monotonic()
        self.stage: str | None = "admission"
        self.wait_reason = "none"
        self.network_started: bool | None = None
        self.token = None

    def __enter__(self) -> _GenerationAdmission:
        global _GENERATION_WAITING
        with _GENERATION_STATE_LOCK:
            self.admitted = _GENERATION_ACCEPTING
            if self.admitted:
                _GENERATION_WAITING += 1
                if len(_GENERATION_REQUESTS) < _GENERATION_MAX_ROWS:
                    _GENERATION_REQUESTS[self.request_id] = self
                self.token = _CURRENT_GENERATION.set(self)
        return self

    def activate(self) -> bool:
        global _GENERATION_WAITING, _GENERATION_ACTIVE
        with _GENERATION_STATE_LOCK:
            if not _GENERATION_ACCEPTING:
                return False
            _GENERATION_WAITING -= 1
            _GENERATION_ACTIVE += 1
            self.active = True
            self.stage, self.stage_started = "00_prepare", time.monotonic()
            self.wait_reason = "none"
            return True

    def __exit__(self, *_exc: Any) -> None:
        global _GENERATION_WAITING, _GENERATION_ACTIVE
        with _GENERATION_STATE_LOCK:
            if self.admitted:
                if self.active:
                    _GENERATION_ACTIVE -= 1
                else:
                    _GENERATION_WAITING -= 1
                _GENERATION_REQUESTS.pop(self.request_id, None)
        if self.token is not None:
            _CURRENT_GENERATION.reset(self.token)


def _shutdown_refusal(json_status: JsonStatusSender, app_version: str) -> None:
    json_status(503, {
        "ok": False, "status": "generator_shutting_down", "error": "generator_shutting_down",
        "message": "Generator is shutting down; no new generation was started.",
        "version": app_version, "httpStatus": 503, "retryable": True,
        "cacheRecoveryAllowed": True, "generationActivity": generation_activity_snapshot(),
    })


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
        # An unavailable authoritative cache is not a miss. Never start a new
        # generation that could replace bytes we could not assess.
        if cache_only or isinstance(cache_error, OSError):
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
    with _GenerationAdmission(str(payload.get("llmProfileId") or "") if payload.get("multiDevCraft") else "") as admission, ExitStack() as permits:
        if not admission.admitted:
            _shutdown_refusal(json_status, app_version)
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
                update_generation_activity(wait_reason="profile_slot")
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
            permits.callback(profile_semaphore.release)
        update_generation_activity(wait_reason="generation_slot")
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
        permits.callback(semaphore.release)
        try:
            if not admission.activate():
                _shutdown_refusal(json_status, app_version)
                return
            data = combine(payload)
        except Exception as error:
            attached = getattr(error, "_infini_failure_snapshot", None)
            snapshot: dict[str, Any] = deepcopy(attached) if isinstance(attached, dict) else {}
            # The process-wide latest failure may belong to a concurrent sibling.
            # Only the canonical recorder's exception-owned snapshot identifies us.
            try:
                setattr(error, "_infini_failure_snapshot", snapshot)
            except Exception:
                pass
            raise
        permits.close()
        if _response_json_error(
            data,
            source="fresh",
            app_version=app_version,
            trace_event=trace_event,
            json_status=json_status,
        ):
            return
        json(data)
