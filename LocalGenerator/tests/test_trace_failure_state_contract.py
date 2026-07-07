from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
COMBINE = server.combine_pipeline


def test_clear_combine_failure_removes_stale_failure_file(monkeypatch, tmp_path) -> None:
    failure_file = tmp_path / "last_combine_failure.json"
    monkeypatch.setattr(COMBINE, "LAST_COMBINE_FAILURE_FILE", failure_file)
    monkeypatch.setattr(COMBINE, "LAST_COMBINE_FAILURE", {})

    server.record_combine_failure(
        "01_author_llm_plan",
        RuntimeError("bad json"),
        {"itemA": {"name": "A"}, "itemB": {"name": "B"}, "worldId": 123},
        {},
        [{"stage": "01_author_llm_plan", "ok": False}],
    )
    assert failure_file.exists()
    assert server.last_combine_failure_summary().get("stage") == "01_author_llm_plan"

    server.clear_combine_failure("test_success")

    assert not failure_file.exists()
    assert server.last_combine_failure_summary() == {}
