from __future__ import annotations

"""Debug helpers, trace/debug merge, and compact debug seams."""

import json
from typing import Any

from infini_local.core.result_models import ClampRecord, as_plain_dict
from infini_local.pipelines.combine_pipeline import (
    clear_combine_failure,
    last_combine_failure_summary,
    record_combine_failure,
)


def compact_json_debug(value: Any, max_chars: int = 6000) -> str:
    return json.dumps(as_plain_dict(value), ensure_ascii=False, separators=(",", ":"), default=str)[:max_chars]


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
    "compact_json_debug",
    "merge_debug_dict",
    "clamp_record",
    "append_clamp_record",
]
