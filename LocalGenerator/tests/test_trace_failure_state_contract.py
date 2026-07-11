from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import generation_debug
from infini_local.pipelines.generation_debug import clear_combine_failure
from infini_local.pipelines.generation_debug import last_combine_failure_summary
from infini_local.pipelines.generation_debug import record_combine_failure

DEBUG = generation_debug


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
