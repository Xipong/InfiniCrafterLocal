from __future__ import annotations

import threading
import time

import pytest

from infini_local.qa.live_stage_accounting import (
    INITIAL_AUTHOR,
    SCOPED_REPAIR,
    GlobalStageAccounting,
    case_accounting_scope,
    current_case_accounting,
    transport_retry_events,
    transport_retry_summary,
)
from infini_local.qa.parallel_crafts import run_parallel_crafts


def test_three_parallel_crafts_keep_context_and_counts_isolated() -> None:
    barrier = threading.Barrier(3)
    active = 0
    max_active = 0
    active_lock = threading.Lock()
    global_counts = GlobalStageAccounting()

    def worker(job: tuple[int, str]) -> tuple[str, dict[str, int]]:
        nonlocal active, max_active
        index, case_id = job
        with case_accounting_scope(case_id, index) as case:
            assert current_case_accounting() is case
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            try:
                barrier.wait(timeout=2)
                global_counts.begin_logical(INITIAL_AUTHOR)
                case.begin_logical(INITIAL_AUTHOR)
                if index == 2:
                    global_counts.begin_logical(SCOPED_REPAIR)
                    case.begin_logical(SCOPED_REPAIR)
                global_counts.next_http()
                time.sleep(0.03)
                return case_id, case.snapshot()
            finally:
                with active_lock:
                    active -= 1

    jobs = [(1, "first"), (2, "second"), (3, "third")]
    rows = run_parallel_crafts(worker, jobs, parallel_crafts=3)

    assert max_active == 3
    assert [case_id for case_id, _ in rows] == ["first", "second", "third"]
    assert rows[0][1] == {
        "logicalRequests": 1,
        "initialAuthorCalls": 1,
        "scopedRepairCalls": 0,
    }
    assert rows[1][1] == {
        "logicalRequests": 2,
        "initialAuthorCalls": 1,
        "scopedRepairCalls": 1,
    }
    assert rows[2][1] == rows[0][1]
    assert current_case_accounting() is None
    assert global_counts.snapshot() == {
        "logicalRequests": 4,
        "authorAttempts": 4,
        "initialAuthorCalls": 3,
        "scopedRepairCalls": 1,
        "httpRequests": 3,
    }


def test_parallel_craft_executor_rejects_invalid_concurrency_and_handles_empty_jobs() -> None:
    assert run_parallel_crafts(lambda value: value, [], parallel_crafts=3) == []
    with pytest.raises(ValueError, match="1..8"):
        run_parallel_crafts(lambda value: value, [1], parallel_crafts=0)


def test_successful_logical_transport_retries_are_fail_visible() -> None:
    rows = [
        {
            "phase": "response",
            "sequence": 7,
            "case": "potion",
            "caseIndex": 19,
            "llmStage": "initial_author",
            "response": {"_debug": {
                "transportRetryCount": 1,
                "transportRetryCauses": ["malformed_json"],
            }},
        },
    ]
    assert transport_retry_events(rows) == [{
        "sequence": 7,
        "case": "potion",
        "caseIndex": 19,
        "llmStage": "initial_author",
        "count": 1,
        "causes": ["malformed_json"],
    }]
    summary = transport_retry_summary(rows, logical_requests=1, http_requests=3)
    assert summary["transportRetryDebugCount"] == 1
    assert summary["httpRequestOverhead"] == 2
    assert summary["transportRetryCount"] == 2
    assert summary["transportRetryAccountingConsistent"] is False
