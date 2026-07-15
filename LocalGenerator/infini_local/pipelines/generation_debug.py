from __future__ import annotations

"""Combine failure diagnostics, trace/debug merge, and compact debug seams."""

from copy import deepcopy
import json
import threading
from typing import Any

from infini_local.core.config_bootstrap import APP_VERSION, CACHE_DIR
from infini_local.core.item_identity_tools import name_of
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.result_models import ClampRecord, as_plain_dict
from infini_local.storage import failure_state
from infini_local.storage.trace_runtime import (
    _json_slim,
    log_event,
)


_LAST_COMBINE_FAILURE: dict[str, Any] = {}
_LAST_COMBINE_FAILURE_LOCK = threading.RLock()
LAST_COMBINE_FAILURE_FILE = CACHE_DIR / "last_combine_failure.json"


def record_combine_failure(
    stage: str,
    error: BaseException | str,
    payload: dict[str, Any] | None,
    partial_data: Any,
    pipeline_log: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Persist and attach the exact failure snapshot to its originating error."""
    failure = failure_state.build_combine_failure(
        app_version=APP_VERSION,
        stage=stage,
        error=error,
        payload=payload,
        partial_data=partial_data,
        pipeline_log=pipeline_log,
        parent_name=name_of,
        json_slim=_json_slim,
    )
    snapshot = deepcopy(failure)
    if isinstance(error, BaseException):
        try:
            setattr(error, "_infini_failure_snapshot", deepcopy(snapshot))
        except Exception:
            pass
    with _LAST_COMBINE_FAILURE_LOCK:
        _LAST_COMBINE_FAILURE.clear()
        _LAST_COMBINE_FAILURE.update(deepcopy(snapshot))
        failure_state.persist_failure(CACHE_DIR, LAST_COMBINE_FAILURE_FILE, snapshot, log_event)
    return snapshot


def clear_combine_failure(reason: str = "success") -> None:
    """Clear in-memory and persisted diagnostic state after a successful craft."""
    with _LAST_COMBINE_FAILURE_LOCK:
        _LAST_COMBINE_FAILURE.clear()
        failure_state.clear_persisted_failure(LAST_COMBINE_FAILURE_FILE, log_event, reason)


def last_combine_failure_summary() -> dict[str, Any]:
    with _LAST_COMBINE_FAILURE_LOCK:
        return deepcopy(
            failure_state.read_failure_summary(_LAST_COMBINE_FAILURE, LAST_COMBINE_FAILURE_FILE)
        )


def last_combine_failure_payload() -> dict[str, Any]:
    with _LAST_COMBINE_FAILURE_LOCK:
        if _LAST_COMBINE_FAILURE:
            return deepcopy(_LAST_COMBINE_FAILURE)
        try:
            if LAST_COMBINE_FAILURE_FILE.exists():
                payload = json.loads(LAST_COMBINE_FAILURE_FILE.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return deepcopy(payload)
        except (OSError, json.JSONDecodeError) as exc:
            log_event("debug", "could not read last_combine_failure.json", {"error": repr(exc)})
    return {"ok": True, "version": APP_VERSION, "lastFailure": None}


def compact_json_debug(value: Any, max_chars: int = 6000) -> str:
    return bounded_json_dumps(as_plain_dict(value), max_chars=max_chars)


def merge_debug_dict(target: dict[str, Any], key: str, value: dict[str, Any], *, max_chars: int = 6000) -> dict[str, Any]:
    target[key] = compact_json_debug(value, max_chars=max_chars)
    return target


def clamp_record(field: str, raw: Any, final: Any, *, kind: str, reason: str, source: str) -> dict[str, Any]:
    return ClampRecord(field=field, raw=raw, final=final, kind=kind, reason=reason, source=source).to_dict()


def append_clamp_record(report: dict[str, Any], record: ClampRecord | dict[str, Any]) -> None:
    report.setdefault("clamps", []).append(as_plain_dict(record))


__all__ = [
    "record_combine_failure",
    "clear_combine_failure",
    "last_combine_failure_summary",
    "last_combine_failure_payload",
    "LAST_COMBINE_FAILURE_FILE",
    "compact_json_debug",
    "merge_debug_dict",
    "clamp_record",
    "append_clamp_record",
]
