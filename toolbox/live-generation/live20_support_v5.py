from __future__ import annotations

from collections.abc import Callable, Generator, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
import time
from typing import Any, TypeVar, cast

from infini_local.qa.live_no_image_fixture import (
    hydrate_no_image_fixture_assets,
    write_no_image_fixture_png,
)

INITIAL_AUTHOR = "initial_author"
SCOPED_REPAIR = "scoped_repair"
VISUAL_DIRECTOR = "visual_director"
VISUAL_REPAIR = "visual_repair"
VFX_DIRECTOR = "vfx_director"
VFX_REPAIR = "vfx_repair"
NON_AUTHOR = "non_author"
FROZEN_LLM_STAGES = (
    INITIAL_AUTHOR,
    SCOPED_REPAIR,
    VISUAL_DIRECTOR,
    VISUAL_REPAIR,
    VFX_DIRECTOR,
    VFX_REPAIR,
)
REPAIR_LLM_STAGES = frozenset((SCOPED_REPAIR, VISUAL_REPAIR, VFX_REPAIR))

_INITIAL_WIRE_STAGE = "planner"
_REPAIR_WIRE_STAGE = "author_repair"
_STAGE_KEY = "_infini_stage"


def select_case_routes(
    routes: Iterable[tuple[str, str, str]], selected_ids: set[str],
) -> list[tuple[str, str, str]]:
    """Filter before resolving parent dumps; unused campaign extras are irrelevant."""
    rows = list(routes)
    unknown = selected_ids - {row[0] for row in rows}
    if unknown:
        raise ValueError(f"unknown case IDs: {', '.join(sorted(unknown))}")
    return [row for row in rows if not selected_ids or row[0] in selected_ids]



def expected_stage_max_tokens(
    stage: str,
    *,
    author_tokens: int | None,
    visual_tokens: int | None,
    vfx_tokens: int | None,
) -> int | None:
    if stage in {VISUAL_DIRECTOR, VISUAL_REPAIR}:
        return visual_tokens if visual_tokens is not None else author_tokens
    if stage in {VFX_DIRECTOR, VFX_REPAIR}:
        return vfx_tokens if vfx_tokens is not None else author_tokens
    return author_tokens


@dataclass
class CaseStageAccounting:
    case_id: str
    case_index: int
    logical_requests: int = 0
    initial_author_calls: int = 0
    scoped_repair_calls: int = 0
    last_logical_sequence: int = 0
    last_logical_error_sequence: int = 0
    last_logical_error_transport: bool = False
    case_transport_retries: int = 0

    def begin_logical(self, stage: str) -> int:
        self.logical_requests += 1
        self.last_logical_sequence = self.logical_requests
        self.last_logical_error_sequence = 0
        self.last_logical_error_transport = False
        if stage == INITIAL_AUTHOR:
            self.initial_author_calls += 1
        elif stage == SCOPED_REPAIR:
            self.scoped_repair_calls += 1
        return self.last_logical_sequence

    def mark_logical_error(self, sequence: int, *, transport: bool) -> None:
        self.last_logical_error_sequence = sequence
        self.last_logical_error_transport = bool(transport)

    def snapshot(self) -> dict[str, int]:
        return {
            "logicalRequests": self.logical_requests,
            "initialAuthorCalls": self.initial_author_calls,
            "scopedRepairCalls": self.scoped_repair_calls,
        }

    def delta_since(self, before: dict[str, int]) -> dict[str, int]:
        now = self.snapshot()
        return {
            key: int(now[key]) - int(before.get(key, 0))
            for key in ("logicalRequests", "initialAuthorCalls", "scopedRepairCalls")
        }


@dataclass
class GlobalStageAccounting:
    logical_requests: int = 0
    author_attempts: int = 0
    initial_author_calls: int = 0
    scoped_repair_calls: int = 0
    http_requests: int = 0
    active_crafts: int = 0
    active_logical: int = 0
    active_http: int = 0
    peak_active_crafts: int = 0
    peak_active_logical: int = 0
    peak_active_http: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _concurrency_snapshot_unlocked(self) -> dict[str, int]:
        return {
            "activeCrafts": self.active_crafts,
            "activeLogical": self.active_logical,
            "activeHttp": self.active_http,
            "peakActiveCrafts": self.peak_active_crafts,
            "peakActiveLogical": self.peak_active_logical,
            "peakActiveHttp": self.peak_active_http,
        }

    def begin_craft(self) -> dict[str, int]:
        with self._lock:
            self.active_crafts += 1
            self.peak_active_crafts = max(self.peak_active_crafts, self.active_crafts)
            return self._concurrency_snapshot_unlocked()

    def end_craft(self) -> dict[str, int]:
        with self._lock:
            if self.active_crafts <= 0:
                raise RuntimeError("craft concurrency counter underflow")
            self.active_crafts -= 1
            return self._concurrency_snapshot_unlocked()

    def begin_http(self) -> dict[str, int]:
        with self._lock:
            self.http_requests += 1
            self.active_http += 1
            self.peak_active_http = max(self.peak_active_http, self.active_http)
            return {"sequence": self.http_requests, **self._concurrency_snapshot_unlocked()}

    def end_http(self) -> dict[str, int]:
        with self._lock:
            if self.active_http <= 0:
                raise RuntimeError("HTTP concurrency counter underflow")
            self.active_http -= 1
            return self._concurrency_snapshot_unlocked()

    def next_http(self) -> int:
        with self._lock:
            self.http_requests += 1
            return self.http_requests

    def begin_logical(self, stage: str) -> dict[str, int | None]:
        with self._lock:
            self.logical_requests += 1
            self.active_logical += 1
            self.peak_active_logical = max(self.peak_active_logical, self.active_logical)
            author_sequence: int | None = None
            initial_sequence: int | None = None
            repair_sequence: int | None = None
            if stage == INITIAL_AUTHOR:
                self.initial_author_calls += 1
                self.author_attempts += 1
                author_sequence = self.author_attempts
                initial_sequence = self.initial_author_calls
            elif stage == SCOPED_REPAIR:
                self.scoped_repair_calls += 1
                self.author_attempts += 1
                author_sequence = self.author_attempts
                repair_sequence = self.scoped_repair_calls
            return {
                "sequence": self.logical_requests,
                "authorSequence": author_sequence,
                "initialAuthorSequence": initial_sequence,
                "scopedRepairSequence": repair_sequence,
                **self._concurrency_snapshot_unlocked(),
            }

    def end_logical(self) -> dict[str, int]:
        with self._lock:
            if self.active_logical <= 0:
                raise RuntimeError("logical concurrency counter underflow")
            self.active_logical -= 1
            return self._concurrency_snapshot_unlocked()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "logicalRequests": self.logical_requests,
                "authorAttempts": self.author_attempts,
                "initialAuthorCalls": self.initial_author_calls,
                "scopedRepairCalls": self.scoped_repair_calls,
                "httpRequests": self.http_requests,
                **self._concurrency_snapshot_unlocked(),
            }


_CURRENT_CASE_ACCOUNTING: ContextVar[CaseStageAccounting | None] = ContextVar(
    "infini_live_case_accounting_v5",
    default=None,
)


@contextmanager
def case_accounting_scope(case_id: str, case_index: int) -> Generator[CaseStageAccounting]:
    state = CaseStageAccounting(case_id=case_id, case_index=case_index)
    token = _CURRENT_CASE_ACCOUNTING.set(state)
    try:
        yield state
    finally:
        _CURRENT_CASE_ACCOUNTING.reset(token)


def current_case_accounting() -> CaseStageAccounting | None:
    return _CURRENT_CASE_ACCOUNTING.get()


def author_stage(payload: dict[str, Any]) -> str:
    """Classify every live LLM call from source-owned finite stage metadata."""
    if not isinstance(cast(object, payload), dict):
        return NON_AUTHOR
    stage = str(payload.get(_STAGE_KEY) or "").strip()
    if stage == _INITIAL_WIRE_STAGE:
        return INITIAL_AUTHOR
    if stage == _REPAIR_WIRE_STAGE:
        return SCOPED_REPAIR
    messages = payload.get("messages")
    names = {
        str(message.get("name") or "")
        for message in messages or []
        if isinstance(message, dict)
    }
    for message_name, classified in (
        ("visual_repair_contract", VISUAL_REPAIR),
        ("visual_director_contract", VISUAL_DIRECTOR),
        ("vfx_repair_contract", VFX_REPAIR),
        ("vfx_director_contract", VFX_DIRECTOR),
    ):
        if message_name in names:
            return classified
    return NON_AUTHOR


def is_first_author_success(*, initial_calls: int, repair_calls: int) -> bool:
    return initial_calls == 1 and repair_calls == 0


def expected_stage_temperature(
    stage: str,
    *,
    director_temperature: float | None,
    repair_temperature: float | None,
    vfx_director_temperature: float | None = None,
) -> float | None:
    if stage not in FROZEN_LLM_STAGES:
        raise ValueError(f"unclassified LLM stage {stage!r}")
    if stage in REPAIR_LLM_STAGES and repair_temperature is not None:
        return repair_temperature
    if stage == VFX_DIRECTOR and vfx_director_temperature is not None:
        return vfx_director_temperature
    return director_temperature


def response_format_type(payload: dict[str, Any]) -> str:
    value = payload.get("response_format")
    if isinstance(value, dict):
        return str(value.get("type") or "").strip()
    return str(value or "").strip()


def valid_author_call_budget(*, initial_calls: int, repair_calls: int) -> bool:
    return initial_calls == 1 and 0 <= repair_calls <= 1


def should_retry_case_failure(*, had_logical_error: bool, low_level_transport_error: bool) -> bool:
    return had_logical_error and low_level_transport_error


def pace_case_transport_retry(
    delay_seconds: int, *,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], float] = time.monotonic,
) -> float:
    """Wait at least a minute between a failed transport and the next case attempt."""
    if delay_seconds < 60:
        raise ValueError("case transport retry delay must be at least 60 seconds")
    started = now_fn()
    for _ in range(16):
        remaining = delay_seconds - (now_fn() - started)
        if remaining <= 0:
            return now_fn() - started
        sleep_fn(remaining)
    raise RuntimeError("retry wait did not advance the monotonic clock")


def case_transport_retry_report(
    logical_rows: list[dict[str, Any]], harness_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconcile each visible transport error with one paced, explicit case retry."""
    def key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
        return row.get("case"), row.get("caseIndex"), row.get("caseLogicalSequence")

    def attempt_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
        return row.get("case"), row.get("caseIndex"), row.get("attempt")

    scheduled = [row for row in harness_rows if row.get("event") == "CASE_RETRY_SCHEDULED"]
    completed = [row for row in harness_rows if row.get("event") == "CASE_RETRY_WAIT_COMPLETE"]
    starts = [row for row in harness_rows if row.get("event") == "CASE_ATTEMPT_START"]
    ends = [row for row in harness_rows if row.get("event") == "CASE_ATTEMPT_END"]
    scheduled_keys = {key(row) for row in scheduled}
    completed_by_attempt = {attempt_key(row): row for row in completed}
    errors = [row for row in logical_rows if row.get("phase") == "error" and row.get("transportError")]
    unaccounted = [{
        "sequence": row.get("sequence"), "case": row.get("case"),
        "caseIndex": row.get("caseIndex"), "caseLogicalSequence": row.get("caseLogicalSequence"),
    } for row in errors if key(row) not in scheduled_keys]
    start_keys = [attempt_key(row) for row in starts]
    end_keys = [attempt_key(row) for row in ends]
    wait_ok = (
        len(scheduled) == len(scheduled_keys) == len(completed) == len(completed_by_attempt)
        and all(
            attempt_key(row) in completed_by_attempt
            and key(completed_by_attempt[attempt_key(row)]) == key(row)
            and float(row.get("waitSeconds") or 0) >= 60
            and float(completed_by_attempt[attempt_key(row)].get("elapsedSeconds") or 0)
                >= float(row.get("waitSeconds") or 0)
            for row in scheduled
        )
    )
    return {
        "caseTransportRetryCount": len(scheduled),
        "caseTransportRetryEvents": [{
            "case": row.get("case"), "caseIndex": row.get("caseIndex"),
            "attempt": row.get("attempt"), "caseLogicalSequence": row.get("caseLogicalSequence"),
            "waitSeconds": row.get("waitSeconds"),
        } for row in scheduled],
        "unaccountedTransportErrors": unaccounted,
        "retryWaitCoverage": wait_ok,
        "caseAttemptCount": len(starts),
        "caseAttemptCoverage": (
            len(starts) == len(ends) == len(set(start_keys)) == len(set(end_keys))
            and set(start_keys) == set(end_keys)
        ),
    }


def transport_retry_events(logical_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in logical_rows:
        if not isinstance(cast(object, row), dict) or row.get("phase") != "response":
            continue
        response = row.get("response")
        debug = response.get("_debug") if isinstance(response, dict) else None
        if not isinstance(debug, dict):
            continue
        try:
            count = int(debug.get("transportRetryCount") or 0)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        raw_causes = debug.get("transportRetryCauses")
        causes = [str(value) for value in raw_causes] if isinstance(raw_causes, list) else []
        events.append({
            "sequence": row.get("sequence"),
            "case": row.get("case"),
            "caseIndex": row.get("caseIndex"),
            "llmStage": row.get("llmStage"),
            "count": count,
            "causes": causes,
        })
    return events


def transport_retry_summary(
    logical_rows: list[dict[str, Any]],
    *,
    logical_requests: int,
    http_requests: int,
) -> dict[str, Any]:
    events = transport_retry_events(logical_rows)
    debug_count = sum(int(event.get("count") or 0) for event in events)
    http_overhead = max(0, int(http_requests) - int(logical_requests))
    return {
        "transportRetryEvents": events,
        "transportRetryDebugCount": debug_count,
        "httpRequestOverhead": http_overhead,
        "transportRetryCount": max(debug_count, http_overhead),
        "transportRetryAccountingConsistent": debug_count == http_overhead,
    }


_JobT = TypeVar("_JobT")
_ResultT = TypeVar("_ResultT")


def run_parallel_crafts(
    run_case: Callable[[_JobT], _ResultT],
    case_jobs: Iterable[_JobT],
    *,
    parallel_crafts: int,
    on_result: Callable[[_ResultT], None] | None = None,
) -> list[_ResultT]:
    jobs = list(case_jobs)
    if not jobs:
        return []
    if parallel_crafts < 1 or parallel_crafts > 8:
        raise ValueError("parallel_crafts must be within 1..8")

    def run_and_record(job: _JobT) -> _ResultT:
        result = run_case(job)
        if on_result is not None:
            on_result(result)
        return result

    with ThreadPoolExecutor(
        max_workers=min(parallel_crafts, len(jobs)),
        thread_name_prefix="infini-live-v5-craft",
    ) as executor:
        return list(executor.map(run_and_record, jobs))


__all__ = [
    "INITIAL_AUTHOR",
    "SCOPED_REPAIR",
    "VISUAL_DIRECTOR",
    "VISUAL_REPAIR",
    "VFX_DIRECTOR",
    "VFX_REPAIR",
    "NON_AUTHOR",
    "FROZEN_LLM_STAGES",
    "REPAIR_LLM_STAGES",
    "author_stage",
    "expected_stage_temperature",
    "response_format_type",
    "is_first_author_success",
    "valid_author_call_budget",
    "should_retry_case_failure",
    "transport_retry_events",
    "transport_retry_summary",
    "CaseStageAccounting",
    "GlobalStageAccounting",
    "case_accounting_scope",
    "current_case_accounting",
    "run_parallel_crafts",
    "write_no_image_fixture_png",
    "hydrate_no_image_fixture_assets",
]
