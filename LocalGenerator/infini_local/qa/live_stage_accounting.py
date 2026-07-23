from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
from typing import Any, Iterator

INITIAL_AUTHOR = "initial_author"
SCOPED_REPAIR = "scoped_repair"
NON_AUTHOR = "non_author"

_INITIAL_USER_STAGE = "recipe_context"
_REPAIR_USER_STAGE = "final_wire_compiler"
_AUTHOR_SYSTEM_STAGE = "item_author_contract"
_INITIAL_SCHEMA = "infini_author_item_v3"
_REPAIR_SCHEMA = "infini_author_item_scoped_repair_v1"


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
    transport_failures_ignored: int = 0

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
        return {
            key: int(self.snapshot()[key]) - int(before.get(key, 0))
            for key in ("logicalRequests", "initialAuthorCalls", "scopedRepairCalls")
        }


@dataclass
class GlobalStageAccounting:
    logical_requests: int = 0
    author_attempts: int = 0
    initial_author_calls: int = 0
    scoped_repair_calls: int = 0
    http_requests: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def next_http(self) -> int:
        with self._lock:
            self.http_requests += 1
            return self.http_requests

    def begin_logical(self, stage: str) -> dict[str, int | None]:
        with self._lock:
            self.logical_requests += 1
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
            }

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "logicalRequests": self.logical_requests,
                "authorAttempts": self.author_attempts,
                "initialAuthorCalls": self.initial_author_calls,
                "scopedRepairCalls": self.scoped_repair_calls,
                "httpRequests": self.http_requests,
            }


_CURRENT_CASE_ACCOUNTING: ContextVar[CaseStageAccounting | None] = ContextVar(
    "infini_live_case_accounting",
    default=None,
)


@contextmanager
def case_accounting_scope(case_id: str, case_index: int) -> Iterator[CaseStageAccounting]:
    state = CaseStageAccounting(case_id=case_id, case_index=case_index)
    token = _CURRENT_CASE_ACCOUNTING.set(state)
    try:
        yield state
    finally:
        _CURRENT_CASE_ACCOUNTING.reset(token)


def current_case_accounting() -> CaseStageAccounting | None:
    return _CURRENT_CASE_ACCOUNTING.get()


def _strict_schema_name(payload: dict[str, Any]) -> str:
    response_format = payload.get("response_format")
    if not isinstance(response_format, dict):
        return ""
    schema = response_format.get("json_schema")
    if not isinstance(schema, dict):
        return ""
    return str(schema.get("name") or "").strip()


def author_stage(payload: dict[str, Any]) -> str:
    """Classify author calls from source-owned transport metadata, never prose."""
    if not isinstance(payload, dict):
        return NON_AUTHOR
    messages = payload.get("messages")
    rows = messages if isinstance(messages, list) else []
    system_names = {
        str(row.get("name") or "").strip()
        for row in rows
        if isinstance(row, dict) and row.get("role") == "system"
    }
    user_names = {
        str(row.get("name") or "").strip()
        for row in rows
        if isinstance(row, dict) and row.get("role") == "user"
    }
    if _AUTHOR_SYSTEM_STAGE in system_names:
        if _INITIAL_USER_STAGE in user_names and _REPAIR_USER_STAGE not in user_names:
            return INITIAL_AUTHOR
        if _REPAIR_USER_STAGE in user_names and _INITIAL_USER_STAGE not in user_names:
            return SCOPED_REPAIR

    schema_name = _strict_schema_name(payload)
    if schema_name == _INITIAL_SCHEMA:
        return INITIAL_AUTHOR
    if schema_name == _REPAIR_SCHEMA:
        return SCOPED_REPAIR
    return NON_AUTHOR


def is_first_author_success(*, initial_calls: int, repair_calls: int) -> bool:
    return initial_calls == 1 and repair_calls == 0


def valid_author_call_budget(*, initial_calls: int, repair_calls: int) -> bool:
    return initial_calls == 1 and 0 <= repair_calls <= 1


def should_retry_case_failure(*, had_logical_error: bool, low_level_transport_error: bool) -> bool:
    """Retry only a confirmed transport failure from the logical LLM boundary."""
    return had_logical_error and low_level_transport_error


def transport_retry_events(logical_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose successful logical calls that needed hidden low-level HTTP retries."""
    events: list[dict[str, Any]] = []
    for row in logical_rows:
        if not isinstance(row, dict) or row.get("phase") != "response":
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


__all__ = [
    "INITIAL_AUTHOR",
    "SCOPED_REPAIR",
    "NON_AUTHOR",
    "author_stage",
    "is_first_author_success",
    "valid_author_call_budget",
    "should_retry_case_failure",
    "transport_retry_events",
    "transport_retry_summary",
    "CaseStageAccounting",
    "GlobalStageAccounting",
    "case_accounting_scope",
    "current_case_accounting",
]
