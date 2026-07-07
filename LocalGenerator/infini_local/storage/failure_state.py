from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


ParentName = Callable[[dict[str, Any]], str]
JsonSlim = Callable[[Any, int], Any]
LogEvent = Callable[[str, str, Any], None]

SUMMARY_KEYS = ["ok", "version", "time", "stage", "error", "parents", "worldId", "pipelineLog"]


def summarize_failure(failure: dict[str, Any]) -> dict[str, Any]:
    if not failure:
        return {}
    return {k: failure.get(k) for k in SUMMARY_KEYS}


def build_combine_failure(
    *,
    app_version: str,
    stage: str,
    error: BaseException | str,
    payload: dict[str, Any] | None,
    partial_data: Any,
    pipeline_log: list[dict[str, Any]] | None,
    parent_name: ParentName,
    json_slim: JsonSlim,
) -> dict[str, Any]:
    """Build the diagnostic payload for the last failed /combine attempt.

    This module owns debug-state shaping only. It does not decide craft success,
    mutate gameplay output, or touch the runtime authoring contract.
    """
    source_payload = payload if isinstance(payload, dict) else {}
    return {
        "ok": False,
        "version": app_version,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": str(stage or "unknown"),
        "error": str(error),
        "repr": repr(error),
        "pipelineLog": list(pipeline_log or []),
        "parents": {
            "a": parent_name(source_payload.get("itemA") or {}),
            "b": parent_name(source_payload.get("itemB") or {}),
        },
        "worldId": str(source_payload.get("worldId") or ""),
        "partialData": json_slim(partial_data, 60000) if isinstance(partial_data, dict) else {},
    }


def persist_failure(cache_dir: Path, failure_file: Path, failure: dict[str, Any], log_event: LogEvent) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        failure_file.write_text(json.dumps(failure, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as write_error:
        log_event("warn", "could not write last_combine_failure.json", {"error": repr(write_error)})


def clear_persisted_failure(failure_file: Path, log_event: LogEvent, reason: str = "success") -> None:
    try:
        if failure_file.exists():
            failure_file.unlink()
    except Exception as e:
        log_event("debug", "could not clear last_combine_failure.json", {"reason": reason, "error": repr(e)})


def read_failure_summary(failure: dict[str, Any], failure_file: Path) -> dict[str, Any]:
    if failure:
        return summarize_failure(failure)
    try:
        if failure_file.exists():
            obj = json.loads(failure_file.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return summarize_failure(obj)
    except Exception:
        pass
    return {}
