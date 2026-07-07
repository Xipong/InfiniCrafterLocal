from __future__ import annotations

import json
from pathlib import Path

from infini_local.storage import trace_tools


def _check_json_slim_keeps_small_json_and_truncates_large_payload() -> None:
    assert trace_tools.json_slim({"a": 1}) == {"a": 1}
    slim = trace_tools.json_slim({"text": "x" * 100}, max_chars=20)
    assert slim["_truncated"] is True
    assert "jsonPrefix" in slim


def _check_trace_event_routes_prompt_events_to_prompt_trace(tmp_path: Path) -> None:
    events = tmp_path / "pipeline.ndjson"
    prompts = tmp_path / "prompt.ndjson"
    trace_tools.trace_event(
        cache_dir=tmp_path,
        trace_prompts_enabled=True,
        trace_max_prompt_chars=1000,
        trace_file=events,
        prompt_trace_file=prompts,
        kind="prompt",
        stage="planner",
        title="Prompt",
        prompt="hello",
    )
    assert prompts.exists()
    assert not events.exists()
    row = json.loads(prompts.read_text(encoding="utf-8").splitlines()[0])
    assert row["kind"] == "prompt"
    assert row["prompt"] == "hello"


def _check_tail_ndjson_survives_bad_lines(tmp_path: Path) -> None:
    f = tmp_path / "events.ndjson"
    f.write_text('{"ok": true}\nnot json\n', encoding="utf-8")
    rows = trace_tools.tail_ndjson(f, 10)
    assert rows[0] == {"ok": True}
    assert rows[1] == {"raw": "not json"}

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_json_slim_keeps_small_json_and_truncates_large_payload',
    '_check_trace_event_routes_prompt_events_to_prompt_trace',
    '_check_tail_ndjson_survives_bad_lines'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_trace_tools_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
