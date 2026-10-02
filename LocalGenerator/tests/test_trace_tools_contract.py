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

def _check_combine_failure_carries_wrapped_transport_debug(tmp_path: Path, monkeypatch) -> None:
    from urllib.error import HTTPError

    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines import generation_debug
    from infini_local.storage import failure_state

    supplement = {
        "logicalCallId": "llm_1:1:call:1", "stage": "planner", "leaseId": "llm_1:1",
        "requestedApiMode": "auto", "requestedResponseFormat": "json_schema",
        "requestedReasoning": {"effort": "medium", "max_tokens": 123, "exclude": True},
        "physicalAttemptCount": 1, "physicalAttemptsDropped": 0, "rateWaitMsTotal": 0.0,
        "rateWaitReason": "none", "physicalAttemptScope": "llm_generation_http_post",
        "effectiveApiMode": "chat_completions", "effectiveResponseFormat": "json_schema",
        "effectiveReasoning": {"effort": "medium"},
        "physicalAttempts": [{
            "logicalCallId": "llm_1:1:call:1", "stage": "planner", "leaseId": "llm_1:1",
            "profileId": "llm_1", "provider": "openai_compat", "openrouterProvider": "",
            "requestedApiMode": "auto", "requestedResponseFormat": "json_schema",
            "requestedReasoning": {"effort": "medium", "max_tokens": 123, "exclude": True},
            "effectiveApiMode": "chat_completions", "effectiveResponseFormat": "json_schema",
            "effectiveReasoning": {"effort": "medium"}, "unsupportedReasoningFields": ["exclude", "max_tokens"],
            "reason": "initial", "networkStarted": True, "httpStatus": 400, "physicalAttemptIndex": 1,
            "rateWaitMs": 0.0, "rateWaitReason": "none", "connectMs": None,
            "openMs": 1.0, "readMs": 2.0, "deadlineRemainingMs": 900.0, "errorType": "HTTPError",
        }],
    }
    from email.message import Message

    cause = HTTPError("http://127.0.0.1/offline", 400, "Bad Request", Message(), None)
    setattr(cause, "_infini_transport_debug", supplement)
    inner = PlannerUnavailable("Author failed")
    inner.__cause__ = cause
    error = RuntimeError("combine failed")
    error.__cause__ = inner
    failure_file = tmp_path / "last_combine_failure.json"
    monkeypatch.setattr(generation_debug, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(generation_debug, "LAST_COMBINE_FAILURE_FILE", failure_file)
    monkeypatch.setattr(generation_debug, "_LAST_COMBINE_FAILURE", {})

    snapshot = generation_debug.record_combine_failure(
        "author", error, {"itemA": {"name": "A"}, "itemB": {"name": "B"}, "worldId": "offline"},
        {"unchanged": True}, [{"stage": "author", "ok": False}],
    )
    assert snapshot["transportDebug"] == supplement
    assert getattr(error, "_infini_failure_snapshot") == snapshot
    persisted = json.loads(failure_file.read_text(encoding="utf-8"))
    assert persisted == snapshot
    assert generation_debug.last_combine_failure_summary()["transportDebug"] == supplement
    assert failure_state.read_failure_summary({}, failure_file)["transportDebug"] == supplement
    assert snapshot["parents"] == {"a": "A", "b": "B"} and snapshot["partialData"] == {"unchanged": True}
    supplement["physicalAttempts"][0]["httpStatus"] = 500
    assert snapshot["transportDebug"]["physicalAttempts"][0]["httpStatus"] == 400


def _check_combine_failure_transport_debug_is_bounded_allowlisted(tmp_path: Path) -> None:
    from email.message import Message
    from urllib.error import HTTPError

    from infini_local.storage import failure_state

    class PrivateValue:
        def __str__(self):
            raise AssertionError("private diagnostics must not be stringified")

    private = "PRIVATE_BODY_PROMPT_CREDENTIAL"
    row = {
        "physicalAttemptIndex": 1, "httpStatus": 400, "provider": PrivateValue(),
        "errorType": "HTTPError", "openMs": float("inf"), "connectMs": None,
        "requestedReasoning": {"effort": "medium", "exclude": True, "prompt": private},
        "effectiveReasoning": {"max_tokens": 10**1000, "enabled": True, "Authorization": private},
        "unsupportedReasoningFields": ["exclude", "max_tokens", private] * 10,
        "body": private, "messages": [private], "headers": {"Authorization": private},
    }
    supplement = {
        "stage": "x" * 1000, "physicalAttemptCount": 20, "physicalAttemptsDropped": 4,
        "rateWaitMsTotal": float("nan"), "requestedApiMode": {"prompt": private},
        "effectiveReasoning": None, "requestedReasoning": {"max_tokens": True, "api_key": private},
        "physicalAttempts": [row] * 20, "rawBody": private, "prompt": private, "api_key": private,
    }
    supplement["unknownCycle"] = supplement
    error = HTTPError("http://127.0.0.1/offline", 400, "Bad Request", Message(), None)
    setattr(error, "_infini_body", private)
    setattr(error, "_infini_transport_debug", supplement)
    snapshot = failure_state.build_combine_failure(
        app_version="offline", stage="author", error=error, payload=None, partial_data=None,
        pipeline_log=None, parent_name=lambda _: "", json_slim=trace_tools.json_slim,
    )
    projected = snapshot["transportDebug"]
    assert set(projected).isdisjoint({"rawBody", "prompt", "api_key", "unknownCycle"})
    assert private not in json.dumps(projected, allow_nan=False)
    assert projected == {
        "stage": "x" * 160, "physicalAttemptCount": 20, "physicalAttemptsDropped": 4,
        "effectiveReasoning": None, "requestedReasoning": {},
        "physicalAttempts": [{
            "physicalAttemptIndex": 1, "httpStatus": 400, "errorType": "HTTPError", "connectMs": None,
            "requestedReasoning": {"effort": "medium", "exclude": True},
            "effectiveReasoning": {"enabled": True}, "unsupportedReasoningFields": ["exclude", "max_tokens"],
        }] * 16,
    }
    failure_file = tmp_path / "last_combine_failure.json"
    warnings = []
    failure_state.persist_failure(tmp_path, failure_file, snapshot, lambda *args: warnings.append(args))
    persisted = json.loads(failure_file.read_text(encoding="utf-8"))
    assert persisted == snapshot and not warnings
    assert private not in json.dumps(persisted)
    assert failure_state.summarize_failure({"ok": False, "transportDebug": supplement})["transportDebug"] == projected


def _check_combine_failure_transport_cause_traversal_is_safe() -> None:
    from email.message import Message
    from urllib.error import HTTPError

    from infini_local.storage import failure_state

    supplement = {"physicalAttemptCount": 1, "physicalAttempts": [], "physicalAttemptScope": "llm_generation_http_post"}
    direct = HTTPError("http://127.0.0.1/offline", 400, "Bad Request", Message(), None)
    setattr(direct, "_infini_transport_debug", supplement)
    malformed = RuntimeError("malformed supplement")
    setattr(malformed, "_infini_transport_debug", ["not metadata"])
    malformed.__cause__ = direct
    nearest = RuntimeError("nearest supplement")
    setattr(nearest, "_infini_transport_debug", {"physicalAttemptCount": 2})
    nearest.__cause__ = direct
    cycle_a, cycle_b = RuntimeError("cycle a"), RuntimeError("cycle b")
    cycle_a.__cause__, cycle_b.__cause__ = cycle_b, cycle_a
    bounded = direct
    for _ in range(15):
        wrapper = RuntimeError("bounded wrapper")
        wrapper.__cause__ = bounded
        bounded = wrapper
    beyond = RuntimeError("beyond bound")
    beyond.__cause__ = bounded
    context_only = RuntimeError("implicit context is not explicit cause")
    context_only.__context__ = direct

    class UnreadableSupplement(RuntimeError):
        @property
        def _infini_transport_debug(self):
            raise RuntimeError("unreadable optional metadata")

    unreadable = UnreadableSupplement("wrapper")
    unreadable.__cause__ = direct
    cases = [
        ("direct", direct, supplement), ("malformed wrapper", malformed, supplement),
        ("nearest", nearest, {"physicalAttemptCount": 2}), ("cycle", cycle_a, None),
        ("depth boundary", bounded, supplement), ("beyond depth", beyond, None),
        ("no supplement", RuntimeError("plain"), None), ("string error", "plain", None),
        ("context only", context_only, None), ("unreadable wrapper", unreadable, supplement),
    ]
    for label, error, expected in cases:
        snapshot = failure_state.build_combine_failure(
            app_version="offline", stage="author", error=error, payload=None, partial_data=None,
            pipeline_log=None, parent_name=lambda _: "", json_slim=trace_tools.json_slim,
        )
        assert snapshot.get("transportDebug") == expected, label
        summary = failure_state.summarize_failure(snapshot)
        assert summary.get("transportDebug") == expected, label
        if expected is None:
            assert "transportDebug" not in snapshot and "transportDebug" not in summary, label
    cycle_b.__cause__ = direct
    assert failure_state.build_combine_failure(
        app_version="offline", stage="author", error=cycle_a, payload=None, partial_data=None,
        pipeline_log=None, parent_name=lambda _: "", json_slim=trace_tools.json_slim,
    )["transportDebug"] == supplement


# One collected item; local checks are discovered and isolated in source order.
def test_trace_tools_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
