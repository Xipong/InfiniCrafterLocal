from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import threading
from typing import Any, Callable

import pytest

LIVE_GENERATION = Path(__file__).resolve().parents[1] / "live-generation"
PROJECTS_ROOT = Path(__file__).resolve().parents[2]
PROJECT = (
    PROJECTS_ROOT
    if (PROJECTS_ROOT / "LocalGenerator/infini_local").is_dir()
    else next(
        path for path in PROJECTS_ROOT.iterdir()
        if path.is_dir() and (path / "LocalGenerator/infini_local").is_dir()
    )
)
LOCAL_GENERATOR = PROJECT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))
if str(LIVE_GENERATION) not in sys.path:
    sys.path.insert(0, str(LIVE_GENERATION))

from live20_support_v5 import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    FROZEN_LLM_STAGES,
    GlobalStageAccounting,
    INITIAL_AUTHOR,
    NON_AUTHOR,
    SCOPED_REPAIR,
    VFX_DIRECTOR,
    VFX_REPAIR,
    VISUAL_DIRECTOR,
    VISUAL_REPAIR,
    author_stage,
    expected_stage_temperature,
    response_format_type,
    run_parallel_crafts,
    transport_retry_summary,
    select_case_routes,
)


from toolbox.infini_toolbox import discover_project


def test_in_repo_toolbox_discovers_its_canonical_project() -> None:
    assert discover_project() == PROJECT.resolve()


def test_bundled_parent_dump_matches_the_original_terraria_snapshot() -> None:
    source = PROJECT / "toolbox/fixtures/items.jsonl"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "62b64ac70eaad27004e4d4e006c1bfb6ba44775b98a216ad2aaa4afaebb20e06"
    )
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    assert len(rows) == 39
    assert len({row["internalName"] for row in rows}) == len(rows)
    assert {row["sourceMod"] for row in rows} == {"Terraria"}


def test_selected_live20_cases_do_not_require_unselected_dump_parents() -> None:
    routes = [("accept", "A", "B"), ("extra", "NotInDump", "OtherMissing")]
    assert select_case_routes(routes, {"accept"}) == [("accept", "A", "B")]
    with pytest.raises(ValueError, match="unknown case IDs"):
        select_case_routes(routes, {"absent"})


def _payload(*names: str, wire_stage: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"messages": [{"name": name} for name in names]}
    if wire_stage:
        payload["_infini_stage"] = wire_stage
    return payload


def test_classifies_every_frozen_live_stage_from_source_owned_metadata() -> None:
    assert author_stage(_payload("item_author_contract", wire_stage="planner")) == INITIAL_AUTHOR
    assert author_stage(_payload("author_repair_contract", wire_stage="author_repair")) == SCOPED_REPAIR
    assert author_stage(_payload("visual_director_contract", "visual_director_context")) == VISUAL_DIRECTOR
    assert author_stage(_payload("visual_repair_contract", "visual_repair_context")) == VISUAL_REPAIR
    assert author_stage(_payload("vfx_director_contract", "vfx_director_context")) == VFX_DIRECTOR
    assert author_stage(_payload("vfx_repair_contract", "vfx_repair_context")) == VFX_REPAIR
    assert author_stage(_payload("unknown_contract")) == NON_AUTHOR


def test_temperature_freeze_covers_directors_and_repairs() -> None:
    for stage in FROZEN_LLM_STAGES:
        expected = 0.12 if stage in {SCOPED_REPAIR, VISUAL_REPAIR, VFX_REPAIR} else 0.5
        assert expected_stage_temperature(
            stage,
            director_temperature=0.5,
            repair_temperature=0.12,
        ) == expected

    assert expected_stage_temperature(
        VFX_DIRECTOR, director_temperature=0.5, repair_temperature=0.12,
        vfx_director_temperature=0.34,
    ) == 0.34
    assert expected_stage_temperature(
        VFX_REPAIR, director_temperature=0.5, repair_temperature=0.12,
        vfx_director_temperature=0.34,
    ) == 0.12

    with pytest.raises(ValueError, match="unclassified LLM stage"):
        expected_stage_temperature(
            NON_AUTHOR,
            director_temperature=0.5,
            repair_temperature=0.12,
        )


def test_response_format_type_is_read_from_each_logical_payload() -> None:
    assert response_format_type({"response_format": {"type": "json_object"}}) == "json_object"
    assert response_format_type({"response_format": {"type": "json_schema", "json_schema": {}}}) == "json_schema"
    assert response_format_type({}) == ""


def test_failed_logical_call_hidden_retry_is_caught_by_physical_http_overhead() -> None:
    summary = transport_retry_summary(
        [{
            "sequence": 1,
            "case": "failed_case",
            "caseIndex": 0,
            "llmStage": INITIAL_AUTHOR,
            "phase": "error",
            "transportError": True,
        }],
        logical_requests=1,
        http_requests=2,
    )

    assert summary["transportRetryDebugCount"] == 0
    assert summary["httpRequestOverhead"] == 1
    assert summary["transportRetryCount"] == 1
    assert summary["transportRetryAccountingConsistent"] is False


def test_parallel_runner_persists_a_completed_case_before_earlier_sibling_finishes() -> None:
    release_held = threading.Event()
    ready_saved = threading.Event()
    finished: list[str] = []

    def worker(case: str) -> str:
        if case == "held":
            assert release_held.wait(timeout=2)
        return case

    on_result: Callable[[str], bool | None] = lambda result: ready_saved.set() if result == "ready" else None

    def run() -> None:
        finished.extend(run_parallel_crafts(
            worker, ["held", "ready"], parallel_crafts=2,
            on_result=on_result,
        ))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert ready_saved.wait(timeout=2), "completed case was not recorded while its sibling was in flight"
        assert thread.is_alive()
    finally:
        release_held.set()
        thread.join(timeout=2)
    assert finished == ["held", "ready"]


def test_global_accounting_proves_three_active_crafts_and_balanced_nested_calls() -> None:
    accounting = GlobalStageAccounting()
    assert accounting.begin_craft()["activeCrafts"] == 1
    assert accounting.begin_craft()["activeCrafts"] == 2
    assert accounting.begin_craft()["activeCrafts"] == 3
    logical = accounting.begin_logical(INITIAL_AUTHOR)
    http = accounting.begin_http()
    assert logical["activeLogical"] == 1
    assert http["activeHttp"] == 1
    assert accounting.end_http()["activeHttp"] == 0
    assert accounting.end_logical()["activeLogical"] == 0
    accounting.end_craft()
    accounting.end_craft()
    final = accounting.end_craft()
    assert final["activeCrafts"] == 0
    snapshot = accounting.snapshot()
    assert snapshot["peakActiveCrafts"] == 3
    assert snapshot["peakActiveLogical"] == 1
    assert snapshot["peakActiveHttp"] == 1


def test_parallel_runner_reaches_three_simultaneous_crafts() -> None:
    accounting = GlobalStageAccounting()
    barrier = threading.Barrier(3)

    def worker(job: int) -> int:
        accounting.begin_craft()
        accounting.begin_logical(INITIAL_AUTHOR)
        accounting.begin_http()
        try:
            barrier.wait(timeout=2)
            return job
        finally:
            accounting.end_http()
            accounting.end_logical()
            accounting.end_craft()

    assert run_parallel_crafts(worker, [1, 2, 3], parallel_crafts=3) == [1, 2, 3]
    snapshot = accounting.snapshot()
    assert snapshot["peakActiveCrafts"] == 3
    assert snapshot["peakActiveLogical"] == 3
    assert snapshot["peakActiveHttp"] == 3
    assert snapshot["activeCrafts"] == 0
    assert snapshot["activeLogical"] == 0
    assert snapshot["activeHttp"] == 0
