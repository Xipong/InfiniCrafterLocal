from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import generation_debug
from infini_local.pipelines.generation_debug import clear_combine_failure
from infini_local.pipelines.generation_debug import last_combine_failure_summary
from infini_local.pipelines.generation_debug import record_combine_failure
from infini_local.storage.failure_state import build_combine_failure, summarize_failure

DEBUG = generation_debug


@pytest.mark.parametrize("resume_stage", [[], {}])
def test_invalid_resume_metadata_preserves_original_failure(resume_stage) -> None:
    resume = {"available": True, "stage": resume_stage}
    error = ValueError("invalid authored output")
    failure = build_combine_failure(
        app_version="test", stage="02_validation", error=error, payload={},
        partial_data={"debug": {"generationResume": resume}}, pipeline_log=[],
        parent_name=lambda _: "parent", json_slim=lambda value, _: value,
    )
    assert failure["error"] == str(error)
    assert "generationResume" not in failure
    # Persisted/operator-provided failure metadata is checked independently of
    # the recorder, without losing the underlying failure in Studio summaries.
    summary = summarize_failure({**failure, "generationResume": resume})
    assert summary["error"] == str(error)
    assert "generationResume" not in summary


def test_clear_combine_failure_removes_stale_failure_file(monkeypatch, tmp_path) -> None:
    failure_file = tmp_path / "last_combine_failure.json"
    monkeypatch.setattr(DEBUG, "LAST_COMBINE_FAILURE_FILE", failure_file)
    clear_combine_failure("test_setup")

    record_combine_failure(
        "01_author_llm_plan",
        RuntimeError("bad json"),
        {"itemA": {"name": "A"}, "itemB": {"name": "B"}, "worldId": 123},
        {},
        [{"stage": "01_author_llm_plan", "ok": False}],
    )
    assert failure_file.exists()
    assert last_combine_failure_summary().get("stage") == "01_author_llm_plan"

    clear_combine_failure("test_success")

    assert not failure_file.exists()
    assert last_combine_failure_summary() == {}
