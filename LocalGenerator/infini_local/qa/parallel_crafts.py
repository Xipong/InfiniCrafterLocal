from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

_JobT = TypeVar("_JobT")
_ResultT = TypeVar("_ResultT")


def run_parallel_crafts(
    run_case: Callable[[_JobT], _ResultT],
    case_jobs: Iterable[_JobT],
    *,
    parallel_crafts: int,
) -> list[_ResultT]:
    """Run bounded craft jobs concurrently while preserving input result order."""
    jobs = list(case_jobs)
    if not jobs:
        return []
    if parallel_crafts < 1 or parallel_crafts > 8:
        raise ValueError("parallel_crafts must be within 1..8")
    with ThreadPoolExecutor(
        max_workers=min(parallel_crafts, len(jobs)),
        thread_name_prefix="infini-live-craft",
    ) as executor:
        return list(executor.map(run_case, jobs))


__all__ = ["run_parallel_crafts"]
