from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from infini_local.storage import trace_tools


def _append_from_process(path: str, worker: int) -> None:
    for sequence in range(80):
        trace_tools.append_ndjson(
            path,
            {"worker": worker, "sequence": sequence, "payload": "x" * 48},
            max_bytes=1200,
            backup_count=3,
        )


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


def _check_serialized_ndjson_append_and_rotation(tmp_path: Path) -> None:
    trace_file = tmp_path / "concurrent.ndjson"

    def append(worker: int) -> None:
        for sequence in range(40):
            trace_tools.append_ndjson(
                trace_file,
                {"worker": worker, "sequence": sequence, "payload": "x" * 48},
                max_bytes=700,
                backup_count=2,
            )

    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(append, range(8)))

    files = [trace_file, trace_file.with_name("concurrent.ndjson.1"), trace_file.with_name("concurrent.ndjson.2")]
    persisted = [path for path in files if path.exists()]
    assert len(persisted) >= 2
    for path in persisted:
        raw_lines = path.read_bytes().splitlines()
        assert raw_lines
        for line in raw_lines:
            assert isinstance(json.loads(line.decode("utf-8")), dict)


def _check_process_safe_ndjson_append_and_rotation(tmp_path: Path) -> None:
    trace_file = tmp_path / "multiprocess.ndjson"
    workers = [multiprocessing.Process(target=_append_from_process, args=(str(trace_file), worker)) for worker in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0

    persisted = [trace_file, *(trace_file.with_name(f"multiprocess.ndjson.{index}") for index in range(1, 4))]
    assert any(path.exists() for path in persisted)
    for path in persisted:
        if not path.exists():
            continue
        for line in path.read_bytes().splitlines():
            assert isinstance(json.loads(line.decode("utf-8")), dict)


def _check_tail_and_recovery_ignore_broken_suffix(tmp_path: Path) -> None:
    trace_file = tmp_path / "broken.ndjson"
    trace_file.write_bytes(
        b'{"sequence":1}\n'
        b'{"sequence":2}\n'
        b'not json\n'
        b'\x00invalid trailing bytes\n'
        b'{"partial":'
    )

    assert trace_tools.tail_ndjson(trace_file, 10) == [{"sequence": 1}, {"sequence": 2}]
    assert trace_tools.recover_ndjson(trace_file) is False
    assert trace_file.read_bytes() == b'{"sequence":1}\n{"sequence":2}\n'
    assert trace_tools.tail_ndjson(trace_file, 10) == [{"sequence": 1}, {"sequence": 2}]


def _check_recovery_reads_from_tail_without_materializing_whole_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    trace_file = tmp_path / "tail-only.ndjson"
    trace_file.write_bytes(b'{"sequence":1}\n{"sequence":2}\n\x00broken-tail')

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError("NDJSON recovery must not materialize the whole file")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    assert trace_tools.recover_ndjson(trace_file) is True
    with trace_file.open("rb") as handle:
        assert handle.read() == b'{"sequence":1}\n{"sequence":2}\n'


def _check_trace_storage_is_write_only_telemetry(tmp_path: Path) -> None:
    trace_file = tmp_path / "pipeline.ndjson"
    prompt_file = tmp_path / "prompt.ndjson"
    trace_tools.trace_event(
        cache_dir=tmp_path,
        trace_prompts_enabled=True,
        trace_max_prompt_chars=1000,
        trace_file=trace_file,
        prompt_trace_file=prompt_file,
        kind="step",
        stage="release",
        title="release telemetry",
        payload={"releaseTelemetry": {"build": "internal-only"}},
    )
    assert "releaseTelemetry" in trace_file.read_text(encoding="utf-8")
    assert not prompt_file.exists()

# One collected item; local checks are discovered and isolated in source order.
def test_trace_tools_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
